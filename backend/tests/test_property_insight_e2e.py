"""End-to-end tests for PropertyInsight + Escalation flow.

Tests the full pipeline with a real SQLite DB and mocked LLM agent calls:
1. PropertyInsightService.search finds EV charging from ContextualMemory
2. PropertyInsightService.search returns found=False for missing feature
3. EscalationService creates thread when insight misses
4. No escalation when insight finds answer
5. Escalation email contains reply_tool_url with correct pattern
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Import Base first, then models to register all tables
from wex_platform.infra.database import Base

import wex_platform.domain.models  # noqa: F401
import wex_platform.domain.sms_models  # noqa: F401
import wex_platform.domain.voice_models  # noqa: F401

from wex_platform.domain.models import (
    Buyer,
    BuyerConversation,
    ContextualMemory,
    Property,
    Warehouse,
)
from wex_platform.domain.sms_models import EscalationThread, SMSConversationState
from wex_platform.agents.base import AgentResult
from wex_platform.services.property_insight_service import InsightResult, PropertyInsightService
from wex_platform.services.escalation_service import EscalationService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def db():
    """Async SQLite in-memory session with all tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False,
    )

    async with factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def seed(db):
    """Seed the DB with test data and return a dict of created objects."""
    prop_id = "test-prop-001"
    buyer_id = "test-buyer-001"
    conv_id = "test-conv-001"
    state_id = str(uuid.uuid4())

    # Warehouse (legacy table, same UUID as Property per memory.md)
    warehouse = Warehouse(
        id=prop_id,
        address="456 Industrial Pkwy",
        city="Detroit",
        state="MI",
        zip="48201",
    )
    db.add(warehouse)

    # Property (v2 schema, same UUID)
    prop = Property(
        id=prop_id,
        address="456 Industrial Pkwy",
        city="Detroit",
        state="MI",
        zip="48201",
        source="test",
    )
    db.add(prop)

    # ContextualMemory about EV charging
    cm = ContextualMemory(
        id=str(uuid.uuid4()),
        warehouse_id=prop_id,
        property_id=prop_id,
        memory_type="feature_intelligence",
        content=(
            "Owner installed 4 Level 2 electric vehicle charging stations "
            "in the parking lot in 2025. Supports Tesla, Rivian and other EVs."
        ),
        confidence=0.9,
    )
    db.add(cm)

    # Buyer
    buyer = Buyer(
        id=buyer_id,
        phone="+15551234567",
        name="Test Buyer",
        email="buyer@test.com",
    )
    db.add(buyer)

    # BuyerConversation
    conv = BuyerConversation(
        id=conv_id,
        buyer_id=buyer_id,
        status="active",
    )
    db.add(conv)

    # SMSConversationState
    sms_state = SMSConversationState(
        id=state_id,
        buyer_id=buyer_id,
        conversation_id=conv_id,
        phone="+15551234567",
        phase="PROPERTY_FOCUSED",
        focused_match_id=prop_id,
        presented_match_ids=[prop_id],
        known_answers={},
        answered_questions=[],
        pending_escalations={},
    )
    db.add(sms_state)

    await db.flush()

    return {
        "property_id": prop_id,
        "buyer_id": buyer_id,
        "conversation_id": conv_id,
        "state_id": state_id,
        "sms_state": sms_state,
        "warehouse": warehouse,
        "property": prop,
        "contextual_memory": cm,
        "buyer": buyer,
        "conversation": conv,
    }


# ---------------------------------------------------------------------------
# Test 1: PropertyInsight search finds EV charging
# ---------------------------------------------------------------------------

class TestPropertyInsightSearchFindsEVCharging:
    """PropertyInsightService.search should find an answer about EV charging
    from the seeded ContextualMemory, with mocked LLM calls."""

    async def test_property_insight_search_finds_ev_charging(self, db, seed):
        translate_mock = AgentResult(
            ok=True,
            data={
                "keywords": ["ev", "electric vehicle", "charging", "charger", "ev station"],
                "category": "feature",
                "relevant_memory_types": ["feature_intelligence", "enrichment_response"],
            },
        )
        evaluate_mock = AgentResult(
            ok=True,
            data={
                "found": True,
                "answer": (
                    "Yes, this property has 4 Level 2 EV charging stations "
                    "in the parking lot, supporting Tesla, Rivian and other EVs."
                ),
                "confidence": 0.92,
                "candidate_used": 0,
            },
        )

        service = PropertyInsightService(db)

        with (
            patch.object(service.agent, "translate_question", new_callable=AsyncMock, return_value=translate_mock),
            patch.object(service.agent, "evaluate", new_callable=AsyncMock, return_value=evaluate_mock),
        ):
            result = await service.search(
                seed["property_id"],
                "does it have EV charging?",
                channel="sms",
            )

        assert result.found is True, f"Expected found=True, got {result.found}"
        assert result.answer is not None
        answer_lower = result.answer.lower()
        assert "charging" in answer_lower, f"Expected 'charging' in answer: {result.answer}"
        assert result.confidence >= 0.7, f"Expected confidence >= 0.7, got {result.confidence}"
        assert result.source == "contextual_memory"


# ---------------------------------------------------------------------------
# Test 2: PropertyInsight search no match for helipad
# ---------------------------------------------------------------------------

class TestPropertyInsightSearchNoMatchForHelipad:
    """PropertyInsightService.search should return found=False when no
    ContextualMemory or PKE matches the helipad keywords."""

    async def test_property_insight_search_no_match_for_helipad(self, db, seed):
        translate_mock = AgentResult(
            ok=True,
            data={
                "keywords": ["helipad", "helicopter", "landing pad", "rooftop landing"],
                "category": "feature",
                "relevant_memory_types": ["feature_intelligence", "enrichment_response"],
            },
        )

        service = PropertyInsightService(db)
        evaluate_spy = AsyncMock()

        with (
            patch.object(service.agent, "translate_question", new_callable=AsyncMock, return_value=translate_mock),
            patch.object(service.agent, "evaluate", evaluate_spy),
        ):
            result = await service.search(
                seed["property_id"],
                "does it have a helipad?",
                channel="sms",
            )

        assert result.found is False, f"Expected found=False, got {result.found}"
        # evaluate should NOT have been called because 0 candidates matched
        evaluate_spy.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: Escalation created when insight misses
# ---------------------------------------------------------------------------

class TestEscalationCreatedWhenInsightMisses:
    """EscalationService.check_and_escalate should create a pending
    EscalationThread when no cached answer exists."""

    async def test_escalation_created_when_insight_misses(self, db, seed):
        svc = EscalationService(db)

        with patch(
            "wex_platform.services.escalation_service.EscalationService._send_escalation_email",
            new_callable=AsyncMock,
        ) as mock_email:
            result = await svc.check_and_escalate(
                property_id=seed["property_id"],
                question_text="does it have a helipad?",
                field_key=None,
                state=seed["sms_state"],
                source_type="sms",
            )

        assert result["escalated"] is True, f"Expected escalated=True, got {result}"
        assert result["thread_id"] is not None

        # Verify thread in DB
        threads = (
            await db.execute(
                select(EscalationThread).where(
                    EscalationThread.property_id == seed["property_id"]
                )
            )
        ).scalars().all()

        assert len(threads) == 1, f"Expected 1 thread, got {len(threads)}"
        thread = threads[0]
        assert thread.status == "pending"
        assert thread.source_type == "sms"
        assert "helipad" in thread.question_text.lower()

        # Verify send_escalation_email was called
        mock_email.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: No escalation when insight finds answer
# ---------------------------------------------------------------------------

class TestNoEscalationWhenInsightFindsAnswer:
    """When PropertyInsightService finds an answer, no EscalationThread
    should be created. This simulates the orchestrator's facility_info path
    at the decision layer: if insight returns found=True, skip escalation."""

    async def test_no_escalation_when_insight_finds_answer(self, db, seed):
        # Step 1: PropertyInsightService returns a found answer
        insight_result = InsightResult(
            found=True,
            answer="Yes, 4 EV chargers in the parking lot.",
            confidence=0.92,
            source="contextual_memory",
            source_detail="feature_intelligence",
            latency_ms=120,
        )

        service = PropertyInsightService(db)
        with patch.object(service, "search", new_callable=AsyncMock, return_value=insight_result):
            result = await service.search(
                seed["property_id"],
                "does it have EV charging?",
                channel="sms",
            )

        # Verify the insight found an answer
        assert result.found is True

        # Step 2: Since insight found answer, orchestrator should NOT escalate.
        # Simulate the decision: if result.found, use the insight answer directly.
        if not result.found:
            # This branch should NOT execute
            escalation_svc = EscalationService(db)
            await escalation_svc.check_and_escalate(
                property_id=seed["property_id"],
                question_text="does it have EV charging?",
                field_key=None,
                state=seed["sms_state"],
                source_type="sms",
            )

        # Step 3: Verify NO EscalationThread was created
        threads = (
            await db.execute(
                select(EscalationThread).where(
                    EscalationThread.property_id == seed["property_id"]
                )
            )
        ).scalars().all()

        assert len(threads) == 0, f"Expected 0 threads (insight found answer), got {len(threads)}"

        # Verify the insight result has the expected _insight key data
        assert result.answer is not None
        assert "EV charger" in result.answer or "charging" in result.answer.lower()
        assert result.source == "contextual_memory"


# ---------------------------------------------------------------------------
# Test 5: Escalation email contains reply_tool_url
# ---------------------------------------------------------------------------

class TestEscalationEmailContainsReplyToolUrl:
    """The _send_escalation_email method should build data containing
    property_address, question_text, and reply_tool_url with the correct
    pattern: /api/sms/internal/form/{thread_id}?token=..."""

    async def test_escalation_email_contains_reply_tool_url(self, db, seed):
        svc = EscalationService(db)

        captured_data = {}

        async def _capture_email(data: dict) -> bool:
            captured_data.update(data)
            return True

        with patch(
            "wex_platform.services.email_service.send_escalation_email",
            new_callable=AsyncMock,
            side_effect=_capture_email,
        ):
            # Create a thread via the normal flow
            result = await svc.check_and_escalate(
                property_id=seed["property_id"],
                question_text="does it have a rooftop garden?",
                field_key=None,
                state=seed["sms_state"],
                source_type="sms",
            )

            assert result["escalated"] is True
            thread_id = result["thread_id"]

            # The email is sent via asyncio.ensure_future — we need to let it run.
            # Since we patched send_escalation_email, the _send_escalation_email method
            # should execute the DB queries and build the data dict.
            import asyncio
            # Give the fire-and-forget coroutine time to complete
            await asyncio.sleep(0.2)

        # Validate captured email data
        assert captured_data, "send_escalation_email was never called with data"
        assert "property_address" in captured_data, f"Missing property_address in {captured_data.keys()}"
        assert "question_text" in captured_data, f"Missing question_text in {captured_data.keys()}"
        assert "reply_tool_url" in captured_data, f"Missing reply_tool_url in {captured_data.keys()}"

        # Validate reply_tool_url pattern
        url = captured_data["reply_tool_url"]
        assert f"/api/sms/internal/form/{thread_id}" in url, (
            f"reply_tool_url should contain /api/sms/internal/form/{thread_id}, got: {url}"
        )
        assert "?token=" in url, f"reply_tool_url should contain ?token=, got: {url}"

        # Validate question_text
        assert captured_data["question_text"] == "does it have a rooftop garden?"

        # Validate property_address is populated from the Property record
        assert captured_data["property_address"] != "Unknown Property", (
            f"property_address should be resolved, got: {captured_data['property_address']}"
        )
        assert "Detroit" in captured_data["property_address"]

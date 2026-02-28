"""Tests for the BuyerSMSOrchestrator — Tier 2 integration with mocked LLM agents.

All LLM agents (CriteriaAgent, ResponseAgent, PolisherAgent) are mocked.
Database interactions use the real async SQLite fixture.
"""

import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from wex_platform.agents.sms.contracts import CriteriaPlan, MessageInterpretation
from wex_platform.domain.models import Buyer, BuyerConversation
from wex_platform.domain.sms_models import SMSConversationState
from wex_platform.services.buyer_sms_orchestrator import BuyerSMSOrchestrator


# Patch targets — these are the source modules (lazy-imported inside process_message)
_CRITERIA = "wex_platform.agents.sms.criteria_agent.CriteriaAgent"
_RESPONSE = "wex_platform.agents.sms.response_agent.ResponseAgent"
_POLISHER = "wex_platform.agents.sms.polisher_agent.PolisherAgent"


# ---------------------------------------------------------------------------
# Helper: create minimal state objects in test DB
# ---------------------------------------------------------------------------

async def make_test_context(db_session, *, phase="INTAKE", turn=0, presented_match_ids=None,
                            criteria_snapshot=None, focused_match_id=None):
    """Create a Buyer + BuyerConversation + SMSConversationState and return them."""
    buyer = Buyer(
        id=str(uuid.uuid4()),
        phone="+15551234567",
        name="Test Buyer",
        email="buyer@test.com",
    )
    db_session.add(buyer)

    conversation = BuyerConversation(
        id=str(uuid.uuid4()),
        buyer_id=buyer.id,
        messages=[],
        status="active",
    )
    db_session.add(conversation)

    state = SMSConversationState(
        id=str(uuid.uuid4()),
        buyer_id=buyer.id,
        conversation_id=conversation.id,
        phone="+15551234567",
        phase=phase,
        turn=turn,
        criteria_readiness=0.0,
        criteria_snapshot=criteria_snapshot or {},
        presented_match_ids=presented_match_ids or [],
        focused_match_id=focused_match_id,
    )
    db_session.add(state)
    await db_session.flush()

    return buyer, conversation, state


# ---------------------------------------------------------------------------
# Test: greeting flow (deterministic fast-path, no LLM for response)
# ---------------------------------------------------------------------------

class TestGreetingFlow:
    async def test_greeting_flow(self, db_session):
        buyer, conversation, state = await make_test_context(db_session, turn=1)
        orchestrator = BuyerSMSOrchestrator(db_session)

        mock_plan = CriteriaPlan(intent="greeting", action=None, confidence=0.9)

        with patch(_CRITERIA) as MockCriteria:
            MockCriteria.return_value.plan = AsyncMock(return_value=mock_plan)

            result = await orchestrator.process_message(
                phone="+15551234567",
                message="hey",
                state=state,
                conversation=conversation,
                buyer=buyer,
            )

        assert result.intent == "greeting"
        assert "Warehouse Exchange" in result.response


# ---------------------------------------------------------------------------
# Test: search flow — CriteriaAgent returns search action
# ---------------------------------------------------------------------------

class TestSearchFlow:
    async def test_search_flow(self, db_session):
        buyer, conversation, state = await make_test_context(db_session)
        orchestrator = BuyerSMSOrchestrator(db_session)

        mock_plan = CriteriaPlan(
            intent="new_search",
            action="search",
            criteria={"location": "Detroit", "sqft": 10000, "use_type": "storage",
                      "timing": "ASAP", "duration": "6_months", "goods_type": "general"},
            confidence=0.9,
        )

        mock_summaries = [
            {"id": "p1", "city": "Detroit", "sqft": 12000, "rate": 5.50, "address": "100 Main St"},
            {"id": "p2", "city": "Detroit", "sqft": 8000, "rate": 6.00, "address": "200 Elm St"},
        ]

        with (
            patch(_CRITERIA) as MockCriteria,
            patch(_RESPONSE) as MockResponse,
            patch(_POLISHER),
            patch.object(
                BuyerSMSOrchestrator, "_run_search", new_callable=AsyncMock, return_value=mock_summaries
            ),
        ):
            MockCriteria.return_value.plan = AsyncMock(return_value=mock_plan)
            MockResponse.return_value.generate_reply = AsyncMock(
                return_value="Found 2 spaces in Detroit matching your search."
            )

            result = await orchestrator.process_message(
                phone="+15551234567",
                message="10k sqft storage in Detroit MI, need it ASAP for general goods",
                state=state,
                conversation=conversation,
                buyer=buyer,
                existing_criteria={},
            )

        assert result.phase == "PRESENTING"
        assert result.intent == "new_search"
        assert "Detroit" in result.response


# ---------------------------------------------------------------------------
# Test: gatekeeper-polisher retry loop
# ---------------------------------------------------------------------------

class TestGatekeeperPolisherLoop:
    async def test_polisher_called_on_rejection(self, db_session):
        buyer, conversation, state = await make_test_context(db_session, turn=2)
        orchestrator = BuyerSMSOrchestrator(db_session)

        mock_plan = CriteriaPlan(intent="new_search", action=None, confidence=0.8)

        long_response = "A" * 900  # Exceeds 320-char followup limit
        short_response = "Got it, searching for warehouse space now."

        with (
            patch(_CRITERIA) as MockCriteria,
            patch(_RESPONSE) as MockResponse,
            patch(_POLISHER) as MockPolisher,
        ):
            MockCriteria.return_value.plan = AsyncMock(return_value=mock_plan)
            MockResponse.return_value.generate_reply = AsyncMock(return_value=long_response)
            MockPolisher.return_value.polish = AsyncMock(return_value=short_response)

            result = await orchestrator.process_message(
                phone="+15551234567",
                message="need a big warehouse",
                state=state,
                conversation=conversation,
                buyer=buyer,
            )

        # Polisher should have been called to fix the long response
        MockPolisher.return_value.polish.assert_called()
        assert len(result.response) <= 320


# ---------------------------------------------------------------------------
# Test: 3 failures fallback template
# ---------------------------------------------------------------------------

class TestThreeFailuresFallback:
    async def test_fallback_after_3_rejections(self, db_session):
        buyer, conversation, state = await make_test_context(db_session, turn=2)
        orchestrator = BuyerSMSOrchestrator(db_session)

        mock_plan = CriteriaPlan(intent="new_search", action=None, confidence=0.8)
        always_too_long = "B" * 900  # Always exceeds 320 followup limit

        with (
            patch(_CRITERIA) as MockCriteria,
            patch(_RESPONSE) as MockResponse,
            patch(_POLISHER) as MockPolisher,
        ):
            MockCriteria.return_value.plan = AsyncMock(return_value=mock_plan)
            MockResponse.return_value.generate_reply = AsyncMock(return_value=always_too_long)
            # Polisher also returns too-long text
            MockPolisher.return_value.polish = AsyncMock(return_value=always_too_long)

            result = await orchestrator.process_message(
                phone="+15551234567",
                message="looking for space",
                state=state,
                conversation=conversation,
                buyer=buyer,
            )

        # After 3 gatekeeper rejections, should use fallback template
        # The fallback for "new_search" is the deterministic template
        assert "searching" in result.response.lower() or "search" in result.response.lower()
        assert len(result.response) <= 800  # fallback templates are always short


# ---------------------------------------------------------------------------
# Test: property reference resolution
# ---------------------------------------------------------------------------

class TestPropertyReferenceResolution:
    async def test_positional_reference_resolves(self, db_session):
        presented_ids = ["p1", "p2", "p3"]
        buyer, conversation, state = await make_test_context(
            db_session, phase="PRESENTING", turn=3, presented_match_ids=presented_ids,
            criteria_snapshot={"match_summaries": [
                {"id": "p1", "city": "Detroit", "sqft": 12000, "rate": 5.50},
                {"id": "p2", "city": "Detroit", "sqft": 8000, "rate": 6.00},
                {"id": "p3", "city": "Detroit", "sqft": 15000, "rate": 4.50},
            ]}
        )
        orchestrator = BuyerSMSOrchestrator(db_session)

        mock_plan = CriteriaPlan(
            intent="facility_info", action="lookup",
            resolved_property_id="p2", confidence=0.9,
        )

        with (
            patch(_CRITERIA) as MockCriteria,
            patch(_RESPONSE) as MockResponse,
            patch(_POLISHER),
        ):
            MockCriteria.return_value.plan = AsyncMock(return_value=mock_plan)
            MockResponse.return_value.generate_reply = AsyncMock(
                return_value="Option 2 is in Detroit, 8000 sqft at six dollars per sqft."
            )

            result = await orchestrator.process_message(
                phone="+15551234567",
                message="tell me about option 2",
                state=state,
                conversation=conversation,
                buyer=buyer,
            )

        # The orchestrator should resolve "option 2" -> "p2"
        assert state.focused_match_id == "p2"
        assert result.phase == "PROPERTY_FOCUSED"


# ---------------------------------------------------------------------------
# Test: criteria readiness computation
# ---------------------------------------------------------------------------

class TestCriteriaReadiness:
    async def test_readiness_weights(self, db_session):
        buyer, conversation, state = await make_test_context(db_session)
        orchestrator = BuyerSMSOrchestrator(db_session)

        mock_plan = CriteriaPlan(
            intent="new_search", action="search",
            criteria={"location": "Detroit", "sqft": 10000, "use_type": "storage"},
            confidence=0.9,
        )

        with (
            patch(_CRITERIA) as MockCriteria,
            patch(_RESPONSE) as MockResponse,
            patch(_POLISHER),
            patch.object(
                BuyerSMSOrchestrator, "_run_search", new_callable=AsyncMock, return_value=None
            ),
        ):
            MockCriteria.return_value.plan = AsyncMock(return_value=mock_plan)
            MockResponse.return_value.generate_reply = AsyncMock(
                return_value="Searching for 10k sqft storage in Detroit area."
            )

            await orchestrator.process_message(
                phone="+15551234567",
                message="10k sqft storage Detroit",
                state=state,
                conversation=conversation,
                buyer=buyer,
            )

        # location=0.3, sqft=0.25, use_type=0.25 => 0.8
        assert abs(state.criteria_readiness - 0.8) < 0.01

    async def test_readiness_with_extras(self, db_session):
        buyer, conversation, state = await make_test_context(db_session)
        orchestrator = BuyerSMSOrchestrator(db_session)

        mock_plan = CriteriaPlan(
            intent="new_search", action="search",
            criteria={
                "location": "Detroit", "sqft": 10000, "use_type": "storage",
                "features": ["dock_doors"],
            },
            confidence=0.9,
        )

        with (
            patch(_CRITERIA) as MockCriteria,
            patch(_RESPONSE) as MockResponse,
            patch(_POLISHER),
            patch.object(
                BuyerSMSOrchestrator, "_run_search", new_callable=AsyncMock, return_value=None
            ),
        ):
            MockCriteria.return_value.plan = AsyncMock(return_value=mock_plan)
            MockResponse.return_value.generate_reply = AsyncMock(
                return_value="Searching for 10k sqft storage in Detroit area."
            )

            await orchestrator.process_message(
                phone="+15551234567",
                message="10k sqft storage Detroit with dock doors",
                state=state,
                conversation=conversation,
                buyer=buyer,
            )

        # location=0.3 + sqft=0.25 + use_type=0.25 + features=0.1 => 0.9
        assert abs(state.criteria_readiness - 0.9) < 0.01


# ---------------------------------------------------------------------------
# Test: stub lookup
# ---------------------------------------------------------------------------

class TestStubLookup:
    async def test_stub_lookup_from_summaries(self, db_session):
        match_summaries = [
            {"id": "p1", "city": "Detroit", "sqft": 12000, "rate": 5.50, "address": "100 Main St"},
            {"id": "p2", "city": "Detroit", "sqft": 8000, "rate": 6.00, "address": "200 Elm St"},
        ]

        presented_ids = ["p1", "p2"]
        buyer, conversation, state = await make_test_context(
            db_session, phase="PRESENTING", turn=3,
            presented_match_ids=presented_ids,
            criteria_snapshot={"match_summaries": match_summaries},
        )
        orchestrator = BuyerSMSOrchestrator(db_session)

        # Directly test the _stub_lookup method
        result = orchestrator._stub_lookup("p2", match_summaries)
        assert result is not None
        assert result["id"] == "p2"
        assert result["city"] == "Detroit"
        assert result["sqft"] == 8000
        assert result["rate"] == 6.00
        assert result["source"] == "match_summary"

    async def test_stub_lookup_missing(self, db_session):
        buyer, conversation, state = await make_test_context(db_session)
        orchestrator = BuyerSMSOrchestrator(db_session)

        result = orchestrator._stub_lookup("nonexistent", [{"id": "p1"}])
        assert result is None

    async def test_stub_lookup_no_summaries(self, db_session):
        buyer, conversation, state = await make_test_context(db_session)
        orchestrator = BuyerSMSOrchestrator(db_session)

        result = orchestrator._stub_lookup("p1", None)
        assert result is None

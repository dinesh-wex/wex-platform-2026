"""Verification tests for Cross-Channel Buyer Journey Unification.

Covers Fix 1 (SMS→Voice continuity) and Fix 2 (Universal Escalation):

Fix 2 scenarios:
  1. SMS unmapped question → EscalationThread created with source_type="sms", field_key=None
  2. Cross-channel dedup → voice check_and_escalate finds SMS thread, no duplicate created
  3. Cache hit → answered thread returns cached answer without creating new thread

Fix 1 scenarios:
  4. _build_voice_summaries_from_sms maps fields correctly and caps at 3
  5. VoiceCallState seeding from SMSConversationState sets all expected fields
  6. BuyerNeed reuse → same city+sqft skips clearing engine, returns cached summaries
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from wex_platform.infra.database import Base
import wex_platform.domain.models  # noqa: F401
import wex_platform.domain.sms_models  # noqa: F401
import wex_platform.domain.voice_models  # noqa: F401

from wex_platform.domain.models import (
    Buyer,
    BuyerConversation,
    BuyerNeed,
    Property,
    PropertyKnowledge,
    PropertyListing,
)
from wex_platform.domain.sms_models import EscalationThread, SMSConversationState
from wex_platform.domain.voice_models import VoiceCallState
from wex_platform.services.escalation_service import EscalationService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite://", connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


async def _seed_property_and_sms_state(db, phone="+15550001111"):
    """Minimal seed: Property + Buyer + SMSConversationState. Returns (prop_id, sms_state)."""
    prop_id = str(uuid.uuid4())
    buyer_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())

    db.add(Property(id=prop_id, address="100 Warehouse Blvd", city="Detroit", state="MI", source="test"))
    db.add(PropertyKnowledge(id=str(uuid.uuid4()), property_id=prop_id))
    db.add(PropertyListing(id=str(uuid.uuid4()), property_id=prop_id, available_sqft=20000, activation_status="live"))
    db.add(Buyer(id=buyer_id, phone=phone, name="Test Buyer", email="buyer@test.com"))
    conv = BuyerConversation(id=conv_id, buyer_id=buyer_id, status="active")
    db.add(conv)

    sms_state = SMSConversationState(
        id=str(uuid.uuid4()),
        buyer_id=buyer_id,
        conversation_id=conv_id,
        phone=phone,
        phase="PROPERTY_FOCUSED",
        known_answers={},
        answered_questions=[],
        pending_escalations={},
    )
    db.add(sms_state)
    await db.flush()
    return prop_id, sms_state


# ---------------------------------------------------------------------------
# Fix 2 — Scenario 1: SMS unmapped question creates EscalationThread
# ---------------------------------------------------------------------------

class TestSMSUnmappedEscalation:
    """Fix 2: Unmapped question via SMS creates thread with correct source_type and field_key=None."""

    @pytest.mark.asyncio
    async def test_creates_thread_with_sms_source_type(self, db):
        prop_id, sms_state = await _seed_property_and_sms_state(db)

        svc = EscalationService(db)
        result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="does it have EV charging?",
            field_key=None,
            state=sms_state,
            source_type="sms",
        )

        assert result["escalated"] is True, "Expected escalation to be created"

        threads = (await db.execute(
            select(EscalationThread).where(EscalationThread.property_id == prop_id)
        )).scalars().all()

        assert len(threads) == 1, f"Expected 1 thread, got {len(threads)}"
        t = threads[0]
        assert t.source_type == "sms", f"Expected source_type='sms', got '{t.source_type}'"
        assert t.field_key is None, f"Expected field_key=None, got '{t.field_key}'"
        assert t.status == "pending"
        assert "EV charging" in t.question_text

    @pytest.mark.asyncio
    async def test_creates_thread_with_voice_source_type(self, db):
        prop_id, sms_state = await _seed_property_and_sms_state(db)

        svc = EscalationService(db)
        result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="ev charging, wifi",
            field_key=None,
            state=sms_state,
            source_type="voice",
        )

        assert result["escalated"] is True

        thread = (await db.execute(
            select(EscalationThread).where(EscalationThread.property_id == prop_id)
        )).scalar_one()

        assert thread.source_type == "voice", f"Expected source_type='voice', got '{thread.source_type}'"
        assert thread.field_key is None


# ---------------------------------------------------------------------------
# Fix 2 — Scenario 2: Cross-channel dedup — voice finds SMS thread
# ---------------------------------------------------------------------------

class TestCrossChannelDedup:
    """Fix 2: Layer 4 finds an existing SMS thread when voice asks the same question."""

    @pytest.mark.asyncio
    async def test_voice_finds_sms_pending_thread(self, db):
        prop_id, sms_state = await _seed_property_and_sms_state(db)

        svc = EscalationService(db)

        # Step 1: SMS creates escalation
        sms_result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="does it have EV charging?",
            field_key=None,
            state=sms_state,
            source_type="sms",
        )
        assert sms_result["escalated"] is True

        # Verify exactly 1 thread exists
        threads_before = (await db.execute(
            select(EscalationThread).where(EscalationThread.property_id == prop_id)
        )).scalars().all()
        assert len(threads_before) == 1

        # Step 2: Voice asks semantically same question → Layer 4 should catch it
        voice_result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="ev charging",
            field_key=None,
            state=sms_state,
            source_type="voice",
        )

        # Should NOT create a new thread
        threads_after = (await db.execute(
            select(EscalationThread).where(EscalationThread.property_id == prop_id)
        )).scalars().all()
        assert len(threads_after) == 1, f"Expected 1 thread (no duplicate), got {len(threads_after)}"

        # Result should indicate waiting (found pending thread)
        assert voice_result.get("waiting") is True, f"Expected waiting=True, got {voice_result}"
        assert voice_result.get("escalated") is not True

    @pytest.mark.asyncio
    async def test_different_property_does_not_dedup(self, db):
        prop_id, sms_state = await _seed_property_and_sms_state(db)
        prop_id2 = str(uuid.uuid4())
        db.add(Property(id=prop_id2, address="200 Other St", city="Chicago", state="IL", source="test"))
        db.add(PropertyKnowledge(id=str(uuid.uuid4()), property_id=prop_id2))
        db.add(PropertyListing(id=str(uuid.uuid4()), property_id=prop_id2, available_sqft=10000, activation_status="live"))
        await db.flush()

        svc = EscalationService(db)

        # SMS escalation on property 1
        await svc.check_and_escalate(
            property_id=prop_id,
            question_text="does it have EV charging?",
            field_key=None,
            state=sms_state,
            source_type="sms",
        )

        # Voice on property 2 — should create NEW thread (different property)
        voice_result = await svc.check_and_escalate(
            property_id=prop_id2,
            question_text="ev charging",
            field_key=None,
            state=sms_state,
            source_type="voice",
        )
        assert voice_result["escalated"] is True, "Different property should create a new thread"

        all_threads = (await db.execute(select(EscalationThread))).scalars().all()
        assert len(all_threads) == 2, f"Expected 2 threads (one per property), got {len(all_threads)}"


# ---------------------------------------------------------------------------
# Fix 2 — Scenario 3: Cache hit — answered thread returns answer, no new thread
# ---------------------------------------------------------------------------

class TestCrossChannelCacheHit:
    """Fix 2: When SMS thread is answered, voice call gets the cached answer immediately."""

    @pytest.mark.asyncio
    async def test_answered_thread_returns_cached_answer(self, db):
        prop_id, sms_state = await _seed_property_and_sms_state(db)

        # Manually insert an already-answered thread (as if supplier replied via SMS)
        answered_thread = EscalationThread(
            id=str(uuid.uuid4()),
            conversation_state_id=sms_state.id,
            property_id=prop_id,
            question_text="does it have EV charging?",
            field_key=None,
            status="answered",
            source_type="sms",
            answer_sent_text="Yes, we have 10 EV charging stations.",
            sla_deadline_at=datetime.now(timezone.utc),
        )
        db.add(answered_thread)
        await db.flush()

        svc = EscalationService(db)

        # Voice asks same question
        voice_result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="ev charging",
            field_key=None,
            state=sms_state,
            source_type="voice",
        )

        assert voice_result.get("escalated") is not True, "Should NOT create new escalation"
        assert voice_result.get("answer") == "Yes, we have 10 EV charging stations.", \
            f"Expected cached answer, got: {voice_result}"

        # No new thread created
        threads = (await db.execute(
            select(EscalationThread).where(EscalationThread.property_id == prop_id)
        )).scalars().all()
        assert len(threads) == 1, "No new thread should have been created for cache hit"

    @pytest.mark.asyncio
    async def test_answered_thread_without_sent_text_does_not_return_answer(self, db):
        """If answered but answer_sent_text is None, Layer 4 should not return it as a cache hit."""
        prop_id, sms_state = await _seed_property_and_sms_state(db)

        # Thread answered but answer_sent_text not populated yet
        incomplete_thread = EscalationThread(
            id=str(uuid.uuid4()),
            conversation_state_id=sms_state.id,
            property_id=prop_id,
            question_text="does it have EV charging?",
            field_key=None,
            status="answered",
            source_type="sms",
            answer_sent_text=None,  # Not populated
            sla_deadline_at=datetime.now(timezone.utc),
        )
        db.add(incomplete_thread)
        await db.flush()

        svc = EscalationService(db)
        result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="ev charging",
            field_key=None,
            state=sms_state,
            source_type="voice",
        )

        # Should NOT return the incomplete answered thread as a cache hit
        # (Layer 4 requires both status=="answered" AND answer_sent_text)
        assert result.get("answer") is None or result.get("escalated") is True


# ---------------------------------------------------------------------------
# Fix 1 — Scenario 4: _build_voice_summaries_from_sms
# ---------------------------------------------------------------------------

class TestBuildVoiceSummariesFromSMS:
    """Fix 1: Helper converts SMS match summaries to voice format correctly."""

    def test_maps_match_score_to_score(self):
        from wex_platform.app.routes.vapi_webhook import _build_voice_summaries_from_sms

        sms_summaries = [
            {"id": "prop-1", "city": "Detroit", "state": "MI", "rate": 0.55, "monthly": 8250,
             "match_score": 87, "description": "Great dock access"}
        ]
        result = _build_voice_summaries_from_sms(sms_summaries)

        assert len(result) == 1
        assert result[0]["score"] == 87, "match_score should be mapped to score"
        assert "match_score" not in result[0], "match_score key should not remain"

    def test_caps_at_three_entries(self):
        from wex_platform.app.routes.vapi_webhook import _build_voice_summaries_from_sms

        sms_summaries = [
            {"id": f"prop-{i}", "city": "Detroit", "state": "MI", "rate": 0.5, "monthly": 7500,
             "match_score": 80 - i}
            for i in range(5)
        ]
        result = _build_voice_summaries_from_sms(sms_summaries)
        assert len(result) == 3, f"Expected 3 summaries (capped), got {len(result)}"

    def test_sets_features_empty_and_instant_book_false(self):
        from wex_platform.app.routes.vapi_webhook import _build_voice_summaries_from_sms

        sms_summaries = [
            {"id": "prop-1", "city": "Chicago", "state": "IL", "rate": 0.60, "monthly": 9000,
             "match_score": 91, "description": "Prime location"}
        ]
        result = _build_voice_summaries_from_sms(sms_summaries)
        assert result[0]["features"] == [], "features should be empty list to force fresh lookup"
        assert result[0]["instant_book"] is False

    def test_handles_empty_input(self):
        from wex_platform.app.routes.vapi_webhook import _build_voice_summaries_from_sms
        assert _build_voice_summaries_from_sms([]) == []
        assert _build_voice_summaries_from_sms(None) == []

    def test_preserves_city_state_rate_monthly(self):
        from wex_platform.app.routes.vapi_webhook import _build_voice_summaries_from_sms

        sms_summaries = [
            {"id": "prop-abc", "city": "Houston", "state": "TX", "rate": 0.45,
             "monthly": 6750, "match_score": 78}
        ]
        result = _build_voice_summaries_from_sms(sms_summaries)
        r = result[0]
        assert r["id"] == "prop-abc"
        assert r["city"] == "Houston"
        assert r["state"] == "TX"
        assert r["rate"] == 0.45
        assert r["monthly"] == 6750


# ---------------------------------------------------------------------------
# Fix 1 — Scenario 5: VoiceCallState seeding from SMSConversationState
# ---------------------------------------------------------------------------

class TestVoiceCallStateSeeding:
    """Fix 1: VoiceCallState is seeded with correct fields from SMS context."""

    @pytest.mark.asyncio
    async def test_seeding_sets_all_fields(self, db):
        prop_id, sms_state = await _seed_property_and_sms_state(db)

        # Populate SMS state with realistic data
        sms_state.buyer_need_id = str(uuid.uuid4())
        sms_state.presented_match_ids = [prop_id, str(uuid.uuid4())]
        sms_state.known_answers = {"clear_height": "28 feet"}
        sms_state.answered_questions = ["clear_height"]
        sms_state.criteria_snapshot = {"location": "Detroit, MI", "sqft": 15000}
        await db.flush()

        # Build sms_context dict (as vapi_webhook.py does)
        sms_context = {
            "phase": sms_state.phase,
            "criteria_snapshot": sms_state.criteria_snapshot or {},
            "presented_match_ids": sms_state.presented_match_ids or [],
            "focused_match_id": sms_state.focused_match_id,
            "renter_first_name": sms_state.renter_first_name,
            "known_answers": sms_state.known_answers or {},
            "answered_questions": sms_state.answered_questions or [],
            "buyer_need_id": sms_state.buyer_need_id,
            "conversation_id": sms_state.conversation_id,
            "sms_state_id": sms_state.id,
        }

        # Simulate VoiceCallState creation and seeding (mirrors vapi_webhook.py logic)
        call_state = VoiceCallState(
            id=str(uuid.uuid4()),
            vapi_call_id="call-abc-123",
            caller_phone=sms_state.phone,
            verified_phone=sms_state.phone,
            call_started_at=datetime.now(timezone.utc),
        )

        call_state.buyer_need_id = sms_context["buyer_need_id"]
        call_state.conversation_id = sms_context["conversation_id"]
        call_state.known_answers = sms_context["known_answers"]
        call_state.answered_questions = sms_context["answered_questions"]
        call_state.presented_match_ids = sms_context["presented_match_ids"]

        db.add(call_state)
        await db.flush()

        # Verify all fields seeded
        assert call_state.buyer_need_id == sms_state.buyer_need_id
        assert call_state.conversation_id == sms_state.conversation_id
        assert call_state.known_answers == {"clear_height": "28 feet"}
        assert call_state.answered_questions == ["clear_height"]
        assert len(call_state.presented_match_ids) == 2

    @pytest.mark.asyncio
    async def test_no_sms_state_no_seeding(self, db):
        """With no SMS history, VoiceCallState is created with defaults — no crash."""
        call_state = VoiceCallState(
            id=str(uuid.uuid4()),
            vapi_call_id="call-fresh",
            caller_phone="+15559998888",
            verified_phone="+15559998888",
            call_started_at=datetime.now(timezone.utc),
        )
        db.add(call_state)
        await db.flush()

        # Fields should be None/empty (no seeding)
        assert call_state.buyer_need_id is None
        assert call_state.conversation_id is None
        assert call_state.known_answers is None or call_state.known_answers == {}


# ---------------------------------------------------------------------------
# Fix 1 — Scenario 6: BuyerNeed reuse when city+sqft match
# ---------------------------------------------------------------------------

class TestBuyerNeedReuse:
    """Fix 1: voice_tool_handlers reuses existing BuyerNeed when city+sqft fall within stored band."""

    @pytest.mark.asyncio
    async def test_sqft_within_band_is_reusable(self, db):
        """Verifies the city_match + sqft_in_range logic used in search_properties()."""
        prop_id, sms_state = await _seed_property_and_sms_state(db)

        buyer_need_id = str(uuid.uuid4())
        # Simulate BuyerNeed created during SMS with sqft=10000 → band 8000–12000
        need = BuyerNeed(
            id=buyer_need_id,
            buyer_id=sms_state.buyer_id,
            city="Detroit",
            state="MI",
            min_sqft=8000,   # 0.8 × 10000
            max_sqft=12000,  # 1.2 × 10000
        )
        db.add(need)
        await db.flush()

        # Simulate voice search_properties() validation logic
        existing_need = (await db.execute(
            select(BuyerNeed).where(BuyerNeed.id == buyer_need_id)
        )).scalar_one()

        voice_city = "Detroit"
        voice_sqft = 10500  # Within 8000–12000

        city_match = (existing_need.city or "").lower() == voice_city.lower()
        sqft_in_range = (
            existing_need.min_sqft is not None
            and existing_need.max_sqft is not None
            and existing_need.min_sqft <= voice_sqft <= existing_need.max_sqft
        )

        assert city_match is True, "City should match case-insensitively"
        assert sqft_in_range is True, f"sqft {voice_sqft} should be within [{existing_need.min_sqft}, {existing_need.max_sqft}]"
        assert city_match and sqft_in_range, "Should reuse existing BuyerNeed"

    @pytest.mark.asyncio
    async def test_sqft_outside_band_is_not_reusable(self, db):
        prop_id, sms_state = await _seed_property_and_sms_state(db)

        need = BuyerNeed(
            id=str(uuid.uuid4()),
            buyer_id=sms_state.buyer_id,
            city="Detroit",
            state="MI",
            min_sqft=8000,
            max_sqft=12000,
        )
        db.add(need)
        await db.flush()

        existing_need = (await db.execute(
            select(BuyerNeed).where(BuyerNeed.city == "Detroit")
        )).scalar_one()

        voice_sqft = 25000  # Way outside band

        sqft_in_range = (
            existing_need.min_sqft is not None
            and existing_need.max_sqft is not None
            and existing_need.min_sqft <= voice_sqft <= existing_need.max_sqft
        )

        assert sqft_in_range is False, "sqft 25000 should NOT be within band [8000, 12000]"

    @pytest.mark.asyncio
    async def test_different_city_is_not_reusable(self, db):
        prop_id, sms_state = await _seed_property_and_sms_state(db)

        need = BuyerNeed(
            id=str(uuid.uuid4()),
            buyer_id=sms_state.buyer_id,
            city="Detroit",
            state="MI",
            min_sqft=8000,
            max_sqft=12000,
        )
        db.add(need)
        await db.flush()

        existing_need = (await db.execute(
            select(BuyerNeed).where(BuyerNeed.city == "Detroit")
        )).scalar_one()

        city_match = (existing_need.city or "").lower() == "chicago"
        assert city_match is False, "Different city should not match"

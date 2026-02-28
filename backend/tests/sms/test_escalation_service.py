"""Tests for EscalationService — escalation lifecycle for unanswerable property questions."""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from wex_platform.domain.models import (
    Buyer,
    BuyerConversation,
    Property,
    PropertyKnowledge,
    PropertyListing,
)
from wex_platform.domain.sms_models import EscalationThread, SMSConversationState
from wex_platform.services.escalation_service import EscalationService, ESCALATION_SLA_HOURS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_full(db_session):
    """Create Property, Buyer, BuyerConversation, and SMSConversationState.

    Returns (property_id, state).
    """
    prop_id = str(uuid.uuid4())
    buyer_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    state_id = str(uuid.uuid4())

    prop = Property(id=prop_id, address="1 Test St", city="Detroit", state="MI", source="test")
    db_session.add(prop)

    knowledge = PropertyKnowledge(
        id=str(uuid.uuid4()),
        property_id=prop_id,
        clear_height_ft=28,
    )
    db_session.add(knowledge)

    listing = PropertyListing(
        id=str(uuid.uuid4()),
        property_id=prop_id,
        available_sqft=15000,
        activation_status="live",
    )
    db_session.add(listing)

    buyer = Buyer(id=buyer_id, phone="+15551234567", name="Test Buyer", email="buyer@test.com")
    db_session.add(buyer)

    conv = BuyerConversation(id=conv_id, buyer_id=buyer_id, status="active")
    db_session.add(conv)

    state = SMSConversationState(
        id=state_id,
        buyer_id=buyer_id,
        conversation_id=conv_id,
        phone="+15551234567",
        phase="PROPERTY_FOCUSED",
        known_answers={},
        answered_questions=[],
        pending_escalations={},
    )
    db_session.add(state)

    await db_session.flush()
    return prop_id, state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestKnownAnswersHit:
    """Pre-populated known_answers cache prevents escalation."""

    async def test_known_answers_hit(self, db_session):
        prop_id, state = await _seed_full(db_session)

        # Pre-populate known_answers
        state.known_answers = {
            prop_id: {
                "clear_height_ft": {"value": 28, "formatted": "28 ft"},
            }
        }

        svc = EscalationService(db_session)
        result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="What is the clear height?",
            field_key="clear_height_ft",
            state=state,
        )

        assert result["escalated"] is False
        assert result["answer"] == "28 ft"


class TestAnsweredQuestionsHit:
    """Previously answered question prevents escalation."""

    async def test_answered_questions_hit(self, db_session):
        prop_id, state = await _seed_full(db_session)

        state.answered_questions = [
            {
                "property_id": prop_id,
                "question": "What is the ceiling height?",
                "field_key": "clear_height_ft",
                "answer": "28 ft",
            }
        ]

        svc = EscalationService(db_session)
        result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="What is the ceiling height?",
            field_key=None,
            state=state,
        )

        assert result["escalated"] is False
        assert result["answer"] == "28 ft"


class TestCrossQuestionContainment:
    """Substring containment match on answered_questions prevents escalation."""

    async def test_cross_question_containment(self, db_session):
        prop_id, state = await _seed_full(db_session)

        state.answered_questions = [
            {
                "property_id": prop_id,
                "question": "what is the ceiling height",
                "answer": "28 ft",
            }
        ]

        svc = EscalationService(db_session)
        result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="ceiling height",
            field_key=None,
            state=state,
        )

        assert result["escalated"] is False
        assert result["answer"] == "28 ft"


class TestAllMissCreatesThread:
    """No cache, no answered questions -> escalation creates EscalationThread in DB."""

    async def test_all_miss_creates_thread(self, db_session):
        prop_id, state = await _seed_full(db_session)

        svc = EscalationService(db_session)
        result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="Is there a rail siding?",
            field_key="rail_served",
            state=state,
        )

        assert result["escalated"] is True
        assert result["thread_id"] is not None

        # Verify the thread exists in DB
        row = await db_session.execute(
            select(EscalationThread).where(EscalationThread.id == result["thread_id"])
        )
        thread = row.scalar_one_or_none()
        assert thread is not None
        assert thread.status == "pending"
        assert thread.property_id == prop_id


class TestSlaDeadline:
    """Created thread has sla_deadline_at = now + 2 hours."""

    async def test_sla_deadline(self, db_session):
        prop_id, state = await _seed_full(db_session)

        before = datetime.now(timezone.utc)
        svc = EscalationService(db_session)
        result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="Is there a fenced yard?",
            field_key="fenced_yard",
            state=state,
        )

        row = await db_session.execute(
            select(EscalationThread).where(EscalationThread.id == result["thread_id"])
        )
        thread = row.scalar_one()

        # sla_deadline_at should be roughly now + 2 hours (allow 30s tolerance)
        expected_min = before + timedelta(hours=ESCALATION_SLA_HOURS) - timedelta(seconds=30)
        expected_max = datetime.now(timezone.utc) + timedelta(hours=ESCALATION_SLA_HOURS) + timedelta(seconds=30)

        # Thread deadline may be naive (SQLite), so compare without tz
        deadline = thread.sla_deadline_at
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)

        assert expected_min <= deadline <= expected_max


class TestPendingEscalationsUpdated:
    """After escalation, state.pending_escalations contains the thread."""

    async def test_pending_escalations_updated(self, db_session):
        prop_id, state = await _seed_full(db_session)

        svc = EscalationService(db_session)
        result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="What zoning applies?",
            field_key="zoning",
            state=state,
        )

        thread_id = result["thread_id"]
        assert thread_id in state.pending_escalations
        entry = state.pending_escalations[thread_id]
        assert entry["property_id"] == prop_id
        assert entry["question"] == "What zoning applies?"


class TestRecordAnswer:
    """record_answer sets status=answered and updates state.answered_questions."""

    async def test_record_answer(self, db_session):
        prop_id, state = await _seed_full(db_session)

        svc = EscalationService(db_session)
        esc = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="Any rail siding?",
            field_key="rail_served",
            state=state,
        )
        thread_id = esc["thread_id"]

        thread = await svc.record_answer(
            thread_id=thread_id,
            answer_text="No rail siding available.",
            answered_by="ops",
            state=state,
        )

        assert thread is not None
        assert thread.status == "answered"

        # state.answered_questions should have the entry
        assert any(
            aq["thread_id"] == thread_id
            for aq in state.answered_questions
        )


class TestReEscalationPrevention:
    """Answering a question, then asking it again -> answered_questions hit, no new thread."""

    async def test_re_escalation_prevention(self, db_session):
        prop_id, state = await _seed_full(db_session)

        svc = EscalationService(db_session)

        # First: escalate
        esc = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="Is there a fenced yard?",
            field_key="fenced_yard",
            state=state,
        )
        assert esc["escalated"] is True

        # Answer it
        await svc.record_answer(
            thread_id=esc["thread_id"],
            answer_text="Yes, fully fenced.",
            answered_by="ops",
            state=state,
        )

        # Ask the same question again
        result = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="Is there a fenced yard?",
            field_key="fenced_yard",
            state=state,
        )

        # Should hit known_answers cache (record_answer caches it there)
        assert result["escalated"] is False


class TestExistingPendingThread:
    """An existing pending thread returns waiting=True, no new thread."""

    async def test_existing_pending_thread(self, db_session):
        prop_id, state = await _seed_full(db_session)

        svc = EscalationService(db_session)

        # First escalation
        esc1 = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="What is the zoning?",
            field_key="zoning",
            state=state,
        )
        assert esc1["escalated"] is True
        thread_id_1 = esc1["thread_id"]

        # Ask the same question again (pending thread still exists)
        esc2 = await svc.check_and_escalate(
            property_id=prop_id,
            question_text="What is the zoning?",
            field_key="zoning",
            state=state,
        )

        assert esc2.get("escalated", False) is False
        assert esc2.get("waiting") is True
        assert esc2.get("thread_id") == thread_id_1

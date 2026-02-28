"""Tests for SMS Reply Tool — ops endpoint for answering escalated buyer questions."""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.models import (
    Buyer,
    BuyerConversation,
    Property,
    PropertyKnowledge,
    PropertyListing,
)
from wex_platform.domain.sms_models import EscalationThread, SMSConversationState
from wex_platform.services.escalation_service import ESCALATION_SLA_HOURS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_reply_client(db_session: AsyncSession):
    """Build an HTTPX AsyncClient wired to a test app with the reply router."""
    from fastapi import FastAPI
    from wex_platform.app.routes.sms_reply_tool import router as reply_router
    from wex_platform.infra.database import get_db

    test_app = FastAPI()
    test_app.include_router(reply_router)

    async def _override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = _override_get_db

    return AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"X-Internal-Token": "wex2026"},
    )


async def _seed_thread(db_session, *, status="pending", answer_sent_text=None):
    """Create the full chain: Property -> Buyer -> Conversation -> State -> Thread.

    Returns (thread_id, state_id, property_id).
    """
    prop_id = str(uuid.uuid4())
    buyer_id = str(uuid.uuid4())
    conv_id = str(uuid.uuid4())
    state_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())

    prop = Property(id=prop_id, address="1 Test St", city="Detroit", state="MI", source="test")
    db_session.add(prop)

    knowledge = PropertyKnowledge(
        id=str(uuid.uuid4()),
        property_id=prop_id,
    )
    db_session.add(knowledge)

    listing = PropertyListing(
        id=str(uuid.uuid4()),
        property_id=prop_id,
        available_sqft=10000,
        activation_status="live",
    )
    db_session.add(listing)

    buyer = Buyer(id=buyer_id, phone="+15551234567", name="Test Buyer", email="b@t.com")
    db_session.add(buyer)

    conv = BuyerConversation(id=conv_id, buyer_id=buyer_id, status="active")
    db_session.add(conv)

    state = SMSConversationState(
        id=state_id,
        buyer_id=buyer_id,
        conversation_id=conv_id,
        phone="+15551234567",
        phase="AWAITING_ANSWER",
        known_answers={},
        answered_questions=[],
        pending_escalations={},
    )
    db_session.add(state)

    thread = EscalationThread(
        id=thread_id,
        conversation_state_id=state_id,
        property_id=prop_id,
        question_text="Is there rail access?",
        field_key="rail_served",
        status=status,
        sla_deadline_at=datetime.now(timezone.utc) + timedelta(hours=ESCALATION_SLA_HOURS),
        answer_sent_text=answer_sent_text,
    )
    db_session.add(thread)

    await db_session.flush()
    return thread_id, state_id, prop_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetThreadDetails:
    """GET /api/sms/internal/reply/{id} returns thread details."""

    async def test_get_thread_details(self, db_session):
        thread_id, _, prop_id = await _seed_thread(db_session)

        async with _build_reply_client(db_session) as client:
            resp = await client.get(f"/api/sms/internal/reply/{thread_id}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == thread_id
        assert data["property_id"] == prop_id
        assert data["status"] == "pending"
        assert data["question"] == "Is there rail access?"
        assert data["field_key"] == "rail_served"


class TestGetNonexistentThread:
    """GET with bad ID returns 404."""

    async def test_get_nonexistent_thread(self, db_session):
        fake_id = str(uuid.uuid4())

        async with _build_reply_client(db_session) as client:
            resp = await client.get(f"/api/sms/internal/reply/{fake_id}")

        assert resp.status_code == 404


class TestSubmitReply:
    """POST answer records it on the thread."""

    async def test_submit_reply(self, db_session):
        thread_id, _, _ = await _seed_thread(db_session)

        with (
            patch("wex_platform.app.routes.sms_reply_tool.SMSService") as MockSMS,
            patch("wex_platform.agents.sms.gatekeeper.validate_outbound") as mock_gate,
        ):
            mock_gate.return_value.ok = True
            MockSMS.return_value.send_buyer_sms = AsyncMock(return_value={"ok": True})

            async with _build_reply_client(db_session) as client:
                resp = await client.post(
                    f"/api/sms/internal/reply/{thread_id}",
                    json={"answer": "No rail access at this facility.", "answered_by": "ops"},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "answered"

        # Verify DB
        row = await db_session.execute(
            select(EscalationThread).where(EscalationThread.id == thread_id)
        )
        thread = row.scalar_one()
        assert thread.status == "answered"


class TestSubmitReplyToAnsweredThread:
    """POST to already-answered thread returns 400."""

    async def test_submit_reply_to_answered_thread(self, db_session):
        thread_id, _, _ = await _seed_thread(db_session, status="answered", answer_sent_text="Already answered")

        async with _build_reply_client(db_session) as client:
            resp = await client.post(
                f"/api/sms/internal/reply/{thread_id}",
                json={"answer": "duplicate answer", "answered_by": "ops"},
            )

        assert resp.status_code == 400


class TestReplySendsSms:
    """POST reply sends SMS to the buyer's phone number."""

    async def test_reply_sends_sms(self, db_session):
        thread_id, _, _ = await _seed_thread(db_session)

        with (
            patch("wex_platform.app.routes.sms_reply_tool.SMSService") as MockSMS,
            patch("wex_platform.agents.sms.gatekeeper.validate_outbound") as mock_gate,
        ):
            mock_gate.return_value.ok = True
            mock_send = AsyncMock(return_value={"ok": True})
            MockSMS.return_value.send_buyer_sms = mock_send

            async with _build_reply_client(db_session) as client:
                resp = await client.post(
                    f"/api/sms/internal/reply/{thread_id}",
                    json={"answer": "Yes, rail siding available.", "answered_by": "ops"},
                )

        assert resp.status_code == 200

        # Verify SMS was sent to buyer's phone
        mock_send.assert_called_once()
        call_args = mock_send.call_args
        assert call_args[0][0] == "+15551234567"  # buyer phone

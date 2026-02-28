"""Tests for BuyerNotificationService — Phase 5 QC."""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from wex_platform.domain.sms_models import SMSConversationState, EscalationThread
from wex_platform.domain.models import Buyer, BuyerConversation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_state(
    db,
    phase="INTAKE",
    last_buyer_message_at=None,
    last_system_message_at=None,
    stall_nudge_counts=None,
    opted_out=False,
) -> SMSConversationState:
    """Create a minimal SMSConversationState for testing."""
    buyer = Buyer(
        id=str(uuid.uuid4()),
        phone="+15559990001",
        name="Test Buyer",
    )
    db.add(buyer)

    convo = BuyerConversation(
        id=str(uuid.uuid4()),
        buyer_id=buyer.id,
        messages=[],
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(convo)

    state = SMSConversationState(
        id=str(uuid.uuid4()),
        buyer_id=buyer.id,
        conversation_id=convo.id,
        phone="+15559990001",
        phase=phase,
        last_buyer_message_at=last_buyer_message_at,
        last_system_message_at=last_system_message_at,
        stall_nudge_counts=stall_nudge_counts or {},
        opted_out=opted_out,
    )
    db.add(state)
    await db.flush()
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stall_presenting(db_session):
    """Stale PRESENTING conversation should receive a nudge."""
    state = await _make_state(
        db_session,
        phase="PRESENTING",
        last_buyer_message_at=datetime.now(timezone.utc) - timedelta(hours=5),
    )

    with patch("wex_platform.services.buyer_notification_service.SMSService") as MockSMS:
        mock_sms = MagicMock()
        mock_sms.send_buyer_sms = AsyncMock(return_value={"ok": True})
        mock_sms.check_quiet_hours = staticmethod(lambda tz=None: False)
        MockSMS.return_value = mock_sms
        MockSMS.check_quiet_hours = staticmethod(lambda tz=None: False)

        from wex_platform.services.buyer_notification_service import BuyerNotificationService
        svc = BuyerNotificationService(db_session)

        count = await svc.check_stale_conversations()

    assert count >= 1
    # Reload state
    result = await db_session.execute(
        select(SMSConversationState).where(SMSConversationState.id == state.id)
    )
    updated = result.scalar_one()
    assert updated.stall_nudge_counts.get("PRESENTING") == 1


@pytest.mark.asyncio
async def test_stall_max_nudges(db_session):
    """Max nudges reached should NOT send another nudge."""
    state = await _make_state(
        db_session,
        phase="PRESENTING",
        last_buyer_message_at=datetime.now(timezone.utc) - timedelta(hours=5),
        stall_nudge_counts={"PRESENTING": 2},
    )

    with patch("wex_platform.services.buyer_notification_service.SMSService") as MockSMS:
        mock_sms = MagicMock()
        mock_sms.send_buyer_sms = AsyncMock(return_value={"ok": True})
        mock_sms.check_quiet_hours = staticmethod(lambda tz=None: False)
        MockSMS.return_value = mock_sms
        MockSMS.check_quiet_hours = staticmethod(lambda tz=None: False)

        from wex_platform.services.buyer_notification_service import BuyerNotificationService
        svc = BuyerNotificationService(db_session)

        count = await svc.check_stale_conversations()

    assert count == 0
    mock_sms.send_buyer_sms.assert_not_called()


@pytest.mark.asyncio
async def test_dormant_transition(db_session):
    """Exhausted nudges + 8 day inactivity should transition to DORMANT."""
    state = await _make_state(
        db_session,
        phase="PRESENTING",
        last_buyer_message_at=datetime.now(timezone.utc) - timedelta(days=8),
        stall_nudge_counts={"PRESENTING": 2},
    )

    with patch("wex_platform.services.buyer_notification_service.SMSService") as MockSMS:
        mock_sms = MagicMock()
        mock_sms.send_buyer_sms = AsyncMock(return_value={"ok": True})
        MockSMS.return_value = mock_sms
        MockSMS.check_quiet_hours = staticmethod(lambda tz=None: False)

        from wex_platform.services.buyer_notification_service import BuyerNotificationService
        svc = BuyerNotificationService(db_session)

        count = await svc.check_dormant_transitions()

    assert count >= 1
    result = await db_session.execute(
        select(SMSConversationState).where(SMSConversationState.id == state.id)
    )
    updated = result.scalar_one()
    assert updated.phase == "DORMANT"


@pytest.mark.asyncio
async def test_intake_abandonment(db_session):
    """INTAKE with 31 days inactivity should transition to ABANDONED."""
    state = await _make_state(
        db_session,
        phase="INTAKE",
        last_buyer_message_at=datetime.now(timezone.utc) - timedelta(days=31),
    )

    with patch("wex_platform.services.buyer_notification_service.SMSService") as MockSMS:
        mock_sms = MagicMock()
        mock_sms.send_buyer_sms = AsyncMock(return_value={"ok": True})
        MockSMS.return_value = mock_sms
        MockSMS.check_quiet_hours = staticmethod(lambda tz=None: False)

        from wex_platform.services.buyer_notification_service import BuyerNotificationService
        svc = BuyerNotificationService(db_session)

        count = await svc.check_inactivity_abandonment()

    assert count >= 1
    result = await db_session.execute(
        select(SMSConversationState).where(SMSConversationState.id == state.id)
    )
    updated = result.scalar_one()
    assert updated.phase == "ABANDONED"


@pytest.mark.asyncio
async def test_dormant_abandonment(db_session):
    """DORMANT with 8 days since last system message should transition to ABANDONED."""
    state = await _make_state(
        db_session,
        phase="DORMANT",
        last_buyer_message_at=datetime.now(timezone.utc) - timedelta(days=20),
        last_system_message_at=datetime.now(timezone.utc) - timedelta(days=8),
    )

    with patch("wex_platform.services.buyer_notification_service.SMSService") as MockSMS:
        mock_sms = MagicMock()
        mock_sms.send_buyer_sms = AsyncMock(return_value={"ok": True})
        MockSMS.return_value = mock_sms
        MockSMS.check_quiet_hours = staticmethod(lambda tz=None: False)

        from wex_platform.services.buyer_notification_service import BuyerNotificationService
        svc = BuyerNotificationService(db_session)

        count = await svc.check_inactivity_abandonment()

    assert count >= 1
    result = await db_session.execute(
        select(SMSConversationState).where(SMSConversationState.id == state.id)
    )
    updated = result.scalar_one()
    assert updated.phase == "ABANDONED"


@pytest.mark.asyncio
async def test_quiet_hours_blocks_send(db_session):
    """Quiet hours should prevent sending."""
    state = await _make_state(
        db_session,
        phase="PRESENTING",
        last_buyer_message_at=datetime.now(timezone.utc) - timedelta(hours=5),
    )

    with patch("wex_platform.services.buyer_notification_service.SMSService") as MockSMS:
        mock_sms = MagicMock()
        mock_sms.send_buyer_sms = AsyncMock(return_value={"ok": True})
        MockSMS.return_value = mock_sms
        MockSMS.check_quiet_hours = staticmethod(lambda tz=None: True)  # Always quiet

        from wex_platform.services.buyer_notification_service import BuyerNotificationService
        svc = BuyerNotificationService(db_session)

        sent = await svc._send_if_allowed(state, "test message")

    assert sent is False
    mock_sms.send_buyer_sms.assert_not_called()


@pytest.mark.asyncio
async def test_opted_out_blocks_send(db_session):
    """Opted-out buyer should not receive messages."""
    state = await _make_state(
        db_session,
        phase="PRESENTING",
        opted_out=True,
    )

    with patch("wex_platform.services.buyer_notification_service.SMSService") as MockSMS:
        mock_sms = MagicMock()
        mock_sms.send_buyer_sms = AsyncMock(return_value={"ok": True})
        MockSMS.return_value = mock_sms
        MockSMS.check_quiet_hours = staticmethod(lambda tz=None: False)

        from wex_platform.services.buyer_notification_service import BuyerNotificationService
        svc = BuyerNotificationService(db_session)

        sent = await svc._send_if_allowed(state, "test message")

    assert sent is False
    mock_sms.send_buyer_sms.assert_not_called()


@pytest.mark.asyncio
async def test_escalation_sla_nudge(db_session):
    """Past-SLA escalation thread should trigger buyer nudge."""
    state = await _make_state(
        db_session,
        phase="AWAITING_ANSWER",
        last_buyer_message_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )

    # Create a Property for FK
    from wex_platform.domain.models import Property
    prop = Property(
        id=str(uuid.uuid4()),
        address="123 Test St",
        city="Detroit",
        state="MI",
        source="test",
    )
    db_session.add(prop)
    await db_session.flush()

    thread = EscalationThread(
        id=str(uuid.uuid4()),
        conversation_state_id=state.id,
        property_id=prop.id,
        question_text="Does it have AC?",
        status="pending",
        sla_deadline_at=datetime.now(timezone.utc) - timedelta(hours=1),
        buyer_nudge_sent=False,
    )
    db_session.add(thread)
    await db_session.flush()

    with patch("wex_platform.services.buyer_notification_service.SMSService") as MockSMS:
        mock_sms = MagicMock()
        mock_sms.send_buyer_sms = AsyncMock(return_value={"ok": True})
        MockSMS.return_value = mock_sms
        MockSMS.check_quiet_hours = staticmethod(lambda tz=None: False)

        from wex_platform.services.buyer_notification_service import BuyerNotificationService
        svc = BuyerNotificationService(db_session)

        count = await svc.check_escalation_sla()

    assert count >= 1
    result = await db_session.execute(
        select(EscalationThread).where(EscalationThread.id == thread.id)
    )
    updated = result.scalar_one()
    assert updated.buyer_nudge_sent is True

"""Tier 1: SMS model tests.

Tests that SMSConversationState, EscalationThread, and SmsSignupToken models
are created with correct defaults, FK relationships, and field types.
"""

import uuid
from datetime import datetime, timezone

from wex_platform.domain.sms_models import (
    EscalationThread,
    SMSConversationState,
    SmsSignupToken,
)


# ---------------------------------------------------------------------------
# SMSConversationState
# ---------------------------------------------------------------------------


class TestSMSConversationState:
    """Tests for the SMSConversationState model."""

    async def test_creation_with_defaults(self, db_session, make_buyer):
        """New state has correct defaults: phase=INTAKE, turn=0, opted_out=False."""
        buyer = await make_buyer(phone="+15551234567")

        # Create a BuyerConversation for the FK
        from wex_platform.domain.models import BuyerConversation

        conv = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            messages=[],
            status="active",
        )
        db_session.add(conv)
        await db_session.flush()

        state = SMSConversationState(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            conversation_id=conv.id,
            phone="+15551234567",
        )
        db_session.add(state)
        await db_session.flush()

        assert state.phase == "INTAKE"
        assert state.turn == 0
        assert state.opted_out is False

    async def test_default_criteria_readiness(self, db_session, make_buyer):
        """criteria_readiness defaults to 0.0."""
        buyer = await make_buyer(phone="+15550001111")

        from wex_platform.domain.models import BuyerConversation

        conv = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            messages=[],
            status="active",
        )
        db_session.add(conv)
        await db_session.flush()

        state = SMSConversationState(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            conversation_id=conv.id,
            phone="+15550001111",
        )
        db_session.add(state)
        await db_session.flush()

        assert state.criteria_readiness == 0.0

    async def test_default_name_status(self, db_session, make_buyer):
        """name_status defaults to 'unknown'."""
        buyer = await make_buyer(phone="+15550002222")

        from wex_platform.domain.models import BuyerConversation

        conv = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            messages=[],
            status="active",
        )
        db_session.add(conv)
        await db_session.flush()

        state = SMSConversationState(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            conversation_id=conv.id,
            phone="+15550002222",
        )
        db_session.add(state)
        await db_session.flush()

        assert state.name_status == "unknown"

    async def test_buyer_fk(self, db_session, make_buyer):
        """buyer_id FK points to buyers table."""
        buyer = await make_buyer(phone="+15550003333")

        from wex_platform.domain.models import BuyerConversation

        conv = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            messages=[],
            status="active",
        )
        db_session.add(conv)
        await db_session.flush()

        state = SMSConversationState(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            conversation_id=conv.id,
            phone="+15550003333",
        )
        db_session.add(state)
        await db_session.flush()

        assert state.buyer_id == buyer.id

    async def test_conversation_fk(self, db_session, make_buyer):
        """conversation_id FK points to buyer_conversations table."""
        buyer = await make_buyer(phone="+15550004444")

        from wex_platform.domain.models import BuyerConversation

        conv = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            messages=[],
            status="active",
        )
        db_session.add(conv)
        await db_session.flush()

        state = SMSConversationState(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            conversation_id=conv.id,
            phone="+15550004444",
        )
        db_session.add(state)
        await db_session.flush()

        assert state.conversation_id == conv.id


# ---------------------------------------------------------------------------
# EscalationThread
# ---------------------------------------------------------------------------


class TestEscalationThread:
    """Tests for the EscalationThread model."""

    async def test_creation_with_required_fields(self, db_session, make_buyer, make_property):
        """EscalationThread can be created with all required fields."""
        buyer = await make_buyer(phone="+15550005555")
        prop = await make_property()

        from wex_platform.domain.models import BuyerConversation

        conv = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            messages=[],
            status="active",
        )
        db_session.add(conv)
        await db_session.flush()

        state = SMSConversationState(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            conversation_id=conv.id,
            phone="+15550005555",
        )
        db_session.add(state)
        await db_session.flush()

        thread = EscalationThread(
            id=str(uuid.uuid4()),
            conversation_state_id=state.id,
            property_id=prop.id,
            question_text="What is the clear height?",
            sla_deadline_at=datetime.now(timezone.utc),
        )
        db_session.add(thread)
        await db_session.flush()

        assert thread.status == "pending"
        assert thread.buyer_nudge_sent is False
        assert thread.question_text == "What is the clear height?"

    async def test_fk_to_conversation_state(self, db_session, make_buyer, make_property):
        """conversation_state_id FK points to sms_conversation_states."""
        buyer = await make_buyer(phone="+15550006666")
        prop = await make_property()

        from wex_platform.domain.models import BuyerConversation

        conv = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            messages=[],
            status="active",
        )
        db_session.add(conv)
        await db_session.flush()

        state = SMSConversationState(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            conversation_id=conv.id,
            phone="+15550006666",
        )
        db_session.add(state)
        await db_session.flush()

        thread = EscalationThread(
            id=str(uuid.uuid4()),
            conversation_state_id=state.id,
            property_id=prop.id,
            question_text="Do you have dock doors?",
            sla_deadline_at=datetime.now(timezone.utc),
        )
        db_session.add(thread)
        await db_session.flush()

        assert thread.conversation_state_id == state.id

    async def test_fk_to_property(self, db_session, make_buyer, make_property):
        """property_id FK points to properties table."""
        buyer = await make_buyer(phone="+15550007777")
        prop = await make_property()

        from wex_platform.domain.models import BuyerConversation

        conv = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            messages=[],
            status="active",
        )
        db_session.add(conv)
        await db_session.flush()

        state = SMSConversationState(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            conversation_id=conv.id,
            phone="+15550007777",
        )
        db_session.add(state)
        await db_session.flush()

        thread = EscalationThread(
            id=str(uuid.uuid4()),
            conversation_state_id=state.id,
            property_id=prop.id,
            question_text="Is it climate controlled?",
            sla_deadline_at=datetime.now(timezone.utc),
        )
        db_session.add(thread)
        await db_session.flush()

        assert thread.property_id == prop.id


# ---------------------------------------------------------------------------
# SmsSignupToken
# ---------------------------------------------------------------------------


class TestSmsSignupToken:
    """Tests for the SmsSignupToken model."""

    async def test_creation_with_token(self, db_session, make_buyer):
        """SmsSignupToken is created with a token field."""
        buyer = await make_buyer(phone="+15550008888")

        from wex_platform.domain.models import BuyerConversation

        conv = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            messages=[],
            status="active",
        )
        db_session.add(conv)
        await db_session.flush()

        state = SMSConversationState(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            conversation_id=conv.id,
            phone="+15550008888",
        )
        db_session.add(state)
        await db_session.flush()

        token_val = "abc123def456"
        signup = SmsSignupToken(
            id=str(uuid.uuid4()),
            conversation_state_id=state.id,
            token=token_val,
            action="create_account",
            buyer_phone="+15550008888",
            expires_at=datetime.now(timezone.utc),
        )
        db_session.add(signup)
        await db_session.flush()

        assert signup.token == token_val
        assert signup.used is False

    async def test_fk_to_conversation_state(self, db_session, make_buyer):
        """conversation_state_id FK points to sms_conversation_states."""
        buyer = await make_buyer(phone="+15550009999")

        from wex_platform.domain.models import BuyerConversation

        conv = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            messages=[],
            status="active",
        )
        db_session.add(conv)
        await db_session.flush()

        state = SMSConversationState(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            conversation_id=conv.id,
            phone="+15550009999",
        )
        db_session.add(state)
        await db_session.flush()

        signup = SmsSignupToken(
            id=str(uuid.uuid4()),
            conversation_state_id=state.id,
            token="xyz789",
            action="sign_guarantee",
            buyer_phone="+15550009999",
            expires_at=datetime.now(timezone.utc),
        )
        db_session.add(signup)
        await db_session.flush()

        assert signup.conversation_state_id == state.id

"""Tests for SmsTokenService — create, validate, and redeem guarantee tokens.

Uses real async SQLite DB via the db_session fixture.
"""

import uuid
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import select

from wex_platform.domain.models import Buyer, BuyerConversation
from wex_platform.domain.sms_models import SMSConversationState, SmsSignupToken
from wex_platform.services.sms_token_service import SmsTokenService


# ---------------------------------------------------------------------------
# Helper: set up the FK chain for SmsSignupToken
# ---------------------------------------------------------------------------

async def _setup_conversation_state(db_session, *, phone="+15551234567"):
    """Create Buyer + BuyerConversation + SMSConversationState.

    SmsSignupToken requires conversation_state_id FK.
    """
    buyer = Buyer(
        id=str(uuid.uuid4()),
        phone=phone,
        name="Token Buyer",
        email="token@test.com",
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
        phone=phone,
        phase="COMMITMENT",
        turn=3,
    )
    db_session.add(state)
    await db_session.flush()
    return state


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_token(db_session):
    """create_guarantee_token produces a token with 48h expiry."""
    state = await _setup_conversation_state(db_session)

    svc = SmsTokenService(db_session)
    token = await svc.create_guarantee_token(
        conversation_state_id=state.id,
        buyer_phone="+15551234567",
        engagement_id="eng_123",
        prefilled_name="Alice Smith",
        prefilled_email="alice@test.com",
    )

    assert token.id is not None
    assert len(token.token) > 20  # ~64 chars from secrets.token_urlsafe(48)
    assert token.action == "guarantee"
    assert token.buyer_phone == "+15551234567"
    assert token.engagement_id == "eng_123"
    assert token.prefilled_name == "Alice Smith"
    assert token.used is False

    # Expiry should be roughly 48 hours from now
    now = datetime.utcnow()
    expires = token.expires_at
    # Handle both naive and aware datetimes for test compatibility
    if expires.tzinfo is not None:
        expires = expires.replace(tzinfo=None)
    delta = expires - now
    assert timedelta(hours=47) < delta < timedelta(hours=49)


@pytest.mark.asyncio
async def test_validate_valid_token(db_session):
    """validate_token returns the record for a valid, unexpired, unused token."""
    state = await _setup_conversation_state(db_session)

    svc = SmsTokenService(db_session)
    created = await svc.create_guarantee_token(
        conversation_state_id=state.id,
        buyer_phone="+15551234567",
    )

    validated = await svc.validate_token(created.token)
    assert validated is not None
    assert validated.id == created.id


@pytest.mark.asyncio
async def test_validate_expired_token(db_session):
    """validate_token returns None for an expired token."""
    state = await _setup_conversation_state(db_session)

    svc = SmsTokenService(db_session)
    created = await svc.create_guarantee_token(
        conversation_state_id=state.id,
        buyer_phone="+15551234567",
    )

    # Manually expire the token
    created.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db_session.flush()

    validated = await svc.validate_token(created.token)
    assert validated is None


@pytest.mark.asyncio
async def test_validate_used_token(db_session):
    """validate_token returns None for a token that has been redeemed."""
    state = await _setup_conversation_state(db_session)

    svc = SmsTokenService(db_session)
    created = await svc.create_guarantee_token(
        conversation_state_id=state.id,
        buyer_phone="+15551234567",
    )

    # Redeem it first
    await svc.redeem_token(created.token)

    # Now validate should fail
    validated = await svc.validate_token(created.token)
    assert validated is None


@pytest.mark.asyncio
async def test_redeem_token(db_session):
    """redeem_token marks the token as used with a timestamp."""
    state = await _setup_conversation_state(db_session)

    svc = SmsTokenService(db_session)
    created = await svc.create_guarantee_token(
        conversation_state_id=state.id,
        buyer_phone="+15551234567",
    )

    redeemed = await svc.redeem_token(created.token)
    assert redeemed is not None
    assert redeemed.used is True
    assert redeemed.used_at is not None

    # Verify the record in DB
    result = await db_session.execute(
        select(SmsSignupToken).where(SmsSignupToken.id == created.id)
    )
    db_token = result.scalar_one()
    assert db_token.used is True


@pytest.mark.asyncio
async def test_redeem_invalid_token(db_session):
    """redeem_token returns None for a non-existent token string."""
    svc = SmsTokenService(db_session)
    result = await svc.redeem_token("totally_bogus_token_string")
    assert result is None

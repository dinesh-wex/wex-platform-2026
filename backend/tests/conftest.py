"""Shared test infrastructure for the WEx Platform test suite.

Provides:
- db_session: async SQLite in-memory session with all tables created
- sms_service_mock: mock SMSService capturing outbound messages
- aircall_webhook_payload: factory for Aircall webhook JSON
- make_property: factory for Property + PropertyKnowledge + PropertyListing + PropertyContact
- make_buyer: factory for Buyer rows
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Import Base first, then models to register all tables
from wex_platform.infra.database import Base

# Import all model modules so their tables are registered with Base.metadata
import wex_platform.domain.models  # noqa: F401
import wex_platform.domain.sms_models  # noqa: F401

from wex_platform.domain.models import (
    Buyer,
    BuyerConversation,
    Property,
    PropertyContact,
    PropertyKnowledge,
    PropertyListing,
)
from wex_platform.domain.sms_models import SMSConversationState


# ---------------------------------------------------------------------------
# Database session fixture
# ---------------------------------------------------------------------------

@pytest.fixture
async def db_session():
    """Async SQLite in-memory session with all tables created.

    Creates a fresh engine + tables for each test, yields a session,
    then rolls back and tears down.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ---------------------------------------------------------------------------
# SMS service mock
# ---------------------------------------------------------------------------

@pytest.fixture
def sms_service_mock():
    """Mock SMSService that captures outbound messages.

    Returns a MagicMock with send_buyer_sms patched to append
    (to_number, message) tuples to a .sent list.
    """
    mock = MagicMock()
    mock.sent = []

    async def _capture_send(to_number: str, message: str):
        mock.sent.append((to_number, message))
        return {"ok": True}

    mock.send_buyer_sms = AsyncMock(side_effect=_capture_send)
    mock.send_sms = AsyncMock(return_value={"ok": True})
    return mock


# ---------------------------------------------------------------------------
# Aircall webhook payload factory
# ---------------------------------------------------------------------------

@pytest.fixture
def aircall_webhook_payload():
    """Factory that builds valid Aircall webhook JSON.

    Usage:
        payload = aircall_webhook_payload("+15551234567", "I need a warehouse")
    """
    def _factory(
        from_number: str,
        body: str,
        direction: str = "inbound",
        to_number: str = "+15559999999",
        token: str = "",
    ) -> dict:
        payload = {
            "event": "message.received",
            "token": token,
            "data": {
                "direction": direction,
                "message": {
                    "body": body,
                    "direction": direction,
                    "external_number": from_number,
                    "raw_digits": from_number,
                    "number": {
                        "digits": to_number,
                        "e164_digits": to_number,
                    },
                },
            },
        }
        return payload

    return _factory


# ---------------------------------------------------------------------------
# Property factory
# ---------------------------------------------------------------------------

@pytest.fixture
def make_property(db_session):
    """Factory that creates Property + PropertyKnowledge + PropertyListing + PropertyContact.

    Usage:
        prop = await make_property(city="Detroit", contact_phone="+15551112222")
    """
    async def _factory(
        city: str = "Detroit",
        state: str = "MI",
        address: str = "123 Warehouse Blvd",
        contact_name: str = "Test Owner",
        contact_email: str = "owner@test.com",
        contact_phone: str = "+15551112222",
        building_size_sqft: int = 50000,
        available_sqft: int = 30000,
        is_primary: bool = True,
    ) -> Property:
        prop_id = str(uuid.uuid4())

        prop = Property(
            id=prop_id,
            address=address,
            city=city,
            state=state,
            source="test",
        )
        db_session.add(prop)

        knowledge = PropertyKnowledge(
            id=str(uuid.uuid4()),
            property_id=prop_id,
            building_size_sqft=building_size_sqft,
        )
        db_session.add(knowledge)

        listing = PropertyListing(
            id=str(uuid.uuid4()),
            property_id=prop_id,
            available_sqft=available_sqft,
            activation_status="live",
        )
        db_session.add(listing)

        contact = PropertyContact(
            id=str(uuid.uuid4()),
            property_id=prop_id,
            contact_type="owner",
            name=contact_name,
            email=contact_email,
            phone=contact_phone,
            is_primary=is_primary,
        )
        db_session.add(contact)

        await db_session.flush()
        return prop

    return _factory


# ---------------------------------------------------------------------------
# Buyer factory
# ---------------------------------------------------------------------------

@pytest.fixture
def make_buyer(db_session):
    """Factory that creates a Buyer row.

    Usage:
        buyer = await make_buyer(phone="+15551234567")
    """
    async def _factory(
        phone: str = "+15551234567",
        name: str = "Test Buyer",
        email: str = "buyer@test.com",
    ) -> Buyer:
        buyer = Buyer(
            id=str(uuid.uuid4()),
            phone=phone,
            name=name,
            email=email,
        )
        db_session.add(buyer)
        await db_session.flush()
        return buyer

    return _factory

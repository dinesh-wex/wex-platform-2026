"""Tests for EngagementBridge — connects SMS buyer conversations to Engagements.

Uses real async SQLite DB via the db_session fixture.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from wex_platform.domain.models import (
    Buyer,
    BuyerNeed,
    Engagement,
    EngagementEvent,
    Property,
    PropertyContact,
    PropertyKnowledge,
    PropertyListing,
    User,
    Warehouse,
)
from wex_platform.services.engagement_bridge import EngagementBridge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _setup_property_with_supplier(db_session, *, contact_email="owner@test.com"):
    """Create Property + Knowledge + Listing + Contact + Warehouse + Supplier User.

    Returns (property, supplier_user).
    """
    prop_id = str(uuid.uuid4())

    # Supplier User (required so _resolve_supplier_id can find a user by email)
    supplier_user = User(
        id=str(uuid.uuid4()),
        email=contact_email,
        password_hash="fakehash",
        name="Supplier Owner",
        phone="+15559990000",
        role="supplier",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(supplier_user)

    # Warehouse (same id as Property)
    warehouse = Warehouse(
        id=prop_id,
        address="123 Warehouse Blvd",
        city="Detroit",
        state="MI",
        owner_email=contact_email,
    )
    db_session.add(warehouse)

    # Property
    prop = Property(
        id=prop_id,
        address="123 Warehouse Blvd",
        city="Detroit",
        state="MI",
        source="test",
    )
    db_session.add(prop)

    # PropertyKnowledge
    knowledge = PropertyKnowledge(
        id=str(uuid.uuid4()),
        property_id=prop_id,
        building_size_sqft=50000,
    )
    db_session.add(knowledge)

    # PropertyListing
    listing = PropertyListing(
        id=str(uuid.uuid4()),
        property_id=prop_id,
        available_sqft=30000,
        activation_status="live",
    )
    db_session.add(listing)

    # PropertyContact (primary)
    contact = PropertyContact(
        id=str(uuid.uuid4()),
        property_id=prop_id,
        contact_type="owner",
        name="Supplier Owner",
        email=contact_email,
        phone="+15559990000",
        is_primary=True,
    )
    db_session.add(contact)

    await db_session.flush()
    return prop, supplier_user


async def _setup_buyer(db_session, *, phone="+15551234567"):
    """Create a Buyer row and return it."""
    buyer = Buyer(
        id=str(uuid.uuid4()),
        phone=phone,
        name="Test Buyer",
        email="buyer@test.com",
    )
    db_session.add(buyer)
    await db_session.flush()
    return buyer


async def _setup_buyer_need(db_session, buyer_id):
    """Create a BuyerNeed so Engagement FK is satisfied."""
    need = BuyerNeed(
        id=str(uuid.uuid4()),
        buyer_id=buyer_id,
        city="Detroit",
        state="MI",
        min_sqft=5000,
        max_sqft=20000,
        status="active",
    )
    db_session.add(need)
    await db_session.flush()
    return need


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initiate_booking(db_session):
    """initiate_booking creates Engagement, User, and EngagementEvent."""
    prop, supplier = await _setup_property_with_supplier(db_session)
    buyer = await _setup_buyer(db_session)
    need = await _setup_buyer_need(db_session, buyer.id)

    bridge = EngagementBridge(db_session)
    result = await bridge.initiate_booking(
        property_id=prop.id,
        buyer_phone="+15551234567",
        buyer_name="Alice Smith",
        buyer_email="alice@example.com",
        buyer_need_id=need.id,
    )

    assert "engagement_id" in result
    assert result["is_new_user"] is True

    # Verify Engagement exists
    engagement = await db_session.get(Engagement, result["engagement_id"])
    assert engagement is not None
    assert engagement.source_channel == "sms"
    assert engagement.status == "account_created"
    assert engagement.warehouse_id == prop.id
    assert engagement.buyer_need_id == need.id

    # Verify User was created
    user = await db_session.get(User, result["user_id"])
    assert user is not None
    assert user.email == "alice@example.com"
    assert user.name == "Alice Smith"
    assert user.role == "buyer"

    # Verify EngagementEvent audit record
    events_result = await db_session.execute(
        select(EngagementEvent).where(
            EngagementEvent.engagement_id == result["engagement_id"]
        )
    )
    events = events_result.scalars().all()
    assert len(events) == 1
    assert events[0].event_type == "account_created"
    assert events[0].data["source"] == "sms"


@pytest.mark.asyncio
async def test_email_dedup(db_session):
    """initiate_booking links to existing User when email already exists."""
    prop, supplier = await _setup_property_with_supplier(db_session)
    buyer = await _setup_buyer(db_session)
    need = await _setup_buyer_need(db_session, buyer.id)

    # Pre-create a User with the same email
    existing_user = User(
        id=str(uuid.uuid4()),
        email="alice@example.com",
        password_hash="fakehash",
        name="Alice Existing",
        phone="+15559998888",
        role="buyer",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(existing_user)
    await db_session.flush()

    bridge = EngagementBridge(db_session)
    result = await bridge.initiate_booking(
        property_id=prop.id,
        buyer_phone="+15551234567",
        buyer_name="Alice Smith",
        buyer_email="alice@example.com",
        buyer_need_id=need.id,
    )

    assert result["is_new_user"] is False
    assert result["user_id"] == existing_user.id


@pytest.mark.asyncio
async def test_request_tour(db_session):
    """request_tour advances engagement to tour_requested with an audit event."""
    prop, supplier = await _setup_property_with_supplier(db_session)
    buyer = await _setup_buyer(db_session)
    need = await _setup_buyer_need(db_session, buyer.id)

    bridge = EngagementBridge(db_session)
    booking = await bridge.initiate_booking(
        property_id=prop.id,
        buyer_phone="+15551234567",
        buyer_name="Bob",
        buyer_email="bob@test.com",
        buyer_need_id=need.id,
    )

    result = await bridge.request_tour(
        engagement_id=booking["engagement_id"],
        requested_date="2026-03-15",
        requested_time="10:00 AM",
        notes="Morning preferred",
    )

    assert result["ok"] is True
    assert result["status"] == "tour_requested"

    engagement = await db_session.get(Engagement, booking["engagement_id"])
    assert engagement.status == "tour_requested"
    assert engagement.tour_requested_at is not None

    # Verify audit event
    events_result = await db_session.execute(
        select(EngagementEvent).where(
            EngagementEvent.engagement_id == booking["engagement_id"],
            EngagementEvent.event_type == "tour_requested",
        )
    )
    events = events_result.scalars().all()
    assert len(events) == 1
    assert events[0].data["source"] == "sms"


@pytest.mark.asyncio
async def test_confirm_tour(db_session):
    """confirm_tour advances engagement from tour_requested to tour_confirmed."""
    prop, supplier = await _setup_property_with_supplier(db_session)
    buyer = await _setup_buyer(db_session)
    need = await _setup_buyer_need(db_session, buyer.id)

    bridge = EngagementBridge(db_session)
    booking = await bridge.initiate_booking(
        property_id=prop.id,
        buyer_phone="+15551234567",
        buyer_email="bob@test.com",
        buyer_need_id=need.id,
    )
    await bridge.request_tour(engagement_id=booking["engagement_id"])

    result = await bridge.confirm_tour(
        engagement_id=booking["engagement_id"],
        confirmed_date="2026-03-15",
        confirmed_time="10:00 AM",
    )

    assert result["ok"] is True
    assert result["status"] == "tour_confirmed"

    engagement = await db_session.get(Engagement, booking["engagement_id"])
    assert engagement.status == "tour_confirmed"
    assert engagement.tour_confirmed_at is not None


@pytest.mark.asyncio
async def test_handle_guarantee_signed(db_session):
    """handle_guarantee_signed advances status and creates audit event."""
    prop, supplier = await _setup_property_with_supplier(db_session)
    buyer = await _setup_buyer(db_session)
    need = await _setup_buyer_need(db_session, buyer.id)

    bridge = EngagementBridge(db_session)
    booking = await bridge.initiate_booking(
        property_id=prop.id,
        buyer_phone="+15551234567",
        buyer_email="bob@test.com",
        buyer_need_id=need.id,
    )

    result = await bridge.handle_guarantee_signed(
        engagement_id=booking["engagement_id"],
        signer_name="Bob Smith",
    )

    assert result["ok"] is True
    assert result["status"] == "guarantee_signed"

    engagement = await db_session.get(Engagement, booking["engagement_id"])
    assert engagement.status == "guarantee_signed"
    assert engagement.guarantee_signed_at is not None

    # Verify audit event
    events_result = await db_session.execute(
        select(EngagementEvent).where(
            EngagementEvent.engagement_id == booking["engagement_id"],
            EngagementEvent.event_type == "guarantee_signed",
        )
    )
    events = events_result.scalars().all()
    assert len(events) == 1
    assert events[0].data["signer"] == "Bob Smith"
    assert events[0].data["source"] == "sms"

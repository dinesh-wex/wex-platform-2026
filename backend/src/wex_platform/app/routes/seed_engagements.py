"""Seed endpoint — creates test engagements across all major lifecycle states.

POST /api/dev/seed-engagements
Creates: 1 supplier user, 1 buyer user, 1 warehouse, 1 buyer need,
         and ~12 engagements spread across the key states for manual testing.

WARNING: Dev-only. Do not ship to production.
"""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.enums import (
    AgreementSignStatus,
    BuyerPaymentStatus,
    EngagementActor,
    EngagementEventType,
    EngagementStatus,
    SupplierPaymentStatus,
)
from wex_platform.domain.models import (
    Buyer,
    BuyerNeed,
    Engagement,
    EngagementAgreement,
    EngagementEvent,
    PaymentRecord,
    TruthCore,
    User,
    Warehouse,
)
from wex_platform.infra.database import get_db
from wex_platform.services.auth_service import hash_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dev", tags=["dev-seed"])

S = EngagementStatus
E = EngagementEventType


def _id():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


def _ago(**kwargs):
    return datetime.now(timezone.utc) - timedelta(**kwargs)


def _future(**kwargs):
    return datetime.now(timezone.utc) + timedelta(**kwargs)


def _event(engagement_id, event_type, actor, from_status, to_status, created_at=None, data=None):
    return EngagementEvent(
        id=_id(),
        engagement_id=engagement_id,
        event_type=event_type.value if hasattr(event_type, "value") else event_type,
        actor=actor.value if hasattr(actor, "value") else actor,
        from_status=from_status.value if hasattr(from_status, "value") else from_status,
        to_status=to_status.value if hasattr(to_status, "value") else to_status,
        data=data,
        created_at=created_at or _now(),
    )


@router.post("/seed-engagements")
async def seed_engagements(db: AsyncSession = Depends(get_db)):
    """Create test data for the engagement lifecycle.

    Idempotent — checks for existing seed data by email before creating.
    """
    # Check if already seeded
    existing = await db.execute(
        select(User).where(User.email == "seed-supplier@wex.test")
    )
    if existing.scalar_one_or_none():
        return {"message": "Already seeded. Delete seed data first or use a fresh DB.", "seeded": False}

    # -----------------------------------------------------------------------
    # 1. Create users
    # -----------------------------------------------------------------------
    supplier_user = User(
        id=_id(),
        email="seed-supplier@wex.test",
        password_hash=hash_password("test1234"),
        name="Demo Supplier",
        role="supplier",
        company="Acme Warehousing LLC",
        phone="+1-555-100-0001",
    )
    buyer_user = User(
        id=_id(),
        email="seed-buyer@wex.test",
        password_hash=hash_password("test1234"),
        name="Demo Buyer",
        role="buyer",
        company="Globex Logistics Inc",
        phone="+1-555-200-0001",
    )
    admin_user = User(
        id=_id(),
        email="seed-admin@wex.test",
        password_hash=hash_password("test1234"),
        name="WEx Admin",
        role="admin",
    )
    db.add_all([supplier_user, buyer_user, admin_user])

    # -----------------------------------------------------------------------
    # 2. Create warehouse + truth core
    # -----------------------------------------------------------------------
    wh_id = _id()
    warehouse = Warehouse(
        id=wh_id,
        owner_name="Demo Supplier",
        owner_email="seed-supplier@wex.test",
        owner_phone="+1-555-100-0001",
        address="1234 Industrial Pkwy",
        city="Dallas",
        state="TX",
        zip="75201",
        lat=32.7767,
        lng=-96.7970,
        building_size_sqft=50000,
        property_type="warehouse",
        supplier_status="in_network",
        primary_image_url="https://placehold.co/600x400?text=Warehouse",
    )
    truth_core = TruthCore(
        id=_id(),
        warehouse_id=wh_id,
        min_sqft=5000,
        max_sqft=50000,
        clear_height_ft=28,
        dock_doors_receiving=3,
        dock_doors_shipping=3,
        activity_tier="storage_light_assembly",
        supplier_rate_per_sqft=5.50,
        activation_status="on",
        min_term_months=6,
    )
    db.add_all([warehouse, truth_core])

    # Second warehouse for variety
    wh2_id = _id()
    warehouse2 = Warehouse(
        id=wh2_id,
        owner_name="Demo Supplier",
        owner_email="seed-supplier@wex.test",
        owner_phone="+1-555-100-0001",
        address="5678 Commerce Blvd",
        city="Fort Worth",
        state="TX",
        zip="76102",
        lat=32.7555,
        lng=-97.3308,
        building_size_sqft=25000,
        property_type="distribution",
        supplier_status="in_network",
        primary_image_url="https://placehold.co/600x400?text=Distribution",
    )
    truth_core2 = TruthCore(
        id=_id(),
        warehouse_id=wh2_id,
        min_sqft=3000,
        max_sqft=25000,
        clear_height_ft=24,
        dock_doors_receiving=2,
        dock_doors_shipping=2,
        activity_tier="storage_only",
        supplier_rate_per_sqft=4.25,
        activation_status="on",
        min_term_months=3,
    )
    db.add_all([warehouse2, truth_core2])

    # -----------------------------------------------------------------------
    # 3. Create buyer + buyer need
    # -----------------------------------------------------------------------
    buyer = Buyer(
        id=_id(),
        name="Demo Buyer",
        company="Globex Logistics Inc",
        email="seed-buyer@wex.test",
        phone="+1-555-200-0001",
    )
    db.add(buyer)

    need = BuyerNeed(
        id=_id(),
        buyer_id=buyer.id,
        city="Dallas",
        state="TX",
        lat=32.78,
        lng=-96.80,
        radius_miles=25,
        min_sqft=5000,
        max_sqft=30000,
        use_type="storage_light_assembly",
        needed_from=_now(),
        duration_months=12,
        max_budget_per_sqft=8.0,
    )
    db.add(need)

    # -----------------------------------------------------------------------
    # 4. Create engagements at various states
    # -----------------------------------------------------------------------
    engagements_created = []

    def _base_engagement(status, wh=wh_id, **overrides):
        eid = _id()
        eng = Engagement(
            id=eid,
            warehouse_id=wh,
            buyer_need_id=need.id,
            buyer_id=None,  # set explicitly when appropriate
            supplier_id=supplier_user.id,
            status=status.value,
            tier="tier_1",
            match_score=0.85,
            match_rank=1,
            supplier_rate_sqft=5.50,
            buyer_rate_sqft=6.96,
            monthly_supplier_payout=2750.00,
            monthly_buyer_total=3480.00,
            sqft=10000,
            term_months=12,
            deal_ping_sent_at=_ago(days=3),
            deal_ping_expires_at=_ago(days=3) + timedelta(hours=12),
            created_at=_ago(days=3),
        )
        for k, v in overrides.items():
            setattr(eng, k, v)
        engagements_created.append({"id": eid, "status": status.value})
        return eng, eid

    events = []

    # --- (A) deal_ping_sent — fresh, waiting for supplier ---
    eng_a, eid_a = _base_engagement(
        S.DEAL_PING_SENT,
        deal_ping_sent_at=_ago(hours=2),
        deal_ping_expires_at=_future(hours=10),
        created_at=_ago(hours=2),
    )
    db.add(eng_a)
    events.append(_event(eid_a, E.DEAL_PING_SENT, EngagementActor.SYSTEM, S.DEAL_PING_SENT, S.DEAL_PING_SENT))

    # --- (B) deal_ping_accepted — supplier said YES, waiting for buyer match ---
    eng_b, eid_b = _base_engagement(
        S.DEAL_PING_ACCEPTED,
        deal_ping_responded_at=_ago(days=2),
    )
    db.add(eng_b)
    events.append(_event(eid_b, E.DEAL_PING_ACCEPTED, EngagementActor.SUPPLIER, S.DEAL_PING_SENT, S.DEAL_PING_ACCEPTED))

    # --- (C) matched → buyer_reviewing ---
    eng_c, eid_c = _base_engagement(S.BUYER_REVIEWING)
    db.add(eng_c)
    events.append(_event(eid_c, E.MATCHED, EngagementActor.SYSTEM, S.DEAL_PING_ACCEPTED, S.MATCHED))
    events.append(_event(eid_c, E.BUYER_REVIEWING, EngagementActor.BUYER, S.MATCHED, S.BUYER_REVIEWING))

    # --- (D) guarantee_signed — buyer committed, address about to be revealed ---
    eng_d, eid_d = _base_engagement(
        S.GUARANTEE_SIGNED,
        buyer_id=buyer.id,
        buyer_email="seed-buyer@wex.test",
        buyer_phone="+1-555-200-0001",
        buyer_company_name="Globex Logistics Inc",
        guarantee_signed_at=_ago(hours=6),
        guarantee_ip_address="127.0.0.1",
        guarantee_terms_version="v1.0",
    )
    db.add(eng_d)
    events.append(_event(eid_d, E.GUARANTEE_SIGNED, EngagementActor.BUYER, S.CONTACT_CAPTURED, S.GUARANTEE_SIGNED))

    # --- (E) tour_requested — buyer wants a tour, supplier needs to confirm ---
    eng_e, eid_e = _base_engagement(
        S.TOUR_REQUESTED,
        wh=wh2_id,
        buyer_id=buyer.id,
        buyer_email="seed-buyer@wex.test",
        buyer_phone="+1-555-200-0001",
        buyer_company_name="Globex Logistics Inc",
        guarantee_signed_at=_ago(days=1),
        guarantee_ip_address="127.0.0.1",
        path="tour",
        tour_requested_at=_ago(hours=4),
        tour_requested_date=date.today() + timedelta(days=3),
        tour_requested_time="10:00 AM",
    )
    db.add(eng_e)
    events.append(_event(eid_e, E.TOUR_REQUESTED, EngagementActor.BUYER, S.ADDRESS_REVEALED, S.TOUR_REQUESTED))

    # --- (F) tour_confirmed — tour is scheduled for tomorrow ---
    eng_f, eid_f = _base_engagement(
        S.TOUR_CONFIRMED,
        buyer_id=buyer.id,
        buyer_email="seed-buyer@wex.test",
        buyer_phone="+1-555-200-0001",
        buyer_company_name="Globex Logistics Inc",
        guarantee_signed_at=_ago(days=2),
        path="tour",
        tour_requested_at=_ago(days=1),
        tour_requested_date=date.today() + timedelta(days=1),
        tour_requested_time="2:00 PM",
        tour_confirmed_at=_ago(hours=12),
        tour_scheduled_date=_future(days=1),
    )
    db.add(eng_f)
    events.append(_event(eid_f, E.TOUR_CONFIRMED, EngagementActor.SUPPLIER, S.TOUR_REQUESTED, S.TOUR_CONFIRMED))

    # --- (G) tour_completed — awaiting buyer decision ---
    eng_g, eid_g = _base_engagement(
        S.TOUR_COMPLETED,
        buyer_id=buyer.id,
        buyer_email="seed-buyer@wex.test",
        buyer_phone="+1-555-200-0001",
        buyer_company_name="Globex Logistics Inc",
        guarantee_signed_at=_ago(days=5),
        path="tour",
        tour_requested_at=_ago(days=3),
        tour_confirmed_at=_ago(days=2),
        tour_scheduled_date=_ago(days=1),
        tour_completed_at=_ago(hours=6),
        tour_outcome=None,
    )
    db.add(eng_g)
    events.append(_event(eid_g, E.TOUR_COMPLETED, EngagementActor.SYSTEM, S.TOUR_CONFIRMED, S.TOUR_COMPLETED))

    # --- (H) agreement_sent — both parties need to sign ---
    eng_h, eid_h = _base_engagement(
        S.AGREEMENT_SENT,
        buyer_id=buyer.id,
        buyer_email="seed-buyer@wex.test",
        buyer_phone="+1-555-200-0001",
        buyer_company_name="Globex Logistics Inc",
        guarantee_signed_at=_ago(days=7),
        path="tour",
        tour_completed_at=_ago(days=3),
        tour_outcome="confirmed",
        agreement_sent_at=_ago(hours=8),
    )
    db.add(eng_h)
    events.append(_event(eid_h, E.AGREEMENT_SENT, EngagementActor.SYSTEM, S.BUYER_CONFIRMED, S.AGREEMENT_SENT))

    # Create agreement record for this engagement
    agreement_h = EngagementAgreement(
        id=_id(),
        engagement_id=eid_h,
        version="v1.0",
        status=AgreementSignStatus.PENDING.value,
        terms_text="Standard WEx lease agreement...",
        buyer_rate_sqft=6.96,
        supplier_rate_sqft=5.50,
        monthly_buyer_total=3480.00,
        monthly_supplier_payout=2750.00,
        sent_at=_ago(hours=8),
        expires_at=_future(hours=64),
    )
    db.add(agreement_h)

    # --- (I) onboarding — agreement signed, uploading docs ---
    eng_i, eid_i = _base_engagement(
        S.ONBOARDING,
        buyer_id=buyer.id,
        buyer_email="seed-buyer@wex.test",
        buyer_phone="+1-555-200-0001",
        buyer_company_name="Globex Logistics Inc",
        guarantee_signed_at=_ago(days=10),
        path="tour",
        tour_outcome="confirmed",
        agreement_sent_at=_ago(days=5),
        agreement_signed_at=_ago(days=3),
        onboarding_started_at=_ago(days=3),
        insurance_uploaded=True,
        company_docs_uploaded=False,
        payment_method_added=False,
        lease_start_date=date.today() + timedelta(days=14),
        lease_end_date=date.today() + timedelta(days=14 + 365),
    )
    db.add(eng_i)
    events.append(_event(eid_i, E.ONBOARDING_STARTED, EngagementActor.SYSTEM, S.AGREEMENT_SIGNED, S.ONBOARDING))

    # --- (J) active — fully operational lease with payments ---
    eng_j, eid_j = _base_engagement(
        S.ACTIVE,
        wh=wh2_id,
        buyer_id=buyer.id,
        buyer_email="seed-buyer@wex.test",
        buyer_phone="+1-555-200-0001",
        buyer_company_name="Globex Logistics Inc",
        guarantee_signed_at=_ago(days=45),
        path="tour",
        tour_outcome="confirmed",
        agreement_sent_at=_ago(days=35),
        agreement_signed_at=_ago(days=33),
        onboarding_started_at=_ago(days=33),
        onboarding_completed_at=_ago(days=30),
        insurance_uploaded=True,
        company_docs_uploaded=True,
        payment_method_added=True,
        lease_start_date=date.today() - timedelta(days=30),
        lease_end_date=date.today() + timedelta(days=335),
    )
    db.add(eng_j)
    events.append(_event(eid_j, E.LEASE_ACTIVATED, EngagementActor.SYSTEM, S.ONBOARDING, S.ACTIVE))

    # Payment records for the active engagement
    payment1 = PaymentRecord(
        id=_id(),
        engagement_id=eid_j,
        period_start=date.today() - timedelta(days=30),
        period_end=date.today(),
        buyer_amount=3480.00,
        supplier_amount=2750.00,
        wex_amount=730.00,
        buyer_status=BuyerPaymentStatus.PAID.value,
        supplier_status=SupplierPaymentStatus.DEPOSITED.value,
        buyer_paid_at=_ago(days=5),
        supplier_deposited_at=_ago(days=3),
    )
    payment2 = PaymentRecord(
        id=_id(),
        engagement_id=eid_j,
        period_start=date.today(),
        period_end=date.today() + timedelta(days=30),
        buyer_amount=3480.00,
        supplier_amount=2750.00,
        wex_amount=730.00,
        buyer_status=BuyerPaymentStatus.UPCOMING.value,
        supplier_status=SupplierPaymentStatus.UPCOMING.value,
    )
    db.add_all([payment1, payment2])

    # --- (K) instant_book_requested — buyer chose instant book ---
    eng_k, eid_k = _base_engagement(
        S.INSTANT_BOOK_REQUESTED,
        buyer_id=buyer.id,
        buyer_email="seed-buyer@wex.test",
        buyer_phone="+1-555-200-0001",
        buyer_company_name="Globex Logistics Inc",
        guarantee_signed_at=_ago(hours=3),
        path="instant_book",
        instant_book_requested_at=_ago(hours=1),
    )
    db.add(eng_k)
    events.append(_event(eid_k, E.INSTANT_BOOK_REQUESTED, EngagementActor.BUYER, S.GUARANTEE_SIGNED, S.INSTANT_BOOK_REQUESTED))

    # --- (L) declined_by_buyer — buyer passed after tour ---
    eng_l, eid_l = _base_engagement(
        S.DECLINED_BY_BUYER,
        buyer_id=buyer.id,
        buyer_email="seed-buyer@wex.test",
        buyer_phone="+1-555-200-0001",
        buyer_company_name="Globex Logistics Inc",
        guarantee_signed_at=_ago(days=8),
        path="tour",
        tour_outcome="passed",
        tour_completed_at=_ago(days=3),
        declined_by="buyer",
        decline_reason="Space layout doesn't fit our operations",
        declined_at=_ago(days=2),
    )
    db.add(eng_l)
    events.append(_event(eid_l, E.DECLINED_BY_BUYER, EngagementActor.BUYER, S.TOUR_COMPLETED, S.DECLINED_BY_BUYER,
                         data={"reason": "Space layout doesn't fit our operations"}))

    # --- (M) deal_ping_expired — supplier never responded ---
    eng_m, eid_m = _base_engagement(
        S.DEAL_PING_EXPIRED,
        deal_ping_sent_at=_ago(days=2),
        deal_ping_expires_at=_ago(days=2) + timedelta(hours=12),
    )
    db.add(eng_m)
    events.append(_event(eid_m, E.DEAL_PING_EXPIRED, EngagementActor.SYSTEM, S.DEAL_PING_SENT, S.DEAL_PING_EXPIRED))

    # Add all events
    db.add_all(events)

    await db.commit()

    return {
        "message": "Seed data created successfully",
        "seeded": True,
        "users": {
            "supplier": {"email": "seed-supplier@wex.test", "password": "test1234", "id": supplier_user.id},
            "buyer": {"email": "seed-buyer@wex.test", "password": "test1234", "id": buyer_user.id},
            "admin": {"email": "seed-admin@wex.test", "password": "test1234", "id": admin_user.id},
        },
        "warehouses": [wh_id, wh2_id],
        "buyer_need": need.id,
        "engagements": engagements_created,
    }

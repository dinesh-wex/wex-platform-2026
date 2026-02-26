"""Engagement lifecycle API endpoints.

Provides role-filtered CRUD and state-transition endpoints for the
24-state engagement lifecycle. Every mutation goes through the
EngagementStateMachine and produces an EngagementEvent audit record.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.app.routes.auth import get_current_user_dep
from wex_platform.services.auth_service import decode_token
from wex_platform.domain.enums import (
    EngagementActor,
    EngagementEventType,
    EngagementStatus,
)
from wex_platform.domain.models import (
    BuyerAgreement,
    Engagement,
    EngagementAgreement,
    EngagementEvent,
    PaymentRecord,
    User,
    Warehouse,
)
from wex_platform.infra.database import get_db
from wex_platform.services.engagement_state_machine import (
    EngagementStateMachine,
    InvalidTransitionError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engagements", tags=["engagements"])
state_machine = EngagementStateMachine()

# ---------------------------------------------------------------------------
# Pydantic request schemas
# ---------------------------------------------------------------------------


class DealPingAcceptRequest(BaseModel):
    terms_accepted: bool = True
    counter_rate: Optional[float] = None


class DealPingDeclineRequest(BaseModel):
    reason: Optional[str] = None


class TourRequestBody(BaseModel):
    preferred_date: Optional[str] = None
    preferred_time: Optional[str] = None


class TourConfirmRequest(BaseModel):
    scheduled_date: str


class TourRescheduleRequest(BaseModel):
    new_date: str
    new_time: Optional[str] = None
    reason: str


class DeclineRequest(BaseModel):
    reason: Optional[str] = None


class CancelRequest(BaseModel):
    reason: Optional[str] = None


class AcceptMatchRequest(BaseModel):
    path: str  # "tour" or "instant_book"


# ---------------------------------------------------------------------------
# Pydantic response schemas — role-filtered
# ---------------------------------------------------------------------------


class EngagementBuyerView(BaseModel):
    """What buyers see — no supplier rates."""

    id: str
    warehouse_id: str
    buyer_need_id: str
    status: str
    tier: str
    path: Optional[str] = None
    match_score: Optional[float] = None
    match_rank: Optional[int] = None

    # Buyer pricing only
    buyer_rate_sqft: Optional[float] = None
    monthly_buyer_total: Optional[float] = None
    sqft: Optional[int] = None

    # Timestamps
    deal_ping_sent_at: Optional[str] = None
    deal_ping_expires_at: Optional[str] = None

    # Buyer contact
    buyer_company_name: Optional[str] = None

    # Guarantee
    guarantee_signed_at: Optional[str] = None

    # Tour
    tour_requested_at: Optional[str] = None
    tour_requested_date: Optional[str] = None
    tour_requested_time: Optional[str] = None
    tour_confirmed_at: Optional[str] = None
    tour_scheduled_date: Optional[str] = None
    tour_completed_at: Optional[str] = None
    tour_reschedule_count: int = 0
    tour_rescheduled_date: Optional[str] = None
    tour_rescheduled_time: Optional[str] = None
    tour_rescheduled_by: Optional[str] = None
    tour_outcome: Optional[str] = None

    # Instant book
    instant_book_requested_at: Optional[str] = None
    instant_book_confirmed_at: Optional[str] = None

    # Agreement
    agreement_sent_at: Optional[str] = None
    agreement_signed_at: Optional[str] = None

    # Onboarding
    onboarding_started_at: Optional[str] = None
    onboarding_completed_at: Optional[str] = None
    insurance_uploaded: bool = False
    company_docs_uploaded: bool = False
    payment_method_added: bool = False

    # Lease
    term_months: Optional[int] = None
    lease_start_date: Optional[str] = None
    lease_end_date: Optional[str] = None

    # Decline
    declined_by: Optional[str] = None
    decline_reason: Optional[str] = None
    declined_at: Optional[str] = None

    # Cancellation
    cancelled_by: Optional[str] = None
    cancel_reason: Optional[str] = None
    cancelled_at: Optional[str] = None

    # Metadata
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    allowed_actions: list[str] = []


class EngagementSupplierView(BaseModel):
    """What suppliers see — no buyer rates."""

    id: str
    warehouse_id: str
    status: str
    tier: str
    path: Optional[str] = None
    match_score: Optional[float] = None

    # Supplier pricing only
    supplier_rate_sqft: Optional[float] = None
    monthly_supplier_payout: Optional[float] = None
    sqft: Optional[int] = None

    # Deal ping
    deal_ping_sent_at: Optional[str] = None
    deal_ping_expires_at: Optional[str] = None
    deal_ping_responded_at: Optional[str] = None

    # Supplier terms
    supplier_terms_accepted: bool = False
    supplier_terms_version: Optional[str] = None

    # Buyer contact — only visible after account_created
    buyer_company_name: Optional[str] = None

    # Tour
    tour_requested_at: Optional[str] = None
    tour_requested_date: Optional[str] = None
    tour_requested_time: Optional[str] = None
    tour_confirmed_at: Optional[str] = None
    tour_scheduled_date: Optional[str] = None
    tour_completed_at: Optional[str] = None
    tour_reschedule_count: int = 0
    tour_rescheduled_date: Optional[str] = None
    tour_rescheduled_time: Optional[str] = None
    tour_rescheduled_by: Optional[str] = None
    tour_outcome: Optional[str] = None

    # Instant book
    instant_book_requested_at: Optional[str] = None
    instant_book_confirmed_at: Optional[str] = None

    # Agreement
    agreement_sent_at: Optional[str] = None
    agreement_signed_at: Optional[str] = None

    # Onboarding
    onboarding_started_at: Optional[str] = None
    onboarding_completed_at: Optional[str] = None

    # Lease
    term_months: Optional[int] = None
    lease_start_date: Optional[str] = None
    lease_end_date: Optional[str] = None

    # Decline
    declined_by: Optional[str] = None
    decline_reason: Optional[str] = None
    declined_at: Optional[str] = None

    # Cancellation
    cancelled_by: Optional[str] = None
    cancel_reason: Optional[str] = None
    cancelled_at: Optional[str] = None

    # Metadata
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    allowed_actions: list[str] = []


class EngagementAdminView(BaseModel):
    """Admin sees everything."""

    id: str
    warehouse_id: str
    buyer_need_id: str
    buyer_id: Optional[str] = None
    supplier_id: str
    status: str
    tier: str
    path: Optional[str] = None
    match_score: Optional[float] = None
    match_rank: Optional[int] = None

    # All pricing
    supplier_rate_sqft: Optional[float] = None
    buyer_rate_sqft: Optional[float] = None
    monthly_supplier_payout: Optional[float] = None
    monthly_buyer_total: Optional[float] = None
    sqft: Optional[int] = None

    # All timestamps and fields
    deal_ping_sent_at: Optional[str] = None
    deal_ping_expires_at: Optional[str] = None
    deal_ping_responded_at: Optional[str] = None
    supplier_terms_accepted: bool = False
    supplier_terms_version: Optional[str] = None
    buyer_company_name: Optional[str] = None
    account_created_at: Optional[str] = None
    guarantee_signed_at: Optional[str] = None
    guarantee_ip_address: Optional[str] = None
    guarantee_terms_version: Optional[str] = None
    tour_requested_at: Optional[str] = None
    tour_requested_date: Optional[str] = None
    tour_requested_time: Optional[str] = None
    tour_confirmed_at: Optional[str] = None
    tour_scheduled_date: Optional[str] = None
    tour_completed_at: Optional[str] = None
    tour_reschedule_count: int = 0
    tour_rescheduled_date: Optional[str] = None
    tour_rescheduled_time: Optional[str] = None
    tour_rescheduled_by: Optional[str] = None
    tour_outcome: Optional[str] = None
    instant_book_requested_at: Optional[str] = None
    instant_book_confirmed_at: Optional[str] = None
    agreement_sent_at: Optional[str] = None
    agreement_signed_at: Optional[str] = None
    onboarding_started_at: Optional[str] = None
    onboarding_completed_at: Optional[str] = None
    insurance_uploaded: bool = False
    company_docs_uploaded: bool = False
    payment_method_added: bool = False
    term_months: Optional[int] = None
    lease_start_date: Optional[str] = None
    lease_end_date: Optional[str] = None
    declined_by: Optional[str] = None
    decline_reason: Optional[str] = None
    declined_at: Optional[str] = None
    cancelled_by: Optional[str] = None
    cancel_reason: Optional[str] = None
    cancelled_at: Optional[str] = None
    admin_notes: Optional[str] = None
    admin_flagged: bool = False
    admin_flag_reason: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    allowed_actions: list[str] = []


class EngagementEventOut(BaseModel):
    id: str
    engagement_id: str
    event_type: str
    actor: str
    actor_id: Optional[str] = None
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    data: Optional[dict] = None
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Statuses AFTER which buyer contact info is visible to suppliers
_POST_CONTACT_STATUSES = {
    EngagementStatus.ACCOUNT_CREATED.value,
    EngagementStatus.GUARANTEE_SIGNED.value,
    EngagementStatus.ADDRESS_REVEALED.value,
    EngagementStatus.TOUR_REQUESTED.value,
    EngagementStatus.TOUR_CONFIRMED.value,
    EngagementStatus.TOUR_RESCHEDULED.value,
    EngagementStatus.INSTANT_BOOK_REQUESTED.value,
    EngagementStatus.TOUR_COMPLETED.value,
    EngagementStatus.BUYER_CONFIRMED.value,
    EngagementStatus.AGREEMENT_SENT.value,
    EngagementStatus.AGREEMENT_SIGNED.value,
    EngagementStatus.ONBOARDING.value,
    EngagementStatus.ACTIVE.value,
    EngagementStatus.COMPLETED.value,
    EngagementStatus.DECLINED_BY_BUYER.value,
    EngagementStatus.DECLINED_BY_SUPPLIER.value,
}


def _dt(val) -> Optional[str]:
    """Safely convert datetime to ISO string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _num(val) -> Optional[float]:
    """Safely convert Numeric/Decimal to float."""
    if val is None:
        return None
    return float(val)


def _actor_for_role(role: str) -> EngagementActor:
    """Map user role to EngagementActor."""
    mapping = {
        "buyer": EngagementActor.BUYER,
        "supplier": EngagementActor.SUPPLIER,
        "admin": EngagementActor.ADMIN,
        "broker": EngagementActor.ADMIN,
    }
    return mapping.get(role, EngagementActor.BUYER)


def _status_enum(engagement) -> EngagementStatus:
    """Get EngagementStatus enum from model (may be stored as string)."""
    s = engagement.status
    if isinstance(s, EngagementStatus):
        return s
    return EngagementStatus(s)


def serialize_engagement(engagement: Engagement, role: str, actor: EngagementActor) -> dict:
    """Serialize an engagement with role-based field filtering."""
    status_enum = _status_enum(engagement)
    allowed = state_machine.get_allowed_transitions(status_enum, actor)
    allowed_actions = [s.value for s in allowed]

    if role == "admin":
        return EngagementAdminView(
            id=engagement.id,
            warehouse_id=engagement.warehouse_id,
            buyer_need_id=engagement.buyer_need_id,
            buyer_id=engagement.buyer_id,
            supplier_id=engagement.supplier_id,
            status=engagement.status if isinstance(engagement.status, str) else engagement.status.value,
            tier=engagement.tier if isinstance(engagement.tier, str) else engagement.tier.value,
            path=engagement.path if isinstance(engagement.path, str) else (engagement.path.value if engagement.path else None),
            match_score=engagement.match_score,
            match_rank=engagement.match_rank,
            supplier_rate_sqft=_num(engagement.supplier_rate_sqft),
            buyer_rate_sqft=_num(engagement.buyer_rate_sqft),
            monthly_supplier_payout=_num(engagement.monthly_supplier_payout),
            monthly_buyer_total=_num(engagement.monthly_buyer_total),
            sqft=engagement.sqft,
            deal_ping_sent_at=_dt(engagement.deal_ping_sent_at),
            deal_ping_expires_at=_dt(engagement.deal_ping_expires_at),
            deal_ping_responded_at=_dt(engagement.deal_ping_responded_at),
            supplier_terms_accepted=engagement.supplier_terms_accepted or False,
            supplier_terms_version=engagement.supplier_terms_version,
            buyer_company_name=engagement.buyer_company_name,
            account_created_at=_dt(engagement.account_created_at),
            guarantee_signed_at=_dt(engagement.guarantee_signed_at),
            guarantee_ip_address=engagement.guarantee_ip_address,
            guarantee_terms_version=engagement.guarantee_terms_version,
            tour_requested_at=_dt(engagement.tour_requested_at),
            tour_requested_date=_dt(engagement.tour_requested_date),
            tour_requested_time=engagement.tour_requested_time,
            tour_confirmed_at=_dt(engagement.tour_confirmed_at),
            tour_scheduled_date=_dt(engagement.tour_scheduled_date),
            tour_completed_at=_dt(engagement.tour_completed_at),
            tour_reschedule_count=engagement.tour_reschedule_count or 0,
            tour_rescheduled_date=_dt(engagement.tour_rescheduled_date),
            tour_rescheduled_time=engagement.tour_rescheduled_time,
            tour_rescheduled_by=engagement.tour_rescheduled_by,
            tour_outcome=engagement.tour_outcome,
            instant_book_requested_at=_dt(engagement.instant_book_requested_at),
            instant_book_confirmed_at=_dt(engagement.instant_book_confirmed_at),
            agreement_sent_at=_dt(engagement.agreement_sent_at),
            agreement_signed_at=_dt(engagement.agreement_signed_at),
            onboarding_started_at=_dt(engagement.onboarding_started_at),
            onboarding_completed_at=_dt(engagement.onboarding_completed_at),
            insurance_uploaded=engagement.insurance_uploaded or False,
            company_docs_uploaded=engagement.company_docs_uploaded or False,
            payment_method_added=engagement.payment_method_added or False,
            term_months=engagement.term_months,
            lease_start_date=_dt(engagement.lease_start_date),
            lease_end_date=_dt(engagement.lease_end_date),
            declined_by=engagement.declined_by,
            decline_reason=engagement.decline_reason,
            declined_at=_dt(engagement.declined_at),
            cancelled_by=engagement.cancelled_by,
            cancel_reason=engagement.cancel_reason,
            cancelled_at=_dt(engagement.cancelled_at),
            admin_notes=engagement.admin_notes,
            admin_flagged=engagement.admin_flagged or False,
            admin_flag_reason=engagement.admin_flag_reason,
            created_at=_dt(engagement.created_at),
            updated_at=_dt(engagement.updated_at),
            allowed_actions=allowed_actions,
        ).model_dump()

    elif role == "supplier":
        status_str = engagement.status if isinstance(engagement.status, str) else engagement.status.value
        show_contact = status_str in _POST_CONTACT_STATUSES
        return EngagementSupplierView(
            id=engagement.id,
            warehouse_id=engagement.warehouse_id,
            status=status_str,
            tier=engagement.tier if isinstance(engagement.tier, str) else engagement.tier.value,
            path=engagement.path if isinstance(engagement.path, str) else (engagement.path.value if engagement.path else None),
            match_score=engagement.match_score,
            supplier_rate_sqft=_num(engagement.supplier_rate_sqft),
            monthly_supplier_payout=_num(engagement.monthly_supplier_payout),
            sqft=engagement.sqft,
            deal_ping_sent_at=_dt(engagement.deal_ping_sent_at),
            deal_ping_expires_at=_dt(engagement.deal_ping_expires_at),
            deal_ping_responded_at=_dt(engagement.deal_ping_responded_at),
            supplier_terms_accepted=engagement.supplier_terms_accepted or False,
            supplier_terms_version=engagement.supplier_terms_version,
            buyer_company_name=engagement.buyer_company_name if show_contact else None,
            tour_requested_at=_dt(engagement.tour_requested_at),
            tour_requested_date=_dt(engagement.tour_requested_date),
            tour_requested_time=engagement.tour_requested_time,
            tour_confirmed_at=_dt(engagement.tour_confirmed_at),
            tour_scheduled_date=_dt(engagement.tour_scheduled_date),
            tour_completed_at=_dt(engagement.tour_completed_at),
            tour_reschedule_count=engagement.tour_reschedule_count or 0,
            tour_rescheduled_date=_dt(engagement.tour_rescheduled_date),
            tour_rescheduled_time=engagement.tour_rescheduled_time,
            tour_rescheduled_by=engagement.tour_rescheduled_by,
            tour_outcome=engagement.tour_outcome,
            instant_book_requested_at=_dt(engagement.instant_book_requested_at),
            instant_book_confirmed_at=_dt(engagement.instant_book_confirmed_at),
            agreement_sent_at=_dt(engagement.agreement_sent_at),
            agreement_signed_at=_dt(engagement.agreement_signed_at),
            onboarding_started_at=_dt(engagement.onboarding_started_at),
            onboarding_completed_at=_dt(engagement.onboarding_completed_at),
            term_months=engagement.term_months,
            lease_start_date=_dt(engagement.lease_start_date),
            lease_end_date=_dt(engagement.lease_end_date),
            declined_by=engagement.declined_by,
            decline_reason=engagement.decline_reason,
            declined_at=_dt(engagement.declined_at),
            cancelled_by=engagement.cancelled_by,
            cancel_reason=engagement.cancel_reason,
            cancelled_at=_dt(engagement.cancelled_at),
            created_at=_dt(engagement.created_at),
            updated_at=_dt(engagement.updated_at),
            allowed_actions=allowed_actions,
        ).model_dump()

    else:  # buyer
        return EngagementBuyerView(
            id=engagement.id,
            warehouse_id=engagement.warehouse_id,
            buyer_need_id=engagement.buyer_need_id,
            status=engagement.status if isinstance(engagement.status, str) else engagement.status.value,
            tier=engagement.tier if isinstance(engagement.tier, str) else engagement.tier.value,
            path=engagement.path if isinstance(engagement.path, str) else (engagement.path.value if engagement.path else None),
            match_score=engagement.match_score,
            match_rank=engagement.match_rank,
            buyer_rate_sqft=_num(engagement.buyer_rate_sqft),
            monthly_buyer_total=_num(engagement.monthly_buyer_total),
            sqft=engagement.sqft,
            deal_ping_sent_at=_dt(engagement.deal_ping_sent_at),
            deal_ping_expires_at=_dt(engagement.deal_ping_expires_at),
            buyer_company_name=engagement.buyer_company_name,
            guarantee_signed_at=_dt(engagement.guarantee_signed_at),
            tour_requested_at=_dt(engagement.tour_requested_at),
            tour_requested_date=_dt(engagement.tour_requested_date),
            tour_requested_time=engagement.tour_requested_time,
            tour_confirmed_at=_dt(engagement.tour_confirmed_at),
            tour_scheduled_date=_dt(engagement.tour_scheduled_date),
            tour_completed_at=_dt(engagement.tour_completed_at),
            tour_reschedule_count=engagement.tour_reschedule_count or 0,
            tour_rescheduled_date=_dt(engagement.tour_rescheduled_date),
            tour_rescheduled_time=engagement.tour_rescheduled_time,
            tour_rescheduled_by=engagement.tour_rescheduled_by,
            tour_outcome=engagement.tour_outcome,
            instant_book_requested_at=_dt(engagement.instant_book_requested_at),
            instant_book_confirmed_at=_dt(engagement.instant_book_confirmed_at),
            agreement_sent_at=_dt(engagement.agreement_sent_at),
            agreement_signed_at=_dt(engagement.agreement_signed_at),
            onboarding_started_at=_dt(engagement.onboarding_started_at),
            onboarding_completed_at=_dt(engagement.onboarding_completed_at),
            insurance_uploaded=engagement.insurance_uploaded or False,
            company_docs_uploaded=engagement.company_docs_uploaded or False,
            payment_method_added=engagement.payment_method_added or False,
            term_months=engagement.term_months,
            lease_start_date=_dt(engagement.lease_start_date),
            lease_end_date=_dt(engagement.lease_end_date),
            declined_by=engagement.declined_by,
            decline_reason=engagement.decline_reason,
            declined_at=_dt(engagement.declined_at),
            cancelled_by=engagement.cancelled_by,
            cancel_reason=engagement.cancel_reason,
            cancelled_at=_dt(engagement.cancelled_at),
            created_at=_dt(engagement.created_at),
            updated_at=_dt(engagement.updated_at),
            allowed_actions=allowed_actions,
        ).model_dump()


async def get_optional_user_dep(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Optional[User]:
    """Optional auth: returns User if valid token present, else None."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ")
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        return None
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        return None
    return user


async def _get_engagement_or_404(
    db: AsyncSession, engagement_id: str
) -> Engagement:
    """Fetch engagement by ID or raise 404."""
    result = await db.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return engagement


def _check_access(engagement: Engagement, user: User) -> None:
    """Raise 403 if user has no access to this engagement."""
    if user.role == "admin":
        return
    if user.role == "supplier" and engagement.supplier_id == user.id:
        return
    if user.role == "buyer" and engagement.buyer_id == user.id:
        return
    # Buyers can also access engagements where buyer_id is not yet set
    # if they have access via buyer_need (pre-account_created)
    if user.role == "buyer" and engagement.buyer_id is None:
        return  # Allow — will be tightened with buyer_need ownership check
    raise HTTPException(status_code=403, detail="Access denied")


async def _transition_engagement(
    db: AsyncSession,
    engagement: Engagement,
    target_status: EngagementStatus,
    actor: EngagementActor,
    actor_id: str,
    event_type: EngagementEventType,
    extra_data: dict | None = None,
) -> Engagement:
    """Validate and execute a state transition, creating an audit event."""
    current = _status_enum(engagement)
    state_machine.validate_transition(current, target_status, actor, engagement)

    from_status = current
    engagement.status = target_status.value
    engagement.updated_at = datetime.now(timezone.utc)

    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement.id,
        event_type=event_type.value,
        actor=actor.value,
        actor_id=actor_id,
        from_status=from_status.value,
        to_status=target_status.value,
        data=extra_data,
    )
    db.add(event)
    await db.flush()

    logger.info(
        "Engagement %s: %s → %s (actor=%s, user=%s)",
        engagement.id,
        from_status.value,
        target_status.value,
        actor.value,
        actor_id,
    )

    return engagement


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_engagements(
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
):
    """List engagements for the current user, role-filtered."""
    role = user.role if user else "buyer"
    query = select(Engagement)

    if role == "supplier":
        query = query.where(Engagement.supplier_id == user.id)
    elif role == "buyer":
        query = query.where(Engagement.buyer_id == (user.id if user else None))
    # admin sees all

    if status:
        query = query.where(Engagement.status == status)

    query = query.order_by(Engagement.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    engagements = result.scalars().all()

    actor = _actor_for_role(role)
    return [serialize_engagement(e, role, actor) for e in engagements]


@router.get("/{engagement_id}")
async def get_engagement(
    engagement_id: str,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Get a single engagement with role-filtered fields."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    role = user.role if user else "buyer"
    actor = _actor_for_role(role)
    return serialize_engagement(engagement, role, actor)


@router.get("/{engagement_id}/timeline")
async def get_engagement_timeline(
    engagement_id: str,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Get the event timeline for an engagement."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    result = await db.execute(
        select(EngagementEvent)
        .where(EngagementEvent.engagement_id == engagement_id)
        .order_by(EngagementEvent.created_at.asc())
    )
    events = result.scalars().all()

    return [
        EngagementEventOut(
            id=e.id,
            engagement_id=e.engagement_id,
            event_type=e.event_type,
            actor=e.actor,
            actor_id=e.actor_id,
            from_status=e.from_status,
            to_status=e.to_status,
            data=e.data,
            created_at=_dt(e.created_at),
        ).model_dump()
        for e in events
    ]


# --- Deal Ping ---


@router.post("/{engagement_id}/deal-ping/accept")
async def accept_deal_ping(
    engagement_id: str,
    body: DealPingAcceptRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Supplier accepts a deal ping."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    _check_access(engagement, user)

    now = datetime.now(timezone.utc)
    engagement.deal_ping_responded_at = now
    engagement.supplier_terms_accepted = body.terms_accepted
    if body.counter_rate is not None:
        engagement.supplier_rate_sqft = body.counter_rate

    try:
        await _transition_engagement(
            db, engagement,
            EngagementStatus.DEAL_PING_ACCEPTED,
            EngagementActor.SUPPLIER,
            user.id,
            EngagementEventType.DEAL_PING_ACCEPTED,
            extra_data={"terms_accepted": body.terms_accepted, "counter_rate": body.counter_rate},
        )
        await db.commit()
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    actor = _actor_for_role(user.role)
    return serialize_engagement(engagement, user.role, actor)


@router.post("/{engagement_id}/deal-ping/decline")
async def decline_deal_ping(
    engagement_id: str,
    body: DealPingDeclineRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Supplier declines a deal ping."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    _check_access(engagement, user)

    now = datetime.now(timezone.utc)
    engagement.deal_ping_responded_at = now
    engagement.decline_reason = body.reason
    engagement.declined_by = "supplier"
    engagement.declined_at = now

    try:
        await _transition_engagement(
            db, engagement,
            EngagementStatus.DEAL_PING_DECLINED,
            EngagementActor.SUPPLIER,
            user.id,
            EngagementEventType.DEAL_PING_DECLINED,
            extra_data={"reason": body.reason},
        )
        await db.commit()
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    actor = _actor_for_role(user.role)
    return serialize_engagement(engagement, user.role, actor)


# --- Accept Match ---


@router.post("/{engagement_id}/accept")
async def accept_match(
    engagement_id: str,
    body: AcceptMatchRequest,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Buyer accepts a match and chooses a path (tour or instant_book)."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    engagement.path = body.path
    actor_id = user.id if user else "anonymous"

    try:
        await _transition_engagement(
            db, engagement,
            EngagementStatus.BUYER_ACCEPTED,
            EngagementActor.BUYER,
            actor_id,
            EngagementEventType.BUYER_ACCEPTED,
            extra_data={"path": body.path},
        )
        await db.commit()
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info("Engagement %s: buyer accepted with path=%s", engagement.id, body.path)

    role = user.role if user else "buyer"
    actor = _actor_for_role(role)
    return serialize_engagement(engagement, role, actor)


# --- Link Buyer (returning buyers who log in) ---


@router.post("/{engagement_id}/link-buyer")
async def link_buyer(
    engagement_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Links authenticated returning buyer to in-progress engagement after login."""
    engagement = await _get_engagement_or_404(db, engagement_id)

    now = datetime.now(timezone.utc)
    engagement.buyer_id = user.id
    engagement.account_created_at = now

    try:
        await _transition_engagement(
            db, engagement,
            EngagementStatus.ACCOUNT_CREATED,
            EngagementActor.BUYER,
            user.id,
            EngagementEventType.ACCOUNT_CREATED,
            extra_data={"method": "login"},
        )
        await db.commit()
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return serialize_engagement(engagement, "buyer", EngagementActor.BUYER)


# --- Guarantee ---


@router.post("/{engagement_id}/guarantee/sign")
async def sign_guarantee(
    engagement_id: str,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Buyer signs the WEx guarantee, then system auto-reveals address.

    Works for both authenticated and anonymous buyers.
    """
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    now = datetime.now(timezone.utc)
    engagement.guarantee_signed_at = now
    engagement.guarantee_ip_address = request.client.host if request.client else None
    engagement.guarantee_terms_version = "v1.0"  # Hardcoded for Inc 1

    actor_id = user.id if user else "anonymous"

    try:
        # Step 1: buyer signs guarantee
        await _transition_engagement(
            db, engagement,
            EngagementStatus.GUARANTEE_SIGNED,
            EngagementActor.BUYER,
            actor_id,
            EngagementEventType.GUARANTEE_SIGNED,
            extra_data={"ip": engagement.guarantee_ip_address},
        )
        # Create BuyerAgreement record for the occupancy guarantee
        buyer_agreement = BuyerAgreement(
            user_id=engagement.buyer_id,
            buyer_id=engagement.buyer_id or "unknown",
            deal_id=engagement.id,
            agreement_type="occupancy_guarantee",
            signed_at=now,
            status="active",
        )
        db.add(buyer_agreement)

        # Step 2: system auto-reveals address
        await _transition_engagement(
            db, engagement,
            EngagementStatus.ADDRESS_REVEALED,
            EngagementActor.SYSTEM,
            "system",
            EngagementEventType.ADDRESS_REVEALED,
        )
        await db.commit()
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    role = user.role if user else "buyer"
    actor = _actor_for_role(role)
    return serialize_engagement(engagement, role, actor)


# --- Property Details ---


_POST_GUARANTEE_STATUSES = {
    EngagementStatus.ADDRESS_REVEALED.value,
    EngagementStatus.TOUR_REQUESTED.value,
    EngagementStatus.TOUR_CONFIRMED.value,
    EngagementStatus.TOUR_RESCHEDULED.value,
    EngagementStatus.INSTANT_BOOK_REQUESTED.value,
    EngagementStatus.TOUR_COMPLETED.value,
    EngagementStatus.BUYER_CONFIRMED.value,
    EngagementStatus.AGREEMENT_SENT.value,
    EngagementStatus.AGREEMENT_SIGNED.value,
    EngagementStatus.ONBOARDING.value,
    EngagementStatus.ACTIVE.value,
    EngagementStatus.COMPLETED.value,
    EngagementStatus.DECLINED_BY_BUYER.value,
    EngagementStatus.DECLINED_BY_SUPPLIER.value,
}


@router.get("/{engagement_id}/property")
async def get_property_details(
    engagement_id: str,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Get full property details after the buyer has signed the guarantee.

    Works for both authenticated and anonymous buyers.
    """
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    status_str = engagement.status if isinstance(engagement.status, str) else engagement.status.value
    if status_str not in _POST_GUARANTEE_STATUSES:
        raise HTTPException(
            status_code=403,
            detail="Property details available after guarantee is signed",
        )

    result = await db.execute(
        select(Warehouse).where(Warehouse.id == engagement.warehouse_id)
    )
    warehouse = result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    logger.info("Engagement %s: property details retrieved by user %s", engagement.id, user.id if user else "anonymous")

    return {
        "id": warehouse.id,
        "name": warehouse.owner_name,
        "address": warehouse.address,
        "city": warehouse.city,
        "state": warehouse.state,
        "zip_code": warehouse.zip,
        "total_sqft": warehouse.building_size_sqft,
        "available_sqft": engagement.sqft,
    }


# --- Tour ---


@router.post("/{engagement_id}/tour/request")
async def request_tour(
    engagement_id: str,
    body: TourRequestBody = TourRequestBody(),
    request: Request = None,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Buyer requests a property tour."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    engagement.tour_requested_at = datetime.now(timezone.utc)
    engagement.path = "tour"
    if body.preferred_date:
        from datetime import date as date_type
        try:
            engagement.tour_requested_date = date_type.fromisoformat(body.preferred_date)
        except (ValueError, TypeError):
            pass
    engagement.tour_requested_time = body.preferred_time

    actor_id = user.id if user else "anonymous"

    try:
        await _transition_engagement(
            db, engagement,
            EngagementStatus.TOUR_REQUESTED,
            EngagementActor.BUYER,
            actor_id,
            EngagementEventType.TOUR_REQUESTED,
            extra_data={"preferred_date": body.preferred_date, "preferred_time": body.preferred_time},
        )
        await db.commit()
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    role = user.role if user else "buyer"
    actor = _actor_for_role(role)
    return serialize_engagement(engagement, role, actor)


@router.post("/{engagement_id}/tour/confirm")
async def confirm_tour(
    engagement_id: str,
    body: TourConfirmRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Supplier confirms a tour with a scheduled date."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    _check_access(engagement, user)

    engagement.tour_confirmed_at = datetime.now(timezone.utc)
    engagement.tour_scheduled_date = datetime.fromisoformat(body.scheduled_date)

    try:
        await _transition_engagement(
            db, engagement,
            EngagementStatus.TOUR_CONFIRMED,
            EngagementActor.SUPPLIER,
            user.id,
            EngagementEventType.TOUR_CONFIRMED,
            extra_data={"scheduled_date": body.scheduled_date},
        )

        # Notify buyer of tour confirmation
        if engagement.buyer_id:
            # Eager-load buyer to avoid async lazy-load error
            from sqlalchemy import select as sa_select
            from wex_platform.domain.models import User as UserModel
            buyer_result = await db.execute(
                sa_select(UserModel).where(UserModel.id == engagement.buyer_id)
            )
            buyer_user = buyer_result.scalar_one_or_none()
            if buyer_user and buyer_user.email:
                logger.info(
                    "[engagement] tour_confirmed email would be sent to %s — engagement=%s, date=%s",
                    buyer_user.email,
                    engagement.id,
                    body.scheduled_date,
                )
            else:
                logger.warning(
                    "[engagement] tour_confirmed but no buyer email — engagement=%s",
                    engagement.id,
                )
        else:
            logger.warning(
                "[engagement] tour_confirmed but no buyer_id — engagement=%s",
                engagement.id,
            )

        await db.commit()
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    actor = _actor_for_role(user.role)
    return serialize_engagement(engagement, user.role, actor)


@router.post("/{engagement_id}/tour/reschedule")
async def reschedule_tour(
    engagement_id: str,
    body: TourRescheduleRequest,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Buyer or supplier reschedules a tour."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    engagement.tour_reschedule_count = (engagement.tour_reschedule_count or 0) + 1
    engagement.tour_scheduled_date = datetime.fromisoformat(body.new_date)

    # Populate first-class reschedule columns
    from datetime import date as date_type
    try:
        engagement.tour_rescheduled_date = date_type.fromisoformat(body.new_date)
    except (ValueError, TypeError):
        pass
    engagement.tour_rescheduled_time = body.new_time

    role = user.role if user else "buyer"
    actor_enum = _actor_for_role(role)
    engagement.tour_rescheduled_by = actor_enum.value
    actor_id = user.id if user else "anonymous"

    try:
        await _transition_engagement(
            db, engagement,
            EngagementStatus.TOUR_RESCHEDULED,
            actor_enum,
            actor_id,
            EngagementEventType.TOUR_RESCHEDULED,
            extra_data={"new_date": body.new_date, "new_time": body.new_time, "reason": body.reason},
        )
        await db.commit()
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return serialize_engagement(engagement, role, actor_enum)


# --- Instant Book ---


@router.post("/{engagement_id}/instant-book")
async def request_instant_book(
    engagement_id: str,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Buyer requests instant book (skip tour)."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    engagement.instant_book_requested_at = datetime.now(timezone.utc)
    engagement.path = "instant_book"
    actor_id = user.id if user else "anonymous"

    try:
        await _transition_engagement(
            db, engagement,
            EngagementStatus.INSTANT_BOOK_REQUESTED,
            EngagementActor.BUYER,
            actor_id,
            EngagementEventType.INSTANT_BOOK_REQUESTED,
        )
        await db.commit()
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    role = user.role if user else "buyer"
    actor = _actor_for_role(role)
    return serialize_engagement(engagement, role, actor)


# --- Decline (generic) ---


@router.post("/{engagement_id}/decline")
async def decline_engagement(
    engagement_id: str,
    body: DeclineRequest,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Buyer or supplier declines the engagement."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    now = datetime.now(timezone.utc)
    role = user.role if user else "buyer"
    actor_enum = _actor_for_role(role)
    actor_id = user.id if user else "anonymous"

    if role == "supplier":
        target = EngagementStatus.DECLINED_BY_SUPPLIER
        event_type = EngagementEventType.DECLINED_BY_SUPPLIER
        engagement.declined_by = "supplier"
    else:
        target = EngagementStatus.DECLINED_BY_BUYER
        event_type = EngagementEventType.DECLINED_BY_BUYER
        engagement.declined_by = "buyer"

    engagement.decline_reason = body.reason
    engagement.declined_at = now

    try:
        await _transition_engagement(
            db, engagement, target, actor_enum, actor_id, event_type,
            extra_data={"reason": body.reason},
        )
        await db.commit()
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return serialize_engagement(engagement, role, actor_enum)


@router.post("/{engagement_id}/cancel")
async def cancel_engagement(
    engagement_id: str,
    body: CancelRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Admin cancels an engagement from any active state."""
    engagement = await _get_engagement_or_404(db, engagement_id)

    if user.role not in ("admin", "broker"):
        raise HTTPException(status_code=403, detail="Only admins can cancel engagements")

    now = datetime.now(timezone.utc)
    engagement.cancelled_by = user.role
    engagement.cancel_reason = body.reason
    engagement.cancelled_at = now

    try:
        await _transition_engagement(
            db, engagement,
            EngagementStatus.CANCELLED,
            EngagementActor.ADMIN,
            user.id,
            EngagementEventType.CANCELLED,
            extra_data={"reason": body.reason, "cancelled_by": user.role},
        )
        await db.commit()
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return serialize_engagement(engagement, user.role, EngagementActor.ADMIN)


# ===========================================================================
# INCREMENT 2 — Post-Tour → Active Lease
# ===========================================================================


# --- Pydantic request schemas (Inc 2) ---


class TourOutcomeRequest(BaseModel):
    outcome: str  # "confirmed" or "passed"
    reason: Optional[str] = None


class AgreementSignRequest(BaseModel):
    role: str  # "buyer" or "supplier"


class OnboardingUploadRequest(BaseModel):
    document_url: Optional[str] = None  # placeholder for file upload path


class PaymentMethodRequest(BaseModel):
    payment_method_type: str = "ach"  # ach, wire, card
    last_four: Optional[str] = None


# --- Pydantic response schemas (Inc 2) ---


class AgreementOut(BaseModel):
    id: str
    engagement_id: str
    version: int
    status: str
    terms_text: str
    buyer_rate_sqft: Optional[float] = None
    supplier_rate_sqft: Optional[float] = None
    monthly_buyer_total: Optional[float] = None
    monthly_supplier_payout: Optional[float] = None
    sent_at: Optional[str] = None
    buyer_signed_at: Optional[str] = None
    supplier_signed_at: Optional[str] = None
    expires_at: Optional[str] = None
    created_at: Optional[str] = None


class OnboardingOut(BaseModel):
    engagement_id: str
    insurance_uploaded: bool = False
    company_docs_uploaded: bool = False
    payment_method_added: bool = False
    onboarding_started_at: Optional[str] = None
    onboarding_completed_at: Optional[str] = None
    all_complete: bool = False


class PaymentRecordOut(BaseModel):
    id: str
    engagement_id: str
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    buyer_amount: Optional[float] = None
    supplier_amount: Optional[float] = None
    wex_amount: Optional[float] = None
    buyer_status: str = "upcoming"
    supplier_status: str = "upcoming"
    buyer_invoiced_at: Optional[str] = None
    buyer_paid_at: Optional[str] = None
    supplier_scheduled_at: Optional[str] = None
    supplier_deposited_at: Optional[str] = None
    created_at: Optional[str] = None


# --- Agreement role-filtering helper ---


def _serialize_agreement(agreement: EngagementAgreement, role: str) -> dict:
    """Serialize agreement with role-based filtering."""
    data = AgreementOut(
        id=agreement.id,
        engagement_id=agreement.engagement_id,
        version=agreement.version,
        status=agreement.status if isinstance(agreement.status, str) else agreement.status,
        terms_text=agreement.terms_text,
        sent_at=_dt(agreement.sent_at),
        buyer_signed_at=_dt(agreement.buyer_signed_at),
        supplier_signed_at=_dt(agreement.supplier_signed_at),
        expires_at=_dt(agreement.expires_at),
        created_at=_dt(agreement.created_at),
    )

    result = data.model_dump()

    # Role-filter pricing on agreement too
    if role == "buyer":
        result["buyer_rate_sqft"] = _num(agreement.buyer_rate_sqft)
        result["monthly_buyer_total"] = _num(agreement.monthly_buyer_total)
        result["supplier_rate_sqft"] = None
        result["monthly_supplier_payout"] = None
    elif role == "supplier":
        result["supplier_rate_sqft"] = _num(agreement.supplier_rate_sqft)
        result["monthly_supplier_payout"] = _num(agreement.monthly_supplier_payout)
        result["buyer_rate_sqft"] = None
        result["monthly_buyer_total"] = None
    else:  # admin
        result["buyer_rate_sqft"] = _num(agreement.buyer_rate_sqft)
        result["supplier_rate_sqft"] = _num(agreement.supplier_rate_sqft)
        result["monthly_buyer_total"] = _num(agreement.monthly_buyer_total)
        result["monthly_supplier_payout"] = _num(agreement.monthly_supplier_payout)

    return result


def _serialize_payment(payment: PaymentRecord, role: str) -> dict:
    """Serialize payment record with role-based filtering."""
    result = PaymentRecordOut(
        id=payment.id,
        engagement_id=payment.engagement_id,
        period_start=_dt(payment.period_start),
        period_end=_dt(payment.period_end),
        buyer_status=payment.buyer_status if isinstance(payment.buyer_status, str) else payment.buyer_status,
        supplier_status=payment.supplier_status if isinstance(payment.supplier_status, str) else payment.supplier_status,
        buyer_invoiced_at=_dt(payment.buyer_invoiced_at),
        buyer_paid_at=_dt(payment.buyer_paid_at),
        supplier_scheduled_at=_dt(payment.supplier_scheduled_at),
        supplier_deposited_at=_dt(payment.supplier_deposited_at),
        created_at=_dt(payment.created_at),
    ).model_dump()

    # Role-filter amounts
    if role == "buyer":
        result["buyer_amount"] = _num(payment.buyer_amount)
        result["supplier_amount"] = None
        result["wex_amount"] = None
    elif role == "supplier":
        result["supplier_amount"] = _num(payment.supplier_amount)
        result["buyer_amount"] = None
        result["wex_amount"] = None
    else:  # admin
        result["buyer_amount"] = _num(payment.buyer_amount)
        result["supplier_amount"] = _num(payment.supplier_amount)
        result["wex_amount"] = _num(payment.wex_amount)

    return result


# --- Tour Outcome ---


@router.post("/{engagement_id}/tour/outcome")
async def submit_tour_outcome(
    engagement_id: str,
    body: TourOutcomeRequest,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Buyer submits tour outcome: confirmed (proceed) or passed (decline)."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    now = datetime.now(timezone.utc)
    engagement.tour_completed_at = now
    engagement.tour_outcome = body.outcome
    actor_id = user.id if user else "anonymous"

    try:
        # First: system marks tour as completed
        await _transition_engagement(
            db, engagement,
            EngagementStatus.TOUR_COMPLETED,
            EngagementActor.SYSTEM,
            "system",
            EngagementEventType.TOUR_COMPLETED,
        )

        if body.outcome == "confirmed":
            # Tour completed → buyer_confirmed → system auto-sends agreement
            await _transition_engagement(
                db, engagement,
                EngagementStatus.BUYER_CONFIRMED,
                EngagementActor.BUYER,
                actor_id,
                EngagementEventType.BUYER_CONFIRMED,
                extra_data={"tour_outcome": "confirmed"},
            )

            # Auto-generate and send agreement
            from datetime import timedelta
            agreement = EngagementAgreement(
                id=str(uuid.uuid4()),
                engagement_id=engagement.id,
                version=1,
                status="pending",
                terms_text=_generate_agreement_terms(engagement),
                buyer_rate_sqft=engagement.buyer_rate_sqft,
                supplier_rate_sqft=engagement.supplier_rate_sqft,
                monthly_buyer_total=engagement.monthly_buyer_total,
                monthly_supplier_payout=engagement.monthly_supplier_payout,
                sent_at=now,
                expires_at=now + timedelta(hours=72),
            )
            db.add(agreement)

            # Auto-transition to agreement_sent
            await _transition_engagement(
                db, engagement,
                EngagementStatus.AGREEMENT_SENT,
                EngagementActor.SYSTEM,
                "system",
                EngagementEventType.AGREEMENT_SENT,
            )

        elif body.outcome == "passed":
            engagement.declined_by = "buyer"
            engagement.decline_reason = body.reason
            engagement.declined_at = now
            await _transition_engagement(
                db, engagement,
                EngagementStatus.DECLINED_BY_BUYER,
                EngagementActor.BUYER,
                actor_id,
                EngagementEventType.BUYER_PASSED,
                extra_data={"reason": body.reason},
            )
        else:
            raise HTTPException(status_code=400, detail="outcome must be 'confirmed' or 'passed'")

        await db.commit()
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    role = user.role if user else "buyer"
    actor = _actor_for_role(role)
    return serialize_engagement(engagement, role, actor)


def _generate_agreement_terms(engagement: Engagement) -> str:
    """Generate agreement terms text for the engagement."""
    sqft = engagement.sqft or 0
    buyer_rate = _num(engagement.buyer_rate_sqft) or 0
    supplier_rate = _num(engagement.supplier_rate_sqft) or 0
    monthly_buyer = _num(engagement.monthly_buyer_total) or 0
    monthly_supplier = _num(engagement.monthly_supplier_payout) or 0

    return (
        f"WAREHOUSE EXCHANGE LEASE AGREEMENT\n\n"
        f"This Lease Agreement ('Agreement') is entered into between the Supplier "
        f"and the Buyer for warehouse space facilitated through Warehouse Exchange (WEx).\n\n"
        f"SPACE: {sqft:,} sq ft at the Property identified in this engagement.\n\n"
        f"RATES:\n"
        f"- Buyer Monthly Rate: ${monthly_buyer:,.2f} (${buyer_rate:.4f}/sq ft)\n"
        f"- Supplier Monthly Payout: ${monthly_supplier:,.2f} (${supplier_rate:.4f}/sq ft)\n\n"
        f"TERM: As specified in the engagement details.\n\n"
        f"TERMS AND CONDITIONS:\n"
        f"1. Buyer shall pay monthly rent on or before the 1st of each month.\n"
        f"2. Supplier shall maintain the property in good working condition.\n"
        f"3. WEx facilitates payments between parties.\n"
        f"4. Either party may terminate with 30 days written notice.\n"
        f"5. This agreement is subject to WEx Platform Terms of Service.\n\n"
        f"By signing below, both parties agree to the terms of this lease.\n"
    )


# --- Agreement ---


@router.get("/{engagement_id}/agreement")
async def get_agreement(
    engagement_id: str,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Get the current agreement for an engagement."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    result = await db.execute(
        select(EngagementAgreement)
        .where(EngagementAgreement.engagement_id == engagement_id)
        .order_by(EngagementAgreement.version.desc())
        .limit(1)
    )
    agreement = result.scalar_one_or_none()
    if not agreement:
        raise HTTPException(status_code=404, detail="No agreement found for this engagement")

    role = user.role if user else "buyer"
    return _serialize_agreement(agreement, role)


@router.post("/{engagement_id}/agreement/sign")
async def sign_agreement(
    engagement_id: str,
    body: AgreementSignRequest,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Sign the engagement agreement (buyer or supplier)."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    actor_id = user.id if user else "anonymous"

    result = await db.execute(
        select(EngagementAgreement)
        .where(EngagementAgreement.engagement_id == engagement_id)
        .order_by(EngagementAgreement.version.desc())
        .limit(1)
    )
    agreement = result.scalar_one_or_none()
    if not agreement:
        raise HTTPException(status_code=404, detail="No agreement found")

    # Check agreement not expired
    if agreement.expires_at:
        expires = agreement.expires_at
        if hasattr(expires, 'tzinfo') and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            agreement.status = "expired"
            try:
                await _transition_engagement(
                    db, engagement,
                    EngagementStatus.EXPIRED,
                    EngagementActor.SYSTEM,
                    "system",
                    EngagementEventType.AGREEMENT_EXPIRED,
                )
            except InvalidTransitionError:
                pass
            await db.commit()
            raise HTTPException(status_code=400, detail="Agreement has expired")

    now = datetime.now(timezone.utc)

    if body.role == "buyer":
        if agreement.buyer_signed_at:
            raise HTTPException(status_code=400, detail="Buyer has already signed")
        agreement.buyer_signed_at = now
        agreement.status = "buyer_signed" if not agreement.supplier_signed_at else "fully_signed"

        event = EngagementEvent(
            id=str(uuid.uuid4()),
            engagement_id=engagement.id,
            event_type=EngagementEventType.AGREEMENT_BUYER_SIGNED.value,
            actor=EngagementActor.BUYER.value,
            actor_id=actor_id,
            from_status=engagement.status,
            to_status=engagement.status,
            data={"agreement_id": agreement.id},
        )
        db.add(event)
        logger.info("Agreement %s: buyer signed (engagement=%s)", agreement.id, engagement.id)

    elif body.role == "supplier":
        if agreement.supplier_signed_at:
            raise HTTPException(status_code=400, detail="Supplier has already signed")
        agreement.supplier_signed_at = now
        agreement.status = "supplier_signed" if not agreement.buyer_signed_at else "fully_signed"

        event = EngagementEvent(
            id=str(uuid.uuid4()),
            engagement_id=engagement.id,
            event_type=EngagementEventType.AGREEMENT_SUPPLIER_SIGNED.value,
            actor=EngagementActor.SUPPLIER.value,
            actor_id=actor_id,
            from_status=engagement.status,
            to_status=engagement.status,
            data={"agreement_id": agreement.id},
        )
        db.add(event)
        logger.info("Agreement %s: supplier signed (engagement=%s)", agreement.id, engagement.id)

    else:
        raise HTTPException(status_code=400, detail="role must be 'buyer' or 'supplier'")

    # If both have signed, transition engagement to agreement_signed → onboarding
    if agreement.buyer_signed_at and agreement.supplier_signed_at:
        agreement.status = "fully_signed"
        try:
            await _transition_engagement(
                db, engagement,
                EngagementStatus.AGREEMENT_SIGNED,
                EngagementActor.SYSTEM,
                "system",
                EngagementEventType.AGREEMENT_SIGNED,
                extra_data={"agreement_id": agreement.id},
            )
            # Auto-start onboarding
            engagement.onboarding_started_at = now
            await _transition_engagement(
                db, engagement,
                EngagementStatus.ONBOARDING,
                EngagementActor.SYSTEM,
                "system",
                EngagementEventType.ONBOARDING_STARTED,
            )
        except InvalidTransitionError as e:
            logger.warning("Agreement fully signed but transition failed: %s", e)

    await db.commit()
    role = user.role if user else "buyer"
    return _serialize_agreement(agreement, role)


# --- Onboarding ---


@router.get("/{engagement_id}/onboarding")
async def get_onboarding_status(
    engagement_id: str,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Get onboarding status for an engagement."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    all_complete = (
        bool(engagement.insurance_uploaded)
        and bool(engagement.company_docs_uploaded)
        and bool(engagement.payment_method_added)
    )

    return OnboardingOut(
        engagement_id=engagement.id,
        insurance_uploaded=engagement.insurance_uploaded or False,
        company_docs_uploaded=engagement.company_docs_uploaded or False,
        payment_method_added=engagement.payment_method_added or False,
        onboarding_started_at=_dt(engagement.onboarding_started_at),
        onboarding_completed_at=_dt(engagement.onboarding_completed_at),
        all_complete=all_complete,
    ).model_dump()


@router.post("/{engagement_id}/onboarding/insurance")
async def upload_insurance(
    engagement_id: str,
    body: OnboardingUploadRequest = OnboardingUploadRequest(),
    request: Request = None,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Mark insurance as uploaded."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    role = user.role if user else "buyer"
    actor_id = user.id if user else "anonymous"

    engagement.insurance_uploaded = True
    engagement.updated_at = datetime.now(timezone.utc)

    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement.id,
        event_type=EngagementEventType.INSURANCE_UPLOADED.value,
        actor=_actor_for_role(role).value,
        actor_id=actor_id,
        from_status=engagement.status,
        to_status=engagement.status,
        data={"document_url": body.document_url},
    )
    db.add(event)
    logger.info("Onboarding: insurance uploaded (engagement=%s)", engagement.id)

    await _check_onboarding_complete(db, engagement, actor_id)
    await db.commit()

    return {"ok": True, "insurance_uploaded": True}


@router.post("/{engagement_id}/onboarding/company-docs")
async def upload_company_docs(
    engagement_id: str,
    body: OnboardingUploadRequest = OnboardingUploadRequest(),
    request: Request = None,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Mark company docs as uploaded."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    role = user.role if user else "buyer"
    actor_id = user.id if user else "anonymous"

    engagement.company_docs_uploaded = True
    engagement.updated_at = datetime.now(timezone.utc)

    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement.id,
        event_type=EngagementEventType.COMPANY_DOCS_UPLOADED.value,
        actor=_actor_for_role(role).value,
        actor_id=actor_id,
        from_status=engagement.status,
        to_status=engagement.status,
        data={"document_url": body.document_url},
    )
    db.add(event)
    logger.info("Onboarding: company docs uploaded (engagement=%s)", engagement.id)

    await _check_onboarding_complete(db, engagement, actor_id)
    await db.commit()

    return {"ok": True, "company_docs_uploaded": True}


@router.post("/{engagement_id}/onboarding/payment")
async def submit_payment_method(
    engagement_id: str,
    body: PaymentMethodRequest = PaymentMethodRequest(),
    request: Request = None,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Submit payment method for onboarding."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    role = user.role if user else "buyer"
    actor_id = user.id if user else "anonymous"

    engagement.payment_method_added = True
    engagement.updated_at = datetime.now(timezone.utc)

    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement.id,
        event_type=EngagementEventType.PAYMENT_METHOD_ADDED.value,
        actor=_actor_for_role(role).value,
        actor_id=actor_id,
        from_status=engagement.status,
        to_status=engagement.status,
        data={"payment_method_type": body.payment_method_type, "last_four": body.last_four},
    )
    db.add(event)
    logger.info("Onboarding: payment method added (engagement=%s)", engagement.id)

    await _check_onboarding_complete(db, engagement, actor_id)
    await db.commit()

    return {"ok": True, "payment_method_added": True}


async def _check_onboarding_complete(
    db: AsyncSession, engagement: Engagement, actor_id: str
) -> None:
    """If all onboarding steps complete, transition to active."""
    if not (engagement.insurance_uploaded and engagement.company_docs_uploaded and engagement.payment_method_added):
        return

    now = datetime.now(timezone.utc)
    engagement.onboarding_completed_at = now

    try:
        await _transition_engagement(
            db, engagement,
            EngagementStatus.ACTIVE,
            EngagementActor.SYSTEM,
            "system",
            EngagementEventType.ONBOARDING_COMPLETED,
        )

        # Set lease start date
        engagement.lease_start_date = now.date()

        event = EngagementEvent(
            id=str(uuid.uuid4()),
            engagement_id=engagement.id,
            event_type=EngagementEventType.LEASE_ACTIVATED.value,
            actor=EngagementActor.SYSTEM.value,
            actor_id="system",
            from_status=EngagementStatus.ONBOARDING.value,
            to_status=EngagementStatus.ACTIVE.value,
            data={"lease_start_date": str(now.date())},
        )
        db.add(event)
        logger.info("Onboarding complete → ACTIVE (engagement=%s)", engagement.id)

    except InvalidTransitionError as e:
        logger.warning("Onboarding complete but transition failed: %s", e)


# --- Payments ---


@router.get("/{engagement_id}/payments")
async def get_engagement_payments(
    engagement_id: str,
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Get payment records for an engagement."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    if user:
        _check_access(engagement, user)

    role = user.role if user else "buyer"

    result = await db.execute(
        select(PaymentRecord)
        .where(PaymentRecord.engagement_id == engagement_id)
        .order_by(PaymentRecord.period_start.desc())
    )
    payments = result.scalars().all()

    return [_serialize_payment(p, role) for p in payments]


# --- Buyer payments (cross-engagement) ---


buyer_payments_router = APIRouter(prefix="/api/buyer", tags=["buyer-payments"])


@buyer_payments_router.get("/payments")
async def get_buyer_payments(
    request: Request,
    user: Optional[User] = Depends(get_optional_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Get all payments across buyer's engagements."""
    role = user.role if user else "buyer"
    if role not in ("buyer", "admin"):
        raise HTTPException(status_code=403, detail="Buyers only")

    actor_id = user.id if user else None

    eng_result = await db.execute(
        select(Engagement.id).where(Engagement.buyer_id == actor_id)
    )
    eng_ids = [row[0] for row in eng_result.fetchall()]

    if not eng_ids:
        return []

    result = await db.execute(
        select(PaymentRecord)
        .where(PaymentRecord.engagement_id.in_(eng_ids))
        .order_by(PaymentRecord.period_start.desc())
    )
    payments = result.scalars().all()

    return [_serialize_payment(p, role) for p in payments]

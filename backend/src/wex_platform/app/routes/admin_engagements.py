"""Admin portal API endpoints for engagement management.

Provides full-access engagement views, status overrides, notes,
deadline extensions, Q&A admin answers, and dashboard metrics.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.app.routes.auth import get_current_user_dep
from wex_platform.domain.enums import (
    EngagementActor,
    EngagementEventType,
    EngagementStatus,
    QuestionStatus,
)
from wex_platform.domain.models import (
    Engagement,
    EngagementAgreement,
    EngagementEvent,
    PaymentRecord,
    PropertyQuestion,
    User,
)
from wex_platform.infra.database import get_db
from wex_platform.services.engagement_state_machine import (
    EngagementStateMachine,
    InvalidTransitionError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/engagements", tags=["admin-engagements"])
state_machine = EngagementStateMachine()


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class StatusOverrideRequest(BaseModel):
    new_status: str
    reason: str


class AdminNoteRequest(BaseModel):
    note: str


class DeadlineExtendRequest(BaseModel):
    field: str  # e.g., "deal_ping_expires_at"
    extend_hours: int = 24


class AdminQAAnswerRequest(BaseModel):
    answer_text: str


class PaymentStatusRequest(BaseModel):
    action: str  # "mark_paid" or "mark_deposited"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dt(val) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _num(val) -> Optional[float]:
    if val is None:
        return None
    return float(val)


def _check_admin(user: User):
    if user.role not in ("admin", "broker"):
        raise HTTPException(status_code=403, detail="Admin access required")


async def _get_engagement_or_404(db: AsyncSession, engagement_id: str) -> Engagement:
    result = await db.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return engagement


def _serialize_admin_engagement(engagement: Engagement) -> dict:
    """Full admin view of an engagement."""
    return {
        "id": engagement.id,
        "warehouse_id": engagement.warehouse_id,
        "buyer_need_id": engagement.buyer_need_id,
        "buyer_id": engagement.buyer_id,
        "supplier_id": engagement.supplier_id,
        "status": engagement.status if isinstance(engagement.status, str) else engagement.status.value,
        "tier": engagement.tier if isinstance(engagement.tier, str) else engagement.tier.value,
        "path": engagement.path if isinstance(engagement.path, str) else (engagement.path.value if engagement.path else None),
        "match_score": engagement.match_score,
        "match_rank": engagement.match_rank,
        "supplier_rate_sqft": _num(engagement.supplier_rate_sqft),
        "buyer_rate_sqft": _num(engagement.buyer_rate_sqft),
        "monthly_supplier_payout": _num(engagement.monthly_supplier_payout),
        "monthly_buyer_total": _num(engagement.monthly_buyer_total),
        "sqft": engagement.sqft,
        "deal_ping_sent_at": _dt(engagement.deal_ping_sent_at),
        "deal_ping_expires_at": _dt(engagement.deal_ping_expires_at),
        "deal_ping_responded_at": _dt(engagement.deal_ping_responded_at),
        "supplier_terms_accepted": engagement.supplier_terms_accepted or False,
        "supplier_terms_version": engagement.supplier_terms_version,
        "buyer_email": engagement.buyer_email,
        "buyer_phone": engagement.buyer_phone,
        "buyer_company_name": engagement.buyer_company_name,
        "guarantee_signed_at": _dt(engagement.guarantee_signed_at),
        "guarantee_ip_address": engagement.guarantee_ip_address,
        "guarantee_terms_version": engagement.guarantee_terms_version,
        "tour_requested_at": _dt(engagement.tour_requested_at),
        "tour_confirmed_at": _dt(engagement.tour_confirmed_at),
        "tour_scheduled_date": _dt(engagement.tour_scheduled_date),
        "tour_completed_at": _dt(engagement.tour_completed_at),
        "tour_reschedule_count": engagement.tour_reschedule_count or 0,
        "tour_outcome": engagement.tour_outcome,
        "instant_book_requested_at": _dt(engagement.instant_book_requested_at),
        "instant_book_confirmed_at": _dt(engagement.instant_book_confirmed_at),
        "agreement_sent_at": _dt(engagement.agreement_sent_at),
        "agreement_signed_at": _dt(engagement.agreement_signed_at),
        "onboarding_started_at": _dt(engagement.onboarding_started_at),
        "onboarding_completed_at": _dt(engagement.onboarding_completed_at),
        "insurance_uploaded": engagement.insurance_uploaded or False,
        "company_docs_uploaded": engagement.company_docs_uploaded or False,
        "payment_method_added": engagement.payment_method_added or False,
        "lease_start_date": _dt(engagement.lease_start_date),
        "lease_end_date": _dt(engagement.lease_end_date),
        "declined_by": engagement.declined_by,
        "decline_reason": engagement.decline_reason,
        "declined_at": _dt(engagement.declined_at),
        "admin_notes": engagement.admin_notes,
        "admin_flagged": engagement.admin_flagged or False,
        "admin_flag_reason": engagement.admin_flag_reason,
        "created_at": _dt(engagement.created_at),
        "updated_at": _dt(engagement.updated_at),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_all_engagements(
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    tier: Optional[str] = Query(None),
    path: Optional[str] = Query(None),
    flagged: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    """Admin lists all engagements with filters."""
    _check_admin(user)

    query = select(Engagement)

    if status:
        query = query.where(Engagement.status == status)
    if tier:
        query = query.where(Engagement.tier == tier)
    if path:
        query = query.where(Engagement.path == path)
    if flagged is not None:
        query = query.where(Engagement.admin_flagged == flagged)

    query = query.order_by(Engagement.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    engagements = result.scalars().all()

    return [_serialize_admin_engagement(e) for e in engagements]


@router.get("/dashboard")
async def admin_dashboard(
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate dashboard metrics for admin."""
    _check_admin(user)

    # Count engagements by status
    result = await db.execute(
        select(Engagement.status, sa_func.count(Engagement.id))
        .group_by(Engagement.status)
    )
    status_counts = {row[0]: row[1] for row in result.fetchall()}

    # Active engagements (non-terminal)
    terminal = {"completed", "declined_by_buyer", "declined_by_supplier", "expired", "deal_ping_expired", "deal_ping_declined"}
    active_count = sum(v for k, v in status_counts.items() if k not in terminal)
    total_count = sum(status_counts.values())

    # Flagged count
    flagged_result = await db.execute(
        select(sa_func.count(Engagement.id)).where(Engagement.admin_flagged == True)
    )
    flagged_count = flagged_result.scalar() or 0

    # Pending deal pings
    pending_pings = status_counts.get("deal_ping_sent", 0)

    # Close rate (completed / (completed + declined + expired))
    completed = status_counts.get("completed", 0)
    closed_total = completed + sum(
        status_counts.get(s, 0) for s in terminal
    )
    close_rate = (completed / closed_total * 100) if closed_total > 0 else 0

    # Active leases
    active_leases = status_counts.get("active", 0)

    # In onboarding
    in_onboarding = status_counts.get("onboarding", 0)

    return {
        "total_engagements": total_count,
        "active_engagements": active_count,
        "active_leases": active_leases,
        "in_onboarding": in_onboarding,
        "pending_deal_pings": pending_pings,
        "flagged_count": flagged_count,
        "close_rate_percent": round(close_rate, 1),
        "status_breakdown": status_counts,
    }


@router.get("/{engagement_id}")
async def admin_get_engagement(
    engagement_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Admin gets full engagement detail."""
    _check_admin(user)
    engagement = await _get_engagement_or_404(db, engagement_id)
    return _serialize_admin_engagement(engagement)


@router.post("/{engagement_id}/status")
async def admin_override_status(
    engagement_id: str,
    body: StatusOverrideRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Admin overrides engagement status with a reason."""
    _check_admin(user)
    engagement = await _get_engagement_or_404(db, engagement_id)

    try:
        new_status = EngagementStatus(body.new_status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {body.new_status}")

    old_status = engagement.status if isinstance(engagement.status, str) else engagement.status.value
    now = datetime.now(timezone.utc)

    # Admin override — state machine allows admin from any non-terminal state
    current_enum = EngagementStatus(old_status) if isinstance(old_status, str) else old_status
    try:
        state_machine.validate_transition(
            current_enum, new_status, EngagementActor.ADMIN, engagement
        )
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    engagement.status = new_status.value
    engagement.updated_at = now

    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement.id,
        event_type=EngagementEventType.ADMIN_OVERRIDE.value,
        actor=EngagementActor.ADMIN.value,
        actor_id=user.id,
        from_status=old_status,
        to_status=new_status.value,
        data={"reason": body.reason, "overridden_by": user.id},
    )
    db.add(event)
    await db.commit()

    logger.info(
        "Admin override: %s → %s (reason=%s, engagement=%s, admin=%s)",
        old_status, new_status.value, body.reason, engagement.id, user.id,
    )
    return _serialize_admin_engagement(engagement)


@router.post("/{engagement_id}/note")
async def admin_add_note(
    engagement_id: str,
    body: AdminNoteRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Admin adds a note to an engagement."""
    _check_admin(user)
    engagement = await _get_engagement_or_404(db, engagement_id)

    now = datetime.now(timezone.utc)
    # Append to existing notes
    existing = engagement.admin_notes or ""
    timestamp = now.strftime("%Y-%m-%d %H:%M UTC")
    new_note = f"[{timestamp}] {body.note}"
    engagement.admin_notes = f"{existing}\n{new_note}".strip() if existing else new_note
    engagement.updated_at = now

    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement.id,
        event_type=EngagementEventType.NOTE_ADDED.value,
        actor=EngagementActor.ADMIN.value,
        actor_id=user.id,
        from_status=engagement.status if isinstance(engagement.status, str) else engagement.status.value,
        to_status=engagement.status if isinstance(engagement.status, str) else engagement.status.value,
        data={"note": body.note},
    )
    db.add(event)
    await db.commit()

    logger.info("Admin note added (engagement=%s)", engagement.id)
    return {"ok": True, "admin_notes": engagement.admin_notes}


@router.post("/{engagement_id}/extend-deadline")
async def admin_extend_deadline(
    engagement_id: str,
    body: DeadlineExtendRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Admin extends a deadline field on the engagement."""
    _check_admin(user)
    engagement = await _get_engagement_or_404(db, engagement_id)

    # Validate field exists
    allowed_fields = {
        "deal_ping_expires_at",
        "supplier_deadline_at",
    }
    if body.field not in allowed_fields and not hasattr(engagement, body.field):
        raise HTTPException(status_code=400, detail=f"Invalid deadline field: {body.field}")

    current_value = getattr(engagement, body.field, None)
    now = datetime.now(timezone.utc)

    if current_value is None:
        new_deadline = now + timedelta(hours=body.extend_hours)
    else:
        if hasattr(current_value, 'tzinfo') and current_value.tzinfo is None:
            current_value = current_value.replace(tzinfo=timezone.utc)
        # Extend from the later of now or current deadline
        base = max(now, current_value)
        new_deadline = base + timedelta(hours=body.extend_hours)

    setattr(engagement, body.field, new_deadline)
    engagement.updated_at = now

    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement.id,
        event_type=EngagementEventType.DEADLINE_EXTENDED.value,
        actor=EngagementActor.ADMIN.value,
        actor_id=user.id,
        from_status=engagement.status if isinstance(engagement.status, str) else engagement.status.value,
        to_status=engagement.status if isinstance(engagement.status, str) else engagement.status.value,
        data={
            "field": body.field,
            "extend_hours": body.extend_hours,
            "new_deadline": new_deadline.isoformat(),
        },
    )
    db.add(event)
    await db.commit()

    logger.info(
        "Admin extended deadline %s by %dh (engagement=%s, new=%s)",
        body.field, body.extend_hours, engagement.id, new_deadline.isoformat(),
    )
    return {
        "ok": True,
        "field": body.field,
        "new_deadline": new_deadline.isoformat(),
    }


@router.post("/{engagement_id}/qa/{question_id}/answer")
async def admin_answer_question(
    engagement_id: str,
    question_id: str,
    body: AdminQAAnswerRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Admin answers a Q&A question directly."""
    _check_admin(user)
    engagement = await _get_engagement_or_404(db, engagement_id)

    result = await db.execute(
        select(PropertyQuestion).where(PropertyQuestion.id == question_id)
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    now = datetime.now(timezone.utc)
    question.final_answer = body.answer_text
    question.final_answer_source = "admin"
    question.status = QuestionStatus.ANSWERED.value

    # Resume timer if paused
    if question.timer_paused_at and not question.timer_resumed_at:
        question.timer_resumed_at = now

    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement_id,
        event_type=EngagementEventType.QUESTION_ANSWERED.value,
        actor=EngagementActor.ADMIN.value,
        actor_id=user.id,
        from_status=engagement.status if isinstance(engagement.status, str) else engagement.status.value,
        to_status=engagement.status if isinstance(engagement.status, str) else engagement.status.value,
        data={"question_id": question.id, "answer_source": "admin"},
    )
    db.add(event)

    # Save to knowledge base
    from wex_platform.app.routes.qa import _save_to_knowledge_base
    await _save_to_knowledge_base(db, engagement.warehouse_id, question)

    await db.commit()
    logger.info("Admin answered question %s (engagement=%s)", question.id, engagement_id)

    return {"ok": True, "question_id": question.id, "answer": body.answer_text}


# --- Payment admin ---


payment_admin_router = APIRouter(prefix="/api/admin/payments", tags=["admin-payments"])


@payment_admin_router.post("/{payment_id}/mark-paid")
async def admin_mark_paid(
    payment_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Admin marks a buyer payment as paid."""
    _check_admin(user)

    result = await db.execute(
        select(PaymentRecord).where(PaymentRecord.id == payment_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    now = datetime.now(timezone.utc)
    payment.buyer_status = "paid"
    payment.buyer_paid_at = now
    payment.updated_at = now

    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=payment.engagement_id,
        event_type=EngagementEventType.PAYMENT_RECORDED.value,
        actor=EngagementActor.ADMIN.value,
        actor_id=user.id,
        from_status=None,
        to_status=None,
        data={"payment_id": payment.id, "action": "mark_paid"},
    )
    db.add(event)
    await db.commit()

    logger.info("Admin marked payment %s as paid", payment.id)
    return {"ok": True, "payment_id": payment.id, "buyer_status": "paid"}


@payment_admin_router.post("/{payment_id}/mark-deposited")
async def admin_mark_deposited(
    payment_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Admin marks a supplier payout as deposited."""
    _check_admin(user)

    result = await db.execute(
        select(PaymentRecord).where(PaymentRecord.id == payment_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    now = datetime.now(timezone.utc)
    payment.supplier_status = "deposited"
    payment.supplier_deposited_at = now
    payment.updated_at = now

    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=payment.engagement_id,
        event_type=EngagementEventType.PAYMENT_RECORDED.value,
        actor=EngagementActor.ADMIN.value,
        actor_id=user.id,
        from_status=None,
        to_status=None,
        data={"payment_id": payment.id, "action": "mark_deposited"},
    )
    db.add(event)
    await db.commit()

    logger.info("Admin marked payment %s as deposited", payment.id)
    return {"ok": True, "payment_id": payment.id, "supplier_status": "deposited"}

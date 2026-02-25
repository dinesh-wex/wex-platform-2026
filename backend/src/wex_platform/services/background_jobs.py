"""Background jobs for engagement lifecycle automation.

11 jobs from spec Section 15. All jobs are idempotent — running twice
produces no duplicate events or records.

These are defined as async functions to be called by a scheduler
(e.g., APScheduler, Celery Beat, or a simple cron runner).
"""

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

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
)
from wex_platform.services.engagement_state_machine import (
    EngagementStateMachine,
    InvalidTransitionError,
    TERMINAL_STATES,
)

logger = logging.getLogger(__name__)
state_machine = EngagementStateMachine()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _expire_engagement(
    db: AsyncSession,
    engagement: Engagement,
    reason: str,
    event_type: EngagementEventType = EngagementEventType.EXPIRED,
) -> bool:
    """Transition engagement to expired state. Returns True on success."""
    old_status = engagement.status if isinstance(engagement.status, str) else engagement.status.value
    current_enum = EngagementStatus(old_status) if isinstance(old_status, str) else old_status

    # Determine target based on current state
    if current_enum == EngagementStatus.DEAL_PING_SENT:
        target = EngagementStatus.DEAL_PING_EXPIRED
        event_type = EngagementEventType.DEAL_PING_EXPIRED
    else:
        target = EngagementStatus.EXPIRED

    try:
        state_machine.validate_transition(
            current_enum, target, EngagementActor.SYSTEM, engagement
        )
    except InvalidTransitionError:
        return False

    engagement.status = target.value
    engagement.updated_at = datetime.now(timezone.utc)

    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement.id,
        event_type=event_type.value,
        actor=EngagementActor.SYSTEM.value,
        actor_id="system",
        from_status=old_status,
        to_status=target.value,
        data={"reason": reason},
    )
    db.add(event)
    return True


async def _log_event(
    db: AsyncSession,
    engagement_id: str,
    event_type: EngagementEventType,
    data: dict | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
) -> None:
    """Create an engagement event (no state change)."""
    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement_id,
        event_type=event_type.value,
        actor=EngagementActor.SYSTEM.value,
        actor_id="system",
        from_status=from_status,
        to_status=to_status,
        data=data,
    )
    db.add(event)


# ---------------------------------------------------------------------------
# Job 1: Check deal ping deadlines (every 15 min)
# ---------------------------------------------------------------------------


async def check_deal_ping_deadlines(db: AsyncSession) -> int:
    """Expire deal pings that have passed their deadline.

    Returns the number of engagements expired.
    """
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(Engagement).where(
            and_(
                Engagement.status == EngagementStatus.DEAL_PING_SENT.value,
                Engagement.deal_ping_expires_at.isnot(None),
                Engagement.deal_ping_expires_at < now,
            )
        )
    )
    expired = result.scalars().all()

    count = 0
    for eng in expired:
        if await _expire_engagement(db, eng, "Deal ping deadline expired"):
            count += 1
            logger.info("Deal ping expired: engagement=%s", eng.id)

    if count:
        await db.commit()
    return count


# ---------------------------------------------------------------------------
# Job 2: Check general deadlines (every 15 min)
# ---------------------------------------------------------------------------

# Status → (deadline_field, max_hours, reason)
_DEADLINE_CHECKS = {
    EngagementStatus.TOUR_REQUESTED.value: (
        "tour_requested_at", 12, "Tour request expired — supplier didn't confirm within 12 hours"
    ),
    EngagementStatus.TOUR_COMPLETED.value: (
        "tour_completed_at", 72, "Post-tour decision expired — buyer didn't respond within 72 hours"
    ),
    EngagementStatus.ADDRESS_REVEALED.value: (
        "updated_at", 168, "Address revealed but no action taken within 7 days"
    ),
}


async def check_deadlines(db: AsyncSession) -> int:
    """Expire engagements past their status-specific deadlines.

    Returns number expired.
    """
    now = datetime.now(timezone.utc)
    count = 0

    for status_val, (field, hours, reason) in _DEADLINE_CHECKS.items():
        cutoff = now - timedelta(hours=hours)

        result = await db.execute(
            select(Engagement).where(
                and_(
                    Engagement.status == status_val,
                    getattr(Engagement, field) < cutoff,
                )
            )
        )
        engagements = result.scalars().all()

        for eng in engagements:
            if await _expire_engagement(db, eng, reason):
                count += 1
                logger.info("Deadline expired: engagement=%s, status=%s", eng.id, status_val)

    if count:
        await db.commit()
    return count


# ---------------------------------------------------------------------------
# Job 3: Send tour reminders (daily 6 AM)
# ---------------------------------------------------------------------------


async def send_tour_reminders(db: AsyncSession) -> int:
    """Send reminders for tours happening tomorrow.

    Returns number of reminders logged.
    """
    now = datetime.now(timezone.utc)
    tomorrow_start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow_end = tomorrow_start + timedelta(days=1)

    result = await db.execute(
        select(Engagement).where(
            and_(
                Engagement.status.in_([
                    EngagementStatus.TOUR_CONFIRMED.value,
                    EngagementStatus.TOUR_RESCHEDULED.value,
                ]),
                Engagement.tour_scheduled_date.isnot(None),
                Engagement.tour_scheduled_date >= tomorrow_start,
                Engagement.tour_scheduled_date < tomorrow_end,
            )
        )
    )
    engagements = result.scalars().all()

    count = 0
    for eng in engagements:
        # Check if reminder already sent (idempotency)
        existing = await db.execute(
            select(EngagementEvent).where(
                and_(
                    EngagementEvent.engagement_id == eng.id,
                    EngagementEvent.event_type == EngagementEventType.REMINDER_SENT.value,
                    EngagementEvent.created_at >= now.replace(hour=0, minute=0, second=0),
                )
            )
        )
        if existing.scalar_one_or_none():
            continue

        await _log_event(
            db, eng.id,
            EngagementEventType.REMINDER_SENT,
            data={"type": "tour_reminder", "tour_date": str(eng.tour_scheduled_date)},
        )
        count += 1
        logger.info("Tour reminder sent: engagement=%s, date=%s", eng.id, eng.tour_scheduled_date)

    if count:
        await db.commit()
    return count


# ---------------------------------------------------------------------------
# Job 4: Send post-tour follow-up (every hour)
# ---------------------------------------------------------------------------


async def send_post_tour_followup(db: AsyncSession) -> int:
    """Send follow-up nudge 24 hours after tour completion.

    Returns number of follow-ups sent.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    result = await db.execute(
        select(Engagement).where(
            and_(
                Engagement.status == EngagementStatus.TOUR_COMPLETED.value,
                Engagement.tour_completed_at.isnot(None),
                Engagement.tour_completed_at <= cutoff,
            )
        )
    )
    engagements = result.scalars().all()

    count = 0
    for eng in engagements:
        # Idempotency check
        existing = await db.execute(
            select(EngagementEvent).where(
                and_(
                    EngagementEvent.engagement_id == eng.id,
                    EngagementEvent.event_type == EngagementEventType.REMINDER_SENT.value,
                    EngagementEvent.data.contains({"type": "post_tour_followup"}),
                )
            )
        )
        if existing.scalar_one_or_none():
            continue

        await _log_event(
            db, eng.id,
            EngagementEventType.REMINDER_SENT,
            data={"type": "post_tour_followup", "hours_since_tour": 24},
        )
        count += 1
        logger.info("Post-tour follow-up sent: engagement=%s", eng.id)

    if count:
        await db.commit()
    return count


# ---------------------------------------------------------------------------
# Job 5: Check Q&A supplier deadline (every hour)
# ---------------------------------------------------------------------------


async def check_qa_supplier_deadline(db: AsyncSession) -> int:
    """Check for questions where supplier's 24hr answer window has expired.

    Resumes the buyer's post-tour timer and notifies admin.
    Returns number of expired questions.
    """
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(PropertyQuestion).where(
            and_(
                PropertyQuestion.status == QuestionStatus.ROUTED_TO_SUPPLIER.value,
                PropertyQuestion.supplier_deadline_at.isnot(None),
                PropertyQuestion.supplier_deadline_at < now,
            )
        )
    )
    questions = result.scalars().all()

    count = 0
    for q in questions:
        q.status = QuestionStatus.EXPIRED.value

        # Resume timer if paused
        if q.timer_paused_at and not q.timer_resumed_at:
            q.timer_resumed_at = now

        await _log_event(
            db, q.engagement_id,
            EngagementEventType.QUESTION_ANSWERED,
            data={
                "question_id": q.id,
                "expired": True,
                "reason": "Supplier did not answer within 24 hours",
            },
        )
        count += 1
        logger.info("Q&A supplier deadline expired: question=%s, engagement=%s", q.id, q.engagement_id)

    if count:
        await db.commit()
    return count


# ---------------------------------------------------------------------------
# Job 6: Save Q&A to property knowledge (triggered on answer)
# ---------------------------------------------------------------------------
# This job is triggered inline when a question is answered (see qa.py).
# Defined here for completeness and for batch-mode backfill if needed.


async def save_qa_to_property_knowledge(db: AsyncSession) -> int:
    """Backfill: save answered questions to property knowledge base that aren't already saved.

    Returns number of new entries created.
    """
    result = await db.execute(
        select(PropertyQuestion).where(
            and_(
                PropertyQuestion.status == QuestionStatus.ANSWERED.value,
                PropertyQuestion.final_answer.isnot(None),
            )
        )
    )
    questions = result.scalars().all()

    from wex_platform.domain.models import PropertyKnowledgeEntry

    count = 0
    for q in questions:
        # Check if already in knowledge base
        existing = await db.execute(
            select(PropertyKnowledgeEntry).where(
                PropertyKnowledgeEntry.source_question_id == q.id
            )
        )
        if existing.scalar_one_or_none():
            continue

        entry = PropertyKnowledgeEntry(
            id=str(uuid.uuid4()),
            warehouse_id=q.warehouse_id,
            question=q.question_text,
            answer=q.final_answer,
            source=q.final_answer_source or "unknown",
            source_question_id=q.id,
            confidence=q.ai_confidence or 0.9,
        )
        db.add(entry)
        count += 1

    if count:
        await db.commit()
        logger.info("Knowledge backfill: created %d entries", count)
    return count


# ---------------------------------------------------------------------------
# Job 7: Generate payment records (daily midnight)
# ---------------------------------------------------------------------------


async def generate_payment_records(db: AsyncSession) -> int:
    """Generate monthly payment records for active engagements.

    Checks if a payment record already exists for the current billing period.
    Returns number of new records created.
    """
    today = date.today()
    # Billing period: 1st of current month to last day of current month
    period_start = today.replace(day=1)
    if today.month == 12:
        period_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        period_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

    result = await db.execute(
        select(Engagement).where(Engagement.status == EngagementStatus.ACTIVE.value)
    )
    active_engagements = result.scalars().all()

    count = 0
    for eng in active_engagements:
        # Check if payment already exists for this period (idempotency)
        existing = await db.execute(
            select(PaymentRecord).where(
                and_(
                    PaymentRecord.engagement_id == eng.id,
                    PaymentRecord.period_start == period_start,
                )
            )
        )
        if existing.scalar_one_or_none():
            continue

        buyer_amount = float(eng.monthly_buyer_total or 0)
        supplier_amount = float(eng.monthly_supplier_payout or 0)
        wex_amount = buyer_amount - supplier_amount

        payment = PaymentRecord(
            id=str(uuid.uuid4()),
            engagement_id=eng.id,
            period_start=period_start,
            period_end=period_end,
            buyer_amount=buyer_amount,
            supplier_amount=supplier_amount,
            wex_amount=wex_amount,
            buyer_status="upcoming",
            supplier_status="upcoming",
        )
        db.add(payment)

        await _log_event(
            db, eng.id,
            EngagementEventType.PAYMENT_RECORDED,
            data={
                "payment_id": payment.id,
                "period": f"{period_start} to {period_end}",
                "buyer_amount": buyer_amount,
            },
        )
        count += 1
        logger.info("Payment record created: engagement=%s, period=%s to %s", eng.id, period_start, period_end)

    if count:
        await db.commit()
    return count


# ---------------------------------------------------------------------------
# Job 8: Send payment reminders (daily 9 AM)
# ---------------------------------------------------------------------------


async def send_payment_reminders(db: AsyncSession) -> int:
    """Send reminders for invoiced payments approaching due date.

    Returns number of reminders sent.
    """
    now = datetime.now(timezone.utc)
    today = date.today()

    result = await db.execute(
        select(PaymentRecord).where(
            and_(
                PaymentRecord.buyer_status == "invoiced",
                PaymentRecord.period_start <= today + timedelta(days=3),
            )
        )
    )
    payments = result.scalars().all()

    count = 0
    for p in payments:
        # Idempotency: check if reminder already sent today
        existing = await db.execute(
            select(EngagementEvent).where(
                and_(
                    EngagementEvent.engagement_id == p.engagement_id,
                    EngagementEvent.event_type == EngagementEventType.REMINDER_SENT.value,
                    EngagementEvent.data.contains({"payment_id": p.id}),
                    EngagementEvent.created_at >= now.replace(hour=0, minute=0, second=0),
                )
            )
        )
        if existing.scalar_one_or_none():
            continue

        await _log_event(
            db, p.engagement_id,
            EngagementEventType.REMINDER_SENT,
            data={"type": "payment_reminder", "payment_id": p.id, "period_start": str(p.period_start)},
        )
        count += 1

    if count:
        await db.commit()
        logger.info("Payment reminders sent: %d", count)
    return count


# ---------------------------------------------------------------------------
# Job 9: Flag stale engagements (daily 8 AM)
# ---------------------------------------------------------------------------


async def flag_stale_engagements(db: AsyncSession) -> int:
    """Flag engagements stuck in the same non-terminal state for > 3 days.

    Returns number of engagements flagged.
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=3)

    terminal_values = [s.value for s in TERMINAL_STATES]

    result = await db.execute(
        select(Engagement).where(
            and_(
                Engagement.status.notin_(terminal_values),
                Engagement.status.notin_([EngagementStatus.ACTIVE.value]),  # Active isn't stale
                Engagement.updated_at < cutoff,
                or_(
                    Engagement.admin_flagged == False,
                    Engagement.admin_flagged.is_(None),
                ),
            )
        )
    )
    engagements = result.scalars().all()

    count = 0
    for eng in engagements:
        eng.admin_flagged = True
        eng.admin_flag_reason = f"Stale: in {eng.status} for >3 days (last updated {eng.updated_at})"
        eng.updated_at = now

        await _log_event(
            db, eng.id,
            EngagementEventType.ADMIN_NOTE,
            data={"flag": "stale", "status": eng.status, "days_stale": 3},
        )
        count += 1
        logger.info("Flagged stale engagement: %s (status=%s)", eng.id, eng.status)

    if count:
        await db.commit()
    return count


# ---------------------------------------------------------------------------
# Job 10: Auto-activate leases (daily midnight)
# ---------------------------------------------------------------------------


async def auto_activate_leases(db: AsyncSession) -> int:
    """Activate leases where onboarding is complete and start date is reached.

    Returns number of leases activated.
    """
    today = date.today()

    result = await db.execute(
        select(Engagement).where(
            and_(
                Engagement.status == EngagementStatus.ONBOARDING.value,
                Engagement.insurance_uploaded == True,
                Engagement.company_docs_uploaded == True,
                Engagement.payment_method_added == True,
                or_(
                    Engagement.lease_start_date.is_(None),
                    Engagement.lease_start_date <= today,
                ),
            )
        )
    )
    engagements = result.scalars().all()

    count = 0
    for eng in engagements:
        old_status = eng.status
        current_enum = EngagementStatus(old_status) if isinstance(old_status, str) else old_status

        try:
            state_machine.validate_transition(
                current_enum, EngagementStatus.ACTIVE, EngagementActor.SYSTEM, eng
            )
        except InvalidTransitionError:
            continue

        eng.status = EngagementStatus.ACTIVE.value
        eng.onboarding_completed_at = datetime.now(timezone.utc)
        if not eng.lease_start_date:
            eng.lease_start_date = today
        eng.updated_at = datetime.now(timezone.utc)

        event = EngagementEvent(
            id=str(uuid.uuid4()),
            engagement_id=eng.id,
            event_type=EngagementEventType.LEASE_ACTIVATED.value,
            actor=EngagementActor.SYSTEM.value,
            actor_id="system",
            from_status=old_status,
            to_status=EngagementStatus.ACTIVE.value,
            data={"lease_start_date": str(eng.lease_start_date)},
        )
        db.add(event)
        count += 1
        logger.info("Auto-activated lease: engagement=%s", eng.id)

    if count:
        await db.commit()
    return count


# ---------------------------------------------------------------------------
# Job 11: Renewal prompts (daily 9 AM)
# ---------------------------------------------------------------------------


async def send_renewal_prompts(db: AsyncSession) -> int:
    """Send renewal prompts for leases ending within 30 days.

    Returns number of prompts sent.
    """
    today = date.today()
    cutoff = today + timedelta(days=30)

    result = await db.execute(
        select(Engagement).where(
            and_(
                Engagement.status == EngagementStatus.ACTIVE.value,
                Engagement.lease_end_date.isnot(None),
                Engagement.lease_end_date <= cutoff,
                Engagement.lease_end_date > today,
            )
        )
    )
    engagements = result.scalars().all()

    now = datetime.now(timezone.utc)
    count = 0
    for eng in engagements:
        # Idempotency: check if renewal prompt already sent
        existing = await db.execute(
            select(EngagementEvent).where(
                and_(
                    EngagementEvent.engagement_id == eng.id,
                    EngagementEvent.event_type == EngagementEventType.REMINDER_SENT.value,
                    EngagementEvent.data.contains({"type": "renewal_prompt"}),
                )
            )
        )
        if existing.scalar_one_or_none():
            continue

        await _log_event(
            db, eng.id,
            EngagementEventType.REMINDER_SENT,
            data={
                "type": "renewal_prompt",
                "lease_end_date": str(eng.lease_end_date),
                "days_remaining": (eng.lease_end_date - today).days,
            },
        )
        count += 1
        logger.info("Renewal prompt sent: engagement=%s, ends=%s", eng.id, eng.lease_end_date)

    if count:
        await db.commit()
    return count

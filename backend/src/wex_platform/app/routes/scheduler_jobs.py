"""Scheduler job endpoints — called by Cloud Scheduler (GCP).

Each endpoint wraps a function from background_jobs.py or hold_monitor.
Auth: internal token header (same pattern as sms_scheduler.py).
"""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.app.config import get_settings
from wex_platform.infra.database import get_db

logger = logging.getLogger(__name__)


async def verify_internal_token(x_internal_token: str = Header(...)):
    """Verify that the request includes a valid internal auth token."""
    settings = get_settings()
    if x_internal_token != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid internal token")


router = APIRouter(
    prefix="/api/internal/scheduler",
    tags=["scheduler-jobs"],
    dependencies=[Depends(verify_internal_token)],
)


@router.post("/hold-monitor")
async def hold_monitor(db: AsyncSession = Depends(get_db)):
    """Run hold expiry checks (replaces in-process hold_monitor_loop)."""
    from wex_platform.services.hold_monitor import check_hold_expiry_warnings, expire_holds

    warnings = await check_hold_expiry_warnings(db)
    expired = await expire_holds(db)
    logger.info("Hold monitor: warnings=%s, expired=%d", warnings, expired)
    return {"ok": True, "warnings": warnings, "expired": expired}


@router.post("/deal-ping-deadlines")
async def deal_ping_deadlines(db: AsyncSession = Depends(get_db)):
    """Expire deal pings past their deadline."""
    from wex_platform.services.background_jobs import check_deal_ping_deadlines

    count = await check_deal_ping_deadlines(db)
    logger.info("Deal ping deadlines: expired=%d", count)
    return {"ok": True, "expired": count}


@router.post("/deadlines")
async def deadlines(db: AsyncSession = Depends(get_db)):
    """Expire engagements past status-specific deadlines."""
    from wex_platform.services.background_jobs import check_deadlines

    count = await check_deadlines(db)
    logger.info("General deadlines: expired=%d", count)
    return {"ok": True, "expired": count}


@router.post("/tour-reminders")
async def tour_reminders(db: AsyncSession = Depends(get_db)):
    """Send reminders for tours happening tomorrow."""
    from wex_platform.services.background_jobs import send_tour_reminders

    count = await send_tour_reminders(db)
    logger.info("Tour reminders: sent=%d", count)
    return {"ok": True, "sent": count}


@router.post("/post-tour-followup")
async def post_tour_followup(db: AsyncSession = Depends(get_db)):
    """Send follow-up nudge 24h after tour completion."""
    from wex_platform.services.background_jobs import send_post_tour_followup

    count = await send_post_tour_followup(db)
    logger.info("Post-tour follow-up: sent=%d", count)
    return {"ok": True, "sent": count}


@router.post("/qa-deadline")
async def qa_deadline(db: AsyncSession = Depends(get_db)):
    """Check for questions where supplier answer window expired."""
    from wex_platform.services.background_jobs import check_qa_supplier_deadline

    count = await check_qa_supplier_deadline(db)
    logger.info("Q&A deadline: expired=%d", count)
    return {"ok": True, "expired": count}


@router.post("/payment-records")
async def payment_records(db: AsyncSession = Depends(get_db)):
    """Generate monthly payment records for active engagements."""
    from wex_platform.services.background_jobs import generate_payment_records

    count = await generate_payment_records(db)
    logger.info("Payment records: created=%d", count)
    return {"ok": True, "created": count}


@router.post("/payment-reminders")
async def payment_reminders(db: AsyncSession = Depends(get_db)):
    """Send reminders for invoiced payments approaching due date."""
    from wex_platform.services.background_jobs import send_payment_reminders

    count = await send_payment_reminders(db)
    logger.info("Payment reminders: sent=%d", count)
    return {"ok": True, "sent": count}


@router.post("/stale-engagements")
async def stale_engagements(db: AsyncSession = Depends(get_db)):
    """Flag engagements stuck in same state for >3 days."""
    from wex_platform.services.background_jobs import flag_stale_engagements

    count = await flag_stale_engagements(db)
    logger.info("Stale engagements: flagged=%d", count)
    return {"ok": True, "flagged": count}


@router.post("/auto-activate")
async def auto_activate(db: AsyncSession = Depends(get_db)):
    """Activate leases where onboarding is complete and start date reached."""
    from wex_platform.services.background_jobs import auto_activate_leases

    count = await auto_activate_leases(db)
    logger.info("Auto-activate leases: activated=%d", count)
    return {"ok": True, "activated": count}


@router.post("/renewal-prompts")
async def renewal_prompts(db: AsyncSession = Depends(get_db)):
    """Send renewal prompts for leases ending within 30 days."""
    from wex_platform.services.background_jobs import send_renewal_prompts

    count = await send_renewal_prompts(db)
    logger.info("Renewal prompts: sent=%d", count)
    return {"ok": True, "sent": count}


@router.post("/check-waitlist")
async def check_waitlist(db: AsyncSession = Depends(get_db)):
    """Check waitlist entries against new inventory."""
    from wex_platform.services.waitlist_service import WaitlistService

    service = WaitlistService(db)
    matched = await service.check_waitlist_matches()
    logger.info("Waitlist check: matched=%d", matched)
    return {"ok": True, "matched": matched}

"""SMS Scheduler cron endpoint — called by Cloud Scheduler (GCP)."""
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
    tags=["sms-scheduler"],
    dependencies=[Depends(verify_internal_token)],
)


@router.post("/sms-tick")
async def sms_tick(db: AsyncSession = Depends(get_db)):
    """Run all scheduled SMS maintenance tasks.

    Called by Cloud Scheduler every 15 minutes.
    """
    from wex_platform.services.sms_scheduler import SMSScheduler

    scheduler = SMSScheduler(db)
    results = await scheduler.tick()

    logger.info("SMS scheduler tick: %s", results)
    return {"ok": True, "results": results}

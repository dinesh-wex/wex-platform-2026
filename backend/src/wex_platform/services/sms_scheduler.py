"""SMS Scheduler — cron-based background jobs for the buyer SMS pipeline."""
import logging
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SMSScheduler:
    """Runs periodic SMS maintenance tasks."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def tick(self) -> dict:
        """Run all scheduled SMS tasks. Called by cron endpoint.

        Returns summary of actions taken.
        """
        from wex_platform.services.buyer_notification_service import BuyerNotificationService

        notification_service = BuyerNotificationService(self.db)

        results = {}

        # 1. Check for stale conversations → send nudges
        try:
            nudges = await notification_service.check_stale_conversations()
            results["nudges_sent"] = nudges
        except Exception as e:
            logger.error("check_stale_conversations failed: %s", e)
            results["nudges_error"] = str(e)

        # 2. Check dormant transitions
        try:
            dormant = await notification_service.check_dormant_transitions()
            results["dormant_transitions"] = dormant
        except Exception as e:
            logger.error("check_dormant_transitions failed: %s", e)
            results["dormant_error"] = str(e)

        # 3. Check inactivity abandonment
        try:
            abandoned = await notification_service.check_inactivity_abandonment()
            results["abandonments"] = abandoned
        except Exception as e:
            logger.error("check_inactivity_abandonment failed: %s", e)
            results["abandonment_error"] = str(e)

        # 4. Check escalation SLA
        try:
            sla_nudges = await notification_service.check_escalation_sla()
            results["sla_nudges"] = sla_nudges
        except Exception as e:
            logger.error("check_escalation_sla failed: %s", e)
            results["sla_error"] = str(e)

        await self.db.commit()

        return results

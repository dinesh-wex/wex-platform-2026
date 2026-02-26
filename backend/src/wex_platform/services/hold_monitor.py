"""Background jobs for hold expiry warnings and auto-expiry."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.enums import (
    EngagementActor,
    EngagementEventType,
    EngagementStatus,
)
from wex_platform.domain.models import Engagement, EngagementEvent, PropertyListing
import uuid

logger = logging.getLogger(__name__)

# States where hold is active (pre-decision)
HOLD_ACTIVE_STATUSES = {
    EngagementStatus.ADDRESS_REVEALED.value,
    EngagementStatus.TOUR_REQUESTED.value,
    EngagementStatus.TOUR_CONFIRMED.value,
    EngagementStatus.TOUR_RESCHEDULED.value,
    EngagementStatus.TOUR_COMPLETED.value,
    EngagementStatus.GUARANTEE_SIGNED.value,
}


async def check_hold_expiry_warnings(db: AsyncSession):
    """Find engagements with holds expiring within 24hrs or 4hrs and log warnings."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(Engagement).where(
            Engagement.hold_expires_at.isnot(None),
            Engagement.status.in_(list(HOLD_ACTIVE_STATUSES)),
        )
    )
    engagements = result.scalars().all()

    for eng in engagements:
        hold_expires = eng.hold_expires_at
        if hasattr(hold_expires, 'tzinfo') and hold_expires.tzinfo is None:
            hold_expires = hold_expires.replace(tzinfo=timezone.utc)

        remaining = hold_expires - now
        if remaining.total_seconds() <= 0:
            continue  # Already expired — handled by expire_holds

        hours_remaining = remaining.total_seconds() / 3600

        # Check if warning already sent by looking for existing events
        events_result = await db.execute(
            select(EngagementEvent).where(
                EngagementEvent.engagement_id == eng.id,
                EngagementEvent.event_type.in_([
                    EngagementEventType.HOLD_WARNING_24H.value,
                    EngagementEventType.HOLD_WARNING_4H.value,
                ]),
            )
        )
        existing_warnings = {e.event_type for e in events_result.scalars().all()}

        if hours_remaining <= 4 and EngagementEventType.HOLD_WARNING_4H.value not in existing_warnings:
            event = EngagementEvent(
                id=str(uuid.uuid4()),
                engagement_id=eng.id,
                event_type=EngagementEventType.HOLD_WARNING_4H.value,
                actor=EngagementActor.SYSTEM.value,
                actor_id="system",
                from_status=eng.status,
                to_status=eng.status,
                data={"hours_remaining": round(hours_remaining, 1)},
            )
            db.add(event)
            logger.info("Hold warning (4h): engagement=%s, expires=%s", eng.id, hold_expires)

        elif hours_remaining <= 24 and EngagementEventType.HOLD_WARNING_24H.value not in existing_warnings:
            event = EngagementEvent(
                id=str(uuid.uuid4()),
                engagement_id=eng.id,
                event_type=EngagementEventType.HOLD_WARNING_24H.value,
                actor=EngagementActor.SYSTEM.value,
                actor_id="system",
                from_status=eng.status,
                to_status=eng.status,
                data={"hours_remaining": round(hours_remaining, 1)},
            )
            db.add(event)
            logger.info("Hold warning (24h): engagement=%s, expires=%s", eng.id, hold_expires)

    await db.commit()


async def expire_holds(db: AsyncSession):
    """Find and expire holds that have passed their deadline."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(Engagement).where(
            Engagement.hold_expires_at.isnot(None),
            Engagement.hold_expires_at < now,
            Engagement.status.in_(list(HOLD_ACTIVE_STATUSES)),
        )
    )
    engagements = result.scalars().all()

    for eng in engagements:
        # Release sqft back to property listing
        if eng.sqft:
            pl_result = await db.execute(
                select(PropertyListing).where(PropertyListing.property_id == eng.warehouse_id)
            )
            pl = pl_result.scalar_one_or_none()
            if pl:
                pl.available_sqft = (pl.available_sqft or 0) + eng.sqft

        # Transition to expired
        old_status = eng.status
        eng.status = EngagementStatus.EXPIRED.value
        eng.updated_at = now

        event = EngagementEvent(
            id=str(uuid.uuid4()),
            engagement_id=eng.id,
            event_type=EngagementEventType.HOLD_EXPIRED.value,
            actor=EngagementActor.SYSTEM.value,
            actor_id="system",
            from_status=old_status,
            to_status=EngagementStatus.EXPIRED.value,
            data={"hold_expires_at": eng.hold_expires_at.isoformat() if eng.hold_expires_at else None},
        )
        db.add(event)
        logger.info("Hold expired: engagement=%s, was_status=%s", eng.id, old_status)

    await db.commit()
    return len(engagements)

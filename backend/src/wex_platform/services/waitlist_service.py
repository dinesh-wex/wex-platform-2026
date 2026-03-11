"""Buyer Waitlist Service — manages waitlist entries and periodic matching."""
import logging
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.sms_models import BuyerWaitlist

logger = logging.getLogger(__name__)

DEFAULT_EXPIRY_DAYS = 90


class WaitlistService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add_to_waitlist(
        self,
        phone: str,
        buyer_id: str,
        criteria: dict,
    ) -> BuyerWaitlist:
        """Add a buyer to the waitlist for a city with no current matches."""
        location = criteria.get("location", "")
        city = location.split(",")[0].strip() if location else ""
        state = None
        if "," in location:
            state = location.split(",")[1].strip()

        sqft = criteria.get("sqft")
        entry = BuyerWaitlist(
            id=str(uuid.uuid4()),
            buyer_id=buyer_id,
            phone=phone,
            city=city,
            state=state,
            min_sqft=sqft,
            max_sqft=int(sqft * 1.5) if sqft else None,
            use_type=criteria.get("use_type"),
            criteria_snapshot=criteria,
            status="active",
            expires_at=datetime.now(timezone.utc) + timedelta(days=DEFAULT_EXPIRY_DAYS),
        )
        self.db.add(entry)
        await self.db.flush()
        logger.info("Added buyer %s to waitlist for %s", phone, city)
        return entry

    async def check_waitlist_matches(self) -> int:
        """Check active waitlist entries against current inventory. Returns count matched."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(BuyerWaitlist).where(
                and_(
                    BuyerWaitlist.status == "active",
                    BuyerWaitlist.expires_at > now,
                )
            )
        )
        entries = result.scalars().all()
        matched_count = 0

        for entry in entries:
            try:
                from wex_platform.services.buyer_conversation_service import BuyerConversationService
                from wex_platform.services.clearing_engine import ClearingEngine

                conv_service = BuyerConversationService(self.db)
                buyer_need = await conv_service.create_buyer_need_from_criteria(
                    criteria=entry.criteria_snapshot,
                    phone=entry.phone,
                )
                if not buyer_need:
                    continue

                engine = ClearingEngine()
                clearing_result = await engine.run_clearing(
                    buyer_need_id=buyer_need.id, db=self.db
                )
                tier1 = clearing_result.get("tier1_matches", []) if isinstance(clearing_result, dict) else []

                if tier1:
                    entry.status = "matched"
                    entry.matched_property_id = tier1[0].get("warehouse_id")
                    entry.notified_at = now

                    # Send SMS notification
                    from wex_platform.services.sms_service import SMSService
                    sms = SMSService()
                    city = entry.city
                    count = len(tier1)
                    await sms.send_buyer_sms(
                        entry.phone,
                        f"Hey, good news! {count} new space{'s' if count != 1 else ''} "
                        f"just opened up in {city}. Text me back to see the options.",
                    )
                    matched_count += 1
                    logger.info("Waitlist match: %s -> %d matches in %s", entry.phone, count, city)

            except Exception:
                logger.exception("Waitlist check failed for entry %s", entry.id)

        # Expire old entries
        expired_result = await self.db.execute(
            select(BuyerWaitlist).where(
                and_(
                    BuyerWaitlist.status == "active",
                    BuyerWaitlist.expires_at <= now,
                )
            )
        )
        for expired in expired_result.scalars().all():
            expired.status = "expired"

        await self.db.flush()
        return matched_count

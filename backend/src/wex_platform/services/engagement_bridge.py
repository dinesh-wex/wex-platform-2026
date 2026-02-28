"""Engagement Bridge — connects SMS buyer conversations to the Engagement system."""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class EngagementBridge:
    """Creates and manages Engagements from SMS conversations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def initiate_booking(
        self,
        property_id: str,
        buyer_phone: str,
        buyer_name: str | None = None,
        buyer_email: str | None = None,
        buyer_need_id: str | None = None,
    ) -> dict:
        """Create an Engagement from SMS commitment.

        Steps:
        1. Find or create User record (email dedup check!)
        2. Link to Buyer record
        3. Create Engagement with source_channel='sms'
        4. Create EngagementEvent audit record

        Returns dict with engagement_id, user_id, is_new_user.
        """
        from wex_platform.domain.models import (
            User, Buyer, Engagement, EngagementEvent, Property, PropertyContact,
        )

        # Find the property to get warehouse_id (same UUID)
        prop = await self.db.get(Property, property_id)
        if not prop:
            logger.error("Property %s not found for booking", property_id)
            return {"error": "Property not found"}

        warehouse_id = property_id  # Property.id = Warehouse.id by design

        # Find a supplier for this property via PropertyContact
        supplier_id = await self._resolve_supplier_id(property_id)

        # Email dedup: check if User already exists with this email
        is_new_user = True
        user = None

        if buyer_email:
            result = await self.db.execute(
                select(User).where(User.email == buyer_email)
            )
            user = result.scalar_one_or_none()
            if user:
                is_new_user = False
                logger.info("Found existing user %s for email %s", user.id, buyer_email)

        # Create User if needed
        if not user:
            from passlib.hash import bcrypt
            user = User(
                id=str(uuid.uuid4()),
                email=buyer_email or f"sms_{buyer_phone.replace('+', '').replace('-', '')}@sms.warehouseexchange.com",
                password_hash=bcrypt.hash(str(uuid.uuid4())),  # Random password, they'll use SMS
                name=buyer_name or "SMS Buyer",
                phone=buyer_phone,
                role="buyer",
                is_active=True,
                email_verified=False,
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(user)
            await self.db.flush()
            logger.info("Created SMS user %s for phone %s", user.id, buyer_phone)

        # Link Buyer record to User
        buyer_result = await self.db.execute(
            select(Buyer).where(Buyer.phone == buyer_phone)
        )
        buyer = buyer_result.scalar_one_or_none()
        if buyer and not buyer.email:
            buyer.email = buyer_email
            buyer.name = buyer_name

        buyer_id = buyer.id if buyer else None

        # Create Engagement
        # Note: buyer_need_id and supplier_id are NOT NULL in the model.
        # For SMS-originated engagements we use the state's buyer_need_id
        # and resolve supplier from PropertyContact.
        engagement = Engagement(
            id=str(uuid.uuid4()),
            warehouse_id=warehouse_id,
            buyer_need_id=buyer_need_id,  # nullable for SMS-originated engagements
            buyer_id=buyer_id,
            supplier_id=supplier_id,  # nullable for SMS-originated engagements
            status="account_created",
            tier="tier_1",
            source_channel="sms",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            account_created_at=datetime.now(timezone.utc),
        )
        self.db.add(engagement)
        await self.db.flush()

        # Create audit event
        event = EngagementEvent(
            id=str(uuid.uuid4()),
            engagement_id=engagement.id,
            event_type="account_created",
            actor="system",
            data={"source": "sms", "phone": buyer_phone},
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        await self.db.flush()

        logger.info(
            "Created engagement %s for property %s via SMS (user=%s)",
            engagement.id, property_id, user.id,
        )

        return {
            "engagement_id": engagement.id,
            "user_id": user.id,
            "is_new_user": is_new_user,
        }

    async def _resolve_supplier_id(self, property_id: str) -> str | None:
        """Resolve the supplier user ID from PropertyContact or Warehouse."""
        from wex_platform.domain.models import PropertyContact, User

        # Try PropertyContact first
        result = await self.db.execute(
            select(PropertyContact).where(
                PropertyContact.property_id == property_id,
                PropertyContact.is_primary == True,
            )
        )
        contact = result.scalar_one_or_none()
        if contact and contact.email:
            user_result = await self.db.execute(
                select(User).where(User.email == contact.email)
            )
            user = user_result.scalar_one_or_none()
            if user:
                return user.id

        # Fallback: check Warehouse.owner_email
        from wex_platform.domain.models import Warehouse
        wh = await self.db.get(Warehouse, property_id)
        if wh and wh.owner_email:
            user_result = await self.db.execute(
                select(User).where(User.email == wh.owner_email)
            )
            user = user_result.scalar_one_or_none()
            if user:
                return user.id

        return None

    async def request_tour(
        self,
        engagement_id: str,
        requested_date: str | None = None,
        requested_time: str | None = None,
        notes: str | None = None,
    ) -> dict:
        """Advance engagement to TOUR_REQUESTED."""
        from wex_platform.domain.models import Engagement, EngagementEvent

        engagement = await self.db.get(Engagement, engagement_id)
        if not engagement:
            return {"error": "Engagement not found"}

        engagement.status = "tour_requested"
        engagement.updated_at = datetime.now(timezone.utc)
        engagement.tour_requested_at = datetime.now(timezone.utc)
        if notes:
            engagement.tour_notes = notes

        event = EngagementEvent(
            id=str(uuid.uuid4()),
            engagement_id=engagement_id,
            event_type="tour_requested",
            actor="system",
            data={
                "requested_date": requested_date,
                "requested_time": requested_time,
                "notes": notes,
                "source": "sms",
            },
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        await self.db.flush()

        return {"ok": True, "status": "tour_requested"}

    async def confirm_tour(
        self,
        engagement_id: str,
        confirmed_date: str | None = None,
        confirmed_time: str | None = None,
    ) -> dict:
        """Advance engagement to TOUR_CONFIRMED."""
        from wex_platform.domain.models import Engagement, EngagementEvent

        engagement = await self.db.get(Engagement, engagement_id)
        if not engagement:
            return {"error": "Engagement not found"}

        engagement.status = "tour_confirmed"
        engagement.updated_at = datetime.now(timezone.utc)
        engagement.tour_confirmed_at = datetime.now(timezone.utc)

        event = EngagementEvent(
            id=str(uuid.uuid4()),
            engagement_id=engagement_id,
            event_type="tour_confirmed",
            actor="system",
            data={
                "confirmed_date": confirmed_date,
                "confirmed_time": confirmed_time,
                "source": "sms",
            },
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        await self.db.flush()

        return {"ok": True, "status": "tour_confirmed"}

    async def handle_guarantee_signed(
        self,
        engagement_id: str,
        signer_name: str | None = None,
    ) -> dict:
        """Handle guarantee signing — advance engagement."""
        from wex_platform.domain.models import Engagement, EngagementEvent

        engagement = await self.db.get(Engagement, engagement_id)
        if not engagement:
            return {"error": "Engagement not found"}

        engagement.status = "guarantee_signed"
        engagement.updated_at = datetime.now(timezone.utc)
        engagement.guarantee_signed_at = datetime.now(timezone.utc)

        event = EngagementEvent(
            id=str(uuid.uuid4()),
            engagement_id=engagement_id,
            event_type="guarantee_signed",
            actor="system",
            data={"signer": signer_name, "source": "sms"},
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(event)
        await self.db.flush()

        return {"ok": True, "status": "guarantee_signed"}

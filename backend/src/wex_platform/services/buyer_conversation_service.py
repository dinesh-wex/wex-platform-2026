"""Buyer conversation management service for SMS intake.

Manages multi-turn SMS conversations with buyers, persisting messages
and creating BuyerNeed records from extracted criteria.
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.models import Buyer, BuyerConversation, BuyerNeed

logger = logging.getLogger(__name__)

# Duration mapping: shorthand -> months
DURATION_MAP = {
    "1_3": 3,
    "3_6": 6,
    "6_12": 12,
    "12_24": 24,
    "24_plus": 36,
}

# Timing mapping: shorthand -> approximate date offset description
TIMING_MAP = {
    "immediately": "now",
    "30_days": "within 30 days",
    "1_3_months": "1-3 months",
    "flexible": "flexible",
}

# Feature key -> requirements JSON key
FEATURE_MAP = {
    "office": "has_office_space",
    "dock_doors": "dock_doors",
    "climate": "climate_controlled",
    "power": "high_power",
    "24_7": "available_24_7",
    "sprinkler": "has_sprinkler",
    "parking": "parking",
    "forklift": "forklift_available",
}


class BuyerConversationService:
    """Manages buyer SMS conversations and need creation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Conversation management
    # ------------------------------------------------------------------

    async def get_or_create_buyer(self, phone: str) -> Buyer:
        """Find an existing buyer by phone or create a new one.

        Args:
            phone: E.164 formatted phone number.

        Returns:
            The Buyer record.
        """
        result = await self.db.execute(
            select(Buyer).where(Buyer.phone == phone)
        )
        buyer = result.scalar_one_or_none()

        if buyer:
            logger.debug("Found existing buyer %s for phone %s", buyer.id, phone)
            return buyer

        buyer = Buyer(
            id=str(uuid.uuid4()),
            phone=phone,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(buyer)
        await self.db.flush()
        logger.info("Created new buyer %s for phone %s", buyer.id, phone)
        return buyer

    async def get_or_create_conversation(
        self, phone: str
    ) -> tuple[BuyerConversation, Buyer]:
        """Find the buyer's active conversation or create a new one.

        An active conversation is one with status='active'. If no active
        conversation exists, a new one is created.

        Args:
            phone: E.164 formatted phone number.

        Returns:
            Tuple of (BuyerConversation, Buyer).
        """
        buyer = await self.get_or_create_buyer(phone)

        result = await self.db.execute(
            select(BuyerConversation)
            .where(
                BuyerConversation.buyer_id == buyer.id,
                BuyerConversation.status == "active",
            )
            .order_by(BuyerConversation.updated_at.desc())
            .limit(1)
        )
        conversation = result.scalar_one_or_none()

        if conversation:
            logger.debug(
                "Found active conversation %s for buyer %s",
                conversation.id, buyer.id,
            )
            return conversation, buyer

        conversation = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            messages=[],
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(conversation)
        await self.db.flush()
        logger.info(
            "Created new conversation %s for buyer %s",
            conversation.id, buyer.id,
        )
        return conversation, buyer

    async def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:
        """Append a message to the conversation history.

        Args:
            conversation_id: The conversation UUID.
            role: 'buyer' or 'assistant'.
            content: The message text.
        """
        result = await self.db.execute(
            select(BuyerConversation).where(
                BuyerConversation.id == conversation_id
            )
        )
        conversation = result.scalar_one_or_none()
        if not conversation:
            logger.warning("Conversation %s not found for add_message", conversation_id)
            return

        messages = list(conversation.messages or [])
        messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        conversation.messages = messages
        conversation.updated_at = datetime.now(timezone.utc)
        await self.db.flush()

        logger.debug(
            "Added %s message to conversation %s (total: %d)",
            role, conversation_id, len(messages),
        )

    # ------------------------------------------------------------------
    # Need creation
    # ------------------------------------------------------------------

    async def create_buyer_need_from_criteria(
        self,
        criteria: dict,
        phone: str,
        conversation_id: str | None = None,
    ) -> BuyerNeed | None:
        """Create a BuyerNeed from extracted SMS criteria.

        Only creates if we have at least location or sqft (minimum viable need).

        Args:
            criteria: Extracted criteria dict from CriteriaExtractor.
            phone: Buyer's phone number.
            conversation_id: Optional conversation to link.

        Returns:
            The created BuyerNeed, or None if criteria is insufficient.
        """
        location = criteria.get("location")
        sqft = criteria.get("sqft")

        # Need at least location or sqft to be actionable
        if not location and not sqft:
            logger.debug("Insufficient criteria for BuyerNeed — skipping creation")
            return None

        buyer = await self.get_or_create_buyer(phone)

        # Parse location into city/state
        city, state = self._parse_location(location)

        # Parse duration
        duration_key = criteria.get("duration")
        duration_months = DURATION_MAP.get(duration_key) if duration_key else None

        # Build requirements JSON from features
        requirements = {}
        features = criteria.get("features") or []
        for feature in features:
            req_key = FEATURE_MAP.get(feature)
            if req_key:
                requirements[req_key] = True

        # Add goods_type and use_type to requirements
        if criteria.get("goods_type"):
            requirements["goods_type"] = criteria["goods_type"]
        if criteria.get("timing"):
            requirements["timing"] = criteria["timing"]

        buyer_need = BuyerNeed(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            city=city,
            state=state,
            min_sqft=int(sqft) if sqft else None,
            max_sqft=int(sqft * 1.5) if sqft else None,  # 50% headroom
            use_type=criteria.get("use_type"),
            duration_months=duration_months,
            requirements=requirements,
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(buyer_need)
        await self.db.flush()

        # Link conversation to this need
        if conversation_id:
            result = await self.db.execute(
                select(BuyerConversation).where(
                    BuyerConversation.id == conversation_id
                )
            )
            conversation = result.scalar_one_or_none()
            if conversation:
                conversation.buyer_need_id = buyer_need.id
                await self.db.flush()

        logger.info(
            "Created BuyerNeed %s — city=%s, state=%s, sqft=%s, use=%s",
            buyer_need.id, city, state, sqft, criteria.get("use_type"),
        )
        return buyer_need

    # ------------------------------------------------------------------
    # SMS state management
    # ------------------------------------------------------------------

    async def get_or_create_sms_state(
        self,
        buyer_id: str,
        conversation_id: str,
        phone: str,
    ) -> "SMSConversationState":
        """Find the SMS conversation state or create a new one.

        Args:
            buyer_id: The buyer's UUID.
            conversation_id: The conversation UUID.
            phone: E.164 phone number.

        Returns:
            The SMSConversationState record.
        """
        from wex_platform.domain.sms_models import SMSConversationState

        result = await self.db.execute(
            select(SMSConversationState).where(
                SMSConversationState.conversation_id == conversation_id,
            )
        )
        state = result.scalar_one_or_none()

        if state:
            return state

        state = SMSConversationState(
            id=str(uuid.uuid4()),
            buyer_id=buyer_id,
            conversation_id=conversation_id,
            phone=phone,
        )
        self.db.add(state)
        await self.db.flush()
        logger.info("Created SMSConversationState %s for conversation %s", state.id, conversation_id)
        return state

    # ------------------------------------------------------------------
    # Cross-channel linking
    # ------------------------------------------------------------------

    async def link_web_account(self, phone: str, user_id: str, email: str | None = None) -> bool:
        """Link a web-created User account to an existing SMS buyer.

        Called when a user signs up via web and we detect they already have
        an SMS conversation (matching by phone number).

        Updates:
        - Buyer.email if provided
        - SMSConversationState.buyer_email if found

        Returns True if a link was made, False if no SMS buyer found.
        """
        from wex_platform.domain.sms_models import SMSConversationState

        # Find buyer by phone
        result = await self.db.execute(
            select(Buyer).where(Buyer.phone == phone)
        )
        buyer = result.scalar_one_or_none()
        if not buyer:
            return False

        # Update buyer email
        if email and not buyer.email:
            buyer.email = email

        # Update SMS conversation state
        result = await self.db.execute(
            select(SMSConversationState).where(SMSConversationState.phone == phone)
        )
        states = result.scalars().all()
        for state in states:
            if email and not state.buyer_email:
                state.buyer_email = email

        await self.db.flush()
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_location(location: str | None) -> tuple[str | None, str | None]:
        """Parse a location string into (city, state).

        Handles formats like:
        - "Detroit, MI"
        - "Detroit Michigan"
        - "MI"
        - "Los Angeles"

        Returns:
            Tuple of (city, state_abbreviation).
        """
        if not location:
            return None, None

        # State abbreviation mapping
        STATE_ABBRS = {
            "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
            "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
            "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
            "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
            "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
            "DC",
        }

        STATE_NAMES = {
            "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
            "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
            "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
            "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
            "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
            "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
            "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
            "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
            "new mexico": "NM", "new york": "NY", "north carolina": "NC",
            "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
            "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
            "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
            "vermont": "VT", "virginia": "VA", "washington": "WA",
            "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
            "district of columbia": "DC",
        }

        location = location.strip()
        city = None
        state = None

        # Try "City, ST" format
        if "," in location:
            parts = [p.strip() for p in location.split(",", 1)]
            city = parts[0] if parts[0] else None
            if len(parts) > 1:
                potential_state = parts[1].strip().upper()
                if potential_state in STATE_ABBRS:
                    state = potential_state
                else:
                    # Try full state name
                    abbr = STATE_NAMES.get(parts[1].strip().lower())
                    if abbr:
                        state = abbr
            return city, state

        # Try to find a state abbreviation at the end
        words = location.split()
        if words:
            last_word = words[-1].upper()
            if last_word in STATE_ABBRS:
                state = last_word
                city = " ".join(words[:-1]) if len(words) > 1 else None
                return city, state

        # Try full state name match
        location_lower = location.lower()
        for name, abbr in STATE_NAMES.items():
            if location_lower == name:
                return None, abbr
            if location_lower.endswith(name):
                city_part = location_lower[: -len(name)].strip()
                return city_part.title() if city_part else None, abbr

        # Default: treat the whole thing as a city
        return location, None

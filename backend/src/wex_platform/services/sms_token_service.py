"""SMS Token Service — creates and validates guarantee signing tokens."""
import logging
import secrets
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.sms_models import SmsSignupToken

logger = logging.getLogger(__name__)

# Token expiry: 48 hours
TOKEN_EXPIRY_HOURS = 48


class SmsTokenService:
    """Manages SmsSignupToken records for guarantee signing flows."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_guarantee_token(
        self,
        conversation_state_id: str,
        buyer_phone: str,
        engagement_id: str | None = None,
        prefilled_name: str | None = None,
        prefilled_email: str | None = None,
    ) -> SmsSignupToken:
        """Create a new guarantee signing token.

        Returns the SmsSignupToken record with a unique 64-char token.
        """
        token = SmsSignupToken(
            id=str(uuid.uuid4()),
            conversation_state_id=conversation_state_id,
            token=secrets.token_urlsafe(48),  # ~64 chars
            action="guarantee",
            buyer_phone=buyer_phone,
            engagement_id=engagement_id,
            prefilled_name=prefilled_name,
            prefilled_email=prefilled_email,
            expires_at=datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS),
        )
        self.db.add(token)
        await self.db.flush()

        logger.info("Created guarantee token %s... for phone %s", token.token[:8], buyer_phone)
        return token

    async def validate_token(self, token_str: str) -> SmsSignupToken | None:
        """Validate a token — returns the record if valid, None if invalid/expired/used."""
        result = await self.db.execute(
            select(SmsSignupToken).where(SmsSignupToken.token == token_str)
        )
        token = result.scalar_one_or_none()

        if not token:
            return None

        if token.used:
            logger.warning("Token %s... already used", token_str[:8])
            return None

        if token.expires_at:
            now = datetime.utcnow()
            expires = token.expires_at
            # Strip tzinfo for SQLite compatibility (stores naive datetimes)
            if expires.tzinfo is not None:
                expires = expires.replace(tzinfo=None)
            if expires < now:
                logger.warning("Token %s... expired", token_str[:8])
                return None

        return token

    async def redeem_token(self, token_str: str) -> SmsSignupToken | None:
        """Redeem a token — marks it as used. Returns None if invalid."""
        token = await self.validate_token(token_str)
        if not token:
            return None

        token.used = True
        token.used_at = datetime.utcnow()
        await self.db.flush()

        logger.info("Redeemed token %s...", token_str[:8])
        return token

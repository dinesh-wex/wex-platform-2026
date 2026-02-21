"""SMS service via Aircall API for supplier outreach.

Ported from the Aircall Test (Node.js) pattern. Uses Aircall's native
SMS API with Basic Auth for outbound messages.

Endpoints used:
- POST /v1/numbers/{number_id}/messages/native/send — send outbound SMS
"""

import base64
import logging

import httpx

from wex_platform.app.config import get_settings

logger = logging.getLogger(__name__)


class SMSService:
    """Send and manage SMS messages via Aircall API."""

    def __init__(self):
        self.settings = get_settings()
        self.base_url = "https://api.aircall.io/v1"

    def _auth_header(self) -> dict:
        """Build Basic Auth header for Aircall API."""
        credentials = f"{self.settings.aircall_api_id}:{self.settings.aircall_api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
        }

    @property
    def _configured(self) -> bool:
        """Check if Aircall credentials are configured."""
        return bool(
            self.settings.aircall_api_id
            and self.settings.aircall_api_token
            and self.settings.aircall_number_id
        )

    async def send_sms(self, to_number: str, message: str) -> dict:
        """Send outbound SMS via Aircall's native send endpoint.

        Args:
            to_number: E.164 formatted phone number (e.g., +1234567890).
            message: Message body text.

        Returns:
            Aircall API response dict.

        Raises:
            RuntimeError: If Aircall is not configured.
            httpx.HTTPStatusError: On API failure.
        """
        if not self._configured:
            logger.warning("Aircall SMS not configured — message not sent to %s", to_number)
            return {"ok": False, "error": "aircall_not_configured", "message": message}

        url = f"{self.base_url}/numbers/{self.settings.aircall_number_id}/messages/native/send"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    headers=self._auth_header(),
                    json={"to": to_number, "body": message},
                )
                response.raise_for_status()
                result = response.json()
                logger.info("SMS sent to %s via Aircall", to_number)
                return result
        except httpx.HTTPStatusError as e:
            logger.error(
                "Aircall SMS send failed (%d): %s",
                e.response.status_code,
                e.response.text,
            )
            raise
        except Exception as e:
            logger.error("Aircall SMS send error: %s", e)
            raise

    async def send_dla_outreach(
        self,
        warehouse_id: str,
        token: str,
        supplier_name: str,
        supplier_phone: str,
        sqft: int,
        neighborhood: str,
        use_type: str,
        rate: float,
        monthly: float,
        timeframe: str,
    ) -> dict:
        """Send DLA outreach SMS with deal details and tokenized link.

        This is the initial outreach message sent to an off-network supplier
        when a buyer match is identified for their property.

        Args:
            warehouse_id: The warehouse being outreached.
            token: The DLA token for the tokenized URL.
            supplier_name: First name of the property owner.
            supplier_phone: E.164 phone number.
            sqft: Buyer's requested square footage.
            neighborhood: Area/neighborhood description.
            use_type: Buyer's intended use (storage, distribution, etc.).
            rate: Suggested rate per sqft.
            monthly: Estimated monthly revenue.
            timeframe: When the buyer needs the space.

        Returns:
            Aircall API response dict.
        """
        frontend_url = self.settings.frontend_url
        message = (
            f"Hi {supplier_name} — Warehouse Exchange has a buyer looking for "
            f"{sqft:,} sqft in {neighborhood} for {use_type}, starting {timeframe}. "
            f"Your property looks like a strong match. Estimated rate: ${rate:.2f}/sqft — "
            f"that's ~${monthly:,.0f}/month.\n\n"
            f"We already have your property info on file, so getting started takes less than 5 minutes.\n"
            f"→ {frontend_url}/dla/{token}\n\n"
            f"Reply STOP to opt out."
        )

        logger.info(
            "Sending DLA outreach to %s for warehouse %s (token: %s...)",
            supplier_phone,
            warehouse_id,
            token[:8],
        )

        return await self.send_sms(supplier_phone, message)

    async def send_outcome_notification(
        self, supplier_phone: str, supplier_name: str, won: bool
    ) -> dict:
        """Send deal outcome notification to a supplier.

        Args:
            supplier_phone: E.164 phone number.
            supplier_name: First name of the property owner.
            won: Whether the supplier won the deal.

        Returns:
            Aircall API response dict.
        """
        if won:
            message = (
                f"Hi {supplier_name} — great news! The buyer selected your space. "
                f"We'll be in touch with next steps shortly."
            )
        else:
            message = (
                f"Hi {supplier_name} — the buyer selected another space this time. "
                f"Your property stays on file — we'll reach out when the next match comes up."
            )

        return await self.send_sms(supplier_phone, message)

    async def send_buyer_notification(
        self, buyer_phone: str, city: str, sqft: int, rate: float
    ) -> dict:
        """Send new match notification to a buyer.

        Args:
            buyer_phone: E.164 phone number.
            city: City/neighborhood of the matched space.
            sqft: Square footage of the matched space.
            rate: Rate per sqft.

        Returns:
            Aircall API response dict.
        """
        message = (
            f"Good news — a new space just confirmed availability for your "
            f"requirements. {city}, {sqft:,} sqft, ${rate:.2f}/sqft. "
            f"Log in to view your updated matches."
        )

        return await self.send_sms(buyer_phone, message)

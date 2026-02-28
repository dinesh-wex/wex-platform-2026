"""SMS service via Aircall API for supplier and buyer outreach.

Uses Aircall's Public API with Basic Auth for outbound messages.
Number must be configured for Public API mode via /messages/configuration.

Endpoints used:
- POST /v1/numbers/{number_id}/messages/send — send outbound SMS (Public API mode)
"""

import asyncio
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

    def _basic_auth(self) -> str:
        """Build Basic Auth base64 string."""
        credentials = f"{self.settings.aircall_api_id}:{self.settings.aircall_api_token}"
        return base64.b64encode(credentials.encode()).decode()

    @property
    def _configured(self) -> bool:
        """Check if Aircall credentials are configured (supplier number)."""
        return bool(
            self.settings.aircall_api_id
            and self.settings.aircall_api_token
            and self.settings.aircall_number_id
        )

    @property
    def _buyer_configured(self) -> bool:
        """Check if buyer Aircall number is configured."""
        return bool(
            self.settings.aircall_api_id
            and self.settings.aircall_api_token
            and self.settings.aircall_buyer_number_id
        )

    async def send_sms(self, to_number: str, message: str) -> dict:
        """Send outbound SMS via Aircall Public API (supplier number)."""
        if not self._configured:
            logger.warning("Aircall SMS not configured — message not sent to %s", to_number)
            return {"ok": False, "error": "aircall_not_configured", "message": message}

        url = f"{self.base_url}/numbers/{self.settings.aircall_number_id}/messages/send"
        return await self._send_httpx(url, to_number, message)

    async def send_buyer_sms(self, to_number: str, message: str) -> dict:
        """Send outbound SMS via Aircall Public API (buyer number)."""
        if not self._buyer_configured:
            logger.warning("Aircall buyer SMS not configured — message not sent to %s", to_number)
            return {"ok": False, "error": "aircall_buyer_not_configured", "message": message}

        url = f"{self.base_url}/numbers/{self.settings.aircall_buyer_number_id}/messages/send"
        return await self._send_httpx(url, to_number, message)

    async def _send_httpx(self, url: str, to_number: str, message: str) -> dict:
        """Send SMS using httpx async client.

        Uses verify=False to bypass Windows Schannel certificate revocation
        check failures with Aircall's CloudFront certificates.
        """
        auth = self._basic_auth()
        payload = {"to": to_number, "body": message}

        logger.info("Aircall send: url=%s to=%s msg_len=%d body=%s", url, to_number, len(message), message[:200])

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
                    resp = await client.post(
                        url,
                        json=payload,
                        headers={
                            "Authorization": f"Basic {auth}",
                            "Accept": "application/json",
                        },
                    )

                if 200 <= resp.status_code < 300:
                    try:
                        data = resp.json()
                    except Exception:
                        data = {"raw": resp.text}
                    logger.info("SMS sent to %s via Aircall (status=%d)", to_number, resp.status_code)
                    return data

                # Log full response headers on non-2xx for debugging
                logger.warning(
                    "Aircall %d response headers: %s",
                    resp.status_code, dict(resp.headers),
                )

                # Retry on 403 (CloudFront intermittent block)
                if resp.status_code == 403 and attempt < 2:
                    wait = 5 * (attempt + 1)
                    logger.warning(
                        "Aircall 403 — retrying in %ds (attempt %d/3): %s",
                        wait, attempt + 1, resp.text[:300],
                    )
                    await asyncio.sleep(wait)
                    continue

                logger.error("Aircall SMS failed (%d): %s", resp.status_code, resp.text[:300])
                return {"ok": False, "error": f"http_{resp.status_code}", "status": resp.status_code, "message": message}

            except httpx.TimeoutException:
                logger.error("Aircall httpx timed out for %s", to_number)
                return {"ok": False, "error": "timeout", "message": message}
            except Exception as e:
                logger.error("Aircall httpx error: %s", e)
                return {"ok": False, "error": str(e), "message": message}

        return {"ok": False, "error": "max_retries", "message": message}

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
        """Send DLA outreach SMS with deal details and tokenized link."""
        frontend_url = self.settings.frontend_url
        message = (
            f"Hi {supplier_name}, Warehouse Exchange has a buyer looking for "
            f"{sqft:,} sqft in {neighborhood} for {use_type}, starting {timeframe}. "
            f"Your property looks like a strong match. Estimated rate: ${rate:.2f}/sqft. "
            f"That's ~${monthly:,.0f}/month.\n\n"
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
        """Send deal outcome notification to a supplier."""
        if won:
            message = (
                f"Hi {supplier_name}, great news! The buyer selected your space. "
                f"We'll be in touch with next steps shortly."
            )
        else:
            message = (
                f"Hi {supplier_name}, the buyer selected another space this time. "
                f"Your property stays on file and we'll reach out when the next match comes up."
            )

        return await self.send_sms(supplier_phone, message)

    @staticmethod
    def check_opt_out(state) -> bool:
        """Check if the conversation state is opted out."""
        return bool(state and state.opted_out)

    @staticmethod
    def check_quiet_hours(timezone_str: str | None = None) -> bool:
        """Check if current time is within quiet hours (9pm-9am) for proactive messages."""
        from datetime import datetime
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo

        tz_name = timezone_str or "America/New_York"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            tz = ZoneInfo("America/New_York")

        local_hour = datetime.now(tz).hour
        return local_hour >= 21 or local_hour < 9

    async def send_buyer_notification(
        self, buyer_phone: str, city: str, sqft: int, rate: float
    ) -> dict:
        """Send new match notification to a buyer."""
        message = (
            f"Good news, a new space just confirmed availability for your "
            f"requirements. {city}, {sqft:,} sqft, ${rate:.2f}/sqft. "
            f"Log in to view your updated matches."
        )

        return await self.send_sms(buyer_phone, message)

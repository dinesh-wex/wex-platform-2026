"""Tier 1 + Tier 2: Buyer SMS webhook tests.

Tier 1 (unit, no DB): TCPA keyword regex, OPT_IN_LINE constant
Tier 2 (integration): Full webhook flow with real DB session
"""

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.app.routes.buyer_sms import (
    HELP_KEYWORD,
    START_KEYWORD,
    STOP_KEYWORDS,
)
from wex_platform.domain.sms_models import SMSConversationState


# ===========================================================================
# Tier 1: Unit tests — no database required
# ===========================================================================


class TestStopKeywords:
    """STOP_KEYWORDS regex matches exact TCPA stop words only."""

    @pytest.mark.parametrize("word", [
        "stop", "STOP", "  stop  ", "unsubscribe", "cancel", "quit", "end",
        "  UNSUBSCRIBE  ", "  CANCEL  ", "QUIT", "END",
    ])
    def test_matches_stop_words(self, word):
        assert STOP_KEYWORDS.match(word) is not None

    @pytest.mark.parametrize("word", [
        "stop it", "stopped", "I want to stop", "stopper",
        "unsubscribed", "cancellation", "quitting", "ending",
        "please stop", "end now",
    ])
    def test_rejects_non_exact_stop(self, word):
        assert STOP_KEYWORDS.match(word) is None


class TestHelpKeyword:
    """HELP_KEYWORD regex matches exact 'help' only."""

    @pytest.mark.parametrize("word", [
        "help", "HELP", "  help  ", "  HELP  ",
    ])
    def test_matches_help(self, word):
        assert HELP_KEYWORD.match(word) is not None

    @pytest.mark.parametrize("word", [
        "help me", "I need help", "helpful", "helping",
    ])
    def test_rejects_non_exact_help(self, word):
        assert HELP_KEYWORD.match(word) is None


class TestStartKeyword:
    """START_KEYWORD regex matches exact 'start' only."""

    @pytest.mark.parametrize("word", [
        "start", "START", "  start  ", "  START  ",
    ])
    def test_matches_start(self, word):
        assert START_KEYWORD.match(word) is not None

    @pytest.mark.parametrize("word", [
        "start over", "starting", "restart", "started",
    ])
    def test_rejects_non_exact_start(self, word):
        assert START_KEYWORD.match(word) is None




# ===========================================================================
# Tier 2: Integration tests — real DB, mocked orchestrator + SMS
# ===========================================================================


@dataclass
class FakeOrchestratorResult:
    """Minimal OrchestratorResult for test mocking."""
    response: str = "Thanks! What city are you looking in?"
    intent: str = "new_search"
    action: str | None = None
    criteria: dict | None = None
    phase: str = "INTAKE"
    error: str | None = None


def _build_app_client(db_session: AsyncSession):
    """Build an HTTPX AsyncClient wired to a test FastAPI app.

    Uses a fresh FastAPI app with only the buyer_sms router to avoid
    loading all app routes and their heavy dependencies.
    """
    from fastapi import FastAPI
    from wex_platform.app.routes.buyer_sms import router as buyer_sms_router
    from wex_platform.infra.database import get_db

    test_app = FastAPI()
    test_app.include_router(buyer_sms_router)

    async def _override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = _override_get_db

    return AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
    )


class TestWebhookCreatesConversationState:
    """POST webhook creates an SMSConversationState row."""

    async def test_webhook_creates_conversation_state(
        self, db_session, aircall_webhook_payload
    ):
        payload = aircall_webhook_payload("+15551234567", "I need 5000 sqft in Detroit")

        with (
            patch("wex_platform.app.routes.buyer_sms.SMSService") as MockSMS,
            patch(
                "wex_platform.services.buyer_sms_orchestrator.BuyerSMSOrchestrator.process_message",
                new_callable=AsyncMock,
                return_value=FakeOrchestratorResult(),
            ),
            patch("wex_platform.app.routes.buyer_sms.get_settings") as mock_settings,
        ):
            mock_settings.return_value.aircall_webhook_token = ""
            MockSMS.return_value.send_buyer_sms = AsyncMock(return_value={"ok": True})

            async with _build_app_client(db_session) as client:
                resp = await client.post("/api/sms/buyer/webhook", json=payload)

            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True

            # Verify SMSConversationState was created
            result = await db_session.execute(
                select(SMSConversationState).where(
                    SMSConversationState.phone == "+15551234567"
                )
            )
            state = result.scalar_one_or_none()
            assert state is not None
            assert state.phase == "INTAKE"
            assert state.turn == 1


class TestStopOptsOut:
    """STOP message opts out the buyer."""

    async def test_stop_opts_out(self, db_session, aircall_webhook_payload):
        payload = aircall_webhook_payload("+15552345678", "STOP")

        with (
            patch("wex_platform.app.routes.buyer_sms.SMSService") as MockSMS,
            patch("wex_platform.app.routes.buyer_sms.get_settings") as mock_settings,
        ):
            mock_settings.return_value.aircall_webhook_token = ""
            MockSMS.return_value.send_buyer_sms = AsyncMock(return_value={"ok": True})

            async with _build_app_client(db_session) as client:
                resp = await client.post("/api/sms/buyer/webhook", json=payload)

            assert resp.status_code == 200
            data = resp.json()
            assert data["action"] == "opted_out"

            # Verify state is opted out
            result = await db_session.execute(
                select(SMSConversationState).where(
                    SMSConversationState.phone == "+15552345678"
                )
            )
            state = result.scalar_one_or_none()
            assert state is not None
            assert state.opted_out is True
            assert state.phase == "ABANDONED"


class TestOptedOutBuyerIgnored:
    """After STOP, subsequent messages return opted_out action."""

    async def test_opted_out_buyer_ignored(self, db_session, aircall_webhook_payload):
        phone = "+15553456789"

        with (
            patch("wex_platform.app.routes.buyer_sms.SMSService") as MockSMS,
            patch(
                "wex_platform.services.buyer_sms_orchestrator.BuyerSMSOrchestrator.process_message",
                new_callable=AsyncMock,
                return_value=FakeOrchestratorResult(),
            ),
            patch("wex_platform.app.routes.buyer_sms.get_settings") as mock_settings,
        ):
            mock_settings.return_value.aircall_webhook_token = ""
            MockSMS.return_value.send_buyer_sms = AsyncMock(return_value={"ok": True})

            async with _build_app_client(db_session) as client:
                # First: STOP
                stop_payload = aircall_webhook_payload(phone, "stop")
                resp1 = await client.post("/api/sms/buyer/webhook", json=stop_payload)
                assert resp1.json()["action"] == "opted_out"

                # Second: regular message should be ignored
                msg_payload = aircall_webhook_payload(phone, "I need a warehouse")
                resp2 = await client.post("/api/sms/buyer/webhook", json=msg_payload)
                assert resp2.json()["action"] == "opted_out"


class TestStartResubscribes:
    """STOP then START re-subscribes the buyer."""

    async def test_start_resubscribes(self, db_session, aircall_webhook_payload):
        phone = "+15554567890"

        with (
            patch("wex_platform.app.routes.buyer_sms.SMSService") as MockSMS,
            patch("wex_platform.app.routes.buyer_sms.get_settings") as mock_settings,
        ):
            mock_settings.return_value.aircall_webhook_token = ""
            MockSMS.return_value.send_buyer_sms = AsyncMock(return_value={"ok": True})

            async with _build_app_client(db_session) as client:
                # STOP first
                stop_payload = aircall_webhook_payload(phone, "STOP")
                await client.post("/api/sms/buyer/webhook", json=stop_payload)

                # Then START
                start_payload = aircall_webhook_payload(phone, "START")
                resp = await client.post("/api/sms/buyer/webhook", json=start_payload)

            assert resp.json()["action"] == "resubscribed"

            # Verify state is no longer opted out
            result = await db_session.execute(
                select(SMSConversationState).where(
                    SMSConversationState.phone == phone
                )
            )
            state = result.scalar_one_or_none()
            assert state is not None
            assert state.opted_out is False
            assert state.phase == "INTAKE"


class TestTurnIncrements:
    """Two messages increment turn correctly."""

    async def test_turn_increments(self, db_session, aircall_webhook_payload):
        phone = "+15555678901"

        with (
            patch("wex_platform.app.routes.buyer_sms.SMSService") as MockSMS,
            patch(
                "wex_platform.app.routes.buyer_sms._process_buyer_message",
                new_callable=AsyncMock,
            ),
            patch("wex_platform.app.routes.buyer_sms.get_settings") as mock_settings,
        ):
            mock_settings.return_value.aircall_webhook_token = ""
            MockSMS.return_value.send_buyer_sms = AsyncMock(return_value={"ok": True})

            async with _build_app_client(db_session) as client:
                # Message 1
                p1 = aircall_webhook_payload(phone, "I need a warehouse in Detroit")
                resp1 = await client.post("/api/sms/buyer/webhook", json=p1)
                assert resp1.json()["turn"] == 1

                # Message 2
                p2 = aircall_webhook_payload(phone, "About 5000 sqft")
                resp2 = await client.post("/api/sms/buyer/webhook", json=p2)
                assert resp2.json()["turn"] == 2


class TestSupplierPhoneRedirect:
    """Message from a PropertyContact phone returns supplier_redirect."""

    async def test_supplier_phone_redirect(
        self, db_session, aircall_webhook_payload, make_property
    ):
        supplier_phone = "+15556789012"
        await make_property(contact_phone=supplier_phone)

        payload = aircall_webhook_payload(supplier_phone, "Hello there")

        with (
            patch("wex_platform.app.routes.buyer_sms.SMSService") as MockSMS,
            patch("wex_platform.app.routes.buyer_sms.get_settings") as mock_settings,
        ):
            mock_settings.return_value.aircall_webhook_token = ""
            MockSMS.return_value.send_buyer_sms = AsyncMock(return_value={"ok": True})

            async with _build_app_client(db_session) as client:
                resp = await client.post("/api/sms/buyer/webhook", json=payload)

        assert resp.status_code == 200
        assert resp.json()["action"] == "supplier_redirect"


class TestSelfLoopPrevention:
    """Same from/to number is silently ignored."""

    async def test_self_loop_prevention(self, db_session, aircall_webhook_payload):
        same_number = "+15557890123"
        payload = aircall_webhook_payload(
            same_number, "test", to_number=same_number,
        )

        with (
            patch("wex_platform.app.routes.buyer_sms.get_settings") as mock_settings,
        ):
            mock_settings.return_value.aircall_webhook_token = ""

            async with _build_app_client(db_session) as client:
                resp = await client.post("/api/sms/buyer/webhook", json=payload)

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


class TestInvalidTokenRejected:
    """Wrong webhook token returns 401."""

    async def test_invalid_token_rejected(self, db_session, aircall_webhook_payload):
        payload = aircall_webhook_payload("+15558901234", "hello", token="wrong-token")

        with (
            patch("wex_platform.app.routes.buyer_sms.get_settings") as mock_settings,
        ):
            # Set a real token so validation is enforced
            mock_settings.return_value.aircall_webhook_token = "correct-token"

            async with _build_app_client(db_session) as client:
                resp = await client.post("/api/sms/buyer/webhook", json=payload)

        assert resp.status_code == 401

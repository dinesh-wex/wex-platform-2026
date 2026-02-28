"""Tests for SMS scheduler endpoint — Phase 5 QC."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from httpx import AsyncClient, ASGITransport

from wex_platform.app.main import app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scheduler_tick():
    """POST /api/internal/scheduler/sms-tick should return 200 with results dict."""
    with patch("wex_platform.services.buyer_notification_service.BuyerNotificationService") as MockNotif:
        mock_notif = MagicMock()
        mock_notif.check_stale_conversations = AsyncMock(return_value=2)
        mock_notif.check_dormant_transitions = AsyncMock(return_value=1)
        mock_notif.check_inactivity_abandonment = AsyncMock(return_value=0)
        mock_notif.check_escalation_sla = AsyncMock(return_value=0)
        MockNotif.return_value = mock_notif

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/scheduler/sms-tick",
                headers={"X-Internal-Token": "wex2026"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "results" in body


@pytest.mark.asyncio
async def test_scheduler_handles_errors():
    """If one task raises, other tasks should still run (error isolated)."""
    with patch("wex_platform.services.buyer_notification_service.BuyerNotificationService") as MockNotif:
        mock_notif = MagicMock()
        mock_notif.check_stale_conversations = AsyncMock(side_effect=RuntimeError("boom"))
        mock_notif.check_dormant_transitions = AsyncMock(return_value=1)
        mock_notif.check_inactivity_abandonment = AsyncMock(return_value=0)
        mock_notif.check_escalation_sla = AsyncMock(return_value=0)
        MockNotif.return_value = mock_notif

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/scheduler/sms-tick",
                headers={"X-Internal-Token": "wex2026"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    results = body["results"]
    # The errored task should have an error key
    assert "nudges_error" in results
    # The other tasks should still have succeeded
    assert "dormant_transitions" in results
    assert results["dormant_transitions"] == 1

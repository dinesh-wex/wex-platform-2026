"""Vapi voice agent webhook endpoint.

Handles three Vapi event types:
- assistant-request: Return assistant config for inbound calls
- tool-calls: Execute tool functions (search, lookup, booking)
- end-of-call-report: Send follow-up SMS with links
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.app.config import get_settings
from wex_platform.domain.voice_models import VoiceCallState
from wex_platform.domain.models import Buyer
from wex_platform.infra.database import async_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])


@router.post("/api/voice/webhook")
async def vapi_webhook(request: Request):
    """Single Vapi webhook endpoint dispatching by event type.

    Uses a manual async_session() context manager (same pattern as
    buyer_sms.py background tasks) so we control commit timing and
    avoid FastAPI Depends lifecycle issues with signature validation.
    """
    # Read raw body for signature validation
    body_bytes = await request.body()

    # Validate webhook signature (before parsing body)
    _validate_vapi_signature(request, body_bytes)

    body = json.loads(body_bytes)
    message = body.get("message", {})
    event_type = message.get("type")

    logger.info("Vapi webhook: event_type=%s", event_type)

    async with async_session() as db:
        if event_type == "assistant-request":
            return await _handle_assistant_request(message, db)
        elif event_type == "tool-calls":
            return await _handle_tool_calls(message, db)
        elif event_type == "end-of-call-report":
            return await _handle_end_of_call(message, db)
        else:
            # Acknowledge unknown events (status-update, speech-update, etc.)
            return JSONResponse({"ok": True})


# ======================================================================
# assistant-request
# ======================================================================


async def _handle_assistant_request(message: dict, db: AsyncSession) -> JSONResponse:
    """Return assistant config for an inbound call.

    1. Extract caller phone and Vapi call ID
    2. Look up existing Buyer to personalize greeting
    3. Create VoiceCallState to track this call
    4. Build and return assistant config via build_assistant_config()
    """
    call = message.get("call", {})
    caller_phone = call.get("customer", {}).get("number", "")
    vapi_call_id = call.get("id", str(uuid.uuid4()))

    # Look up existing buyer by phone to personalize
    buyer_name = None
    if caller_phone:
        result = await db.execute(
            select(Buyer).where(Buyer.phone == caller_phone)
        )
        buyer = result.scalar_one_or_none()
        if buyer and buyer.name:
            buyer_name = buyer.name

    # Create VoiceCallState for this call
    call_state = VoiceCallState(
        id=str(uuid.uuid4()),
        vapi_call_id=vapi_call_id,
        caller_phone=caller_phone,
        verified_phone=caller_phone,  # Default to caller ID; updated if they give alternate
        call_started_at=datetime.now(timezone.utc),
    )
    db.add(call_state)
    await db.commit()

    # Build and return assistant config
    try:
        from wex_platform.services.vapi_assistant_config import build_assistant_config
        config = build_assistant_config(caller_phone=caller_phone, buyer_name=buyer_name)
    except ImportError:
        logger.warning("vapi_assistant_config not available yet, returning minimal config")
        config = _fallback_assistant_config(caller_phone, buyer_name)

    return JSONResponse(config)


# ======================================================================
# tool-calls
# ======================================================================


async def _handle_tool_calls(message: dict, db: AsyncSession) -> JSONResponse:
    """Dispatch tool calls to VoiceToolHandlers.

    Vapi sends tool calls in two possible payload shapes:
    - Nested:  toolCallList[].function.name / toolCallList[].function.arguments
    - Flat:    toolCallList[].name / toolCallList[].arguments
    We handle both.
    """
    call = message.get("call", {})
    vapi_call_id = call.get("id", "")

    # Load call state
    result = await db.execute(
        select(VoiceCallState).where(VoiceCallState.vapi_call_id == vapi_call_id)
    )
    call_state = result.scalar_one_or_none()

    if not call_state:
        logger.error("No VoiceCallState for call_id=%s", vapi_call_id)
        return JSONResponse({
            "results": [
                {"toolCallId": tc.get("id", ""), "result": "System error, please try again."}
                for tc in message.get("toolCallList", [])
            ]
        })

    from wex_platform.services.voice_tool_handlers import VoiceToolHandlers
    handlers = VoiceToolHandlers(db=db, call_state=call_state)

    results = []
    for tool_call in message.get("toolCallList", []):
        # Handle both nested (function.name) and flat (name) payload shapes
        func_block = tool_call.get("function", {})
        tool_name = func_block.get("name") or tool_call.get("name", "")
        raw_args = func_block.get("arguments") or tool_call.get("arguments", {})
        tool_call_id = tool_call.get("id", "")

        # Vapi may send arguments as a JSON string
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except (json.JSONDecodeError, TypeError):
                args = {}
        else:
            args = raw_args or {}

        logger.info("Tool call: %s(%s) call_id=%s", tool_name, args, vapi_call_id)

        try:
            if tool_name == "search_properties":
                result_text = await handlers.search_properties(
                    location=args.get("location", ""),
                    sqft=int(args.get("sqft", 0)),
                    use_type=args.get("use_type"),
                    timing=args.get("timing"),
                    duration=args.get("duration"),
                    features=args.get("features"),
                )
            elif tool_name == "lookup_property_details":
                result_text = await handlers.lookup_property_details(
                    option_number=int(args.get("option_number", 0)),
                    topics=args.get("topics"),
                )
            elif tool_name == "send_booking_link":
                result_text = await handlers.send_booking_link(
                    option_number=int(args.get("option_number", 0)),
                    buyer_name=args.get("buyer_name", ""),
                    buyer_email=args.get("buyer_email"),
                )
            else:
                logger.warning("Unknown tool: %s", tool_name)
                result_text = f"Unknown tool: {tool_name}"
        except Exception as e:
            logger.error("Tool call %s failed: %s", tool_name, e, exc_info=True)
            result_text = "I ran into a technical issue. Let me note that and follow up with you."

        results.append({
            "toolCallId": tool_call_id,
            "result": result_text,
        })

    await db.commit()

    return JSONResponse({"results": results})


# ======================================================================
# end-of-call-report
# ======================================================================


async def _handle_end_of_call(message: dict, db: AsyncSession) -> JSONResponse:
    """Process end-of-call report: update metadata and send follow-up SMS.

    Sends one of two SMS types depending on call outcome:
    - Booking link: if send_booking_link was invoked during the call
    - Search options link: if search was done but no booking
    """
    call = message.get("call", {})
    vapi_call_id = call.get("id", "")

    # Load call state
    result = await db.execute(
        select(VoiceCallState).where(VoiceCallState.vapi_call_id == vapi_call_id)
    )
    call_state = result.scalar_one_or_none()

    if not call_state:
        logger.warning("No VoiceCallState for end-of-call: call_id=%s", vapi_call_id)
        return JSONResponse({"ok": True})

    # Update call metadata
    call_state.call_ended_at = datetime.now(timezone.utc)
    call_state.call_duration_seconds = message.get("durationSeconds")
    call_state.call_summary = message.get("summary")
    call_state.call_transcript = message.get("transcript")
    call_state.recording_url = message.get("recordingUrl") or call.get("recordingUrl")

    # Determine SMS recipient and greeting
    settings = get_settings()
    sms_phone = call_state.verified_phone or call_state.caller_phone
    first_name = call_state.buyer_name.split()[0] if call_state.buyer_name else ""
    name_prefix = f"Hey {first_name}, " if first_name else "Hey, "

    if call_state.guarantee_link_token and not call_state.sms_sent:
        # Booking link SMS
        link = f"{settings.frontend_url}/sms/guarantee/{call_state.guarantee_link_token}"
        sms_text = f"{name_prefix}here's the link to complete your warehouse booking: {link}"
        await _send_follow_up_sms(sms_phone, sms_text, call_state)

    elif call_state.search_session_token and not call_state.sms_sent:
        # Search options link SMS
        link = f"{settings.frontend_url}/buyer/options?session={call_state.search_session_token}"
        sms_text = f"{name_prefix}here are the warehouse options we discussed: {link}"
        await _send_follow_up_sms(sms_phone, sms_text, call_state)

    await db.commit()
    return JSONResponse({"ok": True})


# ======================================================================
# Helpers
# ======================================================================


async def _send_follow_up_sms(
    phone: str, text: str, call_state: VoiceCallState
) -> None:
    """Send SMS and mark sms_sent on call state."""
    from wex_platform.services.sms_service import SMSService

    sms = SMSService()
    try:
        send_result = await sms.send_buyer_sms(phone, text)
        if send_result.get("ok"):
            call_state.sms_sent = True
            logger.info("Sent follow-up SMS to %s", phone)
        else:
            logger.error("Failed to send follow-up SMS: %s", send_result)
    except Exception as e:
        logger.error("Exception sending follow-up SMS to %s: %s", phone, e, exc_info=True)


def _validate_vapi_signature(request: Request, body_bytes: bytes) -> None:
    """Validate Vapi webhook signature (HMAC-SHA256).

    Skipped when vapi_server_secret is not configured (local dev).
    """
    settings = get_settings()

    if not settings.vapi_server_secret:
        return  # Skip validation in dev

    signature = request.headers.get("x-vapi-signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing Vapi signature")

    expected = hmac.new(
        settings.vapi_server_secret.encode(),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="Invalid Vapi signature")


def _fallback_assistant_config(caller_phone: str, buyer_name: str | None) -> dict:
    """Minimal assistant config when vapi_assistant_config module is unavailable.

    This allows the webhook to respond even if the config module is still
    being built. The caller will get a basic greeting.
    """
    greeting = (
        f"Hi {buyer_name}, welcome to Warehouse Exchange."
        if buyer_name
        else "Hi, welcome to Warehouse Exchange."
    )
    return {
        "assistant": {
            "firstMessage": greeting + " How can I help you today?",
            "model": {
                "provider": "google",
                "model": "gemini-3-flash-preview",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful warehouse leasing assistant for "
                            "Warehouse Exchange (WEx). Help callers find warehouse space."
                        ),
                    }
                ],
            },
        }
    }

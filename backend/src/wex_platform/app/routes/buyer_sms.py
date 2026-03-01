"""Buyer SMS webhook — handles inbound SMS from prospective warehouse renters.

Dedicated Aircall webhook for buyer-side SMS. Handles:
- TCPA compliance (STOP/HELP/START keywords)
- Opt-out enforcement
- First-message opt-in line
- Supplier-phone detection (silent forward)
- Routes through BuyerSMSOrchestrator for processing

Returns 200 immediately after fast checks (state creation, opt-out, turn increment).
The slow LLM pipeline runs in a background task to avoid webhook timeouts.
"""

import asyncio
import logging
import re
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.app.config import get_settings
from wex_platform.domain.models import PropertyContact
from wex_platform.infra.database import get_db, async_session
from wex_platform.services.sms_service import SMSService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sms/buyer", tags=["sms-buyer"])

# TCPA keyword patterns
STOP_KEYWORDS = re.compile(
    r"^\s*(stop|unsubscribe|cancel|quit|end)\s*$", re.IGNORECASE
)
HELP_KEYWORD = re.compile(r"^\s*help\s*$", re.IGNORECASE)
START_KEYWORD = re.compile(r"^\s*start\s*$", re.IGNORECASE)

# Dedup cache — prevents Aircall retry storms (retries within ~30s window)
_recent_messages: dict[str, float] = {}
DEDUP_WINDOW_SECONDS = 30

# Hold references to background tasks so they don't get garbage collected
_background_tasks: set = set()


@router.post("/webhook")
async def buyer_sms_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle inbound SMS on the buyer Aircall number.

    Fast checks (validation, TCPA, opt-out, state creation) run inline.
    The slow LLM pipeline runs in a background task so Aircall gets a
    fast 200 response and doesn't retry/cancel.
    """
    settings = get_settings()
    body = await request.json()

    # ── 1. Validate webhook token ─────────────────────────────────────
    token_from_header = request.headers.get("x-aircall-token", "")
    token_from_body = body.get("token", "")
    provided_token = token_from_header or token_from_body

    if settings.aircall_webhook_token and (
        not provided_token or provided_token != settings.aircall_webhook_token
    ):
        logger.warning("Invalid Aircall webhook token on buyer endpoint")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token",
        )

    # ── 2. Filter event type ──────────────────────────────────────────
    event_type = body.get("event")
    if event_type and event_type != "message.received":
        return {"ok": True}

    # ── 3. Extract message data ───────────────────────────────────────
    message_payload = (
        body.get("data", {}).get("message")
        or body.get("data")
        or body.get("message")
        or body
    )

    text = (message_payload.get("body") or "").strip()
    from_number = (
        message_payload.get("external_number")
        or message_payload.get("raw_digits")
        or (message_payload.get("number") or {}).get("digits")
    )
    direction = message_payload.get("direction") or body.get("data", {}).get("direction")

    # ── 4. Self-loop prevention ───────────────────────────────────────
    if direction and direction != "inbound":
        return {"ok": True}

    to_number = (message_payload.get("number") or {}).get("e164_digits") or (
        message_payload.get("number") or {}
    ).get("digits")

    if (
        to_number
        and from_number
        and to_number.replace(" ", "") == from_number.replace(" ", "")
    ):
        logger.debug("Ignoring self-sent message to prevent loop")
        return {"ok": True}

    if not text or not from_number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing message body or sender",
        )

    # ── Dedup check (Aircall retries) ──────────────────────────────────
    dedup_key = f"{from_number}:{text[:50]}"
    now = time.monotonic()

    # Clean old entries
    expired = [k for k, t in _recent_messages.items() if now - t > DEDUP_WINDOW_SECONDS]
    for k in expired:
        del _recent_messages[k]

    if dedup_key in _recent_messages:
        logger.debug("Dedup: ignoring duplicate webhook from %s", from_number)
        return {"ok": True, "action": "dedup_skip"}

    _recent_messages[dedup_key] = now

    logger.info("Buyer SMS inbound from %s: %s", from_number, text[:100])

    sms_service = SMSService()

    # ── 5. Pre-pipeline keyword handling (TCPA) ───────────────────────
    if STOP_KEYWORDS.match(text):
        return await _handle_stop(db, from_number, sms_service)

    if HELP_KEYWORD.match(text):
        return await _handle_help(from_number, sms_service)

    if START_KEYWORD.match(text):
        return await _handle_start(db, from_number, sms_service)

    # ── 6. Supplier-phone detection ───────────────────────────────────
    supplier_contact = await db.execute(
        select(PropertyContact)
        .where(PropertyContact.phone == from_number, PropertyContact.is_primary == True)
        .limit(1)
    )
    if supplier_contact.scalar_one_or_none():
        logger.info("Supplier phone %s texted buyer number — sending generic reply", from_number)
        await sms_service.send_buyer_sms(
            from_number,
            "Thanks for your message. For supplier inquiries, "
            "please contact us at support@warehouseexchange.com."
        )
        return {"ok": True, "action": "supplier_redirect"}

    # ── 7. Load/create SMSConversationState (fast, inline) ────────────
    from wex_platform.services.buyer_conversation_service import BuyerConversationService

    conv_service = BuyerConversationService(db)
    conversation, buyer = await conv_service.get_or_create_conversation(from_number)
    state = await conv_service.get_or_create_sms_state(
        buyer_id=buyer.id,
        conversation_id=conversation.id,
        phone=from_number,
    )

    # Check opt-out status (buyer may have opted out previously)
    if state.opted_out:
        logger.info("Buyer %s is opted out — ignoring message", from_number)
        return {"ok": True, "action": "opted_out"}

    # ── 8. Increment turn, update timestamps (fast, inline) ───────────
    state.turn = (state.turn or 0) + 1
    state.last_buyer_message_at = datetime.now(timezone.utc)

    # Record inbound message
    await conv_service.add_message(conversation.id, "buyer", text)

    # Commit state + inbound message so background task can read them
    await db.commit()

    current_turn = state.turn

    # ── 9. Fire background task for the slow LLM pipeline ─────────────
    # Return 200 to Aircall immediately so Cloudflare doesn't cancel
    task = asyncio.create_task(
        _process_buyer_message(
            from_number=from_number,
            text=text,
            conversation_id=conversation.id,
            buyer_id=buyer.id,
            state_id=state.id,
        )
    )
    # Prevent GC from collecting the task before it finishes
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return {
        "ok": True,
        "action": "buyer_intake",
        "turn": current_turn,
        "phase": state.phase,
    }


async def _process_buyer_message(
    from_number: str,
    text: str,
    conversation_id: str,
    buyer_id: str,
    state_id: str,
) -> None:
    """Background task: run the orchestrator pipeline and send response.

    Uses its own DB session since the request session is closed after 200.
    Reloads state/conversation by ID from the already-committed data.
    """
    logger.info("Background task started for %s: %s", from_number, text[:50])
    try:
        async with async_session() as db:
            from wex_platform.services.buyer_conversation_service import BuyerConversationService
            from wex_platform.domain.models import BuyerConversation, Buyer, BuyerNeed
            from wex_platform.domain.sms_models import SMSConversationState

            # Reload objects in this session
            conversation = await db.get(BuyerConversation, conversation_id)
            buyer = await db.get(Buyer, buyer_id)
            state = await db.get(SMSConversationState, state_id)

            if not conversation or not buyer or not state:
                logger.error("Background task: missing DB objects for %s", from_number)
                return

            # Build conversation history
            conversation_history = conversation.messages or []

            # Extract existing criteria from linked BuyerNeed
            existing_criteria = None
            if conversation.buyer_need_id:
                existing_need = await db.get(BuyerNeed, conversation.buyer_need_id)
                if existing_need:
                    existing_criteria = {
                        "location": f"{existing_need.city or ''}, {existing_need.state or ''}".strip(", "),
                        "sqft": existing_need.min_sqft,
                        "use_type": existing_need.use_type,
                    }
                    if existing_need.requirements:
                        existing_criteria.update({
                            k: v for k, v in existing_need.requirements.items()
                            if k in ("goods_type", "timing", "duration", "requirements")
                        })

            # Also pull criteria from state's snapshot (persisted each turn,
            # covers the gap before a BuyerNeed is created by search)
            if state.criteria_snapshot:
                if not existing_criteria:
                    existing_criteria = {}
                for key in ("location", "sqft", "use_type", "timing", "duration",
                            "requirements", "goods_type", "features"):
                    val = state.criteria_snapshot.get(key)
                    if val and not existing_criteria.get(key):
                        existing_criteria[key] = val

            # Run orchestrator
            from wex_platform.services.buyer_sms_orchestrator import BuyerSMSOrchestrator

            orchestrator = BuyerSMSOrchestrator(db)
            orchestrator_result = await orchestrator.process_message(
                phone=from_number,
                message=text,
                state=state,
                conversation=conversation,
                buyer=buyer,
                conversation_history=conversation_history,
                existing_criteria=existing_criteria,
            )

            if orchestrator_result.error:
                logger.warning("Buyer SMS orchestrator error for %s: %s", from_number, orchestrator_result.error)
                await db.commit()
                return

            response_text = orchestrator_result.response

            # Record outbound message
            conv_service = BuyerConversationService(db)
            await conv_service.add_message(conversation.id, "assistant", response_text)

            # Send response via Aircall
            if response_text:
                try:
                    sms_service = SMSService()
                    await sms_service.send_buyer_sms(from_number, response_text)
                    state.last_system_message_at = datetime.now(timezone.utc)
                except Exception as e:
                    logger.error("Failed to send buyer SMS to %s: %s", from_number, e)

            await db.commit()

            logger.info(
                "Buyer SMS processed for %s: intent=%s phase=%s turn=%d",
                from_number, orchestrator_result.intent, state.phase, state.turn,
            )

    except Exception as e:
        logger.error("Background buyer SMS processing failed for %s: %s", from_number, e, exc_info=True)


# ═══════════════════════════════════════════════════════════════════════════
# TCPA Keyword Handlers
# ═══════════════════════════════════════════════════════════════════════════

async def _handle_stop(db: AsyncSession, phone: str, sms_service: SMSService) -> dict:
    """Handle STOP/UNSUBSCRIBE/CANCEL/QUIT/END — opt out immediately."""
    from wex_platform.services.buyer_conversation_service import BuyerConversationService

    conv_service = BuyerConversationService(db)
    conversation, buyer = await conv_service.get_or_create_conversation(phone)
    state = await conv_service.get_or_create_sms_state(
        buyer_id=buyer.id,
        conversation_id=conversation.id,
        phone=phone,
    )

    state.opted_out = True
    state.opted_out_at = datetime.now(timezone.utc)
    state.phase = "ABANDONED"
    await db.commit()

    # TCPA requires confirmation of opt-out (this is the ONLY message sent after STOP)
    try:
        await sms_service.send_buyer_sms(
            phone,
            "You've been unsubscribed from WEx messages. Text START to re-subscribe."
        )
    except Exception as e:
        logger.error("Failed to send STOP confirmation to %s: %s", phone, e)

    logger.info("Buyer %s opted out (STOP)", phone)
    return {"ok": True, "action": "opted_out"}


async def _handle_help(phone: str, sms_service: SMSService) -> dict:
    """Handle HELP — send support info."""
    try:
        await sms_service.send_buyer_sms(
            phone,
            "WEx Warehouse Exchange - find warehouse space via text. "
            "Tell me a city, size, and use type to search. "
            "Reply STOP to opt out. Questions? support@warehouseexchange.com"
        )
    except Exception as e:
        logger.error("Failed to send HELP response to %s: %s", phone, e)

    return {"ok": True, "action": "help_sent"}


async def _handle_start(db: AsyncSession, phone: str, sms_service: SMSService) -> dict:
    """Handle START — re-subscribe a previously opted-out buyer."""
    from wex_platform.services.buyer_conversation_service import BuyerConversationService

    conv_service = BuyerConversationService(db)
    conversation, buyer = await conv_service.get_or_create_conversation(phone)
    state = await conv_service.get_or_create_sms_state(
        buyer_id=buyer.id,
        conversation_id=conversation.id,
        phone=phone,
    )

    if state.opted_out:
        state.opted_out = False
        state.opted_out_at = None
        state.phase = "INTAKE"
        await db.commit()
        logger.info("Buyer %s re-subscribed (START)", phone)

    try:
        await sms_service.send_buyer_sms(
            phone,
            "Welcome back to Warehouse Exchange! What city, state and how much space do you need?"
        )
    except Exception as e:
        logger.error("Failed to send START response to %s: %s", phone, e)

    return {"ok": True, "action": "resubscribed"}

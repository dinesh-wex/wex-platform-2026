"""SMS webhook routes — handles inbound SMS from Aircall.

Receives webhook payloads from Aircall when suppliers reply to outreach
messages. Parses supplier intent (YES, NO, counter-rate), updates DLA
token status, and optionally auto-responds.

Also handles inbound buyer SMS via the BuyerSMSPipeline — routing is
based on whether the sender has an active DLA token (supplier) or not
(buyer intake flow).
"""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.app.config import get_settings
from wex_platform.domain.models import DLAToken, Warehouse, Property, PropertyContact
from wex_platform.infra.database import get_db
from wex_platform.services.sms_service import SMSService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sms", tags=["sms"])

# Patterns for parsing supplier SMS replies
POSITIVE_PATTERNS = re.compile(
    r"\b(yes|yeah|yep|sure|interested|ok|okay|sounds good|im in|i'm in|let's go|lets go)\b",
    re.IGNORECASE,
)
NEGATIVE_PATTERNS = re.compile(
    r"\b(no|nah|not interested|pass|decline|no thanks|no thank you)\b",
    re.IGNORECASE,
)
STOP_PATTERN = re.compile(r"\bstop\b", re.IGNORECASE)
RATE_PATTERN = re.compile(
    r"\$?(\d+(?:\.\d{1,2})?)\s*(?:/?\s*(?:sqft|sq\s*ft|per\s*sqft))?",
    re.IGNORECASE,
)


@router.post("/webhook")
async def aircall_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Handle inbound SMS from Aircall. Parse supplier replies.

    Expected Aircall webhook payload structure:
    {
        "event": "message.received",
        "data": {
            "message": {
                "body": "...",
                "direction": "inbound",
                "external_number": "+1234567890",
                ...
            }
        }
    }

    Parsing logic:
    - STOP -> opt out, mark as declined
    - YES / positive -> mark token as interested
    - NO / negative -> mark token as declined
    - Dollar amount -> interpret as counter-rate
    """
    settings = get_settings()

    body = await request.json()

    # ── Validate webhook token ───────────────────────────────────────
    token_from_header = request.headers.get("x-aircall-token", "")
    token_from_body = body.get("token", "")
    provided_token = token_from_header or token_from_body

    if settings.aircall_webhook_token and (
        not provided_token or provided_token != settings.aircall_webhook_token
    ):
        logger.warning("Invalid Aircall webhook token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token",
        )

    # ── Filter event type ────────────────────────────────────────────
    event_type = body.get("event")
    if event_type and event_type != "message.received":
        logger.debug("Ignoring Aircall event type: %s", event_type)
        return {"ok": True}

    # ── Extract message data ─────────────────────────────────────────
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

    # ── Self-loop prevention ─────────────────────────────────────────
    if direction and direction != "inbound":
        logger.debug("Ignoring non-inbound message direction: %s", direction)
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
        logger.warning("Missing text or sender in Aircall webhook")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing message body or sender",
        )

    logger.info("Inbound SMS from %s: %s", from_number, text[:100])

    # ── Find the supplier's most recent pending DLA token ────────────
    # Match by phone number on PropertyContact (new schema) or Warehouse (legacy)
    result = await db.execute(
        select(DLAToken)
        .join(PropertyContact, PropertyContact.property_id == DLAToken.warehouse_id)
        .where(
            PropertyContact.phone == from_number,
            PropertyContact.is_primary == True,
            DLAToken.status.in_(["pending", "interested"]),
        )
        .order_by(DLAToken.created_at.desc())
        .limit(1)
    )
    dla_token = result.scalar_one_or_none()

    # Fall back to legacy Warehouse.owner_phone lookup
    if not dla_token:
        result = await db.execute(
            select(DLAToken)
            .join(Warehouse, Warehouse.id == DLAToken.warehouse_id)
            .where(
                Warehouse.owner_phone == from_number,
                DLAToken.status.in_(["pending", "interested"]),
            )
            .order_by(DLAToken.created_at.desc())
            .limit(1)
        )
        dla_token = result.scalar_one_or_none()

    sms_service = SMSService()

    # ── Route: Supplier DLA flow vs Buyer intake flow ─────────────────
    # If the sender has an active DLA token, they're a supplier replying
    # to outreach. Otherwise, treat as buyer SMS intake.

    if dla_token:
        return await _handle_supplier_reply(
            db=db, text=text, from_number=from_number,
            dla_token=dla_token, sms_service=sms_service, settings=settings,
        )

    # No DLA token — route through buyer SMS pipeline
    return await _handle_buyer_message(
        db=db, text=text, from_number=from_number, sms_service=sms_service,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Supplier DLA reply handler (existing logic, extracted for clarity)
# ═══════════════════════════════════════════════════════════════════════════


async def _handle_supplier_reply(
    db: AsyncSession,
    text: str,
    from_number: str,
    dla_token: DLAToken,
    sms_service: SMSService,
    settings,
) -> dict:
    """Handle an inbound SMS from a supplier with an active DLA token."""

    # STOP -> opt out
    if STOP_PATTERN.search(text):
        dla_token.status = "declined"
        dla_token.decline_reason = "STOP reply"
        prop = await db.get(Property, dla_token.warehouse_id)
        if prop:
            prop.relationship_status = "declined"
        warehouse = await db.get(Warehouse, dla_token.warehouse_id)
        if warehouse:
            warehouse.supplier_status = "declined"
        await db.commit()
        logger.info("Supplier %s opted out (STOP)", from_number)
        return {"ok": True, "action": "opted_out"}

    # Check for counter-rate (dollar amount)
    rate_match = RATE_PATTERN.search(text)
    has_rate = rate_match and not NEGATIVE_PATTERNS.search(text)

    if has_rate:
        counter_rate = float(rate_match.group(1))
        dla_token.supplier_rate = counter_rate
        dla_token.status = "rate_decided"
        dla_token.rate_accepted = False
        # Update both new and legacy models
        prop = await db.get(Property, dla_token.warehouse_id)
        warehouse = await db.get(Warehouse, dla_token.warehouse_id)

        await db.commit()

        # Auto-respond with the tokenized link
        frontend_url = settings.frontend_url
        response_msg = (
            f"Got it — ${counter_rate:.2f}/sqft noted. "
            f"Complete the quick review to finalize:\n"
            f"→ {frontend_url}/dla/{dla_token.token}"
        )
        await sms_service.send_sms(from_number, response_msg)

        logger.info("Supplier %s counter-rate: $%.2f", from_number, counter_rate)
        return {"ok": True, "action": "counter_rate", "rate": counter_rate}

    # YES / positive
    if POSITIVE_PATTERNS.search(text):
        dla_token.status = "interested"
        prop = await db.get(Property, dla_token.warehouse_id)
        if prop:
            prop.relationship_status = "interested"
        warehouse = await db.get(Warehouse, dla_token.warehouse_id)
        if warehouse:
            warehouse.supplier_status = "interested"
        await db.commit()

        # Send the tokenized link
        frontend_url = settings.frontend_url
        response_msg = (
            f"Great! Here's your personalized link to review the deal — "
            f"takes less than 5 minutes:\n"
            f"→ {frontend_url}/dla/{dla_token.token}"
        )
        await sms_service.send_sms(from_number, response_msg)

        logger.info("Supplier %s expressed interest", from_number)
        return {"ok": True, "action": "interested"}

    # NO / negative
    if NEGATIVE_PATTERNS.search(text):
        dla_token.status = "declined"
        dla_token.decline_reason = f"SMS reply: {text[:200]}"
        prop = await db.get(Property, dla_token.warehouse_id)
        if prop:
            prop.relationship_status = "declined"
        warehouse = await db.get(Warehouse, dla_token.warehouse_id)
        if warehouse:
            warehouse.supplier_status = "declined"
        await db.commit()

        response_msg = (
            "Understood — no problem. Your property stays on file and "
            "we'll only reach out if there's a strong match in the future."
        )
        await sms_service.send_sms(from_number, response_msg)

        logger.info("Supplier %s declined via SMS", from_number)
        return {"ok": True, "action": "declined"}

    # Unrecognized supplier reply — don't auto-respond to avoid spam
    logger.info(
        "Unrecognized supplier SMS from %s (unclear intent): %s",
        from_number, text[:200],
    )
    return {"ok": True, "action": "unrecognized"}


# ═══════════════════════════════════════════════════════════════════════════
# Buyer SMS intake handler (new)
# ═══════════════════════════════════════════════════════════════════════════


async def _handle_buyer_message(
    db: AsyncSession,
    text: str,
    from_number: str,
    sms_service: SMSService,
) -> dict:
    """Handle an inbound SMS from a buyer (no active DLA token).

    Routes through the BuyerSMSPipeline for AI-powered intake:
    1. Get or create buyer conversation
    2. Run the multi-step pipeline (intent, criteria, response)
    3. If criteria extracted, create BuyerNeed and trigger clearing
    4. Send the generated response back via SMS
    """
    from wex_platform.agents.buyer_sms_agent import BuyerSMSPipeline
    from wex_platform.services.buyer_conversation_service import BuyerConversationService
    from wex_platform.services.clearing_engine import ClearingEngine

    logger.info("Routing inbound SMS from %s to buyer pipeline", from_number)

    conv_service = BuyerConversationService(db)

    # ── Get or create conversation ────────────────────────────────────
    conversation, buyer = await conv_service.get_or_create_conversation(from_number)

    # Build conversation history for the pipeline
    conversation_history = conversation.messages or []

    # Extract existing criteria from the linked BuyerNeed (if any)
    existing_criteria = None
    if conversation.buyer_need_id:
        from wex_platform.domain.models import BuyerNeed
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
                    if k in ("goods_type", "timing")
                })

    # ── Record inbound message ────────────────────────────────────────
    await conv_service.add_message(conversation.id, "buyer", text)

    # ── Run the buyer SMS pipeline ────────────────────────────────────
    pipeline = BuyerSMSPipeline()
    pipeline_result = await pipeline.process_message(
        phone=from_number,
        message=text,
        conversation_history=conversation_history,
        existing_criteria=existing_criteria,
    )

    if pipeline_result.error:
        logger.warning(
            "Buyer SMS pipeline error for %s: %s",
            from_number, pipeline_result.error,
        )
        return {"ok": True, "action": "buyer_error", "error": pipeline_result.error}

    # ── Create/update BuyerNeed if criteria extracted ─────────────────
    buyer_need_id = None
    if (
        pipeline_result.criteria
        and pipeline_result.intent in ("new_search", "refine_search")
    ):
        buyer_need = await conv_service.create_buyer_need_from_criteria(
            criteria=pipeline_result.criteria,
            phone=from_number,
            conversation_id=conversation.id,
        )

        if buyer_need:
            buyer_need_id = buyer_need.id
            logger.info(
                "BuyerNeed %s created from SMS — triggering clearing",
                buyer_need_id,
            )

            # ── Trigger clearing engine ───────────────────────────────
            try:
                clearing_engine = ClearingEngine()
                await clearing_engine.run_clearing(
                    buyer_need_id=buyer_need_id, db=db,
                )
                logger.info("Clearing engine completed for BuyerNeed %s", buyer_need_id)
            except Exception as e:
                logger.error(
                    "Clearing engine failed for BuyerNeed %s: %s",
                    buyer_need_id, e,
                )
                # Don't fail the SMS response — clearing can retry later

    # ── Record outbound message ───────────────────────────────────────
    await conv_service.add_message(conversation.id, "assistant", pipeline_result.response)

    # ── Send SMS reply ────────────────────────────────────────────────
    if pipeline_result.response:
        try:
            await sms_service.send_sms(from_number, pipeline_result.response)
            logger.info("Buyer SMS reply sent to %s", from_number)
        except Exception as e:
            logger.error("Failed to send buyer SMS reply to %s: %s", from_number, e)

    await db.commit()

    return {
        "ok": True,
        "action": "buyer_intake",
        "intent": pipeline_result.intent,
        "buyer_need_id": buyer_need_id,
        "conversation_id": conversation.id,
    }

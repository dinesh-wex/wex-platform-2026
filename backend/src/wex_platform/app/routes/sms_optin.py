"""SMS Opt-in routes — web-to-SMS continuity."""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.infra.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sms/optin", tags=["sms-optin"])


class OptInRequest(BaseModel):
    phone: str
    buyer_need_id: str | None = None
    user_id: str | None = None
    name: str | None = None
    email: str | None = None


@router.post("/")
async def opt_in_sms(
    body: OptInRequest,
    db: AsyncSession = Depends(get_db),
):
    """Opt a web buyer into SMS notifications.

    Creates or finds an SMSConversationState pre-populated with web criteria.
    Sends a contextual first message.
    """
    from wex_platform.services.buyer_conversation_service import BuyerConversationService
    from wex_platform.services.sms_service import SMSService
    from wex_platform.domain.models import BuyerNeed

    conv_service = BuyerConversationService(db)
    conversation, buyer = await conv_service.get_or_create_conversation(body.phone)
    state = await conv_service.get_or_create_sms_state(
        buyer_id=buyer.id,
        conversation_id=conversation.id,
        phone=body.phone,
    )

    # Pre-populate from web data
    if body.name:
        parts = body.name.strip().split(None, 1)
        state.renter_first_name = parts[0]
        state.renter_last_name = parts[1] if len(parts) > 1 else None
        state.name_status = "web"

    if body.email:
        state.buyer_email = body.email

    # Pre-populate criteria from BuyerNeed
    if body.buyer_need_id:
        need = await db.get(BuyerNeed, body.buyer_need_id)
        if need:
            state.buyer_need_id = need.id
            state.criteria_snapshot = {
                "location": f"{need.city or ''}, {need.state or ''}".strip(", "),
                "sqft": need.min_sqft,
                "use_type": need.use_type,
            }
            # Skip INTAKE — they already have criteria
            state.phase = "QUALIFYING"
            state.criteria_readiness = 0.3 if need.city else 0.0
            if need.min_sqft:
                state.criteria_readiness += 0.25
            if need.use_type:
                state.criteria_readiness += 0.25

    # Link web account
    if body.user_id:
        await conv_service.link_web_account(
            phone=body.phone,
            user_id=body.user_id,
            email=body.email,
        )

    await db.commit()

    # Send welcome SMS
    try:
        sms_service = SMSService()
        if state.criteria_snapshot and state.criteria_snapshot.get("location"):
            msg = (
                f"Hey{' ' + state.renter_first_name if state.renter_first_name else ''}! "
                f"I see you're looking for space "
                f"in {state.criteria_snapshot.get('location', 'your area')}. "
                f"I'll text you updates and help you find the right fit."
            )
        else:
            msg = (
                f"Hey{' ' + state.renter_first_name if state.renter_first_name else ''}, "
                f"what city and how much space are you looking for?"
            )
        await sms_service.send_buyer_sms(body.phone, msg)
    except Exception as e:
        logger.error("Failed to send opt-in welcome SMS: %s", e)

    return {
        "ok": True,
        "conversation_id": conversation.id,
        "state_id": state.id,
        "phase": state.phase,
    }

"""SMS Reply Tool — ops endpoint for answering escalated buyer questions."""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.app.config import get_settings
from wex_platform.domain.sms_models import EscalationThread, SMSConversationState
from wex_platform.infra.database import get_db
from wex_platform.services.sms_service import SMSService

logger = logging.getLogger(__name__)


async def verify_internal_token(x_internal_token: str = Header(...)):
    """Verify that the request includes a valid internal auth token."""
    settings = get_settings()
    if x_internal_token != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid internal token")


router = APIRouter(
    prefix="/api/sms/internal",
    tags=["sms-reply-tool"],
    dependencies=[Depends(verify_internal_token)],
)


class ReplyRequest(BaseModel):
    answer: str
    answered_by: str = "ops"


@router.get("/reply/{thread_id}")
async def get_escalation_thread(
    thread_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get escalation thread details for the reply form."""
    result = await db.execute(
        select(EscalationThread).where(EscalationThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    return {
        "id": thread.id,
        "property_id": thread.property_id,
        "question": thread.question_text,
        "field_key": thread.field_key,
        "status": thread.status,
        "created_at": thread.created_at.isoformat() if thread.created_at else None,
        "sla_deadline_at": thread.sla_deadline_at.isoformat() if thread.sla_deadline_at else None,
    }


@router.post("/reply/{thread_id}")
async def submit_reply(
    thread_id: str,
    body: ReplyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit an answer to an escalated question."""
    # Load thread
    result = await db.execute(
        select(EscalationThread).where(EscalationThread.id == thread_id)
    )
    thread = result.scalar_one_or_none()
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.status == "answered":
        raise HTTPException(status_code=400, detail="Thread already answered")

    # Load conversation state
    state_result = await db.execute(
        select(SMSConversationState).where(
            SMSConversationState.id == thread.conversation_state_id
        )
    )
    state = state_result.scalar_one_or_none()

    # Record the answer
    from wex_platform.services.escalation_service import EscalationService
    escalation_service = EscalationService(db)
    thread = await escalation_service.record_answer(
        thread_id=thread_id,
        answer_text=body.answer,
        answered_by=body.answered_by,
        state=state,
    )

    if not thread:
        raise HTTPException(status_code=500, detail="Failed to record answer")

    # Run through gatekeeper
    from wex_platform.agents.sms.gatekeeper import validate_outbound

    # Build response message
    from wex_platform.agents.sms.field_catalog import get_label
    label = get_label(thread.field_key) if thread.field_key else "your question"
    response_text = f"Got an answer on {label}: {body.answer}"

    gate = validate_outbound(response_text)
    if not gate.ok:
        # Try polishing
        from wex_platform.agents.sms.polisher_agent import PolisherAgent
        polisher = PolisherAgent()
        response_text = await polisher.polish(response_text, gate.hint, max_length=320)

        gate = validate_outbound(response_text)
        if not gate.ok:
            # Use minimal answer
            response_text = body.answer[:310]

    thread.answer_sent_text = response_text
    thread.answer_sent_mode = "ops_reply"

    # Send to buyer
    if state and state.phone:
        try:
            sms_service = SMSService()
            await sms_service.send_buyer_sms(state.phone, response_text)

            # Update state
            state.last_system_message_at = datetime.now(timezone.utc)
            if state.phase == "AWAITING_ANSWER":
                state.phase = "PROPERTY_FOCUSED"

        except Exception as e:
            logger.error("Failed to send escalation answer SMS: %s", e)

    await db.commit()

    return {
        "ok": True,
        "thread_id": thread_id,
        "answer_sent": response_text,
        "status": thread.status,
    }

"""Escalation Service — handles unanswerable property questions."""
import logging
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.sms_models import EscalationThread

logger = logging.getLogger(__name__)

# SLA: 2 hours
ESCALATION_SLA_HOURS = 2


class EscalationService:
    """Manages property question escalation when detail fetcher can't answer."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_and_escalate(
        self,
        property_id: str,
        question_text: str,
        field_key: str | None,
        state,  # SMSConversationState
    ) -> dict:
        """3-layer check before creating an escalation.

        Returns dict with:
          - escalated: bool
          - answer: str | None (if found without escalating)
          - thread_id: str | None (if escalated)
        """
        # Layer 1: Check known_answers for this property + field
        if field_key:
            known = (state.known_answers or {}).get(property_id, {}).get(field_key)
            if known:
                return {"escalated": False, "answer": known.get("formatted", str(known.get("value", "")))}

        # Layer 2: Check answered_questions for same property
        answered = state.answered_questions or []
        for aq in answered:
            if aq.get("property_id") == property_id and self._questions_match(question_text, aq.get("question", "")):
                return {"escalated": False, "answer": aq.get("answer", "")}

        # Layer 3: Check existing escalation threads for this property + field
        existing = await self._find_existing_thread(property_id, field_key, state.id)
        if existing:
            if existing.status == "answered" and existing.answer_sent_text:
                return {"escalated": False, "answer": existing.answer_sent_text}
            elif existing.status == "pending":
                return {"escalated": False, "answer": None, "thread_id": existing.id, "waiting": True}

        # All checks missed -> create escalation
        thread = await self._create_thread(
            conversation_state_id=state.id,
            property_id=property_id,
            question_text=question_text,
            field_key=field_key,
        )

        # Update pending escalations on state
        pending = dict(state.pending_escalations or {})
        pending[thread.id] = {
            "property_id": property_id,
            "question": question_text,
            "field_key": field_key,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        state.pending_escalations = pending

        return {"escalated": True, "answer": None, "thread_id": thread.id}

    async def record_answer(
        self,
        thread_id: str,
        answer_text: str,
        answered_by: str,
        state=None,
    ) -> EscalationThread | None:
        """Record an answer to an escalation thread."""
        result = await self.db.execute(
            select(EscalationThread).where(EscalationThread.id == thread_id)
        )
        thread = result.scalar_one_or_none()
        if not thread:
            logger.warning("Escalation thread %s not found", thread_id)
            return None

        thread.answer_raw_text = answer_text
        thread.answer_polished_text = answer_text  # Will be polished by caller
        thread.answered_at = datetime.now(timezone.utc)
        thread.answered_by = answered_by
        thread.status = "answered"

        # Update state if provided
        if state:
            # Add to answered_questions
            answered = list(state.answered_questions or [])
            answered.append({
                "property_id": thread.property_id,
                "question": thread.question_text,
                "field_key": thread.field_key,
                "answer": answer_text,
                "thread_id": thread_id,
            })
            state.answered_questions = answered

            # Remove from pending
            pending = dict(state.pending_escalations or {})
            pending.pop(thread_id, None)
            state.pending_escalations = pending

            # Cache in known_answers if we have a field_key
            if thread.field_key:
                known = dict(state.known_answers or {})
                if thread.property_id not in known:
                    known[thread.property_id] = {}
                known[thread.property_id][thread.field_key] = {
                    "value": answer_text,
                    "formatted": answer_text,
                }
                state.known_answers = known

        await self.db.flush()
        return thread

    async def _find_existing_thread(
        self, property_id: str, field_key: str | None, state_id: str
    ) -> EscalationThread | None:
        """Find an existing escalation thread for this property/field combo."""
        query = select(EscalationThread).where(
            EscalationThread.conversation_state_id == state_id,
            EscalationThread.property_id == property_id,
        )
        if field_key:
            query = query.where(EscalationThread.field_key == field_key)

        result = await self.db.execute(query.order_by(EscalationThread.created_at.desc()).limit(1))
        return result.scalar_one_or_none()

    async def _create_thread(
        self,
        conversation_state_id: str,
        property_id: str,
        question_text: str,
        field_key: str | None,
    ) -> EscalationThread:
        """Create a new escalation thread."""
        thread = EscalationThread(
            id=str(uuid.uuid4()),
            conversation_state_id=conversation_state_id,
            property_id=property_id,
            question_text=question_text,
            field_key=field_key,
            status="pending",
            sla_deadline_at=datetime.utcnow() + timedelta(hours=ESCALATION_SLA_HOURS),
        )
        self.db.add(thread)
        await self.db.flush()
        logger.info(
            "Created escalation thread %s for property %s, field %s",
            thread.id, property_id, field_key,
        )
        return thread

    @staticmethod
    def _questions_match(q1: str, q2: str) -> bool:
        """Check if two questions are semantically similar (simple text match)."""
        # Normalize
        q1_norm = q1.lower().strip().rstrip("?").strip()
        q2_norm = q2.lower().strip().rstrip("?").strip()

        # Exact match after normalization
        if q1_norm == q2_norm:
            return True

        # One contains the other
        if q1_norm in q2_norm or q2_norm in q1_norm:
            return True

        return False

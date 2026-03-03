"""Escalation Service — handles unanswerable property questions."""
import asyncio
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
        source_type: str = "sms",
    ) -> dict:
        """4-layer check before creating an escalation.

        Returns dict with:
          - escalated: bool
          - answer: str | None (if found without escalating)
          - thread_id: str | None (if escalated)

        source_type: the originating channel (e.g. "sms", "voice") passed through
          to the created thread for cross-channel dedup tracking.
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

        # Layer 4: Cross-channel dedup — check other channels' threads for same property/question
        cross = await self._find_existing_thread_cross_channel(property_id, field_key, question_text)
        if cross:
            if cross.status == "answered" and cross.answer_sent_text:
                return {"escalated": False, "answer": cross.answer_sent_text}
            elif cross.status == "pending":
                return {"escalated": False, "answer": None, "thread_id": cross.id, "waiting": True}

        # All checks missed -> create escalation
        thread = await self._create_thread(
            conversation_state_id=state.id,
            property_id=property_id,
            question_text=question_text,
            field_key=field_key,
            source_type=source_type,
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

        # After thread creation, send email notification (fire-and-forget)
        asyncio.ensure_future(self._send_escalation_email(thread, state))

        return {"escalated": True, "answer": None, "thread_id": thread.id}

    async def _send_escalation_email(self, thread, state) -> None:
        """Fire-and-forget email notification for new escalation."""
        try:
            from wex_platform.services.email_service import send_escalation_email
            from wex_platform.domain.models import Property, Warehouse
            from wex_platform.app.config import get_settings

            settings = get_settings()

            # Look up property address
            address = "Unknown Property"
            prop_result = await self.db.execute(
                select(Property).where(Property.id == thread.property_id)
            )
            prop = prop_result.scalar_one_or_none()
            if prop:
                parts = [p for p in [prop.address, prop.city, prop.state] if p]
                address = ", ".join(parts) if parts else "Unknown Property"
            else:
                wh_result = await self.db.execute(
                    select(Warehouse).where(Warehouse.id == thread.property_id)
                )
                wh = wh_result.scalar_one_or_none()
                if wh and wh.address:
                    address = wh.address

            # Build reply tool URL
            base_url = settings.frontend_url.rstrip("/")
            reply_tool_url = f"{base_url}/api/sms/internal/form/{thread.id}?token={settings.admin_password}"

            # Get recent messages — SMS uses messages/conversation_history,
            # Voice uses call_transcript
            recent_messages = []
            if state:
                history = (
                    getattr(state, 'conversation_history', None)
                    or getattr(state, 'messages', None)
                    or getattr(state, 'call_transcript', None)
                    or []
                )
                if isinstance(history, list):
                    recent_messages = history[-5:] if len(history) > 5 else history

            # Extract buyer phone/name — field names differ between
            # SMSConversationState (.phone, .renter_first_name) and
            # VoiceCallState (.caller_phone/.verified_phone, .buyer_name)
            buyer_phone = "Unknown"
            buyer_name = "Unknown"
            if state:
                buyer_phone = (
                    getattr(state, 'phone', None)
                    or getattr(state, 'verified_phone', None)
                    or getattr(state, 'caller_phone', None)
                    or "Unknown"
                )
                buyer_name = (
                    getattr(state, 'renter_first_name', None)
                    or getattr(state, 'buyer_name', None)
                    or "Unknown"
                )

            # Build email data
            data = {
                "property_address": address,
                "property_id": thread.property_id,
                "question_text": thread.question_text,
                "source_type": thread.source_type or "sms",
                "buyer_phone": buyer_phone,
                "buyer_name": buyer_name,
                "thread_id": thread.id,
                "reply_tool_url": reply_tool_url,
                "recent_messages": recent_messages,
                "field_key": thread.field_key,
            }

            await send_escalation_email(data)
        except Exception:
            logger.exception("Failed to send escalation email for thread %s", thread.id)

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

    async def _find_existing_thread_cross_channel(
        self, property_id: str, field_key: str | None, question_text: str
    ) -> EscalationThread | None:
        """Find an escalation thread across ALL channels for the same property+question.

        Unlike _find_existing_thread(), this does NOT filter by conversation_state_id,
        enabling SMS threads to be found by a voice call and vice versa.
        Used as Layer 4 to prevent duplicate escalations across channels.
        """
        query = select(EscalationThread).where(
            EscalationThread.property_id == property_id,
        )
        if field_key:
            query = query.where(EscalationThread.field_key == field_key)

        result = await self.db.execute(
            query.order_by(EscalationThread.created_at.desc()).limit(20)
        )
        threads = result.scalars().all()

        for thread in threads:
            if not field_key:
                # For unmapped questions, use text matching to find the right thread
                if self._questions_match(question_text, thread.question_text):
                    return thread
            else:
                # field_key match is sufficient (already filtered in query)
                return thread

        return None

    async def _create_thread(
        self,
        conversation_state_id: str,
        property_id: str,
        question_text: str,
        field_key: str | None,
        source_type: str = "sms",
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
            source_type=source_type,
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

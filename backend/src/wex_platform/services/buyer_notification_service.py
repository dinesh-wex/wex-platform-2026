"""Buyer Notification Service — proactive SMS notifications and re-engagement."""
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.sms_models import SMSConversationState, EscalationThread
from wex_platform.services.sms_service import SMSService

logger = logging.getLogger(__name__)

# Stall rules: {phase: [(delay_hours, max_nudges_at_this_tier), ...]}
STALL_RULES = {
    "PRESENTING": [(4, 2)],
    "PROPERTY_FOCUSED": [(24, 2)],
    "GUARANTEE_PENDING": [(0.5, 1), (4, 1)],  # 30min first, then 4h
}

# Re-engagement messages by phase
STALL_MESSAGES = {
    "PRESENTING": [
        "Still looking at those options? Let me know if you'd like more details on any of them.",
        "Just checking in. Want to hear more about any of the spaces I found?",
    ],
    "PROPERTY_FOCUSED": [
        "Any more questions about that space? I'm here if you need anything.",
        "Still interested in that property? Let me know how I can help.",
    ],
    "GUARANTEE_PENDING": [
        "Just a reminder, your signing link is ready. Tap it to unlock the property address.",
        "Don't forget to sign the guarantee to see the full address and schedule a tour.",
    ],
}

# Dormant nudge
DORMANT_MESSAGE = "Hey, it's been a while! Still looking for warehouse space? Text me anytime to restart your search."

# Inactivity thresholds
INTAKE_ABANDONMENT_DAYS = 30
DORMANT_ABANDONMENT_DAYS = 7


class BuyerNotificationService:
    """Handles proactive notifications and re-engagement nudges."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.sms_service = SMSService()

    # ------------------------------------------------------------------
    # Event-driven notifications
    # ------------------------------------------------------------------

    async def notify_tour_confirmed(self, state: SMSConversationState, confirmed_date: str | None = None):
        """Send tour confirmed notification."""
        msg = "Great news, your tour is confirmed!"
        if confirmed_date:
            msg += f" It's set for {confirmed_date}."
        msg += " I'll send you a reminder before the visit."
        await self._send_if_allowed(state, msg)

    async def notify_tour_reminder(self, state: SMSConversationState, hours_before: int = 2):
        """Send tour reminder."""
        msg = f"Reminder: your warehouse tour is in about {hours_before} hours. See you there!"
        await self._send_if_allowed(state, msg)

    async def notify_escalation_answered(self, state: SMSConversationState, answer: str):
        """Send escalation answer notification."""
        await self._send_if_allowed(state, answer)

    async def notify_new_match(self, state: SMSConversationState, match_summary: dict):
        """Send new match notification."""
        city = match_summary.get("city", "your area")
        sqft = match_summary.get("sqft", "")
        rate = match_summary.get("rate", "")
        msg = f"New space alert: {city}"
        if sqft:
            msg += f", {sqft:,} sqft" if isinstance(sqft, int) else f", {sqft} sqft"
        if rate:
            msg += f", ${rate}/sqft"
        msg += ". Text back to learn more."
        await self._send_if_allowed(state, msg)

    # ------------------------------------------------------------------
    # Stall detection and re-engagement
    # ------------------------------------------------------------------

    async def check_stale_conversations(self) -> int:
        """Check for stale conversations and send re-engagement nudges.

        Returns number of nudges sent.
        """
        now = datetime.now(timezone.utc)
        nudges_sent = 0

        for phase, tiers in STALL_RULES.items():
            for tier_idx, (delay_hours, max_nudges) in enumerate(tiers):
                tier_key = f"{phase}_{tier_idx}" if tier_idx > 0 else phase
                cutoff = now - timedelta(hours=delay_hours)

                result = await self.db.execute(
                    select(SMSConversationState).where(
                        and_(
                            SMSConversationState.phase == phase,
                            SMSConversationState.last_buyer_message_at < cutoff,
                            SMSConversationState.opted_out == False,
                        )
                    )
                )
                states = result.scalars().all()

                for state in states:
                    nudge_counts = dict(state.stall_nudge_counts or {})

                    # For multi-tier phases, check that previous tiers are exhausted
                    if tier_idx > 0:
                        prev_key = f"{phase}_{tier_idx - 1}" if tier_idx > 1 else phase
                        prev_max = tiers[tier_idx - 1][1]
                        if nudge_counts.get(prev_key, 0) < prev_max:
                            continue

                    current_count = nudge_counts.get(tier_key, 0)
                    if current_count >= max_nudges:
                        continue

                    # Check if we've already sent a nudge recently
                    if state.last_system_message_at and state.last_system_message_at > cutoff:
                        continue

                    # Send nudge — compute total nudges sent across all tiers for message selection
                    total_nudges = sum(nudge_counts.get(f"{phase}_{i}" if i > 0 else phase, 0) for i in range(len(tiers)))
                    messages = STALL_MESSAGES.get(phase, [])
                    msg_idx = min(total_nudges, len(messages) - 1) if messages else 0
                    msg = messages[msg_idx] if messages else "Still there? Let me know if you need anything."

                    sent = await self._send_if_allowed(state, msg)
                    if sent:
                        nudge_counts[tier_key] = current_count + 1
                        state.stall_nudge_counts = nudge_counts
                        state.last_system_message_at = now
                        nudges_sent += 1

        if nudges_sent:
            await self.db.flush()

        return nudges_sent

    async def check_dormant_transitions(self) -> int:
        """Check for conversations that should transition to DORMANT.

        Triggered when re-engagement nudges are exhausted across phases.
        Returns number of transitions.
        """
        now = datetime.now(timezone.utc)
        transitions = 0

        # Find active conversations where all nudges are exhausted
        result = await self.db.execute(
            select(SMSConversationState).where(
                and_(
                    SMSConversationState.phase.in_(["PRESENTING", "PROPERTY_FOCUSED"]),
                    SMSConversationState.opted_out == False,
                )
            )
        )
        states = result.scalars().all()

        for state in states:
            nudge_counts = dict(state.stall_nudge_counts or {})
            phase_tiers = STALL_RULES.get(state.phase)
            if not phase_tiers:
                continue

            # Check if ALL tiers are exhausted
            all_exhausted = True
            for tier_idx, (_, max_nudges) in enumerate(phase_tiers):
                tier_key = f"{state.phase}_{tier_idx}" if tier_idx > 0 else state.phase
                if nudge_counts.get(tier_key, 0) < max_nudges:
                    all_exhausted = False
                    break

            if all_exhausted:
                # All nudges exhausted and still no response
                last_activity = state.last_buyer_message_at or state.created_at
                if last_activity and (now - last_activity).total_seconds() > 7 * 24 * 3600:
                    state.phase = "DORMANT"
                    transitions += 1

        if transitions:
            await self.db.flush()

        return transitions

    # ------------------------------------------------------------------
    # Inactivity abandonment
    # ------------------------------------------------------------------

    async def check_inactivity_abandonment(self) -> int:
        """Check for conversations that should be abandoned due to inactivity.

        Two queries:
        1. INTAKE/QUALIFYING with no buyer activity for 30 days
        2. DORMANT with no system message for 7 days after final nudge

        Returns number of abandonments.
        """
        now = datetime.now(timezone.utc)
        abandonments = 0

        # Query 1: INTAKE/QUALIFYING 30-day timeout
        intake_cutoff = now - timedelta(days=INTAKE_ABANDONMENT_DAYS)
        result = await self.db.execute(
            select(SMSConversationState).where(
                and_(
                    SMSConversationState.phase.in_(["INTAKE", "QUALIFYING"]),
                    SMSConversationState.last_buyer_message_at < intake_cutoff,
                    SMSConversationState.opted_out == False,
                )
            )
        )
        for state in result.scalars().all():
            state.phase = "ABANDONED"
            abandonments += 1

        # Query 2: DORMANT 7-day timeout after last system message
        dormant_cutoff = now - timedelta(days=DORMANT_ABANDONMENT_DAYS)
        result = await self.db.execute(
            select(SMSConversationState).where(
                and_(
                    SMSConversationState.phase == "DORMANT",
                    SMSConversationState.last_system_message_at < dormant_cutoff,
                    SMSConversationState.opted_out == False,
                )
            )
        )
        for state in result.scalars().all():
            state.phase = "ABANDONED"
            abandonments += 1

        if abandonments:
            await self.db.flush()
            logger.info("Abandoned %d stale conversations", abandonments)

        return abandonments

    # ------------------------------------------------------------------
    # Escalation SLA check
    # ------------------------------------------------------------------

    async def check_escalation_sla(self) -> int:
        """Check for escalation threads approaching or past SLA.

        Sends buyer nudge if past SLA and not yet nudged.
        Returns number of nudges sent.
        """
        now = datetime.now(timezone.utc)
        nudges = 0

        result = await self.db.execute(
            select(EscalationThread).where(
                and_(
                    EscalationThread.status == "pending",
                    EscalationThread.sla_deadline_at < now,
                    EscalationThread.buyer_nudge_sent == False,
                )
            )
        )
        threads = result.scalars().all()

        for thread in threads:
            # Load the conversation state to get buyer phone
            state_result = await self.db.execute(
                select(SMSConversationState).where(
                    SMSConversationState.id == thread.conversation_state_id
                )
            )
            state = state_result.scalar_one_or_none()
            if not state or state.opted_out:
                continue

            msg = "Still working on getting an answer to your question. Thanks for your patience, I'll text back as soon as I hear."
            sent = await self._send_if_allowed(state, msg)
            if sent:
                thread.buyer_nudge_sent = True
                nudges += 1

        if nudges:
            await self.db.flush()

        return nudges

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _send_if_allowed(self, state: SMSConversationState, message: str) -> bool:
        """Send SMS if not opted out and not in quiet hours."""
        if state.opted_out:
            return False

        # Check quiet hours for proactive messages
        # Infer timezone from search city (simplified: default to Eastern)
        timezone_str = None  # Could be inferred from state.criteria_snapshot city
        if SMSService.check_quiet_hours(timezone_str):
            logger.debug("Quiet hours — queuing message for %s", state.phone)
            return False  # In a real impl, would queue for later

        try:
            await self.sms_service.send_buyer_sms(state.phone, message)
            return True
        except Exception as e:
            logger.error("Failed to send notification to %s: %s", state.phone, e)
            return False

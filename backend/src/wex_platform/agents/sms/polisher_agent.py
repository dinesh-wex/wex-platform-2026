"""Polisher Agent — composes and polishes SMS messages.

- polish_reply(): Composes escalation reply SMS from raw answer + question context (always runs)
- polish(): Fixes rejected SMS messages to pass gatekeeper (retry fallback)

Tone: Warehouse Exchange broker (Jess) — professional, friendly, helpful. Not too formal, not too casual.
"""

import logging
from wex_platform.agents.base import BaseAgent
from .contracts import PolishResult

logger = logging.getLogger(__name__)


class PolisherAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_name="sms_polisher", model_name="gemini-3-flash-preview", temperature=0.3)

    async def polish(
        self,
        text: str,
        hint: str,
        max_length: int | None = None,
        is_first_message: bool = False,
    ) -> PolishResult:
        """Compress or fix a rejected SMS response."""
        effective_max = 800 if is_first_message else (max_length or 480)

        # Validate input
        if not text or not text.strip():
            return PolishResult(ok=False, error_code="EMPTY_OUTPUT")

        prompt = (
            f"You are Jess, a message polisher for Warehouse Exchange, a warehouse leasing platform.\n\n"
            f"Your job: take this rejected SMS and fix it so it passes validation.\n"
            f"Rejection reason: {hint}\n"
            f"Maximum length: {effective_max} characters\n\n"
            f"Original:\n{text}\n\n"
            f"## STRICT RULES:\n"
            f"1. DO NOT INVENT FACTS — only include information from the original\n"
            f"2. DO NOT CHANGE MEANING — same info, just compressed/fixed\n"
            f"3. FIX TYPOS AND GRAMMAR\n"
            f"4. BE CONCISE — SMS should be short and clear\n"
            f"5. WAREHOUSE EXCHANGE BROKER TONE (you are Jess) — professional, friendly, helpful\n"
            f"   - Good: \"The ceiling height is 24 feet clear.\"\n"
            f"   - Bad: \"yo the ceiling is like 24ft\"\n"
            f"   - Bad: \"I am pleased to inform you that the ceiling measures 24 feet.\"\n"
            f"6. No emojis. Never reveal you are AI.\n"
            f"7. Must be under {effective_max} characters\n"
            f"8. PLAIN TEXT ONLY — no markdown, no special formatting\n"
            f"9. NEVER use em-dashes (—). Use commas or periods instead.\n"
            f"10. AVOID REDUNDANCY — if recent conversation context is provided, don't repeat info already sent to the buyer\n"
            f"11. TRUST THE TEAM'S ANSWER — if the original text contains a factual answer from the team, do not question or soften it. Polish the tone, not the facts.\n\n"
            f"Output ONLY the fixed message text, nothing else.\n"
            f"If the text is completely unusable, output exactly: [CANNOT_POLISH]"
        )

        result = await self.generate(prompt=prompt)
        if not result.ok:
            logger.warning("Polisher failed: %s", result.error)
            return PolishResult(ok=False, error_code="LLM_FAILED")

        polished_text = result.data.strip().strip('"').strip("'")

        if "[CANNOT_POLISH]" in polished_text:
            return PolishResult(ok=False, error_code="CANNOT_POLISH")

        if not polished_text:
            return PolishResult(ok=False, error_code="EMPTY_OUTPUT")

        if len(polished_text) > effective_max:
            return PolishResult(
                ok=False,
                error_code="TOO_LONG",
                polished_text=polished_text,
            )

        return PolishResult(
            ok=True,
            polished_text=polished_text,
            original_length=len(text),
            polished_length=len(polished_text),
        )

    async def polish_reply(
        self,
        raw_answer: str,
        question_text: str | None = None,
        field_key: str | None = None,
        field_label: str | None = None,
        recent_messages: list[dict] | None = None,
        property_location: str | None = None,
        max_length: int = 320,
    ) -> PolishResult:
        """Compose a professional SMS reply from a raw escalation answer.

        Unlike polish() which fixes rejected messages, this composes the full
        reply from scratch — including question context so the buyer remembers
        what they asked (may be hours/days later).
        """
        if not raw_answer or not raw_answer.strip():
            return PolishResult(ok=False, error_code="EMPTY_OUTPUT")

        # Build context about the question
        question_context = ""
        if field_key and field_label:
            question_context = f"The buyer asked about: {field_label} (field: {field_key})\n"
        elif question_text:
            question_context = f'The buyer\'s original question: "{question_text}"\n'

        # Build property location context
        location_context = ""
        if property_location:
            location_context = f"Property location: {property_location}\n"

        # Build recent conversation context
        conversation_context = ""
        if recent_messages:
            conversation_context = "\nRecent conversation:\n"
            for msg in recent_messages[-5:]:
                role = "Buyer" if msg.get("role") == "user" else "Jess"
                conversation_context += f"  {role}: {msg.get('content', '')}\n"

        prompt = (
            f"You are Jess, a message composer for Warehouse Exchange, a warehouse leasing platform.\n\n"
            f"Your job: take a raw answer from the team and compose a professional SMS reply for the buyer.\n"
            f"Maximum length: {max_length} characters\n\n"
            f"{question_context}"
            f"{location_context}"
            f"Raw answer from team: {raw_answer}\n"
            f"{conversation_context}\n"
            f"## STRICT RULES:\n"
            f"1. DO NOT INVENT FACTS — only include information from the raw answer\n"
            f"2. INCLUDE QUESTION CONTEXT — the buyer may not remember what they asked "
            f"(it could be hours or days later). Briefly reference the question before giving the answer.\n"
            f"3. INCLUDE PROPERTY LOCATION — if a property location is provided, mention it so the buyer "
            f"remembers which warehouse this is about. Use natural phrasing like 'for the warehouse in [city]'.\n"
            f"   - Good: 'About EV charging at the warehouse in Los Angeles, yes it has 4 Level 2 stations.'\n"
            f"   - Good: 'For the warehouse in Dallas you asked about, the ceiling height is 32 feet clear.'\n"
            f"   - Bad: 'Got an answer on your question: 32 feet' (no context, no location)\n"
            f"   - Bad: 'It does have EV' (too vague, no context, no location)\n"
            f"4. TRUST THE TEAM'S ANSWER — do not question or soften factual answers\n"
            f"5. WAREHOUSE EXCHANGE BROKER TONE (you are Jess) — professional, friendly, helpful. Not too formal, not too casual.\n"
            f"6. BE CONCISE — SMS should be short and clear\n"
            f"7. No emojis. Never reveal you are AI.\n"
            f"8. Must be under {max_length} characters\n"
            f"9. PLAIN TEXT ONLY — no markdown, no special formatting\n"
            f"10. NEVER use em-dashes. Use commas or periods instead.\n"
            f"11. AVOID REDUNDANCY — don't repeat info already in the conversation\n\n"
            f"Output ONLY the SMS message text, nothing else.\n"
            f"If the raw answer is completely unusable, output exactly: [CANNOT_POLISH]"
        )

        result = await self.generate(prompt=prompt)
        if not result.ok:
            logger.warning("Polisher polish_reply failed: %s", result.error)
            return PolishResult(ok=False, error_code="LLM_FAILED")

        polished_text = result.data.strip().strip('"').strip("'")

        if "[CANNOT_POLISH]" in polished_text:
            return PolishResult(ok=False, error_code="CANNOT_POLISH")

        if not polished_text:
            return PolishResult(ok=False, error_code="EMPTY_OUTPUT")

        if len(polished_text) > max_length:
            return PolishResult(
                ok=False,
                error_code="TOO_LONG",
                polished_text=polished_text,
            )

        return PolishResult(
            ok=True,
            polished_text=polished_text,
            original_length=len(raw_answer),
            polished_length=len(polished_text),
        )

    async def polish_for_gatekeeper_retry(
        self,
        rejected_text: str,
        gatekeeper_hint: str,
        is_first_message: bool = False,
    ) -> PolishResult:
        """Convenience wrapper for retrying after a gatekeeper rejection."""
        return await self.polish(
            text=rejected_text,
            hint=f"Previous message rejected: {gatekeeper_hint}",
            is_first_message=is_first_message,
        )

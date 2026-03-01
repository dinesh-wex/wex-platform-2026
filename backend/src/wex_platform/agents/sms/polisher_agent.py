"""Polisher Agent — compresses/fixes SMS responses rejected by gatekeeper.

Tone: WEX broker — professional, friendly, helpful. Not too formal, not too casual.
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
            f"You are a message polisher for Warehouse Exchange (WEX), a warehouse leasing platform.\n\n"
            f"Your job: take this rejected SMS and fix it so it passes validation.\n"
            f"Rejection reason: {hint}\n"
            f"Maximum length: {effective_max} characters\n\n"
            f"Original:\n{text}\n\n"
            f"## STRICT RULES:\n"
            f"1. DO NOT INVENT FACTS — only include information from the original\n"
            f"2. DO NOT CHANGE MEANING — same info, just compressed/fixed\n"
            f"3. FIX TYPOS AND GRAMMAR\n"
            f"4. BE CONCISE — SMS should be short and clear\n"
            f"5. WEX BROKER TONE — professional, friendly, helpful\n"
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

"""Polisher Agent — compresses/fixes SMS responses rejected by gatekeeper.

Tone: WEX broker — professional, friendly, helpful. Not too formal, not too casual.
"""

import logging
from wex_platform.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class PolisherAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_name="sms_polisher", model_name="gemini-3-flash-preview", temperature=0.3)

    async def polish(self, text: str, hint: str, max_length: int = 320) -> str:
        """Compress or fix a rejected SMS response."""
        prompt = (
            f"You are a message polisher for Warehouse Exchange (WEX), a warehouse leasing platform.\n\n"
            f"Your job: take this rejected SMS and fix it so it passes validation.\n"
            f"Rejection reason: {hint}\n"
            f"Maximum length: {max_length} characters\n\n"
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
            f"7. Must be under {max_length} characters\n"
            f"8. PLAIN TEXT ONLY — no markdown, no special formatting\n"
            f"9. NEVER use em-dashes (—). Use commas or periods instead.\n\n"
            f"Output ONLY the fixed message text, nothing else."
        )
        result = await self.generate(prompt=prompt)
        if not result.ok:
            logger.warning("Polisher failed: %s", result.error)
            return text[:max_length]
        return result.data.strip().strip('"').strip("'")

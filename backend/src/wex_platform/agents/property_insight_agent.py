"""PropertyInsight Agent — 2-LLM-call knowledge lookup before escalation."""

import logging

from wex_platform.agents.base import BaseAgent, AgentResult
from wex_platform.agents.prompts.property_insight import (
    TRANSLATE_QUESTION_PROMPT,
    EVALUATE_CANDIDATES_PROMPT,
)

logger = logging.getLogger(__name__)


class PropertyInsightAgent(BaseAgent):
    """Translates buyer questions into search parameters and evaluates candidates.

    Uses two LLM calls:
    1. translate_question — expands the buyer question into keywords, category,
       and relevant memory types for database search.
    2. evaluate — scores retrieved knowledge candidates against the original
       question and returns a formatted answer if one is found.
    """

    def __init__(self):
        super().__init__(
            agent_name="property_insight",
            model_name="gemini-3-flash-preview",
            temperature=0.2,
        )

    async def translate_question(self, question: str) -> AgentResult:
        """Expand a buyer question into structured search parameters.

        Args:
            question: The raw buyer question about a property.

        Returns:
            AgentResult with parsed JSON containing keywords, category,
            and relevant_memory_types.
        """
        prompt = TRANSLATE_QUESTION_PROMPT.format(question=question)
        return await self.generate_json(prompt=prompt)

    async def evaluate(
        self,
        question: str,
        candidates: list[dict],
        channel: str = "sms",
    ) -> AgentResult:
        """Evaluate ranked candidates to answer the buyer question.

        Args:
            question: The original buyer question.
            candidates: List of candidate dicts with keys: index, content,
                source, confidence, score.
            channel: Response format channel ("sms" or "voice").

        Returns:
            AgentResult with parsed JSON containing found, answer,
            confidence, and candidate_used.
        """
        candidates_text = "\n".join(
            f"[{c['index']}] (score={c['score']:.2f}, source={c['source']}, "
            f"confidence={c['confidence']:.2f}): {c['content']}"
            for c in candidates
        )
        prompt = EVALUATE_CANDIDATES_PROMPT.format(
            question=question,
            candidates=candidates_text,
            channel=channel,
        )
        return await self.generate_json(prompt=prompt)

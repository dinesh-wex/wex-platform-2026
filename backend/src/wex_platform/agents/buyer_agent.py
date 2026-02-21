"""Buyer Agent - Conducts buyer need intake conversations."""

import json
import logging
from typing import Optional

from wex_platform.agents.base import BaseAgent, AgentResult
from wex_platform.agents.prompts.buyer import BUYER_INTAKE_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class BuyerAgent(BaseAgent):
    """Conducts buyer need intake via conversational interface.

    The buyer agent walks a prospective tenant through a friendly
    conversation to understand exactly what kind of warehouse space
    they need.  It progressively extracts structured fields (city,
    size, use type, timing, budget, requirements) and signals when
    the need is complete enough to run through the clearing engine.

    State is managed externally (by the route handler) and passed
    into each call.  The agent itself is stateless between requests.
    """

    def __init__(self):
        super().__init__(
            agent_name="buyer",
            model_name="gemini-3-flash-preview",
            temperature=0.7,
        )

    async def process_message(
        self,
        buyer_id: str,
        user_message: str,
        conversation_history: list[dict],
        extracted_need: Optional[dict] = None,
    ) -> AgentResult:
        """Process a buyer message in the need intake conversation.

        Args:
            buyer_id: The buyer conducting the intake.
            user_message: The buyer's latest message.
            conversation_history: Previous messages [{role, content}].
            extracted_need: Previously extracted need fields.

        Returns:
            AgentResult with data containing:
            - message: Agent's conversational response
            - extracted_need: Updated extracted need dict
            - need_complete: Whether enough info has been collected
            - confidence: How confident the agent is in the extraction
        """
        if extracted_need is None:
            extracted_need = {}

        # Build the conversation messages for the chat
        messages = []

        for msg in conversation_history:
            messages.append({
                "role": msg["role"],
                "parts": [msg["content"]],
            })

        # Add the new user message with context about what we already know
        user_text = (
            f"[Context: extracted={json.dumps(extracted_need)}]\n\n"
            f"Buyer says: {user_message}"
        )
        messages.append({"role": "user", "parts": [user_text]})

        # Call Gemini via chat with the buyer intake system prompt
        result = await self.chat(
            messages=messages,
            system_instruction=BUYER_INTAKE_SYSTEM_PROMPT,
        )

        if not result.ok:
            return result

        # Parse the response
        try:
            response_data = json.loads(result.data)
        except (json.JSONDecodeError, TypeError):
            # If not valid JSON, wrap it
            response_data = {
                "message": result.data,
                "extracted_need": extracted_need,
                "need_complete": False,
                "confidence": 0.0,
            }

        # Merge extracted need fields (new values overwrite old)
        new_need = response_data.get("extracted_need", {})
        for key, value in new_need.items():
            if value is not None:
                extracted_need[key] = value
        response_data["extracted_need"] = extracted_need

        return AgentResult.success(
            data=response_data,
            tokens_used=result.tokens_used,
            latency_ms=result.latency_ms,
        )

    async def generate_initial_message(self) -> AgentResult:
        """Generate the opening message for buyer intake.

        Called when a new buyer conversation is started.  Returns a
        warm welcome message that kicks off the need-discovery flow.

        Returns:
            AgentResult with the initial conversation message in JSON format.
        """
        prompt = (
            "Generate a warm opening message for a buyer looking for "
            "warehouse space through WEx.\n\n"
            "Welcome them and ask what kind of space they're looking for. "
            "Start with location and general use.\n\n"
            "Respond in the JSON format specified in your system instructions."
        )

        return await self.generate(
            prompt=prompt,
            system_instruction=BUYER_INTAKE_SYSTEM_PROMPT,
            json_mode=True,
        )

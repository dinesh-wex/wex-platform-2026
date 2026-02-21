"""Activation Agent - Onboards warehouse owners onto the WEx network."""

import json
import logging
from typing import Optional
from datetime import datetime, timezone

from wex_platform.agents.base import BaseAgent, AgentResult
from wex_platform.agents.prompts.activation import ACTIVATION_SYSTEM_PROMPT, EXTRACTION_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


class ActivationAgent(BaseAgent):
    """Conducts the 5-step warehouse activation conversation.

    The activation flow walks a warehouse owner through:
        1. Space Overview - building size, available sqft, type
        2. Availability - dates, min/max term
        3. Activity Type - activity tier, certifications
        4. Constraints - deal-breakers and restrictions
        5. Pricing - rate guidance and final rate selection

    State is managed externally (by the route handler) and passed into
    each call.  The agent itself is stateless between requests.
    """

    def __init__(self):
        super().__init__(
            agent_name="activation",
            model_name="gemini-3-flash-preview",
            temperature=0.7,
        )

    async def process_message(
        self,
        warehouse_id: str,
        user_message: str,
        conversation_history: list[dict],
        building_data: Optional[dict] = None,
        current_step: int = 1,
        extracted_fields: Optional[dict] = None,
        idle_sqft: Optional[int] = None,
        pricing_path: Optional[str] = None,
    ) -> AgentResult:
        """Process a message in the activation conversation.

        Args:
            warehouse_id: The warehouse being activated.
            user_message: The owner's latest message.
            conversation_history: Previous messages [{role, content}].
            building_data: Pre-loaded building data (from seed/DB).
            current_step: Current step in the 5-step flow (1-5).
            extracted_fields: Previously extracted truth core fields.

        Returns:
            AgentResult with data containing:
            - message: Agent's response text
            - current_step: Updated step number
            - extracted_fields: Updated extracted fields dict
            - step_complete: Whether current step is complete
            - all_steps_complete: Whether all 5 steps are done
        """
        if extracted_fields is None:
            extracted_fields = {}

        # Build the conversation messages for the chat
        messages = []

        # Add context about the building and current state
        context = f"Building data: {json.dumps(building_data or {})}\n"
        context += f"Current step: {current_step}\n"
        context += f"Already extracted: {json.dumps(extracted_fields)}\n"
        context += f"Idle sqft from Phase 1: {idle_sqft}\n"
        context += f"Pricing path: {pricing_path}\n"

        # Add conversation history
        for msg in conversation_history:
            messages.append({
                "role": msg["role"],
                "parts": [msg["content"]],
            })

        # Add the new user message with context
        if not messages:
            # First message - include full context
            user_text = f"{context}\n\nOwner says: {user_message}"
        else:
            user_text = (
                f"[Context: step={current_step}, "
                f"extracted={json.dumps(extracted_fields)}, "
                f"idle_sqft={idle_sqft}, pricing_path={pricing_path}]\n\n"
                f"Owner says: {user_message}"
            )

        messages.append({
            "role": "user",
            "parts": [user_text],
        })

        # Call Gemini via chat with the activation system prompt
        result = await self.chat(
            messages=messages,
            system_instruction=ACTIVATION_SYSTEM_PROMPT,
        )

        if not result.ok:
            return result

        # Strip markdown code fences if Gemini wrapped the JSON
        raw = result.data.strip() if isinstance(result.data, str) else str(result.data)
        if raw.startswith("```"):
            # Remove opening fence (```json or ```) and closing ```
            lines = raw.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

        try:
            response_data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # If not valid JSON, wrap it
            response_data = {
                "message": raw,
                "current_step": current_step,
                "extracted_fields": {},
                "step_complete": False,
                "all_steps_complete": False,
            }

        # Merge newly extracted fields
        new_fields = response_data.get("extracted_fields", {})
        for key, value in new_fields.items():
            if value is not None:
                extracted_fields[key] = value

        response_data["extracted_fields"] = extracted_fields

        return AgentResult.success(
            data=response_data,
            tokens_used=result.tokens_used,
            latency_ms=result.latency_ms,
        )

    async def generate_initial_message(
        self,
        building_data: Optional[dict] = None,
    ) -> AgentResult:
        """Generate the opening message for activation.

        If building data is available, acknowledge it and confirm details.
        Otherwise, ask the owner about their space from scratch.

        Args:
            building_data: Optional pre-loaded building information.

        Returns:
            AgentResult with the initial conversation message in JSON format.
        """
        if building_data:
            address = building_data.get("address", "your building")
            size = building_data.get("building_size_sqft", "")
            size_str = f"{size:,} sqft" if size else "your space"

            prompt = (
                "Generate an opening message for a warehouse owner who wants "
                "to activate their space on WEx.\n\n"
                f"We have building data:\n"
                f"- Address: {address}\n"
                f"- Size: {size_str}\n"
                f"- Building data: {json.dumps(building_data)}\n\n"
                "Start with a warm greeting, confirm the building data we "
                "have, and begin Step 1 by asking about their available space.\n\n"
                "Respond in the JSON format specified in your system instructions."
            )
        else:
            prompt = (
                "Generate an opening message for a warehouse owner who wants "
                "to activate their space on WEx.\n\n"
                "We don't have any building data yet. Start with a warm "
                "greeting and ask them to tell us about their space "
                "(address, size, type).\n\n"
                "Respond in the JSON format specified in your system instructions."
            )

        return await self.generate(
            prompt=prompt,
            system_instruction=ACTIVATION_SYSTEM_PROMPT,
            json_mode=True,
        )

    async def extract_fields(
        self,
        conversation_history: list[dict],
        building_data: Optional[dict] = None,
        current_step: int = 1,
        idle_sqft: Optional[int] = None,
    ) -> AgentResult:
        """Run a separate extraction pass over the conversation.

        Useful when you want to reconcile what the main conversation
        response extracted vs. a dedicated extraction model pass.

        Args:
            conversation_history: Full conversation so far.
            building_data: Optional building data for context.
            current_step: The current activation step.

        Returns:
            AgentResult with extracted fields dict in data.
        """
        conv_text = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in conversation_history
        )

        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            building_data=json.dumps(building_data or {}),
            conversation=conv_text,
            current_step=current_step,
            idle_sqft=idle_sqft,
        )

        return await self.generate_json(prompt=prompt)

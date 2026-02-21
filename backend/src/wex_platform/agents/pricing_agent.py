"""Pricing Agent - Market intelligence and rate guidance."""

import json
import logging
from typing import Optional

from wex_platform.agents.base import BaseAgent, AgentResult
from wex_platform.agents.prompts.pricing import PRICING_SYSTEM_PROMPT, RATE_GUIDANCE_TEMPLATE

logger = logging.getLogger(__name__)


class PricingAgent(BaseAgent):
    """Provides rate guidance and market intelligence for warehouse spaces.

    The Pricing Agent analyses a warehouse's features, location, and
    market position to suggest competitive supplier rates. It is called
    by the route handler during Step 5 of the activation flow and can
    also be invoked independently for ad-hoc pricing queries.
    """

    def __init__(self):
        super().__init__(
            agent_name="pricing",
            model_name="gemini-3-flash-preview",
            temperature=0.3,  # Analytical, less creative
        )

    async def get_rate_guidance(
        self,
        warehouse_data: dict,
        contextual_memories: Optional[list[str]] = None,
    ) -> AgentResult:
        """Get rate guidance for a warehouse.

        Args:
            warehouse_data: Dict with warehouse and truth core fields.
                Expected keys include city, state, building_size_sqft,
                min_sqft, max_sqft, activity_tier, clear_height_ft,
                dock_doors_receiving, drive_in_bays, has_office_space,
                has_sprinkler, parking_spaces, power_supply.
            contextual_memories: List of memory content strings for
                additional market/feature context.

        Returns:
            AgentResult with pricing guidance data containing
            suggested_rate_low, suggested_rate_high, suggested_rate_mid,
            market_context, feature_adjustments, and revenue_projection.
        """
        memory_text = "\n".join(
            contextual_memories or ["No contextual memory available yet."]
        )

        prompt = RATE_GUIDANCE_TEMPLATE.format(
            city=warehouse_data.get("city", "Unknown"),
            state=warehouse_data.get("state", "Unknown"),
            building_size_sqft=warehouse_data.get("building_size_sqft", 0),
            min_sqft=warehouse_data.get("min_sqft", 0),
            max_sqft=warehouse_data.get("max_sqft", 0),
            activity_tier=warehouse_data.get("activity_tier", "storage_only"),
            clear_height_ft=warehouse_data.get("clear_height_ft", "N/A"),
            dock_doors=warehouse_data.get("dock_doors_receiving", 0),
            drive_in_bays=warehouse_data.get("drive_in_bays", 0),
            has_office=warehouse_data.get("has_office_space", False),
            has_sprinkler=warehouse_data.get("has_sprinkler", False),
            parking_spaces=warehouse_data.get("parking_spaces", 0),
            power_supply=warehouse_data.get("power_supply", "N/A"),
            contextual_memory=memory_text,
        )

        result = await self.generate_json(
            prompt=prompt,
            system_instruction=PRICING_SYSTEM_PROMPT,
        )

        return result

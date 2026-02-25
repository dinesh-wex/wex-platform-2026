"""Clearing Agent - Matches buyer needs against available warehouse supply."""

import json
import logging
from typing import Optional

from wex_platform.agents.base import BaseAgent, AgentResult
from wex_platform.agents.prompts.clearing import CLEARING_SYSTEM_PROMPT, CLEARING_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)

FEATURE_EVAL_SYSTEM_PROMPT = """You evaluate warehouse-buyer FEATURE alignment and generate match reasoning.

The composite match score has ALREADY been calculated deterministically. Your ONLY jobs:
1. Score FEATURE alignment (0-100) based on buyer's specific requirements vs warehouse specs
2. Write a 2-3 sentence buyer-facing "Why This Space" explanation
3. Determine instant_book_eligible (true/false)

DO NOT recalculate location, size, use_type, timing, or budget scores.

REASONING RULES (shown directly to the buyer):
- Write like a top commercial RE broker. Confident, specific, no fluff.
- ONLY reference features the buyer explicitly asked for
- Lead with the #1 match reason
- 2-3 SHORT sentences max. Use digits for numbers. Use "SF" not "sqft".
- Never mention: trust levels, scoring internals, system metadata
"""

FEATURE_EVAL_PROMPT = """Evaluate feature alignment for these warehouses against the buyer's requirements:

BUYER USE TYPE: {use_type}
BUYER REQUIREMENTS: {requirements}

WAREHOUSES ({warehouse_count} candidates):
{warehouse_details}

Score each warehouse's FEATURE alignment (0-100) and write buyer-facing reasoning."""


class ClearingAgent(BaseAgent):
    """Matches buyer needs against active warehouse supply.

    The clearing agent receives a structured buyer need and a list
    of candidate warehouses (pre-filtered by the clearing engine's
    deterministic pass).  It scores each warehouse across multiple
    dimensions -- location, size, use-type compatibility, feature
    alignment, and timing -- then returns the top ranked matches
    with explanations and instant-book eligibility flags.

    Temperature is set low (0.2) because scoring should be as
    deterministic and consistent as possible.
    """

    def __init__(self):
        super().__init__(
            agent_name="clearing",
            model_name="gemini-3-flash-preview",
            temperature=0.2,  # Deterministic matching
        )

    async def find_matches(
        self,
        buyer_need: dict,
        warehouses: list[dict],
    ) -> AgentResult:
        """Find and rank warehouse matches for a buyer need.

        Args:
            buyer_need: Dict with buyer need fields (city, state,
                min_sqft, max_sqft, use_type, needed_from,
                duration_months, max_budget_per_sqft, requirements).
            warehouses: List of warehouse dicts, each containing id,
                address, city, state, building_size_sqft, truth_core
                sub-dict, and memories list.

        Returns:
            AgentResult with data containing:
            - matches: Ranked list of match objects with scores
            - no_match_candidates: Warehouses that were considered
              but didn't meet minimum thresholds
        """
        # Format warehouse details for the prompt
        warehouse_details = []
        for i, wh in enumerate(warehouses, 1):
            tc = wh.get("truth_core", {})
            memories = wh.get("memories", [])
            memory_text = (
                "; ".join(m.get("content", "") for m in memories[:5])
                if memories
                else "No contextual memory"
            )

            detail = (
                f"Warehouse #{i}: {wh.get('address', 'Unknown')}\n"
                f"  City: {wh.get('city', '?')}, State: {wh.get('state', '?')}\n"
                f"  Building Size: {wh.get('building_size_sqft', 0):,} sqft\n"
                f"  Available: {tc.get('min_sqft', 0):,} - {tc.get('max_sqft', 0):,} sqft\n"
                f"  Activity Tier: {tc.get('activity_tier', '?')}\n"
                f"  Clear Height: {tc.get('clear_height_ft', '?')} ft\n"
                f"  Dock Doors: {tc.get('dock_doors_receiving', 0)} receiving, "
                f"{tc.get('drive_in_bays', 0)} drive-in\n"
                f"  Office Space: {tc.get('has_office_space', False)}\n"
                f"  Sprinkler: {tc.get('has_sprinkler', False)}\n"
                f"  Parking: {tc.get('parking_spaces', 0)} spaces\n"
                f"  Constraints: {json.dumps(tc.get('constraints', {}))}\n"
                f"  Trust Level: {tc.get('trust_level', 0)}\n"
                f"  Available From: {tc.get('available_from', 'Now')}\n"
                f"  Tour Readiness: {tc.get('tour_readiness', '48_hours')}\n"
                f"  ID: {wh.get('id', '?')}\n"
                f"  Contextual Memory: {memory_text}"
            )
            warehouse_details.append(detail)

        prompt = CLEARING_PROMPT_TEMPLATE.format(
            city=buyer_need.get("city", "Any"),
            state=buyer_need.get("state", "Any"),
            radius_miles=buyer_need.get("radius_miles", 25),
            min_sqft=buyer_need.get("min_sqft", 0),
            max_sqft=buyer_need.get("max_sqft", 999999),
            use_type=buyer_need.get("use_type", "general storage"),
            needed_from=buyer_need.get("needed_from", "ASAP"),
            duration_months=buyer_need.get("duration_months", 6),
            max_budget_per_sqft=buyer_need.get("max_budget_per_sqft", "flexible"),
            requirements=json.dumps(buyer_need.get("requirements", {})),
            warehouse_count=len(warehouses),
            warehouse_details="\n".join(warehouse_details),
        )

        result = await self.generate_json(
            prompt=prompt,
            system_instruction=CLEARING_SYSTEM_PROMPT,
        )

        return result

    async def evaluate_features(
        self,
        buyer_need: dict,
        warehouses: list[dict],
        deterministic_scores: dict[str, dict],
    ) -> AgentResult:
        """Layer 2: LLM evaluates feature alignment and generates reasoning.

        Only evaluates features (15% weight) and generates buyer-facing reasoning.
        All other scoring dimensions are computed deterministically in match_scorer.py.
        """
        from wex_platform.domain.schemas import FeatureEvalResponse

        FEATURE_EVAL_SCHEMA = FeatureEvalResponse.model_json_schema()

        # Build compact prompt with just what LLM needs
        warehouse_details = []
        for wh in warehouses:
            tc = wh.get("truth_core", {})
            wh_scores = deterministic_scores.get(wh["id"], {})
            detail = (
                f"Warehouse {wh['id']}:\n"
                f"  City: {wh.get('city', '?')}, State: {wh.get('state', '?')}\n"
                f"  Available: {tc.get('min_sqft', 0):,} - {tc.get('max_sqft', 0):,} sqft\n"
                f"  Activity Tier: {tc.get('activity_tier', '?')}\n"
                f"  Clear Height: {tc.get('clear_height_ft', '?')} ft\n"
                f"  Dock Doors: {tc.get('dock_doors_receiving', 0)} receiving, "
                f"{tc.get('dock_doors_shipping', 0)} shipping, {tc.get('drive_in_bays', 0)} drive-in\n"
                f"  Office: {tc.get('has_office_space', False)}, Sprinkler: {tc.get('has_sprinkler', False)}\n"
                f"  Parking: {tc.get('parking_spaces', 0)}, Power: {tc.get('power_supply', 'N/A')}\n"
                f"  Constraints: {json.dumps(tc.get('constraints', {}))}\n"
                f"  Pre-computed scores: location={wh_scores.get('location_score', '?')}, "
                f"size={wh_scores.get('size_score', '?')}, budget={wh_scores.get('budget_score', '?')}\n"
                f"  Distance: {wh_scores.get('distance_miles', '?')} miles"
            )
            warehouse_details.append(detail)

        prompt = FEATURE_EVAL_PROMPT.format(
            use_type=buyer_need.get("use_type", "general storage"),
            requirements=json.dumps(buyer_need.get("requirements", {})),
            warehouse_count=len(warehouses),
            warehouse_details="\n\n".join(warehouse_details),
        )

        result = await self.generate_json(
            prompt=prompt,
            system_instruction=FEATURE_EVAL_SYSTEM_PROMPT,
            response_schema=FEATURE_EVAL_SCHEMA,
        )

        if not result.ok:
            return result

        # Pydantic validation as defense-in-depth
        try:
            validated = FeatureEvalResponse.model_validate(result.data)
            return AgentResult.success(
                data=[m.model_dump() for m in validated.matches],
                tokens_used=result.tokens_used,
                latency_ms=result.latency_ms,
            )
        except Exception as exc:
            logger.warning("Pydantic validation failed: %s", exc)
            return AgentResult.failure(f"Validation error: {exc}")

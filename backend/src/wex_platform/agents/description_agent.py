"""Description Agent — generates human-readable warehouse descriptions via Gemini."""

import logging
from typing import Optional

from wex_platform.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

DESCRIPTION_SYSTEM_PROMPT = (
    "You are a creative copywriter for Warehouse Exchange (WEx). "
    "Write ENGAGING, HUMAN warehouse descriptions that feel like talking points.\n\n"
    "Style Guidelines:\n"
    "- Write like you're having an enthusiastic conversation about a great find\n"
    "- Use natural language, not corporate speak\n"
    "- Highlight what makes this space special with SPECIFIC details\n"
    "- Short paragraphs, optional bullet points for clarity\n"
    "- Keep it under 2000 characters\n"
    "- Phrases like 'What really stands out...', 'You'll love that...'\n"
    "- Avoid 'state-of-the-art', 'world-class' — be specific instead\n\n"
    "Structure:\n"
    "- Opening hook about what makes this place special\n"
    "- Key highlights conversationally\n"
    "- Practical details (storage, services, access)\n"
    "- Closing that invites action\n\n"
    "DO NOT:\n"
    "- Start with 'Welcome to...' or 'Introducing...'\n"
    "- Use excessive exclamation marks\n"
    "- Sound like a generic real estate listing\n"
    "- Be vague — always be specific about features\n"
    "- Include pricing, rates, or availability dates (volatile)\n\n"
    "OUTPUT: Return ONLY the description text. No JSON, no markdown formatting."
)


class DescriptionAgent(BaseAgent):
    """Generates human-readable warehouse descriptions via Gemini Flash."""

    def __init__(self):
        super().__init__(
            agent_name="description",
            model_name="gemini-3-flash-preview",
            temperature=0.8,
        )

    async def generate_description(
        self,
        address: str,
        city: str,
        state: str,
        building_size_sqft: Optional[int] = None,
        clear_height_ft: Optional[float] = None,
        dock_doors: Optional[int] = None,
        drive_in_bays: Optional[int] = None,
        parking_spaces: Optional[int] = None,
        has_office_space: Optional[bool] = None,
        has_sprinkler: Optional[bool] = None,
        power_supply: Optional[str] = None,
        activity_tier: Optional[str] = None,
        year_built: Optional[int] = None,
        construction_type: Optional[str] = None,
    ) -> AgentResult:
        """Generate a human-readable description for a warehouse.

        Args:
            address: Street address.
            city: City name.
            state: Two-letter state code.
            building_size_sqft: Total building square footage.
            clear_height_ft: Interior clear height in feet.
            dock_doors: Number of dock doors.
            drive_in_bays: Number of drive-in bays.
            parking_spaces: Number of parking spaces.
            has_office_space: Whether office space is included.
            has_sprinkler: Whether sprinkler system exists.
            power_supply: Power supply description.
            activity_tier: Warehouse activity type.
            year_built: Year the building was constructed.
            construction_type: Construction material/type.

        Returns:
            AgentResult with the description text in ``data``.
        """
        features = []
        if building_size_sqft:
            features.append(f"Building size: {building_size_sqft:,} sqft")
        if clear_height_ft:
            features.append(f"Clear height: {clear_height_ft} ft")
        if dock_doors and dock_doors > 0:
            features.append(f"Dock doors: {dock_doors}")
        if drive_in_bays and drive_in_bays > 0:
            features.append(f"Drive-in bays: {drive_in_bays}")
        if parking_spaces and parking_spaces > 0:
            features.append(f"Parking spaces: {parking_spaces}")
        if has_office_space:
            features.append("Includes office space")
        if has_sprinkler:
            features.append("Full sprinkler system")
        if power_supply:
            features.append(f"Power: {power_supply}")
        if activity_tier:
            features.append(f"Activity type: {activity_tier}")
        if year_built:
            features.append(f"Year built: {year_built}")
        if construction_type:
            features.append(f"Construction: {construction_type}")

        features_text = "\n".join(f"- {f}" for f in features) if features else "- Standard warehouse space"

        prompt = (
            f"Write an engaging, human-like description for this warehouse facility:\n\n"
            f"Location: {address}, {city}, {state}\n\n"
            f"Key Features:\n{features_text}\n\n"
            f"Write a compelling description that would make someone excited to tour this facility.\n"
            f"IMPORTANT: Do NOT include pricing, rates, availability dates, or current available space."
        )

        return await self.generate(
            prompt=prompt,
            system_instruction=DESCRIPTION_SYSTEM_PROMPT,
        )

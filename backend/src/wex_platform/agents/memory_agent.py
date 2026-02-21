"""Memory Agent - Contextual knowledge extraction and management."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from wex_platform.agents.base import BaseAgent, AgentResult
from wex_platform.agents.prompts.memory import MEMORY_EXTRACTION_PROMPT

logger = logging.getLogger(__name__)


class MemoryAgent(BaseAgent):
    """Extracts and manages contextual memory for warehouses.

    The Memory Agent processes raw data sources (building data,
    activation conversations, buyer feedback, deal outcomes) and
    distils them into structured memory entries that enrich future
    matching and pricing decisions.

    Each memory entry contains a type, free-text content, a confidence
    score, and a source tag so the system can trace provenance.
    """

    def __init__(self):
        super().__init__(
            agent_name="memory",
            model_name="gemini-3-flash-preview",
            temperature=0.3,  # Precise extraction
        )

    async def extract_memories(
        self,
        source_data: str,
        context: str = "",
        source_type: str = "building_data",
    ) -> AgentResult:
        """Extract contextual memory entries from source data.

        Args:
            source_data: The text to extract memories from.
            context: Additional context about the warehouse.
            source_type: Source identifier for the memory records
                (e.g. ``building_data``, ``activation_chat``).

        Returns:
            AgentResult with list of memory dicts, each containing
            memory_type, content, confidence, and source.
        """
        prompt = MEMORY_EXTRACTION_PROMPT.format(
            source_data=source_data,
            context=context,
        )

        result = await self.generate_json(
            prompt=prompt,
        )

        if result.ok and isinstance(result.data, list):
            # Add source to each memory
            for mem in result.data:
                mem["source"] = source_type

        return result

    async def extract_from_conversation(
        self,
        conversation: list[dict],
        warehouse_id: str,
    ) -> AgentResult:
        """Extract memories from an activation conversation.

        Flattens the conversation into text and runs the extraction
        prompt to identify owner preferences, feature intelligence,
        and other contextual facts.

        Args:
            conversation: List of {role, content} message dicts.
            warehouse_id: The warehouse ID for context.

        Returns:
            AgentResult with list of memory dicts.
        """
        conv_text = "\n".join(
            f"{msg['role']}: {msg['content']}" for msg in conversation
        )

        return await self.extract_memories(
            source_data=conv_text,
            context=f"Activation conversation for warehouse {warehouse_id}",
            source_type="activation_chat",
        )

    async def extract_from_building_data(
        self,
        building_data: dict,
        warehouse_id: str,
    ) -> AgentResult:
        """Extract memories from raw building/property data.

        Args:
            building_data: Dict of building attributes (address,
                features, specs, etc.).
            warehouse_id: The warehouse ID for context.

        Returns:
            AgentResult with list of memory dicts.
        """
        return await self.extract_memories(
            source_data=json.dumps(building_data, indent=2),
            context=f"Building data for warehouse {warehouse_id}",
            source_type="building_data",
        )

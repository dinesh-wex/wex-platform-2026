"""NLP extraction from freeform buyer input using Gemini."""

import json
import logging
from wex_platform.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

INTAKE_EXTRACTION_PROMPT = """Extract structured warehouse search fields from this buyer input.
Return JSON with these fields (use null for anything NOT explicitly stated):
{
  "location": "string - city, zip, neighborhood, or address mentioned",
  "size_sqft": "integer or null",
  "use_type": "one of: storage_only, storage_office, storage_light_assembly, cold_storage, distribution, ecommerce_fulfillment, manufacturing_light, or null",
  "timing": "string - when they need it, or null",
  "budget_per_sqft": "float or null",
  "budget_monthly": "float or null",
  "duration_months": "integer or null",
  "requirements": ["list of specific requirements like dock doors, clear height, etc"],
  "goods_type": "string or null"
}

Rules:
- Only extract what is EXPLICITLY stated. Never infer or assume.
- For size: "10k" = 10000, "5,000" = 5000, "20K sqft" = 20000
- For budget: "$1.10/sqft" → budget_per_sqft=1.10, "$5000/month" → budget_monthly=5000
- For use type: map common terms: "cold storage" → cold_storage, "e-commerce" → ecommerce_fulfillment, "warehouse" → storage_only, "office" → storage_office, "assembly" → storage_light_assembly
- For timing: preserve the user's words ("March", "Q2", "immediately", "30 days")
- For requirements: extract specific features like "dock doors", "28ft clear height", "sprinkler", "climate controlled"

Buyer input: "{text}"
"""


class IntakeExtractor(BaseAgent):
    """Extracts structured search fields from freeform buyer text."""

    def __init__(self):
        super().__init__(
            agent_name="intake_extractor",
            model_name="gemini-3-flash-preview",
            temperature=0.1,
        )

    async def extract(self, text: str) -> AgentResult:
        """Parse freeform text into structured BuyerNeed fields."""
        if not text or not text.strip():
            return AgentResult.success(data={})

        prompt = INTAKE_EXTRACTION_PROMPT.replace("{text}", text)
        result = await self.generate_json(prompt=prompt)

        if not result.ok:
            logger.warning("Intake extraction failed: %s", result.error)
            return AgentResult.success(data={})  # Graceful: empty = step-by-step

        # Clean nulls
        data = result.data if isinstance(result.data, dict) else {}
        cleaned = {k: v for k, v in data.items() if v is not None}
        return AgentResult.success(
            data=cleaned,
            tokens_used=result.tokens_used,
            latency_ms=result.latency_ms,
        )

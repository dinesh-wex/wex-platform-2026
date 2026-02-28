"""Criteria Agent — LLM-based intent classification and action planning."""

import json
import logging
from wex_platform.agents.base import BaseAgent
from .contracts import CriteriaPlan, MessageInterpretation

logger = logging.getLogger(__name__)


class CriteriaAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_name="sms_criteria", model_name="gemini-3-flash-preview", temperature=0.2)

    async def plan(
        self,
        message: str,
        interpretation: MessageInterpretation,
        conversation_history: list[dict] | None = None,
        phase: str = "INTAKE",
        existing_criteria: dict | None = None,
        resolved_property_id: str | None = None,
        presented_match_summaries: list[dict] | None = None,
    ) -> CriteriaPlan:
        """Classify intent and plan next action."""
        history_ctx = ""
        if conversation_history:
            recent = conversation_history[-8:]
            lines = [f"  {m.get('role','?')}: {m.get('content','')[:200]}" for m in recent]
            history_ctx = "\nConversation history:\n" + "\n".join(lines)

        interp_ctx = json.dumps({
            "cities": interpretation.cities,
            "states": interpretation.states,
            "sqft": interpretation.sqft,
            "topics": interpretation.topics,
            "features": interpretation.features,
            "positional_references": interpretation.positional_references,
            "action_keywords": interpretation.action_keywords,
            "emails": interpretation.emails,
            "names": interpretation.names,
        })

        existing_ctx = f"\nExisting criteria: {json.dumps(existing_criteria)}" if existing_criteria else ""
        property_ctx = f"\nResolved property ID: {resolved_property_id}" if resolved_property_id else ""
        matches_ctx = ""
        if presented_match_summaries:
            match_lines = [f"  Option {i+1}: {m.get('city','?')}, {m.get('sqft','?')} sqft, ${m.get('rate','?')}/sqft" for i, m in enumerate(presented_match_summaries)]
            matches_ctx = "\nPresented matches:\n" + "\n".join(match_lines)

        prompt = (
            f"You are the Search Architect for Warehouse Exchange.\n"
            f"Your job: convert the customer's message into a structured search plan.\n"
            f"You NEVER run the search; you ONLY return JSON describing what to search for and what action to take.\n\n"
            f"## CRITICAL OUTPUT RULES\n"
            f"1. Return ONLY valid JSON — no explanation text before or after\n"
            f"2. Do NOT wrap in markdown code fences\n"
            f"3. If unsure, still return valid JSON with intent: \"unknown\"\n\n"
            f"Current phase: {phase}\n"
            f"Buyer message: \"{message}\"\n"
            f"Interpreted data: {interp_ctx}\n"
            f"{history_ctx}{existing_ctx}{property_ctx}{matches_ctx}\n\n"
            f"## INTENT CLASSIFICATION\n"
            f"- \"new_search\" — looking for warehouse space (new inquiry)\n"
            f"- \"refine_search\" — adjusting previous search criteria\n"
            f"- \"facility_info\" — asking about a specific facility detail\n"
            f"- \"tour_request\" — wants to see/tour a facility (\"I want to see it\", \"can I tour\", \"can I come by\")\n"
            f"- \"commitment\" — wants to book/commit (\"I want that one\", \"book it\", \"let's go with this one\")\n"
            f"- \"provide_info\" — providing name/email during collection phase\n"
            f"- \"greeting\" — just saying hi or thanks\n"
            f"- \"unknown\" — can't determine intent\n\n"
            f"## ACTION DECISION\n"
            f"- \"search\" — search for facilities by criteria (location/sqft/use_type given)\n"
            f"- \"lookup\" — look up specific facility details\n"
            f"- \"schedule_tour\" — proceed with tour booking\n"
            f"- \"commitment_handoff\" — proceed with commitment flow\n"
            f"- \"collect_info\" — buyer is providing name/email\n"
            f"- null — just respond (greeting, thanks)\n\n"
            f"## MATCHING USER REFERENCES\n"
            f"Users reference facilities by any attribute shown: by name, city, price (\"the cheaper one\"), "
            f"size (\"the bigger one\"), or position (\"option 2\"). "
            f"When a user references a KNOWN facility and expresses tour interest, set intent: \"tour_request\".\n\n"
            f"## NAME EXTRACTION\n"
            f"If the user provides their name anywhere in the message, extract it:\n"
            f"- 'Hi, I'm Peter DeSantis' → extracted_name: {{ \"first_name\": \"Peter\", \"last_name\": \"DeSantis\" }}\n"
            f"- 'Thanks, John' → extracted_name: {{ \"first_name\": \"John\", \"last_name\": null }}\n"
            f"- 'My name is Sarah' → extracted_name: {{ \"first_name\": \"Sarah\", \"last_name\": null }}\n"
            f"- No name mentioned → extracted_name: null\n\n"
            f"## REQUIRED JSON SCHEMA\n"
            f'{{"intent": "...", "action": "...", "criteria": {{"location": ..., "sqft": ..., '
            f'"use_type": ..., "timing": ..., "duration": ..., "goods_type": ..., "features": [...]}}, '
            f'"extracted_name": {{"first_name": "...", "last_name": "..."}} or null, '
            f'"response_hint": "...", "confidence": 0.0-1.0}}\n\n'
            f"## CRITERIA FIELDS\n"
            f"- location: city/area name\n"
            f"- sqft: number (parse \"10k\" as 10000, \"2000\" as 2000)\n"
            f"- use_type: storage, fulfillment, distribution, light_assembly, cold_storage, manufacturing\n"
            f"- timing: when they need it (ASAP, next_month, 3_months, 6_months, flexible)\n"
            f"- duration: how long they need the space (month_to_month, 3_months, 6_months, 1_year, 2_years, flexible)\n"
            f"- goods_type: what they'll store (general, food_grade, hazmat, electronics, apparel, raw_materials)\n"
            f"- features: special requirements like dock_doors, cold_storage, office_space\n\n"
            f"Rules:\n"
            f"- Merge new criteria with existing — new values override\n"
            f"- To trigger action: \"search\", need AT LEAST location + sqft + use_type\n"
            f"- If missing any of those three, action: null. Ask for missing ones naturally in ONE message\n"
            f"- Good combined asks: \"How much space and what will you use it for?\" or \"What city? And roughly how many sqft?\"\n"
            f"- After getting location, ask for size AND use_type together if both missing\n"
            f"- Do NOT infer or default ANY field — only set fields the buyer explicitly mentions\n"
            f"- If buyer says just a city, set ONLY location. Do NOT guess sqft or use_type.\n"
            f"- If buyer says just sqft, set ONLY sqft. Do NOT guess location or use_type.\n"
        )

        result = await self.generate_json(prompt=prompt)

        if not result.ok:
            logger.warning("Criteria agent failed: %s", result.error)
            return CriteriaPlan(intent="unknown", confidence=0.0)

        data = result.data if isinstance(result.data, dict) else {}
        return CriteriaPlan(
            intent=data.get("intent", "unknown"),
            action=data.get("action"),
            criteria=data.get("criteria") or {},
            resolved_property_id=resolved_property_id,
            response_hint=data.get("response_hint"),
            confidence=data.get("confidence", 0.0),
            extracted_name=data.get("extracted_name"),
        )

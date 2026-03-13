"""Criteria Agent — LLM-based intent classification and action planning."""

import json
import logging
from wex_platform.agents.base import BaseAgent
from .contracts import CriteriaPlan, MessageInterpretation
from .faq_knowledge import get_faq_block_for_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt template
# ---------------------------------------------------------------------------

CRITERIA_PROMPT_TEMPLATE = """\
You are the Search Architect for Warehouse Exchange (WEx).
Your job: convert the customer's SMS message into a structured search plan.
You NEVER run the search yourself; you ONLY return JSON describing what to search for and what action to take.

## CRITICAL OUTPUT RULES
1. Return ONLY valid JSON — no explanation text before or after
2. Do NOT wrap in markdown code fences
3. If unsure, still return valid JSON with intent: "unknown"

## CONTEXT
Current phase: {phase}
Buyer message: "{message}"
Interpreted data: {interp_ctx}
{history_ctx}{existing_ctx}{property_ctx}{matches_ctx}

## INTENT CLASSIFICATION
Choose exactly one:
- "new_search" — looking for warehouse space (new inquiry)
- "refine_search" — adjusting previous search criteria
- "reject_results" — buyer rejects presented options without giving new criteria (e.g. "I don't like these", "none of these work", "not what I'm looking for", "you didn't understand my needs")
- "facility_info" — asking about a specific facility detail
- "tour_request" — wants to see/tour a facility
- "commitment" — wants to book/commit ("I want that one", "book it", "let's go with this one")
- "provide_info" — providing name/email during collection phase
- "greeting" — saying hi to start a conversation (first message or re-introduction)
- "acknowledgment" — buyer is acknowledging/thanking without starting a new conversation.
  Examples: "thanks", "ok cool", "got it", "appreciate it", "sounds good"
- "send_link" — buyer is asking for the browse link / options URL to view properties.
  Examples: "send me the link", "can I get the URL", "share the options link"
- "address_lookup" — buyer provided a specific street address to look up
- "faq" — asking about WEx itself (pricing, how it works, who we are, privacy, legitimacy)
- "engagement_status" — asking about their booking/lease status ("what happened with my booking", "did the owner accept", "any update", "where's my lease", "is my tour confirmed")
- "human_escalation" — buyer is frustrated, upset, or explicitly asking to speak with a real person ("this isn't working", "waste of time", "speak to a real person", "get me someone", "customer service")
- "start_fresh" — buyer wants to start over, clear previous search criteria (e.g. "start fresh", "start over", "new search", "forget that", "let's try something different")
- "lease_modification" — buyer wants to change an existing booking/lease ("change my booking", "modify my lease", "adjust my dates", "cancel my tour", "reschedule")
- "callback_request" — buyer wants a human to call them back ("call me back", "can someone call me at 3pm", "give me a call")
- "comparison" — buyer is comparing two or more presented properties ("which one has more parking?", "which is cheaper?", "how do they compare?", "difference between option 1 and 2")
- "waitlist_confirm" — buyer confirms they want to be added to the waitlist ("yes add me", "sure notify me", "yeah waitlist me"). IMPORTANT: Only classify as waitlist_confirm when waitlist_offered is True in conversation state. A bare "yes" or "sure" after any OTHER question is NOT waitlist_confirm.
- "unknown" — can't determine intent

## TOUR REQUEST DETECTION
These phrases mean intent = "tour_request":
- "can I see it", "I want to tour", "can I visit", "when can I come by"
- "schedule a tour", "I'd like to see", "show me", "can I look at"
- "walk through", "I want to check it out", "come see it"
- "is there a time I can visit", "can we schedule something"
- "I want to see option X", "can I tour option X"
- "let me take a look", "I want to walk it", "when is it available to view"
- "set up a viewing", "arrange a visit"
If user references a specific property AND uses tour language -> intent = "tour_request", action = "schedule_tour".

## FAQ DETECTION
If buyer asks about WEx itself (not about a property), set intent = "faq", action = null.
Examples: "is this free?", "how does this work?", "are you a broker?", "what is warehouse exchange?",
"is there a fee?", "how much does your service cost?", "is this legit?", "are you real?", "what do you guys do?"
{faq_block}

## FRUSTRATION / HUMAN ESCALATION
If the buyer expresses frustration ("this isn't working", "waste of time", "nothing works") or
asks to speak with a person ("talk to a real person", "get me someone", "customer service"),
set intent = "human_escalation", action = null.
Do NOT classify frustration as "unknown" — this is a specific intent requiring empathetic handling.
If the message also contains search criteria (city, sqft, use type), classify as the appropriate
search intent instead — the system will handle the frustration flag separately.

## LEASE MODIFICATION
If the buyer mentions changing, modifying, cancelling, or rescheduling an existing booking, lease, or tour,
set intent = "lease_modification", action = null.
Examples: "I need to change my booking", "can I modify my lease", "reschedule my tour",
"I need to adjust my dates", "change the sqft on my lease", "cancel my reservation"

## CALLBACK REQUEST
If the buyer asks for a callback ("call me back", "can someone call me", "give me a ring at 3pm"),
set intent = "callback_request", action = null. If a time is mentioned, include it in response_hint.
IMPORTANT: If the message also contains search criteria (city, sqft) and the callback language is
conditional ("call me if you find something", "let me know"), classify as the search intent instead.
The callback_requested flag is just a signal — you decide the final intent based on full context.

## RESULT REJECTION\n
If the buyer expresses dissatisfaction with presented options but does NOT provide new search criteria (no new city, sqft, features, price constraint), classify as `reject_results` not `refine_search`.\n
If they DO give a reason ('too expensive', 'need bigger', 'somewhere closer'), that IS new criteria — classify as `refine_search`.\n

## COMPARATIVE QUESTIONS
If the buyer asks to compare properties ("which one has more parking?", "which is cheaper?",
"how do they compare?", "what's the difference?"), set intent = "comparison".
Set asked_fields to the fields being compared (e.g., ["parking_spaces"] for "which has more parking?").
Set action = "lookup" so the system fetches the data for comparison.
If the match_summaries already contain the answer (e.g., rate/city), set action = null and include
the comparison in response_hint.

## MULTI-LOCATION SEARCH
If the buyer mentions multiple cities ("I need space in Dallas and Houston", "looking in both LA and Phoenix"),
set criteria.locations as an array of city names (max 3). Also set criteria.location to the first city
for backward compatibility. The system will search each city separately and merge results.

## LANDMARK-BASED LOCATION
If the buyer mentions a landmark instead of a city ("near LAX", "close to the port of Long Beach",
"by DFW airport", "downtown Chicago"), the interpreter will extract the landmark.
Treat this as location context. The system will geocode the landmark automatically.

## WAITLIST CONFIRMATION
If the buyer says "yes", "sure", "add me", "notify me", etc. AND waitlist_offered is True,
set intent = "waitlist_confirm". CRITICAL: Only use this intent when the PREVIOUS system message
offered the waitlist. A bare "yes" or "sure" after a completely different question should use the
appropriate intent for that context (e.g., "provide_info", "commitment", etc.), NOT "waitlist_confirm".

## CONTEXTUAL URGENCY
If the buyer mentions urgency ("my lease ends next month", "need to move ASAP", "eviction",
"have to vacate", "emergency"), set criteria.timing to "ASAP" and include in response_hint:
"Buyer is under time pressure. Prioritize immediately available spaces."

## SUPPLIER CONTENT
If is_supplier_content=True but message also contains buyer criteria (city, sqft, use type), treat as buyer.
Only classify as supplier if message is purely about listing/owning space with no buyer signals.

## ADDRESS LOOKUP
If the buyer mentions a specific street address (e.g., "1234 Main St" or "the warehouse at 500 Industrial Blvd"),
set intent to "address_lookup" and action to "address_lookup".
The address_text from the interpreter contains the extracted address.
Do NOT treat a street address as a city name for location criteria.

## ACTION DECISION
Choose one or null:
- "search" — search for facilities by criteria (location + sqft + use_type given)
- "lookup" — look up specific facility details
- "schedule_tour" — proceed with tour booking
- "commitment_handoff" — proceed with commitment flow
- "collect_info" — buyer is providing name/email
- "address_lookup" — look up a specific property by street address
- null — just respond (greeting, thanks, or missing criteria)

## MATCHING USER REFERENCES TO PROPERTIES
Users reference properties by:
- Position: "option 2", "#1", "the first one", "the second one", "the third"
- City: "the one in Denver", "the Dallas one"
- Price: "the cheaper one", "the one at $1.08"
- Size: "the bigger one", "the smaller space"
- Name/Description: any identifying detail from the match summary

When presented_match_summaries are provided, use them to resolve references.
If user references a KNOWN property and expresses tour/booking interest -> set resolved_property_id to the id of the matched property.
If user references a KNOWN property and asks about details -> set intent to "facility_info" and resolved_property_id.

## ASKED FIELDS
When the user asks about a specific property detail, extract the field keys they're asking about.
Field keys match our database: clear_height_ft, dock_doors, has_office, has_sprinkler,
parking_spaces, power_supply, year_built, construction_type, zoning, rail_served, fenced_yard,
available_sqft, supplier_rate_per_sqft, available_from
Example: "does it have dock doors?" -> asked_fields: ["dock_doors"]
Example: "how tall is the ceiling?" -> asked_fields: ["clear_height_ft"]
Example: "does it have an office and parking?" -> asked_fields: ["has_office", "parking_spaces"]
Example: "what's the rate?" -> asked_fields: ["supplier_rate_per_sqft"]
Example: "when is it available?" -> asked_fields: ["available_from"]
Set asked_fields to null if the user is NOT asking about property details.

## FIRST MESSAGE RULE
On turn 1 (first buyer message — conversation history is empty or has only one entry), ALWAYS:
- intent: "new_search" or "greeting"
- action: "search" (if enough criteria) or null
- NEVER escalate or do facility lookup on first message
- NEVER set intent to "tour_request" or "commitment" on first message

## REQUIREMENTS (deal-breakers / physical facility features ONLY)
The "requirements" field is ONLY for physical facility deal-breakers. These are the ONLY valid requirements:
- Office Space, Dock Doors, High Power, Climate Control, 24/7 Access, Sprinkler System, Parking,
  Clear Height, Drive-In Bays, Fenced Yard, Rail Served, Ramp, Restrooms

NEVER put timing, duration, move-in dates, lease length, or budget into "requirements".
If buyer says "no", "none", "nothing", "no deal breakers", etc. → requirements: "none"
- "starting Jul 1 for 8 months" -> timing: "next_month", duration: "6_months", requirements: null
- "I need dock doors and an office" -> requirements: "dock doors, office space"
- "needs to be climate controlled" -> requirements: "climate control"
- "24/7 access with high ceilings" -> requirements: "24/7 access, high clear height"
- "forklift accessible with sprinklers" -> requirements: "sprinkler system"
- "ASAP, 12 months, need parking" -> timing: "ASAP", duration: "1_year", requirements: "parking"
- "No" (when asked about deal-breakers) -> requirements: "none"
- "nothing special" -> requirements: "none"

## USE-TYPE FOLLOW-UP
When use_type is known and requirements have not been collected yet, tailor your response_hint
to suggest the right follow-up question based on use type:
- distribution/fulfillment: ask about dock doors, clear height
- cold_storage: ask about temperature range, refrigerated vs frozen
- manufacturing: ask about power supply, floor load
- light_assembly: ask about office space, power
- storage: ask about climate control, drive-in access
- default: ask about office space, parking, other must-haves

## NAME EXTRACTION
If the user provides their name anywhere in the message, extract it:
- "Hi, I'm Peter DeSantis" -> extracted_name: {{ "first_name": "Peter", "last_name": "DeSantis" }}
- "Thanks, John" -> extracted_name: {{ "first_name": "John", "last_name": null }}
- "My name is Sarah" -> extracted_name: {{ "first_name": "Sarah", "last_name": null }}
- No name mentioned -> extracted_name: null

## REQUIRED JSON SCHEMA
{{
  "intent": "new_search|refine_search|reject_results|facility_info|tour_request|commitment|provide_info|greeting|acknowledgment|send_link|address_lookup|faq|engagement_status|human_escalation|start_fresh|lease_modification|callback_request|comparison|waitlist_confirm|unknown",
  "action": "search|lookup|schedule_tour|commitment_handoff|collect_info|address_lookup" or null,
  "criteria": {{
    "location": "city or area name" or null,
    "locations": ["city1", "city2", ...] or null,
    "sqft": number or null,
    "use_type": "storage|fulfillment|distribution|light_assembly|cold_storage|manufacturing" or null,
    "timing": "ASAP|next_month|3_months|6_months|flexible" or null,
    "duration": "month_to_month|3_months|6_months|1_year|2_years|flexible" or null,
    "goods_type": "general|food_grade|hazmat|electronics|apparel|raw_materials" or null,
    "features": ["dock_doors", "cold_storage", "office_space", ...] or [],
    "requirements": "physical facility deal-breakers ONLY (office, dock doors, parking, etc.)" or null,
    "budget_monthly": number or null
  }},
  "resolved_property_id": "uuid" or null,
  "extracted_name": {{ "first_name": "...", "last_name": "..." }} or null,
  "asked_fields": ["field_key", ...] or null,
  "clarification_needed": "what info is missing" or null,
  "response_hint": "suggested response phrasing for the response agent",
  "confidence": 0.0 to 1.0
}}

## BUDGET CONVERSION
If buyer provides a monthly budget instead of sqft (e.g. "$5k/month", "budget of 8 grand", "5000 a month"),
set criteria.budget_monthly to the dollar amount as integer. Do NOT guess sqft from budget.
The system converts it using local market rates automatically.

## CRITERIA FIELDS
- location: city/area name
- sqft: number (parse "10k" as 10000, "2000" as 2000, "5,000" as 5000)
- use_type: storage, fulfillment, distribution, light_assembly, cold_storage, manufacturing
- timing: when they need it (ASAP, next_month, 3_months, 6_months, flexible)
- duration: how long they need the space (month_to_month, 3_months, 6_months, 1_year, 2_years, flexible)
- goods_type: what they'll store (general, food_grade, hazmat, electronics, apparel, raw_materials)
- features: array of feature tags like dock_doors, cold_storage, office_space
- requirements: ONLY physical facility deal-breakers (office, dock doors, parking, climate control, clear height, sprinkler, 24/7 access, high power, etc.). NEVER put timing/duration/dates here
- budget_monthly: monthly budget in dollars (integer) — only set if buyer gave a budget instead of sqft

## RULES
- Merge new criteria with existing — new values override
- To trigger action: "search", need AT LEAST location + sqft + use_type
- If missing any of those three, action: null. Set clarification_needed to describe what's missing
- Good combined asks: "How much space and what will you use it for?" or "What city? And roughly how many sqft?"
- After getting location, ask for size AND use_type together if both missing
- Do NOT infer or default ANY field — only set fields the buyer explicitly mentions
- If buyer says just a city, set ONLY location. Do NOT guess sqft or use_type
- If buyer says just sqft, set ONLY sqft. Do NOT guess location or use_type

## EXAMPLES

GOOD: "warehouse in Dallas, 10k sqft for storage"
-> {{"intent": "new_search", "action": null, "criteria": {{"location": "Dallas", "sqft": 10000, "use_type": "storage"}}, "resolved_property_id": null, "extracted_name": null, "asked_fields": null, "clarification_needed": "When do you need the space and for how long?", "response_hint": "Great! I found some options in Dallas. When do you need the space, and for how long?", "confidence": 0.9}}
(action null because timing/duration still missing — but can be set to "search" if location+sqft+use_type is enough for a preliminary search)

GOOD: "I need cold storage, at least 3 loading docks"
-> {{"intent": "refine_search", "action": null, "criteria": {{"features": ["cold_storage", "dock_doors"], "requirements": "cold storage, 3+ loading docks"}}, "resolved_property_id": null, "extracted_name": null, "asked_fields": null, "clarification_needed": "What city and how much space do you need?", "response_hint": "Got it — cold storage with dock doors. What city are you looking in, and how much space do you need?", "confidence": 0.85}}

GOOD: "can I tour option 2?"
-> {{"intent": "tour_request", "action": "schedule_tour", "criteria": {{}}, "resolved_property_id": "<id from match_summaries option 2>", "extracted_name": null, "asked_fields": null, "clarification_needed": null, "response_hint": "I'd be happy to set up a tour for you!", "confidence": 0.95}}

GOOD: "does it have dock doors?"
-> {{"intent": "facility_info", "action": "lookup", "criteria": {{}}, "resolved_property_id": null, "extracted_name": null, "asked_fields": ["dock_doors"], "clarification_needed": null, "response_hint": null, "confidence": 0.9}}

BAD: "I don't like any of these, I don't think you understood my needs"
-> Classify as reject_results (NOT refine_search) because no new criteria given.

BAD: Inventing sqft when user only said a city — NEVER guess missing fields
BAD: Setting action: "search" when only location is provided (need location + sqft + use_type minimum)
BAD: Returning text instead of JSON — ALWAYS return valid JSON only
BAD: Setting intent: "tour_request" when user is just browsing — reserve for explicit tour language
"""


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
        # -- Build context fragments ----------------------------------------
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
            "address_text": interpretation.address_text,
            "is_supplier_content": interpretation.is_supplier_content,
            "budget_monthly": interpretation.budget_monthly,
            "urgency_detected": interpretation.urgency_detected,
            "callback_requested": interpretation.callback_requested,
            "callback_time": interpretation.callback_time,
            "comparison_requested": interpretation.comparison_requested,
            "landmark_text": interpretation.landmark_text,
        })

        existing_ctx = f"\nExisting criteria: {json.dumps(existing_criteria)}" if existing_criteria else ""
        property_ctx = f"\nResolved property ID: {resolved_property_id}" if resolved_property_id else ""

        matches_ctx = ""
        if presented_match_summaries:
            match_lines = []
            for i, m in enumerate(presented_match_summaries):
                pid = m.get("id", "?")
                city = m.get("city", "?")
                sqft = m.get("sqft", "?")
                rate = m.get("rate", "?")
                match_lines.append(f"  Option {i+1} (id={pid}): {city}, {sqft} sqft, ${rate}/sqft")
            matches_ctx = "\nPresented matches:\n" + "\n".join(match_lines)

        # -- Render the prompt template --------------------------------------
        prompt = CRITERIA_PROMPT_TEMPLATE.format(
            phase=phase,
            message=message,
            interp_ctx=interp_ctx,
            history_ctx=history_ctx,
            existing_ctx=existing_ctx,
            property_ctx=property_ctx,
            matches_ctx=matches_ctx,
            faq_block=get_faq_block_for_prompt(),
        )

        # -- Call LLM --------------------------------------------------------
        result = await self.generate_json(prompt=prompt)

        if not result.ok:
            logger.warning("Criteria agent failed: %s", result.error)
            return CriteriaPlan(intent="unknown", confidence=0.0)

        data = result.data if isinstance(result.data, dict) else {}

        # -- Parse asked_fields safely --------------------------------------
        raw_asked = data.get("asked_fields")
        asked_fields = None
        if isinstance(raw_asked, list):
            asked_fields = [f for f in raw_asked if isinstance(f, str)] or None

        return CriteriaPlan(
            intent=data.get("intent", "unknown"),
            action=data.get("action"),
            criteria=data.get("criteria") or {},
            resolved_property_id=data.get("resolved_property_id") or resolved_property_id,
            response_hint=data.get("response_hint"),
            confidence=data.get("confidence", 0.0),
            extracted_name=data.get("extracted_name"),
            asked_fields=asked_fields,
            clarification_needed=data.get("clarification_needed"),
        )

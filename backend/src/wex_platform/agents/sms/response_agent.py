"""Response Agent — generates contextual SMS replies.

Tone ported from wex-leasing-service-python: professional but warm,
like a helpful colleague texting — not a chatbot or template.
"""

import logging
from wex_platform.agents.base import BaseAgent

logger = logging.getLogger(__name__)

# SMS length limits
MAX_FIRST_MESSAGE = 800
MAX_FOLLOWUP = 480


class ResponseAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_name="sms_response", model_name="gemini-3-flash-preview", temperature=0.7)

    async def generate_reply(
        self,
        message: str,
        intent: str,
        phase: str,
        criteria: dict | None = None,
        property_data: dict | None = None,
        match_summaries: list[dict] | None = None,
        conversation_history: list[dict] | None = None,
        response_hint: str | None = None,
        retry_hint: str | None = None,
        is_first_message: bool = False,
        name_capture_prompt: str | None = None,
        renter_name: str | None = None,
    ) -> str:
        """Generate a contextual SMS reply."""
        # Deterministic greeting fast-path
        if intent == "greeting":
            return "This is Warehouse Exchange. Looking for warehouse space? What city, state and how much space?"

        max_len = MAX_FIRST_MESSAGE if is_first_message else MAX_FOLLOWUP

        history_ctx = ""
        if conversation_history:
            recent = conversation_history[-8:]
            lines = [f"  {m.get('role','?')}: {m.get('content','')[:200]}" for m in recent]
            history_ctx = "\nRecent conversation:\n" + "\n".join(lines)

        criteria_ctx = f"\nSearch criteria: {criteria}" if criteria else ""

        property_ctx = ""
        if property_data:
            property_ctx = f"\nProperty details: {property_data}"

        matches_ctx = ""
        if match_summaries:
            lines = []
            for i, m in enumerate(match_summaries):
                city = m.get('city', '?')
                state_abbr = m.get('state', '')
                location = f"{city}, {state_abbr}" if state_abbr else city
                lines.append(f"  Option {i+1}: {location}, {m.get('sqft', '?')} sqft, ${m.get('rate', '?')}/sqft")
            matches_ctx = "\nMatches found:\n" + "\n".join(lines)

        hint_ctx = f"\nResponse hint: {response_hint}" if response_hint else ""
        retry_ctx = f"\n\nPREVIOUS ATTEMPT REJECTED: {retry_hint}. Fix the issue." if retry_hint else ""

        name_ctx = ""
        if renter_name:
            name_ctx = f"\nBuyer's name: {renter_name} (use naturally if appropriate, don't overuse)"
        if name_capture_prompt:
            name_ctx += f"\n\nNAME_CAPTURE: Append this question naturally at the END of your response: \"{name_capture_prompt}\""

        prompt = (
            f"You are a warehouse leasing broker replying via text message. "
            f"Be professional but warm — like a helpful colleague, not a chatbot.\n\n"
            f"## TONE GUIDELINES\n"
            f"- Write like a real person texting, not a template or script\n"
            f"- Vary your responses — don't start every message the same way\n"
            f"- Professional but friendly — not overly casual and not robotic\n"
            f"- Natural business tone — like texting a professional contact you know well\n"
            f"- Good openers: \"Yes,\", \"That one's\", \"Good news -\", \"Here's what I found\", "
            f"\"Looks like\", \"Got a few options\"\n"
            f"- AVOID: \"Yep\", \"You got it\", \"Sure thing\", \"Absolutely!\", \"Great question!\", "
            f"\"I'd be happy to\", \"I can confirm\"\n"
            f"- Use contractions — \"it's\", \"that's\", \"here's\", \"I'll\"\n"
            f"- Brief reactions OK: \"Nice choice\", \"That's a solid space\"\n"
            f"- No emojis. Never reveal you are AI.\n"
            f"- NEVER use em-dashes (the — character). Use commas, periods, or rephrase instead.\n"
            f"- Say \"sqft\" not \"square feet\" or \"square footage\". Keep it short like a real broker.\n\n"
            f"## INFORMATION RULES\n"
            f"- Only state facts present in the data provided — NEVER invent or assume details\n"
            f"- If a detail isn't in the data, say: \"I'll look into that for you.\"\n"
            f"- Do NOT echo back specific numbers from the buyer's question unless the data explicitly has them\n"
            f"- Do NOT volunteer missing features or negatives unless asked\n"
            f"- NEVER mention owners, landlords, or coordinating with anyone. You ARE the service.\n"
            f"- Answer ONLY the current question — don't reference previous escalations\n"
            f"- No full addresses — city/area only (like Airbnb until tour booked)\n\n"
            f"## LENGTH\n"
            f"Keep reply under {max_len} characters.\n"
            f"{'First message — include links and alternatives if multiple matches.' if is_first_message else 'Follow-up — be concise, no links needed.'}\n\n"
            f"Phase: {phase}\nIntent: {intent}\n"
            f"Buyer's message: \"{message}\"\n"
            f"{history_ctx}{criteria_ctx}{property_ctx}{matches_ctx}{hint_ctx}{name_ctx}{retry_ctx}\n\n"
            f"Guidelines by intent:\n"
            f"- new_search/refine_search: Confirm what you understood, say you're searching\n"
            f"- facility_info: Answer from data if available, otherwise say you'll look into it\n"
            f"- tour_request: Acknowledge interest, ask for 2-3 preferred days/times\n"
            f"- commitment: Acknowledge interest, guide to next step\n"
            f"- provide_info: Confirm receipt, ask for next needed field\n"
            f"- unknown/other: Ask what kind of space they need (city, size, use)\n\n"
            f"When presenting matches, give a brief count and summary of the top options "
            f"(city, sqft, rate per sqft). Do NOT include any links or URLs. "
            f"Do NOT list each match individually — just summarize the top 2-3 briefly.\n"
            f"Respond with ONLY the SMS text, nothing else."
        )

        result = await self.generate(prompt=prompt)
        if not result.ok:
            logger.warning("Response agent failed: %s", result.error)
            return ""
        return result.data.strip().strip('"').strip("'")

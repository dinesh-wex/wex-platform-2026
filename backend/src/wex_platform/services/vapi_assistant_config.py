"""Vapi assistant configuration and phone number registration."""

import logging
import httpx

from wex_platform.app.config import get_settings

logger = logging.getLogger(__name__)

# ElevenLabs default voice (warm, professional)
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # "Rachel" - calm professional female


def build_assistant_config(caller_phone: str, buyer_name: str | None = None, sms_context: dict | None = None) -> dict:
    """Build the Vapi assistant configuration for an inbound call.

    Returns a dict with the full assistant config including:
    - System prompt (voice-adapted WEx broker persona)
    - Tool definitions (search, lookup, booking)
    - Voice settings (ElevenLabs)
    - Call limits
    """
    settings = get_settings()
    voice_id = settings.vapi_voice_id or DEFAULT_VOICE_ID

    # Build dynamic first message — 3 tiers based on SMS history
    if sms_context and sms_context.get("presented_match_ids"):
        count = len(sms_context["presented_match_ids"])
        first_name = buyer_name.split()[0] if buyer_name else None
        if first_name:
            first_message = (
                f"Hey {first_name}, I can see we've been texting about warehouse space. "
                f"I have those {count} option{'s' if count != 1 else ''} pulled up — "
                f"want to go over them?"
            )
        else:
            first_message = (
                f"Hey there, I can see we've been texting about warehouse space. "
                f"I have those {count} option{'s' if count != 1 else ''} pulled up — "
                f"want to go over them?"
            )
    elif sms_context and sms_context.get("criteria_snapshot"):
        criteria = sms_context["criteria_snapshot"]
        city = None
        if criteria.get("location"):
            city = criteria["location"].split(",")[0].strip()
        first_name = buyer_name.split()[0] if buyer_name else None
        if first_name and city:
            first_message = (
                f"Hey {first_name}, I can see we were chatting about space in {city}. "
                f"Want to pick up where we left off?"
            )
        elif first_name:
            first_message = (
                f"Hey {first_name}, I can see we've been texting. How can I help you today?"
            )
        else:
            first_message = (
                "Hey there, I can see we've been texting about warehouse space. "
                "How can I help you today?"
            )
    elif buyer_name:
        first_message = (
            f"Hey {buyer_name}, thanks for calling Warehouse Exchange. "
            "I help businesses find warehouse space. How can I help you today?"
        )
    else:
        first_message = (
            "Hey there, thanks for calling Warehouse Exchange. "
            "I help businesses find warehouse space. What's your name?"
        )

    return {
        "assistant": {
            "model": {
                "provider": "google",
                "model": "gemini-3-flash-preview",
                "messages": [
                    {"role": "system", "content": _build_system_prompt(sms_context=sms_context)}
                ],
                "tools": _build_tool_definitions(),
                "temperature": 0.7,
            },
            "voice": {
                "provider": "11labs",
                "voiceId": voice_id,
            },
            "firstMessage": first_message,
            "server": {
                "url": f"{settings.frontend_url}/api/voice/webhook",
            },
            "endCallFunctionEnabled": True,
            "recordingEnabled": True,
            "silenceTimeoutSeconds": 30,
            "maxDurationSeconds": 600,  # 10 min max
        }
    }


def _build_system_prompt(sms_context: dict | None = None) -> str:
    """Build the voice agent system prompt."""
    base_prompt = """You are a warehouse space broker at Warehouse Exchange (WEx). You help businesses find warehouse and industrial space. You sound like a friendly, knowledgeable real estate professional — not a robot.

CONVERSATION FLOW:
1. GREET AND GET NAME: Start with a warm greeting. Ask for the caller's name right away. Use their name naturally throughout the call (2-3 times, not every sentence).

2. VERIFY PHONE: After getting their name, confirm the caller ID number is the right one to text: "And just to make sure, is this the best number to reach you by text?" If they give an alternate number, note it.

3. QUALIFY NEEDS (batch questions, don't drip-feed):
   Ask these 6 criteria conversationally in 2 batches:

   Batch 1: "So tell me — what city are you looking in, how much space do you need, and what will you use it for?"
   - Location (city/state)
   - Square footage
   - Use type (storage, fulfillment, distribution, manufacturing, etc.)

   Batch 2: "Got it. Do you need office space in there too? And how about parking — is that important?"
   Then: "How soon do you need it, and how long are you thinking?"
   - Office space (ask FIRST — most common requirement)
   - Parking (ask second)
   - Other features (dock doors, climate control, etc. — ask if relevant to their use type)
   - Timing (when they need it)
   - Duration (how long)

   If the caller gives partial info in batch 1, naturally ask about the missing items before moving to batch 2. Once you have at least location + size + use type, call search_properties.

4. SEARCH: Once you have enough criteria, call the search_properties tool. Then describe ALL options returned (up to 3), including:
   - City/area
   - Price per sqft and estimated monthly cost
   - 1-2 standout features for each

   Example: "I found 3 options. Option 1 is in Detroit at 95 cents per square foot, about $9,500 a month, with 4 dock doors and office space. Option 2 is in Dearborn..."

   After presenting all options, offer to send them over: "If any of these sound good, I can text you the details so you can check them out — want me to send those over?"
   Do NOT ask "which one interests you?" or "which option would you like?" — just offer to send all of them.

5. DETAILS: If they ask about a specific option, call lookup_property_details. Answer naturally from the data returned. If we don't have the info, say you'll check with the warehouse owner and text them back.

6. COMMITMENT: When the caller says yes to receiving the options or wants to proceed:
   - Call send_booking_link with their name and option 1 (the top match) — the text link gives them access to all options
   - Let them know you'll text them a link after the call
   - If they ask for email instead, ask for their email and include it
   - Do NOT ask them to pick a specific option number — just send it

VOICE GUIDELINES:
- Be conversational, warm, and professional
- Keep responses concise — voice conversations need shorter answers than text
- Confirm what you heard before searching: "So you're looking for about 10,000 square feet in Dallas for fulfillment — let me check what's available."
- Use natural transitions: "Great, and how soon would you need the space?"
- Use contractions: it's, that's, here's, I'll, we've
- Say "square feet" when speaking (not "sqft" — voice needs the full phrase for clarity)
- Never mention that you're an AI, a voice agent, or automated
- Never spell out URLs or tokens — just say "I'll text you the link"
- If the caller is unclear, ask a clarifying question rather than guessing

INFORMATION RULES:
- Only state facts from data provided by tools — NEVER invent property details
- If a detail isn't available: "I don't have that on file, but I'll check with the warehouse owner and text you back"
- No full street addresses — refer to properties by city/area and option number
- Never mention total building size or available square footage
- Never mention owner/landlord names, emails, or phone numbers
- Max 3 property options per search
- Properties are flexible — buyers lease the space they need within larger buildings

TERMINOLOGY:
- Use: "lease", "space", "warehouse", "industrial"
- NEVER use: "stay", "book a stay", "accommodation", "hotel", "room"
- Say "per square foot" not "per sqft" (voice clarity)
- Say "a month" not "per month" (natural speech)

ESCALATION:
- When you can't answer a question, tell the caller: "I'll check with the warehouse owner and text you back with the answer"
- Default follow-up is by text. If they prefer a callback, note that."""
    sms_section = _build_sms_context_section(sms_context) if sms_context else ""
    return base_prompt + sms_section


def _build_sms_context_section(sms_context: dict | None) -> str:
    """Generate a dynamic system prompt section summarizing prior SMS history.

    Appended to the base system prompt when the caller has an active SMS
    conversation, so the voice agent doesn't re-ask answered questions.
    """
    if not sms_context:
        return ""

    lines = ["\n\nSMS CONVERSATION CONTEXT:"]
    lines.append("This caller has been texting with WEx before this call. Key context:")

    criteria = sms_context.get("criteria_snapshot") or {}

    # Summarize known criteria
    criteria_parts = []
    if criteria.get("location"):
        criteria_parts.append(f"location: {criteria['location']}")
    if criteria.get("sqft"):
        criteria_parts.append(f"size: {criteria['sqft']} sq ft")
    if criteria.get("use_type"):
        criteria_parts.append(f"use type: {criteria['use_type']}")
    if criteria.get("timing"):
        criteria_parts.append(f"timing: {criteria['timing']}")
    if criteria.get("duration"):
        criteria_parts.append(f"duration: {criteria['duration']}")
    if criteria.get("requirements") and criteria["requirements"] not in ("none", ""):
        criteria_parts.append(f"requirements: {criteria['requirements']}")

    if criteria_parts:
        lines.append(f"- Prior criteria collected via SMS: {', '.join(criteria_parts)}")
    else:
        lines.append("- No criteria collected yet via SMS")

    # Summarize presented matches
    presented = sms_context.get("presented_match_ids") or []
    if presented:
        lines.append(f"- {len(presented)} properties were already presented via SMS")
        focused = sms_context.get("focused_match_id")
        if focused and focused in presented:
            idx = presented.index(focused) + 1
            lines.append(f"- Buyer was focused on option {idx} in the SMS conversation")

    # Phase description
    phase = sms_context.get("phase", "INTAKE")
    phase_descriptions = {
        "INTAKE": "just started texting",
        "QUALIFYING": "was being qualified (answering screening questions)",
        "PRESENTING": "was reviewing presented property options",
        "PROPERTY_FOCUSED": "was asking questions about a specific property",
        "AWAITING_ANSWER": "was waiting for a supplier to answer a question",
        "COLLECTING_INFO": "was providing contact info for booking",
        "COMMITMENT": "was in the commitment/booking flow",
        "GUARANTEE_PENDING": "was sent a booking guarantee link",
    }
    phase_desc = phase_descriptions.get(phase, phase)
    lines.append(f"- SMS conversation phase: {phase_desc}")

    # Cached answers summary
    answered_qs = sms_context.get("answered_questions") or []
    if answered_qs:
        lines.append(f"- {len(answered_qs)} questions already answered and cached")

    lines.append("\nINSTRUCTIONS FOR HANDLING SMS CONTEXT:")
    if criteria_parts:
        lines.append("- Do NOT re-ask questions that were already answered via text")
        lines.append("- You can reference their criteria: \"I see you were looking for X in Y\"")
    if presented:
        lines.append("- Buyer has already seen options. Offer to review them or search for more.")
        lines.append("- Only use search_properties if the buyer wants to change their criteria")
    else:
        lines.append("- Buyer has criteria but hasn't seen matches yet. You can search immediately.")

    return "\n".join(lines)


def _build_tool_definitions() -> list[dict]:
    """Build the Vapi tool definitions in function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": "search_properties",
                "description": "Search for warehouse properties matching the buyer's criteria. Call this once you have at least a location and approximate size.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City and/or state, e.g. 'Dallas, TX' or 'Detroit'"
                        },
                        "sqft": {
                            "type": "integer",
                            "description": "Desired square footage, e.g. 10000"
                        },
                        "use_type": {
                            "type": "string",
                            "description": "What the space will be used for: storage, fulfillment, distribution, manufacturing, office, etc."
                        },
                        "timing": {
                            "type": "string",
                            "description": "When they need it: immediately, 30_days, 1-3 months, 3-6 months, flexible"
                        },
                        "duration": {
                            "type": "string",
                            "description": "How long they need it: 1-3 months, 3-6 months, 6-12 months, 12-24 months, 24+ months"
                        },
                        "features": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Required features: dock_doors, office, climate_control, sprinkler, parking, 24_7_access, fenced_yard"
                        }
                    },
                    "required": ["location", "sqft"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "lookup_property_details",
                "description": "Look up specific details about one of the property options. Use the option number from search results.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "option_number": {
                            "type": "integer",
                            "description": "Which option to look up (1, 2, or 3)"
                        },
                        "topics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "What to look up: dock_doors, office, clear_height, parking, pricing, availability, access_hours, sprinkler, climate_control, year_built, construction_type"
                        }
                    },
                    "required": ["option_number"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "send_booking_link",
                "description": "Set up a booking for a specific property and queue a text message with the link. Call this when the buyer wants to proceed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "option_number": {
                            "type": "integer",
                            "description": "Which property option to book (1, 2, or 3)"
                        },
                        "buyer_name": {
                            "type": "string",
                            "description": "The buyer's full name"
                        },
                        "buyer_email": {
                            "type": "string",
                            "description": "The buyer's email address (only if they specifically request email delivery)"
                        }
                    },
                    "required": ["option_number", "buyer_name"]
                }
            }
        }
    ]


async def register_vapi_phone_number(server_url: str) -> bool:
    """Register our webhook URL with the Vapi phone number.

    Called on app startup. PATCHes the phone number config in Vapi
    to point to our server URL for webhook events.

    Args:
        server_url: Full URL to our voice webhook, e.g.
                    "https://example.com/api/voice/webhook"

    Returns:
        True if registration succeeded, False otherwise.
    """
    settings = get_settings()

    if not settings.vapi_api_key:
        logger.info("VAPI_API_KEY not set, skipping phone number registration")
        return False

    if not settings.vapi_phone_number_id:
        logger.info("VAPI_PHONE_NUMBER_ID not set, skipping registration")
        return False

    url = f"https://api.vapi.ai/phone-number/{settings.vapi_phone_number_id}"
    headers = {
        "Authorization": f"Bearer {settings.vapi_api_key}",
        "Content-Type": "application/json",
    }
    server_config = {"url": server_url}
    if settings.vapi_server_secret:
        server_config["secret"] = settings.vapi_server_secret
    payload = {
        "server": server_config,
    }

    try:
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.patch(url, json=payload, headers=headers, timeout=10)

            if response.status_code == 200:
                logger.info("Vapi phone number registered with server URL: %s", server_url)
                return True
            else:
                logger.error(
                    "Vapi registration failed: %s %s",
                    response.status_code, response.text
                )
                return False
    except Exception as e:
        logger.error("Vapi registration error: %s", e)
        return False

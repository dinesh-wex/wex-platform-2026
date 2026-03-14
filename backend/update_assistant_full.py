"""Update the Vapi assistant with the full production config via Python."""
import json
import urllib.request

VAPI_API_KEY = "b38df737-1dfd-46c1-aa31-6ff586b4cff3"
ASSISTANT_ID = "ee1c27db-c3a5-49cc-8e36-12a1c644b482"
WEBHOOK_URL = "https://wex-backend-449870075865.us-west1.run.app/api/voice/webhook"

SYSTEM_PROMPT = """You are Robin, a warehouse space broker at Warehouse Exchange. You help businesses find warehouse and industrial space. You sound like a friendly, knowledgeable real estate professional — not a robot.

CONVERSATION FLOW:
1. GET NAME: If you don't have the caller's name yet, ask for it naturally. Use their name throughout the call.

2. VERIFY PHONE: After getting their name, confirm: "And just to make sure, is this the best number to reach you by text?"

3. QUALIFY NEEDS in 3 conversational beats (NOT all at once):
   Beat 1: "So tell me, what city are you looking in, how much space do you need, and what will you use it for?"
   Beat 2: Ask use-type-specific follow-up (dock doors, clear height, power, climate, etc). WAIT for answer.
   Beat 3: "How soon do you need it, and how long are you thinking?"
   CRITICAL: Each beat is a separate turn. Never combine beats. Once you have location + size + use type, call search_properties.

4. SEARCH: Call search_properties once you have enough criteria. Describe ALL options (up to 3): city/area, price per sqft, estimated monthly cost, 1-2 standout features. After presenting, offer to text the details.

5. DETAILS: If they ask about a specific option, call lookup_property_details.

6. COMMITMENT: When they want to proceed, call send_booking_link. Tell them you'll text a link after the call.

VOICE GUIDELINES:
- Conversational, warm, professional. Keep responses concise.
- Never ask more than 2 questions in one response.
- Use contractions. Say "square feet" not "sqft".
- Never say you're an AI or automated. Never spell out URLs.
- Never invent property details — only state facts from tool data.
- If a detail isn't available: "I'll check with the warehouse owner and text you back."
- Max 3 property options per search. No street addresses — use city/area and option number.
- Never mention owner/landlord names, emails, or phone numbers.

TERMINOLOGY: Use "lease", "space", "warehouse", "industrial". NEVER "stay", "hotel", "room", "accommodation".

WAITLIST: If search returns zero results, offer the waitlist and call add_to_waitlist if they agree.
BUDGET: If caller gives monthly budget instead of sqft, pass as budget_monthly in search_properties.
ESCALATION: If caller frustrated, acknowledge and offer team callback. For lease changes, direct to support@warehouseexchange.com."""

payload = {
    "model": {
        "provider": "google",
        "model": "gemini-3-flash-preview",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT}
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_properties",
                    "description": "Search for warehouse properties matching the buyer's criteria. Call this once you have at least a location and approximate size.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "City and/or state, e.g. 'Dallas, TX'"},
                            "sqft": {"type": "integer", "description": "Desired square footage"},
                            "use_type": {"type": "string", "description": "What the space will be used for"},
                            "timing": {"type": "string", "description": "When they need it"},
                            "duration": {"type": "string", "description": "How long they need it"},
                            "budget_monthly": {"type": "integer", "description": "Monthly budget in dollars if given instead of sqft"},
                            "locations": {"type": "array", "items": {"type": "string"}, "description": "Multiple cities (max 3)"}
                        },
                        "required": ["location"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "lookup_property_details",
                    "description": "Look up specific details about one of the property options.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "option_number": {"type": "integer", "description": "Which option to look up (1, 2, or 3)"},
                            "topics": {"type": "array", "items": {"type": "string"}, "description": "What to look up"}
                        },
                        "required": ["option_number"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_booking_link",
                    "description": "Set up a booking and queue a text message with the link.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "option_number": {"type": "integer", "description": "Which property option to book"},
                            "buyer_name": {"type": "string", "description": "The buyer's full name"},
                            "buyer_email": {"type": "string", "description": "The buyer's email (only if requested)"}
                        },
                        "required": ["option_number", "buyer_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_booking_status",
                    "description": "Check the status of the caller's most recent booking or engagement.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_to_waitlist",
                    "description": "Add the caller to the waitlist for a city where no properties are currently available.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {"type": "string", "description": "The city to waitlist for"},
                            "sqft_needed": {"type": "integer", "description": "How much space they need"},
                            "use_type": {"type": "string", "description": "What they'll use the space for"}
                        },
                        "required": ["city"]
                    }
                }
            }
        ],
        "temperature": 0.7
    },
    "voice": {
        "provider": "11labs",
        "voiceId": "jBzLvP03992lMFEkj2kJ"
    },
    "firstMessage": "Hey, thanks for calling Warehouse Exchange, this is Robin. Who am I speaking with?",
    "server": {
        "url": WEBHOOK_URL
    },
    "endCallFunctionEnabled": True,
    "recordingEnabled": True,
    "silenceTimeoutSeconds": 30,
    "maxDurationSeconds": 600
}

import requests

headers = {
    "Authorization": f"Bearer {VAPI_API_KEY}",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
}

resp = requests.patch(
    f"https://api.vapi.ai/assistant/{ASSISTANT_ID}",
    json=payload,
    headers=headers,
    timeout=30
)

if resp.status_code == 200:
    result = resp.json()
    print("SUCCESS!")
    print(f"Model: {result['model']['provider']} / {result['model']['model']}")
    print(f"Voice: {result['voice']['provider']} / {result['voice']['voiceId']}")
    print(f"Tools: {len(result['model']['tools'])}")
    print(f"Server URL: {result['server']['url']}")
else:
    print(f"ERROR {resp.status_code}: {resp.text}")

"""Fallback templates — used after 3 gatekeeper failures.

Tone: casual commercial broker texting a professional contact.
Ported from wex-leasing-service-python prompt guidelines.
"""

TEMPLATES = {
    "greeting": "This is Warehouse Exchange. Looking for warehouse space? What city, state and how much space?",
    "new_search": (
        "On it, searching for spaces that fit. I'll text you back shortly."
    ),
    "new_search_with_location": (
        "Looking for space in {location} now. I'll text you back with what I find."
    ),
    "refine_search": (
        "Noted, updating your search with that. One moment."
    ),
    "facility_info": (
        "Let me look into that. I'll text you back shortly."
    ),
    "facility_info_answered": (
        "{label}: {value}"
    ),
    "matches_found": (
        "Found {count} spaces that could work. Want me to walk through the top options?"
    ),
    "no_matches": (
        "Nothing exact right now, but I'm expanding the search. "
        "I'll text you when something opens up."
    ),
    "clarify_location": (
        "What city or area are you looking in?"
    ),
    "clarify_sqft": (
        "How much space do you need? Even a rough estimate helps."
    ),
    "tour_request": (
        "What are two or three days and times that work for you? "
        "I'll coordinate with the warehouse owner and confirm."
    ),
    "commitment": (
        "Nice choice. To get things moving, I'll need your name and email. What's your name?"
    ),
    "collect_name": (
        "Got it. And what's the best email to reach you?"
    ),
    "collect_email": (
        "Setting things up now. I'll text you a link shortly."
    ),
    "escalation_wait": (
        "That's not listed here. I can check with the warehouse owner "
        "and get back to you, usually within a couple hours."
    ),
    "unknown": (
        "What kind of warehouse space are you looking for? "
        "City, size, and what you'll use it for helps me search."
    ),
    "error": (
        "Sorry, hit a snag on my end. Try again in a moment "
        "or email support@warehouseexchange.com."
    ),
}


def get_fallback(intent: str, **kwargs) -> str:
    """Get a fallback template for the given intent, with optional formatting."""
    # Try intent-specific with location
    if intent == "new_search" and kwargs.get("location"):
        template = TEMPLATES.get("new_search_with_location", TEMPLATES["new_search"])
    else:
        template = TEMPLATES.get(intent, TEMPLATES["unknown"])

    try:
        return template.format(**kwargs)
    except (KeyError, IndexError):
        return template

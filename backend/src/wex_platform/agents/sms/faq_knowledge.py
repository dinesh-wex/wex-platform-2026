"""FAQ Knowledge — single source of truth for SMS + Voice.

Update answers here; both channels pick up changes automatically.

NOTE: The `keywords` field provides PROMPT CONTEXT to help the LLM
recognize FAQ topics. Actual intent classification is done by the
CriteriaAgent LLM, not by keyword matching. Adding keywords here
improves LLM accuracy but does NOT create deterministic rules.
"""

FAQ_ENTRIES = {
    "pricing": {
        "keywords": ["free", "fee", "cost", "price", "charge", "how much"],
        "answer": (
            "There's a 6% service fee, but the real value is flexibility. "
            "You get short-term leases without the long-term commitment "
            "that traditional warehousing requires."
        ),
    },
    "what_we_are": {
        "keywords": ["broker", "who are you", "what is warehouse exchange", "what is wex", "what do you do"],
        "answer": (
            "We're a tech-enabled marketplace, not a traditional broker. "
            "We match you with verified warehouse space and handle the coordination."
        ),
    },
    "how_it_works": {
        "keywords": ["how does this work", "how does it work", "how do i", "process", "steps"],
        "answer": (
            "Tell me what you need, city, size, use type, and I'll find matching spaces. "
            "You can tour first or book instantly depending on the property."
        ),
    },
    "privacy": {
        "keywords": ["private", "privacy", "share my info", "data"],
        "answer": (
            "Your information is kept private until you choose to move forward "
            "with a specific property."
        ),
    },
    "safety": {
        "keywords": ["legit", "legitimate", "scam", "safe", "verified", "trust"],
        "answer": (
            "Every property on our platform is verified. You'll sign a guarantee "
            "before we share the full address, which protects both sides."
        ),
    },
}


def get_faq_block_for_prompt() -> str:
    """Return FAQ knowledge as a prompt-ready text block for LLM system prompts."""
    lines = ["FAQ KNOWLEDGE (answer these directly, then transition back to their search):"]
    for key, entry in FAQ_ENTRIES.items():
        triggers = ", ".join(entry["keywords"][:3])
        lines.append(f'- If they ask about {triggers}: "{entry["answer"]}"')
    return "\n".join(lines)


def get_faq_answer(category: str) -> str | None:
    """Get FAQ answer by category key (for fallback templates)."""
    entry = FAQ_ENTRIES.get(category)
    return entry["answer"] if entry else None

"""Message Interpreter — DETERMINISTIC only, no LLM calls.

Regex-based extraction of structured data from buyer SMS messages.
"""

import re
from .contracts import MessageInterpretation

# Known US cities (top 100 + warehouse markets)
KNOWN_CITIES = {
    "los angeles", "new york", "chicago", "houston", "phoenix", "philadelphia",
    "san antonio", "san diego", "dallas", "san jose", "austin", "jacksonville",
    "fort worth", "columbus", "charlotte", "san francisco", "indianapolis",
    "seattle", "denver", "washington", "nashville", "oklahoma city", "el paso",
    "boston", "portland", "las vegas", "memphis", "louisville", "baltimore",
    "milwaukee", "albuquerque", "tucson", "fresno", "mesa", "sacramento",
    "atlanta", "kansas city", "colorado springs", "omaha", "raleigh", "miami",
    "long beach", "virginia beach", "oakland", "minneapolis", "tulsa", "tampa",
    "arlington", "new orleans", "detroit", "commerce", "compton", "vernon",
    "city of industry", "fontana", "riverside", "ontario", "corona", "rancho cucamonga",
    "inland empire", "south gate", "carson", "torrance", "jersey city", "newark",
    "elizabeth", "edison", "paterson", "clifton", "trenton", "bayonne",
}

# State abbreviations
STATE_ABBRS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}

# Sqft patterns: "10k sqft", "10,000 sf", "10000 square feet"
SQFT_PATTERN = re.compile(
    r'(\d{1,3}(?:,\d{3})*|\d+)\s*k?\s*(?:sq\s*(?:ft|feet)|sf|square\s*feet?)',
    re.IGNORECASE
)

# Alternative: just number + k (e.g. "10k" in context of warehouse)
SQFT_K_PATTERN = re.compile(r'(\d+)\s*k\b', re.IGNORECASE)

# Email
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# Positional references: "option 2", "#1", "the first one", "number 3"
POSITIONAL_PATTERN = re.compile(
    r'(?:option|number|#)\s*(\d+)|(?:the\s+)?(first|second|third)\s+(?:one|option|property|space|warehouse)',
    re.IGNORECASE
)
ORDINAL_MAP = {"first": "1", "second": "2", "third": "3"}

# Action keywords
ACTION_PATTERNS = {
    "book": re.compile(r'\b(?:book|reserve|lock|secure|take)\b.*\b(?:it|that|this|space|one)\b', re.IGNORECASE),
    "tour": re.compile(r'\b(?:tour|visit|see|view|walk\s*through|check\s*out)\b', re.IGNORECASE),
    "commitment": re.compile(r'\b(?:i\s+want|i\'ll\s+take|sign\s+me\s+up|let\'s\s+do\s+it|ready\s+to\s+go)\b', re.IGNORECASE),
}

# Feature keywords
FEATURE_KEYWORDS = {
    "office": re.compile(r'\boffice\b', re.IGNORECASE),
    "dock_doors": re.compile(r'\bdock\s*(?:door|high)\b', re.IGNORECASE),
    "climate": re.compile(r'\b(?:climate|temperature|refrigerat|cold|cool|heat)\b', re.IGNORECASE),
    "power": re.compile(r'\b(?:power|electric|amp|volt|3\s*phase)\b', re.IGNORECASE),
    "24_7": re.compile(r'\b24\s*/?\s*7\b', re.IGNORECASE),
    "sprinkler": re.compile(r'\bsprinkler\b', re.IGNORECASE),
    "parking": re.compile(r'\bparking\b', re.IGNORECASE),
    "forklift": re.compile(r'\bforklift\b', re.IGNORECASE),
}

# Name pattern (very simple -- "I'm John Smith", "my name is Jane Doe")
NAME_PATTERN = re.compile(
    r"(?:(?:i'?m|my name is|this is|name:?)\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    re.IGNORECASE
)


def interpret_message(text: str) -> MessageInterpretation:
    """Extract structured data from buyer SMS using deterministic regex."""
    result = MessageInterpretation(raw_text=text)
    text_lower = text.lower()

    # Cities
    for city in KNOWN_CITIES:
        if city in text_lower:
            result.cities.append(city.title())

    # States (look for 2-letter abbreviations)
    for word in re.findall(r'\b[A-Z]{2}\b', text):
        if word in STATE_ABBRS:
            result.states.append(word)

    # Sqft
    sqft_match = SQFT_PATTERN.search(text)
    if sqft_match:
        raw = sqft_match.group(1).replace(",", "")
        multiplier = 1000 if "k" in sqft_match.group(0).lower() else 1
        result.sqft = int(raw) * multiplier
    elif not result.sqft:
        k_match = SQFT_K_PATTERN.search(text)
        if k_match:
            result.sqft = int(k_match.group(1)) * 1000

    # Topics (imported from topic_catalog)
    from .topic_catalog import detect_topics
    result.topics = detect_topics(text)

    # Features
    for feature, pattern in FEATURE_KEYWORDS.items():
        if pattern.search(text):
            result.features.append(feature)

    # Positional references
    for match in POSITIONAL_PATTERN.finditer(text):
        if match.group(1):
            result.positional_references.append(match.group(1))
        elif match.group(2):
            result.positional_references.append(ORDINAL_MAP.get(match.group(2).lower(), "1"))

    # Action keywords
    for action, pattern in ACTION_PATTERNS.items():
        if pattern.search(text):
            result.action_keywords.append(action)

    # Emails
    result.emails = EMAIL_PATTERN.findall(text)

    # Names
    name_match = NAME_PATTERN.search(text)
    if name_match:
        result.names.append(name_match.group(1))

    return result

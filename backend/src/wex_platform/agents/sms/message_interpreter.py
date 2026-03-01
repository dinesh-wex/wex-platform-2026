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

# Full US state names → abbreviation
US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}

# Reverse lookup: lowercase full name → abbreviation
STATE_NAME_TO_ABBR = {name.lower(): abbr for abbr, name in US_STATES.items()}

# ---------------------------------------------------------------------------
# Sqft patterns
# ---------------------------------------------------------------------------

# Single value: "10k sqft", "10,000 sf", "10000 square feet"
SQFT_PATTERN = re.compile(
    r'(\d{1,3}(?:,\d{3})*|\d+)\s*k?\s*(?:sq\s*(?:ft|feet)|sf|square\s*feet?)',
    re.IGNORECASE
)

# Alternative: just number + k (e.g. "10k" in context of warehouse)
SQFT_K_PATTERN = re.compile(r'(\d+)\s*k\b', re.IGNORECASE)

# Range with "to": "5000 to 10000 sqft", "5k to 10k sf"
SIZE_RANGE_TO_PATTERN = re.compile(
    r'(\d{1,3}(?:,\d{3})*|\d+)\s*k?\s*(?:to|through)\s*(\d{1,3}(?:,\d{3})*|\d+)\s*k?\s*(?:sq\s*(?:ft|feet)|sf|square\s*feet?)',
    re.IGNORECASE
)

# Range with dash: "5k-10k sf", "5,000-10,000 sqft"
SIZE_RANGE_PATTERN = re.compile(
    r'(\d{1,3}(?:,\d{3})*|\d+)\s*k?\s*[-–]\s*(\d{1,3}(?:,\d{3})*|\d+)\s*k?\s*(?:sq\s*(?:ft|feet)|sf|square\s*feet?)',
    re.IGNORECASE
)

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

# ---------------------------------------------------------------------------
# City preposition patterns  (fallback if KNOWN_CITIES didn't match)
# ---------------------------------------------------------------------------
CITY_PREPOSITION_PATTERN = re.compile(
    r'\b(?:in|near|around|at)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)',
)

CITY_STOP_WORDS = {
    "please", "with", "sqft", "sf", "square", "feet", "access", "storage",
    "warehouse", "space", "looking", "need", "want", "about", "some", "the",
    "for", "and", "that", "this", "from", "available", "listing", "property",
    "office", "dock", "climate", "power", "parking", "forklift", "sprinkler",
    "loading", "truck", "trailer", "lease", "rent", "month", "year",
}

# ---------------------------------------------------------------------------
# Address detection: street number + street name
# ---------------------------------------------------------------------------
ADDRESS_PATTERN = re.compile(
    r'\b(\d{1,6}\s+[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*'
    r'(?:\s+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Rd|Road|Ln|Lane|Way|Ct|Court|Pl|Place|Trail|Pkwy|Parkway|Hwy|Highway|Cir|Circle)))'
    r'\b',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_sqft_value(raw: str, full_match_text: str) -> int:
    """Parse a sqft numeric token, handling commas and k suffix."""
    cleaned = raw.replace(",", "")
    value = int(cleaned)
    # Check if a "k" appears right after this number in the full match
    # We look at the portion of the match text after the raw number
    idx = full_match_text.lower().find(raw.lower())
    if idx >= 0:
        after = full_match_text[idx + len(raw):].lstrip()
        if after.lower().startswith("k"):
            value *= 1000
    return value


def _classify_query_type(interpretation: MessageInterpretation) -> str:
    """Classify the query based on extracted interpretation fields.

    Returns one of:
        facility_lookup - has positional reference (e.g. "option 2")
        booking         - action keywords include tour/book/visit
        commitment      - action keywords include commitment
        search          - has city, sqft, or feature criteria
        general         - default fallback
    """
    if interpretation.positional_references:
        return "facility_lookup"

    actions = set(interpretation.action_keywords)
    if actions & {"tour"}:
        return "booking"
    if actions & {"book"}:
        return "booking"
    if actions & {"commitment"}:
        return "commitment"

    if interpretation.cities or interpretation.sqft or interpretation.features:
        return "search"

    return "general"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def interpret_message(text: str) -> MessageInterpretation:
    """Extract structured data from buyer SMS using deterministic regex."""
    result = MessageInterpretation(raw_text=text)
    result.original_message = text
    text_lower = text.lower()

    # Cities (hardcoded KNOWN_CITIES first)
    for city in KNOWN_CITIES:
        if city in text_lower:
            result.cities.append(city.title())

    # States (look for 2-letter abbreviations)
    for word in re.findall(r'\b[A-Z]{2}\b', text):
        if word in STATE_ABBRS:
            result.states.append(word)

    # States (full name recognition)
    for state_name, abbr in STATE_NAME_TO_ABBR.items():
        if state_name in text_lower:
            if abbr not in result.states:
                result.states.append(abbr)

    # -----------------------------------------------------------------------
    # Sqft: try range patterns first, then single-value patterns
    # -----------------------------------------------------------------------
    range_match = SIZE_RANGE_TO_PATTERN.search(text) or SIZE_RANGE_PATTERN.search(text)
    if range_match:
        full_text = range_match.group(0)
        min_raw = range_match.group(1).replace(",", "")
        max_raw = range_match.group(2).replace(",", "")
        min_val = int(min_raw)
        max_val = int(max_raw)
        # Detect "k" suffix for each number by examining the match text
        # Split on the separator (to/through/dash) to isolate each side
        sep_match = re.search(r'\b(?:to|through)\b|[-–]', full_text, re.IGNORECASE)
        if sep_match:
            left_part = full_text[:sep_match.start()]
            right_part = full_text[sep_match.end():]
        else:
            left_part = full_text
            right_part = full_text
        if re.search(r'\d\s*k', left_part, re.IGNORECASE):
            min_val *= 1000
        if re.search(r'\d\s*k', right_part, re.IGNORECASE):
            max_val *= 1000
        result.min_sqft = min_val
        result.max_sqft = max_val
        result.sqft = min_val  # backward compat
    else:
        # Single-value sqft patterns
        sqft_match = SQFT_PATTERN.search(text)
        if sqft_match:
            raw = sqft_match.group(1).replace(",", "")
            multiplier = 1000 if "k" in sqft_match.group(0).lower() else 1
            result.sqft = int(raw) * multiplier
            result.min_sqft = result.sqft
        elif not result.sqft:
            k_match = SQFT_K_PATTERN.search(text)
            if k_match:
                result.sqft = int(k_match.group(1)) * 1000
                result.min_sqft = result.sqft

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

    # -----------------------------------------------------------------------
    # City preposition fallback (only if no city found from KNOWN_CITIES)
    # -----------------------------------------------------------------------
    if not result.cities:
        for m in CITY_PREPOSITION_PATTERN.finditer(text):
            candidate = m.group(1).strip()
            # Trim trailing stop words
            words = candidate.split()
            trimmed: list[str] = []
            for w in words:
                if w.lower() in CITY_STOP_WORDS:
                    break
                trimmed.append(w)
            candidate = " ".join(trimmed).strip()
            if not candidate:
                continue
            # Safety checks
            if len(candidate) > 24:
                continue
            if re.search(r'\d', candidate):
                continue
            if candidate.lower() in STATE_NAME_TO_ABBR:
                continue
            if candidate.upper() in STATE_ABBRS and len(candidate) == 2:
                continue
            result.cities.append(candidate)
            break  # take first valid match only

    # -----------------------------------------------------------------------
    # Address text detection
    # -----------------------------------------------------------------------
    addr_match = ADDRESS_PATTERN.search(text)
    if addr_match:
        result.address_text = addr_match.group(0).strip()

    # -----------------------------------------------------------------------
    # Query type classification
    # -----------------------------------------------------------------------
    result.query_type = _classify_query_type(result)

    return result

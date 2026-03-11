"""Voice-specific validation for tool results before returning to Vapi's LLM."""

from dataclasses import dataclass
import re


@dataclass
class VoiceGatekeeperResult:
    ok: bool
    violations: list[str]  # List of violation descriptions
    sanitized_text: str | None = None  # Cleaned text if fixable


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

ADDRESS_PATTERN = re.compile(
    r'\d+\s+[A-Za-z\s]+\b(Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd'
    r'|Drive|Dr|Way|Lane|Ln|Court|Ct|Place|Pl)\b\.?',
    re.IGNORECASE,
)

BUILDING_SIZE_PATTERNS = [
    re.compile(r'total\s+(building\s+)?size', re.IGNORECASE),
    re.compile(r'available\s+sq(uare\s+)?f(ee)?t', re.IGNORECASE),
    re.compile(r'available\s+sqft', re.IGNORECASE),
    re.compile(r'total\s+sq(uare\s+)?f(ee)?t', re.IGNORECASE),
]

OWNER_PII_PATTERNS = [
    re.compile(r'owner[\s\']s?\s+(email|phone|number|contact)', re.IGNORECASE),
    re.compile(r'landlord[\s\']s?\s+(email|phone|number|contact)', re.IGNORECASE),
    re.compile(r'supplier[\s\']s?\s+(email|phone|number|contact)', re.IGNORECASE),
]

OPTION_PATTERN = re.compile(r'Option\s+\d+', re.IGNORECASE)

BAD_TERMS: dict[str, str] = {
    "book a stay": "lease space",
    "accommodation": "warehouse space",
    "hotel": "warehouse",
    "room": "space",
    "check-in": "move-in",
    "check-out": "move-out",
}

# Fields that must never appear in voice match summaries
_SENSITIVE_MATCH_FIELDS = frozenset([
    "address", "full_address", "supplier_rate", "supplier_rate_per_sqft",
    "spread_pct", "owner_email", "owner_phone", "owner_name",
    "building_size_sqft", "available_sqft",
])

VOICE_RESTRICTED_FIELDS = frozenset([
    "supplier_rate_per_sqft",
    "spread_pct",
    "owner_email",
    "owner_phone",
    "owner_name",
    "full_address",
    "building_size_sqft",
    "available_sqft",
])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_tool_result(text: str) -> VoiceGatekeeperResult:
    """Validate a tool result string before returning to Vapi.

    Unlike SMS gatekeeper, this does NOT check character limits.
    It focuses on preventing information leakage in voice responses.
    """
    violations: list[str] = []
    sanitized = text

    # 1. No full addresses — redact street addresses (keep city/area)
    if ADDRESS_PATTERN.search(text):
        violations.append("full_address_leaked")
        sanitized = ADDRESS_PATTERN.sub("[address redacted]", sanitized)

    # 2. No total building size or available sqft disclosure
    for pattern in BUILDING_SIZE_PATTERNS:
        if pattern.search(text):
            violations.append("building_size_leaked")
            break

    # 3. No PII leakage — owner emails, owner phones
    for pattern in OWNER_PII_PATTERNS:
        if pattern.search(text):
            violations.append("owner_pii_leaked")
            break

    # 4. Max 3 options — if presenting more, truncate
    option_count = len(OPTION_PATTERN.findall(text))
    if option_count > 3:
        violations.append("too_many_options")

    # 5. Terminology check — should not use hospitality language
    text_lower = text.lower()
    for bad, good in BAD_TERMS.items():
        if bad in text_lower:
            violations.append(f"bad_terminology: '{bad}' should be '{good}'")
            sanitized = re.sub(re.escape(bad), good, sanitized, flags=re.IGNORECASE)

    return VoiceGatekeeperResult(
        ok=len(violations) == 0,
        violations=violations,
        sanitized_text=sanitized if violations else text,
    )


def sanitize_match_summary(match: dict) -> dict:
    """Sanitize a match summary dict before voice delivery.

    Removes fields that should not be spoken:
    - Full address (keep city only)
    - Total building sqft
    - Supplier rate (only show buyer rate)
    - Owner contact info
    """
    safe = dict(match)
    for field in _SENSITIVE_MATCH_FIELDS:
        safe.pop(field, None)
    return safe


def sanitize_detail_response(data: dict) -> dict:
    """Remove restricted fields from property detail/insight data before voice delivery."""
    safe = dict(data)
    for field in VOICE_RESTRICTED_FIELDS:
        safe.pop(field, None)
    for key, val in list(safe.items()):
        if isinstance(val, dict):
            safe[key] = {k: v for k, v in val.items() if k not in VOICE_RESTRICTED_FIELDS}
    return safe


_NARRATIVE_SQFT_PATTERN = re.compile(
    r'\b\d[\d,]*\s*(?:sq\.?\s*ft|sqft|square\s+feet)\b', re.IGNORECASE
)
_NARRATIVE_ADDRESS_PATTERN = ADDRESS_PATTERN
_NARRATIVE_EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
)
_NARRATIVE_PHONE_PATTERN = re.compile(
    r'(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
)


def scrub_narrative_for_voice(text: str) -> str:
    """Scrub PropertyInsight narrative strings that may contain sensitive data."""
    scrubbed = _NARRATIVE_SQFT_PATTERN.sub("[size info redacted]", text)
    scrubbed = _NARRATIVE_ADDRESS_PATTERN.sub("[address redacted]", scrubbed)
    scrubbed = _NARRATIVE_EMAIL_PATTERN.sub("[contact redacted]", scrubbed)
    scrubbed = _NARRATIVE_PHONE_PATTERN.sub("[contact redacted]", scrubbed)
    return scrubbed

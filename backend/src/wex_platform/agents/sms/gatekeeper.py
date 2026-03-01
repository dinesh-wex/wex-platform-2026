"""Gatekeeper — deterministic SMS validation with expanded rules."""

import re
from collections import Counter
from .contracts import GatekeeperResult

MAX_FIRST_MESSAGE = 800
MAX_FOLLOWUP = 480
MIN_LENGTH = 20

PROFANITY_WORDS = frozenset([
    "fuck", "fucking", "fucker", "shit", "shitty", "asshole",
    "bitch", "dick", "cock", "pussy",
])

PHONE_PATTERN = re.compile(r"(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Garbage detection
REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{39,}")  # 40+ repeated chars
WORD_REPETITION_THRESHOLD = 5

# Common words excluded from repetition check
COMMON_WORDS = {
    "the", "a", "an", "is", "in", "to", "for", "and", "of", "it",
    "i", "you", "your", "we", "at", "on", "with",
}


def validate_outbound(
    text: str,
    is_first_message: bool = False,
    context: str | None = None,
) -> GatekeeperResult:
    """Validate outbound SMS before sending."""
    if not text or not text.strip():
        return GatekeeperResult(ok=False, hint="Empty reply", violation="empty")

    # Messages with URLs get extra room — URLs are non-compressible
    has_url = "http://" in text or "https://" in text
    if is_first_message:
        max_len = MAX_FIRST_MESSAGE
    elif has_url:
        max_len = MAX_FIRST_MESSAGE  # Relax to 800 when a link is present
    else:
        max_len = MAX_FOLLOWUP
    if len(text) > max_len:
        return GatekeeperResult(
            ok=False,
            hint=f"Reply too long ({len(text)} chars, max {max_len}). Compress it.",
            violation="too_long",
        )

    if len(text) < MIN_LENGTH:
        return GatekeeperResult(ok=False, hint=f"Reply too short ({len(text)} chars)", violation="too_short")

    # Garbage detection
    if REPEATED_CHAR_PATTERN.search(text):
        return GatekeeperResult(ok=False, hint="Contains repeated characters", violation="garbage_repeated")

    # Letter ratio check
    alpha_count = sum(1 for c in text if c.isalpha())
    if len(text) > 20 and alpha_count / len(text) < 0.40:
        return GatekeeperResult(ok=False, hint="Low letter ratio — may be garbage", violation="garbage_ratio")

    # Word repetition
    words = text.lower().split()
    if words:
        word_counts = Counter(words)
        for word, count in word_counts.most_common(3):
            if word not in COMMON_WORDS and count > WORD_REPETITION_THRESHOLD:
                return GatekeeperResult(ok=False, hint=f"Word '{word}' repeated {count} times", violation="garbage_repetition")

    # PII leak check
    phones = PHONE_PATTERN.findall(text)
    if len(phones) > 1:
        return GatekeeperResult(ok=False, hint="Contains multiple phone numbers", violation="multiple_phones")

    emails = EMAIL_PATTERN.findall(text)
    if len(emails) > 1:
        return GatekeeperResult(ok=False, hint="Contains multiple email addresses", violation="multiple_emails")

    # Profanity
    text_words = set(re.findall(r"\b\w+\b", text.lower()))
    found = text_words & PROFANITY_WORDS
    if found:
        return GatekeeperResult(ok=False, hint="Contains inappropriate language", violation="profanity")

    # Context-specific checks
    if context == "commitment" and "http" not in text.lower() and "link" not in text.lower() and "warehouseexchange" not in text.lower():
        return GatekeeperResult(ok=False, hint="Commitment message must contain a guarantee link", violation="missing_link")

    if context == "tour" and not re.search(r'\b(?:tour|visit|schedule|appointment|time|date|when)\b', text, re.IGNORECASE):
        return GatekeeperResult(ok=False, hint="Tour message must contain scheduling language", violation="missing_schedule")

    return GatekeeperResult(ok=True)


def validate_inbound(text: str) -> GatekeeperResult:
    """Validate inbound buyer SMS."""
    if not text or not text.strip():
        return GatekeeperResult(ok=False, hint="Empty message", violation="empty")
    if len(text) > 1600:
        return GatekeeperResult(ok=False, hint=f"Message too long ({len(text)} chars)", violation="too_long")
    text_words = set(re.findall(r"\b\w+\b", text.lower()))
    found = text_words & PROFANITY_WORDS
    if found:
        return GatekeeperResult(ok=False, hint="Contains inappropriate language", violation="profanity")
    return GatekeeperResult(ok=True)

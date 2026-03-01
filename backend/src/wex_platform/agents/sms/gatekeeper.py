"""Gatekeeper — deterministic SMS validation with expanded rules."""

import re
from collections import Counter
from .contracts import GatekeeperResult

MAX_FIRST_MESSAGE = 800
MAX_FOLLOWUP = 480
MIN_LENGTH = 20

PROFANITY_WORDS = frozenset([
    "fuck", "fucking", "fucker", "shit", "shitty", "asshole",
    "bitch", "dick", "cock", "pussy", "ass", "damn", "crap",
])

PHONE_PATTERN = re.compile(r"(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Garbage detection
REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{39,}")  # 40+ repeated chars
WORD_REPETITION_THRESHOLD = 5

# Stop words excluded from repetition check
STOP_WORDS = frozenset([
    "the", "and", "for", "are", "but", "not", "you", "all", "can",
    "had", "her", "was", "one", "our", "out", "has", "his", "how",
    "its", "may", "new", "now", "old", "see", "two", "way", "who",
    "did", "get", "let", "put", "say", "she", "too", "use", "with",
    "this", "that", "from", "they", "been", "have", "many", "some",
    "them", "then", "will", "more", "when", "your", "into", "just",
])


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _check_length(
    text: str, is_first_message: bool, has_url: bool,
) -> GatekeeperResult:
    """Validate message length (empty, too short, too long)."""
    if not text or not text.strip():
        return GatekeeperResult(ok=False, hint="Empty reply", violation="empty")

    # Messages with URLs get extra room — URLs are non-compressible
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
        return GatekeeperResult(
            ok=False,
            hint=f"Reply too short ({len(text)} chars)",
            violation="too_short",
        )

    return GatekeeperResult(ok=True)


def _check_garbage(text: str) -> GatekeeperResult:
    """Detect repeated characters, low letter ratio, and word repetition."""
    if REPEATED_CHAR_PATTERN.search(text):
        return GatekeeperResult(
            ok=False,
            hint="Contains repeated characters",
            violation="garbage_repeated",
        )

    # Letter ratio — exclude spaces from denominator
    non_space = text.replace(" ", "")
    alpha_count = sum(1 for c in text if c.isalpha())
    if len(non_space) > 20 and alpha_count / len(non_space) < 0.40:
        return GatekeeperResult(
            ok=False,
            hint="Low letter ratio — may be garbage",
            violation="garbage_ratio",
        )

    # Word repetition — only count words with 3+ characters
    words = [w for w in text.lower().split() if len(w) >= 3]
    if words:
        word_counts = Counter(words)
        for word, count in word_counts.most_common(3):
            if word not in STOP_WORDS and count > WORD_REPETITION_THRESHOLD:
                return GatekeeperResult(
                    ok=False,
                    hint=f"Word '{word}' repeated {count} times",
                    violation="garbage_repetition",
                )

    return GatekeeperResult(ok=True)


def _check_pii(text: str) -> GatekeeperResult:
    """Flag messages leaking multiple phone numbers or emails."""
    phones = PHONE_PATTERN.findall(text)
    if len(phones) > 1:
        return GatekeeperResult(
            ok=False,
            hint="Contains multiple phone numbers",
            violation="multiple_phones",
        )

    emails = EMAIL_PATTERN.findall(text)
    if len(emails) > 1:
        return GatekeeperResult(
            ok=False,
            hint="Contains multiple email addresses",
            violation="multiple_emails",
        )

    return GatekeeperResult(ok=True)


def _check_profanity(text: str) -> GatekeeperResult:
    """Reject messages containing profanity."""
    text_words = set(re.findall(r"\b\w+\b", text.lower()))
    found = text_words & PROFANITY_WORDS
    if found:
        return GatekeeperResult(
            ok=False,
            hint="Contains inappropriate language",
            violation="profanity",
        )
    return GatekeeperResult(ok=True)


def _check_context(text: str, context: str | None) -> GatekeeperResult:
    """Context-specific validation (commitment, tour, awaiting_answer)."""
    if context is None:
        return GatekeeperResult(ok=True)

    text_lower = text.lower()

    if context == "commitment":
        if (
            "http" not in text_lower
            and "link" not in text_lower
            and "warehouseexchange" not in text_lower
        ):
            return GatekeeperResult(
                ok=False,
                hint="Commitment message must contain a guarantee link",
                violation="missing_link",
            )

    elif context == "tour":
        if not re.search(
            r'\b(?:tour|visit|schedule|appointment|time|date|when)\b',
            text,
            re.IGNORECASE,
        ):
            return GatekeeperResult(
                ok=False,
                hint="Tour message must contain scheduling language",
                violation="missing_schedule",
            )

    elif context == "awaiting_answer":
        has_waiting = any(phrase in text_lower for phrase in [
            "waiting", "checking", "look into", "get back to you",
            "let you know", "find out", "working on",
        ])
        if not has_waiting:
            return GatekeeperResult(
                ok=False,
                hint="Awaiting-answer reply must acknowledge the pending inquiry",
                violation="missing_wait_language",
            )

    return GatekeeperResult(ok=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_outbound(
    text: str,
    is_first_message: bool = False,
    context: str | None = None,
) -> GatekeeperResult:
    """Validate outbound SMS before sending."""
    has_url = "http://" in text or "https://" in text if text else False

    for check in (
        lambda: _check_length(text, is_first_message, has_url),
        lambda: _check_garbage(text),
        lambda: _check_pii(text),
        lambda: _check_profanity(text),
        lambda: _check_context(text, context),
    ):
        result = check()
        if not result.ok:
            return result

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


def trim_to_limit(text: str, is_first_message: bool = False) -> str:
    """Trim text to the SMS length limit, preferring clean boundaries.

    Strategy:
    1. If text fits, return as-is.
    2. Try to cut at a sentence boundary (". ", "? ", "! ") that preserves
       at least 50 % of the allowed length.
    3. Fall back to the last word boundary and append "...".
    4. Hard-truncate + "..." as a last resort.
    """
    max_length = MAX_FIRST_MESSAGE if is_first_message else MAX_FOLLOWUP

    if len(text) <= max_length:
        return text

    # Reserve room for ellipsis
    limit = max_length - 3
    half = max_length // 2  # 50 % threshold

    # 1. Sentence boundary
    candidate = text[:max_length]
    for sep in (". ", "? ", "! "):
        idx = candidate.rfind(sep)
        if idx >= half:
            return text[: idx + 1]  # include the punctuation mark itself

    # 2. Word boundary
    snippet = text[:limit]
    space_idx = snippet.rfind(" ")
    if space_idx > 0:
        return snippet[:space_idx] + "..."

    # 3. Hard truncate
    return snippet + "..."

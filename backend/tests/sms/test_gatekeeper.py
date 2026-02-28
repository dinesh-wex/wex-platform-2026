"""Tests for the Gatekeeper — deterministic SMS validation rules.

Covers: length limits, garbage detection, PII leak checks, profanity,
context-specific checks, and validate_inbound.
"""

import pytest
from wex_platform.agents.sms.gatekeeper import validate_outbound, validate_inbound


# ---------------------------------------------------------------------------
# Length limits (validate_outbound)
# ---------------------------------------------------------------------------

class TestLengthLimits:
    @staticmethod
    def _varied_text(n: int) -> str:
        """Build a string of *n* chars that passes all garbage checks.

        Uses a long base so no single non-common word repeats > 5 times.
        """
        # Each sentence unique enough that word counts stay below threshold
        sentences = [
            "Finding warehouse space requires careful planning and market research. ",
            "Location selection depends on logistics routes and customer proximity. ",
            "Square footage calculations must account for storage and operations. ",
            "Loading dock configuration impacts throughput and delivery schedules. ",
            "Climate control systems protect temperature sensitive inventory items. ",
            "Lease negotiations benefit from comparable property rate analysis. ",
            "Building inspections reveal structural condition and code compliance. ",
            "Zoning regulations determine permitted commercial activity categories. ",
            "Parking capacity affects employee access and trailer staging areas. ",
            "Security features include fencing surveillance and controlled entry. ",
        ]
        pool = "".join(sentences)  # ~700 chars
        text = (pool * (n // len(pool) + 1))[:n]
        return text

    def test_first_message_800_ok(self):
        text = self._varied_text(800)
        r = validate_outbound(text, is_first_message=True)
        assert r.ok is True

    def test_first_message_801_rejected(self):
        text = self._varied_text(801)
        r = validate_outbound(text, is_first_message=True)
        assert r.ok is False
        assert r.violation == "too_long"

    def test_followup_480_ok(self):
        text = self._varied_text(480)
        r = validate_outbound(text, is_first_message=False)
        assert r.ok is True

    def test_followup_481_rejected(self):
        text = self._varied_text(481)
        r = validate_outbound(text, is_first_message=False)
        assert r.ok is False
        assert r.violation == "too_long"

    def test_too_short(self):
        text = "short"
        r = validate_outbound(text)
        assert r.ok is False
        assert r.violation == "too_short"

    def test_empty(self):
        r = validate_outbound("")
        assert r.ok is False
        assert r.violation == "empty"

    def test_whitespace_only(self):
        r = validate_outbound("   ")
        assert r.ok is False
        assert r.violation == "empty"


# ---------------------------------------------------------------------------
# Garbage detection
# ---------------------------------------------------------------------------

class TestGarbageDetection:
    def test_repeated_char_41_rejected(self):
        # 41 repeated chars -> regex matches 40+
        text = "a" * 41
        r = validate_outbound(text)
        assert r.ok is False
        assert r.violation == "garbage_repeated"

    def test_repeated_char_39_not_rejected(self):
        # 39 repeated chars -> below 40 threshold, but also < MIN_LENGTH (20)
        # Actually 39 chars is above MIN_LENGTH=20, but below 40 char repeat.
        # The repeated-char regex needs 40+ consecutive repeats.
        # 39 'a's = 39 chars, > 20, letter ratio = 100%, single word 'aaa...' repeated 1 time
        text = "a" * 39
        r = validate_outbound(text)
        assert r.violation != "garbage_repeated"

    def test_low_letter_ratio(self):
        # String with < 40% letters, > 20 chars
        text = "123456789!@#$%^&*()0" + "a"  # 21 chars, 1 letter = 4.8%
        r = validate_outbound(text)
        assert r.ok is False
        assert r.violation == "garbage_ratio"

    def test_word_repeated_6_times_rejected(self):
        # Non-common word repeated 6+ times (threshold is > 5)
        text = " ".join(["warehouse"] * 6) + " plus some extra words here"
        r = validate_outbound(text)
        assert r.ok is False
        assert r.violation == "garbage_repetition"

    def test_common_word_repeated_not_rejected(self):
        # Common words like "the" should NOT trigger repetition check
        text = " ".join(["the"] * 8) + " warehouse is available now nearby"
        r = validate_outbound(text)
        assert r.violation != "garbage_repetition"


# ---------------------------------------------------------------------------
# PII leak
# ---------------------------------------------------------------------------

class TestPIILeak:
    def test_two_phones_rejected(self):
        text = "Call 555-234-5678 or 555-876-5432 for more details and information"
        r = validate_outbound(text)
        assert r.ok is False
        assert r.violation == "multiple_phones"

    def test_one_phone_ok(self):
        text = "Call us at 555-234-5678 for more warehouse details and info"
        r = validate_outbound(text)
        assert r.violation != "multiple_phones"

    def test_two_emails_rejected(self):
        text = "Email john@test.com or jane@test.com for more warehouse information"
        r = validate_outbound(text)
        assert r.ok is False
        assert r.violation == "multiple_emails"

    def test_one_email_ok(self):
        text = "Email john@test.com for more information on the warehouse space"
        r = validate_outbound(text)
        assert r.violation != "multiple_emails"


# ---------------------------------------------------------------------------
# Profanity
# ---------------------------------------------------------------------------

class TestProfanity:
    def test_profanity_detected(self):
        text = "this is shit and you should know better about it"
        r = validate_outbound(text)
        assert r.ok is False
        assert r.violation == "profanity"

    def test_scunthorpe_not_rejected(self):
        # "Scunthorpe" should NOT trigger profanity (word boundary matching)
        text = "The warehouse is located in Scunthorpe"
        r = validate_outbound(text)
        # The gatekeeper uses \b\w+\b word extraction, so "Scunthorpe" is one word
        # It won't match "shit" or other profanity words
        assert r.violation != "profanity"

    def test_shitty_detected(self):
        text = "shitty deal you are offering to us right now"
        r = validate_outbound(text)
        assert r.ok is False
        assert r.violation == "profanity"


# ---------------------------------------------------------------------------
# Context-specific checks
# ---------------------------------------------------------------------------

class TestContextChecks:
    def test_commitment_no_link(self):
        text = "Great choice you made, let us move forward on the deal"
        r = validate_outbound(text, context="commitment")
        assert r.ok is False
        assert r.violation == "missing_link"

    def test_commitment_with_http(self):
        text = "Great choice! Here is your link: http://warehouseexchange.com/guarantee/abc123"
        r = validate_outbound(text, context="commitment")
        assert r.ok is True

    def test_tour_no_schedule_words(self):
        text = "Great, we will get that sorted for you soon"
        r = validate_outbound(text, context="tour")
        assert r.ok is False
        assert r.violation == "missing_schedule"

    def test_tour_with_schedule_word(self):
        text = "Let us schedule a time to visit the property"
        r = validate_outbound(text, context="tour")
        assert r.ok is True


# ---------------------------------------------------------------------------
# validate_inbound
# ---------------------------------------------------------------------------

class TestValidateInbound:
    def test_normal_text(self):
        r = validate_inbound("I need a warehouse in Detroit")
        assert r.ok is True

    def test_too_long(self):
        text = "a" * 1601
        r = validate_inbound(text)
        assert r.ok is False
        assert r.violation == "too_long"

    def test_profanity_inbound(self):
        r = validate_inbound("this is shit")
        assert r.ok is False
        assert r.violation == "profanity"

    def test_empty_inbound(self):
        r = validate_inbound("")
        assert r.ok is False
        assert r.violation == "empty"

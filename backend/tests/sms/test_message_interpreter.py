"""Tests for the deterministic Message Interpreter.

Covers: city extraction, sqft parsing, topic detection, positional references,
action keywords, email extraction, name extraction, and edge cases.
"""

import pytest
from wex_platform.agents.sms.message_interpreter import interpret_message


# ---------------------------------------------------------------------------
# City extraction
# ---------------------------------------------------------------------------

class TestCityExtraction:
    def test_city_with_state(self):
        r = interpret_message("looking for space in Commerce CA")
        assert "Commerce" in r.cities
        assert "CA" in r.states

    def test_known_city(self):
        r = interpret_message("need warehouse in Los Angeles")
        assert "Los Angeles" in r.cities

    def test_detroit_mi(self):
        r = interpret_message("Detroit MI")
        assert "Detroit" in r.cities
        assert "MI" in r.states

    def test_empty_string(self):
        r = interpret_message("")
        assert r.cities == []

    def test_no_city_mentioned(self):
        r = interpret_message("just looking around")
        assert r.cities == []


# ---------------------------------------------------------------------------
# Sqft parsing (parametrized)
# ---------------------------------------------------------------------------

class TestSqftParsing:
    @pytest.mark.parametrize("text,expected", [
        ("10k sqft", 10000),
        ("10,000 sf", 10000),
        ("10000 square feet", 10000),
        ("5k sq ft", 5000),
        ("15000sqft", 15000),
        ("just looking", None),
    ])
    def test_sqft_parsing(self, text, expected):
        r = interpret_message(text)
        assert r.sqft == expected


# ---------------------------------------------------------------------------
# Topic detection
# ---------------------------------------------------------------------------

class TestTopicDetection:
    def test_clear_height(self):
        r = interpret_message("what's the ceiling height?")
        assert "clear_height" in r.topics

    def test_dock_doors(self):
        r = interpret_message("how many dock doors?")
        assert "dock_doors" in r.topics

    def test_parking(self):
        r = interpret_message("do you have parking?")
        assert "parking" in r.topics

    def test_rate(self):
        r = interpret_message("how much per sqft?")
        assert "rate" in r.topics


# ---------------------------------------------------------------------------
# Positional references
# ---------------------------------------------------------------------------

class TestPositionalReferences:
    def test_option_number(self):
        r = interpret_message("option 2")
        assert "2" in r.positional_references

    def test_hash_number(self):
        r = interpret_message("#1")
        assert "1" in r.positional_references

    def test_the_first_one(self):
        r = interpret_message("the first one")
        assert "1" in r.positional_references

    def test_the_second_option(self):
        r = interpret_message("the second option")
        assert "2" in r.positional_references

    def test_no_reference(self):
        r = interpret_message("no reference here")
        assert r.positional_references == []


# ---------------------------------------------------------------------------
# Action keywords
# ---------------------------------------------------------------------------

class TestActionKeywords:
    def test_book(self):
        r = interpret_message("book it")
        assert "book" in r.action_keywords

    def test_tour(self):
        r = interpret_message("schedule a tour")
        assert "tour" in r.action_keywords

    def test_commitment(self):
        r = interpret_message("I want that one")
        assert "commitment" in r.action_keywords


# ---------------------------------------------------------------------------
# Email extraction
# ---------------------------------------------------------------------------

class TestEmailExtraction:
    def test_email_present(self):
        r = interpret_message("my email is john@test.com")
        assert r.emails == ["john@test.com"]

    def test_no_email(self):
        r = interpret_message("no email")
        assert r.emails == []


# ---------------------------------------------------------------------------
# Name extraction
# ---------------------------------------------------------------------------

class TestNameExtraction:
    def test_im_name(self):
        r = interpret_message("I'm John Smith")
        assert "John Smith" in r.names

    def test_my_name_is(self):
        r = interpret_message("my name is Jane")
        assert "Jane" in r.names


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_string_all_fields(self):
        r = interpret_message("")
        assert r.cities == []
        assert r.states == []
        assert r.sqft is None
        assert r.topics == []
        assert r.features == []
        assert r.positional_references == []
        assert r.action_keywords == []
        assert r.emails == []
        assert r.names == []

    def test_emoji_only(self):
        # Should not crash
        r = interpret_message("\U0001f60a")
        assert isinstance(r.cities, list)
        assert isinstance(r.sqft, (int, type(None)))

    def test_mixed_message(self):
        r = interpret_message("10k sqft cold storage in LA")
        assert r.sqft == 10000
        # "la" is substring of "los angeles" — but the matcher checks if "los angeles" in text_lower
        # "la" alone won't match "los angeles"; check that "climate" feature triggers for "cold"
        assert "climate" in r.features

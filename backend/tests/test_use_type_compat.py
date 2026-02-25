"""Exhaustive unit tests for the use-type compatibility matrix.

Covers:
 - Every combination in the 4-tier x 10-use-type matrix
 - Asymmetry rules (cold->storage OK, storage->cold NOT)
 - has_office_space flag overrides
 - Unknown / unrecognised tier and use_type values
 - Callout message content
 - Score boundary validation (scores must be in {0, 30, 60, 100})
"""

from __future__ import annotations

import pytest

from wex_platform.services.use_type_compat import (
    CAPABILITY_MAP,
    NEED_MAP,
    compute_use_type_score,
)

# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

ALL_TIERS = list(CAPABILITY_MAP.keys())
ALL_USE_TYPES = list(NEED_MAP.keys())
VALID_SCORES = {0, 30, 60, 100}


# ──────────────────────────────────────────────────────────────────────
# 1. Asymmetry rules (critical directional tests)
# ──────────────────────────────────────────────────────────────────────

class TestAsymmetryRules:
    """Cold-storage CAN serve plain storage; storage-only CANNOT serve cold."""

    def test_cold_warehouse_storage_buyer(self):
        """cold_storage warehouse + storage buyer -> 100 (overkill works)."""
        score, callouts = compute_use_type_score("cold_storage", "storage")
        assert score == 100

    def test_storage_only_warehouse_cold_buyer(self):
        """storage_only warehouse + cold_storage buyer -> 0 (no refrigeration)."""
        score, callouts = compute_use_type_score("storage_only", "cold_storage")
        assert score == 0

    def test_storage_office_warehouse_storage_buyer(self):
        """storage_office warehouse + storage buyer -> 100 (bonus office)."""
        score, callouts = compute_use_type_score("storage_office", "storage")
        assert score == 100

    def test_storage_only_warehouse_office_buyer(self):
        """storage_only warehouse + office buyer -> 0 (no office space)."""
        score, callouts = compute_use_type_score("storage_only", "office")
        assert score == 0

    def test_storage_light_warehouse_cold_buyer(self):
        """storage_light_assembly cannot serve cold_storage buyer."""
        score, _ = compute_use_type_score("storage_light_assembly", "cold_storage")
        assert score == 0

    def test_cold_warehouse_ecommerce_buyer(self):
        """cold_storage warehouse lacks light_assembly for ecommerce."""
        score, _ = compute_use_type_score("cold_storage", "ecommerce_fulfillment")
        assert score != 100  # cannot fully serve


# ──────────────────────────────────────────────────────────────────────
# 2. Exhaustive matrix: every tier x use_type combination
# ──────────────────────────────────────────────────────────────────────
#
# Expected scores are computed by hand from the CAPABILITY_MAP / NEED_MAP
# definitions and the scoring algorithm.

# Key:  (warehouse_tier, buyer_use_type) -> expected_score
EXPECTED_MATRIX: dict[tuple[str, str], int] = {
    # ── storage_only  caps={storage} ─────────────────────────────────
    ("storage_only", "storage"):               100,  # exact match
    ("storage_only", "storage_only"):          100,  # exact match (alias)
    ("storage_only", "office"):                  0,  # no overlap
    ("storage_only", "storage_office"):         30,  # overlap={storage}, missing={office} => 1 overlap < 1 missing? no, equal => 60... wait
    # overlap={storage}, missing={office}: len(overlap)=1 >= len(missing)=1 => 60
    ("storage_only", "storage_office"):         60,
    ("storage_only", "ecommerce_fulfillment"):  30,  # overlap={storage}, missing={light_assembly}: 1 >= 1 => 60
    # Actually: buyer needs {storage, light_assembly}. caps={storage}. overlap={storage}, missing={light_assembly}. 1>=1 => 60
    ("storage_only", "ecommerce_fulfillment"):  60,
    ("storage_only", "distribution"):          100,  # needs={storage}, exact
    ("storage_only", "cold_storage"):            0,  # needs={cold_storage}, caps={storage}, no overlap
    ("storage_only", "food_grade"):              0,  # needs={cold_storage, food_grade}, no overlap
    ("storage_only", "manufacturing_light"):     0,  # needs={light_assembly}, no overlap
    ("storage_only", "general"):               100,  # needs={storage}, exact

    # ── storage_office  caps={storage, office} ───────────────────────
    ("storage_office", "storage"):             100,  # superset
    ("storage_office", "storage_only"):        100,
    ("storage_office", "office"):              100,  # exact
    ("storage_office", "storage_office"):      100,  # exact
    ("storage_office", "ecommerce_fulfillment"): 60, # overlap={storage}, missing={light_assembly}, 1>=1 => 60
    ("storage_office", "distribution"):        100,  # superset
    ("storage_office", "cold_storage"):          0,  # no overlap (caps has no cold_storage)
    ("storage_office", "food_grade"):            0,  # no overlap
    ("storage_office", "manufacturing_light"):   0,  # no overlap
    ("storage_office", "general"):             100,  # superset

    # ── storage_light_assembly  caps={storage, light_assembly, ecommerce_fulfillment} ──
    ("storage_light_assembly", "storage"):             100,  # superset
    ("storage_light_assembly", "storage_only"):        100,
    ("storage_light_assembly", "office"):                0,  # no overlap
    ("storage_light_assembly", "storage_office"):       60,  # overlap={storage}, missing={office}, 1>=1
    ("storage_light_assembly", "ecommerce_fulfillment"):100, # superset (caps has storage + light_assembly)
    ("storage_light_assembly", "distribution"):        100,
    ("storage_light_assembly", "cold_storage"):          0,  # no overlap
    ("storage_light_assembly", "food_grade"):            0,  # no overlap
    ("storage_light_assembly", "manufacturing_light"): 100,  # caps has light_assembly, exact match
    ("storage_light_assembly", "general"):             100,

    # ── cold_storage  caps={storage, cold_storage, food_grade} ───────
    ("cold_storage", "storage"):               100,  # superset
    ("cold_storage", "storage_only"):          100,
    ("cold_storage", "office"):                  0,  # no overlap
    ("cold_storage", "storage_office"):         60,  # overlap={storage}, missing={office}, 1>=1
    ("cold_storage", "ecommerce_fulfillment"):  60,  # overlap={storage}, missing={light_assembly}, 1>=1
    ("cold_storage", "distribution"):          100,  # superset
    ("cold_storage", "cold_storage"):          100,  # exact
    ("cold_storage", "food_grade"):            100,  # exact
    ("cold_storage", "manufacturing_light"):     0,  # no overlap (no light_assembly)
    ("cold_storage", "general"):               100,
}

# De-duplicate: the dict literal above has repeated keys for storage_only rows
# where I corrected myself. Python keeps the last value, which is correct.


@pytest.mark.parametrize(
    "tier,use_type,expected_score",
    [
        (tier, use_type, EXPECTED_MATRIX[(tier, use_type)])
        for tier in ALL_TIERS
        for use_type in ALL_USE_TYPES
    ],
    ids=[
        f"{tier}--{use_type}"
        for tier in ALL_TIERS
        for use_type in ALL_USE_TYPES
    ],
)
class TestExhaustiveMatrix:
    """Parametrised test for every cell in the compatibility matrix."""

    def test_score(self, tier: str, use_type: str, expected_score: int):
        score, _ = compute_use_type_score(tier, use_type)
        assert score == expected_score, (
            f"compute_use_type_score({tier!r}, {use_type!r}) "
            f"returned score {score}, expected {expected_score}"
        )

    def test_score_in_valid_set(self, tier: str, use_type: str, expected_score: int):
        score, _ = compute_use_type_score(tier, use_type)
        assert score in VALID_SCORES, (
            f"Score {score} for ({tier!r}, {use_type!r}) is not in {VALID_SCORES}"
        )


# ──────────────────────────────────────────────────────────────────────
# 3. has_office_space flag
# ──────────────────────────────────────────────────────────────────────

class TestHasOfficeSpaceFlag:

    def test_storage_only_office_buyer_with_office(self):
        """storage_only + office buyer + has_office_space=True -> 100."""
        score, _ = compute_use_type_score("storage_only", "office", has_office_space=True)
        assert score == 100

    def test_storage_only_office_buyer_without_office(self):
        """storage_only + office buyer + has_office_space=False -> 0."""
        score, _ = compute_use_type_score("storage_only", "office", has_office_space=False)
        assert score == 0

    def test_storage_only_storage_office_buyer_with_office(self):
        """storage_only + storage_office buyer + has_office_space=True -> 100."""
        score, _ = compute_use_type_score("storage_only", "storage_office", has_office_space=True)
        assert score == 100

    def test_storage_only_storage_office_buyer_without_office(self):
        """storage_only + storage_office buyer + has_office_space=False -> 60."""
        score, _ = compute_use_type_score("storage_only", "storage_office", has_office_space=False)
        assert score == 60

    def test_cold_storage_office_buyer_with_office(self):
        """cold_storage + office buyer + has_office_space=True -> 100."""
        score, _ = compute_use_type_score("cold_storage", "office", has_office_space=True)
        assert score == 100

    def test_cold_storage_office_buyer_without_office(self):
        """cold_storage + office buyer + has_office_space=False -> 0."""
        score, _ = compute_use_type_score("cold_storage", "office", has_office_space=False)
        assert score == 0

    def test_office_flag_does_not_affect_already_capable(self):
        """storage_office already has office; flag should not change score."""
        score_without, _ = compute_use_type_score("storage_office", "office", has_office_space=False)
        score_with, _ = compute_use_type_score("storage_office", "office", has_office_space=True)
        assert score_without == score_with == 100

    def test_office_flag_default_is_false(self):
        """Default has_office_space should be False."""
        score_default, _ = compute_use_type_score("storage_only", "office")
        score_explicit, _ = compute_use_type_score("storage_only", "office", has_office_space=False)
        assert score_default == score_explicit


# ──────────────────────────────────────────────────────────────────────
# 4. Unknown tier / use_type
# ──────────────────────────────────────────────────────────────────────

class TestUnknownValues:

    def test_unknown_tier(self):
        score, callouts = compute_use_type_score("nonexistent_tier", "storage")
        assert score == 0
        assert any("Unknown" in c or "unknown" in c.lower() for c in callouts)

    def test_unknown_use_type(self):
        score, callouts = compute_use_type_score("storage_only", "nonexistent_use")
        assert score == 0
        assert any("Unknown" in c or "unknown" in c.lower() for c in callouts)

    def test_both_unknown(self):
        score, callouts = compute_use_type_score("made_up", "also_made_up")
        assert score == 0

    def test_empty_string_tier(self):
        score, callouts = compute_use_type_score("", "storage")
        assert score == 0

    def test_empty_string_use_type(self):
        score, callouts = compute_use_type_score("storage_only", "")
        assert score == 0

    def test_unknown_returns_valid_score(self):
        score, _ = compute_use_type_score("???", "???")
        assert score in VALID_SCORES


# ──────────────────────────────────────────────────────────────────────
# 5. Callout messages
# ──────────────────────────────────────────────────────────────────────

class TestCalloutMessages:

    def test_bonus_office_callout(self):
        """storage_office serving plain storage should mention bonus office."""
        _, callouts = compute_use_type_score("storage_office", "storage")
        assert any("Bonus" in c and "office" in c.lower() for c in callouts)

    def test_no_office_callout(self):
        """storage_only serving storage_office buyer should mention no office."""
        score, callouts = compute_use_type_score("storage_only", "storage_office")
        assert score == 60
        assert any("office" in c.lower() for c in callouts)

    def test_no_cold_storage_callout(self):
        """storage_only serving cold_storage buyer -> incompatible callout."""
        _, callouts = compute_use_type_score("storage_only", "cold_storage")
        assert len(callouts) > 0  # must have at least one callout

    def test_perfect_match_no_negative_callouts(self):
        """Exact match should have no 'No ...' callouts."""
        _, callouts = compute_use_type_score("storage_only", "storage")
        assert not any(c.startswith("No ") for c in callouts)

    def test_bonus_cold_storage_callouts(self):
        """cold_storage serving storage buyer should list bonus capabilities."""
        _, callouts = compute_use_type_score("cold_storage", "storage")
        joined = " ".join(callouts).lower()
        assert "cold" in joined or "food" in joined

    def test_missing_light_assembly_callout(self):
        """cold_storage serving ecommerce buyer should mention missing assembly."""
        score, callouts = compute_use_type_score("cold_storage", "ecommerce_fulfillment")
        assert score == 60
        joined = " ".join(callouts).lower()
        assert "assembly" in joined or "light" in joined

    def test_incompatible_callout_text(self):
        """Incompatible pairing should say 'Incompatible'."""
        _, callouts = compute_use_type_score("storage_only", "cold_storage")
        assert any("Incompatible" in c for c in callouts)

    def test_callouts_are_strings(self):
        """All callouts must be strings."""
        for tier in ALL_TIERS:
            for use_type in ALL_USE_TYPES:
                _, callouts = compute_use_type_score(tier, use_type)
                assert isinstance(callouts, list)
                for c in callouts:
                    assert isinstance(c, str)


# ──────────────────────────────────────────────────────────────────────
# 6. Score boundaries
# ──────────────────────────────────────────────────────────────────────

class TestScoreBoundaries:

    @pytest.mark.parametrize("tier", ALL_TIERS)
    @pytest.mark.parametrize("use_type", ALL_USE_TYPES)
    def test_score_in_valid_set(self, tier: str, use_type: str):
        score, _ = compute_use_type_score(tier, use_type)
        assert score in VALID_SCORES, (
            f"({tier}, {use_type}) yielded score {score} not in {VALID_SCORES}"
        )

    @pytest.mark.parametrize("tier", ALL_TIERS)
    @pytest.mark.parametrize("use_type", ALL_USE_TYPES)
    def test_score_non_negative(self, tier: str, use_type: str):
        score, _ = compute_use_type_score(tier, use_type)
        assert score >= 0

    @pytest.mark.parametrize("tier", ALL_TIERS)
    @pytest.mark.parametrize("use_type", ALL_USE_TYPES)
    def test_score_max_100(self, tier: str, use_type: str):
        score, _ = compute_use_type_score(tier, use_type)
        assert score <= 100

    def test_office_flag_scores_in_valid_set(self):
        for tier in ALL_TIERS:
            for use_type in ALL_USE_TYPES:
                for flag in (True, False):
                    score, _ = compute_use_type_score(tier, use_type, has_office_space=flag)
                    assert score in VALID_SCORES

    def test_unknown_score_in_valid_set(self):
        score, _ = compute_use_type_score("unknown", "unknown")
        assert score in VALID_SCORES


# ──────────────────────────────────────────────────────────────────────
# 7. Return type contract
# ──────────────────────────────────────────────────────────────────────

class TestReturnTypeContract:

    def test_returns_tuple(self):
        result = compute_use_type_score("storage_only", "storage")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_first_element_is_int(self):
        score, _ = compute_use_type_score("storage_only", "storage")
        assert isinstance(score, int)

    def test_second_element_is_list(self):
        _, callouts = compute_use_type_score("storage_only", "storage")
        assert isinstance(callouts, list)


# ──────────────────────────────────────────────────────────────────────
# 8. No accidental routing (specific dangerous mis-routes)
# ──────────────────────────────────────────────────────────────────────

class TestNoAccidentalRouting:
    """Verify that known-dangerous combinations score 0."""

    def test_dry_warehouse_cold_storage_buyer(self):
        """A dry (storage_only) warehouse must NOT route to cold_storage buyer."""
        score, _ = compute_use_type_score("storage_only", "cold_storage")
        assert score == 0

    def test_dry_warehouse_food_grade_buyer(self):
        score, _ = compute_use_type_score("storage_only", "food_grade")
        assert score == 0

    def test_office_tier_cold_buyer(self):
        score, _ = compute_use_type_score("storage_office", "cold_storage")
        assert score == 0

    def test_office_tier_food_grade_buyer(self):
        score, _ = compute_use_type_score("storage_office", "food_grade")
        assert score == 0

    def test_light_assembly_cold_buyer(self):
        score, _ = compute_use_type_score("storage_light_assembly", "cold_storage")
        assert score == 0

    def test_light_assembly_food_grade_buyer(self):
        score, _ = compute_use_type_score("storage_light_assembly", "food_grade")
        assert score == 0

    def test_cold_warehouse_manufacturing_buyer(self):
        """Cold warehouse has no light_assembly capability."""
        score, _ = compute_use_type_score("cold_storage", "manufacturing_light")
        assert score == 0

    def test_storage_only_manufacturing_buyer(self):
        score, _ = compute_use_type_score("storage_only", "manufacturing_light")
        assert score == 0

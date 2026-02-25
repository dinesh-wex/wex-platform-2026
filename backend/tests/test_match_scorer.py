"""Comprehensive unit tests for the deterministic MCDA match scorer."""

from __future__ import annotations

import math
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from wex_platform.services.match_scorer import (
    KNN_MAX_CAP,
    NEUTRAL,
    W_BUDGET,
    W_FEATURE,
    W_LOCATION,
    W_SIZE,
    W_TIMING,
    W_USE_TYPE,
    _compute_budget_score,
    _compute_timing_score,
    apply_budget_context,
    compute_composite_score,
    recompute_with_feature_score,
)


# ---------------------------------------------------------------------------
# Helpers to build minimal dicts
# ---------------------------------------------------------------------------

def _buyer(
    lat=40.0, lng=-74.0, radius_miles=25,
    min_sqft=None, max_sqft=None,
    use_type="general", needed_from=None,
    max_budget_per_sqft=None,
):
    d = {
        "city": "TestCity", "state": "TS",
        "lat": lat, "lng": lng,
        "radius_miles": radius_miles,
        "min_sqft": min_sqft, "max_sqft": max_sqft,
        "use_type": use_type,
        "needed_from": needed_from,
        "max_budget_per_sqft": max_budget_per_sqft,
    }
    return d


def _warehouse(lat=40.0, lng=-74.0, building_size_sqft=10000):
    return {
        "id": "wh-1",
        "address": "123 Test St",
        "city": "TestCity", "state": "TS",
        "lat": lat, "lng": lng,
        "building_size_sqft": building_size_sqft,
    }


def _tc(
    min_sqft=5000, max_sqft=20000,
    activity_tier="storage_only",
    supplier_rate_per_sqft=None,
    has_office_space=False,
    available_from=None,
    clear_height_ft=24,
    dock_doors_receiving=4,
):
    return {
        "min_sqft": min_sqft, "max_sqft": max_sqft,
        "activity_tier": activity_tier,
        "supplier_rate_per_sqft": supplier_rate_per_sqft,
        "has_office_space": has_office_space,
        "available_from": available_from,
        "clear_height_ft": clear_height_ft,
        "dock_doors_receiving": dock_doors_receiving,
    }


# We need a helper to compute haversine offsets for precise distance control.
# Earth radius ~ 3958.8 mi; 1 degree lat ~ 69.05 mi at equator-ish latitudes.
def _offset_lat_for_miles(base_lat, miles):
    """Return a latitude that is *miles* due-north of *base_lat*."""
    # 1 degree of latitude ~ 69.05 miles
    return base_lat + miles / 69.05


# ═══════════════════════════════════════════════════════════════════════════
# 1. Location Score
# ═══════════════════════════════════════════════════════════════════════════

class TestLocationScore:
    """Tests 1-6: location dimension scoring."""

    def test_same_spot_gives_100(self):
        """#1  dist=0  -> location_score = 100."""
        result = compute_composite_score(
            _buyer(lat=40.0, lng=-74.0),
            _warehouse(lat=40.0, lng=-74.0),
            _tc(),
        )
        assert result["location_score"] == 100.0
        assert result["distance_miles"] == 0.0

    def test_half_radius_gives_about_50(self):
        """#2  Warehouse at half the buyer radius -> ~50."""
        radius = 25
        half_dist = radius / 2  # 12.5 mi
        wh_lat = _offset_lat_for_miles(40.0, half_dist)
        result = compute_composite_score(
            _buyer(lat=40.0, lng=-74.0, radius_miles=radius),
            _warehouse(lat=wh_lat, lng=-74.0),
            _tc(),
        )
        # Score = 100 * (1 - dist/radius).  dist ~ 12.5 -> score ~ 50
        assert 45 <= result["location_score"] <= 55

    def test_edge_of_radius_gives_about_0(self):
        """#3  Warehouse at edge of radius -> ~0.

        When dist is just under the radius, effective_denominator = radius,
        so score = 100 * (1 - dist/radius) which approaches 0.
        We place the warehouse at 99% of the radius to stay inside the
        radius branch (dist <= radius) and get a near-zero score.
        """
        radius = 25
        almost_radius = radius * 0.99  # 24.75 mi -- stays inside radius branch
        wh_lat = _offset_lat_for_miles(40.0, almost_radius)
        result = compute_composite_score(
            _buyer(lat=40.0, lng=-74.0, radius_miles=radius),
            _warehouse(lat=wh_lat, lng=-74.0),
            _tc(),
        )
        # score = 100 * (1 - ~24.75/25) ~ 1.0
        assert result["location_score"] <= 5.0

    def test_knn_match_uses_cap_denominator(self):
        """#4  KNN match at 45 mi with buyer radius 25 -> score ~ 55."""
        radius = 25
        dist_target = 45
        wh_lat = _offset_lat_for_miles(40.0, dist_target)
        result = compute_composite_score(
            _buyer(lat=40.0, lng=-74.0, radius_miles=radius),
            _warehouse(lat=wh_lat, lng=-74.0),
            _tc(),
        )
        # dist > radius -> effective_denominator = KNN_MAX_CAP = 100
        # score = 100 * (1 - 45/100) = 55.0
        assert 53.0 <= result["location_score"] <= 57.0
        assert result["distance_miles"] is not None
        assert 43.0 <= result["distance_miles"] <= 47.0

    def test_missing_buyer_coords_gives_neutral(self):
        """#5  Missing coords on buyer -> 50 (neutral)."""
        result = compute_composite_score(
            _buyer(lat=None, lng=None),
            _warehouse(lat=40.0, lng=-74.0),
            _tc(),
        )
        assert result["location_score"] == NEUTRAL
        assert result["distance_miles"] is None

    def test_missing_warehouse_coords_gives_neutral(self):
        """#6  Missing coords on warehouse -> 50 (neutral)."""
        result = compute_composite_score(
            _buyer(lat=40.0, lng=-74.0),
            _warehouse(lat=None, lng=None),
            _tc(),
        )
        assert result["location_score"] == NEUTRAL
        assert result["distance_miles"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. Size Score
# ═══════════════════════════════════════════════════════════════════════════

class TestSizeScore:
    """Tests 7-11: size dimension scoring."""

    def test_exact_match_gives_100(self):
        """#7  Buyer wants 10K, warehouse range includes 10K -> 100."""
        result = compute_composite_score(
            _buyer(min_sqft=8000, max_sqft=12000),
            _warehouse(),
            _tc(min_sqft=5000, max_sqft=20000),
        )
        # buyer_target = (8000+12000)/2 = 10000
        # best_fit = max(5000, min(20000, 10000)) = 10000
        # ratio = 1.0 -> within [0.8, 1.2] -> 100
        assert result["size_score"] == 100.0

    def test_single_point_request_gives_100(self):
        """#8  min=max=10000, warehouse range includes it -> 100."""
        result = compute_composite_score(
            _buyer(min_sqft=10000, max_sqft=10000),
            _warehouse(),
            _tc(min_sqft=5000, max_sqft=20000),
        )
        # buyer_min == buyer_max -> buyer_target = 10000 (first branch: min != max is False, so elif buyer_min -> 10000)
        # best_fit = max(5000, min(20000, 10000)) = 10000, ratio=1.0 -> 100
        assert result["size_score"] == 100.0

    def test_warehouse_too_small_penalty(self):
        """#9  Warehouse too small -> drops with 250x penalty factor."""
        result = compute_composite_score(
            _buyer(min_sqft=8000, max_sqft=12000),
            _warehouse(),
            _tc(min_sqft=2000, max_sqft=3000),  # way too small
        )
        # buyer_target = 10000, best_fit = max(2000, min(3000, 10000)) = 3000
        # ratio = 0.3, score = max(0, 100 - (0.8-0.3)*250) = max(0, 100-125) = 0
        assert result["size_score"] == 0.0

    def test_warehouse_oversized_gentle_penalty(self):
        """#10  Warehouse way oversized -> gentle penalty with 100x factor."""
        result = compute_composite_score(
            _buyer(min_sqft=8000, max_sqft=12000),
            _warehouse(),
            _tc(min_sqft=15000, max_sqft=18000),  # all above target
        )
        # buyer_target = 10000, best_fit = max(15000, min(18000, 10000)) = 15000
        # ratio = 1.5, score = max(0, 100 - (1.5-1.2)*100) = max(0, 100-30) = 70
        assert result["size_score"] == 70.0

    def test_no_buyer_target_gives_neutral(self):
        """#11  No buyer target -> 50."""
        result = compute_composite_score(
            _buyer(min_sqft=None, max_sqft=None),
            _warehouse(),
            _tc(),
        )
        assert result["size_score"] == NEUTRAL


# ═══════════════════════════════════════════════════════════════════════════
# 3. Budget Score (Continuous Decay)
# ═══════════════════════════════════════════════════════════════════════════

class TestBudgetScore:
    """Tests 12-17: budget dimension scoring."""

    def test_on_budget_gives_100(self):
        """#12  On budget -> 100."""
        # buyer_rate = ceil(5.00 * 1.20 * 1.06 * 100) / 100
        #            = ceil(636.0) / 100 = 6.36
        # Set buyer max to 6.36 -> exactly on budget
        supplier_rate = 5.00
        buyer_rate = math.ceil(supplier_rate * 1.20 * 1.06 * 100) / 100
        result = compute_composite_score(
            _buyer(max_budget_per_sqft=buyer_rate),
            _warehouse(),
            _tc(supplier_rate_per_sqft=supplier_rate),
        )
        assert result["budget_score"] == 100.0
        assert result["within_budget"] is True

    def test_15pct_over_gives_about_50(self):
        """#13  15% over budget -> ~50."""
        # We need buyer_rate to be 15% over buyer_max.
        # score = max(0, 100 - percent_over * 3.33) = 100 - 15*3.33 = 100 - 49.95 = 50.05
        # To achieve exactly 15% over: buyer_rate = buyer_max * 1.15
        # buyer_rate = ceil(supplier * 1.272 * 100)/100
        # Let's pick buyer_max = 10.0, so buyer_rate needs to be 11.50
        # supplier * 1.272 = 11.50 -> supplier = 9.04...
        # Actually let's compute it directly via _compute_budget_score
        buyer_max = 10.0
        # We want buyer_rate = 11.50 exactly (15% over)
        # buyer_rate = ceil(supplier * 1.272 * 100) / 100 = 11.50
        # supplier * 127.2 needs ceil to be 1150 -> supplier * 127.2 in (1149, 1150]
        # supplier = 1150 / 127.2 = 9.04088...
        # ceil(9.04088... * 127.2) = ceil(1150.0) = 1150 -> buyer_rate = 11.50  ✓
        supplier_rate = 1150 / 127.2  # ~ 9.04088...
        buyer_rate_check = math.ceil(supplier_rate * 1.20 * 1.06 * 100) / 100
        assert buyer_rate_check == 11.50

        score, within, stretch = _compute_budget_score(buyer_max, supplier_rate)
        assert within is False
        # percent_over = (11.50 - 10.0)/10.0 * 100 = 15.0
        # score = 100 - 15.0 * 3.33 = 50.05
        assert 49.0 <= score <= 51.0

    def test_30pct_over_gives_0(self):
        """#14  30% over budget -> 0."""
        buyer_max = 10.0
        # buyer_rate = 13.0 -> 30% over
        # supplier * 1.272 * 100 -> ceil -> 1300
        # supplier = 1300 / 127.2 = 10.22012...
        supplier_rate = 1300 / 127.2
        buyer_rate_check = math.ceil(supplier_rate * 1.20 * 1.06 * 100) / 100
        assert buyer_rate_check == 13.00

        score, within, stretch = _compute_budget_score(buyer_max, supplier_rate)
        assert within is False
        # percent_over = 30.0, score = 100 - 30*3.33 = 0.1 -> but could be 0 due to max(0, ...)
        # Actually 100 - 99.9 = 0.1, so score = 0.1
        assert score <= 1.0  # effectively 0

    def test_5pct_over_gives_about_83(self):
        """#15  5% over -> ~83.3."""
        buyer_max = 10.0
        # buyer_rate = 10.50 -> 5% over
        # supplier * 127.2 -> ceil -> 1050
        supplier_rate = 1050 / 127.2
        buyer_rate_check = math.ceil(supplier_rate * 1.20 * 1.06 * 100) / 100
        assert buyer_rate_check == 10.50

        score, within, stretch = _compute_budget_score(buyer_max, supplier_rate)
        assert within is False
        # percent_over = 5.0, score = 100 - 5*3.33 = 83.35
        assert 82.0 <= score <= 85.0

    def test_no_budget_stated_gives_neutral(self):
        """#16  No budget -> 50."""
        score, within, stretch = _compute_budget_score(None, 5.0)
        assert score == NEUTRAL
        assert within is True

    def test_wex_pricing_formula(self):
        """#17  Verify: buyer_rate = ceil(supplier * 1.20 * 1.06 * 100) / 100.

        Note: floating-point multiplication may push e.g. 7.50*1.20*1.06*100
        to 954.000...001, causing ceil to return 955 instead of 954.  The
        formula is intentionally ceil-based, so we just verify the formula
        is applied consistently and that on-budget means score 100.
        """
        for supplier in (5.00, 7.50, 7.53, 10.00, 12.99):
            buyer_rate = math.ceil(supplier * 1.20 * 1.06 * 100) / 100
            # Confirm the scorer yields 100 when buyer_max == buyer_rate
            score, within, _ = _compute_budget_score(buyer_rate, supplier)
            assert score == 100.0, f"supplier={supplier}, buyer_rate={buyer_rate}"
            assert within is True

        # Verify the formula is strictly ceiling (never floors)
        supplier = 7.53
        buyer_rate = math.ceil(supplier * 1.20 * 1.06 * 100) / 100
        raw = supplier * 1.20 * 1.06
        assert buyer_rate >= raw  # ceil always >= raw


# ═══════════════════════════════════════════════════════════════════════════
# 4. Timing Score
# ═══════════════════════════════════════════════════════════════════════════

class TestTimingScore:
    """Tests 18-21: timing dimension scoring."""

    def test_now_asap_gives_100(self):
        """#18  Warehouse 'Now', buyer 'ASAP' -> 100."""
        score = _compute_timing_score("ASAP", "Now")
        assert score == 100.0

    def test_available_before_needed_gives_100(self):
        """#19  Warehouse available before buyer needs -> 100."""
        score = _compute_timing_score("2026-06-01", "2026-05-01")
        assert score == 100.0

    def test_30_days_late_gives_70(self):
        """#20  Warehouse available 30 days after buyer needs -> 70."""
        need = date(2026, 6, 1)
        avail = need + timedelta(days=30)
        score = _compute_timing_score(need.isoformat(), avail.isoformat())
        assert score == 70.0

    def test_60_days_late_gives_40(self):
        """#21  Warehouse available 60 days after -> 40."""
        need = date(2026, 6, 1)
        avail = need + timedelta(days=60)
        score = _compute_timing_score(need.isoformat(), avail.isoformat())
        assert score == 40.0


# ═══════════════════════════════════════════════════════════════════════════
# 5. Composite Score
# ═══════════════════════════════════════════════════════════════════════════

class TestCompositeScore:
    """Tests 22-23: composite scoring and recompute."""

    def test_composite_is_weighted_sum(self):
        """#22  Full composite with known dimension scores -> verify weighted sum."""
        result = compute_composite_score(
            _buyer(lat=40.0, lng=-74.0, radius_miles=25,
                   min_sqft=8000, max_sqft=12000,
                   max_budget_per_sqft=None),
            _warehouse(lat=40.0, lng=-74.0),
            _tc(min_sqft=5000, max_sqft=20000),
        )
        # location=100, size=100, feature=50 (placeholder), timing=100, budget=50 (no budget)
        # use_type we just read from result
        expected = round(
            result["location_score"] * W_LOCATION
            + result["size_score"] * W_SIZE
            + result["use_type_score"] * W_USE_TYPE
            + result["feature_score"] * W_FEATURE
            + result["timing_score"] * W_TIMING
            + result["budget_score"] * W_BUDGET,
            1,
        )
        assert result["composite_score"] == expected

    def test_recompute_with_feature_score(self):
        """#23  recompute_with_feature_score replaces placeholder and recalculates."""
        original = compute_composite_score(
            _buyer(), _warehouse(), _tc(),
        )
        assert original["feature_score"] == NEUTRAL

        updated = recompute_with_feature_score(original, 90)
        assert updated["feature_score"] == 90
        assert updated is not original  # new dict

        expected_composite = round(
            updated["location_score"] * W_LOCATION
            + updated["size_score"] * W_SIZE
            + updated["use_type_score"] * W_USE_TYPE
            + 90 * W_FEATURE
            + updated["timing_score"] * W_TIMING
            + updated["budget_score"] * W_BUDGET,
            1,
        )
        assert updated["composite_score"] == expected_composite
        # Composite should differ from original (feature went from 50 to 90)
        assert updated["composite_score"] != original["composite_score"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. Budget Context
# ═══════════════════════════════════════════════════════════════════════════

class TestBudgetContext:
    """Tests 24-26: apply_budget_context tagging."""

    def test_all_over_budget_flags_first_result(self):
        """#24  All over budget -> first result gets budget_alternative_available."""
        results = [
            {"within_budget": False, "budget_stretch_pct": 15.0},
            {"within_budget": False, "budget_stretch_pct": 20.0},
            {"within_budget": False, "budget_stretch_pct": 25.0},
        ]
        tagged = apply_budget_context(results, 10.0)
        assert tagged[0].get("budget_alternative_available") is True
        assert "budget_alternative_available" not in tagged[1]
        assert "budget_alternative_available" not in tagged[2]

    def test_some_within_budget_no_flag(self):
        """#25  Some within budget -> no budget_alternative_available flag."""
        results = [
            {"within_budget": True, "budget_stretch_pct": 0.0},
            {"within_budget": False, "budget_stretch_pct": 20.0},
        ]
        tagged = apply_budget_context(results, 10.0)
        for r in tagged:
            assert "budget_alternative_available" not in r

    def test_no_budget_no_tagging(self):
        """#26  No budget provided -> no budget_alternative_available tagging."""
        results = [{"some_key": "val"}, {"some_key": "val2"}]
        tagged = apply_budget_context(results, None)
        for r in tagged:
            assert r["within_budget"] is True
            assert r["budget_stretch_pct"] == 0.0
            assert "budget_alternative_available" not in r


# ═══════════════════════════════════════════════════════════════════════════
# 7. Return Shape
# ═══════════════════════════════════════════════════════════════════════════

class TestReturnShape:
    """Tests 27-28: output dict structure and value ranges."""

    EXPECTED_KEYS = {
        "composite_score", "location_score", "size_score", "use_type_score",
        "feature_score", "timing_score", "budget_score",
        "distance_miles", "within_budget", "budget_stretch_pct",
        "use_type_callouts",
    }

    def test_all_expected_keys_present(self):
        """#27  All expected keys present in return dict."""
        result = compute_composite_score(
            _buyer(), _warehouse(), _tc(),
        )
        assert self.EXPECTED_KEYS == set(result.keys())

    def test_all_scores_between_0_and_100(self):
        """#28  All numeric scores between 0 and 100."""
        score_keys = [
            "composite_score", "location_score", "size_score",
            "use_type_score", "feature_score", "timing_score", "budget_score",
        ]
        # Test with several different configurations
        configs = [
            (_buyer(), _warehouse(), _tc()),
            (_buyer(lat=None, lng=None, min_sqft=None, max_sqft=None), _warehouse(), _tc()),
            (_buyer(max_budget_per_sqft=1.0), _warehouse(), _tc(supplier_rate_per_sqft=50.0)),
        ]
        for buyer, wh, tc in configs:
            result = compute_composite_score(buyer, wh, tc)
            for key in score_keys:
                val = result[key]
                assert 0 <= val <= 100, f"{key}={val} out of range for config"

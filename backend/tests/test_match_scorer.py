"""Comprehensive unit tests for the deterministic MCDA match scorer."""

from __future__ import annotations

import math
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from wex_platform.services.match_scorer import (
    KNN_MAX_CAP,
    NEUTRAL,
    TIER_MULTIPLIERS,
    W_FEATURE,
    W_LOCATION,
    W_SIZE,
    W_TIMING,
    W_USE_TYPE,
    W_VALUE,
    _compute_timing_score,
    _compute_value_score,
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
):
    d = {
        "city": "TestCity", "state": "TS",
        "lat": lat, "lng": lng,
        "radius_miles": radius_miles,
        "min_sqft": min_sqft, "max_sqft": max_sqft,
        "use_type": use_type,
        "needed_from": needed_from,
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
    generic_market_avg=None,
    has_office_space=False,
    available_from=None,
    clear_height_ft=24,
    dock_doors_receiving=4,
):
    return {
        "min_sqft": min_sqft, "max_sqft": max_sqft,
        "activity_tier": activity_tier,
        "supplier_rate_per_sqft": supplier_rate_per_sqft,
        "generic_market_avg": generic_market_avg,
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
        # Score = 100 * (1 - dist/radius) + 10 city bonus.  dist ~ 12.5 -> ~50 + 10 = 60
        assert 55 <= result["location_score"] <= 65

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
        # score = 100 * (1 - ~24.75/25) + 10 city bonus ~ 11.0
        assert result["location_score"] <= 15.0

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
        # score = 100 * (1 - 45/100) + 10 city bonus = 65.0
        assert 63.0 <= result["location_score"] <= 67.0
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
# 3. Value Score (Market Competitiveness — Index + Coefficient Model)
# ═══════════════════════════════════════════════════════════════════════════

class TestValueScore:
    """Tests for value dimension scoring using tier-adjusted market avg."""

    def test_at_market_avg_storage_only(self):
        """Supplier priced exactly at market for storage_only -> 70."""
        score = _compute_value_score(1.00, 1.00, "storage_only")
        assert score == 70.0

    def test_30pct_below_market_caps_at_100(self):
        """30% below market -> 100 (capped)."""
        score = _compute_value_score(0.70, 1.00, "storage_only")
        assert score == 100.0

    def test_20pct_above_market_gives_50(self):
        """20% above market -> 50."""
        score = _compute_value_score(1.20, 1.00, "storage_only")
        assert score == 50.0

    def test_70pct_above_market_floors_at_0(self):
        """70%+ above market -> 0 (floored)."""
        score = _compute_value_score(1.70, 1.00, "storage_only")
        assert score == 0.0

    def test_cold_storage_fair_pricing(self):
        """Cold storage at $2.50 with $1.00 generic avg -> 70 (adjusted avg = $2.50)."""
        score = _compute_value_score(2.50, 1.00, "cold_storage")
        assert score == 70.0

    def test_cold_storage_good_deal(self):
        """Cold storage at $2.00 with $1.00 generic avg -> 90 (20% below adjusted $2.50)."""
        score = _compute_value_score(2.00, 1.00, "cold_storage")
        assert score == 90.0

    def test_dry_shed_overpriced(self):
        """Dry shed at $2.50 with $1.00 avg -> 0 (150% over adjusted $1.00)."""
        score = _compute_value_score(2.50, 1.00, "storage_only")
        assert score == 0.0

    def test_unknown_tier_defaults_to_1x(self):
        """Unknown activity_tier falls back to 1.0 multiplier."""
        score = _compute_value_score(1.00, 1.00, "unknown_tier")
        assert score == 70.0

    def test_null_supplier_rate_gives_neutral(self):
        """No supplier rate -> NEUTRAL (50)."""
        score = _compute_value_score(None, 1.00, "storage_only")
        assert score == 50.0

    def test_null_market_avg_gives_neutral(self):
        """No market data -> NEUTRAL (50)."""
        score = _compute_value_score(1.00, None, "storage_only")
        assert score == 50.0

    def test_null_activity_tier_defaults_to_1x(self):
        """None activity_tier defaults to 1.0 multiplier."""
        score = _compute_value_score(1.00, 1.00, None)
        assert score == 70.0

    def test_storage_office_premium(self):
        """Storage+office at $1.15 with $1.00 avg -> 70 (exactly at adjusted avg)."""
        score = _compute_value_score(1.15, 1.00, "storage_office")
        assert score == 70.0

    def test_food_grade_premium(self):
        """Food grade at $1.80 with $1.00 avg -> 70 (exactly at adjusted avg)."""
        score = _compute_value_score(1.80, 1.00, "food_grade")
        assert score == 70.0

    def test_tier_multipliers_complete(self):
        """All expected tiers are present in TIER_MULTIPLIERS."""
        expected_tiers = {"storage_only", "storage_office", "storage_light_assembly", "food_grade", "cold_storage"}
        assert set(TIER_MULTIPLIERS.keys()) == expected_tiers


# ═══════════════════════════════════════════════════════════════════════════
# 4. Timing Score (Continuous Linear Decay)
# ═══════════════════════════════════════════════════════════════════════════

class TestTimingScore:
    """Tests for continuous timing dimension scoring."""

    def test_now_asap_gives_100(self):
        """Warehouse 'Now', buyer 'ASAP' -> 100."""
        score = _compute_timing_score("ASAP", "Now")
        assert score == 100.0

    def test_available_before_needed_gives_100(self):
        """Warehouse available before buyer needs -> 100."""
        score = _compute_timing_score("2026-06-01", "2026-05-01")
        assert score == 100.0

    def test_exact_date_gives_100(self):
        """Available on exact date -> 100."""
        score = _compute_timing_score("2026-06-01", "2026-06-01")
        assert score == 100.0

    def test_1_day_late_gives_99(self):
        """1 day late -> 99 (continuous, not 70!)."""
        need = date(2026, 6, 1)
        avail = need + timedelta(days=1)
        score = _compute_timing_score(need.isoformat(), avail.isoformat())
        assert score == 99.0

    def test_15_days_late_gives_85(self):
        """15 days late -> 85."""
        need = date(2026, 6, 1)
        avail = need + timedelta(days=15)
        score = _compute_timing_score(need.isoformat(), avail.isoformat())
        assert score == 85.0

    def test_30_days_late_gives_70(self):
        """30 days late -> 70 (anchor point preserved)."""
        need = date(2026, 6, 1)
        avail = need + timedelta(days=30)
        score = _compute_timing_score(need.isoformat(), avail.isoformat())
        assert score == 70.0

    def test_31_days_late_gives_69(self):
        """31 days late -> 69 (no cliff! was 40 in old staircase)."""
        need = date(2026, 6, 1)
        avail = need + timedelta(days=31)
        score = _compute_timing_score(need.isoformat(), avail.isoformat())
        assert score == 69.0

    def test_60_days_late_gives_40(self):
        """60 days late -> 40 (anchor point preserved)."""
        need = date(2026, 6, 1)
        avail = need + timedelta(days=60)
        score = _compute_timing_score(need.isoformat(), avail.isoformat())
        assert score == 40.0

    def test_90_days_late_gives_10(self):
        """90 days late -> 10 (floor reached)."""
        need = date(2026, 6, 1)
        avail = need + timedelta(days=90)
        score = _compute_timing_score(need.isoformat(), avail.isoformat())
        assert score == 10.0

    def test_120_days_late_stays_at_floor(self):
        """120 days late -> still 10 (floor)."""
        need = date(2026, 6, 1)
        avail = need + timedelta(days=120)
        score = _compute_timing_score(need.isoformat(), avail.isoformat())
        assert score == 10.0

    def test_no_available_from_gives_100(self):
        """No available_from -> 100 (unknown = no friction)."""
        score = _compute_timing_score("2026-06-01", None)
        assert score == 100.0

    def test_no_needed_from_gives_100(self):
        """No needed_from -> 100 (no target = no friction)."""
        score = _compute_timing_score(None, "2026-06-01")
        assert score == 100.0


# ═══════════════════════════════════════════════════════════════════════════
# 5. Composite Score
# ═══════════════════════════════════════════════════════════════════════════

class TestCompositeScore:
    """Tests for composite scoring and recompute."""

    def test_composite_is_weighted_sum(self):
        """Full composite with known dimension scores -> verify weighted sum."""
        result = compute_composite_score(
            _buyer(lat=40.0, lng=-74.0, radius_miles=25,
                   min_sqft=8000, max_sqft=12000),
            _warehouse(lat=40.0, lng=-74.0),
            _tc(min_sqft=5000, max_sqft=20000),
        )
        # location=100, size=100, feature=50 (placeholder), timing=100, value=50 (no market data)
        expected = round(
            result["location_score"] * W_LOCATION
            + result["size_score"] * W_SIZE
            + result["use_type_score"] * W_USE_TYPE
            + result["feature_score"] * W_FEATURE
            + result["timing_score"] * W_TIMING
            + result["value_score"] * W_VALUE,
            1,
        )
        assert result["composite_score"] == expected

    def test_recompute_with_feature_score(self):
        """recompute_with_feature_score replaces placeholder and recalculates."""
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
            + updated["value_score"] * W_VALUE,
            1,
        )
        assert updated["composite_score"] == expected_composite
        # Composite should differ from original (feature went from 50 to 90)
        assert updated["composite_score"] != original["composite_score"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. Return Shape
# ═══════════════════════════════════════════════════════════════════════════

class TestReturnShape:
    """Tests for output dict structure and value ranges."""

    EXPECTED_KEYS = {
        "composite_score", "location_score", "size_score", "use_type_score",
        "feature_score", "timing_score", "value_score",
        "distance_miles", "use_type_callouts",
    }

    def test_all_expected_keys_present(self):
        """All expected keys present in return dict."""
        result = compute_composite_score(
            _buyer(), _warehouse(), _tc(),
        )
        assert self.EXPECTED_KEYS == set(result.keys())

    def test_all_scores_between_0_and_100(self):
        """All numeric scores between 0 and 100."""
        score_keys = [
            "composite_score", "location_score", "size_score",
            "use_type_score", "feature_score", "timing_score", "value_score",
        ]
        # Test with several different configurations
        configs = [
            (_buyer(), _warehouse(), _tc()),
            (_buyer(lat=None, lng=None, min_sqft=None, max_sqft=None), _warehouse(), _tc()),
            (_buyer(), _warehouse(), _tc(supplier_rate_per_sqft=50.0, generic_market_avg=1.0)),
        ]
        for buyer, wh, tc in configs:
            result = compute_composite_score(buyer, wh, tc)
            for key in score_keys:
                val = result[key]
                assert 0 <= val <= 100, f"{key}={val} out of range for config"

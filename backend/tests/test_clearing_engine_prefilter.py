"""Unit tests for ClearingEngine co-primary pre-filter, KNN fallback,
requirements gate, and _build_need_dict helper.

Tests exercise the deterministic (non-async, non-DB) methods directly
using lightweight mock objects.
"""

import types
from unittest.mock import MagicMock

import pytest

from wex_platform.services.clearing_engine import ClearingEngine, _haversine_miles


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------

def _make_truth_core(
    *,
    min_sqft: int = 5_000,
    max_sqft: int = 50_000,
    activity_tier: str = "storage_only",
    has_office_space: bool = False,
    activation_status: str = "on",
    **extra,
) -> MagicMock:
    tc = MagicMock()
    tc.min_sqft = min_sqft
    tc.max_sqft = max_sqft
    tc.activity_tier = activity_tier
    tc.has_office_space = has_office_space
    tc.activation_status = activation_status
    for k, v in extra.items():
        setattr(tc, k, v)
    return tc


def _make_warehouse(
    *,
    id: str = "wh-1",
    lat: float | None = 40.7128,
    lng: float | None = -74.0060,
    state: str = "NY",
    truth_core=None,
    **extra,
) -> MagicMock:
    wh = MagicMock()
    wh.id = id
    wh.lat = lat
    wh.lng = lng
    wh.state = state
    wh.truth_core = truth_core or _make_truth_core()
    for k, v in extra.items():
        setattr(wh, k, v)
    return wh


def _make_buyer_need(
    *,
    lat: float | None = 40.7128,
    lng: float | None = -74.0060,
    state: str = "NY",
    radius_miles: int = 25,
    min_sqft: int = 10_000,
    max_sqft: int = 40_000,
    use_type: str | None = "storage",
    city: str = "New York",
    needed_from=None,
    duration_months: int = 12,
    max_budget_per_sqft: float = 12.0,
    requirements: dict | None = None,
) -> MagicMock:
    bn = MagicMock()
    bn.lat = lat
    bn.lng = lng
    bn.state = state
    bn.radius_miles = radius_miles
    bn.min_sqft = min_sqft
    bn.max_sqft = max_sqft
    bn.use_type = use_type
    bn.city = city
    bn.needed_from = needed_from
    bn.duration_months = duration_months
    bn.max_budget_per_sqft = max_budget_per_sqft
    bn.requirements = requirements
    return bn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A point ~10 miles from default buyer location (40.7128, -74.006)
NEARBY_LAT, NEARBY_LNG = 40.82, -73.95  # approx 8 mi north in Manhattan

# A point ~60 miles away
FAR_LAT, FAR_LNG = 41.30, -74.50

# A point ~120 miles away
VERY_FAR_LAT, VERY_FAR_LNG = 42.65, -73.76  # Albany area


engine = ClearingEngine()


# ===================================================================
# Co-Primary Pre-Filter Tests
# ===================================================================

class TestCoPrimaryPreFilter:
    """Tests 1-5: Co-primary pre-filter (geo + requirements)."""

    def test_within_radius_and_meets_requirements_passes(self):
        """1. Warehouse within radius AND meets requirements -> passes."""
        wh = _make_warehouse(lat=NEARBY_LAT, lng=NEARBY_LNG)
        bn = _make_buyer_need()
        result = engine._pre_filter(bn, [wh])
        assert wh in result

    def test_within_radius_incompatible_use_type_rejected(self):
        """2. Warehouse within radius but incompatible use type (score=0) -> rejected."""
        tc = _make_truth_core(activity_tier="storage_only", has_office_space=False)
        wh = _make_warehouse(lat=NEARBY_LAT, lng=NEARBY_LNG, truth_core=tc)
        bn = _make_buyer_need(use_type="cold_storage")
        result = engine._pre_filter(bn, [wh])
        assert wh not in result

    def test_compatible_use_type_outside_radius_rejected(self):
        """3. Warehouse compatible use type but outside radius -> rejected."""
        wh = _make_warehouse(lat=FAR_LAT, lng=FAR_LNG)
        bn = _make_buyer_need(radius_miles=25)
        result = engine._pre_filter(bn, [wh])
        # Should be empty because the only warehouse is outside radius
        # and KNN fallback max is 100mi -- 60mi is within 100 so KNN will find it.
        # But the strict pass should not include it.
        # Actually, since strict is empty, KNN fires and finds it at ~60mi < 100mi.
        # Let me make it truly unreachable: use very far + incompatible for KNN too.
        # Re-approach: add a second warehouse that passes to avoid KNN trigger:
        # Actually, the test should verify the strict filter rejects it.
        # If strict yields 0, KNN fires. To test strict rejection only,
        # we need at least one warehouse to pass strict so KNN doesn't fire.
        nearby_wh = _make_warehouse(id="wh-nearby", lat=NEARBY_LAT, lng=NEARBY_LNG)
        wh_far = _make_warehouse(id="wh-far", lat=FAR_LAT, lng=FAR_LNG)
        bn = _make_buyer_need(radius_miles=25)
        result = engine._pre_filter(bn, [nearby_wh, wh_far])
        assert nearby_wh in result
        assert wh_far not in result

    def test_outside_radius_but_same_state_no_coords_on_buyer(self):
        """4. Warehouse outside radius but within state (no coords on buyer) -> passes via state fallback."""
        wh = _make_warehouse(lat=FAR_LAT, lng=FAR_LNG, state="NY")
        bn = _make_buyer_need(lat=None, lng=None, state="NY")
        result = engine._pre_filter(bn, [wh])
        assert wh in result

    def test_multiple_warehouses_only_compatible_survive(self):
        """5. Multiple warehouses: only compatible ones survive."""
        wh_good = _make_warehouse(
            id="good",
            lat=NEARBY_LAT,
            lng=NEARBY_LNG,
            truth_core=_make_truth_core(activity_tier="storage_only"),
        )
        wh_bad_use = _make_warehouse(
            id="bad-use",
            lat=NEARBY_LAT,
            lng=NEARBY_LNG,
            truth_core=_make_truth_core(activity_tier="storage_only"),
        )
        wh_bad_geo = _make_warehouse(
            id="bad-geo",
            lat=FAR_LAT,
            lng=FAR_LNG,
            truth_core=_make_truth_core(activity_tier="storage_only"),
        )
        # buyer wants cold_storage -> wh_bad_use (storage_only) is incompatible
        # buyer is near NEARBY -> wh_bad_geo is too far
        bn = _make_buyer_need(use_type="storage")
        result = engine._pre_filter(bn, [wh_good, wh_bad_use, wh_bad_geo])
        assert wh_good in result
        assert wh_bad_use in result  # same tier, same use_type=storage -> compatible
        assert wh_bad_geo not in result  # too far away


class TestCoPrimaryPreFilterMultipleIncompat:
    """Extra test: multiple warehouses with a true incompatible one."""

    def test_incompatible_use_type_filtered(self):
        wh_compat = _make_warehouse(
            id="compat",
            lat=NEARBY_LAT,
            lng=NEARBY_LNG,
            truth_core=_make_truth_core(activity_tier="cold_storage"),
        )
        wh_incompat = _make_warehouse(
            id="incompat",
            lat=NEARBY_LAT,
            lng=NEARBY_LNG,
            truth_core=_make_truth_core(activity_tier="storage_only"),
        )
        bn = _make_buyer_need(use_type="cold_storage")
        result = engine._pre_filter(bn, [wh_compat, wh_incompat])
        assert wh_compat in result
        assert wh_incompat not in result


# ===================================================================
# KNN Fallback Tests
# ===================================================================

class TestKNNFallback:
    """Tests 6-10: KNN fallback when strict filter returns empty."""

    def test_knn_finds_nearest_when_strict_empty(self):
        """6. Strict filter returns 0, KNN finds nearest k=5 within 100mi."""
        # All warehouses are outside the buyer radius (25mi) but within 100mi
        warehouses = [
            _make_warehouse(id=f"wh-{i}", lat=40.7128 + i * 0.2, lng=-74.006)
            for i in range(1, 4)  # ~14mi, ~28mi, ~42mi away
        ]
        bn = _make_buyer_need(radius_miles=5)  # very small radius -> strict yields 0
        result = engine._pre_filter(bn, warehouses)
        assert len(result) > 0  # KNN should have found them
        assert len(result) <= 5

    def test_knn_respects_requirements_gate(self):
        """7. KNN excludes warehouses that fail requirements gate (incompatible use type)."""
        wh_ok = _make_warehouse(
            id="ok",
            lat=40.75,
            lng=-74.01,
            truth_core=_make_truth_core(activity_tier="cold_storage"),
        )
        wh_bad = _make_warehouse(
            id="bad",
            lat=40.73,
            lng=-74.005,  # closer than wh_ok
            truth_core=_make_truth_core(activity_tier="storage_only"),
        )
        bn = _make_buyer_need(use_type="cold_storage", radius_miles=1)
        result = engine._pre_filter(bn, [wh_ok, wh_bad])
        assert wh_ok in result
        assert wh_bad not in result

    def test_knn_returns_empty_when_all_too_far(self):
        """8. KNN returns empty when everything is >100mi away."""
        wh = _make_warehouse(lat=VERY_FAR_LAT, lng=VERY_FAR_LNG)
        # Make it even further - 200+ miles
        wh_far = _make_warehouse(id="wh-far", lat=44.0, lng=-74.0)
        bn = _make_buyer_need(radius_miles=1)
        result = engine._pre_filter(bn, [wh_far])
        assert len(result) == 0

    def test_knn_sorts_by_distance_nearest_first(self):
        """9. KNN sorts by distance (nearest first)."""
        wh_near = _make_warehouse(id="near", lat=40.73, lng=-74.005)
        wh_mid = _make_warehouse(id="mid", lat=40.85, lng=-73.95)
        wh_far = _make_warehouse(id="far", lat=41.05, lng=-73.80)
        bn = _make_buyer_need(radius_miles=1)  # force KNN
        result = engine._pre_filter(bn, [wh_far, wh_near, wh_mid])
        assert len(result) == 3
        assert result[0].id == "near"
        assert result[1].id == "mid"
        assert result[2].id == "far"

    def test_knn_caps_at_k5(self):
        """10. KNN caps at k=5 even when more are available."""
        warehouses = []
        for i in range(1, 11):
            # Start at i=1 so the closest is ~3.5mi away, all outside 1mi radius
            warehouses.append(
                _make_warehouse(
                    id=f"wh-{i}",
                    lat=40.7128 + i * 0.05,
                    lng=-74.006,
                )
            )
        bn = _make_buyer_need(radius_miles=1)  # force KNN (strict yields 0)
        result = engine._pre_filter(bn, warehouses)
        assert len(result) == 5


# ===================================================================
# Requirements Gate Tests
# ===================================================================

class TestRequirementsGate:
    """Tests 11-16: _passes_requirements_gate."""

    def test_size_too_small_rejected(self):
        """11. Warehouse max_sqft < buyer min_sqft -> rejected."""
        tc = _make_truth_core(min_sqft=1_000, max_sqft=5_000)
        wh = _make_warehouse(truth_core=tc)
        bn = _make_buyer_need(min_sqft=10_000, max_sqft=40_000)
        assert engine._passes_requirements_gate(wh, bn) is False

    def test_size_too_large_rejected(self):
        """12. Warehouse min_sqft > buyer max_sqft -> rejected."""
        tc = _make_truth_core(min_sqft=50_000, max_sqft=100_000)
        wh = _make_warehouse(truth_core=tc)
        bn = _make_buyer_need(min_sqft=10_000, max_sqft=40_000)
        assert engine._passes_requirements_gate(wh, bn) is False

    def test_size_overlap_passes(self):
        """13. Size ranges overlap -> passes."""
        tc = _make_truth_core(min_sqft=5_000, max_sqft=30_000)
        wh = _make_warehouse(truth_core=tc)
        bn = _make_buyer_need(min_sqft=10_000, max_sqft=40_000)
        assert engine._passes_requirements_gate(wh, bn) is True

    def test_use_type_score_zero_rejected(self):
        """14. Use type score=0 -> rejected."""
        tc = _make_truth_core(activity_tier="storage_only", has_office_space=False)
        wh = _make_warehouse(truth_core=tc)
        bn = _make_buyer_need(use_type="cold_storage")
        assert engine._passes_requirements_gate(wh, bn) is False

    def test_use_type_score_positive_passes(self):
        """15. Use type score>0 -> passes."""
        tc = _make_truth_core(activity_tier="cold_storage", has_office_space=False)
        wh = _make_warehouse(truth_core=tc)
        bn = _make_buyer_need(use_type="cold_storage")
        assert engine._passes_requirements_gate(wh, bn) is True

    def test_no_use_type_on_buyer_passes(self):
        """16. No use_type on buyer -> passes (no filter)."""
        tc = _make_truth_core(activity_tier="storage_only")
        wh = _make_warehouse(truth_core=tc)
        bn = _make_buyer_need(use_type=None)
        assert engine._passes_requirements_gate(wh, bn) is True


# ===================================================================
# _build_need_dict Tests
# ===================================================================

class TestBuildNeedDict:
    """Test 17: _build_need_dict includes lat/lng."""

    def test_lat_lng_included(self):
        """17. Verify lat/lng are included in the returned dict."""
        bn = _make_buyer_need(lat=40.7128, lng=-74.006)
        result = ClearingEngine._build_need_dict(bn)
        assert "lat" in result
        assert "lng" in result
        assert result["lat"] == 40.7128
        assert result["lng"] == -74.006

    def test_all_keys_present(self):
        """_build_need_dict returns all expected keys."""
        bn = _make_buyer_need()
        result = ClearingEngine._build_need_dict(bn)
        expected_keys = {
            "city", "state", "lat", "lng", "radius_miles",
            "min_sqft", "max_sqft", "use_type", "needed_from",
            "duration_months", "max_budget_per_sqft", "requirements",
        }
        assert expected_keys == set(result.keys())

    def test_needed_from_none_becomes_asap(self):
        """_build_need_dict returns 'ASAP' when needed_from is None."""
        bn = _make_buyer_need(needed_from=None)
        result = ClearingEngine._build_need_dict(bn)
        assert result["needed_from"] == "ASAP"

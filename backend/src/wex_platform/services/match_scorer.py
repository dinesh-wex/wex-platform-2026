"""Deterministic MCDA Match Scorer — Layer 1.

Pure-function module — NO LLM, NO database access.

Computes a composite match score from six weighted dimensions:
    - Location  (25%)  — haversine distance with continuous decay
    - Size      (20%)  — satisfaction ratio against buyer target
    - Use Type  (20%)  — compatibility matrix (delegates to use_type_compat)
    - Feature   (15%)  — PLACEHOLDER (filled by LLM Layer 2)
    - Timing    (10%)  — continuous linear decay (-1 pt/day late)
    - Value     (10%)  — market competitiveness (Index + Coefficient model)

All inputs are plain dicts so the scorer can be called from the clearing
engine, from tests, or from offline batch jobs without touching ORM objects.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Optional

from wex_platform.services.clearing_engine import _haversine_miles
from wex_platform.services.use_type_compat import compute_use_type_score

# ── Weights ──────────────────────────────────────────────────────────────────

W_LOCATION = 0.25
W_SIZE = 0.20
W_USE_TYPE = 0.20
W_FEATURE = 0.15
W_TIMING = 0.10
W_VALUE = 0.10

# Baseline multiplier coefficients for facility types relative to generic dry warehouse.
# Used by _compute_value_score to adjust the generic zip-level NNN market rate
# into a facility-type-specific "apples-to-apples" comparison.
TIER_MULTIPLIERS = {
    "storage_only":           1.0,   # Baseline
    "storage_office":         1.15,  # 15% premium for office buildout
    "storage_light_assembly": 1.3,   # 30% premium for power/ventilation
    "food_grade":             1.8,   # 80% premium for sanitation/certifications
    "cold_storage":           2.5,   # 150% premium for refrigeration/insulation
}

# KNN cap for warehouses beyond the buyer's stated radius
KNN_MAX_CAP = 100

# Neutral score returned when data is insufficient for a dimension
NEUTRAL = 50


# ── Helpers ──────────────────────────────────────────────────────────────────

def _parse_date(value) -> Optional[date]:
    """Best-effort parse of a date-like value into a ``date`` object.

    Accepts ``date``, ``datetime``, ISO-format strings, or ``None``.
    Returns ``None`` when the value cannot be interpreted as a date
    (including the sentinel strings ``"Now"`` and ``"ASAP"``).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.upper() in ("NOW", "ASAP", ""):
            return None
        try:
            return date.fromisoformat(cleaned[:10])
        except (ValueError, TypeError):
            return None
    return None


def _compute_timing_score(needed_from, available_from) -> float:
    """Continuous linear decay for timing gaps.

    If available on or before the needed date: 100.
    If late: -1 point per day late, floored at 10.
    """
    avail = _parse_date(available_from)
    if avail is None:
        return 100.0

    need = _parse_date(needed_from)
    if need is None:
        return 100.0

    gap_days = (avail - need).days  # positive = warehouse is late

    if gap_days <= 0:
        return 100.0

    # Continuous linear decay: -1 point per day, floored at 10
    return float(max(10, 100 - gap_days))


def _compute_value_score(
    supplier_rate: float | None,
    generic_market_avg: float | None,
    activity_tier: str | None,
) -> float:
    """Continuous linear scoring based on adjusted market competitiveness.

    Uses Index + Coefficient model: generic zip-level NNN market rate × tier
    multiplier gives the 'apples-to-apples' adjusted market average for this
    facility type.

    IMPORTANT — Lease type alignment:
    MarketRateCache stores NNN base rent (excludes taxes/insurance/maintenance).
    supplier_rate_per_sqft is also the supplier's base rent (their net take).
    We compare supplier_rate directly against the NNN avg — both are base rent.
    We do NOT apply the WEx markup (×1.20×1.06) here because it's a constant
    multiplier on all properties and doesn't affect relative competitiveness.

    Anchor at 70 for exact market average. Drops 1pt per 1% above. Caps 0-100.
    """
    if not supplier_rate or supplier_rate <= 0:
        return 50.0  # NEUTRAL — no rate data
    if not generic_market_avg or generic_market_avg <= 0:
        return 50.0  # NEUTRAL — no market data for this zip

    # 1. Adjust baseline to facility-type-specific market rate
    tier_coefficient = TIER_MULTIPLIERS.get(activity_tier or "", 1.0)
    adjusted_market_avg = generic_market_avg * tier_coefficient

    # 2. Compare supplier base rent vs NNN market avg (both are base rent)
    #    No WEx markup applied — it's constant across all properties
    pct_deviation = (supplier_rate - adjusted_market_avg) / adjusted_market_avg
    raw_score = 70 - (pct_deviation * 100)

    return max(0.0, min(100.0, round(raw_score, 1)))


# ── Main scorer ──────────────────────────────────────────────────────────────

def compute_composite_score(
    buyer_need_dict: dict,
    warehouse_dict: dict,
    tc_dict: dict,
) -> dict:
    """Compute a deterministic composite match score.

    Parameters
    ----------
    buyer_need_dict
        Keys: city, state, lat, lng, radius_miles, min_sqft, max_sqft,
        use_type, needed_from, duration_months, requirements.
    warehouse_dict
        Keys: id, address, city, state, lat, lng, building_size_sqft.
    tc_dict
        Keys: min_sqft, max_sqft, activity_tier, supplier_rate_per_sqft,
        generic_market_avg, has_office_space, available_from,
        clear_height_ft, dock_doors_receiving, etc.

    Returns
    -------
    dict
        Full scoring breakdown including composite_score, per-dimension
        scores, distance_miles, and use-type callouts.
    """

    # ── 1. Location score (25 %) ─────────────────────────────────────────
    buyer_lat = buyer_need_dict.get("lat")
    buyer_lng = buyer_need_dict.get("lng")
    wh_lat = warehouse_dict.get("lat")
    wh_lng = warehouse_dict.get("lng")

    dist: Optional[float] = None

    if (
        buyer_lat is not None
        and buyer_lng is not None
        and wh_lat is not None
        and wh_lng is not None
    ):
        dist = _haversine_miles(buyer_lat, buyer_lng, wh_lat, wh_lng)
        radius = buyer_need_dict.get("radius_miles") or 25
        effective_denominator = radius if dist <= radius else KNN_MAX_CAP
        location_score = max(0.0, 100.0 * (1.0 - dist / effective_denominator))

        # Tie-breaker: +10 if warehouse is in the exact city the buyer searched
        buyer_city = (buyer_need_dict.get("city") or "").strip().lower()
        wh_city = (warehouse_dict.get("city") or "").strip().lower()
        if buyer_city and wh_city and buyer_city == wh_city:
            location_score = min(100.0, location_score + 10.0)
    else:
        location_score = float(NEUTRAL)

    # ── 2. Size score (20 %) ─────────────────────────────────────────────
    buyer_min = buyer_need_dict.get("min_sqft") or 0
    buyer_max = buyer_need_dict.get("max_sqft") or 0

    if buyer_min and buyer_max and buyer_min != buyer_max:
        buyer_target = (buyer_min + buyer_max) / 2
    elif buyer_min:
        buyer_target = float(buyer_min)
    elif buyer_max:
        buyer_target = float(buyer_max)
    else:
        buyer_target = 0.0

    if buyer_target > 0:
        wh_min = tc_dict.get("min_sqft") or warehouse_dict.get("building_size_sqft") or 0
        wh_max = tc_dict.get("max_sqft") or warehouse_dict.get("building_size_sqft") or 0
        best_fit = max(wh_min, min(wh_max, buyer_target))
        ratio = best_fit / buyer_target

        if 0.8 <= ratio <= 1.2:
            size_score = 100.0
        elif ratio < 0.8:
            size_score = max(0.0, 100.0 - (0.8 - ratio) * 250.0)
        else:
            size_score = max(0.0, 100.0 - (ratio - 1.2) * 100.0)
    else:
        size_score = float(NEUTRAL)

    # ── 3. Use type score (20 %) ─────────────────────────────────────────
    buyer_use_type = buyer_need_dict.get("use_type") or "general"
    activity_tier = tc_dict.get("activity_tier", "storage_only")
    has_office = tc_dict.get("has_office_space", False)

    use_type_score, use_type_callouts = compute_use_type_score(
        activity_tier, buyer_use_type, has_office_space=has_office,
    )

    # ── 4. Timing score (10 %) ───────────────────────────────────────────
    timing_score = _compute_timing_score(
        buyer_need_dict.get("needed_from"),
        tc_dict.get("available_from"),
    )

    # ── 5. Value score (10 %) — market competitiveness ───────────────────
    value_score = _compute_value_score(
        tc_dict.get("supplier_rate_per_sqft"),
        tc_dict.get("generic_market_avg"),
        tc_dict.get("activity_tier"),
    )

    # ── 6. Feature score (15 %) — PLACEHOLDER ────────────────────────────
    feature_score = NEUTRAL

    # ── Composite ────────────────────────────────────────────────────────
    composite = (
        location_score * W_LOCATION
        + size_score * W_SIZE
        + use_type_score * W_USE_TYPE
        + feature_score * W_FEATURE
        + timing_score * W_TIMING
        + value_score * W_VALUE
    )

    return {
        "composite_score": round(composite, 1),
        "location_score": round(location_score, 1),
        "size_score": round(size_score, 1),
        "use_type_score": use_type_score,
        "feature_score": feature_score,
        "timing_score": round(timing_score, 1),
        "value_score": round(value_score, 1),
        "distance_miles": round(dist, 1) if dist is not None else None,
        "use_type_callouts": use_type_callouts,
    }


# ── Layer-2 recompute ───────────────────────────────────────────────────────

def recompute_with_feature_score(scores: dict, feature_score: int) -> dict:
    """Replace the placeholder feature score and recompute the composite.

    Called after the LLM Layer 2 returns a real feature-alignment score.

    Parameters
    ----------
    scores
        An existing breakdown dict produced by ``compute_composite_score``.
    feature_score
        The LLM-derived feature alignment score (0-100).

    Returns
    -------
    dict
        A *new* dict with ``feature_score`` and ``composite_score`` updated.
    """
    updated = dict(scores)
    updated["feature_score"] = feature_score

    updated["composite_score"] = round(
        updated["location_score"] * W_LOCATION
        + updated["size_score"] * W_SIZE
        + updated["use_type_score"] * W_USE_TYPE
        + feature_score * W_FEATURE
        + updated["timing_score"] * W_TIMING
        + updated["value_score"] * W_VALUE,
        1,
    )
    return updated

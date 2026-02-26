"""Deterministic MCDA Match Scorer — Layer 1.

Pure-function module — NO LLM, NO database access.

Computes a composite match score from six weighted dimensions:
    - Location  (25%)  — haversine distance with continuous decay
    - Size      (20%)  — satisfaction ratio against buyer target
    - Use Type  (20%)  — compatibility matrix (delegates to use_type_compat)
    - Feature   (15%)  — PLACEHOLDER (filled by LLM Layer 2)
    - Timing    (10%)  — date-gap comparison
    - Budget    (10%)  — linear decay above buyer ceiling

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
W_BUDGET = 0.10

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
    """Deterministic timing score (0-100).

    Rules
    -----
    * Warehouse available now or date unknown → 100
    * Buyer has no target date               → 100
    * Warehouse available on or before buyer  → 100
    * Up to 30 days late                      → 70
    * Up to 60 days late                      → 40
    * More than 60 days late                  → 10
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
    if gap_days <= 30:
        return 70.0
    if gap_days <= 60:
        return 40.0
    return 10.0


def _compute_budget_score(
    buyer_max_budget: Optional[float],
    supplier_rate: Optional[float],
) -> tuple[float, bool, float]:
    """Deterministic budget score with WEx pricing formula.

    Returns
    -------
    (score, within_budget, budget_stretch_pct)
        *score* is 0-100.
        *within_budget* is True when the buyer rate fits the stated max.
        *budget_stretch_pct* is how far over budget (0.0 when within).
    """
    if buyer_max_budget is None or buyer_max_budget <= 0:
        return NEUTRAL, True, 0.0

    if supplier_rate is None or supplier_rate <= 0:
        return NEUTRAL, True, 0.0

    # WEx pricing formula: supplier × 1.20 margin × 1.06 guarantee, rounded UP
    buyer_rate = math.ceil(supplier_rate * 1.20 * 1.06 * 100) / 100

    if buyer_rate <= buyer_max_budget:
        return 100.0, True, 0.0

    percent_over = ((buyer_rate - buyer_max_budget) / buyer_max_budget) * 100
    score = max(0.0, 100.0 - percent_over * 3.33)
    stretch_pct = round(percent_over, 2)

    return score, False, stretch_pct


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
        use_type, needed_from, duration_months, max_budget_per_sqft,
        requirements.
    warehouse_dict
        Keys: id, address, city, state, lat, lng, building_size_sqft.
    tc_dict
        Keys: min_sqft, max_sqft, activity_tier, supplier_rate_per_sqft,
        has_office_space, available_from, clear_height_ft,
        dock_doors_receiving, etc.

    Returns
    -------
    dict
        Full scoring breakdown including composite_score, per-dimension
        scores, distance_miles, budget flags, and use-type callouts.
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

    # ── 5. Budget score (10 %) ───────────────────────────────────────────
    budget_score, within_budget, budget_stretch_pct = _compute_budget_score(
        buyer_need_dict.get("max_budget_per_sqft"),
        tc_dict.get("supplier_rate_per_sqft"),
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
        + budget_score * W_BUDGET
    )

    return {
        "composite_score": round(composite, 1),
        "location_score": round(location_score, 1),
        "size_score": round(size_score, 1),
        "use_type_score": use_type_score,
        "feature_score": feature_score,
        "timing_score": round(timing_score, 1),
        "budget_score": round(budget_score, 1),
        "distance_miles": round(dist, 1) if dist is not None else None,
        "within_budget": within_budget,
        "budget_stretch_pct": budget_stretch_pct,
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
        + updated["budget_score"] * W_BUDGET,
        1,
    )
    return updated


# ── Budget context tagger ────────────────────────────────────────────────────

def apply_budget_context(
    results: list[dict],
    buyer_max_budget: Optional[float],
) -> list[dict]:
    """Tag each match result with budget context flags.

    For every result dict that contains a ``budget_score`` (or can be
    computed from a ``supplier_rate_per_sqft``), this sets:

    * ``within_budget`` — True when the WEx buyer rate fits
    * ``budget_stretch_pct`` — percentage over budget (0.0 when within)
    * ``budget_alternative_available`` — True on the first result ONLY
      when *every* result exceeds budget (signals the UI to show an
      "alternatives available" badge).

    Parameters
    ----------
    results
        List of match/scoring dicts.  Modified **in place** and returned.
    buyer_max_budget
        The buyer's stated max $/sqft.  When ``None``, all results are
        treated as within budget.

    Returns
    -------
    list[dict]
        The same list, mutated with budget tags.
    """
    if not results:
        return results

    all_over_budget = True

    for r in results:
        if buyer_max_budget is None or buyer_max_budget <= 0:
            r["within_budget"] = True
            r["budget_stretch_pct"] = 0.0
            all_over_budget = False
            continue

        # If the result already carries budget flags (from compute_composite_score),
        # just propagate them.
        if "within_budget" in r and "budget_stretch_pct" in r:
            if r["within_budget"]:
                all_over_budget = False
            continue

        # Otherwise compute from supplier rate if available
        supplier_rate = r.get("supplier_rate_per_sqft") or r.get("supplier_rate")
        if supplier_rate and supplier_rate > 0:
            buyer_rate = math.ceil(supplier_rate * 1.20 * 1.06 * 100) / 100
            if buyer_rate <= buyer_max_budget:
                r["within_budget"] = True
                r["budget_stretch_pct"] = 0.0
            else:
                percent_over = ((buyer_rate - buyer_max_budget) / buyer_max_budget) * 100
                r["within_budget"] = False
                r["budget_stretch_pct"] = round(percent_over, 2)
        else:
            r["within_budget"] = True
            r["budget_stretch_pct"] = 0.0
            all_over_budget = False
            continue

        if r["within_budget"]:
            all_over_budget = False

    # If every single result is over budget, flag the first one
    if all_over_budget and results:
        results[0]["budget_alternative_available"] = True

    return results

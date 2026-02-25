"""Use-type compatibility matrix.

Pure-function module — NO AI, NO database access.

Defines a directional (asymmetric) compatibility matrix between warehouse
activity tiers and buyer use types.  A cold-storage warehouse *can* serve a
plain-storage buyer (overkill but works), while a storage-only warehouse
*cannot* serve a cold-storage buyer (no refrigeration).
"""

from __future__ import annotations

# ── What each warehouse tier CAN provide ──────────────────────────────────

CAPABILITY_MAP: dict[str, set[str]] = {
    "storage_only":           {"storage"},
    "storage_office":         {"storage", "office"},
    "storage_light_assembly": {"storage", "light_assembly", "ecommerce_fulfillment"},
    "cold_storage":           {"storage", "cold_storage", "food_grade"},
}

# ── What each buyer use_type NEEDS ────────────────────────────────────────

NEED_MAP: dict[str, set[str]] = {
    "storage":               {"storage"},
    "storage_only":          {"storage"},
    "office":                {"office"},
    "storage_office":        {"storage", "office"},
    "ecommerce_fulfillment": {"storage", "light_assembly"},
    "distribution":          {"storage"},
    "cold_storage":          {"cold_storage"},
    "food_grade":            {"cold_storage", "food_grade"},
    "manufacturing_light":   {"light_assembly"},
    "general":               {"storage"},
}

# ── Human-readable labels for callout messages ────────────────────────────

_CAPABILITY_LABELS: dict[str, str] = {
    "storage":               "storage",
    "office":                "dedicated office space",
    "light_assembly":        "light-assembly capability",
    "ecommerce_fulfillment": "e-commerce fulfillment capability",
    "cold_storage":          "cold-storage / refrigeration",
    "food_grade":            "food-grade certification",
}


def _label(cap: str) -> str:
    return _CAPABILITY_LABELS.get(cap, cap.replace("_", " "))


# ── Main scoring function ─────────────────────────────────────────────────

def compute_use_type_score(
    warehouse_tier: str,
    buyer_use_type: str,
    has_office_space: bool = False,
) -> tuple[int, list[str]]:
    """Score how well *warehouse_tier* satisfies *buyer_use_type*.

    Returns
    -------
    (score, callouts)
        *score* is 0-100.
        *callouts* is a list of human-readable strings explaining the score.
    """
    wh_caps: set[str] = set(CAPABILITY_MAP.get(warehouse_tier, set()))

    if has_office_space:
        wh_caps = wh_caps | {"office"}

    buyer_needs: set[str] = set(NEED_MAP.get(buyer_use_type, set()))

    # If either side is unknown, treat as incompatible.
    if not wh_caps or not buyer_needs:
        return 0, ["Unknown warehouse tier or buyer use type"]

    overlap = wh_caps & buyer_needs
    missing = buyer_needs - wh_caps
    bonus = wh_caps - buyer_needs

    # ── No overlap at all → incompatible ──────────────────────────────
    if not overlap:
        return 0, ["Incompatible use type"]

    callouts: list[str] = []

    # ── Warehouse is a superset (or exact match) → perfect fit ────────
    if not missing:
        score = 100
        for cap in sorted(bonus):
            callouts.append(f"Bonus: includes {_label(cap)}")
        return score, callouts

    # ── Meets most needs (overlap >= missing) → decent fit ────────────
    if len(overlap) >= len(missing):
        score = 60
        for cap in sorted(missing):
            callouts.append(f"No {_label(cap)}")
        return score, callouts

    # ── Partial match ─────────────────────────────────────────────────
    score = 30
    for cap in sorted(missing):
        callouts.append(f"No {_label(cap)}")
    return score, callouts

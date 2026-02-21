"""Deterministic confidence scoring for property search results."""

KEY_FIELDS = [
    "building_size_sqft",
    "year_built",
    "clear_height_ft",
    "dock_doors",
    "lot_size_acres",
]

SOURCE_QUALITY: dict[str, float] = {
    "cre_listing": 1.0,
    "multiple": 1.0,
    "tax_records": 0.9,
    "broker_flyer": 0.8,
    "past_listing": 0.7,
    "other": 0.4,
    "satellite": 0.3,
    "inferred": 0.2,
}


def compute_confidence(
    property_data: dict,
    fields_by_source: dict,
    address_match_quality: str,
    sanity_flags: list[str],
) -> float:
    """Compute a deterministic confidence score for a property search result.

    Args:
        property_data: Property attributes keyed by field name.
        fields_by_source: Mapping of field name to its source type string.
        address_match_quality: One of "exact", "partial", or "mismatch".
        sanity_flags: List of sanity-check violation labels (if any).

    Returns:
        Confidence score clamped to [0.0, 1.0], rounded to 3 decimal places.
    """

    # 1. Coverage score (0.0 to 0.6)
    populated_count = sum(
        1 for field in KEY_FIELDS if property_data.get(field) is not None
    )
    coverage_score = (populated_count / len(KEY_FIELDS)) * 0.6

    # 2. Source quality multiplier (0.5 to 1.0)
    quality_values: list[float] = []
    for field in KEY_FIELDS:
        if property_data.get(field) is not None:
            source_type = fields_by_source.get(field, "")
            quality = SOURCE_QUALITY.get(source_type, 0.4)
            quality_values.append(quality)

    if quality_values:
        avg_quality = sum(quality_values) / len(quality_values)
        source_quality_multiplier = 0.5 + (avg_quality * 0.5)
    else:
        source_quality_multiplier = 0.5

    # 3. Base confidence
    confidence = coverage_score * source_quality_multiplier

    # 4. Penalties
    if address_match_quality == "mismatch":
        confidence *= 0.3
    elif address_match_quality == "partial":
        confidence *= 0.8

    for _ in sanity_flags:
        confidence *= 0.7

    # 5. Clamp and round
    confidence = max(0.0, min(1.0, confidence))
    return round(confidence, 3)


def compute_source_quality_summary(fields_by_source: dict) -> dict:
    """Count fields per source type for debugging/analytics.

    Returns e.g. {"cre_listing": 3, "tax_records": 1, "inferred": 2}
    """
    counts: dict[str, int] = {}
    for source_type in fields_by_source.values():
        counts[source_type] = counts.get(source_type, 0) + 1
    return counts

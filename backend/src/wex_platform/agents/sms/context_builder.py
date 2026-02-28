"""Context Builder — assembles context for each agent based on phase and state."""


def build_criteria_context(
    message: str,
    interpretation,
    phase: str,
    conversation_history: list[dict] | None = None,
    existing_criteria: dict | None = None,
    presented_match_summaries: list[dict] | None = None,
) -> dict:
    """Build context dict for the Criteria Agent."""
    return {
        "message": message,
        "interpretation": interpretation,
        "phase": phase,
        "history": (conversation_history or [])[-8:],
        "existing_criteria": existing_criteria,
        "match_summaries": presented_match_summaries,
    }


def build_response_context(
    message: str,
    intent: str,
    phase: str,
    criteria: dict | None = None,
    property_data: dict | None = None,
    match_summaries: list[dict] | None = None,
    conversation_history: list[dict] | None = None,
    response_hint: str | None = None,
    is_first_message: bool = False,
) -> dict:
    """Build context dict for the Response Agent."""
    return {
        "message": message,
        "intent": intent,
        "phase": phase,
        "criteria": criteria,
        "property_data": property_data,
        "match_summaries": match_summaries,
        "history": (conversation_history or [])[-8:],
        "response_hint": response_hint,
        "is_first_message": is_first_message,
    }


def build_match_summaries(matches: list) -> list[dict]:
    """Build match summary dicts from ClearingEngine tier1 results or ORM objects.

    ClearingEngine tier1 match structure:
        {
            "warehouse_id": "...",
            "warehouse": {"id": "...", "city": "...", "building_size_sqft": ...,
                          "truth_core": {"max_sqft": ..., "supplier_rate_per_sqft": ...}},
            "buyer_rate": 1.08,
            "match_score": 0.85,
        }
    """
    summaries = []
    for match in matches:
        if isinstance(match, dict):
            # ClearingEngine tier1 format (has "warehouse" sub-dict)
            wh = match.get("warehouse", {})
            tc = wh.get("truth_core", {}) if isinstance(wh, dict) else {}

            prop_id = match.get("warehouse_id") or wh.get("id") or match.get("id")
            city = wh.get("city", "") or match.get("city", "")
            state = wh.get("state", "") or match.get("state", "")
            address = wh.get("address", "") or match.get("address", "")
            sqft = (
                tc.get("max_sqft")
                or wh.get("building_size_sqft")
                or match.get("available_sqft")
                or match.get("sqft")
            )
            rate = (
                match.get("buyer_rate")
                or tc.get("supplier_rate_per_sqft")
                or match.get("rate")
            )

            summaries.append({
                "id": prop_id,
                "city": city,
                "state": state,
                "address": address,
                "sqft": sqft,
                "rate": rate,
                "match_score": match.get("match_score"),
            })
        else:
            # ORM object
            prop = getattr(match, 'warehouse', None) or getattr(match, 'property_ref', None) or match
            listing = getattr(prop, 'listing', None)
            knowledge = getattr(prop, 'knowledge', None)
            summaries.append({
                "id": getattr(prop, 'id', None),
                "city": getattr(prop, 'city', ''),
                "state": getattr(prop, 'state', ''),
                "address": getattr(prop, 'address', ''),
                "sqft": getattr(listing, 'available_sqft', None) or getattr(knowledge, 'building_size_sqft', None) if listing or knowledge else None,
                "rate": getattr(listing, 'supplier_rate_per_sqft', None) if listing else None,
            })
    return summaries

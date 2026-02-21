"""Address matching and data sanity validation for property search results."""

import re
from datetime import datetime

# Lookup table: maps lowercase variants to 2-letter state codes.
_STATE_TO_ABBREV: dict[str, str] = {
    # Full names
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    # 2-letter codes (identity mapping)
    "al": "AL",
    "ak": "AK",
    "az": "AZ",
    "ar": "AR",
    "ca": "CA",
    "co": "CO",
    "ct": "CT",
    "de": "DE",
    "fl": "FL",
    "ga": "GA",
    "hi": "HI",
    "id": "ID",
    "il": "IL",
    "in": "IN",
    "ia": "IA",
    "ks": "KS",
    "ky": "KY",
    "la": "LA",
    "me": "ME",
    "md": "MD",
    "ma": "MA",
    "mi": "MI",
    "mn": "MN",
    "ms": "MS",
    "mo": "MO",
    "mt": "MT",
    "ne": "NE",
    "nv": "NV",
    "nh": "NH",
    "nj": "NJ",
    "nm": "NM",
    "ny": "NY",
    "nc": "NC",
    "nd": "ND",
    "oh": "OH",
    "ok": "OK",
    "or": "OR",
    "pa": "PA",
    "ri": "RI",
    "sc": "SC",
    "sd": "SD",
    "tn": "TN",
    "tx": "TX",
    "ut": "UT",
    "vt": "VT",
    "va": "VA",
    "wa": "WA",
    "wv": "WV",
    "wi": "WI",
    "wy": "WY",
    # Common abbreviations and variants
    "calif.": "CA",
    "calif": "CA",
    "cal.": "CA",
    "cal": "CA",
    "colo.": "CO",
    "colo": "CO",
    "conn.": "CT",
    "conn": "CT",
    "del.": "DE",
    "del": "DE",
    "fla.": "FL",
    "fla": "FL",
    "ill.": "IL",
    "ill": "IL",
    "ind.": "IN",
    "ind": "IN",
    "kans.": "KS",
    "kans": "KS",
    "kan.": "KS",
    "kan": "KS",
    "ky.": "KY",
    "la.": "LA",
    "md.": "MD",
    "mass.": "MA",
    "mass": "MA",
    "mich.": "MI",
    "mich": "MI",
    "minn.": "MN",
    "minn": "MN",
    "miss.": "MS",
    "miss": "MS",
    "mo.": "MO",
    "mont.": "MT",
    "mont": "MT",
    "nebr.": "NE",
    "nebr": "NE",
    "neb.": "NE",
    "neb": "NE",
    "nev.": "NV",
    "nev": "NV",
    "n.h.": "NH",
    "n.j.": "NJ",
    "n.m.": "NM",
    "n.y.": "NY",
    "n.c.": "NC",
    "n.d.": "ND",
    "okla.": "OK",
    "okla": "OK",
    "ore.": "OR",
    "ore": "OR",
    "oreg.": "OR",
    "oreg": "OR",
    "pa.": "PA",
    "penn.": "PA",
    "penn": "PA",
    "penna.": "PA",
    "penna": "PA",
    "r.i.": "RI",
    "s.c.": "SC",
    "s.d.": "SD",
    "tenn.": "TN",
    "tenn": "TN",
    "tex.": "TX",
    "tex": "TX",
    "vt.": "VT",
    "va.": "VA",
    "wash.": "WA",
    "wash": "WA",
    "w.va.": "WV",
    "w. va.": "WV",
    "w.v.": "WV",
    "wis.": "WI",
    "wis": "WI",
    "wisc.": "WI",
    "wisc": "WI",
    "wyo.": "WY",
    "wyo": "WY",
}


def _normalize_state(value: str | None) -> str | None:
    """Normalize a state string to a 2-letter uppercase code, or None."""
    if value is None:
        return None
    key = value.strip().lower()
    return _STATE_TO_ABBREV.get(key)


def _normalize_city(value: str | None) -> str | None:
    """Normalize a city name: lowercase, strip punctuation, collapse whitespace."""
    if value is None:
        return None
    # Remove periods and commas
    cleaned = value.replace(".", "").replace(",", "")
    # Collapse whitespace and strip
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned if cleaned else None


def _normalize_zip(value: str | None) -> str | None:
    """Extract the first 5 digits from a ZIP code string, or None."""
    if value is None:
        return None
    digits = re.sub(r"[^0-9]", "", value)
    return digits[:5] if len(digits) >= 5 else None


def check_address_match(
    extracted_city: str | None,
    extracted_state: str | None,
    extracted_zip: str | None,
    geocoded_city: str | None,
    geocoded_state: str | None,
    geocoded_zip: str | None,
) -> dict:
    """Compare extracted address components against geocoded ones.

    Returns a dict with keys:
        city_match (bool), state_match (bool), zip_match (bool),
        match_quality (str: "exact" | "partial" | "mismatch"),
        mismatch_details (list[str]).
    """
    mismatch_details: list[str] = []

    # --- State ---
    norm_ext_state = _normalize_state(extracted_state)
    norm_geo_state = _normalize_state(geocoded_state)

    if norm_geo_state is None:
        # No geocoded reference — skip comparison (not a mismatch)
        state_match = True
    elif norm_ext_state is not None:
        state_match = norm_ext_state == norm_geo_state
    else:
        state_match = False

    if not state_match:
        mismatch_details.append(
            f"state: extracted='{extracted_state}' vs geocoded='{geocoded_state}'"
        )

    # --- City ---
    norm_ext_city = _normalize_city(extracted_city)
    norm_geo_city = _normalize_city(geocoded_city)

    if norm_geo_city is None:
        # No geocoded reference — skip comparison (not a mismatch)
        city_match = True
    elif norm_ext_city is not None:
        city_match = norm_ext_city == norm_geo_city
    else:
        city_match = False

    if not city_match:
        mismatch_details.append(
            f"city: extracted='{extracted_city}' vs geocoded='{geocoded_city}'"
        )

    # --- ZIP ---
    norm_ext_zip = _normalize_zip(extracted_zip)
    norm_geo_zip = _normalize_zip(geocoded_zip)

    if norm_geo_zip is None:
        # No geocoded reference — skip comparison (not a mismatch)
        zip_match = True
    elif norm_ext_zip is not None:
        zip_match = norm_ext_zip == norm_geo_zip
    else:
        zip_match = False

    if not zip_match:
        mismatch_details.append(
            f"zip: extracted='{extracted_zip}' vs geocoded='{geocoded_zip}'"
        )

    # --- Match quality ---
    if city_match and state_match and zip_match:
        match_quality = "exact"
    elif state_match and zip_match and not city_match:
        match_quality = "partial"
    else:
        match_quality = "mismatch"

    return {
        "city_match": city_match,
        "state_match": state_match,
        "zip_match": zip_match,
        "match_quality": match_quality,
        "mismatch_details": mismatch_details,
    }


# Round clear-height values that suggest inference rather than measurement.
_INFERRED_ROUND_HEIGHTS: set[int | float] = {20, 24, 28, 30, 32, 36}


def check_sanity_flags(
    property_data: dict, fields_by_source: dict | None = None
) -> list[str]:
    """Run sanity checks on property data and return a list of flag strings.

    An empty list means all checks passed.

    Args:
        property_data: Dict of property attributes (e.g. building_size_sqft,
            clear_height_ft, year_built, etc.).
        fields_by_source: Optional dict mapping field names to their source
            (e.g. "inferred", "extracted"). Enables source-aware checks when
            provided.
    """
    flags: list[str] = []

    # 1. Building size range
    building_size = property_data.get("building_size_sqft")
    if building_size is not None:
        if building_size < 1_000 or building_size > 1_000_000:
            flags.append("building_size_out_of_range")

    # 2. Clear height range
    clear_height = property_data.get("clear_height_ft")
    if clear_height is not None:
        if clear_height < 8 or clear_height > 100:
            flags.append("clear_height_out_of_range")

    # 3. Clear height inferred round (only when fields_by_source is available)
    if fields_by_source is not None and clear_height is not None:
        source = fields_by_source.get("clear_height_ft")
        if source == "inferred" and clear_height in _INFERRED_ROUND_HEIGHTS:
            flags.append("clear_height_inferred_round")

    # 4. Year built range
    year_built = property_data.get("year_built")
    if year_built is not None:
        current_year = datetime.now().year
        if year_built < 1800 or year_built > current_year + 2:
            flags.append("year_built_out_of_range")

    # 5. Dock doors range
    dock_doors = property_data.get("dock_doors")
    if dock_doors is not None:
        if dock_doors > 100:
            flags.append("dock_doors_out_of_range")

    # 6. Dock doors on a very small building
    if dock_doors is not None and building_size is not None:
        if building_size < 5_000:
            flags.append("dock_doors_building_too_small")

    # 7. Parking spaces range
    parking_spaces = property_data.get("parking_spaces")
    if parking_spaces is not None:
        if parking_spaces > 1_000:
            flags.append("parking_spaces_out_of_range")

    # 8. Available sqft exceeds building size
    available_sqft = property_data.get("available_sqft")
    if available_sqft is not None and building_size is not None:
        if available_sqft > building_size:
            flags.append("available_exceeds_building_size")

    # 9. Lot size range
    lot_size = property_data.get("lot_size_acres")
    if lot_size is not None:
        if lot_size < 0.1 or lot_size > 500:
            flags.append("lot_size_out_of_range")

    # 10. City and zip both null
    city = property_data.get("city")
    zip_code = property_data.get("zip_code")
    if city is None and zip_code is None:
        flags.append("city_and_zip_null")

    # 11. State null
    state = property_data.get("state")
    if state is None:
        flags.append("state_null")

    return flags

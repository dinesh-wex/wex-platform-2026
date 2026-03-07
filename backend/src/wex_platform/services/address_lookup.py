"""WS4 – Address Lookup Service.

Fuzzy-matches a street address string against the Property table using a
three-strategy pipeline (exact -> fuzzy -> geocode fallback) and returns an
`AddressLookupResult` with match metadata suitable for voice/SMS formatting.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wex_platform.domain.models import Property, PropertyKnowledge, PropertyListing
from wex_platform.services.clearing_engine import _haversine_miles

logger = logging.getLogger(__name__)

# Tier definitions based on relationship_status
_TIER1_STATUSES = {"active"}
_TIER2_STATUSES = {"prospect", "contacted", "interested", "earncheck_only"}

_GEOCODE_RADIUS_MILES = 0.5


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class AddressLookupResult:
    found: bool = False
    property_id: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    tier: int | None = None  # 1 or 2
    confidence: float = 0.0
    match_type: str = ""  # "exact", "fuzzy", "geocode"
    property_data: dict | None = None  # property summary for voice/SMS formatting


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tier_for(relationship_status: str | None) -> int | None:
    """Return 1, 2, or None based on the property's relationship status."""
    if not relationship_status:
        return None
    rs = relationship_status.lower()
    if rs in _TIER1_STATUSES:
        return 1
    if rs in _TIER2_STATUSES:
        return 2
    return None


def _build_property_data(
    prop: Property,
    pk: PropertyKnowledge | None,
    pl: PropertyListing | None,
    is_tier1: bool,
) -> dict:
    """Build the property_data summary dict for voice/SMS formatting."""
    return {
        "id": prop.id,
        "city": prop.city,
        "state": prop.state,
        "building_size_sqft": pk.building_size_sqft if pk else None,
        "property_type": prop.property_type,
        "available_sqft": pl.available_sqft if pl else None,
        "rate": pl.supplier_rate_per_sqft if (pl and is_tier1) else None,
        "features": {
            "dock_doors": (pk.dock_doors_receiving or 0) if pk else 0,
            "has_office": pk.has_office if pk else False,
            "clear_height_ft": pk.clear_height_ft if pk else None,
        },
        "tier": 1 if is_tier1 else 2,
    }


def _to_result(
    prop: Property,
    confidence: float,
    match_type: str,
) -> AddressLookupResult:
    """Convert a Property ORM instance into an AddressLookupResult."""
    tier = _tier_for(prop.relationship_status)
    is_tier1 = tier == 1
    pk: PropertyKnowledge | None = prop.knowledge
    pl: PropertyListing | None = prop.listing

    return AddressLookupResult(
        found=True,
        property_id=prop.id,
        address=prop.address,
        city=prop.city,
        state=prop.state,
        tier=tier,
        confidence=confidence,
        match_type=match_type,
        property_data=_build_property_data(prop, pk, pl, is_tier1),
    )


def _base_query(include_tier2: bool):
    """Return a base SELECT with eager-loaded relationships and optional tier filter."""
    stmt = (
        select(Property)
        .options(
            selectinload(Property.knowledge),
            selectinload(Property.listing),
        )
    )
    if not include_tier2:
        stmt = stmt.where(Property.relationship_status == "active")
    return stmt


def _extract_street_parts(address_text: str) -> tuple[str | None, str | None]:
    """Extract street number and first word of street name from an address.

    Example: "1234 Main Street, Chicago" -> ("1234", "Main")
    """
    cleaned = address_text.strip()
    match = re.match(r"(\d+)\s+(\S+)", cleaned)
    if match:
        return match.group(1), match.group(2)
    return None, None


# ---------------------------------------------------------------------------
# Strategy 1: Exact match
# ---------------------------------------------------------------------------

async def _exact_match(
    address_text: str,
    db: AsyncSession,
    include_tier2: bool,
) -> AddressLookupResult | None:
    """ILIKE substring match — confidence 1.0 if found."""
    stmt = _base_query(include_tier2).where(
        Property.address.ilike(f"%{address_text}%")
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        return None

    # If multiple matches, prefer tier-1 first, then shortest address (most specific)
    rows_sorted = sorted(rows, key=lambda p: (
        0 if p.relationship_status == "active" else 1,
        len(p.address or ""),
    ))
    return _to_result(rows_sorted[0], confidence=1.0, match_type="exact")


# ---------------------------------------------------------------------------
# Strategy 2: Fuzzy match (street number + first word)
# ---------------------------------------------------------------------------

async def _fuzzy_match(
    address_text: str,
    db: AsyncSession,
    include_tier2: bool,
) -> AddressLookupResult | None:
    """Extract street number + first word, ILIKE %num%word% — confidence 0.6-0.8."""
    num, word = _extract_street_parts(address_text)
    if not num or not word:
        return None

    stmt = _base_query(include_tier2).where(
        Property.address.ilike(f"%{num}%{word}%")
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        return None

    if len(rows) == 1:
        return _to_result(rows[0], confidence=0.8, match_type="fuzzy")

    # Multiple results — pick best (prefer tier-1, then shortest address)
    rows_sorted = sorted(rows, key=lambda p: (
        0 if p.relationship_status == "active" else 1,
        len(p.address or ""),
    ))
    return _to_result(rows_sorted[0], confidence=0.6, match_type="fuzzy")


# ---------------------------------------------------------------------------
# Strategy 3: Geocode fallback
# ---------------------------------------------------------------------------

async def _geocode_match(
    address_text: str,
    db: AsyncSession,
    include_tier2: bool,
) -> AddressLookupResult | None:
    """Geocode the address, then find nearest Property within 0.5 miles — confidence 0.7."""
    try:
        from wex_platform.services.geocoding_service import geocode_location

        geo = await geocode_location(address_text)
        if not geo or geo.lat is None or geo.lng is None:
            return None
    except Exception:
        logger.debug("Geocode fallback unavailable", exc_info=True)
        return None

    # Query all properties with lat/lng populated
    stmt = _base_query(include_tier2).where(
        Property.lat.isnot(None),
        Property.lng.isnot(None),
    )
    result = await db.execute(stmt)
    properties = result.scalars().all()

    if not properties:
        return None

    # Find the nearest property within the radius
    best_prop = None
    best_dist = float("inf")

    for prop in properties:
        dist = _haversine_miles(geo.lat, geo.lng, prop.lat, prop.lng)
        if dist <= _GEOCODE_RADIUS_MILES and dist < best_dist:
            best_dist = dist
            best_prop = prop

    if best_prop is None:
        return None

    return _to_result(best_prop, confidence=0.7, match_type="geocode")


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

async def lookup_by_address(
    address_text: str,
    db: AsyncSession,
    include_tier2: bool = True,
) -> AddressLookupResult:
    """Look up a property by street address using a three-strategy pipeline.

    Strategies are tried in order:
      1. **Exact** – ILIKE substring match (confidence 1.0)
      2. **Fuzzy** – street number + first street-name word (confidence 0.6-0.8)
      3. **Geocode fallback** – geocode then nearest within 0.5 mi (confidence 0.7)

    Returns an ``AddressLookupResult``; ``result.found`` is ``False`` if
    every strategy fails.
    """
    if not address_text or not address_text.strip():
        return AddressLookupResult()

    address_text = address_text.strip()

    # Strategy 1: Exact
    result = await _exact_match(address_text, db, include_tier2)
    if result:
        logger.info("Address lookup exact match: %s -> %s", address_text, result.property_id)
        return result

    # Strategy 2: Fuzzy
    result = await _fuzzy_match(address_text, db, include_tier2)
    if result:
        logger.info("Address lookup fuzzy match: %s -> %s", address_text, result.property_id)
        return result

    # Strategy 3: Geocode fallback
    result = await _geocode_match(address_text, db, include_tier2)
    if result:
        logger.info("Address lookup geocode match: %s -> %s", address_text, result.property_id)
        return result

    logger.info("Address lookup found no match for: %s", address_text)
    return AddressLookupResult()

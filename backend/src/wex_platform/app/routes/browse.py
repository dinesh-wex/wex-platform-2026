"""Browse Collection API — public, filterable grid of in-network warehouses.

All responses apply STRICT visibility controls:
  - Location: city + state only (no street address)
  - Sqft: rounded to a range (nearest 5K boundaries)
  - Rate: +/- 15% of actual rate
  - No owner info, no supplier name, no exact values
"""

import math
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from wex_platform.domain.models import Property, PropertyKnowledge, PropertyListing
from wex_platform.infra.database import get_db

router = APIRouter(prefix="/api/browse", tags=["browse"])


# ---------------------------------------------------------------------------
# Helpers — transform exact values into public-safe ranges
# ---------------------------------------------------------------------------

def _sqft_range(exact: int) -> dict:
    """Round sqft to nearest 5K boundaries for public display.

    e.g. 7,500 -> (5000, 10000), 3,200 -> (0, 5000), 27,000 -> (25000, 30000)
    """
    step = 5000
    low = (exact // step) * step
    high = low + step
    return {"min": low, "max": high, "display": f"{low:,}-{high:,} sqft"}


def _rate_range(exact: float) -> dict:
    """Show +/- 15% of actual rate, rounded to 2 decimals."""
    low = round(exact * 0.85, 2)
    high = round(exact * 1.15, 2)
    return {
        "min": low,
        "max": high,
        "display": f"${low:.2f}-${high:.2f}/sqft",
    }


def _building_type_label(property_type: Optional[str]) -> str:
    """Map property_type to a display-friendly badge label."""
    mapping = {
        "warehouse": "Warehouse",
        "distribution": "Distribution",
        "manufacturing": "Manufacturing",
        "flex": "Flex",
        "cold_storage": "Cold Storage",
    }
    return mapping.get(property_type or "", "Warehouse")


def _extract_features(pk: PropertyKnowledge) -> list[dict]:
    """Build feature list from PropertyKnowledge fields."""
    features = []
    if pk.dock_doors_receiving and pk.dock_doors_receiving > 0:
        features.append({"key": "dock", "label": "Dock Doors"})
    if pk.has_office:
        features.append({"key": "office", "label": "Office"})
    if pk.has_sprinkler:
        features.append({"key": "climate", "label": "Climate"})
    if pk.power_supply:
        features.append({"key": "power", "label": "Power"})
    if pk.parking_spaces and pk.parking_spaces > 0:
        features.append({"key": "parking", "label": "Parking"})
    if pk.clear_height_ft and pk.clear_height_ft >= 20:
        features.append({"key": "24_7", "label": "24/7"})
    return features


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/listings")
async def get_listings(
    db: AsyncSession = Depends(get_db),
    city: Optional[str] = Query(None, description="Filter by city name (partial match)"),
    state: Optional[str] = Query(None, description="Filter by state abbreviation"),
    min_sqft: Optional[int] = Query(None, description="Minimum available sqft"),
    max_sqft: Optional[int] = Query(None, description="Maximum available sqft"),
    use_type: Optional[str] = Query(None, description="Use type: storage, light_ops, distribution, any"),
    features: Optional[str] = Query(None, description="Comma-separated feature keys: dock,office,climate,power,24_7,parking"),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
):
    """Return paginated in-network warehouses with CONTROLLED visibility.

    Only returns: neighbourhood location, sqft RANGE, rate RANGE, feature flags.
    Does NOT return: exact address, exact sqft, exact rate, owner info, supplier name.
    """

    # Base query: only active properties with a PropertyListing and PropertyKnowledge
    query = (
        select(Property)
        .options(
            joinedload(Property.knowledge),
            joinedload(Property.listing),
        )
        .where(Property.relationship_status == "active")
    )

    # --- Filters ---
    conditions = []
    need_pk_join = False
    need_pl_join = False

    if city:
        conditions.append(Property.city.ilike(f"%{city}%"))
    if state:
        conditions.append(Property.state.ilike(f"%{state}%"))

    # Sqft filters apply to PropertyListing.max_sqft (available space)
    if min_sqft is not None:
        conditions.append(PropertyListing.max_sqft >= min_sqft)
        need_pl_join = True
    if max_sqft is not None:
        conditions.append(PropertyListing.max_sqft <= max_sqft)
        need_pl_join = True

    # Use type maps to activity_tier on PropertyKnowledge
    if use_type and use_type.lower() != "any":
        use_type_map = {
            "storage": "storage_only",
            "light_ops": "storage_light_assembly",
            "distribution": "distribution",
        }
        mapped = use_type_map.get(use_type.lower(), use_type.lower())
        conditions.append(PropertyKnowledge.activity_tier == mapped)
        need_pk_join = True

    # Feature filters
    if features:
        feature_list = [f.strip().lower() for f in features.split(",") if f.strip()]
        need_pk_join = True
        for feat in feature_list:
            if feat == "dock":
                conditions.append(PropertyKnowledge.dock_doors_receiving > 0)
            elif feat == "office":
                conditions.append(PropertyKnowledge.has_office == True)  # noqa: E712
            elif feat == "climate":
                conditions.append(PropertyKnowledge.has_sprinkler == True)  # noqa: E712
            elif feat == "power":
                conditions.append(PropertyKnowledge.power_supply.isnot(None))
            elif feat == "parking":
                conditions.append(PropertyKnowledge.parking_spaces > 0)

    # Add joins as needed
    if need_pl_join:
        query = query.join(PropertyListing, PropertyListing.property_id == Property.id)
    if need_pk_join:
        query = query.join(PropertyKnowledge, PropertyKnowledge.property_id == Property.id)

    if conditions:
        query = query.where(and_(*conditions))

    # --- Count total ---
    count_query = select(sa_func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # --- Paginate ---
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    result = await db.execute(query)
    properties = result.unique().scalars().all()

    # --- Build response with CONTROLLED visibility ---
    listings = []
    for prop in properties:
        pk = prop.knowledge
        pl = prop.listing
        if not pk or not pl:
            continue

        listing = {
            "id": prop.id,
            "location": {
                "city": prop.city or "Unknown",
                "state": prop.state or "",
                "display": f"{prop.city or 'Unknown'}, {prop.state or ''}".strip(", "),
            },
            "sqft_range": _sqft_range(pl.max_sqft),
            "rate_range": _rate_range(pl.supplier_rate_per_sqft),
            "building_type": _building_type_label(prop.property_type),
            "features": _extract_features(pk),
            "has_image": bool(prop.primary_image_url),
        }
        listings.append(listing)

    return {
        "listings": listings,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": math.ceil(total / per_page) if total > 0 else 0,
    }


@router.get("/locations")
async def get_locations(
    db: AsyncSession = Depends(get_db),
    q: str = Query("", description="Search query for city/state autocomplete"),
):
    """Return distinct city/state pairs for autocomplete, filtered by query."""
    query = (
        select(Property.city, Property.state)
        .where(Property.relationship_status == "active")
        .where(Property.city.isnot(None))
        .distinct()
    )

    if q:
        query = query.where(
            Property.city.ilike(f"%{q}%") | Property.state.ilike(f"%{q}%")
        )

    query = query.limit(20)
    result = await db.execute(query)
    rows = result.all()

    return {
        "locations": [
            {"city": row.city, "state": row.state, "display": f"{row.city}, {row.state}"}
            for row in rows
            if row.city
        ]
    }

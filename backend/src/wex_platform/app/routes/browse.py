"""Browse Collection API — public, filterable grid of in-network warehouses.

All responses apply STRICT visibility controls:
  - Location: city + state only (no street address)
  - Sqft: rounded to a range (nearest 5K boundaries)
  - Rate: +/- 15% of actual rate (Tier 1 only; Tier 2 rate is always null)
  - No owner info, no supplier name, no exact values
"""

import hashlib
import logging
import math
import random as _random
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import case, select, and_, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from wex_platform.app.config import get_settings
from wex_platform.domain.models import (
    Buyer,
    BuyerConversation,
    BuyerNeed,
    Property,
    PropertyEvent,
    PropertyKnowledge,
    PropertyListing,
)
from wex_platform.domain.sms_models import SMSConversationState
from wex_platform.infra.database import get_db
from wex_platform.services.engagement_bridge import EngagementBridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/browse", tags=["browse"])

# Tier 2 browsable statuses (non-active properties shown publicly)
TIER2_STATUSES = ("prospect", "contacted", "interested", "earncheck_only")
# All browsable statuses (Tier 1 + Tier 2)
ALL_BROWSABLE_STATUSES = ("active",) + TIER2_STATUSES


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


def _build_specs(pk) -> dict:
    """Build public-safe specs dict from PropertyKnowledge."""
    specs = {}
    field_map = {
        "clear_height_ft": pk.clear_height_ft,
        "dock_doors": (pk.dock_doors_receiving or 0) + (pk.dock_doors_shipping or 0) if hasattr(pk, 'dock_doors_shipping') else (pk.dock_doors_receiving or 0),
        "parking_spaces": pk.parking_spaces,
        "has_office": pk.has_office,
        "has_sprinkler": pk.has_sprinkler,
        "power_supply": pk.power_supply,
        "year_built": pk.year_built,
        "construction_type": pk.construction_type,
        "zoning": pk.zoning,
        "building_size_sqft": pk.building_size_sqft,
    }
    for key, val in field_map.items():
        if val is not None and val != 0 and val is not False:
            specs[key] = val
    # Special case: has_office/has_sprinkler should include False values if explicitly set
    if pk.has_office is not None:
        specs["has_office"] = pk.has_office
    if pk.has_sprinkler is not None:
        specs["has_sprinkler"] = pk.has_sprinkler
    return specs


def _obfuscated_coords(real_lat: float, real_lng: float, property_id: str, radius_meters: float = 800) -> dict:
    """Deterministic offset so the same property always shows the same approximate circle."""
    seed = int(hashlib.sha256(property_id.encode()).hexdigest()[:16], 16)
    rng = _random.Random(seed)
    distance = rng.uniform(200, radius_meters)
    angle = rng.uniform(0, 2 * math.pi)
    earth_radius = 6378137.0
    offset_lat = distance * math.cos(angle) / earth_radius
    offset_lng = distance * math.sin(angle) / (earth_radius * math.cos(math.pi * real_lat / 180))
    return {
        "lat": round(real_lat + (offset_lat * 180 / math.pi), 6),
        "lng": round(real_lng + (offset_lng * 180 / math.pi), 6),
    }


def _filter_property_images(image_urls: list | None) -> list[str]:
    """Strip only Google Maps roadmap images (they reveal exact location via red pin marker).
    Keep satellite and street view images — they show the building itself."""
    if not image_urls:
        return []
    return [
        url for url in image_urls
        if isinstance(url, str) and not (
            "maps.googleapis.com" in url and "maptype=roadmap" in url
        )
    ]


def _circle_path(lat: float, lng: float, radius_km: float = 0.8, num_points: int = 24) -> str:
    """Generate polygon points approximating a circle for the Static Maps API path param."""
    points = []
    for i in range(num_points + 1):
        angle = 2 * math.pi * i / num_points
        d_lat = (radius_km / 111) * math.cos(angle)
        d_lng = (radius_km / (111 * math.cos(math.radians(lat)))) * math.sin(angle)
        points.append(f"{lat + d_lat:.6f},{lng + d_lng:.6f}")
    return "|".join(points)


def _approximate_area_map_url(lat: float, lng: float, api_key: str) -> str:
    """Silver-styled static map with an emerald circle — used as card thumbnail fallback."""
    circle = _circle_path(lat, lng)
    styles = (
        "&style=feature:poi|visibility:off"
        "&style=element:geometry|color:0xf5f5f5"
        "&style=element:labels.text.fill|color:0x616161"
        "&style=element:labels.text.stroke|color:0xf5f5f5"
        "&style=feature:road|element:geometry|color:0xffffff"
        "&style=feature:road.highway|element:geometry.fill|color:0xe8e8e8"
        "&style=feature:water|element:geometry|color:0xd4e6f1"
    )
    return (
        f"https://maps.googleapis.com/maps/api/staticmap?"
        f"center={lat},{lng}&zoom=13&size=800x400&scale=2&maptype=roadmap"
        f"{styles}"
        f"&path=color:0x05966680|weight:2|fillcolor:0x10b98126|{circle}"
        f"&key={api_key}"
    )


def _fallback_map_image(prop, api_key: str | None) -> list[str]:
    """Generate an approximate-area static map as fallback when no real photos exist."""
    if not api_key or not prop.lat or not prop.lng:
        return []
    coords = _obfuscated_coords(prop.lat, prop.lng, str(prop.id))
    return [_approximate_area_map_url(coords["lat"], coords["lng"], api_key)]


def _extract_features(pk: PropertyKnowledge) -> list[dict]:
    """Build feature list from PropertyKnowledge fields."""
    features = []
    if pk.dock_doors_receiving and pk.dock_doors_receiving > 0:
        features.append({"key": "dock", "label": "Dock Doors"})
    if pk.has_office:
        features.append({"key": "office", "label": "Office"})
    if pk.power_supply:
        features.append({"key": "power", "label": "Power"})
    if pk.parking_spaces and pk.parking_spaces > 0:
        features.append({"key": "parking", "label": "Parking"})
    if pk.clear_height_ft and pk.clear_height_ft >= 20:
        features.append({"key": "24_7", "label": "24/7"})
    return features


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------

class Tier2InterestBody(BaseModel):
    name: str
    email: str
    phone: str
    note: str | None = None


class QualifyRequest(BaseModel):
    sqft_needed: int
    timing: str  # "asap", "1_month", "3_months", "6_months"
    name: str
    phone: str
    email: str | None = None
    action: str  # "book_tour" or "instant_book"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _find_or_create_buyer(
    db: AsyncSession, name: str, phone: str, email: str | None = None,
) -> "Buyer":
    """Find existing Buyer by phone (dedup) or create a new one."""
    result = await db.execute(select(Buyer).where(Buyer.phone == phone))
    buyer = result.scalar_one_or_none()
    if not buyer:
        buyer = Buyer(
            id=str(uuid.uuid4()),
            name=name,
            phone=phone,
            email=email,
        )
        db.add(buyer)
        await db.flush()
    return buyer


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
    tier: Optional[str] = Query("all", description="Filter: tier1, tier2, or all"),
    page: int = Query(1, ge=1),
    per_page: int = Query(12, ge=1, le=50),
):
    """Return paginated browsable warehouses with CONTROLLED visibility.

    Only returns: neighbourhood location, sqft RANGE, rate RANGE (Tier 1 only), feature flags.
    Does NOT return: exact address, exact sqft, exact rate, owner info, supplier name.
    Tier 2 listings never expose rate_range (always null).
    """

    # Sort: Tier 1 first (active=0), then Tier 2 (others=1)
    tier_order = case((Property.relationship_status == "active", 0), else_=1)

    # Base query with eager-loaded relationships
    # Use outerjoin for PropertyListing because Tier 2 properties may lack one
    query = (
        select(Property)
        .outerjoin(PropertyListing, PropertyListing.property_id == Property.id)
        .options(
            joinedload(Property.knowledge),
            joinedload(Property.listing),
        )
    )

    # --- Tier filter on relationship_status ---
    if tier == "tier1":
        query = query.where(Property.relationship_status == "active")
    elif tier == "tier2":
        query = query.where(Property.relationship_status.in_(TIER2_STATUSES))
    else:  # "all" or any other value
        query = query.where(Property.relationship_status.in_(ALL_BROWSABLE_STATUSES))

    # --- Filters ---
    conditions = []
    need_pk_join = False

    if city:
        conditions.append(Property.city.ilike(f"%{city}%"))
    if state:
        conditions.append(Property.state.ilike(f"%{state}%"))

    # Sqft filters apply to PropertyListing.max_sqft (building capacity for browse)
    if min_sqft is not None:
        conditions.append(PropertyListing.max_sqft >= min_sqft)
    if max_sqft is not None:
        conditions.append(PropertyListing.max_sqft <= max_sqft)

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
            elif feat == "power":
                conditions.append(PropertyKnowledge.power_supply.isnot(None))
            elif feat == "parking":
                conditions.append(PropertyKnowledge.parking_spaces > 0)

    # Add PK join only if needed (PL outerjoin is already in base query)
    if need_pk_join:
        query = query.join(PropertyKnowledge, PropertyKnowledge.property_id == Property.id)

    if conditions:
        query = query.where(and_(*conditions))

    # --- Count total ---
    count_query = select(sa_func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # --- Paginate (Tier 1 first, then Tier 2) ---
    offset = (page - 1) * per_page
    query = query.order_by(tier_order, Property.city).offset(offset).limit(per_page)

    result = await db.execute(query)
    properties = result.unique().scalars().all()

    # --- Build response with CONTROLLED visibility ---
    listings = []
    for prop in properties:
        pk = prop.knowledge
        pl = prop.listing
        is_tier1 = prop.relationship_status == "active"

        # PropertyKnowledge is required for any listing to display
        if not pk:
            continue

        # Tier 1 requires a PropertyListing; Tier 2 can proceed without one
        if is_tier1 and not pl:
            continue

        # Determine sqft_range: prefer PropertyListing.max_sqft, fall back to
        # PropertyKnowledge.building_size_sqft for Tier 2
        sqft_source = None
        if pl and pl.max_sqft:
            sqft_source = pl.max_sqft
        elif pk.building_size_sqft:
            sqft_source = pk.building_size_sqft

        # Determine rate_range: Tier 2 privacy — never expose pricing
        rate = None
        if is_tier1 and pl and pl.supplier_rate_per_sqft:
            rate = _rate_range(pl.supplier_rate_per_sqft)

        listing = {
            "id": prop.id,
            "tier": 1 if is_tier1 else 2,
            "location": {
                "city": prop.city or "Unknown",
                "state": prop.state or "",
                "display": f"{prop.city or 'Unknown'}, {prop.state or ''}".strip(", "),
            },
            "sqft_range": _sqft_range(sqft_source) if sqft_source else None,
            "rate_range": rate,
            "building_type": _building_type_label(prop.property_type),
            "features": _extract_features(pk),
            "has_image": True,
            "image_url": (
                _filter_property_images(prop.image_urls)
                or _fallback_map_image(prop, get_settings().google_maps_api_key)
                or [None]
            )[0],
        }
        listings.append(listing)

    return {
        "listings": listings,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": math.ceil(total / per_page) if total > 0 else 0,
    }


@router.get("/listings/{property_id}")
async def get_listing_detail(
    property_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return detailed listing information for a single property.

    Applies the same visibility controls as the listings grid:
    - Location: city + state only
    - Sqft: rounded to a range
    - Rate: +/- 15% (Tier 1 only)
    - Specs and features from PropertyKnowledge
    - No owner info, no supplier name, no exact values
    """

    # Load Property with eager-loaded relationships
    result = await db.execute(
        select(Property)
        .options(
            joinedload(Property.knowledge),
            joinedload(Property.listing),
        )
        .where(Property.id == property_id)
    )
    prop = result.unique().scalar_one_or_none()

    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Don't reveal declined/churned properties
    if prop.relationship_status not in ALL_BROWSABLE_STATUSES:
        raise HTTPException(status_code=404, detail="Property not found")

    pk = prop.knowledge
    pl = prop.listing
    is_tier1 = prop.relationship_status == "active"

    # Determine sqft_range: prefer PropertyListing.max_sqft, fall back to
    # PropertyKnowledge.building_size_sqft for Tier 2
    sqft_source = None
    if pl and pl.max_sqft:
        sqft_source = pl.max_sqft
    elif pk and pk.building_size_sqft:
        sqft_source = pk.building_size_sqft

    # Determine rate_range: Tier 2 privacy — never expose pricing
    rate = None
    if is_tier1 and pl and pl.supplier_rate_per_sqft:
        rate = _rate_range(pl.supplier_rate_per_sqft)

    # Strip Google Maps screenshots — the approximate map component handles location visuals
    filtered_images = _filter_property_images(prop.image_urls)

    # Fallback: branded static map at approximate coords when no real photos
    if not filtered_images:
        filtered_images = _fallback_map_image(prop, get_settings().google_maps_api_key)

    return {
        "id": prop.id,
        "tier": 1 if is_tier1 else 2,
        "location": {
            "city": prop.city or "Unknown",
            "state": prop.state or "",
            "display": f"{prop.city or 'Unknown'}, {prop.state or ''} Area".strip(", "),
        },
        "approximate_location": _obfuscated_coords(prop.lat, prop.lng, str(prop.id)) if (prop.lat and prop.lng) else None,
        "building_type": _building_type_label(prop.property_type),
        "features": _extract_features(pk) if pk else [],
        "specs": _build_specs(pk) if pk else {},
        "sqft_range": _sqft_range(sqft_source) if sqft_source else None,
        "rate_range": rate,
        "instant_book_eligible": pl.instant_book_eligible if (pl and is_tier1) else False,
        "tour_required": pl.tour_required if (pl and is_tier1) else True,
        "has_image": bool(filtered_images),
        "image_url": filtered_images[0] if filtered_images else None,
        "image_urls": filtered_images,
    }


@router.get("/locations")
async def get_locations(
    db: AsyncSession = Depends(get_db),
    q: str = Query("", description="Search query for city/state autocomplete"),
):
    """Return distinct city/state pairs for autocomplete, filtered by query.

    Includes both Tier 1 (active) and Tier 2 cities.
    """
    query = (
        select(Property.city, Property.state)
        .where(Property.relationship_status.in_(ALL_BROWSABLE_STATUSES))
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


@router.post("/listings/{property_id}/interest")
async def submit_tier2_interest(
    property_id: str,
    body: Tier2InterestBody,
    db: AsyncSession = Depends(get_db),
):
    """Capture buyer interest for a Tier 2 property.

    Creates/finds a Buyer by phone (dedup), creates a minimal BuyerNeed
    from the property's city/state, and logs a PropertyEvent.
    """

    # 1. Load Property, verify it exists and is Tier 2
    prop_result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    prop = prop_result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")
    if prop.relationship_status not in TIER2_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Interest capture is only available for Tier 2 properties",
        )

    # 2. Find or create Buyer by phone (dedup)
    buyer = await _find_or_create_buyer(db, body.name, body.phone, body.email)

    # 3. Create minimal BuyerNeed from property's city/state
    buyer_need = BuyerNeed(
        id=str(uuid.uuid4()),
        buyer_id=buyer.id,
        city=prop.city,
        state=prop.state,
        status="active",
    )
    db.add(buyer_need)

    # 4. Log PropertyEvent
    event = PropertyEvent(
        id=str(uuid.uuid4()),
        property_id=property_id,
        event_type="buyer_interest",
        actor=body.phone,
        metadata_={"source": "browse", "note": body.note},
    )
    db.add(event)

    await db.commit()

    return {"ok": True, "message": "We'll check availability and get back to you"}


@router.post("/listings/{property_id}/qualify")
async def qualify_at_commitment(
    property_id: str,
    body: QualifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Qualify a buyer at commitment — fit-check against real-time availability,
    log a PropertyEvent, and either initiate booking (match) or surface
    clearing-engine alternatives (mismatch).
    """

    # 1. Load Property + PropertyListing
    result = await db.execute(
        select(Property)
        .options(
            joinedload(Property.listing),
        )
        .where(Property.id == property_id)
    )
    prop = result.unique().scalar_one_or_none()

    # 2. 404 if not found or not browsable
    if not prop or prop.relationship_status not in ALL_BROWSABLE_STATUSES:
        raise HTTPException(status_code=404, detail="Property not found")

    pl = prop.listing

    # 3. Fit check against real-time available_sqft (NOT max_sqft)
    is_fit = False
    mismatch_reason: str | None = None

    if not pl:
        mismatch_reason = "no_listing_data"
    elif pl.available_sqft is None:
        mismatch_reason = "availability_unknown"
    else:
        above_max = body.sqft_needed > (pl.available_sqft * 1.1)
        below_min = (pl.min_sqft is not None) and (body.sqft_needed < pl.min_sqft)

        if above_max:
            mismatch_reason = (
                f"sqft_exceeds_available: requested {body.sqft_needed}, "
                f"available {pl.available_sqft}"
            )
        elif below_min:
            mismatch_reason = (
                f"sqft_below_minimum: requested {body.sqft_needed}, "
                f"minimum {pl.min_sqft}"
            )
        else:
            is_fit = True

    # 4. Find or create Buyer (dedup by phone)
    buyer = await _find_or_create_buyer(db, body.name, body.phone, body.email)

    # 5. Create BuyerNeed
    buyer_need = BuyerNeed(
        id=str(uuid.uuid4()),
        buyer_id=buyer.id,
        city=prop.city,
        state=prop.state,
        lat=prop.lat,
        lng=prop.lng,
        min_sqft=int(body.sqft_needed * 0.8),
        max_sqft=int(body.sqft_needed * 1.2),
        status="active",
    )
    db.add(buyer_need)
    await db.flush()

    # --- WS5: Cross-channel continuity ---
    # Create SMSConversationState so voice/SMS channels pick up browse context.
    # The Vapi webhook (vapi_webhook.py) already queries this table by phone
    # to seed VoiceCallState. The SMS pipeline loads it for conversation state.
    # focused_match_id uses Property.id which equals old Warehouse.id (same UUIDs
    # from Feb 2026 migration) — this is why cross-channel seeding works.

    # Find or create conversation record
    conv_result = await db.execute(
        select(BuyerConversation)
        .where(BuyerConversation.buyer_id == buyer.id)
        .order_by(BuyerConversation.created_at.desc())
        .limit(1)
    )
    conversation = conv_result.scalar_one_or_none()
    if not conversation:
        conversation = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
        )
        db.add(conversation)
        await db.flush()

    # Find existing SMS state or create new one
    sms_result = await db.execute(
        select(SMSConversationState)
        .where(SMSConversationState.phone == body.phone)
        .order_by(SMSConversationState.updated_at.desc())
        .limit(1)
    )
    sms_state = sms_result.scalar_one_or_none()

    if not sms_state:
        sms_state = SMSConversationState(
            id=str(uuid.uuid4()),
            buyer_id=buyer.id,
            conversation_id=conversation.id,
            buyer_need_id=buyer_need.id,
            phone=body.phone,
            phase="PRESENTING",
            turn=1,
            criteria_snapshot={
                "location": f"{prop.city}, {prop.state}",
                "sqft": body.sqft_needed,
            },
            presented_match_ids=[property_id],
            focused_match_id=property_id,
            renter_first_name=body.name.split()[0] if body.name else None,
            renter_last_name=body.name.split()[-1] if body.name and len(body.name.split()) > 1 else None,
            buyer_email=body.email,
        )
        db.add(sms_state)
    else:
        # Update existing state with browse context (don't duplicate)
        sms_state.buyer_need_id = buyer_need.id
        sms_state.focused_match_id = property_id
        presented = list(sms_state.presented_match_ids or [])
        if property_id not in presented:
            presented.append(property_id)
            sms_state.presented_match_ids = presented
        sms_state.renter_first_name = sms_state.renter_first_name or (body.name.split()[0] if body.name else None)
        sms_state.buyer_email = sms_state.buyer_email or body.email

    await db.flush()

    # 6. Log PropertyEvent (always — both match and mismatch)
    event = PropertyEvent(
        id=str(uuid.uuid4()),
        property_id=property_id,
        event_type="buyer_qualified",
        actor=body.phone,
        metadata_={
            "sqft_requested": body.sqft_needed,
            "action": body.action,
            "result": "match" if is_fit else "mismatch",
            "mismatch_reason": mismatch_reason,
        },
    )
    db.add(event)

    # 7. Match path — initiate booking via EngagementBridge
    if is_fit:
        bridge = EngagementBridge(db)
        booking_result = await bridge.initiate_booking(
            property_id,
            body.phone,
            body.name,
            body.email,
            buyer_need.id,
            source_channel="browse",
        )
        await db.commit()

        if "error" in booking_result:
            raise HTTPException(status_code=500, detail=booking_result["error"])

        return {
            "status": "match",
            "engagement_id": booking_result["engagement_id"],
        }

    # 8. Mismatch path — try clearing engine for alternatives
    alternatives_count = 0
    try:
        from wex_platform.services.clearing_engine import ClearingEngine

        engine = ClearingEngine()
        clearing_result = await engine.run_clearing(
            buyer_need_id=buyer_need.id, db=db,
        )
        tier1_matches = clearing_result.get("tier1", []) if clearing_result else []
        alternatives_count = len(tier1_matches)
    except Exception:
        logger.exception("Clearing engine failed for buyer_need %s", buyer_need.id)

    await db.commit()

    return {
        "status": "mismatch",
        "reasons": [mismatch_reason],
        "alternatives_count": alternatives_count,
    }

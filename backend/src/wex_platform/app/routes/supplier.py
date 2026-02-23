"""Supplier-side API routes.

ECONOMIC ISOLATION: These endpoints only expose supplier-domain data.
No buyer rates, buyer identities, or WEx spread are ever returned.
"""

import time
import uuid
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wex_platform.infra.database import get_db
from wex_platform.domain.models import (
    Warehouse,
    TruthCore,
    ContextualMemory,
    SupplierAgreement,
    SupplierLedger,
    ToggleHistory,
    TruthCoreChange,
    Deal,
    DealEvent,
    PropertyProfile,
)
from wex_platform.domain.schemas import TruthCoreCreate, TruthCoreResponse
from wex_platform.services.pricing_engine import calculate_default_buyer_rate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/supplier", tags=["supplier"])

# ---------------------------------------------------------------------------
# Gemini search guardrails (in-memory rate limiting + negative cache)
# ---------------------------------------------------------------------------
_search_timestamps: dict[str, list[float]] = defaultdict(list)
_SEARCH_RATE_LIMIT = 10  # max searches per minute
_NOT_FOUND_CACHE: dict[str, dict] = {}  # normalized_address -> {"ts": float, "ttl": int}


def _is_cache_valid(entry: dict | None) -> bool:
    """Check if a cache entry is still within its TTL."""
    if entry is None:
        return False
    return (time.time() - entry["ts"]) < entry["ttl"]


# ---------------------------------------------------------------------------
# Inline request / response models
# ---------------------------------------------------------------------------


class EstimateRequest(BaseModel):
    """Request body for the WEx Space Estimator."""

    sqft: int
    city: str | None = None
    state: str | None = None
    zip: str | None = None


# ---------------------------------------------------------------------------
# Street View image proxy (hides API key from frontend)
# ---------------------------------------------------------------------------

@router.get("/street-view")
async def street_view_image(address: str = Query(..., description="Property address")):
    """Proxy a Google Maps Street View image for the given address.

    Fetches the image server-side and streams it back so the API key
    is never exposed to the browser.
    """
    import urllib.request
    from fastapi.responses import Response
    from wex_platform.app.config import get_settings

    settings = get_settings()
    maps_key = settings.google_maps_api_key
    if not maps_key:
        raise HTTPException(status_code=503, detail="Maps API key not configured")

    encoded_addr = urllib.parse.quote(address)
    url = (
        f"https://maps.googleapis.com/maps/api/streetview"
        f"?size=600x400&location={encoded_addr}&key={maps_key}"
    )
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
            content_type = resp.headers.get("Content-Type", "image/jpeg")
    except Exception as e:
        logger.error("Street View proxy failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to fetch image")

    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


class PageViewRequest(BaseModel):
    path: str
    referrer: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    session_id: str | None = None
    is_test: bool = False


class TrackEventRequest(BaseModel):
    event: str
    properties: dict = {}
    session_id: str
    is_test: bool = False


class LeadCaptureRequest(BaseModel):
    email: str
    address: str | None = None
    full_name: str | None = None
    phone: str | None = None
    company: str | None = None
    sqft: int | None = None
    revenue: float | None = None
    rate: float | None = None
    market_rate_low: float | None = None
    market_rate_high: float | None = None
    recommended_rate: float | None = None
    pricing_path: str | None = None
    session_id: str | None = None
    is_test: bool = False


class ToggleRequest(BaseModel):
    """Request body for toggling activation status."""

    status: str  # "on" or "off"
    reason: Optional[str] = None


class ChatMessageRequest(BaseModel):
    """Request body for sending a chat message during activation."""

    warehouse_id: str
    message: str
    conversation_history: list[dict] = []
    current_step: int = 1
    extracted_fields: dict = {}
    idle_sqft: int | None = None
    pricing_path: str | None = None
    session_id: str | None = None


class ActivationStartRequest(BaseModel):
    """Request body for starting a new activation conversation."""

    warehouse_id: str


class SupplierLoginRequest(BaseModel):
    """Request body for supplier login by email."""

    email: str


class RevenueResponse(BaseModel):
    """Revenue summary for a warehouse."""

    monthly_income: float
    total_earned: float
    projected_annual: float
    active_placements: int


class WarehouseListItem(BaseModel):
    """Supplier-safe warehouse list item (no buyer data)."""

    id: str
    owner_name: Optional[str] = None
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    building_size_sqft: Optional[int] = None
    year_built: Optional[int] = None
    construction_type: Optional[str] = None
    primary_image_url: Optional[str] = None
    activation_status: Optional[str] = None
    supplier_rate_per_sqft: Optional[float] = None
    memory_count: int = 0
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class WarehouseDetailResponse(BaseModel):
    """Full warehouse detail for the supplier side (no buyer data)."""

    id: str
    owner_name: Optional[str] = None
    owner_email: Optional[str] = None
    owner_phone: Optional[str] = None
    address: str
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    building_size_sqft: Optional[int] = None
    lot_size_acres: Optional[float] = None
    year_built: Optional[int] = None
    construction_type: Optional[str] = None
    zoning: Optional[str] = None
    primary_image_url: Optional[str] = None
    image_urls: list[str] = []
    source_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    truth_core: Optional[dict] = None
    memories: list[dict] = []
    supplier_agreements: list[dict] = []
    supplier_ledger: list[dict] = []

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/estimate")
async def space_estimate(body: EstimateRequest):
    """WEx Space Estimator — returns instant revenue range.

    No auth required. Powers the Phase 1 activation hook
    and the standalone marketing/lead gen tool.

    If a zipcode is provided, attempts Gemini Search grounded NNN
    rate lookup (cached 30 days). Falls back to regional defaults.
    """
    # Fallback: Regional base rates ($/sqft/month) for industrial warehouse
    REGION_RATES = {
        "CA": (0.85, 1.10), "TX": (0.65, 0.85), "AZ": (0.60, 0.80),
        "SC": (0.55, 0.75), "MD": (0.70, 0.90), "GA": (0.65, 0.85),
        "MI": (0.60, 0.80), "FL": (0.70, 0.90), "IL": (0.65, 0.85),
        "NY": (0.80, 1.05), "NJ": (0.75, 1.00), "PA": (0.65, 0.85),
        "OH": (0.55, 0.75), "WA": (0.75, 0.95), "OR": (0.70, 0.90),
    }
    DEFAULT_RATES = (0.65, 0.90)

    low_rate, high_rate = None, None
    rate_location = None  # Human-readable label for where rates came from

    # --- Tier 1: Exact zip code lookup via Gemini Search ---
    if body.zip:
        try:
            from wex_platform.agents.market_rate_agent import MarketRateAgent
            agent = MarketRateAgent()
            result = await agent.get_nnn_rates(body.zip)
            if result.ok and result.data:
                low_rate = result.data["nnn_low"]
                high_rate = result.data["nnn_high"]
                rate_location = f"{body.city}, {body.state}" if body.city else f"zip {body.zip}"
                logger.info(
                    "NNN rates for zip %s: $%.2f–$%.2f/sqft/mo",
                    body.zip, low_rate, high_rate,
                )
        except Exception as exc:
            logger.warning("MarketRateAgent failed for zip %s: %s", body.zip, exc)

    # --- Tier 2: Nearby cached zip codes (geo proximity) ---
    if (low_rate is None or high_rate is None) and body.zip:
        try:
            from wex_platform.agents.market_rate_agent import MarketRateAgent
            agent = MarketRateAgent()
            nearby = await agent.get_nearby_cached_rate(body.zip)
            if nearby:
                low_rate = nearby["nnn_low"]
                high_rate = nearby["nnn_high"]
                rate_location = f"near {body.city}, {body.state}" if body.city else f"near zip {body.zip}"
                logger.info(
                    "Nearby cached rate for zip %s (from %s): $%.2f–$%.2f/sqft/mo",
                    body.zip, nearby.get("source_zip"), low_rate, high_rate,
                )
        except Exception as exc:
            logger.warning("Nearby rate lookup failed for zip %s: %s", body.zip, exc)

    # --- Tier 3: Hardcoded state-level rates ---
    if low_rate is None or high_rate is None:
        low_rate, high_rate = REGION_RATES.get(body.state, DEFAULT_RATES) if body.state else DEFAULT_RATES
        rate_location = body.state or "your area"

    low_monthly = round(body.sqft * low_rate)
    high_monthly = round(body.sqft * high_rate)

    return {
        "sqft": body.sqft,
        "city": body.city,
        "state": body.state,
        "low_rate": low_rate,
        "high_rate": high_rate,
        "low_monthly": low_monthly,
        "high_monthly": high_monthly,
        "low_annual": low_monthly * 12,
        "high_annual": high_monthly * 12,
        "rate_location": rate_location,
    }


@router.post("/login")
async def supplier_login(
    body: SupplierLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Log in a supplier by email and return their warehouses.

    Looks up warehouses where owner_email matches and returns the supplier's
    identity info along with their warehouse list.
    """
    result = await db.execute(
        select(Warehouse)
        .where(func.lower(Warehouse.owner_email) == func.lower(body.email))
        .options(
            selectinload(Warehouse.truth_core),
            selectinload(Warehouse.memories),
        )
    )
    warehouses = result.scalars().all()

    if not warehouses:
        raise HTTPException(
            status_code=404,
            detail="No warehouses found for this email address",
        )

    # Take owner info from the first warehouse
    first = warehouses[0]

    warehouse_list = []
    for wh in warehouses:
        activation = None
        rate = None
        if wh.truth_core:
            activation = wh.truth_core.activation_status
            rate = wh.truth_core.supplier_rate_per_sqft

        warehouse_list.append(
            WarehouseListItem(
                id=wh.id,
                owner_name=wh.owner_name,
                address=wh.address,
                city=wh.city,
                state=wh.state,
                zip=wh.zip,
                building_size_sqft=wh.building_size_sqft,
                year_built=wh.year_built,
                construction_type=wh.construction_type,
                primary_image_url=wh.primary_image_url,
                activation_status=activation,
                supplier_rate_per_sqft=rate,
                memory_count=len(wh.memories) if wh.memories else 0,
                created_at=wh.created_at,
            ).model_dump()
        )

    return {
        "owner_name": first.owner_name,
        "owner_email": first.owner_email,
        "owner_phone": first.owner_phone,
        "warehouses": warehouse_list,
    }


@router.get("/warehouses", response_model=list[WarehouseListItem])
async def list_warehouses(
    status: Optional[str] = Query(None, description="Filter by activation status: on|off"),
    owner_email: Optional[str] = Query(None, description="Filter warehouses by owner email"),
    db: AsyncSession = Depends(get_db),
):
    """Return all warehouses with truth-core summaries.

    ISOLATION: Only supplier_rate is visible. No buyer pricing data is exposed.
    When owner_email is provided, only warehouses belonging to that supplier are returned.
    """
    query = (
        select(Warehouse)
        .options(
            selectinload(Warehouse.truth_core),
            selectinload(Warehouse.memories),
        )
    )

    if owner_email is not None:
        query = query.where(func.lower(Warehouse.owner_email) == func.lower(owner_email))

    result = await db.execute(query)
    warehouses = result.scalars().all()

    items = []
    for wh in warehouses:
        activation = None
        rate = None
        if wh.truth_core:
            activation = wh.truth_core.activation_status
            rate = wh.truth_core.supplier_rate_per_sqft

        # Apply status filter if provided
        if status is not None:
            if activation != status:
                continue

        items.append(
            WarehouseListItem(
                id=wh.id,
                owner_name=wh.owner_name,
                address=wh.address,
                city=wh.city,
                state=wh.state,
                zip=wh.zip,
                building_size_sqft=wh.building_size_sqft,
                year_built=wh.year_built,
                construction_type=wh.construction_type,
                primary_image_url=wh.primary_image_url,
                activation_status=activation,
                supplier_rate_per_sqft=rate,
                memory_count=len(wh.memories) if wh.memories else 0,
                created_at=wh.created_at,
            )
        )

    return items


def _serialize_warehouse_lookup(wh: Warehouse) -> dict:
    """Serialize a Warehouse + TruthCore into the lookup response format."""
    tc_dict = None
    if wh.truth_core:
        tc = wh.truth_core
        tc_dict = {
            "id": tc.id,
            "activation_status": tc.activation_status,
            "supplier_rate_per_sqft": tc.supplier_rate_per_sqft,
            "min_sqft": tc.min_sqft,
            "max_sqft": tc.max_sqft,
            "activity_tier": tc.activity_tier,
            "available_from": tc.available_from.isoformat() if tc.available_from else None,
            "available_to": tc.available_to.isoformat() if tc.available_to else None,
            "dock_doors_receiving": tc.dock_doors_receiving,
            "dock_doors_shipping": tc.dock_doors_shipping,
            "drive_in_bays": tc.drive_in_bays,
            "parking_spaces": tc.parking_spaces,
            "clear_height_ft": tc.clear_height_ft,
            "has_office_space": tc.has_office_space,
            "has_sprinkler": tc.has_sprinkler,
            "power_supply": tc.power_supply,
        }

    return {
        "id": wh.id,
        "owner_name": wh.owner_name,
        "owner_email": wh.owner_email,
        "address": wh.address,
        "city": wh.city,
        "state": wh.state,
        "zip": wh.zip,
        "building_size_sqft": wh.building_size_sqft,
        "lot_size_acres": wh.lot_size_acres,
        "year_built": wh.year_built,
        "construction_type": wh.construction_type,
        "zoning": wh.zoning,
        "primary_image_url": wh.primary_image_url,
        "image_urls": wh.image_urls or [],
        "property_type": wh.property_type,
        "truth_core": tc_dict,
    }


@router.get("/warehouse/lookup")
async def lookup_warehouse_by_address(
    address: str = Query(..., description="Address search string"),
    session_id: str = Query("", description="Frontend session ID for property profile"),
    is_test: bool = Query(False, description="Mark as test data"),
    db: AsyncSession = Depends(get_db),
):
    """Search warehouses by address substring (case-insensitive).

    Used by the activation flow when a supplier types their building address.
    Returns matching warehouses with their building data (truth core, features).

    Falls back to geocoding + Gemini search if no DB match is found.
    """
    # --- Step 1: Existing DB search (unchanged) ---
    result = await db.execute(
        select(Warehouse)
        .where(func.lower(Warehouse.address).contains(func.lower(address)))
        .options(
            selectinload(Warehouse.truth_core),
            selectinload(Warehouse.memories),
        )
    )
    warehouses = result.scalars().all()

    if warehouses:
        return [_serialize_warehouse_lookup(wh) for wh in warehouses]

    # --- Step 2: No DB match — try geocoding + Gemini search ---
    logger.info("[Lookup] No DB match for '%s', starting geocode + Gemini pipeline...", address)
    from wex_platform.services.geocoding_service import normalize_address

    geocoding = await normalize_address(address)
    logger.info("[Lookup] Geocoding: valid=%s, address='%s'", geocoding.is_valid, geocoding.formatted_address)

    # Use normalized address when geocoding succeeds, raw address otherwise
    search_address = geocoding.formatted_address if geocoding.is_valid else address

    if geocoding.is_valid:
        # Re-check DB with normalized address (catches typos)
        result = await db.execute(
            select(Warehouse)
            .where(func.lower(Warehouse.address).contains(func.lower(geocoding.formatted_address)))
            .options(
                selectinload(Warehouse.truth_core),
                selectinload(Warehouse.memories),
            )
        )
        warehouses = result.scalars().all()

        if warehouses:
            return [_serialize_warehouse_lookup(wh) for wh in warehouses]

    # --- Guardrail: negative cache check ---
    normalized = search_address.lower()
    cached = _NOT_FOUND_CACHE.get(normalized)
    if _is_cache_valid(cached):
        # Return the cached rejection reason so frontend shows the right page
        if cached.get("not_commercial"):
            return [{"not_commercial": True, "address": search_address}]
        return []

    # --- Guardrail: rate limiting ---
    now_ts = time.time()
    client_key = "global"  # Simple global rate limit
    _search_timestamps[client_key] = [
        ts for ts in _search_timestamps[client_key] if now_ts - ts < 60
    ]
    if len(_search_timestamps[client_key]) >= _SEARCH_RATE_LIMIT:
        logger.warning("Gemini search rate limit exceeded")
        return []
    _search_timestamps[client_key].append(now_ts)

    # --- Step 3: Gemini property search + NNN rate lookup (PARALLEL) ---
    import asyncio as _aio
    from wex_platform.agents.property_search_agent import PropertySearchAgent
    from wex_platform.agents.market_rate_agent import MarketRateAgent

    property_agent = PropertySearchAgent()
    rate_agent = MarketRateAgent()

    # Fire both in parallel — property search is ~20s, NNN lookup ~10s
    # This saves ~10s vs running them sequentially
    async def _property_search():
        return await property_agent.search_property(
            search_address,
            geocoded_city=geocoding.city,
            geocoded_state=geocoding.state,
            geocoded_zip=geocoding.zip_code,
        )

    async def _nnn_rate_lookup():
        """Best-effort NNN rate lookup — failures are fine (frontend has fallback)."""
        try:
            zip_code = geocoding.zip_code
            if not zip_code:
                return None
            result = await rate_agent.get_nnn_rates(zip_code)
            if result.ok and result.data:
                return {
                    "nnn_low": result.data["nnn_low"],
                    "nnn_high": result.data["nnn_high"],
                    "rate_location": f"{geocoding.city}, {geocoding.state}" if geocoding.city else f"zip {zip_code}",
                }
            # Try nearby cached rates
            nearby = await rate_agent.get_nearby_cached_rate(zip_code)
            if nearby:
                return {
                    "nnn_low": nearby["nnn_low"],
                    "nnn_high": nearby["nnn_high"],
                    "rate_location": f"near {geocoding.city}, {geocoding.state}" if geocoding.city else f"near zip {zip_code}",
                }
            return None
        except Exception as exc:
            logger.warning("[Lookup] NNN rate lookup failed (non-blocking): %s", exc)
            return None

    search_result, nnn_rates = await _aio.gather(
        _property_search(), _nnn_rate_lookup()
    )
    logger.info("[Lookup] Parallel complete: search_ok=%s, rates=%s", search_result.ok, "found" if nnn_rates else "none")

    if not search_result.ok:
        # Don't cache timeouts/errors — only cache genuine "not found" results.
        # This allows retries after transient Gemini failures.
        logger.warning("[Lookup] Search failed for '%s': %s", search_address, search_result.error)
        return []

    result_data = search_result.data
    property_data = result_data["property_data"]
    meta = result_data.get("meta", {})
    result_class = meta.get("result_class", "not_verified")
    evidence_bundle = meta.get("evidence_bundle")
    fields_by_source = meta.get("fields_by_source", {})

    # HARD GATE: only persist verified_persisted results
    if result_class == "not_verified":
        is_commercial = property_data.get("is_commercial_industrial", False)
        logger.warning("Not verified for '%s': commercial=%s, match=%s", search_address, is_commercial, meta.get("address_match"))
        if not is_commercial:
            # Cache with reason so subsequent requests also show rejection page
            _NOT_FOUND_CACHE[normalized] = {"ts": time.time(), "ttl": 3600, "not_commercial": True}
            return [{"not_commercial": True, "address": search_address}]
        _NOT_FOUND_CACHE[normalized] = {"ts": time.time(), "ttl": 300}  # 5 minutes
        return []

    if result_class == "verified_not_persisted":
        logger.info("Verified but low trust for '%s', not persisting", search_address)
        _NOT_FOUND_CACHE[normalized] = {"ts": time.time(), "ttl": 600}  # 10 minutes
        # Return preview data so frontend can show "Confirm address"
        return [{
            "_preview": True,
            "result_class": "verified_not_persisted",
            "address": (property_data.get("city") or "") + ", " + (property_data.get("state") or ""),
            "building_size_sqft": property_data.get("building_size_sqft"),
            "year_built": property_data.get("year_built"),
            "confidence": property_data.get("confidence"),
            "match_quality": meta.get("address_match", {}).get("match_quality"),
            "mismatch_details": meta.get("address_match", {}).get("mismatch_details"),
        }]

    # Only verified_persisted reaches here — safe to write to DB
    from wex_platform.services.property_service import create_warehouse_from_search

    warehouse, truth_core, memories = await create_warehouse_from_search(
        db, property_data, geocoding, raw_address=address,
        evidence_bundle=evidence_bundle,
        fields_by_source=fields_by_source,
    )

    # Commit warehouse + truth_core + memories to DB
    await db.commit()

    # Trigger 1: Create property profile from Gemini search (background)
    if session_id:
        from wex_platform.services.profile_service import create_profile_from_search
        import asyncio
        asyncio.ensure_future(create_profile_from_search(
            session_id=session_id, warehouse_id=warehouse.id,
            property_data=property_data,
            city=warehouse.city or "", state=warehouse.state or "",
            zip_code=warehouse.zip or "", address=warehouse.address or address,
            is_test=is_test,
        ))

    # Serialize in the same format as existing results
    tc_dict = None
    if truth_core:
        tc_dict = {
            "id": truth_core.id,
            "activation_status": truth_core.activation_status,
            "supplier_rate_per_sqft": truth_core.supplier_rate_per_sqft,
            "min_sqft": truth_core.min_sqft,
            "max_sqft": truth_core.max_sqft,
            "activity_tier": truth_core.activity_tier,
            "available_from": None,
            "available_to": None,
            "dock_doors_receiving": truth_core.dock_doors_receiving,
            "dock_doors_shipping": truth_core.dock_doors_shipping,
            "drive_in_bays": truth_core.drive_in_bays,
            "parking_spaces": truth_core.parking_spaces,
            "clear_height_ft": truth_core.clear_height_ft,
            "has_office_space": truth_core.has_office_space,
            "has_sprinkler": truth_core.has_sprinkler,
            "power_supply": truth_core.power_supply,
        }

    return [{
        "id": warehouse.id,
        "owner_name": warehouse.owner_name,
        "owner_email": warehouse.owner_email,
        "address": warehouse.address,
        "city": warehouse.city,
        "state": warehouse.state,
        "zip": warehouse.zip,
        "building_size_sqft": warehouse.building_size_sqft,
        "lot_size_acres": warehouse.lot_size_acres,
        "year_built": warehouse.year_built,
        "construction_type": warehouse.construction_type,
        "zoning": warehouse.zoning,
        "property_type": warehouse.property_type,
        "primary_image_url": warehouse.primary_image_url,
        "image_urls": warehouse.image_urls or [],
        "source_urls": property_data.get("source_urls", []),
        "truth_core": tc_dict,
        "nnn_rates": nnn_rates,  # Pre-fetched in parallel (may be None)
    }]


@router.get("/warehouse/{warehouse_id}", response_model=WarehouseDetailResponse)
async def get_warehouse(
    warehouse_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return full warehouse detail with truth core, memories, and supplier agreements.

    ISOLATION: No buyer rates, buyer info, or WEx spread are returned.
    """
    result = await db.execute(
        select(Warehouse)
        .where(Warehouse.id == warehouse_id)
        .options(
            selectinload(Warehouse.truth_core),
            selectinload(Warehouse.memories),
            selectinload(Warehouse.supplier_agreements),
            selectinload(Warehouse.supplier_ledger_entries),
        )
    )
    warehouse = result.scalar_one_or_none()

    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    # Build truth core dict (supplier-safe fields only)
    tc_dict = None
    if warehouse.truth_core:
        tc = warehouse.truth_core
        tc_dict = {
            "id": tc.id,
            "warehouse_id": tc.warehouse_id,
            "available_from": tc.available_from.isoformat() if tc.available_from else None,
            "available_to": tc.available_to.isoformat() if tc.available_to else None,
            "min_term_months": tc.min_term_months,
            "max_term_months": tc.max_term_months,
            "min_sqft": tc.min_sqft,
            "max_sqft": tc.max_sqft,
            "activity_tier": tc.activity_tier,
            "constraints": tc.constraints,
            "supplier_rate_per_sqft": tc.supplier_rate_per_sqft,
            "supplier_rate_max": tc.supplier_rate_max,
            "activation_status": tc.activation_status,
            "toggled_at": tc.toggled_at.isoformat() if tc.toggled_at else None,
            "tour_readiness": tc.tour_readiness,
            "dock_doors_receiving": tc.dock_doors_receiving,
            "dock_doors_shipping": tc.dock_doors_shipping,
            "drive_in_bays": tc.drive_in_bays,
            "parking_spaces": tc.parking_spaces,
            "clear_height_ft": tc.clear_height_ft,
            "has_office_space": tc.has_office_space,
            "has_sprinkler": tc.has_sprinkler,
            "power_supply": tc.power_supply,
            "trust_level": tc.trust_level,
            "created_at": tc.created_at.isoformat() if tc.created_at else None,
            "updated_at": tc.updated_at.isoformat() if tc.updated_at else None,
        }

    # Build memories list
    memories_list = []
    for m in (warehouse.memories or []):
        memories_list.append({
            "id": m.id,
            "memory_type": m.memory_type,
            "content": m.content,
            "source": m.source,
            "confidence": m.confidence,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })

    # Build supplier agreements list
    agreements_list = []
    for a in (warehouse.supplier_agreements or []):
        agreements_list.append({
            "id": a.id,
            "status": a.status,
            "terms_json": a.terms_json,
            "signed_at": a.signed_at.isoformat() if a.signed_at else None,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        })

    # Build supplier ledger list
    ledger_list = []
    for le in (warehouse.supplier_ledger_entries or []):
        ledger_list.append({
            "id": le.id,
            "deal_id": le.deal_id,
            "entry_type": le.entry_type,
            "amount": le.amount,
            "description": le.description,
            "period_start": le.period_start.isoformat() if le.period_start else None,
            "period_end": le.period_end.isoformat() if le.period_end else None,
            "status": le.status,
            "created_at": le.created_at.isoformat() if le.created_at else None,
        })

    return WarehouseDetailResponse(
        id=warehouse.id,
        owner_name=warehouse.owner_name,
        owner_email=warehouse.owner_email,
        owner_phone=warehouse.owner_phone,
        address=warehouse.address,
        city=warehouse.city,
        state=warehouse.state,
        zip=warehouse.zip,
        lat=warehouse.lat,
        lng=warehouse.lng,
        building_size_sqft=warehouse.building_size_sqft,
        lot_size_acres=warehouse.lot_size_acres,
        year_built=warehouse.year_built,
        construction_type=warehouse.construction_type,
        zoning=warehouse.zoning,
        primary_image_url=warehouse.primary_image_url,
        image_urls=warehouse.image_urls or [],
        source_url=warehouse.source_url,
        created_at=warehouse.created_at,
        updated_at=warehouse.updated_at,
        truth_core=tc_dict,
        memories=memories_list,
        supplier_agreements=agreements_list,
        supplier_ledger=ledger_list,
    )


@router.post("/warehouse/{warehouse_id}/activate", response_model=TruthCoreResponse)
async def activate_warehouse(
    warehouse_id: str,
    body: TruthCoreCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create or update a TruthCore to activate a warehouse listing.

    Creates a ToggleHistory record and a SupplierAgreement.
    """
    # Verify warehouse exists
    wh_result = await db.execute(
        select(Warehouse).where(Warehouse.id == warehouse_id)
    )
    warehouse = wh_result.scalar_one_or_none()
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    # Mark warehouse as in-network so clearing engine includes it in Tier 1
    if warehouse.supplier_status != "in_network":
        warehouse.supplier_status = "in_network"

    now = datetime.now(timezone.utc)

    # Check for existing truth core
    tc_result = await db.execute(
        select(TruthCore).where(TruthCore.warehouse_id == warehouse_id)
    )
    existing_tc = tc_result.scalar_one_or_none()

    if existing_tc:
        # Update existing truth core
        existing_tc.min_sqft = body.min_sqft
        existing_tc.max_sqft = body.max_sqft
        existing_tc.activity_tier = body.activity_tier
        existing_tc.constraints = body.constraints
        existing_tc.supplier_rate_per_sqft = body.supplier_rate_per_sqft
        existing_tc.buyer_rate_per_sqft = calculate_default_buyer_rate(body.supplier_rate_per_sqft)
        existing_tc.supplier_rate_max = body.supplier_rate_max
        existing_tc.available_from = body.available_from
        existing_tc.available_to = body.available_to
        existing_tc.min_term_months = body.min_term_months
        existing_tc.max_term_months = body.max_term_months
        existing_tc.tour_readiness = body.tour_readiness
        existing_tc.dock_doors_receiving = body.dock_doors_receiving
        existing_tc.dock_doors_shipping = body.dock_doors_shipping
        existing_tc.drive_in_bays = body.drive_in_bays
        existing_tc.parking_spaces = body.parking_spaces
        existing_tc.clear_height_ft = body.clear_height_ft
        existing_tc.has_office_space = body.has_office_space
        existing_tc.has_sprinkler = body.has_sprinkler
        existing_tc.power_supply = body.power_supply
        existing_tc.trust_level = body.trust_level
        existing_tc.activation_status = "on"
        existing_tc.toggled_at = now
        truth_core = existing_tc
    else:
        # Create new truth core
        truth_core = TruthCore(
            id=str(uuid.uuid4()),
            warehouse_id=warehouse_id,
            min_sqft=body.min_sqft,
            max_sqft=body.max_sqft,
            activity_tier=body.activity_tier,
            constraints=body.constraints,
            supplier_rate_per_sqft=body.supplier_rate_per_sqft,
            buyer_rate_per_sqft=calculate_default_buyer_rate(body.supplier_rate_per_sqft),
            supplier_rate_max=body.supplier_rate_max,
            available_from=body.available_from,
            available_to=body.available_to,
            min_term_months=body.min_term_months,
            max_term_months=body.max_term_months,
            tour_readiness=body.tour_readiness,
            dock_doors_receiving=body.dock_doors_receiving,
            dock_doors_shipping=body.dock_doors_shipping,
            drive_in_bays=body.drive_in_bays,
            parking_spaces=body.parking_spaces,
            clear_height_ft=body.clear_height_ft,
            has_office_space=body.has_office_space,
            has_sprinkler=body.has_sprinkler,
            power_supply=body.power_supply,
            trust_level=body.trust_level,
            activation_status="on",
            toggled_at=now,
        )
        db.add(truth_core)

    # Flush to get the truth_core.id if newly created
    await db.flush()

    # Create toggle history record
    toggle = ToggleHistory(
        id=str(uuid.uuid4()),
        warehouse_id=warehouse_id,
        previous_status="off",
        new_status="on",
        reason="Warehouse activated via API",
    )
    db.add(toggle)

    # Create supplier agreement
    agreement = SupplierAgreement(
        id=str(uuid.uuid4()),
        warehouse_id=warehouse_id,
        truth_core_id=truth_core.id,
        status="active",
        terms_json={
            "min_sqft": body.min_sqft,
            "max_sqft": body.max_sqft,
            "activity_tier": body.activity_tier,
            "supplier_rate_per_sqft": body.supplier_rate_per_sqft,
            "constraints": body.constraints,
        },
        signed_at=now,
    )
    db.add(agreement)

    await db.commit()

    # --- Sync Warehouse images → PropertyProfile (background) ---
    import asyncio
    from wex_platform.infra.database import async_session as _async_session

    async def _sync_profile():
        try:
            async with _async_session() as bg_db:
                pp_result = await bg_db.execute(
                    select(PropertyProfile).where(PropertyProfile.warehouse_id == warehouse_id)
                )
                profile = pp_result.scalar_one_or_none()

                if profile:
                    profile.primary_image_url = warehouse.primary_image_url
                    profile.image_urls = warehouse.image_urls or []
                    profile.updated_at = now
                else:
                    profile = PropertyProfile(
                        id=str(uuid.uuid4()),
                        session_id=f"activation-{warehouse_id}",
                        warehouse_id=warehouse_id,
                        address=warehouse.address,
                        city=warehouse.city,
                        state=warehouse.state,
                        zip=warehouse.zip,
                        building_size_sqft=warehouse.building_size_sqft,
                        lot_size_acres=warehouse.lot_size_acres,
                        year_built=warehouse.year_built,
                        construction_type=warehouse.construction_type,
                        zoning=warehouse.zoning,
                        primary_image_url=warehouse.primary_image_url,
                        image_urls=warehouse.image_urls or [],
                    )
                    bg_db.add(profile)
                await bg_db.commit()
        except Exception as exc:
            logger.warning("PropertyProfile image sync failed for %s: %s", warehouse_id, exc)

    asyncio.ensure_future(_sync_profile())

    # Generate AI description (background — never blocks activation)
    async def _generate_description():
        try:
            from wex_platform.services.description_service import generate_warehouse_description
            async with _async_session() as bg_db:
                await generate_warehouse_description(bg_db, warehouse_id)
                await bg_db.commit()
        except Exception as exc:
            logger.warning("Description generation failed for %s: %s", warehouse_id, exc)

    asyncio.ensure_future(_generate_description())

    return truth_core


@router.patch("/warehouse/{warehouse_id}/toggle")
async def toggle_activation(
    warehouse_id: str,
    body: ToggleRequest,
    db: AsyncSession = Depends(get_db),
):
    """Toggle warehouse activation status between 'on' and 'off'.

    Creates a ToggleHistory audit record. If toggling OFF, sets a 48-hour
    grace period.
    """
    if body.status not in ("on", "off"):
        raise HTTPException(status_code=400, detail="Status must be 'on' or 'off'")

    tc_result = await db.execute(
        select(TruthCore).where(TruthCore.warehouse_id == warehouse_id)
    )
    truth_core = tc_result.scalar_one_or_none()

    if not truth_core:
        raise HTTPException(
            status_code=404,
            detail="Truth core not found. Activate the warehouse first.",
        )

    previous_status = truth_core.activation_status
    now = datetime.now(timezone.utc)

    # Count in-flight matches for this warehouse
    match_count_result = await db.execute(
        select(func.count())
        .select_from(Deal)
        .where(
            Deal.warehouse_id == warehouse_id,
            Deal.status.in_(["terms_presented", "terms_accepted", "tour_scheduled"]),
        )
    )
    in_flight_count = match_count_result.scalar() or 0

    # Set grace period if toggling off
    grace_until = None
    if body.status == "off":
        grace_until = now + timedelta(hours=48)
        truth_core.toggle_reason = body.reason

    # Update truth core
    truth_core.activation_status = body.status
    truth_core.toggled_at = now

    # Create toggle history
    toggle = ToggleHistory(
        id=str(uuid.uuid4()),
        warehouse_id=warehouse_id,
        previous_status=previous_status,
        new_status=body.status,
        reason=body.reason,
        in_flight_matches=in_flight_count,
        grace_period_until=grace_until,
    )
    db.add(toggle)

    return {
        "warehouse_id": warehouse_id,
        "previous_status": previous_status,
        "new_status": body.status,
        "toggled_at": now.isoformat(),
        "in_flight_matches": in_flight_count,
        "grace_period_until": grace_until.isoformat() if grace_until else None,
        "truth_core": {
            "id": truth_core.id,
            "activation_status": truth_core.activation_status,
            "supplier_rate_per_sqft": truth_core.supplier_rate_per_sqft,
        },
    }


@router.patch("/warehouse/{warehouse_id}/truth-core")
async def update_truth_core(
    warehouse_id: str,
    updates: dict,
    db: AsyncSession = Depends(get_db),
):
    """Update specific truth core fields with audit trail.

    Creates TruthCoreChange records for each changed field.
    """
    tc_result = await db.execute(
        select(TruthCore).where(TruthCore.warehouse_id == warehouse_id)
    )
    truth_core = tc_result.scalar_one_or_none()

    if not truth_core:
        raise HTTPException(
            status_code=404,
            detail="Truth core not found. Activate the warehouse first.",
        )

    toggle_is_on = truth_core.activation_status == "on"

    # Fields that are allowed to be updated on the truth core
    updatable_fields = {
        "min_sqft", "max_sqft", "activity_tier", "constraints",
        "supplier_rate_per_sqft", "supplier_rate_max",
        "available_from", "available_to",
        "min_term_months", "max_term_months",
        "tour_readiness", "dock_doors_receiving", "dock_doors_shipping",
        "drive_in_bays", "parking_spaces", "clear_height_ft",
        "has_office_space", "has_sprinkler", "power_supply",
    }

    changes_made = []

    for field_name, new_value in updates.items():
        if field_name not in updatable_fields:
            continue

        if not hasattr(truth_core, field_name):
            continue

        old_value = getattr(truth_core, field_name)

        # Skip if value hasn't actually changed
        if old_value == new_value:
            continue

        # Apply the update
        setattr(truth_core, field_name, new_value)

        # Auto-recalculate buyer rate when supplier rate changes
        if field_name == "supplier_rate_per_sqft":
            truth_core.buyer_rate_per_sqft = calculate_default_buyer_rate(new_value)

        # Create audit record
        change = TruthCoreChange(
            id=str(uuid.uuid4()),
            truth_core_id=truth_core.id,
            warehouse_id=warehouse_id,
            field_changed=field_name,
            old_value=json.dumps(old_value) if old_value is not None else None,
            new_value=json.dumps(new_value) if new_value is not None else None,
            changed_by="supplier_api",
            change_reason=updates.get("change_reason"),
            toggle_was_on=toggle_is_on,
        )
        db.add(change)
        changes_made.append({
            "field": field_name,
            "old_value": old_value,
            "new_value": new_value,
        })

    return {
        "warehouse_id": warehouse_id,
        "changes": changes_made,
        "toggle_was_on": toggle_is_on,
        "truth_core": {
            "id": truth_core.id,
            "activation_status": truth_core.activation_status,
            "supplier_rate_per_sqft": truth_core.supplier_rate_per_sqft,
            "min_sqft": truth_core.min_sqft,
            "max_sqft": truth_core.max_sqft,
            "activity_tier": truth_core.activity_tier,
        },
    }


@router.get("/warehouse/{warehouse_id}/revenue", response_model=RevenueResponse)
async def get_revenue(
    warehouse_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return revenue summary for a warehouse.

    Calculates from supplier_ledger entries and active deals.
    ISOLATION: Only supplier-side amounts are returned.
    """
    # Verify warehouse exists
    wh_result = await db.execute(
        select(Warehouse).where(Warehouse.id == warehouse_id)
    )
    if not wh_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Warehouse not found")

    # Total earned from ledger
    total_result = await db.execute(
        select(func.coalesce(func.sum(SupplierLedger.amount), 0.0))
        .where(
            SupplierLedger.warehouse_id == warehouse_id,
            SupplierLedger.status == "paid",
        )
    )
    total_earned = float(total_result.scalar() or 0.0)

    # Monthly income: sum of supplier_rate * sqft_allocated for active deals
    active_deals_result = await db.execute(
        select(Deal).where(
            Deal.warehouse_id == warehouse_id,
            Deal.status.in_(["active", "confirmed"]),
        )
    )
    active_deals = active_deals_result.scalars().all()

    monthly_income = 0.0
    active_placements = len(active_deals)
    for deal in active_deals:
        monthly_income += deal.supplier_rate * deal.sqft_allocated

    projected_annual = monthly_income * 12

    return RevenueResponse(
        monthly_income=round(monthly_income, 2),
        total_earned=round(total_earned, 2),
        projected_annual=round(projected_annual, 2),
        active_placements=active_placements,
    )


@router.post("/activate/chat")
async def activation_chat(
    body: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Handle a message in the activation chat flow.

    At step 5, also calls PricingAgent for rate guidance.
    """
    from wex_platform.agents.activation_agent import ActivationAgent

    # Load warehouse building data
    wh_result = await db.execute(
        select(Warehouse)
        .where(Warehouse.id == body.warehouse_id)
        .options(selectinload(Warehouse.memories))
    )
    warehouse = wh_result.scalar_one_or_none()

    building_data = None
    if warehouse:
        building_data = {
            "address": warehouse.address,
            "city": warehouse.city,
            "state": warehouse.state,
            "building_size_sqft": warehouse.building_size_sqft,
            "year_built": warehouse.year_built,
            "construction_type": warehouse.construction_type,
            "memories": [m.content for m in (warehouse.memories or [])],
        }

    agent = ActivationAgent()

    # Get pricing guidance at step 5
    pricing_data = None
    if body.current_step >= 4 and "supplier_rate_per_sqft" not in body.extracted_fields:
        try:
            from wex_platform.agents.pricing_agent import PricingAgent

            pricing_agent = PricingAgent()
            pricing_result = await pricing_agent.get_rate_guidance(
                warehouse_data={**(building_data or {}), **body.extracted_fields},
                contextual_memories=building_data.get("memories", []) if building_data else [],
            )
            if pricing_result.ok:
                pricing_data = pricing_result.data
        except Exception as e:
            logger.warning("Pricing guidance unavailable: %s", e)

    result = await agent.process_message(
        warehouse_id=body.warehouse_id,
        user_message=body.message,
        conversation_history=body.conversation_history,
        building_data=building_data,
        current_step=body.current_step,
        extracted_fields=body.extracted_fields,
    )

    if not result.ok:
        raise HTTPException(status_code=500, detail=result.error or "Agent processing failed")

    agent_data = result.data if isinstance(result.data, dict) else {}
    return {
        "message": agent_data.get("message", ""),
        "detail_step": agent_data.get("current_step") or agent_data.get("detail_step") or body.current_step,
        "extracted_fields": agent_data.get("extracted_fields", {}),
        "step_complete": agent_data.get("step_complete", False),
        "all_complete": agent_data.get("all_steps_complete", False),
        "pricing_guidance": pricing_data,
    }


@router.post("/activate/start")
async def activation_start(
    body: ActivationStartRequest,
    db: AsyncSession = Depends(get_db),
):
    """Start a new activation conversation.

    Loads warehouse + building data from DB and returns the initial
    AI agent message.
    """
    from wex_platform.agents.activation_agent import ActivationAgent

    # Load warehouse data
    result = await db.execute(
        select(Warehouse)
        .where(Warehouse.id == body.warehouse_id)
        .options(
            selectinload(Warehouse.truth_core),
            selectinload(Warehouse.memories),
        )
    )
    warehouse = result.scalar_one_or_none()

    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    building_data = {
        "address": warehouse.address,
        "city": warehouse.city,
        "state": warehouse.state,
        "zip": warehouse.zip,
        "building_size_sqft": warehouse.building_size_sqft,
        "lot_size_acres": warehouse.lot_size_acres,
        "year_built": warehouse.year_built,
        "construction_type": warehouse.construction_type,
        "zoning": warehouse.zoning,
    }

    # Enrich with truth core data if it already exists
    if warehouse.truth_core:
        tc = warehouse.truth_core
        building_data.update({
            "dock_doors_receiving": tc.dock_doors_receiving,
            "dock_doors_shipping": tc.dock_doors_shipping,
            "drive_in_bays": tc.drive_in_bays,
            "parking_spaces": tc.parking_spaces,
            "clear_height_ft": tc.clear_height_ft,
            "has_office_space": tc.has_office_space,
            "has_sprinkler": tc.has_sprinkler,
            "power_supply": tc.power_supply,
        })

    # Include contextual memories
    building_data["memories"] = [m.content for m in (warehouse.memories or [])]

    agent = ActivationAgent()
    agent_result = await agent.generate_initial_message(building_data=building_data)

    if not agent_result.ok:
        raise HTTPException(
            status_code=500,
            detail=agent_result.error or "Failed to generate initial message",
        )

    # Parse the agent response
    try:
        initial_data = (
            json.loads(agent_result.data)
            if isinstance(agent_result.data, str)
            else agent_result.data
        )
    except (json.JSONDecodeError, TypeError):
        initial_data = {"message": agent_result.data, "current_step": 1}

    return {
        "initial_message": initial_data,
        "building_data": building_data,
        "warehouse_id": warehouse.id,
    }


@router.get("/warehouse/{warehouse_id}/agreements")
async def get_agreements(
    warehouse_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return supplier agreements for a warehouse."""
    # Verify warehouse exists
    wh_result = await db.execute(
        select(Warehouse).where(Warehouse.id == warehouse_id)
    )
    if not wh_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Warehouse not found")

    result = await db.execute(
        select(SupplierAgreement)
        .where(SupplierAgreement.warehouse_id == warehouse_id)
        .order_by(SupplierAgreement.created_at.desc())
    )
    agreements = result.scalars().all()

    return [
        {
            "id": a.id,
            "warehouse_id": a.warehouse_id,
            "truth_core_id": a.truth_core_id,
            "status": a.status,
            "terms_json": a.terms_json,
            "signed_at": a.signed_at.isoformat() if a.signed_at else None,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in agreements
    ]


@router.get("/warehouse/{warehouse_id}/ledger")
async def get_ledger(
    warehouse_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return supplier ledger entries for a warehouse."""
    # Verify warehouse exists
    wh_result = await db.execute(
        select(Warehouse).where(Warehouse.id == warehouse_id)
    )
    if not wh_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Warehouse not found")

    result = await db.execute(
        select(SupplierLedger)
        .where(SupplierLedger.warehouse_id == warehouse_id)
        .order_by(SupplierLedger.created_at.desc())
    )
    entries = result.scalars().all()

    return [
        {
            "id": e.id,
            "warehouse_id": e.warehouse_id,
            "deal_id": e.deal_id,
            "entry_type": e.entry_type,
            "amount": e.amount,
            "description": e.description,
            "period_start": e.period_start.isoformat() if e.period_start else None,
            "period_end": e.period_end.isoformat() if e.period_end else None,
            "status": e.status,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]


@router.post("/pageview")
async def track_pageview(
    body: PageViewRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Record a page view. Lightweight — no auth required."""
    from wex_platform.domain.models import PageView

    # Prefer X-Forwarded-For (set by Cloud Run / load balancers) over request.client
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)

    pv = PageView(
        path=body.path,
        referrer=body.referrer,
        utm_source=body.utm_source,
        utm_medium=body.utm_medium,
        utm_campaign=body.utm_campaign,
        session_id=body.session_id,
        user_agent=request.headers.get("user-agent", ""),
        ip=client_ip,
        is_test=body.is_test,
    )
    db.add(pv)
    await db.commit()
    return {"ok": True}


@router.post("/track")
async def track_event(
    body: TrackEventRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Track a smoke test funnel event. No auth required."""
    from wex_platform.domain.models import SmokeTestEvent
    props = body.properties or {}
    event = SmokeTestEvent(
        event=body.event,
        properties=props,
        session_id=body.session_id,
        email=props.get("email"),
        address=props.get("address"),
        city=props.get("city"),
        state=props.get("state"),
        zip=props.get("zip"),
        is_test=body.is_test,
    )
    db.add(event)
    await db.commit()

    # Send emails in a background task so the response returns immediately.
    # The frontend fires this as fire-and-forget, so if we await the SendGrid
    # calls inline, the client disconnects and the ASGI server cancels them.
    if body.event == "email_submitted":
        email_addr = props.get("email", "")
        email_data = {
            "address": props.get("address", ""),
            "sqft": props.get("sqft", 0),
            "rate": props.get("rateAsk", props.get("rate", 0)),
            "revenue": props.get("revenue", 0),
            "market_rate_low": props.get("market_rate_low"),
            "market_rate_high": props.get("market_rate_high"),
            "recommended_rate": props.get("recommended_rate"),
            "pricing_path": props.get("pricingPath", props.get("pricing_path", "")),
            "building_data": props.get("building_data"),
            "email": email_addr,
            "session_id": body.session_id,
            "is_test": body.is_test,
        }
        background_tasks.add_task(_send_track_emails, email_addr, email_data)

    # --- Property Profile triggers (background, own DB sessions) ---
    import asyncio
    from wex_platform.services.profile_service import update_profile_configurator, update_profile_email

    if body.is_test:
        props["is_test"] = True

    if body.event == "configurator_completed" and body.session_id:
        asyncio.ensure_future(update_profile_configurator(body.session_id, props))

    if body.event == "email_submitted" and body.session_id:
        asyncio.ensure_future(update_profile_email(body.session_id, props))

    return {"ok": True}


async def _send_track_emails(email_addr: str, email_data: dict):
    """Background task: send income report + internal alert via SendGrid."""
    from wex_platform.services.email_service import send_income_report, send_internal_alert
    try:
        if email_addr:
            await send_income_report(email_addr, email_data)
        await send_internal_alert(email_data)
    except Exception as exc:
        logger.warning("Email send failed for track event: %s", exc)


@router.post("/verify-lead")
async def verify_lead(body: LeadCaptureRequest, db: AsyncSession = Depends(get_db)):
    """Capture a verified lead from the email CTA form."""
    from wex_platform.domain.models import LeadCapture
    lead = LeadCapture(
        email=body.email,
        address=body.address,
        full_name=body.full_name,
        phone=body.phone,
        company=body.company,
        sqft=body.sqft,
        revenue=body.revenue,
        rate=body.rate,
        market_rate_low=body.market_rate_low,
        market_rate_high=body.market_rate_high,
        recommended_rate=body.recommended_rate,
        pricing_path=body.pricing_path,
        session_id=body.session_id,
        is_test=body.is_test,
    )
    db.add(lead)
    await db.commit()

    # Send internal alert for the hot lead
    try:
        from wex_platform.services.email_service import send_internal_alert
        alert_data = {
            "email": body.email,
            "address": body.address or "Unknown",
            "sqft": body.sqft or 0,
            "rate": body.rate or 0,
            "revenue": body.revenue or 0,
            "pricing_path": body.pricing_path or "",
            "full_name": body.full_name,
            "phone": body.phone,
            "company": body.company,
        }
        await send_internal_alert(alert_data)
    except Exception as exc:
        logger.warning("Internal alert failed for verified lead: %s", exc)

    return {"ok": True, "lead_id": lead.id}


# ---------------------------------------------------------------------------
# Onboarding (post-EarnCheck network join)
# ---------------------------------------------------------------------------


class OnboardRequest(BaseModel):
    """Request body for supplier network onboarding."""

    warehouse_id: str
    agreement_accepted: bool


@router.post("/onboard")
async def onboard_supplier(
    body: OnboardRequest,
    db: AsyncSession = Depends(get_db),
):
    """Onboard a supplier into the WEx network.

    Validates the warehouse exists, creates a SupplierAgreement record,
    and sets supplier_status to 'in_network' with an onboarded_at timestamp.
    """
    if not body.agreement_accepted:
        raise HTTPException(
            status_code=400,
            detail="You must accept the network agreement to onboard.",
        )

    # Load warehouse with truth core
    result = await db.execute(
        select(Warehouse)
        .where(Warehouse.id == body.warehouse_id)
        .options(selectinload(Warehouse.truth_core))
    )
    warehouse = result.scalar_one_or_none()

    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")

    now = datetime.now(timezone.utc)

    # Update supplier status
    warehouse.supplier_status = "in_network"
    warehouse.onboarded_at = now

    # Ensure truth core exists for the agreement reference
    truth_core = warehouse.truth_core
    if not truth_core:
        raise HTTPException(
            status_code=400,
            detail="Warehouse must complete EarnCheck (have a truth core) before onboarding.",
        )

    # Activate the truth core if it isn't already
    if truth_core.activation_status != "on":
        truth_core.activation_status = "on"
        truth_core.toggled_at = now

    # Create supplier agreement
    agreement = SupplierAgreement(
        id=str(uuid.uuid4()),
        warehouse_id=warehouse.id,
        truth_core_id=truth_core.id,
        status="active",
        terms_json={
            "type": "network_onboarding",
            "agreement_accepted": True,
            "min_sqft": truth_core.min_sqft,
            "max_sqft": truth_core.max_sqft,
            "activity_tier": truth_core.activity_tier,
            "supplier_rate_per_sqft": truth_core.supplier_rate_per_sqft,
        },
        signed_at=now,
    )
    db.add(agreement)

    # Create toggle history record
    toggle = ToggleHistory(
        id=str(uuid.uuid4()),
        warehouse_id=warehouse.id,
        previous_status="off",
        new_status="on",
        reason="Supplier onboarded to WEx network",
    )
    db.add(toggle)

    await db.flush()

    return {
        "ok": True,
        "warehouse_id": warehouse.id,
        "supplier_status": warehouse.supplier_status,
        "onboarded_at": warehouse.onboarded_at.isoformat(),
        "agreement_id": agreement.id,
        "truth_core": {
            "id": truth_core.id,
            "activation_status": truth_core.activation_status,
            "supplier_rate_per_sqft": truth_core.supplier_rate_per_sqft,
        },
    }


# ---------------------------------------------------------------------------
# Tour Management (supplier side)
# ---------------------------------------------------------------------------


class TourConfirmRequest(BaseModel):
    """Request body for supplier confirming or rescheduling a tour."""

    confirmed: bool
    proposed_date: Optional[str] = None  # alternative if not confirmed
    proposed_time: Optional[str] = None


@router.post("/deal/{deal_id}/tour/confirm")
async def confirm_tour(
    deal_id: str,
    body: TourConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    """Supplier confirms or proposes alternative time for a tour.

    12-hour deadline for confirmation. If not confirmed, supplier can
    propose an alternative date/time for the buyer to accept.
    """
    result = await db.execute(
        select(Deal)
        .where(Deal.id == deal_id)
        .options(selectinload(Deal.warehouse))
    )
    deal = result.scalar_one_or_none()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.tour_status != "requested":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot confirm tour with tour_status '{deal.tour_status}'",
        )

    now = datetime.now(timezone.utc)

    if body.confirmed:
        deal.tour_status = "confirmed"
        deal.supplier_confirmed_at = now
        deal.status = "tour_confirmed"

        event = DealEvent(
            id=str(uuid.uuid4()),
            deal_id=deal.id,
            event_type="tour_confirmed",
            details={
                "confirmed_at": now.isoformat(),
                "tour_date": deal.tour_preferred_date,
                "tour_time": deal.tour_preferred_time,
            },
        )
        db.add(event)

        return {
            "deal_id": deal.id,
            "tour_status": "confirmed",
            "confirmed_at": now.isoformat(),
            "tour_date": deal.tour_preferred_date,
            "tour_time": deal.tour_preferred_time,
        }
    else:
        # Supplier proposes alternative
        if not body.proposed_date or not body.proposed_time:
            raise HTTPException(
                status_code=400,
                detail="Must provide proposed_date and proposed_time when not confirming.",
            )

        deal.tour_status = "rescheduled"
        deal.supplier_proposed_date = body.proposed_date
        deal.supplier_proposed_time = body.proposed_time
        deal.status = "tour_rescheduled"

        event = DealEvent(
            id=str(uuid.uuid4()),
            deal_id=deal.id,
            event_type="tour_rescheduled",
            details={
                "original_date": deal.tour_preferred_date,
                "original_time": deal.tour_preferred_time,
                "proposed_date": body.proposed_date,
                "proposed_time": body.proposed_time,
            },
        )
        db.add(event)

        return {
            "deal_id": deal.id,
            "tour_status": "rescheduled",
            "proposed_date": body.proposed_date,
            "proposed_time": body.proposed_time,
            "message": "Alternative time proposed. Waiting for buyer confirmation.",
        }


@router.get("/tours")
async def get_upcoming_tours(
    owner_email: Optional[str] = Query(None, description="Filter by supplier email"),
    db: AsyncSession = Depends(get_db),
):
    """List upcoming tours for a supplier's warehouses.

    Returns deals with tour_status in ('requested', 'confirmed', 'rescheduled')
    for warehouses owned by the given email.
    """
    query = (
        select(Deal)
        .where(Deal.tour_status.in_(["requested", "confirmed", "rescheduled"]))
        .options(selectinload(Deal.warehouse))
        .order_by(Deal.tour_scheduled_at.asc())
    )

    if owner_email:
        query = query.join(Warehouse).where(
            func.lower(Warehouse.owner_email) == func.lower(owner_email)
        )

    result = await db.execute(query)
    deals = result.scalars().all()

    tours = []
    for deal in deals:
        tours.append({
            "deal_id": deal.id,
            "warehouse_id": deal.warehouse_id,
            "warehouse_address": deal.warehouse.address if deal.warehouse else None,
            "tour_status": deal.tour_status,
            "tour_date": deal.tour_preferred_date,
            "tour_time": deal.tour_preferred_time,
            "tour_notes": deal.tour_notes,
            "buyer_id": deal.buyer_id,
            "sqft_allocated": deal.sqft_allocated,
            "supplier_rate": deal.supplier_rate,
            "tour_scheduled_at": deal.tour_scheduled_at.isoformat() if deal.tour_scheduled_at else None,
            "supplier_confirmed_at": deal.supplier_confirmed_at.isoformat() if deal.supplier_confirmed_at else None,
            "proposed_date": deal.supplier_proposed_date,
            "proposed_time": deal.supplier_proposed_time,
        })

    return {"tours": tours, "count": len(tours)}

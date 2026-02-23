"""Service to persist Gemini property search results into the database."""
import json
import logging
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.models import Warehouse, TruthCore, ContextualMemory
from wex_platform.services.geocoding_service import GeocodingResult


async def create_warehouse_from_search(
    db: AsyncSession,
    property_data: dict,
    geocoding: GeocodingResult,
    raw_address: str = "",
    owner_email: Optional[str] = None,
    evidence_bundle: Optional[dict] = None,
    fields_by_source: Optional[dict] = None,
) -> tuple:
    """Create Warehouse + TruthCore + ContextualMemory from search results."""

    warehouse_id = str(uuid.uuid4())
    now = datetime.utcnow()

    # Use geocoding data when available, fall back to raw address / Gemini data
    resolved_address = geocoding.formatted_address if geocoding.is_valid else raw_address

    # Create Warehouse record
    warehouse = Warehouse(
        id=warehouse_id,
        address=resolved_address,
        city=geocoding.city or property_data.get("city") or "",
        state=geocoding.state or property_data.get("state") or "",
        zip=geocoding.zip_code or property_data.get("zip_code") or "",
        lat=geocoding.lat,
        lng=geocoding.lng,
        building_size_sqft=property_data.get("building_size_sqft"),
        lot_size_acres=property_data.get("lot_size_acres"),
        year_built=property_data.get("year_built"),
        construction_type=property_data.get("construction_type"),
        zoning=property_data.get("zoning"),
        property_type=property_data.get("property_type"),
        owner_email=owner_email,
        created_at=now,
        updated_at=now,
    )

    # Generate map images from geocoding + merge extracted images
    image_urls = []
    if geocoding.lat and geocoding.lng:
        from wex_platform.app.config import get_settings
        settings = get_settings()
        maps_key = settings.google_maps_api_key
        if maps_key:
            base = "https://maps.googleapis.com/maps/api/staticmap"
            sv = "https://maps.googleapis.com/maps/api/streetview"
            lat, lng = geocoding.lat, geocoding.lng
            # 1. Satellite view — close-up aerial (zoom 18)
            image_urls.append(
                f"{base}?center={lat},{lng}"
                f"&zoom=18&size=600x400&maptype=satellite&key={maps_key}"
            )
            # 2. Street View — only include if imagery exists at this location
            try:
                import httpx
                sv_meta = httpx.get(
                    f"{sv}/metadata?location={lat},{lng}&key={maps_key}",
                    timeout=5,
                )
                if sv_meta.status_code == 200 and sv_meta.json().get("status") == "OK":
                    image_urls.append(
                        f"{sv}?size=600x400&location={lat},{lng}&key={maps_key}"
                    )
            except Exception:
                pass  # skip street view if metadata check fails
            # 3. Roadmap view — contextual location with pin
            image_urls.append(
                f"{base}?center={lat},{lng}"
                f"&zoom=15&size=600x400&maptype=roadmap"
                f"&markers=color:red%7C{lat},{lng}&key={maps_key}"
            )

    # Merge property photos extracted from CRE listings (up to 7)
    extracted_images = property_data.get("image_urls", [])
    logger.info(
        "[PropertyService] CRE images from Gemini: %s (type=%s), Google Maps images: %d",
        len(extracted_images) if isinstance(extracted_images, list) else repr(extracted_images),
        type(extracted_images).__name__,
        len(image_urls),
    )
    if extracted_images and isinstance(extracted_images, list):
        for url in extracted_images[:7]:
            if isinstance(url, str) and url.startswith("http") and url not in image_urls:
                image_urls.append(url)

    # Cap at 10 images total
    image_urls = image_urls[:10]

    warehouse.image_urls = image_urls
    warehouse.primary_image_url = image_urls[0] if image_urls else None

    # Create TruthCore record
    # Use building_size_sqft for max_sqft, derive min_sqft as 10% rounded to nearest 1000
    building_size = property_data.get("building_size_sqft") or 0
    min_sqft = max(1000, round(building_size * 0.1 / 1000) * 1000) if building_size else 1000

    truth_core = TruthCore(
        id=str(uuid.uuid4()),
        warehouse_id=warehouse_id,
        activation_status="off",
        min_sqft=min_sqft,
        max_sqft=building_size or min_sqft,
        activity_tier="storage_only",
        supplier_rate_per_sqft=0.0,
        clear_height_ft=property_data.get("clear_height_ft"),
        dock_doors_receiving=property_data.get("dock_doors") or 0,
        dock_doors_shipping=0,
        drive_in_bays=property_data.get("drive_in_bays") or 0,
        parking_spaces=property_data.get("parking_spaces") or 0,
        has_sprinkler=property_data.get("sprinkler_system") or False,
        has_office_space=property_data.get("has_office_space") or False,
        power_supply=property_data.get("power_supply"),
        trust_level=0,
        created_at=now,
        updated_at=now,
    )

    # Create ContextualMemory records
    memories = []

    # Search intelligence memory
    if property_data.get("property_overview") or property_data.get("additional_features"):
        memories.append(ContextualMemory(
            id=str(uuid.uuid4()),
            warehouse_id=warehouse_id,
            memory_type="search_intelligence",
            content=json.dumps({
                "overview": property_data.get("property_overview"),
                "features": property_data.get("additional_features", []),
                "building_class": property_data.get("building_class"),
                "confidence": property_data.get("confidence"),
                "fields_by_source": fields_by_source,
            }),
            source="gemini_search",
            confidence=property_data.get("confidence", 0.5),
            created_at=now,
        ))

    # Source provenance memory
    if property_data.get("source_urls"):
        memories.append(ContextualMemory(
            id=str(uuid.uuid4()),
            warehouse_id=warehouse_id,
            memory_type="source_provenance",
            content=json.dumps({
                "source_urls": property_data.get("source_urls", []),
                "retrieved_at": now.isoformat(),
            }),
            source="gemini_search",
            confidence=1.0,
            created_at=now,
        ))

    # Evidence bundle memory (audit trail)
    if evidence_bundle:
        memories.append(ContextualMemory(
            id=str(uuid.uuid4()),
            warehouse_id=warehouse_id,
            memory_type="evidence_bundle",
            content=json.dumps(evidence_bundle, default=str),
            source="gemini_search",
            confidence=1.0,
            created_at=now,
        ))

    # Extended attributes (not yet promoted to columns)
    extended = {}
    for field in ["trailer_parking", "rail_served", "fenced_yard",
                  "column_spacing_ft", "number_of_stories", "warehouse_heated"]:
        val = property_data.get(field)
        if val is not None:
            extended[field] = val

    if extended:
        memories.append(ContextualMemory(
            id=str(uuid.uuid4()),
            warehouse_id=warehouse_id,
            memory_type="extended_attributes",
            content=json.dumps(extended),
            source="gemini_search",
            confidence=property_data.get("confidence", 0.5),
            created_at=now,
        ))

    # Persist all
    db.add(warehouse)
    db.add(truth_core)
    for mem in memories:
        db.add(mem)
    await db.flush()

    return warehouse, truth_core, memories

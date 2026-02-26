"""Backfill script: migrate Warehouse + TruthCore + PropertyProfile → new Property schema.

This script is idempotent — it skips any Property rows that already exist.
It is invoked automatically during init_db() for SQLite (dev) environments.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wex_platform.domain.models import (
    ContextualMemory,
    Property,
    PropertyContact,
    PropertyEvent,
    PropertyKnowledge,
    PropertyListing,
    PropertyProfile,
    TruthCore,
    Warehouse,
)


# ---------------------------------------------------------------------------
# Status mapping: Warehouse.supplier_status → Property.relationship_status
# ---------------------------------------------------------------------------
_STATUS_MAP = {
    "third_party": "prospect",
    "earncheck_only": "earncheck_only",
    "interested": "interested",
    "in_network": "active",
    "onboarding": "earncheck_only",
}


def _map_status(supplier_status: str | None) -> str:
    """Map legacy supplier_status to new relationship_status."""
    if not supplier_status:
        return "prospect"
    return _STATUS_MAP.get(supplier_status, "prospect")


def _provenance_entry(value, source: str) -> dict | None:
    """Return a provenance dict if value is non-null."""
    if value is None:
        return None
    return {"source": source, "at": datetime.now(timezone.utc).isoformat()}


async def backfill_properties(session: AsyncSession) -> dict:
    """Migrate data from legacy tables to new property schema. Returns stats dict."""

    stats = {
        "properties_created": 0,
        "knowledge_created": 0,
        "listings_created": 0,
        "contacts_created": 0,
        "events_created": 0,
    }

    # 1. Load all warehouses with their truth_cores
    wh_result = await session.execute(
        select(Warehouse).options(selectinload(Warehouse.truth_core))
    )
    warehouses = wh_result.scalars().all()

    # 2. Load all PropertyProfile rows keyed by warehouse_id (soft FK)
    pp_result = await session.execute(select(PropertyProfile))
    profiles_by_wh: dict[str, PropertyProfile] = {}
    for pp in pp_result.scalars().all():
        if pp.warehouse_id:
            profiles_by_wh[pp.warehouse_id] = pp

    # 3. Load existing Property IDs to skip duplicates
    existing_result = await session.execute(select(Property.id))
    existing_ids = {row[0] for row in existing_result.all()}

    for wh in warehouses:
        # Skip if already migrated
        if wh.id in existing_ids:
            continue

        tc: TruthCore | None = wh.truth_core
        pp: PropertyProfile | None = profiles_by_wh.get(wh.id)

        # -----------------------------------------------------------------
        # 3a. Create Property (identity fields from Warehouse)
        # -----------------------------------------------------------------
        prop = Property(
            id=wh.id,  # Reuse UUID
            source="manual",
            address=wh.address,
            city=wh.city,
            state=wh.state,
            zip=wh.zip,
            lat=wh.lat,
            lng=wh.lng,
            neighborhood=wh.neighborhood,
            market=None,
            relationship_status=_map_status(wh.supplier_status),
            company_id=wh.company_id,
            property_type=wh.property_type,
            primary_image_url=wh.primary_image_url,
            image_urls=wh.image_urls or [],
            created_at=wh.created_at,
            updated_at=wh.updated_at,
        )
        session.add(prop)
        stats["properties_created"] += 1

        # -----------------------------------------------------------------
        # 3b. Create PropertyKnowledge (merge Warehouse + TruthCore + PP)
        #     Conflict resolution:
        #       - Building specs: PropertyProfile wins if non-null
        #       - Location fields: Warehouse wins (handled in Property)
        #       - Pricing/operational: TruthCore wins
        # -----------------------------------------------------------------
        provenance: dict[str, dict] = {}

        _confidence_map = {
            "truth_core": 0.90,         # Supplier-confirmed data
            "property_profile": 0.60,   # AI/Gemini-enriched data
            "warehouse": 0.80,          # Manual/imported data
            "migration": 0.70,          # Unknown origin
        }

        def _pick(field_name: str, *sources: tuple):
            """Pick the first non-null value from prioritized sources.
            Each source is (value, source_label).
            Returns the winning value and updates provenance with confidence.
            """
            for val, label in sources:
                if val is not None:
                    provenance[field_name] = {
                        "source": label,
                        "confidence": _confidence_map.get(label, 0.70),
                        "at": datetime.now(timezone.utc).isoformat(),
                    }
                    return val
            return None

        # PropertyProfile wins for building specs
        building_size_sqft = _pick(
            "building_size_sqft",
            (pp.building_size_sqft if pp else None, "property_profile"),
            (wh.building_size_sqft, "warehouse"),
        )
        clear_height_ft = _pick(
            "clear_height_ft",
            (pp.clear_height_ft if pp else None, "property_profile"),
            (tc.clear_height_ft if tc else None, "truth_core"),
        )
        dock_doors = _pick(
            "dock_doors",
            (pp.dock_doors if pp else None, "property_profile"),
        )
        dock_doors_receiving = _pick(
            "dock_doors_receiving",
            (tc.dock_doors_receiving if tc else None, "truth_core"),
        )
        dock_doors_shipping = _pick(
            "dock_doors_shipping",
            (tc.dock_doors_shipping if tc else None, "truth_core"),
        )
        drive_in_bays = _pick(
            "drive_in_bays",
            (pp.drive_in_bays if pp else None, "property_profile"),
            (tc.drive_in_bays if tc else None, "truth_core"),
        )
        parking_spaces = _pick(
            "parking_spaces",
            (pp.parking_spaces if pp else None, "property_profile"),
            (tc.parking_spaces if tc else None, "truth_core"),
        )
        trailer_parking = _pick(
            "trailer_parking",
            (pp.trailer_parking if pp else None, "property_profile"),
        )
        has_sprinkler = _pick(
            "has_sprinkler",
            (pp.has_sprinkler if pp else None, "property_profile"),
            (tc.has_sprinkler if tc else None, "truth_core"),
        )
        power_supply = _pick(
            "power_supply",
            (pp.power_supply if pp else None, "property_profile"),
            (tc.power_supply if tc else None, "truth_core"),
        )
        has_office = _pick(
            "has_office",
            (pp.has_office if pp else None, "property_profile"),
            (tc.has_office_space if tc else None, "truth_core"),
        )
        column_spacing_ft = _pick(
            "column_spacing_ft",
            (pp.column_spacing_ft if pp else None, "property_profile"),
        )
        number_of_stories = _pick(
            "number_of_stories",
            (pp.number_of_stories if pp else None, "property_profile"),
        )
        year_built = _pick(
            "year_built",
            (pp.year_built if pp else None, "property_profile"),
            (wh.year_built, "warehouse"),
        )
        year_renovated = _pick(
            "year_renovated",
            (pp.year_renovated if pp else None, "property_profile"),
        )
        construction_type = _pick(
            "construction_type",
            (pp.construction_type if pp else None, "property_profile"),
            (wh.construction_type, "warehouse"),
        )
        building_class = _pick(
            "building_class",
            (pp.building_class if pp else None, "property_profile"),
        )
        zoning = _pick(
            "zoning",
            (pp.zoning if pp else None, "property_profile"),
            (wh.zoning, "warehouse"),
        )
        lot_size_acres = _pick(
            "lot_size_acres",
            (pp.lot_size_acres if pp else None, "property_profile"),
            (wh.lot_size_acres, "warehouse"),
        )
        rail_served = _pick(
            "rail_served",
            (pp.rail_served if pp else None, "property_profile"),
        )
        fenced_yard = _pick(
            "fenced_yard",
            (pp.fenced_yard if pp else None, "property_profile"),
        )
        warehouse_heated = _pick(
            "warehouse_heated",
            (pp.warehouse_heated if pp else None, "property_profile"),
        )
        weekend_access = _pick(
            "weekend_access",
            (pp.weekend_access if pp else None, "property_profile"),
        )
        # TruthCore wins for operational/pricing fields
        activity_tier = _pick(
            "activity_tier",
            (tc.activity_tier if tc else None, "truth_core"),
            (pp.activity_tier if pp else None, "property_profile"),
        )
        market_rate_low = _pick(
            "market_rate_low",
            (pp.market_rate_low if pp else None, "property_profile"),
        )
        market_rate_high = _pick(
            "market_rate_high",
            (pp.market_rate_high if pp else None, "property_profile"),
        )
        ai_profile_summary = _pick(
            "ai_profile_summary",
            (pp.ai_profile_summary if pp else None, "property_profile"),
        )
        additional_notes = _pick(
            "additional_notes",
            (pp.additional_notes if pp else None, "property_profile"),
        )

        knowledge = PropertyKnowledge(
            id=str(uuid.uuid4()),
            property_id=wh.id,
            building_size_sqft=building_size_sqft,
            estimated_sqft=False,
            clear_height_ft=clear_height_ft,
            dock_doors=dock_doors,
            dock_doors_receiving=dock_doors_receiving,
            dock_doors_shipping=dock_doors_shipping,
            drive_in_bays=drive_in_bays,
            parking_spaces=parking_spaces,
            trailer_parking=trailer_parking,
            has_sprinkler=has_sprinkler,
            power_supply=power_supply,
            has_office=has_office,
            column_spacing_ft=column_spacing_ft,
            number_of_stories=number_of_stories,
            year_built=year_built,
            year_renovated=year_renovated,
            construction_type=construction_type,
            building_class=building_class,
            zoning=zoning,
            lot_size_acres=lot_size_acres,
            rail_served=rail_served,
            fenced_yard=fenced_yard,
            warehouse_heated=warehouse_heated,
            weekend_access=weekend_access,
            use_types=None,
            activity_tier=activity_tier,
            market_rate_low=market_rate_low,
            market_rate_high=market_rate_high,
            ai_profile_summary=ai_profile_summary,
            additional_notes=additional_notes,
            field_provenance=provenance,
            enrichment_source="manual",
        )
        session.add(knowledge)
        stats["knowledge_created"] += 1

        # -----------------------------------------------------------------
        # 3c. Create PropertyListing from TruthCore (if exists)
        # -----------------------------------------------------------------
        if tc:
            listing = PropertyListing(
                id=str(uuid.uuid4()),
                property_id=wh.id,
                activation_status=tc.activation_status or "off",
                activated_at=tc.toggled_at if tc.activation_status == "on" else None,
                tour_readiness=tc.tour_readiness or "48_hours",
                tour_required=False,
                trust_level=tc.trust_level or 0,
                available_sqft=wh.available_sqft,  # Mutable operational field from Warehouse
                min_sqft=tc.min_sqft,
                max_sqft=tc.max_sqft,
                available_from=tc.available_from.date() if tc.available_from else None,
                available_to=tc.available_to.date() if tc.available_to else None,
                pricing_mode="manual",
                supplier_rate_per_sqft=tc.supplier_rate_per_sqft,
                recommended_rate=pp.recommended_rate if pp else None,
                min_rentable=pp.min_rentable if pp else None,
                min_term_months=tc.min_term_months or 1,
                max_term_months=tc.max_term_months or 12,
                constraints=tc.constraints or {},
            )
            session.add(listing)
            stats["listings_created"] += 1

        # -----------------------------------------------------------------
        # 3d. Create PropertyContact from Warehouse.owner_* fields
        # -----------------------------------------------------------------
        if wh.owner_name or wh.owner_email or wh.owner_phone:
            contact = PropertyContact(
                id=str(uuid.uuid4()),
                property_id=wh.id,
                contact_type="owner",
                name=wh.owner_name or "Unknown",
                email=wh.owner_email,
                phone=wh.owner_phone,
                is_primary=True,
                company_id=wh.company_id,
            )
            session.add(contact)
            stats["contacts_created"] += 1

        # -----------------------------------------------------------------
        # 3e. Create PropertyEvent rows from lifecycle timestamps
        # -----------------------------------------------------------------
        if wh.earncheck_completed_at:
            session.add(PropertyEvent(
                id=str(uuid.uuid4()),
                property_id=wh.id,
                event_type="earncheck_completed",
                actor="system",
                metadata_={"migrated_from": "warehouse.earncheck_completed_at"},
                created_at=wh.earncheck_completed_at,
            ))
            stats["events_created"] += 1

        if wh.onboarded_at:
            session.add(PropertyEvent(
                id=str(uuid.uuid4()),
                property_id=wh.id,
                event_type="activated",
                actor="system",
                metadata_={"migrated_from": "warehouse.onboarded_at"},
                created_at=wh.onboarded_at,
            ))
            stats["events_created"] += 1

        if wh.last_outreach_at:
            session.add(PropertyEvent(
                id=str(uuid.uuid4()),
                property_id=wh.id,
                event_type="outreach_sent",
                actor="system",
                metadata_={"migrated_from": "warehouse.last_outreach_at"},
                created_at=wh.last_outreach_at,
            ))
            stats["events_created"] += 1

    await session.commit()
    return stats

"""Service for generating and storing warehouse descriptions."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.agents.description_agent import DescriptionAgent
from wex_platform.domain.models import Warehouse, TruthCore, Property, PropertyKnowledge, PropertyListing

logger = logging.getLogger(__name__)


async def generate_warehouse_description(
    db: AsyncSession,
    warehouse_id: str,
) -> str | None:
    """Generate and store an AI description for a warehouse.

    Loads the warehouse and its truth core, calls the DescriptionAgent,
    and persists the result in ``Warehouse.description``.

    Args:
        db: Active async database session (caller manages commit).
        warehouse_id: UUID of the warehouse to describe.

    Returns:
        The generated description text, or None on failure.
    """
    # Try new Property model first, fall back to legacy Warehouse
    prop = await db.get(Property, warehouse_id)
    if prop:
        pk_result = await db.execute(
            select(PropertyKnowledge).where(PropertyKnowledge.property_id == warehouse_id)
        )
        pk = pk_result.scalar_one_or_none()

        pl_result = await db.execute(
            select(PropertyListing).where(PropertyListing.property_id == warehouse_id)
        )
        pl = pl_result.scalar_one_or_none()

        total_docks = 0
        if pk:
            total_docks = (pk.dock_doors_receiving or 0) + (pk.dock_doors_shipping or 0)

        agent = DescriptionAgent()
        result = await agent.generate_description(
            address=prop.address or "",
            city=prop.city or "",
            state=prop.state or "",
            building_size_sqft=pk.building_size_sqft if pk else None,
            clear_height_ft=pk.clear_height_ft if pk else None,
            dock_doors=total_docks if total_docks > 0 else None,
            drive_in_bays=pk.drive_in_bays if pk else None,
            parking_spaces=pk.parking_spaces if pk else None,
            has_office_space=pk.has_office if pk else None,
            has_sprinkler=pk.has_sprinkler if pk else None,
            power_supply=pk.power_supply if pk else None,
            activity_tier=pk.activity_tier if pk else None,
            year_built=pk.year_built if pk else None,
            construction_type=pk.construction_type if pk else None,
        )
    else:
        # Fall back to legacy Warehouse model
        wh = await db.get(Warehouse, warehouse_id)
        if not wh:
            logger.warning("Property/Warehouse %s not found for description gen", warehouse_id)
            return None

        tc_result = await db.execute(
            select(TruthCore).where(TruthCore.warehouse_id == warehouse_id)
        )
        tc = tc_result.scalar_one_or_none()

        total_docks = 0
        if tc:
            total_docks = (tc.dock_doors_receiving or 0) + (tc.dock_doors_shipping or 0)

        agent = DescriptionAgent()
        result = await agent.generate_description(
            address=wh.address or "",
            city=wh.city or "",
            state=wh.state or "",
            building_size_sqft=wh.building_size_sqft,
            clear_height_ft=tc.clear_height_ft if tc else None,
            dock_doors=total_docks if total_docks > 0 else None,
            drive_in_bays=tc.drive_in_bays if tc else None,
            parking_spaces=tc.parking_spaces if tc else None,
            has_office_space=tc.has_office_space if tc else None,
            has_sprinkler=tc.has_sprinkler if tc else None,
            power_supply=tc.power_supply if tc else None,
            activity_tier=tc.activity_tier if tc else None,
            year_built=wh.year_built,
            construction_type=wh.construction_type,
        )
        prop = wh  # For description storage below

    if result.ok and result.data:
        description = str(result.data).strip()
        if len(description) > 5000:
            description = description[:4997] + "..."
        # Store description on whichever model we found
        if hasattr(prop, 'description'):
            prop.description = description
        logger.info(
            "Description generated for property %s (%d chars)",
            warehouse_id,
            len(description),
        )
        return description

    logger.error(
        "Description generation failed for %s: %s",
        warehouse_id,
        result.error,
    )
    return None

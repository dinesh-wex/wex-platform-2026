"""Backfill script: geocode warehouses missing lat/lng or neighborhood.

Usage:
    cd backend
    python scripts/backfill_coordinates.py

Requires GOOGLE_MAPS_API_KEY in .env (already configured).
"""

import asyncio
import logging
import os
import sys

# Ensure backend/src is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


async def backfill():
    from sqlalchemy import select, or_, and_
    from wex_platform.app.config import get_settings
    from wex_platform.infra.database import async_session, init_db
    from wex_platform.domain.models import Warehouse
    from wex_platform.services.geocoding_service import GeocodingService

    settings = get_settings()
    if not settings.google_maps_api_key:
        logger.error("GOOGLE_MAPS_API_KEY not set in .env — aborting.")
        return

    await init_db()

    geo = GeocodingService(settings.google_maps_api_key)

    async with async_session() as session:
        # Find warehouses missing coordinates OR missing neighborhood
        stmt = select(Warehouse).where(
            or_(
                Warehouse.lat.is_(None),
                Warehouse.lng.is_(None),
                Warehouse.neighborhood.is_(None),
            )
        )
        result = await session.execute(stmt)
        warehouses = result.scalars().all()

        if not warehouses:
            logger.info("All warehouses already have coordinates and neighborhood. Nothing to do.")
            return

        needs_coords = sum(1 for w in warehouses if w.lat is None or w.lng is None)
        needs_neighborhood = sum(1 for w in warehouses if w.lat is not None and w.neighborhood is None)
        logger.info(
            "Found %d warehouses to process (%d missing coordinates, %d missing neighborhood only).",
            len(warehouses), needs_coords, needs_neighborhood,
        )

        updated = 0
        failed = 0

        for wh in warehouses:
            # Build the best query from available fields
            parts = []
            if wh.address:
                parts.append(wh.address)
            if wh.city:
                parts.append(wh.city)
            if wh.state:
                parts.append(wh.state)
            if wh.zip:
                parts.append(wh.zip)

            if not parts:
                logger.warning("  [%s] No address data — skipping.", wh.id)
                failed += 1
                continue

            query = ", ".join(parts)
            logger.info("  [%s] Geocoding: %s", wh.id, query)

            geo_result = await geo.geocode(query)

            if geo_result is None:
                logger.warning("  [%s] Geocoding failed — skipping.", wh.id)
                failed += 1
                continue

            # Always update coordinates
            wh.lat = geo_result.lat
            wh.lng = geo_result.lng

            # Backfill city/state/zip/neighborhood if missing
            if not wh.city and geo_result.city:
                wh.city = geo_result.city
            if not wh.state and geo_result.state:
                wh.state = geo_result.state
            if not wh.zip and geo_result.zip_code:
                wh.zip = geo_result.zip_code
            if geo_result.neighborhood:
                wh.neighborhood = geo_result.neighborhood

            updated += 1
            neighborhood_info = f", neighborhood={geo_result.neighborhood}" if geo_result.neighborhood else ""
            logger.info(
                "  [%s] → lat=%.6f, lng=%.6f (confidence=%.1f%s)",
                wh.id, geo_result.lat, geo_result.lng, geo_result.confidence, neighborhood_info,
            )

            # Rate limit: Google allows 50 QPS, but be polite
            await asyncio.sleep(0.1)

        await session.commit()
        logger.info(
            "Done. Updated: %d, Failed: %d, Total: %d",
            updated, failed, len(warehouses),
        )


if __name__ == "__main__":
    asyncio.run(backfill())

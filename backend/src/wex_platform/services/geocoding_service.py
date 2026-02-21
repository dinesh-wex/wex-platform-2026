"""Address normalization via Google Maps Geocoding API."""
import logging
from dataclasses import dataclass
from typing import Optional
import httpx

logger = logging.getLogger(__name__)


@dataclass
class GeocodingResult:
    is_valid: bool
    formatted_address: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    error: Optional[str] = None


async def normalize_address(raw_address: str) -> GeocodingResult:
    """Normalize a user-typed address via Google Maps Geocoding API.

    Handles typos, abbreviations, and partial addresses.
    """
    from wex_platform.app.config import get_settings
    settings = get_settings()

    api_key = settings.google_maps_api_key
    if not api_key:
        logger.warning("GOOGLE_MAPS_API_KEY not set, skipping geocoding")
        return GeocodingResult(is_valid=False, error="Geocoding API key not configured")

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": raw_address, "key": api_key}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        if data["status"] != "OK" or not data.get("results"):
            logger.warning("Geocoding returned status '%s' for '%s'", data["status"], raw_address)
            return GeocodingResult(is_valid=False, error=f"Geocoding status: {data['status']}")

        result = data["results"][0]
        components = {c["types"][0]: c for c in result["address_components"] if c.get("types")}

        return GeocodingResult(
            is_valid=True,
            formatted_address=result["formatted_address"],
            lat=result["geometry"]["location"]["lat"],
            lng=result["geometry"]["location"]["lng"],
            city=components.get("locality", {}).get("long_name") or components.get("sublocality", {}).get("long_name"),
            state=components.get("administrative_area_level_1", {}).get("short_name"),
            zip_code=components.get("postal_code", {}).get("long_name"),
        )
    except Exception as exc:
        logger.error("Geocoding failed for '%s': %s", raw_address, exc)
        return GeocodingResult(is_valid=False, error=str(exc))

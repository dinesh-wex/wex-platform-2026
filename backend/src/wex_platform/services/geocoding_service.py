"""Geocoding service wrapping the Google Maps Geocoding API.

Provides forward and reverse geocoding with an in-memory LRU cache
and async HTTP via httpx.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GOOGLE_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

CONFIDENCE_MAP: dict[str, float] = {
    "ROOFTOP": 1.0,
    "RANGE_INTERPOLATED": 0.8,
    "GEOMETRIC_CENTER": 0.6,
    "APPROXIMATE": 0.4,
}

_MAX_CACHE_SIZE = 10_000


@dataclass(frozen=True)
class GeoResult:
    lat: float
    lng: float
    city: str
    state: str
    zip_code: str
    formatted_address: str
    confidence: float
    neighborhood: str = ""


class GeocodingService:
    """Async geocoding service backed by the Google Maps Geocoding API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._cache: OrderedDict[str, GeoResult | None] = OrderedDict()

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _normalize_key(self, raw: str) -> str:
        return raw.strip().lower()

    def _cache_get(self, key: str) -> tuple[bool, GeoResult | None]:
        """Return (hit, value). Moves item to end on hit (LRU)."""
        if key in self._cache:
            self._cache.move_to_end(key)
            return True, self._cache[key]
        return False, None

    def _cache_put(self, key: str, value: GeoResult | None) -> None:
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = value
        else:
            self._cache[key] = value
            if len(self._cache) > _MAX_CACHE_SIZE:
                self._cache.popitem(last=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def geocode(self, query: str) -> GeoResult | None:
        """Forward-geocode *query* into a `GeoResult`."""
        cache_key = self._normalize_key(query)
        hit, cached = self._cache_get(cache_key)
        if hit:
            return cached

        params = {
            "address": query,
            "key": self._api_key,
        }

        result = await self._fetch(params)
        self._cache_put(cache_key, result)
        return result

    async def reverse_geocode(self, lat: float, lng: float) -> GeoResult | None:
        """Reverse-geocode a lat/lng pair into a `GeoResult`."""
        cache_key = self._normalize_key(f"{lat},{lng}")
        hit, cached = self._cache_get(cache_key)
        if hit:
            return cached

        params = {
            "latlng": f"{lat},{lng}",
            "key": self._api_key,
        }

        result = await self._fetch(params)
        self._cache_put(cache_key, result)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch(self, params: dict) -> GeoResult | None:
        """Execute the HTTP request to Google and parse the response."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(GOOGLE_GEOCODE_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("Google Geocoding API HTTP error: %s", exc)
            return None
        except httpx.RequestError as exc:
            logger.warning("Google Geocoding API request failed: %s", exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unexpected error during geocoding request: %s", exc)
            return None

        return self._parse_google_response(data)

    def _parse_google_response(self, data: dict) -> GeoResult | None:
        """Extract relevant fields from the Google Geocoding JSON response."""
        status = data.get("status")
        if status != "OK":
            if status not in ("ZERO_RESULTS",):
                logger.warning("Google Geocoding API returned status: %s", status)
            return None

        results = data.get("results")
        if not results:
            return None

        top = results[0]

        # --- Location ---
        geometry = top.get("geometry", {})
        location = geometry.get("location", {})
        lat = location.get("lat")
        lng = location.get("lng")
        if lat is None or lng is None:
            logger.warning("Missing lat/lng in geocoding response")
            return None

        # --- Confidence ---
        location_type = geometry.get("location_type", "")
        confidence = CONFIDENCE_MAP.get(location_type, 0.4)

        # --- Address components ---
        components = top.get("address_components", [])
        city = ""
        state = ""
        zip_code = ""
        neighborhood = ""

        for comp in components:
            types = comp.get("types", [])
            if "neighborhood" in types and not neighborhood:
                neighborhood = comp.get("long_name", "")
            if "locality" in types and not city:
                city = comp.get("long_name", "")
            elif "sublocality" in types and not city:
                city = comp.get("long_name", "")
            if "administrative_area_level_1" in types:
                state = comp.get("short_name", "")
            if "postal_code" in types:
                zip_code = comp.get("long_name", "")

        formatted_address = top.get("formatted_address", "")

        return GeoResult(
            lat=lat,
            lng=lng,
            city=city,
            state=state,
            zip_code=zip_code,
            formatted_address=formatted_address,
            confidence=confidence,
            neighborhood=neighborhood,
        )


# ----------------------------------------------------------------------
# Module-level convenience
# ----------------------------------------------------------------------


async def geocode_location(query: str) -> GeoResult | None:
    """Convenience: geocode using the configured API key."""
    from wex_platform.app.config import get_settings

    settings = get_settings()
    if not settings.google_maps_api_key:
        return None
    service = GeocodingService(settings.google_maps_api_key)
    return await service.geocode(query)


@dataclass
class NormalizeResult:
    """Result of address normalization via geocoding."""
    is_valid: bool
    formatted_address: str
    lat: float | None = None
    lng: float | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None


async def normalize_address(address: str) -> NormalizeResult:
    """Normalize an address string via geocoding.

    Returns a NormalizeResult with is_valid=True and the formatted address
    if geocoding succeeds, or is_valid=False with the original address.
    """
    geo = await geocode_location(address)
    if geo:
        return NormalizeResult(
            is_valid=True,
            formatted_address=geo.formatted_address,
            lat=geo.lat,
            lng=geo.lng,
            city=geo.city,
            state=geo.state,
            zip_code=geo.zip_code,
        )
    return NormalizeResult(is_valid=False, formatted_address=address)

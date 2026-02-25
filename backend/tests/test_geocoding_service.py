"""Comprehensive tests for wex_platform.services.geocoding_service.

All HTTP calls are mocked — no real Google API requests are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from wex_platform.services.geocoding_service import (
    CONFIDENCE_MAP,
    GeocodingService,
    GeoResult,
    _MAX_CACHE_SIZE,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

FAKE_API_KEY = "test-api-key-123"


def _google_ok_response(
    lat: float = 34.0522,
    lng: float = -118.2437,
    location_type: str = "ROOFTOP",
    city: str = "Los Angeles",
    state_short: str = "CA",
    zip_code: str = "90012",
    formatted_address: str = "123 Main St, Los Angeles, CA 90012, USA",
) -> dict:
    """Build a realistic Google Maps Geocoding API 'OK' response."""
    return {
        "status": "OK",
        "results": [
            {
                "formatted_address": formatted_address,
                "geometry": {
                    "location": {"lat": lat, "lng": lng},
                    "location_type": location_type,
                },
                "address_components": [
                    {
                        "long_name": "123",
                        "short_name": "123",
                        "types": ["street_number"],
                    },
                    {
                        "long_name": "Main Street",
                        "short_name": "Main St",
                        "types": ["route"],
                    },
                    {
                        "long_name": city,
                        "short_name": city,
                        "types": ["locality", "political"],
                    },
                    {
                        "long_name": "Los Angeles County",
                        "short_name": "Los Angeles County",
                        "types": ["administrative_area_level_2", "political"],
                    },
                    {
                        "long_name": "California",
                        "short_name": state_short,
                        "types": ["administrative_area_level_1", "political"],
                    },
                    {
                        "long_name": "United States",
                        "short_name": "US",
                        "types": ["country", "political"],
                    },
                    {
                        "long_name": zip_code,
                        "short_name": zip_code,
                        "types": ["postal_code"],
                    },
                ],
            }
        ],
    }


def _make_mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message="error",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def service() -> GeocodingService:
    return GeocodingService(api_key=FAKE_API_KEY)


# ---------------------------------------------------------------------------
# 1. _parse_google_response — realistic response
# ---------------------------------------------------------------------------


class TestParseGoogleResponse:
    def test_parse_extracts_all_fields(self, service: GeocodingService) -> None:
        data = _google_ok_response()
        result = service._parse_google_response(data)

        assert result is not None
        assert result.lat == 34.0522
        assert result.lng == -118.2437
        assert result.city == "Los Angeles"
        assert result.state == "CA"
        assert result.zip_code == "90012"
        assert result.formatted_address == "123 Main St, Los Angeles, CA 90012, USA"
        assert result.confidence == 1.0  # ROOFTOP

    def test_parse_returns_none_when_status_not_ok(self, service: GeocodingService) -> None:
        data = {"status": "REQUEST_DENIED", "results": []}
        assert service._parse_google_response(data) is None

    def test_parse_returns_none_on_zero_results(self, service: GeocodingService) -> None:
        data = {"status": "ZERO_RESULTS", "results": []}
        assert service._parse_google_response(data) is None

    def test_parse_returns_none_when_empty_results_list(self, service: GeocodingService) -> None:
        data = {"status": "OK", "results": []}
        assert service._parse_google_response(data) is None

    def test_parse_returns_none_when_lat_lng_missing(self, service: GeocodingService) -> None:
        data = {
            "status": "OK",
            "results": [
                {
                    "geometry": {"location": {}},
                    "address_components": [],
                    "formatted_address": "",
                }
            ],
        }
        assert service._parse_google_response(data) is None


# ---------------------------------------------------------------------------
# 2. Cache behaviour — second call doesn't make HTTP request
# ---------------------------------------------------------------------------


class TestCacheBehaviour:
    @pytest.mark.asyncio
    async def test_second_call_uses_cache(self, service: GeocodingService) -> None:
        mock_resp = _make_mock_response(_google_ok_response())
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("wex_platform.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            result1 = await service.geocode("Los Angeles, CA")
            result2 = await service.geocode("Los Angeles, CA")

        assert result1 is not None
        assert result2 is not None
        assert result1 == result2
        # Only one HTTP call should have been made
        assert mock_client.get.call_count == 1


# ---------------------------------------------------------------------------
# 3. Cache normalisation
# ---------------------------------------------------------------------------


class TestCacheNormalization:
    @pytest.mark.asyncio
    async def test_whitespace_and_case_normalized(self, service: GeocodingService) -> None:
        mock_resp = _make_mock_response(_google_ok_response())
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("wex_platform.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            result1 = await service.geocode("Los Angeles, CA")
            result2 = await service.geocode("  los angeles, ca  ")

        assert result1 is not None
        assert result2 is not None
        assert result1 == result2
        assert mock_client.get.call_count == 1


# ---------------------------------------------------------------------------
# 4. Cache eviction (LRU)
# ---------------------------------------------------------------------------


class TestCacheEviction:
    @pytest.mark.asyncio
    async def test_lru_eviction_when_exceeding_max_size(self) -> None:
        svc = GeocodingService(api_key=FAKE_API_KEY)

        # Manually populate the cache to just under max
        for i in range(_MAX_CACHE_SIZE):
            svc._cache_put(f"key-{i}", GeoResult(
                lat=float(i), lng=float(i),
                city="c", state="s", zip_code="z",
                formatted_address="a", confidence=1.0,
            ))

        assert len(svc._cache) == _MAX_CACHE_SIZE
        first_key = "key-0"
        assert first_key in svc._cache

        # Add one more item to trigger eviction of the oldest
        svc._cache_put("overflow-key", GeoResult(
            lat=0.0, lng=0.0, city="c", state="s",
            zip_code="z", formatted_address="a", confidence=1.0,
        ))

        assert len(svc._cache) == _MAX_CACHE_SIZE
        assert first_key not in svc._cache  # oldest item evicted
        assert "overflow-key" in svc._cache


# ---------------------------------------------------------------------------
# 5. API status != "OK"
# ---------------------------------------------------------------------------


class TestGeocodingFailure:
    @pytest.mark.asyncio
    async def test_returns_none_on_request_denied(self, service: GeocodingService) -> None:
        data = {"status": "REQUEST_DENIED", "error_message": "API key invalid"}
        mock_resp = _make_mock_response(data)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("wex_platform.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            result = await service.geocode("Nowhere")

        assert result is None


# ---------------------------------------------------------------------------
# 6. Network error
# ---------------------------------------------------------------------------


class TestNetworkError:
    @pytest.mark.asyncio
    async def test_returns_none_on_connection_error(self, service: GeocodingService) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ConnectError("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("wex_platform.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            result = await service.geocode("Los Angeles, CA")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self, service: GeocodingService) -> None:
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.side_effect = httpx.ReadTimeout("timed out")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("wex_platform.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            result = await service.geocode("Los Angeles, CA")

        assert result is None


# ---------------------------------------------------------------------------
# 7. Empty query
# ---------------------------------------------------------------------------


class TestEmptyQuery:
    @pytest.mark.asyncio
    async def test_empty_string_still_calls_api(self, service: GeocodingService) -> None:
        """An empty query is sent to the API; the API returns ZERO_RESULTS."""
        data = {"status": "ZERO_RESULTS", "results": []}
        mock_resp = _make_mock_response(data)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("wex_platform.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            result = await service.geocode("")

        assert result is None

    @pytest.mark.asyncio
    async def test_whitespace_only_query(self, service: GeocodingService) -> None:
        data = {"status": "ZERO_RESULTS", "results": []}
        mock_resp = _make_mock_response(data)
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("wex_platform.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            result = await service.geocode("   ")

        assert result is None


# ---------------------------------------------------------------------------
# 8. Confidence mapping
# ---------------------------------------------------------------------------


class TestConfidenceMapping:
    @pytest.mark.parametrize(
        "location_type,expected_confidence",
        [
            ("ROOFTOP", 1.0),
            ("RANGE_INTERPOLATED", 0.8),
            ("GEOMETRIC_CENTER", 0.6),
            ("APPROXIMATE", 0.4),
        ],
    )
    def test_confidence_values(
        self,
        service: GeocodingService,
        location_type: str,
        expected_confidence: float,
    ) -> None:
        data = _google_ok_response(location_type=location_type)
        result = service._parse_google_response(data)
        assert result is not None
        assert result.confidence == expected_confidence

    def test_unknown_location_type_defaults_to_0_4(self, service: GeocodingService) -> None:
        data = _google_ok_response(location_type="SOMETHING_NEW")
        result = service._parse_google_response(data)
        assert result is not None
        assert result.confidence == 0.4

    def test_confidence_map_constant_is_complete(self) -> None:
        assert CONFIDENCE_MAP == {
            "ROOFTOP": 1.0,
            "RANGE_INTERPOLATED": 0.8,
            "GEOMETRIC_CENTER": 0.6,
            "APPROXIMATE": 0.4,
        }


# ---------------------------------------------------------------------------
# 9. Reverse geocode
# ---------------------------------------------------------------------------


class TestReverseGeocode:
    @pytest.mark.asyncio
    async def test_reverse_geocode_basic(self, service: GeocodingService) -> None:
        mock_resp = _make_mock_response(_google_ok_response())
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("wex_platform.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            result = await service.reverse_geocode(34.0522, -118.2437)

        assert result is not None
        assert result.lat == 34.0522
        assert result.lng == -118.2437
        assert result.city == "Los Angeles"
        assert result.state == "CA"

        # Verify latlng param was sent
        call_kwargs = mock_client.get.call_args
        assert "latlng" in call_kwargs.kwargs.get("params", call_kwargs[1].get("params", {}))

    @pytest.mark.asyncio
    async def test_reverse_geocode_uses_cache(self, service: GeocodingService) -> None:
        mock_resp = _make_mock_response(_google_ok_response())
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("wex_platform.services.geocoding_service.httpx.AsyncClient", return_value=mock_client):
            r1 = await service.reverse_geocode(34.0522, -118.2437)
            r2 = await service.reverse_geocode(34.0522, -118.2437)

        assert r1 == r2
        assert mock_client.get.call_count == 1

"""Unit tests for IntakeExtractor and _parse_location."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from wex_platform.agents.base import AgentResult
from wex_platform.services.intake_extractor import IntakeExtractor
from wex_platform.domain.schemas import SearchRequest
from wex_platform.services.geocoding_service import GeoResult


# ── Helpers ──────────────────────────────────────────────────────────────

def _geo(city="Phoenix", state="AZ", lat=33.45, lng=-112.07):
    return GeoResult(
        lat=lat, lng=lng, city=city, state=state,
        zip_code="85001", formatted_address=f"{city}, {state}",
        confidence=0.9,
    )


# ═══════════════════════════════════════════════════════════════════════
# IntakeExtractor tests
# ═══════════════════════════════════════════════════════════════════════


class TestIntakeExtractorConfig:
    """Test 6: Verify model and temperature configuration."""

    def test_model_name_is_gemini_3_flash_preview(self):
        extractor = IntakeExtractor()
        assert extractor.model_name == "gemini-3-flash-preview"

    def test_temperature_is_0_1(self):
        extractor = IntakeExtractor()
        assert extractor.temperature == 0.1


class TestIntakeExtractorExtract:
    """Tests 1-5: extraction behaviour."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_dict(self):
        """Test 1: Empty text -> empty dict, ok=True."""
        extractor = IntakeExtractor()
        result = await extractor.extract("")
        assert result.ok is True
        assert result.data == {}

    @pytest.mark.asyncio
    async def test_whitespace_only_returns_empty_dict(self):
        """Test 2: Whitespace-only text -> empty dict, ok=True."""
        extractor = IntakeExtractor()
        result = await extractor.extract("   \t\n  ")
        assert result.ok is True
        assert result.data == {}

    @pytest.mark.asyncio
    async def test_valid_extraction_returns_cleaned_fields(self):
        """Test 3: Mock Gemini returning structured fields."""
        extractor = IntakeExtractor()
        mock_result = AgentResult.success(
            data={
                "location": "Phoenix, AZ",
                "size_sqft": 10000,
                "use_type": "storage_only",
                "timing": "March",
                "budget_per_sqft": None,
                "budget_monthly": None,
                "duration_months": 6,
                "requirements": ["dock doors"],
                "goods_type": "general",
            },
            tokens_used=150,
            latency_ms=200,
        )

        with patch.object(extractor, "generate_json", new_callable=AsyncMock, return_value=mock_result):
            result = await extractor.extract("I need 10k sqft in Phoenix AZ for storage starting March")

        assert result.ok is True
        assert result.data["location"] == "Phoenix, AZ"
        assert result.data["size_sqft"] == 10000
        assert result.data["use_type"] == "storage_only"
        assert result.data["timing"] == "March"
        assert result.data["duration_months"] == 6
        assert result.data["requirements"] == ["dock doors"]
        assert result.data["goods_type"] == "general"
        # Nulls must be stripped
        assert "budget_per_sqft" not in result.data
        assert "budget_monthly" not in result.data
        # Token/latency forwarded
        assert result.tokens_used == 150
        assert result.latency_ms == 200

    @pytest.mark.asyncio
    async def test_gemini_returns_all_nulls_stripped(self):
        """Test 4: All-null response -> empty dict after stripping."""
        extractor = IntakeExtractor()
        mock_result = AgentResult.success(
            data={
                "location": None,
                "size_sqft": None,
                "use_type": None,
                "timing": None,
            },
            tokens_used=50,
            latency_ms=100,
        )

        with patch.object(extractor, "generate_json", new_callable=AsyncMock, return_value=mock_result):
            result = await extractor.extract("hello")

        assert result.ok is True
        assert result.data == {}

    @pytest.mark.asyncio
    async def test_gemini_failure_returns_empty_dict(self):
        """Test 5: Gemini failure -> graceful fallback to empty dict, ok=True."""
        extractor = IntakeExtractor()
        mock_result = AgentResult.failure(error="API timeout")

        with patch.object(extractor, "generate_json", new_callable=AsyncMock, return_value=mock_result):
            result = await extractor.extract("10k sqft Phoenix")

        assert result.ok is True
        assert result.data == {}


# ═══════════════════════════════════════════════════════════════════════
# _parse_location tests
# ═══════════════════════════════════════════════════════════════════════

# Import the private function from the search module
from wex_platform.app.routes.search import _parse_location


class TestParseLocation:

    @pytest.mark.asyncio
    async def test_explicit_city_and_state_with_geocoding(self):
        """Test 7: city + state explicitly set -> geocodes and returns 4-tuple."""
        req = SearchRequest(city="Phoenix", state="AZ")

        with patch(
            "wex_platform.services.geocoding_service.geocode_location",
            new_callable=AsyncMock,
            return_value=_geo(),
        ) as mock_geo:
            city, state, lat, lng = await _parse_location(req)

        assert city == "Phoenix"
        assert state == "AZ"
        assert lat == 33.45
        assert lng == -112.07
        mock_geo.assert_awaited_once_with("Phoenix, AZ")

    @pytest.mark.asyncio
    async def test_location_string_phoenix_az(self):
        """Test 8: location='Phoenix, AZ' -> geocodes and returns 4-tuple."""
        req = SearchRequest(location="Phoenix, AZ")
        geo = _geo(city="Phoenix", state="AZ", lat=33.45, lng=-112.07)

        with patch(
            "wex_platform.services.geocoding_service.geocode_location",
            new_callable=AsyncMock,
            return_value=geo,
        ):
            city, state, lat, lng = await _parse_location(req)

        assert city == "Phoenix"
        assert state == "AZ"
        assert lat == 33.45
        assert lng == -112.07

    @pytest.mark.asyncio
    async def test_geocoding_failure_falls_back_to_comma_split(self):
        """Test 9: Geocoding raises -> comma-split with None lat/lng."""
        req = SearchRequest(location="Phoenix, AZ")

        with patch(
            "wex_platform.services.geocoding_service.geocode_location",
            new_callable=AsyncMock,
            side_effect=Exception("network error"),
        ):
            city, state, lat, lng = await _parse_location(req)

        assert city == "Phoenix"
        assert state == "AZ"
        assert lat is None
        assert lng is None

    @pytest.mark.asyncio
    async def test_location_zip_code_passed_to_geocoder(self):
        """Test 10: location='85281' -> passed to geocoder as-is."""
        req = SearchRequest(location="85281")
        geo = _geo(city="Tempe", state="AZ", lat=33.41, lng=-111.91)

        with patch(
            "wex_platform.services.geocoding_service.geocode_location",
            new_callable=AsyncMock,
            return_value=geo,
        ) as mock_geo:
            city, state, lat, lng = await _parse_location(req)

        mock_geo.assert_awaited_once_with("85281")
        assert city == "Tempe"
        assert state == "AZ"
        assert lat == 33.41
        assert lng == -111.91

    @pytest.mark.asyncio
    async def test_empty_location_returns_all_none(self):
        """Test 11: No location fields -> (None, None, None, None)."""
        req = SearchRequest()
        city, state, lat, lng = await _parse_location(req)
        assert (city, state, lat, lng) == (None, None, None, None)

"""Tests for LLM schema enforcement across Pydantic models, Gemini client, BaseAgent, and ClearingAgent."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from wex_platform.domain.schemas import FeatureEvalMatch, FeatureEvalResponse
from wex_platform.agents.base import AgentResult, BaseAgent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_settings():
    """Return a mock Settings object with a fake API key."""
    s = MagicMock()
    s.gemini_api_key = "fake-key-for-testing"
    return s


# ===================================================================
# 1-6  Pydantic Schema Validation
# ===================================================================


class TestFeatureEvalMatchValidation:
    """Tests 1-5: FeatureEvalMatch field-level validation."""

    def test_valid_data_passes(self):
        """Test 1: FeatureEvalMatch with valid data passes validation."""
        match = FeatureEvalMatch(
            warehouse_id="wh-001",
            feature_score=75,
            instant_book_eligible=True,
            reasoning="Great dock access and clear height for pallet storage.",
        )
        assert match.warehouse_id == "wh-001"
        assert match.feature_score == 75
        assert match.instant_book_eligible is True

    def test_feature_score_above_100_fails(self):
        """Test 2: feature_score=101 fails (le=100)."""
        with pytest.raises(ValidationError) as exc_info:
            FeatureEvalMatch(
                warehouse_id="wh-001",
                feature_score=101,
                instant_book_eligible=False,
                reasoning="Over the limit.",
            )
        assert "feature_score" in str(exc_info.value)

    def test_feature_score_negative_fails(self):
        """Test 3: feature_score=-1 fails (ge=0)."""
        with pytest.raises(ValidationError) as exc_info:
            FeatureEvalMatch(
                warehouse_id="wh-001",
                feature_score=-1,
                instant_book_eligible=False,
                reasoning="Negative score.",
            )
        assert "feature_score" in str(exc_info.value)

    def test_missing_warehouse_id_fails(self):
        """Test 4: Missing warehouse_id fails."""
        with pytest.raises(ValidationError) as exc_info:
            FeatureEvalMatch(
                feature_score=50,
                instant_book_eligible=False,
                reasoning="No warehouse id provided.",
            )
        assert "warehouse_id" in str(exc_info.value)

    def test_valid_response_with_matches_list(self):
        """Test 5: FeatureEvalResponse with valid matches list passes."""
        response = FeatureEvalResponse(
            matches=[
                FeatureEvalMatch(
                    warehouse_id="wh-001",
                    feature_score=80,
                    instant_book_eligible=True,
                    reasoning="Strong fit.",
                ),
                FeatureEvalMatch(
                    warehouse_id="wh-002",
                    feature_score=45,
                    instant_book_eligible=False,
                    reasoning="Decent location but limited dock access.",
                ),
            ]
        )
        assert len(response.matches) == 2

    def test_model_json_schema_structure(self):
        """Test 6: model_json_schema() returns dict with correct structure."""
        schema = FeatureEvalResponse.model_json_schema()
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "matches" in schema["properties"]
        # The matches field should reference FeatureEvalMatch items
        assert "$defs" in schema or "items" in schema["properties"]["matches"]


# ===================================================================
# 7-9  Gemini Client — get_model schema passing
# ===================================================================


class TestGeminiClientGetModel:
    """Tests 7-9: get_model generation_config construction."""

    @patch("wex_platform.infra.gemini_client.get_settings", return_value=_fake_settings())
    @patch("wex_platform.infra.gemini_client.genai")
    def test_json_mode_with_schema(self, mock_genai, _mock_settings):
        """Test 7: json_mode=True + response_schema includes both mime type and schema."""
        from wex_platform.infra.gemini_client import get_model

        dummy_schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
        get_model(json_mode=True, response_schema=dummy_schema)

        call_kwargs = mock_genai.GenerativeModel.call_args
        gen_config = call_kwargs.kwargs.get("generation_config") or call_kwargs[1].get("generation_config")
        assert gen_config["response_mime_type"] == "application/json"
        assert gen_config["response_schema"] == dummy_schema

    @patch("wex_platform.infra.gemini_client.get_settings", return_value=_fake_settings())
    @patch("wex_platform.infra.gemini_client.genai")
    def test_json_mode_without_schema(self, mock_genai, _mock_settings):
        """Test 8: json_mode=True without response_schema — only mime type, no schema key."""
        from wex_platform.infra.gemini_client import get_model

        get_model(json_mode=True)

        call_kwargs = mock_genai.GenerativeModel.call_args
        gen_config = call_kwargs.kwargs.get("generation_config") or call_kwargs[1].get("generation_config")
        assert gen_config["response_mime_type"] == "application/json"
        assert "response_schema" not in gen_config

    @patch("wex_platform.infra.gemini_client.get_settings", return_value=_fake_settings())
    @patch("wex_platform.infra.gemini_client.genai")
    def test_no_json_mode(self, mock_genai, _mock_settings):
        """Test 9: json_mode=False — no mime type or schema in config."""
        from wex_platform.infra.gemini_client import get_model

        get_model(json_mode=False)

        call_kwargs = mock_genai.GenerativeModel.call_args
        gen_config = call_kwargs.kwargs.get("generation_config") or call_kwargs[1].get("generation_config")
        assert "response_mime_type" not in gen_config
        assert "response_schema" not in gen_config


# ===================================================================
# 10-11  BaseAgent — generate_json schema passthrough
# ===================================================================


class TestBaseAgentSchemaPassthrough:
    """Tests 10-11: generate_json passes response_schema through to generate."""

    @pytest.mark.asyncio
    async def test_generate_json_with_schema(self):
        """Test 10: generate_json with response_schema passes it to generate."""
        agent = BaseAgent(agent_name="test_agent")
        dummy_schema = {"type": "object"}

        with patch.object(agent, "generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = AgentResult.success(data='{"a": 1}')
            await agent.generate_json(
                prompt="test",
                response_schema=dummy_schema,
            )
            mock_gen.assert_called_once_with(
                prompt="test",
                system_instruction=None,
                json_mode=True,
                response_schema=dummy_schema,
            )

    @pytest.mark.asyncio
    async def test_generate_json_without_schema(self):
        """Test 11: generate_json without response_schema passes None (backward compat)."""
        agent = BaseAgent(agent_name="test_agent")

        with patch.object(agent, "generate", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = AgentResult.success(data='{"a": 1}')
            await agent.generate_json(prompt="test")
            mock_gen.assert_called_once_with(
                prompt="test",
                system_instruction=None,
                json_mode=True,
                response_schema=None,
            )


# ===================================================================
# 12-14  ClearingAgent.evaluate_features
# ===================================================================


def _build_evaluate_features_inputs():
    """Return (buyer_need, warehouses, deterministic_scores) for evaluate_features."""
    buyer_need = {
        "use_type": "storage_only",
        "requirements": {"dock_doors": 4},
    }
    warehouses = [
        {
            "id": "wh-aaa",
            "city": "Phoenix",
            "state": "AZ",
            "truth_core": {
                "min_sqft": 5000,
                "max_sqft": 20000,
                "activity_tier": "medium",
                "clear_height_ft": 28,
                "dock_doors_receiving": 4,
                "dock_doors_shipping": 2,
                "drive_in_bays": 1,
                "has_office_space": True,
                "has_sprinkler": True,
                "parking_spaces": 20,
                "power_supply": "3-phase",
                "constraints": {},
            },
        }
    ]
    deterministic_scores = {
        "wh-aaa": {
            "location_score": 90,
            "size_score": 85,
            "budget_score": 70,
            "distance_miles": 5.2,
        }
    }
    return buyer_need, warehouses, deterministic_scores


class TestClearingAgentEvaluateFeatures:
    """Tests 12-14: ClearingAgent.evaluate_features end-to-end."""

    @pytest.mark.asyncio
    async def test_valid_llm_response(self):
        """Test 12: Valid LLM response returns validated list of dicts."""
        from wex_platform.agents.clearing_agent import ClearingAgent

        buyer_need, warehouses, det_scores = _build_evaluate_features_inputs()

        valid_payload = {
            "matches": [
                {
                    "warehouse_id": "wh-aaa",
                    "feature_score": 82,
                    "instant_book_eligible": True,
                    "reasoning": "4 dock doors match requirement. 28 ft clear height ideal for racking.",
                }
            ]
        }

        agent = ClearingAgent()
        with patch.object(
            agent,
            "generate_json",
            new_callable=AsyncMock,
            return_value=AgentResult.success(data=valid_payload),
        ):
            result = await agent.evaluate_features(buyer_need, warehouses, det_scores)

        assert result.ok is True
        assert isinstance(result.data, list)
        assert len(result.data) == 1
        assert result.data[0]["warehouse_id"] == "wh-aaa"
        assert result.data[0]["feature_score"] == 82

    @pytest.mark.asyncio
    async def test_malformed_json_returns_failure(self):
        """Test 13: LLM returning failure (malformed JSON) propagates as failure."""
        from wex_platform.agents.clearing_agent import ClearingAgent

        buyer_need, warehouses, det_scores = _build_evaluate_features_inputs()

        agent = ClearingAgent()
        with patch.object(
            agent,
            "generate_json",
            new_callable=AsyncMock,
            return_value=AgentResult.failure("JSON parse error: Expecting value"),
        ):
            result = await agent.evaluate_features(buyer_need, warehouses, det_scores)

        assert result.ok is False
        assert "JSON parse error" in result.error

    @pytest.mark.asyncio
    async def test_invalid_feature_score_returns_failure(self):
        """Test 14: LLM returning feature_score=150 caught by Pydantic validation."""
        from wex_platform.agents.clearing_agent import ClearingAgent

        buyer_need, warehouses, det_scores = _build_evaluate_features_inputs()

        invalid_payload = {
            "matches": [
                {
                    "warehouse_id": "wh-aaa",
                    "feature_score": 150,  # > 100 — violates le=100
                    "instant_book_eligible": True,
                    "reasoning": "Score too high.",
                }
            ]
        }

        agent = ClearingAgent()
        with patch.object(
            agent,
            "generate_json",
            new_callable=AsyncMock,
            return_value=AgentResult.success(data=invalid_payload),
        ):
            result = await agent.evaluate_features(buyer_need, warehouses, det_scores)

        assert result.ok is False
        assert "Validation error" in result.error

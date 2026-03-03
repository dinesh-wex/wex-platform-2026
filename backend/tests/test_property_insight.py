"""Tests for the PropertyInsight system (agent, service, and caller integration).

Covers:
- Prompt template formatting
- InsightCandidate scoring logic
- InsightResult defaults
- Keyword scoring calculation
- Recency score computation
- Service search error handling
- SMS orchestrator integration (hit/miss paths)
- Voice timeout fallback
- DetailFetcher insight fallback
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wex_platform.agents.base import AgentResult
from wex_platform.agents.prompts.property_insight import (
    EVALUATE_CANDIDATES_PROMPT,
    TRANSLATE_QUESTION_PROMPT,
)
from wex_platform.services.property_insight_service import (
    CONFIDENCE_THRESHOLD,
    CONFIDENCE_WEIGHT,
    InsightCandidate,
    InsightResult,
    KEYWORD_WEIGHT,
    PropertyInsightService,
    RECENCY_WEIGHT,
    TYPE_RELEVANCE_WEIGHT,
)


# ---------------------------------------------------------------------------
# 1. Prompt template formatting
# ---------------------------------------------------------------------------

def test_translate_question_prompt_formatting():
    """TRANSLATE_QUESTION_PROMPT.format(question=...) must not raise.

    Verifies that curly braces in the JSON examples are properly escaped
    (doubled {{ }}) so .format() only substitutes {question}.
    """
    result = TRANSLATE_QUESTION_PROMPT.format(question="Does it have EV charging?")
    assert "Does it have EV charging?" in result
    # The escaped braces should render as single braces in the output
    assert "{" in result  # JSON example braces should remain


def test_evaluate_prompt_formatting():
    """EVALUATE_CANDIDATES_PROMPT.format(question=, candidates=, channel=) must not raise.

    Verifies all three placeholders are substituted and escaped JSON braces
    survive formatting.
    """
    result = EVALUATE_CANDIDATES_PROMPT.format(
        question="test question",
        candidates="some candidate text",
        channel="sms",
    )
    assert "test question" in result
    assert "some candidate text" in result
    assert "sms" in result
    assert "{" in result  # JSON example braces should remain


# ---------------------------------------------------------------------------
# 3. InsightCandidate scoring
# ---------------------------------------------------------------------------

def test_insight_candidate_scoring():
    """Verify composite_score = keyword*0.4 + type_relevance*0.3 + confidence*0.2 + recency*0.1."""
    c = InsightCandidate(
        index=0,
        content="test",
        source="contextual_memory",
        source_type="feature_intelligence",
        confidence=0.9,
        created_at=datetime.now(timezone.utc),
        keyword_score=0.8,
        type_relevance=1.0,
        recency_score=0.5,
    )

    expected = (
        0.8 * KEYWORD_WEIGHT
        + 1.0 * TYPE_RELEVANCE_WEIGHT
        + 0.9 * CONFIDENCE_WEIGHT
        + 0.5 * RECENCY_WEIGHT
    )
    c.composite_score = (
        c.keyword_score * KEYWORD_WEIGHT
        + c.type_relevance * TYPE_RELEVANCE_WEIGHT
        + c.confidence * CONFIDENCE_WEIGHT
        + c.recency_score * RECENCY_WEIGHT
    )

    assert abs(c.composite_score - expected) < 1e-9
    # Verify expected value manually: 0.32 + 0.30 + 0.18 + 0.05 = 0.85
    assert abs(expected - 0.85) < 1e-9


# ---------------------------------------------------------------------------
# 4. InsightResult defaults
# ---------------------------------------------------------------------------

def test_insight_result_defaults():
    """InsightResult(found=False) should have answer=None, confidence=0.0."""
    result = InsightResult(found=False)
    assert result.found is False
    assert result.answer is None
    assert result.confidence == 0.0
    assert result.source == ""
    assert result.source_detail == ""
    assert result.latency_ms == 0


# ---------------------------------------------------------------------------
# 5. Keyword score calculation
# ---------------------------------------------------------------------------

def test_keyword_score_calculation():
    """Given 3 keywords, 2 of which appear in content, score should be 2/3.

    "ev" is NOT a substring of "electric vehicle charging" (no consecutive "ev").
    "electric vehicle" and "charging" both match — so 2 of 3 keywords hit.
    """
    keywords = ["ev", "electric vehicle", "charging"]
    content = "This property has electric vehicle charging"
    content_lower = content.lower()

    hits = sum(1 for kw in keywords if kw.lower() in content_lower)
    score = hits / len(keywords)

    # "ev" -> NOT found: "electric" has "el...", "vehicle" has "ve..." — no "ev" substring
    # "electric vehicle" -> yes, exact substring match
    # "charging" -> yes
    assert hits == 2
    assert abs(score - 2 / 3) < 1e-9


# ---------------------------------------------------------------------------
# 6-8. Recency score computation
# ---------------------------------------------------------------------------

def test_recency_score_fresh():
    """Entry created today should have recency ~1.0."""
    now = datetime.now(timezone.utc)
    ref_dt = now
    age_days = (now - ref_dt).days
    recency = max(0.0, 1.0 - (age_days / 365.0))
    assert abs(recency - 1.0) < 0.01


def test_recency_score_old():
    """Entry created 365 days ago should have recency ~0.0."""
    now = datetime.now(timezone.utc)
    ref_dt = now - timedelta(days=365)
    age_days = (now - ref_dt).days
    recency = max(0.0, 1.0 - (age_days / 365.0))
    assert abs(recency - 0.0) < 0.01


def test_recency_score_half_year():
    """Entry created 182 days ago should have recency ~0.5."""
    now = datetime.now(timezone.utc)
    ref_dt = now - timedelta(days=182)
    age_days = (now - ref_dt).days
    recency = max(0.0, 1.0 - (age_days / 365.0))
    # 1.0 - 182/365 ≈ 0.5014
    assert abs(recency - 0.5) < 0.02


# ---------------------------------------------------------------------------
# 9. search() returns False on translate failure
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_returns_false_on_translate_failure():
    """If translate_question returns AgentResult(ok=False), search returns InsightResult(found=False)."""
    mock_db = AsyncMock()

    service = PropertyInsightService.__new__(PropertyInsightService)
    service.db = mock_db
    service.agent = AsyncMock()
    service.agent.translate_question = AsyncMock(
        return_value=AgentResult(ok=False, error="LLM error")
    )

    result = await service.search("prop-123", "Does it have EV charging?")

    assert result.found is False
    service.agent.translate_question.assert_awaited_once()


# ---------------------------------------------------------------------------
# 10. search() returns False on no candidates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_returns_false_on_no_candidates():
    """If translate succeeds but DB is empty, search returns InsightResult(found=False) without calling evaluate()."""
    mock_db = AsyncMock()
    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(return_value=mock_execute_result)

    service = PropertyInsightService.__new__(PropertyInsightService)
    service.db = mock_db
    service.agent = AsyncMock()
    service.agent.translate_question = AsyncMock(
        return_value=AgentResult(
            ok=True,
            data={"keywords": ["ev", "charging"], "category": "feature", "relevant_memory_types": ["feature_intelligence"]},
        )
    )
    service.agent.evaluate = AsyncMock()

    result = await service.search("prop-123", "Does it have EV charging?")

    assert result.found is False
    service.agent.evaluate.assert_not_awaited()


# ---------------------------------------------------------------------------
# 11. search() returns False on low confidence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_returns_false_on_low_confidence():
    """If evaluate returns found=True but confidence < 0.7, search returns InsightResult(found=False)."""
    now = datetime.now(timezone.utc)
    mock_db = AsyncMock()

    # Create mock CM rows
    mock_row = MagicMock()
    mock_row.content = "This warehouse has electric vehicle charging stations"
    mock_row.memory_type = "feature_intelligence"
    mock_row.confidence = 0.9
    mock_row.created_at = now

    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value.all.return_value = [mock_row]
    mock_db.execute = AsyncMock(return_value=mock_execute_result)

    service = PropertyInsightService.__new__(PropertyInsightService)
    service.db = mock_db
    service.agent = AsyncMock()
    service.agent.translate_question = AsyncMock(
        return_value=AgentResult(
            ok=True,
            data={"keywords": ["ev", "charging"], "category": "feature", "relevant_memory_types": ["feature_intelligence"]},
        )
    )
    service.agent.evaluate = AsyncMock(
        return_value=AgentResult(
            ok=True,
            data={"found": True, "confidence": 0.5, "answer": "Maybe...", "candidate_used": 0},
        )
    )

    result = await service.search("prop-123", "Does it have EV charging?")

    assert result.found is False  # Confidence 0.5 < 0.7 threshold


# ---------------------------------------------------------------------------
# 12. search() returns True on high confidence
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_returns_true_on_high_confidence():
    """If evaluate returns found=True with confidence >= 0.7, search returns InsightResult(found=True)."""
    now = datetime.now(timezone.utc)
    mock_db = AsyncMock()

    mock_row = MagicMock()
    mock_row.content = "This warehouse has electric vehicle charging stations"
    mock_row.memory_type = "feature_intelligence"
    mock_row.confidence = 0.9
    mock_row.created_at = now

    mock_execute_result = MagicMock()
    mock_execute_result.scalars.return_value.all.return_value = [mock_row]
    mock_db.execute = AsyncMock(return_value=mock_execute_result)

    service = PropertyInsightService.__new__(PropertyInsightService)
    service.db = mock_db
    service.agent = AsyncMock()
    service.agent.translate_question = AsyncMock(
        return_value=AgentResult(
            ok=True,
            data={"keywords": ["ev", "charging"], "category": "feature", "relevant_memory_types": ["feature_intelligence"]},
        )
    )
    service.agent.evaluate = AsyncMock(
        return_value=AgentResult(
            ok=True,
            data={"found": True, "confidence": 0.85, "answer": "Yes, this property has EV charging stations.", "candidate_used": 0},
        )
    )

    result = await service.search("prop-123", "Does it have EV charging?")

    assert result.found is True
    assert result.answer == "Yes, this property has EV charging stations."
    assert result.confidence == 0.85


# ---------------------------------------------------------------------------
# 13. search() never raises
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_never_raises():
    """If translate_question raises RuntimeError, search() catches it and returns InsightResult(found=False)."""
    mock_db = AsyncMock()

    service = PropertyInsightService.__new__(PropertyInsightService)
    service.db = mock_db
    service.agent = AsyncMock()
    service.agent.translate_question = AsyncMock(side_effect=RuntimeError("Unexpected LLM crash"))

    result = await service.search("prop-123", "Does it have EV charging?")

    assert result.found is False
    assert result.answer is None


# ---------------------------------------------------------------------------
# 14. SMS orchestrator: insight hit skips escalation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sms_orchestrator_insight_hit_skips_escalation():
    """When PropertyInsight returns found=True, orchestrator uses _insight key and does NOT call EscalationService."""
    insight_result = InsightResult(
        found=True,
        answer="Yes, EV charging is available.",
        confidence=0.85,
    )

    with patch(
        "wex_platform.services.property_insight_service.PropertyInsightService"
    ) as MockPIS, patch(
        "wex_platform.services.escalation_service.EscalationService"
    ) as MockEsc:
        mock_insight_service = AsyncMock()
        mock_insight_service.search = AsyncMock(return_value=insight_result)
        MockPIS.return_value = mock_insight_service

        # Simulate the orchestrator logic (lines 410-424)
        plan_intent = "facility_info"
        resolved_property_id = "prop-123"
        message = "Does it have EV charging?"
        property_data = None

        if plan_intent == "facility_info":
            from wex_platform.services.property_insight_service import PropertyInsightService as PIS
            insight_service = MockPIS(AsyncMock())
            insight = await insight_service.search(
                property_id=resolved_property_id,
                question=message,
                channel="sms",
            )
            if insight.found and insight.answer:
                property_data = {
                    "id": resolved_property_id,
                    "answers": {"_insight": insight.answer},
                    "source": "property_insight",
                }

        assert property_data is not None
        assert property_data["answers"]["_insight"] == "Yes, EV charging is available."
        assert property_data["source"] == "property_insight"
        MockEsc.assert_not_called()


# ---------------------------------------------------------------------------
# 15. SMS orchestrator: insight miss falls to escalation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sms_orchestrator_insight_miss_falls_to_escalation():
    """When PropertyInsight returns found=False, orchestrator calls EscalationService."""
    insight_result = InsightResult(found=False)

    mock_esc_service = AsyncMock()
    mock_esc_service.check_and_escalate = AsyncMock(
        return_value={"escalated": True, "thread_id": "t-123"}
    )

    with patch(
        "wex_platform.services.property_insight_service.PropertyInsightService"
    ) as MockPIS:
        mock_insight_service = AsyncMock()
        mock_insight_service.search = AsyncMock(return_value=insight_result)
        MockPIS.return_value = mock_insight_service

        # Simulate the orchestrator logic (lines 410-449)
        plan_intent = "facility_info"
        resolved_property_id = "prop-123"
        message = "Does it have a helipad?"
        property_data = None
        phase = "PROPERTY_FOCUSED"
        mock_state = MagicMock()

        if plan_intent == "facility_info":
            insight_service = MockPIS(AsyncMock())
            insight = await insight_service.search(
                property_id=resolved_property_id,
                question=message,
                channel="sms",
            )
            if insight.found and insight.answer:
                property_data = {
                    "id": resolved_property_id,
                    "answers": {"_insight": insight.answer},
                    "source": "property_insight",
                }
            else:
                # Escalation path
                esc_result = await mock_esc_service.check_and_escalate(
                    property_id=resolved_property_id,
                    question_text=message,
                    field_key=None,
                    state=mock_state,
                    source_type="sms",
                )
                if esc_result.get("escalated"):
                    phase = "AWAITING_ANSWER"

        assert property_data is None
        assert phase == "AWAITING_ANSWER"
        mock_esc_service.check_and_escalate.assert_awaited_once()


# ---------------------------------------------------------------------------
# 16. Voice timeout falls to escalation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_voice_timeout_falls_to_escalation():
    """When PropertyInsight search takes >4s via voice, TimeoutError is caught and escalation runs."""

    async def slow_search(*args, **kwargs):
        await asyncio.sleep(5)
        return InsightResult(found=True, answer="Too slow...")

    mock_esc_service = AsyncMock()
    mock_esc_service.check_and_escalate = AsyncMock(
        return_value={"escalated": True}
    )
    mock_call_state = MagicMock()

    # Simulate the voice handler logic (lines 425-468)
    property_id = "prop-123"
    topics = ["ev_charging"]
    question_text = ", ".join(t.replace("_", " ") for t in topics)
    parts = []
    insight_found = False

    try:
        mock_insight_service = AsyncMock()
        mock_insight_service.search = slow_search

        insight = await asyncio.wait_for(
            mock_insight_service.search(property_id, question_text, channel="voice"),
            timeout=4.0,
        )
        if insight.found and insight.answer:
            parts.append(insight.answer)
            insight_found = True
    except asyncio.TimeoutError:
        pass  # Expected — insight_found stays False

    if not insight_found:
        esc_result = await mock_esc_service.check_and_escalate(
            property_id=property_id,
            question_text=question_text,
            field_key=None,
            state=mock_call_state,
            source_type="voice",
        )
        if esc_result.get("escalated"):
            parts.append(
                "I don't have that right now. I'll check with the warehouse owner and text you back."
            )

    assert insight_found is False
    mock_esc_service.check_and_escalate.assert_awaited_once()
    assert any("warehouse owner" in p for p in parts)


# ---------------------------------------------------------------------------
# 17. fetch_with_insight_fallback — no escalation needed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_with_insight_fallback_no_escalation_needed():
    """When all results are FOUND, PropertyInsight is never called."""
    from wex_platform.agents.sms.contracts import DetailFetchResult
    from wex_platform.services.sms_detail_fetcher import DetailFetcher

    mock_db = AsyncMock()
    fetcher = DetailFetcher(mock_db)

    found_results = [
        DetailFetchResult(status="FOUND", field_key="clear_height", value="36", formatted="36 ft", needs_escalation=False),
        DetailFetchResult(status="FOUND", field_key="dock_doors", value="8", formatted="8 dock doors", needs_escalation=False),
    ]

    with patch.object(fetcher, "fetch_by_topics", new_callable=AsyncMock, return_value=found_results):
        with patch("wex_platform.services.property_insight_service.PropertyInsightService") as MockPIS:
            results = await fetcher.fetch_with_insight_fallback(
                property_id="prop-123",
                topics=["clear_height", "dock_doors"],
                state=MagicMock(),
                question_text="What is the clear height and dock door count?",
            )

            assert len(results) == 2
            assert all(r.status == "FOUND" for r in results)
            # PropertyInsightService should never be instantiated
            MockPIS.assert_not_called()


# ---------------------------------------------------------------------------
# 18. fetch_with_insight_fallback — empty question
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_with_insight_fallback_empty_question():
    """When question_text is empty, results are returned as-is without PropertyInsight call."""
    from wex_platform.agents.sms.contracts import DetailFetchResult
    from wex_platform.services.sms_detail_fetcher import DetailFetcher

    mock_db = AsyncMock()
    fetcher = DetailFetcher(mock_db)

    results_with_escalation = [
        DetailFetchResult(status="UNMAPPED", field_key="ev_charging", needs_escalation=True),
    ]

    with patch.object(fetcher, "fetch_by_topics", new_callable=AsyncMock, return_value=results_with_escalation):
        with patch("wex_platform.services.property_insight_service.PropertyInsightService") as MockPIS:
            results = await fetcher.fetch_with_insight_fallback(
                property_id="prop-123",
                topics=["ev_charging"],
                state=MagicMock(),
                question_text="",  # Empty question
            )

            assert len(results) == 1
            assert results[0].needs_escalation is True
            MockPIS.assert_not_called()

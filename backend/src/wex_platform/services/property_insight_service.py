"""PropertyInsight Service — knowledge lookup pipeline for buyer questions.

Orchestrates a 2-LLM-call pipeline:
1. Translate the buyer question into search parameters (keywords, category,
   relevant memory types).
2. Query ContextualMemory and PropertyKnowledgeEntry tables, score and rank
   candidates.
3. Ask the LLM to evaluate the top candidates and produce a formatted answer.

This service is the entry point called by engagement routes before escalating
a question to the supplier.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.agents.property_insight_agent import PropertyInsightAgent
from wex_platform.domain.models import ContextualMemory, PropertyKnowledgeEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------
KEYWORD_WEIGHT = 0.4
TYPE_RELEVANCE_WEIGHT = 0.3
CONFIDENCE_WEIGHT = 0.2
RECENCY_WEIGHT = 0.1
CONFIDENCE_THRESHOLD = 0.7
MAX_CANDIDATES = 10


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class InsightCandidate:
    """A scored knowledge candidate from either ContextualMemory or PKE."""

    index: int
    content: str
    source: str           # "contextual_memory" | "knowledge_entry"
    source_type: str      # memory_type or PKE source
    confidence: float
    created_at: datetime
    updated_at: datetime | None = None
    keyword_score: float = 0.0
    type_relevance: float = 0.0
    recency_score: float = 0.0
    composite_score: float = 0.0


@dataclass
class InsightResult:
    """Final result of a property insight lookup."""

    found: bool
    answer: str | None = None
    confidence: float = 0.0
    source: str = ""
    source_detail: str = ""
    latency_ms: int = 0


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class PropertyInsightService:
    """Two-pass LLM knowledge lookup for buyer questions.

    Usage::

        service = PropertyInsightService(db)
        result = await service.search(property_id, "Does it have EV charging?")
        if result.found:
            send_sms(result.answer)
        else:
            escalate_to_supplier()
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.agent = PropertyInsightAgent()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(
        self,
        property_id: str,
        question: str,
        channel: str = "sms",
    ) -> InsightResult:
        """Search property knowledge for an answer to a buyer question.

        This method NEVER raises — any unhandled exception is caught,
        logged, and converted to InsightResult(found=False).

        Args:
            property_id: The property/warehouse UUID.
            question: The buyer's natural-language question.
            channel: Response format ("sms" or "voice").

        Returns:
            InsightResult with the answer if found, or found=False.
        """
        start = time.time()
        try:
            return await self._search_pipeline(property_id, question, channel, start)
        except Exception:
            logger.exception(
                "PropertyInsightService.search failed for property=%s question=%r",
                property_id,
                question,
            )
            return InsightResult(
                found=False,
                latency_ms=int((time.time() - start) * 1000),
            )

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    async def _search_pipeline(
        self,
        property_id: str,
        question: str,
        channel: str,
        start: float,
    ) -> InsightResult:
        """Core pipeline — separated for clean try/except in search()."""

        # ---- LLM Call 1: translate question ----
        translate_result = await self.agent.translate_question(question)
        if not translate_result.ok:
            logger.warning(
                "translate_question failed: %s", translate_result.error,
            )
            return InsightResult(
                found=False,
                latency_ms=int((time.time() - start) * 1000),
            )

        keywords = translate_result.data.get("keywords", [])
        category = translate_result.data.get("category", "general")
        relevant_types = translate_result.data.get("relevant_memory_types", [])

        if not keywords:
            logger.info("No keywords extracted for question=%r", question)
            return InsightResult(
                found=False,
                latency_ms=int((time.time() - start) * 1000),
            )

        # ---- DB queries ----
        memory_candidates = await self._search_contextual_memory(
            property_id, keywords, relevant_types,
        )
        pke_candidates = await self._search_knowledge_entries(
            property_id, keywords,
        )

        # ---- Merge and score ----
        all_candidates = memory_candidates + pke_candidates
        now = datetime.now(timezone.utc)

        for c in all_candidates:
            # Recency score: linearly decays over 365 days
            ref_dt = c.updated_at or c.created_at
            if ref_dt.tzinfo is None:
                ref_dt = ref_dt.replace(tzinfo=timezone.utc)
            age_days = (now - ref_dt).days
            c.recency_score = max(0.0, 1.0 - (age_days / 365.0))

            # Composite score
            c.composite_score = (
                c.keyword_score * KEYWORD_WEIGHT
                + c.type_relevance * TYPE_RELEVANCE_WEIGHT
                + c.confidence * CONFIDENCE_WEIGHT
                + c.recency_score * RECENCY_WEIGHT
            )

        # Sort descending, take top N, assign indices
        all_candidates.sort(key=lambda c: c.composite_score, reverse=True)
        top_candidates = all_candidates[:MAX_CANDIDATES]
        for i, c in enumerate(top_candidates):
            c.index = i

        if not top_candidates:
            logger.info(
                "No candidates found for property=%s question=%r",
                property_id,
                question,
            )
            return InsightResult(
                found=False,
                latency_ms=int((time.time() - start) * 1000),
            )

        # ---- LLM Call 2: evaluate candidates ----
        eval_input = [
            {
                "index": c.index,
                "content": c.content,
                "source": c.source,
                "confidence": c.confidence,
                "score": c.composite_score,
            }
            for c in top_candidates
        ]

        eval_result = await self.agent.evaluate(question, eval_input, channel=channel)
        if not eval_result.ok:
            logger.warning("evaluate failed: %s", eval_result.error)
            return InsightResult(
                found=False,
                latency_ms=int((time.time() - start) * 1000),
            )

        latency_ms = int((time.time() - start) * 1000)

        # ---- Parse evaluation ----
        data = eval_result.data
        if (
            data.get("found") is True
            and data.get("confidence", 0.0) >= CONFIDENCE_THRESHOLD
            and data.get("answer")
        ):
            candidate_idx = data.get("candidate_used")
            matched = (
                top_candidates[candidate_idx]
                if candidate_idx is not None and 0 <= candidate_idx < len(top_candidates)
                else None
            )
            return InsightResult(
                found=True,
                answer=data["answer"],
                confidence=data["confidence"],
                source=matched.source if matched else "",
                source_detail=matched.source_type if matched else "",
                latency_ms=latency_ms,
            )

        return InsightResult(found=False, latency_ms=latency_ms)

    # ------------------------------------------------------------------
    # DB search helpers
    # ------------------------------------------------------------------

    async def _search_contextual_memory(
        self,
        property_id: str,
        keywords: list[str],
        relevant_types: list[str],
    ) -> list[InsightCandidate]:
        """Query ContextualMemory and filter/score by keyword hits."""
        stmt = (
            select(ContextualMemory)
            .where(
                or_(
                    ContextualMemory.warehouse_id == property_id,
                    ContextualMemory.property_id == property_id,
                )
            )
            .order_by(
                ContextualMemory.confidence.desc(),
                ContextualMemory.created_at.desc(),
            )
            .limit(50)
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        candidates: list[InsightCandidate] = []
        for row in rows:
            content_lower = (row.content or "").lower()
            hits = sum(1 for kw in keywords if kw.lower() in content_lower)
            if hits == 0:
                continue

            candidates.append(InsightCandidate(
                index=0,
                content=row.content,
                source="contextual_memory",
                source_type=row.memory_type or "",
                confidence=row.confidence or 0.0,
                created_at=row.created_at,
                updated_at=None,
                keyword_score=hits / len(keywords),
                type_relevance=1.0 if row.memory_type in relevant_types else 0.3,
            ))

        return candidates

    async def _search_knowledge_entries(
        self,
        property_id: str,
        keywords: list[str],
    ) -> list[InsightCandidate]:
        """Query PropertyKnowledgeEntry and filter/score by keyword hits."""
        stmt = (
            select(PropertyKnowledgeEntry)
            .where(PropertyKnowledgeEntry.warehouse_id == property_id)
            .order_by(PropertyKnowledgeEntry.created_at.desc())
            .limit(50)
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        candidates: list[InsightCandidate] = []
        for row in rows:
            searchable = f"{row.question} {row.answer}".lower()
            hits = sum(1 for kw in keywords if kw.lower() in searchable)
            if hits == 0:
                continue

            candidates.append(InsightCandidate(
                index=0,
                content=f"Q: {row.question}\nA: {row.answer}",
                source="knowledge_entry",
                source_type=row.source or "",
                confidence=row.confidence or 0.0,
                created_at=row.created_at,
                updated_at=row.updated_at,
                keyword_score=hits / len(keywords),
                type_relevance=0.8,
            ))

        return candidates

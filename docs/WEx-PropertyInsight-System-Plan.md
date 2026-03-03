# PropertyInsight System — Implementation Plan

## Context

After Fix 1+2 (Cross-Channel + Universal Escalation), unmapped buyer questions now escalate to suppliers even when the answer already exists in `ContextualMemory` or `PropertyKnowledgeEntry`. Example: buyer asks "does it have EV charging?" → escalation created → but a `ContextualMemory` record says "Owner installed 4 Level 2 electric vehicle charging stations in 2025."

**Goal:** Insert a 2-LLM-call knowledge lookup layer (PropertyInsight) between topic matching and escalation. If the answer exists in knowledge stores, return it instantly — no supplier notification needed.

---

## Implementation Order (6 steps)

### Step 1: CREATE `backend/src/wex_platform/agents/prompts/property_insight.py`

Two prompt constants following existing pattern (`prompts/memory.py`):

**`TRANSLATE_QUESTION_PROMPT`** — Template with `{question}` placeholder. Instructs LLM to return JSON:
- `keywords`: 5-10 expanded search terms with synonyms (e.g., "ev" → "electric vehicle", "charging station")
- `category`: one of `"feature"`, `"compliance"`, `"operational"`, `"location"`, `"pricing"`, `"general"`
- `relevant_memory_types`: subset of `["feature_intelligence", "enrichment_response", "owner_preference", "buyer_feedback", "market_context"]`
- Use `{{` / `}}` for literal JSON braces in f-string (same as `memory.py` line 19)

**`EVALUATE_CANDIDATES_PROMPT`** — Template with `{question}`, `{candidates}`, `{channel}` placeholders. Instructs LLM to return JSON:
- `found`: bool, `answer`: string|null, `confidence`: float, `candidate_used`: int|null
- Rules: direct answers only, no fabrication, no partial combining, confidence must be >= 0.7
- Channel-aware formatting: `"Format for {channel}: voice = brief conversational, sms = concise"`

---

### Step 2: CREATE `backend/src/wex_platform/agents/property_insight_agent.py`

Extends `BaseAgent` (from `agents/base.py`). Pattern follows `memory_agent.py`.

```python
class PropertyInsightAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            agent_name="property_insight",
            model_name="gemini-3-flash-preview",
            temperature=0.2,  # Precision — wrong answers worse than no answer
        )

    async def translate_question(self, question: str) -> AgentResult:
        # format TRANSLATE_QUESTION_PROMPT with question
        # return self.generate_json(prompt=...)

    async def evaluate(self, question: str, candidates: list[dict], channel: str = "sms") -> AgentResult:
        # format EVALUATE_CANDIDATES_PROMPT with question + candidates text block + channel
        # return self.generate_json(prompt=...)
```

---

### Step 3: CREATE `backend/src/wex_platform/services/property_insight_service.py`

Deterministic DB search + full pipeline orchestration. Constructor takes `AsyncSession`.

**`InsightCandidate` dataclass** (in this file):
- `source_type`: `"contextual_memory"` | `"knowledge_entry"`
- `content`, `question` (PKE only), `answer` (PKE only), `memory_type` (CM only)
- `confidence`, `relevance_score`

**`InsightResult` dataclass** (in this file):
- `found`: bool, `answer`: str|None, `confidence`: float, `source`: str

**`PropertyInsightService` class:**
- `__init__(self, db: AsyncSession)` — stores db, creates `PropertyInsightAgent()`
- `async search(self, property_id: str, question: str, channel: str = "sms") -> InsightResult` — full pipeline:
  1. **LLM Call 1:** `agent.translate_question(question)` → keywords, relevant_memory_types, category
     - If `translate_result.ok` is False → return `InsightResult(found=False)` immediately
  2. **DB:** `_search_contextual_memory(property_id, keywords, relevant_types)` — query with `or_(CM.warehouse_id == property_id, CM.property_id == property_id)`, limit 50, filter in Python by keyword hits > 0
  3. **DB:** `_search_knowledge_entries(property_id, keywords)` — query `PKE.warehouse_id == property_id`, limit 50, filter in Python by keyword hits in `question + " " + answer`
  4. **Score:** `keyword_score * 0.4 + type_relevance * 0.3 + confidence * 0.2 + recency * 0.1`
     - Recency: `max(0, 1 - (days_old / 365))` (linear decay over 1 year)
     - Type relevance: `1.0` if `memory_type` in `relevant_types`, else `0.3`; PKE gets base `0.8`
  5. Sort descending, take top 10
  6. If no candidates after filtering → return `InsightResult(found=False)` (skip LLM Call 2)
  7. **LLM Call 2:** `agent.evaluate(question, top_candidates, channel=channel)` → found/answer/confidence
     - If `eval_result.ok` is False → return `InsightResult(found=False)` immediately
  8. If `found=True` and `confidence >= 0.7` → return `InsightResult(found=True, answer=...)`
  9. Else → return `InsightResult(found=False)`

**Error contract:** `search()` never raises. All internal failures (LLM errors, DB errors, unexpected exceptions) are caught and return `InsightResult(found=False)`. Wrap the full body in `try/except Exception` as a safety net with `logger.exception()`.

**Key:** Keyword filtering in Python (not SQL LIKE) because 5-10 keywords would produce unwieldy queries. Properties typically have <30 memories each.

---

### Step 4: MODIFY `backend/src/wex_platform/services/sms_detail_fetcher.py`

Add `fetch_with_insight_fallback()` method after `fetch_by_topics` (line 93):

```python
async def fetch_with_insight_fallback(
    self, property_id: str, topics: list[str], state,
    question_text: str,  # Required — no default to prevent empty-string bugs
    channel: str = "sms",
) -> list[DetailFetchResult]:
```

Pipeline:
1. Call `self.fetch_by_topics(property_id, topics, state)` → results
2. Guard: `if not question_text:` → return results as-is (skip insight)
3. Check if any result has `needs_escalation=True`
4. If yes → lazy-import `PropertyInsightService`, call `.search(property_id, question_text, channel=channel)`
5. If insight found → replace UNMAPPED results: `status="FOUND"`, `source="property_insight"`, `formatted=insight.answer`, `needs_escalation=False`
6. Return merged results

---

### Step 5: MODIFY `backend/src/wex_platform/services/buyer_sms_orchestrator.py`

**Target:** `if plan.intent == "facility_info":` block (lines 409-432).

Insert PropertyInsight before `EscalationService.check_and_escalate()`:

```python
if plan.intent == "facility_info":
    # 1. Try PropertyInsight first
    insight = await PropertyInsightService(self.db).search(resolved_property_id, message, channel="sms")
    if insight.found and insight.answer:
        property_data = {"id": resolved_property_id,
                         "answers": {"_insight": insight.answer},
                         "source": "property_insight"}
    else:
        # 2. Fall through to existing escalation code (unchanged)
        esc_result = await EscalationService(self.db).check_and_escalate(...)
        ... (existing 3-branch handling stays identical)
```

Also change the mapped-topics `fetch_by_topics` call (~line 363) to `fetch_with_insight_fallback` to catch mapped-but-NULL fields:

```python
fetch_results = await detail_fetcher.fetch_with_insight_fallback(
    property_id=resolved_property_id, topics=topics_to_fetch,
    state=state, question_text=message,
)
```

---

### Step 6: MODIFY `backend/src/wex_platform/services/voice_tool_handlers.py`

**A)** Add `import asyncio` to file imports (not currently imported).

**B)** In unmapped topics block (`if not fetch_results and topics:`, lines 424-446), insert PropertyInsight with 4-second timeout before escalation:

```python
if not fetch_results and topics:
    question_text = ', '.join(t.replace('_', ' ') for t in topics)

    # Try PropertyInsight first (4-second timeout for voice)
    insight_found = False
    try:
        insight = await asyncio.wait_for(
            PropertyInsightService(self.db).search(property_id, question_text, channel="voice"),
            timeout=4.0,
        )
        if insight.found and insight.answer:
            parts.append(insight.answer)
            insight_found = True
    except asyncio.TimeoutError:
        logger.warning("PropertyInsight timed out for voice, falling through to escalation")
    except Exception:
        logger.exception("PropertyInsight error")

    if not insight_found:
        # Existing escalation code (unchanged)
        esc_result = await EscalationService(self.db).check_and_escalate(...)
        ... (existing 3-branch handling stays identical)
```

---

## Files Summary

| # | Action | File | Key Change |
|---|--------|------|------------|
| 1 | CREATE | `agents/prompts/property_insight.py` | `TRANSLATE_QUESTION_PROMPT` + `EVALUATE_CANDIDATES_PROMPT` |
| 2 | CREATE | `agents/property_insight_agent.py` | `PropertyInsightAgent` with `translate_question()` + `evaluate()` |
| 3 | CREATE | `services/property_insight_service.py` | `InsightCandidate`, `InsightResult`, `PropertyInsightService.search()` |
| 4 | MODIFY | `services/sms_detail_fetcher.py` | Add `fetch_with_insight_fallback()` for mapped-but-NULL fields |
| 5 | MODIFY | `services/buyer_sms_orchestrator.py` | PropertyInsight before escalation + use `fetch_with_insight_fallback` |
| 6 | MODIFY | `services/voice_tool_handlers.py` | PropertyInsight with 4s `asyncio.wait_for` before escalation |

**Schema changes:** None. Uses existing `ContextualMemory` and `PropertyKnowledgeEntry` tables.

---

## Key Design Decisions

- **Single integration point:** `PropertyInsightService.search()` orchestrates the full pipeline (translate → DB search → evaluate). Callers make one call, not three.
- **Error contract:** `search()` never raises. All failures return `InsightResult(found=False)` with logging. Callers don't need error handling.
- **Keyword filtering in Python:** Fetch up to 50 rows per table ordered by confidence, then filter by keyword hits in Python. Simpler and fast enough for typical property memory counts (<30).
- **Voice 4s timeout:** Two Gemini Flash calls typically complete in 1.5-2.5s total. If exceeded, `asyncio.TimeoutError` is caught and escalation proceeds normally.
- **Channel-aware formatting:** `channel` parameter threaded from caller → `search()` → `evaluate()` → prompt template. Voice gets conversational answers, SMS gets concise.
- **`question_text` required:** No default value on `fetch_with_insight_fallback()` plus guard clause prevents empty-string bugs.
- **Lazy imports:** `PropertyInsightService` imported inside functions (same circular-import avoidance pattern as `EscalationService` throughout codebase).
- **`_insight` answer key:** Works because `response_agent.py` iterates `answers.items()` generically with no whitelist.

---

## Verification

1. **Translate quality:** `translate_question("does it have EV charging?")` → keywords include "electric vehicle", "ev", "charging"; memory_types include "feature_intelligence"
2. **Search accuracy:** Seed `ContextualMemory` with "Owner installed 4 Level 2 electric vehicle charging stations". Search with ["ev", "electric vehicle", "charging"] → candidate found with high score
3. **Evaluate precision:** Pass EV charging candidate + dock doors question → `found=False`. Pass EV candidate + EV question → `found=True`, confidence >= 0.7
4. **E2E SMS (hit):** Unmapped question + relevant ContextualMemory → PropertyInsight returns answer, no escalation created
5. **E2E SMS (miss):** Unmapped question + no relevant memories → PropertyInsight returns None, escalation IS created
6. **Voice timeout:** Mock PropertyInsight to take 5s → escalation created, buyer gets "I'll check with the warehouse owner"
7. **Regression:** Mapped topics (dock_doors, clear_height) still go through typed field lookup path

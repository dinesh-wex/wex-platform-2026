# Cross-Channel Buyer Journey Unification — Implementation Plan

## Context

WEx has 3 buyer channels (Web, SMS, Voice) operating in isolation. Two problems:

1. **Unmapped questions silently drop** — Buyer asks "do you have EV charging?" via SMS or voice. `detect_topics()` returns `[]` (no topic catalog entry). SMS falls through to `_stub_lookup()`, voice returns generic "I don't have that." No escalation is created. Promise to follow up is hollow.

2. **Voice starts from scratch** — Buyer texts, qualifies, sees 3 options, then calls. Voice agent has no awareness of their criteria, presented options, or pending escalations. Re-asks everything. Breaks trust.

Fix 2 (Universal Escalation) is implemented first — it lays the cross-channel dedup foundation that Fix 1's VoiceCallState seeding depends on.

---

## Fix 2: Universal Escalation

No schema changes needed. `EscalationThread.field_key` is already `nullable=True`. `EscalationThread.source_type` already exists as `String(20)`, default=`"sms"`.

### File 1: `services/escalation_service.py`

**A)** Add `source_type: str = "sms"` param to `check_and_escalate()` (line 23) and `_create_thread()` (line 145).
- Propagate `source_type` into the `EscalationThread(...)` constructor in `_create_thread()` (line 153). Currently relies on column default; make it explicit.

**B)** Add `_find_existing_thread_cross_channel(property_id, field_key, question_text)` method (insert after existing `_find_existing_thread` at line ~143).
- Query `EscalationThread` by `property_id` only (no `conversation_state_id` filter) — this is what enables cross-channel lookup.
- If `field_key` is provided: filter by `field_key`. Return first match.
- If `field_key=None`: fetch last 20 threads for property, loop with `_questions_match()` to find semantic match.
- Returns `EscalationThread | None`.

**C)** Add Layer 4 to `check_and_escalate()` — insert between current Layer 3 (line 55) and `_create_thread()` call (line 57):

```python
# Layer 4: Cross-channel dedup
cross = await self._find_existing_thread_cross_channel(property_id, field_key, question_text)
if cross:
    if cross.status == "answered" and cross.answer_sent_text:
        return {"escalated": False, "answer": cross.answer_sent_text}
    elif cross.status == "pending":
        return {"escalated": False, "answer": None, "thread_id": cross.id, "waiting": True}
```

**D)** Update `_create_thread()` call (line ~57) to pass `source_type=source_type`.

### File 2: `services/buyer_sms_orchestrator.py`

Target: empty-topics `else` branch (lines 401-403).

Current: `property_data = self._stub_lookup(resolved_property_id, presented_match_summaries)` — no escalation.

Replace `else` block with:

```python
else:
    if plan.intent == "facility_info":
        # Unmapped facility question -> escalate instead of silent drop
        esc_result = await EscalationService(self.db).check_and_escalate(
            property_id=resolved_property_id,
            question_text=message,
            field_key=None,
            state=state,
            source_type="sms",
        )
        if esc_result.get("escalated"):
            phase = "AWAITING_ANSWER"
        elif esc_result.get("answer"):
            property_data = {"id": resolved_property_id,
                             "answers": {"_unmapped": esc_result["answer"]},
                             "source": "escalation_cache"}
        elif esc_result.get("waiting"):
            property_data = {"id": resolved_property_id,
                             "answers": {"_unmapped": "We're still checking on that with the warehouse owner."},
                             "source": "escalation_pending"}
    else:
        property_data = self._stub_lookup(resolved_property_id, presented_match_summaries)
```

**Why `_unmapped` key works:** `response_agent.py` (lines 84-95) iterates `answers.items()` generically — any key is formatted as `"{key}: {value}"` and passed to the LLM as CACHED ANSWERS context. No whitelist.

**Why `plan.intent == "facility_info"` guard:** Confirmed real value in `criteria_agent.py` (line 34) — "asking about a specific facility detail". Prevents general "tell me about option 1" from incorrectly triggering escalation.

### File 3: `services/voice_tool_handlers.py` (Fix 2 portion)

**A)** Update existing `check_and_escalate` call (lines 331-336) — add `source_type="voice"`.

**B)** Add unmapped-topics escalation block for the case where `topics` was provided but all are unmapped (`fetch_by_topics` returns empty list). Insert after the `needs_escalation_results` loop, before the `if not parts:` guard:

```python
# Handle fully unmapped topics (provided but not in topic_catalog)
if not fetch_results and topics:
    # Normalize topic names for _questions_match() cross-channel lookup.
    # Use clean readable text ("ev charging") not raw slugs ("ev_charging")
    # so the substring match finds SMS escalations like "does it have ev charging?"
    question_text = ', '.join(t.replace('_', ' ') for t in topics)
    esc_result = await EscalationService(self.db).check_and_escalate(
        property_id=property_id,
        question_text=question_text,
        field_key=None,
        state=self.call_state,
        source_type="voice",
    )
    if esc_result.get("answer"):
        parts.append(esc_result["answer"])
    elif esc_result.get("waiting"):
        parts.append("We're still checking on that with the warehouse owner. Should hear back soon.")
    elif esc_result.get("escalated"):
        parts.append("I don't have that right now. I'll check with the warehouse owner and text you back.")
```

**Why clean topic names matter for cross-channel matching:** `_questions_match()` does normalized substring containment. If SMS has `"does it have ev charging?"` and voice sends `"ev_charging"`, the underscore breaks the match. With `"ev charging"`, `_questions_match("ev charging", "does it have ev charging?")` → True via substring containment.

**C)** Also add `waiting` handling to the existing escalation loop (for mapped-but-missing fields) — currently handles `answer` and `escalated` but not `waiting`. Add `elif esc_result.get("waiting"): parts.append("We're still checking on that...")`.

**Note:** The no-topics branch (lines 279-296 — buyer says "tell me about option 1" with no topics) stays unchanged. That's general browsing, not an unmapped question.

---

## Fix 1: Cross-Channel Continuity

No schema changes needed. `VoiceCallState` already has `buyer_id`, `conversation_id`, `buyer_need_id`, `known_answers`, `answered_questions`, `presented_match_ids`, `match_summaries`. `EscalationThread.conversation_state_id` is a plain `String(36)` (no FK constraint) so `VoiceCallState.id` values store safely.

### File 4: `app/routes/vapi_webhook.py`

**A)** Add import: `from wex_platform.domain.sms_models import SMSConversationState`

**B)** In `_handle_assistant_request()` (lines 68-109), after buyer lookup by phone (line 88), add SMS state lookup:

The query uses a 30-day freshness window instead of a phase filter because there are no explicit terminal phases (e.g., no `ABANDONED`/`DORMANT` in the phase enum). A buyer who completed a booking 6 months ago and calls fresh should not receive stale context.

```python
from datetime import timedelta

sms_context = None
FRESHNESS_DAYS = 30  # Ignore SMS states older than this
if caller_phone:
    sms_result = await db.execute(
        select(SMSConversationState)
        .where(
            SMSConversationState.phone == caller_phone,
            SMSConversationState.opted_out == False,
            SMSConversationState.updated_at >= datetime.now(timezone.utc) - timedelta(days=FRESHNESS_DAYS),
        )
        .order_by(SMSConversationState.updated_at.desc())
        .limit(1)
    )
    sms_state = sms_result.scalar_one_or_none()
    if sms_state:
        sms_context = {
            "phase": sms_state.phase,
            "criteria_snapshot": sms_state.criteria_snapshot or {},
            "presented_match_ids": sms_state.presented_match_ids or [],
            "focused_match_id": sms_state.focused_match_id,
            "renter_first_name": sms_state.renter_first_name,
            "known_answers": sms_state.known_answers or {},
            "answered_questions": sms_state.answered_questions or [],
            "buyer_need_id": sms_state.buyer_need_id,
            "conversation_id": sms_state.conversation_id,
            "sms_state_id": sms_state.id,
        }
        # Prefer SMS-captured name (more verified than Buyer.name)
        if sms_state.renter_first_name:
            buyer_name = sms_state.renter_first_name
```

**C)** After creating `VoiceCallState` object (line ~95), before `db.add`, seed from SMS:

```python
if sms_context:
    call_state.buyer_id = buyer_id
    call_state.conversation_id = sms_context["conversation_id"]
    call_state.buyer_need_id = sms_context["buyer_need_id"]
    call_state.known_answers = sms_context["known_answers"]
    call_state.answered_questions = sms_context["answered_questions"]
    call_state.presented_match_ids = sms_context["presented_match_ids"]
    call_state.buyer_name = buyer_name
    sms_summaries = sms_context["criteria_snapshot"].get("match_summaries")
    if sms_summaries:
        call_state.match_summaries = _build_voice_summaries_from_sms(sms_summaries)
```

**D)** Update `build_assistant_config` call to pass `sms_context=sms_context`.

**E)** Add `_build_voice_summaries_from_sms(sms_summaries)` helper at bottom of file:
- Converts SMS `{id, city, state, rate, monthly, match_score, description}` → voice `{id, city, state, rate, monthly, score, features: [], instant_book: False}`
- Caps at 3 entries (voice tool only shows 3 max)
- `features: []` is intentional — forces `lookup_property_details` to fetch fresh from DetailFetcher

### File 5: `services/vapi_assistant_config.py`

**A)** Update `build_assistant_config()` signature to add `sms_context: dict | None = None`.

**B)** Replace first message logic (lines 27-30) with 3-tier SMS-aware greeting:
- **Tier 1** — has `presented_match_ids`: *"Hey {name}, I can see we've been texting about warehouse space. I have those {N} options pulled up — want to go over them?"*
- **Tier 2** — has `criteria_snapshot` but no matches: *"Hey {name}, I can see we were chatting about space in {city}. Want to pick up where we left off?"*
- **Tier 3** — no SMS context (fallback = current behavior): generic WEx greeting

**C)** Update `_build_system_prompt()` call at line 38 to pass `sms_context`, and update its signature to `def _build_system_prompt(sms_context: dict | None = None) -> str:`. Change final return to: `return base_prompt + _build_sms_context_section(sms_context)`.

**D)** Add `_build_sms_context_section(sms_context)` helper (insert before `_build_tool_definitions` at line 135). Generates dynamic section with:
- Prior criteria summary (location, sqft, use_type, timing, duration)
- How many properties were presented, which was focused
- Phase description in plain English (e.g., `"AWAITING_ANSWER"` → "waiting for supplier to answer a question")
- Instructions: "Don't re-ask answered questions", "use `search_properties` only if criteria change"

### File 3 (revisited): `services/voice_tool_handlers.py` (Fix 1 portion)

In `search_properties()` (line ~92), before creating BuyerNeed:

Check if `call_state.buyer_need_id` is set (seeded from SMS). If yes, load it from DB. Match is valid if city matches AND the new sqft falls within the existing BuyerNeed's stored range:

```python
city_match = (existing_need.city or "").lower() == city.lower()
sqft_in_range = (
    existing_need.min_sqft is not None
    and existing_need.max_sqft is not None
    and existing_need.min_sqft <= sqft <= existing_need.max_sqft
)
reuse_existing = city_match and sqft_in_range
```

This uses the BuyerNeed's existing ±20% band (`min_sqft = 0.8x`, `max_sqft = 1.2x`) rather than a separate tolerance calculation — tighter and more consistent.

If `reuse_existing=True` AND `call_state.match_summaries` is non-empty: Skip ClearingEngine. Format cached summaries as voice response (*"Based on what we found for you earlier, I have N options..."*). Return immediately.

**Channel independence note:** `VoiceCallState` is seeded from SMS state once at call start and then updated independently for the duration of the call. `SMSConversationState` is never written to by any voice handler — each channel owns its own mutable state. If the buyer gives different criteria on the call (different city, different sqft), a new `BuyerNeed` is created for the voice channel only. The SMS state remains unchanged. Add a comment in the code to make this explicit.

---

## Files Modified (5)

| File | Fix | Key Change |
|------|-----|------------|
| `services/escalation_service.py` | Fix 2 | `source_type` param, Layer 4 cross-channel method |
| `services/buyer_sms_orchestrator.py` | Fix 2 | Empty-topics → escalation instead of silent stub |
| `services/voice_tool_handlers.py` | Fix 1+2 | Unmapped escalation with `source_type="voice"`, BuyerNeed reuse |
| `app/routes/vapi_webhook.py` | Fix 1 | SMS state lookup, VoiceCallState seeding, summary helper |
| `services/vapi_assistant_config.py` | Fix 1 | Dynamic prompt + SMS-aware first message |

**New files:** None. **Schema changes:** None.

---

## Implementation Order

1. `escalation_service.py` — Foundation. All other changes depend on the new Layer 4 and `source_type`.
2. `buyer_sms_orchestrator.py` — Fix 2 SMS path.
3. `voice_tool_handlers.py` (Fix 2 only) — Add `source_type="voice"` + unmapped escalation block.
4. `vapi_assistant_config.py` — Fix 1 prompt/first-message changes (can be written without running).
5. `vapi_webhook.py` — Fix 1 wire-up: SMS lookup + VoiceCallState seeding + pass `sms_context` to config builder.
6. `voice_tool_handlers.py` (Fix 1) — BuyerNeed reuse + `match_summaries` cache shortcut.

---

## Verification

### Fix 2
- **SMS:** Send "does option 1 have EV charging?" where `"ev_charging"` is not in `topic_catalog`. Assert `EscalationThread` is created with `field_key=None`, `source_type="sms"`, phase → `AWAITING_ANSWER`.
- **Cross-channel:** SMS escalation created → call `check_and_escalate` with `source_type="voice"` for same property + similar question. Assert Layer 4 returns the same thread (no duplicate created).
- **Cache hit:** Mark thread as answered with `answer_sent_text`. Call `check_and_escalate` from voice. Assert cached answer returned immediately.

### Fix 1
- **With SMS history:** Mock `SMSConversationState` with criteria + 2 presented matches. Assert `VoiceCallState.buyer_need_id`, `presented_match_ids`, `known_answers` are seeded. Assert first message contains "I have those 2 options pulled up". Assert system prompt includes "Prior criteria collected via SMS".
- **Without SMS history:** Call with phone that has no SMS record. Assert behavior identical to today (no errors, generic greeting).
- **BuyerNeed reuse:** `call_state.buyer_need_id` set + same city/sqft criteria → no new `BuyerNeed` created, no ClearingEngine run, existing match summaries returned.

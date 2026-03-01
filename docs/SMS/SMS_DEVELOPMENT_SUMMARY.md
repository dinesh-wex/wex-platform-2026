# WEx SMS Buyer Journey — Development Summary

> Comprehensive documentation of the SMS communications system built for the WEx Platform (Feb 2026).
> This system replaces the original `wex-leasing-service-python` SMS pipeline with a fully integrated FastAPI-native implementation.

---

## Architecture Overview

The SMS buyer journey is a **6-agent pipeline** that handles the complete lifecycle from first text through tour confirmation. It is built directly into the WEx Platform backend (`backend/src/wex_platform/`), not as a separate service.

```
Inbound SMS (Aircall webhook)
  │
  ▼
┌─────────────────────────────────────────────────────────────┐
│  BuyerSMSOrchestrator (buyer_sms_orchestrator.py)           │
│                                                              │
│  1. Gatekeeper (inbound validation)                         │
│  2. Message Interpreter (deterministic regex extraction)     │
│  3. Property Reference Resolution                            │
│  4. Criteria Agent (LLM — intent + action plan)             │
│  5. Tool Execution (ClearingEngine search, detail lookup)    │
│  6. Response Agent (LLM — SMS reply generation)              │
│  7. Gatekeeper → Polisher retry loop (max 3) → fallback     │
│  8. State update + SMS send via Aircall                      │
└─────────────────────────────────────────────────────────────┘
  │
  ▼
Outbound SMS (Aircall API)
```

### Key Differences from wex-leasing-service-python

| Aspect | Old (wex-leasing) | New (WEx Platform) |
|--------|--------------------|--------------------|
| Runtime | Standalone Python service | Integrated FastAPI backend |
| Database | Firestore | SQLAlchemy async (SQLite dev / PostgreSQL prod) |
| LLM Client | Custom `LLMClient` | `BaseAgent` with Gemini 3 Flash Preview |
| State | Firestore documents | `SMSConversationState` SQLAlchemy model |
| Property Data | WEX API calls | Direct PropertyKnowledge/PropertyListing queries |
| SMS Transport | Direct Twilio/Aircall | `SMSService` wrapper around Aircall API |
| Caching | Two-layer (memory + Firestore) | `known_answers` JSON field on state |

---

## File Layout

### Agent Pipeline (`backend/src/wex_platform/agents/sms/`)

| File | Type | Purpose |
|------|------|---------|
| `contracts.py` | Dataclasses | `MessageInterpretation`, `CriteriaPlan`, `DetailFetchResult`, `GatekeeperResult` — typed I/O for every agent |
| `message_interpreter.py` | Deterministic | Regex extraction: cities, states, sqft, topics, features, emails, dates, action keywords, positional references, names |
| `topic_catalog.py` | Deterministic | `TOPIC_TO_FIELD_KEYS` mapping to PropertyKnowledge columns |
| `field_catalog.py` | Deterministic | Field definitions with `column_name`, `table`, `format_fn`, `label` |
| `criteria_agent.py` | LLM (Gemini) | Intent classification + action planning. Intents: new_search, refine_search, facility_info, tour_request, commitment, provide_info, greeting, unknown |
| `response_agent.py` | LLM (Gemini) | Contextual SMS reply generation. Phase-aware, with broker tone guidelines |
| `gatekeeper.py` | Deterministic | Outbound/inbound validation: length limits, garbage detection, PII leak check, profanity filter, context-specific checks |
| `polisher_agent.py` | LLM (Gemini) | Fixes tone/length issues on gatekeeper rejection. Temperature=0.3. Never adds content, only compresses/fixes |
| `context_builder.py` | Utility | Builds context strings for each agent. Phase-specific prompt injection. Match summaries with reasoning/description |
| `fallback_templates.py` | Deterministic | Templates for all intents, used after 3 gatekeeper failures |

### Services (`backend/src/wex_platform/services/`)

| File | Purpose |
|------|---------|
| `buyer_sms_orchestrator.py` | **Main pipeline coordinator** — 8-stage flow, phase transitions, name capture → link flow, COLLECTING_INFO guard |
| `sms_service.py` | Aircall API wrapper. `send_buyer_sms()`, opt-out check, quiet hours |
| `sms_detail_fetcher.py` | Cache-first property info lookup via PropertyKnowledge/PropertyListing |
| `sms_token_service.py` | Guarantee token create/validate/redeem (48h expiry) |
| `sms_scheduler.py` | Background runner for stale conversations, SLA checks, queued messages |
| `clearing_engine.py` | Property matching engine (shared with web) — called by orchestrator for `action=search` |

### Routes (`backend/src/wex_platform/app/routes/`)

| File | Purpose |
|------|---------|
| `buyer_sms.py` | `POST /api/sms/buyer/webhook` — Aircall webhook, TCPA (STOP/HELP/START), self-loop prevention, supplier-phone detection |
| `sms.py` | Supplier-side SMS routes (existing) |
| `sms_guarantee.py` | `GET/POST /sms/guarantee/{token}` — Mobile signing page |
| `sms_reply_tool.py` | `GET/POST /api/sms/internal/reply/{thread_id}` — Ops reply to escalations |
| `sms_optin.py` | SMS opt-in routes |
| `sms_scheduler.py` | `POST /api/internal/scheduler/sms-tick` — Cron endpoint for Cloud Scheduler |

### Domain (`backend/src/wex_platform/domain/`)

| File | Purpose |
|------|---------|
| `sms_models.py` | `SMSConversationState`, `EscalationThread`, `SmsSignupToken` |
| `sms_enums.py` | `SMSPhase` enum (13 phases) |

---

## State Machine — SMSPhase

```
INTAKE → QUALIFYING → PRESENTING → PROPERTY_FOCUSED → COLLECTING_INFO → COMMITMENT
                                         │                                    │
                                         ▼                                    ▼
                                   AWAITING_ANSWER              GUARANTEE_PENDING
                                         │                            │
                                         ▼                            ▼
                                   (back to PROPERTY_FOCUSED)   TOUR_SCHEDULING
                                                                      │
                                                                      ▼
                                                                   ACTIVE → COMPLETED

Any phase → DORMANT (after max re-engagement nudges)
Any phase → ABANDONED (STOP keyword, 30-day inactivity, or 7 days after final DORMANT nudge)
```

### Phase Descriptions

| Phase | Trigger | What Happens |
|-------|---------|-------------|
| INTAKE | First message | Greeting, opt-in line appended |
| QUALIFYING | Criteria provided but incomplete | Ask for missing criteria (location + sqft + use_type needed) |
| PRESENTING | `criteria_readiness >= 0.6` + matches found | ClearingEngine runs, matches presented |
| PROPERTY_FOCUSED | Buyer selects a specific match | Detail questions answered from PropertyKnowledge |
| AWAITING_ANSWER | Unanswerable question escalated | EscalationThread created, 2h SLA, buyer told "I'll check on that" |
| COLLECTING_INFO | Commitment flow started | Collect name → email for Engagement creation |
| COMMITMENT | Info collected | Engagement created, guarantee link generated |
| GUARANTEE_PENDING | Link sent, awaiting signing | Nudges at 30min + 4h |
| TOUR_SCHEDULING | Guarantee signed | Address revealed, date/time extraction |
| ACTIVE | Tour confirmed | Ongoing communication |
| COMPLETED | Journey finished | Terminal |
| DORMANT | Max re-engagement nudges exhausted | One final 7-day nudge |
| ABANDONED | STOP, 30-day inactivity, or post-DORMANT timeout | Terminal, no further messages |

---

## SMSConversationState — Key Fields

```python
# Identity
buyer_id, conversation_id, buyer_need_id, phone

# State machine
phase: SMSPhase          # Current phase
turn: int                # Message count
criteria_readiness: float  # 0.0-1.0 (threshold 0.6 triggers search)
criteria_snapshot: JSON   # {location, sqft, use_type, timing, duration, ...}

# Property context
focused_match_id: str     # Currently focused property
presented_match_ids: JSON  # Array of property IDs shown to buyer
search_session_token: str  # Token for frontend search results page

# Buyer info
renter_first_name, renter_last_name, buyer_email
name_status: str          # "unknown", "requested", "captured"
name_requested_at_turn: int  # For one-shot name→link trigger

# Engagement bridge
engagement_id, guarantee_link_token, guarantee_signed_at

# Knowledge cache
known_answers: JSON       # {property_id: {field_key: answer}}
answered_questions: JSON  # Previously answered Q&A
pending_escalations: JSON

# Re-engagement
last_buyer_message_at, last_system_message_at
reengagement_count, next_reengagement_at
stall_nudge_counts: JSON  # Per-phase nudge counters

# TCPA
opted_out: bool, opted_out_at
```

---

## Agent Details

### 1. Message Interpreter (Deterministic)

Regex-based extraction, no LLM. Outputs `MessageInterpretation`:
- **Cities**: Known US city patterns + state abbreviations
- **Sqft**: Parses "10k sqft", "10,000 sf", "10000 square feet" → `10000`
- **Topics**: Mapped via `topic_catalog.py` to PropertyKnowledge field keys
- **Positional refs**: "option 2", "#1", "the first one" → `["2"]`, `["1"]`, `["1"]`
- **Action keywords**: "book it", "schedule tour", "I want that one"
- **Names/emails**: Basic extraction

**Boundary**: Interpreter outputs raw `positional_references` — it does NOT resolve to a property ID. Resolution happens in the orchestrator via `presented_match_ids[int(ref) - 1]`.

### 2. Criteria Agent (LLM)

Model: `gemini-3-flash-preview`, Temperature: 0.2

Input: message + MessageInterpretation + conversation history + phase + existing criteria + resolved property ref + presented matches

Output: `CriteriaPlan` JSON:
```json
{
  "intent": "new_search|refine_search|facility_info|tour_request|commitment|provide_info|greeting|unknown",
  "action": "search|lookup|schedule_tour|commitment_handoff|collect_info|null",
  "criteria": {"location": "...", "sqft": 10000, "use_type": "storage", ...},
  "extracted_name": {"first_name": "John", "last_name": "Smith"},
  "response_hint": "...",
  "confidence": 0.85
}
```

**Criteria readiness formula**: `location=0.4 + sqft=0.3 + use_type=0.2 + extras=0.1 each`. Threshold `0.6` triggers ClearingEngine search.

### 3. Response Agent (LLM)

Model: `gemini-3-flash-preview`, Temperature: 0.7

Generates contextual SMS replies with these enforced rules:
- **Terminology**: WAREHOUSE LEASING only. Never "stay", "book a stay", "accommodation". Use "lease", "term", "space", "rent".
- **Tone**: Professional but warm, like texting a professional contact. No emojis. Never reveal AI.
- **No em-dashes**: Uses commas, periods, or rephrase instead.
- **Information rules**: Only state facts from provided data. Never invent details. No full addresses (city/area only until tour booked). Never mention building total size or available sqft.
- **Never push**: Do NOT proactively push for tours, bookings, or commitments. Let buyer decide.
- **Links**: Only include a URL if the response hint explicitly provides one.
- **Length limits**: First message or messages with links = 800 chars. Follow-up = 480 chars.

**Deterministic fast-path**: `intent == "greeting"` returns hardcoded response without LLM call.

### 4. Gatekeeper (Deterministic)

Validates both inbound and outbound SMS:

**Outbound checks**:
- Length: 800 (first message or URL present), 480 (follow-up), min 20
- Garbage: 40+ repeated chars, letter ratio < 0.40, word repetition > 5
- PII: Multiple phone numbers or emails blocked
- Profanity: Exact word match from blocklist
- Context: Commitment must have link, tour must have scheduling language

**Inbound checks**: Empty, length > 1600, profanity

### 5. Polisher Agent (LLM)

Model: `gemini-3-flash-preview`, Temperature: 0.3

Activated when Gatekeeper rejects Response Agent output. Fixes:
- Messages that are too long (compresses)
- Tone issues
- Typos and grammar

**Never bypassed** — always runs in the gatekeeper retry loop. The pipeline is: Response Agent → Gatekeeper → (if rejected) Polisher → Gatekeeper → (if rejected) Polisher → Gatekeeper → (if rejected) fallback template.

### 6. Fallback Templates (Deterministic)

Used after 3 consecutive gatekeeper failures. Has templates for every intent:
- greeting, search_started, matches_found, clarify_location, clarify_sqft, facility_info_ack, tour_request_ack, commitment_ack, unknown, etc.

---

## Key Orchestrator Flows

### Name Capture → Search Link (One-Shot)

When buyer provides their name during PRESENTING phase:

1. Criteria Agent detects `action=collect_info` with `extracted_name`
2. **Phase guard**: If in PRESENTING or QUALIFYING, do NOT enter COLLECTING_INFO (prevents email collection push)
3. Name stored on state, `name_requested_at_turn` recorded
4. **One-shot trigger**: On exact next turn (`turn == name_requested_at_turn + 1`):
   - Build search link: `{FRONTEND_URL}/buyer/options?session={search_session_token}`
   - Get best match (first from `presented_match_ids`) with reasoning + description from ClearingEngine
   - Pass raw data in `response_hint` — let Response Agent paraphrase naturally
   - Normal pipeline (Response Agent → Gatekeeper → Polisher) handles tone + length at 800 chars

### Property Reference Resolution

Orchestrator resolves buyer references before Criteria Agent sees them:
- **Positional**: "option 2" → `presented_match_ids[1]`
- **City match**: "the one in Commerce" → match by city
- **Attribute match**: "the cheapest one" → sort by rate
- **Ambiguous** → returns None, Criteria Agent asks for clarification

### Gatekeeper → Polisher Retry Loop

```python
for attempt in range(3):
    result = gatekeeper.validate_outbound(text, is_first, context)
    if result.ok:
        break
    text = polisher.polish(text, hint=result.hint, is_first_message=is_first)
else:
    text = fallback_templates[intent]  # 3 failures → deterministic fallback
```

URL-aware: when text contains `http://` or `https://`, max length relaxed to 800 chars across gatekeeper, response agent, and polisher.

---

## TCPA Compliance

- **Opt-in**: First message appends "(Reply STOP anytime to opt out.)"
- **STOP**: Immediate opt-out. `opted_out=True`, phase → ABANDONED, no further messages
- **HELP**: Returns compliance info message
- **START**: Re-activates opted-out buyer. `opted_out=False`, phase → INTAKE
- **Quiet hours**: 9pm-9am in buyer timezone (inferred from search city, default Eastern). Proactive messages queued, reactive replies always sent immediately.

---

## Escalation System

When buyer asks a question not answerable from PropertyKnowledge:

1. **3-layer cache check**: known_answers → answered_questions (same property) → cross-property lookup
2. If all miss → `EscalationThread` created (status=pending, 2h SLA)
3. Email sent to ops with reply link
4. Buyer gets "Let me check on that — I'll text you back within 2 hours"
5. Phase → AWAITING_ANSWER
6. **Reply Tool** (`/api/sms/internal/reply/{thread_id}`): Ops types answer → Polisher → Gatekeeper → SMS sent → cached in known_answers
7. Phase → back to PROPERTY_FOCUSED

---

## Engagement Bridge

SMS actions create and advance Engagements (same state machine as web):

1. **COLLECTING_INFO**: Collect name → email
2. **COMMITMENT**: Auto-create Buyer + User records (with email dedup check), create Engagement with `source_channel='sms'`
3. **GUARANTEE_PENDING**: Generate `SmsSignupToken`, send link to mobile signing page
4. **TOUR_SCHEDULING**: After signing, reveal address, extract date/time preferences
5. Engagement state transitions: `ACCOUNT_CREATED → GUARANTEE_SIGNED → ADDRESS_REVEALED → TOUR_REQUESTED → TOUR_CONFIRMED`

---

## Re-engagement & Stall Detection

Per-phase nudge rules (via `sms_scheduler.py` cron):

| Phase | Delay | Max Nudges |
|-------|-------|------------|
| PRESENTING | 4 hours | 2 |
| PROPERTY_FOCUSED | 24 hours | 2 |
| GUARANTEE_PENDING | 30 min, then 4h | 1 each |
| DORMANT | 7 days | 1 (final) |

After max nudges exhausted → DORMANT. After DORMANT final nudge + 7 days silence → ABANDONED.

Inactivity abandonment: INTAKE/QUALIFYING with no buyer message for 30 days → ABANDONED (no SMS sent).

---

## Testing

### Test Suite: `backend/tests/sms/` (13 files, 167+ tests)

```
backend/tests/sms/
├── test_sms_models.py           # Domain model creation, defaults, FKs
├── test_buyer_sms_webhook.py    # TCPA, routing, token validation
├── test_message_interpreter.py  # Regex extraction (large test file)
├── test_gatekeeper.py           # All validation rules
├── test_orchestrator.py         # Full pipeline, reference resolution
├── test_detail_fetcher.py       # Cache logic, DB queries
├── test_escalation_service.py   # 3-layer check, thread lifecycle
├── test_reply_tool.py           # Ops reply flow
├── test_engagement_bridge.py    # Booking, tour, guarantee, email dedup
├── test_token_service.py        # Create, validate, redeem, expiry
├── test_notifications.py        # Event-driven, stall rules, quiet hours
├── test_scheduler.py            # Abandonment queries, SLA checks
└── test_journeys.py             # 5 end-to-end buyer journey scenarios
```

Run: `conda run -n wex python -m pytest backend/tests/sms/ -v --tb=short`

### 3 Test Tiers

1. **Unit**: Deterministic, no DB, no LLM. Tests interpreter, gatekeeper, readiness formula, templates.
2. **Integration**: Real async SQLite DB, mocked LLM + Aircall. Full pipeline flows.
3. **E2E Journeys**: Multi-turn simulations (happy path, refinement, escalation, TCPA, stall→dormant→abandoned).

---

## Configuration

### Environment Variables (backend/.env)

```
AIRCALL_BUYER_NUMBER_ID=476258      # Dedicated buyer SMS number
AIRCALL_WEBHOOK_TOKEN=...           # Webhook authentication
AIRCALL_API_ID=...                  # API credentials
AIRCALL_API_TOKEN=...
FRONTEND_URL=https://...            # For generating search/guarantee links
```

### Aircall Webhook Setup

Point Aircall webhook to: `POST {BACKEND_URL}/api/sms/buyer/webhook`
- Header: `X-Aircall-Token: {AIRCALL_WEBHOOK_TOKEN}`
- Body: Standard Aircall webhook payload with `data.from`, `data.body`, `data.direction`

---

## Migration from wex-leasing-service-python

This new implementation **fully replaces** the wex-leasing-service-python SMS pipeline. Key ports:

| wex-leasing Component | WEx Platform Equivalent |
|----------------------|------------------------|
| `polisher_agent.py` (320/400/800 char limits) | `polisher_agent.py` + `gatekeeper.py` (same limits, URL-aware) |
| `response_agent.py` (tone prompt) | `response_agent.py` (ported tone + terminology rules) |
| `gatekeeper_agent.py` | `gatekeeper.py` (expanded: garbage detection, context checks) |
| `criteria_extraction_agent.py` | `criteria_agent.py` + `message_interpreter.py` (split deterministic from LLM) |
| `detail_fetcher_agent.py` | `sms_detail_fetcher.py` (direct DB instead of API calls) |
| Firestore conversation state | `SMSConversationState` SQLAlchemy model |
| Node.js orchestrator | `buyer_sms_orchestrator.py` (Python async) |

The wex-leasing-service-python repo can be archived once the WEx Platform SMS pipeline is fully deployed and tested in production.

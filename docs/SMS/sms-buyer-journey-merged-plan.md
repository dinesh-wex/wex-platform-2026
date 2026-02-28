# SMS Buyer Journey — Merged Implementation Plan

## Core Principle

Port the proven wex-leasing-service-python 6-agent architecture faithfully into the WEx Platform backend. Extend the pipeline and state machine to cover the full buyer journey (search → match → commit → tour → agreement → active lease). Every design decision passes the test: **"would a helpful human warehouse agent handle it this way?"**

---

## Scope

Buyer SMS only. Supplier SMS is a separate effort with its own Aircall number and pipeline.

- **Buyer webhook:** `POST /api/sms/buyer/webhook` (new, dedicated)
- **Current sms.py:** Stays as-is for existing supplier DLA flow
- **Edge case — supplier texts buyer number:** Silent forward + generic reply ("Got it — we'll get back to you shortly"). Don't reveal routing architecture or mention a different number.

---

## The SMS Journey (Example Conversations)

### Happy Path: Search → Match → Drill In → Commit → Tour

```
BUYER: Hey I need about 15k sqft of warehouse space near Detroit
       for storing auto parts. Need it by April.

WEX:   Got it — 15K sqft near Detroit for auto parts storage,
       starting April. Searching now.

WEX:   Found 2 options:
       1) 18,000 sqft in Commerce Twp — dock doors, available now. ~$1.15/sqft
       2) 12,500 sqft in Pontiac — drive-in access, March 1. ~$0.95/sqft
       Want details on either?

BUYER: Tell me more about the Commerce one

WEX:   Commerce Twp — 18K sqft, 24ft clear height, 4 dock doors,
       sprinkler system, 20 parking spots. 3-12 month terms.
       Ready to tour?

BUYER: What about power? We run heavy conveyors

WEX:   Let me check on that. One sec.
       [Detail Fetcher → PropertyKnowledge → finds 400 amp 3-phase]

WEX:   400 amp, 3-phase power. Should handle conveyors fine.
       Want to schedule a tour?

BUYER: Yeah let's do it

WEX:   Before I share the address, I need a quick signature on our
       occupancy guarantee — takes 30 seconds:
       → wex.co/g/abc123

BUYER: [signs on mobile web page]

WEX:   Done! The property is at 4200 Katy Freeway, Commerce Twp MI.
       When works for a tour? I can check the owner's availability.

BUYER: Thursday morning

WEX:   Checking Thursday morning. I'll confirm shortly.
       [creates Engagement, notifies supplier]

WEX:   Confirmed — Thursday March 6 at 10:00 AM. The owner will
       meet you there. Text me after and let me know how it went.
```

### Partial Info Entry

```
BUYER: Looking for warehouse space in Houston

WEX:   Houston — great market. How much space do you need,
       and what will you be storing?

BUYER: Around 30k, ecommerce fulfillment. Need dock doors and office.

WEX:   30K sqft in Houston for ecommerce fulfillment, dock doors
       + office. Searching.
       [ClearingEngine → presents matches]
```

### Change of Mind

```
BUYER: Actually I think I need cold storage instead

WEX:   No problem — cold storage in Houston, still around 30K sqft?
       Searching now.
       [re-runs ClearingEngine with updated criteria]
```

### Question That Needs Escalation

```
BUYER: Can trucks park overnight there?

WEX:   Good question — let me find out. I'll text you back
       within a couple hours.
       [Detail Fetcher → UNMAPPED → EscalationThread created → email ops]

       [2 hours later, ops hasn't answered]

WEX:   Still working on the overnight parking question for Commerce Twp.
       Want to check out the Pontiac space while we wait?

       [ops answers via Reply Tool]

WEX:   Update on Commerce Twp — yes, overnight truck parking is
       available in the fenced yard. Want to schedule a tour?
```

### Re-engagement (48h silence after matches shown)

```
WEX:   Hey — still thinking about those spaces in Houston?
       They're available. I can also run a fresh search if your
       needs changed.
```

---

## Agent Architecture — Full Port from Leasing Service

### Design Principles (ported exactly)

1. **Each agent has ONE job** — no agent does two things
2. **Deterministic vs LLM separation** — regex/validation agents never call LLM; LLM agents never do validation
3. **Structured output contracts** — every agent has typed input/output dataclasses
4. **Gatekeeper → Polisher retry loop** — guaranteed valid SMS output

### Agent Responsibilities

| Agent | Job | NOT Its Job | Output |
|-------|-----|-------------|--------|
| Message Interpreter | Extract entities via regex | Classify intent, resolve references | `MessageInterpretation` |
| Criteria Agent | Classify intent, plan action | Write SMS text | `CriteriaPlan` (JSON) |
| Detail Fetcher | Fetch property info from cache/DB | Decide to escalate | `DetailFetchResult` |
| Response Agent | Write customer-facing SMS text | Pick properties, validate | Plain text |
| Polisher Agent | Compress/improve text | Generate new content | Plain text |
| Gatekeeper | Validate SMS output | Generate text | `GatekeeperResult` |

### Deterministic vs LLM

| Deterministic (Python) | LLM-Powered |
|------------------------|-------------|
| Message Interpreter | Criteria Agent |
| Gatekeeper | Response Agent |
| Detail Fetcher | Polisher Agent |
| Topic Catalog | |
| Property Reference Resolution (orchestrator) | |
| Criteria Readiness Computation | |

---

## The 6-Agent Pipeline

```
Inbound SMS (Aircall BUYER webhook)
        │
        ├── Keyword handler (deterministic, pre-pipeline)
        │   STOP/UNSUBSCRIBE/CANCEL → cease outbound, log
        │   HELP → send options summary
        │   START → reactivate
        │
        ├── Supplier phone detected? → silent forward + generic reply
        │
        └── Buyer pipeline:
            │
┌───────────────────────────────────────────────────────────────┐
│ 1. MESSAGE INTERPRETER (Deterministic — No LLM)               │
│                                                                │
│    Extracts raw entities only. Stateless — no conversation     │
│    context needed.                                             │
│                                                                │
│    - Extract cities, states via regex + known city list        │
│    - Extract sizes (5000 sqft, 70k SF, 10,000 square feet)    │
│    - Detect topics (ceiling height, dock doors, cold storage)  │
│    - Detect features (24h access, forklift, hazmat)            │
│    - Extract emails (sarah@acmecorp.com)                       │
│    - Extract dates/times ("Thursday morning", "March 5 2pm")   │
│    - Extract action keywords (book, tour, pass, yes)           │
│    - Extract names (basic pattern, confirmed by Criteria Agent)│
│    - Detect positional references ("option 2", "#1", "the      │
│      first one") — raw extraction, NOT resolution              │
│    - Classify query type (search, property_lookup, booking,    │
│      general)                                                  │
│                                                                │
│    → Output: MessageInterpretation dataclass                   │
│                                                                │
│    NOTE: Property reference resolution ("the Commerce one"     │
│    → specific match from presented_match_ids) happens in the   │
│    ORCHESTRATOR, not here. The interpreter only extracts that   │
│    a city name or positional reference was mentioned.           │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR: Property Reference Resolution (Deterministic)    │
│                                                                │
│    Resolves extracted entities against conversation state:      │
│    - Positional: "option 2" → presented_match_ids[1]           │
│    - City name: "the Commerce one" → match by city in          │
│      presented_match_ids                                       │
│    - Attribute: "the cheapest" → sort presented matches by     │
│      rate, pick lowest                                         │
│    - Ambiguous → pass candidates to Criteria Agent for         │
│      confirmation prompt                                       │
│                                                                │
│    This is state-dependent logic, so it lives in the           │
│    orchestrator, not the interpreter.                           │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 2. CRITERIA AGENT (LLM — JSON Output Only)                     │
│                                                                │
│    Receives: message + MessageInterpretation + resolved         │
│    property reference + recent history + phase context          │
│                                                                │
│    - Classify intent: new_search, refine_search, facility_info,│
│      tour_request, commitment, provide_info, greeting, unknown │
│    - Plan action: search, lookup, respond, clarify, ask_owner, │
│      schedule_tour, commitment_handoff, collect_info           │
│    - Extract criteria: location, sqft, use_type, goods_type,   │
│      timing, duration, features                                │
│    - Extract buyer name if present                             │
│    - Identify asked_fields for Detail Fetcher                  │
│                                                                │
│    → Output: CriteriaPlan dataclass (JSON only, NEVER SMS text)│
│                                                                │
│    NOTE: criteria_readiness is computed DETERMINISTICALLY by    │
│    the orchestrator from extracted criteria, not by the LLM.   │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 3. TOOL EXECUTION (Orchestrator — Business Logic)              │
│                                                                │
│    action=search → ClearingEngine.run_clearing()               │
│    action=lookup → Detail Fetcher (see 3b)                     │
│    action=ask_owner → Escalation (see 3c)                      │
│    action=schedule_tour → EngagementBridge.request_tour()      │
│    action=commitment_handoff → EngagementBridge + guarantee    │
│                                 link                           │
│    action=collect_info → store name/email, advance collection  │
│    action=respond → no tools                                   │
│    action=clarify → no tools                                   │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 3b. DETAIL FETCHER (Deterministic — No LLM)                    │
│                                                                │
│    Ported from leasing service. Cache-first property info.     │
│                                                                │
│    1. Merge asked_fields (from Criteria Agent LLM) +           │
│       asked_topics (from Message Interpreter regex)            │
│       → compute final field_keys via Topic Catalog             │
│    2. Check known_answers cache on SMSConversationState        │
│       - If ALL fields cached → return immediately              │
│    3. Query PropertyKnowledge / PropertyListing tables          │
│       (replaces WEX API /details)                              │
│    4. Extract and format fields via Field Catalog              │
│    5. Persist newly found values to known_answers cache        │
│    6. Analyze outcomes: FOUND, CACHE_HIT, MAPPED_TRUE/FALSE,  │
│       UNMAPPED                                                 │
│    7. If all found → skip escalation                           │
│                                                                │
│    → Output: DetailFetchResult dataclass                       │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 3c. CACHE CHECK + ESCALATION (Re-escalation Prevention)        │
│                                                                │
│    Two-layer caching (ported from leasing service):            │
│                                                                │
│    Layer 1: auto_map_question_to_field_key()                   │
│             → check known_answers[property_id][field_key]      │
│    Layer 2: find_matching_answered_question()                  │
│             → check answered_questions (same property)         │
│    Layer 3: Cross-property answer lookup                       │
│             → check answered_questions (all properties)        │
│                                                                │
│    If none hit → create EscalationThread → email internal ops  │
│    Track SLA (2 hours). On SLA breach → nudge buyer +          │
│    alert ops.                                                  │
│    On answer → Reply Tool → Polish → Gatekeeper → send SMS    │
│    → cache in known_answers + answered_questions               │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 4. RESPONSE AGENT (LLM — Plain Text Output)                    │
│                                                                │
│    ONLY agent that produces customer-facing SMS text.           │
│                                                                │
│    - Phase-aware prompt construction via Context Builder        │
│    - Match presentation: max 3, city + sqft + feature + rate   │
│    - Length limits: 800 (first msg / match results),            │
│      320 (follow-up)                                           │
│    - Natural conversational tone — never "Reply 1, 2, 3"       │
│    - Guarantee link messaging                                  │
│    - Tour scheduling messaging                                 │
│    - Escalation wait messaging with time commitment            │
│    - Name personalization when available                        │
│                                                                │
│    → Output: Plain text SMS                                    │
└───────────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ 5. GATEKEEPER (Deterministic — No LLM)                         │
│                                                                │
│    100% deterministic validation. No LLM calls ever.           │
│                                                                │
│    - Length check (800 first / 320 follow-up)                  │
│    - Garbage detection (repeated chars >40, letter ratio <0.40,│
│      word repetition >5)                                       │
│    - PII leak check (multiple phones or emails)                │
│    - Profanity filter                                          │
│    - Context-specific checks:                                  │
│      - commitment messages must contain guarantee link          │
│      - tour messages must contain URL or scheduling language    │
│      - escalation wait messages must contain time commitment    │
│                                                                │
│    → Output: GatekeeperResult (ok / hint / violation)          │
└───────────────────────────────────────────────────────────────┘
        │
        ├── OK → Send via Aircall, persist message, update state
        │
        └── FAIL → POLISHER AGENT (LLM)
                   │
                   - Compress/fix text per gatekeeper hint
                   - Preserve ALL factual information
                   - Remove fluff words ("actually", "basically")
                   - Combine sentences where possible
                   - NEVER add new information
                   - NEVER change meaning
                   - Re-validate via Gatekeeper
                   - After 3 failures → deterministic fallback template
```

---

## Supporting Modules

### Context Builder

**Ported from leasing service's `context_builder.py`.** Single source of truth for all LLM prompts.

Provides:
- `build_criteria_context()` — system prompt + interpretation + recent history + phase context → Criteria Agent
- `build_response_context()` — system prompt + CriteriaPlan + properties + phase + retry hint → Response Agent
- `build_polisher_context()` — rejected text + gatekeeper hint → Polisher Agent

Recent history: last 8 messages (inbound + outbound only, filtered from system messages).

Phase-specific instructions injected per conversation phase (e.g., PRESENTING phase tells Response Agent how to format matches; COMMITMENT phase includes guarantee link messaging rules).

The context builder also passes `presented_match_ids` with property names, cities, and rates into the Criteria Agent prompt — this is how the Criteria Agent resolves ambiguous references like "the cheapest" when the orchestrator's deterministic resolution can't handle it.

### Topic Catalog

**Ported from leasing service's `topic_catalog.py`.** Deterministic topic detection and question-to-field mapping.

- `detect_topics(text)` — regex patterns for ceiling height, dock doors, cold storage, power, parking, etc.
- `auto_map_question_to_field_key(text)` — conservative multi-keyword mapping (requires 2+ keyword hits to reduce false positives)
- `TOPIC_TO_FIELD_KEYS` — maps detected topics to PropertyKnowledge column names

### Field Catalog

**Ported from leasing service's `field_catalog.py`.** Field definitions, extractors, and formatters adapted for PropertyKnowledge columns.

| Field Key | PropertyKnowledge Column | Format |
|-----------|--------------------------|--------|
| ceiling_height | ceiling_height | "{value} ft" |
| dock_doors | dock_doors | "{value} dock doors" |
| drive_in_doors | drive_in_doors | "{value} drive-in doors" |
| temperature_controlled | climate_controlled | bool → "Yes"/"No" |
| rate_per_foot | PropertyListing.base_rate | "${value}/sqft" |
| available_space | PropertyListing.available_sqft | "{value} sqft" |
| office_space | has_office | bool → "Yes"/"No" |
| hours_24h | access_24_7 | bool → "Yes"/"No" |
| forklift | forklift_available | bool → "Yes"/"No" |
| power | electrical_service | text |
| parking | parking_spaces | "{value} spots" |
| overnight_parking | overnight_parking | bool → "Yes"/"No" |
| sprinklers | sprinkler_system | bool → "Yes"/"No" |
| security | security_features | text |

### Fallback Templates

Deterministic templates used after 3 Gatekeeper failures:

```python
FALLBACK_TEMPLATES = {
    "greeting": "Hey! I help find warehouse space. What city, size, and storage type are you looking for?",
    "search_with_results": "Found some warehouse options that could work. Want me to share the details?",
    "search_no_results": "Searching for warehouse space matching your needs. Could you tell me more about what you're looking for?",
    "facility_info": "I can tell you more about this space. What would you like to know?",
    "refine_search": "Happy to narrow it down. What other requirements do you have?",
    "commitment": "Ready to move forward? I'll send you a quick link to get started.",
    "tour_scheduling": "I'll work on getting that tour set up and text you when it's confirmed.",
    "escalation_wait": "Checking on that for you. I'll text back when I have an answer.",
    "default": "Thanks for reaching out! I help find warehouse space. What city and size are you looking for?",
}
```

---

## Goal-Driven Orchestrator

The orchestrator wraps the 6-agent pipeline with phase-aware routing.

```
BuyerSMSOrchestrator.process_message(phone, text, db)
    │
    ├── 1. Load/create state (SMSConversationState + BuyerConversation + Buyer)
    ├── 2. TCPA: update last_interaction_at, check opt-out status
    ├── 3. Run Message Interpreter (deterministic entity extraction)
    ├── 4. Property Reference Resolution (deterministic, uses state)
    ├── 5. Compute criteria_readiness from extracted criteria (deterministic)
    ├── 6. Build phase context for Criteria Agent prompt
    ├── 7. Run Criteria Agent (LLM → CriteriaPlan)
    ├── 8. Phase-specific tool execution:
    │       INTAKE: greet, wait for criteria
    │       QUALIFYING: check readiness → run ClearingEngine if ≥ 0.6
    │       PRESENTING: resolve property reference → PROPERTY_FOCUSED
    │       PROPERTY_FOCUSED: Detail Fetcher → cache check → escalation if needed
    │       COLLECTING_INFO: store name/email as provided
    │       COMMITMENT: generate guarantee link
    │       GUARANTEE_PENDING: check signing status
    │       TOUR_SCHEDULING: create Engagement, notify supplier
    │       ACTIVE: post-tour, agreement, onboarding links
    ├── 9. Run Response Agent (LLM → SMS text)
    ├── 10. Run Gatekeeper → Polisher retry loop
    ├── 11. Send via Aircall
    ├── 12. Update SMSConversationState (phase, timestamps, counters)
    ├── 13. Persist platform records (BuyerNeed, Match, Engagement)
    └── 14. Schedule re-engagement timer if applicable

    KEY RULE: The orchestrator uses phase as context, not a gate.
    Any valid action is allowed regardless of current phase.
    If buyer in TOUR_SCHEDULING asks "what was the price on the
    Commerce one?" → Criteria Agent classifies as facility_info →
    orchestrator runs Detail Fetcher → Response Agent answers →
    phase stays TOUR_SCHEDULING.
```

### Criteria Readiness (Deterministic — computed by orchestrator, not LLM)

```python
def compute_criteria_readiness(criteria: dict) -> float:
    score = 0.0
    if criteria.get("location"):  score += 0.4
    if criteria.get("sqft"):      score += 0.3
    if criteria.get("use_type"):  score += 0.2
    # Any additional field: +0.1 each, capped at 1.0
    extras = ["goods_type", "timing", "duration", "features"]
    for field in extras:
        if criteria.get(field):
            score += 0.1
    return min(score, 1.0)

# Threshold to trigger ClearingEngine search: 0.6
# (location + sqft, or location + use_type)
```

---

## Conversation State Machine

### SMSConversationState (new table)

```
id                      UUID PK
buyer_id                FK → buyers.id
conversation_id         FK → buyer_conversations.id
buyer_need_id           FK → buyer_needs.id (nullable)

# Phase tracking
phase                   VARCHAR(30)
turn                    INT (incremented per inbound)

# Property focus
focused_match_id        FK → matches.id (nullable)
presented_match_ids     JSON [] — match IDs in presentation order

# Criteria
criteria_readiness      FLOAT 0.0–1.0
criteria_snapshot       JSON {} — last extracted criteria

# Buyer info
renter_first_name       VARCHAR(100) (nullable)
renter_last_name        VARCHAR(100) (nullable)
name_status             VARCHAR(20) default "unknown"
buyer_email             VARCHAR(255) (nullable)

# Engagement
engagement_id           FK → engagements.id (nullable)
guarantee_link_token    VARCHAR(64) (nullable)
guarantee_signed_at     DATETIME (nullable)

# Caching (ported from leasing service)
known_answers           JSON {} — {property_id: {field_key: KnownAnswer}}
answered_questions      JSON [] — list of {question, answer, property_id, answered_at}
pending_escalations     JSON {} — {property_id: "pending"}
tour_suggested_for      JSON [] — property IDs where tour was offered

# Re-engagement
last_buyer_message_at   DATETIME
last_system_message_at  DATETIME
reengagement_count      INT default 0
next_reengagement_at    DATETIME (nullable)
stall_nudge_counts      JSON {} — {phase: count} per-phase nudge tracking

# TCPA (minimal)
opted_out               BOOLEAN default false
opted_out_at            DATETIME (nullable)

# Metadata
created_at              DATETIME
updated_at              DATETIME
```

### Phase States

```
INTAKE → QUALIFYING → PRESENTING → PROPERTY_FOCUSED
              ↑            ↑              │
              │            │        ┌─────┴──────────┐
              │            │        ↓                 ↓
         (refine)    (browse)  AWAITING_ANSWER       │
                                    │                 │
                                    ↓                 ↓
                              (answer arrives)  COLLECTING_INFO
                                    │           (name, email)
                                    ↓                 │
                                    └────────→────────↓
                                              COMMITMENT
                                              (guarantee link sent)
                                                      │
                                                      ↓
                                              GUARANTEE_PENDING
                                              (awaiting signature)
                                                      │
                                                      ↓
                                              TOUR_SCHEDULING
                                              (request/confirm)
                                                      │
                                                      ↓
                                              ACTIVE
                                              (post-tour, agreement, onboarding)
                                                      │
                                                      ↓
                                              COMPLETED

(any phase) + STOP keyword → ABANDONED
(any phase) + 3 unanswered re-engagements → DORMANT
```

| Phase | Trigger In | Trigger Out | Platform Records |
|-------|-----------|-------------|------------------|
| INTAKE | First message (greeting only) | Buyer provides any criteria | — |
| QUALIFYING | Buyer provides partial criteria | criteria_readiness ≥ 0.6 | BuyerNeed created/updated |
| PRESENTING | ClearingEngine returns matches | Buyer references a match | Match records |
| PROPERTY_FOCUSED | Buyer selects a property | "tour" / "book" / "let's go" | — |
| AWAITING_ANSWER | Question escalated to ops | Answer received via Reply Tool | EscalationThread |
| COLLECTING_INFO | Buyer expresses commitment | Name + email collected | — |
| COMMITMENT | Info collected | Guarantee link sent | Engagement created |
| GUARANTEE_PENDING | Link sent | Buyer signs (webhook) | Engagement → GUARANTEE_SIGNED |
| TOUR_SCHEDULING | Guarantee signed, address revealed | Tour confirmed | Engagement → TOUR_REQUESTED |
| ACTIVE | Tour confirmed | Deal completes | Engagement → TOUR_CONFIRMED |
| DORMANT | 3 re-engagements unanswered | — | BuyerNeed → expired |

### Backward/Lateral Movement

The phase tracks where the conversation *is*, not what the buyer can *do*. Rules:

- **Any phase → QUALIFYING:** "Actually I need cold storage instead" → re-run ClearingEngine with updated criteria
- **Any phase → PRESENTING:** "What were the other options?" → re-present matched properties
- **Any phase → PROPERTY_FOCUSED:** "What about the Pontiac one?" → shift focus, previous engagement records stay intact
- **AWAITING_ANSWER → PROPERTY_FOCUSED:** Buyer asks about a different property while waiting → shift focus, escalation stays pending
- **Facility question from any phase:** Always allowed — orchestrator runs Detail Fetcher, answers, phase unchanged

---

## Escalation Service

### Full Escalation Path (ported from leasing service)

```
Buyer asks question → Detail Fetcher → UNMAPPED
        │
        ▼
1. auto_map_question_to_field_key() → check known_answers
2. find_matching_answered_question() → check answered_questions (same property)
3. Cross-property answer lookup → check answered_questions (all properties)
4. If none hit → create EscalationThread → email internal ops
        │
        ▼
Internal ops opens email link → Reply Tool web UI
(case details, recent messages, reply textarea)
        │
        ▼
POST /api/sms/internal/reply
  → Validate token
  → Check conversation exists + not opted out
  → Check follow-up window (30 min)
  → auto_map_question_to_field_key() for semantic caching
  → Polish via Polisher Agent
  → Validate via Gatekeeper
  → Send via Aircall
  → Persist message
  → Cache answer in known_answers (field-key) + answered_questions (text)
  → Clear pending escalation
```

### EscalationThread Model

```
id                      UUID PK
conversation_id         FK → buyer_conversations.id
state_id                FK → sms_conversation_states.id
property_id             FK → properties.id
question_text           VARCHAR(500)
answer_text             VARCHAR(500) nullable

# Status
status                  VARCHAR(20) — pending, answered, expired

# SLA
sla_deadline_at         DATETIME — 2 hours from creation
buyer_nudge_sent        BOOLEAN default false

# Email tracking
email_count             INT default 0
last_email_sent_at      DATETIME nullable

# Reply tracking (full chain from leasing service)
answer_raw_text         TEXT nullable — operator's raw input
answer_polished_text    TEXT nullable — after Polisher
answer_sent_text        TEXT nullable — what buyer received
answer_sent_mode        VARCHAR(20) nullable — polished/raw/fallback
answered_at             DATETIME nullable
answered_by             VARCHAR(255) nullable — operator email

# Follow-up window
followup_window_until   DATETIME nullable
followup_count          INT default 0

# Thread support (multiple questions per thread)
thread_questions        JSON [] — supports multi-question threads

created_at / updated_at DATETIME
```

### SLA Handling

- **2-hour SLA** on all escalations (configurable)
- **On SLA breach:** Send buyer a natural follow-up ("Still working on the overnight parking question for Commerce Twp. Want to check out the Pontiac space while we wait?") + alert ops
- **buyer_nudge_sent** flag prevents double-nudging

---

## TCPA Compliance (Minimal — Doesn't Feel Like a Bot)

The buyer is texting us and we're pretending to be a helpful human agent. Keep it natural. No legalese, no bot disclaimers. But protect the sending number and stay legal on proactive outbound.

### What We Handle

**STOP / opt-out keywords** (carrier requirement, non-negotiable):
- STOP, UNSUBSCRIBE, CANCEL, QUIT, END → immediately cease ALL outbound
- Log `opted_out = true`, `opted_out_at = now()`
- Do NOT send a confirmation message (carrier handles this)
- Enforce: check `opted_out` before every outbound send

**Implicit re-opt-in:**
- If an opted-out buyer texts us again with anything other than STOP → treat as implicit re-opt-in
- Respond normally + subtle opt-in: include "Reply STOP anytime" in the first response back (once, naturally, not a legal block)

**First message opt-in** (subtle, embedded naturally):
- NOT: "By continuing, you agree to receive messages from WEx. Msg & data rates apply. Reply STOP to opt out."
- YES: "Hey! I help find warehouse space. Tell me what you need — size, city, what you're storing. I'll find options fast. (Reply STOP anytime to opt out.)"
- The parenthetical is the only concession. It reads like a helpful aside, not a legal notice.

**Quiet hours on proactive-only messages:**
- No proactive outbound (re-engagement nudges, tour reminders, hold warnings) between 9pm–9am buyer local time
- Queue and send at 9am
- Reactive replies (responding to a buyer's text) are always sent immediately, any time
- Timezone: infer from search location (buyer searching Detroit → Eastern). Default to most restrictive if unknown.

### What We Don't Build (for now)

- No daily message cap (we're not sending enough volume to hit carrier limits)
- No formal SmsAuditLog table (opted_out_at timestamp on state + message persistence is sufficient audit trail)
- No double opt-in or confirmation messages
- No legal disclaimer blocks

### How It Feels to the Buyer

The buyer never sees the word "TCPA", never gets a wall of legal text, never thinks "I'm talking to a bot." The only visible compliance elements are:

1. "(Reply STOP anytime to opt out.)" — once, in the first message, in parentheses
2. If they send STOP, messages stop
3. No texts at 3am

That's it.

---

## Proactive Notifications

System events that trigger outbound SMS. All respect opt-out status and quiet hours.

| Event | SMS Message (natural tone) | Timing |
|-------|---------------------------|--------|
| Tour confirmed by supplier | "Tour confirmed — Thursday March 6 at 10 AM at [address]. See you there." | Immediate |
| Tour reminder | "Just a reminder — tour today at [time] at [address]." | 2 hours before |
| Tour rescheduled | "Heads up — your tour got moved to [new date/time]. Does that still work?" | Immediate |
| Escalation answered | "Got an answer on [topic] for [property] — [answer]. Want to move forward?" | Immediate |
| Agreement ready | "Your agreement is ready to sign: [link]" | Immediate |
| Hold expiring (24h) | "Your hold on [property] expires tomorrow. Let me know if you need more time." | At 24h mark |
| Hold expiring (4h) | "Hold expires in a few hours: [link]" | At 4h mark |
| New match (DLA tier2) | "Another space just opened up in [city] that fits what you're looking for." | Within quiet hours |
| Onboarding complete | "You're all set — lease at [address] starts [date]. Text me anytime." | Immediate |

### Re-engagement Nudges

60–70% of SMS conversations stall. Scheduled jobs detect silence and send natural nudges.

| Stall Point | After | Nudge Message | Max Per Phase |
|-------------|-------|---------------|---------------|
| Results shown, no selection | 4 hours | "Still thinking about those spaces? Happy to answer questions or run a different search." | 2 |
| Deep-dive, no action | 24 hours | "The [property] space is still available. Want to schedule a tour?" | 2 |
| Guarantee link sent, no signing | 30 min | "Just sent the guarantee link — takes 30 seconds. Let me know if you have questions." | 1 |
| Guarantee link sent, still no signing | 4 hours | "Still holding [property] for you. Sign here when ready: [link]" | 1 |
| Post-tour, no response | 24 hours | "How'd the tour go? Want to move forward with [property]?" | 1 |
| Long dormancy | 7 days | "Hey — warehouse space in [city] is moving fast. Want me to refresh your search?" | 1 |

**After max nudges → go silent.** Mark conversation as DORMANT after 3 unanswered re-engagements across all phases. No one wants to be spammed.

**`stall_nudge_counts` is a JSON object keyed by phase** — so a buyer who stalled once during PRESENTING and got 2 nudges still gets fresh nudges when they stall at GUARANTEE_PENDING.

---

## Cross-Channel Continuity

**Phone = universal key.** Buyer.phone links SMS conversations to web accounts.

**SMS → Web:** Tokenized short links carry context. On web signup, system matches Buyer.phone, links all existing BuyerNeed, Match, Engagement records. Pre-filled forms (name + email collected via SMS).

**Web → SMS:** Buyer opts in on web → create BuyerConversation + SMSConversationState → send contextual first message: "Hey [name] — you were looking at [criteria] on the web. I'll text you updates. Text back anytime."

---

## Database Changes Summary

### New Tables

| Table | Purpose |
|-------|---------|
| `sms_conversation_states` | SMS-specific conversation state (phases, criteria, caching, re-engagement) |
| `sms_signup_tokens` | One-time web handoff tokens with pre-filled buyer info |
| `escalation_threads` | Question escalation tracking with SLA, Reply Tool support |

### Modified Tables

| Table | Change |
|-------|--------|
| `engagements` | Add `source_channel` VARCHAR(10), default "web" |

### SmsSignupToken Model

```
id                  UUID PK
token               VARCHAR(64) unique, indexed
state_id            FK → sms_conversation_states.id
buyer_id            FK → buyers.id
engagement_id       FK → engagements.id (nullable)
property_id         FK → properties.id (nullable)
action              VARCHAR(20) — "guarantee", "agreement", "onboarding"
buyer_name          VARCHAR(100) nullable — pre-collected via SMS
buyer_email         VARCHAR(255) nullable — pre-collected via SMS
used                BOOLEAN default false
expires_at          DATETIME
created_at          DATETIME
```

---

## Files to Create

### Ported from Leasing Service (adapted for new DB)

| File | Purpose | Key Adaptation |
|------|---------|----------------|
| `agents/sms/message_interpreter.py` | Deterministic regex extraction | Property references as city/position (not #1625 int IDs). Add email, date, action keyword extraction |
| `agents/sms/criteria_agent.py` | LLM intent + action planning | New intents: tour_request, commitment, provide_info. New actions: schedule_tour, commitment_handoff, collect_info |
| `agents/sms/response_agent.py` | LLM SMS text generation | Phase-aware prompts for all journey phases |
| `agents/sms/polisher_agent.py` | LLM text compression | Ported as-is |
| `agents/sms/gatekeeper.py` | Deterministic validation | Context checks for commitment (must have link), tour (must have scheduling language) |
| `agents/sms/context_builder.py` | Centralized prompt construction | Phase-specific instructions, presented matches in Criteria Agent context |
| `agents/sms/topic_catalog.py` | Topic detection + field mapping | TOPIC_TO_FIELD_KEYS maps to PropertyKnowledge columns |
| `agents/sms/field_catalog.py` | Field definitions + extractors | Extractors read PropertyKnowledge model, not API JSON |
| `services/sms_detail_fetcher.py` | Cache-first property info | PropertyKnowledge/PropertyListing via SQLAlchemy (replaces WEX API + Firestore) |

### New (Engagement Extension + Operations)

| File | Purpose |
|------|---------|
| `services/buyer_sms_orchestrator.py` | Goal-driven orchestrator with phase routing, property resolution, criteria readiness |
| `services/engagement_bridge.py` | Connects SMS actions to engagement state machine (initiate_booking, request_tour, confirm, decline) |
| `services/sms_token_service.py` | Create/validate/redeem SmsSignupToken records |
| `services/escalation_service.py` | Create EscalationThread, email ops, SLA tracking, proactive follow-up |
| `services/buyer_notification_service.py` | Proactive outbound (tour confirmed, hold expiring, etc.) + re-engagement nudges + quiet hours |
| `app/routes/buyer_sms.py` | Dedicated buyer SMS webhook (Aircall validation, keyword handling, orchestrator call) |
| `app/routes/sms_reply_tool.py` | Ported Reply Tool — GET (HTML form) + POST (validate → polish → send → cache) |
| `app/routes/sms_guarantee.py` | Mobile guarantee signing page + webhook callback |

### Files to Modify

| File | Change |
|------|--------|
| `domain/models.py` | Add SMSConversationState, SmsSignupToken, EscalationThread models. Add source_channel to Engagement. |
| `services/buyer_conversation_service.py` | Add turn increment, state helpers, KnownAnswers cache management |
| `app/routes/engagement.py` | Extract state-transition logic into shared EngagementService callable by both web routes and EngagementBridge |
| `services/sms_service.py` | Add send_sequential_messages(), TCPA opt-out check, quiet hours check, use AIRCALL_BUYER_NUMBER_ID |

---

## Implementation Sequence

### Sprint 1: Foundation + Minimal TCPA

**Goal:** Pipeline compiles, state model exists, basic inbound/outbound works.

- SMSConversationState model + migration
- EscalationThread model + migration
- SmsSignupToken model + migration
- `buyer_sms.py` webhook route (Aircall validation, STOP/HELP/START keyword handling pre-pipeline)
- TCPA minimum: opt-out enforcement, first-message opt-in line, quiet hours on proactive
- BuyerConversationService: turn increment, state transitions

### Sprint 2: Port Core Agents

**Goal:** Full 6-agent pipeline running for search + results presentation.

- Message Interpreter (all regex patterns, entity extraction)
- Topic Catalog + Field Catalog (mapped to PropertyKnowledge)
- Context Builder (prompt construction for all phases)
- Criteria Agent (5 existing intents + JSON output)
- Response Agent (SMS generation, match presentation)
- Gatekeeper (full validation rules)
- Polisher Agent (compression, retry loop)
- Orchestrator: INTAKE → QUALIFYING → PRESENTING flow
- ClearingEngine integration (criteria readiness → search → present)
- Property reference resolution in orchestrator (deterministic)
- Fallback templates for all intents
- **Verify:** SMS conversation → greeting → criteria → matches presented

### Sprint 3: Detail Fetcher + Escalation

**Goal:** Buyer can ask questions about properties, get answers from cache/DB, unanswerable questions escalate to ops.

- Detail Fetcher (cache check → PropertyKnowledge query → outcome analysis)
- Two-layer caching: known_answers + answered_questions + cross-property lookup
- Escalation Service (create thread, email ops, SLA tracking)
- Reply Tool (GET form + POST reply → polish → gatekeeper → send → cache)
- SLA handling: buyer nudge on breach, ops alert
- Orchestrator: PROPERTY_FOCUSED flow
- **Verify:** Ask answerable question → immediate answer. Ask unanswerable → escalation email → Reply Tool answer → SMS to buyer + cached.

### Sprint 4: Commitment + Tour Flow

**Goal:** Full journey from search to tour confirmation.

- Criteria Agent: add tour_request, commitment, provide_info intents
- EngagementBridge (initiate_booking, request_tour, confirm_tour, decline)
- Info collection flow (name → email via SMS, interruptible)
- SmsSignupToken service + guarantee signing page + webhook callback
- Orchestrator: COLLECTING_INFO → COMMITMENT → GUARANTEE_PENDING → TOUR_SCHEDULING → ACTIVE
- Proactive notifications: tour confirmed, tour reminder
- **Verify:** Full journey — search → match → deep-dive → "book it" → name/email → guarantee link → sign → address revealed → tour requested → tour confirmed

### Sprint 5: Notifications + Re-engagement + Polish

**Goal:** System handles silence, sends proactive updates, works end-to-end.

- BuyerNotificationService: all event-driven outbound messages
- Re-engagement scheduled jobs (stall detection + nudges per phase)
- Hold expiry notifications
- Agreement/onboarding link messaging
- Cross-channel: web opt-in → SMS, SMS token → web signup
- DORMANT state after 3 unanswered re-engagements
- End-to-end testing with real Aircall SMS
- **Verify:** Full stall/nudge cycle. Proactive notifications. Cross-channel linking.

---

## Verification Plan

### Unit Tests

- **Message Interpreter:** Regex extraction for all entity types — cities, sizes, topics, emails, dates, action keywords, positional references
- **Criteria Agent:** Intent classification for all 8 intents. JSON output validation. Facility matching by name/attribute when context provided.
- **Detail Fetcher:** Cache-first behavior — mock PropertyKnowledge, verify no DB query when known_answers has the value
- **Gatekeeper:** Length limits, garbage detection, PII check, profanity, context-specific checks
- **Polisher:** Compression preserves facts, removes fluff, stays under limit
- **Criteria Readiness:** Deterministic computation matches expected scores for various criteria combos
- **Property Resolution:** "option 2" → correct match. "the cheapest" → correct sort. "the Commerce one" → city match. Ambiguous → candidates returned.

### Integration Tests

- **Pipeline end-to-end:** Mock each agent, verify orchestrator calls them in correct order with correct inputs
- **Re-escalation prevention:** Ask same question twice → verify second time uses cache, no email sent
- **Cross-property cache:** Answer question for property A → ask same question about property B → verify cross-property lookup
- **Gatekeeper + Polisher retry:** Generate too-long response → Polisher compresses → Gatekeeper passes → after 3 failures → fallback template
- **State transitions:** Verify all phase transitions including backward movement (TOUR_SCHEDULING → ask price → TOUR_SCHEDULING unchanged)
- **Engagement bridge:** Book → Engagement created with correct status. Tour flow → state transitions match web behavior.
- **Stall nudge counts:** Per-phase tracking — nudges in PRESENTING don't consume budget for GUARANTEE_PENDING

### SMS Flow Tests

- Text Aircall number → greeting → criteria → matches → select property → deep-dive → question → answer → book → name/email → guarantee link → sign → address → tour request → tour confirmed
- STOP → all outbound ceases. Text again → implicit re-opt-in.
- Quiet hours → proactive messages queued until 9am
- Supplier texts buyer number → generic reply, no routing leak
- Escalation: unanswerable question → email → Reply Tool → SMS + cache
- Re-engagement: silence after results → nudge at 4h → nudge at 24h → no 3rd nudge for that phase

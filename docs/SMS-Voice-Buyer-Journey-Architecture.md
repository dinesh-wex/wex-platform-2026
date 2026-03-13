# SMS & Voice Buyer Journey — System Architecture

Complete reference for the WEx Platform's automated buyer communication system. Covers both SMS (text-based) and Voice (Vapi-powered phone calls) channels, including the 5-agent SMS pipeline, voice tool architecture, cross-channel integration, security hardening, and proactive notification system.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [SMS Pipeline Architecture](#sms-pipeline-architecture)
3. [Voice Pipeline Architecture](#voice-pipeline-architecture)
4. [Cross-Channel Integration](#cross-channel-integration)
5. [Conversation Phases & State Machine](#conversation-phases--state-machine)
6. [Intent Classification (19 Intents)](#intent-classification-19-intents)
7. [Search & Matching](#search--matching)
8. [Proactive Notifications & Background Jobs](#proactive-notifications--background-jobs)
9. [Security Hardening](#security-hardening)
10. [Data Models](#data-models)
11. [Key Files Reference](#key-files-reference)
12. [External Dependencies](#external-dependencies)

---

## System Overview

The buyer journey is driven by an AI agent named **Jess** — a persona that spans both SMS and Voice. Jess handles:

- **Inbound SMS**: Buyers text a number, Jess qualifies their needs, searches inventory, presents matches, and routes to booking.
- **Inbound Voice**: Buyers call, Jess conducts a natural phone conversation with the same flow, sending an SMS follow-up with links after the call.
- **Proactive Outbound**: Background jobs send stall nudges, tour reminders, dormant re-engagement, and waitlist notifications via SMS (never proactive outbound calls).

### Design Principles

1. **Deterministic first, LLM second** — Regex extraction handles 80% of parsing; LLM only for intent classification and response generation.
2. **Fast webhook, slow processing** — Webhooks return 200 immediately; expensive LLM pipelines run in background tasks.
3. **Gate at the data layer** — Sensitive data is stripped from dicts before string construction, not relied on prompt instructions alone.
4. **Timezone-aware quiet hours** — Proactive messages respect 9 PM–9 AM in the buyer's local timezone.
5. **Idempotent everything** — Background jobs, dedup checks, and state updates are all safe to retry.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 async |
| SMS Provider | Aircall (native SMS send endpoint) |
| Voice Provider | Vapi (hosted LLM + ElevenLabs TTS) |
| LLM (SMS agents) | Google Gemini 3 Flash |
| LLM (Voice) | Vapi's hosted model (configured via system prompt + tools) |
| Email Alerts | SendGrid |
| Database | SQLite (dev) / PostgreSQL (prod) |

---

## SMS Pipeline Architecture

### Pipeline Flow

```
INBOUND SMS (Aircall webhook)
    |
[buyer_sms.py] Fast path (<100ms, inline)
    |- Validate Aircall token
    |- Filter: message.received only
    |- Dedup: 30-second window (phone+text hash)
    |- TCPA: STOP/HELP/START keyword handling
    |- Supplier phone detection (PropertyContact match)
    |- Load/create SMSConversationState
    |- Check opted_out flag
    |- Increment turn counter
    |- Record inbound message + commit
    '- Return 200
    |
[buyer_sms.py] Background task (async)
    |
[BuyerSMSOrchestrator.process_message()]
    |
    v
Stage 1: GATEKEEPER (regex)
    |- Spam/abuse validation on inbound message
    |
Stage 2: MESSAGE INTERPRETER (regex, no LLM)
    |- Extract: cities, sqft, features, budget, urgency,
    |  frustration, callback requests, landmarks, addresses,
    |  supplier content signals, positional refs ("option 2"),
    |  link requests ("send me the link")
    |- Output: MessageInterpretation dataclass
    |
Stage 3: CRITERIA AGENT (LLM - Gemini 3 Flash)
    |- Input: MessageInterpretation + conversation history + phase
    |- Output: CriteriaPlan (intent, action, criteria, response_hint)
    |- 19 possible intents, 7 possible actions
    |- Confidence score 0.0-1.0
    |
Stage 4: TOOL EXECUTION (orchestrator logic)
    |- Search: ClearingEngine (with outlier filter, multi-city)
    |- Detail lookup: DetailFetcher (field-specific answers)
    |- Address lookup: geocoding + tier classification
    |- Comparison: side-by-side property data
    |- Engagement status: booking lookup
    |- Waitlist: enrollment via WaitlistService
    |- Tool limit enforcement (rolling 24h window)
    |
Stage 5: RESPONSE AGENT (LLM - Gemini 3 Flash)
    |- Input: intent, phase, criteria, response_hint, match data
    |- Output: Natural SMS reply (max 480 chars follow-up, 800 first msg)
    |- Tone: Professional but warm, like a helpful colleague texting
    |
Stage 6: GATEKEEPER + POLISHER (regex + LLM, max 3 retries)
    |- Validate: no addresses, no PII, no "I'm an AI", max 3 options
    |- Polish: enforce character limits
    |- Fallback: hardcoded template if 3 failures
    |
    v
OUTBOUND SMS (Aircall send)
    |- Send response text
    '- Send photo URLs as follow-up if applicable
```

### The 5 SMS Agents

| # | Agent | Type | Purpose |
|---|-------|------|---------|
| 1 | **Gatekeeper** | Regex | Validates inbound (spam check) and outbound (no addresses, no PII, max 3 options) |
| 2 | **MessageInterpreter** | Regex | Extracts structured data: cities, sqft, features, budget, frustration, landmarks, link requests, etc. 100+ regex patterns |
| 3 | **CriteriaAgent** | LLM | Intent classification + action planning. 19 intents, uses conversation history for context |
| 4 | **ResponseAgent** | LLM | Generates natural SMS reply within tone/length guidelines. Phase-aware, intent-specific guidelines. Greeting fast-path gated by `is_first_message` to prevent mid-conversation resets |
| 5 | **Polisher** | LLM | Enforces character limits while preserving meaning. Only runs if response exceeds max length |

### Fallback Templates

If the Gatekeeper rejects the ResponseAgent's output 3 times, the system falls back to hardcoded templates. Templates cover every intent: `greeting`, `new_search`, `matches_found`, `faq`, `human_escalation`, `reject_results`, `waitlist_offer`, `callback_request`, `lease_modification`, `comparison`, `acknowledgment`, `send_link`, etc.

---

## Voice Pipeline Architecture

### Architecture Overview

Voice uses **Vapi** — a hosted voice AI platform. Unlike SMS's 5-agent pipeline, voice is a single system prompt + tool definitions. Vapi's hosted LLM handles conversation flow; WEx provides tool handlers that execute backend logic.

```
INBOUND CALL (Vapi)
    |
[vapi_webhook.py] assistant-request event
    |- Extract caller_phone + vapi_call_id
    |- Look up Buyer record (for name/personalization)
    |- Fetch 30-day-fresh SMSConversationState (cross-channel seed)
    |- Create VoiceCallState record
    |- Build assistant config:
    |   |- System prompt (persona, beats, FAQ, restrictions)
    |   |- 6 tool definitions
    |   |- Dynamic greeting (based on SMS history)
    |   |- Voice: ElevenLabs "Rachel"
    '- Return config to Vapi
    |
[Vapi hosted LLM runs the call]
    |
[vapi_webhook.py] tool-calls events (1..N during call)
    |- Load VoiceCallState
    |- For each tool call:
    |   |- Route to VoiceToolHandlers method
    |   |- Execute (ClearingEngine, DetailFetcher, etc.)
    |   |- Sanitize via 3-layer data gate
    |   '- Return formatted text to Vapi
    '- Commit state
    |
[vapi_webhook.py] end-of-call-report event
    |- Update call metadata (duration, transcript, recording)
    |- Send follow-up SMS:
    |   |- If search occurred: options link
    |   '- If booking: guarantee link
    '- Batch + send deferred escalation emails
```

### Voice Tools (6)

| Tool | Purpose |
|------|---------|
| `search_properties` | Find warehouse matches by criteria (location, sqft, use_type, timing, budget, features) |
| `lookup_property_details` | Get details on a specific presented option by number |
| `lookup_by_address` | Direct address-based property lookup |
| `send_booking_link` | Create engagement and queue SMS booking link |
| `check_booking_status` | Look up existing engagement status |
| `add_to_waitlist` | Enroll buyer in waitlist for zero-inventory cities |

### Conversation Beats (Voice)

1. **GET NAME** — "Hey, this is Jess from Warehouse Exchange. Who am I speaking with?"
2. **VERIFY PHONE** — Confirm contact number for SMS follow-up
3. **QUALIFY NEEDS** — Location, sqft, use type (with use-type-specific follow-ups like dock doors, temp range)
4. **SEARCH** — Call `search_properties`, present top 3 verbally
5. **DETAILS** — Answer questions about specific options via `lookup_property_details`
6. **COMMITMENT** — Send booking link, confirm SMS receipt

### 3-Layer Voice Data Gate

Prevents sensitive data from reaching Vapi's LLM (and thus the caller):

| Layer | Mechanism | What It Catches |
|-------|-----------|-----------------|
| **Layer 1: Data Gate** | `VOICE_RESTRICTED_FIELDS` frozenset — strips fields from dicts before string construction | `supplier_rate_per_sqft`, `spread_pct`, `owner_email`, `owner_phone`, `owner_name`, `full_address`, `building_size_sqft`, `available_sqft` |
| **Layer 2: Narrative Scrub** | `scrub_narrative_for_voice()` — regex on PropertyInsight free-text strings | Sqft mentions, street addresses, email addresses, phone numbers embedded in prose |
| **Layer 3: Regex Gatekeeper** | `validate_tool_result()` — pattern matching on all tool return strings | Addresses, "available sqft", owner PII patterns, hospitality language. Defense-in-depth |

---

## Cross-Channel Integration

SMS and Voice share the same buyer identity and search context:

### SMS → Voice Seeding

When a buyer who has texted previously calls:
1. Webhook looks up `SMSConversationState` by phone (30-day freshness window)
2. Seeds `VoiceCallState` with: `buyer_id`, `buyer_need_id`, `presented_match_ids`, `known_answers`
3. Dynamic greeting references SMS context: "Hey {name}, I see you were texting about space in {city}..."
4. Voice reuses the SMS `BuyerNeed` if criteria match (same city, sqft within range)

### Voice → SMS Follow-up

After every call:
- If search occurred → SMS with options browsing link
- If booking initiated → SMS with guarantee signing link
- Escalation emails batched and sent at call end

### Shared Services

| Service | Used By |
|---------|---------|
| `ClearingEngine` | SMS orchestrator + Voice tool handlers |
| `DetailFetcher` | SMS orchestrator + Voice tool handlers |
| `WaitlistService` | SMS (via orchestrator) + Voice (via tool handler) |
| `EscalationService` | Both channels for unanswered questions |
| `SMSService` | SMS responses + Voice follow-up messages |

### Waitlist Channel Awareness

`BuyerWaitlist.source_channel` tracks enrollment origin. When inventory opens:
- SMS-enrolled: "Good news! {count} new spaces just opened up in {city}."
- Voice-enrolled: "Hey, remember when you called about space in {city}? {count} new spots just opened up."

---

## Conversation Phases & State Machine

SMS conversations move through these phases (stored on `SMSConversationState.phase`):

```
INTAKE → QUALIFYING → PRESENTING → PROPERTY_FOCUSED → COMMITMENT
                                         |
                                    COLLECTING_INFO
                                         |
                                  GUARANTEE_PENDING
                                         |
                                   TOUR_SCHEDULING

(Any phase) → AWAITING_ANSWER (escalation in progress)
(Any phase) → DORMANT (stalled, multiple nudges sent)
(Any phase) → ABANDONED (inactive 30+ days or 7+ days after dormant)
```

| Phase | What Happens |
|-------|-------------|
| **INTAKE** | First contact. Collecting initial criteria. |
| **QUALIFYING** | Have some criteria, need more (location + sqft + use_type minimum). Criteria readiness scored 0.0–1.0; search triggers at >= 0.8. |
| **PRESENTING** | Search results shown. Buyer can refine, reject, ask details, or commit. |
| **PROPERTY_FOCUSED** | Buyer zeroed in on one property. Detail questions answered via DetailFetcher. |
| **COLLECTING_INFO** | Gathering name/email for commitment. |
| **GUARANTEE_PENDING** | Waiting for buyer to sign guarantee via SMS link. |
| **COMMITMENT** | Engagement created, routing to booking flow. |
| **TOUR_SCHEDULING** | Managing tour date/time preferences. |
| **AWAITING_ANSWER** | Question escalated to supplier, waiting for response. |
| **DORMANT** | Conversation stalled after max nudges. Re-engagement messages sent. |
| **ABANDONED** | Permanently inactive. No further outreach. |

### Criteria Readiness Scoring

Search only triggers when readiness >= 0.8:

| Field | Weight |
|-------|--------|
| Location (city) | 0.30 |
| Square footage | 0.25 |
| Use type | 0.25 |
| Each extra field (timing, features, etc.) | 0.10 |

---

## Intent Classification (19 Intents)

The CriteriaAgent classifies every inbound message into one of 19 intents:

| Intent | Description | Phase Impact |
|--------|-------------|-------------|
| `new_search` | Buyer provides search criteria for the first time | → QUALIFYING or PRESENTING |
| `refine_search` | Buyer adjusts criteria ("cheaper", "bigger", "different city") | Re-search with updated criteria |
| `reject_results` | Buyer dislikes options but gives no new criteria | Stay in PRESENTING, ask what's wrong |
| `facility_info` | Question about a specific property ("does it have dock doors?") | → PROPERTY_FOCUSED |
| `comparison` | "Which one has more parking?" — compare presented options | Fetch asked fields for all matches |
| `tour_request` | "Can I see it?" / "Schedule a tour" | → TOUR_SCHEDULING |
| `commitment` | "I want it" / "Let's book" | → COLLECTING_INFO → COMMITMENT |
| `provide_info` | Buyer provides name, email, or other requested info | Updates state |
| `greeting` | "Hi" / "Hello" — first-contact or re-introduction only | Stay in phase (fast-path greeting only on first message) |
| `acknowledgment` | "Thanks" / "Ok cool" / "Got it" — mid-conversation acknowledgment | Stay in phase, phase-aware warm response |
| `send_link` | "Send me the link" / "Can I get the URL" — buyer wants the browse link | Generate options URL from `search_session_token` |
| `faq` | "Is this free?" / "How does it work?" / "Are you a broker?" | Answer from FAQ knowledge |
| `engagement_status` | "What happened with my booking?" | Look up engagement status |
| `human_escalation` | "Let me talk to a person" / frustration signals | Offer human callback, email team |
| `start_fresh` | "Forget all that, I want to start over" | Reset criteria, back to QUALIFYING |
| `lease_modification` | "I need to change my booking" | Route to team email |
| `callback_request` | "Can someone call me at 3pm?" | Email team with callback request |
| `waitlist_confirm` | "Yes, add me to the waitlist" (only valid after waitlist_offered) | Enroll via WaitlistService |
| `unknown` | Unclassifiable message | Ask for city, size, use type |

### FAQ Knowledge (Embedded in Prompts)

| Topic | What Jess Says |
|-------|---------------|
| **Pricing** | "There's a 6% service fee — but the real value is flexibility. Short-term leases without long-term commitment." |
| **What we are** | "We're a tech-enabled marketplace, not a broker. We match you with verified warehouse space." |
| **How it works** | "Tell me what you need — city, size, use type — and I'll find matching spaces." |
| **Privacy** | "Your information is kept private until you choose to move forward." |
| **Safety** | "Every property is verified. You'll sign a guarantee before we share the full address." |

---

## Search & Matching

### ClearingEngine Integration

When criteria readiness >= 0.8, the orchestrator runs a search:

1. **Single-city search**: Run ClearingEngine with location + sqft + use_type + features
2. **Multi-city search** (up to 3): Run ClearingEngine per city, merge results, tag each with city
3. **Budget conversion**: If buyer gives budget but no sqft, estimate via `MarketRateCache`: `sqft = budget / local_rate`
4. **Landmark geocoding**: "Near LAX" → geocode to lat/lng → radius-based search

### Pricing Outlier Filter

After ClearingEngine returns results:
- Calculate median `buyer_rate` across results
- Exclude any result where `rate > 5x median`
- If filtering removes all results, keep all (don't filter to empty)

### Result Presentation

- Max 3 options per SMS message
- Criteria confirmation on first presentation only (not repeated on follow-ups)
- High-quality single match: "I found one that's a great fit" (don't always show 3)
- Multi-city results grouped by city

### Property Details

When buyer asks about a specific property:
- **DetailFetcher**: Retrieves field-specific answers (dock doors, clear height, etc.)
- **Escalation**: Unknown answers escalated to supplier via email, buyer gets "I'll check on that"
- **PropertyInsight**: AI-powered narrative answers for unmapped questions
- **Comparison mode**: Side-by-side data for all presented matches on asked fields

---

## Proactive Notifications & Background Jobs

### Notification Service (`BuyerNotificationService`)

All proactive outbound SMS flows through `_send_if_allowed()`:
- Checks `opted_out` flag
- Checks quiet hours (9 PM–9 AM in buyer's local timezone via `get_buyer_timezone()`)
- If blocked, returns `False` — caller retries on next tick

### Timezone-Aware Quiet Hours

`get_buyer_timezone()` estimates buyer timezone using two signals:

| Priority | Signal | Source |
|----------|--------|--------|
| 1 | Search city | `criteria_snapshot["city"]` → `CITY_TIMEZONE_MAP` (~60 US warehouse markets) |
| 2 | Phone area code | First 3 digits of phone → `AREA_CODE_TIMEZONE_MAP` (~200 US area codes) |
| 3 | Default | `"America/New_York"` |

### Stall Detection & Re-engagement

Configured via `STALL_RULES` per phase:

| Phase | Delay | Max Nudges |
|-------|-------|-----------|
| PRESENTING | 4 hours | 2 |
| PROPERTY_FOCUSED | 24 hours | 2 |
| GUARANTEE_PENDING | 30 min, then 4 hours | 1 each tier |

After all nudge tiers exhausted + 7 days inactive → DORMANT.
INTAKE/QUALIFYING inactive 30 days → ABANDONED.
DORMANT + 7 days after final nudge → ABANDONED.

### Background Jobs (via SMS Scheduler + Cloud Scheduler)

**SMS Scheduler tick** (every 15 minutes, `POST /api/sms/sms-tick`):

| Step | Job | What It Does |
|------|-----|-------------|
| 1 | `check_stale_conversations` | Send stall nudges for idle conversations |
| 2 | `check_dormant_transitions` | Move stalled conversations to DORMANT |
| 3 | `check_inactivity_abandonment` | Move inactive conversations to ABANDONED |
| 4 | `check_escalation_sla` | Nudge buyer if supplier answer past 24h SLA |
| 5 | `send_tour_reminders` | Remind buyer of tomorrow's tour (timezone-aware, skip if quiet hours) |
| 6 | `send_post_tour_followup` | Follow-up 24h after tour completion (timezone-aware, skip if quiet hours) |

**Cloud Scheduler jobs** (separate endpoints, `POST /api/internal/scheduler/*`):

| Endpoint | Schedule | Purpose |
|----------|----------|---------|
| `/deal-ping-deadlines` | Every 15 min | Expire unanswered deal pings |
| `/deadlines` | Every 15 min | Expire engagements past status deadlines |
| `/qa-deadline` | Hourly | Expire unanswered supplier Q&A |
| `/payment-records` | Nightly | Generate monthly payment records |
| `/payment-reminders` | Daily 12 PM ET | Remind buyers of upcoming payments (timezone-safe) |
| `/stale-engagements` | Daily 8 AM | Flag engagements stuck > 3 days |
| `/auto-activate` | Nightly | Activate leases where onboarding complete + start date reached |
| `/renewal-prompts` | Daily 9 AM | Prompt lease renewals 30 days before end |
| `/check-waitlist` | Periodic | Match waitlist entries against new inventory |

Tour and post-tour reminders were moved to the 15-minute tick because the original daily 6 AM schedule was quiet hours for every US timezone. The tick retries every 15 minutes until the buyer's local time exits quiet hours.

### Event-Driven Notifications

| Event | Message |
|-------|---------|
| Tour confirmed | "Great news, tour confirmed on {date}. I'll remind you." |
| Tour reminder | "Just a reminder — your tour is tomorrow at {time}." |
| Escalation answered | Forward supplier's answer naturally |
| New inventory match (waitlist) | Channel-aware message (see Waitlist section) |

---

## Security Hardening

### Voice Data Leakage Prevention (Wave 5.1)

3-layer defense prevents sensitive data from reaching Vapi's LLM:

- **Layer 1 — Data Gate**: `VOICE_RESTRICTED_FIELDS` frozenset strips 8 fields from all dicts before string construction
- **Layer 2 — Narrative Scrub**: `scrub_narrative_for_voice()` regex-scrubs PropertyInsight free-text for sqft, addresses, emails, phones
- **Layer 3 — Regex Gatekeeper**: `validate_tool_result()` catches literal patterns in final tool result strings

### Cross-Channel Enumeration Prevention (Wave 5.2)

Per-session tool counters prevent inventory cataloging:

| Tool | Voice Limit (per call) | SMS Limit (per 24h) |
|------|----------------------|---------------------|
| `search_properties` | 9 | 15 |
| `lookup_property_details` | 15 | 24 |
| `lookup_by_address` | 6 | 9 |

When limits hit:
- Graceful redirect: "I've shown you quite a few options. Want to narrow down, or I can have our team email you a full summary?"
- Alert email to team via SendGrid (`send_tool_limit_email()`)
- Limits configurable via env vars (e.g., `VOICE_SEARCH_LIMIT=9`)

### SMS-Specific Protections

- **TCPA compliance**: STOP/HELP/START keyword handling at webhook fast path
- **Opt-out enforcement**: `opted_out` flag checked before every outbound message
- **Dedup**: 30-second window prevents Aircall webhook retries from creating duplicate responses
- **Supplier detection**: PropertyContact phone match + content signals ("I have space to list") → redirect to team

### Information Protection Rules (Both Channels)

- Max 3 property options per message/response
- No full addresses (city/area only, like Airbnb)
- No total building size or available sqft
- No supplier rates or margin percentages
- No owner PII (name, email, phone)
- Never reveal AI identity — "I'm Jess from Warehouse Exchange"

---

## Data Models

### SMSConversationState

Primary state tracker for SMS conversations. Key fields:

| Field | Type | Purpose |
|-------|------|---------|
| `phone` | String | Buyer's phone number |
| `phase` | String | Current conversation phase |
| `turn` | Integer | Message count |
| `criteria_readiness` | Float | 0.0–1.0 search readiness score |
| `criteria_snapshot` | JSON | Merged criteria + match summaries at each turn |
| `focused_match_id` | String | Currently discussed property |
| `presented_match_ids` | JSON | All property IDs shown to buyer |
| `known_answers` | JSON | Cached property detail answers |
| `pending_escalations` | JSON | Questions awaiting supplier response |
| `tool_counts` | JSON | Per-tool usage counters (rolling 24h) |
| `tool_counts_reset_at` | DateTime | Rolling window reset timestamp |
| `waitlist_offered` | Boolean | Gate for waitlist_confirm intent |
| `opted_out` | Boolean | TCPA opt-out flag |
| `stall_nudge_counts` | JSON | Per-phase nudge tracking |
| `reengagement_count` | Integer | Dormant re-engagement counter |

### VoiceCallState

Per-call state for voice conversations. Key fields:

| Field | Type | Purpose |
|-------|------|---------|
| `vapi_call_id` | String (unique) | Vapi's call identifier |
| `caller_phone` | String | Inbound phone number |
| `buyer_id` | FK → Buyer | Cross-reference to buyer record |
| `buyer_need_id` | FK → BuyerNeed | Search criteria (may be seeded from SMS) |
| `presented_match_ids` | JSON | Property IDs shown during call |
| `match_summaries` | JSON | Cached summaries for detail lookups |
| `known_answers` | JSON | DetailFetcher answer cache |
| `tool_counts` | JSON | Per-call enumeration counters |
| `pending_escalations` | JSON | Deferred ops emails (sent at call end) |
| `engagement_id` | String | Created if booking initiated |
| `call_transcript` | JSON | Full conversation transcript |

### BuyerWaitlist

Channel-agnostic waitlist entries with 90-day TTL:

| Field | Type | Purpose |
|-------|------|---------|
| `buyer_id` | FK → Buyer | Buyer identity |
| `phone` | String | Contact number |
| `city`, `state` | String | Search location |
| `min_sqft`, `max_sqft`, `use_type` | Various | Search criteria |
| `source_channel` | String | `"sms"` or `"voice"` — determines notification message tone |
| `status` | String | `active`, `matched`, `expired`, `cancelled` |
| `expires_at` | DateTime | 90-day auto-expiry |

### EscalationThread

Tracks unanswered property questions with 24h SLA:

| Field | Type | Purpose |
|-------|------|---------|
| `property_id` | String | Which property |
| `field_key` | String | What question (dock_doors, clear_height, etc.) |
| `status` | String | `pending` or `answered` |
| `sla_deadline_at` | DateTime | 24h from creation |
| `buyer_nudge_sent` | Boolean | Whether past-SLA nudge was sent |
| `answer_raw_text` | Text | Supplier's raw answer |
| `answer_sent_text` | Text | Polished answer sent to buyer |

---

## Key Files Reference

### SMS Pipeline

| File | Purpose |
|------|---------|
| `app/routes/buyer_sms.py` | Aircall webhook entry point. TCPA handling, dedup, state creation, background task dispatch |
| `agents/sms/message_interpreter.py` | Regex-based extraction: cities, sqft, features, budget, frustration, landmarks, link requests (100+ patterns) |
| `agents/sms/criteria_agent.py` | LLM intent classification (19 intents) + action planning via Gemini 3 Flash |
| `agents/sms/response_agent.py` | LLM response generation with phase-aware, intent-specific tone guidelines |
| `agents/sms/contracts.py` | Typed dataclasses: MessageInterpretation, CriteriaPlan, OrchestratorResult |
| `agents/sms/fallback_templates.py` | 34 hardcoded fallback templates for when LLM fails validation |
| `services/buyer_sms_orchestrator.py` | Central orchestrator. Chains all 5 agents, handles search/lookup/commitment, manages phase transitions |

### Voice Pipeline

| File | Purpose |
|------|---------|
| `app/routes/vapi_webhook.py` | Vapi webhook: assistant-request, tool-calls, end-of-call-report |
| `services/vapi_assistant_config.py` | System prompt builder, 6 tool definitions, dynamic greeting |
| `services/voice_tool_handlers.py` | Tool handler implementations (search, lookup, booking, waitlist, status) |
| `agents/voice/gatekeeper.py` | 3-layer data sanitization: VOICE_RESTRICTED_FIELDS, scrub_narrative_for_voice, validate_tool_result |
| `domain/voice_models.py` | VoiceCallState model |

### Shared Services

| File | Purpose |
|------|---------|
| `services/clearing_engine.py` | Core search engine — matches buyer criteria against property inventory |
| `services/sms_service.py` | Aircall SMS send + `check_quiet_hours()` |
| `services/buyer_notification_service.py` | Proactive outbound: stall nudges, dormant transitions, escalation SLA, tour notifications |
| `services/sms_scheduler.py` | 15-minute tick: runs all notification checks + tour/post-tour reminders |
| `services/background_jobs.py` | Daily/periodic jobs: deadlines, payment reminders, stale flagging, auto-activation |
| `services/waitlist_service.py` | Shared waitlist enrollment + matching (both SMS and Voice) |
| `services/timezone_utils.py` | `get_buyer_timezone()` — city map + area code map for quiet hours |
| `services/email_service.py` | SendGrid integration: escalation emails, callback requests, tool limit alerts |
| `domain/sms_models.py` | SMSConversationState, BuyerWaitlist, EscalationThread, SmsSignupToken |

---

## External Dependencies

| Dependency | Status | Details |
|-----------|--------|---------|
| **Aircall** | Connected | SMS send/receive via native endpoint. `sms_service.send_buyer_sms()` |
| **Vapi** | Connected | Voice AI platform. Webhook integration for calls. ElevenLabs TTS |
| **SendGrid** | Connected | Email alerts: escalations, callbacks, tool limits. Sends to `dev@warehouseexchange.com` |
| **Google Gemini 3 Flash** | Connected | LLM for SMS CriteriaAgent + ResponseAgent |
| **MarketRateCache** | Available | `MarketRateAgent.get_nnn_rates(zipcode)` — Gemini + Search grounding, 30-day cache. Used for budget-to-sqft conversion |
| **Property Images** | Public URLs | `primary_image_url` and `image_urls` — publicly accessible CDN links |

No external API credentials, templates, or infrastructure beyond the above is needed. Everything is already connected and operational.

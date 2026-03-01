# WEx Voice Agent — Development Summary

> Complete documentation of the Voice Agent system built for the WEx Platform (Feb–Mar 2026).
> Handles inbound buyer calls via Vapi voice AI, qualifying needs and presenting warehouse options through natural conversation. Follow-up links sent via SMS.

---

## Architecture Overview

The Voice Agent uses **Vapi.ai** as the real-time voice layer (STT + LLM + TTS) while our backend handles business logic through **Vapi tool calls**. Unlike SMS's 6-agent pipeline, voice uses a **hybrid architecture**: Vapi's cloud LLM handles conversation flow, while our backend runs mini-pipelines on each tool invocation.

```
Inbound Call (Aircall → Vapi phone number)
  │
  ▼
┌───────────────────────────────────────────────────────────────┐
│  Vapi Cloud                                                    │
│                                                                │
│  1. STT (Speech-to-Text) — transcribes caller speech          │
│  2. LLM (Gemini 3 Flash Preview) — conversation brain         │
│     - System prompt defines WEx broker persona                 │
│     - Decides when to call tools based on conversation         │
│  3. TTS (ElevenLabs) — speaks responses naturally              │
│                                                                │
│  Tool Calls ──────────────────────────────────────┐            │
└───────────────────────────────────────────────────┼────────────┘
                                                    │
  ┌─────────────────────────────────────────────────┘
  │
  ▼
┌───────────────────────────────────────────────────────────────┐
│  WEx Backend (FastAPI)                                         │
│  POST /api/voice/webhook                                       │
│                                                                │
│  Event: assistant-request                                      │
│    → Create VoiceCallState → Return assistant config            │
│                                                                │
│  Event: tool-calls                                             │
│    → VoiceToolHandlers pipeline:                               │
│      search_properties  → Geocode → ClearingEngine → Gate     │
│      lookup_details     → DetailFetcher → Escalation → Gate   │
│      send_booking_link  → EngagementBridge → Token → Queue    │
│                                                                │
│  Event: end-of-call-report                                     │
│    → Store transcript + recording → Send follow-up SMS         │
└───────────────────────────────────────────────────────────────┘
  │
  ▼
Follow-up SMS (Aircall API) — booking link or options link
```

### Call Routing

```
Caller → Aircall number → Forward to Vapi number (+1 424-287-3916)
  → Vapi sends assistant-request to our webhook
  → We return dynamic assistant config (no pre-built assistant in Vapi dashboard)
  → Conversation begins
```

All calls to Aircall forward directly to Vapi. No live agent ring-first, no overflow routing.

---

## Agent Mapping: SMS vs Voice

| SMS Agent | Voice Equivalent | Where it Runs |
|-----------|-----------------|---------------|
| Message Interpreter (regex) | Not needed — Vapi's LLM extracts params into tool args | Vapi cloud |
| Criteria Agent (LLM) | System prompt + tool param validation | Split: Vapi (intent) + Backend (validation) |
| Response Agent (LLM) | Vapi's LLM + system prompt | Vapi cloud |
| Gatekeeper (deterministic) | `VoiceGatekeeper` — validates tool results before returning to Vapi | Backend |
| Polisher Agent (LLM) | Not needed — no character limits, Vapi LLM handles tone | N/A |
| Tool Execution | `VoiceToolHandlers` — search, detail, booking pipelines | Backend |
| Escalation Service | Same `EscalationService` — follows up via SMS | Backend |

---

## File Layout

### Voice-Specific Files (New)

| File | Type | Purpose |
|------|------|---------|
| `app/routes/vapi_webhook.py` | Route | Single webhook `POST /api/voice/webhook` — dispatches `assistant-request`, `tool-calls`, `end-of-call-report` |
| `services/voice_tool_handlers.py` | Service | `VoiceToolHandlers` class with 3 tool pipelines: `search_properties`, `lookup_property_details`, `send_booking_link` |
| `services/vapi_assistant_config.py` | Config | Builds Vapi assistant JSON (system prompt, tool defs, voice config) + auto-registers phone number on startup |
| `agents/voice/gatekeeper.py` | Deterministic | `VoiceGatekeeperResult` — validates tool output: no addresses, no PII, no building sizes, terminology check, max 3 options |
| `domain/voice_models.py` | Model | `VoiceCallState` — per-call state tracking (caller, buyer, search results, escalations, transcript, recording) |
| `clear_voice_data.py` | Script | Testing utility to wipe voice call data (all or per-phone) |

### Existing Services Reused (No Changes)

| Service | Usage in Voice |
|---------|---------------|
| `clearing_engine.py` | `ClearingEngine.run_clearing()` — property matching |
| `sms_detail_fetcher.py` | `DetailFetcher.fetch_by_topics()` — property info lookup |
| `escalation_service.py` | `EscalationService.check_and_escalate()` — unanswerable questions |
| `engagement_bridge.py` | `EngagementBridge.initiate_booking()` — create engagement |
| `sms_token_service.py` | `SmsTokenService.create_guarantee_token()` — booking link |
| `sms_service.py` | `SMSService.send_buyer_sms()` — end-of-call SMS delivery |
| `geocoding_service.py` | `geocode_location()` — convert city to lat/lng |
| `context_builder.py` | `build_match_summaries()` — format match data |
| `field_catalog.py` | `get_label()`, `FIELD_CATALOG` — field display names |

### Modified Files

| File | Change |
|------|--------|
| `app/config.py` | Added 4 Vapi settings: `vapi_api_key`, `vapi_server_secret`, `vapi_phone_number_id`, `vapi_voice_id` |
| `app/main.py` | Register voice router + call `register_vapi_phone_number()` on startup |
| `infra/database.py` | Import `voice_models` in `init_db()` + migration statements for new columns |
| `domain/sms_models.py` | `EscalationThread.conversation_state_id` FK relaxed (supports voice state IDs), added `source_type` column |
| `services/sms_detail_fetcher.py` | Added `label=` to all `DetailFetchResult` constructors |

---

## Data Model: VoiceCallState

Table: `voice_call_states`

| Column | Type | Purpose |
|--------|------|---------|
| `id` | String(36) PK | UUID |
| `vapi_call_id` | String(100) unique | Vapi's call identifier |
| `caller_phone` | String(50) indexed | Caller's phone from caller ID |
| `verified_phone` | String(50) | Confirmed SMS number (may differ from caller_phone) |
| `buyer_id` | FK → buyers | Links to shared Buyer table |
| `conversation_id` | FK → buyer_conversations | Chat log reference |
| `buyer_need_id` | FK → buyer_needs | Space requirement |
| `buyer_name` | String(200) | Collected during call |
| `buyer_email` | String(255) | Only if buyer requests email delivery |
| `presented_match_ids` | JSON | Property IDs shown (for option number resolution) |
| `match_summaries` | JSON | Cached match data for mid-call detail lookups |
| `search_session_token` | String(64) | Token for options link |
| `known_answers` | JSON | DetailFetcher answer cache |
| `answered_questions` | JSON | Escalation answer tracking |
| `pending_escalations` | JSON | Active escalation threads |
| `engagement_id` | String(36) | Engagement created via booking |
| `guarantee_link_token` | String(64) | Token for booking link SMS |
| `call_started_at` | DateTime | When call began |
| `call_ended_at` | DateTime | When call ended |
| `call_duration_seconds` | Integer | Call length |
| `call_summary` | Text | Vapi-generated summary |
| `call_transcript` | JSON | Full conversation transcript |
| `recording_url` | String(500) | Vapi call recording URL |
| `sms_sent` | Boolean | Whether follow-up SMS was sent |
| `follow_up_preference` | String(20) | "text" (default) or "callback" |

### Shared Buyer Data

All channels (voice, SMS, web) share the same `buyers` table. Voice creates/finds a Buyer by phone number. Channel-specific state lives in separate tables:

```
buyers (shared — all channels)
  ├── buyer_needs
  ├── buyer_conversations
  ├── engagements
  │
  ├── sms_conversation_states  (SMS channel state)
  └── voice_call_states         (Voice channel state)
```

---

## Tool Pipelines

### 1. `search_properties(location, sqft, use_type, timing, duration, features)`

```
Validate params
  → Get/create Buyer by phone
  → Create BuyerNeed with criteria
  → Geocode location (Google Maps)
  → ClearingEngine.run_clearing() → tier1 matches
  → build_match_summaries() → formatted data
  → Create SearchSession with token
  → Cache presented_match_ids + match_summaries on VoiceCallState
  → VoiceGatekeeper validates output
  → Return text: "I found 3 options. Option 1 is in Detroit at $0.95/sqft..."
```

### 2. `lookup_property_details(option_number, topics)`

```
Resolve option_number → property_id via presented_match_ids
  → DetailFetcher.fetch_by_topics(property_id, topics, state)
  → Separate answered vs needs_escalation
  → For answered: format naturally
  → For needs_escalation:
      EscalationService.check_and_escalate()
        → Layer 1: Check known_answers cache → hit? return
        → Layer 2: Check answered_questions → hit? return
        → Layer 3: Check existing threads → active? skip
        → Create EscalationThread (pending, 2hr SLA)
      → Return: "I'll check with the warehouse owner and text you back"
  → VoiceGatekeeper validates output
```

### 3. `send_booking_link(option_number, buyer_name, buyer_email=None)`

```
Resolve option_number → property_id
  → Store buyer_name + buyer_email on VoiceCallState
  → EngagementBridge.initiate_booking(property_id, phone, name)
  → SmsTokenService.create_guarantee_token()
  → Store guarantee_link_token on VoiceCallState
  → Return: "I've set that up. I'll text you a link after this call."
  (SMS sent in end-of-call-report handler, not immediately)
```

---

## Voice Conversation Flow

```
Call connects → assistant-request webhook → create VoiceCallState → return config

Agent: "Hey there, thanks for calling Warehouse Exchange.
        I help businesses find warehouse space. What's your name?"

Caller: "Hi, I'm Mike"

Agent: "Hey Mike! And just to make sure, is this the best number
        to reach you by text?"

Caller: "Yeah this is my cell"

Agent: "So tell me — what city are you looking in, how much space
        do you need, and what will you use it for?"

Caller: "About 10,000 sqft in Detroit for fulfillment.
         Need dock doors too."

Agent: "Got it. Do you need office space in there too?
        And how about parking — is that important?"

Caller: "Office would be nice. Parking not critical."

Agent: "How soon do you need it, and how long are you thinking?"

Caller: "Within a month, probably 6 months."

  → Vapi calls search_properties(location="Detroit", sqft=10000,
     use_type="fulfillment", features=["dock_doors", "office"],
     timing="30_days", duration="6_months")

Agent: "I found 3 options. Option 1 is in Detroit at 95 cents
        per square foot, about $9,500 a month, with 4 dock doors
        and office space. Option 2 is in Dearborn..."

Agent: "If any of these sound good, I can text you the details
        so you can check them out — want me to send those over?"

Caller: "Yeah, send them over."

  → Vapi calls send_booking_link(option=1, name="Mike")

Agent: "All set Mike. I'll text you a link right after this call.
        Anything else?"

Caller: "No that's it, thanks!"

Agent: "Great talking with you Mike. Look for that text. Bye!"

  → end-of-call-report webhook:
    → Store transcript + recording
    → Send SMS: "Hey Mike, here's the link to complete your
      warehouse booking: {url}"
```

---

## Escalation Flow

When a buyer asks something not in the database:

```
Caller: "Does it have 24/7 access?"
  → Vapi calls lookup_property_details(option=1, topics=["access_hours"])
  → DetailFetcher → field not in DB → needs_escalation=True
  → EscalationService.check_and_escalate()
    → Check caches → miss → Create EscalationThread (2hr SLA)
  → Return: "I don't have that on file. I'll check and text you back."

(Later: ops answers via /api/sms/internal/reply/{thread_id})
  → EscalationService.record_answer() → caches answer
  → SMS to buyer: "Hey Mike, got an answer on 24/7 access:
    Yes, the facility has 24/7 keycard access."
```

Same `EscalationThread` model and `EscalationService` as SMS. The `source_type` column distinguishes voice vs SMS escalations.

---

## VoiceGatekeeper

Validates all tool results before returning to Vapi's LLM. Unlike SMS gatekeeper, has **no character limit**.

| Rule | Action |
|------|--------|
| Full street addresses | Redacted → "[address redacted]" |
| Total building size / available sqft | Flagged |
| Owner PII (email, phone, name) | Flagged |
| More than 3 options | Flagged |
| Hospitality terms ("book a stay", "hotel") | Auto-replaced with warehouse terms |

---

## System Prompt

Located in `vapi_assistant_config.py:_build_system_prompt()`. Key rules:

- **Persona**: Friendly warehouse broker — not a robot, not an AI
- **Name-first**: Ask name at start, use it 2-3 times during call
- **Batch qualifying**: Ask location + size + use type first, then office space + parking + timing + duration
- **Feature priority**: Ask about office space first (most common), then parking, then others
- **All 3 options**: Present all matches with pricing, not just the best
- **No option picking**: After presenting options, offer to send them all ("want me to text you these?"), don't ask which one
- **Phone verification**: Confirm caller ID is the right SMS number
- **No URLs in speech**: Always "I'll text you the link"
- **Terminology**: "lease/space/warehouse" never "stay/accommodation/hotel"
- **Say "square feet"** not "sqft" (voice clarity)

---

## Configuration

### Environment Variables (`.env`)

```env
# Vapi Voice Agent
VAPI_API_KEY=<Private API Key from Vapi dashboard>
VAPI_PHONE_NUMBER_ID=bb4c3eb8-863e-4ca0-b5be-02b65556d94d
VAPI_SERVER_SECRET=         # Optional: webhook HMAC validation (leave empty for dev)
VAPI_VOICE_ID=              # Optional: ElevenLabs voice ID (leave empty for "Rachel" default)
```

### Config Settings (`app/config.py`)

```python
vapi_api_key: str = ""           # Vapi Private API Key
vapi_server_secret: str = ""     # Webhook signature secret (optional)
vapi_phone_number_id: str = ""   # Vapi phone number UUID
vapi_voice_id: str = ""          # ElevenLabs voice ID override
```

### Models Used

| Component | Provider | Model |
|-----------|----------|-------|
| Conversation brain (LLM) | Google | `gemini-3-flash-preview` |
| Voice (TTS) | ElevenLabs | "Rachel" (`21m00Tcm4TlvDq8ikWAM`) or custom via `VAPI_VOICE_ID` |
| Speech-to-text (STT) | Vapi default | Deepgram (Vapi's default) |

### Call Limits

| Setting | Value |
|---------|-------|
| Max call duration | 10 minutes (600s) |
| Silence timeout | 30 seconds |
| Recording | Enabled |

---

## Auto-Registration

On backend startup, `register_vapi_phone_number()` automatically PATCHes the Vapi API to point the phone number's webhook to our server:

```
PATCH https://api.vapi.ai/phone-number/{VAPI_PHONE_NUMBER_ID}
{
  "server": {
    "url": "{FRONTEND_URL}/api/voice/webhook"
  }
}
```

This means:
- No manual Vapi dashboard configuration needed for the server URL
- Tunnel URL updates automatically when you restart with a new Cloudflare tunnel
- Skips silently if `VAPI_API_KEY` is empty (dev without credentials)

---

## End-of-Call SMS Logic

After the call ends, Vapi sends an `end-of-call-report` event. The handler:

1. Stores `call_summary`, `call_transcript`, `recording_url`, `call_duration_seconds`
2. Determines which SMS to send:
   - If `guarantee_link_token` exists → booking link SMS
   - Else if `search_session_token` exists → options link SMS
   - Else → no SMS (general inquiry)
3. Sends via `SMSService.send_buyer_sms()` (same Aircall API as SMS channel)

---

## Testing

### Clear Voice Data (Reset for Testing)

```bash
# Clear ALL voice call data
conda run -n wex python clear_voice_data.py

# Clear for a specific phone number
conda run -n wex python clear_voice_data.py --phone "+14157661133"
```

This deletes `voice_call_states` and related `escalation_threads` so you can test end-to-end without leftover state.

### Manual Test Flow

1. Start backend: `conda run -n wex python -m uvicorn wex_platform.app.main:app --reload --port 8000`
2. Start Cloudflare tunnel: `cloudflared tunnel --url http://localhost:3000`
3. Update `FRONTEND_URL` in `.env` to the tunnel URL
4. Restart backend (auto-register updates Vapi with new tunnel URL)
5. Call the Vapi number (+1 424-287-3916) directly or via Aircall forwarding
6. Test: greeting → name → qualify → search → details → booking → end-of-call SMS
7. Verify in DB: `voice_call_states` has transcript, recording, buyer link

### Verify Backend Logs

On startup you should see:
```
Vapi phone number registered with server URL: https://{tunnel}.trycloudflare.com/api/voice/webhook
```

On inbound call:
```
Vapi webhook: event_type=assistant-request
Vapi webhook: event_type=tool-calls
Tool call: search_properties({...}) call_id=...
Vapi webhook: event_type=end-of-call-report
Sent follow-up SMS to +1...
```

---

## Vapi Dashboard Setup

Minimal configuration required — most is handled by auto-registration:

1. **Phone Number**: +1 (424) 287-3916 (Vapi-provided)
2. **Server URL**: Auto-set by backend on startup (or manually paste `{tunnel_url}/api/voice/webhook`)
3. **Assistant**: Leave empty — do NOT select an assistant. We use transient/dynamic assistants via `assistant-request`
4. **Credentials**: Ensure Google (Gemini) and ElevenLabs API keys are configured in Vapi's provider settings
5. **No workflows needed**

---

## Known Limitations / Future Work

- **Greeting**: Current greeting is generic — may want to customize based on testing
- **Voice selection**: Using default "Rachel" — evaluate other ElevenLabs voices for brand fit
- **Outbound calls**: Not implemented — current system is inbound only
- **Call transfer**: No live agent transfer option yet (all escalations go to SMS follow-up)
- **Multi-language**: English only
- **Concurrent calls**: Each call gets its own VoiceCallState; no shared session issues

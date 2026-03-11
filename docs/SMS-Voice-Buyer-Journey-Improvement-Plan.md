# SMS & Voice Buyer Journey — Comprehensive Improvement Plan

## Context

The current SMS/Voice system handles the core search-and-book flow well, but real-world callers bring scenarios outside that flow: returning callers, platform questions, supplier misroutes, frustrated users, and budget-based searches. These gaps make the experience feel "bot-like." This plan addresses every identified gap plus additional UX improvements to make conversations feel natural and human.

## External Dependencies (Already In Place — No New Setup Needed)

| Dependency | Status | Details |
|-----------|--------|---------|
| **SendGrid** | Connected | `email_service.py` with `send_escalation_email()` pattern. Sends to `dev@warehouseexchange.com` |
| **MarketRateCache** | Available | `MarketRateAgent.get_nnn_rates(zipcode)` — Gemini + Search grounding, 30-day cache. Also has `get_nearby_cached_rate()` fallback |
| **Property images** | Public URLs | `primary_image_url` and `image_urls` are publicly accessible CDN links, can be sent directly in SMS |
| **Supplier listing page** | Exists | `warehouseexchange.com/list` is live |
| **Aircall SMS** | Connected | Native send endpoint via `sms_service.send_buyer_sms()` |

**No new external files, templates, or API credentials needed.** All infrastructure exists.

---

## Wave 1: Quick Wins (High Impact, Low Effort)

### 1.1 — FAQ / Platform Knowledge

**Problem**: "Is this free?", "How does it work?", "Are you a broker?" → falls to `unknown` intent.

**Files to modify**:
- `agents/sms/criteria_agent.py` — Add `"faq"` intent to prompt template (line ~30-40)
- `agents/sms/response_agent.py` — Add FAQ response guideline (line ~189-196)
- `agents/sms/fallback_templates.py` — Add `"faq"` template
- `services/buyer_sms_orchestrator.py` — Add `elif plan.intent == "faq": pass` (stays in current phase, response agent handles it)
- `services/vapi_assistant_config.py` — Add FAQ HANDLING section to system prompt

**FAQ knowledge to embed** (in both CriteriaAgent prompt and Voice system prompt):
- **Pricing**: "There's a 6% service fee — but the real value is flexibility. You get short-term leases without the long-term commitment that traditional warehousing requires."
- **What we are**: "We're a tech-enabled marketplace, not a traditional broker. We match you with verified warehouse space and handle the coordination."
- **How it works**: "Tell me what you need — city, size, use type — and I'll find matching spaces. You can tour first or book instantly depending on the property."
- **Privacy**: "Your information is kept private until you choose to move forward with a specific property."
- **Safety/legitimacy**: "Every property on our platform is verified. You'll sign a guarantee before we share the full address, which protects both sides."
- After answering, naturally transition back: "What city are you looking in?"

---

### 1.2 — Photo Sharing via SMS

**Problem**: `Property.primary_image_url` and `Property.image_urls` exist but are never sent to buyers.

**Files to modify**:
- `agents/sms/contracts.py` — Add `photo_urls: list[str] | None = None` to `OrchestratorResult`
- `services/buyer_sms_orchestrator.py` — When transitioning to PRESENTING phase, attach `primary_image_url` from top match to result
- `app/routes/buyer_sms.py` — After sending response text, send photo as follow-up if `result.photo_urls`
- `agents/sms/response_agent.py` — Add guideline: "If a photo is being sent, mention it: 'Sending you a photo of the top match.'"
- `agents/sms/message_interpreter.py` — Add "photo", "picture", "image", "what does it look like" to topics detection
- `services/vapi_assistant_config.py` — Add to system prompt: "If they ask to see photos, tell them you'll include photos in the text after the call"

**SMS sending approach**: Include image URL as a clickable link in SMS body (Aircall native SMS may not support MMS). Format: `"Here's a photo: {image_url}"`

**Smart photo timing** (UX enhancement):
- Send main photo only when PRESENTING matches (not during qualification)
- In PROPERTY_FOCUSED phase, if buyer asks for "more photos", send up to 3 from `image_urls` array
- Voice: mention photos in end-of-call SMS alongside the options link

---

### 1.3 — Engagement Status Lookup

**Problem**: "What happened with my booking?" / "Did the owner accept?" → not handled.

**Files to modify**:
- `agents/sms/criteria_agent.py` — Add `"engagement_status"` intent with examples
- `services/buyer_sms_orchestrator.py` — Add status lookup logic using `state.engagement_id` → query `Engagement` table → map status to human-friendly text
- `agents/sms/response_agent.py` — Add guideline for natural status reporting
- `services/vapi_assistant_config.py` — Add `check_booking_status` tool definition (no params)
- `services/voice_tool_handlers.py` — Add `check_booking_status()` method (queries Engagement by `call_state.buyer_id` or `call_state.engagement_id`)
- `app/routes/vapi_webhook.py` — Add `elif tool_name == "check_booking_status"` to dispatch

**Status-to-message mapping** (natural language, not status codes):
| Status | What Jess says |
|--------|---------------|
| `account_created` | "Your account is set up. We're coordinating with the property owner." |
| `guarantee_signed` | "All set — your guarantee is signed and you should have the address." |
| `tour_requested` | "Tour's been requested. You should have a confirmation coming soon." |
| `tour_confirmed` | "Tour confirmed for {date}. You're all set!" |
| `agreement_sent` | "Lease agreement was sent to your email — check your inbox." |
| `declined_by_supplier` | "Unfortunately the owner went another direction. Want me to find alternatives?" |
| `cancelled` | "That one was cancelled. Want to start a new search?" |

---

### 1.4 — Budget-to-Sqft Conversion

**Problem**: "$8k/month" is not extracted or converted to sqft.

**Files to modify**:
- `agents/sms/contracts.py` — Add `budget_monthly: int | None = None` to `MessageInterpretation`
- `agents/sms/message_interpreter.py` — Add regex: `$8k/month`, `$8,000/mo`, `$5000 per month`, `budget of $X`
- `agents/sms/criteria_agent.py` — Add budget as alternative to sqft in prompt; add `budget_monthly` to criteria schema
- `services/buyer_sms_orchestrator.py` — When `budget_monthly` set + location known + no sqft: query `MarketRateCache` for area rate → `estimated_sqft = budget / rate`. Add to merged_criteria
- `services/vapi_assistant_config.py` — Add `budget_monthly` (integer, optional) to `search_properties` tool definition
- `services/voice_tool_handlers.py` — Handle `budget_monthly` param in `search_properties()`: do same MarketRateCache conversion
- Voice system prompt: "If they give a budget instead of square footage, work with that — ask the city and I'll estimate the size"

**Existing infrastructure**: `MarketRateAgent.get_nnn_rates(zipcode)` in `agents/market_rate_agent.py` — queries cache first (30-day TTL), falls back to Gemini with Search grounding. Also has `get_nearby_cached_rate(zipcode)` for fuzzy zip matching. Conversion formula: `estimated_sqft = budget_monthly / ((nnn_low + nnn_high) / 2)`.

---

### 1.5 — Supplier Content Detection

**Problem**: "I have a warehouse to list" in message body → treated as confused buyer. Current detection (buyer_sms.py line ~161) only checks `PropertyContact.phone`, misses content-based signals.

**Files to modify**:
- `agents/sms/message_interpreter.py` — Add `SUPPLIER_KEYWORDS` regex for "list my warehouse", "I'm an owner", "I have space to rent out", "want to list", "looking for tenants"
- `agents/sms/contracts.py` — Add `is_supplier_content: bool = False` to `MessageInterpretation`
- `services/buyer_sms_orchestrator.py` — Add early exit before CriteriaAgent call: if `interpretation.is_supplier_content`, return redirect response
- `agents/sms/fallback_templates.py` — Add `"supplier_inquiry"` template
- `services/vapi_assistant_config.py` — Add SUPPLIER DETECTION section to system prompt

**SMS flow**:
1. Jess responds: "Got it — it sounds like you have space available. Let me have our team reach out to you. Is this the best number to reach you?"
2. Email `dev@warehouseexchange.com` via SendGrid (same pattern as escalation emails) with: phone number, message content, timestamp
3. Team follows up manually through SMS (appears to come from Jess) or eventually routes to a Supplier AI on a separate number

**Voice flow**: Jess says "That's great — I'll have our supplier team reach out to you. Is this the best number?" and the end-of-call handler emails the team.

**Future**: Build a Supplier AI that Jess can hand off to directly when supplier intent is detected.

---

## Wave 2: Conversation Intelligence (Medium Effort)

### 2.1 — Returning Caller Recognition

**Problem**: Buyer texts back after hours/days and system doesn't acknowledge prior context.

**Files to modify**:
- `services/buyer_sms_orchestrator.py` — At start of `process_message`, detect time gap (>7 days since `last_buyer_message_at` + turn > 2 + has `criteria_snapshot`). Generate contextual welcome-back response_hint
- `agents/sms/criteria_agent.py` — Add `"returning_buyer"` intent
- `agents/sms/response_agent.py` — Add guideline: "For returning buyers, briefly acknowledge their prior search before continuing"

**UX approach** (think like a real broker — don't over-acknowledge short gaps):
- Under 7 days: Continue naturally, no special handling. They're still in the same search journey.
- 7–30 days: "Hey, welcome back! Still looking at those options in {city}?"
- Over 30 days: "Hey {name}, good to hear from you again. Last time you were looking for space in {city}. Want to pick up where we left off, or start fresh?"
- If they have active engagement: skip to engagement status

**Voice**: Already partially implemented via SMS context seeding in `vapi_webhook.py`. Enhancement: add time-gap awareness to `build_assistant_config()` first message.

---

### 2.2 — Proactive Use-Type Qualification

**Problem**: "Distribution center" should trigger dock doors/ceiling height questions. Currently all use types get generic "any deal-breakers?" question.

**Files to modify**:
- `agents/sms/criteria_agent.py` — Add USE-TYPE FOLLOW-UP section to prompt with conditional questions
- `services/buyer_sms_orchestrator.py` — In qualifying question logic (line ~277), replace generic deal-breakers with use-type-specific questions
- `services/vapi_assistant_config.py` — Update Beat 2 to be use-type aware

**Use-type → question mapping**:
| Use Type | Proactive Questions |
|----------|-------------------|
| distribution/fulfillment | "How many dock doors do you need? What clear height?" |
| cold_storage | "What temperature range? Refrigerated or frozen?" |
| manufacturing | "What kind of power supply? Any floor load requirements?" |
| light_assembly | "Do you need office space in there? Power requirements?" |
| storage | "Do you need climate control? Drive-in access?" |
| (default) | "Do you need office space or parking? Any must-haves?" |

---

### 2.3 — Sentiment Detection + Human Escalation Path

**Problem**: Frustrated callers have no out. No "let me connect you with someone" capability.

**Files to modify**:
- `agents/sms/message_interpreter.py` — Add `FRUSTRATION_PATTERNS` regex for: "speak to a person", "real person", "this isn't working", "frustrated", "waste of time"
- `agents/sms/contracts.py` — Add `frustration_detected: bool = False` and `wants_human: bool = False` to `MessageInterpretation`
- `services/buyer_sms_orchestrator.py` — Add early handler: if frustrated, offer human help; if they confirm, route to support
- `agents/sms/criteria_agent.py` — Add `"human_escalation"` intent
- `services/vapi_assistant_config.py` — Add FRUSTRATION HANDLING section: "If the caller sounds frustrated, acknowledge it. If they ask for a person, offer to have someone call them back."

**SMS response**: "I hear you, and I'm sorry for the trouble. I can have one of our team members reach out to you directly — would that help?"

**When buyer confirms**: Send team notification email via `email_service.py` (same SendGrid pattern as escalation emails) to `dev@warehouseexchange.com` with buyer phone, name, conversation context, and reason for escalation. Then confirm: "Got it — someone from our team will reach out shortly."

**Voice**: Jess naturally handles this via the system prompt — "If they ask for a person, offer to have someone from the team call them back. Note the preference."

---

### 2.4 — Micro-Confirmations Before Search

**Problem**: System searches immediately after extracting criteria without confirming what it understood.

**Files to modify**:
- `agents/sms/response_agent.py` — Update PRESENTING MATCHES guideline: "Always start by confirming what you understood: 'Looking for ~10k sqft in Dallas for distribution — here's what I found...' This replaces the separate confirmation step."

**UX approach**: Confirm WHILE presenting (not as a separate back-and-forth step). This avoids adding friction while still giving the buyer a chance to correct misunderstandings. The confirmation is woven into the match presentation message.

---

## Wave 3: Advanced Features (Higher Effort)

### 3.1 — Multi-Location Search

**Problem**: "I need space in both Dallas and Houston" → only searches first city.

**Files to modify**:
- `agents/sms/criteria_agent.py` — Support `"locations": ["city1", "city2"]` in criteria schema
- `services/buyer_sms_orchestrator.py` — In `_run_search`, detect multiple locations → run ClearingEngine per location (max 3) → merge results → tag each match with its city
- `agents/sms/response_agent.py` — Format multi-market results: "Found options in both cities..."
- `services/vapi_assistant_config.py` — Add `locations` array param to `search_properties` tool

**Note**: `MessageInterpreter.cities` already extracts multiple cities. The gap is purely downstream.

---

### 3.2 — Callback Requests (Team Notification via SendGrid)

**Problem**: "Call me back at 3pm" → nothing happens.

**Approach**: Don't build outbound calling. Instead, email the team via the existing SendGrid integration (`email_service.py`) so a human can call the buyer back. Reuse the `send_escalation_email()` pattern.

**New function** in `services/email_service.py`:
- `send_callback_request_email(data: dict) -> bool` — sends email to `dev@warehouseexchange.com` with buyer phone, name, requested time, conversation context

**Files to modify**:
- `agents/sms/message_interpreter.py` — Add time extraction regex for callback requests ("call me back at 3pm", "can someone call me")
- `agents/sms/criteria_agent.py` — Add `"callback_request"` intent
- `services/buyer_sms_orchestrator.py` — Handle callback intent: extract requested time, send team notification email, confirm to buyer
- `services/vapi_assistant_config.py` — System prompt: "If they ask for a callback, note the time, confirm, and let them know someone from the team will call them."

**No new models needed.** Email notification is fire-and-forget using existing SendGrid client.

---

### 3.3 — Waitlist / Inventory Notifications

**Problem**: "Nothing in Carson? Let me know if something opens up" → no mechanism.

**New files**:
- `services/waitlist_service.py` — **Shared service** (lives in `services/`, not `agents/sms/`). Both SMS and Voice funnel into the same enrollment logic. Methods: `add_to_waitlist()`, `check_waitlist_matches()` (periodic job)
- New model `BuyerWaitlist` in `domain/sms_models.py` (placed here for FK CASCADE ordering against `buyers` table, but the model itself is channel-agnostic)

**BuyerWaitlist model** should include a `channel` column (`"sms"` or `"voice"`) so the notification job can pick the right message template:
- Voice-enrolled: "Hey, remember when you called about space in Carson? A new 12k sqft spot just opened up — want to take a look?"
- SMS-enrolled: "Good news — a new 12k sqft space just opened in Carson. Want to take a look?"

**SMS files to modify**:
- `services/buyer_sms_orchestrator.py` — When search returns 0 matches, offer waitlist. Double-guard enrollment: `waitlist_confirm` intent only accepted when `state.waitlist_offered == True`
- Periodic job: when new property activates, run ClearingEngine against active waitlist entries, send SMS notifications using channel-aware templates

**Voice files to modify** (cross-channel waitlist enrollment):
- `services/vapi_assistant_config.py` — Add `add_to_waitlist(city, sqft_needed, use_type)` tool definition + `## WAITLIST` section in system prompt: "If the search returns no results, offer to add them to the waitlist: 'Nothing available right now, but I can notify you the moment something opens up in that area. Want me to do that?'"
- `services/voice_tool_handlers.py` — Add `handle_add_to_waitlist()` handler that delegates to shared `WaitlistService`
- `app/routes/vapi_webhook.py` — Add `elif tool_name == "add_to_waitlist"` to tool dispatch

**Note**: Notifications when inventory opens always go out via SMS (can't proactively call someone). The `channel` column ensures the notification text references the original interaction correctly.

---

### 3.4 — Lease Modification Routing

**Problem**: "I need to change my booking" → not handled.

**Files to modify**:
- `agents/sms/criteria_agent.py` — Add `"lease_modification"` intent
- `services/buyer_sms_orchestrator.py` — Route to human support with context

**Response**: "For lease changes, I'll connect you with our team. Email support@warehouseexchange.com with the details, or I can have someone call you."

---

### 3.5 — Contextual Urgency

**Problem**: "My lease ends next month" should prioritize immediately available spaces.

**Files to modify**:
- `agents/sms/criteria_agent.py` — Map urgency phrases ("lease ending", "need to move", "eviction") to `timing: "ASAP"`
- `services/buyer_sms_orchestrator.py` — When timing=ASAP, set `needed_from=today` on BuyerNeed, filter ClearingEngine to `available_from <= today`

---

### 3.6 — Landmark-Based Location

**Problem**: "Near LAX" or "close to the port" → needs geocode-based search.

**Files to modify**:
- `agents/sms/message_interpreter.py` — Add landmark extraction regex for airports (LAX, JFK, ORD, DFW), ports, "downtown {city}"
- `agents/sms/contracts.py` — Add `landmark_text: str | None = None`
- `services/buyer_sms_orchestrator.py` — Geocode landmark → use lat/lng for radius-based ClearingEngine search

---

### 3.7 — Comparative Questions

**Problem**: "Which one has more parking?" → needs to compare presented options.

**Files to modify**:
- `agents/sms/criteria_agent.py` — Add `"comparison"` intent
- `services/buyer_sms_orchestrator.py` — Fetch asked fields for ALL presented properties, not just focused one
- `agents/sms/response_agent.py` — Add comparison formatting: "Option 1 has 12 spots, Option 2 has 8"
- Voice: system prompt already handles comparisons naturally via cached match_summaries

---

## Wave 4: Result Quality & Rejection Handling

### 4.1 — Result Rejection / "I Don't Like These"

**Problem**: When a buyer says "I don't like any of these" or "you didn't understand my needs," the system re-runs the same search with identical criteria and presents the exact same options. This is the most bot-like failure mode — it proves Jess isn't listening.

**Two sub-problems**:

**A. No `reject_results` intent** — "I don't like these" gets classified as `refine_search` with no new criteria, which triggers an identical search.

**What should happen**: Jess should ask what was wrong, not re-search blindly.

**Files to modify**:
- `agents/sms/criteria_agent.py` — Add `"reject_results"` intent: "buyer is unhappy with presented options but hasn't said why." Examples: "I don't like any of these", "none of these work", "these aren't what I need", "not what I'm looking for", "you didn't understand"
- `services/buyer_sms_orchestrator.py` — Add handler: if `plan.intent == "reject_results"` and no new criteria in the message, do NOT re-search. Instead ask what was wrong: "Sorry those weren't a fit. Was it the price, the location, or something specific about the spaces? That'll help me find better options."
- `agents/sms/response_agent.py` — Add guideline: "reject_results: Never re-present the same options. Ask what didn't work. Offer specific dimensions to react to: price, location, size, features."
- `agents/sms/fallback_templates.py` — Add `"reject_results"` template
- `services/vapi_assistant_config.py` — Add RESULT REJECTION section to voice prompt: "If the caller says the options aren't right, don't repeat them. Ask what's missing."

**B. Pricing outlier filter** — A $228/sqft option alongside $1.91/sqft options should never be shown.

**Files to modify**:
- `services/buyer_sms_orchestrator.py` (or `services/clearing_engine.py`) — After ClearingEngine returns results, add an outlier filter before presenting:
  - Calculate median `buyer_rate` across results
  - Exclude any result where `buyer_rate > 5x median` (or `buyer_rate > 3x` the next-highest result)
  - Log excluded outliers for data quality review
  - If filtering removes all but 1 result, still present that 1 — don't show garbage alongside it

**Implementation order**: 4.1A first (reject_results intent), then 4.1B (outlier filter).

**Effort**: ~3h SMS + 0.5h Voice = 3.5h total

**Verification**:
- Present 3 options → buyer says "I don't like these" → expect clarifying question, NOT same options repeated
- Present 3 options → buyer says "too expensive" → expect `refine_search` with price constraint (existing behavior, not reject_results)
- Search returns results with 1 extreme outlier → expect outlier filtered out before presentation
- Search returns 3 results all at similar prices → expect no filtering (regression)

---

## Wave 5: Security Hardening (Voice Data Gating + Cross-Channel Abuse Prevention)

### 5.1 — Voice Data Leakage Prevention

**Problem**: The voice pipeline gates data at the **speech layer** (system prompt rules + regex on tool result text), not the **data layer**. Sensitive fields flow into tool results → Vapi's LLM sees them → a persistent caller can extract them conversationally. The SMS pipeline doesn't have this problem because its Gatekeeper is a hard code gate on the final output channel.

**Architecture principle**: Gate at the data layer (what goes into the tool result), not the speech layer (what the LLM says). All fixes below are in-memory dict/set operations — **zero latency impact**.

**Layer 1: Data Gate** (highest priority — prevents data from reaching the LLM)

Add a `VOICE_RESTRICTED_FIELDS` set to the voice gatekeeper and enforce it in the tool handlers **before** building the summary string:

```python
# In agents/voice/gatekeeper.py
VOICE_RESTRICTED_FIELDS = frozenset([
    "supplier_rate_per_sqft",  # Your cost basis — never expose
    "spread_pct",              # Your margin — never expose
    "owner_email",             # Owner PII
    "owner_phone",             # Owner PII
    "owner_name",              # Owner PII
    "full_address",            # Full street address (city/area only)
    "building_size_sqft",      # System prompt says don't share, enforce in code
    "available_sqft",          # System prompt says don't share, enforce in code
])
```

Then in `voice_tool_handlers.py`, when building match summaries or detail responses, filter these fields **before** the string is constructed. The data never enters the tool result → the LLM never sees it → it can't leak it.

**Layer 2: Dict Sanitization** (already exists, just wire it up)

`sanitize_match_summary()` in `agents/voice/gatekeeper.py` already strips `_SENSITIVE_MATCH_FIELDS` from match dicts — it's just **never called**. Call it in `voice_tool_handlers.py` wherever match dicts are built into summary strings:

- `search_properties` — before formatting each match
- `lookup_property_details` — before formatting the detail response
- `lookup_by_address` — before formatting the address lookup result

**Layer 3: Keep the regex gatekeeper** (defense in depth)

The existing `validate_tool_result()` regex remains as a **last resort** catch. Don't remove it — but recognize it's the weakest layer (catches literal patterns like "available sqft", not semantic rephrasing like "there's room for 10,000 square feet").

**What could leak without this fix**:

| Data | Risk | Why |
|------|------|-----|
| Supplier rate (your cost basis) | **High** | `supplier_rate_per_sqft` is queryable via DetailFetcher with zero gatekeeper protection |
| Full street addresses | **Medium** | Tool handlers build summaries with address fields; gatekeeper regex catches some but `lookup_by_address` returns address data by design |
| Building size / available sqft | **Medium** | Gatekeeper regex catches "available sqft" but misses conversational rephrasing |
| Owner PII | **Low** | Not in field catalog, but could surface through PropertyInsight narrative answers |

**Files to modify**:
- `agents/voice/gatekeeper.py` — Add `VOICE_RESTRICTED_FIELDS` frozenset
- `services/voice_tool_handlers.py` — Call `sanitize_match_summary()` in `search_properties`, `lookup_property_details`, `lookup_by_address`; filter `VOICE_RESTRICTED_FIELDS` from detail responses before string-building

**Priority order**:

| # | Fix | Effort | Impact |
|---|-----|--------|--------|
| 1 | Block `supplier_rate_per_sqft` from voice tool handler responses | 1 line per handler | **Critical** — this is your cost basis |
| 2 | Call `sanitize_match_summary()` in tool handlers | 3-4 lines | **High** — activates existing protection |
| 3 | Add `VOICE_RESTRICTED_FIELDS` set + enforce in DetailFetcher when `channel="voice"` | ~20 lines | **High** — systematic data gate |
| 4 | Add `building_size_sqft` and `available_sqft` to restricted set | 1 line | **Medium** — system prompt says don't share, code should enforce |

**Effort**: ~0.5h SMS (no changes) + 2h Voice = 2.5h total

---

### 5.2 — Cross-Channel Inventory Enumeration Prevention

**Problem**: A caller or bot could repeatedly invoke search/lookup tools to catalog the full inventory. Voice is fast (dozens of properties in one call), and SMS is automatable (scripted webhooks). Neither channel has tool usage limits.

**Threat scenarios**:
1. **Repeat `search_properties`** — cycling through cities: "Show me space in LA", "now Dallas", "now Houston"...
2. **Repeat `lookup_by_address`** — probing specific addresses to check if they're in your system
3. **Repeat `lookup_property_details`** — drilling into every option to extract specs on every property

**Implementation**: Per-session tool counters (in-memory, zero latency). Voice tracks per-call, SMS tracks per-conversation with a rolling 24h window (prevents resetting by starting new conversations).

**Per-session tool limits** (configurable via env vars — start generous during testing, tighten based on real usage data):

| Tool / Action | Voice (per call) | SMS (per conversation, rolling 24h) | Production target | Why different |
|---------------|-----------------|--------------------------------------|-------------------|---------------|
| `search_properties` | **9** | **15** | 3 / 5 | SMS buyers refine more over hours — legit. Voice is one sitting |
| `lookup_by_address` | **6** | **9** | 2 / 3 | Same risk both channels |
| `lookup_property_details` | **15** | **24** | 5 / 8 | SMS buyers ask detail questions across multiple messages |

> **Note**: Initial limits are set to **3x production targets** to avoid blocking testers and team members during QA. Tighten to production targets after testing phase is complete. All limits should be configurable via environment variables (e.g., `VOICE_SEARCH_LIMIT=9`, `SMS_SEARCH_LIMIT=15`) so thresholds can be tuned without redeploying.

**Voice implementation**: Counter dict on the call state (already in memory via `call_state` in tool handlers). Increment on each tool invocation, check before executing.

**SMS implementation**: Counter fields on `SMSConversationState` (persists across messages). Rolling 24h window — reset counts if `last_buyer_message_at` is >24h ago.

**When limits hit** (graceful redirect, not a hard block):
- **Voice**: "I've shown you quite a few options — want to narrow down what we've looked at, or I can have our team email you a full summary?"
- **SMS**: "I've pulled up a lot of options for you! Want to dig into any of these, or I can have our team put together a custom list?"

Both route to the team via SendGrid (`send_escalation_email()` pattern) — which gives visibility into who's hitting limits and whether they're legit or probing.

**Files to modify**:
- `services/voice_tool_handlers.py` — Add `_tool_counts` dict to call state; check/increment before each tool execution; return redirect response when limit hit
- `services/buyer_sms_orchestrator.py` — Add `search_count`, `address_lookup_count`, `detail_count` fields to conversation state tracking; enforce rolling 24h limits
- `domain/sms_models.py` — Add counter fields to `SMSConversationState` if not using JSON blob
- `services/email_service.py` — Reuse `send_escalation_email()` for limit-hit notifications (include phone, tool counts, conversation context)

**Effort**: ~2h SMS + 1.5h Voice = 3.5h total

**Rollout strategy**:
1. **Phase 1 (testing)**: Deploy with 3x limits + logging. Monitor logs to see actual usage patterns across team testers and real buyers
2. **Phase 2 (production)**: Tighten to production targets via env vars based on real usage data. No redeploy needed

**Verification** (using initial 3x limits):
- Voice: Call and request 10+ different city searches → expect graceful redirect on the 10th
- SMS: Send 16+ search requests in one conversation → expect redirect on the 16th
- Both: Verify redirect message includes team follow-up offer
- Both: Verify SendGrid email fires with tool usage details
- Regression: Normal buyer flow (1 search, 2 detail lookups) completes without hitting any limits

---

## Additional UX Enhancements (Woven Into Waves Above)

These aren't separate items but principles applied throughout:

1. **Never re-ask answered questions** — CriteriaAgent prompt already has this rule; reinforce in returning caller flow
2. **Natural transitions** — Every response should end with a forward-moving question, not a dead end
3. **Fewer options when quality is high** — If top match scores >90, present 1 with enthusiasm: "I found one that's a great fit." Don't always show 3
4. **Acknowledge before redirecting** — Supplier detection, FAQ, etc. should acknowledge what they said before redirecting
5. **Time-of-day awareness** — Morning texts can say "Good morning"; evening can say "Hey". Small touch, big difference
6. **Don't say "I'm an AI"** — Never. Jess is Jess. If asked directly, "I'm Jess from Warehouse Exchange" (not "I'm an AI assistant")

---

## Implementation Order & Effort Estimates

| Item | Wave | SMS Effort | Voice Effort | Total |
|------|------|-----------|-------------|-------|
| 1.1 FAQ | 1 | 1h | 0.5h | 1.5h |
| 1.2 Photos | 1 | 2.5h | 1h | 3.5h |
| 1.3 Engagement Status | 1 | 2h | 1.5h | 3.5h |
| 1.4 Budget Conversion | 1 | 2h | 1.5h | 3.5h |
| 1.5 Supplier Detection | 1 | 1.5h | 0.5h | 2h |
| 2.1 Returning Caller | 2 | 2h | 0.5h | 2.5h |
| 2.2 Use-Type Questions | 2 | 1.5h | 0.5h | 2h |
| 2.3 Sentiment/Escalation | 2 | 2h | 0.5h | 2.5h |
| 2.4 Micro-Confirmations | 2 | 0.5h | 0h | 0.5h |
| 3.1 Multi-Location | 3 | 4h | 2h | 6h |
| 3.2 Callbacks (email team) | 3 | 2h | 0.5h | 2.5h |
| 3.3 Waitlist (SMS + Voice enrollment) | 3 | 5h | 2h | 7h |
| 3.4 Lease Modification | 3 | 0.5h | 0.5h | 1h |
| 3.5 Urgency | 3 | 1.5h | 0.5h | 2h |
| 3.6 Landmarks | 3 | 3h | 0.5h | 3.5h |
| 3.7 Comparison | 3 | 3h | 0.5h | 3.5h |

| 4.1 Result Rejection + Outlier Filter | 4 | 3h | 0.5h | 3.5h |
| 5.1 Voice Data Leakage Prevention | 5 | 0h | 2h | 2h |
| 5.2 Cross-Channel Enumeration Prevention | 5 | 2h | 1.5h | 3.5h |

**Wave 1 Total**: ~14h | **Wave 2 Total**: ~7.5h | **Wave 3 Total**: ~25.5h | **Wave 4 Total**: ~3.5h | **Wave 5 Total**: ~5.5h

---

## New Files / Models Summary

| Wave | What | Purpose |
|------|------|---------|
| 1 | `send_callback_request_email()` in existing `email_service.py` | Team notification for callbacks (no new file) |
| 3 | `services/waitlist_service.py` | **Shared service** — both SMS and Voice use same enrollment logic |
| 3 | `BuyerWaitlist` model in `sms_models.py` | Waitlist entries. Includes `channel` column (`"sms"` / `"voice"`) for context-aware notifications |

All other changes are modifications to existing files. No new API credentials, templates, or external services needed.

## Verification Plan

After each wave:
1. **Unit testing**: Send test SMS messages via Aircall webhook simulator covering each new scenario
2. **Voice testing**: Make test calls via Vapi dashboard to verify system prompt changes
3. **Regression**: Run existing happy-path flows (search → present → commit) to ensure nothing broke
4. **Cross-channel**: Text first, then call — verify context carries over correctly
5. **Edge cases**: Test each new intent with off-script variations to ensure CriteriaAgent classifies correctly

---

## Operational Readiness (Non-Code Items)

### Before Implementation
- [ ] **FAQ content sign-off** — Review the pricing/value prop language (6% fee, flexibility) before embedding in prompts
- [ ] **Confirm supplier email** — Is `suppliers@warehouseexchange.com` monitored? The supplier redirect sends people there
- [ ] **Aircall MMS check** — Verify if Aircall native SMS endpoint supports `media_url` for photo sending (fallback: clickable image link)

### After Implementation
- [ ] **Escalation email monitoring** — Ensure `dev@warehouseexchange.com` has a response SLA for callback/frustration emails (consider Slack notification)
- [ ] **Intent classification logging** — Log intent + confidence to a table for auditing prompt accuracy over time
- [ ] **Human escalation state flag** — When team emails a callback, mark it in state so buyer doesn't get "I'll have someone reach out" again on next message
- [ ] **Regression test suite** — After each wave, run original happy-path flows (search → present → commit) to catch prompt degradation
- [ ] **Budget conversion disclaimer** — Market rate estimates aren't exact; consider noting "Based on rates in the area, that's roughly X sqft"
- [ ] **Tool limit monitoring** — After Wave 5, review SendGrid limit-hit emails weekly to tune thresholds (too low = legit buyers blocked, too high = no protection)
- [ ] **Voice gatekeeper audit** — Periodically test voice with adversarial questions ("what's the supplier rate?", "give me the owner's email") to verify data gate holds

### Known Remaining Gaps (Future Work)
- **Live call transfer** — Jess can't warm-transfer to a human mid-call (Vapi supports it but not wired up)
- **Multi-channel state sync** — If buyer texts AND calls simultaneously, states can diverge
- **Cross-number identity** — Buyer texting from one number and calling from another isn't linked
- **Waitlist scheduler** — Item 3.3 needs a periodic job (Cloud Scheduler / celery beat) to check new activations against waitlisted buyers

---

## Critical Files (Most Modified)

| File | Changes |
|------|---------|
| `services/buyer_sms_orchestrator.py` | Every wave — new intent handlers, photo attachment, budget conversion, returning caller, multi-search |
| `agents/sms/criteria_agent.py` | Every wave — new intents (faq, engagement_status, supplier_inquiry, human_escalation, comparison, callback_request, lease_modification) |
| `agents/sms/message_interpreter.py` | Wave 1-3 — new regex patterns (budget, supplier, frustration, landmarks, callbacks, photos) |
| `agents/sms/contracts.py` | Wave 1-2 — new fields on MessageInterpretation and OrchestratorResult |
| `agents/sms/response_agent.py` | Every wave — new response guidelines per intent |
| `services/vapi_assistant_config.py` | Every wave — system prompt sections + new tool definitions |
| `services/voice_tool_handlers.py` | Wave 1 + 3 + 5 — check_booking_status handler, budget param on search, `handle_add_to_waitlist()`, `sanitize_match_summary()` calls, `VOICE_RESTRICTED_FIELDS` enforcement, per-call tool counters |
| `agents/voice/gatekeeper.py` | Wave 5 — `VOICE_RESTRICTED_FIELDS` frozenset, data gate enforcement |
| `app/routes/vapi_webhook.py` | Wave 1 + 3 — tool dispatch entries for check_booking_status + add_to_waitlist |
| `agents/sms/fallback_templates.py` | Wave 1 — new fallback templates (faq, supplier_inquiry) |

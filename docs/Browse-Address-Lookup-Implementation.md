# Implementation Plan: Browse Marketplace + Address Lookup + Cross-Channel Continuity

**Date**: March 7, 2026
**Status**: Approved for implementation

---

## Context

The WEx Platform is live on Google Cloud. Buyer-side flows (SMS, voice, web search) work well for criteria-driven matching ("I need 10K sqft in Carson"). Three gaps exist:

1. **Browse is a dead-end grid** — shows only Tier 1 (in-network) properties, no detail page, clicking just funnels to `/buyer/search`
2. **No address-based lookup** — voice and SMS can't handle "I'm calling about 860 Sandhill Ave"
3. **Web doesn't connect to phone channels** — browsing creates no records that voice/SMS can pick up

## Dependency Map

```
WS1 (Browse Both Tiers)  ─────┐
                               ├──> WS3 (Qualify at Commitment) ──> WS5 (Browse→Voice/SMS Continuity)
WS2 (Property Detail Page) ───┘
WS4 (Address Lookup) ── independent, can run in parallel with WS1/WS2
```

---

## Execution Strategy: Agent Team Structure

I (Claude) stay as **orchestrator** — delegating work to specialized sub-agents per phase, never losing overall context. Each phase uses the minimum team needed.

### Phase 1a — WS4: Address Lookup (Backend Only)

Single dev agent. Self-contained new service file + wiring into voice/SMS. No frontend. No PM needed.

```
Orchestrator (me)
  └── Dev Agent: "ws4-address-lookup"
        Tasks:
        1. Create address_lookup.py (3-strategy fuzzy match service)
        2. Add lookup_by_address Vapi tool def + handler
        3. Add tool dispatch in vapi_webhook.py
        4. Wire address_text through SMS criteria_agent + orchestrator
  └── QC Agent: "qc-ws4"
        Tasks:
        1. Verify address_lookup service handles exact, fuzzy, geocode strategies
        2. Verify voice tool definition is valid schema
        3. Verify voice handler returns correct response shapes
        4. Verify SMS criteria_agent has new intent/action
        5. Verify SMS orchestrator handles address_lookup action
        6. Check all imports resolve, no circular dependencies
```

### Phase 1b — WS1: Browse Both Tiers (Backend + Frontend, parallel with 1a)

Two dev agents (backend + frontend in parallel), overseen by a PM agent.

```
Orchestrator (me)
  └── PM Agent: "pm-browse"
        Role: Coordinate backend/frontend agents, ensure API contract alignment
  └── Dev Agent: "ws1-backend"
        Tasks:
        1. Modify GET /api/browse/listings — tier filter, outerjoin, Tier 2 privacy
        2. Expand GET /api/browse/locations — include Tier 2 cities
        3. New POST /api/browse/listings/{id}/interest — DLA trigger + PropertyEvent
        4. Add buyer_interest to PropertyEventType enum
  └── Dev Agent: "ws1-frontend"
        Tasks:
        1. Update Listing interface (tier field, nullable rate/sqft)
        2. ListingCard Tier 2 styling (muted, amber badge)
        3. Click behavior → navigate to /browse/{id}
        4. Tier2InterestModal component
        5. API client methods
  └── QC Agent: "qc-ws1"
        Tasks:
        1. Hit GET /api/browse/listings — verify both tiers returned
        2. Verify Tier 2 has rate_range: null
        3. Verify sqft filter uses max_sqft (not available_sqft)
        4. Verify Tier 1 cards appear first
        5. Verify Tier 2 cards show correct styling
        6. Verify POST /interest creates DLA token + PropertyEvent
```

### Phase 2 — WS2: Property Detail Page (Backend + Frontend)

Two dev agents (backend endpoint + frontend page).

```
Orchestrator (me)
  └── Dev Agent: "ws2-backend"
        Tasks:
        1. New GET /api/browse/listings/{id} endpoint
        2. New _build_specs() helper
        3. Tier-gated field visibility
  └── Dev Agent: "ws2-frontend"
        Tasks:
        1. New /browse/[id]/page.tsx
        2. Photo gallery, specs grid, features pills
        3. Tier 1 vs Tier 2 display logic
        4. API client method
  └── QC Agent: "qc-ws2"
        Tasks:
        1. Verify /browse/{id} loads for Tier 1 and Tier 2
        2. Verify Tier 1 shows rate, Tier 2 does not
        3. Verify specs grid renders all PropertyKnowledge fields
        4. Verify 404 for non-existent/hidden properties
        5. Verify page navigates correctly from browse grid
```

### Phase 3 — WS3: Qualify at Commitment (Backend + Frontend)

Two dev agents. Touches EngagementBridge, ClearingEngine, enums.

```
Orchestrator (me)
  └── Dev Agent: "ws3-backend"
        Tasks:
        1. New POST /api/browse/listings/{id}/qualify endpoint
        2. Fit check logic (available_sqft, not max_sqft)
        3. PropertyEvent(buyer_qualified) logging
        4. Match path: EngagementBridge.initiate_booking()
        5. Mismatch path: ClearingEngine.run_clearing() + SearchSession
        6. Add buyer_qualified to PropertyEventType enum
        7. Extend EngagementBridge for source_channel="browse"
  └── Dev Agent: "ws3-frontend"
        Tasks:
        1. Inline qualify form on /browse/[id] page
        2. Form fields: sqft, timing, name, phone, email
        3. Match → redirect to engagement page
        4. Mismatch → redirect to /buyer/options
        5. API client method
  └── QC Agent: "qc-ws3"
        Tasks:
        1. Verify inline form appears on button click
        2. Verify match creates engagement + redirects
        3. Verify mismatch runs ClearingEngine + redirects
        4. Verify Buyer created/deduped by phone
        5. Verify PropertyEvent logged with correct metadata
        6. Verify form validation
```

### Phase 4 — WS5: Browse→Voice/SMS Continuity (Backend Only)

Single dev agent. ~30 lines added to qualify endpoint.

```
Orchestrator (me)
  └── Dev Agent: "ws5-continuity"
        Tasks:
        1. Create SMSConversationState in qualify endpoint
        2. Create/find BuyerConversation
        3. Handle existing vs new state (update, don't duplicate)
        4. Document UUID compatibility (Property.id = Warehouse.id)
  └── QC Agent: "qc-ws5"
        Tasks:
        1. Verify SMSConversationState created with correct fields
        2. Verify existing state updated (not duplicated)
        3. Verify focused_match_id resolves to valid Property
```

### Phase 5 — End-to-End QC

One comprehensive QC agent that tests all APIs and simulates user flows.

```
Orchestrator (me)
  └── E2E QC Agent: "qc-e2e"
        Tasks:
        API tests:
        1. GET /api/browse/listings — both tiers, all filters, pagination
        2. GET /api/browse/listings?tier=tier1 — only active properties
        3. GET /api/browse/listings?tier=tier2 — only prospect/contacted/etc
        4. GET /api/browse/listings/{id} — Tier 1 detail, Tier 2 detail, 404
        5. POST /api/browse/listings/{id}/interest — creates DLA + PropertyEvent
        6. POST /api/browse/listings/{id}/qualify (match) — creates engagement
        7. POST /api/browse/listings/{id}/qualify (mismatch) — runs ClearingEngine
        8. Verify SMSConversationState created after qualify

        Cross-channel tests:
        9. After qualify: verify voice webhook seeds from browse context
        10. After qualify: verify SMS pipeline picks up browse context

        Address lookup tests:
        11. Exact address match via address_lookup service
        12. Fuzzy address match (partial street name)
        13. No-match fallback

        Frontend smoke tests (if possible):
        14. Browse page loads, shows both tiers
        15. Detail page loads for both tiers
        16. Qualify form renders and submits

        Data integrity:
        17. PropertyEvents logged correctly for interest + qualify
        18. Buyer dedup by phone works
        19. BuyerNeed created with correct city/state/sqft
```

### Agent Summary Table

| Phase | Agents | Agent Types |
|-------|--------|-------------|
| 1a (WS4) | 2 | 1 Dev + 1 QC |
| 1b (WS1) | 4 | 1 PM + 2 Dev + 1 QC |
| 2 (WS2) | 3 | 2 Dev + 1 QC |
| 3 (WS3) | 3 | 2 Dev + 1 QC |
| 4 (WS5) | 2 | 1 Dev + 1 QC |
| 5 (E2E) | 1 | 1 E2E QC |
| **Total** | **15 agent invocations** | **Orchestrator stays lean** |

---

## Workstream 1: Browse Page — Show Both Tiers

### Backend: Modify `GET /api/browse/listings`

**File**: `backend/src/wex_platform/app/routes/browse.py` (239 lines)

| Change | Details |
|--------|---------|
| Add `tier` query param | `?tier=all\|tier1\|tier2` (default: `all`) |
| Expand base query | Currently line 109 filters `relationship_status == "active"` only. Add `prospect`, `contacted`, `interested`, `earncheck_only` |
| Sqft filter semantics | Lines 123-128 use `PropertyListing.max_sqft` — **keep `max_sqft` for browse**. Browse answers "show me buildings that could accommodate my need" (structural capacity), not "what's free right now." `max_sqft` is the building's leasable footprint (rarely changes). `available_sqft` is what's unoccupied after holds (changes with every engagement). A 50K sqft warehouse with a 5K hold should still appear for "show me spaces over 10K sqft." Reserve `available_sqft` checks for the qualify endpoint (WS3), where we do a real-time fit check. |
| Handle missing PropertyListing | Tier 2 properties may not have a listing. Use `outerjoin` instead of `join` for PropertyListing |
| Add `tier` field to response | `1` or `2` based on `relationship_status` |
| Tier 2 privacy | `rate_range: null` (no pricing exposed for Tier 2) |
| Sort order | Tier 1 first, then Tier 2, via `case()` expression |

**Expand `GET /api/browse/locations`** (line 219): Include Tier 2 cities in autocomplete.

**New endpoint `POST /api/browse/listings/{id}/interest`**: Tier 2 interest capture.
- Request: `{name, email, phone, note?}`
- Creates/finds Buyer by phone, creates minimal BuyerNeed from property's city/state
- Calls `DLAService.generate_token(property_id, buyer_need_id)` to trigger supplier outreach
- **Log PropertyEvent** for demand signal:
  ```python
  PropertyEvent(
      property_id=property.id,
      event_type='buyer_interest',
      actor=buyer.phone or buyer.email,
      metadata={"source": "browse", "note": request.note}
  )
  ```
  This feeds supplier activation pitch: "3 buyers have expressed interest in your property in the last 30 days" — trivial query (`SELECT COUNT(*) FROM property_events WHERE property_id = X AND event_type = 'buyer_interest'`), powerful leverage.
- Response: `{ok: true, message: "We'll check availability and get back to you"}`

### Frontend: Update browse grid

**File**: `frontend/src/app/browse/page.tsx` (788 lines)

| Change | Details |
|--------|---------|
| Update `Listing` interface | Add `tier: 1 \| 2`, make `sqft_range` and `rate_range` nullable |
| `ListingCard` Tier 2 styling | Muted opacity (0.85), amber "Check Availability" badge, no rate shown, "Rate available on request" text |
| Click behavior | Both tiers navigate to `/browse/{id}` detail page (remove `InterestModal` for Tier 1) |
| New `Tier2InterestModal` | Minimal form for Tier 2 interest capture (name, email, phone) |

**File**: `frontend/src/lib/api.ts` — Add `browseListingInterest()` method.

### Data Flow

```
GET /api/browse/listings?tier=all&city=Dallas
  -> Query: Property WHERE relationship_status IN (active, prospect, contacted, interested, earncheck_only)
  -> JOIN PropertyKnowledge, OUTERJOIN PropertyListing
  -> Build response: Tier 1 = full data, Tier 2 = partial (no rate)
  -> Sort: Tier 1 first

Click Tier 2 -> Tier2InterestModal -> POST /interest -> DLAService.generate_token()
```

### Verification

1. `GET /api/browse/listings` returns both Tier 1 and Tier 2 properties
2. Tier 2 listings have `tier: 2`, `rate_range: null`
3. Sqft filter uses `max_sqft` (building capacity, not current availability)
4. Tier 1 cards appear first in grid
5. Tier 2 cards show muted styling + badge
6. Tier 2 interest submission creates DLA token + PropertyEvent(`buyer_interest`)

---

## Workstream 2: Property Detail Page

### Backend: New endpoint `GET /api/browse/listings/{id}`

**File**: `backend/src/wex_platform/app/routes/browse.py`

```
Response shape:
{
  id, tier, location: {city, state, display},
  building_type, features: [...],
  specs: {clear_height_ft, dock_doors, parking_spaces, has_office, has_sprinkler,
          power_supply, year_built, construction_type, zoning, building_size_sqft},
  sqft_range, rate_range (null for Tier 2),
  instant_book_eligible, tour_required,
  has_image, image_url, image_urls
}
```

New helper `_build_specs(pk: PropertyKnowledge) -> dict`: Extracts all available specs from PropertyKnowledge into a public-safe dict.

Only shows properties with `relationship_status` in allowed set. Returns 404 for declined/churned/unresponsive.

### Frontend: New page `/browse/[id]`

**New file**: `frontend/src/app/browse/[id]/page.tsx`

```
Layout:
+-----------------------------------------+
|  BrowseNavbar (reuse from browse page)  |
+-----------------------------------------+
|  Photo Gallery (image_urls)             |
+--------------------+--------------------+
|  Left Column       |  Right Column      |
|  - Location        |  Tier 1:           |
|  - Building type   |  - sqft_range      |
|  - Features pills  |  - rate_range      |
|  - Specs grid      |  - [Book Tour]     |
|                    |  - [Instant Book]  |
|                    |                    |
|                    |  Tier 2:           |
|                    |  - sqft_range      |
|                    |  - [Check Avail.]  |
+--------------------+--------------------+
```

**File**: `frontend/src/lib/api.ts` — Add `browseListingDetail()` method.

### Verification

1. `/browse/{id}` loads for both Tier 1 and Tier 2 properties
2. Tier 1 shows rate range; Tier 2 does not
3. Specs grid renders all available PropertyKnowledge fields
4. 404 for non-existent or hidden properties

---

## Workstream 3: Qualify at Commitment

### Backend: New endpoint `POST /api/browse/listings/{id}/qualify`

**File**: `backend/src/wex_platform/app/routes/browse.py`

Request:
```
{sqft_needed: int, timing: str, name: str, phone: str, email?: str, action: "book_tour" | "instant_book"}
```

Pipeline:
1. Load Property + PropertyListing
2. **Fit check**: `sqft_needed` vs `available_sqft` (10% tolerance), `min_sqft` floor. Note: this is where we use `available_sqft` (real-time availability), not `max_sqft` (used in browse filters for building capacity).
3. **Always create**: Buyer (dedup by phone) + BuyerNeed (city/state/sqft from property + request)
4. **Log PropertyEvent** (always, for both match and mismatch):
   ```python
   PropertyEvent(
       property_id=property.id,
       event_type='buyer_qualified',  # Add to PropertyEventType enum
       actor=buyer.phone,
       metadata={
           "sqft_requested": sqft_needed,
           "action": "book_tour" | "instant_book",
           "result": "match" | "mismatch",
           "mismatch_reason": "sqft_exceeded" | "below_minimum" | null
       }
   )
   ```
   This gives demand signal per property: "which properties get the most qualification attempts?" and "what's the match vs mismatch ratio by market?" — useful for supplier activation and pricing recommendations.
5. **Match path**: Call `EngagementBridge.initiate_booking()` -> return `{status: "match", engagement_id}`
6. **Mismatch path**: Geocode -> `ClearingEngine.run_clearing()` -> create SearchSession -> return `{status: "mismatch", redirect_url: "/buyer/options?session=X", alternatives: [{count, reasons}]}`

Reuses:
- `EngagementBridge.initiate_booking()` from `engagement_bridge.py` (extend `source_channel` to accept `"browse"`)
- `ClearingEngine.run_clearing()` for alternatives
- `geocode_location()` for lat/lng
- `PropertyEvent` model from `models.py` (append-only event log)

### Frontend: Inline qualify form on detail page

**File**: `frontend/src/app/browse/[id]/page.tsx`

- "Book Tour" / "Instant Book" buttons reveal an inline accordion form (not a modal)
- Fields: sqft needed, timing dropdown, name, phone, email (optional)
- On submit -> `POST /qualify`
  - Match -> redirect to `/buyer/engagement/{id}`
  - Mismatch -> redirect to `/buyer/options?session=X` (shows alternatives)

**File**: `frontend/src/lib/api.ts` — Add `browseQualify()` method.

### Data Flow

```
Buyer on /browse/{id} clicks "Book Tour"
  -> Inline form: sqft, timing, name, phone
  -> POST /api/browse/listings/{id}/qualify

  [MATCH]    -> Engagement created -> frontend redirects to engagement page
  [MISMATCH] -> ClearingEngine finds alternatives -> frontend redirects to /buyer/options
```

### Verification

1. "Book Tour" reveals inline form
2. Match: engagement created, redirect works
3. Mismatch: ClearingEngine runs, alternatives page loads
4. Buyer record created/deduped by phone
5. PropertyEvent(`buyer_qualified`) logged with result + mismatch_reason
6. Form validation: phone format, sqft > 0, name required

---

## Workstream 4: Address-Based Lookup (Voice + SMS)

### New service: `address_lookup.py`

**New file**: `backend/src/wex_platform/services/address_lookup.py`

```python
async def lookup_by_address(address_text: str, db: AsyncSession, include_tier2: bool = True) -> AddressLookupResult
```

Three-strategy pipeline:
1. **Exact**: `Property.address ILIKE %{address_text}%` — confidence 1.0
2. **Fuzzy**: Extract street number + first word, `ILIKE %{num}%{word}%` — confidence 0.6-0.8
3. **Geocode**: Geocode address -> find nearest Property within 0.5 miles — confidence 0.7

Returns `AddressLookupResult(found, property_id, address, city, state, tier, confidence, match_type, property_data)`.

**Key discovery**: `Property.address` field exists (models.py line 1139, `String(500)`). No schema changes needed.

**v2 design note — confidence feedback loop**: The `match_type` and `confidence` fields in `AddressLookupResult` are returned but not written back in v1. In a future iteration, if a buyer confirms the match ("yeah, that's the building"), we can write back to `PropertyKnowledge.field_provenance` for the address field with `{source: "buyer_confirmed", confidence: 1.0, at: now}`. Design the service so this feedback path is easy to add — keep confidence and match_type in the return type, don't discard them.

### Voice: New Vapi tool `lookup_by_address`

**File**: `backend/src/wex_platform/services/vapi_assistant_config.py` (line 261)

Add 4th tool to `_build_tool_definitions()`:
```
{name: "lookup_by_address", params: {address: string}, description: "Look up a specific property by street address"}
```

Update system prompt (line 106): Add alternative flow — "If caller asks about a specific property by address, use lookup_by_address first"

**File**: `backend/src/wex_platform/services/voice_tool_handlers.py`

New method `lookup_by_address(address: str) -> str`:
- Calls `address_lookup.lookup_by_address()`
- If found: adds to `call_state.presented_match_ids`, returns voice-formatted summary
- If Tier 2: offers to check availability with owner
- If not found: suggests searching by area instead

**File**: `backend/src/wex_platform/app/routes/vapi_webhook.py` (line ~180)

Add `"lookup_by_address"` to tool dispatch switch.

### SMS: Wire existing `address_text` through pipeline

**Key discovery**: `message_interpreter.py` already has `ADDRESS_PATTERN` regex (lines 132-137) and stores `result.address_text` (lines 311-313) — but it's NOT passed downstream.

**File**: `backend/src/wex_platform/agents/sms/criteria_agent.py`

- Add `address_text` to the `interp_ctx` dict passed to the LLM (line 201)
- Add `"address_lookup"` to intent classification list (line 30)
- Add `"address_lookup"` to action choices (line 52)
- Add prompt section: "If buyer mentions a specific street address, set intent/action to address_lookup"

**File**: `backend/src/wex_platform/services/buyer_sms_orchestrator.py`

Add handler after `elif plan.action == "lookup"` block (line ~351):
```python
elif plan.action == "address_lookup" and interpretation.address_text:
    # Call address_lookup service
    # If found: set focused_match_id, add to presented_match_ids, phase = PROPERTY_FOCUSED
    # If Tier 2: offer to check availability
    # If not found: ask for different address or search by city
```

### Data Flow

```
VOICE:
  Caller: "I'm calling about 860 Sandhill Ave in Carson"
  -> Vapi tool: lookup_by_address(address="860 Sandhill Ave, Carson")
  -> address_lookup service -> 3-strategy search on Property.address
  -> Found -> voice response with property summary
  -> Added to presented_match_ids for follow-up questions

SMS:
  Buyer: "do you have the warehouse at 860 Sandhill Ave?"
  -> Message Interpreter: ADDRESS_PATTERN -> address_text = "860 Sandhill Ave"
  -> Criteria Agent: intent="address_lookup", action="address_lookup"
  -> Orchestrator: calls address_lookup service
  -> Found -> set focused_match_id, present property details
```

### Verification

1. Voice: address mentioned -> `lookup_by_address` tool called
2. Voice: found -> property summary + added to presented_match_ids
3. Voice: not found -> offers area search fallback
4. SMS: address in message -> `address_text` extracted (existing regex)
5. SMS: criteria agent returns `action: "address_lookup"`
6. SMS: orchestrator finds property -> enters PROPERTY_FOCUSED phase
7. Fuzzy matching: "860 Sandhill" matches "860 Sandhill Avenue, Carson, CA 90745"

---

## Workstream 5: Browse -> Voice/SMS Continuity

### How it works

The qualify form (WS3) already creates `Buyer` + `BuyerNeed`. WS5 additionally creates `SMSConversationState` so voice/SMS channels pick up the browse context.

**Important UUID compatibility note**: The `focused_match_id` stored in `SMSConversationState` is `Property.id`, which equals the old `Warehouse.id` (same UUIDs were preserved during the Feb 2026 migration for FK compatibility). This is why voice/SMS seeding works — `Engagement.warehouse_id`, `Property.id`, and `SMSConversationState.focused_match_id` all reference the same UUID. Document this in a code comment so someone reading the code six months from now understands why a "browse-originated" SMSConversationState has a valid `focused_match_id` that resolves to a Property record.

**File**: `backend/src/wex_platform/app/routes/browse.py` (inside `qualify_buyer` endpoint)

After creating Buyer + BuyerNeed, add:
1. Find or create `BuyerConversation` for this buyer
2. Check if `SMSConversationState` already exists for this phone
3. If no existing state -> create new one:
   - `phone` = buyer phone
   - `phase` = `"PRESENTING"` (they've already seen a property)
   - `presented_match_ids` = `[property_id]`
   - `focused_match_id` = `property_id`
   - `criteria_snapshot` = `{location, sqft}` from qualify form
   - `renter_first_name` / `renter_last_name` from name
4. If existing state -> update with new browse context (don't duplicate)

### Why this works automatically

The Vapi webhook (`vapi_webhook.py` lines 96-155) already:
1. Queries `SMSConversationState` by `caller_phone` (30-day freshness window)
2. Seeds `VoiceCallState` with `buyer_need_id`, `presented_match_ids`, `known_answers`
3. Personalizes Jess's greeting based on existing context

Our WS5 records use the same table + schema, so voice seeding works with zero changes to the Vapi webhook.

```
Browse qualify form -> SMSConversationState created (phone, presented_match_ids, focused_match_id)

Later, buyer calls Jess:
  -> vapi_webhook queries SMSConversationState by phone
  -> Finds browse-created record
  -> Seeds VoiceCallState
  -> Jess: "Hey {name}, I see you were looking at a space in {city}..."

Later, buyer texts:
  -> buyer_sms.py loads SMSConversationState by phone
  -> Has criteria, presented_match_ids from browse
  -> Continues where browse left off
```

### Verification

1. Qualify form creates `SMSConversationState` with correct phone, presented_match_ids, focused_match_id
2. Calling Jess after browse -> personalized greeting references browsed property
3. Texting after browse -> SMS pipeline picks up existing context
4. Existing SMS state updated (not duplicated) if buyer already has one

---

## API Contract Summary

### Modified Endpoints

| Endpoint | Change |
|----------|--------|
| `GET /api/browse/listings` | Add `?tier` param, add `tier` field to response, keep `max_sqft` for browse filters, Tier 2 has `rate_range: null` |
| `GET /api/browse/locations` | Include Tier 2 cities |

### New Endpoints

| Endpoint | Method | Purpose | Request | Response |
|----------|--------|---------|---------|----------|
| `/api/browse/listings/{id}` | GET | Property detail | — | `{id, tier, location, building_type, features, specs, sqft_range, rate_range, instant_book_eligible, tour_required, image_urls}` |
| `/api/browse/listings/{id}/qualify` | POST | Qualify + engage | `{sqft_needed, timing, name, phone, email?, action}` | `{status: "match"\|"mismatch", engagement_id?, redirect_url?, alternatives?}` |
| `/api/browse/listings/{id}/interest` | POST | Tier 2 DLA trigger | `{name, email, phone, note?}` | `{ok, message}` |

### New Voice Tool

| Tool | Parameters | Returns |
|------|-----------|---------|
| `lookup_by_address` | `{address: string}` | Voice-formatted property summary or "not found" fallback |

---

## Files Summary

### Files to Modify

| File | Workstreams | Changes |
|------|------------|---------|
| `backend/src/wex_platform/app/routes/browse.py` | WS1, WS2, WS3, WS5 | Tier filter, detail endpoint, qualify endpoint, cross-channel records |
| `frontend/src/app/browse/page.tsx` | WS1 | Tier 2 styling, ListingCard changes, Tier2InterestModal, remove InterestModal |
| `frontend/src/lib/api.ts` | WS1, WS2, WS3 | 3 new API methods |
| `backend/src/wex_platform/services/vapi_assistant_config.py` | WS4 | New tool definition + prompt update |
| `backend/src/wex_platform/services/voice_tool_handlers.py` | WS4 | New `lookup_by_address` handler |
| `backend/src/wex_platform/app/routes/vapi_webhook.py` | WS4 | Dispatch new tool name |
| `backend/src/wex_platform/agents/sms/criteria_agent.py` | WS4 | Pass address_text, add address_lookup intent/action |
| `backend/src/wex_platform/services/buyer_sms_orchestrator.py` | WS4 | Handle `address_lookup` action |
| `backend/src/wex_platform/services/engagement_bridge.py` | WS3 | Accept `source_channel="browse"` |
| `backend/src/wex_platform/domain/enums.py` | WS3 | Add `buyer_qualified` and `buyer_interest` to PropertyEventType |

### Files to Create

| File | Workstream | Purpose |
|------|-----------|---------|
| `backend/src/wex_platform/services/address_lookup.py` | WS4 | Address fuzzy-match service (3-strategy pipeline) |
| `frontend/src/app/browse/[id]/page.tsx` | WS2, WS3 | Property detail page with qualify form |

### Existing Code to Reuse

| What | Where | Used By |
|------|-------|---------|
| ClearingEngine | `clearing_engine.py` -> `run_clearing()` | WS3 (mismatch alternatives) |
| Match summary builder | `clearing_engine.py` -> `build_match_summaries()` | WS3 |
| DLA token creation | `dla_service.py` -> `generate_token()` | WS1 (Tier 2 interest) |
| EngagementBridge | `engagement_bridge.py` -> `initiate_booking()` | WS3 (match path) |
| SMS seeding pattern | `vapi_webhook.py` lines 96-155 | WS5 (browse->voice) |
| Address regex | `message_interpreter.py` lines 132-137 | WS4 (already extracts address_text) |
| Geocoding | `geocoding_service.py` -> `geocode_location()` | WS4 (fallback strategy) |
| Browse obfuscation helpers | `browse.py` -> `_sqft_range()`, `_rate_range()` | WS2 (detail page) |
| PropertyEvent model | `models.py` -> `PropertyEvent` | WS1 (buyer_interest), WS3 (buyer_qualified) |

---

## Build Order

```
Phase 1a (start first):
  WS4: Address lookup service + voice tool + SMS wiring
       -> Self-contained new file, no frontend, testable against Property table immediately.
       -> Shipping this first gives an immediate capability win (callers can ask about
         specific buildings) while browse work is still in progress.
       -> Agents: 1 Dev + 1 QC

Phase 1b (parallel with WS4):
  WS1: Browse both tiers (backend + frontend)
       -> Touches both backend and frontend, takes longer.
       -> Agents: 1 PM + 2 Dev (backend + frontend) + 1 QC

Phase 2 (depends on WS1):
  WS2: Property detail page (backend + frontend)
       -> Agents: 2 Dev (backend + frontend) + 1 QC

Phase 3 (depends on WS2):
  WS3: Qualify at commitment (backend + frontend)
       -> Also add 'buyer_qualified' to PropertyEventType enum
       -> Agents: 2 Dev (backend + frontend) + 1 QC

Phase 4 (depends on WS3):
  WS5: Browse->Voice/SMS continuity (backend only, ~30 lines in qualify endpoint)
       -> Agents: 1 Dev + 1 QC

Phase 5 (after all workstreams):
  E2E QC: Full API + cross-channel + frontend smoke tests
       -> Agents: 1 E2E QC
```

# Supplier Dashboard — Developer Spec

**For:** Frontend + Backend Developer
**Context:** Supplier-facing dashboard for managing properties, engagements, payments, and profile
**Date:** February 2026

---

## Overview

### What We're Building

The supplier dashboard is the command center for warehouse owners who've joined the WEx network. It's where they manage their properties, respond to engagements, track earnings, and optimize their listings. But it is NOT where most supplier interaction happens — SMS, email, and phone handle the real-time engagement flow. The dashboard is the filing cabinet, not the front desk.

### Design Philosophy

**Set it and forget it.** Most suppliers will visit the dashboard during onboarding to configure their properties, then return only when something specific happens — a payment to verify, an engagement to review, or a profile change to make. We design for the supplier who visits once a month, not the one who logs in daily.

**Every screen answers one question:**
- Portfolio page → "How's my portfolio doing?"
- Property detail → "How's this property doing and how can it earn more?"
- Engagements page → "What needs my attention right now?"
- Payments page → "Did I get paid?"

**The system does the work, not the supplier.** Instead of expecting suppliers to study analytics dashboards and figure out what to optimize, the platform analyzes matching data, market conditions, and buyer demand behind the scenes and surfaces specific, actionable suggestions: "Do this → earn more." Every suggestion has a one-click action button. No interpretation required.

**Progressive data collection, not forms.** The dashboard doesn't present a 50-field form to complete. Instead, the AI suggestion engine identifies which missing data points would have the highest impact on matching and earning, and prompts the supplier to fill those specific gaps. Profile completeness grows over time through targeted asks, both on the dashboard and via SMS/email check-ins.

### The Supplier's Primary Interaction Pattern

```
SMS/Email (daily, real-time)          Dashboard (monthly, review)
─────────────────────────             ─────────────────────────
• Receive deal ping → accept/decline  • Check earnings & payments
• Confirm tour date/time              • Review portfolio performance
• Answer buyer questions              • Act on AI optimization suggestions
• Upload photos via QR link           • Adjust rates or configuration
• Progressive enrichment responses    • Download payment statements
                                      • Manage account & team
```

Most engagements will be accepted or declined via a text message reply. The dashboard shows the same information in a structured view for suppliers who want the full picture, and it's where actions that require more thought (rate changes, configuration updates, agreement signing) happen.

### Expected Outcomes

**For suppliers:**
- Clear visibility into earnings across their portfolio at a glance
- Never miss an opportunity — action items surfaced prominently with time-sensitive indicators
- Data-backed guidance on how to earn more (not generic tips — specific suggestions derived from actual buyer demand and near-miss matching data)
- Easy property management without heavy form-filling (confirm inferred data, upload photos from phone, respond to targeted suggestions)
- Confidence that the system is actively working for them (activity timeline shows matching activity even when engagements aren't closing yet)

**For WEx:**
- Higher supplier engagement and profile completeness → better matching → more engagements closed
- Near-miss and response logging builds intelligence that improves matching and pricing over time
- Suggestion engine nudges suppliers toward market-competitive rates and in-demand features without WEx ops team having to make individual calls
- Team management allows property management companies to onboard multiple users, expanding supply without proportional ops effort
- Structured engagement flow reduces the chance of engagements falling through due to missed communications

**For the platform (data flywheel):**
- Every suggestion response (even "No, I don't have office space") is stored as enrichment data
- Every deal ping response contributes to supplier behavioral profiles (response time, acceptance rate, decline patterns)
- Every near-miss logged makes future matching smarter and suggestions more targeted
- Profile completeness improvements directly increase Tier 1 match rates
- The dashboard becomes a self-improving system — the more suppliers use it, the better it gets at telling them what to do

---

## 1. Page Structure

```
/supplier                          → Portfolio Dashboard (landing page)
/supplier/properties/[id]          → Property Detail + Edit
/supplier/engagements                    → Engagements (active, in-progress, past)
/supplier/engagements/[id]               → Engagement Detail + Timeline
/supplier/payments                 → Earnings & Payment History
/supplier/account                  → Account Settings
/supplier/account/team             → Team Management (invite users)
```

All pages require auth (role = supplier or admin). Left nav or top nav with these sections.

---

## 2. Portfolio Dashboard (`/supplier`)

This is the landing page. Answers: "How's my portfolio doing?" and "What needs my attention?"

### 2.1 Portfolio Summary (top of page)

```
TOTAL PROJECTED INCOME        AVG RATE          ACTIVE CAPACITY       OCCUPANCY
$1,740,960/yr                 $1.03/sqft        136,500 sqft          42%
Protected by WEx Occupancy Guarantee
```

- Total Projected Income = sum of (rate × rented sqft × 12) for all active engagements + (rate × available sqft × 12) for listed but unrented space
- Avg Rate = weighted average of supplier rates across portfolio
- Active Capacity = total sqft listed across all in_network properties
- Occupancy = rented sqft / available sqft across portfolio

### 2.2 Action Required (below summary, only shown when items exist)

A notification-style section that surfaces items needing supplier attention. Each item has a description and an action button.

| Source | Display | Action Button |
|--------|---------|---------------|
| New deal ping (in-network match) | "A buyer needs 5,000 sqft storage in your area. $0.75/sqft for 6 months." | [Review Engagement] → goes to engagement detail |
| DLA outreach response needed | "A buyer matched your property at 1221 Wilson Rd." | [View Opportunity] → goes to DLA page or engagement detail |
| Tour to confirm | "Tour requested for March 5 at 1221 Wilson Rd, 10:00 AM" | [Confirm Tour] / [Propose New Time] |
| Agreement to sign | "Engagement agreement ready for Engagement #1234" | [Review & Sign] |
| Post-tour follow-up | "How did the tour go for Engagement #1234?" | [Tour Went Well] / [Issue to Report] |

When no actions pending: show "All caught up — your properties are actively matching with buyers." (not an empty state)

**Backend:** `GET /api/supplier/actions` — returns pending items across all engagement states, sorted by urgency (time-sensitive first).

### 2.3 Portfolio-Level AI Suggestions (below action required)

Cross-property insights. 2-3 suggestions max, each with an action button. Rotate/refresh weekly or when new data arrives.

Examples:
- "Your Torrance property has no photos. Properties with photos get 2x more tour requests." → [Add Photos]
- "40% of buyers in your markets need office space. Only 1 of your 3 properties allows it." → [Update Gardena Property]
- "Your Sugar Land rate is 20% above area median. Lowering to $0.60 would match 5 active searches." → [Adjust Rate]

**Backend:** `GET /api/supplier/suggestions` — aggregates near_miss data, profile completeness, and market demand across all supplier properties. Returns top 3 suggestions with action type and target property_id.

### 2.4 Property Cards (main content)

Grid of property cards. First position = "+ Add Asset to Portfolio" card (links to /supplier/onboard).

Each property card:

```
┌─────────────────────────────────────────┐
│  [Satellite/Street Image]    ● LIVE     │
│                                         │
│  1221 Wilson Rd                         │
│  Glen Burnie, MD 21061                  │
│                                         │
│  REVENUE            RATE LOCKED         │
│  $255,600/yr        $0.71/sqft          │
│                                         │
│  28,000 sqft available · 18,000 rented  │
│  [████████████░░░░░░] 64%               │
│                                         │
│  Matching Tenants...        [toggle]    │
│                                         │
└─────────────────────────────────────────┘
```

**Fields on card:**
| Field | Source | Notes |
|-------|--------|-------|
| Image | Best available (supplier photo > street view > satellite) | |
| Status badge | supplier_status | "LIVE" (in_network), "PAUSED" (in_network_paused), "ONBOARDING" |
| Address | Warehouse.address | Full address (it's the supplier's own property) |
| Revenue | rate × available_sqft × 12 | Projected annual |
| Rate | TruthCore.target_rate_sqft | Supplier's rate, not buyer all-in |
| Available sqft | TruthCore.available_sqft | Total listed on WEx |
| Rented sqft | Sum of active engagement sqft for this property | |
| Occupancy bar | rented / available | Visual progress bar |
| Matching toggle | Enables/disables matching | When OFF → status = in_network_paused |

**If nothing rented yet:**
```
28,000 sqft available · Matching tenants...
[░░░░░░░░░░░░░░░░░░░░]
```

**If fully occupied:**
```
28,000 sqft · Fully occupied
[████████████████████] 100%
```

Click card → navigates to `/supplier/properties/[id]`

---

## 3. Property Detail Page (`/supplier/properties/[id]`)

Where the supplier views, edits, and enriches a specific property. This is NOT a form — it's an organized profile view with inline edit capabilities and AI guidance.

### 3.1 Page Layout

```
┌───────────────────────────────────────────────────────┐
│  ← Back to Portfolio          [Pause Matching] toggle │
│                                                       │
│  1221 Wilson Rd, Glen Burnie, MD 21061                │
│  Status: LIVE · Profile 72% complete                  │
│                                                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │  WAYS TO EARN MORE (AI Suggestions)             │  │
│  │  • Add photos — 2x more tour requests [Add]     │  │
│  │  • Allow office use — matches 4 active searches  │  │
│  │    [Update]                                      │  │
│  │  • Confirm weekend hours — 3 buyers need it      │  │
│  │    [Set Hours]                                   │  │
│  └─────────────────────────────────────────────────┘  │
│                                                       │
│  [Photos]  [Building Info]  [Configuration]           │
│  [Pricing]  [Engagements]  [Activity]                  │
│                                                       │
└───────────────────────────────────────────────────────┘
```

### 3.2 Profile Completeness Score

Not all fields are equal. Completeness is weighted by impact on matching — fields that directly determine whether a buyer match happens carry far more weight than informational fields.

**Tier 1 — Must-Have (60% of score)**

These fields are required for the clearing engine to match and for buyers to make tour decisions. A supplier who fills only these seven items has a fully matchable profile at 60%.

| Field | DB Field | Weight | Why It Matters |
|-------|----------|--------|----------------|
| Photos | ≥ 3 photos uploaded | 15% | Properties with photos get 2x more tour requests. Primary visual decision factor for buyers. |
| Available sqft | available_sqft | 10% | Core matching field — clearing engine can't match without it |
| Target rate | target_rate_sqft | 10% | Core pricing field — buyer all-in rate calculated from this |
| Clear height | clear_height_ft | 8% | Universal buyer concern — determines storage capacity |
| Dock doors | dock_doors | 7% | Most buyers need loading access — shown on every results card |
| Activity tier | activity_tier | 5% | Determines use-type compatibility (storage vs light ops vs distribution) |
| Available from | available_from | 5% | Timing match — buyers filter by when they need space |

**Tier 2 — Matching Boost (30% of score)**

These map to buyer deal-breaker filters (Step 6 of buyer wizard). Missing = system must guess or exclude from deal-breaker matches. Filling these unlocks more precise matching.

| Field | DB Field | Weight | Why It Matters |
|-------|----------|--------|----------------|
| Has office | has_office | 5% | Common buyer deal-breaker filter |
| Weekend / 24/7 access | weekend_access, access_24_7 | 5% | Common buyer deal-breaker filter |
| Min rentable sqft | min_rentable_sqft | 4% | Prevents mismatched size requests |
| Min term | min_term_months | 4% | Prevents mismatched duration requests |
| Parking | parking_spaces | 4% | Buyer deal-breaker for some segments |
| Power supply | power_supply | 4% | Relevant for light ops / distribution buyers |
| Sprinkler | sprinkler_system | 4% | Common requirement, especially for insured goods |

**Tier 3 — Nice-to-Know (10% of score)**

Informational fields that don't affect matching. Buyers don't filter on these. They appear in tour prep (post-commitment) or property detail, not on results cards.

| Field | DB Field | Weight |
|-------|----------|--------|
| Construction type | construction_type | ~1.5% |
| Zoning | zoning | ~1.5% |
| Lot size | lot_size_acres | ~1.5% |
| Year built | year_built | ~1.5% |
| Building size (total) | building_sqft | ~1.5% |
| Drive-in bays | drive_in_bays | ~1.5% |
| All remaining fields | — | ~1% shared |

**Certifications — NOT counted in base profile completeness.**

Certifications (food_grade, fda_registered, hazmat_certified, c_tpat, temperature_controlled, foreign_trade_zone) are only relevant to specific buyer segments. Instead of asking every supplier to fill out six certification fields:

- **Do NOT include certifications in the completeness score**
- **Only surface certification questions via AI suggestions** when there is actual buyer demand in the supplier's area for that certification type
- Example: If food storage buyers are searching in North Charleston → suggestion appears: "Food storage buyers are active in your area. Is your facility food grade?" → [Yes] / [No]
- Both "Yes" and "No" are valuable — "No" prevents the question from reappearing and avoids false matches
- A general storage warehouse should never be nagged about certifications that don't apply to them

**Display:**

Show as "Profile 72% complete" with a simple progress bar. Link to the highest-weight incomplete field (not the first alphabetically).

**Suggestion priority follows the tiers:**
1. Always nag about missing Tier 1 fields first (especially photos — highest single weight)
2. Suggest Tier 2 fields when Tier 1 is complete
3. Rarely or never prompt for Tier 3 fields — let suppliers fill them if they want
4. Certification prompts only appear when demand-triggered

**Backend calculation:**

```python
def calculate_profile_completeness(property) -> dict:
    score = 0.0
    missing = []
    
    # Tier 1 — Must-Have (60%)
    tier1_fields = {
        "photos": (property.photo_count >= 3, 0.15),
        "available_sqft": (property.truth_core.available_sqft is not None, 0.10),
        "target_rate": (property.truth_core.target_rate_sqft is not None and property.truth_core.target_rate_sqft > 0, 0.10),
        "clear_height": (property.clear_height_ft is not None, 0.08),
        "dock_doors": (property.dock_doors is not None, 0.07),
        "activity_tier": (property.truth_core.activity_tier is not None, 0.05),
        "available_from": (property.truth_core.available_from is not None, 0.05),
    }
    
    # Tier 2 — Matching Boost (30%)
    tier2_fields = {
        "has_office": (property.truth_core.has_office is not None, 0.05),
        "access": (property.truth_core.weekend_access is not None or property.truth_core.access_24_7 is not None, 0.05),
        "min_rentable": (property.truth_core.min_rentable_sqft is not None, 0.04),
        "min_term": (property.truth_core.min_term_months is not None, 0.04),
        "parking": (property.parking_spaces is not None, 0.04),
        "power": (property.power_supply is not None, 0.04),
        "sprinkler": (property.sprinkler_system is not None, 0.04),
    }
    
    # Tier 3 — Nice-to-Know (10%)
    tier3_fields = {
        "construction": (property.construction_type is not None, 0.015),
        "zoning": (property.zoning is not None, 0.015),
        "lot_size": (property.lot_size_acres is not None, 0.015),
        "year_built": (property.year_built is not None, 0.015),
        "building_sqft": (property.building_size_sqft is not None, 0.015),
        "drive_in_bays": (property.drive_in_bays is not None, 0.015),
    }
    
    for tier_name, fields in [("tier1", tier1_fields), ("tier2", tier2_fields), ("tier3", tier3_fields)]:
        for field_name, (is_filled, weight) in fields.items():
            if is_filled:
                score += weight
            else:
                missing.append({"field": field_name, "tier": tier_name, "weight": weight})
    
    # Sort missing by weight descending — highest impact first
    missing.sort(key=lambda x: x["weight"], reverse=True)
    
    return {
        "score": round(score * 100),  # percentage
        "missing": missing,
        "top_action": missing[0] if missing else None,  # highest-weight missing field
    }
```

### 3.3 AI Suggestions — Property Specific

Same pattern as portfolio-level but specific to this property. Each suggestion has:
- What to do (plain language)
- Why (data-backed reason)
- Action button that goes directly to the relevant edit

**Data sources for suggestions:**

| Suggestion Type | Data Source | Example |
|----------------|------------|---------|
| Missing profile data (Tier 1) | Profile completeness — Tier 1 fields (see 3.2) | "Add photos to increase tour requests" → [Add Photos]. Always prioritize Tier 1 missing fields first. |
| Missing profile data (Tier 2) | Profile completeness — Tier 2 fields (see 3.2) | "Specify weekend access hours — 3 buyers need it" → [Set Hours]. Only suggest when all Tier 1 fields are complete. |
| Rate optimization | near_miss entries where reason = rate | "3 buyers this month matched everything except rate. Lowering $0.07 would match them." → [Adjust Rate] |
| Feature demand | near_miss entries where reason = missing feature | "5 buyers need office space in your area. Do you have office available?" → [Yes, Add Office] / [No] |
| Availability gap | near_miss where reason = timing | "2 buyers needed space this month but your earliest availability is too far out." → [Update Availability] |
| Certification (demand-triggered) | Buyer search data for area + property goods compatibility | "Food storage buyers are active in Glen Burnie. Is your facility food-grade?" → [Yes, Add] / [No]. Only shown when real buyer demand exists for that certification in the supplier's area. NOT part of profile completeness. |
| Response time | supplier_response data | "Your average response time is 18 hours. Engagements with <4 hour response close 3x more often." → [Enable SMS Notifications] |

**Backend:** `GET /api/supplier/properties/{id}/suggestions` — queries near_miss, supplier_response, buyer search aggregates for this property's area and specs. Returns top 3 suggestions.

**Important:** Every suggestion that asks a yes/no question (e.g., "Do you have office space?") should store the answer immediately — both "Yes, add it" AND "No" are valuable data. "No" prevents the same suggestion from reappearing and updates the property profile. Use a `POST /api/supplier/properties/{id}/suggestion-response` endpoint that stores the response in ContextualMemory (type: enrichment_response).

### 3.4 Photos Section

```
┌─────────────────────────────────────────────────────┐
│  PHOTOS (3)                        [+ Add Photos]   │
│                                                     │
│  [Photo 1]  [Photo 2]  [Photo 3]                   │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │  📱 Upload from your phone                    │  │
│  │                                               │  │
│  │  Scan this QR code to take photos             │  │
│  │  directly from your phone.                    │  │
│  │                                               │  │
│  │       [QR CODE IMAGE]                         │  │
│  │                                               │  │
│  │  Link expires in 30 minutes.                  │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  [Upload from Desktop] (standard file picker)       │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Two upload methods:**

1. **Desktop upload** — standard file input, multi-select, drag-and-drop zone. Accepts jpg/png/heic.

2. **QR code mobile upload:**
   - Clicking [+ Add Photos] or opening this section generates a QR code
   - QR encodes a tokenized URL: `{FRONTEND_URL}/upload/{property_id}/{token}`
   - Token: short-lived (30 minutes), single-property scoped, no login required
   - Mobile page: minimal — camera/gallery picker + upload button + progress indicator
   - Photos upload directly to backend, associated with property_id
   - Desktop page updates in real-time via WebSocket or polling (every 5 seconds) as photos arrive
   - After all photos uploaded, mobile page shows "Done! Photos added to your property."

**Backend:**
- `POST /api/supplier/properties/{id}/upload-token` — generates time-limited token, returns token + QR code URL
- `GET /api/upload/{property_id}/{token}/verify` — validates token (mobile page calls this on load)
- `POST /api/upload/{property_id}/{token}/photos` — accepts multipart file upload, no auth required (token IS auth)
- `GET /api/supplier/properties/{id}/photos` — returns all photos for property (desktop polling)

**Token schema:**
```
UploadToken:
  token: string (uuid or random string)
  property_id: uuid
  created_at: timestamp
  expires_at: timestamp (created_at + 30 minutes)
  is_used: boolean (set true after first upload, but allow multiple uploads within window)
```

### 3.5 Building Info Section

Display all building specs with inline edit capability. Pre-populated from EarnCheck/Gemini data. Fields with "(inferred)" tag can be confirmed or corrected by supplier.

| Field | Value | Edit Type | Notes |
|-------|-------|-----------|-------|
| Building Size | 46,530 sqft | Number input | From data pipeline |
| Clear Height | 30 ft | Number input | |
| Dock Doors | 4 | Number input | |
| Drive-In Bays | 1 | Number input | |
| Year Built | 1980 | Number input | |
| Construction | Metal *(inferred)* | Dropdown [Metal, Concrete, Tilt-up, Masonry] | [Confirm] / [Edit] |
| Building Class | A | Display only | |
| Zoning | M-1 Light Industrial *(inferred)* | Text | [Confirm] / [Edit] |
| Lot Size | 4.02 acres | Number input | |
| Sprinkler | Yes | Toggle | |
| Power Supply | 3-Phase *(inferred)* | Dropdown [Standard, 3-Phase, Manufacturing Grade] | [Confirm] / [Edit] |
| Parking | 20 spaces | Number input | |

Inferred fields show a small "[Confirm]" button. Clicking confirm removes the "(inferred)" tag and stores a ContextualMemory entry (type: enrichment_response) recording that the supplier verified this field.

**Backend:** `PATCH /api/supplier/properties/{id}/specs` — accepts partial updates to building spec fields. Logs changes in TruthCoreChange for audit trail.

### 3.6 Configuration Section

Operational configuration the supplier set during onboarding. All editable.

| Field | Value | Edit Type |
|-------|-------|-----------|
| Available Space | 28,000 sqft | Slider or number input |
| Min Rentable | 8,000 sqft | Number input |
| Activity Tier | Storage Only | Dropdown [Storage, Light Ops, Distribution] |
| Has Office | No | Toggle |
| Weekend Access | No | Toggle |
| 24/7 Access | No | Toggle |
| Min Term | 1 month | Dropdown [1, 3, 6, 12 months] |
| Available From | Immediately | Date picker |
| Operating Hours | Mon-Fri 7am-6pm | Day-by-day schedule editor |

**Certifications sub-section:**

Certifications are NOT shown as a default form to fill out. They appear here ONLY after the supplier has responded to an AI suggestion about a specific certification (e.g., "Is your facility food grade?" → supplier answered Yes or No). This prevents irrelevant certification questions from cluttering the page for suppliers they don't apply to.

| Certification | Status | Source |
|--------------|--------|--------|
| Food Grade | Yes ✓ | Answered via suggestion Feb 15 |
| Hazmat Certified | No | Answered via suggestion Feb 18 |

If no certification questions have been triggered yet, this sub-section is hidden entirely. Certifications are NOT part of the profile completeness score — they are demand-triggered only (see Section 3.2).

**Backend:** `PATCH /api/supplier/properties/{id}/config` — updates TruthCore fields.

### 3.7 Pricing Section

| Field | Value | Edit Type |
|-------|-------|-----------|
| Pricing Model | Automated Payout | Display (set during onboarding, change via support) |
| Your Rate | $0.71/sqft/mo | Number input with market context |
| Projected Annual Revenue | $238,560/yr | Calculated (rate × available_sqft × 12) |
| Market Range | $0.52–$0.82/sqft | From MarketRateCache — display only |

When the supplier adjusts rate, show live update of projected revenue. Show market range for context but don't restrict — supplier can set any rate they want.

**Backend:** `PATCH /api/supplier/properties/{id}/pricing`

### 3.8 Engagements Sub-section (within property detail)

List of all engagements associated with this property.

| Engagement | Buyer Need | Sqft | Rate | Term | Status | Date |
|------------|-----------|------|------|------|--------|------|
| #1234 | Storage, 5K sqft | 5,000 | $0.71 | 6 mo | Active | Jan 15, 2026 |
| #1198 | Distribution, 10K | 10,000 | $0.71 | 12 mo | Tour Scheduled | Feb 20, 2026 |
| #1102 | Storage, 8K | — | — | — | Declined by you | Dec 3, 2025 |

Click row → goes to `/supplier/engagements/[id]`

### 3.9 Activity Log (within property detail)

Chronological feed of everything that's happened with this property:

```
Feb 23 — Shown to 3 buyers (Storage, North Charleston area)
Feb 22 — Deal ping: 5,000 sqft storage, $0.71/sqft → You accepted
Feb 20 — Shown to 5 buyers (2 matched, 3 near-misses: rate too high)
Feb 18 — Photo uploaded via mobile
Feb 15 — Profile updated: confirmed 3-Phase power
Feb 10 — Joined WEx Network
Feb 8  — EarnCheck completed
```

This is a read-only timeline. Helps the supplier understand that the system is actively working on their behalf, even when engagements aren't closing yet.

**Backend:** Assembled from multiple sources: ContextualMemory entries, engagement events, near_miss aggregates (daily summary), profile changes.

---

## 4. Engagements Page (`/supplier/engagements`)

All engagements across all properties. Tabbed by status.

### 4.1 Tabs

| Tab | What's Shown |
|-----|-------------|
| **Action Needed** | Deal pings awaiting response, tours to confirm, agreements to sign. Count badge on tab. |
| **Active** | Engagements with signed agreements, active leases. Currently earning revenue. |
| **In Progress** | Accepted engagements, scheduled tours, pending agreements. Moving toward close. |
| **Past** | Completed leases, declined engagements, expired pings. |

### 4.2 Engagement Card (list item)

```
┌───────────────────────────────────────────────────────┐
│  Engagement #1234                       IN PROGRESS   │
│                                                       │
│  1221 Wilson Rd · 5,000 sqft · Storage                │
│                                                       │
│  Your Rate: $0.71/sqft · Monthly: $3,550              │
│  Term: 6 months · Total: $21,300                      │
│                                                       │
│  Tour: March 5, 10:00 AM — Confirmed ✓               │
│                                                       │
│  Next step: Tour happens → Post-tour confirmation     │
│                                                       │
└───────────────────────────────────────────────────────┘
```

### 4.3 Engagement Detail (`/supplier/engagements/[id]`)

Full timeline of the engagement with all events and current state.

**Engagement Summary** (top):
- Property address, sqft, use type
- Supplier rate, monthly payout, term, total
- Current status with visual progress indicator

**Engagement Timeline** (main content):
```
✓ Feb 20 — Matched: Buyer needs 5,000 sqft storage in Glen Burnie
✓ Feb 20 — You accepted (response time: 2 hours)
✓ Feb 21 — Buyer accepted match & signed WEx Guarantee
✓ Feb 22 — Tour scheduled: March 5, 10:00 AM
✓ Feb 22 — You confirmed tour
○ Mar 5  — Tour (upcoming)
○ TBD    — Post-tour confirmation
○ TBD    — Engagement agreement signed
○ TBD    — Move-in & first payment
```

**Buyer Info** (sidebar or below — limited, anonymized pre-tour):

| Pre-Tour | Post-Tour |
|----------|-----------|
| Use type: Storage | Use type: Storage |
| Sqft needed: 5,000 | Sqft needed: 5,000 |
| Term: 6 months | Term: 6 months |
| Goods: General merchandise | Goods: General merchandise |
| Company: Hidden until tour | Company: Acme Distribution |
| Contact: Via WEx only | Contact: Via WEx only |

**Actions** (contextual based on engagement status):
- If tour pending confirmation: [Confirm Tour] / [Propose New Time]
- If agreement pending: [Review & Sign Agreement]
- If deal ping not yet responded: [Accept] / [Decline] (with reason dropdown)

---

## 5. Payments Page (`/supplier/payments`)

Simple ledger view. Answers: "Did I get paid?"

### 5.1 Earnings Summary (top)

```
TOTAL EARNED          THIS MONTH         NEXT DEPOSIT        PENDING
$12,450.00            $4,260.00          $4,260.00           March 1, 2026
                                         (3 active engagements)
```

### 5.2 Transaction History (table)

| Date | Property | Engagement | Type | Amount | Status |
|------|----------|------------|------|--------|--------|
| Feb 1, 2026 | 1221 Wilson Rd | #1234 | Monthly deposit | $3,550.00 | Deposited ✓ |
| Feb 1, 2026 | 15001 S Figueroa | #1198 | Monthly deposit | $710.00 | Deposited ✓ |
| Jan 1, 2026 | 1221 Wilson Rd | #1234 | Monthly deposit | $3,550.00 | Deposited ✓ |
| Jan 1, 2026 | 15001 S Figueroa | #1198 | Monthly deposit | $710.00 | Deposited ✓ |

**Filters:** Date range, property, engagement
**Export:** [Download CSV] / [Download PDF Statement]

### 5.3 Phase 1 Note (no Stripe Connect yet)

Since Stripe Connect is not in Phase 1, this page shows **ledger entries only** — amounts owed, recorded deposits (manually marked by admin), and projected future deposits. The data model tracks everything, but actual money movement is manual/offline until Stripe Connect is integrated.

**Backend:** 
- `GET /api/supplier/payments` — returns SupplierLedger entries sorted by date
- `GET /api/supplier/payments/summary` — returns aggregate totals
- `GET /api/supplier/payments/export?format=csv&from=2026-01-01&to=2026-02-28` — downloadable report

---

## 6. Account Settings (`/supplier/account`)

### 6.1 Profile

| Field | Edit Type |
|-------|-----------|
| Name | Text input |
| Email | Text input (requires verification if changed) |
| Phone | Text input |
| Company Name | Text input |
| Password | Change password flow (current + new + confirm) |

### 6.2 Notification Preferences

| Notification | SMS | Email | Push |
|-------------|-----|-------|------|
| New deal pings | ✓ | ✓ | — |
| Tour requests | ✓ | ✓ | — |
| Agreement ready | — | ✓ | — |
| Payment deposited | — | ✓ | — |
| Profile suggestions | — | ✓ | — |
| Monthly summary | — | ✓ | — |

Default all SMS and email ON. Supplier can disable but we should discourage disabling SMS for deal pings (show warning: "Deal pings have a 12-hour response window. SMS ensures you don't miss opportunities.").

### 6.3 Payment Info

- Bank account on file (masked: ****4521)
- [Update Bank Info] — Phase 1: manual process (contact support). Phase 2: Stripe Connect onboarding.

### 6.4 Team Management (`/supplier/account/team`)

| Member | Role | Status |
|--------|------|--------|
| John Smith (you) | Admin | Active |
| sarah@company.com | Member | Invited — pending |

**Roles:**
- **Admin** — can edit properties, adjust rates, sign agreements, manage team, view payments
- **Member** — can view properties and engagements, confirm tours, respond to deal pings. Cannot change rates, sign agreements, or manage team.

**Actions:**
- [Invite Team Member] — enter email + role → sends invite email with signup link
- [Remove] — admin can remove members
- [Change Role] — admin can promote member to admin or demote

**MVP scope:** Keep simple. One admin per company initially. Members can view and respond to operational items (tours, pings) but cannot make financial or contractual changes.

**Backend:**
- `GET /api/supplier/team` — list team members
- `POST /api/supplier/team/invite` — send invite (email + role)
- `DELETE /api/supplier/team/{user_id}` — remove member
- `PATCH /api/supplier/team/{user_id}` — change role

**Data model:** User model already has `company` field. Add `company_id` (uuid) to User model to link users to same company. Add `company_role` (admin/member) field.

---

## 7. Data Logging — Near-Miss, Response, Engagement

These are the logging schemas that power the AI suggestion engine. Build now regardless of matching algorithm maturity.

### 7.1 Near-Miss Log

Created by the clearing engine every time a property is evaluated for a buyer match but excluded from results.

```
NearMiss:
  id: uuid
  property_id: uuid
  buyer_need_id: uuid
  match_score: float (nullable — fill in when algorithm provides scores)
  outcome: enum [excluded, low_ranked, shown_not_selected]
  reasons: JSON array [
    {
      field: string,          // "rate", "sqft", "use_type", "feature_missing", "timing", "location"
      detail: string,         // "rate $0.82 is $0.12 above area Tier 1 median of $0.70"
      fix: string             // "lower rate to $0.70 or below"
    }
  ]
  evaluated_at: timestamp
```

**When to create:**
- In the clearing engine matching loop, for every property evaluated but not included in final results
- Also when a property IS shown but buyer doesn't engage (outcome = shown_not_selected, populated from buyer_engagement data)

**Logging rules:**
- Log the top 3 reasons per near-miss (don't log 15 reasons for one exclusion)
- Don't log properties that are obviously wrong (different state, wildly wrong size). Only log near-misses with match_score > 50% (or would have scored > 50% except for 1-2 factors)
- Daily volume estimate: ~50 entries per buyer search × number of daily searches. At 100 searches/day = 5,000 entries/day. Fine for PostgreSQL with a 90-day retention policy.

### 7.2 Supplier Response Log

Created when a supplier responds to (or fails to respond to) a deal ping, DLA outreach, or tour request.

```
SupplierResponse:
  id: uuid
  property_id: uuid
  supplier_id: uuid
  deal_id: uuid (nullable — may not exist yet for DLA)
  dla_token: string (nullable — only for DLA outreach)
  event_type: enum [deal_ping, dla_outreach, tour_request, agreement_request]
  
  sent_at: timestamp
  deadline_at: timestamp
  responded_at: timestamp (nullable — null if expired)
  response_time_hours: float (nullable)
  
  outcome: enum [accepted, declined, counter, expired, confirmed, rescheduled]
  decline_reason: string (nullable) — free text or selected from dropdown
  counter_rate: float (nullable) — if supplier proposed different rate
  
  created_at: timestamp
```

**When to create:**
- When any outbound request is sent to a supplier (deal ping, DLA message, tour request, agreement request)
- Updated when supplier responds or deadline passes

**Decline reason options** (dropdown for supplier, stored as string):
- "Rate too low"
- "Space not available at that time"
- "Wrong use type for my facility"
- "Term too short"
- "Term too long"
- "Sqft too small to be worth it"
- "Already in discussions with another tenant"
- "Other" (free text)

### 7.3 Buyer Engagement Log

Created when a buyer views results and interacts (or doesn't) with property cards.

```
BuyerEngagement:
  id: uuid
  property_id: uuid
  buyer_need_id: uuid
  
  shown_at: timestamp
  position_in_results: int           // 1st, 2nd, 3rd
  tier: enum [tier_1, tier_2]
  
  action_taken: enum [
    accepted,                        // clicked Accept & Schedule Tour
    question_asked,                  // clicked Ask About This Space
    email_list,                      // clicked Email Me This List
    skipped,                         // viewed results page but didn't interact with this card
    bounced                          // left results page without any interaction
  ]
  
  action_at: timestamp (nullable)
  time_on_page_seconds: int (nullable)  // if trackable via frontend analytics
  
  created_at: timestamp
```

**When to create:**
- When the results page loads: create entries for each property shown (action = null initially)
- When buyer takes action: update the relevant entry
- When buyer leaves page: mark remaining entries as "skipped" or "bounced"

**Frontend implementation:** Track via analytics events. On results page load, fire `results_shown` event with property IDs and positions. On button click, fire `property_action` event. On page exit, fire `results_exit` event.

### 7.4 Suggestion Engine Query Patterns

The suggestion engine reads from these three logs to generate recommendations. Here are the key queries:

| Suggestion | Query |
|-----------|-------|
| "Lower rate to match X buyers" | `SELECT COUNT(*) FROM near_miss WHERE property_id = ? AND reasons @> '[{"field": "rate"}]' AND evaluated_at > now() - interval '30 days'` |
| "Add office space" | `SELECT COUNT(*) FROM near_miss WHERE property_id = ? AND reasons @> '[{"field": "feature_missing", "detail": "%office%"}]' AND evaluated_at > now() - interval '30 days'` |
| "Your response time is slow" | `SELECT AVG(response_time_hours) FROM supplier_response WHERE supplier_id = ? AND responded_at IS NOT NULL AND sent_at > now() - interval '30 days'` |
| "Buyers skip your listing" | `SELECT COUNT(*) FROM buyer_engagement WHERE property_id = ? AND action_taken IN ('skipped', 'bounced') AND shown_at > now() - interval '30 days'` |
| "Add photos" | Profile completeness Tier 1 check — photo count < 3. Highest-weight single field (15%). Always suggest first if missing. |
| "Fill [Tier 1 field]" | Profile completeness Tier 1 check — `calculate_profile_completeness()` returns `top_action` with tier=tier1. Suggest in weight order. |
| "Fill [Tier 2 field]" | Profile completeness Tier 2 check — only suggest when all Tier 1 fields are filled. |
| "Is your facility [certification]?" | Only query when: `SELECT COUNT(*) FROM buyer_need WHERE location near property AND goods_type requires certification AND created_at > now() - interval '30 days'` returns > 0. Demand-triggered, not profile-triggered. |

---

## 8. Summary of All Endpoints

### Supplier Dashboard
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/supplier/portfolio | Portfolio summary (income, rate, capacity, occupancy) |
| GET | /api/supplier/actions | Pending actions (pings, tours, agreements) |
| GET | /api/supplier/suggestions | Portfolio-level AI suggestions |

### Properties
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/supplier/properties | List all supplier properties |
| GET | /api/supplier/properties/{id} | Full property detail |
| PATCH | /api/supplier/properties/{id}/specs | Update building specs |
| PATCH | /api/supplier/properties/{id}/config | Update configuration/TruthCore |
| PATCH | /api/supplier/properties/{id}/pricing | Update rate |
| GET | /api/supplier/properties/{id}/suggestions | Property-specific AI suggestions |
| POST | /api/supplier/properties/{id}/suggestion-response | Store yes/no response to suggestion |
| GET | /api/supplier/properties/{id}/photos | List photos |
| DELETE | /api/supplier/properties/{id}/photos/{photo_id} | Remove photo |
| POST | /api/supplier/properties/{id}/upload-token | Generate QR code upload token |
| GET | /api/supplier/properties/{id}/activity | Activity timeline |

### Photo Upload (tokenized, no auth)
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/upload/{property_id}/{token}/verify | Validate upload token |
| POST | /api/upload/{property_id}/{token}/photos | Upload photos (multipart) |

### Engagements
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/supplier/engagements | List all engagements (filterable by status) |
| GET | /api/supplier/engagements/{id} | Engagement detail + timeline |
| POST | /api/supplier/engagements/{id}/respond | Accept or decline deal ping |
| POST | /api/supplier/engagements/{id}/tour/confirm | Confirm or propose new tour time |

### Payments
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/supplier/payments | Transaction history (paginated, filterable) |
| GET | /api/supplier/payments/summary | Earnings summary |
| GET | /api/supplier/payments/export | Download CSV or PDF statement |

### Account & Team
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/supplier/account | Account profile |
| PATCH | /api/supplier/account | Update profile |
| POST | /api/supplier/account/password | Change password |
| GET | /api/supplier/account/notifications | Notification preferences |
| PATCH | /api/supplier/account/notifications | Update preferences |
| GET | /api/supplier/team | List team members |
| POST | /api/supplier/team/invite | Invite member |
| DELETE | /api/supplier/team/{user_id} | Remove member |
| PATCH | /api/supplier/team/{user_id} | Change role |

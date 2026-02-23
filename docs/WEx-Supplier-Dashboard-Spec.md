# Supplier Dashboard — Developer Spec

**For:** Frontend + Backend Developer
**Context:** Supplier-facing dashboard for managing properties, deals, payments, and profile
**Date:** February 2026

---

## Overview

### What We're Building

The supplier dashboard is the command center for warehouse owners who've joined the WEx network. It's where they manage their properties, respond to deals, track earnings, and optimize their listings. But it is NOT where most supplier interaction happens — SMS, email, and phone handle the real-time deal flow. The dashboard is the filing cabinet, not the front desk.

### Design Philosophy

**Set it and forget it.** Most suppliers will visit the dashboard during onboarding to configure their properties, then return only when something specific happens — a payment to verify, a deal to review, or a profile change to make. We design for the supplier who visits once a month, not the one who logs in daily.

**Every screen answers one question:**
- Portfolio page → "How's my portfolio doing?"
- Property detail → "How's this property doing and how can it earn more?"
- Deals page → "What needs my attention right now?"
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

Most deals will be accepted or declined via a text message reply. The dashboard shows the same information in a structured view for suppliers who want the full picture, and it's where actions that require more thought (rate changes, configuration updates, agreement signing) happen.

### Expected Outcomes

**For suppliers:**
- Clear visibility into earnings across their portfolio at a glance
- Never miss a deal opportunity — action items surfaced prominently with time-sensitive indicators
- Data-backed guidance on how to earn more (not generic tips — specific suggestions derived from actual buyer demand and near-miss matching data)
- Easy property management without heavy form-filling (confirm inferred data, upload photos from phone, respond to targeted suggestions)
- Confidence that the system is actively working for them (activity timeline shows matching activity even when deals aren't closing yet)

**For WEx:**
- Higher supplier engagement and profile completeness → better matching → more deals closed
- Near-miss and response logging builds intelligence that improves matching and pricing over time
- Suggestion engine nudges suppliers toward market-competitive rates and in-demand features without WEx ops team having to make individual calls
- Team management allows property management companies to onboard multiple users, expanding supply without proportional ops effort
- Structured deal flow reduces the chance of deals falling through due to missed communications

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
/supplier/deals                    → Active Deals & History
/supplier/deals/[id]               → Deal Detail + Timeline
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

- Total Projected Income = sum of (rate × rented sqft × 12) for all active deals + (rate × available sqft × 12) for listed but unrented space
- Avg Rate = weighted average of supplier rates across portfolio
- Active Capacity = total sqft listed across all in_network properties
- Occupancy = rented sqft / available sqft across portfolio

### 2.2 Action Required (below summary, only shown when items exist)

A notification-style section that surfaces items needing supplier attention. Each item has a description and an action button.

| Source | Display | Action Button |
|--------|---------|---------------|
| New deal ping (in-network match) | "A buyer needs 5,000 sqft storage in your area. $0.75/sqft for 6 months." | [Review Deal] → goes to deal detail |
| DLA outreach response needed | "A buyer matched your property at 1221 Wilson Rd." | [View Opportunity] → goes to DLA page or deal detail |
| Tour to confirm | "Tour requested for March 5 at 1221 Wilson Rd, 10:00 AM" | [Confirm Tour] / [Propose New Time] |
| Agreement to sign | "Engagement agreement ready for Deal #1234" | [Review & Sign] |
| Post-tour follow-up | "How did the tour go for Deal #1234?" | [Tour Went Well] / [Issue to Report] |

When no actions pending: show "All caught up — your properties are actively matching with buyers." (not an empty state)

**Backend:** `GET /api/supplier/actions` — returns pending items across all deal states, sorted by urgency (time-sensitive first).

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
| Rented sqft | Sum of active Deal sqft for this property | |
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
│  [Pricing]  [Deals]  [Activity]                       │
│                                                       │
└───────────────────────────────────────────────────────┘
```

### 3.2 Profile Completeness Score

Calculated from filled vs total fields across these categories:

| Category | Fields Counted | Weight |
|----------|---------------|--------|
| Photos | At least 3 photos uploaded | 25% |
| Building specs | All non-inferred fields confirmed | 20% |
| Configuration | All TruthCore fields populated | 20% |
| Pricing | Rate set + pricing model chosen | 15% |
| Operating hours | Hours specified for each day | 10% |
| Certifications | Relevant certifications confirmed or denied | 10% |

Display as: "Profile 72% complete" with a simple progress indicator. Links to the first incomplete section.

### 3.3 AI Suggestions — Property Specific

Same pattern as portfolio-level but specific to this property. Each suggestion has:
- What to do (plain language)
- Why (data-backed reason)
- Action button that goes directly to the relevant edit

**Data sources for suggestions:**

| Suggestion Type | Data Source | Example |
|----------------|------------|---------|
| Missing profile data | Profile completeness check | "Add photos to increase tour requests" → [Add Photos] |
| Rate optimization | near_miss entries where reason = rate | "3 buyers this month matched everything except rate. Lowering $0.07 would match them." → [Adjust Rate] |
| Feature demand | near_miss entries where reason = missing feature | "5 buyers need office space in your area. Do you have office available?" → [Yes, Add Office] / [No] |
| Availability gap | near_miss where reason = timing | "2 buyers needed space this month but your earliest availability is too far out." → [Update Availability] |
| Certification opportunity | Buyer search data for area + property goods compatibility | "Food storage buyers are active in Glen Burnie. If your facility is food-grade, add the certification." → [Add Certification] / [Not Applicable] |
| Response time | supplier_response data | "Your average response time is 18 hours. Deals with <4 hour response close 3x more often." → [Enable SMS Notifications] |

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
| Certification | Status | Edit |
|--------------|--------|------|
| Food Grade | Not specified | [Yes] / [No] / [Not Sure] |
| FDA Registered | Not specified | [Yes] / [No] |
| Hazmat Certified | Not specified | [Yes] / [No] |
| C-TPAT | Not specified | [Yes] / [No] |
| Temperature Controlled | Not specified | [Yes] / [No] |
| Foreign Trade Zone | Not specified | [Yes] / [No] |

"Not specified" certifications contribute to profile incompleteness. Answering "No" is better than leaving blank — it prevents false matches and removes the suggestion prompt.

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

### 3.8 Deals Sub-section (within property detail)

List of all deals associated with this property.

| Deal | Buyer Need | Sqft | Rate | Term | Status | Date |
|------|-----------|------|------|------|--------|------|
| #1234 | Storage, 5K sqft | 5,000 | $0.71 | 6 mo | Active | Jan 15, 2026 |
| #1198 | Distribution, 10K | 10,000 | $0.71 | 12 mo | Tour Scheduled | Feb 20, 2026 |
| #1102 | Storage, 8K | — | — | — | Declined by you | Dec 3, 2025 |

Click row → goes to `/supplier/deals/[id]`

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

This is a read-only timeline. Helps the supplier understand that the system is actively working on their behalf, even when deals aren't closing yet.

**Backend:** Assembled from multiple sources: ContextualMemory entries, Deal events, near_miss aggregates (daily summary), profile changes.

---

## 4. Deals Page (`/supplier/deals`)

All deals across all properties. Tabbed by status.

### 4.1 Tabs

| Tab | What's Shown |
|-----|-------------|
| **Action Needed** | Deal pings awaiting response, tours to confirm, agreements to sign. Count badge on tab. |
| **Active** | Deals with signed agreements, active leases. Currently earning revenue. |
| **In Progress** | Accepted deals, scheduled tours, pending agreements. Moving toward close. |
| **Past** | Completed leases, declined deals, expired pings. |

### 4.2 Deal Card (list item)

```
┌───────────────────────────────────────────────────────┐
│  Deal #1234                             IN PROGRESS   │
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

### 4.3 Deal Detail (`/supplier/deals/[id]`)

Full timeline of the deal with all events and current state.

**Deal Summary** (top):
- Property address, sqft, use type
- Supplier rate, monthly payout, term, total
- Current status with visual progress indicator

**Deal Timeline** (main content):
```
✓ Feb 20 — Deal matched: Buyer needs 5,000 sqft storage in Glen Burnie
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

**Actions** (contextual based on deal status):
- If tour pending confirmation: [Confirm Tour] / [Propose New Time]
- If agreement pending: [Review & Sign Agreement]
- If deal ping not yet responded: [Accept Deal] / [Decline] (with reason dropdown)

---

## 5. Payments Page (`/supplier/payments`)

Simple ledger view. Answers: "Did I get paid?"

### 5.1 Earnings Summary (top)

```
TOTAL EARNED          THIS MONTH         NEXT DEPOSIT        PENDING
$12,450.00            $4,260.00          $4,260.00           March 1, 2026
                                         (3 active deals)
```

### 5.2 Transaction History (table)

| Date | Property | Deal | Type | Amount | Status |
|------|----------|------|------|--------|--------|
| Feb 1, 2026 | 1221 Wilson Rd | #1234 | Monthly deposit | $3,550.00 | Deposited ✓ |
| Feb 1, 2026 | 15001 S Figueroa | #1198 | Monthly deposit | $710.00 | Deposited ✓ |
| Jan 1, 2026 | 1221 Wilson Rd | #1234 | Monthly deposit | $3,550.00 | Deposited ✓ |
| Jan 1, 2026 | 15001 S Figueroa | #1198 | Monthly deposit | $710.00 | Deposited ✓ |

**Filters:** Date range, property, deal
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
- **Member** — can view properties and deals, confirm tours, respond to deal pings. Cannot change rates, sign agreements, or manage team.

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
- "Deal term too short"
- "Deal term too long"
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
| "Add photos" | Profile completeness check — no query needed, just check if photo count < 3 |

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

### Deals
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/supplier/deals | List all deals (filterable by status) |
| GET | /api/supplier/deals/{id} | Deal detail + timeline |
| POST | /api/supplier/deals/{id}/respond | Accept or decline deal ping |
| POST | /api/supplier/deals/{id}/tour/confirm | Confirm or propose new tour time |

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

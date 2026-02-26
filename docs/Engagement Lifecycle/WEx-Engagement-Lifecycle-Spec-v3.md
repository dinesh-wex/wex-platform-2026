# Engagement Lifecycle — Developer Spec v3

**For:** Frontend + Backend Developer  
**Context:** Complete lifecycle from clearing engine match through active lease. The engagement is the central object both parties interact with.  
**Version:** v3 — February 2026  
**Changes from v2:** Buyer account creation replaces contact capture step. Buyers must create a verified account before signing the WEx Guarantee. `contact_captured` state removed; `account_created` state added. `/contact` endpoint replaced by `/link-buyer`. `buyer_email`, `buyer_phone`, `contact_captured_at` fields removed from Engagement model; `account_created_at` added. Google/Social SSO deferred to future sprint — Phase 1 is email + password only.

---

## Overview

### What We're Building

The engagement is the single object that tracks the entire relationship between a buyer, a supplier, and a property from the moment a match is created through active occupancy and payment. It's the spine of the platform — the buyer dashboard, supplier dashboard, tour flow, agreements, and payments are all just different views of the engagement at different stages.

### Why This Matters

Everything before the engagement (EarnCheck, buyer wizard, matching) is lead generation. Everything after (payments, renewals) is account management. The engagement IS the transaction — and every day it sits in an intermediate state is a day the deal can fall apart. The design priority is speed: minimize the time and friction between "match created" and "lease is signed and payments are flowing."

### Design Principles

**Speed kills deals.** Every transition should happen in hours, not days. The target is: supplier accepts deal ping → buyer accepts match → tour completed → agreement signed → move-in ready in under 5 business days. Every notification has a deadline. Every pending state has an expiration.

**Both parties see their side, never the other's.** The buyer sees their all-in rate and the engagement from their perspective. The supplier sees their rate and the engagement from theirs. WEx sees everything. The engagement model stores both views but the API never leaks the wrong data to the wrong party.

**SMS is the primary action channel, dashboard is the record.** Most state transitions are triggered by SMS responses or email clicks, not by logging into the dashboard. The dashboard shows current state and history. Design notifications first, dashboard views second.

**Nothing is wasted.** Engagements that don't close still produce data — decline reasons, drop-off stages, response times. Every outcome feeds the intelligence flywheel.

**Browse freely, account required to commit.** Buyers can search, browse results, view match cards, and see all pricing anonymously with zero friction. The moment they click "Accept & Schedule Tour," account creation is required. The property address is the highest-value thing WEx delivers — it must be protected by a verified identity before it is revealed.

---

## 0. WEx Guarantee — Definition

The WEx Guarantee is the platform's commitment to both parties that WEx is managing this transaction and stands behind it. It is NOT just an anti-circumvention clause. It is a bilateral protection instrument.

### 0.1 What the WEx Guarantee Covers

**Buyer protections:**
- Space will be as described and represented at time of match (size, features, access, zoning)
- If the space materially misrepresents the listing, WEx will facilitate resolution or find an alternative
- Payment is held and disbursed through WEx — buyer is not paying a stranger directly
- Dispute resolution process is available through WEx if issues arise during occupancy
- WEx is the counterparty for the transaction, not the supplier directly

**Supplier protections:**
- Buyer has been verified and committed (guarantee signed) before the supplier's address is revealed
- Buyer cannot directly contact supplier to negotiate around WEx (anti-circumvention)
- WEx processes and guarantees payment disbursement on the schedule in the agreement
- Supplier's rate is protected — WEx charges its margin separately, buyer's all-in rate is never shown to supplier

**Platform terms (both parties):**
- All negotiations, modifications, and renewals must go through WEx
- Either party attempting to transact outside WEx for this engagement or any future engagement with each other is a material breach
- WEx retains a commission on renewals for 24 months after the initial term ends, regardless of whether the renewal happens through the platform

### 0.2 When Each Party Agrees to the WEx Guarantee

**Buyers:** Sign during the commitment flow — Step 2 of the accept-to-tour sequence (see Section 4.3). The buyer must have created a verified account before the guarantee is presented. Checkbox + timestamp + IP address. Must occur before address is revealed.

**Suppliers — Tier 1 (EarnCheck / Direct Onboarding):**  
Suppliers who entered through EarnCheck or the direct onboarding flow agreed to WEx platform terms during their onboarding. The deal ping for these suppliers does NOT require re-acceptance of terms — their platform agreement already covers all engagements. The deal ping for Tier 1 suppliers is operational confirmation only ("are you available and interested in this specific deal?").

**Suppliers — Tier 2 (DLA / Cold Outreach / Never Onboarded):**  
These suppliers have NOT agreed to WEx platform terms. The deal ping for Tier 2 suppliers is a combined: "Here's a deal for you — AND here are WEx's terms you're agreeing to by saying YES."  
- Deal ping SMS includes a short-link to a one-page WEx terms summary
- Reply YES = acceptance of WEx platform terms for this and future engagements on the platform
- terms_accepted_at and terms_version stored on the engagement record
- Supplier is simultaneously added to the supplier database as an active (term-accepted) partner
- They do NOT need to go through full onboarding to participate — the deal ping acceptance is their lightweight onboarding

**WEx Guarantee Document:** The full guarantee text is version-controlled. Every engagement stores the version in effect at the time of signing. Buyers see the guarantee in their commitment flow. Tier 2 suppliers see a condensed version in the deal ping. Both versions reference the same underlying legal text.

---

## 1. Engagement State Machine

### 1.1 States

The engagement is created when the clearing engine identifies a match. This happens BEFORE the buyer sees results. The supplier is pinged first, and their response determines whether they appear as Tier 1 or are withheld from buyer results.

```
PRE-BUYER STATES (supplier-side):
deal_ping_sent        → Clearing engine created the match; supplier notified via SMS/email; 12hr response window open
deal_ping_accepted    → Supplier replied YES (and agreed to WEx terms if Tier 2); property now eligible for Tier 1 buyer results
deal_ping_declined    → Supplier replied NO; engagement closed; clearing engine notified to find replacement

BUYER-FACING STATES:
matched               → Property is shown to buyer on results page (supplier has pre-accepted)
buyer_reviewing       → Buyer is actively viewing this match
buyer_accepted        → Buyer clicked "Accept & Schedule Tour" or "Book Instantly"
account_created       → Buyer created a verified account; buyer_id set on engagement
guarantee_signed      → Buyer signed WEx Occupancy Guarantee (tied to verified account)

TOUR PATH:
address_revealed      → Property address shared with buyer (tour path entry)
tour_requested        → Buyer selected tour date/time; supplier notified to confirm
tour_confirmed        → Supplier confirmed tour date
tour_rescheduled      → One party proposed a new time (loops back to tour_confirmed)
tour_completed        → Tour happened; awaiting post-tour decision

INSTANT BOOK PATH:
instant_book_requested → Buyer chose "Book Instantly" (skips tour); system proceeds directly to agreement

POST-TOUR / POST-INSTANT-BOOK:
buyer_confirmed       → Buyer wants to proceed (post-tour) or confirmed instant book
agreement_sent        → Engagement agreement sent to both parties
agreement_signed      → Both parties signed the engagement agreement
onboarding            → Buyer submitting insurance, docs, payment setup
active                → Lease is active, payments are flowing
completed             → Lease term ended normally

TERMINAL STATES:
cancelled             → Cancelled by either party (with reason + stage)
expired               → Timed out at any stage (deadline passed without action)
declined_by_buyer     → Buyer explicitly passed on this match
declined_by_supplier  → Supplier declined deal ping (pre-buyer) or tour (post-acceptance)
```

### 1.2 State Transitions

```
CLEARING ENGINE CREATES MATCH
         │
         ▼
  ┌─────────────────┐
  │ deal_ping_sent  │──── 12hr window for supplier
  └────────┬────────┘
           │
    ┌──────┴──────┐
    │ YES         │ NO
    ▼             ▼
┌──────────────┐  ┌─────────────────┐
│deal_ping_    │  │deal_ping_       │
│accepted      │  │declined         │ → Clearing engine finds replacement
└──────┬───────┘  └─────────────────┘   Buyer sees "We're confirming space"
       │
       │ Tier 2 only: terms_accepted_at stored on YES
       │
       ▼
  ┌──────────┐
  │ matched  │ ← Property appears in buyer results (Tier 1)
  └────┬─────┘
       │ buyer views results page
       ▼
  ┌─────────────────┐
  │ buyer_reviewing │
  └────────┬────────┘
           │
    ┌──────┴──────────────────────┐
    │ clicks            clicks    │ passes
    │ "Accept &         "Book     ▼
    │ Schedule Tour"    Instantly"  ┌───────────────┐
    │                  (separate   │declined_by_    │
    │                  path below) │buyer           │
    │                              └───────────────┘
    ▼
┌──────────────────┐
│ buyer_accepted   │
└────────┬─────────┘
         │ account creation form
         ▼
┌──────────────────┐
│ account_created  │ ← buyer_id set on engagement; verified identity established
└────────┬─────────┘
         │ guarantee checkbox (immediately after account creation)
         ▼
┌──────────────────┐
│guarantee_signed  │
└────────┬─────────┘
         │
    ┌────┴──────────────────────┐
    │ Tour Path                 │ Instant Book Path
    ▼                           ▼
┌──────────────────┐  ┌─────────────────────────┐
│address_revealed  │  │instant_book_requested   │
└────────┬─────────┘  └────────────┬────────────┘
         │                         │
         │ buyer picks date/time   │ system confirms availability
         ▼                         │
┌──────────────────┐               │
│tour_requested    │──── 12hr      │
└────────┬─────────┘  deadline for │
         │            supplier     │
   ┌─────┼──────┐                  │
confirm alt time decline           │
   │      │      │                 │
   ▼      ▼      ▼                 │
┌───────┐┌─────┐┌──────────────┐  │
│tour_  ││tour_││declined_by_  │  │
│confir-││resch││supplier      │  │
│med    ││eduled│└──────────────┘  │
└───┬───┘└─────┘                  │
    │ tour happens                 │
    ▼                              │
┌──────────────────┐               │
│tour_completed    │               │
└────────┬─────────┘               │
         │                         │
    ┌────┴─────┐                   │
    │          │                   │
proceed    pass/Q&A                │
    │                              │
    ▼                              │
┌──────────────────┐               │
│buyer_confirmed   │◄──────────────┘
└────────┬─────────┘
         │ system sends agreement
         ▼
┌──────────────────┐
│agreement_sent    │──── 72hr deadline for both to sign
└────────┬─────────┘
         │ both sign
         ▼
┌──────────────────┐
│agreement_signed  │
└────────┬─────────┘
         │ buyer submits docs
         ▼
┌──────────────────┐
│onboarding        │──── 5 business day target
└────────┬─────────┘
         │ all docs verified + start date reached
         ▼
┌──────────────────┐
│active            │
└────────┬─────────┘
         │ term ends
         ▼
┌──────────────────┐
│completed         │
└──────────────────┘
```

### 1.3 Transition Rules & Deadlines

Every pending state has a deadline. Expired deadlines trigger notifications and eventually auto-cancel.

| From State | To State | Trigger | Deadline | On Expiry |
|-----------|----------|---------|----------|-----------|
| deal_ping_sent → deal_ping_accepted | Supplier replies YES | **12 hours** | Reminder at 6hrs. At 12hrs: mark deal_ping_expired (sub-status); clearing engine notified; buyer shown "confirming space" placeholder |
| deal_ping_sent → deal_ping_declined | Supplier replies NO | 12 hours | Clearing engine finds next match |
| deal_ping_accepted → matched | System — buyer results refresh | Immediate | — |
| matched → buyer_reviewing | Buyer loads results page | — | — |
| buyer_reviewing → buyer_accepted | Buyer clicks "Accept & Schedule Tour" or "Book Instantly" | — | — |
| buyer_reviewing → declined_by_buyer | Buyer clicks "Pass" or leaves | — | — |
| buyer_accepted → account_created | Buyer creates account (email + password) | Session (no auto-cancel — form stays open) | — |
| account_created → guarantee_signed | Buyer checks guarantee agreement box | Immediate after account creation | Form stays open, no auto-cancel |
| guarantee_signed → address_revealed | Automatic (tour path) | Immediate | — |
| guarantee_signed → instant_book_requested | Buyer selects Book Instantly | Immediate | — |
| address_revealed → tour_requested | Buyer picks tour date/time | 7 days | Reminder at 3 days. Expire at 7 → notify both, mark expired |
| tour_requested → tour_confirmed | Supplier confirms tour | **12 hours** | Reminder at 6hrs. At 12hrs: auto-notify buyer "supplier unavailable, we'll find alternatives", mark expired, log supplier_response |
| tour_requested → tour_rescheduled | Supplier proposes alt time | 12 hours | Same as above |
| tour_rescheduled → tour_confirmed | Buyer accepts new time | 24 hours | Reminder at 12hrs. Expire at 24hrs. |
| tour_rescheduled → tour_requested | Buyer proposes different time | 24 hours | — |
| tour_confirmed → tour_completed | Tour date passes + follow-up sent | Auto (24hrs after tour) | — |
| instant_book_requested → buyer_confirmed | System confirms space still available | Immediate | If space unavailable, revert to address_revealed with notification |
| tour_completed → buyer_confirmed | Buyer confirms they want to proceed | **48 hours** | Reminder at 24hrs. Final at 48hrs. Expire at 72hrs. |
| tour_completed → declined_by_buyer | Buyer passes (with optional reason) | 48 hours | — |
| buyer_confirmed → agreement_sent | System generates and sends agreement | Immediate | — |
| agreement_sent → agreement_signed | Both parties sign (checkbox) | **72 hours** | Reminder at 24hrs and 48hrs. Expire at 72hrs. |
| agreement_signed → onboarding | Automatic — buyer begins doc submission | Immediate | — |
| onboarding → active | All docs verified, lease start date reached | **5 business days** target | Admin follow-up if stalls past 3 days |
| active → completed | Lease end date reached | Automatic | Renewal prompt 30 days before end |
| any state → cancelled | Either party requests cancellation | — | Reason and stage stored |

### 1.4 Re-entry Rules

| Scenario | Behavior |
|----------|----------|
| Supplier doesn't respond to deal ping within 12hrs | Engagement marked deal_ping_expired. Clearing engine finds next-best supplier. Buyer results may update if they haven't yet viewed. If buyer already viewing results, that property is quietly removed. |
| Supplier declines deal ping | Same as above. If no replacement found within 24hrs, buyer notified: "We're working on finding additional spaces that match your needs." |
| Buyer's engagement expires at tour_requested (supplier didn't confirm) | Buyer auto-returns to results page with this property removed. Other matches still available. If no matches remain, new matching triggered. |
| Buyer declines after tour | Property returns to available pool. Engagement logged as declined_by_buyer with reason. Buyer can continue viewing other matches. |
| Engagement expires at agreement stage | Both notified. Archived. Buyer prompted: "Still looking? We can rematch you." |
| Returning buyer — already has account | Buyer clicks "Accept & Schedule Tour" → login form presented instead of registration. On login, engagement linked to existing account. Proceeds to guarantee step. |

---

## 2. Engagement Data Model

### 2.1 Core Schema

```
Engagement:
  id: uuid

  # Parties
  buyer_id: uuid (FK → User, NULLABLE)
  # buyer_id is null from deal_ping_sent through buyer_accepted.
  # It is populated at account_created — the moment the buyer creates a verified account.
  # From account_created onward, all events, the guarantee, and agreements are tied
  # to a real persistent identity. buyer_need_id (from anonymous session token) is the
  # link to the buyer's search until buyer_id is set.
  buyer_need_id: uuid (FK → BuyerNeed)
  supplier_id: uuid (FK → User)
  # supplier_id records who actioned the deal ping. AUDIT TRAIL ONLY.
  # Authorization checks use company_id via the property FK, not supplier_id directly.
  property_id: uuid (FK → Warehouse)
  broker_id: uuid (nullable, FK → User)

  # Matching
  match_score: float
  match_explanation: text
  tier: enum [tier_1, tier_2]  # tier_1 = supplier pre-accepted; tier_2 = DLA or cold

  # Status
  status: enum [
    deal_ping_sent, deal_ping_accepted, deal_ping_declined,
    matched, buyer_reviewing, buyer_accepted, account_created,
    guarantee_signed, address_revealed,
    tour_requested, tour_confirmed, tour_rescheduled, tour_completed,
    instant_book_requested,
    buyer_confirmed, agreement_sent, agreement_signed,
    onboarding, active, completed,
    cancelled, expired, declined_by_buyer, declined_by_supplier
  ]

  previous_status: string (nullable)
  status_changed_at: timestamp

  # Pricing (stored at creation, immutable for this engagement)
  supplier_rate_sqft: float
  buyer_rate_sqft: float            # supplier_rate × 1.20 × 1.06
  wex_revenue_sqft: float
  sqft: int
  term_months: int
  monthly_buyer_total: float
  monthly_supplier_payout: float
  monthly_wex_revenue: float

  # Implementation note: The formula supplier_rate × 1.20 × 1.06 is implemented as
  # calculate_default_buyer_rate() in services/pricing_engine.py. This is the standard
  # "Global Rate" used for engagement pricing. The separate PricingEngine class
  # (market-specific spreads, feature adjustments) exists for future Phase 2 dynamic
  # pricing — it is NOT used for engagement rate calculation in Phase 1.
  # Engagements always use the fixed formula.

  # Deal Ping (pre-buyer)
  deal_ping_sent_at: timestamp (nullable)
  deal_ping_responded_at: timestamp (nullable)
  deal_ping_response: enum [accepted, declined] (nullable)
  deal_ping_expires_at: timestamp (nullable)

  # Supplier Terms (Tier 2 only)
  supplier_terms_accepted: boolean (default false)
  supplier_terms_accepted_at: timestamp (nullable)
  supplier_terms_version: string (nullable)  # e.g., "platform-terms-v1.0-2026-02"

  # Account Creation (buyer)
  account_created_at: timestamp (nullable)
  # Populated when buyer creates account at buyer_accepted → account_created transition.
  # buyer_id is set simultaneously. From this point forward buyer identity is verified.

  # Guarantee (buyer)
  guarantee_signed_at: timestamp (nullable)
  guarantee_ip_address: string (nullable)
  guarantee_terms_version: string (nullable)

  # Path
  path: enum [tour, instant_book] (nullable)  # set at buyer_accepted

  # Tour
  tour_requested_date: date (nullable)
  tour_requested_time: time (nullable)
  tour_requested_at: timestamp (nullable)
  tour_confirmed_at: timestamp (nullable)
  tour_rescheduled_date: date (nullable)
  tour_rescheduled_time: time (nullable)
  tour_rescheduled_by: enum [buyer, supplier] (nullable)
  tour_completed_at: timestamp (nullable)
  tour_outcome: enum [confirmed, passed, adjustment_needed] (nullable)
  tour_outcome_reason: text (nullable)
  tour_followup_sent_at: timestamp (nullable)

  # Instant Book
  instant_book_requested_at: timestamp (nullable)
  instant_book_confirmed_at: timestamp (nullable)

  # Agreement
  agreement_sent_at: timestamp (nullable)
  buyer_agreement_signed_at: timestamp (nullable)
  supplier_agreement_signed_at: timestamp (nullable)
  agreement_text_version: string (nullable)

  # Onboarding
  onboarding_started_at: timestamp (nullable)
  insurance_uploaded: boolean (default false)
  company_docs_uploaded: boolean (default false)
  payment_method_added: boolean (default false)
  onboarding_completed_at: timestamp (nullable)

  # Lease
  lease_start_date: date (nullable)
  lease_end_date: date (nullable)
  move_in_confirmed_at: timestamp (nullable)

  # Termination
  cancelled_at: timestamp (nullable)
  cancelled_by: enum [buyer, supplier, admin, system] (nullable)
  cancel_reason: text (nullable)
  cancel_stage: string (nullable)
  expired_at: timestamp (nullable)
  expired_stage: string (nullable)

  # Decline
  decline_reason: text (nullable)
  decline_party: enum [buyer, supplier] (nullable)

  # Metadata
  created_at: timestamp
  updated_at: timestamp
```

### 2.2 Engagement Event Log

Every state transition is logged as an event. This powers the timeline view on both dashboards.

```
EngagementEvent:
  id: uuid
  engagement_id: uuid (FK → Engagement)

  event_type: enum [
    created,
    deal_ping_sent, deal_ping_accepted, deal_ping_declined, deal_ping_expired,
    supplier_terms_accepted,
    status_changed,
    account_created, guarantee_signed, address_revealed,
    instant_book_requested, instant_book_confirmed,
    tour_requested, tour_confirmed, tour_rescheduled, tour_completed,
    tour_followup_sent, tour_outcome_recorded,
    qa_question_submitted, qa_answer_provided, qa_routed_to_supplier,
    agreement_sent, buyer_signed, supplier_signed,
    onboarding_doc_uploaded, onboarding_completed,
    lease_activated, payment_recorded, payment_missed,
    lease_completed, renewal_prompted,
    cancelled, expired,
    reminder_sent, deadline_warning,
    note_added
  ]

  actor: enum [buyer, supplier, admin, system]

  data: JSON  # event-specific payload
  # Examples:
  #   deal_ping_accepted: {"response_time_mins": 47, "terms_accepted": true, "terms_version": "platform-terms-v1.0"}
  #   account_created: {"email": "buyer@company.com", "method": "email_password"}
  #   tour_outcome_recorded: {"outcome": "passed", "reason": "Ceiling height too low"}
  #   qa_routed_to_supplier: {"question_id": "uuid", "routed_at": "...", "ai_confidence": 0.3}

  created_at: timestamp
```

---

## 3. Pre-Buyer Phase: Deal Ping Flow

This section is new in v2. The deal ping happens before the buyer sees results. It is the moment the supplier decides whether to participate in this engagement.

### 3.1 When the Deal Ping Fires

The clearing engine creates a match. At that moment:
1. An Engagement record is created with status: `deal_ping_sent`
2. A 12-hour expiration is set (`deal_ping_expires_at = now() + 12hrs`)
3. Notifications fire to the supplier immediately (SMS + email simultaneously)
4. The property is NOT yet shown to the buyer

**Integration with existing clearing engine:** The clearing engine currently creates `Match` and `SupplierResponse` records. With the engagement lifecycle, the clearing engine additionally creates an `Engagement` record (status: `deal_ping_sent`) for each match. The existing `Match` record remains as the matching-algorithm artifact; the `Engagement` is the lifecycle object. The `SupplierResponse` model is retained for response-time analytics but is no longer the primary engagement tracker. The engagement stores a reference to the originating `match_id` but owns the lifecycle state.

The buyer sees a "Searching..." or "Confirming available spaces" state while pings are resolving. A short wait (up to 5 minutes) gives initial fast responders a chance to reply before results render. After 5 minutes, any pre-accepted matches render as Tier 1. Remaining pending pings continue resolving in the background and results update in near-real-time.

### 3.2 Deal Ping: Tier 1 Suppliers (EarnCheck / Direct Onboarded)

These suppliers have already agreed to WEx platform terms. The ping is purely operational.

**Supplier SMS:**
```
WEx: New deal match!
Buyer needs 5,000 sqft for storage, 6 months.
Your rate: $0.71/sqft ($3,550/mo guaranteed payout).
Interested in this deal?
Reply YES to confirm availability or NO to pass.
You have 12 hours to respond.
```

**Supplier email (more detail):**
```
Subject: Deal Match — Buyer Needs 5,000 sqft Storage in Charleston

WEx has matched a buyer to your property.

Property: 7704 Southrail Rd
Buyer needs: 5,000 sqft · Storage · 6 months
Your payout: $0.71/sqft · $3,550/mo · $21,300 total

If you're available and interested, confirm now.

[YES — I'm In]     [NO — Pass]

You have 12 hours to respond. If we don't hear from you, this match 
will be passed to another supplier.
```

**Response handling:**
- YES → `deal_ping_accepted`; `deal_ping_responded_at` stored; property enters buyer results as Tier 1
- NO → `deal_ping_declined`; engagement closed; clearing engine finds next-best supplier; buyer not affected if they haven't seen results yet

### 3.3 Deal Ping: Tier 2 Suppliers (DLA / Cold Outreach / Never Onboarded)

These suppliers have NOT agreed to WEx terms. The ping combines the deal offer with terms acceptance. Reply YES = acceptance of the deal AND WEx platform terms.

**Supplier SMS:**
```
WEx: A buyer needs your warehouse space.
5,000 sqft · Storage · 6 months · $3,550/mo payout to you.
To accept, review our terms: [link]
Reply YES to accept (and agree to WEx terms) or NO to pass.
12 hours to respond.
```

**Supplier email:**
```
Subject: Warehouse Rental Opportunity — 5,000 sqft Storage, 6 months

A buyer is looking for exactly what your property offers.

Buyer needs: 5,000 sqft · Storage · 6 months
Your payout: $0.71/sqft · $3,550/mo guaranteed
Total: $21,300 for the term

How it works:
- WEx manages the transaction — you don't negotiate or collect payments directly
- We handle contracts, insurance verification, and billing
- You receive a monthly deposit for the duration of the lease

Before you accept, review WEx's platform terms: [link to one-page terms summary]
By replying YES, you agree to these terms for this and any future WEx engagements.

[YES — Accept Deal & Terms]     [NO — Pass]

You have 12 hours to respond.
```

**On YES response (Tier 2):**
- `deal_ping_accepted`, `supplier_terms_accepted = true`, `supplier_terms_accepted_at`, `supplier_terms_version` stored
- Supplier record updated: `platform_terms_accepted = true`, `platform_terms_accepted_at`
- Property enters buyer results as Tier 1 (supplier accepted = Tier 1 regardless of how they came in)
- Supplier receives a welcome SMS: "You're set up with WEx. A buyer is being matched now. We'll be in touch as the deal progresses."

---

## 4. The Accept-to-Tour Flow (Detailed)

This is the critical sequence from buyer accepting a match through the tour itself.

### 4.1 Step 1: Buyer Accepts Match

**Trigger:** Buyer clicks "Accept & Schedule Tour" OR "Book Instantly" on results card.

**What happens:**
- Engagement status: buyer_reviewing → buyer_accepted
- `path` field set: `tour` or `instant_book`
- Event logged: status_changed
- Results page transitions to the commitment flow (modal or inline expansion — NOT a page redirect)

### 4.2 Step 2: Account Creation

**Why here:** The property address is the highest-value thing WEx delivers. A buyer with an unverified email could take the address and contact the supplier directly, bypassing WEx entirely. Account creation at this step establishes verified identity before any protected information is revealed. The guarantee signed by a verified account is legally defensible. By the time a buyer reaches "Accept," they have seen satellite imagery, neighborhood, match score, rate, and term — they want this space. Account creation at this point converts well because it feels like completing a commitment, not a surprise gate.

**What the buyer sees:**

```
┌─────────────────────────────────────────────────┐
│                                                 │
│  Create your WEx account to continue.           │
│                                                 │
│  Email                                          │
│  [________________________]                     │
│                                                 │
│  Password                                       │
│  [________________________]  [show]             │
│                                                 │
│  Confirm password                               │
│  [________________________]                     │
│                                                 │
│  Mobile number (optional)                       │
│  [________________________]                     │
│  For tour reminders and updates                 │
│                                                 │
│  [ Create Account & Continue ]                  │
│                                                 │
│  Already have an account? Sign in               │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Returning buyer — login path:**
- Buyer clicks "Already have an account? Sign in"
- Login form presented (email + password)
- On successful login, engagement linked to existing account via `/api/engagements/{id}/link-buyer`
- Proceeds directly to guarantee step

**What happens on successful registration:**
- `POST /api/auth/register` called with `{email, password, phone?, engagement_id}`
- User record created; auth token returned
- `engagement.buyer_id` set to new user's id (within same transaction)
- `engagement.account_created_at` stored
- Engagement status: buyer_accepted → account_created
- Event logged: account_created (actor: buyer)
- Guarantee step presented immediately — no additional navigation

**Phase 1 auth method:** Email + password only. Google/Social SSO deferred to future sprint.

### 4.3 Step 3: WEx Guarantee

**What the buyer sees:**
```
┌─────────────────────────────────────────────────┐
│                                                 │
│  The WEx Guarantee protects you.                │
│                                                 │
│  When you proceed:                              │
│  ✓ The space will be as described               │
│  ✓ Your payment goes through WEx, not           │
│    directly to the owner                        │
│  ✓ WEx handles disputes if issues arise         │
│  ✓ Your contact info stays private until        │
│    the tour is confirmed                        │
│                                                 │
│  ☐ I agree to the WEx Occupancy Guarantee       │
│    [Read full terms ↓]                          │
│                                                 │
│  [ Continue ]                                   │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Copy rules:**
- Lead with what the buyer GETS (protection, verification, dispute resolution)
- Anti-circumvention is embedded in the legal terms, not called out explicitly
- Never use the word "anti-circumvention" in buyer-facing copy

**What happens:**
- Engagement status: account_created → guarantee_signed
- guarantee_signed_at, guarantee_ip_address, guarantee_terms_version stored
- BuyerAgreement record created (type: occupancy_guarantee)

**Model distinction:** `BuyerAgreement` (existing model, type: `occupancy_guarantee`) stores the buyer's signed WEx Guarantee — this is a platform-level protection document. `EngagementAgreement` (Section 6.4) stores the engagement-specific lease agreement with dual-sign workflow. These are two separate records: the guarantee is a precondition for the engagement agreement. Both are linked to the engagement via `engagement_id`.

- If path = instant_book → status goes to instant_book_requested (Section 5)
- If path = tour → status goes to address_revealed (Section 4.4)

### 4.4 Step 4: Address Revealed (Tour Path Only)

**What the buyer sees:**
```
┌─────────────────────────────────────────────────┐
│                                                 │
│  ✓ Here's the property                          │
│                                                 │
│  7704 Southrail Rd                              │
│  North Charleston, SC 29420                     │
│                                                 │
│  [Google Maps embed showing location]           │
│                                                 │
│  Property Details:                              │
│  46,530 sqft building · 28,000 available        │
│  30' Clear · 4 Dock Doors · Sprinklered         │
│  Built 1980 · Metal Construction                │
│  M-1 Zoning · 4.02 acre lot                     │
│                                                 │
│  [See all photos (5)]                           │
│                                                 │
│  ─────────────────────────────────────────────  │
│                                                 │
│  When would you like to tour?                   │
│                                                 │
│  [Date picker]    [Time preference]             │
│  Preferred: Morning / Afternoon / Evening       │
│                                                 │
│  [ Request Tour ]                               │
│                                                 │
└─────────────────────────────────────────────────┘
```

**What happens:**
- Engagement status: guarantee_signed → address_revealed (automatic, no user action)
- Full property details now available via API (address, specs, images, hours)

### 4.5 Step 5: Tour Requested

**What happens when buyer picks a date/time:**
- Engagement status: address_revealed → tour_requested
- tour_requested_date, tour_requested_time, tour_requested_at stored
- 12-hour countdown starts for supplier

**Supplier receives (SMS + email simultaneously):**

SMS:
```
WEx: Tour request for 7704 Southrail Rd.
Buyer needs 5,000 sqft for storage, 6 months.
Requested: Tue Mar 5, 10:00 AM.
Reply YES to confirm or ALT to propose a different time.
```

Email (more detail):
```
Subject: Tour Request — 7704 Southrail Rd, Mar 5

A buyer has requested a tour of your property.

Property: 7704 Southrail Rd, North Charleston, SC
Buyer needs: 5,000 sqft · Storage · 6 months
Your rate: $0.71/sqft ($3,550/mo)
Requested date: Tuesday, March 5, 10:00 AM

Please confirm within 12 hours.

[Confirm This Time]    [Propose Alternative]

If we don't hear from you by [deadline], the buyer will be 
notified and may be matched with another space.
```

**Buyer sees:**
```
Tour requested for Tue Mar 5, 10:00 AM.
Waiting for property owner to confirm.
We'll notify you within 12 hours.
```

### 4.6 Step 6: Tour Confirmed or Rescheduled

**If supplier confirms:**
- Status: tour_requested → tour_confirmed

Buyer SMS:
```
WEx: Your tour is confirmed!
7704 Southrail Rd, North Charleston
Tue Mar 5, 10:00 AM
We'll send a reminder the day before.
```

Supplier SMS:
```
WEx: Tour confirmed for Mar 5, 10:00 AM.
Buyer needs 5,000 sqft for storage.
We'll send details the day before.
```

**If supplier proposes alternative:**
- Status: tour_requested → tour_rescheduled
- tour_rescheduled_date, tour_rescheduled_time, tour_rescheduled_by stored

Buyer SMS:
```
WEx: The property owner proposed a different time:
Thu Mar 7, 2:00 PM
Reply YES to accept or suggest another time at [link].
24-hour window to respond.
```

- Max 2 reschedules before admin intervention flag

### 4.7 Step 7: Tour Day

**Day before — reminders to both parties:**

Buyer:
```
WEx: Reminder — your tour is tomorrow.
7704 Southrail Rd, North Charleston
Tue Mar 5, 10:00 AM
[Get Directions]
```

Supplier:
```
WEx: Reminder — tour tomorrow at 10:00 AM.
Buyer arriving for 5,000 sqft storage tour.
Please ensure the space is accessible.
```

### 4.8 Step 8: Post-Tour Follow-up

**24 hours after scheduled tour time, automated follow-up fires:**

Buyer SMS:
```
WEx: How was your tour of the space in North Charleston?
Reply YES to proceed or PASS if it's not the right fit.
```

Buyer email:
```
Subject: How was your tour?

Ready to proceed?

[Yes, I want this space]     [I have questions]     [Pass on this space]
```

**Response handling:**

| Response | Status Change | Next Step |
|----------|-------------|-----------|
| YES / "I want this space" | tour_completed → buyer_confirmed | Agreement sent immediately |
| "I have questions" | tour_completed (stays) | Routes to Q&A flow (Section 7). Timer paused. Resumes after questions answered. |
| PASS | tour_completed → declined_by_buyer | Reason captured. Property released. Buyer shown remaining matches. |
| No response 48hrs | Reminder sent | "Still thinking? Reply YES or PASS." |
| No response 72hrs | tour_completed → expired | Both notified. |

---

## 5. Instant Book Path

Some buyers will prefer to skip the tour and commit directly — especially repeat buyers, buyers in familiar markets, or buyers whose needs are highly standardized. The "Book Instantly" option is available on Tier 1 matches where the supplier has pre-accepted the deal.

### 5.1 Eligibility

"Book Instantly" is available when:
- Engagement is Tier 1 (supplier has already accepted via deal ping)
- Property has complete information on file (address, specs, photos, access instructions)
- Supplier has not flagged "tour required" on their property settings

### 5.2 Instant Book Flow

**After guarantee_signed (path = instant_book):**

System checks:
1. Supplier acceptance is still valid (deal_ping_accepted and not expired)
2. Space is still available at the requested sqft

If available:
- Status: guarantee_signed → instant_book_requested → buyer_confirmed
- Property address is revealed automatically (no separate address_revealed state — included in the confirmation screen)
- Agreement generated immediately

If no longer available (edge case — space rented in the interim):
- Status: guarantee_signed → address_revealed (redirected to tour path)
- Buyer notified: "This space was just taken, but you can still schedule a tour to confirm the remaining availability."

**Confirmation screen (shown immediately after guarantee_signed on instant book path):**
```
┌─────────────────────────────────────────────────┐
│                                                 │
│  ✓ Space Confirmed — Preparing Your Agreement   │
│                                                 │
│  7704 Southrail Rd                              │
│  North Charleston, SC 29420                     │
│                                                 │
│  5,000 sqft · Storage · 6 months               │
│  $4,250/mo all-in · $25,500 total               │
│                                                 │
│  Your engagement agreement is being prepared.  │
│  You'll receive it by email within minutes.     │
│                                                 │
│  [View Agreement →]                             │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Supplier notified (SMS):**
```
WEx: Buyer has instant-booked your space at 7704 Southrail Rd.
5,000 sqft · Storage · 6 months · $3,550/mo payout.
Your engagement agreement is on its way. 
No tour needed — buyer is ready to proceed.
```

### 5.3 Instant Book Data

Additional fields on Engagement schema (already included in Section 2.1):
- `instant_book_requested_at` — when buyer clicked Book Instantly
- `instant_book_confirmed_at` — when system confirmed availability

---

## 6. Agreement Flow

### 6.1 Trigger

When buyer_confirmed status is reached (either via tour path or instant book path), the system immediately generates the engagement agreement.

### 6.2 Agreement Content

The engagement agreement covers:
- Property address and allocated space (sqft)
- Buyer's all-in rate, monthly total, term, start date
- Supplier's rate and monthly payout (on supplier's copy only)
- Move-in date
- Duration and end date
- WEx Occupancy Guarantee terms (reference to buyer's signed guarantee)
- WEx Platform Terms reference (for Tier 2 supplier: reference to deal ping acceptance)
- Cancellation policy
- Insurance requirements
- Payment schedule

**Phase 1:** Agreement is an in-app document with checkbox acceptance (not DocuSign). Agreement text stored in database with version tracking.  
**Phase 2:** DocuSign integration.

### 6.3 Signing Flow

**Status: buyer_confirmed → agreement_sent**

Both parties receive the agreement simultaneously.

Buyer email:
```
Subject: Your WEx Engagement Agreement — 7704 Southrail Rd

Space: 7704 Southrail Rd, North Charleston, SC
Size: 5,000 sqft · Storage use
Rate: $0.85/sqft all-in · $4,250/mo
Term: 6 months (Mar 15 – Sep 15, 2026)
Total commitment: $25,500

[Review & Sign Agreement]
```

Supplier email:
```
Subject: Engagement Agreement — 7704 Southrail Rd

Property: 7704 Southrail Rd
Buyer: 5,000 sqft · Storage · 6 months
Your rate: $0.71/sqft · $3,550/mo payout
Term: Mar 15 – Sep 15, 2026

[Review & Sign Agreement]
```

**In-app agreement page:**
```
┌─────────────────────────────────────────────────────┐
│  ENGAGEMENT AGREEMENT                               │
│                                                     │
│  [Full agreement text — scrollable]                 │
│                                                     │
│  ────────────────────────────────────────────────── │
│                                                     │
│  ENGAGEMENT SUMMARY                                 │
│  Property: 7704 Southrail Rd, North Charleston, SC  │
│  Space: 5,000 sqft                                  │
│  Use: Storage                                       │
│  Rate: $0.85/sqft all-in (buyer view)               │
│        $0.71/sqft payout (supplier view)            │
│  Monthly: $4,250 (buyer) / $3,550 (supplier)        │
│  Term: 6 months                                     │
│  Start: March 15, 2026                              │
│  End: September 15, 2026                            │
│                                                     │
│  ☐ I have read and agree to the terms of this       │
│    engagement agreement.                            │
│                                                     │
│  [ Sign Agreement ]                                 │
│                                                     │
│  Waiting for other party's signature: Pending       │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Both must sign within 72 hours.** Either party can sign first. When both have signed:
- Status: agreement_sent → agreement_signed
- buyer_agreement_signed_at, supplier_agreement_signed_at stored
- Both notified: "Agreement signed! Next step: move-in preparation."

Reminders: 24hrs, 48hrs. Expire at 72hrs.

### 6.4 Agreement Data

```
EngagementAgreement:
  id: uuid
  engagement_id: uuid (FK → Engagement)

  terms_version: string  # e.g., "v1.0-2026-02"
  agreement_text: text   # full rendered agreement

  # Buyer side
  buyer_rate_sqft: float
  buyer_monthly: float
  buyer_term_total: float
  buyer_signed_at: timestamp (nullable)
  buyer_signed_ip: string (nullable)

  # Supplier side
  supplier_rate_sqft: float
  supplier_monthly: float
  supplier_term_total: float
  supplier_signed_at: timestamp (nullable)
  supplier_signed_ip: string (nullable)

  # Terms
  sqft: int
  term_months: int
  start_date: date
  end_date: date
  use_type: string

  status: enum [pending, buyer_signed, supplier_signed, fully_signed, expired, cancelled]

  created_at: timestamp
  expires_at: timestamp  # created_at + 72 hours
```

---

## 7. Q&A Flow

Q&A is triggered when a buyer selects "I have questions" after a tour. Questions are routed by AI first, then to the supplier if the AI can't confidently answer. All answers are stored permanently in the property record.

### 7.1 Trigger

Buyer selects "I have questions" in the post-tour follow-up. Engagement remains in `tour_completed` status. The 48-hour post-tour decision timer is PAUSED while a question is open. Timer resumes when the question is answered.

### 7.2 Q&A Data Model

```
PropertyQuestion:
  id: uuid
  engagement_id: uuid (FK → Engagement)
  property_id: uuid (FK → Warehouse)

  asked_by: uuid (FK → User)  # buyer
  question_text: text

  # AI routing
  ai_attempted: boolean (default false)
  ai_confidence: float (nullable)  # 0.0–1.0; if < 0.7, route to supplier
  ai_answer: text (nullable)
  ai_answered_at: timestamp (nullable)

  # Supplier routing
  routed_to_supplier: boolean (default false)
  routed_at: timestamp (nullable)
  supplier_answer: text (nullable)
  supplier_answered_at: timestamp (nullable)

  # Final answer (what the buyer receives — AI or supplier answer)
  final_answer: text (nullable)
  final_answer_source: enum [ai, supplier] (nullable)
  answer_delivered_at: timestamp (nullable)

  # Property memory
  saved_to_property: boolean (default false)
  saved_to_property_at: timestamp (nullable)
  property_qa_key: string (nullable)  # slug for property knowledge base lookup

  status: enum [submitted, ai_processing, routed_to_supplier, answered, expired]
  created_at: timestamp
```

### 7.3 Routing Logic

**Step 1: AI attempts to answer**
When a question is submitted, the system queries the property knowledge base:
- Property spec data (size, features, zoning, dock info, etc.)
- Previously answered questions for this property (saved in property memory)
- General WEx warehouse knowledge base

If AI confidence ≥ 0.70: AI answer is sent to buyer immediately. Supplier is not notified.  
If AI confidence < 0.70: Question is routed to supplier with a 24-hour response window.

**Step 2 (if routed to supplier):**

Supplier SMS:
```
WEx: A buyer has a question about 7704 Southrail Rd.
"Do you have 3-phase power available?"
Please reply with your answer or call us at [WEx number].
24 hours to respond or the buyer may move on.
```

Supplier email:
```
Subject: Buyer Question — 7704 Southrail Rd

An interested buyer asked:
"Do you have 3-phase power available?"

Please answer so we can keep this deal moving.

[Answer This Question]   (or reply to this email)

If we don't receive an answer within 24 hours, we'll let the buyer know
you'll follow up — but deals move fast. Reply quickly.
```

**Step 3: Answer delivered to buyer**

SMS:
```
WEx: Your question about the space in North Charleston was answered.
"Yes, 3-phase, 200-amp service available."
Still interested? Reply YES to proceed or PASS.
```

The 48-hour post-tour decision timer resumes from where it was paused.

**Step 4: Saved to property memory**

After answer is delivered:
- `PropertyQuestion.saved_to_property = true`
- Question + answer stored in the property's knowledge base
- Future AI queries on the same property can now answer this question with high confidence
- If the same question is asked again on a different engagement for this property, AI answers immediately

### 7.4 Q&A Timer Rules

| Event | Timer Behavior |
|-------|---------------|
| "I have questions" selected | 48hr post-tour timer PAUSED |
| AI answers (< 30 seconds) | Timer RESUMES immediately after answer delivered |
| Routed to supplier | Timer stays PAUSED during 24hr supplier window |
| Supplier answers | Timer RESUMES after answer delivered to buyer |
| Supplier doesn't answer in 24hrs | Timer RESUMES; buyer notified: "We're still getting an answer — you can also proceed or pass" |
| Buyer asks another question | Timer PAUSES again for the new question |

### 7.5 PropertyKnowledgeBase Schema

```
PropertyKnowledgeEntry:
  id: uuid
  property_id: uuid (FK → Warehouse)
  
  question: text              # normalized question
  answer: text                # canonical answer
  source: enum [ai, supplier, admin]
  source_engagement_id: uuid (nullable)  # which engagement produced this Q&A
  
  confidence: float           # how reliable this answer is (admin can adjust)
  active: boolean             # admin can deactivate outdated entries
  
  created_at: timestamp
  updated_at: timestamp
```

---

## 8. Multi-Property Tour Coordination

**Status: Known gap — NOT specced for launch, documented for future.**

The buyer journey visual shows "Multi-property tours coordinated by WEx" at the scheduling step. The current spec treats each engagement as an independent tour. For launch, this is acceptable — each engagement independently manages its tour request and confirmation.

**Launch behavior:** A buyer with three Tier 1 matches has three separate engagements. Each fires its own tour request independently. Schedules may or may not align. WEx ops manually coordinates if a buyer calls requesting a single-day tour of multiple properties.

**Future spec requirement (Phase 2):** A `TourBundle` object that groups multiple engagements for a single buyer, presents them as a unified tour itinerary, and coordinates supplier schedules in a single workflow. Each engagement in the bundle would move through tour states in parallel.

---

## 9. Buyer Onboarding (Post-Agreement)

### 9.1 What the Buyer Needs to Submit

After agreement is signed, buyer enters the onboarding state.

| Document | Required | Verification |
|----------|----------|-------------|
| Certificate of Insurance | Yes | Admin reviews coverage meets property requirements |
| Company registration / business license | Yes | Admin verifies company identity |
| Payment method | Yes | Phase 1: bank info for manual invoicing. Phase 2: Stripe Connect |

### 9.2 Onboarding Page

```
┌─────────────────────────────────────────────────────┐
│  Almost there! Complete these steps to move in.     │
│                                                     │
│  ✓ Agreement signed                                 │
│                                                     │
│  ○ Upload Certificate of Insurance                  │
│    Your policy must cover: [requirements]           │
│    [Upload File]                                    │
│                                                     │
│  ○ Upload Company Documents                         │
│    Business license or registration                 │
│    [Upload File]                                    │
│                                                     │
│  ○ Payment Setup                                    │
│    How you'll be billed monthly                     │
│    [Set Up Payment]                                 │
│                                                     │
│  ────────────────────────────────────────────────── │
│                                                     │
│  Questions? Text us at [WEx number] or              │
│  email support@warehouseexchange.com                │
│                                                     │
│  Target move-in: March 15, 2026 (12 days away)      │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 9.3 Supplier Onboarding (Parallel)

If the supplier hasn't set up payout method:
- Supplier notified: "Set up your payout method to receive deposits for Engagement #1234."
- Phase 1: Bank info collected via form, stored securely, admin processes manual deposits
- Phase 2: Stripe Connect

---

## 10. Active Lease & Payments

### 10.1 Activation

When onboarding is complete and lease start date is reached:
- Status: onboarding → active
- Both parties notified: "Your engagement is now active! First billing cycle begins [date]."
- Property's rented_sqft increases by engagement sqft
- Recurring billing schedule created

### 10.2 Payment Schedule (Phase 1 — Ledger Only)

```
PaymentRecord:
  id: uuid
  engagement_id: uuid (FK → Engagement)

  period_start: date
  period_end: date
  period_label: string     # e.g., "March 2026"

  buyer_amount: float      # $4,250
  supplier_amount: float   # $3,550
  wex_amount: float        # $700

  buyer_status: enum [upcoming, invoiced, paid, overdue]
  supplier_status: enum [upcoming, scheduled, deposited]

  buyer_paid_at: timestamp (nullable)
  supplier_deposited_at: timestamp (nullable)

  notes: text (nullable)

  created_at: timestamp
```

**Monthly billing cycle:**
1. On billing date, system creates PaymentRecord
2. Admin invoices buyer (manual email)
3. When buyer pays, admin marks buyer_status = paid
4. Admin deposits to supplier, marks supplier_status = deposited
5. Both parties can see payment status on their dashboards

### 10.3 Payment Notifications

| Event | Buyer Notification | Supplier Notification |
|-------|-------------------|----------------------|
| 5 days before billing | "Your monthly payment of $4,250 is due on March 15." | — |
| Payment received | "Payment received. Thank you!" | "Deposit of $3,550 is being processed for March." |
| Payment deposited | — | "Your deposit of $3,550 for March has been sent." |
| Payment overdue (3 days) | "Your payment of $4,250 is overdue. Please remit." | "We're following up on the March payment." |
| Payment overdue (7 days) | "Urgent: payment overdue. Contact us." | Admin intervention triggered |

---

## 11. Buyer Dashboard

### 11.1 Page Structure

```
/buyer                          → Buyer Home
/buyer/search/[id]              → Search results
/buyer/engagements/[id]         → Engagement detail + timeline
/buyer/engagements/[id]/tour    → Tour prep (post-guarantee, pre-tour)
/buyer/engagements/[id]/agree   → Agreement signing page
/buyer/engagements/[id]/onboard → Onboarding docs upload
/buyer/engagements/[id]/qa      → Q&A thread for this engagement
/buyer/payments                 → Payment history
/buyer/account                  → Account settings
```

### 11.2 Buyer Home

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  ACTION NEEDED                                      │
│  ┌───────────────────────────────────────────────┐  │
│  │ Tour confirmed: Tue Mar 5, 10:00 AM           │  │
│  │ 7704 Southrail Rd, North Charleston           │  │
│  │ [Get Directions]  [View Property Details]     │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  YOUR ENGAGEMENTS                                   │
│  [Engagement cards — see Section 11.3]              │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 12. Supplier Dashboard (Engagement Views)

Supplier engagements surface in the supplier dashboard built per the Supplier Dashboard Enhancement spec. The Engagements tab with "Action Needed," "Active," "In Progress," and "Past" buckets covers all engagement states from the supplier's perspective. Pending tour requests surface in the "Action Needed" bucket with deadline countdown and Confirm/Propose Alternative actions.

---

## 13. Admin Portal

### 13.1 Admin Engagement List

```
/admin/engagements
```

Filterable by: status, tier, date range, property, buyer, supplier, stale flag, deadline approaching.

**Bulk actions:** None for MVP.

### 13.2 Admin Engagement Detail

Everything from both buyer and supplier views, plus:
- Full pricing breakdown
- All events with actor and timestamps
- Deal ping response data (response time, terms acceptance)
- Q&A thread with routing details (AI confidence scores, which questions were routed to supplier)
- Ability to manually change status (with reason — logged as admin action)
- Ability to add notes
- Ability to mark payments
- Ability to extend deadlines
- Ability to cancel (with reason)
- Ability to manually route a Q&A question to supplier or answer directly as admin

### 13.3 Admin Dashboard Metrics

| Metric | Description |
|--------|-------------|
| Active engagements | Count of status = active |
| In progress | Statuses between deal_ping_accepted and onboarding |
| Pending deal pings | Count of deal_ping_sent where deadline is approaching |
| Pending actions | Engagements where deadline is < 24 hours away |
| Stale engagements | Same state > 3 days |
| Revenue (monthly) | Sum of monthly_wex_revenue for active engagements |
| Close rate | Engagements reaching active / total created (30-day rolling) |
| Avg days to close | From deal_ping_sent to active |
| Top drop-off stage | Which stage has the most cancellations/expirations |
| Deal ping accept rate | Supplier YES / total pings sent (by tier) |
| Instant book rate | Instant book engagements / total engagements |
| Q&A AI resolution rate | Questions answered by AI / total questions |

---

## 14. API Endpoints

### Engagement Core
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/engagements | List engagements (filtered by role) |
| GET | /api/engagements/{id} | Engagement detail (role-appropriate) |
| GET | /api/engagements/{id}/timeline | Event log |
| POST | /api/engagements/{id}/transition | Advance state (validates allowed transitions) |

### Deal Ping (Pre-Buyer)
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/engagements/{id}/deal-ping/accept | Supplier accepts deal ping → deal_ping_accepted. Body: {terms_accepted: bool, terms_version: string} |
| POST | /api/engagements/{id}/deal-ping/decline | Supplier declines → deal_ping_declined |

### Accept-to-Tour / Account Creation / Instant Book
| Method | Path | Description |
|--------|------|-------------|
| POST | /api/engagements/{id}/accept | Buyer accepts match → buyer_accepted. Body: {path: "tour" \| "instant_book"} |
| POST | /api/auth/register | Create buyer account. Body: {email, password, phone?, engagement_id?}. If engagement_id provided, sets buyer_id on engagement within same transaction → account_created |
| POST | /api/auth/login | Buyer login (returning buyer path). Returns auth token. |
| POST | /api/engagements/{id}/link-buyer | Links authenticated buyer to engagement after login. Called when returning buyer logs in during accept flow → account_created |
| POST | /api/engagements/{id}/guarantee | Buyer signs guarantee → guarantee_signed |
| GET | /api/engagements/{id}/property | Full property details (only after guarantee_signed) |
| POST | /api/engagements/{id}/instant-book/confirm | System checks availability → instant_book_requested → buyer_confirmed |
| POST | /api/engagements/{id}/tour/request | Buyer requests tour date/time → tour_requested |
| POST | /api/engagements/{id}/tour/confirm | Supplier confirms → tour_confirmed |
| POST | /api/engagements/{id}/tour/reschedule | Either party proposes new time → tour_rescheduled |
| POST | /api/engagements/{id}/tour/outcome | Buyer confirms or passes after tour |
| POST | /api/engagements/{id}/decline | Either party declines (with reason) |

### Q&A
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/engagements/{id}/qa | List Q&A thread for this engagement |
| POST | /api/engagements/{id}/qa | Buyer submits question → triggers AI routing |
| POST | /api/engagements/{id}/qa/{question_id}/answer | Supplier answers routed question |
| GET | /api/properties/{id}/knowledge | Property knowledge base entries (admin/internal) |
| POST | /api/admin/properties/{id}/knowledge | Admin adds/edits knowledge base entry |

### Agreement
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/engagements/{id}/agreement | Get agreement (role-appropriate) |
| POST | /api/engagements/{id}/agreement/sign | Sign agreement (checkbox + timestamp) |

### Buyer Onboarding
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/engagements/{id}/onboarding | Onboarding status |
| POST | /api/engagements/{id}/onboarding/insurance | Upload insurance document |
| POST | /api/engagements/{id}/onboarding/company-docs | Upload company documents |
| POST | /api/engagements/{id}/onboarding/payment | Submit payment info |

### Payments
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/engagements/{id}/payments | Payment records |
| GET | /api/buyer/payments | All payments across buyer's engagements |
| GET | /api/supplier/payments | All deposits across supplier's engagements |

**Refactor note:** `/api/supplier/payments` and `/api/supplier/payments/summary` already exist in `routes/supplier_dashboard.py` returning data from the current ledger/mock system. These endpoints should be refactored to query `PaymentRecord` (engagement-based) instead of the existing `SupplierLedger`. The endpoint paths stay the same; the data source changes.

| POST | /api/admin/engagements/{id}/payments/{payment_id}/mark-paid | Admin marks buyer payment received |
| POST | /api/admin/engagements/{id}/payments/{payment_id}/mark-deposited | Admin marks supplier deposit sent |

### Admin
| Method | Path | Description |
|--------|------|-------------|
| GET | /api/admin/engagements | All engagements with filters |
| GET | /api/admin/engagements/{id} | Full engagement detail (both sides) |
| POST | /api/admin/engagements/{id}/status | Override status (with reason) |
| POST | /api/admin/engagements/{id}/note | Add admin note |
| POST | /api/admin/engagements/{id}/extend-deadline | Extend current stage deadline |
| POST | /api/admin/engagements/{id}/qa/{question_id}/answer | Admin answers Q&A question directly |
| GET | /api/admin/dashboard | Aggregate metrics |

---

## 15. Background Jobs

| Job | Schedule | What It Does |
|-----|----------|-------------|
| `check_deal_ping_deadlines` | Every 15 minutes | Finds deal pings past 12hr deadline. Marks expired. Notifies clearing engine. |
| `check_deadlines` | Every 15 minutes | Finds engagements past their deadline. Sends reminders or expires. |
| `send_tour_reminders` | Daily at 6:00 AM | Finds tours scheduled for tomorrow. Sends reminder to both parties. |
| `send_post_tour_followup` | Every hour | Finds tours 24+ hours past scheduled time without follow-up. Sends follow-up. |
| `check_qa_supplier_deadline` | Every hour | Finds Q&A questions routed to supplier > 24hrs without response. Resumes buyer timer. Notifies admin. |
| `save_qa_to_property_knowledge` | Real-time (triggered by qa_answer_delivered) | Saves answered Q&A to property knowledge base. |
| `generate_payment_records` | Daily at midnight | For active engagements approaching billing date, creates PaymentRecord entries. |
| `send_payment_reminders` | Daily at 9:00 AM | Sends reminders for payments due in 5 days or overdue. |
| `flag_stale_engagements` | Daily at 8:00 AM | Flags engagements in same state > 3 days for admin review. |
| `auto_activate_leases` | Daily at midnight | Transitions completed onboarding to active when lease start date reached. |
| `renewal_prompts` | Daily at 9:00 AM | Finds active engagements ending in < 30 days. Sends renewal prompt to buyer. |

---

## 16. Summary: What Both Parties See at Each Stage

| Stage | Buyer Sees | Supplier Sees |
|-------|-----------|--------------|
| **deal_ping_sent** | Nothing yet (or "confirming spaces" placeholder) | SMS/email deal ping with YES/NO prompt |
| **deal_ping_accepted** | Nothing yet (results updating) | Confirmation: "Deal confirmed — awaiting buyer" |
| **deal_ping_declined** | Nothing (property not shown in results) | Decline confirmation |
| **matched** | Property on results page (city, features, rate, match %) | Dashboard: "Buyer is reviewing your space" |
| **buyer_reviewing** | Property details on results page | Dashboard: "Buyer is reviewing your space" |
| **buyer_accepted** | Account creation form (email + password) | Dashboard: "Buyer is committing to this space" |
| **account_created** | WEx Guarantee to sign | Dashboard: "Buyer is committing to this space" |
| **guarantee_signed** | Full address + property details + tour scheduler (or instant book confirmation) | Nothing yet |
| **instant_book_requested** | "Confirming your space..." → immediately to buyer_confirmed screen | SMS: "Buyer has instant-booked your space" |
| **tour_requested** | "Waiting for confirmation" + tour date | SMS/email: "Tour requested, confirm or propose alt" |
| **tour_confirmed** | Tour date confirmed + property details + directions | Tour date confirmed + buyer summary |
| **tour_rescheduled** | New proposed time with accept/counter option | Waiting for buyer response |
| **tour_completed** | "How was your tour?" follow-up options | Waiting for buyer decision |
| **buyer_confirmed** | "Agreement is being prepared" | "Buyer wants to proceed!" |
| **agreement_sent** | Agreement with buyer terms to sign | Agreement with supplier terms to sign |
| **agreement_signed** | Onboarding checklist | Payment setup (if not done) |
| **onboarding** | Progress on doc uploads + target move-in date | "Buyer is preparing for move-in" |
| **active** | Lease details + payment schedule + property info | Lease details + payout schedule |
| **completed** | "Lease completed" + renewal option | "Lease completed" + availability reopened |
| **cancelled** | Reason + option to search again | Reason + property returns to pool |
| **expired** | "Engagement expired" + option to search again | Property returns to available pool |

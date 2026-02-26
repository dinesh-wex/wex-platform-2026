# WEx — Buyer Flow Spec
## Matching Page → Tour Commitment → Dashboard

**For:** Frontend + Backend Developer  
**Context:** Complete buyer-facing flow from the moment a match is shown through tour scheduling, confirmation, and the deal tracker dashboard.  
**Version:** 2.1 · February 2026
**Owned by:** Product (Dinesh)
**Changes from v1:** Book Instantly promoted to primary CTA; "Reserve & Tour" replaces "Schedule a Tour"; 72-hour hold mechanic introduced throughout; urgency signals framework added (Phase 1 signals only — buyer view count deferred to Phase 2); modal copy updated to reflect hold framing.
**Changes from v2.0 → v2.1:** Aligned with Engagement Lifecycle Spec v3 — `contact_captured` replaced by `account_created` throughout. Password-based account creation required at Step 1 (silent/passwordless account creation removed). `buyer_email`/`buyer_phone` fields removed from Engagement model (contact info lives in User model).

---

## Overview

This spec covers four connected surfaces:

1. **Results Card** — how a match is presented and what actions are available
2. **Reserve & Tour Flow** — the 4-step commitment modal (holds space for 72 hours)
3. **Book Instantly Flow** — the abbreviated path for Tier 1 buyers ready to commit without a tour
4. **Buyer Dashboard** — the deal tracker that shows engagement status post-commitment

The design principle throughout: **every screen should feel like the buyer is securing the space, not scheduling an activity.** The tour is the verification step. The hold is what the buyer is actually getting.

---

## 1. Results Card

### 1.1 What the Card Shows

The results card is the buyer's first look at a matched property. It shows enough to evaluate the deal — not enough to locate the property independently.

```
┌──────────────────────────────────────────────────────────────┐
│  [Property photo — street view / generic exterior only.      │
│   No signage, no dock numbers, nothing locatable]            │
│                                                              │
│  📍 CARSON, CA  · 3 mi away                                  │
│                                                              │
│  Carson, CA                          ┌──────────────────┐   │
│  Carson, CA 90746                    │   36,200 sqft    │   │
│  Storage Only                        │  available space │   │
│                                      │ in 90,500 sqft   │   │
│                                      │    building      │   │
│                                      └──────────────────┘   │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ ALLOCATED SIZE    ×   YOUR RATE      =   MONTHLY COST  │  │
│  │   5,000 sqft         $1.79/sqft          $8,950/mo     │  │
│  │                                       all-in pricing   │  │
│  │                                                        │  │
│  │ MONTHLY COST      ×   TERM            TOTAL VALUE      │  │
│  │   $8,950              6 months         $53,700         │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ── Urgency signals (see Section 1.3) ───────────────────    │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │        ⚡  Book Instantly — lock in your space now    │   │  ← PRIMARY. Full-width. Green.
│  └──────────────────────────────────────────────────────┘   │  ← Tier 1 only. Hidden on Tier 2.
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │        🔒  Reserve & Tour — hold for 72 hours         │   │  ← SECONDARY. Full-width. Outlined.
│  └──────────────────────────────────────────────────────┘   │  ← Always present.
│                                                              │
│              Ask a Question                                  │  ← Text link. No button treatment.
│                                                              │
│  🛡 All rates are all-in. Every deal includes WEx            │
│     Occupancy Guarantee.                                     │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 1.2 Button Hierarchy Rules

**Book Instantly** — PRIMARY. Full-width solid green button. Only shown when:
- Engagement tier = tier_1 (supplier has pre-accepted via deal ping)
- Property has complete data on file (address, specs, photos)
- Supplier has not set `tour_required = true` on their property settings

When not eligible (Tier 2, incomplete data, or tour required): Book Instantly is hidden entirely. Reserve & Tour takes full primary width and becomes the only button.

**Reserve & Tour** — SECONDARY. Full-width outlined button (green border, white fill). Always present on every match card. When Book Instantly is hidden, this becomes full primary width and styling.

**Ask a Question** — Text link only. No border, no fill, no button shape. Sits below both buttons. Visually communicates "this is the slower path." A buyer who sees it should feel like they're choosing to wait, not choosing a faster route.

**On Tier 1 cards:** Both Book Instantly and Reserve & Tour are shown. Book Instantly is dominant.

**On Tier 2 cards:** Only Reserve & Tour is shown, at primary full-width styling. No Book Instantly.

### 1.3 Urgency Signals

A one-line signal row appears between the pricing block and the buttons. Rules for what gets shown:

**Phase 1 — Launch signals (real data only):**

| Signal | When to Show | Data Source |
|--------|-------------|-------------|
| `⚠️ Only [X] sqft available in this building` | Show when available sqft ≤ 150% of buyer's requested sqft. So if buyer wants 5,000 sqft and 8,000 sqft is available: show it. If 36,200 sqft is available: don't show — it's not scarce. | `warehouse.available_sqft` |
| `⚡ Similar space nearby leased [X] days ago` | Show when a comparable property (same market, same use type, ±30% sqft) had an engagement reach `active` in the last 14 days. | Engagement transaction log |

**Both signals can show at once**, separated by a dot:
```
⚠️ Only 7,200 sqft remaining  ·  ⚡ Similar space leased 3 days ago
```

**If no signals qualify: show nothing.** The row is empty. Do not fabricate urgency where none exists. Warehouse operators are sophisticated buyers who will notice fake signals and it will damage trust.

**Phase 2 — Deferred (not built at launch):**
- "👁 [X] buyers viewed this space this week" — requires real view tracking across multiple buyers and a minimum count threshold before showing. Spec separately when implementing.

### 1.4 What "Ask a Question" Does (For Now)

Routes to a simple freeform text field. Message stored against property_id and buyer session. Routed manually by WEx ops for now. AI Q&A routing is a future layer — see Engagement Lifecycle Spec v2, Section 7.

No account creation required. No commitment required. A buyer using this path is still evaluating — don't push them to commit.

If the buyer later proceeds to Reserve & Tour on the same property, the question history is visible to WEx ops in the admin portal.

### 1.5 Photo Treatment

The results card photo is a **street-view exterior only** — no interior shots, no signage showing business names, no dock numbering that would identify the building. This is the pre-commitment photo tier.

Full interior photos and property details are revealed at Step 3 of the Reserve & Tour flow, after the guarantee is signed.

If no property photo exists: show a generic warehouse silhouette. Do not show a broken image placeholder.

---

## 2. The 72-Hour Hold Mechanic

### 2.1 What Gets Locked

The moment a buyer enters either commitment flow (Reserve & Tour or Book Instantly), the following are locked for this engagement:

- **The sqft allocation** — the buyer's requested sqft is reserved. No other buyer engagement can claim these same sqft from this property simultaneously.
- **The rate** — $1.79/sqft. Not negotiable after entering the flow, regardless of tour outcome.
- **The total** — $53,700 for the term.

This is the business logic that prevents post-tour price negotiation. The buyer knows the price before they tour, they agreed to it when they signed the guarantee, and it is stated explicitly throughout.

### 2.2 Hold Duration

**72 hours from the moment the guarantee is signed** (Step 2 of the commitment flow).

The hold covers the time needed to: confirm the tour (12hrs), complete the tour, and make a post-tour decision (48hrs). In a normal flow this all happens well within 72 hours.

| Event | Typical Timing |
|-------|---------------|
| Guarantee signed | Hour 0 |
| Supplier confirms tour | Within 12 hours |
| Tour happens | 24–72 hours after request |
| Post-tour decision | Within 48 hours of tour |
| **Total** | Well within 72 hours |

### 2.3 Hold Expiry Behavior

At 48 hours: "Your hold is expiring in 24 hours — [View your deal]" email sent to buyer.  
At 68 hours: "Your hold expires in 4 hours" email + SMS (if phone provided).  
At 72 hours: Engagement status → `expired`. Space returns to available pool. Buyer notified: "Your hold on the Carson space has expired. [Search again]"

**One extension available:** Buyer can request a single 24-hour extension from their dashboard. This creates a second urgency moment — they have to actively ask for more time.

### 2.4 Hold Countdown Display

The countdown is shown wherever the price summary bar appears — in the modal, on the dashboard card, and on the detail page.

**In the modal (Steps 1–4):**
```
5,000 sqft  ·  $8,950/mo  ·  6 months  ·  $53,700  🔒 Held for 72:00:00
```
Countdown ticks in real time. Starts when the modal opens, locks in when guarantee is signed.

**On the dashboard card (post-commitment):**
```
🔒 Hold expires in 47:23:11  ·  Tour: Sat Feb 28, 12:30 PM
```
Shown until the hold resolves (tour confirmed + decision made) or expires.

**On the detail page:**
```
YOUR LOCKED TERMS
Rate:     $1.79/sqft all-in
Monthly:  $8,950
Term:     6 months
Total:    $53,700
🔒 Space held until Feb 28, 2:14 PM
```

---

## 3. Reserve & Tour Flow

### 3.1 Flow Overview

Triggered by: buyer clicks "Reserve & Tour"

The modal opens over the results page — results card remains visible but dimmed. Do not navigate away. Buyer can close and return to results.

**4 steps:**
1. Contact info — "Who should we contact?"
2. WEx Guarantee — "Your space is protected"
3. Address reveal + tour scheduling
4. Confirmation — space held, tour requested

**Pricing summary bar** — visible at the top of every step, never scrolls away:
```
5,000 sqft  ·  $8,950/mo  ·  6 months  ·  $53,700  🔒 Held for 71:58:42
```
Countdown begins when modal opens.

### 3.2 Step 1 — Contact Info

**Modal title:** Reserve & Tour  
**Step label:** Step 1 of 4

```
┌─────────────────────────────────────────────────┐
│ 🔒 Reserve & Tour            Step 1 of 4   ✕   │
│ ①──────②──────③──────④                         │
│ ─────────────────────────────────────────────── │
│ 5,000 sqft · $8,950/mo · 6 months · $53,700 🔒  │
│ ─────────────────────────────────────────────── │
│                                                 │
│  Who should we contact about your tour?         │
│                                                 │
│  First Name          Last Name                  │
│  [____________]      [____________]             │
│                                                 │
│  Email                                          │
│  [________________________________]             │
│  We'll send your tour confirmation here         │
│                                                 │
│  Mobile Number (optional)                       │
│  [________________________________]             │
│  For tour reminders and updates via SMS         │
│                                                 │
│  Company Name (optional)                        │
│  [________________________________]             │
│                                                 │
│  Already have an account? Sign in               │
│                                                 │
│  [ Continue → ]                                 │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Field rules:**
- First Name: required
- Last Name: required
- Email: required, validated format
- Mobile: optional. If not provided, SMS notifications skipped; email only
- Company: optional. Pre-fills company name on account if provided

**Account creation behavior:**
- If email already exists: "Welcome back — sign in to continue" inline. Buyer signs in with existing password, then `POST /api/engagements/{id}/link-buyer` links them to this engagement.
- If email is new: buyer creates a full WEx account (email + password required). Account is created via `POST /api/auth/signup` with `engagement_id`, which atomically creates the account and links the engagement.

**What happens on Continue:**
- Engagement status: buyer_accepted → account_created
- engagement.buyer_id set, account_created_at stored
- Contact info (name, email, phone, company) stored on User model, not on Engagement

### 3.3 Step 2 — WEx Guarantee

**Modal title:** Reserve & Tour  
**Step label:** Step 2 of 4

```
┌─────────────────────────────────────────────────┐
│ 🔒 Reserve & Tour            Step 2 of 4   ✕   │
│ ✓──────②──────③──────④                         │
│ ─────────────────────────────────────────────── │
│ 5,000 sqft · $8,950/mo · 6 months · $53,700 🔒  │
│ ─────────────────────────────────────────────── │
│                                                 │
│     🛡                                          │
│                                                 │
│  Your space is protected by WEx.                │
│                                                 │
│  When you reserve:                              │
│  ✓ This space and rate are held for 72 hours    │
│  ✓ Your rate is locked — no renegotiation       │
│    after the tour                               │
│  ✓ Payment goes through WEx, never directly     │
│    to the owner                                 │
│  ✓ WEx handles disputes if the space            │
│    doesn't match what's described               │
│  ✓ Your contact info stays private until        │
│    the tour is confirmed                        │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │  📄 WEx Occupancy Guarantee  View Terms ↓ │  │
│  │                                           │  │
│  │  ☐ I agree to the WEx Occupancy Guarantee │  │
│  │    and confirm the pricing above for      │  │
│  │    this engagement.                       │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  [ Confirm & See the Space → ]                  │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Copy rules:**
- First bullet now explicitly calls out the 72-hour hold — this is the primary benefit being sold
- "Rate is locked — no renegotiation after the tour" stated explicitly. Buyer knows what they're committing to before they see the address
- "View Terms" expands full legal text inline. Not required to read
- Checkbox must be checked — button disabled until checked
- Button: "Confirm & See the Space" — not "Sign & Reveal Address"
- Never use the word "anti-circumvention" in buyer-facing copy

**What happens on Confirm:**
- Engagement status: account_created → guarantee_signed
- guarantee_signed_at, guarantee_ip_address, guarantee_terms_version stored
- **72-hour hold timer starts here** — hold_expires_at = guarantee_signed_at + 72hrs
- BuyerAgreement record created (type: occupancy_guarantee)
- Transition to Step 3 automatic

### 3.4 Step 3 — Address Revealed + Tour Scheduling

**Modal title:** Reserve & Tour  
**Step label:** Step 3 of 4

```
┌─────────────────────────────────────────────────┐
│ 🔒 Reserve & Tour            Step 3 of 4   ✕   │
│ ✓──────✓──────③──────④                         │
│ ─────────────────────────────────────────────── │
│ 5,000 sqft · $8,950/mo · 6 months · $53,700 🔒  │
│ ─────────────────────────────────────────────── │
│                                                 │
│  📍 YOUR RESERVED SPACE                         │
│  860 Sandhill Ave                               │
│  Carson, CA 90746                               │
│  [Open in Maps ↗]                              │
│                                                 │
│  [Property photo — full, unblurred interior]    │
│                                                 │
│  ┌────────────────┬─────────────┬─────────────┐ │
│  │  36,200 sqft   │ $1.79/sqft  │  $8,950/mo  │ │
│  │  available     │ your rate   │  your cost  │ │
│  └────────────────┴─────────────┴─────────────┘ │
│                                                 │
│  ─────────────────────────────────────────────  │
│                                                 │
│  📅 Schedule Your Tour                          │
│  Space is held — pick a time to visit.          │
│                                                 │
│  Date             Time                          │
│  [mm/dd/yyyy 📅]  [Select time ▾]              │
│                                                 │
│  Notes (optional)                               │
│  [Any special requests or access instructions] │
│                                                 │
│  [ Schedule My Tour → ]                         │
│                                                 │
└─────────────────────────────────────────────────┘
```

**Address reveal behavior:**
- Engagement status: guarantee_signed → address_revealed (automatic, no user action required)
- Full property details now accessible via API: address, specs, full interior photos, access notes
- Label is "YOUR RESERVED SPACE" — not "ADDRESS REVEALED." The buyer has a space, not a secret.

**Date/time picker rules:**
- No past dates
- Minimum 24 hours from now — can't book a tour for today
- Time dropdown: 8:00 AM through 5:00 PM, 30-minute increments
- If supplier has set available hours on their property, grey out unavailable slots
- Notes field: stored as tour_notes on engagement. Visible to WEx ops and supplier.

**Button:** "Schedule My Tour" — active verb, buyer is doing something for themselves

**What happens on Schedule:**
- Engagement status: address_revealed → tour_requested
- tour_requested_date, tour_requested_time, tour_requested_at stored
- 12-hour countdown begins for supplier confirmation
- Modal advances to Step 4

### 3.5 Step 4 — Confirmed

**Modal title:** Reserve & Tour  
**Step label:** Step 4 of 4

```
┌─────────────────────────────────────────────────┐
│ 🔒 Reserve & Tour            Step 4 of 4   ✕   │
│ ✓──────✓──────✓──────④                         │
│                                                 │
│              ✅                                 │
│                                                 │
│         Space Reserved!                         │
│   Tour request sent. Supplier confirms          │
│   within 12 hours.                              │
│                                                 │
│  ┌───────────────────────────────────────────┐  │
│  │  📍 860 Sandhill Ave, Carson, CA 90746    │  │
│  │                                           │  │
│  │  📅 Saturday, February 28, 2026           │  │
│  │                                           │  │
│  │  🕐 12:30 PM                              │  │
│  │                                           │  │
│  │  🔒 Hold expires Feb 28, 2:14 PM          │  │
│  └───────────────────────────────────────────┘  │
│                                                 │
│  We'll notify you by email (and SMS if you      │
│  provided your number) when confirmed.          │
│                                                 │
│  [ View My Deals → ]                            │
│                                                 │
│  🛡 WEx Occupancy Guarantee active              │
│                                                 │
└─────────────────────────────────────────────────┘
```

**"View My Deals"** — takes buyer to their dashboard (Section 5).

**Confirmation email fires immediately:**
```
Subject: Space reserved — 860 Sandhill Ave, Carson, CA

Your space is reserved. Here's what happens next:

Space: 860 Sandhill Ave, Carson, CA 90746
Size: 5,000 sqft · Storage
Your rate: $1.79/sqft · $8,950/mo (all-in, locked)
Tour requested: Saturday, February 28, 12:30 PM
Hold expires: February 28, 2:14 PM

The supplier will confirm your tour within 12 hours. 
We'll email you as soon as it's confirmed.

If your tour goes well and you'd like to move forward, your agreement 
will be ready the same day — no renegotiation needed.

[View your deal status →]

WEx Occupancy Guarantee is active for this engagement.
```

---

## 4. Book Instantly Flow

### 4.1 When It's Available

Shown as primary button on results card only when:
- Engagement tier = tier_1 (supplier pre-accepted via deal ping)
- Property has complete data (address, specs, photos)
- `supplier.tour_required = false`

### 4.2 Flow Overview

Book Instantly shares Steps 1 and 2 with the Reserve & Tour flow (contact capture and guarantee). The modal title changes to "Book Instantly." After guarantee is signed, instead of a tour scheduler the buyer sees immediate confirmation.

The flow is 3 steps (not 4):
1. Contact info (identical to Reserve & Tour Step 1 — modal title: "Book Instantly")
2. WEx Guarantee (identical — button says "Confirm & Book This Space")
3. Booking confirmed + address revealed

### 4.3 Step 2 — Guarantee (Instant Book Variant)

Same layout as Reserve & Tour Step 2 with two changes:

**Button text:** "Confirm & Book This Space" (not "Confirm & See the Space")

**First bullet changes to:**
```
✓ This space is locked in immediately — no tour needed
```

### 4.4 Step 3 — Booking Confirmed

```
┌─────────────────────────────────────────────────┐
│ ⚡ Book Instantly            Step 3 of 3   ✕   │
│ ✓──────✓──────③                                │
│ ─────────────────────────────────────────────── │
│ 5,000 sqft · $8,950/mo · 6 months · $53,700 🔒  │
│ ─────────────────────────────────────────────── │
│                                                 │
│              ✅                                 │
│                                                 │
│         Space Booked!                           │
│   Your agreement is being prepared.             │
│                                                 │
│  📍 860 Sandhill Ave                            │
│     Carson, CA 90746                            │
│  [Open in Maps ↗]                              │
│                                                 │
│  [Property photo — full, unblurred]             │
│                                                 │
│  5,000 sqft · Storage · $8,950/mo               │
│  6-month term · March 15 – September 15, 2026   │
│                                                 │
│  You'll receive your engagement agreement       │
│  by email within minutes.                       │
│                                                 │
│  [ View My Deals → ]                            │
│                                                 │
│  🛡 WEx Occupancy Guarantee active              │
│                                                 │
└─────────────────────────────────────────────────┘
```

**What happens in background:**
- Engagement status: guarantee_signed → instant_book_requested → buyer_confirmed
- System confirms space still available at requested sqft
- Agreement generated immediately
- Both buyer and supplier receive agreement via email
- If space no longer available (edge case): redirect to Reserve & Tour path with message "This space was just claimed — but you can still reserve it and schedule a tour to confirm availability."

---

## 5. Post-Commitment Notifications

### 5.1 Tour Confirmed

**Buyer email:**
```
Subject: Tour confirmed — 860 Sandhill Ave, Carson CA · Sat Feb 28

Your tour is confirmed and your space is still held.

Space: 860 Sandhill Ave, Carson, CA 90746
Date: Saturday, February 28, 2026 · 12:30 PM
Rate: $8,950/mo (locked)

[Get Directions]    [View Deal Details]

After your tour, let us know if you'd like to proceed — we'll prepare 
your agreement the same day, at the rate you've already locked in.

We'll send a reminder the day before.
WEx Occupancy Guarantee is active.
```

**Buyer SMS:**
```
WEx: Tour confirmed!
860 Sandhill Ave, Carson CA
Sat Feb 28 · 12:30 PM
Rate locked: $8,950/mo
Reminder tomorrow.
```

### 5.2 Tour Rescheduled

**Buyer email:**
```
Subject: New tour time proposed — your hold is still active

The owner of 860 Sandhill Ave proposed a different time:

Proposed: Monday, March 2, 10:00 AM
Your hold expires: February 28, 2:14 PM

[Accept This Time]    [Suggest a Different Time]

Note: the proposed time is after your current hold expires. 
If you accept, we'll extend your hold to cover the new tour date.

Respond within 24 hours to keep this deal moving.
```

**Buyer SMS:**
```
WEx: New tour time proposed.
Mon Mar 2, 10:00 AM
Reply YES to accept or click to suggest another: [link]
Hold still active — 24hrs to respond.
```

### 5.3 Hold Expiry Warnings

**48-hour warning:**
```
Subject: Your hold on the Carson space expires in 24 hours

Your space at 860 Sandhill Ave is still held for you.

Hold expires: February 28, 2:14 PM (24 hours from now)

Tour: Saturday, February 28, 12:30 PM (confirmed)

After your tour, respond YES, PASS, or QUESTIONS to 
keep things moving. If we don't hear from you, the hold 
will expire and the space returns to the available pool.

[View your deal →]
```

**4-hour warning:**
```
WEx: Your hold on the Carson space expires in 4 hours.
Tour was Sat Feb 28. Let us know — YES, PASS, or QUESTIONS.
[link]
```

### 5.4 Tour Day Reminder

**Buyer email (day before):**
```
Subject: Your tour is tomorrow — 860 Sandhill Ave

Reminder: your tour is tomorrow.

860 Sandhill Ave, Carson, CA 90746
Saturday, February 28 · 12:30 PM

[Get Directions]    [View Property Details]

After your tour, your rate ($8,950/mo) is locked and ready. 
If you want the space, your agreement can be signed the same day.
```

### 5.5 Post-Tour Follow-up (24 Hours After Tour)

**Buyer email:**
```
Subject: How was your tour of the Carson space?

We hope the tour went well.

Space: 860 Sandhill Ave, Carson, CA 90746
Your locked rate: $8,950/mo · 6 months · $53,700 total

Ready to move forward?

[Yes, I want this space]    [I have questions]    [Pass on this space]

Your hold expires Feb 28, 2:14 PM. 
If you're ready, we'll send your agreement today — same locked rate.
```

**Buyer SMS:**
```
WEx: How was your tour at Carson?
Reply YES to proceed, QUESTION for questions, PASS to decline.
Rate: $8,950/mo — locked.
```

---

## 6. Buyer Dashboard — Deal Tracker

### 6.1 Design Principle

The dashboard is a **deal tracker**, not a portfolio manager. Most buyers at launch have one engagement in progress. The page leads with the most urgent thing — the active engagement and its status — not aggregate metrics that are all zero.

The metrics bar (Total Deals / Monthly Spend / Total Space) earns its place when a buyer has multiple active leases. When empty, it's replaced by a single clear CTA.

### 6.2 Empty State

```
┌─────────────────────────────────────────────────────────┐
│ WEx | My Spaces                    [Find Space →]       │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │                                                  │   │
│  │       Find your next warehouse space.            │   │
│  │                                                  │   │
│  │  Tell us what you need and we'll match you       │   │
│  │  to available spaces in your market — with       │   │
│  │  rates locked the moment you reserve.            │   │
│  │                                                  │   │
│  │              [ Find Space → ]                    │   │
│  │                                                  │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  🛡 All WEx deals include Occupancy Guarantee.          │
│     Rates are all-in, no hidden fees.                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

No "Total Deals: 0" metrics. No "No deals yet" empty state illustration. One clear CTA.

### 6.3 Active Engagement — Tour Pending

```
┌─────────────────────────────────────────────────────────┐
│ WEx | My Spaces                    [Find More Space]    │
│                                                         │
│  YOUR SPACES                                            │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │  ⏳ Waiting for supplier to confirm your tour    │   │
│  │                                                  │   │
│  │  860 Sandhill Ave, Carson, CA                    │   │
│  │  5,000 sqft · Storage · $8,950/mo                │   │
│  │                                                  │   │
│  │  Tour requested: Sat Feb 28, 12:30 PM            │   │
│  │  🔒 Hold expires in 47:23:11                     │   │
│  │                                                  │   │
│  │  We'll notify you within 12 hours.               │   │
│  │  [View Details]                                  │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  Looking for more space?  [Start a new search →]        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 6.4 Status Labels by Engagement State

The status badge and supporting text on every dashboard card adapts to state:

| State | Badge | Supporting Text | CTA on Card |
|-------|-------|----------------|-------------|
| tour_requested | ⏳ Awaiting tour confirmation | "We'll notify you within 12 hours. Hold expires in [countdown]" | View Details |
| tour_confirmed | ✅ Tour confirmed | "[Day], [Date] · [Time] · Hold expires in [countdown]" | Get Directions |
| tour_rescheduled | 🔄 New tour time proposed | "Review the new time — respond within 24 hours" | Accept / Suggest Different |
| tour_completed | 💬 How was your tour? | "Let us know to keep your hold active" | Yes / Questions / Pass |
| buyer_confirmed | 📄 Agreement being prepared | "You'll receive it by email shortly" | View Details |
| agreement_sent | ✍️ Agreement ready to sign | "Sign within 72 hours to secure your space" | Sign Now |
| agreement_signed | 📦 Preparing for move-in | "Complete your onboarding checklist" | Continue Setup |
| onboarding | 📋 Complete your setup | Progress: Insurance ○ / Docs ○ / Payment ○ | Continue Setup |
| active | ✅ Active lease | "Next payment: $8,950 due [date]" | View Details |
| expired | ⚠️ Hold expired | "This space is no longer held." | Search Again |
| declined_by_buyer | — | Archived — not shown in default list | — |

**Hold countdown rule:** Show the countdown on the card for all states from tour_requested through tour_completed. Once buyer_confirmed is reached, the hold is effectively resolved — the agreement supersedes it. Remove countdown at buyer_confirmed.

### 6.5 Multiple Engagements — Sort Order and Metrics

When buyer has more than one engagement, sort by urgency:

1. Action required (agreement_sent, tour_rescheduled, tour_completed awaiting decision, onboarding incomplete)
2. Hold expiring within 12 hours
3. Active leases
4. Upcoming confirmed tours
5. Everything else

**"ACTION NEEDED" section** — shown above the main list when any engagement requires action:

```
┌─────────────────────────────────────────────────────────┐
│ WEx | My Spaces                    [Find More Space]    │
│                                                         │
│  ACTION NEEDED                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │  ✍️ Agreement ready to sign                      │   │
│  │  860 Sandhill Ave, Carson, CA                    │   │
│  │  5,000 sqft · $8,950/mo · Due in 58 hours        │   │
│  │  [Sign Agreement →]                              │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  YOUR SPACES                                            │
│  ┌──────────────────────────────────────────────────┐   │
│  │  ✅ Active lease                                  │   │
│  │  3240 E 26th St, Los Angeles, CA                 │   │
│  │  8,000 sqft · Distribution · $12,400/mo          │   │
│  │  Next payment: March 15 · [View Details]         │   │
│  └──────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────┐   │
│  │  ✅ Tour confirmed                               │   │
│  │  1400 S Alameda St, Compton, CA                  │   │
│  │  12,000 sqft · Thu Mar 6, 2:00 PM                │   │
│  │  🔒 Hold expires in 31:14:08                     │   │
│  │  [View Details]                                  │   │
│  └──────────────────────────────────────────────────┘   │
│                                                         │
│  Monthly total across all spaces: $21,350               │  ← Only when >1 active lease
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Aggregate metrics bar (Total Deals / Monthly Spend / Total Space) shown only when buyer has ≥ 2 active engagements with data worth showing.

### 6.6 Engagement Detail Page (`/buyer/engagements/[id]`)

```
┌─────────────────────────────────────────────────────────┐
│ ← My Spaces                                             │
│                                                         │
│  860 Sandhill Ave, Carson, CA                           │
│  5,000 sqft · Storage                                   │
│                                                         │
│  [Property photo]                                       │
│                                                         │
│  ─── STATUS ──────────────────────────────────────────  │
│  ⏳ Waiting for tour confirmation                       │
│  Requested: Saturday, February 28, 12:30 PM             │
│  We'll notify you within 12 hours.                      │
│                                                         │
│  ─── YOUR LOCKED TERMS ────────────────────────────────  │
│  Rate:    $1.79/sqft all-in                             │
│  Monthly: $8,950                                        │
│  Term:    6 months                                      │
│  Total:   $53,700                                       │
│  🔒 Space held until Feb 28, 2:14 PM                   │
│  Rate confirmed at reservation. Not renegotiable.       │
│                                                         │
│  ─── PROPERTY DETAILS ─────────────────────────────────  │
│  36,200 sqft available in 90,500 sqft building          │
│  Storage only · M-1 Zoning                              │
│  4 dock doors · 28' clear height · Sprinklered          │
│  [Open in Maps ↗]                                      │
│                                                         │
│  ─── TIMELINE ─────────────────────────────────────────  │
│  ✓ Feb 25, 2:14 PM — Space reserved                    │
│  ✓ Feb 25, 2:14 PM — WEx Guarantee signed              │
│  ✓ Feb 25, 2:16 PM — Tour requested                    │
│  ● Waiting for supplier confirmation...                 │
│                                                         │
│  ─── QUESTIONS ────────────────────────────────────────  │
│  Have a question about this space?                      │
│  [Ask a Question]                                       │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 6.7 Tour Rescheduled — Action Required

```
┌──────────────────────────────────────────────────┐
│  🔄 New tour time proposed                       │
│                                                  │
│  860 Sandhill Ave, Carson, CA                    │
│  Proposed: Monday, March 2, 10:00 AM             │
│                                                  │
│  🔒 Hold still active — expires Feb 28, 2:14 PM  │
│                                                  │
│  [Accept New Time]    [Suggest Different Time]   │
│                                                  │
│  Respond within 24 hours.                        │
└──────────────────────────────────────────────────┘
```

Note: If proposed new time is after the current hold expiry, the system automatically extends the hold to cover the proposed tour date + 48 hours for post-tour decision. Surface this clearly:
```
Note: Accepting this time will extend your hold to March 4, 2:14 PM.
```

### 6.8 Post-Tour Decision — Action Required

```
┌──────────────────────────────────────────────────┐
│  💬 How was your tour?                           │
│                                                  │
│  860 Sandhill Ave, Carson, CA                    │
│  Tour: Saturday, February 28                     │
│                                                  │
│  🔒 Hold expires in 23:41:09                     │
│  Rate locked: $8,950/mo · 6 months               │
│                                                  │
│  [✓ Yes, I want this space]                      │
│  [? I have questions]   [✗ Pass on this space]  │
│                                                  │
└──────────────────────────────────────────────────┘
```

Countdown visible here creates natural urgency — the hold expiry and the decision timer are the same mechanic.

---

## 7. Data Fields Required by This Flow

These fields must be added or confirmed on the Engagement model to support the hold mechanic:

| Field | Type | Purpose |
|-------|------|---------|
| `hold_expires_at` | timestamp | Set at guarantee_signed. hold_expires_at = guarantee_signed_at + 72hrs |
| `hold_extended` | boolean | True if buyer used their one extension |
| `hold_extended_at` | timestamp | When extension was granted |
| `hold_extended_until` | timestamp | New expiry after extension |
| `tour_notes` | text (nullable) | Buyer's notes from Step 3 date picker |
| `path` | enum [tour, instant_book] | Set at buyer_accepted. Already in Engagement Lifecycle Spec v2. |

---

## 8. Page Routes

| Route | Page | Notes |
|-------|------|-------|
| `/search/results` | Results page with match cards | Update button hierarchy per this spec |
| `/buyer` | Buyer dashboard (deal tracker) | Redirect here after "View My Deals" on Step 4 |
| `/buyer/engagements/[id]` | Engagement detail page | Accessible from dashboard "View Details" |
| `/buyer/engagements/[id]/agree` | Agreement signing | Accessible when agreement_sent |
| `/buyer/engagements/[id]/onboard` | Onboarding checklist | Accessible when agreement_signed |
| `/buyer/payments` | Payment history | Accessible when active |

---

## 9. State Transitions Triggered by This Flow

| User Action | Engagement Transition |
|-------------|----------------------|
| Clicks "Reserve & Tour" | buyer_reviewing → buyer_accepted (path=tour) |
| Clicks "Book Instantly" | buyer_reviewing → buyer_accepted (path=instant_book) |
| Creates account / signs in (Step 1) | buyer_accepted → account_created |
| Checks guarantee + confirms (Step 2) | account_created → guarantee_signed · hold_expires_at set |
| guarantee_signed + path=tour | guarantee_signed → address_revealed (automatic) |
| guarantee_signed + path=instant_book | guarantee_signed → instant_book_requested → buyer_confirmed |
| Submits tour date/time (Step 3) | address_revealed → tour_requested |
| Clicks "Accept New Time" | tour_rescheduled → tour_confirmed |
| Clicks "Yes, I want this space" | tour_completed → buyer_confirmed |
| Clicks "Pass" | tour_completed → declined_by_buyer |
| Hold timer reaches 72hrs | any active state → expired (if decision not made) |
| Buyer requests extension | hold_expires_at extended by 24hrs (once only) |

---

## 10. Background Jobs Added by This Flow

| Job | Schedule | What It Does |
|-----|----------|-------------|
| `check_hold_expiry_warnings` | Every 15 minutes | Finds engagements where hold_expires_at is within 24hrs or 4hrs. Sends warning notifications. |
| `expire_holds` | Every 15 minutes | Finds engagements where hold_expires_at has passed and status is still pre-decision. Transitions to expired. Notifies both parties. Releases sqft allocation. |

Both jobs are additive to the existing `check_deadlines` job. They run on the same schedule but check hold_expires_at specifically.

---

## 11. What This Spec Does Not Cover

| Feature | Spec |
|---------|------|
| Agreement signing page content | Agreements Spec |
| Onboarding checklist | Agreements Spec |
| Payment schedule and invoicing | Payments Spec |
| Q&A AI routing | Engagement Lifecycle Spec v2, Section 7 |
| Supplier deal ping and confirmation | Engagement Lifecycle Spec v2, Section 3 |
| Admin portal | Admin Spec |
| SMS / Twilio integration | Deferred — email only for launch |
| Buyer view count urgency signal | Phase 2 — spec separately when implementing |

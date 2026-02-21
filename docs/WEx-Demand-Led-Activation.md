# Demand-Led Activation (DLA)
## WEx Architecture Supplement — Supplier Flow

**Version:** 1.0 · **Date:** February 2026  
**Status:** Design Spec · **Owned by:** Product (Dinesh)

---

## 1. What Is Demand-Led Activation?

Demand-Led Activation is a distinct supplier onboarding path triggered not by supplier curiosity or intent, but by a live buyer match. A real buyer has submitted requirements. The clearing engine has identified a non-network property as a strong candidate. WEx reaches out to that supplier with a specific opportunity already in hand.

This is fundamentally different from the other supplier paths:

| Path | Trigger | Supplier Motivation | Deal Visible? |
|------|---------|---------------------|---------------|
| EarnCheck | Supplier curiosity | "What could I earn?" | No — hypothetical |
| Direct Onboarding | Supplier intent | "I want to list my space" | No — future deals |
| **Demand-Led Activation** | **Buyer match found** | **"There's a real deal right now"** | **Yes — specific buyer** |

The psychology is entirely different. The supplier isn't being asked to speculatively join a network. They're being shown a deal on the table today. This produces higher conversion, faster decisions, and better pricing cooperation — because the opportunity cost of saying no is visible and real.

---

## 2. EarnCheck vs. Direct Onboarding vs. DLA — Key Distinctions

These three paths are often confused. They must remain architecturally and experientially separate.

### EarnCheck
- A **curiosity tool only** — not an onboarding funnel
- Supplier enters address, sees revenue estimate, adjusts slider, leaves
- No commitment, no network activation
- WEx captures address + valuation data silently in the background
- Supplier is **not in the network** after EarnCheck

### Direct Onboarding
- Supplier arrives with **intent to list**
- WEx auto-pulls property data from CoStar/database — no manual entry needed
- Supplier reviews data, configures space, sets pricing, agrees to terms, flips the switch
- No specific buyer is shown — supplier is joining for future deals
- Target completion: under 5 minutes

### If They Did EarnCheck First
- WEx already has their property data
- Onboarding becomes **confirmation + consent**, not data collection
- "We already have your building on file. Here's what we have — does anything need updating? Great — agree to these terms and you're live."
- Even faster than standard onboarding

### Post-Onboarding Profile Building (All Paths)
After joining through any path, WEx continues to enrich the property profile progressively:
- One-question SMS or email follow-ups over time
- Photo requests via mobile link
- Answers stored automatically into property record
- Never feels like form-filling — feels like occasional check-ins

---

## 3. Where DLA Lives in the Overall Flow

DLA is triggered by the Clearing Engine when a buyer search produces insufficient Tier 1 (in-network) matches.

```
Buyer submits 5-step requirements
        │
        ▼
Clearing Engine runs against in-network supply
        │
        ├─► Sufficient Tier 1 matches → Standard flow, no DLA needed
        │
        └─► Insufficient matches → DLA triggered
                │
                ▼
        Property DB query: off-network candidates
        (earncheck_only, interested, third_party)
                │
                ▼
        Score + rank candidates by match quality
                │
                ▼
        Generate deal-specific tokenized URL per candidate
                │
                ▼
        Send outreach SMS / email → Supplier
                │
        ┌───────┴────────┐
        │                │
   Interested       Not interested / No response
        │                │
        ▼                ▼
  DLA Flow begins   Store outcome in property record
                    Adjust future outreach frequency
```

**Buyer visibility:** The buyer sees "we're sourcing additional options" and gets notified when a new match clears. They never know whether a space was already in-network or just activated in response to their search. This is intentional and must remain invisible.

---

## 4. The Outreach Message

Sent via SMS (primary) or email (fallback). References the supplier's specific property and the real buyer opportunity — buyer identity remains anonymous.

**Message format:**

> Hi [Name] — Warehouse Exchange has a buyer looking for [X,XXX] sqft in [neighborhood/area] for [use type], starting [timeframe]. Your property looks like a strong match. Estimated rate: $X.XX/sqft — that's ~$X,XXX/month.
>
> We already have your property info on file, so getting started takes less than 5 minutes. Interested?
> → [tokenized link]
>
> Reply STOP to opt out.

**What the message does not include:**
- Buyer name or company
- Full property address (neighborhood only)
- Platform pitch or signup language — reads as an opportunity, not an ad

**Config variables (owned by Product, not hardcoded by backend):**
- Response window duration (default: 48 hours — testable at 24, 12, 8, 4)
- Maximum outreach attempts per property per 30-day period
- Channel priority (SMS first vs. email first)
- Message copy and tone variants (A/B testable)

---

## 5. The DLA Flow — Step by Step

### Step 1 — Supplier Clicks the Link

The tokenized URL carries two identifiers: the property ID and the buyer requirement ID. When opened, the backend resolves both and returns a pre-loaded page. No address entry. No registration. No form.

The supplier sees:
- Building specs already displayed (size, specs, neighborhood-level location, satellite image)
- "Is this your property?" — a single confirm or correct action

If any data is wrong, they can flag it. That correction is stored into the property record regardless of whether the deal proceeds.

### Step 2 — The Opportunity Is Shown

Before asking for any commitment, WEx shows the supplier the specific deal:

> A company needs [X,XXX sqft] for [use type] starting [date]. [X]-month term.  
> Your space fits their requirements.  
> **Proposed rate: $X.XX/sqft — $X,XXX/month.**  
> Market range for your area: $X.XX – $X.XX/sqft.

The proposed rate is WEx's recommended rate, anchored to market data and the buyer's budget. It is presented as the rate most likely to win — not a take-it-or-leave-it, but informed guidance.

### Step 3 — Rate Decision

The supplier has two options:

**Accept the proposed rate** → Proceed directly to agreement. Fastest path.

**Propose a different rate** → Supplier enters their preferred rate. The system responds honestly:

> Got it — we've noted your rate of $X.XX/sqft. The buyer's current budget is closer to $X.XX, so we'll present your space but want to be upfront — there are already [N] spaces within their budget range. We'll let you know what they decide.

The counter-rate is stored against the property record. The supplier is not rejected — they are informed. WEx presents the counter to the buyer and lets the market decide.

**If the buyer selects a different space**, the supplier receives a factual outcome notification:

> The buyer selected another space this time. Your property stays on file — we'll reach out when the next match comes up.

Over time, suppliers who consistently ask above market will see a pattern of losses without WEx ever applying pressure. The market teaches them to trust the recommended rate.

### Step 4 — Agreement

Once rate is confirmed, the supplier moves through a lightweight agreement:
- WEx terms of engagement (anti-circumvention, platform rules)
- Stripe bank setup for automated monthly deposits
- Confirmation of available dates and any restrictions

Because property data is already on file, this is confirmation + consent — not data collection. Target completion: under 5 minutes.

### Step 5 — Supplier Status Flips

The moment agreement is signed, three things happen simultaneously:

1. `supplier_status` → `in_network`
2. Property enters the clearing engine as an active Tier 1 match for the triggering buyer
3. Buyer notification fires

### Step 6 — Buyer Is Notified

The buyer receives a notification through whatever channel they left contact for — email, SMS, or a live update to their results page if still active.

> Good news — a new space just confirmed availability for your requirements. [Neighborhood], [sqft], $X.XX/sqft. [View match →]

The buyer has no visibility into the fact that this supplier just onboarded. From their perspective, a new match appeared.

---

## 6. Property Status Model

All properties — network and non-network — live in **one `properties` table** with a `supplier_status` field. Do not split into separate tables. The clearing engine needs to evaluate all candidates in a single query; cross-table joins create unnecessary complexity and performance risk.

```
supplier_status: enum [
  third_party,          // in WEx DB from CoStar/public data, never contacted
  earncheck_only,       // completed EarnCheck, no onboarding initiated
  interested,           // clicked DLA link or expressed intent, not yet onboarded
  onboarding,           // actively in onboarding flow
  in_network,           // fully onboarded, active, matchable (Tier 1)
  in_network_paused,    // onboarded but not accepting new deals
  declined,             // explicitly not interested
  unresponsive          // outreached, no response after max attempts
]
```

| Status | Tier 1 Eligible | DLA Outreach Eligible |
|--------|----------------|----------------------|
| `third_party` | No | Yes |
| `earncheck_only` | No | Yes |
| `interested` | No | Yes |
| `onboarding` | No | No (in progress) |
| `in_network` | Yes | No |
| `in_network_paused` | No | No |
| `declined` | No | No (subject to cooldown) |
| `unresponsive` | No | No (subject to cooldown) |

---

## 7. What Happens to Non-Converted Suppliers

Every DLA outcome — whether the supplier converts or not — produces data stored to the property record. Nothing is wasted.

| Outcome | What Gets Stored |
|---------|-----------------|
| Completed onboarding | `in_network`, rate agreed, deal linked |
| Interested → dropped off mid-flow | `interested`, last step reached, timestamp |
| Counter-rate provided | Rate floor stored, outcome of deal tracked |
| Not interested (with reason) | Reason stored, `declined`, outreach frequency reduced |
| No response after window | `unresponsive`, retry scheduled per policy |
| Flagged data corrections | Property record updated regardless of deal outcome |

Over time, this builds a behavioral profile on every property — even those that have never formally joined the network.

---

## 8. Time-Bound Response Windows

Response windows apply to both off-network suppliers in DLA outreach and in-network suppliers receiving deal pings. Windows enforce deal momentum and protect buyer experience.

- **Off-network (DLA outreach):** Default 48-hour response window. Configurable by Product.
- **In-network (deal ping):** Default 12-hour accept/pass window. Supplier missing the window does not penalize the buyer — WEx moves to the next candidate automatically.
- Consistently slow responders are tracked behaviorally and ranked lower in future dispatch.
- Window duration is a **Product-owned config variable** — changeable without a backend deploy.

---

## 9. Build Ownership

| Component | Owner |
|-----------|-------|
| Outreach message copy and tone | Product |
| Response window duration | Product (config-driven) |
| Rate presentation UX and messaging | Product |
| Counter-rate framing and response messaging | Product |
| A/B test variants on any of the above | Product |
| Number of match slots shown to supplier ("2 other spaces") | Product |
| Outcome notification copy (win/loss messages) | Product |
| Deal-specific tokenized URL generation | Backend |
| Property + buyer requirement resolution by token | Backend |
| `supplier_status` transitions and timing enforcement | Backend (config-driven, rules set by Product) |
| Stripe agreement and bank setup integration | Backend |
| Buyer notification trigger on supplier confirmation | Backend |
| Property record field writes from every DLA outcome | Backend |
| Outreach rate limiting and retry scheduling | Backend (rules set by Product) |

---

## 10. Key API Contracts (Backend Must Provide)

### 1. Resolve DLA Token
`GET /dla/token/:token`  
Returns: property data (pre-populated), buyer requirement summary (anonymized), recommended rate, market rate range, buyer budget ceiling

### 2. Submit Rate Decision
`POST /dla/token/:token/rate`  
Body: `{ accepted: bool, proposed_rate?: float }`  
Returns: next step URL (agreement) or counter-rate confirmation message copy

### 3. Confirm Agreement
`POST /dla/token/:token/confirm`  
Body: signed agreement reference, Stripe setup status  
Returns: success → triggers `supplier_status: in_network` + buyer notification simultaneously

### 4. Store Non-Conversion Outcome
`POST /dla/token/:token/outcome`  
Body: `{ outcome: enum, reason?: string, rate_floor?: float }`  
Returns: acknowledgment → property record updated

---

## 11. SLAs

| Operation | Target | Impact if Missed |
|-----------|--------|-----------------|
| Outreach delivery after buyer search | < 30 minutes | Buyer waiting, deal cools |
| Token URL page load (property + opportunity) | < 2 seconds | Supplier abandons |
| Supplier status flip on agreement | Real-time | Buyer notification delayed |
| Buyer notification after supplier confirms | < 1 minute | Buyer has moved on |
| Response window enforcement | Exact | Creates trust that windows mean something |

---

*This document supplements the WEx Technical Overview and should be read alongside the Supplier Journey and Marketplace Interaction Map. It describes the Demand-Led Activation path only — EarnCheck, Direct Onboarding, and post-onboarding profile building are covered in the main Technical Overview.*

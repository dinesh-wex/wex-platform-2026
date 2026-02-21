# Warehouse Exchange — Technical Overview
## Complete User Journey Architecture

**Version:** 1.0 · **Date:** February 2026 · **Audience:** CTO / Engineering Leadership
**Status:** Architecture Review Draft

---

## 1. System Overview

WEx is transitioning from a broker-assisted marketplace to an AI-powered clearinghouse. The platform matches buyer demand for flexible warehouse space with supplier inventory, earning revenue through an invisible spread between the buyer's all-in rate and the supplier's asking rate.

The system has five core subsystems:

| Subsystem | Purpose | Key Dependencies |
|-----------|---------|-----------------|
| **Property Intelligence** | Auto-build property profiles from address input | CoStar API, Google Maps/Satellite, WEx proprietary DB |
| **Clearing Engine** | Match buyer requirements to supplier inventory | Matching algorithm, pricing model, dispatch queue |
| **Communication Layer** | Multi-channel buyer/supplier interaction | SMS (Twilio), Email, Web chat, Multi-agent AI |
| **Transaction Engine** | Contracts, payments, billing | DocuSign API, Stripe Connect |
| **Data Flywheel** | Learn from every interaction to improve matching/pricing | Event store, analytics pipeline, ML models |

---

## 2. Property Intelligence Service

### 2.1 Data Acquisition Pipeline

When a supplier enters an address (via EarnCheck or direct onboarding), the system executes a data enrichment pipeline:

```
Address Input
  │
  ├─► Geocode (Google Maps API)
  │     └─► lat/lng, formatted address, place_id
  │
  ├─► WEx Property DB Lookup
  │     └─► If exists: return cached profile (skip CoStar)
  │     └─► If not: continue pipeline
  │
  ├─► CoStar API Query
  │     └─► Building specs: size, clear height, dock doors, drive-in bays,
  │         year built, construction type, zoning, lot size, power supply
  │     └─► Owner info: name, contact, entity type
  │
  ├─► Satellite Imagery (Google Maps Static API)
  │     └─► Aerial view of property
  │     └─► Street-level imagery if available
  │
  └─► WEx Valuation Model
        └─► Market rate estimate based on: location, building class,
            size, comparable transactions, current demand density
```

### 2.2 Property Profile Schema (Core Fields)

```
Property {
  id: uuid
  address: {street, city, state, zip, lat, lng}
  
  // From data APIs (auto-populated)
  building_specs: {
    total_sqft: int
    clear_height_ft: int
    dock_doors: int
    drive_in_bays: int
    year_built: int
    construction_type: enum [metal_steel, concrete, tilt_up, masonry]
    zoning: string
    lot_size_acres: float
    heated: bool
    power_supply: enum [standard, manufacturing_grade]
  }
  
  owner: {name, email, phone, entity, source: enum [costar, manual, earncheck]}
  images: [{url, type: enum [satellite, street, uploaded], source}]
  
  // From supplier configuration
  config: {
    available_sqft: int
    min_rentable_sqft: int
    activity_tier: enum [storage, light_ops, distribution]
    has_office: bool
    weekend_access: bool
    available_from: date
    min_term_months: int
  }
  
  // From supplier pricing decision
  pricing: {
    model: enum [automated, manual]
    target_rate_sqft: float          // supplier's asking rate
    rate_floor: float                // lowest they've indicated willingness
    manual_fee_pct: float            // 15% for manual model
  }
  
  // System-generated
  market_data: {
    area_rate_low: float
    area_rate_high: float
    area_rate_median: float
    demand_density: float            // buyer searches per month in area
    last_updated: timestamp
  }
  
  // Behavioral (built over time)
  memory: {
    rejection_reasons: [{buyer_id, reason, timestamp}]
    questions_asked: [{question, answer, source, timestamp}]
    deal_history: [{buyer_id, outcome, rate, timestamp}]
    response_time_avg: float         // hours
    acceptance_rate: float
  }
  
  status: enum [passive, network_ready, active_deal, occupied]
  network_joined: timestamp | null
  source_path: enum [earncheck, direct, cold_outreach]
}
```

### 2.3 WEx Property Database (Proprietary)

Long-term strategy is to build a comprehensive US warehouse database independent of CoStar:

- **Sources:** CoStar (current), county assessor records, web scraping (LoopNet, Crexi listings), user-submitted data, satellite analysis
- **Goal:** Every commercial/industrial property in target metros profiled without needing CoStar per-query
- **Storage:** PostgreSQL with PostGIS extension for geospatial queries
- **Update cadence:** CoStar sync weekly, proprietary sources daily, user-submitted real-time

---

## 3. EarnCheck Service

### 3.1 Architecture

EarnCheck is a standalone microservice that serves as the primary supplier acquisition funnel. It is intentionally decoupled from the main platform so it can be deployed as a lightweight landing page, embedded widget, or linked from marketing campaigns.

```
EarnCheck Flow:
  
  [Address Input] ──► Property Intelligence Service
                           │
                           ▼
                    [Valuation Model]
                           │
                           ▼
                    [Results Page: Revenue Estimate + Satellite Image]
                           │
                     User adjusts space slider
                           │
                           ▼
                    [Configurator: 5-6 questions]
                           │
                           ▼
                    [Pricing Model Selection]
                           │
                           ▼
                    [Network Activation] ──► Main Platform (Property created)
```

### 3.2 Valuation Model

```
estimate_revenue(property, available_sqft):
  base_rate = get_market_rate(property.address, property.building_specs)
  
  adjustments:
    +15% if activity_tier allows light_ops (vs storage only)
    +8%  if has_office
    +2%  if weekend_access
    -5%  if building_age > 30 years
    +10% if clear_height > 24ft
    ±X%  demand density adjustment (high demand areas get premium)
  
  adjusted_rate = base_rate * (1 + sum(adjustments))
  monthly_revenue = adjusted_rate * available_sqft
  annual_revenue = monthly_revenue * 12
  
  return {monthly_revenue, annual_revenue, rate_per_sqft, market_range}
```

### 3.3 Analytics & Tracking

EarnCheck has its own analytics dashboard (already built) tracking:

- Properties searched, total available space, estimated monthly/annual value
- Funnel: Address → Size → Form → Pricing → Email (with drop-off rates per step)
- Pricing model choice: Automated vs Manual split
- Visitor engagement: page views, engaged visitors, email submissions, conversion %

---

## 4. Buyer Flow Service

### 4.1 Requirements Capture

The buyer flow captures structured requirements through a multi-step UI or natural language via SMS.

```
BuyerRequirement {
  id: uuid
  
  // From flow steps
  location: {city, state, zip, lat, lng, radius_miles}
  use_type: enum [storage, light_ops, distribution]
  goods_type: enum [general, food_perishable, chemicals_hazmat, 
                     high_value, electronics, apparel, other]
  size_sqft: int
  timing: enum [immediately, within_30_days, 1_3_months, flexible]
  duration: enum [1_3_mo, 3_6_mo, 6_12_mo, 12_24_mo, 24_plus]
  deal_breakers: [enum [office, weekend_access, loading_dock, high_power, 
                         climate_control, 24_7_access, sprinkler, parking_50]]
  budget_monthly: float | null        // optional, may be skipped
  
  // Contact (captured at action, not upfront)
  contact: {
    email: string | null
    phone: string | null
    capture_method: enum [tour_booking, question, save_search, 
                          sms, email_list, tier2_notify]
    captured_at: timestamp | null
  }
  
  // System
  source: enum [web_flow, sms, loopnet, crexi, broker]
  broker_id: uuid | null
  created_at: timestamp
  status: enum [searching, matched, touring, closed, expired]
}
```

### 4.2 SMS Channel Architecture

```
Buyer SMS ("I need 10K sqft in Houston for storage")
    │
    ▼
[Twilio Webhook] ──► [AI Parser Agent]
                           │
                           ▼
                    [NLP → Structured BuyerRequirement]
                           │
                           ▼
                    [Clearing Engine] ──► matches
                           │
                           ▼
                    [Response Agent] ──► formats match results for SMS
                           │
                           ▼
                    [Polisher Agent] ──► tone, dedup, error check
                           │
                           ▼
                    [Twilio Send] ──► Buyer receives SMS with matches
```

**Multi-Agent Stack:**

| Agent | Role | Handles |
|-------|------|---------|
| **Parser Agent** | NLP extraction | Converts natural language to structured requirements |
| **Response Agent** | Content generation | Formats match results, answers questions, drafts messages |
| **Router Agent** | Triage | Determines if AI can handle or needs human escalation |
| **Human Operator** | Judgment calls | Complex negotiations, edge cases, relationship moments |
| **Polisher Agent** | Quality gate | Ensures consistent tone, removes repeated info, fixes typos |

All agents share conversation context. Human operators see full AI conversation history before responding. Polisher is the last gate before any message reaches the buyer — human or AI responses both pass through it.

---

## 5. Clearing Engine (Matching & Dispatch)

This is the core system. It connects buyer demand to supplier inventory using a tiered dispatch model.

### 5.1 Matching Algorithm

```
match(buyer_requirement) -> [ScoredMatch]:
  
  candidates = query_properties(
    location = buyer.location (within radius),
    min_sqft >= buyer.size_sqft,
    activity_tier includes buyer.use_type,
    available_from <= buyer.timing_date,
    min_term <= buyer.duration,
    zoning compatible with buyer.goods_type
  )
  
  for each candidate:
    score = weighted_sum(
      location_proximity:    0.25,  // distance from requested location
      size_fit:              0.20,  // how close to requested size (not too big, not too small)
      activity_match:        0.15,  // exact match vs compatible
      amenity_match:         0.15,  // deal-breakers satisfied
      supplier_reliability:  0.10,  // response rate, acceptance rate history
      price_fit:             0.10,  // rate vs buyer budget (if provided)
      availability_fit:      0.05,  // how soon vs when buyer needs
    )
    
    classify:
      TIER_1 if candidate.status == network_ready AND candidate.pricing.model != null
      TIER_2 if candidate exists in database but not network_ready
  
  return sorted by score, partitioned by tier
```

### 5.2 Dispatch Logic

```
dispatch(buyer_requirement, matches):
  
  tier_1 = matches.filter(TIER_1).top(3)
  tier_2 = matches.filter(TIER_2).top(3)
  
  // IMMEDIATE: Show Tier 1 to buyer
  present_to_buyer(tier_1)
  
  // ASYNC: Ping Tier 2 suppliers
  for each supplier in tier_2:
    suggested_rate = calculate_suggested_rate(
      market_median = area_rate_median,
      buyer_budget = buyer.budget_monthly / buyer.size_sqft,  // if available
      tier_1_rates = avg(tier_1.rates),
      supplier_rate_floor = supplier.pricing.rate_floor        // if known from history
    )
    
    send_deal_ping(supplier, {
      buyer_requirements: anonymized,
      suggested_rate: suggested_rate,
      estimated_monthly_income: suggested_rate * available_sqft,
      response_deadline: now + 12_hours
    })
  
  // BACKFILL LOOP
  schedule_job(after: 12_hours) {
    accepted = get_accepted_tier2()
    if accepted.count < 3 - tier_1.count:
      next_batch = matches.filter(TIER_2).skip(3).top(3 - accepted.count)
      dispatch_tier2(next_batch)
    
    // Notify buyer of new options
    for each newly_accepted:
      notify_buyer("A new space just cleared for your search", newly_accepted)
  }
```

### 5.3 Dispatch Queue Schema

```
DispatchPing {
  id: uuid
  buyer_requirement_id: uuid
  property_id: uuid
  supplier_id: uuid
  
  tier: enum [tier_1, tier_2]
  suggested_rate: float
  
  status: enum [pending, accepted, declined, expired, auto_accepted]
  response_deadline: timestamp
  responded_at: timestamp | null
  
  decline_reason: string | null      // stored in property memory
  counter_rate: float | null         // if supplier proposes different rate
  
  created_at: timestamp
}
```

### 5.4 Pricing Engine

The pricing engine determines the buyer's all-in rate (which includes WEx's spread) and the suggested rate for Tier 2 supplier outreach.

```
calculate_buyer_rate(supplier_rate, property, buyer_requirement):
  
  base_spread = 0.15    // 15% default target spread
  
  adjustments:
    +5%  if timing == immediately (urgency premium)
    +3%  if size < 3000 sqft (small space premium)
    -3%  if duration > 12 months (volume discount on spread)
    ±X%  demand/supply ratio in market
  
  spread = base_spread * (1 + sum(adjustments))
  buyer_rate = supplier_rate * (1 + spread)
  
  // Sanity check against market
  if buyer_rate > area_rate_high * 1.3:
    cap buyer_rate, reduce spread
  
  return {buyer_rate, supplier_rate, spread, monthly_buyer_cost, monthly_supplier_payout}
```

Over time, the spread becomes dynamic based on:
- Supply/demand density per market (more demand, higher spread)
- Supplier response rates (reliable suppliers may get better positioning)
- Buyer urgency (immediate needs tolerate higher rates)
- Seasonal patterns (Q4 peak season vs Q1 slow season)

---

## 6. Tour & Commitment Service

### 6.1 Tour Booking Flow

```
Tour Request Flow:

  [Buyer accepts match] 
      │
      ├─► Buyer provides contact info (if not already captured)
      ├─► Buyer signs WEx Occupancy Guarantee (DocuSign / in-app checkbox)
      ├─► Buyer selects preferred tour date/time
      │
      ▼
  [WEx sends tour request to supplier]
      │
      ├─► Supplier has 12 hours to:
      │     ├─ Confirm → tour is booked, buyer notified
      │     ├─ Propose alternative time → buyer reviews
      │     └─ No response → buyer notified, property deprioritized
      │
      ▼
  [Tour confirmed]
      │
      ├─► Both parties receive: date, time, address (NOW revealed to buyer)
      ├─► Supplier receives: buyer company name, requirements summary
      ├─► Anti-circumvention agreement active for both parties
      │
      ▼
  [Tour occurs]
      │
      ▼
  [Post-tour follow-up: automated 24hr check-in]
      │
      ├─► Buyer confirms → proceed to close
      ├─► Buyer has questions → route to Q&A system
      ├─► Buyer requests adjustment → mediation flow
      ├─► Buyer passes → property released, buyer shown alternatives
      └─► No response 48hrs → reminder. No response 72hrs → requirement marked stale.
```

### 6.2 Multi-Property Tour Coordination

When a buyer selects multiple properties for tours:

```
coordinate_tours(buyer, selected_properties):
  
  group_by_city = cluster(selected_properties by location)
  
  for each city_group:
    suggest_single_day with staggered times:
      property_1: 10:00 AM
      property_2: 1:00 PM
      property_3: 3:00 PM
    
    account for travel_time between properties
    send_combined_schedule to buyer
    send_individual_confirmations to each supplier
```

### 6.3 Anti-Circumvention Agreement

Triggered at tour scheduling. Executed as:
- **Primary:** DocuSign for formal execution
- **Fallback:** In-app checkbox with legal acceptance language

Framed to both parties as **WEx Occupancy Guarantee**, covering:
- Pricing transparency commitment
- Insurance coverage during lease
- Dispute resolution process
- Non-circumvention clause for this specific deal (defined period)

---

## 7. Transaction Engine

### 7.1 Close Sequence

```
close_deal(buyer, supplier, property, agreed_terms):
  
  Step 1: Engagement Agreement
    ├─► Generate from WEx template with deal-specific terms
    ├─► Send via DocuSign to both parties simultaneously
    ├─► Buyer sees: all-in rate (supplier_rate + spread)
    ├─► Supplier sees: their agreed rate
    └─► Track: signed/pending/expired status
  
  Step 2: Buyer Onboarding (parallel with Step 3)
    ├─► Upload: certificate of insurance
    ├─► Upload: company registration documents
    ├─► Stripe Connect: payment method for recurring billing
    └─► Validation: verify insurance coverage meets property requirements
  
  Step 3: Supplier Onboarding
    ├─► Stripe Connect: bank account for receiving deposits
    └─► Verify: account ownership
  
  Step 4: Activate Lease
    ├─► Set lease start date
    ├─► Schedule recurring billing (Stripe Subscriptions)
    ├─► Buyer charged: all-in rate × sqft (monthly)
    ├─► Supplier deposited: their rate × sqft (monthly, after WEx processing)
    └─► WEx retains: spread amount
```

### 7.2 Stripe Integration Architecture

```
Stripe Connect (Platform Model):

  WEx = Platform Account
    │
    ├── Buyer = Customer
    │     └── PaymentMethod (card or ACH)
    │     └── Subscription (monthly billing)
    │
    └── Supplier = Connected Account (Express or Custom)
          └── Bank Account (for payouts)
          └── Transfer (monthly deposit from WEx)

Monthly Billing Cycle:
  1. Stripe charges Buyer: $5,000 (all-in rate)
  2. Funds land in WEx platform account
  3. WEx transfers to Supplier connected account: $4,100 (supplier rate)
  4. WEx retains: $900 (spread)
  5. Stripe fees deducted from WEx's retained amount
```

### 7.3 Deal Schema

```
Deal {
  id: uuid
  buyer_requirement_id: uuid
  property_id: uuid
  supplier_id: uuid
  buyer_id: uuid
  broker_id: uuid | null
  
  terms: {
    buyer_rate_sqft: float         // all-in rate buyer pays
    supplier_rate_sqft: float      // rate supplier receives
    spread_sqft: float             // WEx margin
    sqft: int                      // rented space
    monthly_buyer_total: float
    monthly_supplier_payout: float
    monthly_wex_revenue: float
    term_months: int
    start_date: date
    end_date: date
  }
  
  agreements: {
    guarantee_signed_buyer: {docusign_id, signed_at}
    guarantee_signed_supplier: {docusign_id, signed_at}
    engagement_signed_buyer: {docusign_id, signed_at}
    engagement_signed_supplier: {docusign_id, signed_at}
  }
  
  payments: {
    stripe_customer_id: string      // buyer
    stripe_connected_account_id: string  // supplier
    stripe_subscription_id: string
    deposit_collected: bool
    first_month_collected: bool
  }
  
  status: enum [pending_agreements, pending_onboarding, active, 
                completed, cancelled, disputed]
  
  timeline: {
    matched_at: timestamp
    tour_scheduled_at: timestamp
    tour_completed_at: timestamp
    buyer_confirmed_at: timestamp
    agreements_signed_at: timestamp
    onboarding_completed_at: timestamp
    lease_started_at: timestamp
    lease_ended_at: timestamp
  }
}
```

---

## 8. Communication Layer

### 8.1 Multi-Agent Architecture

All buyer-facing communication routes through a unified agent pipeline:

```
Incoming Message (any channel: web chat, SMS, email)
    │
    ▼
[Router Agent]
    │
    ├── Can AI answer? (data lookup, FAQ, property specs)
    │     └── YES → [Response Agent] → [Polisher Agent] → Send
    │
    ├── Needs supplier input? (property-specific question not in DB)
    │     └── Route to supplier → await response → store in property memory
    │     └── Buyer sees: "Checking on this — we'll have an answer shortly."
    │
    └── Needs human judgment? (negotiation, complex situation, emotional)
          └── Route to human operator queue
          └── Human responds → [Polisher Agent] → Send
```

### 8.2 Polisher Agent Responsibilities

- Ensure consistent voice/tone across AI and human responses
- Remove repeated information (checks full conversation history)
- Fix typos and grammar in human operator responses
- Redact internal information (supplier rates, WEx margin, internal notes)
- Validate no addresses/names are revealed pre-commitment
- Final quality gate — nothing reaches buyer or supplier without passing through

### 8.3 Property Memory (Question-Answer Store)

```
PropertyQA {
  property_id: uuid
  question: string
  answer: string
  source: enum [database, supplier, ai_inferred]
  confidence: float
  asked_count: int              // how many buyers asked this
  first_asked: timestamp
  last_asked: timestamp
}

// When a new question comes in:
lookup_answer(property_id, question):
  1. Check PropertyQA for semantic match (embedding similarity)
  2. Check building_specs for factual answer
  3. Check CoStar data
  4. If no answer found → route to supplier
  5. Store answer in PropertyQA for future use
```

---

## 9. Data Flywheel & Intelligence

### 9.1 Event Store

Every interaction generates events that feed the intelligence layer:

```
Events captured:
  buyer_searched         {requirements, timestamp, source}
  property_matched       {buyer_id, property_id, score, tier}
  supplier_pinged        {property_id, suggested_rate, deadline}
  supplier_accepted      {property_id, accepted_rate}
  supplier_declined      {property_id, reason, counter_rate}
  supplier_expired       {property_id, no_response}
  buyer_viewed_results   {buyer_id, properties_shown, time_spent}
  buyer_selected         {buyer_id, property_id, action: tour|book}
  buyer_abandoned        {buyer_id, last_step, properties_shown}
  tour_scheduled         {deal_id, date}
  tour_completed         {deal_id, outcome}
  question_asked         {buyer_id, property_id, question, channel}
  deal_closed            {deal_id, terms}
  deal_lost              {deal_id, reason, stage}
```

### 9.2 Intelligence Outputs

| Input Data | Intelligence Produced | Used For |
|------------|----------------------|----------|
| Supplier accept/decline patterns | Rate floors per property, preferred use types | Smarter dispatch, avoid wasted pings |
| Buyer selections (cheaper vs premium) | Willingness-to-pay by segment | Dynamic spread optimization |
| Response times by supplier | Reliability score | Matching rank weighting, backfill priority |
| Tour-to-close conversion rates | Property quality signal | Match scoring, listing quality prompts |
| Questions frequently asked | Missing profile data indicators | Product roadmap for profile fields |
| Buyer abandonment by step | Funnel optimization signals | UX improvements |
| Market rate by micro-geography | Pricing model per zip/city | EarnCheck valuations, Tier 2 suggested rates |

### 9.3 Dynamic Pricing (Future State)

As transaction volume grows, the spread becomes algorithmically optimized:

```
optimize_spread(market, buyer_segment, urgency, supply_density):
  
  base = 0.15
  
  if supply_density < threshold:     // few suppliers, high demand
    increase spread (sellers market for WEx)
  
  if buyer.timing == immediately:
    increase spread (urgency premium)
  
  if buyer.duration > 12 months:
    decrease spread (volume incentive)
  
  if market.avg_days_to_fill < 7:
    increase spread (hot market)
  
  // A/B test spread levels to find revenue-maximizing point
  // without reducing conversion
```

---

## 10. Infrastructure & Tech Stack

### 10.1 Recommended Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Frontend** | Next.js (React) | SSR for SEO (listing pages), fast buyer flow |
| **Mobile** | React Native or PWA | SMS-first buyers, supplier deal pings |
| **API** | Node.js / Python FastAPI | Node for real-time, Python for ML/data |
| **Database** | PostgreSQL + PostGIS | Geospatial queries for location matching |
| **Cache** | Redis | Session state, real-time match results, dispatch queue |
| **Search** | Elasticsearch | Property search, fuzzy matching, Browse Collection |
| **Queue** | Bull (Redis) or SQS | Dispatch pings, backfill jobs, notification scheduling |
| **SMS** | Twilio | Buyer/supplier SMS communication |
| **Email** | SendGrid or Postmark | Transactional emails, notifications |
| **Payments** | Stripe Connect | Platform billing model with connected accounts |
| **Contracts** | DocuSign API | Engagement agreements, guarantee signing |
| **AI/NLP** | Gemini / Claude API | SMS parsing, question answering, response generation |
| **Data APIs** | CoStar, Google Maps | Property data enrichment |
| **Hosting** | GCP (Cloud Run + Cloud SQL) | Already aligned with current infrastructure |
| **Monitoring** | Datadog or GCP Cloud Monitoring | System health, funnel metrics |

### 10.2 Key Service Boundaries

```
┌─────────────────────────────────────────────────────┐
│                    API Gateway                       │
├──────────┬──────────┬──────────┬──────────┬─────────┤
│ EarnCheck│  Buyer   │ Clearing │  Tour &  │  Comms  │
│ Service  │  Flow    │  Engine  │  Close   │  Layer  │
│          │  Service │          │  Service │         │
├──────────┴──────┬───┴──────────┴────┬─────┴─────────┤
│   Property Intelligence Service     │  Transaction  │
│   (CoStar, DB, Valuation)           │  Engine       │
│                                     │  (Stripe,     │
│                                     │   DocuSign)   │
├─────────────────┴───────────────────┴───────────────┤
│              PostgreSQL + Redis + Event Store         │
└─────────────────────────────────────────────────────┘
```

### 10.3 Critical SLAs

| Operation | Target | Impact if missed |
|-----------|--------|-----------------|
| EarnCheck address → valuation | < 3 seconds | Supplier drops off |
| Buyer flow → results | < 5 seconds | Buyer abandons |
| Supplier deal ping delivery | < 1 minute | Delayed matching |
| Tier 2 supplier outreach | < 30 minutes after buyer search | Buyer waiting too long |
| Tour confirmation notification | Real-time | Buyer loses confidence |
| SMS response (AI) | < 30 seconds | Buyer texts a broker instead |
| SMS response (human escalation) | < 15 minutes | Buyer disengages |
| Post-tour follow-up | Within 24 hours | Deal cools |

---

## 11. Cold Outreach Service (Gap 8)

### 11.1 Non-Network Supplier Activation Flow

```
Cold Outreach Pipeline:

  [Clearing Engine: no Tier 1 matches or insufficient supply]
      │
      ▼
  [Property DB Query: non-network properties matching buyer requirements]
      │
      ├─► Filter: correct zoning, size range, location
      ├─► Filter: owner contact info available (CoStar)
      ├─► Rank: by match score, exclude previously declined (rate floor check)
      │
      ▼
  [Generate outreach message]
      │
      ├─► Personalized with: property address, estimated rate, buyer
      │   requirement summary (anonymized), projected monthly income
      │
      ▼
  [Send via SMS (primary) or Email (fallback)]
      │
      ├─► "We have a buyer for space at [address]. Est. rate: $X.XX/sqft.
      │    Monthly income: $X,XXX. Interested? Reply YES with your rate."
      │
      ▼
  [Response Handler]
      │
      ├── YES + rate → Fast-track activation
      │     ├── Confirm 2-3 details via text (space, restrictions, start date)
      │     ├── If rate within buyer budget → present to buyer
      │     ├── If rate above buyer budget → store rate floor, notify if future match
      │     └── Supplier enters network as network_ready
      │
      ├── Counter rate → Store as rate floor, evaluate against buyer budget
      │
      ├── Not interested → Tag property, reduce future ping frequency
      │
      └── No response (48hrs) → Mark as unresponsive, retry once after 7 days
```

### 11.2 Outreach Rate Limits

To protect supplier goodwill and WEx reputation:

- Max 1 outreach per property per 30 days (unless supplier responded positively before)
- Max 3 outreach attempts per property lifetime before requiring manual review
- Track response rates by channel (SMS vs email) — use higher-performing channel
- If a market has < 20% cold outreach response rate, flag for manual review of messaging

---

## 12. Broker Integration

### 12.1 Current State (Phase 1)

Brokers operate as referral partners. Low-lift integration:

- Broker contacts WEx (email/phone) with buyer requirements
- WEx ops team enters requirements into buyer flow on broker's behalf
- Deal closes through standard flow
- Broker receives referral fee: fixed % of WEx's spread on that deal
- Attribution tracked via `broker_id` on BuyerRequirement and Deal schemas

### 12.2 Future State (Phase 2, If Volume Warrants)

Self-service broker portal:

```
Broker Portal:
  ├── Submit buyer briefs (same as buyer flow, on behalf of client)
  ├── Track deal pipeline (submitted → matched → touring → closed)
  ├── View earnings per deal (transparent: "WEx spread was $X, your share: $Y")
  ├── Manage multiple active clients
  └── Performance dashboard (deals submitted, close rate, total earnings)
```

Build only if broker volume exceeds 20% of total deals or specific broker partners request it.

---

## 13. Key Technical Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **CoStar API dependency** | If CoStar changes terms or pricing, property data pipeline breaks | Accelerate proprietary database build. Diversify data sources (county records, web scraping). Cache aggressively. |
| **SMS deliverability** | Carrier filtering could block outreach messages as spam | Register for A2P 10DLC. Use branded sender. Keep message content transactional, not promotional. Monitor delivery rates. |
| **Matching quality in thin markets** | Few suppliers in some metros = poor buyer experience | Show honest "sourcing in progress" state rather than weak matches. Use cold outreach to fill gaps. Focus initial growth on 5-10 dense metros. |
| **Spread exposure at tour** | Buyer and supplier compare pricing face-to-face | Pre-load narrative in onboarding materials. Position as "all-in rate includes platform services." Consider adjusting spread display if data shows it's causing deal failures. |
| **Multi-agent AI inconsistency** | Different agents give contradictory info | Polisher agent as mandatory final gate. Shared conversation context. Regular prompt tuning. Human review of flagged conversations. |
| **Stripe Connect complexity** | Onboarding friction for suppliers unfamiliar with Stripe | Use Stripe Express accounts (simplest onboarding). Provide step-by-step guide. Offer phone support for supplier bank setup. |

---

## 14. Build Prioritization

### Phase 1: Core Loop (Weeks 1-8)

The minimum to run the new clearinghouse model:

1. **EarnCheck → Network Activation** (supplier acquisition funnel) — partially built
2. **Buyer 5-step flow → Results page** (demand capture) — partially built
3. **Clearing Engine v1** (Tier 1 matching + Tier 2 manual dispatch)
4. **Tour booking + WEx Guarantee agreement**
5. **Close sequence** (DocuSign + Stripe)

### Phase 2: Intelligence (Weeks 9-16)

Make the system smarter:

6. **Automated Tier 2 dispatch** (cold outreach pipeline)
7. **Multi-agent SMS channel** (AI + human + polisher)
8. **Property memory** (Q&A store, rejection reasons)
9. **Pricing engine v1** (market-aware spread calculation)
10. **Analytics dashboard** (funnel metrics, deal tracking)

### Phase 3: Scale (Weeks 17-24)

Optimize and expand:

11. **Dynamic pricing** (A/B tested spread optimization)
12. **Browse Collection** (searchable property grid with controlled visibility)
13. **Broker portal** (if volume warrants)
14. **Proprietary property database** (reduce CoStar dependency)
15. **Returning buyer experience** (saved searches, past deal memory)

---

*This document covers the technical architecture required to support the complete WEx user journey as defined in the journey map. It should be reviewed alongside the WEx Complete User Journey Map document for full product context.*

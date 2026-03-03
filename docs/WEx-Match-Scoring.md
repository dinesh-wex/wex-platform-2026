# WEx Match Scoring System

> **TL;DR** — Every warehouse match gets a score from 0–100 computed across 6 weighted dimensions.
> Five are instant deterministic math (Layer 1), one is LLM-evaluated (Layer 2).
> All three channels (Web, SMS, Voice) use the exact same scorer.

---

## How It Works — At a Glance

```
  COMPOSITE SCORE (0–100)
  ═══════════════════════════════════════════════════════

  Layer 1 — Deterministic (instant, no LLM)
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │  Location   ████████████████████████░░░░░░░░  25%   │
  │  Size       ████████████████████░░░░░░░░░░░░  20%   │
  │  Use Type   ████████████████████░░░░░░░░░░░░  20%   │
  │  Timing     ██████████░░░░░░░░░░░░░░░░░░░░░░  10%   │
  │  Value      ██████████░░░░░░░░░░░░░░░░░░░░░░  10%   │
  │                                                     │
  └─────────────────────────────────────────────────────┘

  Layer 2 — LLM (async, after Layer 1)
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │  Feature    ███████████████░░░░░░░░░░░░░░░░░  15%   │
  │                                                     │
  └─────────────────────────────────────────────────────┘
```

### Composite Formula

```
composite = location  × 0.25
          + size      × 0.20
          + use_type  × 0.20
          + feature   × 0.15
          + timing    × 0.10
          + value     × 0.10
```

Each dimension scores **0–100**. The weighted composite is also **0–100**.

---

## Channel Convergence

All three buyer intake channels feed into the same scoring path:

```
  ┌───────────┐   ┌───────────┐   ┌───────────┐
  │    Web     │   │    SMS    │   │   Voice   │
  │  (6-step  │   │ (Aircall  │   │  (Vapi    │
  │   intake)  │   │  + Agent) │   │  handler) │
  └─────┬─────┘   └─────┬─────┘   └─────┬─────┘
        │               │               │
        └───────────────┼───────────────┘
                        ▼
               ┌─────────────────┐
               │   BuyerNeed     │
               │   (DB record)   │
               └────────┬────────┘
                        ▼
               ┌─────────────────┐
               │ ClearingEngine  │
               │ _run_clearing() │
               └────────┬────────┘
                        │
              ┌─────────┴──────────┐
              ▼                    ▼
     ┌────────────────┐  ┌────────────────┐
     │   Tier 1       │  │   Tier 2       │
     │  In-network    │  │  Off-network   │
     │  (Property DB) │  │  (DLA search)  │
     └───────┬────────┘  └───────┬────────┘
             │                   │
             └────────┬──────────┘
                      ▼
          ┌───────────────────────┐
          │ compute_composite_    │  ← Layer 1
          │ score()               │     (deterministic)
          └───────────┬───────────┘
                      ▼
          ┌───────────────────────┐
          │ LLM Clearing Agent    │  ← Layer 2
          │ recompute_with_       │     (feature eval)
          │ feature_score()       │
          └───────────────────────┘
```

---

## Dimension Details

### 1. Location (25%)

> How close is the warehouse to where the buyer wants to be?

**Method**: Haversine distance with continuous linear decay.

```
  Score
  100 ┤●━━━━━━━━━━━━━━━━╲
      │                   ╲
   75 ┤                    ╲
      │                     ╲
   50 ┤· · · · · · · · · · · ╲· · · · · · · · · · · NEUTRAL (no coords)
      │                       ╲
   25 ┤                        ╲
      │                         ╲
    0 ┤                          ●━━━━━━━━━━━━━━━━━
      └──────────┬──────────┬──────────────────────
              radius      KNN cap (100mi)
                     Distance →
```

| Rule | Detail |
|:-----|:-------|
| **Inside radius** | `100 × (1 − distance / radius)` |
| **Beyond radius** | `100 × (1 − distance / 100)` — KNN overflow, penalized heavily |
| **City match** | +10 bonus if exact city match (capped at 100) |
| **Missing coords** | 50 (neutral) |

---

### 2. Size (20%)

> Does the warehouse have the right amount of space?

**Method**: Clamp buyer target into warehouse's min/max range, compute satisfaction ratio.

```
  Score
  100 ┤          ●━━━━━━━━━━━●
      │        ╱               ╲
   75 ┤      ╱                   ╲
      │    ╱                       ╲
   50 ┤· ╱· · · · · · · · · · · · · ╲· · · · · · ·  NEUTRAL (no target)
      │╱                               ╲
   25 ┤                                   ╲
      │                                     ╲
    0 ┤●                                      ╲━━━●
      └────┬─────┬───────────┬─────┬──────────────
         0.48×  0.8×      1.2×   2.2×
                   Ratio (fit / target) →
```

| Ratio | Score | Interpretation |
|:------|:------|:---------------|
| 0.8× – 1.2× | **100** | Sweet spot — perfect fit |
| < 0.8× | Drops at **250 pts/unit** | Too small, steep penalty |
| > 1.2× | Drops at **100 pts/unit** | Too large, gentler penalty |
| No target | **50** | Neutral |

---

### 3. Use Type (20%)

> Is the warehouse built for what the buyer needs to do?

**Method**: Compatibility matrix between warehouse `activity_tier` and buyer `use_type`.

```
  Warehouse Tier          Can Serve
  ─────────────────────────────────────────────────
  cold_storage         →  food, pharma, general, storage
  food_grade           →  food, general, storage
  storage_light_assembly → light mfg, general, storage
  storage_office       →  office + storage needs
  storage_only         →  basic dry storage only
```

| Match Quality | Score Range | Example |
|:--------------|:------------|:--------|
| Exact / superset | **80–100** | cold_storage facility for food_grade need |
| Partial overlap | **40–70** | storage_office for light assembly |
| Dangerous mismatch | **0–30** | storage_only for food_grade need |

Callout messages are returned alongside the score to explain mismatches.

---

### 4. Timing (10%)

> Can the warehouse be ready when the buyer needs it?

**Method**: Continuous linear decay — loses 1 point per day late, floored at 10.

```
  Score
  100 ┤●━━━━━━━━━━╲
      │             ╲
   70 ┤· · · · · · · ·╲· · · · · · · · · · · · · ·  30 days late
      │                 ╲
   40 ┤· · · · · · · · · ·╲· · · · · · · · · · · ·  60 days late
      │                     ╲
   10 ┤· · · · · · · · · · · ·●━━━━━━━━━━━━━━━━━━━  90+ days (floor)
      │
    0 ┤
      └─────┬──────┬──────┬──────┬─────────────────
           0d    30d    60d    90d
                  Days Late →
```

| Scenario | Score |
|:---------|:------|
| On time or early | **100** |
| 1 day late | **99** |
| 30 days late | **70** |
| 60 days late | **40** |
| 90+ days late | **10** (floor) |
| Unknown / "ASAP" / null | **100** (no friction) |

---

### 5. Value (10%) — Market Competitiveness

> Is the supplier pricing this warehouse fairly for its type?

**Method**: Index + Coefficient model using zip-level NNN market rates.

#### How It Works

```
  Step 1                    Step 2                     Step 3
  ┌──────────────┐         ┌───────────────┐         ┌──────────────┐
  │ MarketRate   │         │ Tier          │         │ Compare      │
  │ Cache        │────────▶│ Multiplier    │────────▶│ supplier     │
  │              │         │               │         │ vs adjusted  │
  │ NNN avg for  │    ×    │ Facility type │    =    │ market avg   │
  │ this zipcode │         │ coefficient   │         │              │
  └──────────────┘         └───────────────┘         └──────────────┘
```

#### Tier Multipliers

These adjust the generic dry-warehouse baseline to an apples-to-apples comparison:

```
  storage_only             ██████████  1.0×   Baseline
  storage_office           ████████████  1.15×  +15% office buildout
  storage_light_assembly   █████████████  1.3×   +30% power/ventilation
  food_grade               ██████████████████  1.8×   +80% sanitation/certs
  cold_storage             █████████████████████████  2.5×   +150% refrigeration
```

#### Scoring Curve

```
  Score
  100 ┤●━━━━━━━━━╲
      │            ╲
   70 ┤· · · · · · · ●· · · · · · · · · · · · · ·  At market average
      │                ╲
   50 ┤· · · · · · · · · ●· · · · · · · · · · · ·  20% above market
      │                    ╲
      │                      ╲
    0 ┤· · · · · · · · · · · · ●━━━━━━━━━━━━━━━━━  70%+ above market
      └────┬────┬────┬────┬────┬───────────────────
         -30%  -15%   0%  +20% +70%
              Deviation from adjusted market avg →
```

| Scenario | Score | Why |
|:---------|:------|:----|
| 30% below market | **100** | Great deal (capped) |
| At adjusted market avg | **70** | Fair market price |
| 20% above market | **50** | Getting pricey |
| 70%+ above market | **0** | Way overpriced (floored) |
| No supplier rate | **50** | Neutral — no data |
| No market data for zip | **50** | Neutral — no data |

> **Lease type note**: Both `supplier_rate_per_sqft` and MarketRateCache NNN rates are **base rent**
> (excludes taxes, insurance, maintenance). The WEx buyer markup (x1.20 x 1.06) is intentionally
> excluded — it's a constant applied to all properties and doesn't change relative competitiveness.

---

### 6. Feature (15%) — LLM Layer 2

> Do the warehouse's physical features match the buyer's specific requirements?

**Method**: LLM (Clearing Agent) evaluates free-text buyer requirements against property attributes.

```
  Layer 1 runs instantly               Layer 2 runs async
  ┌──────────────────────┐            ┌──────────────────────┐
  │ feature_score = 50   │───────────▶│ LLM evaluates:       │
  │ (placeholder)        │            │ - clear height        │
  │                      │            │ - dock doors          │
  │                      │            │ - certifications      │
  │                      │            │ - special needs       │
  │                      │            │                       │
  │                      │            │ feature_score = 0-100 │
  └──────────────────────┘            └──────────┬───────────┘
                                                 │
                                      recompute_with_feature_score()
                                      → new composite
```

---

## Relevant Files

```
  backend/src/wex_platform/
  ├── services/
  │   ├── match_scorer.py ············ Core scorer — weights, formulas, composite
  │   ├── clearing_engine.py ·········· Pipeline orchestrator — market rate fetch, matching
  │   └── use_type_compat.py ·········· Use type compatibility matrix
  │
  ├── agents/
  │   ├── clearing_agent.py ··········· LLM Layer 2 — feature evaluation
  │   └── prompts/
  │       └── market_rate.py ·········· Gemini prompt for NNN rates by zip
  │
  └── domain/
      └── models.py ··················· MarketRateCache, PropertyKnowledge, PropertyListing

  backend/tests/
  └── test_match_scorer.py ············ 41 unit tests — all dimensions + edge cases
```

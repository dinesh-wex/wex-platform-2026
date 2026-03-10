# WEx Platform API Test Plan

Comprehensive test plan for verifying all API endpoints and end-to-end flows after GCP deployment. Tests are designed to run against the live Cloud Run backend via `curl` / Python scripts.

---

## Prerequisites

```bash
# Set your base URL (Cloud Run backend or Load Balancer)
export BASE_URL="https://warehouseexchange.com"
# or direct Cloud Run URL:
# export BASE_URL="https://wex-backend-xxxxx-uc.a.run.app"

# Admin password (from Secret Manager)
export ADMIN_PASSWORD="wex2026"

# Aircall webhook token (for simulating inbound SMS)
export AIRCALL_WEBHOOK_TOKEN="your-webhook-token"

# Vapi server secret (for simulating voice webhooks)
export VAPI_SERVER_SECRET="your-vapi-secret"
```

---

## Phase 1: Infrastructure Health

### 1.1 Health Check
```bash
curl -s "$BASE_URL/health" | python -m json.tool
# Expected: {"status": "ok"}
```

### 1.2 Database Connectivity (via seed endpoint)
```bash
curl -s -X POST "$BASE_URL/api/dev/seed-engagements" | python -m json.tool
# Expected: 200 with created test data (users, warehouses, engagements)
# This confirms: Cloud SQL connection, table creation, write operations
```

---

## Phase 2: Auth Endpoints

### 2.1 Signup (Supplier)
```bash
curl -s -X POST "$BASE_URL/api/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test-supplier@example.com",
    "password": "TestPass123!",
    "name": "Test Supplier",
    "role": "supplier",
    "company": "Test Warehouses Inc",
    "phone": "+15551000001"
  }' | python -m json.tool
# Expected: 200 with {token, user: {id, email, role}}
# Save: export SUPPLIER_TOKEN="<token>"
```

### 2.2 Signup (Buyer)
```bash
curl -s -X POST "$BASE_URL/api/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test-buyer@example.com",
    "password": "TestPass123!",
    "name": "Test Buyer",
    "role": "buyer",
    "company": "Test Logistics Co",
    "phone": "+15552000001"
  }' | python -m json.tool
# Save: export BUYER_TOKEN="<token>"
```

### 2.3 Login
```bash
curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "test-supplier@example.com", "password": "TestPass123!"}' \
  | python -m json.tool
# Expected: 200 with {token, user}
```

### 2.4 Get Current User
```bash
curl -s "$BASE_URL/api/auth/me" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" | python -m json.tool
# Expected: 200 with user profile
```

### 2.5 Update Profile
```bash
curl -s -X PATCH "$BASE_URL/api/auth/profile" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Updated Supplier Name"}' | python -m json.tool
# Expected: 200 with updated profile
```

### 2.6 Auth Failure Cases
```bash
# Bad credentials
curl -s -X POST "$BASE_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "test-supplier@example.com", "password": "wrong"}' \
  -w "\nHTTP_STATUS: %{http_code}\n"
# Expected: 401

# No token
curl -s "$BASE_URL/api/auth/me" -w "\nHTTP_STATUS: %{http_code}\n"
# Expected: 401

# Invalid token
curl -s "$BASE_URL/api/auth/me" \
  -H "Authorization: Bearer invalid-token" -w "\nHTTP_STATUS: %{http_code}\n"
# Expected: 401
```

---

## Phase 3: Browse & Search (Public, No Auth)

### 3.1 Browse Listings
```bash
curl -s "$BASE_URL/api/browse/listings?page=1&per_page=5" | python -m json.tool
# Expected: paginated listing grid (location, sqft ranges, rate ranges)
```

### 3.2 Browse with Filters
```bash
curl -s "$BASE_URL/api/browse/listings?city=Dallas&min_sqft=5000&max_sqft=50000&use_type=storage" \
  | python -m json.tool
```

### 3.3 Location Autocomplete
```bash
curl -s "$BASE_URL/api/browse/locations?q=Dal" | python -m json.tool
# Expected: city/state suggestions matching "Dal"
```

### 3.4 Anonymous Search
```bash
curl -s -X POST "$BASE_URL/api/search" \
  -H "Content-Type: application/json" \
  -d '{
    "city": "Dallas",
    "state": "TX",
    "size_sqft": 10000,
    "use_type": "storage",
    "duration_months": 12
  }' | python -m json.tool
# Expected: {session_token, matches: [...]}
# Save: export SEARCH_TOKEN="<session_token>"
```

### 3.5 Retrieve Search Session
```bash
curl -s "$BASE_URL/api/search/session/$SEARCH_TOKEN" | python -m json.tool
# Expected: cached search results
```

### 3.6 NLP Text Extraction
```bash
curl -s -X POST "$BASE_URL/api/search/extract" \
  -H "Content-Type: application/json" \
  -d '{"text": "I need about 15000 sqft of warehouse space in Houston for ecommerce fulfillment starting next month"}' \
  | python -m json.tool
# Expected: extracted {city, state, size_sqft, use_type, timing}
```

### 3.7 Quick Match Count
```bash
curl -s "$BASE_URL/api/clearing/match-count?location=Dallas,TX&min_sqft=5000&max_sqft=20000" \
  | python -m json.tool
# Expected: {count: N}
```

---

## Phase 4: Buyer Flow

### 4.1 Register Buyer
```bash
curl -s -X POST "$BASE_URL/api/buyer/register" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "E2E Test Buyer",
    "company": "Test Logistics",
    "email": "e2e-buyer@example.com",
    "phone": "+15553000001"
  }' | python -m json.tool
# Save: export BUYER_ID="<buyer_id>"
```

### 4.2 Create Buyer Need
```bash
curl -s -X POST "$BASE_URL/api/buyer/need" \
  -H "Content-Type: application/json" \
  -d "{
    \"buyer_id\": \"$BUYER_ID\",
    \"city\": \"Dallas\",
    \"state\": \"TX\",
    \"min_sqft\": 8000,
    \"max_sqft\": 15000,
    \"use_type\": \"storage\",
    \"duration_months\": 12,
    \"max_budget_per_sqft\": 1.50
  }" | python -m json.tool
# Save: export NEED_ID="<need_id>"
```

### 4.3 Get Buyer Needs
```bash
curl -s "$BASE_URL/api/buyer/$BUYER_ID/needs" | python -m json.tool
```

### 4.4 Buyer Intake Chat
```bash
# Start conversation
curl -s -X POST "$BASE_URL/api/buyer/need/$NEED_ID/chat/start" | python -m json.tool

# Send message
curl -s -X POST "$BASE_URL/api/buyer/need/$NEED_ID/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "I need space for storing electronics with climate control"}' \
  | python -m json.tool
```

### 4.5 Get Cleared Options
```bash
curl -s "$BASE_URL/api/buyer/need/$NEED_ID/options" | python -m json.tool
# Expected: triggers clearing engine, returns matches
# Save: export MATCH_ID="<first_match_id>"
```

### 4.6 Accept Match
```bash
curl -s -X POST "$BASE_URL/api/buyer/need/$NEED_ID/accept" \
  -H "Content-Type: application/json" \
  -d "{\"match_id\": \"$MATCH_ID\", \"deal_type\": \"standard\"}" \
  | python -m json.tool
# Save: export DEAL_ID="<deal_id>"
```

### 4.7 Sign Guarantee
```bash
curl -s -X POST "$BASE_URL/api/buyer/deal/$DEAL_ID/guarantee" \
  -H "Content-Type: application/json" \
  -d '{"accepted": true}' | python -m json.tool
# Expected: address revealed
```

### 4.8 Schedule Tour
```bash
curl -s -X POST "$BASE_URL/api/buyer/deal/$DEAL_ID/tour" \
  -H "Content-Type: application/json" \
  -d '{"preferred_date": "2026-03-15", "preferred_time": "10:00", "notes": "Main entrance please"}' \
  | python -m json.tool
```

### 4.9 Tour Outcome
```bash
curl -s -X POST "$BASE_URL/api/buyer/deal/$DEAL_ID/tour-outcome" \
  -H "Content-Type: application/json" \
  -d '{"outcome": "confirmed"}' | python -m json.tool
```

### 4.10 Get Buyer Deals
```bash
curl -s "$BASE_URL/api/buyer/$BUYER_ID/deals" | python -m json.tool
```

---

## Phase 5: Engagement Lifecycle (Full State Machine)

### 5.1 List Engagements
```bash
# As buyer
curl -s "$BASE_URL/api/engagements" \
  -H "Authorization: Bearer $BUYER_TOKEN" | python -m json.tool

# As supplier
curl -s "$BASE_URL/api/engagements" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" | python -m json.tool
```

### 5.2 Get Single Engagement
```bash
curl -s "$BASE_URL/api/engagements/$ENGAGEMENT_ID" \
  -H "Authorization: Bearer $BUYER_TOKEN" | python -m json.tool
# Verify: buyer view hides supplier_rate_sqft
```

### 5.3 Deal Ping Accept (Supplier)
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/deal-ping/accept" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"terms_accepted": true}' | python -m json.tool
# Expected: status -> DEAL_PING_ACCEPTED
```

### 5.4 Deal Ping with Counter Rate
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/deal-ping/accept" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"terms_accepted": true, "counter_rate": 1.25}' | python -m json.tool
```

### 5.5 Deal Ping Decline
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/deal-ping/decline" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Rate too low"}' | python -m json.tool
# Expected: status -> DEAL_PING_DECLINED
```

### 5.6 Accept Match (Buyer, Tour Path)
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/accept" \
  -H "Content-Type: application/json" \
  -d '{"path": "tour"}' | python -m json.tool
# Expected: status -> BUYER_ACCEPTED
```

### 5.7 Sign Guarantee
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/guarantee/sign" \
  | python -m json.tool
# Expected: status -> ADDRESS_REVEALED (auto-transition from GUARANTEE_SIGNED)
# Verify: hold_expires_at set to +72 hours
```

### 5.8 Request Tour
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/tour/request" \
  -H "Content-Type: application/json" \
  -d '{"preferred_date": "2026-03-15", "preferred_time": "14:00", "tour_notes": "Loading dock access"}' \
  | python -m json.tool
# Expected: status -> TOUR_REQUESTED
```

### 5.9 Confirm Tour (Supplier)
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/tour/confirm" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"scheduled_date": "2026-03-15T14:00:00"}' | python -m json.tool
# Expected: status -> TOUR_CONFIRMED
```

### 5.10 Reschedule Tour
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/tour/reschedule" \
  -H "Content-Type: application/json" \
  -d '{"new_date": "2026-03-17T10:00:00", "reason": "Conflict on original date"}' \
  | python -m json.tool
# Expected: status -> TOUR_RESCHEDULED, hold auto-extended if needed
```

### 5.11 Tour Outcome (Confirmed)
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/tour/outcome" \
  -H "Content-Type: application/json" \
  -d '{"outcome": "confirmed"}' | python -m json.tool
# Expected: status -> BUYER_CONFIRMED -> AGREEMENT_SENT (auto-transition)
```

### 5.12 Tour Outcome (Passed)
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/tour/outcome" \
  -H "Content-Type: application/json" \
  -d '{"outcome": "passed", "reason": "Space too small"}' | python -m json.tool
# Expected: status -> DECLINED_BY_BUYER, sqft released
```

### 5.13 Instant Book Path (Alternative to Tour)
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/instant-book" \
  | python -m json.tool
# Expected: INSTANT_BOOK_REQUESTED -> BUYER_CONFIRMED -> AGREEMENT_SENT (auto)
```

### 5.14 Hold Extension
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/hold/extend" \
  -H "Authorization: Bearer $BUYER_TOKEN" | python -m json.tool
# Expected: hold_expires_at += 24 hours (one-time only)
```

### 5.15 Get Agreement
```bash
curl -s "$BASE_URL/api/engagements/$ENGAGEMENT_ID/agreement" \
  -H "Authorization: Bearer $BUYER_TOKEN" | python -m json.tool
# Verify: buyer sees buyer_rate only, not supplier_rate
```

### 5.16 Sign Agreement (Buyer)
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/agreement/sign" \
  -H "Content-Type: application/json" \
  -d '{"role": "buyer"}' | python -m json.tool
```

### 5.17 Sign Agreement (Supplier)
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/agreement/sign" \
  -H "Content-Type: application/json" \
  -d '{"role": "supplier"}' | python -m json.tool
# Expected: status -> AGREEMENT_SIGNED -> ONBOARDING (auto)
```

### 5.18 Onboarding Steps
```bash
# Insurance
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/onboarding/insurance" \
  -H "Content-Type: application/json" \
  -d '{"document_url": "https://example.com/insurance.pdf"}' | python -m json.tool

# Company docs
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/onboarding/company-docs" \
  -H "Content-Type: application/json" \
  -d '{"document_url": "https://example.com/docs.pdf"}' | python -m json.tool

# Payment method (triggers ACTIVE if all 3 complete)
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/onboarding/payment" \
  -H "Content-Type: application/json" \
  -d '{"payment_method_type": "ach", "last_four": "4242"}' | python -m json.tool
# Expected: status -> ACTIVE
```

### 5.19 Get Onboarding Status
```bash
curl -s "$BASE_URL/api/engagements/$ENGAGEMENT_ID/onboarding" | python -m json.tool
# Expected: {insurance_uploaded, company_docs_uploaded, payment_method_added, all_complete}
```

### 5.20 Timeline / Audit Trail
```bash
curl -s "$BASE_URL/api/engagements/$ENGAGEMENT_ID/timeline" | python -m json.tool
# Expected: ordered list of EngagementEvents with from_status -> to_status
```

### 5.21 Payments
```bash
curl -s "$BASE_URL/api/engagements/$ENGAGEMENT_ID/payments" \
  -H "Authorization: Bearer $BUYER_TOKEN" | python -m json.tool
```

### 5.22 Decline
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/decline" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Found alternative space"}' | python -m json.tool
```

### 5.23 Cancel (Admin Only)
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/cancel" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Compliance issue"}' | python -m json.tool
# Expected: 200 for admin, 403 for non-admin
```

---

## Phase 6: Supplier Dashboard

### 6.1 Portfolio Summary
```bash
curl -s "$BASE_URL/api/supplier/portfolio/summary" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" | python -m json.tool
# Expected: {total_income, avg_rate, occupancy_pct, rented_sqft, available_sqft}
```

### 6.2 List Properties
```bash
curl -s "$BASE_URL/api/supplier/properties" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" | python -m json.tool
```

### 6.3 Property Detail
```bash
curl -s "$BASE_URL/api/supplier/properties/$PROPERTY_ID" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" | python -m json.tool
```

### 6.4 Update Property
```bash
curl -s -X PATCH "$BASE_URL/api/supplier/properties/$PROPERTY_ID" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"pricing_mode": "auto", "tour_required": false}' | python -m json.tool
```

### 6.5 Supplier Engagements with Action Items
```bash
curl -s "$BASE_URL/api/supplier/engagements" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" | python -m json.tool
# Expected: list with action_items (deal_ping, tour_confirm, etc.)
```

### 6.6 Supplier Payments
```bash
curl -s "$BASE_URL/api/supplier/payments" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" | python -m json.tool

curl -s "$BASE_URL/api/supplier/payments/summary" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" | python -m json.tool
```

---

## Phase 7: Admin Endpoints

### 7.1 Network Overview
```bash
curl -s "$BASE_URL/api/admin/overview" | python -m json.tool
# Expected: {warehouses, buyers, deals, gmv, spread}
```

### 7.2 All Warehouses
```bash
curl -s "$BASE_URL/api/admin/warehouses" | python -m json.tool
```

### 7.3 All Deals
```bash
curl -s "$BASE_URL/api/admin/deals" | python -m json.tool
curl -s "$BASE_URL/api/admin/deals?status=active" | python -m json.tool
```

### 7.4 Single Deal Detail
```bash
curl -s "$BASE_URL/api/admin/deals/$DEAL_ID" | python -m json.tool
# Expected: full economics (buyer rate, supplier rate, WEx spread)
```

### 7.5 Agent Activity
```bash
curl -s "$BASE_URL/api/admin/agents" | python -m json.tool
```

### 7.6 Ledger
```bash
curl -s "$BASE_URL/api/admin/ledger" | python -m json.tool
# Expected: buyer payments in, supplier payments out, WEx revenue
```

### 7.7 Clearing Stats
```bash
curl -s "$BASE_URL/api/admin/clearing/stats" | python -m json.tool
```

### 7.8 Admin Engagement Management
```bash
# List with filters
curl -s "$BASE_URL/api/admin/engagements?status=active" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | python -m json.tool

# Override status
curl -s -X PATCH "$BASE_URL/api/admin/engagements/$ENGAGEMENT_ID/status" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"new_status": "cancelled", "reason": "Test override"}' | python -m json.tool

# Add note
curl -s -X POST "$BASE_URL/api/admin/engagements/$ENGAGEMENT_ID/note" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"note": "Admin test note"}' | python -m json.tool

# Extend deadline
curl -s -X POST "$BASE_URL/api/admin/engagements/$ENGAGEMENT_ID/extend-deadline" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"field": "deal_ping_expires_at", "extend_hours": 4}' | python -m json.tool
```

---

## Phase 8: Clearing Engine

### 8.1 Trigger Clearing
```bash
curl -s -X POST "$BASE_URL/api/clearing/match" \
  -H "Content-Type: application/json" \
  -d "{\"buyer_need_id\": \"$NEED_ID\"}" | python -m json.tool
# Expected: {tier1_matches: [...], tier2_matches: [...]}
```

### 8.2 Match Detail
```bash
curl -s "$BASE_URL/api/clearing/match/$MATCH_ID" | python -m json.tool
# Expected: detailed match with scoring breakdown
```

---

## Phase 9: DLA (Demand-Led Activation)

### 9.1 Resolve DLA Token
```bash
curl -s "$BASE_URL/api/dla/token/$DLA_TOKEN" | python -m json.tool
# Expected: property data + anonymized buyer requirements + suggested rate
```

### 9.2 Submit Rate Decision
```bash
# Accept suggested rate
curl -s -X POST "$BASE_URL/api/dla/token/$DLA_TOKEN/rate" \
  -H "Content-Type: application/json" \
  -d '{"accepted": true}' | python -m json.tool

# Counter with different rate
curl -s -X POST "$BASE_URL/api/dla/token/$DLA_TOKEN/rate" \
  -H "Content-Type: application/json" \
  -d '{"accepted": false, "proposed_rate": 1.10}' | python -m json.tool
```

### 9.3 Confirm Agreement
```bash
curl -s -X POST "$BASE_URL/api/dla/token/$DLA_TOKEN/confirm" \
  -H "Content-Type: application/json" \
  -d '{"agreement_ref": "ref-123", "available_from": "2026-04-01"}' | python -m json.tool
```

### 9.4 Record Non-Conversion
```bash
curl -s -X POST "$BASE_URL/api/dla/token/$DLA_TOKEN/outcome" \
  -H "Content-Type: application/json" \
  -d '{"outcome": "declined", "reason": "Not interested at this time"}' | python -m json.tool
```

---

## Phase 10: Enrichment

### 10.1 Get Next Question
```bash
curl -s "$BASE_URL/api/enrichment/warehouse/$WAREHOUSE_ID/next" | python -m json.tool
# Expected: next unanswered enrichment question
```

### 10.2 Submit Response
```bash
curl -s -X POST "$BASE_URL/api/enrichment/warehouse/$WAREHOUSE_ID/respond" \
  -H "Content-Type: application/json" \
  -d '{"question_id": "q1", "response": "28 feet"}' | python -m json.tool
```

### 10.3 Completeness Score
```bash
curl -s "$BASE_URL/api/enrichment/warehouse/$WAREHOUSE_ID/completeness" | python -m json.tool
# Expected: {completeness: 0.65, ...}
```

### 10.4 Enrichment History
```bash
curl -s "$BASE_URL/api/enrichment/warehouse/$WAREHOUSE_ID/history" | python -m json.tool
```

---

## Phase 11: Q&A

### 11.1 Submit Question
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/qa" \
  -H "Content-Type: application/json" \
  -d '{"question_text": "Does this warehouse have climate control?"}' | python -m json.tool
# Save: export QUESTION_ID="<question_id>"
```

### 11.2 Get Question Detail
```bash
curl -s "$BASE_URL/api/engagements/$ENGAGEMENT_ID/qa/$QUESTION_ID" | python -m json.tool
# Expected: AI answer + pending supplier answer
```

### 11.3 Supplier Answer
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/qa/$QUESTION_ID/supplier-answer" \
  -H "Content-Type: application/json" \
  -d '{"answer_text": "Yes, we have full HVAC with temperature control between 55-75F"}' \
  | python -m json.tool
```

### 11.4 Admin Force-Answer
```bash
curl -s -X POST "$BASE_URL/api/engagements/$ENGAGEMENT_ID/qa/$QUESTION_ID/admin-answer" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"answer_text": "Confirmed: climate controlled facility"}' | python -m json.tool
```

### 11.5 Q&A History
```bash
curl -s "$BASE_URL/api/engagements/$ENGAGEMENT_ID/qa/history" | python -m json.tool
```

---

## Phase 12: Agreements

### 12.1 Sign Agreement
```bash
curl -s -X POST "$BASE_URL/api/agreements/sign" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type": "network_agreement"}' | python -m json.tool
```

### 12.2 Check Agreement Status
```bash
curl -s "$BASE_URL/api/agreements/status/network_agreement" \
  -H "Authorization: Bearer $SUPPLIER_TOKEN" | python -m json.tool
```

---

## Phase 13: Simulate Inbound SMS (Supplier DLA Reply)

These simulate Aircall webhooks hitting your backend as if a supplier texted back.

### 13.1 Supplier Replies "YES"
```bash
curl -s -X POST "$BASE_URL/api/sms/webhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"event\": \"message.received\",
    \"token\": \"$AIRCALL_WEBHOOK_TOKEN\",
    \"data\": {
      \"message\": {
        \"body\": \"Yes, interested!\",
        \"direction\": \"inbound\",
        \"external_number\": \"+15551000001\",
        \"number\": {
          \"digits\": \"5559999999\"
        }
      }
    }
  }" | python -m json.tool
# Expected: 200, DLAToken.status -> "interested"
```

### 13.2 Supplier Replies with Counter Rate
```bash
curl -s -X POST "$BASE_URL/api/sms/webhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"event\": \"message.received\",
    \"token\": \"$AIRCALL_WEBHOOK_TOKEN\",
    \"data\": {
      \"message\": {
        \"body\": \"I want 1.25/sqft\",
        \"direction\": \"inbound\",
        \"external_number\": \"+15551000001\",
        \"number\": {
          \"digits\": \"5559999999\"
        }
      }
    }
  }" | python -m json.tool
# Expected: 200, DLAToken.status -> "rate_decided", supplier_rate = 1.25
```

### 13.3 Supplier Replies "NO"
```bash
curl -s -X POST "$BASE_URL/api/sms/webhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"event\": \"message.received\",
    \"token\": \"$AIRCALL_WEBHOOK_TOKEN\",
    \"data\": {
      \"message\": {
        \"body\": \"No thanks, not interested\",
        \"direction\": \"inbound\",
        \"external_number\": \"+15551000001\",
        \"number\": {
          \"digits\": \"5559999999\"
        }
      }
    }
  }" | python -m json.tool
# Expected: 200, DLAToken.status -> "declined"
```

### 13.4 Supplier Replies "STOP"
```bash
curl -s -X POST "$BASE_URL/api/sms/webhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"event\": \"message.received\",
    \"token\": \"$AIRCALL_WEBHOOK_TOKEN\",
    \"data\": {
      \"message\": {
        \"body\": \"STOP\",
        \"direction\": \"inbound\",
        \"external_number\": \"+15551000001\",
        \"number\": {
          \"digits\": \"5559999999\"
        }
      }
    }
  }" | python -m json.tool
# Expected: 200, DLAToken.status -> "declined", no reply SMS sent (TCPA compliance)
```

---

## Phase 14: Simulate Inbound SMS (Buyer Conversation)

### 14.1 Buyer Initial Message
```bash
curl -s -X POST "$BASE_URL/api/sms/buyer/webhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"event\": \"message.received\",
    \"token\": \"$AIRCALL_WEBHOOK_TOKEN\",
    \"data\": {
      \"message\": {
        \"body\": \"Hi, I need about 10000 sqft of warehouse space in Dallas\",
        \"direction\": \"inbound\",
        \"external_number\": \"+15553000001\",
        \"number\": {
          \"digits\": \"5558888888\"
        }
      }
    }
  }" | python -m json.tool
# Expected: 200 immediately (processing happens in background)
# Background: Creates SMSConversationState, parses intent, may run clearing
```

### 14.2 Buyer Follow-Up (Show Options)
```bash
curl -s -X POST "$BASE_URL/api/sms/buyer/webhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"event\": \"message.received\",
    \"token\": \"$AIRCALL_WEBHOOK_TOKEN\",
    \"data\": {
      \"message\": {
        \"body\": \"Show me option 2\",
        \"direction\": \"inbound\",
        \"external_number\": \"+15553000001\",
        \"number\": {
          \"digits\": \"5558888888\"
        }
      }
    }
  }" | python -m json.tool
```

### 14.3 Buyer TCPA Opt-Out
```bash
curl -s -X POST "$BASE_URL/api/sms/buyer/webhook" \
  -H "Content-Type: application/json" \
  -d "{
    \"event\": \"message.received\",
    \"token\": \"$AIRCALL_WEBHOOK_TOKEN\",
    \"data\": {
      \"message\": {
        \"body\": \"STOP\",
        \"direction\": \"inbound\",
        \"external_number\": \"+15553000001\",
        \"number\": {
          \"digits\": \"5558888888\"
        }
      }
    }
  }" | python -m json.tool
# Expected: Opt-out recorded, no further messages sent
```

### 14.4 Web Buyer SMS Opt-In
```bash
curl -s -X POST "$BASE_URL/api/sms/optin/" \
  -H "Content-Type: application/json" \
  -d "{
    \"phone\": \"+15554000001\",
    \"name\": \"Web Buyer\",
    \"email\": \"web@example.com\",
    \"buyer_need_id\": \"$NEED_ID\"
  }" | python -m json.tool
```

---

## Phase 15: Simulate Vapi Voice Call (End-to-End)

### 15.1 Assistant Request (Call Starts)

Generate the HMAC signature and send the assistant-request webhook:

```bash
# Build the payload
PAYLOAD='{
  "message": {
    "type": "assistant-request",
    "call": {
      "id": "test-call-001",
      "customer": {
        "number": "+15553000001"
      }
    }
  }
}'

# Generate HMAC-SHA256 signature
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$VAPI_SERVER_SECRET" | awk '{print $2}')

curl -s -X POST "$BASE_URL/api/voice/webhook" \
  -H "Content-Type: application/json" \
  -H "x-vapi-signature: $SIGNATURE" \
  -d "$PAYLOAD" | python -m json.tool
# Expected: full assistant config JSON (model, voice, tools, firstMessage, system prompt)
```

### 15.2 Tool Call: search_properties

```bash
PAYLOAD='{
  "message": {
    "type": "tool-calls",
    "call": {"id": "test-call-001"},
    "artifact": {
      "messages": [
        {"role": "user", "content": "I need about 10000 sqft in Dallas for storage"},
        {"role": "bot", "content": "Let me search for that..."}
      ]
    },
    "toolCallList": [
      {
        "id": "tc-001",
        "function": {
          "name": "search_properties",
          "arguments": "{\"location\": \"Dallas, TX\", \"sqft\": 10000, \"use_type\": \"storage\"}"
        }
      }
    ]
  }
}'

SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$VAPI_SERVER_SECRET" | awk '{print $2}')

curl -s -X POST "$BASE_URL/api/voice/webhook" \
  -H "Content-Type: application/json" \
  -H "x-vapi-signature: $SIGNATURE" \
  -d "$PAYLOAD" | python -m json.tool
# Expected: {results: [{toolCallId: "tc-001", result: "I found 3 options..."}]}
```

### 15.3 Tool Call: lookup_property_details

```bash
PAYLOAD='{
  "message": {
    "type": "tool-calls",
    "call": {"id": "test-call-001"},
    "artifact": {
      "messages": [
        {"role": "user", "content": "Tell me more about option 1"},
        {"role": "bot", "content": "Let me look that up..."}
      ]
    },
    "toolCallList": [
      {
        "id": "tc-002",
        "function": {
          "name": "lookup_property_details",
          "arguments": "{\"option_number\": 1, \"topics\": [\"clear_height_ft\", \"dock_doors\"]}"
        }
      }
    ]
  }
}'

SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$VAPI_SERVER_SECRET" | awk '{print $2}')

curl -s -X POST "$BASE_URL/api/voice/webhook" \
  -H "Content-Type: application/json" \
  -H "x-vapi-signature: $SIGNATURE" \
  -d "$PAYLOAD" | python -m json.tool
# Expected: property detail response or escalation notice
```

### 15.4 Tool Call: send_booking_link

```bash
PAYLOAD='{
  "message": {
    "type": "tool-calls",
    "call": {"id": "test-call-001"},
    "artifact": {
      "messages": [
        {"role": "user", "content": "I want to book option 1"},
        {"role": "bot", "content": "Setting that up for you..."}
      ]
    },
    "toolCallList": [
      {
        "id": "tc-003",
        "function": {
          "name": "send_booking_link",
          "arguments": "{\"option_number\": 1, \"buyer_name\": \"Test Buyer\", \"buyer_email\": \"test@example.com\"}"
        }
      }
    ]
  }
}'

SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$VAPI_SERVER_SECRET" | awk '{print $2}')

curl -s -X POST "$BASE_URL/api/voice/webhook" \
  -H "Content-Type: application/json" \
  -H "x-vapi-signature: $SIGNATURE" \
  -d "$PAYLOAD" | python -m json.tool
# Expected: confirmation text, engagement created, guarantee token queued
```

### 15.5 End-of-Call Report

```bash
PAYLOAD='{
  "message": {
    "type": "end-of-call-report",
    "call": {
      "id": "test-call-001",
      "recordingUrl": "https://example.com/recording.mp3"
    },
    "durationSeconds": 245,
    "summary": "Buyer searched for 10k sqft in Dallas, interested in option 1, booking link sent",
    "transcript": [
      {"role": "user", "content": "I need warehouse space in Dallas"},
      {"role": "bot", "content": "I found 3 options for you..."},
      {"role": "user", "content": "I want to book option 1"},
      {"role": "bot", "content": "Done! Ill text you a link."}
    ]
  }
}'

SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$VAPI_SERVER_SECRET" | awk '{print $2}')

curl -s -X POST "$BASE_URL/api/voice/webhook" \
  -H "Content-Type: application/json" \
  -H "x-vapi-signature: $SIGNATURE" \
  -d "$PAYLOAD" | python -m json.tool
# Expected: 200, call state updated, follow-up SMS sent, escalation emails sent
```

---

## Phase 16: SMS Guarantee Signing (Mobile Web)

### 16.1 View Guarantee Page
```bash
curl -s "$BASE_URL/sms/guarantee/$GUARANTEE_TOKEN" -w "\nHTTP_STATUS: %{http_code}\n"
# Expected: 200, HTML page with guarantee terms
```

### 16.2 Sign Guarantee
```bash
curl -s -X POST "$BASE_URL/sms/guarantee/$GUARANTEE_TOKEN/sign" \
  -H "Content-Type: application/json" \
  -d '{"signer_name": "Test Buyer", "signer_email": "test@example.com"}' \
  | python -m json.tool
# Expected: guarantee recorded, engagement status updated
```

---

## Phase 17: Escalation Reply Tool (Ops)

### 17.1 View Reply Form
```bash
curl -s "$BASE_URL/api/sms/internal/form/$THREAD_ID?token=$ADMIN_PASSWORD" \
  -w "\nHTTP_STATUS: %{http_code}\n"
# Expected: 200, HTML form
```

### 17.2 Get Thread Details
```bash
curl -s "$BASE_URL/api/sms/internal/reply/$THREAD_ID" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool
```

### 17.3 Submit Reply
```bash
curl -s -X POST "$BASE_URL/api/sms/internal/reply/$THREAD_ID" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"answer": "The clear height is 32 feet", "answered_by": "ops@warehouseexchange.com"}' \
  | python -m json.tool
# Expected: answer polished via LLM, SMS sent to buyer, thread status -> "answered"
```

---

## Phase 18: Internal Scheduler Jobs (Cloud Scheduler Simulation)

Test each scheduled job endpoint. These would normally be triggered by Cloud Scheduler with OIDC auth.

```bash
# Hold monitor
curl -s -X POST "$BASE_URL/api/internal/scheduler/hold-monitor" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool

# SMS tick
curl -s -X POST "$BASE_URL/api/internal/scheduler/sms-tick" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool

# Deal ping deadlines
curl -s -X POST "$BASE_URL/api/internal/scheduler/deal-ping-deadlines" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool

# General deadlines
curl -s -X POST "$BASE_URL/api/internal/scheduler/deadlines" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool

# Tour reminders
curl -s -X POST "$BASE_URL/api/internal/scheduler/tour-reminders" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool

# Post-tour follow-up
curl -s -X POST "$BASE_URL/api/internal/scheduler/post-tour-followup" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool

# Q&A deadline
curl -s -X POST "$BASE_URL/api/internal/scheduler/qa-deadline" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool

# Payment records
curl -s -X POST "$BASE_URL/api/internal/scheduler/payment-records" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool

# Payment reminders
curl -s -X POST "$BASE_URL/api/internal/scheduler/payment-reminders" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool

# Stale engagements
curl -s -X POST "$BASE_URL/api/internal/scheduler/stale-engagements" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool

# Auto-activate leases
curl -s -X POST "$BASE_URL/api/internal/scheduler/auto-activate" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool

# Renewal prompts
curl -s -X POST "$BASE_URL/api/internal/scheduler/renewal-prompts" \
  -H "X-Internal-Token: $ADMIN_PASSWORD" | python -m json.tool
```

---

## Phase 19: WebSocket Connections

### 19.1 Admin WebSocket
```bash
# Using websocat (install: cargo install websocat)
websocat "wss://warehouseexchange.com/ws/admin"
# Expected: connected, receives real-time events (deal_update, match_created, agent_activity)
# Type a message to test ping/pong keepalive
```

### 19.2 Activation Agent WebSocket
```bash
websocat "wss://warehouseexchange.com/ws/activation/$WAREHOUSE_ID"
# Expected: connected, can send messages for 5-step activation chat
# Send: {"message": "Hello, I want to activate my warehouse"}
```

---

## Phase 20: End-to-End Flows

### E2E Flow 1: Full Deal via Tour Path
```
1. POST /api/dev/seed-engagements          → seed test data
2. POST /api/auth/signup (supplier)         → get SUPPLIER_TOKEN
3. POST /api/auth/signup (buyer)            → get BUYER_TOKEN
4. POST /api/buyer/register                 → get BUYER_ID
5. POST /api/buyer/need                     → get NEED_ID
6. GET  /api/buyer/need/{id}/options        → get MATCH_ID, triggers clearing
7. POST /api/buyer/need/{id}/accept         → creates engagement (DEAL_PING_SENT)
8. POST /api/engagements/{id}/deal-ping/accept  → DEAL_PING_ACCEPTED (as supplier)
9. POST /api/engagements/{id}/accept        → BUYER_ACCEPTED (path: "tour")
10. POST /api/engagements/{id}/guarantee/sign → ADDRESS_REVEALED (hold starts)
11. POST /api/engagements/{id}/tour/request  → TOUR_REQUESTED
12. POST /api/engagements/{id}/tour/confirm  → TOUR_CONFIRMED (as supplier)
13. POST /api/engagements/{id}/tour/outcome  → BUYER_CONFIRMED → AGREEMENT_SENT
14. POST /api/engagements/{id}/agreement/sign → buyer signs
15. POST /api/engagements/{id}/agreement/sign → supplier signs → ONBOARDING
16. POST /api/engagements/{id}/onboarding/insurance
17. POST /api/engagements/{id}/onboarding/company-docs
18. POST /api/engagements/{id}/onboarding/payment → ACTIVE
19. GET  /api/engagements/{id}/timeline      → verify full audit trail
20. GET  /api/engagements/{id}/payments      → verify payment records
```

### E2E Flow 2: Instant Book Path
```
1-6. Same as above
7.  POST /api/engagements/{id}/deal-ping/accept
8.  POST /api/engagements/{id}/accept (path: "instant_book")
9.  POST /api/engagements/{id}/instant-book  → AGREEMENT_SENT (skips tour)
10. POST /api/engagements/{id}/agreement/sign (buyer)
11. POST /api/engagements/{id}/agreement/sign (supplier) → ONBOARDING
12-14. Onboarding steps → ACTIVE
```

### E2E Flow 3: SMS → Voice Cross-Channel
```
1. POST /api/sms/buyer/webhook              → buyer texts "need 10k sqft in Dallas"
2. (wait 5s for background processing)
3. POST /api/sms/buyer/webhook              → buyer texts "show me option 1"
4. POST /api/voice/webhook (assistant-request) → same phone number calls in
   Verify: firstMessage references SMS context ("I've got those options pulled up")
5. POST /api/voice/webhook (tool-calls)     → search_properties (should reuse SMS criteria)
6. POST /api/voice/webhook (tool-calls)     → send_booking_link
7. POST /api/voice/webhook (end-of-call)    → follow-up SMS with guarantee link sent
8. POST /sms/guarantee/{token}/sign         → buyer signs guarantee via mobile web
```

### E2E Flow 4: DLA Supplier Activation via SMS
```
1. POST /api/clearing/match                 → triggers DLA for off-network property
2. POST /api/sms/webhook (YES reply)        → DLAToken.status -> "interested"
3. GET  /api/dla/token/{token}              → supplier views deal details
4. POST /api/dla/token/{token}/rate         → supplier accepts rate
5. POST /api/dla/token/{token}/confirm      → supplier confirms, property flips to in_network
6. POST /api/clearing/match                 → re-run clearing, property now in Tier 1
```

---

## Validation Checklist

After running all phases, verify:

- [ ] Health check returns 200
- [ ] Auth signup/login/me all work
- [ ] Browse listings returns paginated data
- [ ] Search returns matches and session tokens
- [ ] Buyer registration and need creation work
- [ ] Clearing engine returns tier 1 + tier 2 matches
- [ ] Engagement state machine transitions correctly through all 24 states
- [ ] Role-based filtering hides pricing correctly (buyer vs supplier vs admin)
- [ ] Tour scheduling full lifecycle works
- [ ] Instant book skips tour correctly
- [ ] Agreement signing by both parties triggers ONBOARDING
- [ ] Onboarding completion triggers ACTIVE
- [ ] Hold extension works once and blocks second attempt
- [ ] Sqft claimed on guarantee, released on decline
- [ ] DLA token resolution and rate submission work
- [ ] Supplier SMS webhook processes YES/NO/STOP/rate correctly
- [ ] Buyer SMS webhook creates conversation state and processes in background
- [ ] Vapi assistant-request returns valid config with cross-channel SMS context
- [ ] Vapi tool-calls (search, lookup, booking) return correct results
- [ ] Vapi end-of-call sends follow-up SMS
- [ ] SMS guarantee signing page renders and processes signatures
- [ ] Escalation reply tool sends polished answers
- [ ] All 12 scheduler jobs execute without errors
- [ ] WebSocket connections establish and receive events
- [ ] Admin endpoints show full economics (both rates + spread)
- [ ] Timeline/audit trail captures every state transition

# GCP Hosting Plan for WEx Platform

## Context
The WEx Platform currently runs locally (SQLite, local filesystem, in-process background tasks). This plan covers everything needed to host it production-ready on Google Cloud: infrastructure, code changes, CI/CD, and migration steps.

---

## GCP Services Overview

| Service | Purpose |
|---------|---------|
| **Cloud Run** (x5) | Host all containerized services |
| **Cloud SQL** (PostgreSQL 16) | Relational DB for main platform + clearing house |
| **Firestore** | Leasing service document store (already integrated) |
| **Secret Manager** (22 secrets) | All API keys, tokens, DB passwords |
| **Cloud Storage** | Property photo uploads (replaces local `/uploads/`) |
| **Cloud Scheduler** (12 jobs) | Cron triggers for background jobs |
| **Global HTTP(S) Load Balancer** | Custom domain, SSL, path-based routing, WebSocket support |
| **Direct VPC Egress** | Private networking between Cloud Run and Cloud SQL (no connector instances to manage) |
| **Cloud DNS** | Manage `warehouseexchange.com` records |
| **Artifact Registry** | Docker image storage |
| **GitHub Actions** | CI/CD pipelines (build, push to Artifact Registry, deploy to Cloud Run) |
| **Cloud Logging + Monitoring** | Observability, alerts, uptime checks |

---

## Architecture

```
              Internet
                 |
          [Cloud DNS: warehouseexchange.com]
                 |
      [Global HTTP(S) Load Balancer]
       SSL termination + routing
      +------+------+------+------+
      |      |      |      |      |
  wex-fe  wex-be  clr-fe clr-be  leasing
  (Next)  (Fast)  (Next) (Fast)  (Fast)
      |      |      |      |      |
      +------+--+---+------+      |
                |                  |
      [Direct VPC Egress]      [Firestore]
                |
        [Cloud SQL - PG 16]
         (private IP only)

  [Cloud Scheduler] --HTTP POST--> wex-be /api/internal/scheduler/*
  [Cloud Storage]   <------------ wex-be (photo uploads)
  [Secret Manager]  <------------ all services (env injection)
```

**Load balancer routing:**
- `warehouseexchange.com/*` --> `wex-frontend`
- `warehouseexchange.com/api/*` --> `wex-backend`
- `warehouseexchange.com/ws/*` --> `wex-backend` (WebSocket upgrade)
- `clearing.warehouseexchange.com/*` --> `clearing-frontend`
- `clearing.warehouseexchange.com/api/*` --> `clearing-backend`
- `leasing.warehouseexchange.com/*` --> `leasing-service`

---

## Cloud Run Services

| Service | Port | Memory | CPU | Min Inst | Max Inst | Timeout | Session Affinity | Notes |
|---------|------|--------|-----|----------|----------|---------|------------------|-------|
| **wex-backend** | 8080 | 1 Gi | 2 | 1 | 10 | 300s | Yes | CPU always allocated + session affinity for WebSockets |
| **wex-frontend** | 8080 | 512 Mi | 1 | 0 | 5 | 60s | No | Can cold-start |
| **clearing-backend** | 8080 | 512 Mi | 1 | 0 | 5 | 120s | No | Already Dockerized |
| **clearing-frontend** | 8080 | 256 Mi | 1 | 0 | 3 | 60s | No | Already Dockerized |
| **leasing-service** | 8080 | 512 Mi | 1 | 1 | 5 | 120s | No | Always-on for Twilio webhooks |

- Backend min=1 because WebSocket connections + Vapi/Aircall webhooks can't tolerate cold starts
- **CPU always allocated** on wex-backend: required for WebSockets. Default "CPU only during requests" throttles the container between HTTP requests, silently dropping persistent WS connections
- Session affinity on backend for WebSocket sticky routing
- All services locked to `--ingress=internal-and-cloud-load-balancing` (except leasing if Twilio hits it directly)

---

## Cloud SQL Setup

- **Instance:** `wex-db`, PostgreSQL 16, `db-custom-2-4096` (2 vCPU, 4 GB)
- **HA:** Regional (auto-failover) -- can start zonal to save ~$45/mo
- **Storage:** 20 GB SSD, auto-increase
- **Backups:** Daily at 4 AM, 14-day retention, point-in-time recovery
- **Networking:** Private IP only (no public IP), accessed via Direct VPC Egress from Cloud Run
- **Databases:** `wex_platform` (main) + `wex_clearing` (clearing house)
- **Connection string format** (already supported in code):
  ```
  postgresql+asyncpg://wex_app:PASSWORD@/wex_platform?host=/cloudsql/PROJECT:us-central1:wex-db
  ```
- **Connection pooling:** As Cloud Run scales to 10 instances (each with pool_size=5 + max_overflow=10), up to 150 connections can open simultaneously. Use the **Cloud SQL Auth Proxy** in sidecar mode with built-in connection management, or add **PgBouncer** as a sidecar container to pool connections across instances and stay within `max_connections=200`

---

## Secret Manager (22 secrets)

**Database:** `wex-database-url`, `clearing-database-url`
**Auth:** `wex-jwt-secret`, `wex-admin-password`
**AI/Google:** `wex-gemini-api-key`, `wex-google-maps-api-key`
**Email:** `wex-sendgrid-api-key`, `wex-supply-alert-from`, `wex-supply-alert-to`
**Aircall:** `wex-aircall-api-id`, `wex-aircall-api-token`, `wex-aircall-number-id`, `wex-aircall-buyer-number-id`, `wex-aircall-webhook-token`
**Vapi:** `wex-vapi-api-key`, `wex-vapi-server-secret`, `wex-vapi-phone-number-id`, `wex-vapi-voice-id`
**Twilio:** `wex-twilio-sid`, `wex-twilio-auth-token`, `wex-twilio-phone`
**Internal:** `wex-internal-api-token`

Injected via Cloud Run `--set-secrets` flag (no code changes needed for reading).

---

## Cloud Storage

- **Bucket:** `gs://wex-prod-uploads/properties/{property_id}/{uuid}_{filename}.jpg`
- **Access:** Private bucket + signed URLs (1-hour expiry) generated at read-time
- **IAM:** Only `wex-backend-sa` gets `roles/storage.objectAdmin`

---

## Cloud Scheduler (12 jobs)

Replaces in-process `asyncio.create_task()` background loops. Each job POSTs to a new `/api/internal/scheduler/{job}` endpoint.

| Job | Schedule | Endpoint |
|-----|----------|----------|
| Hold monitor | `*/15 * * * *` | `/api/internal/scheduler/hold-monitor` |
| SMS cron tick | `*/15 * * * *` | `/api/internal/scheduler/sms-tick` |
| Deal ping deadlines | `*/15 * * * *` | `/api/internal/scheduler/deal-ping-deadlines` |
| General deadlines | `*/15 * * * *` | `/api/internal/scheduler/deadlines` |
| Tour reminders | `0 6 * * *` | `/api/internal/scheduler/tour-reminders` |
| Post-tour follow-up | `0 * * * *` | `/api/internal/scheduler/post-tour-followup` |
| Q&A deadline | `0 * * * *` | `/api/internal/scheduler/qa-deadline` |
| Payment record gen | `0 0 * * *` | `/api/internal/scheduler/payment-records` |
| Payment reminders | `0 9 * * *` | `/api/internal/scheduler/payment-reminders` |
| Stale engagements | `0 8 * * *` | `/api/internal/scheduler/stale-engagements` |
| Auto-activate leases | `0 0 * * *` | `/api/internal/scheduler/auto-activate` |
| Renewal prompts | `0 9 * * *` | `/api/internal/scheduler/renewal-prompts` |

Auth: OIDC token from `wex-scheduler-sa` service account (Cloud Run verifies natively).

---

## IAM Service Accounts

| Account | Roles |
|---------|-------|
| `wex-backend-sa` | Cloud SQL Client, Secret Accessor, Storage Object Admin |
| `wex-frontend-sa` | (none -- no GCP resources accessed) |
| `clearing-backend-sa` | Cloud SQL Client, Secret Accessor |
| `clearing-frontend-sa` | (none) |
| `leasing-sa` | Firestore User, AI Platform User, Secret Accessor |
| `wex-scheduler-sa` | Cloud Run Invoker |

---

## Code Changes Required

### 1. Create `backend/Dockerfile` (new file)
Multi-stage Python 3.12-slim build, non-root user, port 8080.

### 2. Create `frontend/Dockerfile` (new file)
Multi-stage Node 20-slim build, `npm run build` then `next start -p 8080`.

### 3. Modify `backend/src/wex_platform/app/main.py`
- Read `PORT` from env var: `port=int(os.environ.get("PORT", 8000))`
- Remove `asyncio.create_task(hold_monitor_loop())` from lifespan (Cloud Scheduler replaces it)
- Conditionalize the `StaticFiles` mount for `/uploads/` (only in dev)

### 4. Modify `frontend/next.config.ts`
- Skip the `/api/:path*` rewrite in production (load balancer handles routing)
- Optionally add `output: 'standalone'` for smaller Docker images

### 5. Create `backend/src/wex_platform/app/routes/scheduler_jobs.py` (new file)
- HTTP POST endpoints wrapping each of the 11 functions in `background_jobs.py`
- Auth: verify OIDC token or internal token header
- Follow the existing pattern in `sms_scheduler.py`

### 6. Modify `backend/src/wex_platform/app/routes/supplier_dashboard.py` (~line 1335)
- Replace local filesystem writes with `google-cloud-storage` client
- Return signed URLs instead of `/uploads/...` paths

### 7. Add `google-cloud-storage` to `pyproject.toml` dependencies

### 8. Create `.github/workflows/` CI/CD pipelines (backend + frontend)

---

## CI/CD Pipeline (GitHub Actions)

GitHub Actions preferred over Cloud Build for better developer experience and faster pipeline execution, especially for Next.js and Python builds.

1. **Artifact Registry:** `us-central1-docker.pkg.dev/wex-prod/wex-images/`
2. **Auth:** Workload Identity Federation (keyless auth from GitHub to GCP -- no service account keys to manage)
3. **Workflows:** One per service in `.github/workflows/` (e.g. `deploy-backend.yml`), triggered on push to `main` with path filter
4. **Steps:** Checkout --> Authenticate to GCP via WIF --> Build Docker image --> Push to Artifact Registry --> Deploy to Cloud Run via `gcloud run deploy`
5. **Environments:** Use GitHub Environments for staging vs production with approval gates

---

## Monitoring & Alerts

- **Uptime checks** on `/health` for all backend services (5-min interval)
- **Alert policies:** Error rate > 5%, latency p95 > 5s, Cloud SQL CPU > 80%, max instances reached, scheduler job failures
- **Structured logging:** Already uses `structlog` -- Cloud Logging parses JSON automatically
- **Dashboard:** Request count, latency, instance count, DB metrics, scheduler success rates

---

## Estimated Monthly Cost

| Item | Cost |
|------|------|
| Cloud Run (5 services) | $80-140 |
| Cloud SQL (HA) | $90-120 |
| Load Balancer | $18-25 |
| Direct VPC Egress | $0 (included in Cloud Run pricing) |
| Storage, Secrets, DNS, Scheduler | $3-10 |
| **Total** | **~$190-310/mo** |

Start zonal (no HA) to save ~$45/mo. Enable HA before accepting paying customers.

---

## Migration Steps

1. **Day 1:** Create GCP project, enable APIs, configure Direct VPC Egress, Cloud SQL, Storage bucket, populate secrets
2. **Day 2:** Write Dockerfiles, build/test images locally, push to Artifact Registry
3. **Day 3:** Deploy all 5 Cloud Run services, verify health + DB connectivity
4. **Day 4:** Set up Load Balancer, SSL certs, DNS records, test all routes
5. **Day 5:** Create scheduler endpoints, deploy Cloud Scheduler jobs, set up monitoring
6. **Day 6:** Migrate SQLite data to Cloud SQL, migrate uploads to Cloud Storage
7. **Day 7:** Set up GitHub Actions workflows + Workload Identity Federation, test full CI/CD pipeline, go live

---

## Verification

1. Hit `https://warehouseexchange.com/health` -- expect `{"status":"ok"}`
2. Open frontend, login, verify supplier dashboard loads data from Cloud SQL
3. Upload a property photo -- confirm it lands in Cloud Storage bucket
4. Check Cloud Scheduler execution logs -- confirm all 12 jobs fire on schedule
5. Send test SMS via Aircall -- verify webhook round-trip
6. Make a Vapi voice call -- verify webhook at `/api/voice/webhook`
7. Open `/ws/admin` WebSocket in browser -- confirm real-time events stream
8. Push a code change to `main` -- confirm GitHub Actions auto-deploys

---

## API Endpoint Test Plan

All endpoints grouped by module. Use `scripts/test_endpoints.sh` to run automated smoke tests after deployment.

### Health & Infrastructure (no auth)

| # | Method | Endpoint | Expected |
|---|--------|----------|----------|
| 1 | GET | `/health` | 200 `{"status":"ok"}` |

### Auth (no auth required)

| # | Method | Endpoint | Body | Expected |
|---|--------|----------|------|----------|
| 2 | POST | `/api/auth/signup` | `{email, password, name, role, company, phone}` | 200 + JWT token |
| 3 | POST | `/api/auth/login` | `{email, password}` | 200 + JWT token |
| 4 | GET | `/api/auth/me` | (Bearer token) | 200 + user profile |
| 5 | PATCH | `/api/auth/profile` | `{name?, company?, phone?}` | 200 + updated user |

### Browse & Search (no auth)

| # | Method | Endpoint | Expected |
|---|--------|----------|----------|
| 6 | GET | `/api/browse/listings` | 200 + paginated listings |
| 7 | GET | `/api/browse/locations` | 200 + city/state pairs |
| 8 | POST | `/api/search` | 200 + search results with session token |
| 9 | GET | `/api/search/session/{token}` | 200 + cached results |
| 10 | POST | `/api/search/extract` | 200 + extracted intent fields |

### Buyer Flow (no auth)

| # | Method | Endpoint | Expected |
|---|--------|----------|----------|
| 11 | POST | `/api/buyer/register` | 200 + buyer profile |
| 12 | POST | `/api/buyer/need` | 200 + buyer need |
| 13 | GET | `/api/buyer/{buyer_id}/needs` | 200 + needs list |
| 14 | POST | `/api/buyer/need/{need_id}/chat/start` | 200 + initial message |
| 15 | POST | `/api/buyer/need/{need_id}/chat` | 200 + agent response |
| 16 | GET | `/api/buyer/need/{need_id}/options` | 200 + matched options |
| 17 | POST | `/api/buyer/need/{need_id}/accept` | 200 + deal created |
| 18 | GET | `/api/buyer/{buyer_id}/deals` | 200 + deals list |

### Clearing Engine (no auth)

| # | Method | Endpoint | Expected |
|---|--------|----------|----------|
| 19 | POST | `/api/clearing/match` | 200 + tier1/tier2 matches |
| 20 | GET | `/api/clearing/match-count?location=...` | 200 + count |
| 21 | GET | `/api/clearing/match/{match_id}` | 200 + scoring breakdown |

### Supplier Dashboard (Bearer token required)

| # | Method | Endpoint | Expected |
|---|--------|----------|----------|
| 22 | GET | `/api/supplier/dashboard` | 200 + portfolio summary |
| 23 | GET | `/api/supplier/properties` | 200 + property list |
| 24 | GET | `/api/supplier/properties/{id}` | 200 + property detail |
| 25 | POST | `/api/supplier/properties/{id}/specs` | 200 + updated specs |
| 26 | POST | `/api/supplier/properties/{id}/config` | 200 + updated config |
| 27 | POST | `/api/supplier/properties/{id}/pricing` | 200 + updated pricing |
| 28 | GET | `/api/supplier/engagements` | 200 + engagement list |
| 29 | POST | `/api/supplier/engagements/{id}/respond` | 200 + engagement updated |
| 30 | GET | `/api/supplier/account` | 200 + account info |
| 31 | GET | `/api/supplier/account/preferences` | 200 + prefs |

### Photo Upload

| # | Method | Endpoint | Auth | Expected |
|---|--------|----------|------|----------|
| 32 | POST | `/api/upload/token` | Bearer | 200 + upload token |
| 33 | POST | `/api/upload/photo/{token}` | None (token) | 200 + file URL |

### Engagement Lifecycle (Bearer token required)

| # | Method | Endpoint | Expected |
|---|--------|----------|----------|
| 34 | GET | `/api/engagements/{id}` | 200 + engagement detail |
| 35 | POST | `/api/engagements/{id}/accept` | 200 + state transition |
| 36 | POST | `/api/engagements/{id}/tour/request` | 200 + tour requested |
| 37 | POST | `/api/engagements/{id}/tour/confirm` | 200 + tour confirmed |
| 38 | POST | `/api/engagements/{id}/tour/complete` | 200 + tour completed |

### Q&A (Bearer token required)

| # | Method | Endpoint | Expected |
|---|--------|----------|----------|
| 39 | POST | `/api/engagements/{id}/questions` | 200 + question created |
| 40 | POST | `/api/engagements/{id}/questions/{qid}/supplier-answer` | 200 + answered |

### Admin (admin auth required)

| # | Method | Endpoint | Expected |
|---|--------|----------|----------|
| 41 | GET | `/api/admin/overview` | 200 + network stats |
| 42 | GET | `/api/admin/warehouses` | 200 + all properties |
| 43 | GET | `/api/admin/deals` | 200 + all deals |
| 44 | GET | `/api/admin/deals/{id}` | 200 + deal detail |
| 45 | GET | `/api/admin/agents` | 200 + agent log |
| 46 | GET | `/api/admin/ledger` | 200 + ledger |
| 47 | GET | `/api/admin/clearing/stats` | 200 + clearing stats |
| 48 | GET | `/api/admin/engagements` | 200 + engagement list |
| 49 | POST | `/api/admin/engagements/{id}/override-status` | 200 + overridden |
| 50 | POST | `/api/admin/engagements/{id}/note` | 200 + note added |

### DLA (token-based auth)

| # | Method | Endpoint | Expected |
|---|--------|----------|----------|
| 51 | GET | `/api/dla/token/{token}` | 200 + property + buyer req |
| 52 | POST | `/api/dla/token/{token}/rate` | 200 + rate decision |
| 53 | POST | `/api/dla/token/{token}/confirm` | 200 + deal created |

### Enrichment (no auth)

| # | Method | Endpoint | Expected |
|---|--------|----------|----------|
| 54 | GET | `/api/enrichment/warehouse/{id}/next` | 200 + next question |
| 55 | POST | `/api/enrichment/warehouse/{id}/respond` | 200 + stored |
| 56 | GET | `/api/enrichment/warehouse/{id}/completeness` | 200 + % complete |

### Webhooks (signature/token validated)

| # | Method | Endpoint | Auth | Expected |
|---|--------|----------|------|----------|
| 57 | POST | `/api/voice/webhook` | Vapi HMAC signature | 200 + assistant config |
| 58 | POST | `/api/sms/webhook` | Aircall token | 200 + `{ok}` |
| 59 | POST | `/api/sms/buyer/webhook` | Aircall token | 200 + `{ok}` |

### WebSockets

| # | Endpoint | Expected |
|---|----------|----------|
| 60 | `wss://warehouseexchange.com/ws/admin` | Connection established, receives events |
| 61 | `wss://warehouseexchange.com/ws/activation/{id}` | Connection established, agent responds |

### Cloud Scheduler Endpoints (OIDC auth)

| # | Method | Endpoint | Expected |
|---|--------|----------|----------|
| 62 | POST | `/api/internal/scheduler/hold-monitor` | 200 |
| 63 | POST | `/api/internal/scheduler/sms-tick` | 200 |
| 64 | POST | `/api/internal/scheduler/deal-ping-deadlines` | 200 |
| 65 | POST | `/api/internal/scheduler/deadlines` | 200 |
| 66 | POST | `/api/internal/scheduler/tour-reminders` | 200 |
| 67 | POST | `/api/internal/scheduler/post-tour-followup` | 200 |
| 68 | POST | `/api/internal/scheduler/qa-deadline` | 200 |
| 69 | POST | `/api/internal/scheduler/payment-records` | 200 |
| 70 | POST | `/api/internal/scheduler/payment-reminders` | 200 |
| 71 | POST | `/api/internal/scheduler/stale-engagements` | 200 |
| 72 | POST | `/api/internal/scheduler/auto-activate` | 200 |
| 73 | POST | `/api/internal/scheduler/renewal-prompts` | 200 |

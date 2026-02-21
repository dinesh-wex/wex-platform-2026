# WEx Platform 2026 - Setup & Testing Guide

## Prerequisites

- **Conda** (Anaconda or Miniconda) — you likely already have this
- **Python 3.12+**
- **Node.js 18+** and **npm**

---

## FIRST TIME SETUP (do this once)

### Step 1: Create and activate a Python environment

Open a terminal (PowerShell or Command Prompt) and navigate to the project:

```powershell
cd "C:\Users\deser\Github\Warehouse Exchange\WEx Platform 2026"
```

Create a dedicated Conda environment for this project:

```powershell
conda create -n wex python=3.12 -y
```

Activate it:

```powershell
conda activate wex
```

> **IMPORTANT:** You must run `conda activate wex` every time you open a new terminal before running backend commands. Your prompt should show `(wex)` instead of `(base)`.

### Step 2: Install backend Python dependencies

With the `(wex)` environment active:

```powershell
cd backend
pip install -e ".[dev]"
```

This installs FastAPI, SQLAlchemy, uvicorn, and all other backend dependencies into your `wex` environment.

### Step 3: Install frontend Node.js dependencies

Open a **second terminal** (this one doesn't need Conda):

```powershell
cd "C:\Users\deser\Github\Warehouse Exchange\WEx Platform 2026\frontend"
npm install
```

### Step 4: Configure environment variables

The backend `.env` file should already exist at `backend/.env`. If not, copy the template:

```powershell
copy .env.example backend\.env
```

Edit `backend/.env` and fill in your API keys:

```
GEMINI_API_KEY=your-gemini-api-key
GOOGLE_MAPS_API_KEY=your-maps-api-key
SENDGRID_API_KEY=your-sendgrid-key         # optional for local dev
AIRCALL_API_ID=your-aircall-api-id         # optional for local dev
AIRCALL_API_TOKEN=your-aircall-api-token   # optional for local dev
AIRCALL_NUMBER_ID=your-aircall-number-id   # optional for local dev
AIRCALL_WEBHOOK_TOKEN=your-webhook-token   # optional for local dev
```

The defaults work fine for local dev (SQLite DB, debug mode, localhost CORS).

The frontend `.env.local` is already configured with:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## RUNNING THE PLATFORM (every time)

You need **two terminals** running simultaneously.

### Terminal 1 — Backend (port 8000)

```powershell
conda activate wex
cd "C:\Users\deser\Github\Warehouse Exchange\WEx Platform 2026\backend"
uvicorn wex_platform.app.main:app --reload --port 8000
```

On first run, the SQLite database (`wex_platform.db`) is auto-created with all tables.

You should see output like:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
```

### Terminal 2 — Frontend (port 3000)

```powershell
cd "C:\Users\deser\Github\Warehouse Exchange\WEx Platform 2026\frontend"
npm run dev
```

You should see:
```
  ▲ Next.js 15.1.0
  - Local:   http://localhost:3000
```

### Verify both are running

| Check | URL | Expected |
|-------|-----|----------|
| Backend health | http://localhost:8000/health | `{"status":"ok","service":"wex-platform"}` |
| Swagger API docs | http://localhost:8000/docs | Interactive API documentation |
| Frontend | http://localhost:3000 | Marketplace homepage |

---

## TROUBLESHOOTING

### "uvicorn is not recognized"
You forgot to activate the Conda environment. Run:
```powershell
conda activate wex
```
Your prompt should show `(wex)` not `(base)`.

### "ModuleNotFoundError: No module named 'wex_platform'"
You need to install the backend package. With `(wex)` active:
```powershell
cd backend
pip install -e ".[dev]"
```

### "npm: command not found"
Install Node.js from https://nodejs.org/ (LTS version).

### Database issues / want to start fresh
Delete the database file and restart the backend:
```powershell
del backend\wex_platform.db
```
It will be recreated on next startup.

### Port already in use
Kill the process using the port:
```powershell
# Find what's using port 8000
netstat -ano | findstr :8000
# Kill it (replace PID with the number from above)
taskkill /PID <PID> /F
```

---

## TEST THE FLOWS

### Public Flows (no login required)

| Flow | URL | What to Test |
|------|-----|--------------|
| **Homepage** | http://localhost:3000/ | Hero section, dual CTAs ("Find Space" / "List Your Space"), How It Works, Featured Listings, Value Props, CTA Section, Footer |
| **EarnCheck** | http://localhost:3000/supplier/earncheck | Full 6-phase wizard: address entry, property intel, revenue estimate, configure space, pricing, report. Last step has "Join the WEx Network" CTA |
| **Buyer Wizard** | http://localhost:3000/buyer | 7-step flow: Location, Use Type (3 cards), What Goods (conditional), Size (slider + live match count), Timing + Duration, Deal-Breakers (multi-select), "Find My Matches". Check "Prefer to text?" link on every screen |
| **Browse Collection** | http://localhost:3000/browse | Filterable grid of listings. Verify: shows neighborhood (not address), size/rate ranges (not exact), no supplier names. Click a card to see interest modal routing to buyer wizard |
| **DLA Flow** | http://localhost:3000/dla/test-token | 5-step Demand-Led Activation: property confirmation, deal shown, rate decision, agreement, success |

### Auth Flows

| Flow | URL | What to Test |
|------|-----|--------------|
| **Sign Up** | http://localhost:3000/signup | Two tabs: "I have space" (supplier) / "I need space" (buyer). Fill form, submit |
| **Log In** | http://localhost:3000/login | Email + password, redirects to appropriate dashboard on success |
| **Profile** | http://localhost:3000/profile | View/edit profile (requires login) |

### Protected Flows (login required)

| Flow | URL | Role | What to Test |
|------|-----|------|--------------|
| **Supplier Dashboard** | /supplier | Supplier | Portfolio of in-network warehouses |
| **Supplier Onboard** | /supplier/onboard | Supplier | Two paths: post-EarnCheck (data pre-loaded) or direct (full data collection). Checkbox agreement + activate |
| **Warehouse Detail** | /supplier/warehouse/{id} | Supplier | Property details + progressive enrichment section (profile completeness, photo upload, Q&A) |
| **Buyer Results** | /buyer/options | Buyer | Three states: Tier 1 (cleared matches with %, rate, "Why This Space"), Tier 2 (being sourced), No-match (designed "sourcing" screen + contact capture) |
| **Buyer Search** | /buyer/search | Buyer | Chat-based alternative search |
| **Buyer Deals** | /buyer/deals | Buyer | Active deals list |
| **Admin Dashboard** | /admin | Admin | Overview stats |
| **Admin Agents** | /admin/agents | Admin | AI agent logs |
| **Admin Clearing** | /admin/clearing | Admin | Matching stats |
| **Admin EarnCheck** | /admin/earncheck | Admin | EarnCheck analytics |
| **Admin Ledger** | /admin/ledger | Admin | Financial ledger |

### API Endpoints (via Swagger at http://localhost:8000/docs)

| Category | Key Endpoints |
|----------|--------------|
| **Auth** | `POST /api/auth/signup`, `POST /api/auth/login`, `GET /api/auth/me`, `PATCH /api/auth/profile` |
| **Supplier** | `POST /api/supplier/onboard`, `GET /api/supplier/warehouses`, `POST /api/supplier/deal/{id}/tour/confirm` |
| **Buyer** | `POST /api/buyer/needs`, `POST /api/buyer/deal/{id}/guarantee`, `POST /api/buyer/deal/{id}/tour` |
| **Clearing** | `POST /api/clearing/match`, `GET /api/clearing/match-count` |
| **DLA** | `GET /api/dla/token/{token}`, `POST /api/dla/token/{token}/rate`, `POST /api/dla/token/{token}/confirm` |
| **Browse** | `GET /api/browse/listings`, `GET /api/browse/locations` |
| **Agreements** | `POST /api/agreements/sign`, `GET /api/agreements/status` |
| **Enrichment** | `GET /api/enrichment/warehouse/{id}/next`, `POST /api/enrichment/warehouse/{id}/respond`, `GET /api/enrichment/warehouse/{id}/completeness` |
| **SMS** | `POST /api/sms/webhook` (Aircall webhook) |

---

## KEY ANTI-CIRCUMVENTION SEQUENCE

The critical buyer-to-tour flow enforces this order:

1. Buyer clicks "Accept & Schedule Tour" on results page
2. Contact capture (email + phone)
3. WEx Occupancy Guarantee signed (checkbox agreement)
4. Address revealed (only AFTER guarantee signed)
5. Tour scheduled (date/time picker)
6. Supplier notified + confirms (12hr deadline)
7. Post-tour follow-up (24hr automated check-in)

---

## EXTERNAL SERVICE DEPENDENCIES

These features need real API keys to function (everything else works without them):

| Service | Used For | Config Key |
|---------|----------|------------|
| **Gemini** | AI property analysis, buyer agent, SMS parsing | `GEMINI_API_KEY` |
| **Google Maps** | Geocoding, address validation | `GOOGLE_MAPS_API_KEY` |
| **SendGrid** | Email notifications, EarnCheck reports | `SENDGRID_API_KEY` |
| **Aircall** | SMS outreach (DLA), buyer SMS intake | `AIRCALL_API_ID`, `AIRCALL_API_TOKEN`, `AIRCALL_NUMBER_ID` |

---

## USEFUL COMMANDS

```powershell
# ── Always activate environment first ──
conda activate wex

# ── Backend ──
cd backend
uvicorn wex_platform.app.main:app --reload --port 8000    # Run backend
pip install -e ".[dev]"                                     # Reinstall after adding deps

# ── Frontend ──
cd frontend
npm run dev                                                 # Run frontend
npm run build                                               # Production build
npm run lint                                                # ESLint check
npx tsc --noEmit                                           # TypeScript type check

# ── Using Makefile (from project root, with wex env active) ──
make install           # Install both frontend + backend
make dev-backend       # Run backend
make dev-frontend      # Run frontend
make lint              # Lint both
make db-init           # Initialize database manually
```

---

## PROJECT STRUCTURE

```
WEx Platform 2026/
├── frontend/                    # Next.js 15 + React 19 + Tailwind
│   ├── src/
│   │   ├── app/                 # Pages (20 total)
│   │   ├── components/          # Reusable components (26+)
│   │   │   ├── activation/      # 6-phase EarnCheck wizard
│   │   │   ├── auth/            # Login, Signup, AuthGuard, UserMenu
│   │   │   ├── homepage/        # Hero, HowItWorks, etc.
│   │   │   └── ui/              # ContactCapture, Agreement, TourBooking
│   │   ├── lib/                 # api.ts, auth.ts, utils.ts, analytics.ts
│   │   └── config/              # flowCopy.ts
│   └── .env.local               # NEXT_PUBLIC_API_URL
├── backend/                     # FastAPI + SQLAlchemy + SQLite
│   ├── src/wex_platform/
│   │   ├── app/
│   │   │   ├── main.py          # FastAPI app (10 routers)
│   │   │   ├── config.py        # Pydantic Settings
│   │   │   └── routes/          # 10 route files
│   │   ├── domain/
│   │   │   ├── models.py        # 24 SQLAlchemy models
│   │   │   └── schemas.py       # Pydantic request/response schemas
│   │   ├── infra/
│   │   │   └── database.py      # Async SQLAlchemy engine
│   │   ├── services/            # 14 service files
│   │   └── agents/              # 10 AI agents + prompts
│   ├── .env                     # Environment variables (DO NOT commit)
│   └── pyproject.toml           # Python deps + tooling config
├── docs/                        # Design documents
├── .env.example                 # Template for environment setup
├── SETUP.md                     # This file
└── Makefile                     # Dev commands
```

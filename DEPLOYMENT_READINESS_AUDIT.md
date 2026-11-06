# DEPLOYMENT READINESS AUDIT
## Stock Intelligence Pro — Phase 13 Cloud Migration Audit

**Date:** November 5, 2026  
**Auditor:** Antigravity Agent  
**Workspace:** `D:\ST\Stock-Intelligence-Starter\Stock-Intelligence`  
**Target Environment:** 
- Frontend: Cloudflare Pages Free (React + TypeScript + Vite)
- Backend: Render Free (FastAPI + Uvicorn)
- Database & Auth: Supabase Free (PostgreSQL + Supabase Auth)
- Monthly Budget: ₹0

---

## 1. Actual Frontend Build Directory & Configuration

- **Source Directory:** `frontend/`
- **Build Output Directory:** `frontend/dist/`
- **Build Tooling:** Vite v6.0.1, TypeScript v5.7.2, React v18.3.1
- **Build Command:** `npm run build` (runs `tsc && vite build`)
- **Bundle Verification:** 
  - `dist/index.html` (0.51 kB)
  - `dist/assets/index-*.css` (16.69 kB)
  - `dist/assets/vendor-*.js` (141.74 kB)
  - `dist/assets/charts-*.js` (173.96 kB)
  - `dist/assets/index-*.js` (383.42 kB)
- **Routing Status:** Single-Page Application (SPA). Requires Cloudflare Pages `public/_redirects` file with rule `/* /index.html 200` to prevent 404 errors on deep linking or page refresh.

---

## 2. Actual Backend Entry Point & Server Execution

- **Source Directory:** `backend/`
- **Application File:** `backend/app/main.py`
- **ASGI Instance:** `app = FastAPI(...)` in `app.main`
- **Current Execution Command:** `uvicorn app.main:app` (executed from `backend/` directory)
- **Cloud Execution Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- **Render Service Type:** Web Service (Free Tier, Linux runtime, Python 3.12 environment)
- **Health Check Endpoint:** `GET /api/health` returning `{"status": "ok"}`

---

## 3. Existing API Base URL Configuration

- **Current State:** Hardcoded across 25+ frontend components as `http://127.0.0.1:8000` or `http://localhost:8000`.
- **Files Affected:**
  - `frontend/src/api/fundamentals.ts`
  - `frontend/src/api/marketFeed.ts`
  - `frontend/src/api/screener.ts`
  - `frontend/src/components/AIMentorView.tsx`
  - `frontend/src/components/AlertsView.tsx`
  - `frontend/src/components/CompanyResearch.tsx`
  - `frontend/src/components/FootprintOrderFlowView.tsx`
  - `frontend/src/components/MarketOverview.tsx`
  - `frontend/src/components/MarketScannerView.tsx`
  - `frontend/src/components/MarketXRayView.tsx`
  - `frontend/src/components/MoneyFlowIntelligenceView.tsx`
  - `frontend/src/components/OrderBlockBoardView.tsx`
  - `frontend/src/components/SettingsView.tsx`
  - `frontend/src/components/SetupBoardView.tsx`
  - `frontend/src/components/SmartMoneyConceptsView.tsx`
  - `frontend/src/components/SMCBacktestView.tsx`
  - `frontend/src/components/TechnicalAnalysisView.tsx`
  - `frontend/src/components/TradingViewChart.tsx`
  - `frontend/src/components/UnifiedResearchDashboardView.tsx`
  - `frontend/src/components/VolumeAnalyticsView.tsx`
  - `frontend/src/components/WatchlistView.tsx`
- **Remediation Plan:** Centralize API URL resolution into `frontend/src/api/client.ts` using `import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"`, with automatic Bearer token injection for all authenticated Supabase sessions.

---

## 4. Existing Database Implementation & Schema Inventory

- **Database Engine:** SQLite 3
- **Primary Database Path:** `backend/data/stock_intelligence.db` (208,896 bytes)
- **Secondary Root Artifact:** `backend/stock_intelligence.db` (0 bytes, unreferenced duplicate)
- **Total Tables:** 20 (including SQLite internal table)
- **Total Records:** 301

### Table-by-Table Row Count Audit:

| Table Name | Row Count | Classification | User Scoped? | Migration Strategy |
| :--- | :---: | :--- | :---: | :--- |
| `stocks` | 31 | Market Reference Data | No | Seeded reference data |
| `ohlcv` | 44 | Historical Candle Data | No | Seeded reference data |
| `data_updates` | 3 | Ingestion Metadata | No | System log |
| `fundamental_company_profiles` | 6 | Fundamental Financials | No | Reference data |
| `fundamental_income_statements` | 46 | Fundamental Statements | No | Reference data |
| `fundamental_balance_sheets` | 21 | Fundamental Statements | No | Reference data |
| `fundamental_cash_flows` | 21 | Fundamental Statements | No | Reference data |
| `fundamental_ratios` | 23 | Financial Metrics | No | Reference data |
| `fundamental_shareholdings` | 13 | Shareholding Patterns | No | Reference data |
| `fundamental_corporate_actions` | 0 | Corporate Actions | No | Schema only |
| `fundamental_competitors` | 0 | Peer Comparison | No | Schema only |
| `fundamental_sync_history` | 40 | Sync Logs | No | System log |
| **`custom_watchlists`** | **3** | **Personal User Data** | **YES (`user_id`)** | **User-scoped RLS** |
| **`market_alerts`** | **4** | **Personal User Data** | **YES (`user_id`)** | **User-scoped RLS** |
| **`market_alert_history`** | **34** | **Personal User Data** | **YES (`user_id`)** | **User-scoped RLS** |
| **`saved_screeners`** | **2** | **Personal User Data** | **YES (`user_id`)** | **User-scoped RLS** |
| **`saved_custom_scanners`** | **0** | **Personal User Data** | **YES (`user_id`)** | **User-scoped RLS** |
| **`research_trade_plans`** | **0** | **Personal User Data** | **YES (`user_id`)** | **User-scoped RLS** |
| **`research_notes`** | **0** | **Personal User Data** | **YES (`user_id`)** | **User-scoped RLS** |
| `sqlite_sequence` | 10 | SQLite System Table | N/A | Excluded from PostgreSQL |

---

## 5. Direct SQLite Access Locations

Direct database connection (`connect()`) and raw SQL execution are strictly encapsulated in:
1. `backend/app/database.py`: Core connection manager and CRUD operations.
2. `backend/app/fundamental_db.py`: Dedicated fundamental dataset DDL and queries.
3. `backend/app/providers/fundamentals/manager.py`: Sync state verification.
4. `backend/app/routers/fundamentals.py`: Sync history check.
5. `backend/app/services/dhan_ws_client.py`: WebSocket instrument lookup.
6. `backend/app/services/fundamental_seeder.py`: Direct SQLite seeding helper.

**Key Architecture Advantage:** All higher-level business services (`unified_research_engine.py`, `market_regime_engine.py`, `sector_rotation_engine.py`, `alerts_watchlist_service.py`, `advanced_scanner_service.py`) interact with data exclusively through repository helper functions in `app.database`. Introducing a database abstraction supporting PostgreSQL when `DATABASE_URL` is set enables seamless migration without modifying business logic.

---

## 6. Existing Authentication & Authorization Status

- **Web Application Authentication:** Currently **NONE**.
- **Security Vulnerability:** In the local environment, all endpoints (`/api/*`) are public. On a public cloud deployment, unauthenticated exposure would allow anyone on the internet to view or alter watchlists, alerts, and trade plans.
- **Broker Authentication:** `backend/app/routers/dhan_auth.py` implements DhanHQ broker OAuth and credential verification; this manages trading broker connectivity, NOT application user identity.
- **Target Auth Solution:** Supabase Auth (Email + Password) with signed JWT verification on FastAPI endpoints via JWKS / Supabase secret and Row-Level Security (RLS) in PostgreSQL.

---

## 7. Environment Variables Inventory

### Existing Variables (Local):
- `DATA_MODE`: Set to `demo` or `historical`.
- `DHAN_CLIENT_ID`: Broker Client ID.
- `DHAN_API_KEY`: Broker API key.
- `DHAN_API_SECRET`: Broker API secret.
- `DHAN_API_BASE_URL`: `https://api.dhan.co`.
- `DHAN_AUTH_BASE_URL`: `https://auth.dhan.co`.
- `DHAN_REDIRECT_URL`: Broker OAuth callback URL.
- `DHAN_LIVE_DATA_ENABLED`: Boolean (set to `false`).
- `MARKET_DATA_PROVIDER`: Provider selector (`yfinance` default).
- `UPSTOX_ACCESS_TOKEN`: Upstox fundamentals token.
- `UPSTOX_API_BASE_URL`: `https://api.upstox.com`.

### Additional Cloud Variables Required:

#### Frontend (Cloudflare Pages):
- `VITE_API_BASE_URL`: URL of the deployed Render backend (e.g. `https://stock-intelligence-api.onrender.com`).
- `VITE_SUPABASE_URL`: Supabase project URL (e.g. `https://xyzcompany.supabase.co`).
- `VITE_SUPABASE_ANON_KEY`: Supabase client publishable anon key (safe for browser).

#### Backend (Render Free):
- `PORT`: Automatically provided by Render.
- `ENVIRONMENT`: Set to `production` (or `development`).
- `FRONTEND_ORIGIN`: Allowed Cloudflare Pages domain (e.g. `https://stock-intelligence.pages.dev`).
- `DATABASE_URL`: Supabase PostgreSQL connection string (Transaction pooler or Session pooler).
- `SUPABASE_URL`: Supabase project URL.
- `SUPABASE_ANON_KEY`: Supabase anon key (for token verification).
- `SUPABASE_JWT_SECRET`: Supabase JWT secret for high-performance signature verification.
- `SUPABASE_SERVICE_ROLE_KEY`: Supabase backend service role key (backend only, never exposed to browser).

---

## 8. External Dependencies & Package Auditing

### Backend (`requirements.txt`):
- Currently installed: `fastapi`, `uvicorn`, `pydantic`, `pandas`, `numpy`, `yfinance`, `python-dotenv`, `httpx`, `keyring`.
- Required additions:
  - `psycopg2-binary>=2.9.9` (PostgreSQL adapter)
  - `PyJWT[crypto]>=2.9.0` (Cryptographic JWT signature verification)

### Frontend (`package.json`):
- Currently installed: `react`, `react-dom`, `lightweight-charts`.
- Required additions:
  - `@supabase/supabase-js>=2.45.0` (Official Supabase authentication client)

---

## 9. Background Jobs & Scheduled Tasks

- **Dhan WebSocket Feed (`dhan_ws_client.py`):** Configured with `live_data_enabled = False`. Background thread remains in `DISABLED` state; no connection or reconnection loop runs.
- **Alert Evaluation (`alerts_watchlist_service.py`):** Operates on-demand via REST endpoint `/api/market/alerts/evaluate`. Does NOT require a 24/7 background cron job, making it 100% compatible with Render Free tier sleeping behavior.
- **Render Free Tier Sleep Consideration:** Render Free web services spin down after 15 minutes of inactivity. When the user visits the Cloudflare Pages frontend, the first API request will wake up Render within ~30–50 seconds. This is standard and expected for ₹0 budget hosting.

---

## 10. Local Filesystem Assumptions & Ephemeral Storage Safeguards

1. **SQLite Database (`backend/data/stock_intelligence.db`):** 
   - Render's container filesystem is ephemeral: any changes written to disk are erased upon restart or redeployment.
   - Migrating user data and state to Supabase PostgreSQL permanently decouples data storage from the ephemeral container.
2. **Local `.env` File Reading:**
   - In `backend/app/config.py`, configuration is read directly from process environment variables (`os.environ`), which Render sets at the platform level.
3. **Local Credential Storage (`keyring`):**
   - On Linux containers without a desktop D-Bus session, `keyring` falls back gracefully to in-memory mode without crashing.

---

## 11. Migration & Implementation Phasing Plan

```
  [Phase A: Audit] (COMPLETE)
         │
         ▼
  [Phase B: Git & Secrets Protection] (.gitignore, .env.example, git clean check)
         │
         ▼
  [Phase C: Frontend Cloud Readiness] (VITE_API_BASE_URL, Supabase Auth UI, _redirects)
         │
         ▼
  [Phase D: Backend Cloud Readiness] (0.0.0.0 bind, CORS, Render config, JWT middleware)
         │
         ▼
  [Phase E: Database Migration] (PostgreSQL DDL, SQLite export/import script, backup)
         │
         ▼
  [Phase F: Supabase Auth & RLS] (User ownership column, RLS policies, JWKS verification)
         │
         ▼
  [Phase G & H: Env & Task Safety] (Config templates, Render sleep tolerance)
         │
         ▼
  [Phase I & J: Testing & Packaging] (Full pytest suite, frontend build, deployment tests)
         │
         ▼
  [Phase K & L: Documentation & Delivery] (CLOUD_DEPLOYMENT_GUIDE.md, final report)
```

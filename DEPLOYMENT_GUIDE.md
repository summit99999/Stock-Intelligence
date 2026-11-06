# Stock Intelligence Pro — Zero-Cost Cloud Deployment Guide
## Phase 13: Cloudflare Pages + Render + Supabase + Private GitHub

---

## 1. Architecture & Free-Tier Specifications

Stock Intelligence Pro is designed for **100% zero-cost cloud deployment** with private single-user access from any device (laptop, tablet, phone) without requiring your local workstation to remain powered on.

```
+-----------------------------------------------------------------------------+
|                          OPERATOR BROWSER / MOBILE                          |
|                       https://<your-app>.pages.dev                          |
+--------------------------------------|--------------------------------------+
                                       |
                   +-------------------+-------------------+
                   | HTTPS                                 | HTTPS
                   v                                       v
+--------------------------------------+   +----------------------------------+
|          CLOUDFLARE PAGES            |   |          SUPABASE AUTH           |
|            Free Tier                 |   |            Free Tier             |
|  - React 18 + Vite SPA               |   |  - Email/Password Operator Auth  |
|  - Global AnyCast Edge CDN           |   |  - JWT HS256 Token Minting       |
|  - SPA rewrite: /* -> /index.html    |   |  - Ephemeral user sessions       |
+--------------------------------------+   +----------------------------------+
                   |                                       |
                   | REST API                              | Bearer <JWT>
                   v                                       v
+-----------------------------------------------------------------------------+
|                                 RENDER                                      |
|                       Free Web Service (Python 3.12)                        |
|  - FastAPI ASGI application on Uvicorn                                      |
|  - Automatic zero-trust Supabase JWT validation on every private request    |
|  - Port dynamic binding via $PORT                                           |
|  - Dual-mode database layer (PostgreSQL in cloud, SQLite locally)           |
+--------------------------------------|--------------------------------------+
                                       |
                                       | SSL / pgBouncer Pool
                                       v
+-----------------------------------------------------------------------------+
|                          SUPABASE POSTGRESQL 16                             |
|                                 Free Tier                                   |
|  - 19 Tables (Reference, OHLCV, Fundamentals, User-Scoped Assets)           |
|  - Row Level Security (RLS) enabled on all tables                           |
|  - Automatic user isolation (`auth.uid() = user_id`)                        |
|  - 500 MB storage capacity (app currently utilizes < 5 MB)                 |
+-----------------------------------------------------------------------------+
```

### Cost & Resource Constraints Summary

| Component | Platform | Plan | Monthly Cost | Limitations & Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend** | Cloudflare Pages | Free | **₹0.00** | Unlimited bandwidth, 500 builds/month, global edge network. |
| **Backend API** | Render | Free Web Service | **₹0.00** | 512 MB RAM, 0.1 CPU, spins down after 15m inactivity (~40s cold start). |
| **Database & Auth** | Supabase | Free Tier | **₹0.00** | 500 MB PostgreSQL 16, 50,000 MAUs, full RLS, pgBouncer pooler. |
| **Source Control** | GitHub | Free | **₹0.00** | Private repository, automatic webhook deploys. |
| **Total Cost** | — | — | **₹0.00 / month** | **Strictly ₹0 expenditure guaranteed.** |

---

## 2. Operator Setup Walkthrough (Step-by-Step)

Follow these steps sequentially to deploy your application.

### STEP 1: Push Code to a Private GitHub Repository

1. Open [GitHub](https://github.com/new) and create a **New Repository**:
   - Repository name: `stock-intelligence-pro` (or any name you choose)
   - Visibility: **Private** (do NOT choose Public)
   - Do NOT initialize with a README, `.gitignore`, or license (the workspace already has these).
2. On your local machine, open terminal in `D:\ST\Stock-Intelligence-Starter\Stock-Intelligence`:
   ```bash
   # 1. Verify git status and check that sensitive files are ignored
   git status

   # 2. Add remote and push to your private GitHub repo
   git remote add origin https://github.com/<your-username>/stock-intelligence-pro.git
   git branch -M main
   git push -u origin main
   ```
   > [!NOTE]
   > The repository's root `.gitignore` strictly prevents any `.env`, `.env.*`, `*.db`, `*.sqlite*`, `backups/`, or build artifacts from being committed.

---

### STEP 2: Set Up Supabase (Database & Authentication)

1. Sign up or log in to [Supabase](https://supabase.com).
2. Click **New Project**:
   - **Name**: `stock-intelligence-db`
   - **Database Password**: Generate and securely store a strong password.
   - **Region**: Choose `South Asia (Mumbai)` or `Southeast Asia (Singapore)` for lowest latency to Indian market systems.
   - **Pricing Plan**: Free (₹0/month).
3. Initialize the Database Schema:
   - In the left sidebar of your Supabase dashboard, click **SQL Editor**.
   - Click **New Query**.
   - Open [`database/supabase_migrations.sql`](file:///D:/ST/Stock-Intelligence-Starter/Stock-Intelligence/database/supabase_migrations.sql) in your code editor, copy the entire file contents, and paste them into the SQL Editor.
   - Click **Run**.
   - Verify that all 19 tables, indexes, and RLS policies are created successfully with no errors.
4. Create Your Operator Account:
   - In the left sidebar, click **Authentication** -> **Users**.
   - Click **Add User** -> **Create User**.
   - Enter your email address and a strong private password.
   - Click **Auto-confirm user** (enables immediate sign-in without waiting for email verification).
   - Once created, copy the **User UID** (a UUID like `e7f82b8a-1234-4567-890a-bcdef1234567`) — you will use this during data migration.
5. Collect Supabase Connection Credentials:
   - Click **Project Settings** (gear icon) -> **API**:
     - **Project URL**: `https://<project-ref>.supabase.co`
     - **Project API Keys**: Copy `anon` (public key).
     - **JWT Settings**: Copy `JWT Secret`.
   - Click **Project Settings** -> **Database**:
     - Under **Connection string**, select **URI**.
     - Choose **Transaction** or **Session** pooler mode (port 6543 or 5432).
     - Replace `[YOUR-PASSWORD]` with your database password:
       `postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres`

---

### STEP 3: Deploy Frontend to Cloudflare Pages

1. Log in to the [Cloudflare Dashboard](https://dash.cloudflare.com/) and navigate to **Workers & Pages**.
2. Click **Create Application** -> **Pages** tab -> **Connect to Git**.
3. Select your private GitHub repository `stock-intelligence-pro`.
4. Configure Build Settings:
   - **Project Name**: `stock-intelligence-pro` (results in `https://stock-intelligence-pro.pages.dev`)
   - **Production Branch**: `main`
   - **Framework Preset**: `Vite` (or None)
   - **Root Directory**: `frontend`
   - **Build Command**: `npm run build`
   - **Build Output Directory**: `dist`
5. Configure Environment Variables (click **Environment Variables** under build settings):
   | Variable | Value | Description |
   | :--- | :--- | :--- |
   | `VITE_API_BASE_URL` | `https://stock-intelligence-api.onrender.com` | URL of your backend on Render |
   | `VITE_SUPABASE_URL` | `https://<project-ref>.supabase.co` | Your Supabase project URL |
   | `VITE_SUPABASE_ANON_KEY` | `<your-supabase-anon-key>` | Your Supabase public anon key |
6. Click **Save and Deploy**. Cloudflare Pages will build and deploy your frontend in ~60 seconds.
7. Note down your production URL: `https://<your-project>.pages.dev`.

---

### STEP 4: Deploy Backend to Render

1. Sign up or log in to [Render](https://render.com).
2. Click **New +** -> **Web Service**.
3. Connect your private GitHub repository `stock-intelligence-pro`.
4. Configure the Web Service:
   - **Name**: `stock-intelligence-api`
   - **Region**: Oregon, USA (or closest available free region)
   - **Branch**: `main`
   - **Root Directory**: *(leave blank — runs from project root)*
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r backend/requirements.txt`
   - **Start Command**: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type**: `Free`
5. Configure Environment Variables (click **Environment Variables**):
   | Key | Value | Notes |
   | :--- | :--- | :--- |
   | `PYTHON_VERSION` | `3.12.10` | Enforces exact Python version |
   | `DATABASE_URL` | `<your-supabase-postgresql-uri>` | From Supabase Database Settings |
   | `SUPABASE_URL` | `https://<project-ref>.supabase.co` | From Supabase API Settings |
   | `SUPABASE_JWT_SECRET` | `<your-supabase-jwt-secret>` | From Supabase API Settings |
   | `FRONTEND_ORIGIN` | `https://<your-project>.pages.dev` | Your Cloudflare Pages domain |
   | `DHAN_LIVE_DATA_ENABLED` | `false` | Keeps live websocket dormant |
6. Click **Create Web Service**. Render will install requirements and start your FastAPI service.
7. Once started, verify health by opening `https://stock-intelligence-api.onrender.com/api/health` in your browser. It should return:
   ```json
   {"status": "ok"}
   ```

---

### STEP 5: Migrate Data from SQLite to Supabase PostgreSQL

Once your Supabase database is online, run the built-in migration utility from your local terminal to transfer all 299+ records, historical bars, fundamental statements, and custom watchlists:

1. **Perform Dry-Run Inspection**:
   ```bash
   python backend/app/migrate_to_postgres.py --dry-run
   ```
   *Verifies local database integrity and creates an automatic timestamped backup in `backups/`.*

2. **Execute Full Migration to Supabase**:
   ```bash
   python backend/app/migrate_to_postgres.py --database-url "<YOUR_SUPABASE_DATABASE_URL>" --user-id "<YOUR_SUPABASE_USER_UID>"
   ```
   *Migrates all 19 tables in topological order using parameterized batch inserts with `ON CONFLICT DO NOTHING`.*

3. **Verify Destination Counts**:
   ```bash
   python backend/app/migrate_to_postgres.py --database-url "<YOUR_SUPABASE_DATABASE_URL>" --verify
   ```

---

## 3. Post-Deployment Verification Checklist

Verify your cloud deployment by completing these quick checks:

- [ ] **Backend Health Check**: Open `https://<your-api>.onrender.com/api/health` -> returns `{"status": "ok"}`.
- [ ] **System Status**: Open `https://<your-api>.onrender.com/api/system/status` -> returns database `postgresql` and auth mode `supabase_jwt`.
- [ ] **Frontend Loading**: Open `https://<your-app>.pages.dev` -> loads the dark terminal interface.
- [ ] **Authentication Gateway**: The application prompts for your operator email and password.
- [ ] **Operator Login**: Sign in with the credentials created in Step 2 -> authentication succeeds, user email appears in topbar with a Sign Out button.
- [ ] **Market Data & Watchlists**: Navigate to Watchlist & Scanners -> verify that large-cap stocks, NIFTY indices, and technical indicators display properly.
- [ ] **Interactive Charts**: Open VolumeLens interactive chart -> verify candlestick rendering, volume bars, and MA overlays.
- [ ] **Create Trade Plan**: Create a new trade plan under Unified Research -> verify it saves successfully to Supabase and is persisted under your authenticated user ID.
- [ ] **Mobile Responsive**: Open `https://<your-app>.pages.dev` on your smartphone -> confirm touch-friendly layout and smooth scrolling.

---

## 4. Cold Starts, Sleep Cycles & Best Practices

1. **Render Free Tier Spin-Down**:
   - Render's free tier spins down services after 15 minutes of inactivity.
   - When you access the application after a dormant period, the initial API call may take **30 to 45 seconds** to respond while the container boots.
   - Once awake, the container remains active for all subsequent requests.
   - The frontend automatically retries initial status checks with a loading indicator.
2. **Supabase Inactivity Pausing**:
   - Supabase Free tier projects pause after 7 consecutive days of zero database activity.
   - Simply opening your application once a week keeps the Supabase project active indefinitely.
3. **Data Safety**:
   - Your local SQLite database `backend/data/stock_intelligence.db` remains 100% untouched and functional.
   - You can switch between local SQLite development and cloud PostgreSQL anytime by toggling `DATABASE_URL`.

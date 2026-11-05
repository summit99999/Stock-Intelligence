# Stock Intelligence Pro

A sophisticated personal Indian equity market analysis and quantitative intelligence platform inspired by **VolumeLens**, **TradingView**, and institutional **Smart Money Concepts (SMC)** trading terminals.

Built for personal equity research on Indian markets (NSE & BSE) with real quantitative calculations, technical indicators, multi-year financial statements, volume profiling, order flow estimation, Smart Money Concepts / Order Block analysis, and strict data truthfulness.

---

## Key Highlights & Features

### 1. Data Truthfulness & Provider Abstraction
- **Dual Data Engine**: Runs out-of-the-box with **yfinance** (zero-cost, historical OHLCV, no subscription required) and integrates with **DhanHQ** for live tick-by-tick streaming when credentials are configured.
- **Provider Switching**: Configure provider preference via `MARKET_DATA_PROVIDER=yfinance` (default) or `dhan`.
- **Honest Labeling**: Real exchange data is marked `LIVE`; derived indicators and proxy calculations are explicitly labeled `ESTIMATED`; offline/fallback data is labeled `DEMO` or `HISTORICAL`.
- **Safety First**: Personal analysis platform only. Automated order placement or broker execution is intentionally absent.

### 2. 16 Institutional Workspace Modules

#### Core Analysis & Intelligence
1. **Dashboard**: High-level market pulse with benchmark indices (NIFTY 50, BANK NIFTY, SENSEX, INDIA VIX), live market breadth meter, sector rotation tracks, and top movers.
2. **Market Overview**: Advance/decline breadth metrics, interactive sector heatmap, gainers, losers, and unusual volume (RVOL) leaderboards.
3. **Stock Scanner**: Screen 30+ NSE stocks with 20+ technical indicators and fundamental metrics. Includes the signature **VolumeLens 7-Point Breakout Strategy** and 8 institutional presets.
4. **Technical Analysis**: Interactive candlestick and volume charts powered by **TradingView Lightweight Charts v5**. Features SMA 20/50, EMA 20, Wilder's RSI, MACD, ADX, Supertrend, and historical returns (1D to 1Y) with toggleable **SMC overlays** (OB, FVG, LIQ, EQ).
5. **Volume Analytics**: Horizontal Volume Profile distribution across price tiers, automated calculation of Point of Control (POC), Value Area High (VAH), Value Area Low (VAL, 70% volume), and Volume-Weighted Average Price (VWAP).
6. **Footprint & Order Flow**: Multi-level candle footprints with Bid × Ask volume clusters, buying/selling volume imbalances ($>1.5\times$), bar delta, and Cumulative Volume Delta (CVD) tracking.
7. **Fundamental Research**: Deep 5-year financial statements (P&L, Balance Sheet, Cash Flow), DuPont ROE breakdown, Screener.in CSV import, peer valuation matrix, and 100-point institutional quality scorecard.
8. **AI Mentor**: Rule-grounded quantitative trading auditor. Generates a 12-factor checklist evaluating trend alignment, volume expansion, POC support, solvency, and setup viability.
9. **Trade Planner**: Institutional position sizing and risk management calculator. Calculates exact shares, maximum risk in ₹, total capital outlay, and Risk-to-Reward (R:R) ratio.
10. **Watchlist**: Persistent watchlist manager with sector filtering, column sorting, 52-week high/low metrics, and direct links to charts and research.
11. **Alerts**: Price cross, RSI overbought/oversold, and volume spike alert rules with simulation triggers and historical event logging.
12. **Settings**: Real-time provider status, Dhan credential presence diagnostic, Windows Vault keyring inspection, live WebSocket toggle, and cache management.

#### Smart Money Concepts (SMC) & Order Blocks
13. **Market X-Ray**: Market-wide stock ranking dashboard with dual independent Bullish and Bearish boards, Normalized ADR 50-day expansion scores, Choppiness penalty, and sector strength aggregation.
14. **Order Block Board**: Dedicated live Order Block terminal displaying Bullish/Bearish institutional zones, Displacement ATR ratios, Volume expansion, retest counts, and lifecycle tracking (`FRESH` -> `TESTED` -> `MITIGATED` -> `INVALIDATED`).
15. **Smart Money Concepts (SMC)**: Deep-dive quantitative suite with:
    - **Market Structure**: Non-repainting Swing Pivots (HH, HL, LH, LL) and confirmed Break of Structure (BOS) vs Change of Character (CHoCH).
    - **Supply & Demand Zones**: DBR, RBD, RBR, and DBD base zone recognition.
    - **Fair Value Gaps (FVG)**: 3-candle imbalance zones with real-time fill % progress tracking.
    - **Liquidity Mapping**: Equal Highs (EQH), Equal Lows (EQL), benchmark levels (PDH, PDL, PWH, PWL), and confirmed liquidity sweep detection.
    - **Premium vs Discount**: Active dealing range with 50% Equilibrium marker and buyer/seller percentile zones.
    - **Institutional Setup Scorecard**: 100-point confluence index across 7 weighted institutional factors.
16. **SMC Backtest & Quantitative Integrity**: Chronological simulation and validation engine featuring:
    - **5 Independent Strategies**: `ORDER_BLOCK_RETEST`, `FVG_FILL_REVERSAL`, `BOS_CONTINUATION`, `LIQUIDITY_SWEEP_REVERSAL`, and `SMC_VOLUME_CONFIRMATION`.
    - **Non-Repainting Multi-Dimensional Timestamps**: Strict separation of `occurrence`, `confirmation`, and `signal_available` prevents look-ahead bias.
    - **Realistic Execution Engine**: Next executable candle entry, conservative same-bar resolution (Stop Loss evaluated prior to Take Profit), and gap execution.
    - **Indian Statutory Cost Model**: Realistic equity charges modeling (Brokerage, STT, NSE Exchange turnover fees, SEBI turnover charges, Stamp Duty, and 18% GST).
    - **Walk-Forward Regime Breakdown**: Out-of-sample stress testing across 5 market conditions (`BULLISH`, `BEARISH`, `SIDEWAYS`, `HIGH_VOLATILITY`, `LOW_VOLATILITY`).
    - **Parameter Sensitivity Grid**: Multi-dimensional parameter perturbation evaluating stability across Target R:R and holding periods.
    - **Market Data Quality Audit**: Automated health check for zero-volume, missing bars, and data truthfulness reporting.

---

## Project Architecture

```
Stock-Intelligence/
├── backend/
│   ├── app/
│   │   ├── config.py                   # Environment & credential management
│   │   ├── database.py                 # SQLite engine & database queries
│   │   ├── fundamental_db.py           # Multi-year financial tables
│   │   ├── main.py                     # FastAPI application & lifespan management
│   │   ├── providers/                  # Data-provider abstraction layer
│   │   │   ├── base.py                 # DataProvider abstract interface
│   │   │   ├── manager.py              # Provider registration & fallback orchestrator
│   │   │   ├── yfinance_provider.py    # Zero-cost Yahoo Finance integration
│   │   │   └── dhan_provider.py        # DhanHQ REST & scrip integration
│   │   ├── routers/                    # REST API endpoints
│   │   │   ├── stocks.py               # Stock universe & historical candles
│   │   │   ├── screener.py             # Advanced screening & presets
│   │   │   ├── market_data.py          # Background updates & provider status
│   │   │   ├── volume_analytics.py     # Volume Profile & Order Flow APIs
│   │   │   ├── ai_planner.py           # AI Mentor Audit & Trade Planner APIs
│   │   │   ├── fundamentals.py         # Financial statements & 100-pt scorecard
│   │   │   ├── smc.py                  # Smart Money Concepts, Order Blocks & Backtest APIs
│   │   │   └── market_feed.py          # WebSocket client & dispatcher
│   │   ├── schemas/                    # Pydantic data models
│   │   └── services/                   # Quantitative calculation engines
│   │       ├── indicators.py           # 20+ Technical indicators & consolidation
│   │       ├── volume_profile_service.py # POC, VAH, VAL, VWAP engine
│   │       ├── order_flow_service.py   # Footprint & CVD engine
│   │       ├── quality_score_service.py# 100-pt fundamental score engine
│   │       ├── smc_service.py          # Core SMC, OB, FVG, Liquidity & Setup Score engine
│   │       ├── market_xray_service.py  # Market X-Ray Dual Boards & Sector engine
│   │       ├── smc_backtest_service.py # Walk-forward chronological backtest engine
│   │       └── data_quality_service.py # Market data health & truthfulness audit
│   ├── tests/                          # 239 passing pytest test suite (0 failures, 4 skipped)
│   ├── requirements.txt
│   └── stock_intelligence.db           # SQLite persistent store
│
└── frontend/
    ├── src/
    │   ├── api/                        # Typed API clients
    │   ├── components/                 # 16 Pro Terminal Views
    │   │   ├── TradingViewChart.tsx    # Lightweight Charts v5 with SMC overlays
    │   │   ├── MarketOverview.tsx      # Indices, sectors & market breadth
    │   │   ├── StockScreener.tsx       # Multi-factor stock scanner
    │   │   ├── TechnicalAnalysisView.tsx# Technical gauges & overlays
    │   │   ├── VolumeAnalyticsView.tsx # Volume profile & POC analyzer
    │   │   ├── FootprintOrderFlowView.tsx # Bid x Ask footprint & CVD
    │   │   ├── CompanyResearch.tsx     # 5-year financials & scorecard
    │   │   ├── AIMentorView.tsx        # Quantitative 12-factor audit
    │   │   ├── TradePlannerView.tsx    # Position sizing & risk calculator
    │   │   ├── WatchlistView.tsx       # Persistent watchlist manager
    │   │   ├── AlertsView.tsx          # Price & indicator alerts
    │   │   ├── SettingsView.tsx        # Provider & system diagnostics
    │   │   ├── MarketXRayView.tsx      # Dual Bullish/Bearish boards & Breadth
    │   │   ├── OrderBlockBoardView.tsx # Dedicated live Order Block terminal
    │   │   ├── SmartMoneyConceptsView.tsx# Structure, FVG, Liquidity & Scorecard
    │   │   └── SMCBacktestView.tsx     # Walk-forward simulation & equity curve
    │   ├── App.tsx                     # App shell & 16-module navigation
    │   └── style.css                   # Dark theme design system
    ├── package.json
    └── vite.config.ts
```

---

## Quickstart Guide

### Prerequisites
- Windows 10/11
- Python 3.12+
- Node.js 18+ and npm

---

### Step 1: Start Backend (FastAPI)

In PowerShell:
```powershell
cd backend

# Activate existing virtual environment (or create with: python -m venv .venv)
.\.venv\Scripts\Activate.ps1

# Install dependencies if not already installed
pip install -r requirements.txt

# Start FastAPI server
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Backend API: `http://127.0.0.1:8000`
- Interactive API Docs (Swagger): `http://127.0.0.1:8000/docs`

---

### Step 2: Start Frontend (React + Vite)

In a second terminal:
```powershell
cd frontend

# Install packages if not already installed
npm install

# Start Vite dev server
npm run dev
```

Open your browser to: `http://localhost:5173`

---

### Step 3: Run Backend Tests

```powershell
# In the backend directory:
$env:PYTHONPATH='backend'
.\.venv\Scripts\pytest backend\tests -v
```

*Results*: **239 passed, 4 skipped, 0 failures**.

---

### Step 4: Build Production Frontend

```powershell
# In the frontend directory:
npm run build
```

---

## Configuration & Optional DhanHQ Live Feed

Create or edit `backend/.env`:
```ini
# Core Market Data Provider (yfinance or dhan)
MARKET_DATA_PROVIDER=yfinance

# DhanHQ Live Data (Optional - leave false for zero cost)
DHAN_LIVE_DATA_ENABLED=false

# Optional DhanHQ API Credentials (if using Dhan live feed)
DHAN_CLIENT_ID=your_client_id
DHAN_API_KEY=your_api_key
DHAN_API_SECRET=your_api_secret
DHAN_REDIRECT_URL=http://127.0.0.1:8000/api/dhan/oauth/callback
```

When `DHAN_LIVE_DATA_ENABLED=false`, the system uses `yfinance` and internal models, completely eliminating any external API billing or rate limits.

---

## License & Disclaimer
This software is intended strictly for personal financial education, equity research, and quantitative analysis. It does not provide investment advice or automated order execution. Always perform independent due diligence before making financial decisions.

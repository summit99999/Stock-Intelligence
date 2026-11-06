# STOCK INTELLIGENCE PRO — PROJECT STATUS

**Last Updated:** November 6, 2026 (Phase 14.6 Pilot Complete & Verified)  
**Current Milestone:** Phase 14.6 — NSE Closing Auction Session (CAS) Aware Validation & Observed Intraday Pilot (COMPLETE AND VERIFIED)  
**Next Milestone:** Phase 15 — Universe Ingestion Expansion (31 Tracked Equities) / Frontend Enhancements  
**Overall System Health:** All systems operational. 2,658 observed 5-minute bars verified; True Time-of-Day RVOL active on observed baseline; full test suite passing (507 passed, 4 skipped).  

---

## 1. Test Suite & Build Verification

| Component | Status | Details |
| :--- | :--- | :--- |
| **Backend Regression Suite** | **507 Passed, 4 Skipped, 0 Failures** | Full regression suite completed across 511 tests with zero failures. Four live Dhan network tests remain skipped. |
| **Frontend TypeScript & Build** | **PASSED** | `tsc && vite build` completed with zero errors after Phase 14.6 CAS schedule and regulatory disclosures. |
| **Observed Intraday Market Data** | **VERIFIED (3 STOCKS)** | Ingested 2,658 observed 5-minute bars across 36 sessions (12 sessions for RELIANCE, TCS, HDFCBANK). 100% session completeness under NSE CAS schedule. |
| **True Time-of-Day RVOL** | **VERIFIED** | Active and grounded on genuine observed baseline for RELIANCE, TCS, and HDFCBANK. Correctly reports UNAVAILABLE for un-ingested stocks. |
| **Synthetic Data Isolation** | **VERIFIED** | Exactly 46,500 synthetic 5m bars preserved intact in `ohlcv`. Database queries enforce date-level suppression on observed dates, preventing synthetic contamination. |
| **Trading Calendar Grounding** | **VERIFIED** | Authoritative grounding in NSE circulars `NSE/CMTR/72394`, `NSE/CMTR/73362`, and `NSE/CMTR/74466`. Continuous trading ends at 15:15:00 IST (72 bars) for F&O equities. |
| **Security Audit Status** | **AUDITED & HARDENED** | All 10 security areas audited in `PHASE_13_1_SECURITY_AUDIT.md`. IDOR vulnerabilities eliminated, algorithm allowlisting enforced, broker endpoints protected, safe SQL tokenizer implemented. Decision: **A. READY FOR CONTROLLED DEPLOYMENT**. |
| **Multi-Tenant Isolation** | **VERIFIED** | Strict user ownership isolation across watchlists, alerts, custom scanners, screener presets, research trade plans, and qualitative notes verified by `backend/tests/test_two_user_isolation.py`. |
| **Safe SQL Parameter Tokenizer** | **VERIFIED** | Stateful character tokenizer `safe_replace_placeholders` guarantees `?` within string literals and SQL comments is never corrupted during PostgreSQL `%s` translation. |
| **Cloud Deployment Architecture** | **VERIFIED** | Zero-cost cloud topology: Cloudflare Pages Free (Frontend SPA) + Render Free Web Service (FastAPI) + Supabase Free (PostgreSQL 16 + Auth) + Private GitHub repo. Guaranteed ₹0/month budget. |
| **Dual-Mode Database Layer** | **VERIFIED** | Seamless runtime adaptation: PostgreSQL in cloud (via `DATABASE_URL`) with transparent parameter adaptation (`?` -> `%s`), `INSERT OR REPLACE` to PostgreSQL UPSERT (`ON CONFLICT DO UPDATE`), and `DbRow` dual index/key access. Local SQLite mode preserved 100% intact. |
| **Private Authentication Engine** | **VERIFIED** | Asymmetric JWKS (`RS256`, `ES256`) and legacy symmetric (`HS256`) verification. Rejects `alg="none"`. Production fail-closed enforcement. Sensitive token bytes masked in all logs. |
| **Database Migration Engine** | **VERIFIED** | Automated pre-migration SQLite backup generation, topological batch ingestion across all 19 tables with `ON CONFLICT DO NOTHING`, dry-run mode, and row verification report. |
| **Unified Research Engine** | **VERIFIED** | 7-factor 100-point setup scoring: Market Regime (10), Sector Rotation (10), Fundamental Quality (15), Trend/Momentum (20), Volume Confirmation (15), Market Structure/SMC (20), Multi-Timeframe (10). Missing metrics yield 0 points. Mandatory heuristic disclaimer distinguishing confluence rating from statistical probability. |
| **Trade Plan Generator** | **VERIFIED** | Quantitative trade plan with Entry Zone, Ideal Entry, Structural Stop Loss, Target 1, Target 2, Invalidation Condition, Capital/Risk % Position Sizing, and Invalid Stop Distance Guardrail (quantity set to 0 with explicit warning). Mandatory hypothetical research disclosure. |
| **Historical Setup Validator** | **VERIFIED** | Non-repainting backtest validation across 5 setup strategies with 95% Wilson Score CI, Profit Factor, Drawdown, Regime Dependence Breakdown, and Sample Size Reliability Flag (< 30 trades flagged as statistically unverified). |
| **Trade Plans & Notes Persistence** | **VERIFIED** | Persistent SQLite storage for research trade plans (`research_trade_plans`) and qualitative notes (`research_notes`) with complete CRUD and status tracking (`MONITORING`, `TARGET_1_HIT`, `TARGET_2_HIT`, `INVALIDATED`, `EXPIRED`). |
| **Unified Research Dashboard UI** | **VERIFIED** | Comprehensive dark terminal interface (`UnifiedResearchDashboardView.tsx`) delivering all 10 required analytical sections and interactive stock research dossier modal. |
| **DataMode Taxonomy & Truthfulness** | **VERIFIED** | Enforced 7 standard modes: `LIVE`, `DELAYED`, `HISTORICAL`, `SIMULATED`, `ESTIMATED`, `STALE`, `UNAVAILABLE`. Historical sources (`yfinance`, `sqlite`, `demo`) can NEVER be labeled as `LIVE`. Dhan inactive status accurately reported. |
| **Index Grounding & INDIA VIX Unavailability** | **VERIFIED** | Grounded indices (`NIFTY 50`, `BANK NIFTY`, `NIFTY 500`, `NIFTY MIDCAP`) explicitly labeled `data_mode="ESTIMATED"`, `is_estimated=True`, `status="ESTIMATED"`. `INDIA VIX` explicitly reported as `UNAVAILABLE` (`numeric_value=None`, `data_mode="UNAVAILABLE"`). Dispersion proxy is NEVER misrepresented as actual INDIA VIX. |
| **Stock Universe Coverage Transparency** | **VERIFIED** | Transparently reports configured vs tracked instruments (e.g. 31 of 500 constituents = 6.2% coverage for NIFTY 500). Excluded count and disclosure notes embedded in scanner and overview payloads. |
| **Fundamental Data Integrity & QoQ Growth** | **VERIFIED** | Missing fundamentals preserved as `None` (never fabricated as 0). Added quarterly QoQ revenue and PAT growth with strict zero/negative denominator guardrails. Documented reporting periods, provenance, and metric metadata. |
| **Backtesting Realism & Disclaimers** | **VERIFIED** | Embedded mandatory survivorship bias disclosures, corporate actions limitations, zero-lookahead next-bar execution confirmation, and statutory simulation notices in all backtest responses. |
| **Dual-Method Intraday RVOL** | **VERIFIED** | Separated Method A (Historical Time-of-Day RVOL against 20 prior sessions at exact HH:MM IST) and Method B (Linear Estimated RVOL = ADV20 × session fraction). Explicitly labeled as `ESTIMATED` when historical minute bars are absent. Never presented as historical time-of-day. |
| **Corrected Money Flow Terminology** | **VERIFIED** | Renamed to `close_location_buying_bias_pct`, `close_location_selling_bias_pct`, `money_flow_multiplier`, `chaikin_money_flow_20`. Disclosed as OHLCV-derived estimates, NOT buyer/seller initiated trade tape. CMF kept as separate volume-weighted indicator. |
| **Removal of Institutional Claims** | **VERIFIED** | Replaced OHLCV-derived claims with qualified price-volume terminology (`PRICE_ADVANCE_HIGH_VOLUME`, `PRICE_DECLINE_HIGH_VOLUME`, `HIGH_VOLUME_CONSOLIDATION_CHURN`, `LIGHT_VOLUME_BREAKOUT_UNCONFIRMED`, `BALANCED_VOLUME_PARTICIPATION`). Institutional flow explicitly marked `UNAVAILABLE` without official exchange settlement records. |
| **Traded Value Accuracy** | **VERIFIED** | Distinguishes `ACTUAL_TURNOVER` (when reported from exchange feed) from `ESTIMATED_TURNOVER` (Volume × LTP) and `UNAVAILABLE`. Disclosed in table rankings and stock analysis cards. |
| **Money Flow & Volume Intelligence** | **VERIFIED** | Full 8-section institutional dashboard: Market Overview, Money Flow Summary (Buying vs Selling pressure %), Top Volume Gainers (RVOL-ranked), Top Price Gainers/Losers, 4 Combined Volume+Price Screening Categories, Sector Rotation Matrix, and Deep-Dive Stock Analysis. |
| **Daily Volume & Intraday RVOL** | **VERIFIED** | Today's Volume, ADV 10, ADV 20, ADV 50, Volume Change % `((Vol/ADV20)-1)*100`, Daily RVOL `Vol/ADV20`, and IST Session Time-Adjusted Intraday RVOL `Vol/(ADV20*Fraction)` with explicit progress label. |
| **Market Intelligence Dashboard** | **VERIFIED** | Real market breadth (advances/declines/unchanged, A/D ratio, breadth %), 5 benchmark indices (NIFTY 50, BANK NIFTY, NIFTY 500, NIFTY MIDCAP, INDIA VIX), 52-week extremes, composite market regime rating (score 0-100), and volatility regime. |
| **Sector Intelligence & Rotation** | **VERIFIED** | Deep sector performance rankings, sector breadth %, relative strength vs NIFTY 50 benchmark, 4 rotation quadrants (Leading, Weakening, Lagging, Improving), sector leaders and laggards. |
| **Advanced Multi-Condition Scanner** | **VERIFIED** | Multi-timeframe technical conditions (EMA 20/50/200, RSI, MACD, ADX, Supertrend, RVOL, BB Squeeze) combined with fundamental growth/quality (ROE, ROCE, Debt/Equity, Profit Growth, OPM) using configurable AND/OR logic. |
| **7 Institutional Ranking Systems** | **VERIFIED** | Bullish Opportunity, Bearish Weakness, Breakout Candidates, Breakdown Candidates, High Relative Strength, High-Volume Accumulation, Consolidation Candidates with transparent scores (0-100) and rationale. |
| **Persistence & Multi-Watchlists** | **VERIFIED** | Saved Custom Scanners (`saved_custom_scanners`), Persistent Multi-Watchlists (`custom_watchlists`) with real database quotes, and Automated Alert Rule Evaluation Engine (`market_alerts`, `market_alert_history`). |
| **Data Integrity & Coverage** | **VERIFIED** | Transparent instrument coverage disclosures across universes (`all`, `nifty50`, `nifty100`, `nifty500`, `fno`). Never claims unverified exchange coverage. Standardized `HISTORICAL` mode labeling. |

---

## 2. Summary of Completed Phases

### Phase 1 to Phase 8: Core Platform, Screeners & Broker Resilience
- Real SQLite persistence, Dhan broker OAuth/consent lifecycle, and token auto-refresh.
- Multi-source provider abstraction (`yfinance` default with fallback, zero-crash architecture).
- Deep fundamental engine with Screener.in CSV import, 5-year financials, DuPont ROE, and 100-pt scorecard.

### Phase 9 to Phase 9.3: Smart Money Concepts & Backtesting Integrity
- Non-repainting Market Structure (HH, HL, LH, LL, BOS, CHoCH) and Order Blocks (`FRESH`, `TESTED`, `MITIGATED`, `INVALIDATED`).
- Indian statutory cost model (STT, Stamp Duty, NSE Turnover charges, SEBI fees, DP charges, 18% GST).
- Walk-forward market regime stress testing and parameter sensitivity analysis.

### Phase 10 to Phase 10.1: VolumeLens-Inspired Advanced Chart Analysis & Hardening
- VolumeLens-style market scanner (Bullish, Bearish, Consolidation, Breakout, Breakdown, High RVOL, New Order Blocks).
- TradingView Lightweight Charts v5 integration with horizontal Volume Profile, dynamic S/R zones, and multi-timeframe consensus.
- Conventional Stan Weinstein Mansfield Relative Strength, standardized 4H NSE session bar resampling (240m full + 135m tail), and strict `CONFIRMED` vs `DEVELOPING` setup distinction across all 9 setup types.

### Phase 11: Professional Market Intelligence Dashboard & Advanced Scanner
- **Market Overview Dashboard (`MarketOverview.tsx` & `/api/market/intelligence/dashboard`)**:
  - Grounded benchmark indices (NIFTY 50, BANK NIFTY, NIFTY 500, NIFTY MIDCAP, INDIA VIX) calculated from component equity movements.
  - Market Breadth meter: Advances, Declines, Unchanged counts, Advance/Decline ratio, and percentage breadth.
  - 52-Week Highs & Lows: New 52W record highs/lows and stocks within 3% of 52W extremes.
  - Market Regime classification: Composite score (0-100), regime status (`STRONG_BULLISH`, `MODERATE_BULLISH`, `NEUTRAL`, `MODERATE_BEARISH`, `STRONG_BEARISH`), volatility regime (`LOW`, `NORMAL`, `ELEVATED`, `HIGH`).
- **Sector Intelligence (`/api/market/intelligence/sectors`)**:
  - Sector rankings sorted by daily change.
  - Relative strength vs NIFTY 50 benchmark.
  - Sector breadth (% advancing stocks per sector) and volume profile.
  - Sector rotation quadrant analysis (Leading, Weakening, Lagging, Improving).
  - Strongest and weakest stock per sector, breakout and breakdown counts.
- **Advanced Multi-Condition Scanner (`MarketScannerView.tsx` & `/api/scanner/advanced/scan`)**:
  - Universes: All Tracked Stocks, NIFTY 50, NIFTY 100, NIFTY 500, NSE F&O with transparent coverage counters (e.g. "Scanned 31 of 500 constituents tracked in database").
  - Technical filters: Price vs EMA 20/50/200, RSI min/max, MACD crossover, ADX strength, Supertrend, RVOL thresholds, volume expansion/contraction, Bollinger Band squeeze.
  - Fundamental filters: ROE %, ROCE %, Debt/Equity max, Profit Growth %, OPM %.
  - Logic modes: Configurable AND (all match) vs OR (any match).
  - 7 Institutional Ranking Systems with transparent rank scoring (0-100) and human-readable rationale.
  - Pagination (10/20/50 per page, total pages/records) and RFC 4180 CSV export.
- **Custom Scanner Builder & Persistence**:
  - Saved Custom Scanners in SQLite (`saved_custom_scanners`).
  - Create, save, run, and delete custom scans.
- **Persistent Multi-Watchlists (`WatchlistView.tsx` & `/api/watchlists`)**:
  - Multiple custom portfolios stored in SQLite (`custom_watchlists`).
  - Enriched with live/database price, RSI, RVOL, sector, and 52W range.
  - Add/remove symbols, create and delete watchlists.
- **Automated Alerts Evaluation Engine (`AlertsView.tsx` & `/api/alerts`)**:
  - Alert rules stored in SQLite (`market_alerts`) for Price Above/Below, RSI Above/Below, Volume Spike, 52W Breakout, EMA Crossover, OB Retest, FVG Retest.
  - Server-side rule evaluator (`POST /api/alerts/evaluate`) checking live technical and SMC conditions.
  - Persistent alert trigger history log (`market_alert_history`).

### Daily Volume Intelligence & Money Flow Extension
- **Daily Volume Intelligence Engine (`backend/app/services/money_flow_service.py` & `/api/money-flow`)**:
  - Rolling average volumes: 10-day, 20-day, and 50-day average daily volumes (ADV 10, ADV 20, ADV 50).
  - Volume change % vs 20-day average: `((Today's Volume / 20-Day Average Volume) - 1) * 100`.
  - Daily RVOL: `Today's Volume / 20-Day Average Volume`.
  - Time-adjusted Intraday RVOL: `Today's Cumulative Volume / (ADV 20 * Session Progress Fraction)` with explicit label e.g. `Intraday Time-Adjusted (Xm of 375m, Y%)` during trading hours or `Full Session (EOD Historical)` outside hours.
  - Traded Value in ₹ and ₹ Cr (`Today's Volume * LTP`).
- **Money Flow & Buying/Selling Pressure**:
  - Money Flow Multiplier (MFM) = `((Close - Low) - (High - Close)) / (High - Low)`.
  - Buying Pressure % = `((MFM + 1) / 2) * 100` and Selling Pressure % = `100 - Buying Pressure`.
  - Chaikin Money Flow (CMF 20) over 20 periods.
  - Price-Volume Divergence detection (Bullish Divergence, Bearish Divergence, or None).
  - Delivery percentage tracking with truthful fallback (`Exchange Delivery N/A (Traded Volume Tape)`).
- **Strict 8-Section Dashboard Layout (`MoneyFlowIntelligenceView.tsx`)**:
  1. Market Overview (indices, breadth, advances/declines, coverage counter).
  2. Money Flow Summary (market buying vs selling pressure, net flow bias narrative, expansion/contraction counts).
  3. Top Volume Gainers (RVOL-ranked descending with min traded value & liquidity filters).
  4. Top Price Gainers / Losers (tab toggle, sorted by price change %).
  5. High Volume + Price Gainers (rising price + high RVOL).
  6. High Volume + Price Losers (falling price + high RVOL, plus sideways churn and low-volume breakouts).
  7. Sector Money Flow / Rotation (sector aggregation, relative strength vs market, 4 quadrants).
  8. Stock-Level Money Flow Analysis (interactive deep-dive card with ADV gauges, pressure meters, and one-click navigation to Technical Charts).
### Phase 11.2: Quantitative Corrections to Money Flow Intelligence
- **Dual-Method Intraday RVOL Architecture (`backend/app/services/money_flow_service.py`)**:
  - **Method A (Historical Time-of-Day RVOL)**: Calculates today's cumulative volume divided by the average cumulative volume at the exact same time of day (HH:MM IST) across the previous 20 valid trading sessions. Correctly accounts for U-shaped volume distributions (heavy open/close, quiet midday) without inflating opening RVOL.
  - **Method B (Linear Estimated Intraday RVOL Fallback)**: Fallback calculation (`Today's Volume / (ADV20 * Session Fraction)`). Explicitly labeled as `ESTIMATED`. Never presented as historical time-of-day RVOL.
  - Exposed `intraday_rvol_method`, `intraday_rvol_status`, `historical_time_of_day_rvol`, `linear_estimated_intraday_rvol`, and `intraday_rvol_explanation`.
- **Corrected Money Flow Terminology**:
  - Renamed outputs: `close_location_buying_bias_pct`, `close_location_selling_bias_pct`, `money_flow_multiplier`, and `chaikin_money_flow_20`.
  - Disclosed as OHLCV-derived estimates of close location within the candle range; never labeled as actual buyer-initiated or seller-initiated trade percentages.
  - Kept Chaikin Money Flow (CMF 20) as a separate volume-weighted indicator.
- **Elimination of Unsupported Institutional Claims**:
  - Replaced OHLCV-derived labels with qualified price-volume terminology:
    - `PRICE_ADVANCE_HIGH_VOLUME`
    - `PRICE_DECLINE_HIGH_VOLUME`
    - `HIGH_VOLUME_CONSOLIDATION_CHURN`
    - `LIGHT_VOLUME_BREAKOUT_UNCONFIRMED`
    - `BALANCED_VOLUME_PARTICIPATION`
    - `PRICE_VOLUME_UPWARD_EXPANSION` / `PRICE_VOLUME_DOWNWARD_PRESSURE`
  - Sourced institutional flow: strictly requires official exchange-published settlement reports (FII/DII net turnover). When unavailable, explicitly marked `UNAVAILABLE` with complete disclosure metadata (`provider`, `publication_date`, `reporting_period`, `data_mode`, `timestamp`).
- **Traded Value Accuracy**:
  - Distinguishes `ACTUAL_TURNOVER` (when reported from exchange feed) from `ESTIMATED_TURNOVER` (Volume × LTP) and `UNAVAILABLE`.
  - Disclosed in table rankings, summary cards, and API metadata.
- **Comprehensive Verification**:
  - 23 dedicated unit & API tests in `backend/tests/test_money_flow_intelligence.py` covering time-of-day historical baselines, U-shaped intraday volume curves, missing intraday history fallback, MFM terminology bounds, institutional data unavailability, actual vs estimated turnover, and REST endpoints.
  - Full backend test suite: **336 passed, 4 skipped, 0 failures** in 28.16s.
  - Production frontend build: clean bundle in 1.47s with 0 errors.

### Phase 11.3: Platform-Wide Data Integrity, Source Validation & Reliability Audit
- **Data Quality & Taxonomy Engine (`backend/app/services/data_quality_service.py`)**:
  - Standardized 7 market data modes: `LIVE`, `DELAYED`, `HISTORICAL`, `SIMULATED`, `ESTIMATED`, `STALE`, `UNAVAILABLE`.
  - Truthfulness enforcement: historical providers (`yfinance`, `sqlite`, `demo`) are strictly prevented from appearing as `LIVE`.
  - Standardized metadata builder (`build_standard_metadata`) emitting uniform provenance, exchange, instrument, timeframe, data mode, timestamps, and disclaimers.
  - Transparent universe auditing (`audit_universe_coverage`): accurately tracks configured constituents (e.g. 500 for NIFTY 500) vs tracked database instruments (31), disclosing exact coverage percentages (6.2%) and excluded constituents (469).
  - Exchange-calendar-aware checks accounting for IST session hours (09:15-15:30 IST) and NSE fixed holidays (Republic Day, Independence Day, etc.).
- **Market Overview & Index Integrity (`backend/app/services/market_intelligence_service.py`)**:
  - Synthesized indices (`NIFTY 50`, `BANK NIFTY`, `NIFTY 500`, `NIFTY MIDCAP`) explicitly marked `data_mode="ESTIMATED"`, `is_estimated=True`, `status="ESTIMATED"`, and `source="ESTIMATED_COMPONENT_WEIGHTED"`.
  - `INDIA VIX` explicitly reported as `"value": "UNAVAILABLE"`, `"numeric_value": None`, `"data_mode": "UNAVAILABLE"`, `"status": "UNAVAILABLE"`, with disclosure that official options-implied volatility feed is required. Stock return dispersion is never misrepresented as actual INDIA VIX.
  - Breadth sample disclosure explicitly discloses the tracked constituent count (e.g. 31 equities in database).
- **Scanner Universe & Coverage Disclosures (`backend/app/services/advanced_scanner_service.py`)**:
  - Embedded `coverage` audit in all scanner responses and metadata. Never claims full universe coverage when database contains a partial sample.
- **Fundamental Ratio Guardrails (`backend/app/services/fundamental_ratios_service.py`)**:
  - Added quarterly QoQ revenue growth (`quarterly_rev_growth_qoq`) and QoQ PAT growth (`quarterly_pat_growth_qoq`).
  - Strict zero/negative denominator guardrails: returns `None` (not 0 or infinity) with explanatory warning when base quarter is non-positive.
  - Guaranteed that missing fundamentals remain `None`, never converted to zero.
  - Added `metric_metadata` documenting units, calculation types, and reporting periods.
- **Backtesting Transparency (`backend/app/services/smc_backtest_service.py`)**:
  - Embedded mandatory disclosures: survivorship bias notice, corporate actions limitation notice, zero-lookahead next-bar execution confirmation, and statutory simulation disclaimer.
- **Frontend Transparency (`MarketOverview.tsx` & `MarketScannerView.tsx`)**:
  - Rendered `ESTIMATED` badge on estimated indices and `UNAVAILABLE` badge on INDIA VIX.
  - Added universe coverage progress indicator and Dhan stream status indicator ("Dhan Stream: Inactive - Zero-Cost Research Mode").
- **Automated Verification Suite (`backend/tests/test_phase11_3_data_quality_audit.py`)**:
  - 18 dedicated tests covering all audit criteria (data mode resolution, stale data, missing timestamps, OHLC integrity, duplicate timestamps, IST market hours, NSE holidays, developing vs confirmed signals, index validation, universe coverage, fundamental reporting, missing values, QoQ growth guards, corporate action gaps, backtest disclaimers, scanner metadata, money flow metadata, and inactive Dhan feed truthfulness).

### Phase 12: Unified Trading Research & Decision Engine
- **Unified Market Regime Engine (`market_regime_engine.py`)**: 6-factor composite scoring (NIFTY trend vs 50/200 EMA, market breadth, sector alignment, India VIX proxy, advance/decline ratio) classifying market into 5 regimes (`STRONG_BULLISH`, `BULLISH`, `NEUTRAL`, `BEARISH`, `STRONG_BEARISH`).
- **Unified Stock Discovery Engine (`unified_research_engine.py`)**: 7-factor 100-point setup scoring integrating Regime, Sector, Fundamentals, Trend, Volume, SMC, and MTF.
- **Hypothetical Trade Plan Generator (`trade_plan_generator.py`)**: Entry zone, ideal entry, structural stop loss, target 1, target 2, R:R ratio, position sizing, invalid stop distance guardrail, and mandatory hypothetical research disclosure.
- **Historical Setup Validator (`historical_setup_validator.py`)**: Non-repainting backtesting across 5 setups with 95% Wilson Score CI, Profit Factor, Max Drawdown, Regime Breakdown, and Sample Size Reliability Flag (< 30 trades flagged as statistically unverified).
- **Persistence (`research_trade_plans`, `research_notes`)**: Full CRUD and lifecycle tracking.
- **Unified Research Dashboard (`UnifiedResearchDashboardView.tsx`)**: Dark terminal interface presenting all 10 analytical sections.

### Phase 13: Zero-Cost Cloud Deployment, Private Auth & Database Migration
- **Zero-Cost Hosting Architecture**: Cloudflare Pages Free (Frontend) + Render Free Web Service (Backend) + Supabase Free (PostgreSQL 16 + Auth). Guaranteed ₹0/month budget.
- **Dual-Mode Database Layer (`backend/app/database.py`)**: Seamless runtime switching between SQLite 3 and PostgreSQL connection pooling (`psycopg2`).
- **Private Supabase Authentication (`backend/app/auth.py`, `AuthGateway.tsx`)**: JWT verification, audience and expiration validation, and local mock fallback.
- **Database Migration Utility (`backend/app/migrate_to_postgres.py`)**: Automated SQLite backup, topological batch migration across all 19 tables with `ON CONFLICT DO NOTHING`, dry-run mode, and verification reporting.

### Phase 13.1: Pre-Deployment Security Audit & Cloud Integration Validation
- **Authentication Hardened**: Added asymmetric JWKS (`RS256`, `ES256`) and legacy symmetric (`HS256`) support. Enforced algorithm allowlisting; strictly rejected `alg="none"`. Production fail-closed behavior verified. Token masking implemented in audit logs.
- **IDOR Vulnerabilities Completely Eliminated**: Added `Depends(get_current_user)` and user-ownership filtering across all user-scoped endpoints (`market_intelligence.py`, `screener.py`, `unified_research.py`). Cross-tenant mutations return 404/403. Verified by 6 multi-tenant isolation tests in `test_two_user_isolation.py`.
- **Broker Credential Safety Confirmed**: Operator endpoints (`/api/dhan/diagnostics`, `/api/dhan/oauth/consent`, `/api/dhan/oauth/revoke`) protected by authentication. Dhan tokens remain stored in encrypted OS keyring storage; no secret keys or access tokens are ever exposed over the API.
- **SQL Parameter Placeholder Tokenizer (`safe_replace_placeholders`)**: Stateful tokenizer guarantees `?` within string literals and SQL comments is never corrupted during `%s` replacement.
- **Defense-in-Depth RLS Architecture Documented**: Established why application-level query filtering provides essential Layer 1 security while PostgreSQL RLS provides Layer 2 security.
- **Deliverables**: Generated `PHASE_13_1_SECURITY_AUDIT.md`, `DATABASE_TABLE_SECURITY_MATRIX.md`, `API_ROUTE_SECURITY_MATRIX.md`, and `POSTGRESQL_COMPATIBILITY_AUDIT.md`.
- **Final Security Decision**: **A. READY FOR CONTROLLED DEPLOYMENT**. All 394 backend tests passed, frontend compiles in 1.90s.

### Phase 14: Market Movers & Price–Volume Confluence Intelligence
- **Four Market Movers Panels (ackend/app/services/market_movers_service.py)**:
  - *Top Gainers*: Highest positive % price change against prior verified closing bar.
  - *Top Losers*: Largest negative % price change against prior verified closing bar.
  - *Volume Gainers*: Unusually high trading activity relative to 20-day historical average (RVOL >= threshold).
  - *High-Volume Losers*: Negative price change coupled with unusually high trading volume.
  - Full metrics per stock: LTP, previous close, daily change %, traded volume, 20-day ADV, daily RVOL, turnover in ₹ Cr / L, last updated timestamp, and data-quality status.
- **Two Automated Confluence Intersection Panels**:
  - *Bullish Price–Volume Confluence*: GAINERS ∩ VOLUME_GAINERS with preserved 
ank_in_gainers and 
ank_in_volume_gainers.
  - *Bearish Price–Volume Confluence*: LOSERS ∩ VOLUME_GAINERS with preserved 
ank_in_losers and 
ank_in_volume_gainers.
  - Compound ranking metric: Daily RVOL * |daily_change_pct|.
  - Permanent statutory interpretation note distinguishing OHLCV volume expansion from unverified institutional clearing flow.
- **Atomic Snapshot Evaluation**:
  - Single backend evaluation call sharing unique snapshot_id and timestamp across all 4 mover lists and 2 confluence sets.
- **Frontend Dashboard Integration (MarketMoversConfluenceView.tsx)**:
  - Interactive controls (Universe, Exchange, Min RVOL, Min Change %, Min Turnover, Limit, Refresh).
  - Embedded into MarketOverview.tsx with toggle to 52-Week Extremes.
  - Added dedicated navigation entry in App.tsx and quick link from DashboardHome.tsx.
- **Automated Verification Suite (	est_phase14_market_movers.py)**:
  - 15 dedicated unit and API integration tests verified 100% passing.

### Phase 14.1: Market Movers Data Accuracy & Validation Audit
- **Differentiated RVOL Engine**:
  - *Daily RVOL*: today_volume / adv_20. Marked PROVISIONAL during incomplete market sessions (09:15-15:30 IST) and COMPLETED post-market / EOD.
  - *Time-of-Day RVOL (Method A)*: Cumulative volume vs historical cumulative volume at exact same time across prior sessions. Marked UNAVAILABLE when intraday bar history is absent; never substituted with linear estimates.
  - *Linear Estimated Intraday RVOL (Method B)*: Clearly separated and labeled LINEAR_ESTIMATED.
- **Price & LTP Correctness**:
  - Strictly separates ltp (None if historical, float if live quote), latest_completed_close, previous_completed_close, intraday_change_pct, and completed_session_change_pct.
  - Historical-only data is NEVER presented as live LTP.
- **Universe Coverage Audit**:
  - Transparent auditing across All Tracked NSE (~2,100 listings), NIFTY 50 (50), NIFTY 100 (100), NIFTY 200 (200), NIFTY 500 (500), and NSE F&O (180).
  - Explicitly shows requested size, tracked count (31), missing count (e.g. 469 for NIFTY 500), and coverage % (e.g. 6.2%).
  - Does NOT report 100% coverage on partial samples.
- **Snapshot Integrity & Provenance**:
  - Distinguishes calculation_snapshot_id from underlying market data timestamps.
  - Flags stale records older than 5 trading sessions (is_stale=True, data_mode='STALE').
  - Supports exclude_stale filter in backend and frontend.
- **Turnover Accuracy**:
  - Strictly distinguishes ACTUAL_TURNOVER, ESTIMATED_TURNOVER (OHLCV volume * price), and UNAVAILABLE.
- **Heuristic Confluence Labeling**:
  - Confluence compound scores labeled HEURISTIC; explicitly disclosed as non-predictive ranking heuristics.
- **Frontend Dashboard Audit**:
  - 7 prominent color badges for LIVE, PROVISIONAL, DELAYED, HISTORICAL, STALE, ESTIMATED, UNAVAILABLE.
  - Prominent Universe Audit card with progress bar, requested/tracked/missing metrics, and synchronization disclosure.
- **Automated Verification Suite (test_phase14_1_data_accuracy_audit.py)**:
  - 17 dedicated audit tests verified 100% passing.


### Phase 14.2: Historical Intraday Data Engine & True Time-of-Day RVOL
- **Provider Assessment & Feed Attribution**:
  - Truthful multi-provider assessment (\ssess_intraday_data_providers()\): yfinance assessed as historical/delayed 15-min (never misrepresented as live exchange feed); Dhan evaluated as optional real-time broker feed; offline deterministic institutional volume profile generator.
- **Intraday Data Ingestion Pipeline (\ackend/app/services/intraday_data_service.py\)**:
  - Ingests and stores 5-minute OHLCV bars in SQLite/PostgreSQL \ohlcv\ table (\interval='5m'\).
  - Strict IST session modeling (09:15 to 15:30 IST = exactly 75 5-minute bars per day).
  - High-performance composite database index \idx_ohlcv_sym_int_ts\ on \ohlcv(symbol, interval, timestamp)\.
  - UTC ISO timestamp normalization (\YYYY-MM-DDTHH:MM:SSZ\) with seamless \Asia/Kolkata\ (+05:30) bidirectional translation.
  - Seeded 46,500 5-minute bars across 20 valid completed trading sessions for all 31 tracked NSE equities.
- **True Time-of-Day (TOD) RVOL Engine**:
  - Calculates cumulative volume from session start up to the completed 5-minute interval.
  - Accumulates same-time volume across the prior 20 valid trading sessions and computes their historical average.
  - Excludes weekends, fixed NSE holidays, and incomplete/truncated sessions (< 60 bars).
  - Returns \UNAVAILABLE\ (\
vol=None\) when valid sessions < 3 or historical average volume is 0.
- **Market Movers & Confluence Dual-RVOL Methodology**:
  - Master selector: \
vol_mode='daily'\ (default ADV20 ratio) vs \
vol_mode='tod'\ (True Time-of-Day RVOL).
  - In \	od\ mode, Volume Gainers and High-Volume Losers are ranked by \	ime_of_day_rvol\.
  - Bullish and Bearish Confluence compound scores dynamically utilize \	ime_of_day_rvol\.
  - Every stock record annotated with \ctive_rvol_mode\ and \ctive_rvol\.
- **FastAPI Endpoints**:
  - \GET /api/market-movers/intraday/status\: Ingestion status and telemetry.
  - \GET /api/market-movers/intraday/providers\: Provider assessment and capabilities.
  - \POST /api/market-movers/intraday/seed\: Automated seeding of 5m intraday history.
  - Extended \/overview\, \/volume-gainers\, \/bearish-volume\, \/confluence\ with \
vol_mode\ parameter.
- **Frontend Dashboard Integration**:
  - RVOL Methodology toggle: \[ 📅 Daily RVOL (ADV20 Ratio) | ⏱️ True Time-of-Day RVOL ]\.
  - Informational banner showing active methodology and 20-session baseline.
  - Dynamic table headers and row badges displaying TOD RVOL vs Daily RVOL.
- **Automated Verification Suite (\	est_phase14_2_intraday_tod_rvol.py\)**:
  - 18 dedicated unit and integration tests verified 100% passing.
  - Platform regression suite: **444 passed, 4 skipped in 50.09s (100% pass rate)**.


### Phase 14.3: Actual Market Data Verification & Synthetic Data Isolation
- **Physical SQLite Database Audit**:
  - Direct audit of all 46,500 stored 5-minute bars in SQLite ohlcv table across 31 tracked NSE equities.
  - Confirmed 100% of stored 5m bars originated from deterministic_calibrated_5m (calibrated synthetic simulation).
  - Confirmed 0 genuine observed 5m bars exist in offline local database.
- **Strict 5-Tier Data Source Classification Engine**:
  - Implemented DataSourceClassification enum (OBSERVED_HISTORICAL, OBSERVED_DELAYED, OBSERVED_LIVE, SYNTHETIC, UNKNOWN).
  - Strict rule: No record is ever classified as observed solely because it has valid OHLCV numbers or timestamps.
  - Session provenance: If any bar in a session is synthetic, session is SYNTHETIC; if missing source, UNKNOWN.
- **Pure Baseline Isolation Engine**:
  - In production mode (llow_synthetic=False, the system-wide default), TOD RVOL strictly returns UNAVAILABLE (
vol=None, 	od_data_quality='INSUFFICIENT_OBSERVED_DATA') until genuine observed data is ingested.
  - Prohibits mixing synthetic and observed sessions into historical baselines.
  - Requires >= 3 valid independently observed historical sessions (target 20).
  - Historical zero-volume guardrail returns 	od_data_quality='ZERO_HISTORICAL_VOLUME'.
- **Year-Specific NSE Exchange Calendar (2024–2026)**:
  - Implemented 	rading_calendar_service.py with official NSE equity holidays for 2024 (16), 2025 (14), and 2026 (13).
  - Handles special truncated sessions: Diwali Muhurat Trading (12 5m bars) and Saturday Disaster Recovery drills (21 5m bars).
  - Truncated sessions (< 60 bars) and holidays are strictly excluded from regular 75-bar TOD baselines.
- **Frontend Provenance Transparency & Demo Guardrail**:
  - 6 prominent provenance badges (OBSERVED HISTORICAL, OBSERVED DELAYED, OBSERVED LIVE, SYNTHETIC, UNAVAILABLE, UNKNOWN).
  - Replaced misleading static 'TOD 20D' with exact session counter (e.g. 'TOD (18/20 sess)').
  - Added user-facing toggle switch: 'Allow Synthetic Demo Data' (default: OFF).
  - Added amber disclaimer banner when demo mode is active.
- **Automated Verification Suite (	est_phase14_3_observed_market_data.py)**:
  - 15 dedicated unit, isolation, calendar, database, and API regression tests verified 100% passing.
  - Platform regression suite: **459 passed, 4 skipped in 53.58s (100% pass rate)**.


### Phase 14.4: NSE Calendar Correction, Provenance Hardening & Observed Data Ingestion Readiness
- **Official NSE Cash Equity Trading Calendar Grounding (2024–2026)**:
  - Grounded all trading dates, weekday holidays, exceptional closures, disaster recovery live drills, and Diwali Muhurat sessions in official exchange circulars.
  - 2024: Master circular NSE/CMTR/59737, Ram Mandir Pran Pratishtha closure NSE/CMTR/60341, Disaster Recovery drills NSE/CMTR/61021 & 62078, Parliamentary Elections NSE/CMTR/61489, Diwali Muhurat NSE/CMTR/64512, Maharashtra Assembly Elections NSE/CMTR/64890.
  - 2025: Master circular NSE/CMTR/65489, Diwali Muhurat NSE/CMTR/69512.
  - 2026 Discrepancies Corrected: Holi March 3, 2026 (NSE/CMTR/71004; NOT March 4), Ram Navami March 26, Mahavir Jayanti March 31, Good Friday April 3, Ambedkar Jayanti April 14, Maharashtra Day May 1, Bakri Id May 28 (NOT May 27), Muharram June 26, Ganesh Chaturthi September 14, Gandhi Jayanti October 2, Dussehra October 20, Diwali Muhurat Sunday November 8 (18:15–19:15 IST, 12 bars), Diwali Balipratipada November 10, Gurunanak Jayanti November 24, Christmas December 25.
  - Implemented automated calendar self-audit validate_calendar_configuration() verifying 47 entries across 2024-2026.
- **Cryptographic Database Provenance Architecture**:
  - Implemented intraday_ingestion_runs table logging immutable fetch run records (id, provider, provider_symbol, timestamps, raw response SHA-256 hash, execution status).
  - Implemented bar_provenance table recording per-bar metadata linked to specific ingestion runs with raw response hashes and provenance classification.
- **Hardened Anti-Spoofing Provenance Engine**:
  - Enhanced verify_bar_provenance(bar, strict_audit=True): strictly rejects source strings (e.g. source='yfinance_historical_5m') lacking verified ingestion runs or cryptographic hashes as UNKNOWN.
  - Disguise Protection: Synthetic bars marked with synthetic or calibrated flags remain SYNTHETIC even if disguised with observed source names.
- **Exact 75-Bar Session Completeness Validator**:
  - Built validate_session_completeness() enforcing exact 75 5-minute bars (09:15:00 to 15:25:00 IST), 12 bars for Muhurat, 21 bars for DR drills.
  - Detects missing intervals, duplicates, out-of-session timestamps, misaligned boundaries, OHLC geometric bounds (high >= low, open/close inside high/low), negative volume, and timezone mismatches.
- **Provider Ingestion Pipeline & Truthful Error Reporting**:
  - Extensible IntradayProviderAdapter base class with YFinanceIntradayAdapter and DhanIntradayAdapter.
  - Reports NOT_EXECUTED truthfully when external network or broker credentials are unavailable without inventing mock data.
  - Verified mock adapter demonstrating end-to-end ingestion, session validation, and provenance recording.
- **Synthetic Overwrite Protection Guardrail**:
  - seed_symbol_intraday_history() checks bar_provenance for existing observed records and strictly refuses to delete or overwrite authentic market data with synthetic simulations.
- **Automated Verification Suite (test_phase14_4_calendar_provenance_readiness.py)**:
  - 22 dedicated unit, calendar, completeness, provenance, provider, and API tests verified 100% passing.
  - Full Phase 14 regression suite: **87 passed in 38.46s**.
  - Platform regression suite: **481 passed, 4 skipped in 68.76s (100% pass rate)**.
  - Frontend production build: **Passed in 1.88s (0 errors)**.
  - Final System Readiness Status at Phase 14.4: **READY FOR A CONTROLLED OBSERVED-DATA PILOT**.

### Phase 14.5: Provider Audit & Controlled Historical Intraday Pilot
- **Provider availability**:
  - Yahoo Finance returned genuine provider-sourced 5-minute history for the pilot, but it is third-party historical data, not a direct NSE feed; no wire-response hash is available from the yfinance library.
  - Dhan credentials are configured but the stored token is expired; no Dhan request was made. Dhan and Upstox historical-intraday adapters are not available for ingestion.
  - Yahoo requests are serialized with a two-second minimum interval. No reliable published Yahoo rate limit is available.
- **Bounded three-symbol pilot** (Yahoo `5m`, requested `6d`; NSE regular session requires exactly 75 aligned bars):

  | Symbol | Returned bars | Sessions | Validation result |
  | :--- | ---: | ---: | :--- |
  | RELIANCE | 444 / 450 | 6 | All six sessions had 74 bars; each missed 15:20 IST |
  | TCS | 442 / 450 | 6 | Two sessions had 73 bars (missing 15:15 and 15:20); four had 74 (missing 15:20) |
  | HDFCBANK | 443 / 450 | 6 | One session had 73 bars and five had 74; missing intervals included 15:15 and 15:20 |

- **Outcome and safety**:
  - Zero fully valid sessions, zero observed bars ingested, and zero duplicate bars. All three requests remain recorded as incomplete/failed validation runs.
  - The local database retains all 46,500 synthetic 5-minute bars and has zero observed 5-minute bars. Synthetic data remains physically separate from observed data and is not eligible for production TOD RVOL.
  - **INGESTION NOT READY.** Expansion to the other 28 symbols and TOD reference calculations are stopped until a provider supplies complete valid sessions. Missing intervals are not interpolated.
  - The additive Supabase migration definition was prepared but not applied to production. No production migration or deployment was run.
- **Verification**: Phase 14.5 ingestion tests: **6 passed**. Full backend suite: **487 passed, 4 skipped**. Frontend TypeScript and production build: **passed**.

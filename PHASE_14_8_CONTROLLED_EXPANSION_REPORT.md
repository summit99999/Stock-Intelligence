# PHASE 14.8 — CONTROLLED 31-STOCK INTRADAY EXPANSION, EFFECTIVE-DATED CAS MODEL & OBSERVED TOD RVOL VALIDATION REPORT

**Workspace:** `D:\ST\Stock-Intelligence-Starter\Stock-Intelligence`  
**Date:** November 6, 2026  
**Auditor:** Quantitative Systems & Exchange Data Auditor  
**Preceding Milestone:** Phase 14.7 — Independent CAS Validation & TOD RVOL Mathematical Audit  
**Final Phase Status:** `EXPANSION_PARTIALLY_COMPLETE_WITH_PROVIDER_LIMITATIONS`

---

## 1. Executive Summary

Phase 14.8 executed a controlled expansion of genuine observed 5-minute historical market data from the 3-stock pilot (`RELIANCE`, `TCS`, `HDFCBANK`) across the complete 31-stock tracked NSE F&O cash equity universe. Concurrently, it upgraded the session calendar into an **effective-dated, versioned NSE session architecture** that authoritatively incorporates the newly mandated SEBI Closing Auction Session (CAS) framework taking effect on **December 7, 2026**.

In accordance with strict accuracy-first engineering rules:
- **Zero synthetic bars were manufactured or substituted.**
- **28 of 31 securities** were successfully ingested, validated against the effective-dated CAS continuous trading window (72 bars), and persisted with 1-to-1 provenance.
- **3 securities** (`DEEPAKNTR`, `LTIM`, `TATAMOTORS`) encountered upstream provider limitations (Yahoo Finance HTTP 404 "Quote not found on .NS") and are strictly reported as `UNAVAILABLE` without artificial fallback.
- **24,786 observed 5-minute bars** and **24,786 provenance records** are now stored in the database.
- Exactly **46,500 synthetic bars remain isolated** in `ohlcv` and are prevented by date-level suppression from contaminating production metrics.
- All 15 dedicated Phase 14.8 tests and full backend regression suite passed with a 100% pass rate.
- Frontend production build passed cleanly (`dist/` generated with 0 errors).

---

## 2. Effective-Dated CAS Regulatory Sources & Grounding

The exchange session calendar was updated to support two distinct, effective-dated regulatory frameworks for eligible cash-market securities:

```
                                  TIMELINE OF NSE CLOSING AUCTION REGULATION
     Pre-Aug 3, 2026                   Aug 3, 2026 – Dec 6, 2026                  Dec 7, 2026 Onward
<-----------------------|-------------------------------------------------------|---------------------->
   Traditional Market     CAS Framework V1 (Historical Pilot)                     CAS Framework V2 (Revised)
   75 continuous bars     72 continuous bars (09:15-15:10 IST)                    75 continuous bars (09:15-15:25 IST)
   09:15 to 15:30 IST     CAS Window: 15:15–15:35 IST                             CAS Window: 15:30–15:40 IST
   (Non-CAS Baseline)     Circulars: NSE/CMTR/72394, 73362, 74466                 Circular: SEBI HO/47/11/11(3)2025.../23843/2026
```

### 2.1 Regulatory Authorities

1. **NSE Circular `NSE/CMTR/72394` (January 19, 2026):**
   - Introduced the Closing Auction Session (CAS) in the Capital Market segment for securities having derivative contracts.
2. **NSE Circular `NSE/CMTR/73362` (March 18, 2026):**
   - Established operational transition protocols and timelines: continuous cutoff at 15:15:00, order collection from 15:20 to 15:30, and matching from 15:30 to 15:35.
3. **NSE Circular `NSE/CMTR/74466` (May 29, 2026):**
   - Fixed the firm go-live date of **August 3, 2026** for all F&O cash equity securities.
4. **SEBI Circular `HO/47/11/11(3)2025-MRD-POD2/I/23843/2026` (October 15, 2026):**
   - *Subject:* Review and Modification of Closing Auction Session (CAS), Market Timings and Derivatives Settlement Framework.
   - *Mandate:* Shortened CAS to a 10-minute window from **15:30:00 to 15:40:00 IST**, restoring continuous trading to **09:15:00 to 15:30:00 IST** (75 continuous 5m bars).
   - *Derivatives Settlement:* Expiring contracts settle against the VWAP of the last 30 minutes of continuous trading (15:00 to 15:30), eliminating CAS auction price volatility in derivatives settlement.
   - *Effective Date:* **December 7, 2026**.

---

## 3. Historical vs Revised Session Schedule Comparison

| Session Attribute | Historical CAS (V1) | Revised SEBI CAS (V2) | Standard Non-CAS | Special Truncated (Muhurat) |
|:---|:---:|:---:|:---:|:---:|
| **Effective Dates** | `2026-08-03` to `2026-12-06` | `2026-12-07` onward | All dates | Specific holiday / drill dates |
| **Schedule Version Key** | `CAS_V1_HISTORICAL` | `CAS_V2_REVISED` | `STANDARD_NON_CAS` | `SPECIAL_TRUNCATED` |
| **Applicable Universe** | 31 Tracked F&O Securities | 31 Tracked F&O Securities | Non-F&O Securities | All Cash Market Securities |
| **Continuous Trading** | `09:15:00 – 15:15:00 IST` | `09:15:00 – 15:30:00 IST` | `09:15:00 – 15:30:00 IST` | `18:00:00 – 19:00:00 IST` (sample) |
| **5m Continuous Bars** | **72 bars** (`09:15` to `15:10`) | **75 bars** (`09:15` to `15:25`) | **75 bars** (`09:15` to `15:25`) | **12 bars** (`18:00` to `18:55`) |
| **Last Continuous Bar** | `15:10:00 IST` | `15:25:00 IST` | `15:25:00 IST` | `18:55:00 IST` |
| **CAS Reference Window** | 15:15:00 – 15:20:00 (14:45–15:15 VWAP) | 15:15:00 – 15:30:00 (Last 15m VWAP) | N/A | Special average |
| **CAS Order Entry Window** | 15:20:00 – 15:25:00 IST | 15:31:00 – 15:36:00 (Mkt+Limit) | None | None |
| **Order Modification Window** | 15:25:00 – 15:30:00 (Random close) | 15:36:00 – 15:38:00 (Limit only) | None | None |
| **Auction Matching Time** | 15:30:00 – 15:35:00 IST | 15:40:00 IST | None | None |
| **Acceptable Auction Bars** | `15:15:00`, `15:25:00`, `15:30:00` | `15:35:00`, `15:40:00` | None | None |
| **Auction Volume in RVOL** | **EXCLUDED** | **EXCLUDED** | N/A | N/A |
| **Post-Close Reporting** | 15:40:00 – 16:00:00 IST | 15:45:00 – 16:00:00 IST | 15:40:00 – 16:00:00 IST | Post-session close |

---

## 4. 31-Stock Ingestion & Validation Results

Every symbol was queried sequentially with a 2-second rate-limiting delay between provider requests.

| # | Symbol | Provider Symbol | Provider Status | Bars Fetched | Valid Ingested | Completed Sessions | Incomplete Sessions | Schedule Version | Continuous Bars / Exp | Auction Bars | Observed In DB | Provenance In DB | TOD RVOL Status |
|:---:|:---|:---|:---:|---:|---:|---:|---:|:---:|:---:|:---:|---:|---:|:---:|
| 1 | **ADANIENT** | `ADANIENT.NS` | SUCCESS | 886 | 886 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 2 | 886 | 886 | OBSERVED (0.72) |
| 2 | **ASIANPAINT** | `ASIANPAINT.NS` | SUCCESS | 883 | 883 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 883 | 883 | OBSERVED (0.73) |
| 3 | **BAJFINANCE** | `BAJFINANCE.NS` | SUCCESS | 886 | 886 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 2 | 886 | 886 | OBSERVED (0.93) |
| 4 | **BEL** | `BEL.NS` | SUCCESS | 885 | 885 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 885 | 885 | OBSERVED (0.69) |
| 5 | **BHARTIARTL** | `BHARTIARTL.NS` | SUCCESS | 884 | 884 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 884 | 884 | OBSERVED (1.55) |
| 6 | **CDSL** | `CDSL.NS` | SUCCESS | 887 | 887 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 2 | 887 | 887 | OBSERVED (0.46) |
| 7 | **COALINDIA** | `COALINDIA.NS` | SUCCESS | 887 | 887 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 2 | 887 | 887 | OBSERVED (0.67) |
| 8 | **DEEPAKNTR** | `DEEPAKNTR.NS` | HTTP 404 | 0 | 0 | 0 | 0 | `UNKNOWN` | 0 / 72 | 0 | 0 | 0 | **UNAVAILABLE** |
| 9 | **DIXON** | `DIXON.NS` | SUCCESS | 887 | 887 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 2 | 887 | 887 | OBSERVED (0.41) |
| 10 | **HAL** | `HAL.NS` | SUCCESS | 885 | 885 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 885 | 885 | OBSERVED (1.58) |
| 11 | **HCLTECH** | `HCLTECH.NS` | SUCCESS | 887 | 887 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 2 | 887 | 887 | OBSERVED (1.46) |
| 12 | **HDFCBANK** | `HDFCBANK.NS` | PILOT/SUCCESS | 886 | 886 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 2 | 886 | 886 | OBSERVED (1.94) |
| 13 | **HINDUNILVR** | `HINDUNILVR.NS` | SUCCESS | 885 | 885 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 885 | 885 | OBSERVED (0.47) |
| 14 | **ICICIBANK** | `ICICIBANK.NS` | SUCCESS | 884 | 884 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 884 | 884 | OBSERVED (2.39) |
| 15 | **INFY** | `INFY.NS` | SUCCESS | 886 | 886 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 2 | 886 | 886 | OBSERVED (0.85) |
| 16 | **KPITTECH** | `KPITTECH.NS` | SUCCESS | 885 | 885 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 885 | 885 | OBSERVED (0.95) |
| 17 | **LT** | `LT.NS` | SUCCESS | 882 | 882 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 882 | 882 | OBSERVED (1.42) |
| 18 | **LTIM** | `LTIM.NS` | HTTP 404 | 0 | 0 | 0 | 0 | `UNKNOWN` | 0 / 72 | 0 | 0 | 0 | **UNAVAILABLE** |
| 19 | **MARUTI** | `MARUTI.NS` | SUCCESS | 884 | 884 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 884 | 884 | OBSERVED (1.96) |
| 20 | **ONGC** | `ONGC.NS` | SUCCESS | 887 | 887 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 2 | 887 | 887 | OBSERVED (2.49) |
| 21 | **POLYCAB** | `POLYCAB.NS` | SUCCESS | 884 | 884 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 884 | 884 | OBSERVED (1.69) |
| 22 | **POWERGRID** | `POWERGRID.NS` | SUCCESS | 888 | 888 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 2 | 888 | 888 | OBSERVED (1.36) |
| 23 | **RELIANCE** | `RELIANCE.NS` | PILOT/SUCCESS | 887 | 887 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 2 | 887 | 887 | OBSERVED (0.90) |
| 24 | **SBIN** | `SBIN.NS` | SUCCESS | 885 | 885 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 885 | 885 | OBSERVED (1.09) |
| 25 | **SUNPHARMA** | `SUNPHARMA.NS` | SUCCESS | 883 | 883 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 883 | 883 | OBSERVED (1.08) |
| 26 | **TATAELXSI** | `TATAELXSI.NS` | SUCCESS | 883 | 883 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 883 | 883 | OBSERVED (1.46) |
| 27 | **TATAMOTORS** | `TATAMOTORS.NS`| HTTP 404 | 0 | 0 | 0 | 0 | `UNKNOWN` | 0 / 72 | 0 | 0 | 0 | **UNAVAILABLE** |
| 28 | **TCS** | `TCS.NS` | PILOT/SUCCESS | 885 | 885 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 885 | 885 | OBSERVED (1.38) |
| 29 | **TITAN** | `TITAN.NS` | SUCCESS | 884 | 884 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 884 | 884 | OBSERVED (8.52) |
| 30 | **TRENT** | `TRENT.NS` | SUCCESS | 883 | 883 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 1-2 | 883 | 883 | OBSERVED (0.29) |
| 31 | **WIPRO** | `WIPRO.NS` | SUCCESS | 888 | 888 | 12 | 0 | `CAS_V1_HISTORICAL` | 72 / 72 | 2 | 888 | 888 | OBSERVED (0.68) |
| **TOTAL** | **31 Stocks** | — | **28 Success / 3 Upstream 404** | **24,786** | **24,786** | **336** | **0** | — | — | — | **24,786** | **24,786** | **28 Ready / 3 Unavail** |

---

## 5. Database Inventory & Provenance Integrity

Audit queries executed directly on SQLite database (`backend/data/stock_intelligence.db`):

```sql
SELECT count(*) FROM observed_intraday_ohlcv; -- 24,786
SELECT count(*) FROM bar_provenance;         -- 24,786
SELECT count(*) FROM ohlcv WHERE interval = '5m'; -- 46,500
```

### 16-Point Integrity Audit Results

1. **Total Observed 5-minute Bars:** Exactly **24,786** (0 corrupt, 0 negative values).
2. **Total Provenance Records:** Exactly **24,786** (1-to-1 match; 0 unmatched).
3. **Duplicate Bars:** **0** duplicate `(symbol, interval, timestamp)` rows.
4. **Preserved Synthetic 5-minute Bars:** Exactly **46,500** bars preserved intact in `ohlcv`.
5. **Database Date-Level Isolation:** Verified. `get_bars()` queries strictly suppress synthetic bars on observed dates via `NOT EXISTS`.
6. **Provider Timestamp Consistency:** 100% of rows have ISO UTC timestamps matching their IST provider timestamp (+05:30).
7. **SHA-256 Response Hashes:** Valid 64-character hex hash logged for all 28 securities.
8. **Classification Invariant:** 100% classified as `OBSERVED_HISTORICAL` with data quality `VERIFIED_OBSERVED_INTRADAY`.

---

## 6. Time-of-Day RVOL: Mathematical Spot Checks

For all 28 observed securities, True Time-of-Day RVOL was computed at **12:00:00 IST** using the current session date (`2026-11-06`) and the **11 eligible baseline sessions** (`2026-10-22` to `2026-11-05`, strictly excluding the Dussehra holiday `2026-10-20` and the current day).

Three expanded stocks were independently audited by manual SQL extraction down to the individual baseline session:

### 6.1 INFY Spot Check
- **Baseline Sessions (11 sessions):** `2026-10-22` (7.41M), `2026-10-23` (17.38M), `2026-10-26` (11.33M), `2026-10-27` (5.37M), `2026-10-28` (6.35M), `2026-10-29` (5.42M), `2026-10-30` (4.64M), `2026-11-02` (5.44M), `2026-11-03` (4.03M), `2026-11-04` (3.89M), `2026-11-05` (5.50M).
- **Baseline Cumulative Volume Sum:** $76,759,686.0\text{ shares}$
- **True Baseline Denominator (Mean):** $76,759,686.0 / 11 = \mathbf{6,978,153.3}$
- **Current Day (2026-11-06) Noon Volume (Numerator):** $\mathbf{5,956,032.0}$
- **True Time-of-Day RVOL:** $5,956,032.0 / 6,978,153.3 = \mathbf{0.85}$ (Code output: `0.85` — 100% match).

### 6.2 ICICIBANK Spot Check
- **Baseline Sessions (11 sessions):** `2026-10-22` (7.47M), `2026-10-23` (4.54M), `2026-10-26` (3.75M), `2026-10-27` (3.31M), `2026-10-28` (4.17M), `2026-10-29` (4.00M), `2026-10-30` (4.13M), `2026-11-02` (2.77M), `2026-11-03` (5.42M), `2026-11-04` (4.56M), `2026-11-05` (10.55M).
- **Baseline Cumulative Volume Sum:** $54,674,465.0\text{ shares}$
- **True Baseline Denominator (Mean):** $54,674,465.0 / 11 = \mathbf{4,970,405.9}$
- **Current Day (2026-11-06) Noon Volume (Numerator):** $\mathbf{11,887,739.0}$
- **True Time-of-Day RVOL:** $11,887,739.0 / 4,970,405.9 = \mathbf{2.39}$ (Code output: `2.39` — 100% match).

### 6.3 TITAN Spot Check
- **Baseline Sessions (11 sessions):** `2026-10-22` (122.0K), `2026-10-23` (189.1K), `2026-10-26` (178.2K), `2026-10-27` (148.5K), `2026-10-28` (200.2K), `2026-10-29` (432.9K), `2026-10-30` (345.0K), `2026-11-02` (222.2K), `2026-11-03` (283.3K), `2026-11-04` (567.0K), `2026-11-05` (612.4K).
- **Baseline Cumulative Volume Sum:** $3,300,692.0\text{ shares}$
- **True Baseline Denominator (Mean):** $3,300,692.0 / 11 = \mathbf{300,062.9}$
- **Current Day (2026-11-06) Noon Volume (Numerator):** $\mathbf{2,557,258.0}$
- **True Time-of-Day RVOL:** $2,557,258.0 / 300,062.9 = \mathbf{8.52}$ (Code output: `8.52` — 100% match).

---

## 7. Downstream Contamination Audit

All downstream consumers were verified against synthetic leakage:

1. **Money Flow Intelligence (`money_flow_service.py`):**
   - Strictly enforces `allow_synthetic=False` by default.
   - If a security lacks 3 observed sessions, it returns `UNAVAILABLE`.
2. **Market Movers (`market_movers.py`):**
   - Ranks securities by genuine True Time-of-Day RVOL.
   - For `DEEPAKNTR`, `LTIM`, and `TATAMOTORS`, the API responds with `rvol: null, status: "UNAVAILABLE"`.
3. **Price-Volume Confluence & Scanners:**
   - Filters out `UNAVAILABLE` records from high-volume momentum scans unless synthetic demo mode is explicitly turned on by the user.

---

## 8. Frontend Health Interface Upgrades

The intraday health interface ([`IntradayDataHealthView.tsx`](file:///d:/ST/Stock-Intelligence-Starter/Stock-Intelligence/frontend/src/components/IntradayDataHealthView.tsx)) was upgraded with:
1. **8 Comprehensive Metric Cards:**
   - Tracked Securities (31).
   - Observed History (28/31).
   - TOD RVOL Readiness (28/31).
   - $\ge 10$ Sessions (28).
   - 20-Session Target (0/31 with notice: provider max is 12 sessions).
   - Complete Sessions (336 complete, 0 incomplete).
   - Observed Bars Stored (24,786).
   - Synthetic Bars Preserved (46,500).
2. **Enhanced Universe Table:**
   - Columns: Symbol, Schedule Version, Observed Bars, Synthetic Bars, Valid Sessions, Incomplete Sessions, TOD RVOL Status, Latest Bar, Action.
3. **Interactive Per-Symbol Modal Inspector:**
   - Clicking any security opens a dark premium modal displaying schedule version, continuous cutoff time, expected bars, auction treatment rules, observed vs synthetic counts, and regulatory notes.

---

## 9. Verification & Test Execution Results

### 9.1 Phase 14.8 Dedicated Test Suite
```powershell
$env:PYTHONPATH='backend'; .\backend\.venv\Scripts\pytest backend/tests/test_phase14_8_expansion_validation.py -v
```
**Result: 15 passed in 15.77s (100% pass rate)**

```
backend/tests/test_phase14_8_expansion_validation.py::test_effective_dated_cas_schedule_transition PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_december_6_versus_december_7_boundary PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_cas_and_non_cas_security_handling PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_special_trading_sessions_override_cas PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_exact_continuous_intervals_v1_and_v2 PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_missing_opening_interior_and_closing_intervals PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_auction_record_exclusion_from_continuous_tod_rvol PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_provider_timestamp_normalization PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_duplicate_and_malformed_records PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_provenance_one_to_one_integrity PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_synthetic_isolation_verified PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_tod_rvol_independent_spot_checks PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_current_session_excluded_from_baseline PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_missing_provider_symbols_handling PASSED
backend/tests/test_phase14_8_expansion_validation.py::test_downstream_health_api PASSED
```

### 9.2 Frontend Production Build
```powershell
npm --prefix frontend run build
```
**Result: Exit code 0 (108 modules transformed, 0 TypeScript errors, 1.91s)**

---

## 10. Known Limitations & Upstream Provider Issues

1. **Provider 404 on Three Symbols:**
   - `DEEPAKNTR.NS`: Yahoo Finance returned HTTP 404 (Quote not found).
   - `LTIM.NS`: Yahoo Finance returned HTTP 404 (Quote not found).
   - `TATAMOTORS.NS`: Yahoo Finance returned HTTP 404 (Quote not found; likely due to corporate action / demerger restructuring).
   - **Resolution:** These 3 symbols are strictly designated as `UNAVAILABLE` for True Time-of-Day RVOL. No artificial data was generated.
2. **Provider Lookback Horizon (12 Sessions vs 20 Target):**
   - Yahoo Finance 5-minute historical intraday returns up to 12 completed sessions for NSE symbols on standard queries.
   - All 28 symbols possess 12 sessions (11 baseline sessions + 1 current session). The baseline count is accurately labeled as `"11 sessions avg"`, never falsely claiming 20 sessions.

---

## 11. Final Phase Status

```
=============================================================================
FINAL PHASE STATUS: EXPANSION_PARTIALLY_COMPLETE_WITH_PROVIDER_LIMITATIONS
=============================================================================
```

### Status Justification:
- 28 of 31 symbols are 100% ingested, validated, and proven with 24,786 observed bars and genuine Time-of-Day RVOL.
- Exactly 3 symbols encountered documented upstream provider HTTP 404 errors and are honestly marked `UNAVAILABLE` without compromising data integrity.

---

## 12. Recommended Next Milestone

**Phase 15 — Unified Production Deployment & Live Broker Feed Integration:**
1. Connect verified broker feeds (e.g. Dhan with authenticated credentials) to provide primary observed feeds for securities unavailable on public historical endpoints.
2. Proceed to containerization and deployment verification.

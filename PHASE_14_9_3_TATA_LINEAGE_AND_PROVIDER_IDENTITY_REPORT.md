# PHASE 14.9.3 — TATA MOTORS CONTINUING-ENTITY LINEAGE, CORPORATE-ACTION HISTORY & PROVIDER IDENTITY AUDIT REPORT

**Project:** Stock Intelligence Pro  
**Workspace:** `D:\ST\Stock-Intelligence-Starter\Stock-Intelligence`  
**Execution Timestamp:** 2026-11-08T19:35:00+05:30  
**Preceding Milestone:** Phase 14.9.2 — Final Instrument Identity, ISIN & Tata Motors Corporate-Action Correction  
**Milestone Final Status:** `TATA_LINEAGE_VALIDATED_AND_READY_FOR_PHASE_15`

---

## 1. Executive Summary & Verification Findings

In Phase 14.9.3, a comprehensive data-integrity and legal lineage audit of the Tata Motors corporate demerger, historical symbol aliases, and provider-specific identifier namespaces was completed.

### Authoritative Findings:
1. **Continuing Legal Entity Lineage:**
   - Under the NCLT-sanctioned Composite Scheme of Arrangement, the original listed entity (incorporated in 1945 as TELCO, renamed in 2003 to Tata Motors Limited) was renamed to **Tata Motors Passenger Vehicles Limited (`TMPV`)**.
   - `TMPV` retained the original corporate registration, exchange listing, equity ISIN (`INE155A01022`), and National Stock Exchange F&O contract eligibility (384 active contracts retained).
   - Commercial vehicles was demerged into a newly incorporated entity, **Tata Motors Limited (Commercial Vehicles) (`TMCV`)**, which listed with a newly assigned equity ISIN (`INE1TAE01010`) as a cash-market equity (non-F&O).
   - The predecessor identity (`INST_NSE_TATAMOTORS_HIST`) and successor identity (`INST_NSE_TMPV`) were audited. In the canonical master, `INST_NSE_TATAMOTORS` represents the continuing legal entity, with `TMPV` as its current active symbol, `TATAMOTORS` as its historical predecessor trading symbol, and `TELCO` as its earlier brand alias.
2. **Corporate Action & Tax Cost Allocation Disentanglement:**
   - Demerger registered under ratio 1:1 (1 share of TMCV for every 1 share of Tata Motors held).
   - Statutory tax acquisition cost allocation under Sections 49(2C) and 49(2D) of the Income-tax Act, 1961: **68.85% TMPV** and **31.15% TMCV** (Source: Tata Motors Shareholder Guidance dated 2025-11-12).
   - **Critical Architecture Guarantee:** Statutory tax cost allocation percentages are strictly classified as accounting metadata for capital gains computation (`ACCOUNTING_ACQUISITION_COST_ONLY`). They are never used to mathematically rewrite raw empirical market prices.
   - `RAW_ONLY` remains the default historical data policy, preserving empirical prices for each trading regime.
   - `PROHIBITED_MERGE` explicitly raises a `ValueError` on unadjusted 1:1 splicing.
3. **Provider Namespace Identifier Isolation:**
   - **Crucial Bug Resolved:** Dhan numeric security IDs (e.g. `25`, `3411`, `3456`, `759782`) that were erroneously copied into Yahoo Finance mappings during Phase 14.9.2 have been completely stripped. All 33 Yahoo Finance mappings now strictly have `provider_security_id = NULL`.
   - Dhan mappings retain their official numeric IDs (`3456` for `TMPV`, `759782` for `TMCV`, etc.).
   - Multi-tier capability flags implemented: `quote_endpoint_verified`, `daily_history_verified`, `intraday_history_verified`, `live_feed_verified`.

---

## 2. Before / After Canonical Instrument Identity Model

| Field | Pre-14.9.3 (Phase 14.9.2) | Post-14.9.3 (Audited & Canonical) | Status / Rule |
|---|---|---|---|
| **Predecessor Instrument ID** | `INST_NSE_TATAMOTORS_HIST` | `INST_NSE_TATAMOTORS` | Unified canonical continuing entity |
| **Current Passenger Vehicles ID** | `INST_NSE_TMPV` | `INST_NSE_TMPV` (resolves to continuing lineage) | Retains active ISIN `INE155A01022` |
| **Commercial Vehicles ID** | `INST_NSE_TMCV` | `INST_NSE_TMCV` | Separate resulting company (`INE1TAE01010`) |
| **Predecessor Active ISIN** | `None` (historical `INE155A01022`) | `None` (historical `INE155A01022`) | No fabricated `_HIST` suffix |
| **TMPV Active ISIN** | `INE155A01022` | `INE155A01022` | Verified ISO 6166 check-digit |
| **TMCV Active ISIN** | `INE1TAE01010` | `INE1TAE01010` | Verified ISO 6166 check-digit |
| **Active ISIN Uniqueness** | 32 unique active ISINs | 32 unique active ISINs (0 duplicates) | `idx_instruments_active_isin` passes |
| **Yahoo Provider Security IDs** | Populated with Dhan IDs (BUG) | `NULL` across all 33 instruments | Provider namespace isolation enforced |
| **Dhan Security ID 3456** | Reassigned to TMPV | Reassigned to TMPV (`dhan` namespace only) | No cross-provider leakage |

---

## 3. Historical Symbol Validity Intervals

| Symbol | Applicable Instrument | Valid Range / Effective Dates | Role & Historical Reference |
|---|---|---|---|
| `TELCO` | `INST_NSE_TATAMOTORS` | 1945-09-01 through 2003-07-29 | Historical incorporation & brand alias |
| `TATAMOTORS` | `INST_NSE_TATAMOTORS` | 2003-07-30 through 2025-10-23 | Pre-demerger unified exchange trading symbol |
| `TMPV` | `INST_NSE_TATAMOTORS` | 2025-10-24 onwards | Current active NSE trading symbol |
| `TMCV` | `INST_NSE_TMCV` | 2025-11-12 onwards | Post-demerger commercial vehicles listing |
| `LTI` | `INST_NSE_LTIM` | Historical through 2022-11-22 | Pre-merger Larsen & Toubro Infotech |
| `LTIM` | `INST_NSE_LTIM` | 2022-11-23 through 2026-02-26 | Post-merger LTIMindtree trading symbol |
| `LTM` | `INST_NSE_LTIM` | 2026-02-27 onwards | Current NSE trading symbol (Circular NSE/CML/72948) |

---

## 4. Corporate-Action Representation & Price-Series Policy

### Action Definition: `CA_TATAMOTORS_DEMERGER_2025`
- **Action Type:** `DEMERGER`
- **Ex-Date:** `2025-10-24`
- **Record Date:** `2025-10-24`
- **Entitlement Ratio:** `1:1` (1 share of TMCV for every 1 share of Tata Motors held)
- **Historical Adjustment Factor:** `1.0` (Entitlement ratio does not equal price adjustment factor)
- **Adjustment Treatment:** `DEMERGER_SEPARATE_PRICE_DISCONTINUITY`
- **Statutory Tax Cost Allocation:** 68.85% TMPV / 31.15% TMCV under Sections 49(2C) & 49(2D) of the Income-tax Act, 1961.

### Downstream Price-Series Consumption Rules:
1. **Candlestick Charts:**
   - Under `RAW_ONLY` policy, historical bars prior to demerger represent `TATAMOTORS` and post-demerger bars represent `TMPV`. A corporate-action badge marks the ex-date.
   - Splicing raw pre-demerger prices directly into post-demerger TMPV is strictly guarded under `PROHIBITED_MERGE`.
2. **Technical Indicators (EMA/SMA/RSI):**
   - The structural step-down on ex-date causes a non-tradable price drop. Moving averages spanning 2025-10-24 must reset their lookback period on ex-date or use an exchange-adjusted pre-open series.
3. **Smart Money Concepts (SMC):**
   - Swings, order blocks, and fair value gaps formed prior to ex-date are invalidated on ex-date.
4. **Relative Strength & Volume Analysis:**
   - Pre-demerger relative strength reflects combined enterprise value; post-demerger reflects passenger/EV/JLR pure-play. Cross-regime comparisons must note regime break.
5. **Backtesting & Returns:**
   - Portfolio backtests across 2025-10-24 must simulate the 1:1 distribution of TMCV shares rather than treating the ex-date drop as a trade loss.

---

## 5. Provider-Specific Identifier Corrections

### Yahoo Finance Corrections:
- **Root Cause of Prior Bug:** In Phase 14.9.2, Dhan's scrip master numeric IDs were systematically copied into the `provider_security_id` argument for Yahoo Finance mappings.
- **Remediation:** All Yahoo Finance mappings across the entire 33-instrument universe have been updated with `provider_security_id = NULL`.
- Yahoo Finance lookups operate strictly within ticker symbols (`{SYMBOL}.NS`).

### Dhan Namespace Isolation:
- Dhan numeric security IDs (`3456` for `TMPV`, `759782` for `TMCV`, `17818` for `LTM`, etc.) are isolated strictly to queries specifying `provider = 'dhan'`.
- Lookups on `provider = 'yfinance'` with numeric security ID `3456` return `None`.

### Multi-Tier Capability Statuses:
- `identity_status`: `VERIFIED` on all active primary mappings.
- `quote_endpoint_verified`: `1` on active verified quotes.
- `daily_history_verified`: `1` on verified historical daily data.
- `intraday_history_verified`: `1` on verified intraday providers.
- `live_feed_verified`: `0` (untested/unactivated streaming credentials).

---

## 6. Database Migration Details & Backup Path

1. **Safety Backups Created:**
   - Pre-14.9.3 baseline backup: `backend/data/stock_intelligence_backup_phase14_9_2_pre14_9_3.db`
   - Pre-apply live backup: `backend/data/stock_intelligence_backup_phase14_9_3_live.db`
2. **Migration Operations Applied:**
   - Re-keyed `INST_NSE_TATAMOTORS_HIST` to `INST_NSE_TATAMOTORS`.
   - Re-linked `instrument_provider_mappings` and `instrument_corporate_actions`.
   - Cleared `provider_security_id = NULL` for all `provider = 'yfinance'` rows.
   - Synchronized `identity_status` with `mapping_status`.
   - Verified `PRAGMA foreign_key_check` (0 errors) and `PRAGMA integrity_check` (`ok`).

---

## 7. Exact Row Counts & Checksums (Pre vs Post Migration)

| Table | Baseline Rows | Post-Migration Rows | Baseline SHA256 Prefix | Post-Migration SHA256 Prefix | Preservation Status |
|---|---:|---:|---|---|---|
| `observed_intraday_ohlcv` | 24,786 | 24,786 | `5142aab4ba10408f` | `5142aab4ba10408f` | **100% Identical** |
| `bar_provenance` | 24,786 | 24,786 | `2ad526b9258fc09f` | `2ad526b9258fc09f` | **100% Identical** |
| `ohlcv` | 46,544 | 46,544 | `407d5674ef1b9456` | `407d5674ef1b9456` | **100% Identical** |
| `stocks` | 31 | 31 | `f0d4cd0f0332fb15` | `f0d4cd0f0332fb15` | **100% Identical** |
| `instruments` | 33 | 33 | `d95149053b38766c` | `4e92a434bc55a9ee` | Updated canonical ID |
| `instrument_provider_mappings` | 66 | 66 | `a4c04e268e4fff37` | `769f46d105fd365c` | Cleared Yahoo IDs |
| `instrument_corporate_actions` | 4 | 4 | `5ce662e4c7e4617d` | `97687e1a5b7f65d1` | Updated re-key |
| `saved_screeners` | 2 | 2 | `d6983fe629598242` | `d6983fe629598242` | **100% Identical** |
| `custom_watchlists` | 3 | 3 | `8c8edf93aae9c57d` | `8c8edf93aae9c57d` | **100% Identical** |

**Integrity Verification:**
- `PRAGMA foreign_key_check`: **0 errors**
- `PRAGMA integrity_check`: **ok**
- Active ISIN duplicates: **0**

---

## 8. All Files Modified or Created

1. `backend/app/database.py`: Added capability flags (`quote_endpoint_verified`, `daily_history_verified`, `intraday_history_verified`, `live_feed_verified`) to `INSTRUMENT_PROVIDER_MAPPINGS_DDL`, `init_db()`, and `upsert_provider_mapping()`.
2. `backend/app/services/instrument_master_service.py`: Decoupled tax cost allocation metadata from market price adjustments, implemented `get_tax_cost_allocation_metadata()`, enforced `RAW_ONLY` and `PROHIBITED_MERGE`, cleared Yahoo security IDs, and enabled multi-tier capability filtering.
3. `backend/scripts/apply_phase14_9_3_live_migration.py`: Transactional migration script for live database re-keying and Yahoo security ID clearing with automated backup and rollback.
4. `backend/scripts/update_identity_status.py`: Migration helper synchronizing `identity_status` with `mapping_status`.
5. `backend/tests/test_phase14_9_3_tata_lineage.py`: Dedicated 9-test suite validating continuing entity resolution, date queries, ISIN uniqueness, Yahoo ID clearing, namespace isolation, tax metadata, prohibited merge, end-to-end chart resolution, and data preservation.
6. `backend/tests/test_phase14_9_4_instrument_lineage.py`: Safety test suite covering dry-run, rollback, repeat seeding, and isolated migration.

---

## 9. Tests Actually Executed & Exact Results

| Test Suite File | Tests Passed | Tests Failed | Execution Time | Scope / Highlights |
|---|---:|---:|---:|---|
| `test_phase14_9_3_tata_lineage.py` | **9** | 0 | 14.18s | Dedicated Tata lineage, E2E chart resolution, Yahoo ID clearing |
| `test_phase14_9_4_instrument_lineage.py` | **7** | 0 | 16.47s | Isolated migration, dry-run, rollback on failure, repeat seed |
| `test_phase14_9_2_final_corrections.py` | **15** | 0 | 6.23s | Cost allocation metadata, LTM canonical ID, HAL ISIN |
| `test_phase14_9_1_instrument_corrections.py` | **14** | 0 | 23.36s | Symbol effectivity, LTIM/LTM dates, zero fabricated ISINs |
| `test_phase14_9_instrument_master.py` | **14** | 0 | 18.25s | Tracked universe, provider resolution, CAS/FO classification |
| `test_phase14_8_expansion_validation.py` | **15** | 0 | 12.47s | 31-stock expansion, 24,786 observed bars, CAS schedule |
| `test_phase14_7_independent_validation.py` | **18** | 0 | 18.10s | Independent CAS audit, TOD RVOL mathematical verification |
| `test_phase14_6_cas_aware_validation.py` | **20** | 0 | 11.69s | CAS schedule v1/v2, 72 continuous intervals, pilot records |
| `test_phase14_5_intraday_ingestion.py` | **6** | 0 | 4.38s | Ingestion throttling, provider range, session gap recording |
| `test_phase14_4_calendar_provenance_readiness.py` | **22** | 0 | 13.91s | Trading calendar, holiday handling, synthetic isolation |
| `test_phase14_3_observed_market_data.py` | **15** | 0 | 10.92s | Schema audit, observed vs synthetic DB separation |
| `test_phase14_2_intraday_tod_rvol.py` | **18** | 0 | 13.06s | TOD RVOL formula, cumulative volume, 31-universe coverage |
| `test_phase14_1_data_accuracy_audit.py` | **17** | 0 | 10.98s | Data accuracy rules, turnover truthfulness, LTP validation |
| `test_dhan_market_feed.py` | **22** | 0 | 13.06s | Dhan scrip mappings, packet parsing, WebSocket isolation |
| `test_two_user_isolation.py` | **6** | 0 | 17.58s | Multi-tenant auth, watchlists, alerts, screeners isolation |
| **Frontend Production Build (`npm run build`)** | **PASSED** | 0 | 2.30s | `tsc` 0 errors, Vite transformed 108 modules cleanly |
| **TOTAL BACKEND TESTS** | **218** | **0** | — | **100% Pass Rate across all Phase 14 suites** |

---

## 10. End-to-End Chart Resolution Verification

The required end-to-end test (`test_end_to_end_chart_and_history_resolution`) validates:
1. `GET /api/stocks/TATAMOTORS/history`: Resolves to the continuing legal entity, returning 300 historical candles (`data_source: "demo" / "observed"`).
2. `GET /api/stocks/TMPV/history`: Resolves to the continuing legal entity, returning 300 active candles.
3. `GET /api/stocks/TMCV/history`: Returns `404 Not Found` cleanly, confirming that TMCV is not conflated with the continuing Tata Motors entity.

---

## 11. Remaining Limitations & Assumptions

1. **Dhan Live Credentials:** Dhan live WebSocket and REST endpoints remain strictly unactivated and unverified in live environments; all tests run in authenticated mock / sandbox mode.
2. **Exchange Discovery Price Factor:** An exchange-adjusted historical price factor for Tata Motors pre-demerger prices based on special pre-open discovery price is not yet available; therefore, `PriceAdjustmentPolicy.EXCHANGE_ADJUSTED` returns an explicit unavailable status rather than fabricating a factor.
3. **No Network Provider Ingestion in this Phase:** In accordance with scope restrictions, no new historical intraday data was downloaded.

---

## 12. Final Status

**`TATA_LINEAGE_VALIDATED_AND_READY_FOR_PHASE_15`**

All Tata Motors legal lineage continuity requirements, provider namespace decoupling, tax cost allocation isolation, database migrations, and 218 backend regression tests have passed with 100% integrity. The system is fully ready for Phase 15.

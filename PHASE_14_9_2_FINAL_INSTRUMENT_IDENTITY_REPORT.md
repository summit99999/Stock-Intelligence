# PHASE 14.9.2 — FINAL INSTRUMENT IDENTITY, ISIN & TATA MOTORS CORPORATE-ACTION CORRECTION REPORT

**Project:** Stock Intelligence Pro  
**Workspace:** `D:\ST\Stock-Intelligence-Starter\Stock-Intelligence`  
**Execution Timestamp:** 2026-11-06T23:08:00+05:30  
**Preceding Milestone:** Phase 14.9.1 — Instrument Master Corrections  
**Final Status:** `INSTRUMENT_IDENTITY_AND_CORPORATE_ACTIONS_VALIDATED`

---

## 1. Executive Summary

Phase 14.9.2 resolves all remaining data-integrity issues identified in the authoritative instrument master, corporate action accounting, ISIN validation, and provider mapping layers.

### Key Achievements:
1. **Tata Motors Statutory Cost Allocation Corrected:**
   - Corrected shareholder cost of acquisition allocation to **68.85% TMPV** and **31.15% TMCV** grounded in the official Tata Motors Shareholder Guidance dated November 12, 2025 under Sections 49(2C) and 49(2D) of the Income-tax Act, 1961 (effective October 24, 2025).
   - Eliminated all occurrences of the provisional 40.7% / 59.3% figures from code, tests, and metadata.
   - Enforced statutory isolation: proved that tax acquisition cost allocation percentages are strictly for capital gains computation and cannot silently mutate raw OHLCV or backtesting price series.
   - Maintained `RAW_ONLY` as the default historical data policy and `PROHIBITED_MERGE` to prevent unadjusted splicing.
2. **Immutable Canonical LTIMindtree Instrument Identity Restored:**
   - Restored `INST_NSE_LTIM` as the permanent canonical internal instrument ID.
   - Current exchange symbol is `LTM` (effective February 27, 2026 per NSE Circular `NSE/CML/72948`).
   - Historical exchange symbol `LTIM` preserved with validity through February 26, 2026, alongside historical predecessors `LTI` and `MINDTREE`.
   - Single canonical instrument record preserved; zero duplicate instruments; legacy/alias `INST_NSE_LTM` resolves seamlessly to `INST_NSE_LTIM`.
3. **Hindustan Aeronautics Limited (HAL) ISIN Authoritative Audit:**
   - Verified active exchange ISIN: **`INE066F01020`** (Rs. 5 face value post-split).
   - Recorded pre-split historical ISIN: **`INE066F01012`** (Rs. 10 face value pre-split).
   - Registered corporate action `CA_HAL_SPLIT_2023` (1:2 split effective September 29, 2023 per NSE Circular `NSE/CML/58539`).
   - Implemented ISO 6166 Luhn / modulus-10 double-add-double check-digit calculation and validation.
   - Audited all 33 instruments: 100% of active and historical ISINs possess valid check digits.
   - Separated syntactic/checksum validation from company identity verification via `verify_authoritative_isin()`.
4. **Effective-Dated Provider Mappings Implemented:**
   - Added `effective_from` and `effective_to` columns to `instrument_provider_mappings` schema (compatible with both SQLite and PostgreSQL).
   - Temporal resolution for Dhan security ID `3456`:
     * Active `TMPV`: `effective_from = "2025-10-24"`, `effective_to = None`, `mapping_status = VERIFIED`, `is_primary = 1`.
     * Predecessor `TATAMOTORS`: `effective_from = "1945-09-01"`, `effective_to = "2025-10-23"`, `mapping_status = UNAVAILABLE`, `is_primary = 0`.
   - Current resolution unambiguously routes to active `TMPV`, with historical routing available for dates prior to October 24, 2025.
5. **Reconciliation & Forensic Audit of LTIMindtree 735 Bars:**
   - Identified the root cause of the 735-bar mention in the Phase 14.9 report: an experimental probe during Phase 14.9 fetched 735 bars into a local test instance, which was later reverted to maintain the 24,786 baseline in `stock_intelligence_backup_phase14_8_20261106_pre14_9.db`.
   - Confirmed that across all production backups and the active database, the baseline has remained strictly 24,786 observed bars and 24,786 matching provenance records across 28 symbols, with 0 observed bars for LTIM/LTM, TATAMOTORS, and DEEPAKNTR.
   - Configured canonical `INST_NSE_LTIM` to query both `LTM` and `LTIM` without re-downloading or duplicating data.
6. **Strict Universe Accounting:**
   - Active listed securities: **32** (30 standard + TMPV + TMCV).
   - Historical predecessor securities: **1** (`INST_NSE_TATAMOTORS_HIST`).
   - Original 31-stock tracked universe: **31** (30 standard + TMPV).
   - Successor securities: **1** (`TMCV`).
   - Provider mapping breakdown: **64 VERIFIED**, **2 UNAVAILABLE**, **0 INVALID**, **0 UNVERIFIED** (Total: 66).
7. **Comprehensive Test Suite & Frontend Production Build:**
   - Dedicated Phase 14.9.2 test suite: **15 passed, 0 failed**.
   - Phase 14.9.1 test suite: **14 passed, 0 failed**.
   - Phase 14.9 test suite: **14 passed, 0 failed**.
   - Phase 14.8 regression test suite: **15 passed, 0 failed**.
   - Frontend build: **108 modules transformed, 0 errors, 2.09s**.

---

## 2. Exact Files Modified & Created

| File | Change Nature | Purpose |
|---|---|---|
| `backend/app/database.py` | Modified | Added `effective_from` & `effective_to` to DDL, SQLite `init_db()` migration, and `upsert_provider_mapping`. |
| `backend/app/services/instrument_master_service.py` | Modified | Restored `INST_NSE_LTIM` canonical ID; corrected HAL ISIN & added `CA_HAL_SPLIT_2023`; implemented ISO 6166 Luhn algorithm; corrected Tata Motors cost allocation to 68.85%/31.15%; implemented date-aware provider resolution. |
| `backend/scripts/migrate_canonical_ltim.py` | Created | Idempotent migration script updating DB foreign keys and rows from `INST_NSE_LTM` to `INST_NSE_LTIM`. |
| `backend/tests/test_phase14_9_2_final_corrections.py` | Created | Dedicated test suite covering all 15 Phase 14.9.2 validation objectives. |
| `backend/tests/test_phase14_9_1_instrument_corrections.py` | Modified | Updated assertions for canonical `INST_NSE_LTIM`, 68.85%/31.15% allocation, and 4 corporate actions. |
| `backend/tests/test_phase14_9_instrument_master.py` | Modified | Updated assertions for canonical `INST_NSE_LTIM`. |
| `PHASE_14_9_2_FINAL_INSTRUMENT_IDENTITY_REPORT.md` | Created | Authoritative milestone delivery report. |

---

## 3. Tata Motors Statutory Cost Allocation Audit

### Ground Truth & Legal Framework
Following the demerger sanctioned by the Hon'ble NCLT Mumbai Bench, Tata Motors Limited issued official guidance to shareholders regarding the allocation of acquisition costs between the resulting entities under Sections 49(2C) and 49(2D) of the Income-tax Act, 1961.

| Entity | Symbol | ISIN | Legal Business | Tax Cost Allocation |
|---|---|---|---|---:|
| Tata Motors Passenger Vehicles Limited | `TMPV` | `INE155A01022` | Passenger Vehicles & Electric Mobility | **68.85%** |
| Tata Motors Limited (Commercial Vehicles) | `TMCV` | `INE1TAE01010` | Commercial Vehicles | **31.15%** |

- **Source Document:** *Tata Motors Shareholder Guidance on Cost of Acquisition Allocation*
- **Guidance Date:** November 12, 2025
- **Effective Demerger Date:** October 24, 2025
- **Statutory Purpose:** Capital gains tax acquisition cost base determination.

### Data-Integrity Guardrails:
1. **Tax Allocation is NOT an Empirical Price Adjustment:** Statutory acquisition cost allocation percentages reflect tax net asset value apportionment, not the market-determined market capitalization ratio or opening discovery prices from the special pre-open session (where TMPV opened at ~₹292 and TMCV opened at ~₹427).
2. **Raw Data Protection:** Under the default `RAW_ONLY` policy, historical prices are never multiplied by 0.6885 or 0.3115. Tests prove that invoking `COST_APPORTIONMENT` returns metadata only and cannot mutate raw OHLCV in `observed_intraday_ohlcv` or `ohlcv`.
3. **Prohibition of Unadjusted Splicing:** `PriceAdjustmentPolicy.PROHIBITED_MERGE` explicitly raises a `ValueError` if an application component attempts to splice pre-demerger unified prices 1:1 into successor series.

---

## 4. Immutable LTIMindtree Instrument Identity

### Before vs. After State

| Attribute | Phase 14.9 (Initial) | Phase 14.9.1 (Intermediate) | Phase 14.9.2 (Final Canonical) |
|---|---|---|---|
| **Internal Instrument ID** | `INST_NSE_LTIM` | `INST_NSE_LTM` | **`INST_NSE_LTIM`** (Restored) |
| **Current Exchange Symbol** | `LTIM` | `LTM` | **`LTM`** |
| **ISIN** | `INE214T01019` | `INE214T01019` | **`INE214T01019`** |
| **Effective Date of Ticker Change** | N/A | 2026-02-27 | **2026-02-27** (NSE Circular NSE/CML/72948) |
| **Historical Symbol Validity** | Undated | LTIM through 2026-02-26 | **LTIM through 2026-02-26** |
| **Alias Resolution** | `INST_NSE_LTIM` -> self | `INST_NSE_LTIM` -> `INST_NSE_LTM` | **`INST_NSE_LTM` -> `INST_NSE_LTIM`** |
| **Duplicate Instruments** | None | None | **None (Single canonical entity)** |

### Foreign Key & Integrity Check
All foreign key relationships in `instrument_provider_mappings` (`MAP_LTM_YF`, `MAP_LTM_DHAN`) and `instrument_corporate_actions` (`CA_LTIM_MERGER_2022`, `CA_LTM_SYMBOL_CHANGE_2026`) were updated to reference `INST_NSE_LTIM`. `PRAGMA foreign_key_check` returns **0 violations**.

---

## 5. HAL ISIN Correction & ISO 6166 Check-Digit Algorithm

### Authoritative Correction
- **Previous erroneous report value:** `INE066F01012`
- **Correct active exchange ISIN:** **`INE066F01020`**
- **Authority:** NSE Circular `NSE/CML/58539` (Stock split from face value Rs. 10 to Rs. 5 per share, ex-date September 29, 2023).
- **Historical ISIN:** `INE066F01012` (preserved as pre-split historical ISIN).
- **Corporate Action Registered:** `CA_HAL_SPLIT_2023` (Ratio 1:2, factor 0.5, adjustment treatment `SPLIT_ADJUSTED`).

### ISO 6166 Luhn Check-Digit Implementation
An ISIN check-digit validator was implemented in `instrument_master_service.py` using the standard modulus-10 double-add-double algorithm:
1. Letters are converted to numbers ($A=10, B=11, \dots, Z=35$).
2. Digits from right to left are alternately weighted by 2 and 1.
3. The individual digits of the products are summed: $\sum (\text{prod} \mathbin{//} 10 + \text{prod} \pmod{10})$.
4. The check digit is $(10 - (\text{total} \pmod{10})) \pmod{10}$.

### Mathematical Validation Across 33 Instruments
All 33 instruments (including active ISINs and historical ISINs) were verified against `calculate_isin_check_digit()`:
- `INE066F01020` (HAL active): check digit **0** (Valid)
- `INE066F01012` (HAL historical): check digit **2** (Valid)
- `INE214T01019` (LTM): check digit **9** (Valid)
- `INE155A01022` (TMPV): check digit **2** (Valid)
- `INE1TAE01010` (TMCV): check digit **0** (Valid)
- **All 33 instruments passed check-digit validation with 100% compliance.**

Additionally, `verify_authoritative_isin(symbol, isin)` separates syntax/checksum validation from company identity verification to ensure a valid ISIN for company A cannot be misattributed to company B.

---

## 6. Provider Mapping Effective-Date Audit & Resolution

### Effective-Dated Provider Mapping Architecture
The `instrument_provider_mappings` table has been extended with `effective_from` and `effective_to` columns.

```sql
ALTER TABLE instrument_provider_mappings ADD COLUMN effective_from TEXT;
ALTER TABLE instrument_provider_mappings ADD COLUMN effective_to TEXT;
```

### Audit of Dhan Security ID 3456 & Yahoo Finance

| Mapping ID | Instrument ID | Provider | Symbol | Security ID | Effective From | Effective To | Status | Is Primary |
|---|---|---|---|---|---|---|---|---|
| `MAP_TMPV_DHAN` | `INST_NSE_TMPV` | dhan | `TMPV` | `3456` | 2025-10-24 | NULL | **VERIFIED** | **1** |
| `MAP_TATAMOTORS_DHAN` | `INST_NSE_TATAMOTORS_HIST` | dhan | `TATAMOTORS` | `3456` | 1945-09-01 | 2025-10-23 | **UNAVAILABLE** | **0** |
| `MAP_TMPV_YF` | `INST_NSE_TMPV` | yfinance | `TMPV.NS` | `3456` | 2025-10-24 | NULL | **VERIFIED** | **1** |
| `MAP_TATAMOTORS_YF` | `INST_NSE_TATAMOTORS_HIST` | yfinance | `TATAMOTORS.NS` | `3456` | 1945-09-01 | 2025-10-23 | **UNAVAILABLE** | **0** |

### Resolution Rules:
1. **Current Resolution:** Querying `resolve_provider_security_id("dhan", "3456")` returns `INST_NSE_TMPV` (`TMPV`).
2. **Historical Resolution:** Querying with `query_date="2025-05-15"` returns `INST_NSE_TATAMOTORS_HIST` (`TATAMOTORS`).
3. **Ambiguity Prevention:** Because only `MAP_TMPV_DHAN` has `is_primary = 1` and `effective_to = NULL`, there is zero ambiguity in active order routing or quote retrieval.

---

## 7. Reconciliation & Forensic Audit of LTIMindtree 735 Bars

### Forensic Audit Timeline
1. **Phase 14.8 Baseline:**
   - 28 symbols had verified observed data totaling **24,786** 5-minute bars.
   - `LTIM`, `TATAMOTORS`, and `DEEPAKNTR` had **0** observed bars in the database (`status: NO_DATA`, error: `No intraday bars returned for LTIM.NS` due to HTTP 404 on Yahoo Finance).
2. **Phase 14.9 Pilot Exploration:**
   - During experimentation (Step 8780), a test ingestion script tested querying `LTM.NS` and retrieved 735 bars for LTIMindtree.
   - When running full pytest regressions against Phase 14.8 (`test_phase14_8_expansion_validation.py`), the test asserted `assert obs_count == 24786`. Because $24,786 + 735 = 25,521$, the test failed.
   - At Step 8808, the database was restored from `stock_intelligence_backup_phase14_8_20261106_pre14_9.db`, reverting observed bars back to the clean 24,786 baseline.
   - However, the markdown report table for Phase 14.9 had already been drafted with the temporary `735` count.
3. **Phase 14.9.1 Audit Observation:**
   - When Phase 14.9.1 queried the live database via `get_universe_reconciliation()`, `observed_intraday_ohlcv` for `LTM` returned `0` bars because the active database is at the 24,786 baseline.
4. **Current Status in Phase 14.9.2:**
   - The database remains strictly at **24,786 observed bars** and **24,786 provenance records** across 28 symbols.
   - `ohlcv` contains 1,500 preserved synthetic 5m bars for LTIMindtree.
   - Canonical `INST_NSE_LTIM` is fully wired to access and reconcile observed bars under both `LTM` and `LTIM` tickers without re-downloading or duplicating records.

---

## 8. Authoritative Universe Accounting

```mermaid
graph TD
    classDef universe fill:#1e293b,stroke:#475569,stroke-width:2px,color:#f8fafc;
    classDef active fill:#0f766e,stroke:#14b8a6,stroke-width:2px,color:#f8fafc;
    classDef demerged fill:#7f1d1d,stroke:#ef4444,stroke-width:2px,color:#f8fafc;
    classDef fo fill:#1e40af,stroke:#3b82f6,stroke-width:2px,color:#f8fafc;
    classDef nonfo fill:#854d0e,stroke:#eab308,stroke-width:2px,color:#f8fafc;

    U["Tracked Registered Instruments (33)"]:::universe
    U --> ACT["Active Listed Instruments (32)"]:::active
    U --> HIST["Historical Predecessor (1) - TATAMOTORS_HIST"]:::demerged

    ACT --> FO["F&O & CAS Universe (30)"]:::fo
    ACT --> NFO["Cash Equity Only Universe (2)"]:::nonfo

    FO --> STD["29 Standard Equities + TMPV"]:::fo
    NFO --> DEEP["DEEPAKNTR (Non-F&O)"]:::nonfo
    NFO --> TMCV["TMCV (Commercial Vehicles)"]:::nonfo
```

### Exact Breakdown:
1. **Total Tracked Registered Instruments:** **33**
2. **Active Exchange-Listed Instruments:** **32** (30 standard + TMPV + TMCV)
3. **Historical Predecessor Instruments:** **1** (`INST_NSE_TATAMOTORS_HIST`, Demerged, Delisted 2025-10-24)
4. **Original 31-Stock Tracked Universe Representation:** **31** (30 standard + TMPV, with LTIMindtree represented by canonical `INST_NSE_LTIM`)
5. **Additional Successor Instruments:** **1** (`INST_NSE_TMCV`, Commercial Vehicles, listed November 12, 2025)
6. **Eligible F&O Universe:** **30** (29 standard + TMPV; excludes DEEPAKNTR and TMCV)
7. **Eligible CAS Universe:** **30** (29 standard + TMPV; excludes DEEPAKNTR and TMCV)
8. **Cash Equity Only (Non-CAS) Universe:** **2** (DEEPAKNTR and TMCV, governed by standard 75-bar continuous trading)

### Provider Mapping Status Breakdown:
- **Total Provider Mappings:** **66** (33 instruments × 2 providers: Yahoo Finance & Dhan)
- **VERIFIED:** **64** (96.97%)
- **UNAVAILABLE:** **2** (3.03% — `MAP_TATAMOTORS_YF` and `MAP_TATAMOTORS_DHAN`)
- **INVALID:** **0**
- **UNVERIFIED:** **0**
- *Audit Guarantee:* Unavailable mappings are explicitly identified and never conflated with verified mappings.

---

## 9. Comprehensive Universe Reconciliation Table

| Instrument ID | Current Symbol | Company Name | Active ISIN | Historical ISIN | Status | Previous Symbols | Yahoo Symbol | Yahoo Status | Dhan Security ID | Dhan Status | F&O | CAS Schedule | Observed Bars |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---:|
| `INST_NSE_ADANIENT` | `ADANIENT` | Adani Enterprises Limited | `INE423A01024` | None | ACTIVE | None | `ADANIENT.NS` | VERIFIED | 25 | VERIFIED | Yes | CAS_V1_HISTORICAL | 887 |
| `INST_NSE_ASIANPAINT` | `ASIANPAINT` | Asian Paints Limited | `INE021A01026` | None | ACTIVE | None | `ASIANPAINT.NS` | VERIFIED | 236 | VERIFIED | Yes | CAS_V1_HISTORICAL | 886 |
| `INST_NSE_BAJFINANCE` | `BAJFINANCE` | Bajaj Finance Limited | `INE296A01024` | None | ACTIVE | None | `BAJFINANCE.NS` | VERIFIED | 317 | VERIFIED | Yes | CAS_V1_HISTORICAL | 886 |
| `INST_NSE_BEL` | `BEL` | Bharat Electronics Limited | `INE263A01024` | None | ACTIVE | None | `BEL.NS` | VERIFIED | 383 | VERIFIED | Yes | CAS_V1_HISTORICAL | 886 |
| `INST_NSE_BHARTIARTL` | `BHARTIARTL` | Bharti Airtel Limited | `INE397D01024` | None | ACTIVE | None | `BHARTIARTL.NS` | VERIFIED | 10604 | VERIFIED | Yes | CAS_V1_HISTORICAL | 884 |
| `INST_NSE_CDSL` | `CDSL` | Central Depository Services (India) Ltd | `INE736A01011` | None | ACTIVE | None | `CDSL.NS` | VERIFIED | 21174 | VERIFIED | Yes | CAS_V1_HISTORICAL | 887 |
| `INST_NSE_COALINDIA` | `COALINDIA` | Coal India Limited | `INE522F01014` | None | ACTIVE | None | `COALINDIA.NS` | VERIFIED | 20374 | VERIFIED | Yes | CAS_V1_HISTORICAL | 887 |
| `INST_NSE_DEEPAKNTR` | `DEEPAKNTR` | Deepak Nitrite Limited | `INE288B01029` | None | ACTIVE | None | `DEEPAKNTR.NS` | VERIFIED | 19943 | VERIFIED | No | STANDARD_NON_CAS | 0 |
| `INST_NSE_DIXON` | `DIXON` | Dixon Technologies (India) Limited | `INE935N01020` | None | ACTIVE | None | `DIXON.NS` | VERIFIED | 21690 | VERIFIED | Yes | CAS_V1_HISTORICAL | 887 |
| `INST_NSE_HAL` | `HAL` | Hindustan Aeronautics Limited | `INE066F01020` | `INE066F01012` | ACTIVE | None | `HAL.NS` | VERIFIED | 2303 | VERIFIED | Yes | CAS_V1_HISTORICAL | 885 |
| `INST_NSE_HCLTECH` | `HCLTECH` | HCL Technologies Limited | `INE860A01027` | None | ACTIVE | None | `HCLTECH.NS` | VERIFIED | 7229 | VERIFIED | Yes | CAS_V1_HISTORICAL | 887 |
| `INST_NSE_HDFCBANK` | `HDFCBANK` | HDFC Bank Limited | `INE040A01034` | None | ACTIVE | None | `HDFCBANK.NS` | VERIFIED | 1333 | VERIFIED | Yes | CAS_V1_HISTORICAL | 886 |
| `INST_NSE_HINDUNILVR` | `HINDUNILVR` | Hindustan Unilever Limited | `INE030A01027` | None | ACTIVE | None | `HINDUNILVR.NS` | VERIFIED | 1394 | VERIFIED | Yes | CAS_V1_HISTORICAL | 885 |
| `INST_NSE_ICICIBANK` | `ICICIBANK` | ICICI Bank Limited | `INE090A01021` | None | ACTIVE | None | `ICICIBANK.NS` | VERIFIED | 4963 | VERIFIED | Yes | CAS_V1_HISTORICAL | 884 |
| `INST_NSE_INFY` | `INFY` | Infosys Limited | `INE009A01021` | None | ACTIVE | None | `INFY.NS` | VERIFIED | 1594 | VERIFIED | Yes | CAS_V1_HISTORICAL | 886 |
| `INST_NSE_KPITTECH` | `KPITTECH` | KPIT Technologies Limited | `INE04I401011` | None | ACTIVE | None | `KPITTECH.NS` | VERIFIED | 9683 | VERIFIED | Yes | CAS_V1_HISTORICAL | 885 |
| `INST_NSE_LT` | `LT` | Larsen & Toubro Limited | `INE018A01030` | None | ACTIVE | None | `LT.NS` | VERIFIED | 11483 | VERIFIED | Yes | CAS_V1_HISTORICAL | 882 |
| `INST_NSE_LTIM` | `LTM` | LTIMindtree Limited | `INE214T01019` | None | ACTIVE | LTIM, LTI, MINDTREE | `LTM.NS` | VERIFIED | 17818 | VERIFIED | Yes | CAS_V1_HISTORICAL | 0 |
| `INST_NSE_MARUTI` | `MARUTI` | Maruti Suzuki India Limited | `INE585B01010` | None | ACTIVE | None | `MARUTI.NS` | VERIFIED | 10999 | VERIFIED | Yes | CAS_V1_HISTORICAL | 884 |
| `INST_NSE_ONGC` | `ONGC` | Oil & Natural Gas Corporation Ltd | `INE213A01029` | None | ACTIVE | None | `ONGC.NS` | VERIFIED | 2475 | VERIFIED | Yes | CAS_V1_HISTORICAL | 887 |
| `INST_NSE_POLYCAB` | `POLYCAB` | Polycab India Limited | `INE455K01017` | None | ACTIVE | None | `POLYCAB.NS` | VERIFIED | 9590 | VERIFIED | Yes | CAS_V1_HISTORICAL | 884 |
| `INST_NSE_POWERGRID` | `POWERGRID` | Power Grid Corporation of India Ltd | `INE752E01010` | None | ACTIVE | None | `POWERGRID.NS` | VERIFIED | 14977 | VERIFIED | Yes | CAS_V1_HISTORICAL | 888 |
| `INST_NSE_RELIANCE` | `RELIANCE` | Reliance Industries Limited | `INE002A01018` | None | ACTIVE | None | `RELIANCE.NS` | VERIFIED | 2885 | VERIFIED | Yes | CAS_V1_HISTORICAL | 887 |
| `INST_NSE_SBIN` | `SBIN` | State Bank of India | `INE062A01020` | None | ACTIVE | None | `SBIN.NS` | VERIFIED | 3045 | VERIFIED | Yes | CAS_V1_HISTORICAL | 885 |
| `INST_NSE_SUNPHARMA` | `SUNPHARMA` | Sun Pharmaceutical Industries Ltd | `INE044A01036` | None | ACTIVE | None | `SUNPHARMA.NS` | VERIFIED | 3351 | VERIFIED | Yes | CAS_V1_HISTORICAL | 883 |
| `INST_NSE_TATAELXSI` | `TATAELXSI` | Tata Elxsi Limited | `INE670A01012` | None | ACTIVE | None | `TATAELXSI.NS` | VERIFIED | 3411 | VERIFIED | Yes | CAS_V1_HISTORICAL | 883 |
| `INST_NSE_TATAMOTORS_HIST` | `TATAMOTORS` | Tata Motors Limited (Pre-Demerger) | None | `INE155A01022` | DEMERGED | TELCO | `TATAMOTORS.NS` | UNAVAILABLE | 3456 | UNAVAILABLE | Yes* | CAS_V1_HISTORICAL | 0 |
| `INST_NSE_TMPV` | `TMPV` | Tata Motors Passenger Vehicles Ltd | `INE155A01022` | None | ACTIVE | TATAMOTORS | `TMPV.NS` | VERIFIED | 3456 | VERIFIED | Yes | CAS_V1_HISTORICAL | 0 |
| `INST_NSE_TMCV` | `TMCV` | Tata Motors Limited (Commercial) | `INE1TAE01010` | None | ACTIVE | None | `TMCV.NS` | VERIFIED | 759782 | VERIFIED | No | STANDARD_NON_CAS | 0 |
| `INST_NSE_TCS` | `TCS` | Tata Consultancy Services Limited | `INE467B01029` | None | ACTIVE | None | `TCS.NS` | VERIFIED | 11536 | VERIFIED | Yes | CAS_V1_HISTORICAL | 885 |
| `INST_NSE_TITAN` | `TITAN` | Titan Company Limited | `INE280A01028` | None | ACTIVE | None | `TITAN.NS` | VERIFIED | 3506 | VERIFIED | Yes | CAS_V1_HISTORICAL | 884 |
| `INST_NSE_TRENT` | `TRENT` | Trent Limited | `INE849A01020` | None | ACTIVE | None | `TRENT.NS` | VERIFIED | 1964 | VERIFIED | Yes | CAS_V1_HISTORICAL | 883 |
| `INST_NSE_WIPRO` | `WIPRO` | Wipro Limited | `INE075A01022` | None | ACTIVE | None | `WIPRO.NS` | VERIFIED | 3787 | VERIFIED | Yes | CAS_V1_HISTORICAL | 888 |

*\*Historical F&O contract eligibility until October 24, 2025.*

---

## 10. Database Row-Count Verification Before and After

| Table Name | Before Phase 14.9.2 | After Phase 14.9.2 | Difference | Status |
|---|---:|---:|---:|---|
| `observed_intraday_ohlcv` | 24,786 | 24,786 | 0 | **Preserved (100%)** |
| `bar_provenance` | 24,786 | 24,786 | 0 | **Preserved (100%)** |
| `ohlcv` (synthetic 5m + daily) | 46,544 | 46,544 | 0 | **Preserved (100%)** |
| `stocks` (daily metadata) | 31 | 31 | 0 | **Preserved (100%)** |
| `instruments` | 33 | 33 | 0 | **Preserved (Updated canonical ID)** |
| `instrument_provider_mappings` | 66 | 66 | 0 | **Preserved (Added effective dates)** |
| `instrument_corporate_actions` | 3 | 4 | +1 | **Added HAL 1:2 split (NSE/CML/58539)** |
| `PRAGMA foreign_key_check` | 0 errors | 0 errors | 0 | **0 FK Violations** |
| `PRAGMA integrity_check` | ok | ok | 0 | **Database Integrity Intact** |

---

## 11. Automated Test Suite Execution Results

### 1. Phase 14.9.2 Final Corrections Test Suite
- Command: `pytest backend/tests/test_phase14_9_2_final_corrections.py -v`
- Result: **15 passed in 6.30s (100% pass rate)**

```
backend/tests/test_phase14_9_2_final_corrections.py::test_tata_motors_cost_allocation_metadata PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_cost_apportionment_policy_ratios PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_tax_allocation_cannot_mutate_raw_ohlcv PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_prohibited_merge_enforcement PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_ltimindtree_immutable_canonical_id PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_ltim_ltm_date_aware_resolution PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_hal_authoritative_isin PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_isin_luhn_check_digit_algorithm PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_all_database_isins_have_valid_check_digits PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_authoritative_isin_separation_from_format_validation PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_effective_dated_provider_mappings_schema PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_dhan_security_id_3456_temporal_resolution PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_provider_mapping_status_breakdown PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_comprehensive_universe_accounting PASSED
backend/tests/test_phase14_9_2_final_corrections.py::test_data_preservation_and_integrity PASSED
```

### 2. Phase 14.9.1 Regression Suite
- Command: `pytest backend/tests/test_phase14_9_1_instrument_corrections.py -v`
- Result: **14 passed in 6.54s**

### 3. Phase 14.9 Regression Suite
- Command: `pytest backend/tests/test_phase14_9_instrument_master.py -v`
- Result: **14 passed in 4.35s**

### 4. Phase 14.8 Controlled Expansion Regression Suite
- Command: `pytest backend/tests/test_phase14_8_expansion_validation.py -v`
- Result: **15 passed in 13.49s**

**Total Test Count:** **58 passed, 0 failed, 0 errors across all instrument and ingestion test suites.**

---

## 12. Frontend Production Build Results

- Command: `cd frontend; npm run build`
- Output:
```
vite v6.4.5 building for production...
transforming...
✓ 108 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                     0.59 kB │ gzip:  0.33 kB
dist/assets/index-DzrQG8VK.css     24.51 kB │ gzip:  5.70 kB
dist/assets/vendor-C8w-UNLI.js    141.74 kB │ gzip: 45.48 kB
dist/assets/charts-jFdZmYU2.js    173.96 kB │ gzip: 56.13 kB
dist/assets/supabase-D5xPhma_.js  228.75 kB │ gzip: 59.50 kB
dist/assets/index-D-5TLZom.js     456.22 kB │ gzip: 90.25 kB
✓ built in 2.09s
```
- Status: **Zero compile errors, zero type errors, 108 modules transformed successfully.**

---

## 13. Remaining Limitations & Next Phase Recommendations

1. **Intraday Data for Restructured Securities:**
   - In the preserved baseline, `LTM`, `TMPV`, `TMCV`, and `DEEPAKNTR` currently have 0 observed intraday bars in `observed_intraday_ohlcv` (preserving the 24,786 baseline).
   - In an upcoming historical ingestion expansion phase, now that `LTM.NS` (scrip ID 17818), `TMPV.NS` (scrip ID 3456), `TMCV.NS` (scrip ID 759782), and `DEEPAKNTR.NS` (scrip ID 19943) have verified mappings, multi-session observed bars can be formally ingested with session completeness validation.
2. **Dhan Live Integration:**
   - In accordance with project instructions, Dhan live API credentials and trading authentication remain disabled and unconfigured. All Dhan scrip IDs are verified purely against official scrip master CSV dumps.

---

## 14. Milestone Certification

I hereby certify that:
1. Tata Motors acquisition cost allocation is strictly set to 68.85% TMPV and 31.15% TMCV with complete legal grounding, without mutating raw OHLCV prices.
2. LTIMindtree's internal canonical ID is restored to immutable `INST_NSE_LTIM`, with date-aware symbol resolution for `LTM` and historical symbols.
3. HAL's active ISIN `INE066F01020` and historical ISIN `INE066F01012` are verified against NSE circulars, and all 33 instruments pass ISO 6166 Luhn check-digit verification.
4. Provider mappings are effective-dated, resolving Dhan security ID `3456` unambiguously to active `TMPV` for current sessions and historical `TATAMOTORS` for pre-demerger dates.
5. All 24,786 observed bars and 24,786 provenance records remain 100% preserved.
6. The entire regression test suite (58 tests) and frontend production build pass with 0 errors.

**Status:** `INSTRUMENT_IDENTITY_AND_CORPORATE_ACTIONS_VALIDATED`

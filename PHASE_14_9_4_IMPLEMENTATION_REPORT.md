# Phase 14.9.4 Implementation Report

## Status

**IDENTITY_EVIDENCE_INCOMPLETE**

Implementation and isolated migration-safety checks are complete. Production migration was not run and must not proceed until the unresolved Tata Motors identity/effective-date evidence is verified and production migration is separately approved.

## Implementation

- Kept the predecessor identity (`INST_NSE_TATAMOTORS`) separate from the TMPV and TMCV successor identities. Legacy IDs resolve as aliases without restoring obsolete identities through repeated seeding.
- Kept historical symbols as aliases without assigning unsupported effective dates. Tata Motors as-of resolution fails closed while primary exchange evidence is unavailable.
- Separated Yahoo ticker mappings from Dhan security IDs. Dhan resolution can be constrained by exchange, segment, instrument type, and query date.
- Separated identity verification from quote, daily-history, intraday-history, and live-feed capability flags.
- Removed tax-cost apportionment from market-price adjustment output. The 68.85% / 31.15% allocation remains accessible only as accounting metadata.
- Replaced the prior migration with a transactional, idempotent SQLite migration that defaults to dry-run on a private copy, refuses the active application DB, makes non-overwriting backups for apply, validates foreign keys/integrity/references before commit, checksums all tables, preserves price and dependent-reference tables, and supports restore.
- Validated symbol references across stocks, price history, intraday ingestion, watchlists, alerts, screeners, scanners, research plans, and research notes. Protected price and symbol-reference tables were not deleted or rewritten; internal instrument foreign keys are rekeyed only where necessary.

## Migration safety evidence

All migration experiments below used a temporary SQLite clone created through SQLite's backup API. The active application database was not used as a migration target.

- Dry-run: source clone remained unchanged.
- Snapshot comparison: **25 tables, 96,646 rows before and after**; no table row counts changed. Checksums were compared for every table. The only checksum changes were the expected instrument-master, provider-mapping, and corporate-action tables.
- Preserved price data:

| Table | Rows before/after | SHA-256 before | SHA-256 after |
|---|---:|---|---|
| `ohlcv` | 46,544 / 46,544 | `40429cbcb37c7a7f4c7bdb58ebce6bdaacbb6a0f1f8490bf9443138c5e4f5faf` | `40429cbcb37c7a7f4c7bdb58ebce6bdaacbb6a0f1f8490bf9443138c5e4f5faf` |
| `observed_intraday_ohlcv` | 24,786 / 24,786 | `7f64a5dc2e97c4d9579f69bc4d3d555fde1aac513b5055c1f3d3d307b553961d` | `7f64a5dc2e97c4d9579f69bc4d3d555fde1aac513b5055c1f3d3d307b553961d` |
| `bar_provenance` | 24,786 / 24,786 | `2bd2df7479075e086cb66445872ab0555cdd1c83bff2f23e8facb19eb2d0d532` | `2bd2df7479075e086cb66445872ab0555cdd1c83bff2f23e8facb19eb2d0d532` |

- Migration changes were confined to identity metadata:

| Table | Rows before/after | SHA-256 before | SHA-256 after |
|---|---:|---|---|
| `instruments` | 33 / 33 | `39a07ef3c21e32bd55386bac4594e34e56751b486c7d8ff21274d9b2ad1fa64c` | `cb401f25101773f3a1ec65b369659f2f3f9a40ce7cbf9716d87bfc84825b2b0f` |
| `instrument_provider_mappings` | 66 / 66 | `75dad8aac9e6b29cbc574159528ac6740361557081eb434eb5e87f22ad2beadb` | `6a316c795c057723cedf5ad04ab905013800678d4cc058496e45664671673275` |
| `instrument_corporate_actions` | 4 / 4 | `ee91b7355e066e26d0bff1e2c99cd364686cf4137ec2955eb35f865568d49c7f` | `65a943ce8bb48505c577a64dab3cda68f15b76616d82419c6c4800f0218376ec` |

- `PRAGMA foreign_key_check`: **0 errors**. `PRAGMA integrity_check`: **ok**. Duplicate active ISIN check: **0**.
- Deliberate validation failure raised as requested and rollback restored the complete pre-failure table snapshot.
- Backup restore into a new path exactly matched the complete pre-migration table snapshot. Existing restore targets and backup paths are refused rather than overwritten.
- Repeated apply changed **0 tables** and **0 row counts**.

## Validation results

- Python syntax compilation for the changed backend modules: **passed**.
- Focused instrument/Dhan regression set, against an isolated copy migrated first: **71 passed**.
- Frontend production build (`npm run build`): **passed**, TypeScript check succeeded and Vite transformed 108 modules.
- Full backend regression suite on an isolated, migrated DB clone: **571 passed, 18 failed, 4 skipped** in **1,492.75 seconds**. The failures were confined to Phase 14.2–14.8 tests involving observed-bar counts/provenance, synthetic-vs-observed RVOL, and historical calendar/session expectations. The complete failure list is:
  - `tests/test_phase14_2_intraday_tod_rvol.py::test_seed_symbol_intraday_history_and_index`
  - `tests/test_phase14_3_observed_market_data.py::test_database_actual_bar_provenance_audit`
  - `tests/test_phase14_3_observed_market_data.py::test_true_tod_rvol_strictly_unavailable_in_production_mode`
  - `tests/test_phase14_3_observed_market_data.py::test_synthetic_demo_mode_explicit`
  - `tests/test_phase14_3_observed_market_data.py::test_api_market_movers_production_mode_isolates_synthetic`
  - `tests/test_phase14_3_observed_market_data.py::test_api_intraday_status_provenance_audit`
  - `tests/test_phase14_4_calendar_provenance_readiness.py::test_database_strict_audit_isolates_db_synthetic`
  - `tests/test_phase14_4_calendar_provenance_readiness.py::test_system_wide_demo_isolation_across_endpoints`
  - `tests/test_phase14_6_cas_aware_validation.py::test_get_expected_session_schedule_cas_regular`
  - `tests/test_phase14_6_cas_aware_validation.py::test_pilot_database_records_inspection`
  - `tests/test_phase14_6_cas_aware_validation.py::test_tod_rvol_unobserved_stock_returns_unavailable`
  - `tests/test_phase14_7_independent_validation.py::test_official_cas_session_timing`
  - `tests/test_phase14_7_independent_validation.py::test_auction_timestamp_interpretation`
  - `tests/test_phase14_7_independent_validation.py::test_synthetic_records_excluded_without_allow_synthetic`
  - `tests/test_phase14_7_independent_validation.py::test_observed_provenance_preservation`
  - `tests/test_phase14_7_independent_validation.py::test_downstream_scanner_and_ranking_integrity`
  - `tests/test_phase14_8_expansion_validation.py::test_tod_rvol_independent_spot_checks`
  - `tests/test_phase14_8_expansion_validation.py::test_current_session_excluded_from_baseline`
- Active application DB protection: its SHA-256 was `8CE729E355B96D3596FDF8FF4831A31408719140A6F4C728835F8749A0F17B25` both before and after the full isolated-clone regression run.
- Final regression follow-up on an isolated copy of the active DB, without running a migration: **550 passed, 10 failed, 4 skipped, 29 errors** (593 collected) in **3,754.79 seconds**. All 18 Phase 14.2–14.8 tests listed above passed in this run and in a focused reproduction, so their prior failures were not reproducible under the current no-migration test setup; no source or expectation changes were made for them. The 29 setup errors and five of the ten failures stop at the deliberate `INST_NSE_TATAMOTORS_HIST` fail-closed guard because this test DB still contains the legacy row and migrations were prohibited. The other five failures are in two-user isolation tests: their module-level JWTs expire after one hour, while this suite took over an hour to reach them. These are unresolved test-fixture/environment issues; this run is not a clean full-suite result. The active application DB SHA-256 remained `8CE729E355B96D3596FDF8FF4831A31408719140A6F4C728835F8749A0F17B25` before and after this run.

## Unresolved evidence and release gate

- The [Tata Motors official website](https://www.tatamotors.com/) states that the Composite Scheme of Arrangement was effective **October 1, 2025**. This verifies the scheme's legal effective date only; it does not establish the exchange ex-date, listing/trading cutover, or historical alias validity. The recorded October 24, 2025 ex-date and tax-allocation effective date remain explicitly `UNVERIFIED`; dated Tata resolution therefore returns no identity instead of guessing.
- Exchange/provider evidence for historical and current quote, daily-history, intraday-history, and live-feed support is not sufficient to mark those capabilities verified. Capability flags remain disabled.
- Dhan security IDs and exchange-segment mappings have not been independently verified against an authoritative current Dhan instrument master. No Dhan API was activated and no credentials were added.
- No production migration has been run. Approval is still required after the primary-source identity evidence and regression results are reviewed.

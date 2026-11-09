"""
Phase 14.8 Universe Expansion Ingestion Script.
Ingests and validates genuine observed 5m historical data across the complete 31-stock NSE tracked universe.
Uses effective-dated CAS session schedules, 2-second polite rate-limiting, and atomic persistence.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.intraday_data_service import (
    TRACKED_NSE_SYMBOLS,
    ingest_symbol_intraday_history,
)
from app.services.money_flow_service import calculate_historical_time_of_day_rvol
from app.services.trading_calendar_service import (
    get_expected_session_schedule,
    is_cas_eligible_security,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phase14_8_expansion")

ALL_31_SYMBOLS = sorted(TRACKED_NSE_SYMBOLS)


def run_expansion_ingestion():
    print("=" * 80)
    print("PHASE 14.8 — 31-STOCK CONTROLLED HISTORICAL INTRADAY EXPANSION")
    print(f"Target Universe: {len(ALL_31_SYMBOLS)} NSE F&O Equities")
    print("Sequential Ingestion with 2-second polite rate limiting...")
    print("=" * 80)

    db_path = backend_dir / "data" / "stock_intelligence.db"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    # Pre-ingestion counts
    pre_obs = c.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]
    pre_prov = c.execute("SELECT count(*) FROM bar_provenance").fetchone()[0]
    pre_syn = c.execute("SELECT count(*) FROM ohlcv WHERE interval = '5m'").fetchone()[0]

    print(f"\nPre-Ingestion DB Inventory: Observed={pre_obs}, Provenance={pre_prov}, Synthetic={pre_syn}")

    symbol_results: Dict[str, Any] = {}
    validation_summaries: List[Dict[str, Any]] = []

    for idx, sym in enumerate(ALL_31_SYMBOLS, 1):
        print(f"\n[{idx:02d}/{len(ALL_31_SYMBOLS):02d}] Processing {sym}...")
        
        # Check if symbol already has observed data in DB
        existing_bars = c.execute(
            "SELECT count(*) FROM observed_intraday_ohlcv WHERE symbol = ?", (sym,)
        ).fetchone()[0]

        start_time = time.time()
        try:
            res = ingest_symbol_intraday_history(symbol=sym, provider="yfinance", num_sessions=6)
        except Exception as e:
            logger.error("Ingestion failed for %s: %s", sym, e)
            res = {
                "status": "EXCEPTION",
                "symbol": sym,
                "provider": "yfinance",
                "error_message": str(e),
                "valid_bars_ingested": 0,
                "completed_sessions": 0,
                "incomplete_sessions": 0,
                "session_quality": [],
            }

        elapsed = time.time() - start_time
        symbol_results[sym] = res

        # Verify DB counts for this symbol
        current_obs = c.execute(
            "SELECT count(*) FROM observed_intraday_ohlcv WHERE symbol = ?", (sym,)
        ).fetchone()[0]
        current_prov = c.execute(
            "SELECT count(*) FROM bar_provenance WHERE symbol = ?", (sym,)
        ).fetchone()[0]

        # Extract session dates and quality
        sq_list = res.get("session_quality", [])
        complete_count = len([sq for sq in sq_list if sq.get("is_complete")])
        incomplete_count = len([sq for sq in sq_list if not sq.get("is_complete")])
        total_fetched = res.get("total_bars_fetched", 0) or 0
        newly_ingested = res.get("valid_bars_ingested", 0) or 0

        # CAS and schedule version
        sample_date = sq_list[0].get("session_date") if sq_list else "2026-10-22"
        is_cas, cas_reason = is_cas_eligible_security(sym, sample_date)
        sample_sched = get_expected_session_schedule(sym, sample_date)
        sched_ver = sample_sched.get("schedule_version", "UNKNOWN")

        # Missing & duplicate intervals across all sessions
        missing_total = sum(len(sq.get("missing_intervals", [])) for sq in sq_list)
        dup_total = sum(len(sq.get("duplicate_intervals", [])) for sq in sq_list)

        summary_entry = {
            "symbol": sym,
            "provider_symbol": f"{sym}.NS",
            "provider": "yfinance",
            "status": res.get("status"),
            "total_bars_fetched": total_fetched,
            "observed_bars_in_db": current_obs,
            "provenance_records_in_db": current_prov,
            "newly_ingested_bars": newly_ingested,
            "completed_sessions": complete_count,
            "incomplete_sessions": incomplete_count,
            "total_sessions_evaluated": len(sq_list),
            "missing_intervals_count": missing_total,
            "duplicate_intervals_count": dup_total,
            "is_cas_eligible": is_cas,
            "schedule_version": sched_ver,
            "auction_bars_treated": "EXCLUDED_FROM_CONTINUOUS",
            "data_quality_status": "VERIFIED_OBSERVED_INTRADAY" if complete_count >= 3 else "INSUFFICIENT_OBSERVED_SESSIONS",
            "error_message": res.get("error_message") or res.get("reason"),
            "elapsed_seconds": round(elapsed, 2),
        }
        validation_summaries.append(summary_entry)

        print(f"    Status: {summary_entry['status']} | Fetched: {total_fetched} | Valid Ingested: {newly_ingested} | In DB: {current_obs}")
        print(f"    Completed Sessions: {complete_count} | Incomplete: {incomplete_count} | Schedule: {sched_ver}")

        # Conservative rate limiting: 2 seconds between provider calls
        if idx < len(ALL_31_SYMBOLS):
            time.sleep(2.0)

    # Post-ingestion DB inventory
    post_obs = c.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]
    post_prov = c.execute("SELECT count(*) FROM bar_provenance").fetchone()[0]
    post_syn = c.execute("SELECT count(*) FROM ohlcv WHERE interval = '5m'").fetchone()[0]

    print("\n" + "=" * 80)
    print("EXPANSION INGESTION COMPLETE — DATABASE INVENTORY")
    print(f"  Observed 5m Bars:   {post_obs} (Initial: {pre_obs}, Added: {post_obs - pre_obs})")
    print(f"  Provenance Records: {post_prov} (Initial: {pre_prov}, Added: {post_prov - pre_prov})")
    print(f"  Synthetic 5m Bars:  {post_syn} (Preserved exactly: {post_syn == pre_syn})")
    print("=" * 80)

    # Calculate TOD RVOL for all 31 symbols at 12:00:00 IST
    print("\n" + "=" * 80)
    print("OBSERVED TIME-OF-DAY RVOL AUDIT ACROSS ALL 31 SECURITIES (12:00:00 IST):")
    print("=" * 80)
    tod_rvol_results: Dict[str, Any] = {}
    for sym in ALL_31_SYMBOLS:
        tod = calculate_historical_time_of_day_rvol(
            symbol=sym,
            today_cumulative_volume=0.0,  # Auto-derive from today's observed bars
            current_time_str="12:00:00",
            min_required_sessions=3,
            allow_synthetic=False,
        )
        tod_rvol_results[sym] = tod
        rvol_val = tod.get("rvol")
        status_val = tod.get("tod_rvol_status")
        valid_sess = tod.get("tod_valid_sessions", 0)
        num = tod.get("numerator")
        den = tod.get("denominator")
        sched_v = tod.get("schedule_version")
        lbl = tod.get("label")
        print(f"  {sym:12s} | RVOL: {str(rvol_val):5s} | Status: {status_val:20s} | Sessions: {valid_sess:2d} | Num: {num} | Den: {den} | Ver: {sched_v}")

    # Save complete JSON report
    output_path = backend_dir / "data" / "phase14_8_expansion_results.json"
    full_report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_symbols": len(ALL_31_SYMBOLS),
        "db_inventory": {
            "pre_observed_bars": pre_obs,
            "post_observed_bars": post_obs,
            "pre_provenance_records": pre_prov,
            "post_provenance_records": post_prov,
            "synthetic_bars_preserved": post_syn,
        },
        "summaries": validation_summaries,
        "tod_rvol_results": tod_rvol_results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)
    print(f"\nFull report written to: {output_path}")

    conn.close()
    return full_report


if __name__ == "__main__":
    run_expansion_ingestion()

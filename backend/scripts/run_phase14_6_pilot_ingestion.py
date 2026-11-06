"""
Phase 14.6 Pilot Ingestion Runner for RELIANCE, TCS, and HDFCBANK.
Executes genuine Yahoo Finance intraday retrieval and CAS-aware validation.
Persists observed bars and provenance records into SQLite database.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parents[1]
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.services.intraday_data_service import ingest_symbol_intraday_history
from app.services.money_flow_service import calculate_historical_time_of_day_rvol

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phase14_6_pilot")

PILOT_SYMBOLS = ["RELIANCE", "TCS", "HDFCBANK"]


def main():
    print("=" * 70)
    print("PHASE 14.6 — OBSERVED INTRADAY DATA PILOT INGESTION")
    print("=" * 70)

    pilot_results = {}
    for sym in PILOT_SYMBOLS:
        print(f"\n>>> Ingesting 5m historical intraday bars for: {sym}")
        # Request 6 sessions to match Phase 14.5 pilot
        res = ingest_symbol_intraday_history(symbol=sym, provider="yfinance", num_sessions=6)
        pilot_results[sym] = res
        print(f"Status: {res.get('status')}")
        print(f"Total bars fetched: {res.get('total_bars_fetched')}")
        print(f"Valid bars ingested: {res.get('valid_bars_ingested')}")
        print(f"Completed sessions: {res.get('completed_sessions')}")
        print(f"Incomplete sessions: {res.get('incomplete_sessions')}")
        print("Session Quality:")
        for sq in res.get("session_quality", []):
            d = sq.get("session_date")
            comp = sq.get("is_complete")
            st = sq.get("status")
            act = sq.get("actual_bars")
            cont = sq.get("actual_continuous_bars")
            exp = sq.get("expected_continuous_bars")
            auc = sq.get("auction_bars_count")
            print(f"  - {d}: complete={comp} | status={st} | actual_total={act} | continuous={cont}/{exp} | auction_bars={auc}")

    # Inspect Database Counts
    db_path = backend_dir / "data" / "stock_intelligence.db"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    obs_total = c.execute("SELECT count(*) FROM observed_intraday_ohlcv").fetchone()[0]
    prov_total = c.execute("SELECT count(*) FROM bar_provenance").fetchone()[0]
    synth_total = c.execute("SELECT count(*) FROM ohlcv WHERE interval = '5m'").fetchone()[0]

    print("\n" + "=" * 70)
    print("POST-PILOT DATABASE INVENTORY:")
    print(f"  Observed 5m bars in observed_intraday_ohlcv: {obs_total}")
    print(f"  Provenance records in bar_provenance:       {prov_total}")
    print(f"  Synthetic 5m bars in ohlcv (preserved):     {synth_total}")
    print("=" * 70)

    for sym in PILOT_SYMBOLS:
        obs_sym = c.execute("SELECT count(*) FROM observed_intraday_ohlcv WHERE symbol = ?", (sym,)).fetchone()[0]
        prov_sym = c.execute("SELECT count(*) FROM bar_provenance WHERE symbol = ?", (sym,)).fetchone()[0]
        synth_sym = c.execute("SELECT count(*) FROM ohlcv WHERE symbol = ? AND interval = '5m'", (sym,)).fetchone()[0]
        print(f"  {sym:10s} -> Observed: {obs_sym:5d} | Provenance: {prov_sym:5d} | Synthetic: {synth_sym:5d}")

    # Test TOD RVOL calculation for each pilot symbol
    print("\n" + "=" * 70)
    print("TIME-OF-DAY RVOL VERIFICATION (STRICT OBSERVED BASELINE):")
    print("=" * 70)
    for sym in PILOT_SYMBOLS:
        tod_res = calculate_historical_time_of_day_rvol(
            symbol=sym,
            today_cumulative_volume=500000.0,
            current_time_str="12:00:00",
            min_required_sessions=3,
            allow_synthetic=False,
        )
        print(f"\nSymbol: {sym} at 12:00:00 IST")
        print(f"  TOD RVOL:              {tod_res.get('rvol')}")
        print(f"  Status:                {tod_res.get('tod_rvol_status')}")
        print(f"  Source:                {tod_res.get('tod_source')}")
        print(f"  Data Quality:          {tod_res.get('tod_data_quality')}")
        print(f"  Valid Sessions:        {tod_res.get('tod_valid_sessions')}")
        print(f"  Hist Avg Volume:       {tod_res.get('historical_avg_volume')}")
        print(f"  Label:                 {tod_res.get('label')}")

    conn.close()


if __name__ == "__main__":
    main()

"""
Audit the stored OHLCV bars in backend/data/stock_intelligence.db.
Provides an exhaustive breakdown of:
- Total bars by interval and source
- Distinct symbols
- Date ranges
- Provider provenance and whether bars are actual observed or synthetic
- Session counts and missing intervals
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

DB_PATH = Path(__file__).resolve().parents[1] / "data" / "stock_intelligence.db"

def run_audit():
    print(f"Auditing database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 1. Table summary
    c.execute("SELECT COUNT(*) FROM ohlcv")
    total_bars = c.fetchone()[0]
    print(f"Total OHLCV rows: {total_bars}")

    # 2. Breakdown by interval and source
    c.execute("SELECT interval, source, COUNT(*) FROM ohlcv GROUP BY interval, source")
    print("\n--- Breakdown by interval and source ---")
    interval_sources = c.fetchall()
    for row in interval_sources:
        print(f"Interval: {row[0]:<10} | Source: {row[1]:<35} | Count: {row[2]:>6}")

    # 3. 5-minute bars audit per symbol
    c.execute("""
        SELECT symbol, source, COUNT(*), MIN(timestamp), MAX(timestamp)
        FROM ohlcv
        WHERE interval = '5m'
        GROUP BY symbol, source
        ORDER BY symbol
    """)
    sym_rows = c.fetchall()
    print(f"\n--- 5-Minute Bars per Symbol ({len(sym_rows)} symbols) ---")
    for r in sym_rows:
        print(f"Symbol: {r[0]:<12} | Source: {r[1]:<32} | Bars: {r[2]:>5} | Min TS: {r[3]} | Max TS: {r[4]}")

    # 4. Check daily bars
    c.execute("""
        SELECT symbol, source, COUNT(*), MIN(timestamp), MAX(timestamp)
        FROM ohlcv
        WHERE interval = 'daily'
        GROUP BY symbol, source
        ORDER BY symbol
    """)
    daily_rows = c.fetchall()
    print(f"\n--- Daily Bars per Symbol ({len(daily_rows)} symbols) ---")
    for r in daily_rows:
        print(f"Symbol: {r[0]:<12} | Source: {r[1]:<15} | Bars: {r[2]:>5} | Min TS: {r[3]} | Max TS: {r[4]}")

    # 5. Check session completeness for 5m bars
    # Each NSE regular session is 75 bars.
    c.execute("""
        SELECT symbol, timestamp, volume, source
        FROM ohlcv
        WHERE interval = '5m'
    """)
    all_5m = c.fetchall()
    symbol_sessions = {}
    for sym, ts, vol, src in all_5m:
        # Convert to IST date
        if ts.endswith("Z"):
            dt_utc = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            dt_ist = dt_utc + timedelta(hours=5, minutes=30)
            date_str = dt_ist.strftime("%Y-%m-%d")
        else:
            date_str = ts.split("T")[0].split(" ")[0]
        symbol_sessions.setdefault(sym, {}).setdefault(date_str, []).append((ts, vol, src))

    print(f"\n--- 5-Minute Session Completeness Analysis ---")
    synthetic_count = 0
    observed_count = 0
    for sym, sessions in sorted(symbol_sessions.items()):
        session_bar_counts = [len(bars) for bars in sessions.values()]
        sources = set(src for bars in sessions.values() for _, _, src in bars)
        is_synthetic = any("synthetic" in s.lower() or "deterministic" in s.lower() or "calibrated" in s.lower() for s in sources)
        if is_synthetic:
            synthetic_count += 1
        else:
            observed_count += 1
        print(f"Symbol: {sym:<12} | Sessions: {len(sessions):>2} | Bars/Session: min={min(session_bar_counts)}, max={max(session_bar_counts)} | Sources: {sources} | Classification: {'SYNTHETIC' if is_synthetic else 'OBSERVED'}")

    print(f"\nSummary: {len(symbol_sessions)} symbols with 5m data. Observed: {observed_count}, Synthetic: {synthetic_count}")
    conn.close()

if __name__ == "__main__":
    run_audit()

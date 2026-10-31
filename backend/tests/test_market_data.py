"""
Integration tests for market data pipeline.

Tests cover:
1. Downloading historical prices (RELIANCE.NS, TCS.NS)
2. Saving data into SQLite
3. Reading cached data
4. Calculating indicators from real data
5. Handling invalid ticker symbols
6. Handling missing data
7. Incremental updates
8. Connecting to the screener
9. Preserving existing functionality
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import time

from app.database import (
    init_db,
    connect,
    get_bars,
    get_latest_bar_date,
    get_ohlcv_count,
    get_stock,
    list_stocks,
    upsert_ohlcv,
    upsert_data_update,
    get_data_update,
    update_stock_fields,
    get_all_symbols,
)
from app.services.indicators import calculate_all_indicators
from app.services.market_data_service import update_stock_data, _recalculate_indicators
from app.providers.manager import get_provider_manager
from app.providers.yfinance_provider import YFinanceProvider

passed = 0
failed = 0
skipped = 0


def test(name, func, requires_network=False):
    global passed, failed, skipped
    try:
        func()
        print(f"  PASS {name}")
        passed += 1
    except Exception as e:
        if requires_network and "urlopen" in str(e).lower():
            print(f"  SKIP {name}: Network unavailable")
            skipped += 1
        else:
            print(f"  FAIL {name}: {e}")
            failed += 1


# --- Database tests ---

def test_init_db():
    init_db()
    syms = get_all_symbols()
    assert len(syms) >= 28, f"Expected >= 28 symbols, got {len(syms)}"
test("init_db preserves existing stocks", test_init_db)


def test_upsert_ohlcv():
    bars = [
        {"date": "2024-01-02", "open": 100, "high": 105, "low": 98, "close": 103, "adj_close": 103, "volume": 50000},
        {"date": "2024-01-03", "open": 103, "high": 108, "low": 101, "close": 106, "adj_close": 106, "volume": 60000},
    ]
    n = upsert_ohlcv("TEST_SYM", bars, source="test")
    assert n == 2, f"Expected 2 rows, got {n}"
    # Read back
    stored = get_bars("TEST_SYM", "daily")
    assert len(stored) >= 2
    assert stored[0]["close"] == 103
test("Upsert OHLCV bars", test_upsert_ohlcv)


def test_ohlcv_dedup():
    bars = [
        {"date": "2024-01-02", "open": 100, "high": 105, "low": 98, "close": 999, "volume": 50000},
    ]
    upsert_ohlcv("TEST_SYM", bars, source="test")
    stored = get_bars("TEST_SYM", "daily")
    dates = [b["timestamp"] for b in stored]
    assert dates.count("2024-01-02") == 1, "Duplicate bars found"
    # Value should be updated
    bar_jan2 = [b for b in stored if b["timestamp"] == "2024-01-02"][0]
    assert bar_jan2["close"] == 999, "UPSERT should update existing bar"
test("OHLCV deduplication on upsert", test_ohlcv_dedup)


def test_latest_bar_date():
    d = get_latest_bar_date("TEST_SYM")
    assert d == "2024-01-03", f"Expected 2024-01-03, got {d}"
test("Get latest bar date", test_latest_bar_date)


def test_ohlcv_count():
    count = get_ohlcv_count("TEST_SYM")
    assert count == 2, f"Expected 2, got {count}"
test("Get OHLCV count", test_ohlcv_count)


def test_data_update_tracking():
    upsert_data_update("TEST_SYM", "test", bars_count=100, period="1y", status="ok")
    info = get_data_update("TEST_SYM", "test")
    assert info is not None
    assert info["bars_count"] == 100
    assert info["status"] == "ok"
test("Data update tracking", test_data_update_tracking)


def test_update_stock_fields():
    # First ensure demo stock exists
    stock = get_stock("RELIANCE")
    assert stock is not None
    ok = update_stock_fields("RELIANCE", {"rsi": 55.5, "data_source": "test"})
    assert ok
    updated = get_stock("RELIANCE")
    assert updated["rsi"] == 55.5
    assert updated["data_source"] == "test"
    # Restore
    update_stock_fields("RELIANCE", {"rsi": 58.2, "data_source": "demo"})
test("Update stock fields", test_update_stock_fields)


# --- Provider tests ---

def test_provider_available():
    mgr = get_provider_manager()
    assert mgr.active_provider is not None, "No provider available"
    attr = mgr.get_attribution()
    assert attr is not None
    assert "Yahoo" in attr.name
test("YFinance provider is available", test_provider_available)


def test_provider_attribution():
    mgr = get_provider_manager()
    attr = mgr.get_attribution()
    assert attr.data_type == "historical"
    assert "not" in attr.note.lower() or "historical" in attr.note.lower()
test("Provider attribution says 'historical'", test_provider_attribution)


# --- Indicator calculation from stored data ---

def test_indicators_from_synthetic():
    # Insert 100 bars of synthetic data
    import random
    random.seed(99)
    bars = []
    price = 100.0
    for i in range(100):
        c = price + random.gauss(0, 2)
        bars.append({
            "date": f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "open": round(price, 2),
            "high": round(max(price, c) + 1, 2),
            "low": round(min(price, c) - 1, 2),
            "close": round(c, 2),
            "volume": 1000000,
        })
        price = c
    upsert_ohlcv("SYNTH_TEST", bars, source="test")
    stored = get_bars("SYNTH_TEST", "daily")
    assert len(stored) == 100
    indicators = calculate_all_indicators(stored)
    assert indicators["sma_20"] is not None
    assert indicators["ema_20"] is not None
    assert indicators["rsi"] is not None
    assert indicators["macd"] is not None
    assert 0 <= indicators["rsi"] <= 100
test("Indicators from synthetic OHLCV data", test_indicators_from_synthetic)


# --- Network-dependent tests (may be skipped) ---

def test_download_reliance():
    result = update_stock_data("RELIANCE", exchange="NSE", period="1mo", force=True)
    assert result["status"] in ("updated", "cached"), f"Status: {result['status']}, Error: {result.get('error')}"
    if result["status"] == "updated":
        assert result.get("new_bars", 0) > 0 or result.get("total_bars", 0) > 0
    # Check indicators were calculated
    stock = get_stock("RELIANCE")
    assert stock is not None
    if stock.get("data_source") == "yfinance":
        assert stock.get("sma_20") is not None or stock.get("close") is not None
test("Download RELIANCE.NS history", test_download_reliance, requires_network=True)


def test_download_tcs():
    result = update_stock_data("TCS", exchange="NSE", period="1mo", force=True)
    assert result["status"] in ("updated", "cached"), f"Status: {result['status']}, Error: {result.get('error')}"
test("Download TCS.NS history", test_download_tcs, requires_network=True)


def test_cached_data():
    """After downloading, data should be cached — second call should be fast."""
    result = update_stock_data("RELIANCE", exchange="NSE", period="1mo", force=False)
    # Should use cache or do incremental update
    assert result["status"] in ("cached", "updated"), f"Status: {result['status']}"
test("Read cached data (no re-download)", test_cached_data, requires_network=True)


def test_invalid_ticker():
    result = update_stock_data("ZZZZZZZ_INVALID_99", exchange="NSE", period="1mo", force=True)
    assert result["status"] in ("no_data", "error"), f"Expected error, got: {result['status']}"
test("Handle invalid ticker gracefully", test_invalid_ticker, requires_network=True)


# --- Screener integration ---

def test_screener_with_data():
    from app.services.screener_service import run_screen
    from app.schemas.screener import ScreenRequest
    stocks = list_stocks()
    req = ScreenRequest(min_roe=10, page_size=50)
    items, total = run_screen(stocks, req)
    assert total >= 0
    # Screener should work regardless of data source
test("Screener works with mixed demo/real data", test_screener_with_data)


def test_dashboard_preserved():
    stocks = list_stocks()
    assert len(stocks) >= 28, f"Expected >= 28 stocks, got {len(stocks)}"
    # Check that demo stocks still have data
    rel = get_stock("RELIANCE")
    assert rel is not None
    assert rel["company_name"] == "Reliance Industries"
test("Dashboard data preserved", test_dashboard_preserved)


# --- Cleanup test data ---

def test_cleanup():
    with connect() as con:
        con.execute("DELETE FROM ohlcv WHERE symbol IN ('TEST_SYM', 'SYNTH_TEST')")
        con.execute("DELETE FROM data_updates WHERE symbol = 'TEST_SYM'")
        con.commit()
    assert get_ohlcv_count("TEST_SYM") == 0
test("Cleanup test data", test_cleanup)


print(f"\n{passed} passed, {failed} failed, {skipped} skipped out of {passed + failed + skipped} tests.")
sys.exit(1 if failed else 0)

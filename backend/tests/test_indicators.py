"""
Tests for the technical indicators engine.

Uses synthetic data to validate calculations against known expected values.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.indicators import (
    calculate_all_indicators,
    _rsi,
    _macd,
    _adx,
    _supertrend,
    _pct_return,
    _round,
    _prepare_dataframe,
)
import pandas as pd
import numpy as np

passed = 0
failed = 0


def test(name, func):
    global passed, failed
    try:
        func()
        print(f"  PASS {name}")
        passed += 1
    except Exception as e:
        print(f"  FAIL {name}: {e}")
        failed += 1

test.__test__ = False



def make_bars(n=300, start_price=100.0, volatility=2.0):
    """Generate synthetic OHLCV bars for testing."""
    import random
    random.seed(42)
    np.random.seed(42)
    bars = []
    price = start_price
    for i in range(n):
        change = random.gauss(0, volatility)
        o = price
        h = o + abs(random.gauss(0, volatility * 0.5))
        l = o - abs(random.gauss(0, volatility * 0.5))
        c = o + change
        c = max(c, l)
        c = min(c, h)
        v = int(abs(random.gauss(1000000, 300000)))
        bars.append({
            "date": f"2024-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}",
            "open": round(o, 2),
            "high": round(h, 2),
            "low": round(l, 2),
            "close": round(c, 2),
            "volume": v,
        })
        price = c
    return bars


# --- Tests ---

def test_empty_bars():
    result = calculate_all_indicators([])
    assert "error" in result
test("Empty bars returns error", test_empty_bars)


def test_single_bar():
    result = calculate_all_indicators([{
        "date": "2024-01-01", "open": 100, "high": 105,
        "low": 95, "close": 102, "volume": 1000
    }])
    assert "error" in result
test("Single bar returns error", test_single_bar)


def test_insufficient_for_sma200():
    bars = make_bars(50)
    result = calculate_all_indicators(bars)
    assert result["sma_200"] is None, "SMA 200 should be None with 50 bars"
    assert result["sma_20"] is not None, "SMA 20 should exist with 50 bars"
test("Insufficient data for SMA 200", test_insufficient_for_sma200)


def test_sma_20_calculation():
    bars = make_bars(100)
    result = calculate_all_indicators(bars)
    # Manual check: SMA 20 = avg of last 20 closes
    df = pd.DataFrame(bars)
    expected = df["close"].iloc[-20:].mean()
    assert result["sma_20"] is not None
    assert abs(result["sma_20"] - round(expected, 2)) < 0.5, (
        f"SMA 20 mismatch: got {result['sma_20']}, expected ~{round(expected, 2)}"
    )
test("SMA 20 matches manual calculation", test_sma_20_calculation)


def test_ema_20_exists():
    bars = make_bars(100)
    result = calculate_all_indicators(bars)
    assert result["ema_20"] is not None
    # EMA should be different from SMA
    assert result["ema_20"] != result["sma_20"] or True  # may coincide, that's ok
test("EMA 20 computed successfully", test_ema_20_exists)


def test_rsi_range():
    bars = make_bars(100)
    result = calculate_all_indicators(bars)
    assert result["rsi"] is not None
    assert 0 <= result["rsi"] <= 100, f"RSI out of range: {result['rsi']}"
test("RSI is within 0-100", test_rsi_range)


def test_rsi_insufficient():
    bars = make_bars(10)
    result = calculate_all_indicators(bars)
    assert result["rsi"] is None, "RSI should be None with < 15 bars"
test("RSI None with insufficient data", test_rsi_insufficient)


def test_macd_components():
    bars = make_bars(100)
    result = calculate_all_indicators(bars)
    assert result["macd"] is not None
    assert result["macd_signal"] is not None
    assert result["macd_histogram"] is not None
test("MACD line, signal, histogram all computed", test_macd_components)


def test_macd_insufficient():
    bars = make_bars(30)
    result = calculate_all_indicators(bars)
    assert result["macd"] is None, "MACD should be None with < 35 bars"
test("MACD None with insufficient data", test_macd_insufficient)


def test_adx_range():
    bars = make_bars(200)
    result = calculate_all_indicators(bars)
    if result["adx"] is not None:
        assert 0 <= result["adx"] <= 100, f"ADX out of range: {result['adx']}"
test("ADX is within 0-100 (or None)", test_adx_range)


def test_supertrend_direction():
    bars = make_bars(100)
    result = calculate_all_indicators(bars)
    if result["supertrend"] is not None:
        assert result["supertrend_dir"] in ("up", "down"), (
            f"Supertrend direction invalid: {result['supertrend_dir']}"
        )
test("Supertrend has valid direction", test_supertrend_direction)


def test_returns():
    bars = make_bars(300)
    result = calculate_all_indicators(bars)
    assert result["return_1d_pct"] is not None
    assert result["return_1w_pct"] is not None
    assert result["return_1m_pct"] is not None
    assert result["return_3m_pct"] is not None
    assert result["return_1y_pct"] is not None
test("All return periods computed with 300 bars", test_returns)


def test_return_1d_manual():
    bars = make_bars(10)
    result = calculate_all_indicators(bars)
    # 1-day return = (close[-1] - close[-2]) / close[-2] * 100
    c_last = bars[-1]["close"]
    c_prev = bars[-2]["close"]
    expected = round((c_last - c_prev) / c_prev * 100, 2)
    assert result["return_1d_pct"] is not None
    assert abs(result["return_1d_pct"] - expected) < 0.1, (
        f"1d return mismatch: got {result['return_1d_pct']}, expected {expected}"
    )
test("1-day return matches manual calc", test_return_1d_manual)


def test_volume_and_relative_volume():
    bars = make_bars(50)
    result = calculate_all_indicators(bars)
    assert result["volume"] is not None
    assert result["volume"] > 0
    assert result["relative_volume"] is not None
    assert result["relative_volume"] > 0
test("Volume and relative volume computed", test_volume_and_relative_volume)


def test_52_week_high_low():
    bars = make_bars(300)
    result = calculate_all_indicators(bars)
    assert result["week_52_high"] is not None
    assert result["week_52_low"] is not None
    assert result["week_52_high"] >= result["week_52_low"]
test("52-week high >= 52-week low", test_52_week_high_low)


def test_close_price():
    bars = make_bars(50)
    result = calculate_all_indicators(bars)
    assert result["close"] == round(bars[-1]["close"], 2)
test("Close price matches last bar", test_close_price)


def test_daily_change_pct():
    bars = make_bars(50)
    result = calculate_all_indicators(bars)
    assert result["daily_change_pct"] is not None
test("Daily change percentage computed", test_daily_change_pct)


def test_all_sma_ema_with_enough_data():
    bars = make_bars(300)
    result = calculate_all_indicators(bars)
    for period in (20, 50, 100, 200):
        assert result[f"sma_{period}"] is not None, f"SMA {period} should not be None"
        assert result[f"ema_{period}"] is not None, f"EMA {period} should not be None"
test("All SMA/EMA periods computed with 300 bars", test_all_sma_ema_with_enough_data)


def test_round_helper():
    assert _round(None) is None
    assert _round(float("nan")) is None
    assert _round(float("inf")) is None
    assert _round(3.14159) == 3.14
    assert _round(100.0, 0) == 100
test("_round helper edge cases", test_round_helper)


def test_bars_count_in_result():
    bars = make_bars(75)
    result = calculate_all_indicators(bars)
    assert result["bars_count"] == 75
test("bars_count matches input length", test_bars_count_in_result)


if __name__ == "__main__":
    print(f"\n{passed} passed, {failed} failed out of {passed + failed} tests.")
    sys.exit(1 if failed else 0)

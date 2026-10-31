"""
Tests for the screening engine.

Verifies:
  1. Simple min/max filters correctly compare stock column vs threshold
  2. Missing (None) values cause filter failure, not false positives
  3. AND/OR condition groups work correctly
  4. Pagination and sorting
  5. Between operator
"""

import sys
from pathlib import Path

# Add backend to path so app modules can be imported
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.screener import (
    ConditionGroup,
    FilterCondition,
    LogicOp,
    Operator,
    ScreenRequest,
    SortOrder,
)
from app.services.screener_service import run_screen, _compare, _safe_float


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

STOCKS = [
    {
        "symbol": "STOCK_A",
        "company_name": "Alpha Corp",
        "exchange": "NSE",
        "sector": "IT",
        "market_cap_cr": 5000.0,
        "close": 500.0,
        "pe": 20.0,
        "roe": 25.0,
        "roce": 30.0,
        "debt_equity": 0.3,
        "rsi": 60.0,
        "relative_volume": 1.5,
        "return_1m_pct": 8.0,
        "return_3m_pct": 15.0,
        "revenue_growth_pct": 12.0,
        "profit_growth_pct": 18.0,
        "opm_pct": 22.0,
        "promoter_holding": 55.0,
        "promoter_pledging": 0.0,
        "fii_holding": 20.0,
        "dii_holding": 15.0,
    },
    {
        "symbol": "STOCK_B",
        "company_name": "Beta Ltd",
        "exchange": "BSE",
        "sector": "Banking",
        "market_cap_cr": 1000.0,
        "close": 150.0,
        "pe": 12.0,
        "roe": 10.0,
        "roce": None,   # Missing ROCE
        "debt_equity": 0.8,
        "rsi": 35.0,
        "relative_volume": 0.5,
        "return_1m_pct": -5.0,
        "return_3m_pct": -2.0,
        "revenue_growth_pct": 5.0,
        "profit_growth_pct": -3.0,
        "opm_pct": None,  # Missing OPM
        "promoter_holding": 40.0,
        "promoter_pledging": 5.0,
        "fii_holding": 12.0,
        "dii_holding": 8.0,
    },
    {
        "symbol": "STOCK_C",
        "company_name": "Gamma Industries",
        "exchange": "NSE",
        "sector": "Auto",
        "market_cap_cr": 3000.0,
        "close": 800.0,
        "pe": 15.0,
        "roe": 18.0,
        "roce": 22.0,
        "debt_equity": 0.5,
        "rsi": 72.0,
        "relative_volume": 2.0,
        "return_1m_pct": 12.0,
        "return_3m_pct": 25.0,
        "revenue_growth_pct": 20.0,
        "profit_growth_pct": 30.0,
        "opm_pct": 15.0,
        "promoter_holding": 62.0,
        "promoter_pledging": 1.0,
        "fii_holding": 18.0,
        "dii_holding": 10.0,
    },
]


# ---------------------------------------------------------------------------
# Unit tests: _compare helper
# ---------------------------------------------------------------------------

def test_compare_gte():
    assert _compare(10.0, "gte", 5.0) is True
    assert _compare(5.0, "gte", 5.0) is True
    assert _compare(4.9, "gte", 5.0) is False

def test_compare_lte():
    assert _compare(3.0, "lte", 5.0) is True
    assert _compare(5.0, "lte", 5.0) is True
    assert _compare(5.1, "lte", 5.0) is False

def test_compare_none_returns_false():
    """Missing values must fail any comparison."""
    assert _compare(None, "gte", 5.0) is False
    assert _compare(None, "lte", 5.0) is False
    assert _compare(None, ">", 5.0) is False

def test_compare_between():
    assert _compare(5.0, "between", 3.0, 7.0) is True
    assert _compare(3.0, "between", 3.0, 7.0) is True
    assert _compare(7.0, "between", 3.0, 7.0) is True
    assert _compare(2.0, "between", 3.0, 7.0) is False
    assert _compare(8.0, "between", 3.0, 7.0) is False

def test_safe_float():
    assert _safe_float(None) is None
    assert _safe_float(42) == 42.0
    assert _safe_float("3.14") == 3.14
    assert _safe_float(float("nan")) is None
    assert _safe_float(float("inf")) is None
    assert _safe_float("abc") is None


# ---------------------------------------------------------------------------
# Integration tests: simple filters
# ---------------------------------------------------------------------------

def test_no_filters_returns_all():
    req = ScreenRequest()
    items, total = run_screen(STOCKS, req)
    assert total == 3

def test_min_market_cap():
    req = ScreenRequest(min_market_cap_cr=2000)
    items, total = run_screen(STOCKS, req)
    assert total == 2
    symbols = {s["symbol"] for s in items}
    assert "STOCK_A" in symbols
    assert "STOCK_C" in symbols
    assert "STOCK_B" not in symbols

def test_max_pe():
    req = ScreenRequest(max_pe=15)
    items, total = run_screen(STOCKS, req)
    symbols = {s["symbol"] for s in items}
    assert "STOCK_B" in symbols
    assert "STOCK_C" in symbols
    assert "STOCK_A" not in symbols  # PE=20

def test_min_roe_filters_correctly():
    """ROE filter should use stock.roe, not compare against 'min_roe'."""
    req = ScreenRequest(min_roe=15)
    items, total = run_screen(STOCKS, req)
    symbols = {s["symbol"] for s in items}
    assert "STOCK_A" in symbols   # ROE=25
    assert "STOCK_C" in symbols   # ROE=18
    assert "STOCK_B" not in symbols  # ROE=10

def test_missing_value_fails_filter():
    """STOCK_B has roce=None, so min_roce filter should exclude it."""
    req = ScreenRequest(min_roce=10)
    items, total = run_screen(STOCKS, req)
    symbols = {s["symbol"] for s in items}
    assert "STOCK_B" not in symbols

def test_combined_filters():
    """Multiple filters should AND together."""
    req = ScreenRequest(
        min_market_cap_cr=2000,
        min_roe=15,
        max_debt_equity=0.5,
        min_rsi=55,
    )
    items, total = run_screen(STOCKS, req)
    # STOCK_A (cap=5000, roe=25, d/e=0.3, rsi=60) and
    # STOCK_C (cap=3000, roe=18, d/e=0.5, rsi=72) both pass
    assert total == 2
    symbols = {s["symbol"] for s in items}
    assert "STOCK_A" in symbols
    assert "STOCK_C" in symbols
    assert "STOCK_B" not in symbols


# ---------------------------------------------------------------------------
# Advanced condition groups
# ---------------------------------------------------------------------------

def test_and_group():
    req = ScreenRequest(
        condition_groups=[
            ConditionGroup(
                logic=LogicOp.AND,
                conditions=[
                    FilterCondition(field="roe", operator=Operator.GTE, value=15),
                    FilterCondition(field="debt_equity", operator=Operator.LTE, value=0.4),
                ],
            )
        ]
    )
    items, total = run_screen(STOCKS, req)
    assert total == 1
    assert items[0]["symbol"] == "STOCK_A"

def test_or_group():
    req = ScreenRequest(
        condition_groups=[
            ConditionGroup(
                logic=LogicOp.OR,
                conditions=[
                    FilterCondition(field="rsi", operator=Operator.GTE, value=70),
                    FilterCondition(field="rsi", operator=Operator.LTE, value=40),
                ],
            )
        ]
    )
    items, total = run_screen(STOCKS, req)
    symbols = {s["symbol"] for s in items}
    assert "STOCK_B" in symbols  # RSI=35
    assert "STOCK_C" in symbols  # RSI=72
    assert "STOCK_A" not in symbols  # RSI=60

def test_between_condition():
    req = ScreenRequest(
        condition_groups=[
            ConditionGroup(
                logic=LogicOp.AND,
                conditions=[
                    FilterCondition(
                        field="return_1m_pct",
                        operator=Operator.BETWEEN,
                        value=-10.0,
                        value2=10.0,
                    ),
                ],
            )
        ]
    )
    items, total = run_screen(STOCKS, req)
    symbols = {s["symbol"] for s in items}
    assert "STOCK_A" in symbols   # 8%
    assert "STOCK_B" in symbols   # -5%
    assert "STOCK_C" not in symbols  # 12%


# ---------------------------------------------------------------------------
# Pagination and sorting
# ---------------------------------------------------------------------------

def test_sorting_asc():
    req = ScreenRequest(sort_by="close", sort_order=SortOrder.ASC)
    items, total = run_screen(STOCKS, req)
    prices = [s["close"] for s in items]
    assert prices == sorted(prices)

def test_sorting_desc():
    req = ScreenRequest(sort_by="market_cap_cr", sort_order=SortOrder.DESC)
    items, total = run_screen(STOCKS, req)
    caps = [s["market_cap_cr"] for s in items]
    assert caps == sorted(caps, reverse=True)

def test_pagination():
    req = ScreenRequest(page=1, page_size=2)
    items, total = run_screen(STOCKS, req)
    assert total == 3
    assert len(items) == 2

    req2 = ScreenRequest(page=2, page_size=2)
    items2, total2 = run_screen(STOCKS, req2)
    assert total2 == 3
    assert len(items2) == 1


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  PASS {t.__name__}")
        except Exception:
            failed += 1
            print(f"  FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{passed} passed, {failed} failed out of {passed + failed} tests.")
    if failed:
        sys.exit(1)

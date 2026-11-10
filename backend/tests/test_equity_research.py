import pytest
from app.services.equity_research_service import (
    calculate_1y_performance,
    calculate_relative_strength,
    calculate_dvm_scores,
    generate_fundamental_checklist_and_swot,
    get_sector_peer_comparison,
)
from app.services.candle_service import get_multi_timeframe_bars
from app.routers.fundamentals import get_company_research


def test_1y_performance():
    perf = calculate_1y_performance("ETERNAL")
    assert perf["symbol"] == "ETERNAL"
    assert perf["return_pct"] is not None
    assert perf["week_52_high"] >= perf["week_52_low"]
    assert 0 <= perf["current_position_in_52w_range_pct"] <= 100
    assert len(perf["history"]) > 0


def test_relative_strength():
    rs = calculate_relative_strength("ETERNAL", "NIFTY 50")
    assert rs["symbol"] == "ETERNAL"
    assert 0 <= rs["rs_rating"] <= 100
    assert "relative_performance_3m" in rs
    assert "status" in rs


def test_dvm_scores():
    dvm = calculate_dvm_scores("ETERNAL")
    assert dvm["symbol"] == "ETERNAL"
    assert 0 <= dvm["overall_score"] <= 100
    assert dvm["classification"] in ("Excellent", "Strong", "Moderate", "Weak", "Poor")
    assert 0 <= dvm["durability_score"] <= 100
    assert 0 <= dvm["valuation_score"] <= 100
    assert 0 <= dvm["momentum_score"] <= 100


def test_checklist_and_swot():
    swot = generate_fundamental_checklist_and_swot("ETERNAL")
    assert swot["symbol"] == "ETERNAL"
    assert swot["total_count"] == 9
    assert swot["passed_count"] <= 9
    assert len(swot["checklist"]) == 9
    assert "strengths" in swot["swot"]
    assert "weaknesses" in swot["swot"]


def test_sector_peers():
    peers = get_sector_peer_comparison("ETERNAL")
    assert peers["target_symbol"] == "ETERNAL"
    assert len(peers["peers"]) >= 1


def test_multi_timeframe_bars():
    bars_1m = get_multi_timeframe_bars("ETERNAL", "1m")
    bars_5m = get_multi_timeframe_bars("ETERNAL", "5m")
    bars_15m = get_multi_timeframe_bars("ETERNAL", "15m")
    bars_1h = get_multi_timeframe_bars("ETERNAL", "1h")
    bars_1d = get_multi_timeframe_bars("ETERNAL", "1D")

    assert len(bars_1m) > 0
    assert len(bars_5m) > 0
    assert len(bars_15m) > 0
    assert len(bars_1h) > 0
    assert len(bars_1d) > 0


def test_company_research_dossier_integration():
    dossier = get_company_research("ETERNAL")
    assert dossier.symbol == "ETERNAL"
    assert dossier.current_price is not None
    assert dossier.performance_1y is not None
    assert dossier.relative_strength is not None
    assert dossier.dvm_scores is not None
    assert dossier.checklist_swot is not None
    assert dossier.sector_peers is not None
    assert len(dossier.quarterly_income_statements) >= 6

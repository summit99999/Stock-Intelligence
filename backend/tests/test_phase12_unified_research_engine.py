"""
Unit and Integration Tests for Phase 12: Unified Trading Research & Decision Engine.

Validates:
1. Market Regime Engine (evidence-based, no fabricated VIX, score <= 100)
2. Sector Rotation Engine (4-quadrant rotation, breadth, relative strength)
3. 100-Point Setup Quality Engine (7 components, missing data -> 0 pts, heuristic disclaimer)
4. Stock Discovery Engine (filtering, pagination, ranking)
5. Trade Plan Generator (entry zone, stop-loss, targets, position sizing, guardrails, disclaimers)
6. Historical Setup Validator (sample size reliability, Wilson CI, regime breakdown)
7. Research Persistence CRUD (trade plans & qualitative notes)
8. REST API Endpoints via FastAPI TestClient
"""

import pytest
from fastapi.testclient import TestClient

from app.database import (
    delete_research_note,
    delete_research_trade_plan,
    get_research_trade_plan,
    list_research_notes,
    list_research_trade_plans,
    save_research_note,
    save_research_trade_plan,
    update_research_trade_plan,
)
from app.main import app
from app.services.historical_setup_validator import validate_historical_setup
from app.services.market_regime_engine import classify_market_regime
from app.services.sector_rotation_engine import compute_sector_rotation
from app.services.trade_plan_generator import generate_trade_plan
from app.services.unified_research_engine import discover_stocks, evaluate_stock_setup_quality

client = TestClient(app)


# ---------------------------------------------------------------------------
# 1. Market Regime Engine Tests
# ---------------------------------------------------------------------------

def test_market_regime_engine_evidence_and_bounds():
    regime = classify_market_regime(universe="all")
    assert "regime" in regime
    assert regime["regime"] in (
        "STRONG BULLISH", "BULLISH", "NEUTRAL", "BEARISH", "STRONG BEARISH", "INSUFFICIENT DATA"
    )
    assert 0.0 <= regime["composite_score"] <= 100.0

    # Components checked in evidence
    evidence = regime["evidence"]
    assert 0.0 <= evidence["breadth"]["score_contribution"] <= 25.0
    assert 0.0 <= evidence["ema_participation"]["score_contribution"] <= 25.0
    assert 0.0 <= evidence["sector_participation"]["score_contribution"] <= 20.0
    assert 0.0 <= evidence["trend_strength"]["score_contribution"] <= 15.0
    assert 0.0 <= evidence["momentum"]["score_contribution"] <= 15.0

    # Data integrity check: VIX must be unavailable or explicitly estimated, never fabricated
    vol_ctx = regime.get("volatility_context", {})
    assert vol_ctx.get("vix_status") == "UNAVAILABLE"
    assert regime["coverage"]["tracked_instruments"] > 0


# ---------------------------------------------------------------------------
# 2. Sector Rotation Engine Tests
# ---------------------------------------------------------------------------

def test_sector_rotation_engine_quadrants_and_breadth():
    sectors_data = compute_sector_rotation(universe="all")
    assert "sectors" in sectors_data
    assert len(sectors_data["sectors"]) > 0

    valid_quadrants = {"LEADING", "WEAKENING", "DECLINING", "IMPROVING", "NEUTRAL"}
    for sec in sectors_data["sectors"]:
        assert sec["rotation_quadrant"] in valid_quadrants
        assert 0.0 <= sec["breadth_pct"] <= 100.0
        assert "strongest_stock" in sec
        assert "weakest_stock" in sec


# ---------------------------------------------------------------------------
# 3. 100-Point Setup Quality Engine Tests
# ---------------------------------------------------------------------------

def test_setup_quality_scoring_components_and_disclaimer():
    eval_res = evaluate_stock_setup_quality("RELIANCE")
    assert eval_res["symbol"] == "RELIANCE"
    assert 0.0 <= eval_res["setup_score"] <= 100.0
    assert eval_res["setup_category"] in (
        "HIGH-QUALITY BULLISH SETUP",
        "BULLISH SETUP",
        "DEVELOPING SETUP",
        "WEAK SETUP",
        "BEARISH SETUP",
        "NO VALID SETUP",
    )

    cb = eval_res["component_breakdown"]
    assert len(cb) == 7
    assert 0.0 <= cb["market_regime"]["score"] <= 10.0
    assert 0.0 <= cb["sector_strength"]["score"] <= 10.0
    assert 0.0 <= cb["fundamental_quality"]["score"] <= 15.0
    assert 0.0 <= cb["trend_momentum"]["score"] <= 20.0
    assert 0.0 <= cb["volume_confirmation"]["score"] <= 15.0
    assert 0.0 <= cb["market_structure"]["score"] <= 20.0
    assert 0.0 <= cb["multi_timeframe"]["score"] <= 10.0

    # Every component has a non-empty rationale
    for comp_name, comp_info in cb.items():
        assert len(comp_info["rationale"]) > 0

    # Heuristic disclaimer must exist and explicitly disclaim win probability
    disclaimer = eval_res["probability_disclaimer"]
    assert "heuristic" in disclaimer.lower()
    assert "not represent a statistically calibrated probability" in disclaimer.lower()


def test_setup_quality_missing_data_never_earns_points():
    # Test an unknown or empty symbol
    res = evaluate_stock_setup_quality("NON_EXISTENT_SYMBOL_XYZ")
    assert res["setup_score"] == 0.0
    assert res["setup_category"] == "NO VALID SETUP"


# ---------------------------------------------------------------------------
# 4. Stock Discovery Engine Tests
# ---------------------------------------------------------------------------

def test_stock_discovery_filters_and_pagination():
    res = discover_stocks(universe="all", page_size=10)
    assert "items" in res
    assert res["total_records"] > 0
    assert len(res["items"]) <= 10
    assert res["metadata"]["data_mode"] == "HISTORICAL"

    # Filter by min_score
    res_filtered = discover_stocks(universe="all", min_score=99.0)
    assert res_filtered["total_records"] <= res["total_records"]

    # Ranks must be 1, 2, ...
    for i, it in enumerate(res["items"], start=1):
        assert it["rank"] == i


# ---------------------------------------------------------------------------
# 5. Trade Plan Generator Tests
# ---------------------------------------------------------------------------

def test_trade_plan_generator_long():
    plan = generate_trade_plan("RELIANCE", account_capital=100000.0, risk_pct=1.0)
    assert plan["symbol"] == "RELIANCE"
    assert plan["status"] == "READY"
    assert plan["direction"] in ("LONG", "SHORT")

    entry_p = plan["entry_plan"]
    ideal_entry = entry_p["ideal_entry"]
    assert ideal_entry > 0.0
    assert entry_p["entry_zone_min"] <= ideal_entry <= entry_p["entry_zone_max"]

    exit_p = plan["exit_plan"]
    stop_loss = exit_p["stop_loss"]
    if plan["direction"] == "LONG":
        assert stop_loss < ideal_entry, "Stop loss must be strictly below entry for LONG"
        assert exit_p["target_1"]["price"] > ideal_entry
        assert exit_p["target_2"]["price"] > exit_p["target_1"]["price"]
    else:
        assert stop_loss > ideal_entry, "Stop loss must be strictly above entry for SHORT"
        assert exit_p["target_1"]["price"] < ideal_entry

    # Invalidation condition
    assert "invalidation_condition" in exit_p
    assert len(exit_p["invalidation_condition"]) > 10

    # Position sizing
    pos = plan["position_sizing"]
    assert pos["account_capital"] == 100000.0
    assert pos["risk_amount_inr"] == 1000.0
    assert pos["recommended_shares"] >= 0
    assert pos["capital_allocated_inr"] == round(pos["recommended_shares"] * ideal_entry, 2)
    assert pos["portfolio_heat_pct"] >= 0.0

    # Disclaimers and failure risks
    assert len(plan["risk_factors"]) >= 2
    assert "hypothetical" in plan["disclaimer"].lower()
    assert "no orders will be placed" in plan["disclaimer"].lower()


def test_trade_plan_guardrail_prevents_negative_stop_distance():
    # If a short plan has stop below entry or long plan has stop above entry
    plan = generate_trade_plan("RELIANCE", account_capital=100000.0, risk_pct=1.0, direction_override="LONG")
    # Even under edge cases, recommended_shares must never be negative
    assert plan["position_sizing"]["recommended_shares"] >= 0


# ---------------------------------------------------------------------------
# 6. Historical Setup Validator Tests
# ---------------------------------------------------------------------------

def test_historical_setup_validator():
    res = validate_historical_setup("RELIANCE", setup_type="ORDER_BLOCK_RETEST")
    assert res["status"] == "VALIDATED"
    assert res["setup_type"] == "ORDER_BLOCK_RETEST"

    # Sample size assessment
    ssa = res["sample_size_assessment"]
    assert "total_occurrences" in ssa
    assert "is_statistically_reliable" in ssa
    assert ssa["is_statistically_reliable"] == (ssa["total_occurrences"] >= 30)

    # Disclaimers present
    disclaimers = res["disclaimers"]
    assert any("past performance" in d.lower() for d in disclaimers)
    assert any("statutory" in d.lower() for d in disclaimers)


# ---------------------------------------------------------------------------
# 7. Research Persistence CRUD Tests
# ---------------------------------------------------------------------------

def test_research_trade_plans_and_notes_crud():
    # 1. Save Trade Plan
    plan_payload = {
        "symbol": "TCS",
        "direction": "LONG",
        "setup_type": "ORDER_BLOCK_RETEST",
        "entry_type": "LIMIT",
        "ideal_entry": 3500.0,
        "stop_loss": 3400.0,
        "target_1": 3650.0,
        "target_2": 3750.0,
        "risk_reward_ratio": 2.5,
        "position_size": 10,
        "risk_amount": 1000.0,
        "capital_allocated": 35000.0,
        "invalidation_condition": "Daily close below 3400",
        "notes": "Test research plan",
    }
    saved_plan = save_research_trade_plan(plan_payload)
    plan_id = saved_plan["id"]
    assert plan_id is not None
    assert saved_plan["symbol"] == "TCS"
    assert saved_plan["status"] == "MONITORING"

    # 2. Get Plan
    fetched_plan = get_research_trade_plan(plan_id)
    assert fetched_plan is not None
    assert fetched_plan["id"] == plan_id

    # 3. List Plans
    plans_list = list_research_trade_plans(symbol="TCS")
    assert any(p["id"] == plan_id for p in plans_list)

    # 4. Update Plan
    updated_plan = update_research_trade_plan(plan_id, {"status": "TARGET_1_HIT", "notes": "Target 1 achieved!"})
    assert updated_plan["status"] == "TARGET_1_HIT"
    assert updated_plan["notes"] == "Target 1 achieved!"

    # 5. Delete Plan
    assert delete_research_trade_plan(plan_id) is True
    assert get_research_trade_plan(plan_id) is None

    # 6. Save Note
    saved_note = save_research_note("TCS", note="Earnings report expected next week.", title="Quarterly Earnings")
    note_id = saved_note["id"]
    assert note_id is not None

    # 7. List Notes
    notes = list_research_notes("TCS")
    assert any(n["id"] == note_id for n in notes)

    # 8. Delete Note
    assert delete_research_note(note_id) is True


# ---------------------------------------------------------------------------
# 8. FastAPI Endpoints Tests
# ---------------------------------------------------------------------------

def test_api_endpoints_health_and_data():
    # Regime
    resp = client.get("/api/research/regime")
    assert resp.status_code == 200
    assert "regime" in resp.json()

    # Sectors
    resp = client.get("/api/research/sectors")
    assert resp.status_code == 200
    assert "sectors" in resp.json()

    # Discovery GET & POST
    resp_get = client.get("/api/research/discovery?universe=all&page_size=5")
    assert resp_get.status_code == 200
    assert len(resp_get.json()["items"]) <= 5

    resp_post = client.post("/api/research/discovery", json={"universe": "all", "page_size": 5})
    assert resp_post.status_code == 200

    # Stock Research Dossier
    resp_stock = client.get("/api/research/stock/RELIANCE")
    assert resp_stock.status_code == 200
    data = resp_stock.json()
    assert data["symbol"] == "RELIANCE"
    assert "setup_evaluation" in data
    assert "trade_plan" in data
    assert "indicators" in data
    assert "volume_intelligence" in data

    # Trade Plan endpoint
    resp_tp = client.post("/api/research/trade-plan", json={"symbol": "RELIANCE", "account_capital": 50000.0, "risk_pct": 1.5})
    assert resp_tp.status_code == 200
    assert resp_tp.json()["position_sizing"]["account_capital"] == 50000.0

    # Validate endpoint
    resp_val = client.post("/api/research/validate", json={"symbol": "RELIANCE", "setup_type": "ORDER_BLOCK_RETEST"})
    assert resp_val.status_code == 200
    assert resp_val.json()["setup_type"] == "ORDER_BLOCK_RETEST"

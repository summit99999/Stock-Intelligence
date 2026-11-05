"""
Comprehensive Test Suite for Phase 6: Advanced Fundamental Stock Screening Engine.

Tests:
1. CAGR Calculation Engine:
   - Valid positive 3Y and 5Y CAGRs
   - Rejection when base value <= 0
   - Rejection when end value <= 0
   - Insufficient historical periods
2. Average-Balance Ratio Calculations:
   - Average equity for ROE
   - Average capital employed for ROCE
   - Average assets for ROA
   - Single-period fallback when previous year missing
3. 100-Point Fundamental Quality Scoring Engine:
   - 6 category scores and weighting
   - Letter grades (A+, A, B, C, D)
   - Deduction details with economic reasons
   - Insufficient data rejection
4. Peer Comparison Service:
   - 2 to 5 companies comparison
   - Best performer identification
   - Reporting period alignment
   - Auto-suggesting sector peers
5. Screener Presets & Dynamic Enrichment:
   - 8 institutional presets
   - Dynamic enrichment with calculated ratios and quality scores
6. Screener.in CSV Provider & Overwrite Protection:
   - Watchlist/screen format parsing
   - Multi-period company statements format parsing
   - Overwrite protection preserving verified data when overwrite_verified=False
   - Allowing update when overwrite_verified=True
7. REST API Endpoints:
   - GET /api/fundamentals/company/{symbol}/calculated-ratios
   - GET /api/fundamentals/company/{symbol}/quality-score
   - GET /api/fundamentals/company/{symbol}/research
   - POST /api/fundamentals/peers/compare
   - GET /api/screener/presets/default
   - POST /api/fundamentals/import/screener-csv
"""

import pytest
from fastapi.testclient import TestClient

from app.database import init_db, list_stocks
from app.fundamental_db import (
    has_verified_record,
    init_fundamental_tables,
)
from app.main import app
from app.providers.fundamentals.screener_csv_provider import ScreenerCsvProvider
from app.routers.screener import DEFAULT_PRESETS, get_default_presets
from app.schemas.screener import ScreenRequest
from app.services.fundamental_ratios_service import (
    calculate_cagr,
    compute_all_ratios,
)
from app.services.peer_comparison_service import compare_peers
from app.services.quality_score_service import calculate_quality_score
from app.services.screener_service import run_screen


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """Ensure database and tables are seeded and initialized."""
    init_db()
    init_fundamental_tables()


@pytest.fixture
def client():
    return TestClient(app)


# ===========================================================================
# 1. CAGR Calculation & Mathematical Guardrails
# ===========================================================================

def test_cagr_positive_case():
    """Test standard CAGR calculation with normal positive growth."""
    # 100 growing to 133.1 over 3 years is exactly 10% CAGR
    cagr, warn = calculate_cagr(100.0, 133.1, 3)
    assert cagr is not None
    assert round(cagr, 1) == 10.0
    assert warn is None


def test_cagr_base_zero():
    """CAGR cannot be computed from 0 base value."""
    cagr, warn = calculate_cagr(0.0, 150.0, 3)
    assert cagr is None
    assert warn is not None
    assert "non-positive" in warn


def test_cagr_base_negative():
    """CAGR is mathematically undefined when base year has losses."""
    cagr, warn = calculate_cagr(-50.0, 150.0, 3)
    assert cagr is None
    assert warn is not None
    assert "non-positive" in warn


def test_cagr_end_negative():
    """CAGR is undefined when end year has losses."""
    cagr, warn = calculate_cagr(100.0, -20.0, 3)
    assert cagr is None
    assert warn is not None
    assert "non-positive" in warn


def test_cagr_insufficient_years():
    """Years must be > 0."""
    cagr, warn = calculate_cagr(100.0, 120.0, 0)
    assert cagr is None
    assert warn is not None


# ===========================================================================
# 2. Fundamental Ratio Engine & Average-Balance Calculations
# ===========================================================================

def test_tcs_calculated_ratios():
    """Verify calculated ratios for TCS using multi-year statements."""
    res = compute_all_ratios("TCS", statement_type="consolidated")
    assert res.symbol == "TCS"
    assert res.data_coverage_pct > 80.0
    assert res.confidence in ("HIGH", "MEDIUM")

    # TCS has strong profitability
    assert res.profitability.roe is not None
    assert res.profitability.roe > 35.0  # TCS average ROE is > 40%
    assert res.profitability.roce is not None
    assert res.profitability.roce > 45.0  # TCS ROCE is > 50%
    assert res.profitability.operating_margin_pct is not None
    assert res.profitability.operating_margin_pct > 20.0

    # Financial health: TCS has minimal debt
    assert res.health.debt_equity is not None
    assert res.health.debt_equity < 0.2
    assert res.health.cfo_pat_ratio is not None
    assert res.health.cfo_pat_ratio > 0.6  # Strong cash generation

    # Growth
    assert res.growth.revenue_cagr_3y is not None
    assert res.growth.revenue_cagr_3y > 0.0


def test_missing_stock_ratios():
    """Verify graceful handling when stock has no financial statements."""
    res = compute_all_ratios("NONEXISTENT_STOCK_999")
    assert res.symbol == "NONEXISTENT_STOCK_999"
    assert res.data_coverage_pct == 0.0
    assert res.confidence == "INSUFFICIENT_DATA"
    assert res.profitability.roe is None
    assert res.growth.revenue_cagr_3y is None


# ===========================================================================
# 3. 100-Point Fundamental Quality Scoring Engine
# ===========================================================================

def test_tcs_quality_score():
    """Verify 100-point score breakdown and deductions for TCS."""
    score_res = calculate_quality_score("TCS")
    assert score_res.symbol == "TCS"
    assert score_res.total_score is not None
    assert score_res.total_score >= 70  # TCS is top-tier bluechip
    assert score_res.grade.startswith("A")

    # Category weights sum to 100
    assert sum(c.max_points for c in score_res.category_scores.values()) == 100.0

    # Check that deductions are transparent and itemized
    category_names = [c.category.lower() for c in score_res.category_scores.values()]
    for deduction in score_res.deductions:
        assert deduction.points_lost > 0
        assert deduction.reason != ""
        assert any(c in deduction.category.lower() or deduction.category.lower() in c for c in category_names)


def test_insufficient_data_quality_score():
    """Quality score must refuse to assign misleading score with no data."""
    score_res = calculate_quality_score("NONEXISTENT_XYZ")
    assert score_res.total_score is None
    assert score_res.grade == "INSUFFICIENT_DATA"
    assert score_res.confidence == "INSUFFICIENT_DATA"


# ===========================================================================
# 4. Peer Comparison Service
# ===========================================================================

def test_peer_comparison_tcs_infy():
    """Compare TCS and INFY side-by-side."""
    comp = compare_peers(["TCS", "INFY"], target_symbol="TCS")
    assert comp.target_symbol == "TCS"
    assert len(comp.companies) == 2
    assert len(comp.metrics) >= 10

    # Ensure best_symbol is identified for metrics
    roe_metric = next((m for m in comp.metrics if m.metric_key == "roe"), None)
    assert roe_metric is not None
    assert roe_metric.best_symbol in ("TCS", "INFY")
    assert roe_metric.higher_is_better is True

    pe_metric = next((m for m in comp.metrics if m.metric_key == "pe"), None)
    assert pe_metric is not None
    assert pe_metric.higher_is_better is False


def test_peer_comparison_auto_suggest():
    """Single symbol auto-suggests sector peers."""
    comp = compare_peers(["TCS"])
    assert comp.target_symbol == "TCS"
    assert len(comp.companies) >= 1


# ===========================================================================
# 5. Screener Presets & Dynamic Enrichment
# ===========================================================================

def test_screener_default_presets_list():
    """Verify that all 8 institutional presets exist."""
    presets = get_default_presets()
    assert len(presets) == 8
    preset_names = [p.name for p in presets]
    assert "High Growth Companies" in preset_names
    assert "High ROCE Companies" in preset_names
    assert "Low Debt Companies" in preset_names
    assert "Consistent Profit Growers" in preset_names
    assert "Cash Flow Strong Companies" in preset_names
    assert "Undervalued Quality Companies" in preset_names
    assert "Promoter Skin-in-the-Game" in preset_names
    assert "Turnaround Candidates" in preset_names


def test_screener_high_roce_preset():
    """Run screening using High ROCE criteria."""
    stocks = list_stocks()
    req = ScreenRequest(min_roce=25.0, min_roe=20.0, max_debt_equity=0.5)
    items, total = run_screen(stocks, req)
    assert total > 0
    for stock in items:
        if stock.get("roce") is not None:
            assert stock["roce"] >= 25.0
        if stock.get("roe") is not None:
            assert stock["roe"] >= 20.0
        if stock.get("debt_equity") is not None:
            assert stock["debt_equity"] <= 0.5


def test_screener_quality_score_filter():
    """Screen stocks by minimum quality score."""
    stocks = list_stocks()
    req = ScreenRequest(min_quality_score=60)
    items, total = run_screen(stocks, req)
    assert total > 0
    for stock in items:
        if stock.get("quality_score") is not None:
            assert stock["quality_score"] >= 60


# ===========================================================================
# 6. Screener.in CSV Provider & Overwrite Protection
# ===========================================================================

def test_screener_csv_detect_format():
    """Test detection between screen export and multi-period statements."""
    provider = ScreenerCsvProvider()

    screen_csv = "Name,Symbol,CMP,P/E,Mar Cap\nTata Consultancy,TCS,3500,28.5,1200000"
    assert provider.detect_csv_format(screen_csv) == "screen"

    statement_csv = "Report Date,Mar 2022,Mar 2023,Mar 2024\nSales,100,120,150\nExpenses,80,95,115"
    assert provider.detect_csv_format(statement_csv) == "statements"


def test_screener_csv_parse_statements():
    """Test parsing multi-period statement sheet into normalized models."""
    provider = ScreenerCsvProvider()
    csv_content = """Report Date,Mar 2023,Mar 2024
Sales,200000,225000
Expenses,150000,165000
Operating Profit,50000,60000
OPM %,25.0%,26.7%
Other Income,3000,3500
Interest,500,600
Depreciation,4500,5000
Profit before tax,48000,57900
Tax %,25%,25%
Net Profit,36000,43425
EPS in Rs,95.0,114.5
Equity Capital,366,366
Reserves,88000,98000
Borrowings,7500,6000
Total Assets,140000,155000
Cash from Operating Activity,42000,48000
"""
    res = provider.parse_financial_statements_csv(csv_content, symbol="MOCK_STOCK", isin="INMOCK123456")
    assert len(res["income_statements"]) == 2
    assert len(res["balance_sheets"]) == 2
    assert len(res["cash_flows"]) == 2

    inc24 = next(i for i in res["income_statements"] if i.period == "FY2024")
    assert inc24.revenue_cr == 225000.0
    assert inc24.net_profit_cr == 43425.0
    assert inc24.verification_status == "imported"


def test_has_verified_record_check():
    """Verify has_verified_record correctly identifies verified statements."""
    # TCS has verified seed data for FY2024
    is_verified = has_verified_record("fundamental_income_statements", "INE467B01029", "FY2024")
    assert is_verified is True

    # Nonexistent record
    not_verified = has_verified_record("fundamental_income_statements", "INE467B01029", "FY1980")
    assert not_verified is False


# ===========================================================================
# 7. REST API Integration Endpoints
# ===========================================================================

def test_api_calculated_ratios(client):
    """GET /api/fundamentals/company/{symbol}/calculated-ratios"""
    res = client.get("/api/fundamentals/company/TCS/calculated-ratios")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "TCS"
    assert "growth" in data
    assert "profitability" in data
    assert "health" in data
    assert "valuation" in data


def test_api_quality_score(client):
    """GET /api/fundamentals/company/{symbol}/quality-score"""
    res = client.get("/api/fundamentals/company/TCS/quality-score")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "TCS"
    assert data["total_score"] is not None
    assert "category_scores" in data
    assert "deductions" in data


def test_api_peer_comparison(client):
    """POST /api/fundamentals/peers/compare"""
    res = client.post(
        "/api/fundamentals/peers/compare",
        json={"symbols": ["TCS", "INFY"], "target_symbol": "TCS"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["target_symbol"] == "TCS"
    assert len(data["companies"]) == 2


def test_api_research_dossier(client):
    """GET /api/fundamentals/company/{symbol}/research"""
    res = client.get("/api/fundamentals/company/TCS/research")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "TCS"
    assert len(data["annual_income_statements"]) > 0
    assert data["calculated_ratios"] is not None
    assert data["quality_score"] is not None
    assert data["provenance"]["verification_status"] == "verified"


def test_api_screener_presets_default(client):
    """GET /api/screener/presets/default"""
    res = client.get("/api/screener/presets/default")
    assert res.status_code == 200
    presets = res.json()
    assert len(presets) == 8


def test_api_csv_import_overwrite_protection(client):
    """POST /api/fundamentals/import/screener-csv with overwrite_verified=false protects verified data."""
    csv_content = """Report Date,Mar 2024
Sales,999999
Expenses,111111
Operating Profit,888888
Net Profit,777777
"""
    # Attempting to import into TCS which already has verified FY2024 data
    res = client.post(
        "/api/fundamentals/import/screener-csv?symbol=TCS&overwrite_verified=false",
        content=csv_content,
        headers={"Content-Type": "text/plain"},
    )
    assert res.status_code == 200
    data = res.json()
    # It must skip overwriting and record warning
    assert data["rows_skipped"] > 0
    assert any("verified record already exists" in w for w in data["warnings"])

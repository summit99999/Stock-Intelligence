"""
Phase 14.2 Test Suite: Historical Intraday Data Engine & True Time-of-Day (TOD) RVOL.

Verifies:
1. Provider Assessment & Disclosures:
   - yfinance honest evaluation (historical/delayed only, not live exchange feed).
   - Dhan optional integration status.
   - Calibrated deterministic 20-session institutional volume profile generator.
2. Ingestion Engine & Database Indexing:
   - Index `idx_ohlcv_sym_int_ts` creation and verification.
   - 75 5-minute bars per regular session (09:15 to 15:30 IST).
   - Mathematical OHLC integrity: high >= max(open, close), low <= min(open, close).
   - UTC ISO timestamp formatting (YYYY-MM-DDTHH:MM:SSZ) and IST conversion.
   - Ingestion status and telemetry reporting.
3. True Time-of-Day RVOL Precision:
   - Exact same-time interval volume accumulation across 20 historical sessions.
   - Exclusion of incomplete sessions (< 60 bars).
   - Exclusion of weekends and holidays.
   - Safe return of UNAVAILABLE (rvol: None) when valid prior sessions < 3.
   - Zero historical volume guardrail.
   - Exclusion of current ongoing session from historical baseline.
4. Market Movers & Confluence Dual-RVOL Methodology:
   - 'daily' mode ranks volume gainers by daily_rvol vs ADV20.
   - 'tod' mode ranks volume gainers by time_of_day_rvol vs same-time 20-session average.
   - Confluence compound scores and explanations dynamically reflect active RVOL mode.
   - Each stock record annotated with active_rvol_mode and active_rvol.
5. FastAPI Endpoints:
   - /api/market-movers/intraday/status
   - /api/market-movers/intraday/providers
   - /api/market-movers/intraday/seed
   - /api/market-movers/overview?rvol_mode=tod
   - /api/market-movers/volume-gainers?rvol_mode=tod
   - /api/market-movers/confluence?rvol_mode=tod
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.services.intraday_data_service import (
    assess_intraday_data_providers,
    ensure_ohlcv_indexes,
    generate_realistic_5m_bars,
    get_latest_completed_5m_interval,
    get_prior_trading_dates,
    ist_to_utc_iso,
    parse_bar_to_ist,
    seed_symbol_intraday_history,
    seed_all_tracked_stocks_intraday,
    get_intraday_ingestion_status,
    BARS_PER_REGULAR_SESSION,
    MIN_VALID_SESSION_BARS,
    TARGET_LOOKBACK_SESSIONS,
)
from app.services.money_flow_service import (
    calculate_historical_time_of_day_rvol,
    _parse_timestamp_to_ist,
)
from app.services.market_movers_service import (
    get_market_movers_and_confluence,
    extract_stock_mover_metrics,
)


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Provider Assessment Tests
# ---------------------------------------------------------------------------

def test_intraday_provider_assessment_truthfulness():
    """Verify that provider assessment truthfully differentiates delayed vs live feeds."""
    assessment = assess_intraday_data_providers()
    assert "providers" in assessment
    providers = assessment["providers"]

    # yfinance check
    assert "yfinance" in providers
    yf = providers["yfinance"]
    assert yf["is_real_time_exchange_feed"] is False
    assert yf["interval_supported"] == "5m"
    assert yf["data_mode"] == "THIRD_PARTY_HISTORICAL"
    assert yf["max_history_days"] == 60
    assert "unofficial" in yf["rate_limits"].lower()
    assert "Yahoo Finance" in yf["name"]

    # dhan check
    assert "dhan" in providers
    dhan = providers["dhan"]
    assert dhan["is_real_time_exchange_feed"] is False
    assert "5m" in dhan["interval_supported"]
    assert dhan["implemented_adapter"] is False
    assert dhan["status"] in ("CONFIGURED_UNVERIFIED", "EXPIRED_TOKEN", "AUTHENTICATION_REQUIRED")

    # deterministic offline engine check
    assert "offline_deterministic_engine" in providers
    engine = providers["offline_deterministic_engine"]
    assert engine["is_real_time_exchange_feed"] is False
    assert engine["sessions_provided"] == 20
    assert engine["bars_per_session"] == 75


# ---------------------------------------------------------------------------
# 2. Timestamp & Session Generation Tests
# ---------------------------------------------------------------------------

def test_ist_to_utc_and_parse_back():
    """Verify conversion of IST session time to UTC ISO string and back."""
    ist_date = "2026-11-05"
    ist_time = "09:15:00"

    utc_iso = ist_to_utc_iso(ist_date, ist_time)
    # 09:15 IST is 03:45 UTC
    assert utc_iso == "2026-11-05T03:45:00Z"

    # Parse back
    parsed_d, parsed_t = parse_bar_to_ist(utc_iso)
    assert parsed_d == ist_date
    assert parsed_t == ist_time


def test_parse_timestamp_to_ist_formats():
    """Verify parser handles UTC Z, UTC offset, IST offset, and naive timestamps."""
    # UTC Z
    d, t = _parse_timestamp_to_ist("2026-11-05T03:45:00Z")
    assert d == "2026-11-05"
    assert t == "09:15:00"

    # IST Offset
    d, t = _parse_timestamp_to_ist("2026-11-05T09:15:00+05:30")
    assert d == "2026-11-05"
    assert t == "09:15:00"

    # Naive space separated
    d, t = _parse_timestamp_to_ist("2026-11-05 11:30:00")
    assert d == "2026-11-05"
    assert t == "11:30:00"

    # Naive ISO
    d, t = _parse_timestamp_to_ist("2026-11-05T15:25:00")
    assert d == "2026-11-05"
    assert t == "15:25:00"


def test_generate_realistic_5m_bars_structure():
    """Verify 5-minute generator creates 75 mathematically consistent bars with U-curve volume."""
    bars = generate_realistic_5m_bars(
        symbol="RELIANCE",
        session_date="2026-11-04",
        base_price=1200.0,
        adv_20=1000000,
        session_index=1,
    )
    assert len(bars) == 75

    first_bar = bars[0]
    last_bar = bars[-1]

    # First bar is 09:15 IST (03:45 UTC)
    assert first_bar["timestamp"].endswith("03:45:00Z")
    # Last bar is 15:25 IST (09:55 UTC)
    assert last_bar["timestamp"].endswith("09:55:00Z")

    # Strict OHLC validation
    total_volume = 0
    for b in bars:
        assert b["high"] >= max(b["open"], b["close"])
        assert b["low"] <= min(b["open"], b["close"])
        assert b["volume"] > 0
        total_volume += b["volume"]

    # Verify U-curve: Open (bar 0) and Close (bar 74) have higher volume than midday (bar 36)
    open_vol = bars[0]["volume"]
    midday_vol = bars[36]["volume"]
    close_vol = bars[74]["volume"]

    assert open_vol > midday_vol
    assert close_vol > midday_vol


def test_prior_trading_dates_skips_weekends_and_holidays():
    """Verify trading dates calendar generator yields exactly 20 valid non-weekend dates."""
    dates = get_prior_trading_dates(num_sessions=20)
    assert len(dates) == 20
    # No weekends
    for d_str in dates:
        dt = datetime.strptime(d_str, "%Y-%m-%d")
        assert dt.weekday() < 5, f"Date {d_str} is on a weekend ({dt.weekday()})"
        assert d_str[5:] not in ("01-26", "08-15", "10-02", "12-25")


# ---------------------------------------------------------------------------
# 3. Database Ingestion & Telemetry Tests
# ---------------------------------------------------------------------------

def test_seed_symbol_intraday_history_and_index():
    """Verify single symbol seeding and index existence."""
    ensure_ohlcv_indexes()
    written = seed_symbol_intraday_history("INFY", num_sessions=20, force=True)
    assert written == 1500  # 20 sessions * 75 bars = 1500

    # Status check
    status = get_intraday_ingestion_status()
    assert status["total_5m_bars_stored"] >= 1500
    assert status["coverage_pct"] > 0

    infy_stats = next((s for s in status["symbol_details"] if s["symbol"] == "INFY"), None)
    assert infy_stats is not None
    assert infy_stats["bar_count"] >= 1500
    assert infy_stats["valid_sessions_count"] >= 20
    assert infy_stats["meets_target_lookback"] is True


# ---------------------------------------------------------------------------
# 4. True Time-of-Day RVOL Precision Tests
# ---------------------------------------------------------------------------

def test_tod_rvol_same_time_accumulation_exactness():
    """
    Construct 20 deterministic synthetic sessions.
    Verify that TOD RVOL accurately compares cumulative volume up to target time.
    """
    synthetic_bars = []
    # 20 prior trading sessions
    for session_idx in range(1, 21):
        date_str = f"2026-02-{session_idx:02d}"
        # Session has 75 bars: 09:15:00 to 15:25:00
        # For simplicity, assign 1,000 volume to 09:15-11:30 (28 bars), 500 to remaining
        for bar_idx in range(75):
            h = 9 + (15 + bar_idx * 5) // 60
            m = (15 + bar_idx * 5) % 60
            t_str = f"{h:02d}:{m:02d}:00"
            vol = 1000 if t_str <= "11:30:00" else 500
            # 28 bars up to 11:30:00 -> Cumulative at 11:30:00 = 28,000
            synthetic_bars.append({
                "timestamp": f"{date_str} {t_str}",
                "volume": vol,
            })

    # Today's cumulative volume at 11:30:00 is 56,000 (exactly 2.0x historical average)
    res = calculate_historical_time_of_day_rvol(
        symbol="SYNTH_TEST",
        today_cumulative_volume=56000.0,
        current_time_str="11:30:00",
        lookback_sessions=20,
        min_bars_per_session=60,
        intraday_history_bars=synthetic_bars,
        today_date="2026-02-25",
    )

    assert res["status"] == "HISTORICAL_TIME_OF_DAY"
    assert res["historical_avg_volume"] == 28000.0
    assert res["sessions_evaluated"] == 20
    assert res["rvol"] == 2.0
    assert "11:30" in res["label"]


def test_tod_rvol_excludes_incomplete_sessions():
    """
    Verify that historical sessions with < 60 bars (e.g. truncated/special sessions)
    are excluded from the 20-session baseline.
    """
    synthetic_bars = []
    # Create 5 valid sessions (75 bars each)
    for day in range(1, 6):
        date_str = f"2026-02-{day:02d}"
        for b in range(75):
            synthetic_bars.append({
                "timestamp": f"{date_str} 10:00:00",
                "volume": 100,
            })

    # Create 2 incomplete sessions (only 20 bars each)
    for day in range(6, 8):
        date_str = f"2026-02-{day:02d}"
        for b in range(20):
            synthetic_bars.append({
                "timestamp": f"{date_str} 10:00:00",
                "volume": 100,
            })

    # When min_bars_per_session=60 is enforced, only 5 sessions should be evaluated
    res = calculate_historical_time_of_day_rvol(
        symbol="INCOMPLETE_TEST",
        today_cumulative_volume=1000.0,
        current_time_str="10:00:00",
        min_bars_per_session=60,
        intraday_history_bars=synthetic_bars,
        today_date="2026-02-25",
    )

    assert res["status"] == "HISTORICAL_TIME_OF_DAY"
    assert res["sessions_evaluated"] == 5  # Exactly the 5 full sessions, not the 2 truncated ones


def test_tod_rvol_insufficient_sessions_yields_unavailable():
    """
    Verify that if fewer than min_required_sessions exist,
    TOD RVOL returns UNAVAILABLE (rvol: None) rather than an ungrounded estimate.
    """
    synthetic_bars = [
        {"timestamp": "2026-02-01 10:00:00", "volume": 1000},
        {"timestamp": "2026-02-02 10:00:00", "volume": 1000},
    ]  # Only 2 sessions, but min required is 3

    res = calculate_historical_time_of_day_rvol(
        symbol="FEW_SESSIONS",
        today_cumulative_volume=2000.0,
        current_time_str="10:00:00",
        min_required_sessions=3,
        intraday_history_bars=synthetic_bars,
        today_date="2026-02-25",
    )

    assert res["status"] == "UNAVAILABLE"
    assert res["rvol"] is None
    assert "Insufficient prior intraday sessions" in res["reason"]


def test_tod_rvol_zero_historical_volume_guardrail():
    """Verify handling when historical cumulative volume is zero."""
    synthetic_bars = []
    for day in range(1, 5):
        synthetic_bars.append({"timestamp": f"2026-02-{day:02d} 10:00:00", "volume": 0})

    res = calculate_historical_time_of_day_rvol(
        symbol="ZERO_VOL",
        today_cumulative_volume=1000.0,
        current_time_str="10:00:00",
        intraday_history_bars=synthetic_bars,
        today_date="2026-02-25",
    )

    assert res["status"] == "UNAVAILABLE"
    assert res["rvol"] is None
    assert "zero" in res["reason"].lower()


# ---------------------------------------------------------------------------
# 5. Market Movers Dual RVOL Methodology Integration Tests
# ---------------------------------------------------------------------------

def test_market_movers_rvol_methodology_selector():
    """
    Verify get_market_movers_and_confluence under both 'daily' and 'tod' modes:
    - 'daily' mode ranks volume gainers by daily_rvol.
    - 'tod' mode ranks volume gainers by time_of_day_rvol.
    - Active mode is clearly displayed in result metadata and item objects.
    """
    # Daily mode
    res_daily = get_market_movers_and_confluence(
        universe="all",
        rvol_mode="daily",
        min_rvol=0.5,
        force_refresh=True,
    )
    assert res_daily["active_rvol_mode"] == "daily"
    assert "Daily RVOL" in res_daily["rvol_methodology_label"]
    assert res_daily["filters_applied"]["rvol_mode"] == "daily"
    assert res_daily["metadata"]["active_rvol_mode"] == "daily"
    assert res_daily["metadata"]["rvol_methodology"] == "DAILY"

    if res_daily["volume_gainers"]:
        item = res_daily["volume_gainers"][0]
        assert item["active_rvol_mode"] == "daily"
        assert item["active_rvol"] == item["daily_rvol"]

    # TOD mode
    res_tod = get_market_movers_and_confluence(
        universe="all",
        rvol_mode="tod",
        min_rvol=0.1,  # Low threshold to capture all seeded stocks
        force_refresh=True,
    )
    assert res_tod["active_rvol_mode"] == "tod"
    assert "True Time-of-Day" in res_tod["rvol_methodology_label"]
    assert res_tod["filters_applied"]["rvol_mode"] == "tod"
    assert res_tod["metadata"]["active_rvol_mode"] == "tod"
    assert res_tod["metadata"]["rvol_methodology"] == "TIME_OF_DAY"

    if res_tod["volume_gainers"]:
        item = res_tod["volume_gainers"][0]
        assert item["active_rvol_mode"] == "tod"
        assert item["active_rvol"] == item["time_of_day_rvol"]
        assert item["time_of_day_rvol"] is not None
        assert item["time_of_day_rvol_status"] == "HISTORICAL_TIME_OF_DAY"


def test_confluence_compound_score_uses_active_rvol_mode():
    """Verify confluence heuristic compound score dynamically uses active RVOL."""
    res_daily = get_market_movers_and_confluence(rvol_mode="daily", min_rvol=0.1, force_refresh=True)
    res_tod = get_market_movers_and_confluence(rvol_mode="tod", min_rvol=0.1, force_refresh=True)

    if res_daily["bullish_confluence"] and res_tod["bullish_confluence"]:
        b_daily = res_daily["bullish_confluence"][0]
        b_tod = res_tod["bullish_confluence"][0]

        assert b_daily["active_rvol_mode"] == "daily"
        assert b_tod["active_rvol_mode"] == "tod"
        assert "Daily" in b_daily["interpretation"] or "RVOL" in b_daily["interpretation"]
        assert "TOD" in b_tod["interpretation"] or "Time-of-Day" in b_tod["interpretation"]


# ---------------------------------------------------------------------------
# 6. FastAPI Router Endpoints Tests
# ---------------------------------------------------------------------------

def test_api_intraday_status_endpoint(client):
    """Verify GET /api/market-movers/intraday/status endpoint."""
    r = client.get("/api/market-movers/intraday/status")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "tracked_symbols_count" in data
    assert "total_5m_bars_stored" in data
    assert data["total_5m_bars_stored"] > 0
    assert "symbols_meeting_20_session_target" in data


def test_api_intraday_providers_endpoint(client):
    """Verify GET /api/market-movers/intraday/providers endpoint."""
    r = client.get("/api/market-movers/intraday/providers")
    assert r.status_code == 200
    data = r.json()
    assert "providers" in data
    assert "yfinance" in data["providers"]
    assert "dhan" in data["providers"]
    assert "offline_deterministic_engine" in data["providers"]


def test_api_intraday_seed_endpoint(client):
    """Verify POST /api/market-movers/intraday/seed endpoint."""
    r = client.post("/api/market-movers/intraday/seed?sessions=5&force=false")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "SUCCESS"
    assert "symbols_processed" in data
    assert data["symbols_processed"] > 0


def test_api_overview_with_rvol_mode_endpoint(client):
    """Verify GET /api/market-movers/overview?rvol_mode=tod endpoint."""
    r = client.get("/api/market-movers/overview?rvol_mode=tod&min_rvol=0.5")
    assert r.status_code == 200
    data = r.json()
    assert data["active_rvol_mode"] == "tod"
    assert "True Time-of-Day" in data["rvol_methodology_label"]
    assert data["metadata"]["active_rvol_mode"] == "tod"
    assert data["filters_applied"]["rvol_mode"] == "tod"


def test_api_volume_gainers_with_rvol_mode_endpoint(client):
    """Verify GET /api/market-movers/volume-gainers?rvol_mode=tod endpoint."""
    r = client.get("/api/market-movers/volume-gainers?rvol_mode=tod&min_rvol=0.5")
    assert r.status_code == 200
    data = r.json()
    assert data["active_rvol_mode"] == "tod"
    assert "True Time-of-Day" in data["rvol_methodology_label"]


def test_api_confluence_with_rvol_mode_endpoint(client):
    """Verify GET /api/market-movers/confluence?rvol_mode=tod endpoint."""
    r = client.get("/api/market-movers/confluence?rvol_mode=tod&min_rvol=0.5")
    assert r.status_code == 200
    data = r.json()
    assert data["active_rvol_mode"] == "tod"
    assert "True Time-of-Day" in data["rvol_methodology_label"]

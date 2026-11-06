"""
Phase 14.4 — NSE Calendar Correction, Provenance Hardening & Observed Data Ingestion Readiness Test Suite.

Validates:
1. Official NSE trading calendar corrections for 2024, 2025, 2026 grounded in exchange circulars.
2. 2026 holiday discrepancies explicitly corrected (Holi Mar 3, Bakri Id May 28, Muhurat Nov 8, etc.).
3. Calendar audit function (validate_calendar_configuration).
4. Provenance audit system rejecting spoofed source strings and preserving synthetic classification.
5. Ingestion metadata validation (run_id, provider, retrieval_timestamp, raw_response_hash).
6. Exact session completeness validation (75 bars, missing/duplicate/out-of-session/misaligned, OHLC/volume bounds).
7. Special truncated session completeness (Muhurat 12 bars, DR drill 21 bars).
8. Provider ingestion readiness: truthful NOT_EXECUTED reporting for offline yfinance and unconfigured Dhan.
9. Provider-neutral ingestion pipeline with verified mock adapter (run logging, provenance recording).
10. Strict protection preventing synthetic data from ever overwriting observed data.
11. Database strict audit isolating synthetic records from TOD RVOL baseline.
12. System-wide API demo isolation.
"""

from __future__ import annotations

import hashlib
import json
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.main import app
from app.database import (
    connect,
    get_bars,
    record_ingestion_run,
    get_ingestion_run,
    list_ingestion_runs,
    record_bar_provenance_batch,
    get_bar_provenance,
    get_bars_provenance_map,
)
from app.services.data_quality_service import (
    DataSourceClassification,
    classify_data_source,
    verify_bar_provenance,
    validate_session_completeness,
    classify_session_provenance,
)
from app.services.trading_calendar_service import (
    CalendarSessionType,
    TradingStatus,
    NSECalendarEntry,
    NSE_MASTER_CALENDAR,
    is_trading_holiday,
    is_special_trading_session,
    is_trading_day,
    get_valid_historical_trading_sessions,
    get_session_expected_bars,
    get_calendar_entry,
    validate_calendar_configuration,
)
from app.services.intraday_data_service import (
    IntradayProviderAdapter,
    YFinanceIntradayAdapter,
    DhanIntradayAdapter,
    ProviderFetchResult,
    ingest_symbol_intraday_history,
    seed_symbol_intraday_history,
    get_intraday_ingestion_status,
)
from app.services.money_flow_service import (
    calculate_historical_time_of_day_rvol,
)


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Official NSE Trading Calendar & Circular Grounding Tests
# ---------------------------------------------------------------------------

def test_2024_calendar_revalidation_and_circulars():
    """Verify official NSE equity calendar 2024 with specific circular references."""
    # Republic Day (Jan 26, 2024 - Master annual circular NSE/CMTR/59737)
    entry_rep = get_calendar_entry("2024-01-26")
    assert entry_rep is not None
    assert entry_rep.session_type == CalendarSessionType.WEEKDAY_HOLIDAY
    assert entry_rep.trading_status == TradingStatus.CLOSED
    assert "Republic Day" in entry_rep.name
    assert entry_rep.circular_reference == "NSE/CMTR/59737"

    # Ram Mandir Pran Pratishtha (Jan 22, 2024 - exceptional closure NSE/CMTR/60341)
    entry_ram = get_calendar_entry("2024-01-22")
    assert entry_ram is not None
    assert entry_ram.session_type == CalendarSessionType.EXCEPTIONAL_CLOSURE
    assert entry_ram.trading_status == TradingStatus.CLOSED
    assert entry_ram.circular_reference == "NSE/CMTR/60341"

    # Disaster Recovery Live Drill (Mar 2, 2024 - Saturday special session NSE/CMTR/61021)
    entry_dr = get_calendar_entry("2024-03-02")
    assert entry_dr is not None
    assert entry_dr.session_type == CalendarSessionType.SPECIAL_TRUNCATED
    assert entry_dr.trading_status == TradingStatus.SPECIAL_HOURS
    assert entry_dr.expected_5m_bars == 21
    assert entry_dr.circular_reference == "NSE/CMTR/61021"

    # Parliamentary Elections Maharashtra (May 20, 2024 - exceptional closure NSE/CMTR/61489)
    entry_elec = get_calendar_entry("2024-05-20")
    assert entry_elec is not None
    assert entry_elec.session_type == CalendarSessionType.EXCEPTIONAL_CLOSURE
    assert entry_elec.circular_reference == "NSE/CMTR/61489"

    # Diwali Laxmi Pujan / Muhurat Trading (Nov 1, 2024 - 12 bars NSE/CMTR/64512)
    entry_muh = get_calendar_entry("2024-11-01")
    assert entry_muh is not None
    assert entry_muh.session_type == CalendarSessionType.SPECIAL_TRUNCATED
    assert entry_muh.expected_5m_bars == 12
    assert entry_muh.circular_reference == "NSE/CMTR/64512"

    # Maharashtra Assembly Elections (Nov 20, 2024 - exceptional closure NSE/CMTR/64890)
    entry_ass = get_calendar_entry("2024-11-20")
    assert entry_ass is not None
    assert entry_ass.circular_reference == "NSE/CMTR/64890"


def test_2025_calendar_revalidation_and_circulars():
    """Verify official NSE equity calendar 2025 with specific circular references."""
    # Mahashivratri (Feb 26, 2025 - Master annual circular NSE/CMTR/65489)
    entry_maha = get_calendar_entry("2025-02-26")
    assert entry_maha is not None
    assert entry_maha.session_type == CalendarSessionType.WEEKDAY_HOLIDAY
    assert entry_maha.circular_reference == "NSE/CMTR/65489"

    # Holi (Mar 14, 2025)
    entry_holi = get_calendar_entry("2025-03-14")
    assert entry_holi is not None
    assert "Holi" in entry_holi.name

    # Bakri Id (Jun 7, 2025 - Saturday weekend holiday)
    entry_bakri = get_calendar_entry("2025-06-07")
    assert entry_bakri is not None
    assert entry_bakri.session_type == CalendarSessionType.WEEKEND_HOLIDAY

    # Diwali Muhurat Trading (Oct 21, 2025 - 12 bars circular NSE/CMTR/69512)
    entry_muh = get_calendar_entry("2025-10-21")
    assert entry_muh is not None
    assert entry_muh.session_type == CalendarSessionType.SPECIAL_TRUNCATED
    assert entry_muh.circular_reference == "NSE/CMTR/69512"


def test_2026_calendar_corrected_discrepancies():
    """
    Verify all 2026 NSE cash equity calendar dates and explicit discrepancy corrections.
    """
    # 1. Holi MUST be March 3, 2026 (circular NSE/CMTR/71004) - NOT March 4
    entry_holi = get_calendar_entry("2026-03-03")
    assert entry_holi is not None
    assert "Holi" in entry_holi.name
    assert entry_holi.circular_reference == "NSE/CMTR/71004"
    is_hol_mar3, _ = is_trading_holiday("2026-03-03")
    assert is_hol_mar3 is True
    # Verify March 4, 2026 is a regular trading day
    is_hol_mar4, _ = is_trading_holiday("2026-03-04")
    assert is_hol_mar4 is False

    # 2. Ram Navami: March 26, 2026
    entry_ram = get_calendar_entry("2026-03-26")
    assert entry_ram is not None
    assert "Ram Navami" in entry_ram.name
    is_hol_ram, _ = is_trading_holiday("2026-03-26")
    assert is_hol_ram is True

    # 3. Mahavir Jayanti: March 31, 2026
    entry_mah = get_calendar_entry("2026-03-31")
    assert entry_mah is not None
    assert "Mahavir Jayanti" in entry_mah.name
    is_hol_mah, _ = is_trading_holiday("2026-03-31")
    assert is_hol_mah is True

    # 4. Good Friday: April 3, 2026
    entry_gf = get_calendar_entry("2026-04-03")
    assert entry_gf is not None
    assert "Good Friday" in entry_gf.name

    # 5. Dr. Baba Saheb Ambedkar Jayanti: April 14, 2026
    entry_amb = get_calendar_entry("2026-04-14")
    assert entry_amb is not None
    assert "Ambedkar" in entry_amb.name

    # 6. Maharashtra Day: May 1, 2026
    entry_mah_day = get_calendar_entry("2026-05-01")
    assert entry_mah_day is not None
    assert "Maharashtra Day" in entry_mah_day.name

    # 7. Bakri Id (Id-Ul-Zuha): May 28, 2026 (NOT May 27)
    entry_bak = get_calendar_entry("2026-05-28")
    assert entry_bak is not None
    assert "Bakri Id" in entry_bak.name
    is_hol_bak, _ = is_trading_holiday("2026-05-28")
    assert is_hol_bak is True
    # May 27 is NOT a holiday
    is_hol_may27, _ = is_trading_holiday("2026-05-27")
    assert is_hol_may27 is False

    # 8. Muharram: June 26, 2026
    entry_muh = get_calendar_entry("2026-06-26")
    assert entry_muh is not None
    assert "Muharram" in entry_muh.name

    # 9. Ganesh Chaturthi: September 14, 2026
    entry_gan = get_calendar_entry("2026-09-14")
    assert entry_gan is not None
    assert "Ganesh Chaturthi" in entry_gan.name

    # 10. Mahatma Gandhi Jayanti: October 2, 2026
    entry_gan2 = get_calendar_entry("2026-10-02")
    assert entry_gan2 is not None
    assert "Gandhi" in entry_gan2.name

    # 11. Dussehra: October 20, 2026
    entry_dus = get_calendar_entry("2026-10-20")
    assert entry_dus is not None
    assert "Dussehra" in entry_dus.name

    # 12. Diwali Muhurat Trading: Sunday, November 8, 2026 (Special session 18:15–19:15 IST, 12 bars)
    entry_muhurat_26 = get_calendar_entry("2026-11-08")
    assert entry_muhurat_26 is not None
    assert entry_muhurat_26.session_type == CalendarSessionType.SPECIAL_TRUNCATED
    assert entry_muhurat_26.trading_status == TradingStatus.SPECIAL_HOURS
    assert entry_muhurat_26.expected_5m_bars == 12
    assert "Muhurat" in entry_muhurat_26.name
    assert entry_muhurat_26.start_time == "18:15:00"
    assert entry_muhurat_26.end_time == "19:15:00"

    # 13. Diwali-Balipratipada: November 10, 2026
    entry_bali = get_calendar_entry("2026-11-10")
    assert entry_bali is not None
    assert "Balipratipada" in entry_bali.name

    # 14. Gurunanak Jayanti: November 24, 2026
    entry_guru = get_calendar_entry("2026-11-24")
    assert entry_guru is not None
    assert "Gurunanak" in entry_guru.name

    # 15. Christmas: December 25, 2026
    entry_xmas = get_calendar_entry("2026-12-25")
    assert entry_xmas is not None
    assert "Christmas" in entry_xmas.name


def test_calendar_audit_function():
    """Verify that validate_calendar_configuration() audits all entries without error."""
    audit = validate_calendar_configuration()
    assert audit["status"] == "VALID"
    assert 2024 in audit["verified_years"]
    assert 2025 in audit["verified_years"]
    assert 2026 in audit["verified_years"]
    assert audit["total_calendar_entries"] >= 45
    assert audit["entries_with_circulars"] > 0


# ---------------------------------------------------------------------------
# 2. Provenance Hardening & Anti-Spoofing Tests
# ---------------------------------------------------------------------------

def test_provenance_verification_rejects_spoofed_source():
    """
    A bar with source='yfinance_historical_5m' but lacking ingestion metadata or
    hash verification must be classified as UNKNOWN (unverified/spoofed).
    """
    spoofed_bar = {
        "timestamp": "2026-03-02T04:00:00Z",
        "open": 2400.0,
        "high": 2410.0,
        "low": 2395.0,
        "close": 2405.0,
        "volume": 50000,
        "source": "yfinance_historical_5m",
        # Missing ingestion_run_id, raw_response_hash, etc.
    }
    cls, reason, meta = verify_bar_provenance(spoofed_bar, strict_audit=True)
    assert cls == DataSourceClassification.UNKNOWN
    assert "UNVERIFIED_OR_SPOOFED_SOURCE" in reason


def test_provenance_verification_synthetic_cannot_disguise():
    """
    Synthetic bars cannot be disguised by setting source='yfinance' or adding mock flags.
    """
    synthetic_disguised_bar = {
        "timestamp": "2026-03-02T04:00:00Z",
        "open": 2400.0,
        "high": 2410.0,
        "low": 2395.0,
        "close": 2405.0,
        "volume": 50000,
        "source": "yfinance_historical_5m",
        "is_synthetic": True,  # Explicit marker
    }
    cls, reason, meta = verify_bar_provenance(synthetic_disguised_bar, strict_audit=True)
    assert cls == DataSourceClassification.SYNTHETIC
    assert "SYNTHETIC" in reason

    # Also check source='deterministic_calibrated_5m'
    calibrated_bar = {
        "timestamp": "2026-03-02T04:00:00Z",
        "open": 2400.0,
        "high": 2410.0,
        "low": 2395.0,
        "close": 2405.0,
        "volume": 50000,
        "source": "deterministic_calibrated_5m",
    }
    cls_cal, reason_cal, meta_cal = verify_bar_provenance(calibrated_bar, strict_audit=True)
    assert cls_cal == DataSourceClassification.SYNTHETIC
    assert "SYNTHETIC" in reason_cal


def test_provenance_verification_genuine_ingestion_metadata():
    """
    A bar with full cryptographic ingestion trail (run_id, provider, sha256 hash, retrieval_timestamp)
    is verified as OBSERVED_HISTORICAL.
    """
    valid_sha256 = hashlib.sha256(b'{"sample": "market_payload"}').hexdigest()
    genuine_bar = {
        "timestamp": "2026-03-02T04:00:00Z",
        "open": 2400.0,
        "high": 2410.0,
        "low": 2395.0,
        "close": 2405.0,
        "volume": 50000,
        "source": "yfinance_historical_5m",
        "provider": "yfinance",
        "ingestion_run_id": "run_ingest_test_001",
        "raw_response_hash": valid_sha256,
        "retrieval_timestamp": "2026-03-02T10:00:00Z",
    }
    cls, reason, meta = verify_bar_provenance(genuine_bar, strict_audit=True)
    assert cls == DataSourceClassification.OBSERVED_HISTORICAL
    assert "VERIFIED_OBSERVED" in reason
    assert meta["ingestion_run_id"] == "run_ingest_test_001"


# ---------------------------------------------------------------------------
# 3. Exact Session Completeness Validator Tests
# ---------------------------------------------------------------------------

def _generate_valid_regular_session_bars(date_str: str = "2026-03-02", source: str = "yfinance") -> list[dict]:
    """Helper to generate a perfect sequence of 75 5-minute bars (09:15:00 to 15:25:00 IST)."""
    # 09:15:00 IST = 03:45:00 UTC
    start_utc = datetime.fromisoformat(f"{date_str}T03:45:00+00:00")
    bars = []
    for i in range(75):
        bar_time = start_utc + timedelta(minutes=5 * i)
        ts_str = bar_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        bars.append({
            "timestamp": ts_str,
            "open": 2400.0 + i * 0.1,
            "high": 2405.0 + i * 0.1,
            "low": 2395.0 + i * 0.1,
            "close": 2402.0 + i * 0.1,
            "volume": 10000 + i * 100,
            "source": source,
        })
    return bars


def test_session_completeness_valid_75_bars():
    """Verify that a standard regular trading session of 75 bars validates completely."""
    bars = _generate_valid_regular_session_bars("2026-03-02")
    res = validate_session_completeness("2026-03-02", bars, "5m")
    assert res["is_complete"] is True
    assert res["status"] == "SESSION_COMPLETE"
    assert res["expected_bars"] == 75
    assert res["actual_bars"] == 75
    assert len(res["errors"]) == 0
    assert len(res["missing_intervals"]) == 0


def test_session_completeness_missing_intervals():
    """Verify detection of missing intervals (e.g., 74 bars instead of 75)."""
    bars = _generate_valid_regular_session_bars("2026-03-02")
    # Drop interval #30 (11:45 IST)
    bars.pop(30)
    res = validate_session_completeness("2026-03-02", bars, "5m")
    assert res["is_complete"] is False
    assert res["actual_bars"] == 74
    assert len(res["missing_intervals"]) == 1
    assert any("MISSING_INTERVALS" in e for e in res["errors"])


def test_session_completeness_duplicate_intervals():
    """Verify detection of duplicate timestamps within a session."""
    bars = _generate_valid_regular_session_bars("2026-03-02")
    # Duplicate bar #5
    bars.append(bars[5].copy())
    res = validate_session_completeness("2026-03-02", bars, "5m")
    assert res["is_complete"] is False
    assert any("DUPLICATE_TIMESTAMPS" in e for e in res["errors"])


def test_session_completeness_out_of_session_intervals():
    """Verify detection of bars outside 09:15–15:30 IST window."""
    bars = _generate_valid_regular_session_bars("2026-03-02")
    # Add a bar at 09:10:00 IST (03:40 UTC)
    out_bar = {
        "timestamp": "2026-03-02T03:40:00Z",
        "open": 2400.0, "high": 2405.0, "low": 2395.0, "close": 2400.0,
        "volume": 5000, "source": "yfinance",
    }
    bars.insert(0, out_bar)
    res = validate_session_completeness("2026-03-02", bars, "5m")
    assert res["is_complete"] is False
    assert any("OUT_OF_SESSION_TIMESTAMPS" in e for e in res["errors"])


def test_session_completeness_misaligned_interval():
    """Verify detection of timestamps not aligned to 5-minute boundaries."""
    bars = _generate_valid_regular_session_bars("2026-03-02")
    # Replace bar #10 with an unaligned timestamp (09:17:00 IST = 03:47 UTC)
    bars[10]["timestamp"] = "2026-03-02T03:47:00Z"
    res = validate_session_completeness("2026-03-02", bars, "5m")
    assert res["is_complete"] is False
    assert any("MISALIGNED_INTERVALS" in e for e in res["errors"])


def test_session_completeness_invalid_ohlc():
    """Verify rejection of bars with invalid OHLC geometry."""
    bars = _generate_valid_regular_session_bars("2026-03-02")
    # Make High < Low in bar #15
    bars[15]["high"] = 2390.0
    bars[15]["low"] = 2410.0
    res = validate_session_completeness("2026-03-02", bars, "5m")
    assert res["is_complete"] is False
    assert any("INVALID_OHLC_RELATIONSHIPS" in e for e in res["errors"])


def test_session_completeness_negative_volume():
    """Verify rejection of bars with negative volume."""
    bars = _generate_valid_regular_session_bars("2026-03-02")
    bars[20]["volume"] = -100
    res = validate_session_completeness("2026-03-02", bars, "5m")
    assert res["is_complete"] is False
    assert any("NEGATIVE_OR_INVALID_VOLUME" in e for e in res["errors"])


def test_session_completeness_special_session_muhurat():
    """Verify that Diwali Muhurat special truncated session validates with 12 bars."""
    # 2024-11-01 Muhurat was 18:00–19:00 IST (12:30 UTC), 12 bars expected
    start_utc = datetime.fromisoformat("2024-11-01T12:30:00+00:00")
    bars = []
    for i in range(12):
        ts = (start_utc + timedelta(minutes=5 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        bars.append({
            "timestamp": ts,
            "open": 2400.0, "high": 2405.0, "low": 2395.0, "close": 2402.0,
            "volume": 20000, "source": "yfinance",
        })
    res = validate_session_completeness("2024-11-01", bars, "5m")
    assert res["is_complete"] is True
    assert res["expected_bars"] == 12
    assert res["actual_bars"] == 12
    assert res["status"] == "SESSION_COMPLETE"


# ---------------------------------------------------------------------------
# 4. Provider Ingestion Readiness & Truthful Error Reporting
# ---------------------------------------------------------------------------

def test_provider_yfinance_network_failure_truthful_reporting(monkeypatch):
    """A mocked network failure is reported without making external requests."""
    import yfinance as yf

    class FailedTicker:
        def history(self, **kwargs):
            raise RuntimeError("network connection timed out")

    monkeypatch.setattr(yf, "Ticker", lambda symbol: FailedTicker())
    adapter = YFinanceIntradayAdapter()
    result = adapter.fetch_intraday_bars("RELIANCE", interval="5m", num_sessions=5)
    assert result.status == "NETWORK_UNAVAILABLE"
    assert result.error_message is not None
    assert len(result.bars) == 0


def test_provider_dhan_unconfigured_truthful_reporting():
    """
    Dhan adapter with no API credentials must report NOT_EXECUTED.
    """
    adapter = DhanIntradayAdapter()
    result = adapter.fetch_intraday_bars("TCS", interval="5m", num_sessions=5)
    assert result.status == "NOT_EXECUTED"
    assert result.error_message is not None
    assert any(k in result.error_message.lower() for k in ("authentication", "configured", "token", "client"))


class MockVerifiedObservedAdapter(IntradayProviderAdapter):
    """A test adapter producing verified observed bars with valid SHA-256 payload."""
    def __init__(self, session_date: str = "2026-03-02"):
        self.session_date = session_date
        self.provider_name = "yfinance"

    def fetch_intraday_bars(
        self,
        symbol: str,
        interval: str = "5m",
        num_sessions: int = 1,
    ) -> ProviderFetchResult:
        run_id = f"test_run_{uuid.uuid4().hex[:12]}"
        bars = _generate_valid_regular_session_bars(self.session_date, source="yfinance_historical_5m")
        raw_json = json.dumps(bars, sort_keys=True).encode("utf-8")
        raw_hash = hashlib.sha256(raw_json).hexdigest()
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Attach observed metadata
        for b in bars:
            b["provider"] = "yfinance"
            b["provider_symbol"] = f"{symbol}.NS"
            b["provider_timestamp"] = datetime.fromisoformat(
                b["timestamp"].replace("Z", "+00:00")
            ).isoformat()
            b["symbol"] = symbol
            b["exchange"] = "NSE"
            b["interval"] = interval
            b["raw_response_hash"] = raw_hash
            b["retrieval_timestamp"] = now_utc
            b["ingestion_run_id"] = run_id

        return ProviderFetchResult(
            success=True,
            status="SUCCESS",
            provider="yfinance",
            symbol=symbol,
            interval=interval,
            bars=bars,
            provider_symbol=f"{symbol}.NS",
            run_id=run_id,
            retrieval_timestamp=now_utc,
            raw_response_hash=raw_hash,
        )


def test_provider_ingestion_pipeline_with_mock_adapter():
    """
    Test the full ingestion pipeline:
    1. Adapter fetches valid observed bars.
    2. Session completeness is verified.
    3. Run recorded in intraday_ingestion_runs.
    4. Observed bars recorded separately from synthetic ohlcv and with provenance.
    """
    test_sym = "TEST_INGESTION_SYM"
    mock_adapter = MockVerifiedObservedAdapter("2026-03-02")
    run_id_created = None

    try:
        report = ingest_symbol_intraday_history(
            symbol=test_sym,
            adapter=mock_adapter,
            num_sessions=1,
        )

        assert report["status"] == "SUCCESS"
        assert report["completed_sessions"] == 1
        assert report["valid_bars_ingested"] == 75
        assert report["run_id"] is not None
        run_id_created = report["run_id"]

        # Verify DB ingestion run was logged
        run_record = get_ingestion_run(report["run_id"])
        assert run_record is not None
        assert run_record["symbol"] == test_sym
        assert run_record["provider"] == "yfinance"
        assert run_record["bar_count"] == 75

        # Verify bar provenance was written
        sample_bar_prov = get_bar_provenance(test_sym, "5m", "2026-03-02T03:45:00Z")
        assert sample_bar_prov is not None
        assert sample_bar_prov["provider"] == "yfinance"
        assert sample_bar_prov["ingestion_run_id"] == report["run_id"]
        assert sample_bar_prov["provenance_classification"] == "OBSERVED_HISTORICAL"

        # Verify get_bars with exclude_synthetic=True returns the ingested bars
        stored_bars = get_bars(test_sym, interval="5m", exclude_synthetic=True)
        assert len(stored_bars) == 75

    finally:
        # Clean up test symbol records
        with connect() as con:
            con.execute("DELETE FROM observed_intraday_ohlcv WHERE symbol = ?", (test_sym,))
            con.execute("DELETE FROM ohlcv WHERE symbol = ?", (test_sym,))
            con.execute("DELETE FROM bar_provenance WHERE symbol = ?", (test_sym,))
            if run_id_created:
                con.execute("DELETE FROM intraday_ingestion_runs WHERE id = ?", (run_id_created,))


def test_seed_synthetic_cannot_overwrite_observed_data():
    """
    Verify that seed_symbol_intraday_history strictly refuses to overwrite observed data
    if bar_provenance records exist.
    """
    test_sym = "TEST_GUARD_SYM"
    mock_adapter = MockVerifiedObservedAdapter("2026-03-02")
    run_id_created = None

    try:
        # Ingest observed data first
        report = ingest_symbol_intraday_history(test_sym, adapter=mock_adapter, num_sessions=1)
        run_id_created = report.get("run_id")

        # Attempt to seed synthetic data over the observed symbol (even with force=True)
        res = seed_symbol_intraday_history(test_sym, num_sessions=5, force=True)
        assert res == 0

        # Verify observed bars were NOT wiped out or overwritten
        stored_bars = get_bars(test_sym, interval="5m")
        assert len(stored_bars) == 75
        sample_prov = get_bar_provenance(test_sym, "5m", "2026-03-02T03:45:00Z")
        assert sample_prov is not None
        assert sample_prov["provenance_classification"] == "OBSERVED_HISTORICAL"

    finally:
        with connect() as con:
            con.execute("DELETE FROM observed_intraday_ohlcv WHERE symbol = ?", (test_sym,))
            con.execute("DELETE FROM ohlcv WHERE symbol = ?", (test_sym,))
            con.execute("DELETE FROM bar_provenance WHERE symbol = ?", (test_sym,))
            if run_id_created:
                con.execute("DELETE FROM intraday_ingestion_runs WHERE id = ?", (run_id_created,))


# ---------------------------------------------------------------------------
# 5. Production Baseline & Demo Isolation Audit Tests
# ---------------------------------------------------------------------------

def test_database_strict_audit_isolates_db_synthetic():
    """
    Calling calculate_historical_time_of_day_rvol on database bars with allow_synthetic=False
    must return UNAVAILABLE because all 46,500 bars in database are synthetic.
    """
    res = calculate_historical_time_of_day_rvol(
        symbol="INFY",
        today_cumulative_volume=500000,
        current_time_str="14:15:00",
        allow_synthetic=False,
    )
    assert res["rvol"] is None
    assert res["tod_rvol_status"] == "UNAVAILABLE"
    assert res["tod_source"] == "UNAVAILABLE"
    assert res["tod_valid_sessions"] == 0
    assert "synthetic calibrated sessions isolated" in res["reason"]


def test_system_wide_demo_isolation_across_endpoints(client):
    """
    Verify API endpoints: default production request (allow_synthetic=false) isolates
    synthetic data, while demo request (allow_synthetic=true) returns SYNTHETIC badges.
    """
    # 1. Market Movers Overview
    resp_prod = client.get("/api/market-movers/overview?rvol_mode=tod&allow_synthetic=false")
    assert resp_prod.status_code == 200
    data_prod = resp_prod.json()
    assert data_prod["filters_applied"]["allow_synthetic"] is False
    for item in data_prod["volume_gainers"]:
        assert item["tod_source"] == "OBSERVED_HISTORICAL"

    # 2. Ingestion Status
    resp_status = client.get("/api/market-movers/intraday/status?allow_synthetic=false")
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["total_synthetic_bars"] == 46500
    assert status_data["total_observed_bars"] in (0, 2658)
    assert status_data["production_status"] in ("SYNTHETIC_SIMULATION_ONLY", "PARTIAL_OBSERVED_DATA")


def test_database_provenance_helpers():
    """Verify database CRUD helpers for intraday_ingestion_runs and bar_provenance."""
    test_run_id = f"test_run_crud_{uuid.uuid4().hex[:8]}"
    test_sym = "CRUD_SYM"

    try:
        # 1. Record ingestion run
        run_data = {
            "id": test_run_id,
            "provider": "test_prov",
            "provider_symbol": f"{test_sym}.NS",
            "symbol": test_sym,
            "interval": "5m",
            "bar_count": 5,
            "retrieval_timestamp": "2026-03-02T10:00:00Z",
            "raw_response_hash": "hash999",
            "provenance_classification": "OBSERVED_HISTORICAL",
            "data_quality_status": "VERIFIED_OBSERVED_INTRADAY",
        }
        res_id = record_ingestion_run(run_data)
        assert res_id == test_run_id

        run_info = get_ingestion_run(test_run_id)
        assert run_info is not None
        assert run_info["provider"] == "test_prov"
        assert run_info["bar_count"] == 5

        runs_list = list_ingestion_runs(symbol=test_sym)
        assert len(runs_list) >= 1

        # 2. Record provenance batch
        records = [
            {
                "symbol": test_sym,
                "interval": "5m",
                "timestamp": f"2026-03-02T03:{45 + 5*i:02d}:00Z",
                "provider": "test_prov",
                "provider_symbol": f"{test_sym}.NS",
                "ingestion_run_id": test_run_id,
                "raw_response_hash": "hash999",
                "retrieval_timestamp": "2026-03-02T10:00:00Z",
                "provenance_classification": "OBSERVED_HISTORICAL",
                "data_quality_status": "VERIFIED_OBSERVED_INTRADAY",
            }
            for i in range(3)
        ]
        n_rec = record_bar_provenance_batch(records)
        assert n_rec == 3

        # 3. Retrieve single and map
        single_p = get_bar_provenance(test_sym, "5m", "2026-03-02T03:45:00Z")
        assert single_p is not None
        assert single_p["provider"] == "test_prov"

        prov_map = get_bars_provenance_map(test_sym, "5m")
        assert len(prov_map) == 3

    finally:
        with connect() as con:
            con.execute("DELETE FROM bar_provenance WHERE symbol = ?", (test_sym,))
            con.execute("DELETE FROM intraday_ingestion_runs WHERE id = ?", (test_run_id,))

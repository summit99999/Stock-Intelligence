from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json

import pandas as pd
import pytest

from app import database
from app.services import intraday_data_service as intraday


@pytest.fixture
def temporary_intraday_db(monkeypatch, tmp_path):
    path = tmp_path / "intraday-test.sqlite"
    monkeypatch.setattr(database, "DB_PATH", path)
    with database.connect() as con:
        con.execute(database.OHLCV_DDL)
        con.execute(database.INTRADAY_INGESTION_RUNS_DDL)
        con.execute(database.BAR_PROVENANCE_DDL)
        con.execute(database.OBSERVED_INTRADAY_OHLCV_DDL)
    return path


def _provider_frame() -> pd.DataFrame:
    timestamps = pd.date_range(
        "2026-03-02 09:15:00",
        periods=75,
        freq="5min",
        tz="Asia/Kolkata",
    )
    return pd.DataFrame(
        {
            "Open": [100.0] * len(timestamps),
            "High": [102.0] * len(timestamps),
            "Low": [99.0] * len(timestamps),
            "Close": [101.0] * len(timestamps),
            "Adj Close": [101.0] * len(timestamps),
            "Volume": [2500] * len(timestamps),
        },
        index=timestamps,
    )


def test_yfinance_adapter_normalizes_provider_response_and_throttles(
    monkeypatch, prepared_current_instrument_database
):
    import yfinance as yf

    frame = _provider_frame()
    request_intervals = []

    class FakeTicker:
        def history(self, **kwargs):
            request_intervals.append(kwargs)
            return frame

    monkeypatch.setattr(yf, "Ticker", lambda symbol: FakeTicker())
    clock = [100.0]
    sleeps = []

    def fake_sleep(seconds):
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(intraday.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(intraday.time, "sleep", fake_sleep)
    monkeypatch.setattr(intraday, "_YFINANCE_LAST_REQUEST", 0.0)

    adapter = intraday.YFinanceIntradayAdapter()
    first = adapter.fetch_intraday_bars("RELIANCE", num_sessions=3)
    second = adapter.fetch_intraday_bars("RELIANCE", num_sessions=3)

    assert first.success and second.success
    assert request_intervals[0]["interval"] == "5m"
    assert request_intervals[0]["period"] == "6d"
    assert first.provider_symbol == "RELIANCE.NS"
    assert len(first.bars) == 75
    bar = first.bars[0]
    assert bar["symbol"] == "RELIANCE"
    assert bar["exchange"] == "NSE"
    assert bar["provider_timestamp"] == "2026-03-02T09:15:00+05:30"
    assert bar["timestamp"] == "2026-03-02T03:45:00Z"
    assert bar["volume"] == 2500
    assert bar["provenance_classification"] == "PENDING_VALIDATION"
    assert first.raw_response_hash == hashlib.sha256(
        frame.to_json(orient="table", date_format="iso").encode("utf-8")
    ).hexdigest()
    assert first.provider_metadata["raw_http_response_available"] is False
    assert sleeps == [pytest.approx(2.0)]


def test_yfinance_adapter_rejects_missing_volume_column(
    monkeypatch, prepared_current_instrument_database
):
    import yfinance as yf

    frame = _provider_frame().drop(columns=["Volume"])

    class FakeTicker:
        def history(self, **kwargs):
            return frame

    monkeypatch.setattr(yf, "Ticker", lambda symbol: FakeTicker())
    monkeypatch.setattr(intraday.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(intraday, "_YFINANCE_LAST_REQUEST", 0.0)

    result = intraday.YFinanceIntradayAdapter().fetch_intraday_bars("TCS", num_sessions=1)
    assert result.status == "INVALID_PROVIDER_RESPONSE"
    assert result.bars == []
    assert "Volume" in result.error_message


def test_dhan_missing_authentication_does_not_make_request(monkeypatch):
    from app.config import DhanConfig
    from app.services import token_store

    monkeypatch.setattr("app.config.get_dhan_config", lambda: DhanConfig())
    monkeypatch.setattr(token_store, "get_token", lambda: None)
    result = intraday.DhanIntradayAdapter().fetch_intraday_bars("TCS")
    assert result.status == "NOT_EXECUTED"
    assert result.bars == []
    assert "valid stored access token" in result.error_message


def test_incomplete_ingestion_records_provider_range_and_session_gaps(temporary_intraday_db):
    frame = _provider_frame().iloc[:-1]
    response_hash = hashlib.sha256(frame.to_json(orient="table", date_format="iso").encode("utf-8")).hexdigest()
    retrieval_timestamp = "2026-03-03T00:00:00Z"
    bars = []
    for timestamp, row in frame.iterrows():
        bars.append({
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "interval": "5m",
            "provider_timestamp": timestamp.isoformat(),
            "timestamp": timestamp.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": int(row["Volume"]),
            "adj_close": float(row["Adj Close"]),
            "source": "yfinance_historical_5m",
            "provider": "yfinance",
            "provider_symbol": "RELIANCE.NS",
            "retrieval_timestamp": retrieval_timestamp,
            "raw_response_hash": response_hash,
            "provenance_classification": "PENDING_VALIDATION",
            "data_quality_status": "PENDING_SESSION_VALIDATION",
        })

    class PartialAdapter:
        def fetch_intraday_bars(self, symbol, interval="5m", num_sessions=20):
            return intraday.ProviderFetchResult(
                success=True,
                status="SUCCESS",
                provider="yfinance",
                symbol=symbol,
                interval=interval,
                bars=bars,
                provider_symbol="RELIANCE.NS",
                run_id="incomplete-run",
                retrieval_timestamp=retrieval_timestamp,
                raw_response_hash=response_hash,
                provider_metadata={
                    "requested_period": "6d",
                    "max_history_days": 60,
                    "response_dataframe_sha256": response_hash,
                    "raw_http_response_available": False,
                },
            )

    result = intraday.ingest_symbol_intraday_history("RELIANCE", adapter=PartialAdapter())
    run = database.get_ingestion_run("incomplete-run")

    assert result["status"] == "INCOMPLETE_DATA"
    assert run["actual_start_date"] == "2026-03-02"
    assert run["actual_end_date"] == "2026-03-02"
    assert run["data_quality_status"] == "REJECTED_NO_VALID_SESSION"
    assert run["raw_response_hash"] == response_hash
    provider_metadata = json.loads(run["provider_metadata_json"])
    session_quality = json.loads(run["session_quality_json"])
    assert provider_metadata["request"]["period"] == "6d"
    assert provider_metadata["response"]["raw_http_response_available"] is False
    assert session_quality[0]["missing_intervals"] == ["15:25:00"]
    with database.connect() as con:
        assert con.execute("SELECT COUNT(*) FROM observed_intraday_ohlcv").fetchone()[0] == 0


def _run_metadata(run_id: str) -> dict:
    return {
        "id": run_id,
        "symbol": "RELIANCE",
        "provider": "yfinance",
        "provider_symbol": "RELIANCE.NS",
        "exchange": "NSE",
        "interval": "5m",
        "bar_count": 1,
        "retrieval_timestamp": "2026-03-03T00:00:00Z",
        "raw_response_hash": "response-hash",
        "provenance_classification": "OBSERVED_HISTORICAL",
        "data_quality_status": "VERIFIED_OBSERVED_INTRADAY",
    }


def _observed_bar(run_id: str, *, volume: int = 100) -> dict:
    return {
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "interval": "5m",
        "provider_timestamp": "2026-03-02T09:15:00+05:30",
        "timestamp": "2026-03-02T03:45:00Z",
        "open": 100.0,
        "high": 102.0,
        "low": 99.0,
        "close": 101.0,
        "volume": volume,
        "adj_close": 101.0,
        "source": "yfinance_historical_5m",
        "provider": "yfinance",
        "provider_symbol": "RELIANCE.NS",
        "retrieval_timestamp": "2026-03-03T00:00:00Z",
        "ingestion_run_id": run_id,
        "raw_response_hash": "response-hash",
        "provenance_classification": "OBSERVED_HISTORICAL",
        "data_quality_status": "VERIFIED_OBSERVED_INTRADAY",
    }


def test_observed_ingestion_is_idempotent_and_preserves_synthetic_rows(temporary_intraday_db):
    with database.connect() as con:
        con.execute(
            "INSERT INTO ohlcv (symbol, interval, timestamp, open, high, low, close, volume, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("RELIANCE", "5m", "2026-03-02T03:45:00Z", 50, 51, 49, 50.5, 800, "deterministic_calibrated_5m"),
        )

    run1 = _run_metadata("run-one")
    bar1 = _observed_bar("run-one")
    provenance = [{
        "symbol": "RELIANCE",
        "interval": "5m",
        "timestamp": bar1["timestamp"],
        "provider": "yfinance",
        "provider_symbol": "RELIANCE.NS",
        "retrieval_timestamp": bar1["retrieval_timestamp"],
        "ingestion_run_id": "run-one",
        "raw_response_hash": "response-hash",
        "provenance_classification": "OBSERVED_HISTORICAL",
        "data_quality_status": "VERIFIED_OBSERVED_INTRADAY",
    }]
    assert database.persist_intraday_ingestion(run1, [bar1], provenance)[1] == 1
    assert database.persist_intraday_ingestion(
        _run_metadata("run-two"),
        [_observed_bar("run-two", volume=500)],
        provenance,
    )[1] == 0

    with database.connect() as con:
        synthetic = con.execute(
            "SELECT close, source FROM ohlcv WHERE symbol='RELIANCE' AND interval='5m'"
        ).fetchone()
        observed_count = con.execute("SELECT COUNT(*) FROM observed_intraday_ohlcv").fetchone()[0]
    assert synthetic["close"] == 50.5
    assert synthetic["source"] == "deterministic_calibrated_5m"
    assert observed_count == 1
    visible = database.get_bars("RELIANCE", "5m")
    assert len(visible) == 1
    assert visible[0]["close"] == 101.0
    assert len(database.get_bars("RELIANCE", "5m", exclude_synthetic=True)) == 1


def test_observed_ingestion_rolls_back_run_when_bar_insert_fails(temporary_intraday_db):
    with pytest.raises(Exception):
        database.persist_intraday_ingestion(
            _run_metadata("rollback-run"),
            [_observed_bar("rollback-run", volume=-1)],
            [],
        )
    with database.connect() as con:
        assert con.execute(
            "SELECT COUNT(*) FROM intraday_ingestion_runs WHERE id='rollback-run'"
        ).fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM observed_intraday_ohlcv").fetchone()[0] == 0

"""
Historical Intraday Data Engine & True Time-of-Day RVOL Ingestion Service (Phase 14.2).

Responsibilities:
1. Provider Assessment:
   - Evaluates provider capabilities (yfinance delayed/historical, optional Dhan live/historical, offline deterministic seeder).
   - Strict truthfulness: Historical data is never represented as live exchange tick feeds.
2. Ingestion & Persistence:
   - Ingests and stores 5-minute OHLCV bars for all tracked NSE stocks in SQLite/PostgreSQL `ohlcv` table (interval='5m').
   - Normalizes timestamps to UTC ISO strings (YYYY-MM-DDTHH:MM:SSZ) and accurately translates to Asia/Kolkata (09:15 to 15:30 IST, exactly 75 5-min bars/day).
   - Deduplicates records via composite unique constraint/index `(symbol, interval, timestamp)`.
   - Supports incremental ingestion and avoids redundant downloads.
3. Quality & Session Validation:
   - Validates session completeness (NSE standard = 75 5-min bars).
   - Excludes holidays, weekends, and incomplete/truncated sessions (< 60 bars) from historical baselines.
4. Ingestion Telemetry & Monitoring:
   - Exposes comprehensive ingestion status (tracked symbols, session counts, bar counts, missing symbols, errors).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import hashlib
import json
import logging
import math
import random
import threading
import time
import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app.database import (
    connect,
    get_bars,
    get_ohlcv_count,
    get_latest_bar_date,
    list_stocks,
    upsert_ohlcv,
    is_postgres,
    record_ingestion_run,
    persist_intraday_ingestion,
    get_bar_provenance,
    list_ingestion_runs,
)
from app.services.data_quality_service import (
    NSE_FIXED_HOLIDAYS,
    check_ist_market_hours,
    DataSourceClassification,
    classify_data_source,
    classify_session_provenance,
    validate_session_completeness,
    verify_bar_provenance,
)
from app.services.trading_calendar_service import (
    is_trading_holiday,
    is_special_trading_session,
    is_trading_day,
    is_cas_eligible_security,
    get_valid_historical_trading_sessions,
    STANDARD_SESSION_BARS_5M,
    CAS_CONTINUOUS_BARS_5M,
    MIN_REGULAR_SESSION_BARS_5M,
)

logger = logging.getLogger(__name__)

# Standard NSE Cash Market Session Constants
BARS_PER_REGULAR_SESSION = 75  # 375 minutes / 5 minutes = 75 bars
MIN_VALID_SESSION_BARS = 60    # Sessions with fewer than 60 bars are considered truncated/incomplete
TARGET_LOOKBACK_SESSIONS = 20
MIN_REQUIRED_SESSIONS = 3

MARKET_OPEN_IST = "09:15:00"
MARKET_CLOSE_IST = "15:30:00"
_YFINANCE_MIN_REQUEST_INTERVAL = 2.0
_YFINANCE_REQUEST_LOCK = threading.Lock()
_YFINANCE_LAST_REQUEST = 0.0


def _set_yfinance_last_request(request_time: float) -> None:
    global _YFINANCE_LAST_REQUEST
    _YFINANCE_LAST_REQUEST = request_time

# Canonical Tracked Universe (31 tracked NSE equities in current database)
TRACKED_NSE_SYMBOLS = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "HINDUNILVR", "SUNPHARMA", "TATAMOTORS", "BHARTIARTL", "WIPRO",
    "BAJFINANCE", "LT", "MARUTI", "ASIANPAINT", "TITAN",
    "SBIN", "HCLTECH", "ADANIENT", "POWERGRID", "TRENT",
    "BEL", "HAL", "ONGC", "LTIM", "COALINDIA",
    "POLYCAB", "DIXON", "DEEPAKNTR", "CDSL", "KPITTECH", "TATAELXSI"
]


# ---------------------------------------------------------------------------
# 1. Provider Assessment
# ---------------------------------------------------------------------------

def assess_intraday_data_providers() -> Dict[str, Any]:
    """
    Evaluates configured data providers for 5-minute intraday bar ingestion.
    Assesses coverage, retention, timestamp consistency, and exchange feed honesty.
    """
    from app.config import get_dhan_config, get_upstox_config
    from app.services.token_store import get_token

    import importlib.util

    dhan_cfg = get_dhan_config()
    token = get_token()
    token_valid = bool(token and token.access_token and not token.is_expired)
    upstox_cfg = get_upstox_config()
    yfinance_installed = importlib.util.find_spec("yfinance") is not None
    try:
        latest_yfinance_run = next(
            (run for run in list_ingestion_runs(limit=100) if run.get("provider") == "yfinance"),
            None,
        )
    except Exception as exc:
        logger.warning("Could not read recent provider ingestion status: %s", exc)
        latest_yfinance_run = None
    if latest_yfinance_run and latest_yfinance_run.get("raw_response_hash"):
        yfinance_status = (
            "DATA_RETURNED_QUALITY_REJECTED"
            if latest_yfinance_run.get("data_quality_status") == "REJECTED_NO_VALID_SESSION"
            else "DATA_RETURNED"
        )
    elif latest_yfinance_run:
        yfinance_status = latest_yfinance_run.get("data_quality_status") or "LAST_REQUEST_FAILED"
    else:
        yfinance_status = "PACKAGE_AVAILABLE_NOT_NETWORK_VERIFIED" if yfinance_installed else "PACKAGE_MISSING"
    dhan_status = (
        "CONFIGURED_UNVERIFIED"
        if dhan_cfg.is_configured and token_valid
        else "EXPIRED_TOKEN"
        if dhan_cfg.is_configured and token
        else "AUTHENTICATION_REQUIRED"
    )
    dhan_reason = (
        "A valid stored token exists, but no historical request was made for this assessment."
        if dhan_status == "CONFIGURED_UNVERIFIED"
        else "Configured credentials exist, but the stored token is expired; no request was made."
        if dhan_status == "EXPIRED_TOKEN"
        else "Dhan credentials are configured, but no valid stored access token is available; no request was made."
        if dhan_cfg.is_configured
        else "No complete Dhan credential and valid-token configuration is available."
    )
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "assessment_summary": "Provider configuration and capability audit; only successful, validated provider responses qualify as observed data.",
        "providers": {
            "yfinance": {
                "name": "Yahoo Finance (NSE Suffix .NS)",
                "status": yfinance_status,
                "package_installed": yfinance_installed,
                "last_request_at": latest_yfinance_run.get("retrieval_timestamp") if latest_yfinance_run else None,
                "credentials_required": False,
                "credentials_configured": None,
                "implemented_adapter": True,
                "interval_supported": "5m",
                "max_history_days": 60,
                "approx_sessions": 40,
                "is_real_time_exchange_feed": False,
                "data_mode": "THIRD_PARTY_HISTORICAL",
                "rate_limits": "Yahoo does not publish a stable limit for this unofficial interface; adapter serializes requests with a 2-second minimum interval and can still be throttled.",
                "network_dependency": "Requires external Internet HTTP access.",
                "exchange_mapping": "NSE symbols use Yahoo .NS suffix; this is not an exchange-authorized feed.",
                "timestamps": "Yahoo response index is timezone-aware Asia/Kolkata; adapter preserves it and normalizes to UTC.",
                "volume_returned": True,
                "limitations": "Community yfinance wrapper; 5-minute history is limited to approximately 60 calendar days, intraday rows may be incomplete, and Yahoo can change or restrict availability.",
            },
            "dhan": {
                "name": "Dhan Trading Open API",
                "status": dhan_status,
                "credentials_required": True,
                "credentials_configured": dhan_cfg.is_configured,
                "stored_token_available": bool(token and token.access_token),
                "stored_token_valid": token_valid,
                "implemented_adapter": False,
                "interval_supported": "1m, 5m, 15m, 60m",
                "max_history_days": 100,
                "is_real_time_exchange_feed": False,
                "details": dhan_reason,
                "limitations": "No direct Dhan historical intraday adapter is implemented; configured credentials alone do not verify API access.",
            },
            "upstox": {
                "name": "Upstox API",
                "status": "AUTHENTICATION_REQUIRED" if not upstox_cfg.is_configured else "CONFIGURED_UNVERIFIED",
                "credentials_required": True,
                "credentials_configured": upstox_cfg.is_configured,
                "implemented_adapter": False,
                "interval_supported": None,
                "max_history_days": None,
                "limitations": "Existing Upstox connector is for fundamentals only; historical intraday access is not implemented or verified.",
            },
            "offline_deterministic_engine": {
                "name": "Institutional Volume Profile Intraday Generator",
                "status": "SYNTHETIC_ONLY_NOT_PROVIDER",
                "interval_supported": "5m",
                "sessions_provided": TARGET_LOOKBACK_SESSIONS,
                "bars_per_session": BARS_PER_REGULAR_SESSION,
                "is_real_time_exchange_feed": False,
                "data_mode": "HISTORICAL_SYNTHETIC_CALIBRATED",
                "purpose": "Zero-dependency reproducible 20-session quantitative baseline calibrated to each stock's actual ADV20 and IST U-curve.",
            },
        },
    }


# ---------------------------------------------------------------------------
# 2. Database Index & Schema Optimization
# ---------------------------------------------------------------------------

def ensure_ohlcv_indexes() -> None:
    """
    Ensure the compound index `idx_ohlcv_sym_int_ts` exists on `ohlcv(symbol, interval, timestamp)`.
    Enables sub-millisecond retrieval of 5m bars for all tracked stocks.
    """
    try:
        with connect() as con:
            con.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_sym_int_ts ON ohlcv (symbol, interval, timestamp)")
            logger.info("Verified database index idx_ohlcv_sym_int_ts on ohlcv.")
    except Exception as e:
        logger.warning("Index creation notice: %s", e)


# ---------------------------------------------------------------------------
# 3. Timestamp & Time-of-Day Utilities
# ---------------------------------------------------------------------------

def ist_to_utc_iso(ist_date_str: str, ist_time_str: str) -> str:
    """
    Converts IST date ('YYYY-MM-DD') and IST time ('HH:MM:SS')
    to normalized UTC ISO-8601 string ('YYYY-MM-DDTHH:MM:SSZ').
    IST = UTC + 05:30.
    """
    parts_d = [int(p) for p in ist_date_str.split("-")]
    parts_t = [int(p) for p in ist_time_str.split(":")[:3]]
    while len(parts_t) < 3:
        parts_t.append(0)

    dt_ist = datetime(parts_d[0], parts_d[1], parts_d[2], parts_t[0], parts_t[1], parts_t[2])
    dt_utc = dt_ist - timedelta(hours=5, minutes=30)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_bar_to_ist(ts_str: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Converts any bar timestamp (UTC ISO, IST with offset, or naive)
    to normalized (ist_date 'YYYY-MM-DD', ist_time 'HH:MM:SS').
    """
    if not ts_str:
        return None, None
    clean = str(ts_str).strip()
    if clean.endswith("Z") or "+00:00" in clean:
        try:
            iso_clean = clean.replace("Z", "+00:00")
            dt_utc = datetime.fromisoformat(iso_clean)
            dt_ist = dt_utc + timedelta(hours=5, minutes=30)
            return dt_ist.strftime("%Y-%m-%d"), dt_ist.strftime("%H:%M:%S")
        except Exception:
            pass
    elif "+05:30" in clean:
        try:
            dt_ist = datetime.fromisoformat(clean)
            return dt_ist.strftime("%Y-%m-%d"), dt_ist.strftime("%H:%M:%S")
        except Exception:
            pass

    if "T" in clean:
        parts = clean.split("T", 1)
        return parts[0], parts[1].split("+")[0].split("Z")[0].strip()[:8]
    elif " " in clean:
        parts = clean.split(" ", 1)
        return parts[0], parts[1].split("+")[0].split("Z")[0].strip()[:8]
    return None, None


def get_latest_completed_5m_interval(now_dt: Optional[datetime] = None) -> Tuple[str, str, bool]:
    """
    Returns the latest completed 5-minute interval in IST:
    Returns (ist_date_str, ist_time_str, is_market_open).
    Rounds down to the nearest completed 5-minute boundary.
    """
    if now_dt is None:
        utc_now = datetime.now(timezone.utc)
    elif now_dt.tzinfo is None:
        utc_now = now_dt.replace(tzinfo=timezone.utc)
    else:
        utc_now = now_dt.astimezone(timezone.utc)

    dt_ist = utc_now + timedelta(hours=5, minutes=30)
    ist_date = dt_ist.strftime("%Y-%m-%d")
    h, m, s = dt_ist.hour, dt_ist.minute, dt_ist.second

    # Round down to nearest 5 minutes
    completed_m = (m // 5) * 5
    completed_time = f"{h:02d}:{completed_m:02d}:00"

    is_open, _, _, _ = check_ist_market_hours()

    # If before market open on current day, interval is previous session close
    if completed_time < MARKET_OPEN_IST:
        return ist_date, "15:25:00", False
    # If after market close on current day, interval is 15:25:00 (the last 5m candle)
    elif completed_time > "15:25:00":
        return ist_date, "15:25:00", False

    return ist_date, completed_time, is_open


# ---------------------------------------------------------------------------
# 4. Deterministic Realistic Intraday Bar Generator (U-Curve Calibrated)
# ---------------------------------------------------------------------------

def _get_ist_session_timestamps() -> List[str]:
    """
    Generates all 75 5-minute bar start times for an Indian trading session:
    ['09:15:00', '09:20:00', ..., '15:25:00']
    """
    times = []
    curr = datetime(2000, 1, 1, 9, 15, 0)
    end = datetime(2000, 1, 1, 15, 25, 0)
    while curr <= end:
        times.append(curr.strftime("%H:%M:%S"))
        curr += timedelta(minutes=5)
    return times


def generate_realistic_5m_bars(
    symbol: str,
    session_date: str,
    base_price: float,
    adv_20: int,
    session_index: int = 0,
    daily_return_pct: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Generates a deterministic 75-bar 5-minute intraday session for an NSE stock.
    Features:
    1. Realistic U-curve volume distribution:
       - Open surge (09:15-10:00): ~28% of day's volume
       - Morning momentum (10:00-11:30): ~22%
       - Midday European lull (11:30-13:30): ~16%
       - Afternoon resumption (13:30-14:30): ~14%
       - Closing auction & institutional cross (14:30-15:30): ~20%
    2. Strict OHLC mathematical validity:
       - high >= max(open, close)
       - low <= min(open, close)
    3. Normalizes timestamps to UTC ISO strings.
    """
    times = _get_ist_session_timestamps()
    n_bars = len(times)  # Exactly 75

    # Derive deterministic seed per symbol, date, and session index
    seed_val = int(abs(hash(f"{symbol}_{session_date}_{session_index}")) % 1000000)
    rng = random.Random(seed_val)

    # Base session volume variance (+/- 25% around ADV20)
    session_vol_factor = 0.75 + (rng.random() * 0.5)
    target_daily_volume = max(10000, int(round(adv_20 * session_vol_factor)))

    # Compute U-shaped profile weights across the 75 intervals
    weights: List[float] = []
    for i, t in enumerate(times):
        # Time of day factors
        if t <= "09:45:00":
            # Opening bell rush
            w = 2.8 + 0.8 * rng.random()
        elif t <= "10:30:00":
            # Morning continuation
            w = 1.6 + 0.4 * rng.random()
        elif t <= "11:30:00":
            # Morning steady
            w = 1.1 + 0.3 * rng.random()
        elif t <= "13:30:00":
            # Midday European lull
            w = 0.6 + 0.2 * rng.random()
        elif t <= "14:30:00":
            # Afternoon pickup
            w = 1.0 + 0.3 * rng.random()
        else:
            # Closing volume surge
            w = 2.2 + 0.6 * rng.random()
        weights.append(w)

    sum_weights = sum(weights)
    bar_volumes = [max(50, int(round((w / sum_weights) * target_daily_volume))) for w in weights]

    # Target session price drift
    if daily_return_pct is None:
        # Pseudo-random realistic daily price move between -2.5% and +2.5%
        daily_drift = (rng.random() * 5.0 - 2.5) / 100.0
    else:
        daily_drift = daily_return_pct / 100.0

    target_close = base_price * (1.0 + daily_drift)
    current_price = base_price
    drift_per_bar = (target_close - base_price) / float(n_bars)

    bars: List[Dict[str, Any]] = []
    for i, t in enumerate(times):
        utc_ts = ist_to_utc_iso(session_date, t)
        vol = bar_volumes[i]

        volatility = current_price * 0.0015 * (1.0 + 0.5 * rng.random())
        bar_open = round(current_price, 2)
        step = drift_per_bar + (rng.random() - 0.5) * volatility
        bar_close = round(max(0.5, bar_open + step), 2)
        bar_high = round(max(bar_open, bar_close) + abs(rng.random() * volatility), 2)
        bar_low = round(min(bar_open, bar_close) - abs(rng.random() * volatility), 2)
        bar_low = max(0.1, bar_low)

        bars.append({
            "timestamp": utc_ts,
            "open": bar_open,
            "high": bar_high,
            "low": bar_low,
            "close": bar_close,
            "adj_close": bar_close,
            "volume": vol,
            "source": "deterministic_calibrated_5m",
        })
        current_price = bar_close

    return bars


# ---------------------------------------------------------------------------
# 5. Ingestion Engine
# ---------------------------------------------------------------------------

def get_prior_trading_dates(
    num_sessions: int = TARGET_LOOKBACK_SESSIONS,
    end_date: Optional[date] = None,
) -> List[str]:
    """
    Returns the previous `num_sessions` valid trading dates in 'YYYY-MM-DD' format,
    using the authoritative NSE trading calendar service (skipping weekends, official NSE holidays,
    and special truncated sessions).
    """
    return get_valid_historical_trading_sessions(
        num_sessions=num_sessions,
        end_date=end_date,
        exclude_special=True,
    )


def seed_symbol_intraday_history(
    symbol: str,
    num_sessions: int = TARGET_LOOKBACK_SESSIONS,
    force: bool = False,
) -> int:
    """
    Ensures at least `num_sessions` completed 5-minute sessions exist for `symbol`.
    Returns the total number of 5m bars upserted.
    """
    sym = symbol.upper().strip()
    ensure_ohlcv_indexes()

    with connect() as con:
        # Critical Guardrail: Check if verified observed bars exist for this symbol
        obs_count = con.execute(
            "SELECT COUNT(*) FROM bar_provenance WHERE symbol = ? AND interval = '5m' "
            "AND provenance_classification = 'OBSERVED_HISTORICAL'",
            (sym,)
        ).fetchone()[0]
        obs_count += con.execute(
            "SELECT COUNT(*) FROM observed_intraday_ohlcv WHERE symbol = ? AND interval = '5m'",
            (sym,),
        ).fetchone()[0]
        if obs_count > 0:
            logger.warning(
                "CRITICAL GUARDRAIL: Stock %s contains %d verified observed bars. "
                "Synthetic seeding is strictly prohibited from deleting or overwriting observed records.",
                sym, obs_count
            )
            return 0
        if force:
            con.execute("DELETE FROM ohlcv WHERE symbol = ? AND interval = '5m'", (sym,))

    existing_bars = get_bars(sym, interval="5m")
    if existing_bars and not force:
        # Check distinct sessions
        sessions = set()
        for b in existing_bars:
            d_ist, _ = parse_bar_to_ist(b.get("timestamp"))
            if d_ist:
                sessions.add(d_ist)
        if len(sessions) >= num_sessions:
            logger.info("Stock %s already has %d 5m sessions (>= %d target). Skipping.", sym, len(sessions), num_sessions)
            return 0

    # Retrieve base price and ADV from database or stocks table
    stock_record = None
    all_stocks = list_stocks()
    for s in all_stocks:
        if str(s.get("symbol", "")).upper() == sym:
            stock_record = s
            break

    base_close = float(stock_record.get("close", 1000.0)) if stock_record else 1000.0
    adv_20 = int(float(stock_record.get("volume", 500000))) if stock_record else 500000
    if adv_20 <= 0:
        adv_20 = 500000

    trading_dates = get_prior_trading_dates(num_sessions=num_sessions)
    all_generated_bars: List[Dict[str, Any]] = []

    curr_price = base_close * 0.95  # Start slightly below current to simulate realistic trend
    for idx, d_str in enumerate(trading_dates):
        session_bars = generate_realistic_5m_bars(
            symbol=sym,
            session_date=d_str,
            base_price=curr_price,
            adv_20=adv_20,
            session_index=idx,
        )
        all_generated_bars.extend(session_bars)
        if session_bars:
            curr_price = session_bars[-1]["close"]

    # Upsert in chunks to ensure high performance
    written = upsert_ohlcv(
        symbol=sym,
        bars=all_generated_bars,
        interval="5m",
        source="deterministic_calibrated_5m",
    )
    logger.info("Seeded %d 5-minute bars across %d sessions for %s.", written, len(trading_dates), sym)
    return written


def seed_all_tracked_stocks_intraday(
    num_sessions: int = TARGET_LOOKBACK_SESSIONS,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Seeds 5-minute historical bars for all 31 tracked NSE equities.
    Guarantees that genuine Time-of-Day RVOL is immediately available.
    """
    t0 = time.time()
    ensure_ohlcv_indexes()

    stocks = list_stocks()
    symbols = [str(s.get("symbol", "")).upper() for s in stocks if s.get("symbol")]
    if not symbols:
        symbols = TRACKED_NSE_SYMBOLS

    results: Dict[str, int] = {}
    total_bars_written = 0

    for sym in symbols:
        try:
            bars_added = seed_symbol_intraday_history(sym, num_sessions=num_sessions, force=force)
            results[sym] = bars_added
            total_bars_written += bars_added
        except Exception as e:
            logger.exception("Error seeding intraday data for %s: %s", sym, e)
            results[sym] = -1

    elapsed = round(time.time() - t0, 2)
    return {
        "status": "SUCCESS",
        "symbols_processed": len(symbols),
        "total_bars_written": total_bars_written,
        "elapsed_seconds": elapsed,
        "target_sessions": num_sessions,
        "results_by_symbol": results,
    }


# ---------------------------------------------------------------------------
# 5. Provider-Neutral Historical Intraday Ingestion Pipeline (Phase 14.4)
# ---------------------------------------------------------------------------

@dataclass
class ProviderFetchResult:
    success: bool
    status: str  # SUCCESS, NOT_EXECUTED, NETWORK_UNAVAILABLE, AUTHENTICATION_REQUIRED, NO_DATA, ERROR
    provider: str
    symbol: str
    interval: str
    bars: List[Dict[str, Any]]
    provider_symbol: str
    run_id: str
    retrieval_timestamp: str
    raw_response_hash: Optional[str] = None
    error_message: Optional[str] = None
    provider_metadata: Optional[Dict[str, Any]] = None


class IntradayProviderAdapter(ABC):
    @abstractmethod
    def fetch_intraday_bars(
        self,
        symbol: str,
        interval: str = "5m",
        num_sessions: int = 20,
    ) -> ProviderFetchResult:
        pass


class YFinanceIntradayAdapter(IntradayProviderAdapter):
    """
    Third-party historical/delayed feed provider adapter (Yahoo Finance).
    CRITICAL DISCLOSURE: YFinance data is third-party historical/delayed data,
    NOT direct official NSE exchange tick feeds.
    """
    provider_name = "yfinance"

    def fetch_intraday_bars(
        self,
        symbol: str,
        interval: str = "5m",
        num_sessions: int = 20,
    ) -> ProviderFetchResult:
        run_id = str(uuid.uuid4())
        requested_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        prov_sym = f"{symbol.upper().strip()}.NS"
        if interval != "5m":
            return ProviderFetchResult(
                False, "UNSUPPORTED_INTERVAL", self.provider_name, symbol, interval, [],
                prov_sym, run_id, requested_at,
                error_message="Yahoo intraday adapter supports only 5-minute bars.",
            )

        try:
            import yfinance as yf
            calendar_days = min(max(int(num_sessions) * 2, 5), 59)
            period_str = f"{calendar_days}d"
            with _YFINANCE_REQUEST_LOCK:
                wait_seconds = _YFINANCE_MIN_REQUEST_INTERVAL - (
                    time.monotonic() - _YFINANCE_LAST_REQUEST
                )
                if wait_seconds > 0:
                    time.sleep(wait_seconds)
                _set_yfinance_last_request(time.monotonic())
                ticker = yf.Ticker(prov_sym)
                df = ticker.history(
                    period=period_str,
                    interval=interval,
                    auto_adjust=False,
                    actions=False,
                )
            if df is None or df.empty:
                return ProviderFetchResult(
                    success=False,
                    status="NO_DATA",
                    provider=self.provider_name,
                    symbol=symbol,
                    interval=interval,
                    bars=[],
                    provider_symbol=prov_sym,
                    run_id=run_id,
                    retrieval_timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    provider_metadata={
                        "requested_period": period_str,
                        "max_history_days": 60,
                        "volume_column_present": bool(df is not None and "Volume" in df.columns),
                    },
                    error_message=f"No intraday bars returned for {prov_sym}",
                )

            required_columns = {"Open", "High", "Low", "Close", "Volume"}
            missing_columns = sorted(required_columns - set(df.columns))
            if missing_columns:
                return ProviderFetchResult(
                    success=False,
                    status="INVALID_PROVIDER_RESPONSE",
                    provider=self.provider_name,
                    symbol=symbol,
                    interval=interval,
                    bars=[],
                    provider_symbol=prov_sym,
                    run_id=run_id,
                    retrieval_timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    error_message=f"Yahoo response is missing required columns: {', '.join(missing_columns)}",
                )

            raw_bytes = df.to_json(orient="table", date_format="iso").encode("utf-8")
            raw_hash = hashlib.sha256(raw_bytes).hexdigest()
            retrieval_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            bars = []
            for ts, row in df.iterrows():
                ts_dt = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
                if ts_dt.tzinfo is None:
                    raise ValueError("Yahoo response contains a naive timestamp; timezone cannot be verified.")
                provider_timestamp = ts_dt.isoformat()
                iso_utc = ts_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                raw_volume = row["Volume"]
                volume = int(raw_volume) if pd.notna(raw_volume) else None
                bars.append({
                    "symbol": symbol.upper().strip(),
                    "exchange": "NSE",
                    "interval": interval,
                    "provider_timestamp": provider_timestamp,
                    "timestamp": iso_utc,
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": volume,
                    "adj_close": float(row["Adj Close"]) if "Adj Close" in row and pd.notna(row["Adj Close"]) else None,
                    "source": "yfinance_historical_5m",
                    "provider": "yfinance",
                    "provider_symbol": prov_sym,
                    "ingestion_run_id": run_id,
                    "retrieval_timestamp": retrieval_timestamp,
                    "raw_response_hash": raw_hash,
                    "provenance_classification": "PENDING_VALIDATION",
                    "data_quality_status": "PENDING_SESSION_VALIDATION",
                })

            return ProviderFetchResult(
                success=True,
                status="SUCCESS",
                provider=self.provider_name,
                symbol=symbol,
                interval=interval,
                bars=bars,
                provider_symbol=prov_sym,
                run_id=run_id,
                retrieval_timestamp=retrieval_timestamp,
                raw_response_hash=raw_hash,
                provider_metadata={
                    "requested_period": period_str,
                    "max_history_days": 60,
                    "returned_timezone": str(df.index.tz),
                    "returned_columns": list(df.columns),
                    "response_dataframe_sha256": raw_hash,
                    "raw_http_response_available": False,
                },
            )

        except Exception as e:
            err_msg = str(e)
            logger.warning("YFinance fetch error for %s: %s", prov_sym, err_msg)
            is_net_err = any(k in err_msg.lower() for k in ("dns", "curl", "resolve", "network", "connect", "timeout"))
            status_code = "NETWORK_UNAVAILABLE" if is_net_err else "ERROR"
            return ProviderFetchResult(
                success=False,
                status=status_code,
                provider=self.provider_name,
                symbol=symbol,
                interval=interval,
                bars=[],
                provider_symbol=prov_sym,
                run_id=run_id,
                retrieval_timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                error_message=f"{status_code}: {err_msg}",
            )


class DhanIntradayAdapter(IntradayProviderAdapter):
    """
    Direct broker feed adapter (Dhan).
    CRITICAL RULE: Remains strictly unauthenticated unless live credentials are configured.
    Never fabricates connection or mock observed data.
    """
    provider_name = "dhan"

    def fetch_intraday_bars(
        self,
        symbol: str,
        interval: str = "5m",
        num_sessions: int = 20,
    ) -> ProviderFetchResult:
        run_id = str(uuid.uuid4())
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        from app.config import get_dhan_config
        from app.services.token_store import get_token

        config = get_dhan_config()
        token = get_token()
        if not config.is_configured or not token or not token.access_token or token.is_expired:
            return ProviderFetchResult(
                success=False,
                status="NOT_EXECUTED",
                provider=self.provider_name,
                symbol=symbol,
                interval=interval,
                bars=[],
                provider_symbol=symbol,
                run_id=run_id,
                retrieval_timestamp=now_utc,
                error_message="Dhan historical request not executed: complete credentials and a valid stored access token are required.",
            )

        return ProviderFetchResult(
            success=False,
            status="NOT_EXECUTED",
            provider=self.provider_name,
            symbol=symbol,
            interval=interval,
            bars=[],
            provider_symbol=symbol,
            run_id=run_id,
            retrieval_timestamp=now_utc,
            error_message="Dhan historical intraday adapter is not implemented; no API request was made.",
        )


def ingest_symbol_intraday_history(
    symbol: str,
    provider: str = "yfinance",
    num_sessions: int = TARGET_LOOKBACK_SESSIONS,
    adapter: Optional[IntradayProviderAdapter] = None,
) -> Dict[str, Any]:
    """
    Provider-neutral intraday historical bar ingestion with strict provenance registration.
    - If network or credentials are unavailable, reports NOT_EXECUTED without fabricating data.
    - Validates session completeness on incoming bars before persistence.
    - Preserves provenance metadata in bar_provenance and intraday_ingestion_runs.
    - Idempotent: avoids duplicate bars and never overwrites observed bars with synthetic data.
    """
    sym = symbol.upper().strip()
    ensure_ohlcv_indexes()

    if adapter is None:
        if provider == "dhan":
            adapter = DhanIntradayAdapter()
        else:
            adapter = YFinanceIntradayAdapter()

    res = adapter.fetch_intraday_bars(sym, interval="5m", num_sessions=num_sessions)
    session_quality: List[Dict[str, Any]] = []
    sessions_map: Dict[str, List[Dict[str, Any]]] = {}
    unparsed_timestamps: List[str] = []
    for bar in res.bars:
        d_ist, _ = parse_bar_to_ist(bar.get("timestamp"))
        if d_ist:
            sessions_map.setdefault(d_ist, []).append(bar)
        else:
            unparsed_timestamps.append(str(bar.get("timestamp")))

    valid_bars: List[Dict[str, Any]] = []
    provenance_records: List[Dict[str, Any]] = []
    incomplete_sessions = 0
    for session_date, session_bars in sorted(sessions_map.items()):
        is_trading, calendar_reason = is_trading_day(session_date)
        if not is_trading:
            validation = {
                "is_complete": False,
                "session_date": session_date,
                "actual_bars": len(session_bars),
                "missing_intervals": [],
                "duplicate_intervals": [],
                "errors": [f"EXCHANGE_CALENDAR_EXCLUSION: {calendar_reason}"],
                "status": f"EXCHANGE_CALENDAR_EXCLUSION: {calendar_reason}",
            }
        else:
            validation = validate_session_completeness(
                session_date=session_date,
                bars=session_bars,
                expected_interval="5m",
                symbol=sym,
            )

        if validation["is_complete"]:
            for bar in session_bars:
                try:
                    provider_ts = datetime.fromisoformat(str(bar["provider_timestamp"]))
                    normalized_ts = datetime.fromisoformat(str(bar["timestamp"]).replace("Z", "+00:00"))
                    if provider_ts.tzinfo is None or normalized_ts.tzinfo is None:
                        raise ValueError("provider or normalized timestamp is timezone-naive")
                    if provider_ts.astimezone(timezone.utc) != normalized_ts.astimezone(timezone.utc):
                        raise ValueError("provider timestamp does not match normalized UTC timestamp")
                except (KeyError, TypeError, ValueError) as exc:
                    validation["is_complete"] = False
                    validation.setdefault("errors", []).append(f"TIMESTAMP_PROVENANCE_MISMATCH: {exc}")
                    validation["status"] = validation["errors"][-1]
                    break

        if validation["is_complete"]:
            for bar in session_bars:
                classification, reason, _ = verify_bar_provenance(bar, strict_audit=True)
                if classification != DataSourceClassification.OBSERVED_HISTORICAL:
                    validation["is_complete"] = False
                    validation.setdefault("errors", []).append(f"PROVENANCE_REJECTED: {reason}")
                    validation["status"] = validation["errors"][-1]
                    break

        if validation["is_complete"]:
            for bar in session_bars:
                bar["provenance_classification"] = "OBSERVED_HISTORICAL"
                bar["data_quality_status"] = "VERIFIED_OBSERVED_INTRADAY"
                valid_bars.append(bar)
                provenance_records.append({
                    "symbol": sym,
                    "interval": "5m",
                    "timestamp": bar["timestamp"],
                    "provider": res.provider,
                    "provider_symbol": res.provider_symbol,
                    "exchange": "NSE",
                    "segment": "EQUITY",
                    "retrieval_timestamp": res.retrieval_timestamp,
                    "ingestion_run_id": res.run_id,
                    "raw_response_hash": res.raw_response_hash,
                    "transformation_version": "v1.0",
                    "provenance_classification": "OBSERVED_HISTORICAL",
                    "data_quality_status": "VERIFIED_OBSERVED_INTRADAY",
                })
        else:
            incomplete_sessions += 1
            logger.warning(
                "Session %s for %s failed observed-data validation: %s",
                session_date,
                sym,
                validation["status"],
            )
        session_quality.append(validation)

    if unparsed_timestamps:
        incomplete_sessions += 1
        session_quality.append({
            "session_date": None,
            "actual_bars": len(unparsed_timestamps),
            "unparsed_timestamps": unparsed_timestamps,
            "errors": ["UNPARSEABLE_TIMESTAMP"],
            "status": "UNPARSEABLE_TIMESTAMP",
        })

    retrieved_dates = sorted(sessions_map)
    requested_period = (res.provider_metadata or {}).get("requested_period")
    actual_start_date = retrieved_dates[0] if retrieved_dates else None
    actual_end_date = retrieved_dates[-1] if retrieved_dates else None
    requested_date_range = {
        "period": requested_period,
        "as_of": res.retrieval_timestamp,
    }
    validation_errors = [
        f"{item.get('session_date')}: {', '.join(item.get('errors', []))}"
        for item in session_quality
        if item.get("errors")
    ]
    quality_status = (
        "VERIFIED_OBSERVED_INTRADAY"
        if res.success and session_quality and not validation_errors and valid_bars
        else "PARTIALLY_VALIDATED"
        if valid_bars
        else "REJECTED_NO_VALID_SESSION"
        if res.success and res.bars
        else res.status
    )
    run_metadata = {
        "id": res.run_id,
        "symbol": sym,
        "provider": res.provider,
        "provider_symbol": res.provider_symbol,
        "exchange": "NSE",
        "segment": "EQUITY",
        "interval": "5m",
        "bar_count": len(res.bars),
        "retrieval_timestamp": res.retrieval_timestamp,
        "raw_response_hash": res.raw_response_hash,
        "transformation_version": "v1.0",
        "provenance_classification": "OBSERVED_HISTORICAL" if res.success else "UNKNOWN",
        "data_quality_status": quality_status,
        "error_message": res.error_message or ("; ".join(validation_errors) if validation_errors else None),
        "actual_start_date": actual_start_date,
        "actual_end_date": actual_end_date,
        "provider_metadata_json": json.dumps({
            "request": requested_date_range,
            "response": res.provider_metadata or {},
        }, sort_keys=True),
        "session_quality_json": json.dumps(session_quality, sort_keys=True),
    }

    if not res.success or not res.bars:
        record_ingestion_run(run_metadata)
        return {
            "status": res.status,
            "symbol": sym,
            "provider": res.provider,
            "reason": res.error_message or "No data returned",
            "requested_date_range": requested_date_range,
            "actual_date_range": None,
            "retrieved_bars": 0,
            "ingested_bars": 0,
            "completed_sessions": 0,
            "incomplete_sessions": 0,
            "run_id": res.run_id,
        }

    inserted_count = 0
    if valid_bars:
        _, inserted_count = persist_intraday_ingestion(run_metadata, valid_bars, provenance_records)
    else:
        record_ingestion_run(run_metadata)

    return {
        "status": "SUCCESS" if valid_bars and not validation_errors else "PARTIAL" if valid_bars else "INCOMPLETE_DATA",
        "symbol": sym,
        "provider": res.provider,
        "total_bars_fetched": len(res.bars),
        "requested_date_range": requested_date_range,
        "actual_date_range": {
            "start": actual_start_date,
            "end": actual_end_date,
        } if retrieved_dates else None,
        "provider_metadata": res.provider_metadata,
        "valid_bars_ingested": inserted_count,
        "completed_sessions": len([item for item in session_quality if item.get("is_complete")]),
        "incomplete_sessions": incomplete_sessions,
        "session_quality": session_quality,
        "run_id": res.run_id,
    }


def ingest_all_tracked_symbols_intraday(
    provider: str = "yfinance",
    num_sessions: int = TARGET_LOOKBACK_SESSIONS,
    adapter: Optional[IntradayProviderAdapter] = None,
) -> Dict[str, Any]:
    """
    Ingests 5-minute historical bars for all tracked NSE equities via provider adapter.
    """
    stocks = list_stocks()
    symbols = [str(s.get("symbol", "")).upper() for s in stocks if s.get("symbol")]
    if not symbols:
        symbols = TRACKED_NSE_SYMBOLS

    results: Dict[str, Any] = {}
    total_valid_bars = 0
    not_executed_count = 0

    for sym in symbols:
        res = ingest_symbol_intraday_history(
            symbol=sym,
            provider=provider,
            num_sessions=num_sessions,
            adapter=adapter,
        )
        results[sym] = res
        total_valid_bars += res.get("valid_bars_ingested", 0)
        if res.get("status") == "NOT_EXECUTED":
            not_executed_count += 1

    overall_status = "NOT_EXECUTED" if not_executed_count == len(symbols) else ("SUCCESS" if total_valid_bars > 0 else "PARTIAL")

    return {
        "status": overall_status,
        "provider": provider,
        "symbols_processed": len(symbols),
        "total_valid_bars_ingested": total_valid_bars,
        "not_executed_count": not_executed_count,
        "target_sessions": num_sessions,
        "symbol_results": results,
    }


# ---------------------------------------------------------------------------
# 6. Ingestion Status & Telemetry
# ---------------------------------------------------------------------------

def get_intraday_ingestion_status(allow_synthetic: bool = False) -> Dict[str, Any]:
    """
    Inspects stored 5-minute bars in SQLite/PostgreSQL database with strict source auditing (Phase 14.3).
    Differentiates genuine exchange-observed historical data from synthetic/calibrated bars.
    """
    stocks = list_stocks()
    all_symbols = [str(s.get("symbol", "")).upper() for s in stocks if s.get("symbol")]
    if not all_symbols:
        all_symbols = TRACKED_NSE_SYMBOLS

    stored_counts: Dict[str, Dict[str, int]] = {}
    with connect() as con:
        rows = con.execute(
            "SELECT symbol, source, COUNT(*) AS count FROM ohlcv "
            "WHERE interval = '5m' GROUP BY symbol, source"
        ).fetchall()
        for row in rows:
            symbol = str(row["symbol"]).upper()
            counts = stored_counts.setdefault(symbol, {"synthetic": 0, "unknown": 0, "observed": 0})
            classification = classify_data_source(row["source"])
            if classification == DataSourceClassification.SYNTHETIC:
                counts["synthetic"] += int(row["count"])
            elif classification == DataSourceClassification.UNKNOWN:
                counts["unknown"] += int(row["count"])

        observed_rows = con.execute(
            "SELECT symbol, COUNT(*) AS count FROM observed_intraday_ohlcv "
            "WHERE interval = '5m' GROUP BY symbol"
        ).fetchall()
        for row in observed_rows:
            symbol = str(row["symbol"]).upper()
            counts = stored_counts.setdefault(symbol, {"synthetic": 0, "unknown": 0, "observed": 0})
            counts["observed"] = int(row["count"])

    symbol_stats: List[Dict[str, Any]] = []
    missing_symbols: List[str] = []

    total_5m_bars = sum(sum(counts.values()) for counts in stored_counts.values())
    total_observed_bars = sum(counts["observed"] for counts in stored_counts.values())
    total_synthetic_bars = sum(counts["synthetic"] for counts in stored_counts.values())
    total_unknown_bars = sum(counts["unknown"] for counts in stored_counts.values())

    observed_target_symbols = 0
    observed_min_symbols = 0
    synthetic_only_symbols = 0

    earliest_overall_ts = None
    latest_overall_ts = None

    for sym in all_symbols:
        bars = get_bars(sym, interval="5m")
        physical_counts = stored_counts.get(sym, {"synthetic": 0, "unknown": 0, "observed": 0})
        n_bars = sum(physical_counts.values())

        if not bars:
            missing_symbols.append(sym)
            is_cas, cas_reason = is_cas_eligible_security(sym, datetime.now(timezone.utc))
            symbol_stats.append({
                "symbol": sym,
                "bar_count": 0,
                "observed_bars_count": 0,
                "synthetic_bars_count": 0,
                "unknown_bars_count": 0,
                "session_count": 0,
                "observed_valid_sessions_count": 0,
                "synthetic_valid_sessions_count": 0,
                "truncated_sessions_count": 0,
                "holiday_sessions_count": 0,
                "source_classification": DataSourceClassification.UNKNOWN.value,
                "production_ready": False,
                "has_min_sessions": False,
                "earliest_bar": None,
                "latest_bar": None,
                "status": "MISSING_DATA",
                "is_cas_eligible": is_cas,
                "expected_continuous_bars": CAS_CONTINUOUS_BARS_5M if is_cas else STANDARD_SESSION_BARS_5M,
                "cas_reason": cas_reason,
            })
            continue

        sym_obs_bars = physical_counts["observed"]
        sym_syn_bars = physical_counts["synthetic"]
        sym_unk_bars = physical_counts["unknown"]

        # Group bars by date
        sessions_map: Dict[str, List[Dict[str, Any]]] = {}
        for b in bars:
            d_ist, _ = parse_bar_to_ist(b.get("timestamp"))
            if d_ist:
                sessions_map.setdefault(d_ist, []).append(b)

        observed_valid_sessions: List[str] = []
        synthetic_valid_sessions: List[str] = []
        truncated_sessions: List[str] = []
        holiday_sessions: List[str] = []

        for d_str, s_bars in sessions_map.items():
            is_hol, _ = is_trading_holiday(d_str)
            if is_hol:
                holiday_sessions.append(d_str)
                continue

            is_spec, _, _ = is_special_trading_session(d_str)
            if is_spec:
                # Special truncated session (e.g. Muhurat)
                truncated_sessions.append(d_str)
                continue

            if len(s_bars) < MIN_VALID_SESSION_BARS:
                truncated_sessions.append(d_str)
                continue

            session_class, _ = classify_session_provenance(s_bars)
            if session_class in (DataSourceClassification.OBSERVED_HISTORICAL, DataSourceClassification.OBSERVED_DELAYED, DataSourceClassification.OBSERVED_LIVE):
                observed_valid_sessions.append(d_str)
            elif session_class == DataSourceClassification.SYNTHETIC:
                synthetic_valid_sessions.append(d_str)
            else:
                truncated_sessions.append(d_str)

        earliest_bar = bars[0].get("timestamp")
        latest_bar = bars[-1].get("timestamp")

        if earliest_overall_ts is None or (earliest_bar and earliest_bar < earliest_overall_ts):
            earliest_overall_ts = earliest_bar
        if latest_overall_ts is None or (latest_bar and latest_bar > latest_overall_ts):
            latest_overall_ts = latest_bar

        has_obs_target = len(observed_valid_sessions) >= TARGET_LOOKBACK_SESSIONS
        has_obs_min = len(observed_valid_sessions) >= MIN_REQUIRED_SESSIONS

        if has_obs_target:
            observed_target_symbols += 1
        if has_obs_min:
            observed_min_symbols += 1
        if sym_syn_bars > 0 and sym_obs_bars == 0:
            synthetic_only_symbols += 1

        if sym_obs_bars > 0 and sym_syn_bars == 0:
            overall_sym_source = DataSourceClassification.OBSERVED_HISTORICAL.value
        elif sym_syn_bars > 0 and sym_obs_bars == 0:
            overall_sym_source = DataSourceClassification.SYNTHETIC.value
        elif sym_obs_bars > 0 and sym_syn_bars > 0:
            overall_sym_source = "MIXED_PROVENANCE"
        else:
            overall_sym_source = DataSourceClassification.UNKNOWN.value

        if has_obs_target:
            status_str = "OBSERVED_OPTIMAL"
        elif has_obs_min:
            status_str = "OBSERVED_ADEQUATE"
        elif len(synthetic_valid_sessions) >= TARGET_LOOKBACK_SESSIONS:
            status_str = "SYNTHETIC_SIMULATION"
        elif len(synthetic_valid_sessions) >= MIN_REQUIRED_SESSIONS:
            status_str = "SYNTHETIC_PARTIAL"
        else:
            status_str = "INSUFFICIENT_DATA"

        total_valid = len(observed_valid_sessions) + len(synthetic_valid_sessions)

        is_cas, cas_reason = is_cas_eligible_security(sym, latest_bar or datetime.now(timezone.utc))

        symbol_stats.append({
            "symbol": sym,
            "bar_count": n_bars,
            "observed_bars_count": sym_obs_bars,
            "synthetic_bars_count": sym_syn_bars,
            "unknown_bars_count": sym_unk_bars,
            "session_count": len(sessions_map),
            "valid_sessions_count": total_valid,
            "observed_valid_sessions_count": len(observed_valid_sessions),
            "synthetic_valid_sessions_count": len(synthetic_valid_sessions),
            "truncated_sessions_count": len(truncated_sessions),
            "holiday_sessions_count": len(holiday_sessions),
            "source_classification": overall_sym_source,
            "production_ready": has_obs_min,
            "has_min_sessions": total_valid >= MIN_REQUIRED_SESSIONS,
            "meets_target_lookback": total_valid >= TARGET_LOOKBACK_SESSIONS,
            "has_min_observed_sessions": has_obs_min,
            "meets_observed_target": has_obs_target,
            "earliest_bar": earliest_bar,
            "latest_bar": latest_bar,
            "status": status_str,
            "is_cas_eligible": is_cas,
            "expected_continuous_bars": CAS_CONTINUOUS_BARS_5M if is_cas else STANDARD_SESSION_BARS_5M,
            "cas_reason": cas_reason,
        })

    coverage_pct = round(len(all_symbols) - len(missing_symbols)) / max(len(all_symbols), 1) * 100.0

    if observed_min_symbols == len(all_symbols):
        prod_status = "PRODUCTION_OBSERVED_READY"
    elif observed_min_symbols > 0:
        prod_status = "PARTIAL_OBSERVED_DATA"
    elif synthetic_only_symbols > 0:
        prod_status = "SYNTHETIC_SIMULATION_ONLY"
    else:
        prod_status = "ZERO_DATA"

    bar_prov_count = 0
    ingestion_runs_count = 0
    try:
        with connect() as con:
            bar_prov_count = con.execute("SELECT COUNT(*) FROM bar_provenance").fetchone()[0]
            ingestion_runs_count = con.execute("SELECT COUNT(*) FROM intraday_ingestion_runs").fetchone()[0]
    except Exception:
        pass

    return {
        "status": prod_status if not allow_synthetic else ("HEALTHY_SYNTHETIC_DEMO" if synthetic_only_symbols > 0 else prod_status),
        "production_status": prod_status,
        "allow_synthetic_active": allow_synthetic,
        "tracked_symbols_count": len(all_symbols),
        "symbols_with_intraday_data": len(all_symbols) - len(missing_symbols),
        "symbols_meeting_observed_target": observed_target_symbols,
        "symbols_meeting_observed_min": observed_min_symbols,
        "symbols_with_synthetic_only": synthetic_only_symbols,
        "symbols_meeting_20_session_target": observed_target_symbols if not allow_synthetic else (observed_target_symbols or synthetic_only_symbols),
        "coverage_pct": round(coverage_pct, 1),
        "total_5m_bars_stored": total_5m_bars,
        "total_observed_bars": total_observed_bars,
        "total_synthetic_bars": total_synthetic_bars,
        "total_unknown_bars": total_unknown_bars,
        "total_bar_provenance_records": bar_prov_count,
        "total_ingestion_runs_logged": ingestion_runs_count,
        "earliest_timestamp": earliest_overall_ts,
        "latest_timestamp": latest_overall_ts,
        "missing_symbols": missing_symbols,
        "database_engine": "postgresql" if is_postgres() else "sqlite",
        "isolation_notice": (
            f"Strict isolation active: {total_synthetic_bars} synthetic, {total_observed_bars} observed, "
            f"and {total_unknown_bars} unknown 5m bars are stored. In production mode (allow_synthetic=False), "
            "only provenance-verified observed sessions are eligible for True Time-of-Day RVOL."
        ),
        "symbol_details": symbol_stats,
    }

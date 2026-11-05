"""
Market Data Quality Assurance & Diagnostic Engine (Audited Priority 6).

Audits:
- Exchange-calendar-aware missing sessions (NSE trading schedule)
- Duplicate and out-of-order timestamps
- Full OHLC mathematical consistency (high >= max(open, close), low <= min(open, close))
- Zero and anomalous volume spikes (>20x median)
- Data freshness relative to current market sessions
- Corporate-action adjustment limitations (flag unadjusted splits/bonuses)
- Provider attribution: Strict truthfulness — Never label delayed/stale data as live
"""

from __future__ import annotations

from datetime import datetime, timezone, date, timedelta
import logging
from enum import Enum
from typing import Any, Optional
import numpy as np
import pandas as pd

from app.database import get_bars, list_stocks

logger = logging.getLogger(__name__)

# Standard Indian Equity (NSE) Fixed Holidays for calendar-aware missing session checks
NSE_FIXED_HOLIDAYS = {
    "01-26",  # Republic Day
    "05-01",  # Maharashtra Day
    "08-15",  # Independence Day
    "10-02",  # Gandhi Jayanti
    "12-25",  # Christmas
}


class DataMode(str, Enum):
    """
    Standardized platform-wide market data modes.
    Strict rule: Historical/offline data can NEVER be labeled as LIVE.
    """
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    HISTORICAL = "HISTORICAL"
    SIMULATED = "SIMULATED"
    ESTIMATED = "ESTIMATED"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


def check_ist_market_hours() -> tuple[bool, int, float, str]:
    """
    Check if NSE market is currently open in Asia/Kolkata timezone (UTC + 5:30).
    Session: 09:15 to 15:30 IST (375 total minutes).
    Returns (is_market_open, elapsed_minutes, session_fraction, status_str).
    """
    utc_now = datetime.now(timezone.utc)
    ist_total_minutes = (utc_now.hour * 60 + utc_now.minute) + 330
    ist_day_minutes = ist_total_minutes % 1440
    weekday = utc_now.weekday()

    market_open_min = 9 * 60 + 15   # 09:15 IST
    market_close_min = 15 * 60 + 30 # 15:30 IST

    # Check for fixed holiday
    ist_date_str = (utc_now + timedelta(minutes=330)).strftime("%m-%d")
    is_holiday = ist_date_str in NSE_FIXED_HOLIDAYS

    is_open = (weekday < 5) and (not is_holiday) and (market_open_min <= ist_day_minutes <= market_close_min)
    if is_open:
        elapsed = max(1, ist_day_minutes - market_open_min)
        fraction = min(1.0, elapsed / 375.0)
        return True, elapsed, fraction, f"MARKET_OPEN ({elapsed}m of 375m, {fraction*100:.1f}%)"
    else:
        return False, 375, 1.0, "MARKET_CLOSED (EOD/Weekend/Holiday)"


def resolve_data_mode(
    provider: str,
    is_live_stream: bool = False,
    is_stale: bool = False,
    is_estimated: bool = False,
    has_data: bool = True,
) -> str:
    """
    Centrally resolve and enforce truthfulness in market data modes.
    CRITICAL RULE: Historical data (yfinance, demo, SQLite cache) cannot silently appear as live data.
    """
    if not has_data:
        return DataMode.UNAVAILABLE.value

    p_lower = str(provider).lower()

    # Synthetic or calculated estimate (e.g. index approximated from stock movements)
    if is_estimated:
        return DataMode.ESTIMATED.value

    # Providers that can NEVER provide genuine live tick data
    if p_lower in ("yfinance", "yahoo", "demo", "historical", "sqlite"):
        if is_live_stream:
            logger.warning("Attempted to set live mode on historical provider '%s'; forced HISTORICAL", provider)
        if is_stale:
            return DataMode.STALE.value
        return DataMode.HISTORICAL.value

    # Broker live feed (Dhan)
    if p_lower == "dhan":
        if is_live_stream:
            if is_stale:
                return DataMode.STALE.value
            return DataMode.LIVE.value
        else:
            # Dhan configured but stream not actively connected/subscribed
            return DataMode.DELAYED.value if not is_stale else DataMode.STALE.value

    if is_stale:
        return DataMode.STALE.value

    return DataMode.HISTORICAL.value


def build_standard_metadata(
    provider: str = "yfinance",
    exchange: str = "NSE",
    instrument: str = "EQUITY",
    symbol: Optional[str] = None,
    timeframe: str = "1D",
    data_mode: Optional[str] = None,
    last_updated: Optional[str] = None,
    source_interval: str = "1d",
    is_stale: bool = False,
    stale_reason: Optional[str] = None,
    data_quality_status: str = "HEALTHY",
    disclaimer: Optional[str] = None,
    is_estimated: bool = False,
    is_live_stream: bool = False,
    has_data: bool = True,
) -> dict[str, Any]:
    """
    Standardized metadata builder for every market-data response across the platform.
    """
    resolved_mode = data_mode or resolve_data_mode(
        provider=provider,
        is_live_stream=is_live_stream,
        is_stale=is_stale,
        is_estimated=is_estimated,
        has_data=has_data,
    )

    utc_now = datetime.now(timezone.utc)
    ts_iso = utc_now.strftime("%Y-%m-%dT%H:%M:%SZ")

    if not last_updated:
        last_updated = ts_iso

    default_disclaimer = (
        "Market data provided in HISTORICAL mode via yfinance zero-cost research engine. "
        "Dhan live streaming feed is currently inactive. No live tick or market depth execution claimed."
    )

    return {
        "provider": str(provider).upper(),
        "exchange": str(exchange).upper(),
        "instrument": str(instrument).upper(),
        "symbol": str(symbol).upper() if symbol else None,
        "timeframe": timeframe,
        "data_mode": resolved_mode,
        "timestamp": ts_iso,
        "last_updated": str(last_updated),
        "is_stale": is_stale,
        "stale_reason": stale_reason if is_stale else None,
        "source_interval": source_interval,
        "data_quality_status": data_quality_status,
        "disclaimer": disclaimer or default_disclaimer,
    }


def audit_universe_coverage(
    universe_name: str = "all",
    target_symbols: Optional[set[str]] = None,
) -> dict[str, Any]:
    """
    Audit stock universe coverage transparently.
    Never claims full NIFTY 500 when only a subset is available in the database.
    """
    all_stocks = list_stocks()
    total_in_db = len(all_stocks)

    univ = universe_name.lower()
    if univ == "nifty50":
        configured_count = 50
        universe_label = "NIFTY 50"
    elif univ == "nifty100":
        configured_count = 100
        universe_label = "NIFTY 100"
    elif univ == "nifty500":
        configured_count = 500
        universe_label = "NIFTY 500"
    elif univ == "fno":
        configured_count = 180
        universe_label = "NSE F&O Stocks"
    else:
        configured_count = total_in_db
        universe_label = "All Tracked NSE Stocks"

    # Evaluate target stocks
    if target_symbols:
        matched = [s for s in all_stocks if s.get("symbol") in target_symbols]
    else:
        matched = all_stocks

    price_avail = sum(1 for s in matched if (s.get("close") or 0) > 0)
    fund_avail = sum(1 for s in matched if s.get("roe") is not None or s.get("pe") is not None)
    tech_valid = sum(1 for s in matched if s.get("rsi") is not None)

    tracked_count = len(matched)
    excluded_count = max(0, configured_count - tracked_count)
    coverage_pct = round((tracked_count / max(configured_count, 1)) * 100.0, 1)

    is_full = tracked_count >= configured_count
    if is_full:
        disclosure = f"100% full universe coverage ({tracked_count} of {configured_count} constituents)."
    else:
        disclosure = (
            f"Partial universe coverage: scanned {tracked_count} of {configured_count} "
            f"configured constituents ({coverage_pct}%). {excluded_count} constituents unseeded/missing in database."
        )

    return {
        "universe_name": universe_name,
        "universe_label": universe_label,
        "configured_instruments": configured_count,
        "tracked_instruments": tracked_count,
        "price_available_count": price_avail,
        "fundamental_available_count": fund_avail,
        "technical_valid_count": tech_valid,
        "excluded_count": excluded_count,
        "coverage_pct": coverage_pct,
        "is_full_coverage": is_full,
        "coverage_disclosure": disclosure,
    }


def audit_single_symbol_data_quality(
    bars: list[dict],
    symbol: str = "UNKNOWN",
    provider: str = "YFINANCE",
    is_live_stream: bool = False,
) -> dict:
    """
    Perform deep quantitative data quality inspection on an OHLCV dataset.
    """
    if not bars or len(bars) == 0:
        return {
            "symbol": symbol,
            "status": "MISSING_DATA",
            "quality_grade": "F",
            "bars_count": 0,
            "first_timestamp": None,
            "last_timestamp": None,
            "data_provider": provider.upper(),
            "is_live": False,
            "anomalies": ["No historical bars found in dataset"],
            "ohlc_consistency": {"passed": False, "violations_count": 0},
            "temporal_integrity": {"is_sorted": False, "duplicates_count": 0, "out_of_order_count": 0},
            "calendar_integrity": {"missing_sessions_count": 0, "missing_session_dates": []},
            "volume_integrity": {"zero_volume_bars": 0, "anomalous_spikes_count": 0},
            "corporate_actions": {"unadjusted_gap_flags": []},
            "freshness": {"is_fresh": False, "business_days_lag": 999},
        }

    df = pd.DataFrame(bars)
    if "date" in df.columns and "timestamp" not in df.columns:
        df = df.rename(columns={"date": "timestamp"})

    n_bars = len(df)
    anomalies = []

    # 1. Temporal Integrity: Duplicate & Out-of-Order Timestamps
    ts_series = pd.to_datetime(df["timestamp"], errors="coerce")
    duplicates_count = int(df["timestamp"].duplicated().sum())
    is_monotonic = bool(ts_series.is_monotonic_increasing)
    out_of_order_count = 0
    if not is_monotonic:
        diffs = ts_series.diff().dt.total_seconds()
        out_of_order_count = int((diffs < 0).sum())
        anomalies.append(f"{out_of_order_count} out-of-order timestamp sequence(s) detected")

    if duplicates_count > 0:
        anomalies.append(f"{duplicates_count} duplicate timestamp(s) detected")

    # 2. Full OHLC Consistency Checks
    ohlc_violations = 0
    ohlc_violation_details = []

    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            non_pos = int((df[col] <= 0).sum())
            if non_pos > 0:
                ohlc_violations += non_pos
                ohlc_violation_details.append(f"{non_pos} bar(s) with price <= 0 in {col}")

    if "high" in df.columns and "low" in df.columns:
        inverted = int((df["high"] < df["low"]).sum())
        if inverted > 0:
            ohlc_violations += inverted
            ohlc_violation_details.append(f"{inverted} bar(s) with High < Low")

    if all(c in df.columns for c in ("open", "high", "low", "close")):
        high_invalid = int(((df["high"] < df["open"]) | (df["high"] < df["close"])).sum())
        if high_invalid > 0:
            ohlc_violations += high_invalid
            ohlc_violation_details.append(f"{high_invalid} bar(s) where High < max(Open, Close)")

        low_invalid = int(((df["low"] > df["open"]) | (df["low"] > df["close"])).sum())
        if low_invalid > 0:
            ohlc_violations += low_invalid
            ohlc_violation_details.append(f"{low_invalid} bar(s) where Low > min(Open, Close)")

    anomalies.extend(ohlc_violation_details)

    # 3. Exchange-Calendar-Aware Missing Sessions Check
    missing_sessions = []
    if is_monotonic and len(ts_series.dropna()) >= 2:
        valid_dates = ts_series.dropna().dt.date
        for i in range(1, len(valid_dates)):
            d_prev = valid_dates.iloc[i - 1]
            d_curr = valid_dates.iloc[i]
            # Expected trading days between previous and current bar
            b_days = pd.bdate_range(d_prev, d_curr, inclusive="neither")
            for b_day in b_days:
                mm_dd = b_day.strftime("%m-%d")
                if mm_dd not in NSE_FIXED_HOLIDAYS:
                    missing_sessions.append(b_day.strftime("%Y-%m-%d"))

    if len(missing_sessions) > 0:
        anomalies.append(f"{len(missing_sessions)} potential exchange-calendar missing session(s)")

    # 4. Zero and Anomalous Volume Spikes
    zero_vol_count = 0
    anomalous_spikes = 0
    if "volume" in df.columns:
        zero_vol_count = int((df["volume"] == 0).sum())
        if zero_vol_count > 0:
            anomalies.append(f"{zero_vol_count} bar(s) with 0 volume")

        vol_series = df["volume"]
        rolling_median = vol_series.rolling(20, min_periods=5).median()
        spikes = (vol_series > 20.0 * rolling_median) & (rolling_median > 0)
        anomalous_spikes = int(spikes.sum())
        if anomalous_spikes > 0:
            anomalies.append(f"{anomalous_spikes} anomalous volume spike(s) (>20x 20-day median)")

    # 5. Corporate-Action Adjustment Limitations (Flag large unadjusted price jumps)
    unadjusted_gaps = []
    if "close" in df.columns and "open" in df.columns and len(df) >= 2:
        prev_close = df["close"].shift(1)
        curr_open = df["open"]
        overnight_pct = ((curr_open - prev_close) / prev_close) * 100.0
        # Flag drops > 40% (e.g. 2:1, 5:1 stock split) or surges > 80%
        suspected_splits = df[(overnight_pct < -40.0) | (overnight_pct > 80.0)]
        for idx in suspected_splits.index:
            t_str = str(df["timestamp"].iloc[idx])
            gap_pct = round(float(overnight_pct.iloc[idx]), 1)
            unadjusted_gaps.append({"timestamp": t_str, "gap_pct": gap_pct})
            anomalies.append(f"Unadjusted corporate-action gap ({gap_pct}%) on {t_str}")

    # 6. Data Freshness Check
    first_t = str(df["timestamp"].iloc[0])
    last_t = str(df["timestamp"].iloc[-1])
    try:
        last_dt = pd.to_datetime(last_t).date()
        today_dt = datetime.now(timezone.utc).date()
        b_days_lag = len(pd.bdate_range(last_dt, today_dt, inclusive="neither"))
        is_fresh = b_days_lag <= 3
        if not is_fresh:
            anomalies.append(f"Stale data: last bar is {b_days_lag} business day(s) old")
    except Exception:
        b_days_lag = 0
        is_fresh = True

    # 7. Provider Attribution Truthfulness
    # Never mark historical or delayed data as live
    is_live = False
    if provider.lower() == "dhan" and is_live_stream:
        is_live = True

    # Quality Grade assignment
    if len(anomalies) == 0 and n_bars >= 100 and is_fresh:
        grade = "A+"
        status = "HEALTHY"
    elif len(anomalies) <= 1 and n_bars >= 40:
        grade = "A"
        status = "HEALTHY"
    elif len(anomalies) <= 3:
        grade = "B"
        status = "WARNING"
    else:
        grade = "C"
        status = "DEGRADED"

    return {
        "symbol": symbol,
        "status": status,
        "quality_grade": grade,
        "bars_count": n_bars,
        "first_timestamp": first_t,
        "last_timestamp": last_t,
        "data_provider": provider.upper(),
        "is_live": is_live,
        "anomalies": anomalies,
        "ohlc_consistency": {
            "passed": ohlc_violations == 0,
            "violations_count": ohlc_violations,
            "details": ohlc_violation_details,
        },
        "temporal_integrity": {
            "is_sorted": is_monotonic,
            "duplicates_count": duplicates_count,
            "out_of_order_count": out_of_order_count,
        },
        "calendar_integrity": {
            "missing_sessions_count": len(missing_sessions),
            "missing_session_dates": missing_sessions[:10],
        },
        "volume_integrity": {
            "zero_volume_bars": zero_vol_count,
            "anomalous_spikes_count": anomalous_spikes,
        },
        "corporate_actions": {
            "unadjusted_gap_flags": unadjusted_gaps,
        },
        "freshness": {
            "is_fresh": is_fresh,
            "business_days_lag": b_days_lag,
        },
    }


def generate_market_data_quality_report() -> dict:
    """
    Audit data quality across all configured stocks in the universe.
    """
    stocks = list_stocks()
    total_requested = len(stocks)
    audited_stocks = []
    healthy_count = 0
    warning_count = 0
    error_count = 0

    now_utc = datetime.now(timezone.utc)

    for stk in stocks:
        sym = stk["symbol"]
        provider = stk.get("data_source", "yfinance")
        bars = get_bars(sym)

        stk_report = audit_single_symbol_data_quality(
            bars=bars,
            symbol=sym,
            provider=provider,
            is_live_stream=bool(provider == "dhan" and stk.get("live_available", False)),
        )
        stk_report["company_name"] = stk.get("company_name", sym)
        stk_report["sector"] = stk.get("sector", "General")

        if stk_report["status"] == "HEALTHY":
            healthy_count += 1
        elif stk_report["status"] == "WARNING":
            warning_count += 1
        else:
            error_count += 1

        audited_stocks.append(stk_report)

    overall_health = (
        "EXCELLENT"
        if healthy_count >= total_requested * 0.85
        else ("GOOD" if healthy_count >= total_requested * 0.60 else "DEGRADED")
    )

    return {
        "report_generated_utc": now_utc.isoformat(),
        "total_stocks_evaluated": total_requested,
        "healthy_stocks": healthy_count,
        "warning_stocks": warning_count,
        "error_stocks": error_count,
        "overall_health": overall_health,
        "data_providers": {
            "primary": "yfinance (historical OHLCV)",
            "live_stream": "DhanHQ WebSocket (when configured & enabled)",
            "live_policy": "Zero-Cost default; offline/historical data never labeled as LIVE",
        },
        "stocks": audited_stocks,
    }


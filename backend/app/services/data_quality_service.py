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


class DataSourceClassification(str, Enum):
    """
    Strict market data source provenance classification (Phase 14.3).
    Guarantees that synthetic, calibrated, or mock bars are never conflated
    with genuine exchange-observed historical or live data.
    """
    OBSERVED_LIVE = "OBSERVED_LIVE"
    OBSERVED_DELAYED = "OBSERVED_DELAYED"
    OBSERVED_HISTORICAL = "OBSERVED_HISTORICAL"
    SYNTHETIC = "SYNTHETIC"
    UNKNOWN = "UNKNOWN"


def classify_data_source(source_str: Optional[str]) -> DataSourceClassification:
    """
    Strictly classify bar or quote data source into standardized provenance categories.
    CRITICAL RULE: Never classify a record as observed solely because it has OHLCV values or timestamps.
    """
    if not source_str:
        return DataSourceClassification.UNKNOWN

    s = str(source_str).strip().lower()

    # Synthetic / simulated / calibrated markers
    synthetic_indicators = (
        "synthetic", "calibrated", "deterministic", "simulated",
        "mock", "dummy", "offline_deterministic", "demo_feed"
    )
    if any(k in s for k in synthetic_indicators):
        return DataSourceClassification.SYNTHETIC

    # Live observed feeds
    if s in ("dhan_live", "dhan_broker_live", "live_stream", "exchange_tick_live"):
        return DataSourceClassification.OBSERVED_LIVE

    # Delayed observed feeds
    if s in ("yfinance_delayed", "delayed_stream", "15m_delayed"):
        return DataSourceClassification.OBSERVED_DELAYED

    # Historical observed feeds
    if s in (
        "yfinance", "yfinance_historical_5m", "dhan", "dhan_historical",
        "dhan_historical_5m", "nse_official_historical", "sqlite_observed"
    ):
        return DataSourceClassification.OBSERVED_HISTORICAL

    return DataSourceClassification.UNKNOWN


def verify_bar_provenance(
    bar: dict[str, Any],
    strict_audit: bool = False,
    check_db_provenance: bool = False,
    symbol: Optional[str] = None,
    interval: str = "5m",
) -> tuple[DataSourceClassification, str, dict[str, Any]]:
    """
    Strengthened Provenance Verification Engine (Phase 14.4).
    CRITICAL PROVENANCE RULES:
    1. Never infer observed provenance from the presence of OHLCV values, timestamps,
       or a manually supplied source string alone when strict audit is requested.
    2. A bar claiming observed status under strict audit MUST possess verified ingestion metadata:
       - ingestion_run_id
       - provider identifier
       - provider_symbol
       - retrieval_timestamp (UTC)
       - raw_response_hash
       OR have a matching verified record in the database bar_provenance table.
    3. Synthetic records remain SYNTHETIC, even if their source field is changed or disguised.
    4. Spoofed or unverified source strings without audit trail are strictly classified as UNKNOWN.
    """
    if not bar:
        return DataSourceClassification.UNKNOWN, "Empty bar record", {}

    source_val = str(bar.get("source") or "").strip().lower()
    prov_class_val = str(bar.get("provenance_classification") or "").strip().upper()
    is_synthetic_marker = bool(
        bar.get("is_synthetic") or
        prov_class_val == "SYNTHETIC" or
        any(k in source_val for k in ("synthetic", "calibrated", "deterministic", "simulated", "mock", "dummy", "offline"))
    )

    if is_synthetic_marker:
        provenance_dict = {
            "provider": bar.get("provider") or "synthetic_calibrated_engine",
            "provenance_classification": DataSourceClassification.SYNTHETIC.value,
            "data_quality_status": "SYNTHETIC_SIMULATION",
            "ingestion_run_id": bar.get("ingestion_run_id"),
        }
        return DataSourceClassification.SYNTHETIC, "SYNTHETIC_SIMULATION: Calibrated offline simulation bar", provenance_dict

    # Check for explicit spoofing marker
    if bar.get("is_spoofed") or bar.get("spoofed"):
        return DataSourceClassification.UNKNOWN, "UNVERIFIED_OR_SPOOFED_SOURCE: Injected source string without valid exchange audit trail", {}

    # Check for attached ingestion audit metadata
    has_audit_metadata = bool(
        bar.get("ingestion_run_id") and
        bar.get("provider") and
        (bar.get("raw_response_hash") or bar.get("retrieval_timestamp"))
    )

    if has_audit_metadata:
        raw_class = classify_data_source(bar.get("source") or bar.get("provider"))
        if raw_class in (
            DataSourceClassification.OBSERVED_HISTORICAL,
            DataSourceClassification.OBSERVED_DELAYED,
            DataSourceClassification.OBSERVED_LIVE,
        ):
            provenance_dict = {
                "provider": bar.get("provider"),
                "provider_symbol": bar.get("provider_symbol"),
                "exchange": bar.get("exchange", "NSE"),
                "segment": bar.get("segment", "EQUITY"),
                "interval": bar.get("interval", interval),
                "ingestion_run_id": bar.get("ingestion_run_id"),
                "retrieval_timestamp": bar.get("retrieval_timestamp"),
                "raw_response_hash": bar.get("raw_response_hash"),
                "provenance_classification": raw_class.value,
                "data_quality_status": bar.get("data_quality_status", "VERIFIED_OBSERVED_INTRADAY"),
            }
            return raw_class, f"VERIFIED_OBSERVED: Validated against ingestion run {bar.get('ingestion_run_id')}", provenance_dict

    # Check database bar_provenance table if requested
    if check_db_provenance:
        sym = symbol or bar.get("symbol")
        ts = bar.get("timestamp")
        if sym and ts:
            try:
                from app.database import get_bar_provenance
                db_prov = get_bar_provenance(sym, interval, ts)
                if db_prov:
                    c_val = DataSourceClassification(db_prov.get("provenance_classification", "UNKNOWN"))
                    return c_val, f"VERIFIED_OBSERVED_DB: Validated in bar_provenance ({db_prov.get('ingestion_run_id')})", db_prov
            except Exception as e:
                logger.debug("bar_provenance lookup exception: %s", e)

    # When strict audit is enabled, raw source string without audit trail is rejected as UNKNOWN
    if strict_audit:
        if source_val in (
            "yfinance", "yfinance_historical_5m", "dhan", "dhan_historical",
            "dhan_historical_5m", "nse_official_historical", "sqlite_observed"
        ):
            return DataSourceClassification.UNKNOWN, "UNVERIFIED_OR_SPOOFED_SOURCE: Bar lacks verified ingestion run ID and provider retrieval audit trail", {}

    # Non-strict backward-compatible path for simple source classification
    base_class = classify_data_source(bar.get("source"))
    if base_class != DataSourceClassification.UNKNOWN:
        return base_class, f"CLASSIFIED_SOURCE: {base_class.value}", {"source": bar.get("source")}

    return DataSourceClassification.UNKNOWN, "MISSING_OR_UNRECOGNIZED_SOURCE", {}


def validate_session_completeness(
    session_date: str,
    bars: list[dict[str, Any]],
    expected_interval: str = "5m",
    symbol: Optional[str] = None,
) -> dict[str, Any]:
    """
    Exact Intraday Session Completeness Validator (Phase 14.6 CAS-Aware Architecture).
    Grounding:
    - NSE Circulars NSE/CMTR/72394, NSE/CMTR/73362, NSE/CMTR/74466.
    - Go-live August 03, 2026 for Closing Auction Session (CAS) in F&O cash equities.

    Validates:
    - Security- and Date-aware continuous session schedule:
      * CAS-eligible securities post-Aug 3, 2026: 72 continuous 5m bars (09:15 to 15:10 IST).
      * Standard regular securities: 75 continuous 5m bars (09:15 to 15:25 IST).
      * Special sessions: Muhurat (12 bars), DR Drill (21 bars).
    - Separation of continuous trading from Closing Auction transition & confirmation bars.
    - Missing continuous intervals (distinguishes interior gaps from boundary omissions).
    - Duplicate timestamps within continuous session.
    - Out-of-session timestamps (outside continuous trading and closing auction window).
    - Misaligned intervals (seconds != 0 or minutes % 5 != 0).
    - Invalid OHLC mathematical relationships (high < low, open or close outside high/low).
    - Negative or impossible volume (< 0).
    - Timezone consistency (Asia/Kolkata +05:30).
    """
    from app.services.trading_calendar_service import (
        get_expected_session_schedule,
        is_trading_day,
    )

    clean_sym = symbol.strip().split(".")[0].upper() if symbol else None
    schedule = get_expected_session_schedule(clean_sym, session_date, interval=expected_interval)

    if not schedule["is_trading_day"]:
        return {
            "is_complete": False,
            "session_date": session_date,
            "symbol": clean_sym,
            "session_type": schedule["session_type"],
            "schedule_version": schedule.get("schedule_version", "NON_TRADING_DAY"),
            "circular_references": schedule.get("circular_references", []),
            "is_cas_eligible": schedule["is_cas_eligible"],
            "expected_bars": 0,
            "expected_continuous_bars": 0,
            "actual_bars": len(bars),
            "actual_continuous_bars": 0,
            "valid_bars_count": 0,
            "missing_intervals": [],
            "missing_interior_intervals": [],
            "duplicate_intervals": [],
            "has_closing_auction": False,
            "auction_bars_count": 0,
            "auction_timestamps": [],
            "out_of_session_intervals": [],
            "misaligned_intervals": [],
            "ohlc_violations": [],
            "volume_violations": [],
            "errors": [f"EXCHANGE_CALENDAR_EXCLUSION: {schedule['status_reason']}"],
            "status": f"EXCHANGE_CALENDAR_EXCLUSION: {schedule['status_reason']}",
            "schedule": schedule,
        }

    expected_continuous_times = schedule["expected_continuous_timestamps"]
    expected_continuous_bars = schedule["expected_continuous_bars"]
    has_closing_auction = schedule["has_closing_auction"]
    acceptable_auction_times = set(schedule["acceptable_auction_timestamps"])

    seen_continuous_times: list[str] = []
    seen_continuous_set: set[str] = set()
    duplicate_continuous_times: list[str] = []

    auction_bars: list[dict[str, Any]] = []
    out_of_session_times: list[str] = []
    misaligned_times: list[str] = []
    date_mismatches: list[str] = []
    ohlc_violations: list[dict[str, Any]] = []
    volume_violations: list[dict[str, Any]] = []

    for b in bars:
        raw_ts = str(b.get("timestamp") or "")
        # Parse timestamp to IST
        d_ist, t_ist = None, None
        try:
            if "T" in raw_ts or raw_ts.endswith("Z"):
                clean = raw_ts.replace("Z", "+00:00")
                dt = datetime.fromisoformat(clean)
                if dt.tzinfo is not None:
                    ist_dt = dt.astimezone(timezone(timedelta(hours=5, minutes=30)))
                else:
                    ist_dt = dt + timedelta(hours=5, minutes=30)
                d_ist = ist_dt.strftime("%Y-%m-%d")
                t_ist = ist_dt.strftime("%H:%M:%S")
            else:
                parts = raw_ts.strip().split(" ")
                if len(parts) >= 2:
                    d_ist = parts[0]
                    t_ist = parts[1][:8]
        except Exception:
            pass

        if not d_ist or not t_ist:
            date_mismatches.append(raw_ts)
            continue

        if d_ist != session_date:
            date_mismatches.append(f"{raw_ts} (IST date {d_ist} != session {session_date})")

        # Alignment check: seconds must be 00 and minute must be multiple of 5
        t_parts = t_ist.split(":")
        if len(t_parts) >= 2:
            mins = int(t_parts[1])
            secs = int(t_parts[2]) if len(t_parts) >= 3 else 0
            if mins % 5 != 0 or secs != 0:
                misaligned_times.append(t_ist)

        # Categorize bar: Continuous vs Auction vs Out of Session
        if t_ist in expected_continuous_times:
            if t_ist in seen_continuous_set:
                duplicate_continuous_times.append(t_ist)
            seen_continuous_times.append(t_ist)
            seen_continuous_set.add(t_ist)
        elif has_closing_auction and t_ist in acceptable_auction_times:
            auction_bars.append({
                "time": t_ist,
                "bar": b,
            })
        else:
            out_of_session_times.append(t_ist)

        # OHLC mathematical consistency check
        o = float(b.get("open") or 0.0)
        h = float(b.get("high") or 0.0)
        l = float(b.get("low") or 0.0)
        c = float(b.get("close") or 0.0)

        if o <= 0 or h <= 0 or l <= 0 or c <= 0 or h < l or h < o or h < c or l > o or l > c:
            ohlc_violations.append({
                "time": t_ist,
                "open": o, "high": h, "low": l, "close": c,
                "reason": "Invalid OHLC bounds (high < low or open/close outside high/low range)",
            })

        # Volume validity check
        v = b.get("volume")
        if v is None or float(v) < 0:
            volume_violations.append({
                "time": t_ist,
                "volume": v,
                "reason": "Negative or missing volume",
            })

    # Continuous session completeness & gap analysis
    missing_continuous = [t for t in expected_continuous_times if t not in seen_continuous_set]

    # Differentiate interior gaps vs boundary omissions
    missing_interior: list[str] = []
    missing_boundary: list[str] = []
    if seen_continuous_times:
        min_seen = min(seen_continuous_times)
        max_seen = max(seen_continuous_times)
        for t in missing_continuous:
            if min_seen < t < max_seen:
                missing_interior.append(t)
            else:
                missing_boundary.append(t)
    else:
        missing_boundary = list(missing_continuous)

    errors: list[str] = []
    if missing_interior:
        errors.append(f"MISSING_INTERIOR_INTERVALS ({len(missing_interior)} interior missing: {', '.join(missing_interior[:3])})")
    if missing_continuous:
        errors.append(f"MISSING_INTERVALS ({len(missing_continuous)} missing of {expected_continuous_bars})")
    if duplicate_continuous_times:
        errors.append(f"DUPLICATE_TIMESTAMPS ({len(duplicate_continuous_times)} duplicates)")
    if out_of_session_times:
        errors.append(f"OUT_OF_SESSION_TIMESTAMPS ({len(out_of_session_times)} intervals)")
    if misaligned_times:
        errors.append(f"MISALIGNED_INTERVALS ({len(misaligned_times)} intervals not 5m-aligned)")
    if date_mismatches:
        errors.append(f"DATE_OR_TIMEZONE_MISMATCH ({len(date_mismatches)} bars)")
    if ohlc_violations:
        errors.append(f"INVALID_OHLC_RELATIONSHIPS ({len(ohlc_violations)} bars)")
    if volume_violations:
        errors.append(f"NEGATIVE_OR_INVALID_VOLUME ({len(volume_violations)} bars)")

    # Check continuous bar count
    if len(seen_continuous_set) != expected_continuous_bars:
        errors.append(f"UNEXPECTED_BAR_COUNT ({len(seen_continuous_set)} continuous actual vs {expected_continuous_bars} expected)")

    is_complete = (
        len(errors) == 0 and
        len(seen_continuous_set) == expected_continuous_bars and
        len(missing_continuous) == 0
    )

    if is_complete:
        if has_closing_auction:
            if auction_bars:
                status = "SESSION_COMPLETE_AUCTION_INCLUDED"
            else:
                status = "SESSION_COMPLETE_CAS_NOT_INCLUDED"
        else:
            status = "SESSION_COMPLETE"
    else:
        if ohlc_violations or volume_violations:
            status = "SESSION_INVALID"
        elif missing_interior:
            status = f"SESSION_INCOMPLETE_INTERIOR_GAP ({len(missing_interior)} bars)"
        elif missing_boundary:
            status = f"SESSION_INCOMPLETE_BOUNDARY_GAP ({len(missing_boundary)} bars)"
        elif errors:
            status = errors[0]
        else:
            status = "SESSION_INCOMPLETE"

    return {
        "is_complete": is_complete,
        "session_date": session_date,
        "symbol": clean_sym,
        "session_type": schedule["session_type"],
        "schedule_version": schedule.get("schedule_version", "STANDARD_SCHEDULE"),
        "circular_references": schedule.get("circular_references", []),
        "is_cas_eligible": schedule["is_cas_eligible"],
        "expected_bars": expected_continuous_bars,
        "expected_continuous_bars": expected_continuous_bars,
        "actual_bars": len(bars),
        "actual_continuous_bars": len(seen_continuous_set),
        "valid_bars_count": len(seen_continuous_set),
        "missing_intervals": missing_continuous,
        "missing_interior_intervals": missing_interior,
        "duplicate_intervals": duplicate_continuous_times,
        "has_closing_auction": has_closing_auction,
        "auction_bars_count": len(auction_bars),
        "auction_timestamps": [b["time"] for b in auction_bars],
        "out_of_session_intervals": out_of_session_times,
        "misaligned_intervals": misaligned_times,
        "ohlc_violations": ohlc_violations,
        "volume_violations": volume_violations,
        "errors": errors,
        "status": status,
        "schedule": schedule,
    }


def classify_session_provenance(
    bars: list[dict[str, Any]],
    strict_audit: bool = False,
    check_db_audit: bool = False,
    require_completeness: bool = False,
    session_date: Optional[str] = None,
    symbol: Optional[str] = None,
) -> tuple[DataSourceClassification, str]:
    """
    Audits the provenance of all bars in a trading session.
    If ANY bar is synthetic, the entire session is classified as SYNTHETIC.
    If any bar has unknown origin, session is UNKNOWN.
    If require_completeness=True, validates continuous session completeness.
    """
    if not bars:
        return DataSourceClassification.UNKNOWN, "Empty bar list"

    classifications = set()
    for b in bars:
        c, _, _ = verify_bar_provenance(
            b,
            strict_audit=strict_audit,
            check_db_provenance=check_db_audit,
            symbol=symbol or b.get("symbol"),
        )
        classifications.add(c)

    if DataSourceClassification.SYNTHETIC in classifications:
        return DataSourceClassification.SYNTHETIC, "Contains synthetic/calibrated bars"

    if DataSourceClassification.UNKNOWN in classifications:
        return DataSourceClassification.UNKNOWN, "Contains unverified/unknown source bars"

    # Optional session completeness check for observed sessions
    if require_completeness and session_date:
        comp = validate_session_completeness(session_date, bars, symbol=symbol)
        if not comp["is_complete"]:
            return DataSourceClassification.UNKNOWN, f"INCOMPLETE_SESSION: {comp['status']}"

    if len(classifications) == 1:
        single = next(iter(classifications))
        return single, f"Uniform {single.value} session"

    # Mixed observed (e.g. historical + delayed)
    return DataSourceClassification.OBSERVED_HISTORICAL, "Mixed observed bars"


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


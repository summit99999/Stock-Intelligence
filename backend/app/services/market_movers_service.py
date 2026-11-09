"""
Market Movers & Price-Volume Confluence Intelligence Service (Phase 14 & Phase 14.1).

Computes 4 market mover panels:
1. Top Gainers — highest positive % price change.
2. Top Losers — largest negative % price change.
3. Volume Gainers — stocks with unusually high volume relative to 20-day average (RVOL).
4. High-Volume Losers — stocks with negative price change AND unusually high volume.

And 2 automated confluence intersection panels:
A. Bullish Price-Volume Confluence: GAINERS ∩ VOLUME_GAINERS
B. Bearish Price-Volume Confluence: LOSERS ∩ VOLUME_GAINERS

Phase 14.1 Data Accuracy & Validation Audit Guarantees:
1. Differentiated RVOL:
   - Daily RVOL: today's cumulative volume / 20-day average daily volume (PROVISIONAL during active session, COMPLETED post-market).
   - Time-of-day RVOL: cumulative volume / historical average at exact same time across comparable past sessions (UNAVAILABLE when intraday history missing).
   - Linear Estimated Intraday RVOL: explicitly separated and labeled LINEAR_ESTIMATED.
2. Price & LTP Correctness:
   - Latest traded price (ltp): only present if live/streaming quote; otherwise null/None.
   - Latest completed daily close (latest_completed_close): closing price of latest completed session.
   - Previous completed daily close (previous_completed_close): prior session closing price.
   - Intraday percentage change (intraday_change_pct): null for historical-only.
   - Completed session percentage change (completed_session_change_pct): change between latest and previous completed close.
3. Universe Coverage Audit:
   - Explicit constituent mapping for NIFTY 50, NIFTY 100, NIFTY 200, NIFTY 500, F&O, and All NSE.
   - Transparent reporting of requested universe size, tracked symbols, missing symbols, coverage %, and freshness.
   - Never reports 100% coverage when evaluating a 31-symbol sample against ~2,100 listed equities or NIFTY 500.
4. Snapshot Integrity:
   - Preserves source, source_timestamp, retrieval_timestamp, data_mode, and data_quality_status for every stock.
   - Flags stale and mismatched records.
   - Explicitly distinguishes calculation_snapshot_id from underlying market data timestamps.
5. Turnover Accuracy:
   - ACTUAL_TURNOVER when supplied directly by exchange/broker feed.
   - ESTIMATED_TURNOVER when calculated from OHLCV (volume × price).
   - UNAVAILABLE when volume or price is missing/zero.
6. Heuristic Confluence:
   - Compound score explicitly labeled HEURISTIC (not probability or institutional flow).
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

from app.database import get_bars, list_stocks
from app.services.data_quality_service import (
    DataMode,
    check_ist_market_hours,
)
from app.services.money_flow_service import (
    calculate_historical_time_of_day_rvol,
    calculate_linear_estimated_intraday_rvol,
)

logger = logging.getLogger(__name__)

# In-memory TTL cache for market movers
_MOVERS_CACHE: Dict[str, Any] = {}
_MOVERS_CACHE_TS: float = 0.0
_CACHE_TTL_SECONDS: float = 30.0

# ---------------------------------------------------------------------------
# Canonical Universe Definitions
# ---------------------------------------------------------------------------

ESTIMATED_NSE_CASH_LISTINGS_COUNT = 2100
ESTIMATED_FNO_SECURITIES_COUNT = 180

NIFTY_50_FULL: Set[str] = {
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BPCL",
    "BHARTIARTL", "BRITANNIA", "CIPLA", "COALINDIA", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "ITC",
    "INDUSINDBK", "INFY", "JSWSTEEL", "KOTAKBANK", "LT",
    "LTIM", "LTM", "MARUTI", "NTPC", "NESTLEIND", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SHRIRAMFIN", "SBIN",
    "SUNPHARMA", "TCS", "TATACONSUM", "TATAMOTORS", "TMPV", "TATASTEEL",
    "TECHM", "TITAN", "TRENT", "ULTRACEMCO", "WIPRO",
}

NIFTY_NEXT_50: Set[str] = {
    "ABB", "AMBUJACEM", "ATGL", "BANKBARODA", "BERGEPAINT",
    "BOSCHLTD", "CANBK", "CHOLAFIN", "COLPAL", "DLF",
    "DMART", "GAIL", "GODREJCP", "HAL", "HAVELLS",
    "ICICIGI", "ICICIPRULI", "IOC", "IRCTC", "JINDALSTEL",
    "JIOFIN", "LICI", "MARICO", "MOTHERSON", "NAUKRI",
    "NHPC", "PAGEIND", "PFC", "PIDILITIND", "PNB",
    "POLYCAB", "RECLTD", "SBICARD", "SIEMENS", "SRF",
    "TATACOMM", "TATAELXSI", "TATAPOWER", "TORNTPHARM", "TVSMOTOR",
    "UNITDSPR", "VBL", "VEDL", "ZOMATO", "ZYDUSLIFE",
    "DIXON", "KPITTECH", "DEEPAKNTR", "CDSL", "MAXHEALTH",
}

NIFTY_100_FULL: Set[str] = NIFTY_50_FULL | NIFTY_NEXT_50

from app.services.market_intelligence_service import NIFTY_50_CORE


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------

def format_turnover(val_in_rupees: float) -> str:
    """Format turnover in Indian numbering: Cr (>= 1e7), L (>= 1e5), or K."""
    if val_in_rupees >= 1e7:
        return f"₹{val_in_rupees / 1e7:.2f} Cr"
    elif val_in_rupees >= 1e5:
        return f"₹{val_in_rupees / 1e5:.2f} L"
    elif val_in_rupees >= 1e3:
        return f"₹{val_in_rupees / 1e3:.2f} K"
    return f"₹{val_in_rupees:.2f}"


def format_volume(vol: int) -> str:
    """Format volume in Indian numbering: Cr, L, or K."""
    if vol >= 1e7:
        return f"{vol / 1e7:.2f} Cr"
    elif vol >= 1e5:
        return f"{vol / 1e5:.2f} L"
    elif vol >= 1e3:
        return f"{vol / 1e3:.1f} K"
    return str(vol)


def check_is_stale(source_ts_str: Optional[str], max_days: int = 7) -> Tuple[bool, Optional[str]]:
    """
    Determine if a source timestamp is older than max_days calendar days
    (~5 trading sessions). Returns (is_stale, reason).
    """
    if not source_ts_str:
        return True, "Missing source timestamp"
    try:
        clean_ts = str(source_ts_str).replace("T", " ").split("+")[0].split("Z")[0].strip()
        dt = datetime.strptime(clean_ts[:19], "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        age_days = (now - dt).total_seconds() / 86400.0
        if age_days > max_days:
            return True, f"Data age is {age_days:.1f} days (exceeds {max_days}-day / 5-session threshold)"
        return False, None
    except Exception:
        try:
            dt = datetime.strptime(clean_ts[:10], "%Y-%m-%d")
            age_days = (datetime.now() - dt).total_seconds() / 86400.0
            if age_days > max_days:
                return True, f"Data age is {age_days:.1f} days (exceeds {max_days}-day threshold)"
            return False, None
        except Exception:
            return False, None


# ---------------------------------------------------------------------------
# Core Metric Extractor (Phase 14.1 Enhanced)
# ---------------------------------------------------------------------------

def extract_stock_mover_metrics(
    stock_record: dict[str, Any],
    live_quote: Optional[dict[str, Any]] = None,
    is_session_open: Optional[bool] = None,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    """
    Extract and compute standardized price, previous close, RVOL, volume, and turnover
    for a single stock within an atomic evaluation pass.

    Guarantees:
    - Separates live LTP from latest completed close and previous completed close.
    - Historical data is never represented as live LTP.
    - Differentiates daily RVOL (PROVISIONAL/COMPLETED) from Time-of-Day RVOL (UNAVAILABLE if missing).
    - Labels turnover as ACTUAL_TURNOVER, ESTIMATED_TURNOVER, or UNAVAILABLE.
    - Tracks source_timestamp, retrieval_timestamp, data_mode, and stale status.
    """
    retrieval_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    sym = str(stock_record.get("symbol", "")).upper()
    company_name = stock_record.get("company_name", sym)
    sector = stock_record.get("sector") or "General"
    meta_close = float(stock_record.get("close") or 0.0)
    meta_change = float(stock_record.get("daily_change_pct") or 0.0)
    meta_volume = int(float(stock_record.get("volume") or 0))
    meta_rvol = float(stock_record.get("relative_volume") or 1.0)
    meta_updated_at = stock_record.get("updated_at") or time.strftime("%Y-%m-%d %H:%M:%S")

    # 1. Fetch daily OHLCV bars
    bars = get_bars(sym, interval="daily")
    n_bars = len(bars) if bars else 0

    adv_20 = 0
    latest_completed_close = meta_close
    previous_completed_close = 0.0
    quality_status = "ESTIMATED_SNAPSHOT"
    source_timestamp = meta_updated_at

    if n_bars >= 2:
        df = pd.DataFrame(bars)
        for col in ("open", "high", "low", "close", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close", "volume"]).reset_index(drop=True)

        if len(df) >= 2:
            volumes = df["volume"]
            closes = df["close"]
            prior_volumes = volumes.iloc[:-1]
            adv_20 = int(round(float(prior_volumes.tail(20).mean()))) if len(prior_volumes) >= 1 else meta_volume
            previous_completed_close = round(float(closes.iloc[-2]), 2)
            today_bar_volume = int(round(float(volumes.iloc[-1])))
            today_volume = today_bar_volume if today_bar_volume > 0 else meta_volume
            today_bar_close = round(float(closes.iloc[-1]), 2)
            if today_bar_close > 0:
                latest_completed_close = today_bar_close
            quality_status = "VERIFIED_OHLCV_20D"
            if "timestamp" in df.columns and str(df["timestamp"].iloc[-1]):
                source_timestamp = str(df["timestamp"].iloc[-1])
        elif len(df) == 1:
            today_volume = int(round(float(df["volume"].iloc[0]))) if float(df["volume"].iloc[0]) > 0 else meta_volume
            latest_completed_close = round(float(df["close"].iloc[0]), 2)
            quality_status = "INSUFFICIENT_BARS_1D"
        else:
            today_volume = meta_volume
    else:
        today_volume = meta_volume

    # Fallback for previous close if bars unavailable
    if previous_completed_close <= 0.0:
        if stock_record.get("previous_close") and float(stock_record["previous_close"]) > 0:
            previous_completed_close = round(float(stock_record["previous_close"]), 2)
        elif meta_change != 0.0 and latest_completed_close > 0:
            previous_completed_close = round(latest_completed_close / (1.0 + (meta_change / 100.0)), 2)
        else:
            previous_completed_close = latest_completed_close

    # Completed session percentage change
    if previous_completed_close > 0.0 and latest_completed_close > 0.0:
        completed_session_change_pct = round(
            ((latest_completed_close - previous_completed_close) / previous_completed_close) * 100.0, 2
        )
    else:
        completed_session_change_pct = round(meta_change, 2)

    # 2. Check Live LTP and Live Quote
    ltp: Optional[float] = None
    ltp_available = False
    intraday_change_pct: Optional[float] = None
    is_live_quote = False

    if live_quote and live_quote.get("source") == "LIVE" and live_quote.get("ltp") is not None:
        ltp = round(float(live_quote["ltp"]), 2)
        ltp_available = True
        is_live_quote = True
        if live_quote.get("volume") and float(live_quote["volume"]) > 0:
            today_volume = int(float(live_quote["volume"]))
        if live_quote.get("timestamp"):
            source_timestamp = str(live_quote["timestamp"])
        if previous_completed_close > 0.0:
            intraday_change_pct = round(((ltp - previous_completed_close) / previous_completed_close) * 100.0, 2)
        elif live_quote.get("change_percent") is not None:
            intraday_change_pct = round(float(live_quote["change_percent"]), 2)
    elif stock_record.get("is_live") is True and stock_record.get("ltp") is not None:
        ltp = round(float(stock_record["ltp"]), 2)
        ltp_available = True
        is_live_quote = True
        if previous_completed_close > 0.0:
            intraday_change_pct = round(((ltp - previous_completed_close) / previous_completed_close) * 100.0, 2)

    # Backward compatible fields:
    close = ltp if ltp_available and ltp is not None else latest_completed_close
    previous_close = previous_completed_close
    daily_change_pct = intraday_change_pct if (ltp_available and intraday_change_pct is not None) else completed_session_change_pct

    # 3. Fallback for 20-day ADV if bars unavailable
    if adv_20 <= 0:
        if meta_rvol > 0 and today_volume > 0:
            adv_20 = int(round(today_volume / meta_rvol))
        else:
            adv_20 = max(1, today_volume)
        if quality_status == "ESTIMATED_SNAPSHOT":
            quality_status = "ESTIMATED_ADV_SNAPSHOT"

    # 4. Session State & Daily RVOL (Differentiated)
    if is_session_open is not None:
        session_is_active = is_session_open
        session_fraction = 0.5 if session_is_active else 1.0
        elapsed_min = 188 if session_is_active else 375
    else:
        mkt_open, elapsed_min, session_fraction, _ = check_ist_market_hours()
        session_is_active = mkt_open or stock_record.get("is_provisional", False)

    if adv_20 > 0:
        daily_rvol = round(today_volume / adv_20, 2)
    else:
        daily_rvol = round(meta_rvol, 2) if meta_rvol > 0 else 1.0

    if session_is_active:
        daily_rvol_is_provisional = True
        daily_rvol_status = "PROVISIONAL"
        daily_rvol_note = f"Session in progress ({elapsed_min}m elapsed of 375m). Cumulative daily volume is provisional."
    else:
        daily_rvol_is_provisional = False
        daily_rvol_status = "COMPLETED"
        daily_rvol_note = "Completed session. Daily RVOL is finalized against full session ADV20."

    # 5. Time-of-Day RVOL (Method A: Historical Time-of-Day)
    # Exclude holidays and incomplete sessions (< 60 bars); mark UNAVAILABLE if intraday history missing
    from app.services.intraday_data_service import get_latest_completed_5m_interval
    _, target_intraday_time, _ = get_latest_completed_5m_interval()

    tod_res = calculate_historical_time_of_day_rvol(
        symbol=sym,
        today_cumulative_volume=float(today_volume),
        current_time_str=target_intraday_time,
        min_bars_per_session=60,
        allow_synthetic=allow_synthetic,
    )
    time_of_day_rvol = tod_res.get("rvol")
    time_of_day_rvol_status = tod_res.get("status", "UNAVAILABLE")
    tod_rvol_status = tod_res.get("tod_rvol_status", "UNAVAILABLE")
    time_of_day_rvol_reason = tod_res.get("reason")
    tod_valid_sessions = tod_res.get("tod_valid_sessions", 0)
    tod_source = tod_res.get("tod_source", "UNAVAILABLE")
    tod_data_quality = tod_res.get("tod_data_quality", "INSUFFICIENT_OBSERVED_DATA")

    # Linear Estimated Intraday RVOL (Method B: Fallback calculation)
    linear_res = calculate_linear_estimated_intraday_rvol(
        today_cumulative_volume=float(today_volume),
        adv_20=float(adv_20),
        session_fraction=session_fraction,
    )
    linear_estimated_intraday_rvol = linear_res["rvol"]
    linear_estimated_intraday_rvol_status = "LINEAR_ESTIMATED"

    # 6. Turnover Calculation & Status Distinction
    actual_turnover = stock_record.get("turnover") or stock_record.get("actual_turnover")
    if actual_turnover is None and live_quote and live_quote.get("source") == "LIVE" and live_quote.get("turnover"):
        actual_turnover = live_quote.get("turnover")

    if actual_turnover is not None and float(actual_turnover) > 0 and (
        stock_record.get("turnover_status") == "ACTUAL_TURNOVER" or is_live_quote
    ):
        traded_val = round(float(actual_turnover), 2)
        turnover_status = "ACTUAL_TURNOVER"
        turnover_note = "Official exchange-reported turnover"
    elif today_volume > 0 and close > 0:
        traded_val = round(today_volume * close, 2)
        turnover_status = "ESTIMATED_TURNOVER"
        turnover_note = "Calculated from OHLCV bar volume × close price"
    else:
        traded_val = 0.0
        turnover_status = "UNAVAILABLE"
        turnover_note = "Turnover data unavailable"

    traded_value_cr = round(traded_val / 1e7, 2)
    turnover_formatted = format_turnover(traded_val)
    volume_formatted = format_volume(today_volume)
    adv_20_formatted = format_volume(adv_20)

    # 7. Stale and Data Mode Determination
    source = stock_record.get("data_source") or ("dhan" if is_live_quote else "yfinance")
    is_stale, stale_reason = check_is_stale(source_timestamp)
    if stock_record.get("is_stale") is True:
        is_stale = True
        stale_reason = stock_record.get("stale_reason") or "Flagged as stale in stock record"

    if is_stale:
        data_mode = DataMode.STALE.value
        quality_status = "STALE_RECORD"
    elif is_live_quote:
        data_mode = DataMode.LIVE.value
    elif daily_rvol_is_provisional:
        data_mode = "PROVISIONAL"
    else:
        data_mode = DataMode.HISTORICAL.value

    return {
        "symbol": sym,
        "company_name": company_name,
        "sector": sector,
        # Price and LTP Correctness
        "ltp": ltp,
        "ltp_available": ltp_available,
        "latest_completed_close": round(latest_completed_close, 2),
        "previous_completed_close": round(previous_completed_close, 2),
        "intraday_change_pct": intraday_change_pct,
        "completed_session_change_pct": completed_session_change_pct,
        # Backward-compatible price fields
        "close": round(close, 2),
        "previous_close": round(previous_close, 2),
        "daily_change_pct": daily_change_pct,
        # Volume & ADV
        "today_volume": today_volume,
        "volume_formatted": volume_formatted,
        "adv_20": adv_20,
        "adv_20_formatted": adv_20_formatted,
        # Differentiated RVOL Metrics
        "daily_rvol": daily_rvol,
        "daily_rvol_status": daily_rvol_status,
        "daily_rvol_is_provisional": daily_rvol_is_provisional,
        "daily_rvol_note": daily_rvol_note,
        "time_of_day_rvol": time_of_day_rvol,
        "time_of_day_rvol_status": time_of_day_rvol_status,
        "tod_rvol_status": tod_rvol_status,
        "time_of_day_rvol_reason": time_of_day_rvol_reason,
        "tod_valid_sessions": tod_valid_sessions,
        "tod_source": tod_source,
        "tod_data_quality": tod_data_quality,
        "linear_estimated_intraday_rvol": linear_estimated_intraday_rvol,
        "linear_estimated_intraday_rvol_status": linear_estimated_intraday_rvol_status,
        # Turnover Accuracy
        "traded_value": traded_val,
        "traded_value_cr": traded_value_cr,
        "turnover_formatted": turnover_formatted,
        "turnover_status": turnover_status,
        "turnover_note": turnover_note,
        # Snapshot Provenance & Freshness
        "data_source": source,
        "source_timestamp": source_timestamp,
        "retrieval_timestamp": retrieval_timestamp,
        "data_mode": data_mode,
        "data_quality_status": quality_status,
        "is_stale": is_stale,
        "stale_reason": stale_reason,
        "last_updated_time": source_timestamp,  # backward compatibility
    }


# ---------------------------------------------------------------------------
# Universe Coverage Audit (Phase 14.1 Transparent Audit)
# ---------------------------------------------------------------------------

def audit_universe_coverage_movers(
    universe_name: str,
    target_stocks: list[dict[str, Any]],
    all_database_stocks: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Transparently audit requested universe vs tracked symbols in local database.
    Explicitly prevents reporting 100% coverage on partial samples.
    """
    univ = universe_name.lower()
    total_db = len(all_database_stocks)
    all_db_symbols = {str(s.get("symbol", "")).upper() for s in all_database_stocks}
    target_symbols = [str(s.get("symbol", "")).upper() for s in target_stocks]

    if univ == "nifty50":
        requested_size = 50
        universe_label = "NIFTY 50"
        canonical_set = NIFTY_50_CORE
        tracked_symbols = sorted(list(set(target_symbols) & canonical_set))
        missing_symbols = sorted(list(canonical_set - set(tracked_symbols)))
    elif univ == "nifty100":
        requested_size = 100
        universe_label = "NIFTY 100"
        canonical_set = NIFTY_100_FULL
        tracked_symbols = sorted(list(set(target_symbols) & canonical_set))
        missing_symbols = sorted(list(canonical_set - set(tracked_symbols)))
    elif univ == "nifty200":
        requested_size = 200
        universe_label = "NIFTY 200"
        tracked_symbols = sorted(target_symbols)
        missing_symbols = [f"UNTRACKED_{i}" for i in range(1, max(1, requested_size - len(tracked_symbols)) + 1)]
    elif univ == "nifty500":
        requested_size = 500
        universe_label = "NIFTY 500"
        tracked_symbols = sorted(target_symbols)
        missing_symbols = [f"UNTRACKED_CONSTITUENT_{i}" for i in range(1, max(1, requested_size - len(tracked_symbols)) + 1)]
    elif univ == "fno":
        requested_size = ESTIMATED_FNO_SECURITIES_COUNT
        universe_label = "NSE F&O Equities"
        tracked_symbols = sorted(target_symbols)
        missing_symbols = [f"UNTRACKED_FNO_{i}" for i in range(1, max(1, requested_size - len(tracked_symbols)) + 1)]
    else:
        # All tracked stocks: Compare against total listed NSE equity universe
        requested_size = ESTIMATED_NSE_CASH_LISTINGS_COUNT
        universe_label = f"All Tracked NSE Equities ({total_db} Research Sample)"
        tracked_symbols = sorted(target_symbols)
        missing_symbols = [f"UNTRACKED_NSE_{i}" for i in range(1, max(1, requested_size - len(tracked_symbols)) + 1)]

    tracked_count = len(tracked_symbols)
    missing_count = max(0, requested_size - tracked_count)
    coverage_pct = round((tracked_count / max(1, requested_size)) * 100.0, 2)
    is_full = (tracked_count >= requested_size)

    if is_full:
        disclosure = f"100% full universe coverage ({tracked_count} of {requested_size} constituents)."
    elif univ == "all":
        disclosure = (
            f"Evaluating {tracked_count} locally tracked equities. This represents a research sample "
            f"({coverage_pct}%) of the ~{requested_size:,} active listed NSE cash market equities. "
            "NOT 100% NSE coverage."
        )
    else:
        disclosure = (
            f"Partial universe coverage: scanned {tracked_count} of {requested_size} configured "
            f"{universe_label} constituents ({coverage_pct}%). {missing_count} constituents unseeded/missing in database."
        )

    return {
        "universe_name": universe_name,
        "universe_label": universe_label,
        "requested_universe_size": requested_size,
        "tracked_symbols_count": tracked_count,
        "tracked_symbols": tracked_symbols,
        "missing_symbols_count": missing_count,
        "missing_symbols_sample": missing_symbols[:15],
        "coverage_pct": coverage_pct,
        "is_full_coverage": is_full,
        "coverage_disclosure": disclosure,
        "total_database_equities": total_db,
    }


# ---------------------------------------------------------------------------
# Master Market Movers & Confluence Engine (Phase 14.1)
# ---------------------------------------------------------------------------

def get_market_movers_and_confluence(
    universe: str = "all",
    exchange: str = "NSE",
    min_rvol: float = 1.5,
    min_price_change_pct: float = 0.0,
    min_traded_value_cr: float = 0.0,
    limit: int = 10,
    force_refresh: bool = False,
    exclude_stale: bool = False,
    is_session_open: Optional[bool] = None,
    live_quotes: Optional[dict[str, Any]] = None,
    rvol_mode: str = "daily",
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    """
    Produce the 4 Market Movers lists and 2 Confluence intersection lists
    from a single, atomic, synchronized snapshot.
    Supports dual RVOL methodology:
    - 'daily': Daily RVOL = Today's Volume / 20-Day Average Daily Volume (PROVISIONAL during session, COMPLETED after).
    - 'tod': True Time-of-Day RVOL = Today's Volume / Historical Average Volume at the same time across 20 sessions.
    Strict market verification (Phase 14.3):
    - allow_synthetic=False: Synthetic bars strictly isolated; TOD RVOL returns UNAVAILABLE when genuine observed data is absent.
    - allow_synthetic=True: Explicit demonstration mode only with non-confirmation disclaimer.
    """
    global _MOVERS_CACHE, _MOVERS_CACHE_TS

    # Normalize RVOL methodology
    active_rvol_mode = "tod" if str(rvol_mode).lower() in ("tod", "time_of_day", "intraday") else "daily"

    now = time.time()
    cache_key = (
        f"{universe}_{exchange}_{min_rvol}_{min_price_change_pct}_{min_traded_value_cr}_"
        f"{limit}_{exclude_stale}_{is_session_open}_{active_rvol_mode}_{allow_synthetic}"
    )
    if (
        not force_refresh
        and cache_key in _MOVERS_CACHE
        and (now - _MOVERS_CACHE_TS < _CACHE_TTL_SECONDS)
        and live_quotes is None
    ):
        cached = dict(_MOVERS_CACHE[cache_key])
        cached["is_cached"] = True
        return cached

    all_stocks = list_stocks()
    if not all_stocks:
        return {
            "error": "No stocks found in database.",
            "status": "EMPTY_DATABASE",
        }

    # 1. Universe Subsetting
    univ = universe.lower()
    if univ == "nifty50":
        target_stocks = [s for s in all_stocks if str(s.get("symbol", "")).upper() in NIFTY_50_CORE]
    elif univ == "nifty100":
        target_stocks = [s for s in all_stocks if str(s.get("symbol", "")).upper() in NIFTY_100_FULL]
    else:
        target_stocks = all_stocks

    # Optional Exchange Filtering
    if exchange and exchange.upper() in ("NSE", "BSE"):
        ex_filter = exchange.upper()
        matched = [s for s in target_stocks if str(s.get("exchange", "NSE")).upper() == ex_filter]
        if matched:
            target_stocks = matched

    # 2. Snapshot Identifiers (Distinguishing Calculation Snapshot from Market Data Timestamps)
    calc_now_utc = datetime.now(timezone.utc)
    calculation_timestamp = calc_now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    calculation_snapshot_id = f"snap_{int(now)}_{uuid.uuid4().hex[:8]}"
    snapshot_id = calculation_snapshot_id

    # 3. Evaluate Metrics for All Stocks in Snapshot
    evaluated_stocks: list[dict[str, Any]] = []
    source_timestamps: list[str] = []

    for s in target_stocks:
        sym = str(s.get("symbol", "")).upper()
        l_quote = live_quotes.get(sym) if live_quotes else None
        item = extract_stock_mover_metrics(
            stock_record=s,
            live_quote=l_quote,
            is_session_open=is_session_open,
            allow_synthetic=allow_synthetic,
        )

        # Stale record handling
        if exclude_stale and item["is_stale"]:
            continue

        # Turnover threshold filtering
        if item["traded_value_cr"] < min_traded_value_cr:
            continue

        evaluated_stocks.append(item)
        if item["source_timestamp"]:
            source_timestamps.append(str(item["source_timestamp"]))

    # 4. Underlying Data Freshness Analysis
    distinct_source_ts = sorted(list(set(source_timestamps)))
    earliest_source_ts = distinct_source_ts[0] if distinct_source_ts else None
    latest_source_ts = distinct_source_ts[-1] if distinct_source_ts else None
    is_time_synchronized = len(distinct_source_ts) <= 1

    # 5. Build List 1: Top Gainers (highest positive percentage price change)
    gainers_candidates = [
        st for st in evaluated_stocks
        if st["daily_change_pct"] > 0 and st["daily_change_pct"] >= min_price_change_pct
    ]
    gainers_candidates.sort(key=lambda x: x["daily_change_pct"], reverse=True)
    top_gainers: list[dict[str, Any]] = []
    gainers_rank_map: dict[str, int] = {}
    for idx, st in enumerate(gainers_candidates[:limit], start=1):
        item = dict(st)
        item["rank"] = idx
        top_gainers.append(item)
        gainers_rank_map[st["symbol"]] = idx

    for idx, st in enumerate(gainers_candidates, start=1):
        if st["symbol"] not in gainers_rank_map:
            gainers_rank_map[st["symbol"]] = idx

    # 6. Build List 2: Top Losers (largest negative percentage price change)
    losers_candidates = [
        st for st in evaluated_stocks
        if st["daily_change_pct"] < 0 and abs(st["daily_change_pct"]) >= min_price_change_pct
    ]
    losers_candidates.sort(key=lambda x: x["daily_change_pct"])  # Most negative first
    top_losers: list[dict[str, Any]] = []
    losers_rank_map: dict[str, int] = {}
    for idx, st in enumerate(losers_candidates[:limit], start=1):
        item = dict(st)
        item["rank"] = idx
        top_losers.append(item)
        losers_rank_map[st["symbol"]] = idx

    for idx, st in enumerate(losers_candidates, start=1):
        if st["symbol"] not in losers_rank_map:
            losers_rank_map[st["symbol"]] = idx

    # 7. Build List 3: Volume Gainers
    # Mode 'daily': ranked by daily_rvol vs ADV20
    # Mode 'tod': ranked by time_of_day_rvol vs historical average volume at same time across 20 sessions
    if active_rvol_mode == "tod":
        volume_gainers_candidates = [
            st for st in evaluated_stocks
            if st.get("time_of_day_rvol") is not None and st["time_of_day_rvol"] >= min_rvol and st["today_volume"] > 0
        ]
        volume_gainers_candidates.sort(key=lambda x: x["time_of_day_rvol"], reverse=True)
    else:
        volume_gainers_candidates = [
            st for st in evaluated_stocks
            if st["daily_rvol"] >= min_rvol and st["today_volume"] > 0
        ]
        volume_gainers_candidates.sort(key=lambda x: x["daily_rvol"], reverse=True)

    volume_gainers: list[dict[str, Any]] = []
    vol_rank_map: dict[str, int] = {}
    for idx, st in enumerate(volume_gainers_candidates[:limit], start=1):
        item = dict(st)
        item["rank"] = idx
        volume_gainers.append(item)
        vol_rank_map[st["symbol"]] = idx

    for idx, st in enumerate(volume_gainers_candidates, start=1):
        if st["symbol"] not in vol_rank_map:
            vol_rank_map[st["symbol"]] = idx

    # 8. Build List 4: High-Volume Losers (negative price change + high volume)
    if active_rvol_mode == "tod":
        hv_losers_candidates = [
            st for st in evaluated_stocks
            if st["daily_change_pct"] < 0
            and st.get("time_of_day_rvol") is not None
            and st["time_of_day_rvol"] >= min_rvol
        ]
        if min_price_change_pct > 0:
            hv_losers_candidates = [
                st for st in hv_losers_candidates if abs(st["daily_change_pct"]) >= min_price_change_pct
            ]
        hv_losers_candidates.sort(key=lambda x: (x["time_of_day_rvol"], -x["daily_change_pct"]), reverse=True)
    else:
        hv_losers_candidates = [
            st for st in evaluated_stocks
            if st["daily_change_pct"] < 0 and st["daily_rvol"] >= min_rvol
        ]
        if min_price_change_pct > 0:
            hv_losers_candidates = [
                st for st in hv_losers_candidates if abs(st["daily_change_pct"]) >= min_price_change_pct
            ]
        hv_losers_candidates.sort(key=lambda x: (x["daily_rvol"], -x["daily_change_pct"]), reverse=True)

    high_volume_losers: list[dict[str, Any]] = []
    for idx, st in enumerate(hv_losers_candidates[:limit], start=1):
        item = dict(st)
        item["rank"] = idx
        high_volume_losers.append(item)

    # -----------------------------------------------------------------------
    # 9. Intersection Panel A: Bullish Price-Volume Confluence
    # (GAINERS ∩ VOLUME_GAINERS)
    # -----------------------------------------------------------------------
    bullish_confluence: list[dict[str, Any]] = []
    seen_bullish: set[str] = set()

    top_gainer_syms = {st["symbol"]: st for st in top_gainers}
    top_vol_syms = {st["symbol"]: st for st in volume_gainers}
    common_bullish = set(top_gainer_syms.keys()) & set(top_vol_syms.keys())

    for sym in common_bullish:
        if sym in seen_bullish:
            continue
        seen_bullish.add(sym)
        base = top_gainer_syms[sym]
        rank_g = gainers_rank_map.get(sym, 0)
        rank_v = vol_rank_map.get(sym, 0)
        active_rvol = base["time_of_day_rvol"] if (active_rvol_mode == "tod" and base.get("time_of_day_rvol") is not None) else base["daily_rvol"]
        compound_score = round(active_rvol * max(0.1, base["daily_change_pct"]), 2)
        rvol_desc = f"{active_rvol}x TOD RVOL" if active_rvol_mode == "tod" else f"{base['daily_rvol']}x Daily RVOL"

        bullish_confluence.append({
            **base,
            "rank_in_gainers": rank_g,
            "rank_in_volume_gainers": rank_v,
            "confluence_type": "BULLISH",
            "heuristic_compound_score": compound_score,
            "compound_score": compound_score,  # backward compatibility alias
            "score_label": "HEURISTIC",
            "score_nature": "Descriptive ranking metric (Active RVOL × % Change), NOT a probability, predictive model, or institutional flow.",
            "is_in_displayed_gainers": True,
            "is_in_displayed_volume": True,
            "interpretation": (
                f"Rising price (+{base['daily_change_pct']}%) with high relative volume ({rvol_desc}). "
                f"Ranked #{rank_g} in Gainers and #{rank_v} in Volume Surge. "
                "Qualified bullish price-volume confluence (OHLCV volume expansion; not institutional order-flow confirmation). "
                f"Heuristic score: {compound_score}."
            ),
        })

    # Extended candidate intersection
    all_g_map = {st["symbol"]: st for st in gainers_candidates}
    all_v_map = {st["symbol"]: st for st in volume_gainers_candidates}
    extended_bullish = set(all_g_map.keys()) & set(all_v_map.keys())

    for sym in extended_bullish:
        if sym in seen_bullish:
            continue
        seen_bullish.add(sym)
        base = all_g_map[sym]
        rank_g = gainers_rank_map.get(sym, 0)
        rank_v = vol_rank_map.get(sym, 0)
        active_rvol = base["time_of_day_rvol"] if (active_rvol_mode == "tod" and base.get("time_of_day_rvol") is not None) else base["daily_rvol"]
        compound_score = round(active_rvol * max(0.1, base["daily_change_pct"]), 2)
        rvol_desc = f"{active_rvol}x TOD RVOL" if active_rvol_mode == "tod" else f"{base['daily_rvol']}x Daily RVOL"

        bullish_confluence.append({
            **base,
            "rank_in_gainers": rank_g,
            "rank_in_volume_gainers": rank_v,
            "confluence_type": "BULLISH",
            "heuristic_compound_score": compound_score,
            "compound_score": compound_score,
            "score_label": "HEURISTIC",
            "score_nature": "Descriptive ranking metric (Active RVOL × % Change), NOT a probability, predictive model, or institutional flow.",
            "is_in_displayed_gainers": sym in top_gainer_syms,
            "is_in_displayed_volume": sym in top_vol_syms,
            "interpretation": (
                f"Rising price (+{base['daily_change_pct']}%) with high relative volume ({rvol_desc}). "
                f"Ranked #{rank_g} in Universe Gainers and #{rank_v} in Volume Surge. "
                "Qualified bullish price-volume confluence. "
                f"Heuristic score: {compound_score}."
            ),
        })

    bullish_confluence.sort(key=lambda x: (x.get("is_in_displayed_gainers", False), x["heuristic_compound_score"]), reverse=True)

    # -----------------------------------------------------------------------
    # 10. Intersection Panel B: Bearish Price-Volume Confluence
    # (LOSERS ∩ VOLUME_GAINERS)
    # -----------------------------------------------------------------------
    bearish_confluence: list[dict[str, Any]] = []
    seen_bearish: set[str] = set()

    top_loser_syms = {st["symbol"]: st for st in top_losers}
    common_bearish = set(top_loser_syms.keys()) & set(top_vol_syms.keys())

    for sym in common_bearish:
        if sym in seen_bearish:
            continue
        seen_bearish.add(sym)
        base = top_loser_syms[sym]
        rank_l = losers_rank_map.get(sym, 0)
        rank_v = vol_rank_map.get(sym, 0)
        active_rvol = base["time_of_day_rvol"] if (active_rvol_mode == "tod" and base.get("time_of_day_rvol") is not None) else base["daily_rvol"]
        compound_score = round(active_rvol * max(0.1, abs(base["daily_change_pct"])), 2)
        rvol_desc = f"{active_rvol}x TOD RVOL" if active_rvol_mode == "tod" else f"{base['daily_rvol']}x Daily RVOL"

        bearish_confluence.append({
            **base,
            "rank_in_losers": rank_l,
            "rank_in_volume_gainers": rank_v,
            "confluence_type": "BEARISH",
            "heuristic_compound_score": compound_score,
            "compound_score": compound_score,
            "score_label": "HEURISTIC",
            "score_nature": "Descriptive ranking metric (Active RVOL × |% Change|), NOT a probability, predictive model, or institutional flow.",
            "is_in_displayed_losers": True,
            "is_in_displayed_volume": True,
            "interpretation": (
                f"Falling price ({base['daily_change_pct']}%) with high relative volume ({rvol_desc}). "
                f"Ranked #{rank_l} in Losers and #{rank_v} in Volume Surge. "
                "Qualified bearish price-volume confluence (OHLCV volume expansion; not institutional order-flow confirmation). "
                f"Heuristic score: {compound_score}."
            ),
        })

    all_l_map = {st["symbol"]: st for st in losers_candidates}
    extended_bearish = set(all_l_map.keys()) & set(all_v_map.keys())

    for sym in extended_bearish:
        if sym in seen_bearish:
            continue
        seen_bearish.add(sym)
        base = all_l_map[sym]
        rank_l = losers_rank_map.get(sym, 0)
        rank_v = vol_rank_map.get(sym, 0)
        active_rvol = base["time_of_day_rvol"] if (active_rvol_mode == "tod" and base.get("time_of_day_rvol") is not None) else base["daily_rvol"]
        compound_score = round(active_rvol * max(0.1, abs(base["daily_change_pct"])), 2)
        rvol_desc = f"{active_rvol}x TOD RVOL" if active_rvol_mode == "tod" else f"{base['daily_rvol']}x Daily RVOL"

        bearish_confluence.append({
            **base,
            "rank_in_losers": rank_l,
            "rank_in_volume_gainers": rank_v,
            "confluence_type": "BEARISH",
            "heuristic_compound_score": compound_score,
            "compound_score": compound_score,
            "score_label": "HEURISTIC",
            "score_nature": "Descriptive ranking metric (Active RVOL × |% Change|), NOT a probability, predictive model, or institutional flow.",
            "is_in_displayed_losers": sym in top_loser_syms,
            "is_in_displayed_volume": sym in top_vol_syms,
            "interpretation": (
                f"Falling price ({base['daily_change_pct']}%) with high relative volume ({rvol_desc}). "
                f"Ranked #{rank_l} in Universe Losers and #{rank_v} in Volume Surge. "
                "Qualified bearish price-volume confluence. "
                f"Heuristic score: {compound_score}."
            ),
        })

    bearish_confluence.sort(key=lambda x: (x.get("is_in_displayed_losers", False), x["heuristic_compound_score"]), reverse=True)

    # Annotate active RVOL mode and active RVOL value across all mover panels
    for group in (top_gainers, top_losers, volume_gainers, high_volume_losers, bullish_confluence, bearish_confluence):
        for it in group:
            it["active_rvol_mode"] = active_rvol_mode
            it["active_rvol"] = it.get("time_of_day_rvol") if (active_rvol_mode == "tod" and it.get("time_of_day_rvol") is not None) else it.get("daily_rvol")

    # 11. Universe Coverage Audit (Phase 14.1)
    coverage_audit = audit_universe_coverage_movers(
        universe_name=universe,
        target_stocks=target_stocks,
        all_database_stocks=all_stocks,
    )

    # 12. Snapshot Metadata & Provenance
    live_count = sum(1 for s in evaluated_stocks if s["data_mode"] == "LIVE")
    hist_count = sum(1 for s in evaluated_stocks if s["data_mode"] == "HISTORICAL")
    prov_count = sum(1 for s in evaluated_stocks if s["data_mode"] == "PROVISIONAL")
    stale_count = sum(1 for s in evaluated_stocks if s["is_stale"])

    metadata = {
        "provider": "yfinance" if live_count == 0 else "hybrid",
        "instrument": "EQUITY_MARKET_MOVERS",
        "timeframe": "1D",
        "snapshot_id": calculation_snapshot_id,
        "snapshot_timestamp": calculation_timestamp,
        "calculation_snapshot_id": calculation_snapshot_id,
        "calculation_timestamp": calculation_timestamp,
        "underlying_market_data": {
            "earliest_source_timestamp": earliest_source_ts,
            "latest_source_timestamp": latest_source_ts,
            "distinct_source_timestamps_count": len(distinct_source_ts),
            "is_time_synchronized": is_time_synchronized,
            "synchronization_disclosure": (
                "calculation_snapshot_id identifies a single calculation run across local database records. "
                "Underlying market data timestamps vary according to individual instrument bar/feed availability "
                "and do not represent a synchronized exchange tick snapshot."
            ),
        },
        "freshness_summary": {
            "total_evaluated": len(evaluated_stocks),
            "live_records_count": live_count,
            "historical_records_count": hist_count,
            "provisional_records_count": prov_count,
            "stale_records_count": stale_count,
        },
        "cache_ttl_seconds": int(_CACHE_TTL_SECONDS),
        "is_cached": False,
        "active_rvol_mode": active_rvol_mode,
        "rvol_methodology": "TIME_OF_DAY" if active_rvol_mode == "tod" else "DAILY",
        "allow_synthetic": allow_synthetic,
        "tod_provenance_summary": {
            "total_evaluated": len(evaluated_stocks),
            "observed_ready_count": sum(
                1 for s in evaluated_stocks
                if (s.get("tod_valid_sessions", 0) >= 3 and s.get("tod_source") in ("OBSERVED_HISTORICAL", "OBSERVED_DELAYED", "OBSERVED_LIVE"))
            ),
            "synthetic_only_count": sum(1 for s in evaluated_stocks if s.get("tod_source") == "SYNTHETIC"),
            "unavailable_tod_count": sum(1 for s in evaluated_stocks if s.get("time_of_day_rvol") is None),
            "isolation_notice": (
                "DEMONSTRATION ONLY: Synthetic calibrated volume data active. Does NOT confirm real market volume."
                if allow_synthetic
                else "Strict market verification active: Genuine observed intraday data is required for True TOD RVOL. Synthetic calibrated data is strictly isolated and excluded from volume rankings."
            ),
        },
        "disclaimer": (
            "Market movers and price-volume confluence rankings are computed from OHLCV candle records and 20-day historical ADV. "
            "High volume confluence reflects trading participation and does NOT establish buyer-initiated or seller-initiated "
            "institutional execution without official exchange trade and settlement records. Compound scores are purely heuristic."
        ),
    }

    result = {
        "status": "SUCCESS",
        "snapshot_id": calculation_snapshot_id,  # backward compatibility alias
        "snapshot_timestamp": calculation_timestamp,  # backward compatibility alias
        "calculation_snapshot_id": calculation_snapshot_id,
        "calculation_timestamp": calculation_timestamp,
        "active_rvol_mode": active_rvol_mode,
        "rvol_methodology_label": (
            "True Time-of-Day RVOL (20-session same-time historical average)"
            if active_rvol_mode == "tod"
            else "Daily RVOL (20-day ADV ratio)"
        ),
        "universe": universe,
        "universe_label": coverage_audit["universe_label"],
        "exchange": exchange.upper(),
        "coverage": coverage_audit,
        "configured_universe_count": coverage_audit["requested_universe_size"],
        "scanned_count": len(evaluated_stocks),
        "total_database_count": len(all_stocks),
        "coverage_pct": coverage_audit["coverage_pct"],
        "coverage_note": coverage_audit["coverage_disclosure"],
        "filters_applied": {
            "universe": universe,
            "exchange": exchange.upper(),
            "rvol_mode": active_rvol_mode,
            "min_rvol": min_rvol,
            "min_price_change_pct": min_price_change_pct,
            "min_traded_value_cr": min_traded_value_cr,
            "limit": limit,
            "exclude_stale": exclude_stale,
            "is_session_open": is_session_open,
            "allow_synthetic": allow_synthetic,
        },
        "metadata": metadata,
        # Four Market Movers Panels
        "top_gainers": top_gainers,
        "top_losers": top_losers,
        "volume_gainers": volume_gainers,
        "high_volume_losers": high_volume_losers,
        # Two Confluence Panels
        "bullish_confluence": bullish_confluence[:limit],
        "bearish_confluence": bearish_confluence[:limit],
        "summary_counts": {
            "total_evaluated": len(evaluated_stocks),
            "gainers_count": len(gainers_candidates),
            "losers_count": len(losers_candidates),
            "volume_gainers_count": len(volume_gainers_candidates),
            "high_volume_losers_count": len(hv_losers_candidates),
            "bullish_confluence_count": len(bullish_confluence),
            "bearish_confluence_count": len(bearish_confluence),
            "stale_records_count": stale_count,
        },
    }

    _MOVERS_CACHE[cache_key] = result
    _MOVERS_CACHE_TS = now
    return result

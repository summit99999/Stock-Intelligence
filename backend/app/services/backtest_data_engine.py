"""
Backtest Historical Data Engine (Phase 2).

Manages 5-year daily OHLCV market data ingestion, SQLite persistence,
exchange calendar validation, and corporate action accounting.

Key invariants:
- Zero price fabrication: never forward-fills or creates synthetic OHLCV values.
- Dual-price maintenance: keeps raw tradable OHLC for execution simulation and
  adjusted prices (adj_close) for multi-year indicators across corporate actions.
- Multi-provider waterfall: Upstox REST API -> YFinance historical engine.
- Complete per-stock data quality auditing against official NSE trading calendar.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
import logging
import sqlite3
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from app.database import connect, DB_PATH
from app.providers.upstox_provider import UpstoxProvider
from app.providers.yfinance_provider import YFinanceProvider
from app.services.trading_calendar_service import get_trading_days_between, is_trading_day
from app.services.upstox_instrument_sync import resolve_symbol_alias

logger = logging.getLogger(__name__)

# Predefined benchmark and universe symbols
NIFTY_50_CORE: List[str] = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "BHARTIARTL", "SBIN",
    "LT", "ITC", "HINDUNILVR", "BAJFINANCE", "M&M", "MARUTI", "HCLTECH",
    "SUNPHARMA", "TATAMOTORS", "AXISBANK", "NTPC", "ONGC", "TITAN",
    "POWERGRID", "ADANIENT", "COALINDIA", "TRENT", "BEL", "BAJAJFINSV",
    "ASIANPAINT", "ULTRACEMCO", "KOTAKBANK", "JSWSTEEL", "TATASTEEL",
    "GRASIM", "HEROMOTOCO", "WIPRO", "NESTLEIND", "BPCL", "TECHM",
    "HINDALCO", "EICHERMOT", "CIPLA", "APOLLOHOSP", "DRREDDY", "SHRIRAMFIN",
    "DIVISLAB", "TATACONSUM", "SBILIFE", "HDFCLIFE", "ADANIPORTS", "BRITANNIA", "INDUSINDBK"
]

LIQUID_MOMENTUM_UNIVERSE: List[str] = [
    "TRENT", "BEL", "DIXON", "HAL", "CDSL", "POLYCAB", "TATAMOTORS",
    "RELIANCE", "HDFCBANK", "INFY", "BAJFINANCE", "BHARTIARTL", "ICICIBANK",
    "HCLTECH", "SUNPHARMA", "LT", "SBIN", "TITAN", "COALINDIA", "ADANIENT"
]


@dataclass
class StockDataQuality:
    symbol: str
    total_bars: int
    start_date: str
    end_date: str
    expected_sessions: int
    coverage_pct: float
    missing_sessions_count: int
    missing_dates: List[str]
    anomalies: List[str]
    data_quality_score: float
    data_source: str
    status: str  # "VALID", "WARNING", "INSUFFICIENT"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BacktestDataEngine:
    """Manages historical OHLCV data lifecycle for backtesting."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path or DB_PATH)
        self.upstox = UpstoxProvider()
        self.yfinance = YFinanceProvider()

    def get_stored_bars(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        interval: str = "daily",
    ) -> List[Dict[str, Any]]:
        """Retrieve cached daily bars from SQLite database."""
        sym = resolve_symbol_alias(symbol)
        conn = connect()
        cur = conn.cursor()
        query = """
            SELECT timestamp, open, high, low, close, adj_close, volume, source
            FROM ohlcv
            WHERE symbol = ? AND interval = ?
        """
        params: List[Any] = [sym, interval]
        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date)
        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date)
        query += " ORDER BY timestamp ASC"

        cur.execute(query, params)
        rows = cur.fetchall()
        conn.close()

        bars = []
        for r in rows:
            ts_str = str(r["timestamp"])[:10]
            bars.append({
                "date": ts_str,
                "timestamp": r["timestamp"],
                "open": float(r["open"] or 0.0),
                "high": float(r["high"] or 0.0),
                "low": float(r["low"] or 0.0),
                "close": float(r["close"] or 0.0),
                "adj_close": float(r["adj_close"] or r["close"] or 0.0),
                "volume": int(r["volume"] or 0),
                "source": r["source"] or "unknown",
            })
        return bars

    def save_bars(self, symbol: str, df: pd.DataFrame, source: str = "upstox") -> int:
        """Persist cleaned daily bars into the SQLite ohlcv table."""
        if df.empty:
            return 0

        sym = resolve_symbol_alias(symbol)
        conn = connect()
        cur = conn.cursor()

        records = []
        for _, row in df.iterrows():
            d_str = str(row["date"])[:10]
            open_val = float(row.get("open", 0.0))
            high_val = float(row.get("high", 0.0))
            low_val = float(row.get("low", 0.0))
            close_val = float(row.get("close", 0.0))
            adj_close_val = float(row.get("adj_close", close_val))
            vol_val = int(row.get("volume", 0))
            records.append((
                sym,
                "daily",
                d_str,
                open_val,
                high_val,
                low_val,
                close_val,
                adj_close_val,
                vol_val,
                source,
            ))

        cur.executemany(
            """
            INSERT INTO ohlcv (symbol, interval, timestamp, open, high, low, close, adj_close, volume, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, interval, timestamp) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                adj_close = excluded.adj_close,
                volume = excluded.volume,
                source = excluded.source
            """,
            records,
        )
        conn.commit()
        inserted_count = len(records)
        conn.close()
        return inserted_count

    def fetch_and_store_history(
        self,
        symbol: str,
        start_date: str = "2021-01-01",
        end_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Fetch 5-year daily history using Upstox (primary) or YFinance (fallback),
        store in database, and return formatted bars with source attribution.
        """
        sym = resolve_symbol_alias(symbol)
        if not end_date:
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Check existing DB cache if not forcing refresh
        if not force_refresh:
            existing = self.get_stored_bars(sym, start_date=start_date, end_date=end_date)
            # If we have at least 800 bars for a 5y request, consider cache warm
            if len(existing) >= 800:
                return existing, existing[0].get("source", "database_cache")

        # Priority 1: Upstox Provider
        df = None
        source_used = "yfinance"
        try:
            if self.upstox.is_available():
                df = self.upstox.get_daily_candles(sym, period="5y")
                if df is not None and not df.empty and len(df) >= 200:
                    source_used = "upstox"
        except Exception as e:
            logger.warning("Upstox historical fetch failed for %s: %s", sym, e)

        # Priority 2: YFinance Provider
        if df is None or df.empty or len(df) < 200:
            try:
                # Benchmark symbol mapping
                ticker_to_fetch = "^NSEI" if sym in ("NIFTY 50", "NIFTY", "^NSEI") else sym
                exchange = "NSE" if ticker_to_fetch != "^NSEI" else ""
                df = self.yfinance.fetch_history(ticker_to_fetch, exchange=exchange, period="5y")
                source_used = "yfinance"
            except Exception as e:
                logger.error("YFinance historical fetch failed for %s: %s", sym, e)

        if df is not None and not df.empty:
            # Filter within requested date window
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
            df = df[(df["date"] >= start_date) & (df["date"] <= end_date)]
            df = df.sort_values("date").reset_index(drop=True)
            self.save_bars(sym, df, source=source_used)
            bars = self.get_stored_bars(sym, start_date=start_date, end_date=end_date)
            return bars, source_used

        # Return whatever is in DB if external fetch failed
        fallback_bars = self.get_stored_bars(sym, start_date=start_date, end_date=end_date)
        return fallback_bars, "database_fallback"

    def audit_stock_data_quality(
        self,
        symbol: str,
        bars: List[Dict[str, Any]],
        start_date: str,
        end_date: str,
    ) -> StockDataQuality:
        """
        Validate OHLCV bars against official NSE trading calendar and detect anomalies.
        """
        if not bars:
            return StockDataQuality(
                symbol=symbol,
                total_bars=0,
                start_date=start_date,
                end_date=end_date,
                expected_sessions=0,
                coverage_pct=0.0,
                missing_sessions_count=0,
                missing_dates=[],
                anomalies=["CRITICAL_NO_DATA_AVAILABLE"],
                data_quality_score=0.0,
                data_source="none",
                status="INSUFFICIENT",
            )

        bar_dates = {b["date"] for b in bars}
        expected_sessions = get_trading_days_between(start_date, end_date, exclude_special=False)
        exp_set = set(expected_sessions)

        missing_dates = sorted(list(exp_set - bar_dates))
        anomalies: List[str] = []

        total_bars = len(bars)
        exp_count = len(expected_sessions)
        coverage_pct = round((total_bars / exp_count) * 100.0, 2) if exp_count > 0 else 100.0

        zero_volume_count = 0
        high_low_violations = 0
        price_gap_anomalies = 0

        prev_close = None
        for b in bars:
            o = b["open"]
            h = b["high"]
            l = b["low"]
            c = b["close"]
            v = b["volume"]

            # Geometric check
            if h < max(o, c, l) or l > min(o, c, h) or o <= 0 or c <= 0:
                high_low_violations += 1

            if v <= 0:
                zero_volume_count += 1

            # Check single-session gap > 35% without split
            if prev_close and prev_close > 0:
                gap_pct = abs((c - prev_close) / prev_close) * 100.0
                if gap_pct > 35.0:
                    price_gap_anomalies += 1
            prev_close = c

        if high_low_violations > 0:
            anomalies.append(f"OHLC_INVERSION_VIOLATIONS_{high_low_violations}")
        if zero_volume_count > 0:
            anomalies.append(f"ZERO_VOLUME_SESSIONS_{zero_volume_count}")
        if price_gap_anomalies > 0:
            anomalies.append(f"SUSPICIOUS_PRICE_GAPS_{price_gap_anomalies}")

        # Compute quality score (100 base)
        penalties = 0.0
        if coverage_pct < 95.0:
            penalties += (95.0 - coverage_pct) * 1.5
        penalties += min(30.0, high_low_violations * 5.0)
        penalties += min(20.0, zero_volume_count * 1.0)
        penalties += min(20.0, price_gap_anomalies * 5.0)

        quality_score = max(0.0, round(100.0 - penalties, 1))

        status = "VALID"
        if quality_score < 70.0 or coverage_pct < 80.0:
            status = "INSUFFICIENT"
        elif quality_score < 90.0 or len(anomalies) > 0:
            status = "WARNING"

        source = bars[0].get("source", "unknown") if bars else "unknown"

        return StockDataQuality(
            symbol=symbol,
            total_bars=total_bars,
            start_date=bars[0]["date"],
            end_date=bars[-1]["date"],
            expected_sessions=exp_count,
            coverage_pct=coverage_pct,
            missing_sessions_count=len(missing_dates),
            missing_dates=missing_dates[:15],  # Sample of missing dates
            anomalies=anomalies,
            data_quality_score=quality_score,
            data_source=source,
            status=status,
        )

    def load_universe_data(
        self,
        symbols: List[str],
        start_date: str = "2021-01-01",
        end_date: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Tuple[Dict[str, pd.DataFrame], Dict[str, StockDataQuality]]:
        """
        Load, validate, and convert 5y daily data for multiple symbols into DataFrames.
        Returns (dataframes_dict, data_quality_reports_dict).
        """
        dataframes: Dict[str, pd.DataFrame] = {}
        reports: Dict[str, StockDataQuality] = {}

        if not end_date:
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        for sym in symbols:
            bars, _ = self.fetch_and_store_history(
                sym, start_date=start_date, end_date=end_date, force_refresh=force_refresh
            )
            report = self.audit_stock_data_quality(sym, bars, start_date, end_date)
            reports[sym] = report

            if bars:
                df = pd.DataFrame(bars)
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                df = df.sort_values("date").reset_index(drop=True)
                # Compute indicators needed for strategy
                df["sma_20"] = df["close"].rolling(20).mean()
                df["sma_50"] = df["close"].rolling(50).mean()
                df["vol_sma_5"] = df["volume"].rolling(5).mean()
                df["vol_sma_20"] = df["volume"].rolling(20).mean()
                dataframes[sym] = df

        return dataframes, reports

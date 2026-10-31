"""
Market data service — orchestrates data downloads, indicator calculations,
and database updates.

This is the main entry point for fetching and processing market data.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.database import (
    get_all_symbols,
    get_bars,
    get_data_update,
    get_latest_bar_date,
    get_ohlcv_count,
    update_stock_fields,
    upsert_data_update,
    upsert_ohlcv,
)
from app.providers.manager import get_provider_manager
from app.services.indicators import calculate_all_indicators

logger = logging.getLogger(__name__)


def update_stock_data(
    symbol: str,
    exchange: str = "NSE",
    period: str = "1y",
    force: bool = False,
) -> dict:
    """
    Download historical data for a single stock and update the database.

    Uses incremental updates: if data exists, only fetches from the last
    cached date onward (unless ``force=True``).

    Returns a status dict.
    """
    mgr = get_provider_manager()
    if not mgr.active_provider:
        return {"symbol": symbol, "status": "error", "error": "No data provider available"}

    # Check if we already have recent data
    start_date: Optional[str] = None
    if not force:
        latest = get_latest_bar_date(symbol)
        if latest:
            # Only fetch from 1 day after the last cached date
            from datetime import date as _date
            last = _date.fromisoformat(latest)
            today = _date.today()
            if last >= today - timedelta(days=1):
                # Data is already up-to-date
                return {
                    "symbol": symbol,
                    "status": "cached",
                    "bars_count": get_ohlcv_count(symbol),
                    "latest_date": latest,
                    "message": "Data is already up-to-date",
                }
            start_date = (last + timedelta(days=1)).isoformat()

    # Fetch history
    try:
        df = mgr.fetch_history(symbol, exchange, period, start_date)
    except Exception as e:
        error_msg = f"Download failed: {e}"
        logger.error("update_stock_data(%s): %s", symbol, error_msg)
        upsert_data_update(symbol, "yfinance", status="error", error_message=error_msg)
        return {"symbol": symbol, "status": "error", "error": error_msg}

    if df is None or df.empty:
        msg = "No data returned by provider"
        upsert_data_update(symbol, "yfinance", status="no_data", error_message=msg)
        return {"symbol": symbol, "status": "no_data", "error": msg}

    # Convert to list of dicts and upsert
    bars = df.to_dict("records")
    rows_written = upsert_ohlcv(symbol, bars, source="yfinance")

    # Update tracking
    total_bars = get_ohlcv_count(symbol)
    upsert_data_update(
        symbol, "yfinance",
        bars_count=total_bars,
        period=period,
        status="ok",
    )

    # Now recalculate indicators from full OHLCV history
    _recalculate_indicators(symbol)

    return {
        "symbol": symbol,
        "status": "updated",
        "new_bars": rows_written,
        "total_bars": total_bars,
        "latest_date": get_latest_bar_date(symbol),
    }


def _recalculate_indicators(symbol: str) -> None:
    """Recalculate all technical indicators and update the stocks table."""
    all_bars = get_bars(symbol, "daily")
    if not all_bars or len(all_bars) < 2:
        return

    indicators = calculate_all_indicators(all_bars)
    if "error" in indicators:
        return

    # Map indicator keys to stocks-table columns
    fields: dict = {}
    direct_fields = [
        "close", "daily_change_pct",
        "rsi", "macd", "macd_signal", "adx",
        "supertrend", "supertrend_dir",
        "ema_20", "ema_50", "ema_100", "ema_200",
        "sma_20", "sma_50", "sma_100", "sma_200",
        "volume", "relative_volume",
        "week_52_high", "week_52_low",
        "return_1d_pct", "return_1w_pct", "return_1m_pct",
        "return_3m_pct", "return_6m_pct", "return_1y_pct",
    ]
    for k in direct_fields:
        if k in indicators and indicators[k] is not None:
            fields[k] = indicators[k]

    # Update metadata
    fields["data_source"] = "yfinance"
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    if fields:
        update_stock_fields(symbol, fields)


def batch_update(
    symbols: Optional[list[str]] = None,
    period: str = "1y",
    force: bool = False,
    job_id: Optional[str] = None,
) -> list[dict]:
    """
    Update data for multiple stocks.

    If ``symbols`` is None, updates all stocks in the master table.
    """
    if symbols is None:
        symbols = get_all_symbols()

    mgr = get_provider_manager()
    results: list[dict] = []

    for i, sym in enumerate(symbols):
        result = update_stock_data(sym, period=period, force=force)
        results.append(result)

        # Update job progress if tracking
        if job_id:
            mgr.update_job(
                job_id,
                completed_count=i + 1,
                failed_count=sum(1 for r in results if r["status"] == "error"),
                symbols_done=[r["symbol"] for r in results],
            )

        logger.info(
            "[%d/%d] %s: %s", i + 1, len(symbols), sym, result["status"]
        )

    # Mark job complete
    if job_id:
        mgr.update_job(
            job_id,
            status="completed",
            finished_at=datetime.now(timezone.utc).isoformat(),
        )

    return results


def start_background_update(
    symbols: Optional[list[str]] = None,
    period: str = "1y",
    force: bool = False,
) -> str:
    """
    Start a background thread to update market data.
    Returns the job ID immediately.
    """
    mgr = get_provider_manager()

    actual_symbols = symbols if symbols else get_all_symbols()
    job_id = mgr.create_job(actual_symbols)
    mgr.update_job(
        job_id,
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    def _worker():
        try:
            batch_update(actual_symbols, period, force, job_id)
        except Exception as e:
            logger.error("Background update failed: %s", e)
            mgr.update_job(
                job_id,
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                errors=[str(e)],
            )

    thread = threading.Thread(target=_worker, daemon=True, name=f"data-update-{job_id}")
    thread.start()

    return job_id

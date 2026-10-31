"""Pydantic schemas for market data endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class UpdateRequest(BaseModel):
    """Request to trigger a market-data update."""
    symbols: list[str] = Field(
        default_factory=list,
        description="Symbols to update. Empty = all stocks in the universe.",
    )
    period: str = Field(
        "1y",
        description="History period: 1mo, 3mo, 6mo, 1y, 2y, 3y, 5y",
    )
    force: bool = Field(
        False,
        description="Force re-download even if data is cached.",
    )


class UpdateResponse(BaseModel):
    """Response from a data-update request."""
    job_id: str
    status: str
    message: str
    symbols_count: int


class JobStatus(BaseModel):
    """Status of a background update job."""
    job_id: str
    status: str  # pending | running | completed | failed
    total: int
    completed_count: int
    failed_count: int
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    symbols_done: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class DataUpdateStatus(BaseModel):
    """Per-symbol data update status."""
    symbol: str
    provider: str
    last_updated: Optional[str] = None
    bars_count: int = 0
    period: Optional[str] = None
    status: str = "pending"
    error_message: Optional[str] = None


class MarketDataStatus(BaseModel):
    """Overall market data status."""
    provider_name: Optional[str] = None
    provider_data_type: Optional[str] = None
    provider_available: bool = False
    total_stocks: int = 0
    stocks_with_data: int = 0
    total_bars: int = 0
    updates: list[DataUpdateStatus] = Field(default_factory=list)


class OHLCVBar(BaseModel):
    """A single OHLCV bar."""
    date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    adj_close: Optional[float] = None
    volume: Optional[int] = None


class HistoryResponse(BaseModel):
    """Response for stock history endpoint."""
    symbol: str
    exchange: str
    bars: list[OHLCVBar]
    total_bars: int
    latest_date: Optional[str] = None
    data_source: str = "demo"
    notice: str = "Historical data — not live exchange prices."


class IndicatorsResponse(BaseModel):
    """Response for stock indicators endpoint."""
    symbol: str
    exchange: str
    indicators: dict
    bars_count: int = 0
    data_source: str = "demo"
    notice: str = "Indicators calculated from historical data."

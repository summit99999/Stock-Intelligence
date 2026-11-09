"""Pydantic schemas for Upstox Live Market Data (REST quotes and WebSocket feed)."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class LiveQuote(BaseModel):
    """Normalized live market quote for a stock or index."""
    symbol: str = Field(..., description="Trading symbol or index name (e.g. RELIANCE, NIFTY 50)")
    security_id: str = Field(..., description="Upstox instrument key, e.g. NSE_EQ|INE002A01018")
    exchange_segment: str = Field("NSE_EQ", description="Exchange segment, e.g. NSE_EQ, NSE_INDEX")
    ltp: float = Field(..., description="Last Traded Price")
    open: Optional[float] = Field(None, description="Day Open price")
    high: Optional[float] = Field(None, description="Day High price")
    low: Optional[float] = Field(None, description="Day Low price")
    close: Optional[float] = Field(None, description="Previous Day Close or Official Close")
    change: Optional[float] = Field(None, description="Net price change from previous close")
    change_percent: Optional[float] = Field(None, description="Percentage change from previous close")
    volume: Optional[int] = Field(None, description="Total traded volume")
    atp: Optional[float] = Field(None, description="Average Traded Price")
    ltt: Optional[str] = Field(None, description="Last Traded Time (ISO format or formatted string)")
    source: str = Field("LIVE", description="Data source indicator: LIVE, DELAYED, HISTORICAL, DEMO")
    updated_at: str = Field(..., description="Timestamp of when this quote was updated")


class LiveFeedStatus(BaseModel):
    """Status of the Upstox live market feed connection."""
    status: str = Field(
        ...,
        description="CONNECTED | DISCONNECTED | AUTHENTICATION_REQUIRED | CONNECTING | RATE_LIMITED | DISABLED",
    )
    authenticated: bool = Field(..., description="Whether a valid Upstox access token is present")
    live_data_enabled: bool = Field(True, description="Whether live market data is enabled in configuration")
    subscribed_symbols: list[str] = Field(default_factory=list, description="Currently subscribed symbols")
    subscribed_count: int = Field(0, description="Count of subscribed instruments")
    last_tick_time: Optional[str] = Field(None, description="Timestamp of most recent tick received")
    ticks_received: int = Field(0, description="Total number of tick messages processed")
    connected_clients: int = Field(0, description="Number of connected frontend WebSocket clients")
    error: Optional[str] = Field(None, description="Latest error message if any")
    retry_in_seconds: Optional[float] = Field(None, description="Seconds until next connection attempt if backing off")


class SubscribeRequest(BaseModel):
    """Request to subscribe to symbols for live market feed."""
    symbols: list[str] = Field(..., description="List of symbols or index names to subscribe")


class LiveQuotesResponse(BaseModel):
    """Response containing multiple live quotes."""
    quotes: dict[str, LiveQuote] = Field(default_factory=dict, description="Map of symbol -> LiveQuote")
    source: str = Field("LIVE", description="Predominant source: LIVE or DEMO")
    count: int = 0

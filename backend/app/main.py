"""
Stock Intelligence API — main application.
Personal research platform with zero-cost cloud deployment readiness,
dual SQLite/PostgreSQL storage, and private authentication support.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import get_auth_mode, get_current_user, is_auth_enabled
from app.config import get_upstox_config
from app.database import get_database_mode, init_db
from app.routers import (
    ai_planner,
    fundamentals,
    instruments,
    market_data,
    market_feed,
    market_intelligence,
    market_movers,
    money_flow,
    scanner,
    screener,
    smc,
    stocks,
    unified_research,
    upstox_auth,
    volume_analytics,
)
from app.services.upstox_ws_client import get_upstox_ws_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and graceful shutdown lifecycle manager."""
    logger.info("Initializing database (mode: %s)...", get_database_mode())
    init_db()

    # Populate verified NSE equity universe with official Upstox metadata & candles
    try:
        from app.services.upstox_instrument_sync import ensure_full_universe_seeded
        ensure_full_universe_seeded()
    except Exception as e:
        logger.warning("Could not auto-seed full NSE universe on startup: %s", e)

    # Start Upstox live market feed background task only if enabled in config
    upstox_cfg = get_upstox_config()
    if upstox_cfg.live_data_enabled:
        get_upstox_ws_client().start()
    else:
        # Client stays in DISABLED status; no connection or reconnection loop is started
        get_upstox_ws_client().set_disabled()

    yield

    logger.info("Stopping Upstox websocket client...")
    await get_upstox_ws_client().stop()


app = FastAPI(
    title="Stock Intelligence API",
    version="0.5.0",
    description="Personal Indian equity research platform. Cloud deployment with private authentication and dual-mode database.",
    lifespan=lifespan,
)

# CORS configuration
allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]
frontend_origin_env = os.getenv("FRONTEND_ORIGIN", "").strip()
if frontend_origin_env:
    for origin in frontend_origin_env.split(","):
        clean = origin.strip()
        if clean and clean not in allowed_origins:
            allowed_origins.append(clean)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*(\.pages\.dev|\.vercel\.app|\.onrender\.com|\.railway\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "name": "Stock Intelligence",
        "version": "0.3.0",
        "status": "running",
        "database_mode": get_database_mode(),
        "auth_mode": get_auth_mode(),
        "data_mode": "demo",
        "warning": "Sample data only; not live market data.",
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/system/status")
def system_status():
    return {
        "status": "ok",
        "database": get_database_mode(),
        "auth": get_auth_mode(),
        "version": "0.5.0",
    }


@app.get("/api/auth/status")
def auth_status(current_user: Dict[str, Any] = Depends(get_current_user)):
    return {
        "auth_enabled": is_auth_enabled(),
        "auth_mode": get_auth_mode(),
        "database_mode": get_database_mode(),
        "authenticated": True,
        "user_id": current_user.get("id"),
        "user_email": current_user.get("email"),
        "is_local_operator": current_user.get("is_local", False),
    }


# Include routers
app.include_router(stocks.router)
app.include_router(screener.router)
app.include_router(market_data.router)
app.include_router(upstox_auth.router)
app.include_router(fundamentals.router)
app.include_router(market_feed.router)
app.include_router(volume_analytics.router)
app.include_router(ai_planner.router)
app.include_router(smc.router)
app.include_router(scanner.router)
app.include_router(market_intelligence.router)
app.include_router(market_movers.router)
app.include_router(money_flow.router)
app.include_router(unified_research.router)
app.include_router(instruments.router)

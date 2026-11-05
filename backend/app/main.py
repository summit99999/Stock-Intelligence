"""
Stock Intelligence API — main application.
Personal research prototype. All demo data is clearly labelled.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_dhan_config
from app.database import init_db
from app.routers import (
    screener,
    stocks,
    market_data,
    dhan_auth,
    fundamentals,
    market_feed,
    volume_analytics,
    ai_planner,
    smc,
    scanner,
    market_intelligence,
    money_flow,
    unified_research,
)
from app.services.dhan_ws_client import get_dhan_ws_client

app = FastAPI(
    title="Stock Intelligence API",
    version="0.5.0",
    description="Personal Indian equity research platform. Live DhanHQ market feed with demo/historical fallback.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    # Start Dhan live market feed background task only if enabled in config
    dhan_cfg = get_dhan_config()
    if dhan_cfg.live_data_enabled:
        get_dhan_ws_client().start()
    else:
        # Client stays in DISABLED status; no connection or reconnection loop is started
        get_dhan_ws_client().set_disabled()


@app.on_event("shutdown")
async def shutdown():
    await get_dhan_ws_client().stop()


@app.get("/")
def root():
    return {
        "name": "Stock Intelligence",
        "version": "0.3.0",
        "status": "running",
        "data_mode": "demo",
        "warning": "Sample data only; not live market data.",
    }


@app.get("/api/health")
def health():
    return {"status": "ok"}


# Include routers
app.include_router(stocks.router)
app.include_router(screener.router)
app.include_router(market_data.router)
app.include_router(dhan_auth.router)
app.include_router(fundamentals.router)
app.include_router(market_feed.router)
app.include_router(volume_analytics.router)
app.include_router(ai_planner.router)
app.include_router(smc.router)
app.include_router(scanner.router)
app.include_router(market_intelligence.router)
app.include_router(money_flow.router)
app.include_router(unified_research.router)

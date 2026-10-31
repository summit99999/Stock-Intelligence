"""
Stock Intelligence API — main application.
Personal research prototype. All demo data is clearly labelled.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import screener, stocks, market_data

app = FastAPI(
    title="Stock Intelligence API",
    version="0.2.0",
    description="Personal Indian equity research platform. Demo data is clearly labelled.",
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


@app.get("/")
def root():
    return {
        "name": "Stock Intelligence",
        "version": "0.2.0",
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

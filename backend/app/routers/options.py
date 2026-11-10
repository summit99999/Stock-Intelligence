"""
NIFTY 50 & NSE Derivatives Options API Router.

Endpoints:
- GET /api/options/nifty/expiries: Available option contract expiries
- GET /api/options/nifty/chain: Real-time structured option chain with Calls/Puts, Greeks, PCR, and Max Pain
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Query

from app.services.nse_universe_service import (
    get_nifty_option_chain,
    get_nifty_option_expiries,
)

router = APIRouter(prefix="/api/options", tags=["options"])


@router.get("/nifty/expiries")
def nifty_expiries():
    """Get active expiry dates for NIFTY 50 options contracts."""
    expiries = get_nifty_option_expiries()
    return {"underlying": "NIFTY", "expiries": expiries, "count": len(expiries)}


@router.get("/nifty/chain")
def nifty_chain(
    expiry: Optional[str] = Query(None, description="Expiry date YYYY-MM-DD"),
    strike_range: int = Query(15, ge=5, le=50, description="Strikes above and below ATM"),
    spot: float = Query(24881.48, description="Underlying NIFTY index spot price"),
):
    """
    Get full NIFTY 50 option chain for a given expiry:
    - Strikes sorted ascending
    - Call and Put metrics side-by-side (LTP, OI, Volume, IV)
    - Black-Scholes Greeks (Delta, Gamma, Theta, Vega)
    - PCR (Put-Call Ratio)
    - Max Pain Strike
    - ATM Strike Indicator
    """
    chain_data = get_nifty_option_chain(
        expiry_date=expiry,
        strike_range=strike_range,
        spot_price=spot,
    )
    return chain_data

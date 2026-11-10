"""
Tests for NSE Universe Service and Options Chain Router.
"""

from app.routers.stocks import search_stocks
from app.routers.options import nifty_expiries, nifty_chain
from app.services.nse_universe_service import (
    search_nse_universe,
    get_nifty_option_chain,
    get_nifty_option_expiries,
    calculate_black_scholes_greeks,
)


def test_search_nse_universe():
    results = search_nse_universe("RELI", limit=10)
    assert len(results) > 0
    symbols = [r["symbol"] for r in results]
    assert "RELIANCE" in symbols
    assert results[0]["symbol"] == "RELIANCE"


def test_search_nse_universe_eternal():
    results = search_nse_universe("ETER", limit=5)
    assert len(results) > 0
    assert results[0]["symbol"] == "ETERNAL"
    assert results[0]["instrument_key"] == "NSE_EQ|INE758T01015"


def test_stocks_search_api():
    data = search_stocks(q="TRENT", limit=10)
    assert data["count"] > 0
    assert data["items"][0]["symbol"] == "TRENT"


def test_nifty_option_expiries_api():
    data = nifty_expiries()
    assert data["underlying"] == "NIFTY"
    assert len(data["expiries"]) > 0


def test_nifty_option_chain_api():
    data = nifty_chain(strike_range=10, spot=24881.48)
    assert data["underlying"] == "NIFTY"
    assert data["spot_price"] > 0
    assert data["atm_strike"] > 0
    assert data["pcr"] > 0
    assert len(data["chain"]) > 0
    first_strike = data["chain"][0]
    assert "strike_price" in first_strike
    assert "ce" in first_strike
    assert "pe" in first_strike


def test_black_scholes_greeks():
    greeks = calculate_black_scholes_greeks(
        spot=25000.0,
        strike=25000.0,
        time_to_expiry_years=30.0 / 365.0,
        rate=0.07,
        iv=0.15,
    )
    # ATM Call Delta ~ 0.50 - 0.58 (with r=7%), Put Delta = Call Delta - 1.0
    assert 0.45 <= greeks["ce"]["delta"] <= 0.60
    assert -0.55 <= greeks["pe"]["delta"] <= -0.40
    assert greeks["ce"]["gamma"] > 0
    assert greeks["pe"]["gamma"] > 0
    assert greeks["ce"]["theta"] < 0
    assert greeks["ce"]["vega"] > 0

import pytest
from app.services.canonical_market_data_service import CanonicalMarketDataService

def test_canonical_quote_schema():
    service = CanonicalMarketDataService()
    quote = service.get_quote("RELIANCE", exchange="NSE")
    assert isinstance(quote, dict)
    assert quote["symbol"] == "RELIANCE"
    assert quote["exchange"] == "NSE"
    assert quote["ltp"] > 0
    assert quote["prev_close"] > 0
    assert quote["is_valid"] is True
    # Verify strict math: change = ltp - prev_close
    assert round(quote["change"], 2) == round(quote["ltp"] - quote["prev_close"], 2)
    expected_pct = round(((quote["ltp"] - quote["prev_close"]) / quote["prev_close"]) * 100, 2)
    assert round(quote["change_pct"], 2) == expected_pct

def test_canonical_batch_quotes():
    service = CanonicalMarketDataService()
    symbols = ["RELIANCE", "TCS", "INFY"]
    quotes = service.get_quotes_batch(symbols, exchange="NSE")
    assert len(quotes) == 3
    for s in symbols:
        assert s in quotes
        assert quotes[s]["symbol"] == s
        assert quotes[s]["ltp"] > 0

def test_compare_providers():
    service = CanonicalMarketDataService()
    res = service.compare_providers("RELIANCE")
    assert "symbol" in res
    assert res["symbol"] == "RELIANCE"
    assert "canonical_quote" in res
    assert "database_master_close" in res
    assert "is_synchronized" in res

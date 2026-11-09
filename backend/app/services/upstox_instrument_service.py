"""Upstox Instrument Mapping and Resolution Service.

Maps NSE equities and indices to authoritative Upstox instrument keys:
- NSE Equities: 'NSE_EQ|{ISIN}' (e.g. 'NSE_EQ|INE002A01018' for RELIANCE)
- NSE Indices:  'NSE_INDEX|{Index Name}' (e.g. 'NSE_INDEX|Nifty 50')
- BSE Equities: 'BSE_EQ|{ISIN}'
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.services.instrument_master_service import get_instrument_master_service

logger = logging.getLogger(__name__)

INDEX_KEY_MAPPINGS: Dict[str, str] = {
    "NIFTY 50": "NSE_INDEX|Nifty 50",
    "NIFTY50": "NSE_INDEX|Nifty 50",
    "NIFTY BANK": "NSE_INDEX|Nifty Bank",
    "BANKNIFTY": "NSE_INDEX|Nifty Bank",
    "FINNIFTY": "NSE_INDEX|Nifty Fin Service",
    "SENSEX": "BSE_INDEX|SENSEX",
}


CANONICAL_INDEX_NAMES: Dict[str, str] = {
    "NSE_INDEX|Nifty 50": "NIFTY 50",
    "NSE_INDEX|Nifty Bank": "NIFTY BANK",
    "NSE_INDEX|Nifty Fin Service": "FINNIFTY",
    "BSE_INDEX|SENSEX": "SENSEX",
}


@dataclass
class UpstoxInstrument:
    symbol: str
    instrument_key: str
    company_name: str
    isin: str
    exchange_segment: str = "NSE_EQ"


class UpstoxInstrumentService:
    """Service to look up and resolve Upstox instrument keys."""

    def __init__(self):
        self._inst_master = get_instrument_master_service()
        self._key_to_symbol: Dict[str, str] = {}
        self._symbol_to_key: Dict[str, str] = {}
        self._init_mappings()

    def _init_mappings(self):
        """Populate initial cache from authoritative instrument universe and index mappings."""
        # Index mappings
        for name, key in INDEX_KEY_MAPPINGS.items():
            clean = name.upper()
            self._symbol_to_key[clean] = key
            if key in CANONICAL_INDEX_NAMES:
                self._key_to_symbol[key] = CANONICAL_INDEX_NAMES[key]
            elif key not in self._key_to_symbol:
                self._key_to_symbol[key] = clean

        # Equities from InstrumentMasterService
        try:
            instruments = self._inst_master.get_universe_reconciliation()
            for inst in instruments:
                sym = inst.get("symbol", "").upper()
                isin = inst.get("isin", "")
                if sym and isin:
                    key = f"NSE_EQ|{isin}"
                    self._symbol_to_key[sym] = key
                    self._key_to_symbol[key] = sym
                    # Also map historical symbols
                    for hist in inst.get("historical_symbols", []):
                        h_sym = hist.get("symbol") if isinstance(hist, dict) else str(hist)
                        if h_sym:
                            self._symbol_to_key[h_sym.upper()] = key
        except Exception as e:
            logger.warning("Could not pre-load instruments into UpstoxInstrumentService: %s", e)

    def get_instrument_key(self, symbol: str) -> Optional[str]:
        """Return the Upstox instrument key for a given symbol or index."""
        sym_clean = symbol.strip().upper()
        if sym_clean in self._symbol_to_key:
            return self._symbol_to_key[sym_clean]

        # Try resolving via instrument master
        inst = self._inst_master.resolve_instrument(sym_clean)
        if inst:
            isin = inst.get("isin") or inst.get("historical_isin")
            if isin:
                key = f"NSE_EQ|{isin}"
                self._symbol_to_key[sym_clean] = key
                self._key_to_symbol[key] = sym_clean
                return key

        return None

    def get_symbol_by_key(self, instrument_key: str) -> Optional[str]:
        """Reverse-resolve an Upstox instrument key to a canonical trading symbol."""
        if instrument_key in self._key_to_symbol:
            return self._key_to_symbol[instrument_key]

        # Extract ISIN from 'NSE_EQ|INE...'
        if "|" in instrument_key:
            _, isin = instrument_key.split("|", 1)
            inst = self._inst_master.resolve_instrument(isin)
            if inst and inst.get("symbol"):
                sym = inst["symbol"].upper()
                self._key_to_symbol[instrument_key] = sym
                return sym

        return None

    def get_instrument(self, symbol: str) -> Optional[UpstoxInstrument]:
        """Return UpstoxInstrument structure for symbol."""
        key = self.get_instrument_key(symbol)
        if not key:
            return None

        inst = self._inst_master.resolve_instrument(symbol)
        company_name = inst.get("company_name", symbol) if inst else symbol
        isin = inst.get("isin", "") if inst else ""
        segment = key.split("|")[0] if "|" in key else "NSE_EQ"

        return UpstoxInstrument(
            symbol=symbol.upper(),
            instrument_key=key,
            company_name=company_name,
            isin=isin,
            exchange_segment=segment,
        )


_instrument_service_instance: Optional[UpstoxInstrumentService] = None


def get_upstox_instrument_service() -> UpstoxInstrumentService:
    global _instrument_service_instance
    if _instrument_service_instance is None:
        _instrument_service_instance = UpstoxInstrumentService()
    return _instrument_service_instance

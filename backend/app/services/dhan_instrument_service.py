"""Dhan instrument lookup and scrip master management service.

Provides authoritative mapping between symbols (RELIANCE, TCS, NIFTY 50, etc.)
and Dhan exchange segments + security IDs.
"""

from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

SCRIP_MASTER_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "dhan_scrip_master.csv"
)


@dataclass
class DhanInstrument:
    """An instrument recognized by DhanHQ."""
    symbol: str
    security_id: str
    exchange: str
    exchange_segment: str
    display_name: str
    instrument_type: str = "EQUITY"
    tick_size: float = 0.05
    lot_size: int = 1
    series: Optional[str] = "EQ"


# Pre-mapped benchmark instruments (Validation set required by specification)
BENCHMARK_MAP: dict[str, DhanInstrument] = {
    "RELIANCE": DhanInstrument(
        symbol="RELIANCE",
        security_id="2885",
        exchange="NSE",
        exchange_segment="NSE_EQ",
        display_name="Reliance Industries",
        instrument_type="EQUITY",
    ),
    "TCS": DhanInstrument(
        symbol="TCS",
        security_id="11536",
        exchange="NSE",
        exchange_segment="NSE_EQ",
        display_name="Tata Consultancy Services",
        instrument_type="EQUITY",
    ),
    "HDFCBANK": DhanInstrument(
        symbol="HDFCBANK",
        security_id="1333",
        exchange="NSE",
        exchange_segment="NSE_EQ",
        display_name="HDFC Bank",
        instrument_type="EQUITY",
    ),
    "NIFTY": DhanInstrument(
        symbol="NIFTY",
        security_id="13",
        exchange="NSE",
        exchange_segment="IDX_I",
        display_name="Nifty 50",
        instrument_type="INDEX",
    ),
    "NIFTY 50": DhanInstrument(
        symbol="NIFTY 50",
        security_id="13",
        exchange="NSE",
        exchange_segment="IDX_I",
        display_name="Nifty 50",
        instrument_type="INDEX",
    ),
    "BANKNIFTY": DhanInstrument(
        symbol="BANKNIFTY",
        security_id="25",
        exchange="NSE",
        exchange_segment="IDX_I",
        display_name="Nifty Bank",
        instrument_type="INDEX",
    ),
    "BANK NIFTY": DhanInstrument(
        symbol="BANK NIFTY",
        security_id="25",
        exchange="NSE",
        exchange_segment="IDX_I",
        display_name="Nifty Bank",
        instrument_type="INDEX",
    ),
    "SENSEX": DhanInstrument(
        symbol="SENSEX",
        security_id="51",
        exchange="BSE",
        exchange_segment="IDX_I",
        display_name="BSE Sensex",
        instrument_type="INDEX",
    ),
    "INDIA VIX": DhanInstrument(
        symbol="INDIA VIX",
        security_id="21",
        exchange="NSE",
        exchange_segment="IDX_I",
        display_name="India VIX",
        instrument_type="INDEX",
    ),
    "INDIAVIX": DhanInstrument(
        symbol="INDIAVIX",
        security_id="21",
        exchange="NSE",
        exchange_segment="IDX_I",
        display_name="India VIX",
        instrument_type="INDEX",
    ),
}

# Complete 31 stock universe mapping for full coverage
UNIVERSE_MAP: dict[str, DhanInstrument] = {
    "ADANIENT": DhanInstrument("ADANIENT", "25", "NSE", "NSE_EQ", "Adani Enterprises"),
    "ASIANPAINT": DhanInstrument("ASIANPAINT", "236", "NSE", "NSE_EQ", "Asian Paints"),
    "BAJFINANCE": DhanInstrument("BAJFINANCE", "317", "NSE", "NSE_EQ", "Bajaj Finance"),
    "BEL": DhanInstrument("BEL", "383", "NSE", "NSE_EQ", "Bharat Electronics"),
    "BHARTIARTL": DhanInstrument("BHARTIARTL", "10604", "NSE", "NSE_EQ", "Bharti Airtel"),
    "CDSL": DhanInstrument("CDSL", "21174", "NSE", "NSE_EQ", "CDSL"),
    "COALINDIA": DhanInstrument("COALINDIA", "20374", "NSE", "NSE_EQ", "Coal India"),
    "DEEPAKNTR": DhanInstrument("DEEPAKNTR", "19943", "NSE", "NSE_EQ", "Deepak Nitrite"),
    "DIXON": DhanInstrument("DIXON", "21690", "NSE", "NSE_EQ", "Dixon Technologies"),
    "HAL": DhanInstrument("HAL", "2303", "NSE", "NSE_EQ", "Hindustan Aeronautics"),
    "HCLTECH": DhanInstrument("HCLTECH", "7229", "NSE", "NSE_EQ", "HCL Technologies"),
    "HDFCBANK": BENCHMARK_MAP["HDFCBANK"],
    "HINDUNILVR": DhanInstrument("HINDUNILVR", "1394", "NSE", "NSE_EQ", "Hindustan Unilever"),
    "ICICIBANK": DhanInstrument("ICICIBANK", "4963", "NSE", "NSE_EQ", "ICICI Bank"),
    "INFY": DhanInstrument("INFY", "1594", "NSE", "NSE_EQ", "Infosys"),
    "KPITTECH": DhanInstrument("KPITTECH", "9683", "NSE", "NSE_EQ", "KPIT Technologies"),
    "LT": DhanInstrument("LT", "11483", "NSE", "NSE_EQ", "Larsen & Toubro"),
    "LTIM": DhanInstrument("LTIM", "17818", "NSE", "NSE_EQ", "LTIMindtree"),
    "MARUTI": DhanInstrument("MARUTI", "10999", "NSE", "NSE_EQ", "Maruti Suzuki"),
    "ONGC": DhanInstrument("ONGC", "2475", "NSE", "NSE_EQ", "Oil & Natural Gas Corporation"),
    "POLYCAB": DhanInstrument("POLYCAB", "9590", "NSE", "NSE_EQ", "Polycab"),
    "POWERGRID": DhanInstrument("POWERGRID", "14977", "NSE", "NSE_EQ", "Power Grid Corp"),
    "RELIANCE": BENCHMARK_MAP["RELIANCE"],
    "SBIN": DhanInstrument("SBIN", "3045", "NSE", "NSE_EQ", "State Bank of India"),
    "SUNPHARMA": DhanInstrument("SUNPHARMA", "3351", "NSE", "NSE_EQ", "Sun Pharmaceutical"),
    "TATAELXSI": DhanInstrument("TATAELXSI", "3411", "NSE", "NSE_EQ", "Tata Elxsi"),
    "TATAMOTORS": DhanInstrument("TATAMOTORS", "3456", "NSE", "NSE_EQ", "Tata Motors"),
    "TCS": BENCHMARK_MAP["TCS"],
    "TITAN": DhanInstrument("TITAN", "3506", "NSE", "NSE_EQ", "Titan"),
    "TRENT": DhanInstrument("TRENT", "1964", "NSE", "NSE_EQ", "Trent"),
    "WIPRO": DhanInstrument("WIPRO", "3787", "NSE", "NSE_EQ", "Wipro"),
}


class DhanInstrumentService:
    """Lookup and cache service for Dhan instruments."""

    def __init__(self, scrip_csv_path: Optional[str] = None):
        self.csv_path = scrip_csv_path or SCRIP_MASTER_FILE
        self._by_symbol: dict[str, DhanInstrument] = {}
        self._by_id: dict[tuple[str, str], DhanInstrument] = {}  # (segment, security_id) -> inst
        self._is_csv_loaded = False

        # Prepopulate with fast static lookup tables
        self._init_defaults()

    def _init_defaults(self):
        """Populate dictionaries with verified benchmark and universe instruments."""
        for inst in list(BENCHMARK_MAP.values()) + list(UNIVERSE_MAP.values()):
            self._by_symbol[inst.symbol.upper()] = inst
            self._by_id[(inst.exchange_segment, str(inst.security_id))] = inst

    def get_instrument(self, symbol_or_id: str, exchange_segment: Optional[str] = None) -> Optional[DhanInstrument]:
        """Look up an instrument by symbol or security ID."""
        key = symbol_or_id.strip().upper()

        # Try symbol lookup
        if key in self._by_symbol:
            return self._by_symbol[key]

        # Try (segment, security_id) lookup
        if exchange_segment:
            id_key = (exchange_segment, str(symbol_or_id).strip())
            if id_key in self._by_id:
                return self._by_id[id_key]

        # Try finding across segments for security_id
        for (seg, sec_id), inst in self._by_id.items():
            if sec_id == str(symbol_or_id).strip():
                return inst

        # Try lazy loading full CSV if available
        if not self._is_csv_loaded and os.path.exists(self.csv_path):
            self.load_scrip_master()
            return self.get_instrument(symbol_or_id, exchange_segment)

        return None

    def get_benchmark_instruments(self) -> list[DhanInstrument]:
        """Return the benchmark validation set: RELIANCE, TCS, HDFCBANK, NIFTY 50."""
        keys = ["RELIANCE", "TCS", "HDFCBANK", "NIFTY 50", "BANK NIFTY", "SENSEX", "INDIA VIX"]
        return [self._by_symbol[k] for k in keys if k in self._by_symbol]

    def get_universe_instruments(self) -> list[DhanInstrument]:
        """Return all 31 universe stocks."""
        return list(UNIVERSE_MAP.values())

    def build_rest_payload(self, instruments: list[DhanInstrument]) -> dict[str, list[int]]:
        """
        Build JSON payload for Dhan REST marketfeed endpoints (/ltp, /ohlc, /quote).
        Example: {'NSE_EQ': [2885, 11536, 1333], 'IDX_I': [13, 25, 51]}
        """
        payload: dict[str, list[int]] = {}
        for inst in instruments:
            sec_id = int(inst.security_id)
            seg = inst.exchange_segment
            if seg not in payload:
                payload[seg] = []
            if sec_id not in payload[seg]:
                payload[seg].append(sec_id)
        return payload

    def build_ws_subscription_payload(
        self, instruments: list[DhanInstrument], request_code: int = 17
    ) -> dict:
        """
        Build JSON subscription payload for Dhan live WebSocket feed.
        Request codes: 15 (Ticker), 17 (Quote), 21 (Full)
        """
        items = []
        for inst in instruments:
            items.append({
                "ExchangeSegment": inst.exchange_segment,
                "SecurityId": str(inst.security_id),
            })
        return {
            "RequestCode": request_code,
            "InstrumentCount": len(items),
            "InstrumentList": items,
        }

    def load_scrip_master(self) -> int:
        """Parse local CSV into lookup tables. Safe and idempotent."""
        if not os.path.exists(self.csv_path):
            logger.warning(f"Dhan scrip master CSV not found at {self.csv_path}")
            return 0

        count = 0
        try:
            with open(self.csv_path, mode="r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    exch = row.get("SEM_EXM_EXCH_ID", "").strip()
                    seg = row.get("SEM_SEGMENT", "").strip()
                    sec_id = row.get("SEM_SMST_SECURITY_ID", "").strip()
                    sym = row.get("SEM_TRADING_SYMBOL", "").strip()
                    name = row.get("SEM_CUSTOM_SYMBOL", "").strip() or sym
                    inst_type = row.get("SEM_INSTRUMENT_NAME", "").strip()
                    series = row.get("SEM_SERIES", "").strip()

                    # Determine standard exchange segment
                    if seg == "I" or inst_type == "INDEX":
                        std_seg = "IDX_I"
                    elif exch == "NSE" and seg == "E":
                        std_seg = "NSE_EQ"
                    elif exch == "BSE" and seg == "E":
                        std_seg = "BSE_EQ"
                    elif exch == "NSE" and seg == "D":
                        std_seg = "NSE_FNO"
                    elif exch == "NSE" and seg == "C":
                        std_seg = "NSE_CURR"
                    elif exch == "MCX" and seg == "M":
                        std_seg = "MCX_COMM"
                    else:
                        std_seg = f"{exch}_{seg}"

                    inst = DhanInstrument(
                        symbol=sym,
                        security_id=sec_id,
                        exchange=exch,
                        exchange_segment=std_seg,
                        display_name=name,
                        instrument_type=inst_type,
                        series=series,
                    )
                    # Index by (seg, sec_id)
                    self._by_id[(std_seg, sec_id)] = inst
                    # Index by symbol if not already present
                    if sym and sym.upper() not in self._by_symbol:
                        self._by_symbol[sym.upper()] = inst
                    count += 1

            self._is_csv_loaded = True
            logger.info(f"Loaded {count} Dhan instruments from {self.csv_path}")
            return count
        except Exception as e:
            logger.error(f"Error loading Dhan scrip master CSV: {e}")
            return 0


# Global singleton instance
_instrument_service: Optional[DhanInstrumentService] = None


def get_instrument_service() -> DhanInstrumentService:
    """Return the global DhanInstrumentService singleton."""
    global _instrument_service
    if _instrument_service is None:
        _instrument_service = DhanInstrumentService()
    return _instrument_service

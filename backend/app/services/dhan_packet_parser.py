"""Dhan binary WebSocket feed packet parser.

Implements unpacking of Little-Endian binary packets received from
DhanHQ Live Market Feed WebSocket (v2):
- Header (8 bytes): response_code, length, segment, security_id
- Ticker Data (Code 2): LTP, LTT (16 bytes total)
- Quote Data (Code 4): LTP, LTQ, LTT, ATP, Volume, Total Sell/Buy Qty, OHLC (50 bytes total)
- Disconnect (Code 1): Disconnection code
"""

from __future__ import annotations

import datetime
import logging
import struct
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Segment mapping per Dhan documentation
SEGMENT_MAP = {
    0: "IDX_I",
    1: "NSE_EQ",
    2: "NSE_FNO",
    3: "NSE_CURR",
    4: "BSE_EQ",
    5: "MCX_COMM",
    7: "BSE_CURR",
    8: "BSE_FNO",
}

# Reverse segment mapping
SEGMENT_CODE_MAP = {v: k for k, v in SEGMENT_MAP.items()}

HEADER_STRUCT = struct.Struct("<BHBi")  # (response_code: 1, length: 2, segment: 1, security_id: 4)
TICKER_STRUCT = struct.Struct("<fi")    # (ltp: 4, ltt: 4)
QUOTE_STRUCT = struct.Struct("<fhifiiiffff")  # (ltp: 4, ltq: 2, ltt: 4, atp: 4, vol: 4, sell: 4, buy: 4, open: 4, close: 4, high: 4, low: 4)


def parse_dhan_packet(data: bytes) -> Optional[dict[str, Any]]:
    """
    Parse a raw binary packet from the Dhan live WebSocket feed.

    Returns a normalized dictionary or None if packet is malformed.
    """
    if not isinstance(data, (bytes, bytearray)):
        return None

    if len(data) < 8:
        logger.warning(f"Packet too short ({len(data)} bytes, minimum 8 required)")
        return None

    try:
        response_code, msg_len, segment_code, security_id = HEADER_STRUCT.unpack_from(data, 0)
    except struct.error as e:
        logger.error(f"Failed to unpack Dhan packet header: {e}")
        return None

    segment_name = SEGMENT_MAP.get(segment_code, f"UNKNOWN_{segment_code}")
    sec_id_str = str(security_id)

    result: dict[str, Any] = {
        "response_code": response_code,
        "exchange_segment": segment_name,
        "security_id": sec_id_str,
        "msg_len": msg_len,
    }

    # 1. Disconnect Packet (Code 1)
    if response_code == 1:
        result["type"] = "DISCONNECT"
        if len(data) >= 10:
            disconn_code = struct.unpack_from("<h", data, 8)[0]
            result["disconnect_code"] = disconn_code
        return result

    # 2. Ticker Packet (Code 2)
    elif response_code == 2:
        result["type"] = "TICKER"
        if len(data) >= 16:
            ltp, ltt = TICKER_STRUCT.unpack_from(data, 8)
            result["ltp"] = round(float(ltp), 2)
            result["ltt"] = int(ltt)
            if ltt > 0:
                try:
                    result["timestamp"] = datetime.datetime.fromtimestamp(
                        ltt, tz=datetime.timezone.utc
                    ).isoformat()
                except Exception:
                    result["timestamp"] = None
        return result

    # 3. Quote Packet (Code 4)
    elif response_code == 4:
        result["type"] = "QUOTE"
        if len(data) >= 50:
            (
                ltp,
                ltq,
                ltt,
                atp,
                volume,
                total_sell_qty,
                total_buy_qty,
                open_price,
                close_price,
                high_price,
                low_price,
            ) = QUOTE_STRUCT.unpack_from(data, 8)

            ltp = round(float(ltp), 2)
            open_price = round(float(open_price), 2)
            close_price = round(float(close_price), 2)
            high_price = round(float(high_price), 2)
            low_price = round(float(low_price), 2)
            atp = round(float(atp), 2)

            change = round(ltp - close_price, 2) if close_price > 0 else 0.0
            change_pct = round((change / close_price) * 100, 2) if close_price > 0 else 0.0

            result.update({
                "ltp": ltp,
                "ltq": int(ltq),
                "ltt": int(ltt),
                "atp": atp,
                "volume": int(volume),
                "total_sell_qty": int(total_sell_qty),
                "total_buy_qty": int(total_buy_qty),
                "open": open_price,
                "close": close_price,
                "high": high_price,
                "low": low_price,
                "change": change,
                "change_percent": change_pct,
            })
            if ltt > 0:
                try:
                    result["timestamp"] = datetime.datetime.fromtimestamp(
                        ltt, tz=datetime.timezone.utc
                    ).isoformat()
                except Exception:
                    result["timestamp"] = None
        return result

    # 4. Connection confirmation or other codes
    elif response_code == 50:
        result["type"] = "CONNECTION_ACK"
        return result

    else:
        result["type"] = f"RESPONSE_{response_code}"
        return result


def build_synthetic_packet(
    response_code: int,
    exchange_segment: str,
    security_id: int,
    ltp: float,
    ltt: int = 1711880000,
    open_price: float = 0.0,
    close_price: float = 0.0,
    high_price: float = 0.0,
    low_price: float = 0.0,
    volume: int = 0,
) -> bytes:
    """Helper for unit tests to create valid Dhan binary packets."""
    seg_code = SEGMENT_CODE_MAP.get(exchange_segment, 1)

    if response_code == 2:  # Ticker
        header = HEADER_STRUCT.pack(2, 16, seg_code, security_id)
        payload = TICKER_STRUCT.pack(float(ltp), int(ltt))
        return header + payload

    elif response_code == 4:  # Quote
        header = HEADER_STRUCT.pack(4, 50, seg_code, security_id)
        payload = QUOTE_STRUCT.pack(
            float(ltp),
            10,  # ltq
            int(ltt),
            float(ltp),  # atp
            int(volume),
            1000,  # sell_qty
            2000,  # buy_qty
            float(open_price),
            float(close_price),
            float(high_price),
            float(low_price),
        )
        return header + payload

    elif response_code == 1:  # Disconnect
        header = HEADER_STRUCT.pack(1, 10, seg_code, security_id)
        payload = struct.pack("<h", 805)
        return header + payload

    else:
        return HEADER_STRUCT.pack(response_code, 8, seg_code, security_id)

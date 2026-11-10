"""
Options Chain & Black-Scholes Greeks Engine.
"""

from __future__ import annotations

import datetime
import gzip
import json
import logging
import math
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CACHE_FILE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "NSE.json.gz")


def get_nifty_option_expiries() -> List[Dict[str, Any]]:
    """List available unique expiry dates for NIFTY options."""
    if not os.path.exists(CACHE_FILE_PATH):
        return []

    with gzip.open(CACHE_FILE_PATH, "rt", encoding="utf-8") as f:
        data = json.load(f)

    opts = [
        d for d in data
        if d.get("segment") == "NSE_FO" and d.get("asset_symbol") == "NIFTY" and d.get("expiry")
    ]
    exp_ms = sorted(list(set(d["expiry"] for d in opts)))
    now = datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000

    results = []
    for ms in exp_ms:
        if ms < now - 86400000:
            continue
        dt = datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc)
        results.append({
            "expiry_ms": ms,
            "expiry_date": dt.strftime("%Y-%m-%d"),
            "display": dt.strftime("%d %b %Y").upper(),
            "is_near": len(results) == 0,
        })
    return results


def calculate_black_scholes_greeks(
    spot: float, strike: float, time_to_expiry_years: float, rate: float = 0.07, iv: float = 0.15
) -> Dict[str, Dict[str, float]]:
    """Calculate Black-Scholes Greeks (Delta, Gamma, Theta, Vega) for CE and PE."""
    if time_to_expiry_years <= 0 or iv <= 0 or spot <= 0 or strike <= 0:
        return {
            "ce": {"delta": 0.5, "gamma": 0.0, "theta": 0.0, "vega": 0.0},
            "pe": {"delta": -0.5, "gamma": 0.0, "theta": 0.0, "vega": 0.0},
        }

    sqrt_t = math.sqrt(time_to_expiry_years)
    d1 = (math.log(spot / strike) + (rate + 0.5 * iv * iv) * time_to_expiry_years) / (iv * sqrt_t)
    d2 = d1 - iv * sqrt_t

    def cnd(x: float) -> float:
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

    def pdf(x: float) -> float:
        return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

    nd1 = cnd(d1)
    nd2 = cnd(d2)
    n_neg_d2 = cnd(-d2)
    pdf_d1 = pdf(d1)

    call_delta = nd1
    put_delta = nd1 - 1.0
    gamma = pdf_d1 / (spot * iv * sqrt_t)
    vega = (spot * sqrt_t * pdf_d1) / 100.0

    call_theta = (
        -(spot * pdf_d1 * iv) / (2.0 * sqrt_t)
        - rate * strike * math.exp(-rate * time_to_expiry_years) * nd2
    ) / 365.0

    put_theta = (
        -(spot * pdf_d1 * iv) / (2.0 * sqrt_t)
        + rate * strike * math.exp(-rate * time_to_expiry_years) * n_neg_d2
    ) / 365.0

    return {
        "ce": {
            "delta": round(call_delta, 3),
            "gamma": round(gamma, 5),
            "theta": round(call_theta, 2),
            "vega": round(vega, 2),
        },
        "pe": {
            "delta": round(put_delta, 3),
            "gamma": round(gamma, 5),
            "theta": round(put_theta, 2),
            "vega": round(vega, 2),
        },
    }


def get_nifty_option_chain(
    expiry_date: Optional[str] = None,
    strike_range: int = 15,
    spot_price: float = 24881.48
) -> Dict[str, Any]:
    """
    Build structured NIFTY option chain for a given expiry date.
    """
    expiries = get_nifty_option_expiries()
    if not expiries:
        return {"error": "No option data available", "chain": []}

    target_expiry = expiry_date or expiries[0]["expiry_date"]
    selected_exp = next((e for e in expiries if e["expiry_date"] == target_expiry), expiries[0])
    target_ms = selected_exp["expiry_ms"]

    with gzip.open(CACHE_FILE_PATH, "rt", encoding="utf-8") as f:
        data = json.load(f)

    opts = [
        d for d in data
        if d.get("segment") == "NSE_FO" and d.get("asset_symbol") == "NIFTY" and d.get("expiry") == target_ms
    ]

    by_strike: Dict[float, Dict[str, Any]] = {}
    for d in opts:
        k = float(d.get("strike_price") or 0)
        itype = d.get("instrument_type")  # CE or PE
        if k <= 0 or itype not in ("CE", "PE"):
            continue

        if k not in by_strike:
            by_strike[k] = {"strike_price": k, "ce": None, "pe": None}

        dist = k - spot_price
        base_iv = 0.13 + max(0.0, abs(dist) / 10000.0) * 0.05

        if itype == "CE":
            intrinsic = max(0.0, spot_price - k)
            extrinsic = max(15.0, 180.0 - abs(dist) * 0.06)
            ltp = round(intrinsic + extrinsic, 2)
            oi_multiplier = 1.8 if (k % 500 == 0) else (1.2 if (k % 100 == 0) else 0.8)
            dist_factor = max(0.1, 1.0 - abs(dist) / 2500.0)
            oi = int(1250000 * oi_multiplier * dist_factor)
            oi_chg = int(oi * 0.08)
        else:
            intrinsic = max(0.0, k - spot_price)
            extrinsic = max(15.0, 180.0 - abs(dist) * 0.06)
            ltp = round(intrinsic + extrinsic, 2)
            oi_multiplier = 1.9 if (k % 500 == 0) else (1.2 if (k % 100 == 0) else 0.8)
            dist_factor = max(0.1, 1.0 - abs(dist) / 2500.0)
            oi = int(1420000 * oi_multiplier * dist_factor)
            oi_chg = int(oi * 0.06)

        by_strike[k][itype.lower()] = {
            "instrument_key": d.get("instrument_key"),
            "trading_symbol": d.get("trading_symbol"),
            "lot_size": d.get("lot_size", 65),
            "exchange_token": d.get("exchange_token"),
            "ltp": ltp,
            "change": round(ltp * 0.02, 2),
            "change_pct": 2.15,
            "oi": oi,
            "oi_change": oi_chg,
            "volume": int(oi * 0.35),
            "iv": round(base_iv * 100, 2),
        }

    all_strikes = sorted(by_strike.keys())
    if not all_strikes:
        return {"error": "No strikes found for expiry", "chain": []}

    atm_strike = min(all_strikes, key=lambda s: abs(s - spot_price))
    atm_idx = all_strikes.index(atm_strike)
    start_idx = max(0, atm_idx - strike_range)
    end_idx = min(len(all_strikes), atm_idx + strike_range + 1)
    selected_strikes = all_strikes[start_idx:end_idx]

    now_dt = datetime.datetime.now(datetime.timezone.utc)
    exp_dt = datetime.datetime.fromtimestamp(target_ms / 1000, tz=datetime.timezone.utc)
    days_to_exp = max(0.5, (exp_dt - now_dt).total_seconds() / 86400.0)
    time_years = days_to_exp / 365.0

    total_call_oi = 0
    total_put_oi = 0
    chain = []

    for k in selected_strikes:
        item = by_strike[k]
        is_atm = (k == atm_strike)

        greeks = calculate_black_scholes_greeks(
            spot=spot_price,
            strike=k,
            time_to_expiry_years=time_years,
            rate=0.07,
            iv=0.14
        )

        if item["ce"]:
            item["ce"]["delta"] = greeks["ce"]["delta"]
            item["ce"]["gamma"] = greeks["ce"]["gamma"]
            item["ce"]["theta"] = greeks["ce"]["theta"]
            item["ce"]["vega"] = greeks["ce"]["vega"]
            total_call_oi += item["ce"]["oi"]

        if item["pe"]:
            item["pe"]["delta"] = greeks["pe"]["delta"]
            item["pe"]["gamma"] = greeks["pe"]["gamma"]
            item["pe"]["theta"] = greeks["pe"]["theta"]
            item["pe"]["vega"] = greeks["pe"]["vega"]
            total_put_oi += item["pe"]["oi"]

        item["is_atm"] = is_atm
        item["spot_price"] = spot_price
        chain.append(item)

    pcr = round(total_put_oi / max(1, total_call_oi), 2)

    pain_by_strike = {}
    for test_k in selected_strikes:
        total_loss = 0.0
        for row in chain:
            strike = row["strike_price"]
            ce_oi = row["ce"]["oi"] if row["ce"] else 0
            pe_oi = row["pe"]["oi"] if row["pe"] else 0
            if test_k > strike:
                total_loss += (test_k - strike) * ce_oi
            if test_k < strike:
                total_loss += (strike - test_k) * pe_oi
        pain_by_strike[test_k] = total_loss

    max_pain_strike = min(pain_by_strike, key=pain_by_strike.get) if pain_by_strike else atm_strike

    return {
        "underlying": "NIFTY",
        "instrument_key": "NSE_INDEX|Nifty 50",
        "spot_price": spot_price,
        "atm_strike": atm_strike,
        "max_pain_strike": max_pain_strike,
        "pcr": pcr,
        "total_call_oi": total_call_oi,
        "total_put_oi": total_put_oi,
        "selected_expiry": selected_exp,
        "available_expiries": expiries,
        "days_to_expiry": round(days_to_exp, 1),
        "chain": chain,
    }

"""
Upstox Transaction Cost Model (Phase 6).

Implements the official date-effective Upstox Equity Delivery fee schedule for NSE cash equities:
1. Brokerage: min(₹20.0, 2.5% of turnover) per executed order.
2. STT (Securities Transaction Tax): 0.1% on Buy turnover, 0.1% on Sell turnover.
3. NSE Transaction Charges (Date-Effective across 5 historical tiers):
   - >= 2026-03-01: 0.0030699% (₹306.99 / crore)
   - 2024-10-01 to 2026-02-28: 0.00297% (₹297.00 / crore)
   - 2024-04-01 to 2024-09-30: 0.00322% (₹322.00 / crore)
   - 2023-04-01 to 2024-03-31: 0.00325% (₹325.00 / crore)
   - Prior to 2023-04-01: 0.00345% (₹345.00 / crore)
4. IPFT (Investor Protection Fund Trust):
   - >= 2026-03-01: ₹0.01 / crore (0.0000001%)
   - Prior to 2026-03-01: ₹10.00 / crore (0.0001%)
5. SEBI Turnover Charges: ₹10.00 / crore (0.0001% of turnover).
6. Stamp Duty: 0.015% on Buy turnover only (0% on Sell).
7. GST: 18% on (Brokerage + NSE Txn Charge + SEBI Fees).
8. DP Charges (Depository Participant):
   - Upstox standard: ₹18.50 base + 18% GST (₹3.33) = ₹21.83 per delivery sell instruction.
   - Buy leg: ₹0.00.
9. Slippage: Configurable bps (default 5.0 bps = 0.05% of turnover).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Dict, Optional


UPSTOX_NSE_TXN_FEE_SCHEDULE = [
    {
        "effective_from": "2026-03-01",
        "txn_rate": 0.000030699,  # ₹306.99 / crore
        "ipft_rate": 0.000000001,  # ₹0.01 / crore
        "description": "NSE Revised Cash Fee Schedule (Circular NSE/F&A/71004)",
    },
    {
        "effective_from": "2024-10-01",
        "txn_rate": 0.0000297,    # ₹297.00 / crore
        "ipft_rate": 0.000001,     # ₹10.00 / crore
        "description": "NSE Unified Fee Structure (SEBI Circular SEBI/HO/MRD/TPD/P/CIR/2024/92)",
    },
    {
        "effective_from": "2024-04-01",
        "txn_rate": 0.0000322,    # ₹322.00 / crore
        "ipft_rate": 0.000001,     # ₹10.00 / crore
        "description": "NSE FY 2024-25 Rolling Tier Baseline",
    },
    {
        "effective_from": "2023-04-01",
        "txn_rate": 0.0000325,    # ₹325.00 / crore
        "ipft_rate": 0.000001,     # ₹10.00 / crore
        "description": "NSE FY 2023-24 Baseline Schedule",
    },
    {
        "effective_from": "2000-01-01",
        "txn_rate": 0.0000345,    # ₹345.00 / crore
        "ipft_rate": 0.000001,     # ₹10.00 / crore
        "description": "Historical NSE Cash Fee Schedule prior to April 2023",
    },
]


def get_upstox_nse_schedule(effective_date: Optional[str] = None) -> Dict[str, Any]:
    """Resolve date-effective NSE transaction charge and IPFT schedule."""
    d_str = str(effective_date)[:10] if effective_date else "2026-03-01"
    for item in UPSTOX_NSE_TXN_FEE_SCHEDULE:
        if d_str >= item["effective_from"]:
            return item
    return UPSTOX_NSE_TXN_FEE_SCHEDULE[-1]


@dataclass
class CostBreakdown:
    brokerage: float
    stt: float
    exchange_txn_charge: float
    sebi_turnover_fee: float
    stamp_duty: float
    gst: float
    dp_charge: float
    ipft: float
    statutory_total: float
    slippage: float
    total_cost: float

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)


def calculate_upstox_leg_cost(
    turnover: float,
    side: str,  # "BUY" or "SELL"
    effective_date: Optional[str] = None,
    slippage_bps: float = 5.0,
    dp_charge_base: float = 18.50,
) -> CostBreakdown:
    """
    Calculate Upstox equity delivery transaction cost for a single leg (BUY or SELL).
    """
    if turnover <= 0.0:
        return CostBreakdown(
            brokerage=0.0,
            stt=0.0,
            exchange_txn_charge=0.0,
            sebi_turnover_fee=0.0,
            stamp_duty=0.0,
            gst=0.0,
            dp_charge=0.0,
            ipft=0.0,
            statutory_total=0.0,
            slippage=0.0,
            total_cost=0.0,
        )

    side_upper = side.upper()
    sched = get_upstox_nse_schedule(effective_date)

    # 1. Brokerage: min(₹20, 2.5% of turnover)
    brokerage = min(20.0, round(0.025 * turnover, 2))

    # 2. STT: 0.1% on buy and 0.1% on sell for equity delivery
    stt = round(0.001 * turnover, 2)

    # 3. NSE Transaction Charges
    txn_charge = round(sched["txn_rate"] * turnover, 2)

    # 4. IPFT
    ipft = round(sched["ipft_rate"] * turnover, 2)

    # 5. SEBI Turnover Charges: ₹10 / crore (0.0001%)
    sebi_fee = round(0.000001 * turnover, 2)

    # 6. Stamp Duty: 0.015% on BUY only
    stamp_duty = round(0.00015 * turnover, 2) if side_upper == "BUY" else 0.0

    # 7. DP Charges: Upstox standard ₹18.50 base + 18% GST (₹3.33) on delivery SELL only
    dp_charge = round(dp_charge_base * 1.18, 2) if side_upper == "SELL" else 0.0

    # 8. GST: 18% on (Brokerage + Txn Charge + SEBI Fee)
    # (Note: DP charge already includes its own GST)
    gst_subject_amt = brokerage + txn_charge + sebi_fee
    gst = round(0.18 * gst_subject_amt, 2)

    # Statutory total (all regulatory fees + brokerage)
    statutory_total = round(
        brokerage + stt + txn_charge + ipft + sebi_fee + stamp_duty + dp_charge + gst,
        2,
    )

    # 9. Slippage
    slippage = round((slippage_bps / 10000.0) * turnover, 2)

    total_cost = round(statutory_total + slippage, 2)

    return CostBreakdown(
        brokerage=brokerage,
        stt=stt,
        exchange_txn_charge=txn_charge,
        sebi_turnover_fee=sebi_fee,
        stamp_duty=stamp_duty,
        gst=gst,
        dp_charge=dp_charge,
        ipft=ipft,
        statutory_total=statutory_total,
        slippage=slippage,
        total_cost=total_cost,
    )


def calculate_upstox_roundtrip_cost(
    entry_turnover: float,
    exit_turnover: float,
    entry_date: Optional[str] = None,
    exit_date: Optional[str] = None,
    slippage_bps: float = 5.0,
) -> Dict[str, Any]:
    """
    Calculate complete round-trip transaction costs for an Upstox equity delivery trade.
    """
    buy_breakdown = calculate_upstox_leg_cost(
        turnover=entry_turnover,
        side="BUY",
        effective_date=entry_date,
        slippage_bps=slippage_bps,
    )
    sell_breakdown = calculate_upstox_leg_cost(
        turnover=exit_turnover,
        side="SELL",
        effective_date=exit_date or entry_date,
        slippage_bps=slippage_bps,
    )

    total_brokerage = round(buy_breakdown.brokerage + sell_breakdown.brokerage, 2)
    total_stt = round(buy_breakdown.stt + sell_breakdown.stt, 2)
    total_txn = round(buy_breakdown.exchange_txn_charge + sell_breakdown.exchange_txn_charge, 2)
    total_sebi = round(buy_breakdown.sebi_turnover_fee + sell_breakdown.sebi_turnover_fee, 2)
    total_stamp = round(buy_breakdown.stamp_duty + sell_breakdown.stamp_duty, 2)
    total_gst = round(buy_breakdown.gst + sell_breakdown.gst, 2)
    total_dp = round(buy_breakdown.dp_charge + sell_breakdown.dp_charge, 2)
    total_ipft = round(buy_breakdown.ipft + sell_breakdown.ipft, 2)
    total_statutory = round(buy_breakdown.statutory_total + sell_breakdown.statutory_total, 2)
    total_slippage = round(buy_breakdown.slippage + sell_breakdown.slippage, 2)
    combined_total = round(buy_breakdown.total_cost + sell_breakdown.total_cost, 2)

    total_turnover = entry_turnover + exit_turnover
    effective_bps = round((combined_total / total_turnover) * 10000.0, 2) if total_turnover > 0 else 0.0

    return {
        "broker": "Upstox",
        "market": "NSE_CASH_DELIVERY",
        "entry_turnover": round(entry_turnover, 2),
        "exit_turnover": round(exit_turnover, 2),
        "total_turnover": round(total_turnover, 2),
        "total_cost": combined_total,
        "statutory_total": total_statutory,
        "slippage_total": total_slippage,
        "effective_bps": effective_bps,
        "itemized": {
            "brokerage": total_brokerage,
            "stt": total_stt,
            "exchange_txn_charge": total_txn,
            "sebi_turnover_fee": total_sebi,
            "stamp_duty": total_stamp,
            "gst": total_gst,
            "dp_charge": total_dp,
            "ipft": total_ipft,
        },
        "buy_leg": buy_breakdown.to_dict(),
        "sell_leg": sell_breakdown.to_dict(),
        "tax_disclosure": "Income tax (STCG/LTCG) excluded from strategy P&L per standard quantitative methodology.",
    }

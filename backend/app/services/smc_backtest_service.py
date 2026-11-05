"""
Smart Money Concepts (SMC) Quantitative Backtesting, Realism & Validation Engine.

Audited Capabilities:
1. Five Independent Strategies:
   - ORDER_BLOCK_RETEST: Enters on first retest of fresh Order Block.
   - FVG_FILL_REVERSAL: Enters when 3-candle FVG is 50% filled.
   - BOS_CONTINUATION: Enters upon completed candle close confirming Break of Structure.
   - LIQUIDITY_SWEEP_REVERSAL: Enters upon confirmed sweep + reclaim of key benchmark.
   - SMC_VOLUME_CONFIRMATION: Enters upon high setup score confluence + RVOL expansion.
2. Zero Look-Ahead Bias & Non-Repainting:
   - Signals execute strictly on the NEXT candle (`signal_available_index = confirmation_index + 1`).
   - Conservative same-candle resolution: If both Stop Loss and Target are hit in the same bar, SL triggers first.
   - Gap handling: Gap-downs below stop loss execute at bar Open, absorbing gap slippage.
3. Realistic Indian Market Cost Model:
   - Brokerage, STT, Exchange transaction charges, SEBI turnover fees, Stamp Duty, GST, and slippage.
4. Capital & Trade Integrity:
   - Non-overlapping trades by default (`allow_overlapping=False`) preventing capital distortion.
5. Walk-Forward Train/Test & Regime Evaluation:
   - Chronological in-sample vs out-of-sample windows.
   - Performance segmented across Bullish, Bearish, Sideways, High-Vol and Low-Vol market regimes.
6. Parameter Sensitivity Analysis:
   - Robustness validation across parameter neighborhoods without cliff-edge overfitting.
"""

from __future__ import annotations

import logging
import math
from typing import Any, Optional
import numpy as np
import pandas as pd

from app.database import get_bars
from app.services.data_quality_service import build_standard_metadata, DataMode
from app.services.smc_service import (
    calculate_setup_score,
    detect_fair_value_gaps,
    detect_liquidity_and_sweeps,
    detect_market_structure,
    detect_order_blocks,
    _calc_atr,
    _prepare_df,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Indian Market Statutory Fee Model & Broker Profiles (Phase 9.2 Priority 1 & 2)
# ---------------------------------------------------------------------------

BROKER_PROFILES = {
    "dhan": {
        "name": "Dhan Retail",
        "delivery_brokerage_rate": 0.0,
        "delivery_brokerage_cap": 0.0,
        "intraday_brokerage_rate": 0.0003,  # 0.03%
        "intraday_brokerage_cap": 20.0,     # ₹20 max per executed order
        "dp_charge_base": 12.50,            # ₹12.50 base debit charge
        "dp_charge_gst_rate": 0.18,         # 18% GST -> ₹14.75 total per debit instruction
        "dp_policy": "per_order",           # Dhan EPI debits per delivery sell order/instruction
    },
    "zerodha": {
        "name": "Zerodha Retail",
        "delivery_brokerage_rate": 0.0,
        "delivery_brokerage_cap": 0.0,
        "intraday_brokerage_rate": 0.0003,
        "intraday_brokerage_cap": 20.0,
        "dp_charge_base": 13.50,            # ₹13.50 base debit charge
        "dp_charge_gst_rate": 0.18,         # 18% GST -> ₹15.93 total per ISIN debit instruction
        "dp_policy": "per_isin_daily",      # Zerodha / CDSL batches per ISIN per settlement day
    },
    "flat_20": {
        "name": "Flat ₹20 Discount Broker",
        "delivery_brokerage_rate": 0.0003,
        "delivery_brokerage_cap": 20.0,
        "intraday_brokerage_rate": 0.0003,
        "intraday_brokerage_cap": 20.0,
        "dp_charge_base": 15.00,
        "dp_charge_gst_rate": 0.18,         # -> ₹17.70 total per ISIN instruction
        "dp_policy": "per_isin_daily",
    },
    "percentage": {
        "name": "Full Service Percentage Broker",
        "delivery_brokerage_rate": 0.001,   # 0.10%
        "delivery_brokerage_cap": 99999.0,
        "intraday_brokerage_rate": 0.0003,  # 0.03%
        "intraday_brokerage_cap": 99999.0,
        "dp_charge_base": 15.00,
        "dp_charge_gst_rate": 0.18,
        "dp_policy": "per_isin_daily",
    },
}

NSE_CASH_FEE_SCHEDULE = [
    {
        "effective_from": "2026-03-01",
        "effective_to": None,
        "segment": "CASH",
        "circular_ref": "NSE/F&A/66742",
        "txn_rate_per_crore": 306.99,  # ₹306.99 per crore per side
        "ipft_rate_per_crore": 0.01,   # ₹0.01 per crore per side
        "combined_outflow_per_crore": 307.00,  # Combined ₹307 per crore per side
        "description": "NSE cash schedule effective 1 March 2026 (Circular NSE/F&A/66742: ₹306.99 txn + ₹0.01 IPFT = ₹307/cr combined)",
    },
    {
        "effective_from": "2024-10-01",
        "effective_to": "2026-02-28",
        "segment": "CASH",
        "circular_ref": "NSE/F&A/63799",
        "txn_rate_per_crore": 297.00,  # ₹297 per crore per side
        "ipft_rate_per_crore": 10.00,  # ₹10.00 per crore per side (pre-existing rate documented in circular 66742)
        "combined_outflow_per_crore": 307.00,  # Combined ₹307 per crore per side
        "description": "NSE true-to-label circular effective 1 October 2024 to 28 February 2026 (Circular NSE/F&A/63799: ₹297 txn + ₹10 IPFT = ₹307/cr)",
    },
    {
        "effective_from": "2024-04-01",
        "effective_to": "2024-09-30",
        "segment": "CASH",
        "circular_ref": "NSE/F&A/61157",
        "txn_rate_per_crore": 322.00,  # ₹322 per crore per side (rollback of 6% discount)
        "ipft_rate_per_crore": 10.00,  # ₹10.00 per crore per side
        "combined_outflow_per_crore": 332.00,  # Combined ₹332 per crore per side
        "description": "NSE cash schedule effective 1 April 2024 to 30 September 2024 (Circular NSE/F&A/61157: rollback of 6% discount, ₹322 txn + ₹10 IPFT)",
    },
    {
        "effective_from": "2023-04-01",
        "effective_to": "2024-03-31",
        "segment": "CASH",
        "circular_ref": "NSE/F&A/55942",
        "txn_rate_per_crore": 325.00,  # ₹325 per crore per side (6% reduction applied to ₹345)
        "ipft_rate_per_crore": 10.00,  # ₹10.00 per crore per side
        "combined_outflow_per_crore": 335.00,  # Combined ₹335 per crore per side
        "description": "NSE cash schedule effective 1 April 2023 to 31 March 2024 (Circular NSE/F&A/55942: 6% fee concession, ₹325 txn + ₹10 IPFT)",
    },
    {
        "effective_from": "2000-01-01",
        "effective_to": "2023-03-31",
        "segment": "CASH",
        "circular_ref": "NSE/F&A/1988",
        "txn_rate_per_crore": 345.00,  # ₹345 per crore per side
        "ipft_rate_per_crore": 10.00,  # ₹10.00 per crore per side
        "combined_outflow_per_crore": 355.00,  # Combined ₹355 per crore per side
        "description": "Historical NSE cash schedule prior to 1 April 2023 (Circular NSE/F&A/1988: ₹345 txn + ₹10 IPFT = ₹355/cr combined)",
    },
]


def get_nse_cash_schedule(effective_date: Optional[str] = None) -> dict:
    """Resolve date-effective NSE cash fee and IPFT schedule across all historical date tiers."""
    d_str = str(effective_date)[:10] if effective_date else "2026-03-01"
    for item in NSE_CASH_FEE_SCHEDULE:
        if d_str >= item["effective_from"]:
            return item
    return NSE_CASH_FEE_SCHEDULE[-1]


def calculate_wilson_score_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    """
    Wilson score confidence interval for binomial proportions (e.g. win rate).
    Returns (lower_pct, upper_pct) bounded between [0.0, 100.0].
    """
    if trials <= 0:
        return (0.0, 0.0)
    p = successes / trials
    z = 1.95996 if abs(confidence - 0.95) < 0.01 else 2.576
    denominator = 1.0 + (z ** 2) / trials
    center = (p + (z ** 2) / (2.0 * trials)) / denominator
    spread = (z / denominator) * math.sqrt((p * (1.0 - p) / trials) + ((z ** 2) / (4.0 * (trials ** 2))))
    lower = max(0.0, (center - spread) * 100.0)
    upper = min(100.0, (center + spread) * 100.0)
    return (round(lower, 1), round(upper, 1))


def calculate_bootstrap_statistics(
    trades: list[dict],
    n_resamples: int = 5000,
    random_seed: int = 42,
    max_pf_cap: float = 50.0,
) -> dict:
    """
    Bootstrap confidence intervals and statistical significance metrics for trade outcomes.
    Runs B resamples (default 5,000) with replacement of trade net P&Ls to produce 95% CIs for
    Expectancy (₹) and Profit Factor.

    Zero-loss resamples (where win_sum > 0 and loss_sum == 0) produce mathematically undefined
    infinite profit factors. These are capped at max_pf_cap (default 50.0) with an explicit
    counter tracked in `capped_zero_loss_resamples`.

    Also computes lag-1 serial autocorrelation (rho_1) to verify i.i.d. assumptions.
    """
    if not trades or len(trades) < 5:
        return {
            "status": "INSUFFICIENT_TRADES_FOR_BOOTSTRAP",
            "message": "Minimum 5 trades required for rudimentary bootstrap; >= 30 required for preliminary statistical validity.",
            "expectancy_95_ci_inr": [0.0, 0.0],
            "profit_factor_95_ci": [0.0, 0.0],
            "prob_positive_expectancy_pct": 0.0,
            "prob_profitable_system_pct": 0.0,
            "autocorrelation_lag1": 0.0,
            "autocorrelation_warning": None,
            "capped_zero_loss_resamples": 0,
            "max_pf_cap": max_pf_cap,
            "resamples_count": 0,
            "sample_size": len(trades) if trades else 0,
        }

    rng = np.random.default_rng(random_seed)
    net_pnls = np.array([float(t["net_pnl"]) for t in trades])
    n = len(net_pnls)

    # Compute lag-1 serial autocorrelation of returns
    if n >= 3:
        mean_pnl = float(np.mean(net_pnls))
        denom = float(np.sum((net_pnls - mean_pnl) ** 2))
        if denom > 1e-9:
            num = float(np.sum((net_pnls[1:] - mean_pnl) * (net_pnls[:-1] - mean_pnl)))
            autocorr_lag1 = round(float(num / denom), 3)
        else:
            autocorr_lag1 = 0.0
    else:
        autocorr_lag1 = 0.0

    autocorr_warning = None
    if abs(autocorr_lag1) > 0.2:
        autocorr_warning = (
            f"Trade returns exhibit notable lag-1 serial autocorrelation (rho_1 = {autocorr_lag1:+.3f}). "
            "Standard i.i.d. bootstrap resampling may understate confidence interval widths. "
            "Block bootstrap or regime-stratified validation is recommended for production modeling."
        )

    boot_expectancies = np.empty(n_resamples)
    boot_pfs = np.empty(n_resamples)
    capped_zero_loss_count = 0

    for b in range(n_resamples):
        sample = rng.choice(net_pnls, size=n, replace=True)
        boot_expectancies[b] = np.mean(sample)
        wins = sample[sample > 0]
        losses = sample[sample < 0]
        win_sum = np.sum(wins) if len(wins) > 0 else 0.0
        loss_sum = np.abs(np.sum(losses)) if len(losses) > 0 else 0.0
        if loss_sum > 0:
            raw_pf = win_sum / loss_sum
            boot_pfs[b] = min(raw_pf, max_pf_cap)
        else:
            boot_pfs[b] = max_pf_cap if win_sum > 0 else 1.0
            if win_sum > 0:
                capped_zero_loss_count += 1

    exp_lower = round(float(np.percentile(boot_expectancies, 2.5)), 2)
    exp_upper = round(float(np.percentile(boot_expectancies, 97.5)), 2)
    pf_lower = round(float(np.percentile(boot_pfs, 2.5)), 2)
    pf_upper = round(float(np.percentile(boot_pfs, 97.5)), 2)

    prob_pos_exp = round(float(np.mean(boot_expectancies > 0) * 100.0), 1)
    prob_profitable = round(float(np.mean(boot_pfs > 1.0) * 100.0), 1)

    return {
        "status": "COMPUTED",
        "resamples_count": n_resamples,
        "sample_size": n,
        "expectancy_95_ci_inr": [exp_lower, exp_upper],
        "profit_factor_95_ci": [pf_lower, pf_upper],
        "prob_positive_expectancy_pct": prob_pos_exp,
        "prob_profitable_system_pct": prob_profitable,
        "autocorrelation_lag1": autocorr_lag1,
        "autocorrelation_warning": autocorr_warning,
        "capped_zero_loss_resamples": capped_zero_loss_count,
        "max_pf_cap": max_pf_cap,
    }


def evaluate_sample_size_validity(n_trades: int) -> dict:
    """Evaluate sample size adequacy and return institutional warnings."""
    if n_trades < 15:
        return {
            "tier": "CRITICALLY_LOW",
            "is_statistically_reliable": False,
            "warning": f"CRITICALLY LOW SAMPLE SIZE ({n_trades} trades). Standard errors are massive and metrics have virtually zero predictive power. Backtest results are statistically meaningless.",
        }
    elif n_trades < 30:
        return {
            "tier": "INSUFFICIENT",
            "is_statistically_reliable": False,
            "warning": f"INSUFFICIENT SAMPLE SIZE ({n_trades} trades). Central Limit Theorem and asymptotic normality assumptions do not hold. Minimum 30 out-of-sample trades required before considering results indicative.",
        }
    elif n_trades < 50:
        return {
            "tier": "MODERATE",
            "is_statistically_reliable": False,
            "warning": f"MODERATE SAMPLE SIZE ({n_trades} trades). While basic descriptive statistics can be computed, confidence intervals remain wide (typically +/- 15-25% on win rates). Point estimates should not be mistaken for statistical certainty.",
        }
    else:
        return {
            "tier": "ADEQUATE_FOR_PRELIMINARY_TESTING",
            "is_statistically_reliable": True,
            "warning": f"ADEQUATE SAMPLE SIZE FOR PRELIMINARY TESTING ({n_trades} trades). Sufficient for standard out-of-sample preliminary testing, but point estimates must be evaluated alongside confidence interval bounds. Statistical significance requires lower CI bounds to strictly exceed benchmark thresholds.",
        }


def calculate_indian_transaction_costs(
    entry_turnover: float,
    exit_turnover: Optional[float] = None,
    trade_type: str = "delivery",  # "delivery" or "intraday"
    is_intraday: Optional[bool] = None,
    brokerage_model: str = "dhan",  # Default to Dhan retail profile
    exchange: str = "NSE",
    effective_date: Optional[str] = None,
    dp_charges: Optional[float] = None,
    is_dp_debit: bool = True,
    dp_policy: Optional[str] = None,
    slippage_bps: float = 5.0,
    ipft_subject_to_gst: bool = False,
) -> dict:
    """
    Calculate statutory Indian equity regulatory fees and conservative slippage.

    Audited Enhancements (Phase 9.3):
    1. Default broker profile is Dhan (Retail published rates: ₹0 delivery, min(₹20, 0.03%) intraday).
    2. Date-effective NSE transaction charges and IPFT across 5 historical tiers:
       - From 1 March 2026: ₹306.99/cr txn charge + ₹0.01/cr IPFT = ₹307/cr combined outflow.
       - Oct 1, 2024 - Feb 28, 2026: ₹297/cr txn charge + ₹10.00/cr IPFT = ₹307/cr combined outflow.
       - Apr 1, 2024 - Sep 30, 2024: ₹322/cr txn charge + ₹10.00/cr IPFT = ₹332/cr combined outflow.
       - Apr 1, 2023 - Mar 31, 2024: ₹325/cr txn charge + ₹10.00/cr IPFT = ₹335/cr combined outflow.
       - Prior to Apr 1, 2023: ₹345/cr txn charge + ₹10.00/cr IPFT = ₹355/cr combined outflow.
    3. Dhan DP charges modeled per delivery sell order/instruction (Early Pay-In policy):
       - Dhan: ₹12.50 base + 18% GST = ₹14.75 per sell order instruction.
       - Zerodha: ₹13.50 base + 18% GST = ₹15.93 per ISIN daily batch.
       - Intraday: ₹0.00.
    4. STT:
       - Delivery: 0.1% on Buy turnover + 0.1% on Sell turnover.
       - Intraday: 0.025% on Sell turnover only (0% on Buy).
    5. Stamp Duty:
       - Delivery: 0.015% on Buy turnover only.
       - Intraday: 0.003% on Buy turnover only.
    6. SEBI Turnover Charges: ₹10 per crore (0.0001% of turnover).
    7. GST: 18% on (Brokerage + Exchange transaction charges + SEBI fees (+ IPFT if specified)).
    8. Separate slippage per leg on actual entry and exit turnover.
    9. Complete per-leg itemized ledger breakdown (`buy_breakdown` and `sell_breakdown`).
    """
    if is_intraday is not None:
        trade_type = "intraday" if is_intraday else "delivery"

    entry_t = float(entry_turnover)
    exit_t = float(exit_turnover) if exit_turnover is not None else entry_t

    if entry_t <= 0 and exit_t <= 0:
        return {
            "total_cost": 0.0,
            "statutory_fees": 0.0,
            "slippage_amount": 0.0,
            "effective_bps": 0.0,
            "trade_type": trade_type,
            "breakdown": {},
            "buy_breakdown": {},
            "sell_breakdown": {},
        }

    total_turnover = entry_t + exit_t
    prof = BROKER_PROFILES.get(brokerage_model, BROKER_PROFILES["dhan"])
    sched = get_nse_cash_schedule(effective_date)

    # -----------------
    # BUY SIDE (ENTRY)
    # -----------------
    if trade_type == "delivery":
        brokerage_buy = round(min(prof["delivery_brokerage_cap"], prof["delivery_brokerage_rate"] * entry_t), 2)
        stt_buy = round(0.001 * entry_t, 2)  # 0.1%
        stamp_duty_buy = round(0.00015 * entry_t, 2)  # 0.015%
    else:  # intraday
        brokerage_buy = round(min(prof["intraday_brokerage_cap"], prof["intraday_brokerage_rate"] * entry_t), 2)
        stt_buy = 0.0  # 0% on intraday buy
        stamp_duty_buy = round(0.00003 * entry_t, 2)  # 0.003%

    exchange_charges_buy = round((sched["txn_rate_per_crore"] / 1e7) * entry_t, 2)
    ipft_buy = round((sched["ipft_rate_per_crore"] / 1e7) * entry_t, 5)
    sebi_buy = round((10.0 / 1e7) * entry_t, 2)
    gst_base_buy = brokerage_buy + exchange_charges_buy + sebi_buy + (ipft_buy if ipft_subject_to_gst else 0.0)
    gst_buy = round(0.18 * gst_base_buy, 2)
    slippage_buy = round((slippage_bps / 10000.0) * entry_t, 2)
    statutory_buy = round(brokerage_buy + stt_buy + exchange_charges_buy + sebi_buy + stamp_duty_buy + gst_buy, 2)
    total_buy = round(statutory_buy + slippage_buy, 2)

    # -----------------
    # SELL SIDE (EXIT)
    # -----------------
    if trade_type == "delivery":
        brokerage_sell = round(min(prof["delivery_brokerage_cap"], prof["delivery_brokerage_rate"] * exit_t), 2)
        stt_sell = round(0.001 * exit_t, 2)  # 0.1%
    else:  # intraday
        brokerage_sell = round(min(prof["intraday_brokerage_cap"], prof["intraday_brokerage_rate"] * exit_t), 2)
        stt_sell = round(0.00025 * exit_t, 2)  # 0.025%

    stamp_duty_sell = 0.0
    exchange_charges_sell = round((sched["txn_rate_per_crore"] / 1e7) * exit_t, 2)
    ipft_sell = round((sched["ipft_rate_per_crore"] / 1e7) * exit_t, 5)
    sebi_sell = round((10.0 / 1e7) * exit_t, 2)
    gst_base_sell = brokerage_sell + exchange_charges_sell + sebi_sell + (ipft_sell if ipft_subject_to_gst else 0.0)
    gst_sell = round(0.18 * gst_base_sell, 2)

    # DP charge: applicable on delivery sell leg
    if trade_type == "delivery" and is_dp_debit:
        if dp_charges is not None:
            dp_base = round(float(dp_charges) / (1.0 + prof["dp_charge_gst_rate"]), 2)
            dp_gst = round(float(dp_charges) - dp_base, 2)
            dp_fee = round(float(dp_charges), 2)
        else:
            dp_base = round(prof["dp_charge_base"], 2)
            dp_gst = round(prof["dp_charge_base"] * prof["dp_charge_gst_rate"], 2)
            dp_fee = round(dp_base + dp_gst, 2)
    else:
        dp_base = 0.0
        dp_gst = 0.0
        dp_fee = 0.0

    slippage_sell = round((slippage_bps / 10000.0) * exit_t, 2)
    statutory_sell = round(brokerage_sell + stt_sell + exchange_charges_sell + sebi_sell + gst_sell + dp_fee, 2)
    total_sell = round(statutory_sell + slippage_sell, 2)

    # -----------------
    # COMBINED LEDGER
    # -----------------
    total_brokerage = round(brokerage_buy + brokerage_sell, 2)
    total_stt = round(stt_buy + stt_sell, 2)
    exchange_charges = round((sched["txn_rate_per_crore"] / 1e7) * total_turnover, 2)
    ipft = round((sched["ipft_rate_per_crore"] / 1e7) * total_turnover, 5)
    combined_exchange_outflow = round((sched["combined_outflow_per_crore"] / 1e7) * total_turnover, 2)
    sebi_charges = round((10.0 / 1e7) * total_turnover, 2)
    stamp_duty = stamp_duty_buy
    gst_base = total_brokerage + exchange_charges + sebi_charges + (ipft if ipft_subject_to_gst else 0.0)
    gst = round(0.18 * gst_base, 2)
    slippage_amount = round(slippage_buy + slippage_sell, 2)

    statutory_fees = round(
        total_brokerage + total_stt + exchange_charges + sebi_charges + stamp_duty + gst + dp_fee, 2
    )
    total_cost = round(statutory_fees + slippage_amount, 2)
    effective_bps = round((total_cost / total_turnover) * 10000.0, 2) if total_turnover > 0 else 0.0

    return {
        "total_cost": total_cost,
        "statutory_fees": statutory_fees,
        "slippage_amount": slippage_amount,
        "effective_bps": effective_bps,
        "trade_type": trade_type,
        "breakdown": {
            "brokerage": total_brokerage,
            "stt": total_stt,
            "exchange_charges": exchange_charges,
            "ipft": ipft,
            "combined_exchange_outflow": combined_exchange_outflow,
            "sebi_charges": sebi_charges,
            "stamp_duty": stamp_duty,
            "gst": gst,
            "dp_charges": dp_fee,
            "dp_base": dp_base,
            "dp_gst": dp_gst,
            "slippage": slippage_amount,
            "slippage_entry": slippage_buy,
            "slippage_exit": slippage_sell,
            "broker_profile": brokerage_model,
            "exchange_schedule": sched["description"],
            "circular_ref": sched["circular_ref"],
        },
        "buy_breakdown": {
            "turnover": entry_t,
            "brokerage": brokerage_buy,
            "stt": stt_buy,
            "exchange_charges": exchange_charges_buy,
            "ipft": ipft_buy,
            "sebi_charges": sebi_buy,
            "stamp_duty": stamp_duty_buy,
            "gst": gst_buy,
            "slippage": slippage_buy,
            "statutory_fees": statutory_buy,
            "total_cost": total_buy,
        },
        "sell_breakdown": {
            "turnover": exit_t,
            "brokerage": brokerage_sell,
            "stt": stt_sell,
            "exchange_charges": exchange_charges_sell,
            "ipft": ipft_sell,
            "sebi_charges": sebi_sell,
            "stamp_duty": 0.0,
            "gst": gst_sell,
            "dp_base": dp_base,
            "dp_gst": dp_gst,
            "dp_charges": dp_fee,
            "slippage": slippage_sell,
            "statutory_fees": statutory_sell,
            "total_cost": total_sell,
        },
    }


# ---------------------------------------------------------------------------
# Market Regime Detection
# ---------------------------------------------------------------------------

def classify_market_regimes(df: pd.DataFrame) -> pd.Series:
    """
    Classify historical candles into 5 mutually exclusive structural regimes:
    BULLISH, BEARISH, SIDEWAYS, HIGH_VOLATILITY, LOW_VOLATILITY.
    """
    n = len(df)
    regimes = ["NEUTRAL"] * n
    if n < 30:
        return pd.Series(regimes, index=df.index)

    close = df["close"]
    ema_20 = close.ewm(span=20, adjust=False).mean()
    ema_50 = close.ewm(span=50, adjust=False).mean()
    atr = _calc_atr(df, 14)
    atr_mean_50 = atr.rolling(50, min_periods=10).mean()

    for i in range(20, n):
        cur_atr = atr.iloc[i]
        bench_atr = atr_mean_50.iloc[i] if pd.notna(atr_mean_50.iloc[i]) and atr_mean_50.iloc[i] > 0 else cur_atr

        # Volatility classification takes precedence
        if cur_atr > 1.45 * bench_atr:
            regimes[i] = "HIGH_VOLATILITY"
        elif cur_atr < 0.70 * bench_atr:
            regimes[i] = "LOW_VOLATILITY"
        else:
            diff_pct = (ema_20.iloc[i] - ema_50.iloc[i]) / ema_50.iloc[i] * 100.0
            if diff_pct > 1.0 and close.iloc[i] > ema_20.iloc[i]:
                regimes[i] = "BULLISH"
            elif diff_pct < -1.0 and close.iloc[i] < ema_20.iloc[i]:
                regimes[i] = "BEARISH"
            else:
                regimes[i] = "SIDEWAYS"

    return pd.Series(regimes, index=df.index)


# ---------------------------------------------------------------------------
# Strategy Signal Generators (Non-Repainting)
# ---------------------------------------------------------------------------

def _generate_signals_for_strategy(
    df: pd.DataFrame,
    strategy_type: str,
    target_rr: float = 2.0,
) -> list[dict]:
    """
    Extract discrete trade candidate signals for a specific strategy.
    Guarantees that each signal defines an available entry bar index >= confirmation bar index + 1.
    """
    n = len(df)
    signals = []

    high = df["high"]
    low = df["low"]
    open_ = df["open"]
    close = df["close"]
    atr = _calc_atr(df, 14)
    timestamps = df["timestamp"].astype(str)

    if strategy_type == "ORDER_BLOCK_RETEST":
        structure = detect_market_structure(df)
        order_blocks = detect_order_blocks(df, structure["breaks"])

        for ob in order_blocks:
            conf_bar = ob.get("confirmation_index", ob["candle_index"] + 1)
            direction = ob["direction"]
            z_high = ob["zone_high"]
            z_low = ob["zone_low"]
            stop_price = ob["invalidation_level"]
            min_entry_bar = conf_bar + 1

            if min_entry_bar >= n:
                continue

            # Scan forward for first retest on or after min_entry_bar
            for k in range(min_entry_bar, min(n, min_entry_bar + 25)):
                k_open = float(open_.iloc[k])
                k_high = float(high.iloc[k])
                k_low = float(low.iloc[k])

                if direction == "BULLISH":
                    if k_low <= z_high:
                        # Entry occurs at z_high or at open if gapped into zone
                        entry_price = min(k_open, z_high)
                        risk = entry_price - stop_price
                        if risk > 0:
                            signals.append({
                                "entry_bar": k,
                                "direction": "BULLISH",
                                "entry_price": round(entry_price, 2),
                                "stop_price": round(stop_price, 2),
                                "target_price": round(entry_price + (target_rr * risk), 2),
                                "setup_id": ob["id"],
                                "timestamp": timestamps.iloc[k],
                            })
                        break
                else:  # BEARISH
                    if k_high >= z_low:
                        entry_price = max(k_open, z_low)
                        risk = stop_price - entry_price
                        if risk > 0:
                            signals.append({
                                "entry_bar": k,
                                "direction": "BEARISH",
                                "entry_price": round(entry_price, 2),
                                "stop_price": round(stop_price, 2),
                                "target_price": round(entry_price - (target_rr * risk), 2),
                                "setup_id": ob["id"],
                                "timestamp": timestamps.iloc[k],
                            })
                        break

    elif strategy_type == "FVG_FILL_REVERSAL":
        fvgs = detect_fair_value_gaps(df)
        for f in fvgs:
            conf_bar = f["confirmation_index"]
            direction = f["direction"]
            z_high = f["zone_high"]
            z_low = f["zone_low"]
            mid_gap = (z_high + z_low) / 2.0
            stop_price = z_low if direction == "BULLISH" else z_high
            min_entry_bar = conf_bar + 1

            for k in range(min_entry_bar, min(n, min_entry_bar + 20)):
                k_high = float(high.iloc[k])
                k_low = float(low.iloc[k])
                k_open = float(open_.iloc[k])

                if direction == "BULLISH" and k_low <= mid_gap:
                    entry_price = min(k_open, mid_gap)
                    risk = entry_price - stop_price
                    if risk > 0:
                        signals.append({
                            "entry_bar": k,
                            "direction": "BULLISH",
                            "entry_price": round(entry_price, 2),
                            "stop_price": round(stop_price, 2),
                            "target_price": round(entry_price + (target_rr * risk), 2),
                            "setup_id": f["id"],
                            "timestamp": timestamps.iloc[k],
                        })
                    break
                elif direction == "BEARISH" and k_high >= mid_gap:
                    entry_price = max(k_open, mid_gap)
                    risk = stop_price - entry_price
                    if risk > 0:
                        signals.append({
                            "entry_bar": k,
                            "direction": "BEARISH",
                            "entry_price": round(entry_price, 2),
                            "stop_price": round(stop_price, 2),
                            "target_price": round(entry_price - (target_rr * risk), 2),
                            "setup_id": f["id"],
                            "timestamp": timestamps.iloc[k],
                        })
                    break

    elif strategy_type == "BOS_CONTINUATION":
        structure = detect_market_structure(df)
        breaks = structure.get("breaks", [])

        for b in breaks:
            if b["type"] == "BOS":
                conf_bar = b["confirmation_index"]
                direction = b["direction"]
                entry_bar = conf_bar + 1
                if entry_bar >= n:
                    continue

                cur_atr = float(atr.iloc[conf_bar]) if pd.notna(atr.iloc[conf_bar]) else 10.0
                entry_price = float(open_.iloc[entry_bar])

                if direction == "BULLISH":
                    stop_price = entry_price - (1.5 * cur_atr)
                    risk = entry_price - stop_price
                    signals.append({
                        "entry_bar": entry_bar,
                        "direction": "BULLISH",
                        "entry_price": round(entry_price, 2),
                        "stop_price": round(stop_price, 2),
                        "target_price": round(entry_price + (target_rr * risk), 2),
                        "setup_id": f"bos-bull-{conf_bar}",
                        "timestamp": timestamps.iloc[entry_bar],
                    })
                else:
                    stop_price = entry_price + (1.5 * cur_atr)
                    risk = stop_price - entry_price
                    signals.append({
                        "entry_bar": entry_bar,
                        "direction": "BEARISH",
                        "entry_price": round(entry_price, 2),
                        "stop_price": round(stop_price, 2),
                        "target_price": round(entry_price - (target_rr * risk), 2),
                        "setup_id": f"bos-bear-{conf_bar}",
                        "timestamp": timestamps.iloc[entry_bar],
                    })

    elif strategy_type == "LIQUIDITY_SWEEP_REVERSAL":
        structure = detect_market_structure(df)
        liq = detect_liquidity_and_sweeps(df, structure["swings"], scan_lookback=None)
        sweeps = liq.get("sweeps", [])

        for s in sweeps:
            if s.get("reclaim_confirmed") and s.get("opposing_reaction") is True:
                entry_bar = s.get("signal_available_index")
                if entry_bar is None or entry_bar >= n:
                    continue

                direction = "BEARISH" if "BEARISH" in s["direction"] else "BULLISH"
                entry_price = float(open_.iloc[entry_bar])
                occ_idx = s.get("occurrence_index", entry_bar - 2)
                cur_atr = float(atr.iloc[occ_idx]) if pd.notna(atr.iloc[occ_idx]) else 10.0

                if direction == "BULLISH":
                    stop_price = float(s["sweep_price"]) - (0.2 * cur_atr)
                    risk = entry_price - stop_price
                    if risk > 0:
                        signals.append({
                            "entry_bar": entry_bar,
                            "direction": "BULLISH",
                            "entry_price": round(entry_price, 2),
                            "stop_price": round(stop_price, 2),
                            "target_price": round(entry_price + (target_rr * risk), 2),
                            "setup_id": f"sweep-bull-{occ_idx}",
                            "timestamp": timestamps.iloc[entry_bar],
                        })
                else:
                    stop_price = float(s["sweep_price"]) + (0.2 * cur_atr)
                    risk = stop_price - entry_price
                    if risk > 0:
                        signals.append({
                            "entry_bar": entry_bar,
                            "direction": "BEARISH",
                            "entry_price": round(entry_price, 2),
                            "stop_price": round(stop_price, 2),
                            "target_price": round(entry_price - (target_rr * risk), 2),
                            "setup_id": f"sweep-bear-{occ_idx}",
                            "timestamp": timestamps.iloc[entry_bar],
                        })

    elif strategy_type == "SMC_VOLUME_CONFIRMATION":
        avg_vol_20 = df["volume"].rolling(20).mean()
        structure = detect_market_structure(df)
        order_blocks = detect_order_blocks(df, structure["breaks"])

        for ob in order_blocks:
            conf_bar = ob.get("confirmation_index", ob["candle_index"] + 1)
            vol_ratio = ob.get("volume_expansion_ratio", 1.0)
            if vol_ratio >= 1.4:  # Institutional volume surge
                entry_bar = conf_bar + 1
                if entry_bar >= n:
                    continue

                direction = ob["direction"]
                entry_price = float(open_.iloc[entry_bar])
                stop_price = ob["invalidation_level"]
                risk = abs(entry_price - stop_price)

                if risk > 0:
                    target_price = entry_price + (target_rr * risk) if direction == "BULLISH" else entry_price - (target_rr * risk)
                    signals.append({
                        "entry_bar": entry_bar,
                        "direction": direction,
                        "entry_price": round(entry_price, 2),
                        "stop_price": round(stop_price, 2),
                        "target_price": round(target_price, 2),
                        "setup_id": f"vol-ob-{conf_bar}",
                        "timestamp": timestamps.iloc[entry_bar],
                    })

    # Sort signals strictly chronologically by entry_bar
    signals = sorted(signals, key=lambda s: s["entry_bar"])
    return signals


# ---------------------------------------------------------------------------
# Master Backtester Execution Engine (Audited Priorities 1, 2, 4)
# ---------------------------------------------------------------------------

def run_smc_backtest(
    symbol: str,
    strategy_type: str = "ORDER_BLOCK_RETEST",
    bars: Optional[list[dict]] = None,
    target_rr: float = 2.0,
    cost_bps: float = 5.0,
    use_indian_costs: bool = True,
    trade_type: str = "delivery",  # "delivery" (default for swing) or "intraday"
    brokerage_model: str = "dhan",  # "dhan" (default), "zerodha", "flat_20", "percentage"
    dp_charges: Optional[float] = None,
    dp_policy: Optional[str] = None,  # None uses broker default ("per_order" for Dhan, "per_isin_daily" for Zerodha)
    allow_overnight_short: bool = False,
    risk_pct: float = 0.02,  # Risk 2.0% of equity per trade
    max_holding_bars: int = 15,
    allow_overlapping: bool = False,
    initial_capital: float = 100000.0,
    risk_free_rate: float = 0.06,  # Assumed benchmark annual risk-free rate (6.0%)
) -> dict:
    """
    Run a rigorous, non-repainting chronological walk-forward backtest.

    Audited Enhancements (Phase 9.3):
    1. Default broker profile is Dhan retail pricing (₹0 delivery, min(₹20, 0.03%) intraday).
    2. Date-effective NSE cash transaction charge & IPFT schedule across 5 date-bound tiers.
    3. Dhan DP charges modeled per delivery sell order/instruction (Early Pay-In policy confirmation).
    4. Delivery overnight shorting rejected as UNSUPPORTED_OVERNIGHT_SHORT (retail spot delivery shorting impossible without SLB).
    5. Continuous daily mark-to-market equity curve with unrealized P&L and cash tracking on every trading bar.
    6. Annualized Sharpe and Sortino ratios computed with daily excess returns penalized against RBI 91-day T-Bill proxy.
    7. Wilson score 95% confidence intervals for win rates.
    8. 5,000-resample Bootstrap confidence intervals for Expectancy (₹) and Profit Factor with capped zero-loss handling and lag-1 autocorrelation testing.
    9. Sample size validity assessment and institutional warning tiers.
    """
    sym = symbol.upper()
    if bars is None:
        bars = get_bars(sym)

    if not bars or len(bars) < 12:
        return {
            "symbol": sym,
            "strategy": strategy_type,
            "error": "Insufficient historical data for backtesting (minimum 12 bars required)",
            "bars_count": len(bars) if bars else 0,
            "trades": [],
            "rejected_trades": [],
            "summary": {
                "total_trades": 0,
                "gross_win_count": 0,
                "gross_loss_count": 0,
                "gross_win_rate_pct": 0.0,
                "gross_profit_factor": 1.0,
                "gross_pnl": 0.0,
                "gross_expectancy_inr": 0.0,
                "win_count": 0,
                "loss_count": 0,
                "win_rate_pct": 0.0,
                "profit_factor": 1.0,
                "net_profit_factor": 1.0,
                "net_pnl": 0.0,
                "expectancy_inr": 0.0,
                "expectancy_pct": 0.0,
                "average_r": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "max_drawdown_inr": 0.0,
                "market_exposure_pct": 0.0,
                "average_capital_employed": 0.0,
                "max_capital_employed": 0.0,
                "capital_utilization_pct": 0.0,
                "trades_flipped_win_to_loss": 0,
                "average_holding_bars": 0.0,
                "net_return_pct": 0.0,
                "final_equity": initial_capital,
                "gross_profit": 0.0,
                "gross_loss": 0.0,
                "total_statutory_fees": 0.0,
                "total_slippage": 0.0,
                "trade_type": trade_type,
                "brokerage_model": brokerage_model,
                "transaction_cost_bps": cost_bps,
                "risk_free_rate_assumed": float(risk_free_rate),
                "sample_size_assessment": evaluate_sample_size_validity(0),
            },
            "equity_curve": [{"bar": 0, "timestamp": "", "equity": initial_capital}],
            "daily_equity_series": [initial_capital],
        }

    df = _prepare_df(bars)
    n = len(df)
    regimes = classify_market_regimes(df)

    # 1. Generate candidate signals
    raw_signals = _generate_signals_for_strategy(df, strategy_type, target_rr=target_rr)

    trades = []
    rejected_trades = []
    settled_dp_instructions = set()  # Track order IDs or (ISIN/sym, settlement_date) for DP charge debits
    capital = float(initial_capital)
    last_exit_bar = -1
    total_statutory_fees = 0.0
    total_slippage_cost = 0.0

    high = df["high"]
    low = df["low"]
    open_ = df["open"]
    close = df["close"]
    timestamps = df["timestamp"].astype(str)

    prof = BROKER_PROFILES.get(brokerage_model, BROKER_PROFILES["dhan"])
    active_dp_policy = dp_policy or prof.get("dp_policy", "per_order")

    # 2. Chronological trade execution loop
    for sig in raw_signals:
        entry_bar = sig["entry_bar"]

        # Prevent overlapping concurrent positions if configured
        if not allow_overlapping and entry_bar <= last_exit_bar:
            continue

        direction = sig["direction"]
        entry_price = float(sig["entry_price"])
        stop_price = float(sig["stop_price"])
        target_price = float(sig["target_price"])

        # Reject delivery overnight shorting (unsupported in Indian cash equity without SLB)
        if direction == "BEARISH" and trade_type == "delivery" and not allow_overnight_short:
            rejected_trades.append({
                "setup_id": sig["setup_id"],
                "entry_bar": entry_bar,
                "entry_time": timestamps.iloc[entry_bar],
                "reason": "UNSUPPORTED_OVERNIGHT_SHORT",
                "entry_price": entry_price,
                "capital": round(capital, 2),
                "detail": "Short selling in Indian cash equity delivery segment is unsupported without Securities Lending & Borrowing (SLB). Intraday shorting is permitted.",
            })
            continue

        price_risk_per_share = abs(entry_price - stop_price)
        if price_risk_per_share <= 0:
            continue

        # Position Sizing: Strict Risk & Capital Constraints (Priority 4)
        risk_budget = capital * risk_pct

        # Include estimated round-trip friction in share sizing
        est_cost_rate = (0.0025 if trade_type == "delivery" else 0.001) + (cost_bps / 10000.0)
        effective_risk_per_share = price_risk_per_share + (entry_price * est_cost_rate)

        raw_shares = math.floor(risk_budget / effective_risk_per_share)
        max_affordable_shares = math.floor(capital / entry_price)
        shares = min(raw_shares, max_affordable_shares)

        # Strict constraint: Reject trade if 1 share exceeds risk budget or capital
        if shares <= 0:
            reason = "CAPITAL_EXCEEDED" if entry_price > capital else "RISK_BUDGET_EXCEEDED"
            rejected_trades.append({
                "setup_id": sig["setup_id"],
                "entry_bar": entry_bar,
                "entry_time": timestamps.iloc[entry_bar],
                "reason": reason,
                "entry_price": entry_price,
                "capital": round(capital, 2),
                "risk_budget": round(risk_budget, 2),
                "effective_risk_per_share": round(effective_risk_per_share, 2),
            })
            continue

        actual_risk_inr = round(shares * effective_risk_per_share, 2)
        actual_risk_pct = round((actual_risk_inr / capital) * 100.0, 2)
        position_value = round(shares * entry_price, 2)

        # Scan subsequent bars for exit
        exit_bar = None
        exit_price = None
        outcome = "EXPIRED"

        for k in range(entry_bar, min(n, entry_bar + max_holding_bars + 1)):
            k_open = float(open_.iloc[k])
            k_high = float(high.iloc[k])
            k_low = float(low.iloc[k])

            if direction == "BULLISH":
                # Gap-down below stop loss: exit at open (absorbs gap slippage)
                if k_open <= stop_price:
                    exit_bar = k
                    exit_price = k_open
                    outcome = "LOSS"
                    break

                # Conservative same-candle resolution: check SL first, then TP
                if k_low <= stop_price:
                    exit_bar = k
                    exit_price = stop_price
                    outcome = "LOSS"
                    break

                # Target hit
                if k_high >= target_price:
                    exit_bar = k
                    exit_price = max(k_open, target_price) if k_open >= target_price else target_price
                    outcome = "WIN"
                    break

            else:  # BEARISH
                # Gap-up above stop loss: exit at open
                if k_open >= stop_price:
                    exit_bar = k
                    exit_price = k_open
                    outcome = "LOSS"
                    break

                # Conservative same-candle resolution: check SL first
                if k_high >= stop_price:
                    exit_bar = k
                    exit_price = stop_price
                    outcome = "LOSS"
                    break

                # Target hit
                if k_low <= target_price:
                    exit_price = min(k_open, target_price) if k_open <= target_price else target_price
                    exit_bar = k
                    outcome = "WIN"
                    break

        # Max holding period exit at close
        if exit_bar is None:
            exit_bar = min(n - 1, entry_bar + max_holding_bars)
            exit_price = float(close.iloc[exit_bar])
            if direction == "BULLISH":
                outcome = "WIN" if exit_price > entry_price else "LOSS"
            else:
                outcome = "WIN" if exit_price < entry_price else "LOSS"

        # Calculate Gross P&L on exact share count
        if direction == "BULLISH":
            gross_pnl = shares * (exit_price - entry_price)
            raw_pct = (exit_price - entry_price) / entry_price * 100.0
        else:
            gross_pnl = shares * (entry_price - exit_price)
            raw_pct = (entry_price - exit_price) / entry_price * 100.0

        # Calculate exact turnover on actual entry and exit prices
        entry_turnover = shares * entry_price
        exit_turnover = shares * exit_price
        total_trade_turnover = entry_turnover + exit_turnover

        if use_indian_costs:
            exit_date = str(timestamps.iloc[exit_bar])[:10]
            is_delivery_sell = (direction == "BULLISH" and trade_type == "delivery")
            if is_delivery_sell:
                if active_dp_policy == "per_isin_daily":
                    dp_key = (sym, exit_date)
                    if dp_key in settled_dp_instructions:
                        is_debit = False
                    else:
                        is_debit = True
                        settled_dp_instructions.add(dp_key)
                else:  # "per_order" (Dhan EPI debit per executed delivery sell order)
                    order_key = sig.get("parent_order_id") or sig.get("order_id") or f"order_{len(trades)+1}"
                    if order_key in settled_dp_instructions:
                        is_debit = False
                    else:
                        is_debit = True
                        settled_dp_instructions.add(order_key)
            else:
                is_debit = False

            costs = calculate_indian_transaction_costs(
                entry_turnover=entry_turnover,
                exit_turnover=exit_turnover,
                trade_type=trade_type,
                brokerage_model=brokerage_model,
                effective_date=timestamps.iloc[entry_bar],
                dp_charges=dp_charges,
                is_dp_debit=is_debit,
                dp_policy=active_dp_policy,
                slippage_bps=cost_bps,
            )
            fees = costs["statutory_fees"]
            slippage = costs["slippage_amount"]
            entry_friction = costs["buy_breakdown"]["total_cost"]
        else:
            slippage_entry = round((cost_bps / 10000.0) * entry_turnover, 2)
            slippage_exit = round((cost_bps / 10000.0) * exit_turnover, 2)
            fees = 0.0
            slippage = round(slippage_entry + slippage_exit, 2)
            entry_friction = slippage_entry

        total_statutory_fees += fees
        total_slippage_cost += slippage
        total_trade_costs = fees + slippage

        net_pnl = gross_pnl - total_trade_costs
        net_pct = (net_pnl / position_value) * 100.0 if position_value > 0 else 0.0
        realized_r = round(net_pnl / max(risk_budget, 1.0), 2)

        capital += net_pnl
        last_exit_bar = exit_bar

        entry_regime = regimes.iloc[entry_bar] if entry_bar < len(regimes) else "NEUTRAL"

        trades.append({
            "trade_id": len(trades) + 1,
            "direction": direction,
            "strategy": strategy_type,
            "setup_id": sig["setup_id"],
            "entry_bar": entry_bar,
            "entry_time": timestamps.iloc[entry_bar],
            "entry_price": round(entry_price, 2),
            "stop_loss": round(stop_price, 2),
            "take_profit": round(target_price, 2),
            "exit_bar": exit_bar,
            "exit_time": timestamps.iloc[exit_bar],
            "exit_price": round(exit_price, 2),
            "shares": shares,
            "position_value": round(position_value, 2),
            "actual_risk_inr": actual_risk_inr,
            "actual_risk_pct": actual_risk_pct,
            "outcome": outcome,
            "bars_held": exit_bar - entry_bar,
            "regime": entry_regime,
            "gross_pnl": round(gross_pnl, 2),
            "statutory_fees": round(fees, 2),
            "fees": round(fees, 2),  # backwards compatibility
            "slippage": round(slippage, 2),
            "entry_friction": entry_friction,
            "total_costs": round(total_trade_costs, 2),
            "net_pnl": round(net_pnl, 2),
            "raw_pnl_pct": round(raw_pct, 2),
            "net_pnl_pct": round(net_pct, 2),
            "realized_r": realized_r,
            "equity_after": round(capital, 2),
        })

    # Summary Statistics: Independent Gross vs Net calculations (Priority 2)
    total_trades = len(trades)

    # 1. Gross metrics (Strictly using gross_pnl)
    gross_wins = [t for t in trades if t["gross_pnl"] > 0]
    gross_losses = [t for t in trades if t["gross_pnl"] < 0]
    gross_win_count = len(gross_wins)
    gross_loss_count = len(gross_losses)
    gross_win_rate = round((gross_win_count / total_trades * 100.0), 1) if total_trades > 0 else 0.0

    total_gross_profit = sum(t["gross_pnl"] for t in gross_wins)
    total_gross_loss = abs(sum(t["gross_pnl"] for t in gross_losses))
    gross_profit_factor = (
        round(total_gross_profit / total_gross_loss, 2)
        if total_gross_loss > 0
        else (round(total_gross_profit, 2) if total_gross_profit > 0 else 1.0)
    )
    total_gross_pnl = sum(t["gross_pnl"] for t in trades)
    gross_expectancy_inr = round(total_gross_pnl / total_trades, 2) if total_trades > 0 else 0.0
    gross_expectancy_pct = round(sum(t["raw_pnl_pct"] for t in trades) / total_trades, 2) if total_trades > 0 else 0.0

    # 2. Net metrics (Strictly using net_pnl)
    net_wins = [t for t in trades if t["net_pnl"] > 0]
    net_losses = [t for t in trades if t["net_pnl"] < 0]
    net_win_count = len(net_wins)
    net_loss_count = len(net_losses)
    net_win_rate = round((net_win_count / total_trades * 100.0), 1) if total_trades > 0 else 0.0

    total_net_profit = sum(t["net_pnl"] for t in net_wins)
    total_net_loss = abs(sum(t["net_pnl"] for t in net_losses))
    net_profit_factor = (
        round(total_net_profit / total_net_loss, 2)
        if total_net_loss > 0
        else (round(total_net_profit, 2) if total_net_profit > 0 else 1.0)
    )
    total_net_pnl = sum(t["net_pnl"] for t in trades)
    net_expectancy_inr = round(total_net_pnl / total_trades, 2) if total_trades > 0 else 0.0
    net_expectancy_pct = round(sum(t["net_pnl_pct"] for t in trades) / total_trades, 2) if total_trades > 0 else 0.0

    trades_flipped_win_to_loss = len([t for t in trades if t["gross_pnl"] > 0 and t["net_pnl"] <= 0])
    avg_r = round(sum(t["realized_r"] for t in trades) / total_trades, 2) if total_trades > 0 else 0.0
    avg_holding = round(sum(t["bars_held"] for t in trades) / total_trades, 1) if total_trades > 0 else 0.0

    # 3. Continuous Daily Mark-to-Market Portfolio Equity Series (Phase 9.3 Priority 5)
    # The portfolio equity is tracked continuously every trading day from bar 0 to n-1.
    # Open positions are marked to market on each day using df["close"].
    # Realized gains/losses from completed trades are held in cash.
    # On days without open positions (idle cash), equity is constant (daily return = 0.0%).
    # Excess return is: 0.0 - r_f_daily, accurately penalizing idle cash against the assumed benchmark.
    daily_equity = [initial_capital] * n
    for k in range(n):
        k_close = float(close.iloc[k])
        realized_pnl_sum = sum(t["net_pnl"] for t in trades if t["exit_bar"] <= k)

        unrealized_sum = 0.0
        for t in trades:
            if t["entry_bar"] <= k < t["exit_bar"]:
                if t["direction"] == "BULLISH":
                    unrealized_gross = t["shares"] * (k_close - t["entry_price"])
                else:
                    unrealized_gross = t["shares"] * (t["entry_price"] - k_close)
                unrealized_net = unrealized_gross - t.get("entry_friction", 0.0)
                unrealized_sum += unrealized_net

        daily_equity[k] = round(initial_capital + realized_pnl_sum + unrealized_sum, 2)

    eq_series = pd.Series(daily_equity)
    periodic_returns = eq_series.pct_change().dropna()

    # Annualized Sharpe & Sortino using configurable benchmark risk-free rate
    r_f_daily = float(risk_free_rate) / 252.0
    if len(periodic_returns) >= 5 and periodic_returns.std() > 0:
        excess_returns = periodic_returns - r_f_daily
        mean_excess = float(excess_returns.mean())
        std_ret = float(periodic_returns.std())
        sharpe = round(float((mean_excess / std_ret) * math.sqrt(252)), 2)

        # Sortino downside convention: sqrt( (1/N) * sum( min(R_k - R_f_daily, 0)^2 ) )
        downside_diffs = np.minimum(excess_returns, 0.0)
        downside_sq = downside_diffs ** 2
        downside_dev = math.sqrt(float(np.mean(downside_sq)))
        if downside_dev > 0:
            sortino = round(float((mean_excess / downside_dev) * math.sqrt(252)), 2)
        else:
            sortino = sharpe if sharpe > 0 else 0.0
    else:
        sharpe = 0.0
        sortino = 0.0

    # Maximum Drawdown in % and INR
    peaks = eq_series.cummax()
    dd_pct_series = (eq_series - peaks) / peaks * 100.0
    dd_inr_series = eq_series - peaks
    max_dd_pct = abs(round(float(dd_pct_series.min()), 2)) if not dd_pct_series.empty else 0.0
    max_dd_inr = abs(round(float(dd_inr_series.min()), 2)) if not dd_inr_series.empty else 0.0

    # Continuous daily mark-to-market equity curve
    equity_curve = [
        {"bar": k, "timestamp": timestamps.iloc[k], "equity": daily_equity[k]}
        for k in range(n)
    ]

    # Exposure & Capital Utilization
    total_bars_held = sum(t["bars_held"] for t in trades)
    market_exposure_pct = round((total_bars_held / max(n, 1)) * 100.0, 2)
    avg_capital_employed = round(sum(t["position_value"] for t in trades) / total_trades, 2) if total_trades > 0 else 0.0
    max_capital_employed = round(max((t["position_value"] for t in trades), default=0.0), 2)
    capital_utilization_pct = round((avg_capital_employed / initial_capital) * 100.0, 2) if initial_capital > 0 else 0.0

    # Long vs Short Performance
    long_trades = [t for t in trades if t["direction"] == "BULLISH"]
    short_trades = [t for t in trades if t["direction"] == "BEARISH"]

    long_wins = [t for t in long_trades if t["net_pnl"] > 0]
    short_wins = [t for t in short_trades if t["net_pnl"] > 0]

    long_perf = {
        "trades_count": len(long_trades),
        "win_rate_pct": round((len(long_wins) / len(long_trades) * 100.0), 1) if long_trades else 0.0,
        "net_pnl": round(sum(t["net_pnl"] for t in long_trades), 2),
    }
    short_perf = {
        "trades_count": len(short_trades),
        "win_rate_pct": round((len(short_wins) / len(short_trades) * 100.0), 1) if short_trades else 0.0,
        "net_pnl": round(sum(t["net_pnl"] for t in short_trades), 2),
    }

    # 4. Statistical Rigor: Wilson Score CIs, Bootstrap Statistics (5,000 resamples), and Sample Size Validity (Phase 9.3)
    net_win_rate_ci = calculate_wilson_score_interval(net_win_count, total_trades, confidence=0.95)
    gross_win_rate_ci = calculate_wilson_score_interval(gross_win_count, total_trades, confidence=0.95)
    sample_size_assessment = evaluate_sample_size_validity(total_trades)
    bootstrap_stats = calculate_bootstrap_statistics(trades, n_resamples=5000)

    return {
        "symbol": sym,
        "strategy": strategy_type,
        "sample_size": total_trades,
        "rejected_trades_count": len(rejected_trades),
        "summary": {
            "total_trades": total_trades,
            "gross_win_count": gross_win_count,
            "gross_loss_count": gross_loss_count,
            "gross_win_rate_pct": gross_win_rate,
            "gross_win_rate_95_ci_pct": list(gross_win_rate_ci),
            "gross_profit_factor": gross_profit_factor,
            "gross_pnl": round(total_gross_pnl, 2),
            "gross_expectancy_inr": gross_expectancy_inr,
            "gross_expectancy_pct": gross_expectancy_pct,
            "win_count": net_win_count,
            "loss_count": net_loss_count,
            "win_rate_pct": net_win_rate,
            "win_rate_95_ci_pct": list(net_win_rate_ci),
            "profit_factor": net_profit_factor,  # canonical
            "net_profit_factor": net_profit_factor,
            "net_pnl": round(total_net_pnl, 2),
            "expectancy_inr": net_expectancy_inr,
            "expectancy_pct": net_expectancy_pct,
            "average_r": avg_r,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown_pct": max_dd_pct,
            "max_drawdown_inr": max_dd_inr,
            "market_exposure_pct": market_exposure_pct,
            "average_capital_employed": avg_capital_employed,
            "max_capital_employed": max_capital_employed,
            "capital_utilization_pct": capital_utilization_pct,
            "trades_flipped_win_to_loss": trades_flipped_win_to_loss,
            "average_holding_bars": avg_holding,
            "net_return_pct": round(((capital - initial_capital) / initial_capital) * 100.0, 2),
            "final_equity": round(capital, 2),
            "gross_profit": round(total_gross_profit, 2),
            "gross_loss": round(total_gross_loss, 2),
            "total_statutory_fees": round(total_statutory_fees, 2),
            "total_slippage": round(total_slippage_cost, 2),
            "trade_type": trade_type,
            "brokerage_model": brokerage_model,
            "dp_policy": active_dp_policy,
            "transaction_cost_bps": cost_bps,
            "risk_free_rate_assumed": float(risk_free_rate),
            "risk_free_benchmark_note": f"Assumed annual benchmark risk-free rate of {risk_free_rate*100.0:.1f}% (e.g. RBI 91-day T-Bill / repo proxy), daily rf = {r_f_daily*10000.0:.2f} bps. Days without open positions earn 0.0% and are penalized against rf.",
            "sortino_downside_convention": "sqrt( (1/N) * sum( min(R_k - R_f_daily, 0)^2 ) )",
            "sample_size_assessment": sample_size_assessment,
            "bootstrap_analysis": bootstrap_stats,
            "disclaimers": {
                "survivorship_bias": "Backtest executed on surviving listed stock dataset; does not account for historically delisted or suspended securities (survivorship bias).",
                "corporate_actions": "Historical prices use split-adjusted database bars; dividends, buybacks, and restructuring cash flows may affect historical cost basis.",
                "lookahead_prevention": "Strict zero-lookahead execution: order entered on NEXT candle open after signal confirmation.",
                "statutory_notice": "Backtest results are historical simulations and do not guarantee future profitability or statistical validity. Past performance is not indicative of future market returns.",
            },
        },
        "performance_breakdown": {
            "long": long_perf,
            "short": short_perf,
        },
        "trades": trades,
        "rejected_trades": rejected_trades,
        "equity_curve": equity_curve,
        "daily_equity_series": daily_equity,
        "metadata": build_standard_metadata(
            provider="yfinance",
            instrument="EQUITY",
            symbol=sym,
            timeframe="1D",
            data_mode=DataMode.SIMULATED.value,
            disclaimer="Simulated quantitative backtest under Indian statutory cost schedule. Not indicative of future market execution.",
        ),
        "disclaimers": {
            "survivorship_bias": "Backtest executed on surviving listed stock dataset; does not account for historically delisted or suspended securities (survivorship bias).",
            "corporate_actions": "Historical prices use split-adjusted database bars; dividends, buybacks, and restructuring cash flows may affect historical cost basis.",
            "lookahead_prevention": "Strict zero-lookahead execution: order entered on NEXT candle open after signal confirmation.",
            "statutory_notice": "Backtest results are historical simulations and do not guarantee future profitability or statistical validity. Past performance is not indicative of future market returns.",
        },
    }


# ---------------------------------------------------------------------------
# Walk-Forward Chronological Rolling / Expanding Windows (Priority 5)
# ---------------------------------------------------------------------------

def run_walk_forward_validation(
    symbol: str,
    strategy_type: str = "ORDER_BLOCK_RETEST",
    bars: Optional[list[dict]] = None,
    num_windows: int = 3,
    window_type: str = "rolling",  # "rolling" or "expanding"
    warmup_bars: int = 25,
    train_ratio: float = 0.60,
    target_rr: float = 2.0,
    cost_bps: float = 5.0,
    trade_type: str = "delivery",
    brokerage_model: str = "dhan",
    dp_policy: Optional[str] = None,
    risk_free_rate: float = 0.06,
) -> dict:
    """
    Perform rigorous chronological multi-window walk-forward validation.

    Audited Enhancements (Phase 9.3):
    1. Default broker profile is Dhan retail pricing with per-order EPI DP charge policy.
    2. Date-effective NSE cash charges and IPFT across 5 date-bound tiers.
    3. Multi-window rolling / expanding walk-forward slices instead of a naive single 60/40 split.
    4. Historical warm-up data made available to test windows for indicator seeding with zero trade leakage.
    5. Frozen strategy parameters before test windows.
    6. Institutional sample size thresholds: >= 30 trades strictly required for out-of-sample evaluation.
    7. 5,000-resample Bootstrap confidence intervals for out-of-sample expectancy and profit factor with zero-loss cap.
    8. Wilson score confidence interval for win rate.
    9. Explicit insufficient-evidence classification when sample size is low or CI crosses 1.0.
    """
    sym = symbol.upper()
    if bars is None:
        bars = get_bars(sym)

    if not bars or len(bars) < 30:
        return {
            "symbol": sym,
            "strategy": strategy_type,
            "error": "Insufficient bars for walk-forward validation (minimum 30 required)",
        }

    df = _prepare_df(bars)
    n = len(df)

    # Compute step size for multi-window generation
    eff_bars = n - warmup_bars
    k_windows = max(1, min(num_windows, eff_bars // 10))
    step_size = max(6, eff_bars // (k_windows + 1))

    window_summaries = []
    all_oos_trades = []
    train_pfs = []
    train_wrs = []

    for w in range(k_windows):
        # 1. Define In-Sample (Train) window
        if window_type == "expanding":
            train_start = 0
        else:  # rolling
            train_start = w * step_size
        train_end = warmup_bars + (w + 1) * step_size

        train_bars = df.iloc[train_start:train_end].to_dict("records")
        if len(train_bars) < 12:
            continue

        train_res = run_smc_backtest(
            sym,
            strategy_type=strategy_type,
            bars=train_bars,
            target_rr=target_rr,
            cost_bps=cost_bps,
            trade_type=trade_type,
            brokerage_model=brokerage_model,
            dp_policy=dp_policy,
            risk_free_rate=risk_free_rate,
        )

        # 2. Define Out-of-Sample (Test) window with warm-up
        test_start = train_end
        test_end = min(n, train_end + step_size) if (w < k_windows - 1) else n
        if test_start >= test_end:
            continue

        # Warm-up slice before test_start ensures indicator readiness
        slice_start = max(0, test_start - warmup_bars)
        warmup_offset = test_start - slice_start
        test_slice_bars = df.iloc[slice_start:test_end].to_dict("records")

        # Run backtest with frozen parameters on slice
        test_slice_res = run_smc_backtest(
            sym,
            strategy_type=strategy_type,
            bars=test_slice_bars,
            target_rr=target_rr,
            cost_bps=cost_bps,
            trade_type=trade_type,
            brokerage_model=brokerage_model,
            dp_policy=dp_policy,
            risk_free_rate=risk_free_rate,
        )

        # Filter trades: strictly include only trades whose entry occurred in the test window
        oos_window_trades = [
            t for t in test_slice_res.get("trades", [])
            if t["entry_bar"] >= warmup_offset
        ]

        # Calculate window-specific OOS metrics
        w_oos_trades_count = len(oos_window_trades)
        w_oos_wins = [t for t in oos_window_trades if t["net_pnl"] > 0]
        w_oos_losses = [t for t in oos_window_trades if t["net_pnl"] < 0]
        w_oos_win_rate = round(len(w_oos_wins) / w_oos_trades_count * 100.0, 1) if w_oos_trades_count > 0 else 0.0
        w_oos_gross_profit = sum(t["gross_pnl"] for t in oos_window_trades if t["gross_pnl"] > 0)
        w_oos_gross_loss = abs(sum(t["gross_pnl"] for t in oos_window_trades if t["gross_pnl"] < 0))
        w_oos_net_profit = sum(t["net_pnl"] for t in w_oos_wins)
        w_oos_net_loss = abs(sum(t["net_pnl"] for t in w_oos_losses))
        w_oos_net_pf = (
            round(w_oos_net_profit / w_oos_net_loss, 2)
            if w_oos_net_loss > 0
            else (round(w_oos_net_profit, 2) if w_oos_net_profit > 0 else 1.0)
        )
        w_oos_net_pnl = round(sum(t["net_pnl"] for t in oos_window_trades), 2)

        window_summaries.append({
            "window_index": w + 1,
            "train_period": {
                "start": str(df["timestamp"].iloc[train_start]),
                "end": str(df["timestamp"].iloc[train_end - 1]),
                "bars": train_end - train_start,
                "summary": train_res["summary"],
            },
            "test_period_oos": {
                "start": str(df["timestamp"].iloc[test_start]),
                "end": str(df["timestamp"].iloc[test_end - 1]),
                "bars": test_end - test_start,
                "warmup_bars": warmup_offset,
                "trades_count": w_oos_trades_count,
                "win_rate_pct": w_oos_win_rate,
                "net_profit_factor": w_oos_net_pf,
                "net_pnl": w_oos_net_pnl,
            },
        })

        all_oos_trades.extend(oos_window_trades)
        train_pfs.append(train_res["summary"]["profit_factor"])
        train_wrs.append(train_res["summary"]["win_rate_pct"])

    # 3. Overall Combined Out-of-Sample Performance
    total_oos_trades = len(all_oos_trades)
    oos_wins = [t for t in all_oos_trades if t["net_pnl"] > 0]
    oos_losses = [t for t in all_oos_trades if t["net_pnl"] < 0]
    oos_win_rate = round(len(oos_wins) / total_oos_trades * 100.0, 1) if total_oos_trades > 0 else 0.0

    oos_net_profit = sum(t["net_pnl"] for t in oos_wins)
    oos_net_loss = abs(sum(t["net_pnl"] for t in oos_losses))
    oos_net_pf = (
        round(oos_net_profit / oos_net_loss, 2)
        if oos_net_loss > 0
        else (round(oos_net_profit, 2) if oos_net_profit > 0 else 1.0)
    )

    oos_gross_profit = sum(t["gross_pnl"] for t in all_oos_trades if t["gross_pnl"] > 0)
    oos_gross_loss = abs(sum(t["gross_pnl"] for t in all_oos_trades if t["gross_pnl"] < 0))
    oos_gross_pf = (
        round(oos_gross_profit / oos_gross_loss, 2)
        if oos_gross_loss > 0
        else (round(oos_gross_profit, 2) if oos_gross_profit > 0 else 1.0)
    )

    oos_net_pnl = round(sum(t["net_pnl"] for t in all_oos_trades), 2)
    oos_gross_pnl = round(sum(t["gross_pnl"] for t in all_oos_trades), 2)
    oos_statutory_fees = round(sum(t.get("statutory_fees", t.get("fees", 0.0)) for t in all_oos_trades), 2)
    oos_slippage = round(sum(t.get("slippage", 0.0) for t in all_oos_trades), 2)

    # 4. Regime breakdown across out-of-sample trades with sample sizes (Priority 5)
    oos_regimes = {}
    for r in ("BULLISH", "BEARISH", "SIDEWAYS", "HIGH_VOLATILITY", "LOW_VOLATILITY"):
        r_trades = [t for t in all_oos_trades if t.get("regime") == r]
        r_wins = [t for t in r_trades if t["net_pnl"] > 0]
        oos_regimes[r] = {
            "sample_size": len(r_trades),
            "trades_count": len(r_trades),
            "win_rate_pct": round((len(r_wins) / len(r_trades) * 100.0), 1) if r_trades else 0.0,
            "net_pnl": round(sum(t["net_pnl"] for t in r_trades), 2),
        }

    # 5. Out-of-Sample Statistical Rigor & Robustness Classification (Phase 9.3)
    sample_size_assessment = evaluate_sample_size_validity(total_oos_trades)
    oos_win_rate_ci = calculate_wilson_score_interval(len(oos_wins), total_oos_trades, confidence=0.95)
    boot_stats = calculate_bootstrap_statistics(all_oos_trades, n_resamples=5000)

    avg_train_pf = round(float(np.mean(train_pfs)), 2) if train_pfs else 1.0
    avg_train_wr = round(float(np.mean(train_wrs)), 1) if train_wrs else 0.0
    pf_degradation = round(((avg_train_pf - oos_net_pf) / max(avg_train_pf, 0.01)) * 100.0, 1)

    windows_positive = sum(1 for w in window_summaries if w["test_period_oos"]["net_pnl"] > 0)
    window_consistency_pct = round((windows_positive / max(len(window_summaries), 1)) * 100.0, 1)

    pf_lower_ci = boot_stats["profit_factor_95_ci"][0] if boot_stats["status"] == "COMPUTED" else 0.0
    exp_lower_ci = boot_stats["expectancy_95_ci_inr"][0] if boot_stats["status"] == "COMPUTED" else 0.0
    prob_prof = boot_stats["prob_profitable_system_pct"] if boot_stats["status"] == "COMPUTED" else 0.0

    # Institutional Robustness Criteria:
    # Requires:
    # 1. Total OOS trades >= 30 (minimum sample size threshold)
    # 2. Net Profit Factor >= 1.15 point estimate
    # 3. 95% Bootstrap CI lower bound for Net PF > 1.00 (statistically significant positive edge)
    # 4. 95% Bootstrap CI lower bound for Net Expectancy > 0.0 INR
    # 5. Bootstrap confidence of positive profit factor >= 90.0%
    # 6. Controlled profit factor degradation <= 30.0% from in-sample
    # 7. Positive net P&L in >= 60.0% of rolling test windows
    is_robust = (
        total_oos_trades >= 30
        and oos_net_pf >= 1.15
        and pf_lower_ci > 1.00
        and exp_lower_ci > 0.0
        and prob_prof >= 90.0
        and pf_degradation <= 30.0
        and window_consistency_pct >= 60.0
    )

    if total_oos_trades < 15:
        verdict = f"CRITICALLY INSUFFICIENT SAMPLE SIZE ({total_oos_trades} trades). Out-of-sample statistical significance cannot be evaluated."
    elif total_oos_trades < 30:
        verdict = f"INSUFFICIENT SAMPLE SIZE ({total_oos_trades} trades < 30 required). Statistical significance cannot be claimed regardless of Net Profit Factor."
    elif not is_robust:
        reasons = []
        if oos_net_pf < 1.0:
            reasons.append("Unprofitable system (Net PF < 1.0)")
        elif pf_lower_ci <= 1.0:
            reasons.append(f"95% Bootstrap CI lower bound ({pf_lower_ci:.2f}) does not strictly exceed 1.00")
        if exp_lower_ci <= 0.0:
            reasons.append(f"95% Bootstrap CI expectancy lower bound (₹{exp_lower_ci:.2f}) includes non-positive payoff")
        if pf_degradation > 30.0:
            reasons.append(f"Excessive out-of-sample degradation ({pf_degradation:.1f}% > 30% limit)")
        if prob_prof < 90.0:
            reasons.append(f"Bootstrap probability of profitability is only {prob_prof:.1f}% (< 90% required)")
        if window_consistency_pct < 60.0:
            reasons.append(f"Poor window consistency ({window_consistency_pct}% < 60% positive windows)")
        verdict = "STATISTICALLY INCONCLUSIVE / RISK OF OVERFITTING: " + "; ".join(reasons)
    else:
        verdict = "STATISTICALLY ROBUST OUT-OF-SAMPLE STABILITY (95% CI PROVEN POSITIVE EDGE ACROSS WINDOWS)"

    return {
        "symbol": sym,
        "strategy": strategy_type,
        "window_type": window_type,
        "total_windows": len(window_summaries),
        "windows": window_summaries,
        "combined_out_of_sample": {
            "total_trades": total_oos_trades,
            "sample_size": total_oos_trades,
            "win_count": len(oos_wins),
            "loss_count": len(oos_losses),
            "win_rate_pct": oos_win_rate,
            "win_rate_95_ci_pct": list(oos_win_rate_ci),
            "gross_profit_factor": oos_gross_pf,
            "net_profit_factor": oos_net_pf,
            "gross_pnl": oos_gross_pnl,
            "net_pnl": oos_net_pnl,
            "statutory_fees": oos_statutory_fees,
            "slippage": oos_slippage,
            "regime_breakdown": oos_regimes,
            "sample_size_assessment": sample_size_assessment,
            "bootstrap_analysis": boot_stats,
        },
        "regime_breakdown": oos_regimes,
        "overfitting_audit": {
            "in_sample_profit_factor": avg_train_pf,
            "out_of_sample_profit_factor": oos_net_pf,
            "profit_factor_degradation_pct": pf_degradation,
            "in_sample_win_rate": avg_train_wr,
            "out_of_sample_win_rate": oos_win_rate,
            "sample_size": total_oos_trades,
            "sample_size_tier": sample_size_assessment["tier"],
            "sample_size_warning": sample_size_assessment["warning"],
            "window_consistency_pct": window_consistency_pct,
            "is_statistically_robust": is_robust,
            "verdict": verdict,
            "bootstrap_stats": boot_stats,
        },
        # Backwards compatibility keys
        "train_period": window_summaries[0]["train_period"] if window_summaries else {},
        "test_period_oos": window_summaries[-1]["test_period_oos"] if window_summaries else {},
    }


# ---------------------------------------------------------------------------
# Parameter Sensitivity Grid (Milestone 8)
# ---------------------------------------------------------------------------

def run_parameter_sensitivity(
    symbol: str,
    strategy_type: str = "ORDER_BLOCK_RETEST",
    bars: Optional[list[dict]] = None,
) -> dict:
    """
    Run multi-dimensional parameter perturbation grid to verify stability.
    Includes multiple testing / selection bias warning (Family-Wise Error Rate).
    """
    sym = symbol.upper()
    if bars is None:
        bars = get_bars(sym)

    if not bars or len(bars) < 12:
        return {"symbol": sym, "error": "Insufficient bars for parameter sensitivity"}

    target_rrs = [1.5, 2.0, 2.5, 3.0]
    holding_periods = [10, 15, 20]

    grid_results = []
    win_rates = []
    profit_factors = []

    for rr in target_rrs:
        for hp in holding_periods:
            res = run_smc_backtest(
                sym, strategy_type=strategy_type, bars=bars, target_rr=rr, max_holding_bars=hp
            )
            s = res["summary"]
            win_rates.append(s["win_rate_pct"])
            profit_factors.append(s["profit_factor"])
            grid_results.append({
                "target_rr": rr,
                "max_holding_bars": hp,
                "trades": s["total_trades"],
                "win_rate_pct": s["win_rate_pct"],
                "profit_factor": s["profit_factor"],
                "net_return_pct": s["net_return_pct"],
            })

    wr_series = pd.Series(win_rates)
    pf_series = pd.Series(profit_factors)
    m_evals = len(grid_results)
    fwer_risk_pct = round((1.0 - (0.95 ** max(m_evals, 1))) * 100.0, 1)

    multiple_testing_warning = (
        f"MULTIPLE TESTING SELECTION BIAS WARNING: Evaluating {m_evals} parameter combinations yields a cumulative "
        f"false discovery risk of ~{fwer_risk_pct}% under standard alpha=0.05. Apparent parameter optima must be "
        "validated against independent out-of-sample walk-forward windows or penalized via Bonferroni / "
        "White's Reality Check adjustments before deployment."
    )

    return {
        "symbol": sym,
        "strategy": strategy_type,
        "grid_evaluations": m_evals,
        "metrics_distribution": {
            "win_rate_mean": round(float(wr_series.mean()), 1),
            "win_rate_std": round(float(wr_series.std()), 1),
            "win_rate_min": round(float(wr_series.min()), 1),
            "win_rate_max": round(float(wr_series.max()), 1),
            "profit_factor_mean": round(float(pf_series.mean()), 2),
            "profit_factor_std": round(float(pf_series.std()), 2),
        },
        "robustness_verdict": (
            "HIGH PARAMETER STABILITY (NO CLIFF-EDGE OVERFITTING)"
            if float(wr_series.std()) <= 12.0
            else "MODERATE SENSITIVITY TO HOLDING PERIOD OR R:R"
        ),
        "false_discovery_risk_pct": fwer_risk_pct,
        "multiple_testing_warning": multiple_testing_warning,
        "detailed_grid": grid_results,
    }

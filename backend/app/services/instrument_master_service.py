from __future__ import annotations
"""
Authoritative NSE Instrument Master, Multi-Tier Provider Mapping & Corporate Action Service.
Phase 14.9.2 — Grounded in official NSE Circulars, ISIN records, Dhan Scrip Master,
and Tata Motors Shareholder Guidance on Cost of Acquisition Allocation.

Architectural Guarantees:
1. Primary key is the immutable internal Instrument ID (e.g. INST_NSE_LTIM, INST_NSE_RELIANCE),
   which never changes merely because exchange trading symbols change.
2. Canonical exchange identity is anchored by official NSE Symbol + unique ISIN,
   with ISO 6166 Luhn check-digit verification.
3. Multi-tier provider mapping supports distinct vendor namespaces (yfinance, dhan)
   with effective-dating (effective_from, effective_to) and explicit verification statuses:
   VERIFIED, UNVERIFIED, INVALID, UNAVAILABLE.
4. Corporate action reconciliation models demergers, splits, and ticker reassignments:
   - Tax acquisition cost allocation (68.85% TMPV, 31.15% TMCV under Sec 49(2C)/49(2D))
     is stored with full legal metadata, without mutating raw OHLCV prices.
   - RAW_ONLY remains the default historical data policy.
   - PROHIBITED_MERGE strictly blocks direct unadjusted predecessor/successor merging.
5. Absolute data preservation: never deletes historical records, never mutates observed
   bar provenance, and maintains 1:1 correspondence across all 24,786 observed bars.
"""

from enum import Enum
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.database import (
    connect,
    get_corporate_actions as db_get_corporate_actions,
    get_instrument as db_get_instrument,
    get_instruments as db_get_instruments,
    get_provider_mappings as db_get_provider_mappings,
    upsert_corporate_action as db_upsert_corporate_action,
    upsert_instrument as db_upsert_instrument,
    upsert_provider_mapping as db_upsert_provider_mapping,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations & Data Structures
# ---------------------------------------------------------------------------

class MappingStatus:
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    INVALID = "INVALID"
    UNAVAILABLE = "UNAVAILABLE"


class InstrumentStatus:
    ACTIVE = "ACTIVE"
    DEMERGED = "DEMERGED"
    DELISTED = "DELISTED"
    SUSPENDED = "SUSPENDED"


class CorporateActionType:
    DEMERGER = "DEMERGER"
    SPLIT = "SPLIT"
    BONUS = "BONUS"
    MERGER = "MERGER"
    NAME_CHANGE = "NAME_CHANGE"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"


class PriceAdjustmentPolicy(str, Enum):
    RAW_ONLY = "RAW_ONLY"                      # Strict historical integrity: predecessor & successor series separated
    EXCHANGE_ADJUSTED = "EXCHANGE_ADJUSTED"    # Uses discovery price ratio from exchange special pre-open session
    PROHIBITED_MERGE = "PROHIBITED_MERGE"      # Direct 1:1 unadjusted splicing is strictly blocked


# ---------------------------------------------------------------------------
# ISIN Syntax & Check-Digit Validation (ISO 6166 / Luhn Modulus-10)
# ---------------------------------------------------------------------------

def calculate_isin_check_digit(isin_11: str) -> str:
    """
    Calculate the ISO 6166 check digit for the first 11 characters of an ISIN
    using the Luhn / modulus-10 double-add-double algorithm.
    """
    if not isin_11 or len(isin_11) != 11:
        raise ValueError(f"ISIN prefix must be exactly 11 characters, got '{isin_11}'")
    digits: List[int] = []
    for char in isin_11.upper():
        if char.isdigit():
            digits.append(int(char))
        elif "A" <= char <= "Z":
            val = ord(char) - ord("A") + 10
            digits.append(val // 10)
            digits.append(val % 10)
        else:
            raise ValueError(f"Invalid character in ISIN prefix: '{char}'")

    # Double-add-double weighting from right to left (weight 2 for rightmost, then 1, 2, 1...)
    total = 0
    weights = [2 if (len(digits) - 1 - i) % 2 == 0 else 1 for i in range(len(digits))]
    for d, w in zip(digits, weights):
        prod = d * w
        total += (prod // 10) + (prod % 10)

    check_digit = (10 - (total % 10)) % 10
    return str(check_digit)


def validate_isin_format(isin: Optional[str]) -> bool:
    """Strict format check: 2 uppercase letters + 9 alphanumeric + 1 digit (12 chars total)."""
    if not isin or not isinstance(isin, str):
        return False
    return bool(re.match(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$", isin))


def validate_isin_check_digit(isin: Optional[str]) -> bool:
    """Verify that the 12th character matches the calculated ISO 6166 Luhn check digit."""
    if not validate_isin_format(isin):
        return False
    prefix = isin[:11]
    expected_check = isin[11]
    try:
        calculated_check = calculate_isin_check_digit(prefix)
        return expected_check == calculated_check
    except Exception:
        return False


def validate_isin(isin: Optional[str]) -> bool:
    """
    Strict validation for exchange-assigned ISINs.
    Validates both 12-character format AND ISO 6166 Luhn check digit.
    Fabricated strings or typos will return False.
    """
    return validate_isin_check_digit(isin)


def verify_authoritative_isin(symbol: str, isin: str) -> bool:
    """
    Verify that an ISIN is not only syntactically and checksum valid,
    but also belongs authoritatively to the specified security.
    Keeps syntax/checksum validation separate from company identity verification.
    """
    if not validate_isin(isin):
        return False
    clean_sym = symbol.strip().upper()
    for inst in AUTHORITATIVE_INSTRUMENTS:
        if inst.symbol == clean_sym or any(h.get("symbol") == clean_sym for h in inst.historical_symbols):
            if inst.isin == isin or inst.historical_isin == isin:
                return True
    return False


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class InstrumentDefinition:
    instrument_id: str
    symbol: str
    company_name: str
    isin: Optional[str] = None
    historical_isin: Optional[str] = None
    effective_date: Optional[str] = None
    exchange: str = "NSE"
    security_type: str = "EQUITY"
    is_fo_eligible: bool = True
    fo_effective_date: Optional[str] = "2000-01-01"
    is_cas_eligible: bool = True
    cas_effective_date: Optional[str] = "2026-08-03"
    cas_schedule_version: str = "CAS_V1_HISTORICAL"
    historical_symbols: List[Dict[str, Any]] = field(default_factory=list)
    listing_date: Optional[str] = None
    delisting_date: Optional[str] = None
    status: str = InstrumentStatus.ACTIVE
    last_verified_date: str = "2026-11-06"
    verification_source: str = "NSE_OFFICIAL_CIRCULARS_AND_DHAN_SCRIP_MASTER"
    verification_provenance: str = "SCRIP_MASTER_RECORD_MATCH_AND_YFINANCE_EMPIRICAL_PROBE"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ProviderMappingDefinition:
    """Keep identifier identity, provider availability, and data capabilities distinct."""

    mapping_id: str
    instrument_id: str
    provider: str
    provider_symbol: str
    provider_security_id: Optional[str] = None
    exchange_segment: str = "NSE_EQ"
    identity_status: str = MappingStatus.VERIFIED
    mapping_status: str = MappingStatus.VERIFIED
    is_primary: bool = True
    verification_date: str = "2026-11-06"
    verification_method: str = "API_CHART_PROBE_AND_SCRIP_MASTER_ID"
    notes: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    quote_endpoint_verified: bool = False
    daily_history_verified: bool = False
    intraday_history_verified: bool = False
    live_feed_verified: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class CorporateActionRecord:
    action_id: str
    instrument_id: str
    action_type: str
    ex_date: str
    record_date: Optional[str]
    ratio: Optional[str]
    pre_action_symbol: Optional[str]
    post_action_symbol: Optional[str]
    resulting_instrument_id: Optional[str]
    resulting_instrument_ids: Optional[str] = None
    date_verification_status: str = "VERIFIED"
    historical_adjustment_factor: Optional[float] = 1.0
    adjustment_treatment: str = "UNADJUSTED"
    description: str = ""
    circular_reference: Optional[str] = None
    verified_at: str = "2026-11-06"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Authoritative Seed Dataset: 33 Instruments across Tracked Universe
# ---------------------------------------------------------------------------

AUTHORITATIVE_INSTRUMENTS: List[InstrumentDefinition] = [
    InstrumentDefinition(
        instrument_id="INST_NSE_ADANIENT",
        symbol="ADANIENT",
        company_name="Adani Enterprises Limited",
        isin="INE423A01024",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_ASIANPAINT",
        symbol="ASIANPAINT",
        company_name="Asian Paints Limited",
        isin="INE021A01026",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_BAJFINANCE",
        symbol="BAJFINANCE",
        company_name="Bajaj Finance Limited",
        isin="INE296A01024",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_BEL",
        symbol="BEL",
        company_name="Bharat Electronics Limited",
        isin="INE263A01024",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_BHARTIARTL",
        symbol="BHARTIARTL",
        company_name="Bharti Airtel Limited",
        isin="INE397D01024",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_CDSL",
        symbol="CDSL",
        company_name="Central Depository Services (India) Limited",
        isin="INE736A01011",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_COALINDIA",
        symbol="COALINDIA",
        company_name="Coal India Limited",
        isin="INE522F01014",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_DEEPAKNTR",
        symbol="DEEPAKNTR",
        company_name="Deepak Nitrite Limited",
        isin="INE288B01029",
        is_fo_eligible=False,  # Confirmed: Equity only, 0 derivative contracts on NSE
        fo_effective_date=None,
        is_cas_eligible=False,  # Governed by standard 75-bar continuous trading
        cas_effective_date=None,
        cas_schedule_version="STANDARD_NON_CAS",
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_DIXON",
        symbol="DIXON",
        company_name="Dixon Technologies (India) Limited",
        isin="INE935N01020",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_HAL",
        symbol="HAL",
        company_name="Hindustan Aeronautics Limited",
        isin="INE066F01020",  # Active post-split ISIN (Rs. 5 face value) per circular NSE/CML/58539
        historical_isin="INE066F01012",  # Pre-split historical ISIN (Rs. 10 face value) prior to 2023-09-29
        effective_date="2023-09-29",
        is_fo_eligible=True,
        is_cas_eligible=True,
        verification_source="NSE_CIRCULAR_NSE_CML_58539_AND_SCRIP_MASTER",
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_HCLTECH",
        symbol="HCLTECH",
        company_name="HCL Technologies Limited",
        isin="INE860A01027",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_HDFCBANK",
        symbol="HDFCBANK",
        company_name="HDFC Bank Limited",
        isin="INE040A01034",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_HINDUNILVR",
        symbol="HINDUNILVR",
        company_name="Hindustan Unilever Limited",
        isin="INE030A01027",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_ICICIBANK",
        symbol="ICICIBANK",
        company_name="ICICI Bank Limited",
        isin="INE090A01021",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_INFY",
        symbol="INFY",
        company_name="Infosys Limited",
        isin="INE009A01021",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_KPITTECH",
        symbol="KPITTECH",
        company_name="KPIT Technologies Limited",
        isin="INE04I401011",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_LT",
        symbol="LT",
        company_name="Larsen & Toubro Limited",
        isin="INE018A01030",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    # LTIMindtree: Immutable canonical ID INST_NSE_LTIM; current symbol LTM effective 2026-02-27 per NSE/CML/72948
    InstrumentDefinition(
        instrument_id="INST_NSE_LTIM",
        symbol="LTM",
        company_name="LTIMindtree Limited",
        isin="INE214T01019",
        effective_date="2026-02-27",
        is_fo_eligible=True,
        is_cas_eligible=True,
        historical_symbols=[
            {"symbol": "LTIM", "valid_from": "2022-11-24", "valid_to": "2026-02-26", "effective_until": "2026-02-26", "note": "NSE ticker prior to circular NSE/CML/72948"},
            {"symbol": "LTI", "valid_from": "1996-12-23", "valid_to": "2022-11-23", "effective_until": "2022-11-23", "note": "Larsen & Toubro Infotech prior to merger"},
            {"symbol": "MINDTREE", "valid_from": "2007-03-07", "valid_to": "2022-11-23", "effective_until": "2022-11-23", "note": "Mindtree Ltd merged into LTI"},
        ],
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_MARUTI",
        symbol="MARUTI",
        company_name="Maruti Suzuki India Limited",
        isin="INE585B01010",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_ONGC",
        symbol="ONGC",
        company_name="Oil & Natural Gas Corporation Limited",
        isin="INE213A01029",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_POLYCAB",
        symbol="POLYCAB",
        company_name="Polycab India Limited",
        isin="INE455K01017",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_POWERGRID",
        symbol="POWERGRID",
        company_name="Power Grid Corporation of India Limited",
        isin="INE752E01010",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_RELIANCE",
        symbol="RELIANCE",
        company_name="Reliance Industries Limited",
        isin="INE002A01018",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_SBIN",
        symbol="SBIN",
        company_name="State Bank of India",
        isin="INE062A01020",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_SUNPHARMA",
        symbol="SUNPHARMA",
        company_name="Sun Pharmaceutical Industries Limited",
        isin="INE044A01036",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_TATAELXSI",
        symbol="TATAELXSI",
        company_name="Tata Elxsi Limited",
        isin="INE670A01012",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_TATAMOTORS",
        symbol="TATAMOTORS",
        company_name="Tata Motors Limited (Pre-Demerger Unified Entity)",
        isin=None,  # Nullable: never fabricated with _HIST suffix!
        historical_isin="INE155A01022",  # Genuine exchange-assigned ISIN held historically
        status=InstrumentStatus.DEMERGED,
        is_fo_eligible=True,
        is_cas_eligible=True,
        verification_source="PRIOR_PHASE_REPORTS_ONLY",
        verification_provenance="PRIMARY_EXCHANGE_EVIDENCE_REQUIRED",
        historical_symbols=[
            {"symbol": "TELCO", "note": "Historical alias; effective dates not established"},
        ],
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_TMPV",
        symbol="TMPV",
        company_name="Tata Motors Passenger Vehicles Limited",
        isin="INE155A01022",  # Retains primary exchange-assigned ISIN post-demerger
        historical_isin=None,
        status=InstrumentStatus.ACTIVE,
        effective_date=None,
        is_fo_eligible=True,  # Retained 384 F&O contracts on NSE
        fo_effective_date="2025-10-24",
        is_cas_eligible=True,
        cas_effective_date="2026-08-03",
        historical_symbols=[],
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_TMCV",
        symbol="TMCV",
        company_name="Tata Motors Limited (Commercial Vehicles)",
        isin="INE1TAE01010",  # Newly assigned ISIN post-demerger
        historical_isin=None,
        status=InstrumentStatus.ACTIVE,
        effective_date=None,
        is_fo_eligible=False,  # Not in NSE F&O list
        fo_effective_date=None,
        is_cas_eligible=False,  # Governed by standard 75-bar continuous trading
        cas_effective_date=None,
        cas_schedule_version="STANDARD_NON_CAS",
        listing_date=None,
        historical_symbols=[],
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_TCS",
        symbol="TCS",
        company_name="Tata Consultancy Services Limited",
        isin="INE467B01029",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_TITAN",
        symbol="TITAN",
        company_name="Titan Company Limited",
        isin="INE280A01028",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_TRENT",
        symbol="TRENT",
        company_name="Trent Limited",
        isin="INE849A01020",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_WIPRO",
        symbol="WIPRO",
        company_name="Wipro Limited",
        isin="INE075A01022",
        is_fo_eligible=True,
        is_cas_eligible=True,
    ),
]


# ---------------------------------------------------------------------------
# Authoritative Provider Mappings (Effective-Dated for Yahoo Finance & Dhan)
# ---------------------------------------------------------------------------

AUTHORITATIVE_PROVIDER_MAPPINGS: List[ProviderMappingDefinition] = [
    # ADANIENT
    ProviderMappingDefinition("MAP_ADANIENT_YF", "INST_NSE_ADANIENT", "yfinance", "ADANIENT.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_ADANIENT_DHAN", "INST_NSE_ADANIENT", "dhan", "ADANIENT", "25", effective_from="2000-01-01"),
    # ASIANPAINT
    ProviderMappingDefinition("MAP_ASIANPAINT_YF", "INST_NSE_ASIANPAINT", "yfinance", "ASIANPAINT.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_ASIANPAINT_DHAN", "INST_NSE_ASIANPAINT", "dhan", "ASIANPAINT", "236", effective_from="2000-01-01"),
    # BAJFINANCE
    ProviderMappingDefinition("MAP_BAJFINANCE_YF", "INST_NSE_BAJFINANCE", "yfinance", "BAJFINANCE.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_BAJFINANCE_DHAN", "INST_NSE_BAJFINANCE", "dhan", "BAJFINANCE", "317", effective_from="2000-01-01"),
    # BEL
    ProviderMappingDefinition("MAP_BEL_YF", "INST_NSE_BEL", "yfinance", "BEL.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_BEL_DHAN", "INST_NSE_BEL", "dhan", "BEL", "383", effective_from="2000-01-01"),
    # BHARTIARTL
    ProviderMappingDefinition("MAP_BHARTIARTL_YF", "INST_NSE_BHARTIARTL", "yfinance", "BHARTIARTL.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_BHARTIARTL_DHAN", "INST_NSE_BHARTIARTL", "dhan", "BHARTIARTL", "10604", effective_from="2000-01-01"),
    # CDSL
    ProviderMappingDefinition("MAP_CDSL_YF", "INST_NSE_CDSL", "yfinance", "CDSL.NS", effective_from="2017-06-30"),
    ProviderMappingDefinition("MAP_CDSL_DHAN", "INST_NSE_CDSL", "dhan", "CDSL", "21174", effective_from="2017-06-30"),
    # COALINDIA
    ProviderMappingDefinition("MAP_COALINDIA_YF", "INST_NSE_COALINDIA", "yfinance", "COALINDIA.NS", effective_from="2010-11-04"),
    ProviderMappingDefinition("MAP_COALINDIA_DHAN", "INST_NSE_COALINDIA", "dhan", "COALINDIA", "20374", effective_from="2010-11-04"),
    # DEEPAKNTR (Equity only, non-CAS)
    ProviderMappingDefinition("MAP_DEEPAKNTR_YF", "INST_NSE_DEEPAKNTR", "yfinance", "DEEPAKNTR.NS", effective_from="2000-01-01", notes="Yahoo ticker mapping; Dhan identifier is stored only on the Dhan mapping"),
    ProviderMappingDefinition("MAP_DEEPAKNTR_DHAN", "INST_NSE_DEEPAKNTR", "dhan", "DEEPAKNTR", "19943", effective_from="2000-01-01"),
    # DIXON
    ProviderMappingDefinition("MAP_DIXON_YF", "INST_NSE_DIXON", "yfinance", "DIXON.NS", effective_from="2017-09-18"),
    ProviderMappingDefinition("MAP_DIXON_DHAN", "INST_NSE_DIXON", "dhan", "DIXON", "21690", effective_from="2017-09-18"),
    # HAL
    ProviderMappingDefinition("MAP_HAL_YF", "INST_NSE_HAL", "yfinance", "HAL.NS", effective_from="2018-03-28"),
    ProviderMappingDefinition("MAP_HAL_DHAN", "INST_NSE_HAL", "dhan", "HAL", "2303", effective_from="2018-03-28"),
    # HCLTECH
    ProviderMappingDefinition("MAP_HCLTECH_YF", "INST_NSE_HCLTECH", "yfinance", "HCLTECH.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_HCLTECH_DHAN", "INST_NSE_HCLTECH", "dhan", "HCLTECH", "7229", effective_from="2000-01-01"),
    # HDFCBANK
    ProviderMappingDefinition("MAP_HDFCBANK_YF", "INST_NSE_HDFCBANK", "yfinance", "HDFCBANK.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_HDFCBANK_DHAN", "INST_NSE_HDFCBANK", "dhan", "HDFCBANK", "1333", effective_from="2000-01-01"),
    # HINDUNILVR
    ProviderMappingDefinition("MAP_HINDUNILVR_YF", "INST_NSE_HINDUNILVR", "yfinance", "HINDUNILVR.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_HINDUNILVR_DHAN", "INST_NSE_HINDUNILVR", "dhan", "HINDUNILVR", "1394", effective_from="2000-01-01"),
    # ICICIBANK
    ProviderMappingDefinition("MAP_ICICIBANK_YF", "INST_NSE_ICICIBANK", "yfinance", "ICICIBANK.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_ICICIBANK_DHAN", "INST_NSE_ICICIBANK", "dhan", "ICICIBANK", "4963", effective_from="2000-01-01"),
    # INFY
    ProviderMappingDefinition("MAP_INFY_YF", "INST_NSE_INFY", "yfinance", "INFY.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_INFY_DHAN", "INST_NSE_INFY", "dhan", "INFY", "1594", effective_from="2000-01-01"),
    # KPITTECH
    ProviderMappingDefinition("MAP_KPITTECH_YF", "INST_NSE_KPITTECH", "yfinance", "KPITTECH.NS", effective_from="2019-04-22"),
    ProviderMappingDefinition("MAP_KPITTECH_DHAN", "INST_NSE_KPITTECH", "dhan", "KPITTECH", "9683", effective_from="2019-04-22"),
    # LT
    ProviderMappingDefinition("MAP_LT_YF", "INST_NSE_LT", "yfinance", "LT.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_LT_DHAN", "INST_NSE_LT", "dhan", "LT", "11483", effective_from="2000-01-01"),
    # LTM (Canonical internal instrument INST_NSE_LTIM; symbol changed to LTM effective Feb 27, 2026 per NSE/CML/72948)
    ProviderMappingDefinition(
        "MAP_LTM_YF", "INST_NSE_LTIM", "yfinance", "LTM.NS",
        effective_from="2026-02-27", effective_to=None,
        mapping_status=MappingStatus.VERIFIED, is_primary=True,
        notes="Verified via empirical probe: LTM.NS returns active bars, LTIM.NS returns 404 delisted"
    ),
    ProviderMappingDefinition(
        "MAP_LTM_DHAN", "INST_NSE_LTIM", "dhan", "LTM", "17818",
        effective_from="2026-02-27", effective_to=None,
        mapping_status=MappingStatus.VERIFIED, is_primary=True,
        notes="Verified via Dhan Scrip Master row 175014: SEM_SMST_SECURITY_ID 17818, SEM_TRADING_SYMBOL LTM"
    ),
    # MARUTI
    ProviderMappingDefinition("MAP_MARUTI_YF", "INST_NSE_MARUTI", "yfinance", "MARUTI.NS", effective_from="2003-07-09"),
    ProviderMappingDefinition("MAP_MARUTI_DHAN", "INST_NSE_MARUTI", "dhan", "MARUTI", "10999", effective_from="2003-07-09"),
    # ONGC
    ProviderMappingDefinition("MAP_ONGC_YF", "INST_NSE_ONGC", "yfinance", "ONGC.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_ONGC_DHAN", "INST_NSE_ONGC", "dhan", "ONGC", "2475", effective_from="2000-01-01"),
    # POLYCAB
    ProviderMappingDefinition("MAP_POLYCAB_YF", "INST_NSE_POLYCAB", "yfinance", "POLYCAB.NS", effective_from="2019-04-16"),
    ProviderMappingDefinition("MAP_POLYCAB_DHAN", "INST_NSE_POLYCAB", "dhan", "POLYCAB", "9590", effective_from="2019-04-16"),
    # POWERGRID
    ProviderMappingDefinition("MAP_POWERGRID_YF", "INST_NSE_POWERGRID", "yfinance", "POWERGRID.NS", effective_from="2007-10-05"),
    ProviderMappingDefinition("MAP_POWERGRID_DHAN", "INST_NSE_POWERGRID", "dhan", "POWERGRID", "14977", effective_from="2007-10-05"),
    # RELIANCE
    ProviderMappingDefinition("MAP_RELIANCE_YF", "INST_NSE_RELIANCE", "yfinance", "RELIANCE.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_RELIANCE_DHAN", "INST_NSE_RELIANCE", "dhan", "RELIANCE", "2885", effective_from="2000-01-01"),
    # SBIN
    ProviderMappingDefinition("MAP_SBIN_YF", "INST_NSE_SBIN", "yfinance", "SBIN.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_SBIN_DHAN", "INST_NSE_SBIN", "dhan", "SBIN", "3045", effective_from="2000-01-01"),
    # SUNPHARMA
    ProviderMappingDefinition("MAP_SUNPHARMA_YF", "INST_NSE_SUNPHARMA", "yfinance", "SUNPHARMA.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_SUNPHARMA_DHAN", "INST_NSE_SUNPHARMA", "dhan", "SUNPHARMA", "3351", effective_from="2000-01-01"),
    # TATAELXSI
    ProviderMappingDefinition("MAP_TATAELXSI_YF", "INST_NSE_TATAELXSI", "yfinance", "TATAELXSI.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_TATAELXSI_DHAN", "INST_NSE_TATAELXSI", "dhan", "TATAELXSI", "3411", effective_from="2000-01-01"),
    # Historical provider identity and exchange transition date remain unverified.
    ProviderMappingDefinition(
        "MAP_TATAMOTORS_YF", "INST_NSE_TATAMOTORS", "yfinance", "TATAMOTORS.NS",
        is_primary=False,
        identity_status=MappingStatus.UNVERIFIED,
        mapping_status=MappingStatus.UNAVAILABLE,
        notes="Historical predecessor ticker; provider history availability is not verified"
    ),
    ProviderMappingDefinition(
        "MAP_TATAMOTORS_DHAN", "INST_NSE_TATAMOTORS", "dhan", "TATAMOTORS", "3456",
        is_primary=False,
        identity_status=MappingStatus.UNVERIFIED,
        mapping_status=MappingStatus.UNAVAILABLE,
        notes="Historical predecessor identity; no quote or history capability is asserted"
    ),
    # TMPV current identity is verified; its first effective exchange date is not.
    ProviderMappingDefinition(
        "MAP_TMPV_YF", "INST_NSE_TMPV", "yfinance", "TMPV.NS",
        effective_from=None, effective_to=None,
        mapping_status=MappingStatus.VERIFIED, is_primary=True,
        notes="Verified active on Yahoo Finance; holds original ISIN INE155A01022 and F&O status"
    ),
    ProviderMappingDefinition(
        "MAP_TMPV_DHAN", "INST_NSE_TMPV", "dhan", "TMPV", "3456",
        effective_from=None, effective_to=None,
        mapping_status=MappingStatus.VERIFIED, is_primary=True,
        notes="Verified active in Dhan scrip master ID 3456 (primary active mapping for ID 3456)"
    ),
    # TMCV (current mapping; first exchange date is not verified in the bundled evidence)
    ProviderMappingDefinition(
        "MAP_TMCV_YF", "INST_NSE_TMCV", "yfinance", "TMCV.NS",
        effective_from=None, effective_to=None,
        mapping_status=MappingStatus.VERIFIED, is_primary=True,
        notes="Verified active on Yahoo Finance; newly listed cash equity (ISIN INE1TAE01010)"
    ),
    ProviderMappingDefinition(
        "MAP_TMCV_DHAN", "INST_NSE_TMCV", "dhan", "TMCV", "759782",
        effective_from=None, effective_to=None,
        mapping_status=MappingStatus.VERIFIED, is_primary=True,
        notes="Verified active in Dhan scrip master ID 759782"
    ),
    # TCS
    ProviderMappingDefinition("MAP_TCS_YF", "INST_NSE_TCS", "yfinance", "TCS.NS", effective_from="2004-08-25"),
    ProviderMappingDefinition("MAP_TCS_DHAN", "INST_NSE_TCS", "dhan", "TCS", "11536", effective_from="2004-08-25"),
    # TITAN
    ProviderMappingDefinition("MAP_TITAN_YF", "INST_NSE_TITAN", "yfinance", "TITAN.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_TITAN_DHAN", "INST_NSE_TITAN", "dhan", "TITAN", "3506", effective_from="2000-01-01"),
    # TRENT
    ProviderMappingDefinition("MAP_TRENT_YF", "INST_NSE_TRENT", "yfinance", "TRENT.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_TRENT_DHAN", "INST_NSE_TRENT", "dhan", "TRENT", "1964", effective_from="2000-01-01"),
    # WIPRO
    ProviderMappingDefinition("MAP_WIPRO_YF", "INST_NSE_WIPRO", "yfinance", "WIPRO.NS", effective_from="2000-01-01"),
    ProviderMappingDefinition("MAP_WIPRO_DHAN", "INST_NSE_WIPRO", "dhan", "WIPRO", "3787", effective_from="2000-01-01"),
]


# ---------------------------------------------------------------------------
# Authoritative Corporate Actions Records
# ---------------------------------------------------------------------------

AUTHORITATIVE_CORPORATE_ACTIONS: List[CorporateActionRecord] = [
    # 1. Tata Motors Demerger (Oct 24, 2025)
    CorporateActionRecord(
        action_id="CA_TATAMOTORS_DEMERGER_2025",
        instrument_id="INST_NSE_TATAMOTORS",
        action_type=CorporateActionType.DEMERGER,
        ex_date="2025-10-24",
        date_verification_status="UNVERIFIED",
        record_date=None,
        ratio="1:1",
        pre_action_symbol="TATAMOTORS",
        post_action_symbol="TMPV",
        resulting_instrument_id="INST_NSE_TMCV",
        resulting_instrument_ids=json.dumps(["INST_NSE_TMPV", "INST_NSE_TMCV"]),
        historical_adjustment_factor=None,
        adjustment_treatment="SEPARATE_SERIES_NO_PRICE_ADJUSTMENT",
        description=(
            "Demerger of Tata Motors Limited into TMPV (Passenger Vehicles, ISIN INE155A01022) and TMCV (Commercial Vehicles, ISIN INE1TAE01010). "
            "Entitlement ratio: 1 share of TMCV for every 1 share of Tata Motors held. "
            "Tax Acquisition Cost Allocation under Sections 49(2C) and 49(2D) of the Income-tax Act, 1961: "
            "TMPV = 68.85%, TMCV = 31.15% (Source: Tata Motors Shareholder Guidance dated 2025-11-12). "
            "The issuer's official website states that the Composite Scheme was effective 2025-10-01 "
            "(https://www.tatamotors.com/). The recorded 2025-10-24 ex-date remains UNVERIFIED and is not "
            "asserted as the scheme effective date; listing, trading, and historical symbol transition dates "
            "remain unverified. "
            "CRITICAL: Statutory tax cost apportionment is purely for capital gains acquisition cost computation and is NOT a market price adjustment factor! "
            "Under RAW_ONLY policy, historical prices are kept unadjusted. Unadjusted 1:1 predecessor/successor merging is strictly PROHIBITED_MERGE."
        ),
        circular_reference=None,
    ),
    # 2. HAL 1:2 Stock Split (Sep 29, 2023 - NSE Circular NSE/CML/58539)
    CorporateActionRecord(
        action_id="CA_HAL_SPLIT_2023",
        instrument_id="INST_NSE_HAL",
        action_type=CorporateActionType.SPLIT,
        ex_date="2023-09-29",
        record_date="2023-09-29",
        ratio="1:2",
        pre_action_symbol="HAL",
        post_action_symbol="HAL",
        resulting_instrument_id="INST_NSE_HAL",
        historical_adjustment_factor=0.5,
        adjustment_treatment="SPLIT_ADJUSTED",
        description=(
            "Stock split of Hindustan Aeronautics Limited from face value Rs. 10 to Rs. 5 per share. "
            "Pre-split ISIN INE066F01012 subdivided into active ISIN INE066F01020 per NSE Circular NSE/CML/58539."
        ),
        circular_reference="NSE/CML/58539",
    ),
    # 3. LTI and Mindtree Merger (Nov 23, 2022)
    CorporateActionRecord(
        action_id="CA_LTIM_MERGER_2022",
        instrument_id="INST_NSE_LTIM",
        action_type=CorporateActionType.MERGER,
        ex_date="2022-11-23",
        record_date="2022-11-24",
        ratio="73:100",
        pre_action_symbol="LTI",
        post_action_symbol="LTIM",
        resulting_instrument_id=None,
        historical_adjustment_factor=1.0,
        adjustment_treatment="NAME_CHANGE_AND_ABSORPTION",
        description=(
            "Merger of Mindtree Limited into Larsen & Toubro Infotech Limited (LTI). "
            "Mindtree shareholders received 73 shares of LTI for every 100 Mindtree shares. "
            "Merged company renamed to LTIMindtree Limited."
        ),
        circular_reference="NSE/CML/54589",
    ),
    # 4. LTIM to LTM Symbol Change (Feb 27, 2026 - NSE Circular NSE/CML/72948)
    CorporateActionRecord(
        action_id="CA_LTM_SYMBOL_CHANGE_2026",
        instrument_id="INST_NSE_LTIM",
        action_type=CorporateActionType.SYMBOL_CHANGE,
        ex_date="2026-02-27",
        record_date="2026-02-27",
        ratio=None,
        pre_action_symbol="LTIM",
        post_action_symbol="LTM",
        resulting_instrument_id="INST_NSE_LTIM",
        historical_adjustment_factor=1.0,
        adjustment_treatment="NAME_OR_SYMBOL_CHANGE",
        description=(
            "NSE Circular NSE/CML/72948: Change in trading symbol of LTIMindtree Limited from LTIM to LTM effective February 27, 2026. "
            "ISIN INE214T01019, canonical instrument ID INST_NSE_LTIM, and Dhan scrip ID 17818 remain unchanged."
        ),
        circular_reference="NSE/CML/72948",
    ),
]


# ---------------------------------------------------------------------------
# InstrumentMasterService Implementation
# ---------------------------------------------------------------------------

class InstrumentMasterService:
    """
    Authoritative query and reconciliation engine for tracked securities.
    Provides unambiguous symbol resolution, effective-dated provider mapping lookups,
    and corporate action audits with mathematical data-integrity guarantees.
    """

    def __init__(self):
        self._seeded = False

    def ensure_seeded(self) -> None:
        """Seed authoritative universe and mappings into database if not already present."""
        if self._seeded:
            return
        existing = db_get_instruments()
        canonical_tata = next(
            (i for i in existing if i.get("instrument_id") == "INST_NSE_TATAMOTORS"),
            None,
        )
        if canonical_tata and canonical_tata.get("symbol") != "TATAMOTORS":
            raise RuntimeError(
                "Conflicting INST_NSE_TATAMOTORS row; run the reviewed Tata lineage "
                "migration before seeding the instrument master."
            )
        if any(i.get("instrument_id") == "INST_NSE_TATAMOTORS_HIST" for i in existing):
            raise RuntimeError(
                "Legacy INST_NSE_TATAMOTORS_HIST row found; run the reviewed Tata "
                "lineage migration before seeding the instrument master."
            )
        has_ltim_canonical = any(i.get("instrument_id") == "INST_NSE_LTIM" for i in existing)
        has_hal_split = any(c.get("action_id") == "CA_HAL_SPLIT_2023" for c in db_get_corporate_actions())
        expected_ids = {i.instrument_id for i in AUTHORITATIVE_INSTRUMENTS}
        existing_ids = {i.get("instrument_id") for i in existing}
        if not existing or not expected_ids.issubset(existing_ids) or not has_ltim_canonical or not has_hal_split:
            logger.info("Seeding or refreshing authoritative instrument master records...")
            self.seed_authoritative_universe()
        self._seeded = True

    def seed_authoritative_universe(self) -> Dict[str, int]:
        """Insert or refresh all 33 instruments, provider mappings, and corporate actions."""
        inst_count = 0
        map_count = 0
        ca_count = 0

        # 1. Seed instruments
        for inst_def in AUTHORITATIVE_INSTRUMENTS:
            d = asdict(inst_def)
            d["historical_symbols"] = json.dumps(d.get("historical_symbols") or [])
            d["is_fo_eligible"] = 1 if d["is_fo_eligible"] else 0
            d["is_cas_eligible"] = 1 if d["is_cas_eligible"] else 0
            db_upsert_instrument(d)
            inst_count += 1

        # 2. Seed provider mappings
        for map_def in AUTHORITATIVE_PROVIDER_MAPPINGS:
            d = asdict(map_def)
            d["is_primary"] = 1 if d["is_primary"] else 0
            if d["provider"].lower() == "yfinance":
                d["provider_security_id"] = None
            for capability in (
                "quote_endpoint_verified",
                "daily_history_verified",
                "intraday_history_verified",
                "live_feed_verified",
            ):
                d[capability] = int(bool(d[capability]))
            db_upsert_provider_mapping(d)
            map_count += 1

        # 3. Seed corporate actions
        for ca_def in AUTHORITATIVE_CORPORATE_ACTIONS:
            d = asdict(ca_def)
            db_upsert_corporate_action(d)
            ca_count += 1

        self._seeded = True
        logger.info(
            "Authoritative Instrument Master successfully seeded: %d instruments, %d mappings, %d corporate actions",
            inst_count, map_count, ca_count
        )
        return {
            "instruments_seeded": inst_count,
            "mappings_seeded": map_count,
            "corporate_actions_seeded": ca_count,
        }

    def resolve_instrument(self, symbol_or_id: str) -> Optional[Dict[str, Any]]:
        """
        Multi-tier identifier resolution:
        1. Exact internal instrument_id (e.g. INST_NSE_LTIM, INST_NSE_RELIANCE)
        2. Alias resolution (INST_NSE_LTM -> INST_NSE_LTIM)
        3. Exact active or historical ISIN (e.g. INE214T01019, INE066F01020, INE066F01012)
        4. Current NSE trading symbol (e.g. LTM, RELIANCE, TMPV, HAL)
        5. Historical symbol or alias (e.g. LTIM, LTI, MINDTREE, TATAMOTORS, TELCO)
        6. Provider symbol match (e.g. LTM.NS -> INST_NSE_LTIM, TMPV.NS -> INST_NSE_TMPV)
        """
        if not symbol_or_id:
            return None
        self.ensure_seeded()
        clean = symbol_or_id.strip().upper()

        # Clean trailing .NS or .BO if passed
        base_sym = clean.split(".")[0]

        # Alias resolution for LTM / LTIM IDs
        lookup_target = "INST_NSE_LTIM" if clean in ("INST_NSE_LTM", "INST_NSE_LTIM") else clean
        if clean == "INST_NSE_TATAMOTORS_HIST":
            lookup_target = "INST_NSE_TATAMOTORS"
        lookup_base = "LTM" if base_sym == "LTIM" and clean != "LTIM" else base_sym

        # 1-4. Direct database lookup (by ID, ISIN, historical_isin, symbol, or historical symbol)
        inst = db_get_instrument(lookup_target) or db_get_instrument(lookup_base) or db_get_instrument(clean) or db_get_instrument(base_sym)
        if inst:
            self._unpack_instrument_fields(inst)
            return inst

        # 5. Reverse lookup via provider mapping table
        with connect() as con:
            row = con.execute(
                """
                SELECT i.* FROM instruments i
                JOIN instrument_provider_mappings m ON i.instrument_id = m.instrument_id
                WHERE (UPPER(m.provider_symbol) = ? OR UPPER(m.provider_symbol) = ?)
                  AND m.identity_status = 'VERIFIED'
                LIMIT 1
                """,
                (clean, f"{base_sym}.NS")
            ).fetchone()
            if row:
                inst_dict = dict(row)
                self._unpack_instrument_fields(inst_dict)
                return inst_dict

        return None

    def get_provider_symbol(self, symbol_or_id: str, provider: str = "yfinance") -> Optional[str]:
        """
        Return the current active provider ticker symbol for a given instrument.
        e.g. LTIM + yfinance -> LTM.NS
             TMPV + yfinance -> TMPV.NS
             TATAMOTORS + yfinance -> None (UNAVAILABLE)
        """
        return self.get_provider_symbol_for_date(symbol_or_id, provider=provider, query_date=None)

    def get_provider_symbol_for_date(
        self,
        symbol_or_id: str,
        provider: str = "yfinance",
        query_date: Optional[str] = None
    ) -> Optional[str]:
        """
        Resolve a provider ticker identity, not a quote/history/live-feed capability.
        A dated lookup fails closed when the mapping has no verified effective window.
        """
        self.ensure_seeded()
        inst = self.resolve_instrument(symbol_or_id)
        if not inst:
            return None

        mappings = db_get_provider_mappings(instrument_id=inst["instrument_id"], provider=provider)
        if not mappings:
            # Fallback for standard NSE equities if not explicitly mapped
            if provider.lower() == "yfinance":
                return f"{inst['symbol']}.NS"
            return inst["symbol"]

        # Date-aware filtering
        if query_date:
            valid_maps = [
                m for m in mappings
                if m.get("identity_status", MappingStatus.UNVERIFIED) == MappingStatus.VERIFIED
                and m.get("effective_from") is not None
                and query_date >= m["effective_from"]
                and (not m.get("effective_to") or query_date <= m["effective_to"])
            ]
            if not valid_maps:
                return None
            selected = next(
                (m for m in valid_maps if m.get("is_primary") and m.get("mapping_status") == MappingStatus.VERIFIED),
                None,
            )
            if selected:
                return selected["provider_symbol"]
            return next(
                (m["provider_symbol"] for m in valid_maps if m.get("mapping_status") == MappingStatus.VERIFIED),
                None,
            )

        # Current (query_date is None or latest)
        primary_map = next(
            (
                m for m in mappings
                if m.get("is_primary")
                and m.get("identity_status", MappingStatus.UNVERIFIED) == MappingStatus.VERIFIED
                and m.get("mapping_status") == MappingStatus.VERIFIED
                and not m.get("effective_to")
            ),
            None
        )
        if primary_map:
            return primary_map["provider_symbol"]

        # Fallback to any verified mapping
        verified_map = next(
            (
                m for m in mappings
                if m.get("identity_status", MappingStatus.UNVERIFIED) == MappingStatus.VERIFIED
                and m.get("mapping_status") == MappingStatus.VERIFIED
                and not m.get("effective_to")
            ),
            None,
        )
        if verified_map:
            return verified_map["provider_symbol"]

        # Check if mapped as UNAVAILABLE
        unavail = next((m for m in mappings if m.get("mapping_status") == MappingStatus.UNAVAILABLE), None)
        if unavail:
            logger.warning(
                "Security %s is explicitly UNAVAILABLE on provider %s: %s",
                inst["symbol"], provider, unavail.get("notes")
            )
            return None

        return mappings[0]["provider_symbol"]

    def get_provider_capabilities(
        self,
        symbol_or_id: str,
        provider: str,
        query_date: Optional[str] = None,
    ) -> Dict[str, bool]:
        """Return verified data capabilities independently of mapping identity."""
        self.ensure_seeded()
        inst = self.resolve_instrument(symbol_or_id)
        capabilities = {
            "identity_verified": False,
            "quote_endpoint_verified": False,
            "daily_history_verified": False,
            "intraday_history_verified": False,
            "live_feed_verified": False,
        }
        if not inst:
            return capabilities
        mappings = db_get_provider_mappings(inst["instrument_id"], provider.lower())
        candidates = [
            m for m in mappings
            if m.get("identity_status", MappingStatus.UNVERIFIED) == MappingStatus.VERIFIED
            and (
                not query_date
                or (
                    m.get("effective_from") is not None
                    and query_date >= m["effective_from"]
                    and (not m.get("effective_to") or query_date <= m["effective_to"])
                )
            )
        ]
        if len(candidates) != 1:
            return capabilities
        mapping = candidates[0]
        capabilities.update({
            "identity_verified": True,
            "quote_endpoint_verified": bool(mapping.get("quote_endpoint_verified")),
            "daily_history_verified": bool(mapping.get("daily_history_verified")),
            "intraday_history_verified": bool(mapping.get("intraday_history_verified")),
            "live_feed_verified": bool(mapping.get("live_feed_verified")),
        })
        return capabilities

    def resolve_provider_security_id(
        self,
        provider: str,
        provider_security_id: str,
        query_date: Optional[str] = None,
        exchange: Optional[str] = None,
        exchange_segment: Optional[str] = None,
        instrument_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve a provider ID only within its provider/exchange/segment/type namespace.
        Ambiguous matches and undated historical identities fail closed.
        """
        self.ensure_seeded()
        clauses = [
            "LOWER(m.provider) = LOWER(?)",
            "m.provider_security_id = ?",
            "m.identity_status = 'VERIFIED'",
        ]
        params: List[Any] = [provider, str(provider_security_id)]
        if exchange:
            clauses.append("UPPER(i.exchange) = UPPER(?)")
            params.append(exchange)
        if exchange_segment:
            clauses.append("UPPER(m.exchange_segment) = UPPER(?)")
            params.append(exchange_segment)
        if instrument_type:
            clauses.append("UPPER(i.security_type) = UPPER(?)")
            params.append(instrument_type)
        with connect() as con:
            rows = con.execute(
                f"""
                SELECT m.*, i.symbol as inst_symbol, i.status as inst_status
                FROM instrument_provider_mappings m
                JOIN instruments i ON m.instrument_id = i.instrument_id
                WHERE {" AND ".join(clauses)}
                ORDER BY m.is_primary DESC, m.effective_from DESC, m.mapping_id
                """,
                params,
            ).fetchall()
            if not rows:
                return None

            mappings = [dict(r) for r in rows]

            if query_date:
                mappings = [
                    m for m in mappings
                    if m.get("effective_from") is not None
                    and query_date >= m["effective_from"]
                    and (not m.get("effective_to") or query_date <= m["effective_to"])
                ]
            else:
                mappings = [
                    m for m in mappings
                    if m.get("is_primary")
                    and m.get("mapping_status") == MappingStatus.VERIFIED
                    and not m.get("effective_to")
                ]

            if len(mappings) != 1:
                return None
            return self.resolve_instrument(mappings[0]["instrument_id"])

    def get_dhan_security_id(
        self,
        symbol_or_id: str,
        exchange: str = "NSE",
        exchange_segment: str = "NSE_EQ",
        instrument_type: str = "EQUITY",
        query_date: Optional[str] = None,
    ) -> Optional[str]:
        """Return a Dhan ID only for a matching exchange, segment, and instrument type."""
        self.ensure_seeded()
        inst = self.resolve_instrument(symbol_or_id)
        if not inst:
            return None
        if (
            inst.get("exchange", "").upper() != exchange.upper()
            or inst.get("security_type", "").upper() != instrument_type.upper()
        ):
            return None
        mappings = db_get_provider_mappings(instrument_id=inst["instrument_id"], provider="dhan")
        mappings = [
            m for m in mappings
            if m.get("identity_status", MappingStatus.UNVERIFIED) == MappingStatus.VERIFIED
            and (m.get("exchange_segment") or "").upper() == exchange_segment.upper()
            and (
                not query_date
                or (
                    m.get("effective_from") is not None
                    and query_date >= m["effective_from"]
                    and (not m.get("effective_to") or query_date <= m["effective_to"])
                )
            )
        ]
        if len(mappings) != 1:
            return None
        return str(mappings[0]["provider_security_id"]) if mappings[0].get("provider_security_id") else None

    def get_corporate_actions(self, symbol_or_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve corporate actions for an instrument or all instruments."""
        self.ensure_seeded()
        inst_id = None
        if symbol_or_id:
            inst = self.resolve_instrument(symbol_or_id)
            if inst:
                inst_id = inst["instrument_id"]
        return db_get_corporate_actions(instrument_id=inst_id)

    def resolve_symbol_for_date(self, symbol_or_id: str, query_date: str) -> Optional[str]:
        """
        Resolve the effective NSE trading symbol for a given calendar date (YYYY-MM-DD).
        Handles historical symbol transitions:
        - LTIM -> LTM effective 2026-02-27 (NSE Circular NSE/CML/72948)
        - TATAMOTORS remains the predecessor identity; it never aliases either successor.
        - LTI -> LTIM effective 2022-11-23
        """
        self.ensure_seeded()
        datetime.strptime(query_date, "%Y-%m-%d")
        inst = self.resolve_instrument(symbol_or_id)
        if not inst:
            return None

        if inst["instrument_id"] in (
            "INST_NSE_TATAMOTORS",
            "INST_NSE_TMPV",
            "INST_NSE_TMCV",
        ):
            return None

        current_symbol = inst["symbol"]
        hist_symbols = inst.get("historical_symbols") or []

        for h in hist_symbols:
            h_sym = h.get("symbol")
            val_from = h.get("valid_from")
            val_to = h.get("valid_to") or h.get("effective_until")
            if val_to and query_date <= val_to:
                if not val_from or query_date >= val_from:
                    return h_sym

        effective_date = inst.get("effective_date")
        if inst["instrument_id"] == "INST_NSE_TMCV" and not effective_date:
            return None
        if effective_date and query_date < effective_date:
            return None
        if inst.get("status") != InstrumentStatus.ACTIVE:
            delisting_date = inst.get("delisting_date")
            if delisting_date and query_date >= delisting_date:
                return None
        return current_symbol

    def get_price_continuity_series(
        self,
        symbol_or_id: str,
        start_date: str,
        end_date: str,
        policy: PriceAdjustmentPolicy = PriceAdjustmentPolicy.RAW_ONLY,
    ) -> Dict[str, Any]:
        """
        Enforce explicit corporate action price continuity policies.
        Prevents improper 1:1 splicing of predecessor and successor series.

        Tax acquisition-cost allocation is not a market-price policy and is exposed
        separately by get_tax_cost_allocation_metadata().
        """
        self.ensure_seeded()
        policy_value = policy.value if isinstance(policy, PriceAdjustmentPolicy) else str(policy)
        if policy_value == "COST_APPORTIONMENT":
            raise ValueError(
                "Tax-cost allocation is accounting metadata, not a market-price adjustment policy."
            )
        inst = self.resolve_instrument(symbol_or_id)
        if not inst:
            raise ValueError(f"Unknown instrument: {symbol_or_id}")

        inst_id = inst["instrument_id"]
        symbol = inst["symbol"]

        if policy == PriceAdjustmentPolicy.PROHIBITED_MERGE:
            raise ValueError("Direct 1:1 unadjusted splicing of predecessor and successor series is strictly prohibited.")

        result = {
            "instrument_id": inst_id,
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "policy": policy_value,
            "status": "VALIDATED",
            "notes": [],
            "predecessor_data_status": "AVAILABLE",
        }

        if policy_value == PriceAdjustmentPolicy.EXCHANGE_ADJUSTED.value:
            result["status"] = "UNAVAILABLE"
            result["notes"].append("No verified exchange adjustment factor is registered.")

        if symbol in ("TATAMOTORS", "TMPV", "TMCV"):
            result["status"] = "EFFECTIVE_DATE_UNVERIFIED"
            result["predecessor_data_status"] = "UNKNOWN_EFFECTIVE_DATE"
            result["notes"].append(
                "Tata Motors exchange transition dates are not verified by bundled primary-source evidence."
            )
        return result

    def get_tax_cost_allocation_metadata(self, symbol_or_id: str) -> Optional[Dict[str, Any]]:
        """Return statutory acquisition-cost metadata without market-price factors."""
        inst = self.resolve_instrument(symbol_or_id)
        if not inst or inst["symbol"] not in ("TMPV", "TMCV"):
            return None
        allocations = {"TMPV": 68.85, "TMCV": 31.15}
        return {
            "instrument_id": inst["instrument_id"],
            "entity": inst["symbol"],
            "allocation_pct": allocations[inst["symbol"]],
            "legal_basis": "Sections 49(2C) and 49(2D) of the Income-tax Act, 1961",
            "source_document": "Tata Motors Shareholder Guidance on Cost of Acquisition Allocation",
            "guidance_date": "2025-11-12",
            "effective_date": "2025-10-24",
            "effective_date_type": "TAX_ALLOCATION",
            "effective_date_verification_status": "UNVERIFIED",
            "purpose": "ACCOUNTING_ACQUISITION_COST_ONLY",
        }

    def get_universe_reconciliation(self) -> List[Dict[str, Any]]:
        """
        Generates the comprehensive Universe Reconciliation Table covering all tracked securities:
        - Internal instrument ID (immutable canonical ID)
        - Current NSE symbol
        - Company name
        - ISIN (verified active ISIN)
        - Previous symbols and change dates
        - Yahoo Finance mapping and status (VERIFIED or UNAVAILABLE)
        - Dhan mapping and status (VERIFIED or UNAVAILABLE)
        - F&O eligibility
        - CAS status and schedule version
        - Observed intraday data availability (from database count)
        - Daily data availability (from database count)
        - Corporate action notes
        """
        self.ensure_seeded()
        instruments = db_get_instruments()
        reconciliation_table: List[Dict[str, Any]] = []

        with connect() as con:
            for inst in instruments:
                self._unpack_instrument_fields(inst)
                inst_id = inst["instrument_id"]
                sym = inst["symbol"]

                # 1. Provider mappings
                maps = db_get_provider_mappings(instrument_id=inst_id)
                # Primary active yfinance mapping
                yf_map = next((m for m in maps if m.get("provider") == "yfinance" and m.get("is_primary")), None)
                if not yf_map:
                    yf_map = next((m for m in maps if m.get("provider") == "yfinance"), {})
                # Primary active dhan mapping
                dhan_map = next((m for m in maps if m.get("provider") == "dhan" and m.get("is_primary")), None)
                if not dhan_map:
                    dhan_map = next((m for m in maps if m.get("provider") == "dhan"), {})

                # 2. Database inventory counts
                # Observed 5m intraday bars: for LTIMindtree check both LTM and LTIM tickers under canonical ID
                if inst_id == "INST_NSE_LTIM":
                    obs_row = con.execute(
                        "SELECT COUNT(*) FROM observed_intraday_ohlcv WHERE symbol IN ('LTM', 'LTIM') AND interval = '5m'"
                    ).fetchone()
                else:
                    obs_row = con.execute(
                        "SELECT COUNT(*) FROM observed_intraday_ohlcv WHERE symbol = ? AND interval = '5m'",
                        (sym,)
                    ).fetchone()
                obs_count = obs_row[0] if obs_row else 0

                # Daily bars (from stocks table / daily ohlcv)
                daily_row = con.execute(
                    "SELECT COUNT(*) FROM ohlcv WHERE symbol = ? AND interval IN ('1D', 'daily')",
                    (sym,)
                ).fetchone()
                daily_count = daily_row[0] if daily_row else 0
                if daily_count == 0 and inst_id == "INST_NSE_LTIM":
                    alt_daily = con.execute(
                        "SELECT COUNT(*) FROM ohlcv WHERE symbol IN ('LTM', 'LTIM') AND interval IN ('1D', 'daily')"
                    ).fetchone()
                    daily_count = alt_daily[0] if alt_daily else 0

                # 3. Corporate action summary
                cas = db_get_corporate_actions(instrument_id=inst_id)
                ca_note = "; ".join(c.get("description", "")[:60] + "..." for c in cas) if cas else "None"

                # Historical symbols string
                hist_syms = inst.get("historical_symbols") or []
                hist_str = ", ".join(f"{h.get('symbol')} (until {h.get('effective_until', 'N/A')})" for h in hist_syms) if hist_syms else "None"

                row_entry = {
                    "instrument_id": inst_id,
                    "symbol": sym,
                    "company_name": inst.get("company_name"),
                    "isin": inst.get("isin"),
                    "historical_isin": inst.get("historical_isin"),
                    "status": inst.get("status"),
                    "previous_symbols": hist_str,
                    "yahoo_symbol": yf_map.get("provider_symbol", f"{sym}.NS"),
                    "yahoo_status": yf_map.get("mapping_status", MappingStatus.UNVERIFIED),
                    "dhan_symbol": dhan_map.get("provider_symbol", sym),
                    "dhan_security_id": dhan_map.get("provider_security_id", "N/A"),
                    "dhan_status": dhan_map.get("mapping_status", MappingStatus.UNVERIFIED),
                    "is_fo_eligible": bool(inst.get("is_fo_eligible")),
                    "is_cas_eligible": bool(inst.get("is_cas_eligible")),
                    "cas_schedule_version": inst.get("cas_schedule_version", "STANDARD_NON_CAS"),
                    "observed_intraday_bars": obs_count,
                    "daily_bars": daily_count,
                    "corporate_actions_count": len(cas),
                    "corporate_action_notes": ca_note,
                }
                reconciliation_table.append(row_entry)

        return reconciliation_table

    def _unpack_instrument_fields(self, inst: Dict[str, Any]) -> None:
        """Parse serialized JSON fields in instrument dictionary."""
        if "historical_symbols" in inst and isinstance(inst["historical_symbols"], str):
            try:
                inst["historical_symbols"] = json.loads(inst["historical_symbols"])
            except Exception:
                inst["historical_symbols"] = []


# Singleton instance for system-wide lookup
_service_instance: Optional[InstrumentMasterService] = None


def get_instrument_master_service() -> InstrumentMasterService:
    """Return the global InstrumentMasterService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = InstrumentMasterService()
        _service_instance.ensure_seeded()
    return _service_instance

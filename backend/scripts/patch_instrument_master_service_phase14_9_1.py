"""
Patch script for backend/app/services/instrument_master_service.py in Phase 14.9.1.
"""

def patch():
    path = "backend/app/services/instrument_master_service.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Add Enum import and PriceAdjustmentPolicy, validate_isin
    old_enums = """class MappingStatus:
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


@dataclass
class InstrumentDefinition:
    instrument_id: str
    symbol: str
    company_name: str
    isin: str"""

    new_enums = """class MappingStatus:
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
    COST_APPORTIONMENT = "COST_APPORTIONMENT"  # Apportions historical prices by official cost allocation ratio (40.7% TMPV, 59.3% TMCV)
    EXCHANGE_ADJUSTED = "EXCHANGE_ADJUSTED"    # Uses discovery price ratio from exchange special pre-open session
    PROHIBITED_MERGE = "PROHIBITED_MERGE"      # Direct 1:1 unadjusted splicing is strictly blocked


def validate_isin(isin: Optional[str]) -> bool:
    \"\"\"
    Strict format validation for real exchange-assigned ISINs.
    Must be exactly 12 characters: 2 uppercase alpha + 9 uppercase alphanumeric + 1 numeric check digit.
    Fabricated internal strings like 'INE155A01022_HIST' will return False.
    \"\"\"
    if not isin or not isinstance(isin, str):
        return False
    return bool(re.match(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$", isin))


@dataclass
class InstrumentDefinition:
    instrument_id: str
    symbol: str
    company_name: str
    isin: Optional[str] = None
    historical_isin: Optional[str] = None
    effective_date: Optional[str] = None"""

    assert old_enums in content, "old_enums not found"
    content = content.replace(old_enums, new_enums)

    # 2. Add Enum import if not present
    if "from enum import Enum" not in content:
        content = "from enum import Enum\n" + content

    # 3. Update LTIM in AUTHORITATIVE_INSTRUMENTS
    old_ltim = """    InstrumentDefinition(
        instrument_id="INST_NSE_LTIM",
        symbol="LTIM",
        company_name="LTIMindtree Limited",
        isin="INE214T01019",
        is_fo_eligible=True,
        is_cas_eligible=True,
        historical_symbols=[
            {"symbol": "LTI", "effective_until": "2022-11-23", "note": "Larsen & Toubro Infotech prior to merger"},
            {"symbol": "MINDTREE", "effective_until": "2022-11-23", "note": "Mindtree Ltd merged into LTI"},
            {"symbol": "LTM", "note": "Dhan and Yahoo provider trading symbol convention"},
        ],
    ),"""

    new_ltm = """    InstrumentDefinition(
        instrument_id="INST_NSE_LTM",
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
    ),"""

    assert old_ltim in content, "old_ltim not found"
    content = content.replace(old_ltim, new_ltm)

    # 4. Update TATAMOTORS_HIST, TMPV, TMCV in AUTHORITATIVE_INSTRUMENTS
    old_tata = """    InstrumentDefinition(
        instrument_id="INST_NSE_TATAMOTORS_HIST",
        symbol="TATAMOTORS",
        company_name="Tata Motors Limited (Pre-Demerger Unified Entity)",
        isin="INE155A01022_HIST",  # Disambiguated historical ISIN tag
        status=InstrumentStatus.DEMERGED,
        is_fo_eligible=True,
        is_cas_eligible=True,
        delisting_date="2025-10-24",
        historical_symbols=[
            {"symbol": "TELCO", "effective_until": "2003-07-29", "note": "Historical brand name"},
        ],
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_TMPV",
        symbol="TMPV",
        company_name="Tata Motors Passenger Vehicles Limited",
        isin="INE155A01022",  # Retains primary historical ISIN
        status=InstrumentStatus.ACTIVE,
        is_fo_eligible=True,  # Retained 384 F&O contracts on NSE
        fo_effective_date="2025-10-24",
        is_cas_eligible=True,
        cas_effective_date="2026-08-03",
        historical_symbols=[
            {"symbol": "TATAMOTORS", "effective_until": "2025-10-24", "note": "Predecessor unified ticker"},
        ],
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_TMCV",
        symbol="TMCV",
        company_name="Tata Motors Limited (Commercial Vehicles)",
        isin="INE1TAE01010",  # Newly assigned ISIN post-demerger
        status=InstrumentStatus.ACTIVE,
        is_fo_eligible=False,  # Not currently in NSE F&O list
        fo_effective_date=None,
        is_cas_eligible=False,  # Governed by standard 75-bar continuous trading
        cas_effective_date=None,
        cas_schedule_version="STANDARD_NON_CAS",
        listing_date="2025-11-12",
        historical_symbols=[],
    ),"""

    new_tata = """    InstrumentDefinition(
        instrument_id="INST_NSE_TATAMOTORS_HIST",
        symbol="TATAMOTORS",
        company_name="Tata Motors Limited (Pre-Demerger Unified Entity)",
        isin=None,  # Nullable: never fabricated with _HIST suffix!
        historical_isin="INE155A01022",  # Genuine exchange-assigned ISIN held historically
        status=InstrumentStatus.DEMERGED,
        is_fo_eligible=True,
        is_cas_eligible=True,
        listing_date="1945-09-01",
        delisting_date="2025-10-24",
        effective_date="1945-09-01",
        historical_symbols=[
            {"symbol": "TELCO", "valid_from": "1945-09-01", "valid_to": "2003-07-29", "effective_until": "2003-07-29", "note": "Historical brand name"},
        ],
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_TMPV",
        symbol="TMPV",
        company_name="Tata Motors Passenger Vehicles Limited",
        isin="INE155A01022",  # Retains primary exchange-assigned ISIN post-demerger
        historical_isin=None,
        status=InstrumentStatus.ACTIVE,
        effective_date="2025-10-24",
        is_fo_eligible=True,  # Retained 384 F&O contracts on NSE
        fo_effective_date="2025-10-24",
        is_cas_eligible=True,
        cas_effective_date="2026-08-03",
        historical_symbols=[
            {"symbol": "TATAMOTORS", "valid_from": "1945-09-01", "valid_to": "2025-10-23", "effective_until": "2025-10-24", "note": "Predecessor unified ticker"},
        ],
    ),
    InstrumentDefinition(
        instrument_id="INST_NSE_TMCV",
        symbol="TMCV",
        company_name="Tata Motors Limited (Commercial Vehicles)",
        isin="INE1TAE01010",  # Newly assigned ISIN post-demerger
        historical_isin=None,
        status=InstrumentStatus.ACTIVE,
        effective_date="2025-11-12",
        is_fo_eligible=False,  # Not in NSE F&O list
        fo_effective_date=None,
        is_cas_eligible=False,  # Governed by standard 75-bar continuous trading
        cas_effective_date=None,
        cas_schedule_version="STANDARD_NON_CAS",
        listing_date="2025-11-12",
        historical_symbols=[],
    ),"""

    assert old_tata in content, "old_tata not found"
    content = content.replace(old_tata, new_tata)

    # 5. Update provider mappings for LTM
    old_ltim_map = """    # LTIM (Uses LTM.NS on Yahoo and LTM / 17818 on Dhan)
    ProviderMappingDefinition(
        "MAP_LTIM_YF", "INST_NSE_LTIM", "yfinance", "LTM.NS", "17818",
        notes="Yahoo ticker override: LTIM.NS is HTTP 404, LTM.NS is verified active LTIMindtree stream"
    ),
    ProviderMappingDefinition(
        "MAP_LTIM_DHAN", "INST_NSE_LTIM", "dhan", "LTM", "17818",
        notes="Dhan Scrip Master mapping: trading symbol LTM, security ID 17818"
    ),"""

    new_ltm_map = """    # LTM (LTIMindtree Limited - Changed from LTIM effective Feb 27, 2026 per NSE/CML/72948)
    ProviderMappingDefinition(
        "MAP_LTM_YF", "INST_NSE_LTM", "yfinance", "LTM.NS", "17818",
        notes="Verified via empirical probe: LTM.NS returns active bars, LTIM.NS returns 404 delisted"
    ),
    ProviderMappingDefinition(
        "MAP_LTM_DHAN", "INST_NSE_LTM", "dhan", "LTM", "17818",
        notes="Verified via Dhan Scrip Master row 175014: SEM_SMST_SECURITY_ID 17818, SEM_TRADING_SYMBOL LTM"
    ),"""

    assert old_ltim_map in content, "old_ltim_map not found"
    content = content.replace(old_ltim_map, new_ltm_map)

    # 6. Update corporate actions
    old_cas = """AUTHORITATIVE_CORPORATE_ACTIONS: List[CorporateActionRecord] = [
    # 1. Tata Motors Demerger (Oct 24, 2025)
    CorporateActionRecord(
        action_id="CA_TATAMOTORS_DEMERGER_2025",
        instrument_id="INST_NSE_TATAMOTORS_HIST",
        action_type=CorporateActionType.DEMERGER,
        ex_date="2025-10-24",
        record_date="2025-10-24",
        ratio="1:1",
        pre_action_symbol="TATAMOTORS",
        post_action_symbol="TMPV",
        resulting_instrument_id="INST_NSE_TMCV",
        historical_adjustment_factor=1.0,
        adjustment_treatment="DEMERGER_SEPARATE",
        description=(
            "Demerger of Tata Motors Limited into two separate listed entities: "
            "1. Commercial Vehicles (TMCV, ISIN INE1TAE01010). "
            "2. Passenger Vehicles & EV Mobility (TMPV, ISIN INE155A01022). "
            "Entitlement ratio 1:1 (1 share of TMCV for every 1 share of Tata Motors held). "
            "Entities are maintained as strictly distinct instruments; no synthetic price merging."
        ),
        circular_reference="NSE/CML/2025/10/DEMERGER_TATA_MOTORS",
    ),
    # 2. LTI and Mindtree Merger (Nov 23, 2022)
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
            "Merged company renamed to LTIMindtree Limited (LTIM). "
            "Yahoo Finance uses ticker LTM.NS; Dhan scrip master uses LTM (ID 17818)."
        ),
        circular_reference="NSE/CML/54589",
    ),
]"""

    new_cas = """AUTHORITATIVE_CORPORATE_ACTIONS: List[CorporateActionRecord] = [
    # 1. Tata Motors Demerger (Oct 24, 2025)
    CorporateActionRecord(
        action_id="CA_TATAMOTORS_DEMERGER_2025",
        instrument_id="INST_NSE_TATAMOTORS_HIST",
        action_type=CorporateActionType.DEMERGER,
        ex_date="2025-10-24",
        record_date="2025-10-24",
        ratio="1:1",
        pre_action_symbol="TATAMOTORS",
        post_action_symbol="TMPV",
        resulting_instrument_id="INST_NSE_TMCV",
        historical_adjustment_factor=1.0,  # Entitlement ratio 1:1 does NOT equal 1.0 price adjustment!
        adjustment_treatment="DEMERGER_SEPARATE_PRICE_DISCONTINUITY",
        description=(
            "Demerger of Tata Motors Limited into TMPV (PV & EV, ISIN INE155A01022) and TMCV (CV, ISIN INE1TAE01010). "
            "Entitlement ratio 1:1. Historical prices are NOT equal 1:1; pre-demerger combined history belongs exclusively to TATAMOTORS_HIST under RAW_ONLY policy. "
            "Unadjusted 1:1 price merging is strictly prohibited."
        ),
        circular_reference="NSE/CML/2025/10/DEMERGER_TATA_MOTORS",
    ),
    # 2. LTI and Mindtree Merger (Nov 23, 2022)
    CorporateActionRecord(
        action_id="CA_LTIM_MERGER_2022",
        instrument_id="INST_NSE_LTM",
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
    # 3. LTIM to LTM Symbol Change (Feb 27, 2026 - NSE Circular NSE/CML/72948)
    CorporateActionRecord(
        action_id="CA_LTM_SYMBOL_CHANGE_2026",
        instrument_id="INST_NSE_LTM",
        action_type=CorporateActionType.SYMBOL_CHANGE,
        ex_date="2026-02-27",
        record_date="2026-02-27",
        ratio=None,
        pre_action_symbol="LTIM",
        post_action_symbol="LTM",
        resulting_instrument_id="INST_NSE_LTM",
        historical_adjustment_factor=1.0,
        adjustment_treatment="NAME_OR_SYMBOL_CHANGE",
        description=(
            "NSE Circular NSE/CML/72948: Change in trading symbol of LTIMindtree Limited from LTIM to LTM effective February 27, 2026. "
            "ISIN INE214T01019, instrument ID INST_NSE_LTM, and Dhan scrip ID 17818 remain unchanged."
        ),
        circular_reference="NSE/CML/72948",
    ),
]"""

    assert old_cas in content, "old_cas not found"
    content = content.replace(old_cas, new_cas)

    # 7. Update resolve_instrument to handle INST_NSE_LTIM -> INST_NSE_LTM
    old_res = """        # Clean trailing .NS or .BO if passed
        base_sym = clean.split(".")[0]

        # 1-4. Direct database lookup (by ID, ISIN, symbol, or historical symbol)
        inst = db_get_instrument(clean) or db_get_instrument(base_sym)"""

    new_res = """        # Clean trailing .NS or .BO if passed
        base_sym = clean.split(".")[0]

        # Handle historical ID alias
        lookup_target = "INST_NSE_LTM" if clean == "INST_NSE_LTIM" else clean
        lookup_base = "LTM" if base_sym == "LTIM" and clean != "LTIM" else base_sym

        # 1-4. Direct database lookup (by ID, ISIN, historical_isin, symbol, or historical symbol)
        inst = db_get_instrument(lookup_target) or db_get_instrument(lookup_base) or db_get_instrument(clean) or db_get_instrument(base_sym)"""

    assert old_res in content, "old_res not found"
    content = content.replace(old_res, new_res)

    # 8. Remove the fake copying of TATAMOTORS observed bars to TMPV in get_universe_reconciliation
    old_recon_copy = """                # Also check historical symbol bar count if demerged/renamed
                if obs_count == 0 and sym == "TMPV":
                    obs_alt = con.execute(
                        "SELECT COUNT(*) FROM observed_intraday_ohlcv WHERE symbol = 'TATAMOTORS' AND interval = '5m'"
                    ).fetchone()
                    alt_count = obs_alt[0] if obs_alt else 0
                    if alt_count > 0:
                        obs_count = alt_count"""

    new_recon_copy = """                # Predecessor observations are NEVER copied into successor counts under Phase 14.9.1 rules"""

    assert old_recon_copy in content, "old_recon_copy not found"
    content = content.replace(old_recon_copy, new_recon_copy)

    # 9. Add resolve_symbol_for_date and get_price_continuity_series to InstrumentMasterService class
    old_recon_def = """    def get_universe_reconciliation(self) -> List[Dict[str, Any]]:"""

    new_methods = """    def resolve_symbol_for_date(self, symbol_or_id: str, query_date: str) -> str:
        \"\"\"
        Resolve the effective NSE trading symbol for a given calendar date (YYYY-MM-DD).
        Handles historical symbol transitions:
        - LTIM -> LTM effective 2026-02-27 (NSE Circular NSE/CML/72948)
        - TATAMOTORS -> TMPV / TMCV effective 2025-10-24
        - LTI -> LTIM effective 2022-11-23
        \"\"\"
        self.ensure_seeded()
        inst = self.resolve_instrument(symbol_or_id)
        if not inst:
            return symbol_or_id.upper()

        current_symbol = inst["symbol"]
        hist_symbols = inst.get("historical_symbols") or []

        for h in hist_symbols:
            h_sym = h.get("symbol")
            val_from = h.get("valid_from")
            val_to = h.get("valid_to") or h.get("effective_until")
            if val_to and query_date <= val_to:
                if not val_from or query_date >= val_from:
                    return h_sym

        return current_symbol

    def get_price_continuity_series(
        self,
        symbol_or_id: str,
        start_date: str,
        end_date: str,
        policy: PriceAdjustmentPolicy = PriceAdjustmentPolicy.RAW_ONLY,
    ) -> Dict[str, Any]:
        \"\"\"
        Enforce explicit corporate action price continuity policies.
        Prevents improper 1:1 splicing of predecessor and successor series.
        \"\"\"
        self.ensure_seeded()
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
            "policy": policy.value if isinstance(policy, PriceAdjustmentPolicy) else policy,
            "status": "VALIDATED",
            "notes": [],
            "predecessor_data_status": "AVAILABLE",
            "adjustment_factor_applied": 1.0,
        }

        if symbol == "TMPV":
            if policy == PriceAdjustmentPolicy.RAW_ONLY:
                if start_date < "2025-10-24":
                    result["predecessor_data_status"] = "UNAVAILABLE_WITHOUT_ADJUSTMENT"
                    result["notes"].append(
                        "Pre-demerger raw data prior to 2025-10-24 belongs strictly to predecessor INST_NSE_TATAMOTORS_HIST. "
                        "Successor raw series begins 2025-10-24."
                    )
            elif policy == PriceAdjustmentPolicy.COST_APPORTIONMENT:
                result["adjustment_factor_applied"] = 0.407
                result["notes"].append("Pre-demerger combined prices scaled by 40.7% passenger vehicle cost apportionment ratio.")
        elif symbol == "TMCV":
            if policy == PriceAdjustmentPolicy.RAW_ONLY:
                if start_date < "2025-11-12":
                    result["predecessor_data_status"] = "UNAVAILABLE_WITHOUT_ADJUSTMENT"
                    result["notes"].append(
                        "Commercial vehicles entity listed on 2025-11-12. Prior data is unavailable under RAW_ONLY policy."
                    )
            elif policy == PriceAdjustmentPolicy.COST_APPORTIONMENT:
                result["adjustment_factor_applied"] = 0.593
                result["notes"].append("Pre-demerger combined prices scaled by 59.3% commercial vehicle cost apportionment ratio.")
        elif symbol == "TATAMOTORS" and inst_id == "INST_NSE_TATAMOTORS_HIST":
            if end_date >= "2025-10-24":
                result["notes"].append("Predecessor trading ceased on 2025-10-23 ex-demerger. Post-demerger data unavailable.")

        return result

    def get_universe_reconciliation(self) -> List[Dict[str, Any]]:"""

    assert old_recon_def in content, "old_recon_def not found"
    content = content.replace(old_recon_def, new_methods)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("instrument_master_service.py successfully patched.")

if __name__ == "__main__":
    patch()

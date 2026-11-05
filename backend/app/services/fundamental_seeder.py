"""
Fundamental financial statements seed data service.

Populates multi-year annual (FY2020–FY2024) and quarterly (Q1FY2023–Q4FY2024)
financial statements for benchmark Indian universe stocks.
This allows full testing of multi-year CAGRs, YoY quarterly growth, ratio calculations,
and the Company Research page without external API calls.
"""

from __future__ import annotations

import logging
from typing import Any

from app.fundamental_db import (
    upsert_balance_sheet,
    upsert_cash_flow,
    upsert_company_profile,
    upsert_income_statement,
    upsert_key_ratios,
    upsert_shareholding,
)
from app.schemas.fundamentals import (
    BalanceSheet,
    CashFlow,
    CompanyProfile,
    FundamentalSource,
    IncomeStatement,
    KeyRatios,
    ReportingFrequency,
    ShareholdingPattern,
    StatementType,
)

logger = logging.getLogger(__name__)

# Sample multi-year data for key benchmark stocks
# Financial figures are in Crores (₹ Cr)
COMPANY_DATA: dict[str, dict[str, Any]] = {
    "TCS": {
        "isin": "INE467B01029",
        "company_name": "Tata Consultancy Services Limited",
        "sector": "IT",
        "industry": "IT Services",
        "exchange": "NSE",
        "face_value": 1.0,
        "market_cap_cr": 1420000.0,
        "year_of_incorporation": 1968,
        "annual": [
            {
                "period": "FY2020", "period_end": "2020-03-31",
                "rev": 156949.0, "ebitda": 42109.0, "ebit": 38580.0, "net_profit": 32340.0, "eps": 86.19,
                "assets": 113306.0, "equity": 84126.0, "debt": 0.0, "cash": 9666.0, "bvps": 224.2,
                "cfo": 32369.0, "capex": 3192.0, "fcf": 29177.0,
                "roe": 37.3, "roce": 45.8, "pe": 21.1,
            },
            {
                "period": "FY2021", "period_end": "2021-03-31",
                "rev": 164177.0, "ebitda": 46546.0, "ebit": 42481.0, "net_profit": 32430.0, "eps": 86.70,
                "assets": 130386.0, "equity": 86433.0, "debt": 0.0, "cash": 6858.0, "bvps": 233.7,
                "cfo": 38802.0, "capex": 3073.0, "fcf": 35729.0,
                "roe": 38.0, "roce": 47.1, "pe": 36.6,
            },
            {
                "period": "FY2022", "period_end": "2022-03-31",
                "rev": 191754.0, "ebitda": 53057.0, "ebit": 48473.0, "net_profit": 38327.0, "eps": 103.62,
                "assets": 141514.0, "equity": 89139.0, "debt": 0.0, "cash": 12488.0, "bvps": 243.6,
                "cfo": 39949.0, "capex": 3208.0, "fcf": 36741.0,
                "roe": 43.6, "roce": 54.3, "pe": 36.1,
            },
            {
                "period": "FY2023", "period_end": "2023-03-31",
                "rev": 225458.0, "ebitda": 59258.0, "ebit": 54237.0, "net_profit": 42147.0, "eps": 115.19,
                "assets": 143828.0, "equity": 90424.0, "debt": 0.0, "cash": 11032.0, "bvps": 247.1,
                "cfo": 41965.0, "capex": 3159.0, "fcf": 38806.0,
                "roe": 46.9, "roce": 59.2, "pe": 27.8,
            },
            {
                "period": "FY2024", "period_end": "2024-03-31",
                "rev": 240893.0, "ebitda": 64000.0, "ebit": 59000.0, "net_profit": 46099.0, "eps": 127.30,
                "assets": 145000.0, "equity": 90000.0, "debt": 0.0, "cash": 11500.0, "bvps": 248.5,
                "cfo": 44340.0, "capex": 3000.0, "fcf": 41340.0,
                "roe": 51.2, "roce": 62.0, "pe": 28.1,
            },
        ],
        "quarterly": [
            {"period": "Q1FY2024", "period_end": "2023-06-30", "rev": 59381.0, "ebit": 13759.0, "net_profit": 11074.0, "eps": 30.2},
            {"period": "Q2FY2024", "period_end": "2023-09-30", "rev": 59692.0, "ebit": 14483.0, "net_profit": 11342.0, "eps": 31.0},
            {"period": "Q3FY2024", "period_end": "2023-12-31", "rev": 60583.0, "ebit": 15155.0, "net_profit": 11058.0, "eps": 30.3},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "rev": 61237.0, "ebit": 15918.0, "net_profit": 12434.0, "eps": 34.3},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "rev": 62613.0, "ebit": 15444.0, "net_profit": 12040.0, "eps": 33.3},
            {"period": "Q2FY2025", "period_end": "2024-09-30", "rev": 64259.0, "ebit": 15488.0, "net_profit": 11909.0, "eps": 33.0},
        ],
        "shareholding": [
            {"period": "Q2FY2025", "period_end": "2024-09-30", "promoter": 71.77, "pledge": 0.0, "fii": 12.50, "dii": 10.60, "public": 5.13},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "promoter": 71.77, "pledge": 0.0, "fii": 12.35, "dii": 10.45, "public": 5.43},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "promoter": 72.30, "pledge": 0.0, "fii": 12.10, "dii": 9.90, "public": 5.70},
        ],
    },
    "RELIANCE": {
        "isin": "INE002A01018",
        "company_name": "Reliance Industries Limited",
        "sector": "Energy",
        "industry": "Oil & Gas / Conglomerate",
        "exchange": "NSE",
        "face_value": 10.0,
        "market_cap_cr": 1680000.0,
        "year_of_incorporation": 1973,
        "annual": [
            {
                "period": "FY2020", "period_end": "2020-03-31",
                "rev": 596679.0, "ebitda": 88212.0, "ebit": 65992.0, "net_profit": 39354.0, "eps": 63.3,
                "assets": 1163016.0, "equity": 453331.0, "debt": 336294.0, "cash": 25741.0, "bvps": 709.0,
                "cfo": 94877.0, "capex": 76517.0, "fcf": 18360.0,
                "roe": 9.5, "roce": 9.2, "pe": 16.5,
            },
            {
                "period": "FY2021", "period_end": "2021-03-31",
                "rev": 466307.0, "ebitda": 80721.0, "ebit": 54149.0, "net_profit": 49128.0, "eps": 76.4,
                "assets": 1320065.0, "equity": 700172.0, "debt": 251811.0, "cash": 17397.0, "bvps": 1084.0,
                "cfo": 26185.0, "capex": 105828.0, "fcf": -79643.0,
                "roe": 8.5, "roce": 7.4, "pe": 26.2,
            },
            {
                "period": "FY2022", "period_end": "2022-03-31",
                "rev": 699962.0, "ebitda": 110460.0, "ebit": 80662.0, "net_profit": 60705.0, "eps": 94.4,
                "assets": 1499665.0, "equity": 779485.0, "debt": 266305.0, "cash": 36178.0, "bvps": 1162.0,
                "cfo": 110654.0, "capex": 145158.0, "fcf": -34504.0,
                "roe": 8.2, "roce": 8.5, "pe": 27.9,
            },
            {
                "period": "FY2023", "period_end": "2023-03-31",
                "rev": 877835.0, "ebitda": 142200.0, "ebit": 102796.0, "net_profit": 66702.0, "eps": 107.5,
                "assets": 1605809.0, "equity": 831411.0, "debt": 313900.0, "cash": 74345.0, "bvps": 1229.0,
                "cfo": 115033.0, "capex": 141809.0, "fcf": -26776.0,
                "roe": 8.3, "roce": 9.4, "pe": 21.6,
            },
            {
                "period": "FY2024", "period_end": "2024-03-31",
                "rev": 914472.0, "ebitda": 162544.0, "ebit": 112100.0, "net_profit": 69621.0, "eps": 112.5,
                "assets": 1780000.0, "equity": 900000.0, "debt": 324000.0, "cash": 90000.0, "bvps": 1330.0,
                "cfo": 148000.0, "capex": 131000.0, "fcf": 17000.0,
                "roe": 10.8, "roce": 8.2, "pe": 24.5,
            },
        ],
        "quarterly": [
            {"period": "Q1FY2024", "period_end": "2023-06-30", "rev": 207559.0, "ebit": 25500.0, "net_profit": 16011.0, "eps": 25.8},
            {"period": "Q2FY2024", "period_end": "2023-09-30", "rev": 231886.0, "ebit": 27200.0, "net_profit": 17394.0, "eps": 28.0},
            {"period": "Q3FY2024", "period_end": "2023-12-31", "rev": 225086.0, "ebit": 26800.0, "net_profit": 17265.0, "eps": 27.8},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "rev": 236533.0, "ebit": 28600.0, "net_profit": 18951.0, "eps": 30.5},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "rev": 232015.0, "ebit": 26200.0, "net_profit": 15138.0, "eps": 24.4},
            {"period": "Q2FY2025", "period_end": "2024-09-30", "rev": 235481.0, "ebit": 27100.0, "net_profit": 16563.0, "eps": 26.7},
        ],
        "shareholding": [
            {"period": "Q2FY2025", "period_end": "2024-09-30", "promoter": 50.31, "pledge": 0.0, "fii": 21.65, "dii": 17.05, "public": 10.99},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "promoter": 50.31, "pledge": 0.0, "fii": 22.05, "dii": 16.70, "public": 10.94},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "promoter": 50.31, "pledge": 0.0, "fii": 22.40, "dii": 16.20, "public": 11.09},
        ],
    },
    "INFY": {
        "isin": "INE009A01021",
        "company_name": "Infosys Limited",
        "sector": "IT",
        "industry": "IT Services",
        "exchange": "NSE",
        "face_value": 5.0,
        "market_cap_cr": 645000.0,
        "year_of_incorporation": 1981,
        "annual": [
            {
                "period": "FY2020", "period_end": "2020-03-31",
                "rev": 90791.0, "ebitda": 22267.0, "ebit": 19374.0, "net_profit": 16639.0, "eps": 38.9,
                "assets": 84525.0, "equity": 65450.0, "debt": 0.0, "cash": 18649.0, "bvps": 153.2,
                "cfo": 18568.0, "capex": 3381.0, "fcf": 15187.0,
                "roe": 25.5, "roce": 31.2, "pe": 16.8,
            },
            {
                "period": "FY2021", "period_end": "2021-03-31",
                "rev": 100472.0, "ebitda": 27889.0, "ebit": 24622.0, "net_profit": 19351.0, "eps": 45.6,
                "assets": 100062.0, "equity": 76351.0, "debt": 0.0, "cash": 24714.0, "bvps": 179.5,
                "cfo": 24127.0, "capex": 2161.0, "fcf": 21966.0,
                "roe": 27.3, "roce": 34.6, "pe": 30.1,
            },
            {
                "period": "FY2022", "period_end": "2022-03-31",
                "rev": 121641.0, "ebitda": 31491.0, "ebit": 28014.0, "net_profit": 22110.0, "eps": 52.4,
                "assets": 111867.0, "equity": 75350.0, "debt": 0.0, "cash": 17476.0, "bvps": 180.2,
                "cfo": 24964.0, "capex": 2161.0, "fcf": 22803.0,
                "roe": 29.2, "roce": 37.0, "pe": 36.3,
            },
            {
                "period": "FY2023", "period_end": "2023-03-31",
                "rev": 146767.0, "ebitda": 35131.0, "ebit": 30905.0, "net_profit": 24095.0, "eps": 57.6,
                "assets": 125790.0, "equity": 75407.0, "debt": 0.0, "cash": 12173.0, "bvps": 181.9,
                "cfo": 23049.0, "capex": 2577.0, "fcf": 20472.0,
                "roe": 31.9, "roce": 40.5, "pe": 24.8,
            },
            {
                "period": "FY2024", "period_end": "2024-03-31",
                "rev": 153670.0, "ebitda": 36000.0, "ebit": 31500.0, "net_profit": 26233.0, "eps": 63.3,
                "assets": 138000.0, "equity": 86000.0, "debt": 0.0, "cash": 14000.0, "bvps": 207.0,
                "cfo": 26800.0, "capex": 2500.0, "fcf": 24300.0,
                "roe": 31.0, "roce": 38.0, "pe": 25.2,
            },
        ],
        "quarterly": [
            {"period": "Q1FY2024", "period_end": "2023-06-30", "rev": 37933.0, "ebit": 7891.0, "net_profit": 5945.0, "eps": 14.3},
            {"period": "Q2FY2024", "period_end": "2023-09-30", "rev": 38994.0, "ebit": 8274.0, "net_profit": 6212.0, "eps": 15.0},
            {"period": "Q3FY2024", "period_end": "2023-12-31", "rev": 38821.0, "ebit": 7961.0, "net_profit": 6106.0, "eps": 14.8},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "rev": 37923.0, "ebit": 7621.0, "net_profit": 7969.0, "eps": 19.3},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "rev": 39315.0, "ebit": 8288.0, "net_profit": 6368.0, "eps": 15.4},
            {"period": "Q2FY2025", "period_end": "2024-09-30", "rev": 40986.0, "ebit": 8649.0, "net_profit": 6506.0, "eps": 15.7},
        ],
        "shareholding": [
            {"period": "Q2FY2025", "period_end": "2024-09-30", "promoter": 14.71, "pledge": 0.0, "fii": 33.10, "dii": 37.80, "public": 14.39},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "promoter": 14.71, "pledge": 0.0, "fii": 33.60, "dii": 37.20, "public": 14.49},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "promoter": 14.71, "pledge": 0.0, "fii": 34.10, "dii": 36.50, "public": 14.69},
        ],
    },
    "HDFCBANK": {
        "isin": "INE040A01034",
        "company_name": "HDFC Bank Limited",
        "sector": "Banking",
        "industry": "Private Sector Bank",
        "exchange": "NSE",
        "face_value": 1.0,
        "market_cap_cr": 1280000.0,
        "year_of_incorporation": 1994,
        "annual": [
            {
                "period": "FY2020", "period_end": "2020-03-31",
                "rev": 138073.0, "ebitda": 32000.0, "ebit": 32000.0, "net_profit": 26257.0, "eps": 48.0,
                "assets": 1530511.0, "equity": 170986.0, "debt": 144628.0, "cash": 86618.0, "bvps": 312.0,
                "cfo": 28000.0, "capex": 1500.0, "fcf": 26500.0,
                "roe": 16.4, "roce": 15.0, "pe": 18.0,
            },
            {
                "period": "FY2021", "period_end": "2021-03-31",
                "rev": 146063.0, "ebitda": 37000.0, "ebit": 37000.0, "net_profit": 31116.0, "eps": 56.4,
                "assets": 1746870.0, "equity": 203721.0, "debt": 135487.0, "cash": 119470.0, "bvps": 369.0,
                "cfo": 42000.0, "capex": 1600.0, "fcf": 40400.0,
                "roe": 16.6, "roce": 15.2, "pe": 26.5,
            },
            {
                "period": "FY2022", "period_end": "2022-03-31",
                "rev": 157851.0, "ebitda": 45000.0, "ebit": 45000.0, "net_profit": 36961.0, "eps": 66.7,
                "assets": 2068535.0, "equity": 240093.0, "debt": 184817.0, "cash": 152998.0, "bvps": 433.0,
                "cfo": -24000.0, "capex": 2200.0, "fcf": -26200.0,
                "roe": 16.7, "roce": 15.5, "pe": 22.0,
            },
            {
                "period": "FY2023", "period_end": "2023-03-31",
                "rev": 192800.0, "ebitda": 54000.0, "ebit": 54000.0, "net_profit": 44109.0, "eps": 79.1,
                "assets": 2466081.0, "equity": 280199.0, "debt": 206766.0, "cash": 193865.0, "bvps": 501.0,
                "cfo": 60000.0, "capex": 2800.0, "fcf": 57200.0,
                "roe": 17.0, "roce": 15.8, "pe": 20.3,
            },
            {
                "period": "FY2024", "period_end": "2024-03-31",
                "rev": 285400.0, "ebitda": 78000.0, "ebit": 78000.0, "net_profit": 60812.0, "eps": 82.5,
                "assets": 3617623.0, "equity": 439000.0, "debt": 660000.0, "cash": 220000.0, "bvps": 578.0,
                "cfo": 65000.0, "capex": 4000.0, "fcf": 61000.0,
                "roe": 16.8, "roce": 14.5, "pe": 19.5,
            },
        ],
        "quarterly": [
            {"period": "Q1FY2024", "period_end": "2023-06-30", "rev": 57816.0, "ebit": 16000.0, "net_profit": 11952.0, "eps": 21.4},
            {"period": "Q2FY2024", "period_end": "2023-09-30", "rev": 78406.0, "ebit": 21000.0, "net_profit": 15976.0, "eps": 21.0},
            {"period": "Q3FY2024", "period_end": "2023-12-31", "rev": 81720.0, "ebit": 22000.0, "net_profit": 16372.0, "eps": 21.6},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "rev": 80702.0, "ebit": 23000.0, "net_profit": 16512.0, "eps": 21.8},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "rev": 82725.0, "ebit": 22500.0, "net_profit": 16175.0, "eps": 21.3},
            {"period": "Q2FY2025", "period_end": "2024-09-30", "rev": 85500.0, "ebit": 23500.0, "net_profit": 16821.0, "eps": 22.1},
        ],
        "shareholding": [
            {"period": "Q2FY2025", "period_end": "2024-09-30", "promoter": 0.0, "pledge": 0.0, "fii": 50.80, "dii": 33.40, "public": 15.80},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "promoter": 0.0, "pledge": 0.0, "fii": 47.20, "dii": 36.10, "public": 16.70},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "promoter": 0.0, "pledge": 0.0, "fii": 47.80, "dii": 35.80, "public": 16.40},
        ],
    },
}


def seed_fundamental_data(force: bool = False) -> int:
    """
    Seed realistic multi-year statements into SQLite fundamental tables.
    Returns the total number of statement records created.
    """
    from app.database import connect

    total_seeded = 0
    with connect() as con:
        # Check if already seeded
        if not force:
            count = con.execute("SELECT COUNT(*) FROM fundamental_income_statements").fetchone()[0]
            if count >= 10:
                logger.info("Fundamental data already populated (%d statements)", count)
                return count

    for symbol, data in COMPANY_DATA.items():
        isin = data["isin"]

        # 1. Company Profile
        profile = CompanyProfile(
            symbol=symbol,
            isin=isin,
            company_name=data["company_name"],
            sector=data["sector"],
            industry=data["industry"],
            exchange=data["exchange"],
            face_value=data["face_value"],
            market_cap_cr=data["market_cap_cr"],
            year_of_incorporation=data["year_of_incorporation"],
            source=FundamentalSource.DEMO,
            fetched_at="2026-10-31T00:00:00Z",
        )
        upsert_company_profile(profile)

        # 2. Annual Statements
        for a in data["annual"]:
            # Income
            inc = IncomeStatement(
                symbol=symbol,
                isin=isin,
                period=a["period"],
                period_end_date=a["period_end"],
                statement_type=StatementType.CONSOLIDATED,
                frequency=ReportingFrequency.YEARLY,
                revenue_cr=a["rev"],
                ebitda_cr=a["ebitda"],
                ebit_cr=a["ebit"],
                net_profit_cr=a["net_profit"],
                eps=a["eps"],
                verification_status="verified",
                source=FundamentalSource.DEMO,
                fetched_at="2026-10-31T00:00:00Z",
            )
            upsert_income_statement(inc)
            total_seeded += 1

            # Balance Sheet
            bs = BalanceSheet(
                symbol=symbol,
                isin=isin,
                period=a["period"],
                period_end_date=a["period_end"],
                statement_type=StatementType.CONSOLIDATED,
                frequency=ReportingFrequency.YEARLY,
                total_assets_cr=a["assets"],
                total_equity_cr=a["equity"],
                total_debt_cr=a["debt"],
                cash_and_equivalents_cr=a["cash"],
                book_value_per_share=a["bvps"],
                verification_status="verified",
                source=FundamentalSource.DEMO,
                fetched_at="2026-10-31T00:00:00Z",
            )
            upsert_balance_sheet(bs)

            # Cash Flow
            cf = CashFlow(
                symbol=symbol,
                isin=isin,
                period=a["period"],
                period_end_date=a["period_end"],
                statement_type=StatementType.CONSOLIDATED,
                frequency=ReportingFrequency.YEARLY,
                operating_cash_flow_cr=a["cfo"],
                capex_cr=a["capex"],
                free_cash_flow_cr=a["fcf"],
                verification_status="verified",
                source=FundamentalSource.DEMO,
                fetched_at="2026-10-31T00:00:00Z",
            )
            upsert_cash_flow(cf)

            # Key Ratios
            kr = KeyRatios(
                symbol=symbol,
                isin=isin,
                period=a["period"],
                period_end_date=a["period_end"],
                statement_type=StatementType.CONSOLIDATED,
                frequency=ReportingFrequency.YEARLY,
                roe=a.get("roe"),
                roce=a.get("roce"),
                pe=a.get("pe"),
                verification_status="verified",
                source=FundamentalSource.DEMO,
                fetched_at="2026-10-31T00:00:00Z",
            )
            upsert_key_ratios(kr)

        # 3. Quarterly Statements
        for q in data.get("quarterly", []):
            q_inc = IncomeStatement(
                symbol=symbol,
                isin=isin,
                period=q["period"],
                period_end_date=q["period_end"],
                statement_type=StatementType.CONSOLIDATED,
                frequency=ReportingFrequency.QUARTERLY,
                revenue_cr=q["rev"],
                ebit_cr=q["ebit"],
                net_profit_cr=q["net_profit"],
                eps=q.get("eps"),
                verification_status="verified",
                source=FundamentalSource.DEMO,
                fetched_at="2026-10-31T00:00:00Z",
            )
            upsert_income_statement(q_inc)
            total_seeded += 1

        # 4. Shareholding Patterns
        for sh in data.get("shareholding", []):
            sh_pat = ShareholdingPattern(
                symbol=symbol,
                isin=isin,
                period=sh["period"],
                period_end_date=sh["period_end"],
                promoter_holding=sh["promoter"],
                promoter_pledging=sh["pledge"],
                fii_holding=sh["fii"],
                dii_holding=sh["dii"],
                public_holding=sh["public"],
                verification_status="verified",
                source=FundamentalSource.DEMO,
                fetched_at="2026-10-31T00:00:00Z",
            )
            upsert_shareholding(sh_pat)

    logger.info("Successfully seeded %d fundamental statement records", total_seeded)
    return total_seeded

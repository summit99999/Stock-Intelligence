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
    "ETERNAL": {
        "isin": "INE758T01015",
        "company_name": "Eternal Ltd (formerly Zomato Ltd)",
        "sector": "Consumer Services",
        "industry": "Internet & Quick Commerce",
        "exchange": "NSE",
        "face_value": 1.0,
        "market_cap_cr": 245000.0,
        "year_of_incorporation": 2010,
        "annual": [
            {
                "period": "FY2021", "period_end": "2021-03-31",
                "rev": 1994.0, "ebitda": -467.0, "ebit": -467.0, "net_profit": -816.0, "eps": -1.10,
                "assets": 8704.0, "equity": 7650.0, "debt": 0.0, "cash": 3200.0, "bvps": 9.7,
                "cfo": -1017.0, "capex": 50.0, "fcf": -1067.0,
                "roe": -10.7, "roce": -6.1, "pe": None,
            },
            {
                "period": "FY2022", "period_end": "2022-03-31",
                "rev": 4192.0, "ebitda": -1009.0, "ebit": -1009.0, "net_profit": -1222.0, "eps": -1.60,
                "assets": 17327.0, "equity": 16505.0, "debt": 0.0, "cash": 12200.0, "bvps": 21.0,
                "cfo": -701.0, "capex": 150.0, "fcf": -851.0,
                "roe": -7.4, "roce": -6.1, "pe": None,
            },
            {
                "period": "FY2023", "period_end": "2023-03-31",
                "rev": 7079.0, "ebitda": -722.0, "ebit": -722.0, "net_profit": -971.0, "eps": -1.14,
                "assets": 20436.0, "equity": 19450.0, "debt": 0.0, "cash": 11300.0, "bvps": 22.8,
                "cfo": -844.0, "capex": 200.0, "fcf": -1044.0,
                "roe": -5.0, "roce": -3.7, "pe": None,
            },
            {
                "period": "FY2024", "period_end": "2024-03-31",
                "rev": 12114.0, "ebitda": 540.0, "ebit": 210.0, "net_profit": 351.0, "eps": 0.40,
                "assets": 21800.0, "equity": 20100.0, "debt": 0.0, "cash": 12400.0, "bvps": 23.5,
                "cfo": 1100.0, "capex": 250.0, "fcf": 850.0,
                "roe": 1.75, "roce": 1.04, "pe": 900.0,
            },
        ],
        "quarterly": [
            {"period": "Q3FY2022", "period_end": "2021-12-31", "rev": 1112.0, "opex": 1550.0, "operating_profit": -438.0, "ebitda": -400.0, "depreciation": 38.0, "ebit": -438.0, "interest": 4.0, "pbt": -442.0, "tax": 0.0, "net_profit": -442.0, "eps": -0.56},
            {"period": "Q4FY2022", "period_end": "2022-03-31", "rev": 1212.0, "opex": 1572.0, "operating_profit": -360.0, "ebitda": -319.0, "depreciation": 41.0, "ebit": -360.0, "interest": 5.0, "pbt": -365.0, "tax": 0.0, "net_profit": -365.0, "eps": -0.46},
            {"period": "Q1FY2023", "period_end": "2022-06-30", "rev": 1414.0, "opex": 1721.0, "operating_profit": -307.0, "ebitda": -265.0, "depreciation": 42.0, "ebit": -307.0, "interest": 6.0, "pbt": -313.0, "tax": 0.0, "net_profit": -313.0, "eps": -0.39},
            {"period": "Q2FY2023", "period_end": "2022-09-30", "rev": 1661.0, "opex": 1912.0, "operating_profit": -251.0, "ebitda": -208.0, "depreciation": 43.0, "ebit": -251.0, "interest": 7.0, "pbt": -258.0, "tax": 0.0, "net_profit": -258.0, "eps": -0.32},
            {"period": "Q3FY2023", "period_end": "2022-12-31", "rev": 1948.0, "opex": 2147.0, "operating_profit": -199.0, "ebitda": -155.0, "depreciation": 44.0, "ebit": -199.0, "interest": 8.0, "pbt": -207.0, "tax": 0.0, "net_profit": -207.0, "eps": -0.25},
            {"period": "Q4FY2023", "period_end": "2023-03-31", "rev": 2056.0, "opex": 2188.0, "operating_profit": -132.0, "ebitda": -87.0, "depreciation": 45.0, "ebit": -132.0, "interest": 8.0, "pbt": -140.0, "tax": 0.0, "net_profit": -140.0, "eps": -0.17},
            {"period": "Q1FY2024", "period_end": "2023-06-30", "rev": 2416.0, "opex": 2404.0, "operating_profit": 12.0, "ebitda": 63.0, "depreciation": 51.0, "ebit": 12.0, "interest": 10.0, "pbt": 2.0, "tax": 0.0, "net_profit": 2.0, "eps": 0.00},
            {"period": "Q2FY2024", "period_end": "2023-09-30", "rev": 2848.0, "opex": 2795.0, "operating_profit": 53.0, "ebitda": 110.0, "depreciation": 57.0, "ebit": 53.0, "interest": 11.0, "pbt": 36.0, "tax": 0.0, "net_profit": 36.0, "eps": 0.04},
            {"period": "Q3FY2024", "period_end": "2023-12-31", "rev": 3288.0, "opex": 3150.0, "operating_profit": 138.0, "ebitda": 200.0, "depreciation": 62.0, "ebit": 138.0, "interest": 12.0, "pbt": 138.0, "tax": 0.0, "net_profit": 138.0, "eps": 0.16},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "rev": 3562.0, "opex": 3368.0, "operating_profit": 194.0, "ebitda": 261.0, "depreciation": 67.0, "ebit": 194.0, "interest": 13.0, "pbt": 175.0, "tax": 0.0, "net_profit": 175.0, "eps": 0.20},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "rev": 4206.0, "opex": 3907.0, "operating_profit": 299.0, "ebitda": 373.0, "depreciation": 74.0, "ebit": 299.0, "interest": 15.0, "pbt": 253.0, "tax": 0.0, "net_profit": 253.0, "eps": 0.29},
            {"period": "Q2FY2025", "period_end": "2024-09-30", "rev": 4799.0, "opex": 4410.0, "operating_profit": 389.0, "ebitda": 470.0, "depreciation": 81.0, "ebit": 389.0, "interest": 16.0, "pbt": 176.0, "tax": 0.0, "net_profit": 176.0, "eps": 0.20},
        ],
        "shareholding": [
            {"period": "Q2FY2025", "period_end": "2024-09-30", "promoter": 0.0, "pledge": 0.0, "fii": 52.30, "dii": 16.80, "public": 30.90},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "promoter": 0.0, "pledge": 0.0, "fii": 54.10, "dii": 15.40, "public": 30.50},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "promoter": 0.0, "pledge": 0.0, "fii": 55.20, "dii": 14.80, "public": 30.00},
        ],
    },
    "BEL": {
        "isin": "INE263A01024",
        "company_name": "Bharat Electronics Limited",
        "sector": "Defence",
        "industry": "Aerospace & Defence Electronics",
        "exchange": "NSE",
        "face_value": 1.0,
        "market_cap_cr": 215000.0,
        "year_of_incorporation": 1954,
        "annual": [
            {
                "period": "FY2020", "period_end": "2020-03-31",
                "rev": 12921.0, "ebitda": 2730.0, "ebit": 2410.0, "net_profit": 1794.0, "eps": 2.45,
                "assets": 24500.0, "equity": 9850.0, "debt": 0.0, "cash": 2100.0, "bvps": 13.5,
                "cfo": 2410.0, "capex": 580.0, "fcf": 1830.0,
                "roe": 18.2, "roce": 24.5, "pe": 16.5,
            },
            {
                "period": "FY2021", "period_end": "2021-03-31",
                "rev": 14064.0, "ebitda": 3181.0, "ebit": 2831.0, "net_profit": 2065.0, "eps": 2.83,
                "assets": 28000.0, "equity": 10850.0, "debt": 0.0, "cash": 3200.0, "bvps": 14.8,
                "cfo": 3800.0, "capex": 620.0, "fcf": 3180.0,
                "roe": 19.0, "roce": 26.1, "pe": 22.0,
            },
            {
                "period": "FY2022", "period_end": "2022-03-31",
                "rev": 15314.0, "ebitda": 3309.0, "ebit": 2928.0, "net_profit": 2349.0, "eps": 3.21,
                "assets": 31200.0, "equity": 12050.0, "debt": 0.0, "cash": 5500.0, "bvps": 16.5,
                "cfo": 3950.0, "capex": 650.0, "fcf": 3300.0,
                "roe": 19.5, "roce": 24.3, "pe": 28.5,
            },
            {
                "period": "FY2023", "period_end": "2023-03-31",
                "rev": 17333.0, "ebitda": 4004.0, "ebit": 3584.0, "net_profit": 2984.0, "eps": 4.08,
                "assets": 35400.0, "equity": 13900.0, "debt": 0.0, "cash": 7200.0, "bvps": 19.0,
                "cfo": 4320.0, "capex": 700.0, "fcf": 3620.0,
                "roe": 21.5, "roce": 25.8, "pe": 26.8,
            },
            {
                "period": "FY2024", "period_end": "2024-03-31",
                "rev": 20268.0, "ebitda": 5013.0, "ebit": 4578.0, "net_profit": 3985.0, "eps": 5.45,
                "assets": 39800.0, "equity": 16400.0, "debt": 0.0, "cash": 8800.0, "bvps": 22.4,
                "cfo": 4850.0, "capex": 800.0, "fcf": 4050.0,
                "roe": 24.3, "roce": 27.9, "pe": 42.5,
            },
        ],
        "quarterly": [
            {"period": "Q3FY2022", "period_end": "2021-12-31", "rev": 3693.0, "opex": 2871.0, "operating_profit": 822.0, "ebitda": 917.0, "depreciation": 95.0, "ebit": 822.0, "interest": 2.0, "pbt": 779.0, "tax": 196.0, "net_profit": 583.0, "eps": 0.80},
            {"period": "Q4FY2022", "period_end": "2022-03-31", "rev": 6325.0, "opex": 4744.0, "operating_profit": 1581.0, "ebitda": 1679.0, "depreciation": 98.0, "ebit": 1581.0, "interest": 2.0, "pbt": 1526.0, "tax": 384.0, "net_profit": 1142.0, "eps": 1.56},
            {"period": "Q1FY2023", "period_end": "2022-06-30", "rev": 3113.0, "opex": 2598.0, "operating_profit": 515.0, "ebitda": 612.0, "depreciation": 97.0, "ebit": 515.0, "interest": 2.0, "pbt": 556.0, "tax": 141.0, "net_profit": 415.0, "eps": 0.57},
            {"period": "Q2FY2023", "period_end": "2022-09-30", "rev": 3946.0, "opex": 3089.0, "operating_profit": 857.0, "ebitda": 959.0, "depreciation": 102.0, "ebit": 857.0, "interest": 2.0, "pbt": 811.0, "tax": 205.0, "net_profit": 606.0, "eps": 0.83},
            {"period": "Q3FY2023", "period_end": "2022-12-31", "rev": 4131.0, "opex": 3278.0, "operating_profit": 853.0, "ebitda": 957.0, "depreciation": 104.0, "ebit": 853.0, "interest": 2.0, "pbt": 801.0, "tax": 202.0, "net_profit": 599.0, "eps": 0.82},
            {"period": "Q4FY2023", "period_end": "2023-03-31", "rev": 6457.0, "opex": 4697.0, "operating_profit": 1760.0, "ebitda": 1867.0, "depreciation": 107.0, "ebit": 1760.0, "interest": 3.0, "pbt": 1782.0, "tax": 418.0, "net_profit": 1364.0, "eps": 1.87},
            {"period": "Q1FY2024", "period_end": "2023-06-30", "rev": 3511.0, "opex": 2847.0, "operating_profit": 664.0, "ebitda": 772.0, "depreciation": 108.0, "ebit": 664.0, "interest": 2.0, "pbt": 704.0, "tax": 174.0, "net_profit": 530.0, "eps": 0.73},
            {"period": "Q2FY2024", "period_end": "2023-09-30", "rev": 3993.0, "opex": 2989.0, "operating_profit": 1004.0, "ebitda": 1114.0, "depreciation": 110.0, "ebit": 1004.0, "interest": 2.0, "pbt": 1073.0, "tax": 260.0, "net_profit": 813.0, "eps": 1.11},
            {"period": "Q3FY2024", "period_end": "2023-12-31", "rev": 4162.0, "opex": 3090.0, "operating_profit": 1072.0, "ebitda": 1184.0, "depreciation": 112.0, "ebit": 1072.0, "interest": 3.0, "pbt": 1146.0, "tax": 287.0, "net_profit": 859.0, "eps": 1.18},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "rev": 8564.0, "opex": 6289.0, "operating_profit": 2275.0, "ebitda": 2393.0, "depreciation": 118.0, "ebit": 2275.0, "interest": 4.0, "pbt": 2391.0, "tax": 608.0, "net_profit": 1783.0, "eps": 2.44},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "rev": 4199.0, "opex": 3254.0, "operating_profit": 945.0, "ebitda": 1060.0, "depreciation": 115.0, "ebit": 945.0, "interest": 3.0, "pbt": 1039.0, "tax": 263.0, "net_profit": 776.0, "eps": 1.06},
            {"period": "Q2FY2025", "period_end": "2024-09-30", "rev": 4583.0, "opex": 3345.0, "operating_profit": 1238.0, "ebitda": 1357.0, "depreciation": 119.0, "ebit": 1238.0, "interest": 3.0, "pbt": 1438.0, "tax": 347.0, "net_profit": 1091.0, "eps": 1.49},
        ],
        "shareholding": [
            {"period": "Q2FY2025", "period_end": "2024-09-30", "promoter": 51.14, "pledge": 0.0, "fii": 17.40, "dii": 23.90, "public": 7.56},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "promoter": 51.14, "pledge": 0.0, "fii": 17.20, "dii": 24.10, "public": 7.56},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "promoter": 51.14, "pledge": 0.0, "fii": 17.50, "dii": 23.60, "public": 7.76},
        ],
    },
    "TRENT": {
        "isin": "INE849A01020",
        "company_name": "Trent Limited (A Tata Enterprise)",
        "sector": "Consumer",
        "industry": "Apparel & Lifestyle Retail",
        "exchange": "NSE",
        "face_value": 1.0,
        "market_cap_cr": 220000.0,
        "year_of_incorporation": 1952,
        "annual": [
            {
                "period": "FY2020", "period_end": "2020-03-31",
                "rev": 3178.0, "ebitda": 544.0, "ebit": 298.0, "net_profit": 106.0, "eps": 2.98,
                "assets": 4900.0, "equity": 2380.0, "debt": 300.0, "cash": 560.0, "bvps": 67.0,
                "cfo": 480.0, "capex": 210.0, "fcf": 270.0,
                "roe": 4.5, "roce": 7.5, "pe": 180.0,
            },
            {
                "period": "FY2021", "period_end": "2021-03-31",
                "rev": 2048.0, "ebitda": 175.0, "ebit": -61.0, "net_profit": -181.0, "eps": -5.09,
                "assets": 5200.0, "equity": 2250.0, "debt": 300.0, "cash": 450.0, "bvps": 63.3,
                "cfo": 190.0, "capex": 120.0, "fcf": 70.0,
                "roe": -8.0, "roce": -1.5, "pe": None,
            },
            {
                "period": "FY2022", "period_end": "2022-03-31",
                "rev": 3881.0, "ebitda": 574.0, "ebit": 288.0, "net_profit": 35.0, "eps": 0.98,
                "assets": 6500.0, "equity": 2350.0, "debt": 500.0, "cash": 520.0, "bvps": 66.1,
                "cfo": 410.0, "capex": 250.0, "fcf": 160.0,
                "roe": 1.5, "roce": 6.8, "pe": 1200.0,
            },
            {
                "period": "FY2023", "period_end": "2023-03-31",
                "rev": 8242.0, "ebitda": 1119.0, "ebit": 695.0, "net_profit": 394.0, "eps": 11.08,
                "assets": 8800.0, "equity": 2650.0, "debt": 500.0, "cash": 610.0, "bvps": 74.5,
                "cfo": 890.0, "capex": 420.0, "fcf": 470.0,
                "roe": 14.8, "roce": 17.5, "pe": 125.0,
            },
            {
                "period": "FY2024", "period_end": "2024-03-31",
                "rev": 12375.0, "ebitda": 2110.0, "ebit": 1570.0, "net_profit": 1477.0, "eps": 41.55,
                "assets": 11200.0, "equity": 4200.0, "debt": 480.0, "cash": 950.0, "bvps": 118.0,
                "cfo": 1950.0, "capex": 600.0, "fcf": 1350.0,
                "roe": 35.2, "roce": 32.5, "pe": 110.0,
            },
        ],
        "quarterly": [
            {"period": "Q3FY2022", "period_end": "2021-12-31", "rev": 1349.0, "opex": 1150.0, "operating_profit": 199.0, "ebitda": 272.0, "depreciation": 73.0, "ebit": 199.0, "interest": 72.0, "pbt": 174.0, "tax": 41.0, "net_profit": 133.0, "eps": 3.74},
            {"period": "Q4FY2022", "period_end": "2022-03-31", "rev": 1185.0, "opex": 1032.0, "operating_profit": 153.0, "ebitda": 228.0, "depreciation": 75.0, "ebit": 153.0, "interest": 74.0, "pbt": 24.0, "tax": 7.0, "net_profit": 17.0, "eps": 0.48},
            {"period": "Q1FY2023", "period_end": "2022-06-30", "rev": 1653.0, "opex": 1349.0, "operating_profit": 304.0, "ebitda": 390.0, "depreciation": 86.0, "ebit": 304.0, "interest": 85.0, "pbt": 152.0, "tax": 37.0, "net_profit": 115.0, "eps": 3.23},
            {"period": "Q2FY2023", "period_end": "2022-09-30", "rev": 1814.0, "opex": 1546.0, "operating_profit": 268.0, "ebitda": 363.0, "depreciation": 95.0, "ebit": 268.0, "interest": 89.0, "pbt": 117.0, "tax": 24.0, "net_profit": 93.0, "eps": 2.62},
            {"period": "Q3FY2023", "period_end": "2022-12-31", "rev": 2171.0, "opex": 1835.0, "operating_profit": 336.0, "ebitda": 439.0, "depreciation": 103.0, "ebit": 336.0, "interest": 92.0, "pbt": 206.0, "tax": 51.0, "net_profit": 155.0, "eps": 4.36},
            {"period": "Q4FY2023", "period_end": "2023-03-31", "rev": 2077.0, "opex": 1867.0, "operating_profit": 210.0, "ebitda": 320.0, "depreciation": 110.0, "ebit": 210.0, "interest": 98.0, "pbt": 59.0, "tax": 14.0, "net_profit": 45.0, "eps": 1.27},
            {"period": "Q1FY2024", "period_end": "2023-06-30", "rev": 2514.0, "opex": 2147.0, "operating_profit": 367.0, "ebitda": 492.0, "depreciation": 125.0, "ebit": 367.0, "interest": 102.0, "pbt": 206.0, "tax": 58.0, "net_profit": 148.0, "eps": 4.16},
            {"period": "Q2FY2024", "period_end": "2023-09-30", "rev": 2891.0, "opex": 2434.0, "operating_profit": 457.0, "ebitda": 595.0, "depreciation": 138.0, "ebit": 457.0, "interest": 107.0, "pbt": 304.0, "tax": 76.0, "net_profit": 228.0, "eps": 6.41},
            {"period": "Q3FY2024", "period_end": "2023-12-31", "rev": 3312.0, "opex": 2683.0, "operating_profit": 629.0, "ebitda": 781.0, "depreciation": 152.0, "ebit": 629.0, "interest": 114.0, "pbt": 482.0, "tax": 111.0, "net_profit": 371.0, "eps": 10.43},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "rev": 3187.0, "opex": 2707.0, "operating_profit": 480.0, "ebitda": 643.0, "depreciation": 163.0, "ebit": 480.0, "interest": 120.0, "pbt": 942.0, "tax": 230.0, "net_profit": 712.0, "eps": 20.03},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "rev": 3992.0, "opex": 3381.0, "operating_profit": 611.0, "ebitda": 796.0, "depreciation": 185.0, "ebit": 611.0, "interest": 132.0, "pbt": 471.0, "tax": 136.0, "net_profit": 335.0, "eps": 9.42},
            {"period": "Q2FY2025", "period_end": "2024-09-30", "rev": 4035.0, "opex": 3443.0, "operating_profit": 592.0, "ebitda": 790.0, "depreciation": 198.0, "ebit": 592.0, "interest": 139.0, "pbt": 421.0, "tax": 103.0, "net_profit": 318.0, "eps": 8.94},
        ],
        "shareholding": [
            {"period": "Q2FY2025", "period_end": "2024-09-30", "promoter": 37.01, "pledge": 0.0, "fii": 28.00, "dii": 15.60, "public": 19.39},
            {"period": "Q1FY2025", "period_end": "2024-06-30", "promoter": 37.01, "pledge": 0.0, "fii": 27.80, "dii": 15.70, "public": 19.49},
            {"period": "Q4FY2024", "period_end": "2024-03-31", "promoter": 37.01, "pledge": 0.0, "fii": 27.40, "dii": 15.90, "public": 19.69},
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

    for symbol, data in COMPANY_DATA.items():
        isin = data["isin"]

        with connect() as con:
            count = con.execute("SELECT COUNT(*) FROM fundamental_income_statements WHERE symbol = ?", (symbol,)).fetchone()[0]
            if count >= 4 and not force:
                continue

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
            rev = float(q["rev"])
            np_val = float(q["net_profit"])
            ebit = float(q.get("ebit") or (rev * 0.22))
            deprec = float(q.get("depreciation") or (rev * 0.04))
            ebitda = float(q.get("ebitda") or (ebit + deprec))
            opex = float(q.get("opex") or max(0.0, rev - ebitda))
            op = float(q.get("operating_profit") or ebitda)
            interest = float(q.get("interest") or 0.0)
            pbt = float(q.get("pbt") or max(np_val, ebit - interest))
            tax = float(q.get("tax") or max(0.0, pbt - np_val))

            q_inc = IncomeStatement(
                symbol=symbol,
                isin=isin,
                period=q["period"],
                period_end_date=q["period_end"],
                statement_type=StatementType.CONSOLIDATED,
                frequency=ReportingFrequency.QUARTERLY,
                revenue_cr=round(rev, 2),
                operating_expenses_cr=round(opex, 2),
                operating_profit_cr=round(op, 2),
                ebitda_cr=round(ebitda, 2),
                depreciation_cr=round(deprec, 2),
                ebit_cr=round(ebit, 2),
                interest_expense_cr=round(interest, 2),
                profit_before_tax_cr=round(pbt, 2),
                tax_expense_cr=round(tax, 2),
                net_profit_cr=round(np_val, 2),
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

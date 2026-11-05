"""
Fundamental data provider manager.

Coordinates multiple fundamental-data sources, handles ISIN resolution,
database persistence, and source-conflict detection.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.providers.fundamentals.base import FundamentalProvider
from app.schemas.fundamentals import (
    BalanceSheet,
    CashFlow,
    CompanyProfile,
    Competitor,
    CorporateAction,
    FundamentalSource,
    IncomeStatement,
    KeyRatios,
    ReportingFrequency,
    ShareholdingPattern,
    SourceConflict,
    StatementType,
    SyncStatus,
)

logger = logging.getLogger(__name__)


class FundamentalProviderManager:
    """Manages fundamental-data providers and persists their output."""

    def __init__(self) -> None:
        self._providers: list[FundamentalProvider] = []

    def register(self, provider: FundamentalProvider) -> None:
        self._providers.append(provider)
        logger.info(
            "Registered fundamental provider: %s (available=%s)",
            provider.source_label().value,
            provider.is_available(),
        )

    @property
    def available_providers(self) -> list[FundamentalProvider]:
        return [p for p in self._providers if p.is_available()]

    @property
    def primary_provider(self) -> Optional[FundamentalProvider]:
        avail = self.available_providers
        return avail[0] if avail else None

    def get_provider(self, source: FundamentalSource) -> Optional[FundamentalProvider]:
        for p in self._providers:
            if p.source_label() == source:
                return p
        return None

    # ------------------------------------------------------------------
    # ISIN resolution
    # ------------------------------------------------------------------

    @staticmethod
    def resolve_isin(symbol: str) -> Optional[str]:
        """Look up ISIN for a symbol from the stocks table."""
        from app.database import get_stock
        stock = get_stock(symbol)
        if stock and stock.get("isin"):
            return stock["isin"]
        return None

    @staticmethod
    def get_symbol_isin_map() -> dict[str, str]:
        """Return {symbol: isin} for all stocks that have ISINs."""
        from app.database import connect
        with connect() as con:
            rows = con.execute(
                "SELECT symbol, isin FROM stocks WHERE isin IS NOT NULL AND isin != ''"
            ).fetchall()
            return {r["symbol"]: r["isin"] for r in rows}

    @staticmethod
    def get_isin_symbol_map() -> dict[str, str]:
        """Return {isin: symbol} for all stocks that have ISINs."""
        mapping = FundamentalProviderManager.get_symbol_isin_map()
        return {v: k for k, v in mapping.items()}

    # ------------------------------------------------------------------
    # Sync individual stock
    # ------------------------------------------------------------------

    async def sync_profile(
        self, symbol: str, provider: Optional[FundamentalProvider] = None
    ) -> Optional[CompanyProfile]:
        isin = self.resolve_isin(symbol)
        if not isin:
            logger.warning("No ISIN for symbol %s — cannot sync profile", symbol)
            return None

        p = provider or self.primary_provider
        if not p:
            logger.warning("No available fundamental provider")
            return None

        profile = await p.fetch_profile(isin)
        if profile:
            profile.symbol = symbol
            self._persist_profile(profile)
            self._record_sync(symbol, isin, p.source_label(), "profile", SyncStatus.OK, 1)
        else:
            self._record_sync(symbol, isin, p.source_label(), "profile", SyncStatus.ERROR, 0,
                              "No data returned")
        return profile

    async def sync_financial_data(
        self,
        symbol: str,
        data_types: list[str],
        statement_type: StatementType = StatementType.CONSOLIDATED,
        frequency: ReportingFrequency = ReportingFrequency.YEARLY,
        provider: Optional[FundamentalProvider] = None,
    ) -> dict[str, int]:
        """
        Sync specified data types for a symbol.
        Returns dict of {data_type: records_fetched}.
        """
        isin = self.resolve_isin(symbol)
        if not isin:
            logger.warning("No ISIN for symbol %s", symbol)
            return {}

        p = provider or self.primary_provider
        if not p:
            logger.warning("No available fundamental provider")
            return {}

        results: dict[str, int] = {}

        for dtype in data_types:
            try:
                count = await self._sync_data_type(
                    symbol, isin, dtype, statement_type, frequency, p
                )
                results[dtype] = count
            except Exception:
                logger.exception("Error syncing %s for %s", dtype, symbol)
                self._record_sync(symbol, isin, p.source_label(), dtype,
                                  SyncStatus.ERROR, 0, "Exception during sync")
                results[dtype] = 0

        return results

    async def _sync_data_type(
        self,
        symbol: str,
        isin: str,
        dtype: str,
        statement_type: StatementType,
        frequency: ReportingFrequency,
        provider: FundamentalProvider,
    ) -> int:
        """Fetch and persist a single data type. Returns record count."""
        count = 0

        if dtype == "profile":
            profile = await provider.fetch_profile(isin)
            if profile:
                profile.symbol = symbol
                self._persist_profile(profile)
                count = 1

        elif dtype == "income_statement":
            items = await provider.fetch_income_statements(isin, statement_type, frequency)
            for item in items:
                item.symbol = symbol
            self._persist_income_statements(items)
            count = len(items)

        elif dtype == "balance_sheet":
            items = await provider.fetch_balance_sheets(isin, statement_type, frequency)
            for item in items:
                item.symbol = symbol
            self._persist_balance_sheets(items)
            count = len(items)

        elif dtype == "cash_flow":
            items = await provider.fetch_cash_flows(isin, statement_type, frequency)
            for item in items:
                item.symbol = symbol
            self._persist_cash_flows(items)
            count = len(items)

        elif dtype == "ratios":
            items = await provider.fetch_ratios(isin, statement_type, frequency)
            for item in items:
                item.symbol = symbol
            self._persist_ratios(items)
            count = len(items)

        elif dtype == "shareholding":
            items = await provider.fetch_shareholding(isin)
            for item in items:
                item.symbol = symbol
            self._persist_shareholding(items)
            count = len(items)

        elif dtype == "corporate_actions":
            items = await provider.fetch_corporate_actions(isin)
            for item in items:
                item.symbol = symbol
            self._persist_corporate_actions(items)
            count = len(items)

        elif dtype == "competitors":
            items = await provider.fetch_competitors(isin)
            for item in items:
                item.symbol = symbol
            self._persist_competitors(items)
            count = len(items)

        else:
            logger.warning("Unknown data type: %s", dtype)
            return 0

        status = SyncStatus.OK if count > 0 else SyncStatus.ERROR
        err = None if count > 0 else "No data returned"
        self._record_sync(symbol, isin, provider.source_label(), dtype, status, count, err)
        return count

    # ------------------------------------------------------------------
    # Source conflict detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_conflicts(
        symbol: str,
        field: str,
        records: list[dict[str, Any]],
        tolerance_pct: float = 5.0,
    ) -> list[SourceConflict]:
        """
        Compare values from different sources for the same field.
        Returns conflicts where values differ by more than tolerance_pct.
        """
        by_source: dict[str, Any] = {}
        for rec in records:
            src = rec.get("source", "unknown")
            val = rec.get(field)
            if val is not None:
                by_source[src] = val

        conflicts: list[SourceConflict] = []
        sources = list(by_source.keys())
        for i in range(len(sources)):
            for j in range(i + 1, len(sources)):
                a_src, a_val = sources[i], by_source[sources[i]]
                b_src, b_val = sources[j], by_source[sources[j]]

                try:
                    a_f, b_f = float(a_val), float(b_val)
                    if a_f == 0 and b_f == 0:
                        continue
                    denom = max(abs(a_f), abs(b_f))
                    if denom == 0:
                        continue
                    diff_pct = abs(a_f - b_f) / denom * 100
                    if diff_pct > tolerance_pct:
                        conflicts.append(SourceConflict(
                            field=field,
                            symbol=symbol,
                            source_a=a_src,
                            value_a=a_val,
                            source_b=b_src,
                            value_b=b_val,
                            discrepancy_pct=round(diff_pct, 2),
                        ))
                except (ValueError, TypeError):
                    if str(a_val) != str(b_val):
                        conflicts.append(SourceConflict(
                            field=field,
                            symbol=symbol,
                            source_a=a_src,
                            value_a=a_val,
                            source_b=b_src,
                            value_b=b_val,
                        ))

        return conflicts

    # ------------------------------------------------------------------
    # Persistence helpers  (all additive — never delete existing data)
    # ------------------------------------------------------------------

    @staticmethod
    def _persist_profile(profile: CompanyProfile) -> None:
        from app import fundamental_db as fdb
        fdb.upsert_company_profile(profile)

    @staticmethod
    def _persist_income_statements(items: list[IncomeStatement]) -> None:
        from app import fundamental_db as fdb
        for item in items:
            fdb.upsert_income_statement(item)

    @staticmethod
    def _persist_balance_sheets(items: list[BalanceSheet]) -> None:
        from app import fundamental_db as fdb
        for item in items:
            fdb.upsert_balance_sheet(item)

    @staticmethod
    def _persist_cash_flows(items: list[CashFlow]) -> None:
        from app import fundamental_db as fdb
        for item in items:
            fdb.upsert_cash_flow(item)

    @staticmethod
    def _persist_ratios(items: list[KeyRatios]) -> None:
        from app import fundamental_db as fdb
        for item in items:
            fdb.upsert_key_ratios(item)

    @staticmethod
    def _persist_shareholding(items: list[ShareholdingPattern]) -> None:
        from app import fundamental_db as fdb
        for item in items:
            fdb.upsert_shareholding(item)

    @staticmethod
    def _persist_corporate_actions(items: list[CorporateAction]) -> None:
        from app import fundamental_db as fdb
        for item in items:
            fdb.upsert_corporate_action(item)

    @staticmethod
    def _persist_competitors(items: list[Competitor]) -> None:
        from app import fundamental_db as fdb
        for item in items:
            fdb.upsert_competitor(item)

    @staticmethod
    def _record_sync(
        symbol: str,
        isin: str,
        source: FundamentalSource,
        data_type: str,
        status: SyncStatus,
        records_fetched: int,
        error_message: Optional[str] = None,
    ) -> None:
        from app import fundamental_db as fdb
        fdb.record_sync_history(
            symbol=symbol,
            isin=isin,
            provider=source.value,
            data_type=data_type,
            status=status.value,
            records_fetched=records_fetched,
            error_message=error_message,
        )


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: Optional[FundamentalProviderManager] = None


def get_fundamental_manager() -> FundamentalProviderManager:
    """Return the singleton FundamentalProviderManager."""
    global _manager
    if _manager is None:
        _manager = FundamentalProviderManager()

        # Auto-register Upstox provider
        try:
            from app.providers.fundamentals.upstox_provider import UpstoxFundamentalProvider
            _manager.register(UpstoxFundamentalProvider())
        except Exception as e:
            logger.warning("Could not register Upstox fundamental provider: %s", e)

        # Register NSE stub (not available but registered for future)
        try:
            from app.providers.fundamentals.nse_provider import NseFilingProvider
            _manager.register(NseFilingProvider())
        except Exception as e:
            logger.warning("Could not register NSE filing provider: %s", e)

        # Register Screener CSV provider
        try:
            from app.providers.fundamentals.screener_csv_provider import ScreenerCsvProvider
            _manager.register(ScreenerCsvProvider())
        except Exception as e:
            logger.warning("Could not register Screener CSV provider: %s", e)

    return _manager

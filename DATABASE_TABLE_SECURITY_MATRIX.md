# Stock Intelligence Pro — Database Table Security Matrix
**Phase 13.1 Pre-Deployment Security Audit & Cloud Integration Validation**  
**Audit Date:** 2026-11-06  
**Target Environment:** Supabase Free (PostgreSQL 15+) / SQLite 3 Local Fallback  

---

## 1. Executive Summary & Inventory Overview

The Stock Intelligence Pro database topology comprises **19 tables** divided into three distinct security and operational tiers:
1. **Public Reference & Ingestion Data (12 tables)**: Market symbols, OHLCV candle bars, update tracking, and fundamental financial disclosures. These tables contain public market intelligence data shared across all users.
2. **User-Scoped Private Assets (7 tables)**: Watchlists, technical alert rules, alert history, custom scanner configurations, screener presets, research trade plans, and qualitative notes. These tables store private trader data and require strict tenant isolation.
3. **Defense-in-Depth Model**:
   - **Layer 1 (Application / Query Tier)**: Every database query on user-scoped tables enforces tenant isolation via parameterized `WHERE user_id = ?` (or `WHERE (user_id = ? OR user_id IS NULL)` for local operator fallback). Cross-tenant read, update, or delete attempts return 0 modified rows and map to HTTP 404/403.
   - **Layer 2 (Database Engine / RLS Tier)**: In PostgreSQL / Supabase, Row-Level Security (`ENABLE ROW LEVEL SECURITY`) is activated on all user-scoped tables, constraining direct client API access (`anon` / `authenticated` roles) to rows where `auth.uid()::text = user_id`.

---

## 2. Comprehensive 19-Table Security Inventory

| # | Table Name | Classification | Primary Key | Foreign Keys | User Ownership (`user_id`) | PostgreSQL RLS Policy | Permissions (`anon` / `authenticated` / `service_role`) |
|---|---|---|---|---|---|---|---|
| **1** | `stocks` | Reference Data | `symbol TEXT` | None | None (Global) | Disabled (Public Reference) | `anon`: SELECT<br>`authenticated`: SELECT<br>`service_role`: ALL |
| **2** | `ohlcv` | Market Time Series | `(symbol, interval, timestamp)` | None | None (Global) | Disabled (Public Market Data) | `anon`: SELECT<br>`authenticated`: SELECT<br>`service_role`: ALL |
| **3** | `data_updates` | System Telemetry | `(symbol, provider)` | None | None (Global) | Disabled (Internal Tracking) | `anon`: SELECT<br>`authenticated`: SELECT<br>`service_role`: ALL |
| **4** | `fundamental_company_profiles` | Fundamental Data | `(isin, source)` | None | None (Global) | Disabled (Public Reference) | `anon`: SELECT<br>`authenticated`: SELECT<br>`service_role`: ALL |
| **5** | `fundamental_income_statements` | Fundamental Data | `(isin, period, statement_type, frequency, source)` | None | None (Global) | Disabled (Public Financials) | `anon`: SELECT<br>`authenticated`: SELECT<br>`service_role`: ALL |
| **6** | `fundamental_balance_sheets` | Fundamental Data | `(isin, period, statement_type, frequency, source)` | None | None (Global) | Disabled (Public Financials) | `anon`: SELECT<br>`authenticated`: SELECT<br>`service_role`: ALL |
| **7** | `fundamental_cash_flows` | Fundamental Data | `(isin, period, statement_type, frequency, source)` | None | None (Global) | Disabled (Public Financials) | `anon`: SELECT<br>`authenticated`: SELECT<br>`service_role`: ALL |
| **8** | `fundamental_ratios` | Fundamental Data | `(isin, period, statement_type, frequency, source)` | None | None (Global) | Disabled (Public Financials) | `anon`: SELECT<br>`authenticated`: SELECT<br>`service_role`: ALL |
| **9** | `fundamental_shareholdings` | Fundamental Data | `(isin, period, source)` | None | None (Global) | Disabled (Public Financials) | `anon`: SELECT<br>`authenticated`: SELECT<br>`service_role`: ALL |
| **10** | `fundamental_corporate_actions` | Fundamental Data | `(isin, action_type, ex_date, source)` | None | None (Global) | Disabled (Public Financials) | `anon`: SELECT<br>`authenticated`: SELECT<br>`service_role`: ALL |
| **11** | `fundamental_competitors` | Fundamental Data | `(isin, peer_symbol, source)` | None | None (Global) | Disabled (Public Financials) | `anon`: SELECT<br>`authenticated`: SELECT<br>`service_role`: ALL |
| **12** | `fundamental_sync_history` | Audit / Operational | `id BIGSERIAL` | None | None (Global) | Disabled (Internal Audit) | `anon`: None<br>`authenticated`: SELECT<br>`service_role`: ALL |
| **13** | `saved_screeners` | User Asset | `id BIGSERIAL` | None | `user_id TEXT` | `auth.uid()::text = user_id` | `anon`: None<br>`authenticated`: SELECT, INSERT, UPDATE, DELETE (Own rows only)<br>`service_role`: ALL |
| **14** | `saved_custom_scanners` | User Asset | `id BIGSERIAL` | None | `user_id TEXT` | `auth.uid()::text = user_id` | `anon`: None<br>`authenticated`: SELECT, INSERT, UPDATE, DELETE (Own rows only)<br>`service_role`: ALL |
| **15** | `custom_watchlists` | User Asset | `id BIGSERIAL` | None | `user_id TEXT` | `auth.uid()::text = user_id` | `anon`: None<br>`authenticated`: SELECT, INSERT, UPDATE, DELETE (Own rows only)<br>`service_role`: ALL |
| **16** | `market_alerts` | User Asset | `id BIGSERIAL` | None | `user_id TEXT` | `auth.uid()::text = user_id` | `anon`: None<br>`authenticated`: SELECT, INSERT, UPDATE, DELETE (Own rows only)<br>`service_role`: ALL |
| **17** | `market_alert_history` | User Asset | `id BIGSERIAL` | `alert_id -> market_alerts(id)` | `user_id TEXT` | `auth.uid()::text = user_id` | `anon`: None<br>`authenticated`: SELECT, INSERT, DELETE (Own rows only)<br>`service_role`: ALL |
| **18** | `research_trade_plans` | User Asset | `id BIGSERIAL` | None | `user_id TEXT` | `auth.uid()::text = user_id` | `anon`: None<br>`authenticated`: SELECT, INSERT, UPDATE, DELETE (Own rows only)<br>`service_role`: ALL |
| **19** | `research_notes` | User Asset | `id BIGSERIAL` | None | `user_id TEXT` | `auth.uid()::text = user_id` | `anon`: None<br>`authenticated`: SELECT, INSERT, DELETE (Own rows only)<br>`service_role`: ALL |

---

## 3. Row-Level Security (RLS) Policy Specifications

In `database/supabase_migrations.sql`, all user-scoped tables have RLS enabled with explicit policy definitions:

```sql
-- Pattern applied to saved_screeners, saved_custom_scanners, custom_watchlists,
-- market_alerts, market_alert_history, research_trade_plans, research_notes:

ALTER TABLE saved_screeners ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can select own screeners"
    ON saved_screeners FOR SELECT
    USING (auth.uid()::text = user_id);

CREATE POLICY "Users can insert own screeners"
    ON saved_screeners FOR INSERT
    WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "Users can update own screeners"
    ON saved_screeners FOR UPDATE
    USING (auth.uid()::text = user_id)
    WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "Users can delete own screeners"
    ON saved_screeners FOR DELETE
    USING (auth.uid()::text = user_id);
```

---

## 4. Multi-Tenant Isolation Verification Evidence

Automated regression suite `backend/tests/test_two_user_isolation.py` verifies tenant isolation across all user tables:
- **Trade Plans Isolation**: Alice's trade plan (`00000000-...-aaaa`) cannot be read, updated, or deleted by Bob (`11111111-...-bbbb`), returning HTTP 404.
- **Qualitative Notes Isolation**: Alice's notes are excluded from Bob's symbol query; Bob's delete attempts return HTTP 404.
- **Watchlists Isolation**: Bob's list does not show Alice's watchlists; Bob's attempts to add symbols or delete Alice's watchlist return HTTP 404.
- **Alerts Isolation**: Bob cannot view, mute, or delete Alice's price alerts.
- **Custom Scanners & Presets**: Bob cannot view or delete Alice's custom scanner definitions or screener presets.
- **Unauthenticated Cloud Rejection**: All 14 user-scoped operations return HTTP 401 Unauthorized when executed without a valid Bearer token in cloud mode.

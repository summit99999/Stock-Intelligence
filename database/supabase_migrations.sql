-- ===========================================================================
-- Stock Intelligence Pro — Complete Supabase PostgreSQL Schema & Migrations
-- Phase 13 Cloud Migration
-- ===========================================================================

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------------------------------------------------------------------------
-- 2. Core Market & Reference Data Tables
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS stocks (
    symbol              TEXT PRIMARY KEY,
    company_name        TEXT NOT NULL,
    exchange            TEXT NOT NULL DEFAULT 'NSE',
    sector              TEXT,
    industry            TEXT,
    cap_category        TEXT,
    isin                TEXT,
    close               DOUBLE PRECISION,
    daily_change_pct    DOUBLE PRECISION,
    week_52_high        DOUBLE PRECISION,
    week_52_low         DOUBLE PRECISION,
    market_cap_cr       DOUBLE PRECISION,
    pe                  DOUBLE PRECISION,
    pb                  DOUBLE PRECISION,
    roe                 DOUBLE PRECISION,
    roce                DOUBLE PRECISION,
    debt_equity         DOUBLE PRECISION,
    revenue_growth_pct  DOUBLE PRECISION,
    profit_growth_pct   DOUBLE PRECISION,
    opm_pct             DOUBLE PRECISION,
    free_cash_flow_cr   DOUBLE PRECISION,
    promoter_holding    DOUBLE PRECISION,
    promoter_pledging   DOUBLE PRECISION,
    fii_holding         DOUBLE PRECISION,
    dii_holding         DOUBLE PRECISION,
    rsi                 DOUBLE PRECISION,
    macd                DOUBLE PRECISION,
    macd_signal         DOUBLE PRECISION,
    adx                 DOUBLE PRECISION,
    supertrend          DOUBLE PRECISION,
    supertrend_dir      TEXT,
    ema_20              DOUBLE PRECISION,
    ema_50              DOUBLE PRECISION,
    ema_100             DOUBLE PRECISION,
    ema_200             DOUBLE PRECISION,
    sma_20              DOUBLE PRECISION,
    sma_50              DOUBLE PRECISION,
    sma_100             DOUBLE PRECISION,
    sma_200             DOUBLE PRECISION,
    volume              BIGINT,
    relative_volume     DOUBLE PRECISION,
    return_1d_pct       DOUBLE PRECISION,
    return_1w_pct       DOUBLE PRECISION,
    return_1m_pct       DOUBLE PRECISION,
    return_3m_pct       DOUBLE PRECISION,
    return_6m_pct       DOUBLE PRECISION,
    return_1y_pct       DOUBLE PRECISION,
    data_source         TEXT DEFAULT 'demo',
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ohlcv (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    interval            TEXT NOT NULL DEFAULT 'daily',
    timestamp           TEXT NOT NULL,
    open                DOUBLE PRECISION,
    high                DOUBLE PRECISION,
    low                 DOUBLE PRECISION,
    close               DOUBLE PRECISION,
    adj_close           DOUBLE PRECISION,
    volume              BIGINT,
    source              TEXT DEFAULT 'demo',
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_ohlcv_candle UNIQUE (symbol, interval, timestamp)
);

CREATE TABLE IF NOT EXISTS intraday_ingestion_runs (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    segment TEXT NOT NULL DEFAULT 'EQUITY',
    interval TEXT NOT NULL DEFAULT '5m',
    start_date TEXT,
    end_date TEXT,
    bar_count INTEGER NOT NULL DEFAULT 0,
    retrieval_timestamp TEXT NOT NULL,
    raw_response_hash TEXT,
    transformation_version TEXT DEFAULT 'v1.0',
    provenance_classification TEXT NOT NULL,
    data_quality_status TEXT NOT NULL,
    error_message TEXT,
    actual_start_date TEXT,
    actual_end_date TEXT,
    provider_metadata_json TEXT,
    session_quality_json TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE intraday_ingestion_runs
    ADD COLUMN IF NOT EXISTS actual_start_date TEXT,
    ADD COLUMN IF NOT EXISTS actual_end_date TEXT,
    ADD COLUMN IF NOT EXISTS provider_metadata_json TEXT,
    ADD COLUMN IF NOT EXISTS session_quality_json TEXT;

CREATE TABLE IF NOT EXISTS bar_provenance (
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    segment TEXT NOT NULL DEFAULT 'EQUITY',
    retrieval_timestamp TEXT NOT NULL,
    ingestion_run_id TEXT NOT NULL,
    raw_response_hash TEXT,
    transformation_version TEXT DEFAULT 'v1.0',
    provenance_classification TEXT NOT NULL,
    data_quality_status TEXT NOT NULL,
    PRIMARY KEY (symbol, interval, timestamp)
);

CREATE TABLE IF NOT EXISTS observed_intraday_ohlcv (
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL DEFAULT '5m',
    timestamp TEXT NOT NULL,
    provider_timestamp TEXT NOT NULL,
    open DOUBLE PRECISION NOT NULL,
    high DOUBLE PRECISION NOT NULL,
    low DOUBLE PRECISION NOT NULL,
    close DOUBLE PRECISION NOT NULL,
    adj_close DOUBLE PRECISION,
    volume BIGINT NOT NULL CHECK (volume >= 0),
    source TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_symbol TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'NSE',
    retrieval_timestamp TEXT NOT NULL,
    ingestion_run_id TEXT NOT NULL,
    raw_response_hash TEXT NOT NULL,
    provenance_classification TEXT NOT NULL,
    data_quality_status TEXT NOT NULL,
    PRIMARY KEY (symbol, interval, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_observed_intraday_sym_int_ts
    ON observed_intraday_ohlcv (symbol, interval, timestamp);
CREATE INDEX IF NOT EXISTS idx_observed_intraday_run
    ON observed_intraday_ohlcv (ingestion_run_id);

CREATE TABLE IF NOT EXISTS data_updates (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    provider            TEXT NOT NULL DEFAULT 'yfinance',
    last_updated        TIMESTAMPTZ,
    bars_count          INTEGER DEFAULT 0,
    period              TEXT,
    status              TEXT DEFAULT 'pending',
    error_message       TEXT,
    CONSTRAINT uq_data_updates UNIQUE (symbol, provider)
);

-- ---------------------------------------------------------------------------
-- 3. Fundamental Datasets (Screener.in / Upstox / yfinance)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS fundamental_company_profiles (
    symbol              TEXT NOT NULL,
    isin                TEXT NOT NULL,
    company_name        TEXT,
    industry            TEXT,
    sector              TEXT,
    exchange            TEXT,
    face_value          DOUBLE PRECISION,
    market_cap_cr       DOUBLE PRECISION,
    year_of_incorporation INTEGER,
    bse_code            TEXT,
    nse_code            TEXT,
    website             TEXT,
    description         TEXT,
    source              TEXT NOT NULL DEFAULT 'demo',
    fetched_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (isin, source)
);

CREATE TABLE IF NOT EXISTS fundamental_income_statements (
    symbol              TEXT NOT NULL,
    isin                TEXT NOT NULL,
    period              TEXT NOT NULL,
    statement_type      TEXT NOT NULL DEFAULT 'consolidated',
    frequency           TEXT NOT NULL DEFAULT 'yearly',
    revenue_cr          DOUBLE PRECISION,
    other_income_cr     DOUBLE PRECISION,
    cost_of_revenue_cr  DOUBLE PRECISION,
    gross_profit_cr     DOUBLE PRECISION,
    operating_expenses_cr DOUBLE PRECISION,
    operating_profit_cr DOUBLE PRECISION,
    ebitda_cr           DOUBLE PRECISION,
    depreciation_cr     DOUBLE PRECISION,
    ebit_cr             DOUBLE PRECISION,
    interest_expense_cr DOUBLE PRECISION,
    profit_before_tax_cr DOUBLE PRECISION,
    tax_expense_cr      DOUBLE PRECISION,
    net_profit_cr       DOUBLE PRECISION,
    eps                 DOUBLE PRECISION,
    diluted_eps         DOUBLE PRECISION,
    period_end_date     TEXT,
    verification_status TEXT DEFAULT 'unverified',
    raw_data            TEXT,
    source              TEXT NOT NULL DEFAULT 'demo',
    fetched_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (isin, period, statement_type, frequency, source)
);

CREATE TABLE IF NOT EXISTS fundamental_balance_sheets (
    symbol              TEXT NOT NULL,
    isin                TEXT NOT NULL,
    period              TEXT NOT NULL,
    statement_type      TEXT NOT NULL DEFAULT 'consolidated',
    frequency           TEXT NOT NULL DEFAULT 'yearly',
    total_assets_cr     DOUBLE PRECISION,
    current_assets_cr   DOUBLE PRECISION,
    non_current_assets_cr DOUBLE PRECISION,
    total_liabilities_cr DOUBLE PRECISION,
    current_liabilities_cr DOUBLE PRECISION,
    non_current_liabilities_cr DOUBLE PRECISION,
    total_equity_cr     DOUBLE PRECISION,
    share_capital_cr    DOUBLE PRECISION,
    reserves_cr         DOUBLE PRECISION,
    borrowings_cr       DOUBLE PRECISION,
    period_end_date     TEXT,
    verification_status TEXT DEFAULT 'unverified',
    raw_data            TEXT,
    source              TEXT NOT NULL DEFAULT 'demo',
    fetched_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (isin, period, statement_type, frequency, source)
);

CREATE TABLE IF NOT EXISTS fundamental_cash_flows (
    symbol              TEXT NOT NULL,
    isin                TEXT NOT NULL,
    period              TEXT NOT NULL,
    statement_type      TEXT NOT NULL DEFAULT 'consolidated',
    frequency           TEXT NOT NULL DEFAULT 'yearly',
    operating_cf_cr     DOUBLE PRECISION,
    investing_cf_cr     DOUBLE PRECISION,
    financing_cf_cr     DOUBLE PRECISION,
    net_cf_cr           DOUBLE PRECISION,
    capital_expenditure_cr DOUBLE PRECISION,
    free_cash_flow_cr   DOUBLE PRECISION,
    period_end_date     TEXT,
    verification_status TEXT DEFAULT 'unverified',
    raw_data            TEXT,
    source              TEXT NOT NULL DEFAULT 'demo',
    fetched_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (isin, period, statement_type, frequency, source)
);

CREATE TABLE IF NOT EXISTS fundamental_ratios (
    symbol              TEXT NOT NULL,
    isin                TEXT NOT NULL,
    period              TEXT NOT NULL,
    statement_type      TEXT NOT NULL DEFAULT 'consolidated',
    frequency           TEXT NOT NULL DEFAULT 'yearly',
    pe_ratio            DOUBLE PRECISION,
    pb_ratio            DOUBLE PRECISION,
    ev_ebitda           DOUBLE PRECISION,
    roe_pct             DOUBLE PRECISION,
    roce_pct            DOUBLE PRECISION,
    debt_to_equity      DOUBLE PRECISION,
    interest_coverage   DOUBLE PRECISION,
    current_ratio       DOUBLE PRECISION,
    quick_ratio         DOUBLE PRECISION,
    operating_margin_pct DOUBLE PRECISION,
    net_profit_margin_pct DOUBLE PRECISION,
    asset_turnover      DOUBLE PRECISION,
    dividend_yield_pct  DOUBLE PRECISION,
    earnings_yield_pct  DOUBLE PRECISION,
    fcf_yield_pct       DOUBLE PRECISION,
    period_end_date     TEXT,
    provenance          TEXT DEFAULT 'unverified',
    source              TEXT NOT NULL DEFAULT 'demo',
    fetched_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (isin, period, statement_type, frequency, source)
);

CREATE TABLE IF NOT EXISTS fundamental_shareholdings (
    symbol              TEXT NOT NULL,
    isin                TEXT NOT NULL,
    period              TEXT NOT NULL,
    promoter_holding_pct DOUBLE PRECISION,
    fii_holding_pct     DOUBLE PRECISION,
    dii_holding_pct     DOUBLE PRECISION,
    public_holding_pct  DOUBLE PRECISION,
    others_holding_pct  DOUBLE PRECISION,
    pledged_promoter_pct DOUBLE PRECISION,
    source              TEXT NOT NULL DEFAULT 'demo',
    fetched_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (isin, period, source)
);

CREATE TABLE IF NOT EXISTS fundamental_corporate_actions (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    isin                TEXT,
    action_type         TEXT NOT NULL,
    announcement_date   TEXT,
    record_date         TEXT,
    ex_date             TEXT,
    details             TEXT,
    source              TEXT NOT NULL DEFAULT 'demo',
    fetched_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fundamental_competitors (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    isin                TEXT,
    competitor_symbol   TEXT NOT NULL,
    competitor_name     TEXT,
    peer_group          TEXT,
    source              TEXT NOT NULL DEFAULT 'demo',
    fetched_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fundamental_sync_history (
    id                  BIGSERIAL PRIMARY KEY,
    symbol              TEXT NOT NULL,
    isin                TEXT,
    sync_type           TEXT NOT NULL,
    status              TEXT NOT NULL,
    records_updated     INTEGER DEFAULT 0,
    source              TEXT NOT NULL,
    error_message       TEXT,
    synced_at           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- 4. User-Scoped Tables (Protected by Supabase Auth & RLS)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS custom_watchlists (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    description         TEXT,
    symbols_json        TEXT NOT NULL DEFAULT '[]',
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS market_alerts (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol              TEXT NOT NULL,
    alert_type          TEXT NOT NULL,
    target_value        DOUBLE PRECISION,
    timeframe           TEXT DEFAULT '1D',
    note                TEXT,
    status              TEXT DEFAULT 'ACTIVE',
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    last_triggered      TIMESTAMPTZ,
    trigger_count       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS market_alert_history (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    alert_id            BIGINT REFERENCES market_alerts(id) ON DELETE CASCADE,
    symbol              TEXT NOT NULL,
    alert_type          TEXT NOT NULL,
    condition           TEXT NOT NULL,
    triggered_value     TEXT NOT NULL,
    message             TEXT,
    timestamp           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS saved_screeners (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    description         TEXT,
    config_json         TEXT NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS saved_custom_scanners (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    description         TEXT,
    universe            TEXT DEFAULT 'all',
    timeframe           TEXT DEFAULT '1D',
    logic_mode          TEXT DEFAULT 'AND',
    conditions_json     TEXT NOT NULL,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS research_trade_plans (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol              TEXT NOT NULL,
    exchange            TEXT NOT NULL DEFAULT 'NSE',
    setup_type          TEXT NOT NULL,
    direction           TEXT NOT NULL DEFAULT 'BULLISH',
    timeframe           TEXT NOT NULL DEFAULT '1D',
    reference_price     DOUBLE PRECISION NOT NULL,
    entry_zone_json     TEXT NOT NULL DEFAULT '{}',
    stop_loss           DOUBLE PRECISION NOT NULL,
    target_1            DOUBLE PRECISION NOT NULL,
    target_2            DOUBLE PRECISION NOT NULL,
    risk_reward_ratio   DOUBLE PRECISION NOT NULL,
    setup_score         DOUBLE PRECISION NOT NULL,
    position_size_qty   INTEGER NOT NULL DEFAULT 0,
    position_value      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    account_capital     DOUBLE PRECISION NOT NULL DEFAULT 100000.0,
    risk_pct            DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    invalidation_condition TEXT NOT NULL,
    evidence_json       TEXT NOT NULL DEFAULT '[]',
    risks_json          TEXT NOT NULL DEFAULT '[]',
    status              TEXT NOT NULL DEFAULT 'MONITORING',
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS research_notes (
    id                  BIGSERIAL PRIMARY KEY,
    user_id             UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    symbol              TEXT NOT NULL,
    title               TEXT,
    note                TEXT NOT NULL,
    tags                TEXT,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- 5. Indexes for Query Performance
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_stocks_sector ON stocks(sector);
CREATE INDEX IF NOT EXISTS idx_ohlcv_sym_time ON ohlcv(symbol, interval, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trade_plans_user ON research_trade_plans(user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_research_notes_user ON research_notes(user_id, symbol);
CREATE INDEX IF NOT EXISTS idx_watchlists_user ON custom_watchlists(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_user ON market_alerts(user_id, status);
CREATE INDEX IF NOT EXISTS idx_alert_history_user ON market_alert_history(user_id, alert_id);

-- ---------------------------------------------------------------------------
-- 6. Row-Level Security (RLS) Configuration
-- ---------------------------------------------------------------------------

-- Enable RLS on User-Scoped Tables
ALTER TABLE custom_watchlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_alert_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_screeners ENABLE ROW LEVEL SECURITY;
ALTER TABLE saved_custom_scanners ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_trade_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_notes ENABLE ROW LEVEL SECURITY;

-- Enable RLS on Public Reference Data (Read-only for Authenticated Users, Full for Service Role)
ALTER TABLE stocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE ohlcv ENABLE ROW LEVEL SECURITY;
ALTER TABLE data_updates ENABLE ROW LEVEL SECURITY;
ALTER TABLE fundamental_company_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE fundamental_income_statements ENABLE ROW LEVEL SECURITY;
ALTER TABLE fundamental_balance_sheets ENABLE ROW LEVEL SECURITY;
ALTER TABLE fundamental_cash_flows ENABLE ROW LEVEL SECURITY;
ALTER TABLE fundamental_ratios ENABLE ROW LEVEL SECURITY;
ALTER TABLE fundamental_shareholdings ENABLE ROW LEVEL SECURITY;
ALTER TABLE fundamental_corporate_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE fundamental_competitors ENABLE ROW LEVEL SECURITY;
ALTER TABLE fundamental_sync_history ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Reference Data (Read-only for authenticated, full for service_role)
DO $$
BEGIN
    DROP POLICY IF EXISTS "Authenticated users can read stocks" ON stocks;
    CREATE POLICY "Authenticated users can read stocks" ON stocks FOR SELECT TO authenticated USING (true);

    DROP POLICY IF EXISTS "Authenticated users can read ohlcv" ON ohlcv;
    CREATE POLICY "Authenticated users can read ohlcv" ON ohlcv FOR SELECT TO authenticated USING (true);

    DROP POLICY IF EXISTS "Authenticated users can read fundamental profiles" ON fundamental_company_profiles;
    CREATE POLICY "Authenticated users can read fundamental profiles" ON fundamental_company_profiles FOR SELECT TO authenticated USING (true);

    DROP POLICY IF EXISTS "Authenticated users can read fundamental income" ON fundamental_income_statements;
    CREATE POLICY "Authenticated users can read fundamental income" ON fundamental_income_statements FOR SELECT TO authenticated USING (true);

    DROP POLICY IF EXISTS "Authenticated users can read fundamental balance" ON fundamental_balance_sheets;
    CREATE POLICY "Authenticated users can read fundamental balance" ON fundamental_balance_sheets FOR SELECT TO authenticated USING (true);

    DROP POLICY IF EXISTS "Authenticated users can read fundamental cashflow" ON fundamental_cash_flows;
    CREATE POLICY "Authenticated users can read fundamental cashflow" ON fundamental_cash_flows FOR SELECT TO authenticated USING (true);

    DROP POLICY IF EXISTS "Authenticated users can read fundamental ratios" ON fundamental_ratios;
    CREATE POLICY "Authenticated users can read fundamental ratios" ON fundamental_ratios FOR SELECT TO authenticated USING (true);

    DROP POLICY IF EXISTS "Authenticated users can read fundamental shareholdings" ON fundamental_shareholdings;
    CREATE POLICY "Authenticated users can read fundamental shareholdings" ON fundamental_shareholdings FOR SELECT TO authenticated USING (true);
END $$;

-- RLS Policies: User-Scoped Records (Isolated to auth.uid())
DO $$
BEGIN
    -- 1. Research Trade Plans
    DROP POLICY IF EXISTS "Users can view own trade plans" ON research_trade_plans;
    CREATE POLICY "Users can view own trade plans" ON research_trade_plans FOR SELECT TO authenticated
    USING (auth.uid() = user_id OR user_id IS NULL);

    DROP POLICY IF EXISTS "Users can insert own trade plans" ON research_trade_plans;
    CREATE POLICY "Users can insert own trade plans" ON research_trade_plans FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = user_id);

    DROP POLICY IF EXISTS "Users can update own trade plans" ON research_trade_plans;
    CREATE POLICY "Users can update own trade plans" ON research_trade_plans FOR UPDATE TO authenticated
    USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

    DROP POLICY IF EXISTS "Users can delete own trade plans" ON research_trade_plans;
    CREATE POLICY "Users can delete own trade plans" ON research_trade_plans FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

    -- 2. Research Notes
    DROP POLICY IF EXISTS "Users can view own research notes" ON research_notes;
    CREATE POLICY "Users can view own research notes" ON research_notes FOR SELECT TO authenticated
    USING (auth.uid() = user_id OR user_id IS NULL);

    DROP POLICY IF EXISTS "Users can insert own research notes" ON research_notes;
    CREATE POLICY "Users can insert own research notes" ON research_notes FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = user_id);

    DROP POLICY IF EXISTS "Users can update own research notes" ON research_notes;
    CREATE POLICY "Users can update own research notes" ON research_notes FOR UPDATE TO authenticated
    USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

    DROP POLICY IF EXISTS "Users can delete own research notes" ON research_notes;
    CREATE POLICY "Users can delete own research notes" ON research_notes FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

    -- 3. Custom Watchlists
    DROP POLICY IF EXISTS "Users can view own watchlists" ON custom_watchlists;
    CREATE POLICY "Users can view own watchlists" ON custom_watchlists FOR SELECT TO authenticated
    USING (auth.uid() = user_id OR user_id IS NULL);

    DROP POLICY IF EXISTS "Users can insert own watchlists" ON custom_watchlists;
    CREATE POLICY "Users can insert own watchlists" ON custom_watchlists FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = user_id);

    DROP POLICY IF EXISTS "Users can update own watchlists" ON custom_watchlists;
    CREATE POLICY "Users can update own watchlists" ON custom_watchlists FOR UPDATE TO authenticated
    USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

    DROP POLICY IF EXISTS "Users can delete own watchlists" ON custom_watchlists;
    CREATE POLICY "Users can delete own watchlists" ON custom_watchlists FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

    -- 4. Market Alerts
    DROP POLICY IF EXISTS "Users can view own alerts" ON market_alerts;
    CREATE POLICY "Users can view own alerts" ON market_alerts FOR SELECT TO authenticated
    USING (auth.uid() = user_id OR user_id IS NULL);

    DROP POLICY IF EXISTS "Users can insert own alerts" ON market_alerts;
    CREATE POLICY "Users can insert own alerts" ON market_alerts FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = user_id);

    DROP POLICY IF EXISTS "Users can update own alerts" ON market_alerts;
    CREATE POLICY "Users can update own alerts" ON market_alerts FOR UPDATE TO authenticated
    USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

    DROP POLICY IF EXISTS "Users can delete own alerts" ON market_alerts;
    CREATE POLICY "Users can delete own alerts" ON market_alerts FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

    -- 5. Market Alert History
    DROP POLICY IF EXISTS "Users can view own alert history" ON market_alert_history;
    CREATE POLICY "Users can view own alert history" ON market_alert_history FOR SELECT TO authenticated
    USING (auth.uid() = user_id OR user_id IS NULL);

    DROP POLICY IF EXISTS "Users can insert own alert history" ON market_alert_history;
    CREATE POLICY "Users can insert own alert history" ON market_alert_history FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = user_id);

    -- 6. Saved Scanners
    DROP POLICY IF EXISTS "Users can view own saved scanners" ON saved_custom_scanners;
    CREATE POLICY "Users can view own saved scanners" ON saved_custom_scanners FOR SELECT TO authenticated
    USING (auth.uid() = user_id OR user_id IS NULL);

    DROP POLICY IF EXISTS "Users can insert own saved scanners" ON saved_custom_scanners;
    CREATE POLICY "Users can insert own saved scanners" ON saved_custom_scanners FOR INSERT TO authenticated
    WITH CHECK (auth.uid() = user_id);

    DROP POLICY IF EXISTS "Users can update own saved scanners" ON saved_custom_scanners;
    CREATE POLICY "Users can update own saved scanners" ON saved_custom_scanners FOR UPDATE TO authenticated
    USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

    DROP POLICY IF EXISTS "Users can delete own saved scanners" ON saved_custom_scanners;
    CREATE POLICY "Users can delete own saved scanners" ON saved_custom_scanners FOR DELETE TO authenticated
    USING (auth.uid() = user_id);
END $$;

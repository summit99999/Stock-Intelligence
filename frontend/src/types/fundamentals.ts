/** TypeScript interfaces for Fundamental Analysis, Quality Scoring, and Company Research. */

export interface GrowthRatios {
  revenue_cagr_3y?: number | null;
  revenue_cagr_5y?: number | null;
  ebitda_cagr_3y?: number | null;
  pat_cagr_3y?: number | null;
  pat_cagr_5y?: number | null;
  eps_cagr_3y?: number | null;
  quarterly_rev_growth_yoy?: number | null;
  quarterly_pat_growth_yoy?: number | null;
  cagr_warnings: string[];
}

export interface ProfitabilityRatios {
  roe?: number | null;
  roce?: number | null;
  roa?: number | null;
  ebitda_margin_pct?: number | null;
  operating_margin_pct?: number | null;
  net_profit_margin_pct?: number | null;
}

export interface FinancialHealthRatios {
  debt_equity?: number | null;
  interest_coverage?: number | null;
  is_debt_free: boolean;
  current_ratio?: number | null;
  cfo_pat_ratio?: number | null;
  free_cash_flow_cr?: number | null;
  cash_conversion_ratio?: number | null;
}

export interface ValuationRatios {
  pe?: number | null;
  pb?: number | null;
  peg?: number | null;
  ev_ebitda?: number | null;
  dividend_yield?: number | null;
  market_price?: number | null;
  price_date?: string | null;
  price_source: string;
  is_loss_making: boolean;
  is_price_stale: boolean;
}

export interface CalculatedRatiosResult {
  symbol: string;
  statement_type: string;
  reporting_period: string;
  data_coverage_pct: number;
  confidence: string;
  growth: GrowthRatios;
  profitability: ProfitabilityRatios;
  financial_health: FinancialHealthRatios;
  valuation: ValuationRatios;
}

export interface CategoryScore {
  category: string;
  points_awarded: number;
  max_points: number;
  percentage: number;
  description: string;
}

export interface DeductionDetail {
  category: string;
  metric: string;
  points_lost: number;
  reason: string;
}

export interface QualityScoreResult {
  symbol: string;
  total_score?: number | null;
  grade: string;
  data_coverage_pct: number;
  confidence: string;
  category_scores: Record<string, CategoryScore>;
  deductions: DeductionDetail[];
  summary_verdict: string;
  reporting_period: string;
}

export interface PeerMetricRow {
  metric_key: string;
  label: string;
  unit: string;
  values: Record<string, number | null>;
  best_symbol?: string | null;
  higher_is_better: boolean;
}

export interface PeerCompanySummary {
  symbol: string;
  company_name: string;
  sector?: string | null;
  industry?: string | null;
  market_cap_cr?: number | null;
  current_price?: number | null;
  quality_score?: number | null;
  quality_grade: string;
  statement_type: string;
  reporting_period: string;
  data_provenance: string;
}

export interface PeerComparisonResponse {
  symbols: string[];
  target_symbol: string;
  sector?: string | null;
  statement_type: string;
  reporting_period: string;
  companies: PeerCompanySummary[];
  metrics: PeerMetricRow[];
  data_notes: string[];
}

export interface IncomeStatement {
  symbol: string;
  isin: string;
  period: string;
  statement_type: string;
  frequency: string;
  revenue_from_operations_cr?: number | null;
  total_expenses_cr?: number | null;
  ebitda_cr?: number | null;
  other_income_cr?: number | null;
  finance_costs_cr?: number | null;
  depreciation_cr?: number | null;
  profit_before_tax_cr?: number | null;
  tax_expense_cr?: number | null;
  net_profit_cr?: number | null;
  eps?: number | null;
  opm_pct?: number | null;
  npm_pct?: number | null;
  period_end_date?: string | null;
  verification_status: string;
  source: string;
  fetched_at?: string | null;
}

export interface BalanceSheet {
  symbol: string;
  isin: string;
  period: string;
  statement_type: string;
  frequency: string;
  total_assets_cr?: number | null;
  total_equity_cr?: number | null;
  share_capital_cr?: number | null;
  reserves_cr?: number | null;
  total_debt_cr?: number | null;
  borrowings_cr?: number | null;
  cash_and_equivalents_cr?: number | null;
  book_value_per_share?: number | null;
  period_end_date?: string | null;
  verification_status: string;
  source: string;
}

export interface CashFlow {
  symbol: string;
  isin: string;
  period: string;
  statement_type: string;
  frequency: string;
  operating_cash_flow_cr?: number | null;
  investing_cash_flow_cr?: number | null;
  financing_cash_flow_cr?: number | null;
  net_cash_flow_cr?: number | null;
  capex_cr?: number | null;
  free_cash_flow_cr?: number | null;
  period_end_date?: string | null;
  verification_status: string;
  source: string;
}

export interface ShareholdingPattern {
  symbol: string;
  isin: string;
  period: string;
  promoter_holding?: number | null;
  promoter_pledging?: number | null;
  fii_holding?: number | null;
  dii_holding?: number | null;
  public_holding?: number | null;
  government_holding?: number | null;
  period_end_date?: string | null;
  verification_status: string;
}

export interface CompanyResearchDossier {
  symbol: string;
  company_name: string;
  sector?: string | null;
  industry?: string | null;
  isin?: string | null;
  market_cap_cr?: number | null;
  current_price?: number | null;
  close?: number | null;
  daily_change_pct?: number | null;
  week_52_high?: number | null;
  week_52_low?: number | null;
  profile?: Record<string, any> | null;
  annual_income_statements: IncomeStatement[];
  quarterly_income_statements: IncomeStatement[];
  balance_sheets: BalanceSheet[];
  cash_flows: CashFlow[];
  shareholding: ShareholdingPattern[];
  stored_ratios: any[];
  calculated_ratios?: CalculatedRatiosResult | null;
  quality_score?: QualityScoreResult | null;
  peers?: PeerComparisonResponse | null;
  corporate_actions: any[];
  competitors: any[];
  provenance: {
    primary_source: string;
    verification_status: string;
    is_price_stale: boolean;
    price_date?: string | null;
    statement_count: number;
  };
}

export interface ScreenerCsvImportResponse {
  status: string;
  rows_imported: number;
  rows_skipped: number;
  unmapped_symbols: string[];
  errors: string[];
  warnings: string[];
  overwrite_verified: boolean;
}

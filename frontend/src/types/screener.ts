/** Types for the Stock Screener module. */

export type Operator = ">" | ">=" | "<" | "<=" | "==" | "!=" | "between";
export type LogicOp = "AND" | "OR";
export type SortOrder = "asc" | "desc";

export interface FilterCondition {
  id: string;  // client-side unique key
  field: string;
  operator: Operator;
  value: number;
  value2?: number;  // for "between"
}

export interface ConditionGroup {
  id: string;  // client-side unique key
  logic: LogicOp;
  conditions: FilterCondition[];
}

export interface ScreenRequest {
  // Universe
  exchange?: string;
  sector?: string;
  cap_category?: string;
  search?: string;

  // Simple filters
  min_market_cap_cr?: number;
  max_market_cap_cr?: number;
  min_price?: number;
  max_price?: number;
  min_pe?: number;
  max_pe?: number;
  min_pb?: number;
  max_pb?: number;
  min_roe?: number;
  max_roe?: number;
  min_roce?: number;
  max_roce?: number;
  min_debt_equity?: number;
  max_debt_equity?: number;
  min_revenue_growth?: number;
  max_revenue_growth?: number;
  min_profit_growth?: number;
  max_profit_growth?: number;
  min_opm?: number;
  max_opm?: number;
  min_promoter_holding?: number;
  max_promoter_pledging?: number;
  min_fii_holding?: number;
  min_dii_holding?: number;
  min_rsi?: number;
  max_rsi?: number;
  min_adx?: number;
  min_relative_volume?: number;
  max_relative_volume?: number;
  min_return_1m?: number;
  max_return_1m?: number;
  min_return_3m?: number;
  max_return_3m?: number;
  min_return_1y?: number;
  max_return_1y?: number;

  // Advanced
  condition_groups?: ConditionGroup[];

  // Pagination
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_order?: SortOrder;
}

export interface StockResult {
  symbol: string;
  company_name: string;
  exchange: string;
  sector?: string;
  industry?: string;
  cap_category?: string;
  close?: number;
  daily_change_pct?: number;
  market_cap_cr?: number;
  pe?: number;
  pb?: number;
  roe?: number;
  roce?: number;
  debt_equity?: number;
  revenue_growth_pct?: number;
  profit_growth_pct?: number;
  opm_pct?: number;
  rsi?: number;
  relative_volume?: number;
  return_1m_pct?: number;
  return_3m_pct?: number;
  return_1y_pct?: number;
  promoter_holding?: number;
  fii_holding?: number;
  dii_holding?: number;
  volume?: number;
}

export interface ScreenResponse {
  items: StockResult[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  data_mode: string;
  notice: string;
}

export interface FilterFieldDef {
  field: string;
  label: string;
  type: string;
}

export interface ScreenerMetadata {
  sectors: string[];
  exchanges: string[];
  cap_categories: string[];
  filter_fields: {
    fundamental: FilterFieldDef[];
    technical: FilterFieldDef[];
  };
}

export interface SavedScreener {
  id: number;
  name: string;
  description: string;
  config_json: string;
  created_at?: string;
  updated_at?: string;
}

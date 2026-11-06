/**
 * Market Movers & Price-Volume Confluence API Service (Phase 14 & Phase 14.1).
 */

import { apiJson } from "./client";

export interface StockMoverItem {
  symbol: string;
  company_name: string;
  sector: string;
  // Price & LTP Correctness
  ltp?: number | null;
  ltp_available?: boolean;
  latest_completed_close: number;
  previous_completed_close: number;
  intraday_change_pct?: number | null;
  completed_session_change_pct: number;
  // Backward-compatible price fields
  close: number;
  previous_close: number;
  daily_change_pct: number;
  // Volume & ADV
  today_volume: number;
  volume_formatted: string;
  adv_20: number;
  adv_20_formatted: string;
  // Differentiated RVOL Metrics
  daily_rvol: number;
  daily_rvol_status: "PROVISIONAL" | "COMPLETED";
  daily_rvol_is_provisional?: boolean;
  daily_rvol_note?: string;
  time_of_day_rvol?: number | null;
  time_of_day_rvol_status: string;
  time_of_day_rvol_reason?: string | null;
  tod_valid_sessions?: number;
  tod_source?: "OBSERVED_HISTORICAL" | "OBSERVED_DELAYED" | "OBSERVED_LIVE" | "SYNTHETIC" | "UNAVAILABLE" | string;
  tod_data_quality?: string;
  tod_rvol_status?: string;
  linear_estimated_intraday_rvol?: number | null;
  linear_estimated_intraday_rvol_status?: string;
  active_rvol_mode?: "daily" | "tod" | string;
  active_rvol?: number | null;
  // Turnover
  traded_value: number;
  traded_value_cr: number;
  turnover_formatted: string;
  turnover_status: "ACTUAL_TURNOVER" | "ESTIMATED_TURNOVER" | "UNAVAILABLE" | string;
  turnover_note?: string;
  // Provenance & Freshness
  data_source: string;
  source_timestamp: string;
  retrieval_timestamp: string;
  data_mode: "LIVE" | "DELAYED" | "HISTORICAL" | "PROVISIONAL" | "STALE" | "ESTIMATED" | "UNAVAILABLE" | string;
  data_quality_status: string;
  is_stale?: boolean;
  stale_reason?: string | null;
  last_updated_time: string;
  rank?: number;
}

export interface ConfluenceStockItem extends StockMoverItem {
  rank_in_gainers?: number;
  rank_in_losers?: number;
  rank_in_volume_gainers: number;
  confluence_type: "BULLISH" | "BEARISH";
  heuristic_compound_score: number;
  compound_score: number; // backward compatibility
  score_label?: string;
  score_nature?: string;
  is_in_displayed_gainers?: boolean;
  is_in_displayed_losers?: boolean;
  is_in_displayed_volume?: boolean;
  interpretation: string;
}

export interface UniverseCoverageAudit {
  universe_name: string;
  universe_label: string;
  requested_universe_size: number;
  tracked_symbols_count: number;
  tracked_symbols?: string[];
  missing_symbols_count: number;
  missing_symbols_sample?: string[];
  coverage_pct: number;
  is_full_coverage: boolean;
  coverage_disclosure: string;
  total_database_equities: number;
}

export interface MarketMoversOverviewResponse {
  status: string;
  snapshot_id: string;
  snapshot_timestamp: string;
  calculation_snapshot_id?: string;
  calculation_timestamp?: string;
  active_rvol_mode?: "daily" | "tod" | string;
  rvol_methodology_label?: string;
  universe: string;
  universe_label: string;
  exchange: string;
  coverage?: UniverseCoverageAudit;
  configured_universe_count: number;
  scanned_count: number;
  total_database_count: number;
  coverage_pct: number;
  coverage_note: string;
  filters_applied: {
    universe: string;
    exchange: string;
    rvol_mode?: string;
    min_rvol: number;
    min_price_change_pct: number;
    min_traded_value_cr: number;
    limit: number;
    exclude_stale?: boolean;
    is_session_open?: boolean | null;
  };
  metadata: {
    provider: string;
    instrument: string;
    timeframe: string;
    data_mode: string;
    last_updated?: string;
    snapshot_id: string;
    snapshot_timestamp: string;
    calculation_snapshot_id?: string;
    calculation_timestamp?: string;
    underlying_market_data?: {
      earliest_source_timestamp?: string;
      latest_source_timestamp?: string;
      distinct_source_timestamps_count?: number;
      is_time_synchronized?: boolean;
      synchronization_disclosure?: string;
    };
    freshness_summary?: {
      total_evaluated: number;
      live_records_count: number;
      historical_records_count: number;
      provisional_records_count: number;
      stale_records_count: number;
    };
    disclaimer: string;
  };
  top_gainers: StockMoverItem[];
  top_losers: StockMoverItem[];
  volume_gainers: StockMoverItem[];
  high_volume_losers: StockMoverItem[];
  bullish_confluence: ConfluenceStockItem[];
  bearish_confluence: ConfluenceStockItem[];
  summary_counts: {
    total_evaluated: number;
    gainers_count: number;
    losers_count: number;
    volume_gainers_count: number;
    high_volume_losers_count: number;
    bullish_confluence_count: number;
    bearish_confluence_count: number;
    stale_records_count?: number;
  };
}

export interface MarketMoversFilters {
  universe?: string;
  exchange?: string;
  rvol_mode?: "daily" | "tod";
  min_rvol?: number;
  min_price_change_pct?: number;
  min_traded_value_cr?: number;
  limit?: number;
  force_refresh?: boolean;
  exclude_stale?: boolean;
  is_session_open?: boolean | null;
  allow_synthetic?: boolean;
}

/**
 * Fetch unified market movers and price-volume confluence intelligence.
 */
export async function fetchMarketMoversOverview(
  filters: MarketMoversFilters = {}
): Promise<MarketMoversOverviewResponse> {
  const params = new URLSearchParams();
  if (filters.universe) params.set("universe", filters.universe);
  if (filters.exchange) params.set("exchange", filters.exchange);
  if (filters.rvol_mode) params.set("rvol_mode", filters.rvol_mode);
  if (filters.min_rvol !== undefined) params.set("min_rvol", String(filters.min_rvol));
  if (filters.min_price_change_pct !== undefined) {
    params.set("min_price_change_pct", String(filters.min_price_change_pct));
  }
  if (filters.min_traded_value_cr !== undefined) {
    params.set("min_traded_value_cr", String(filters.min_traded_value_cr));
  }
  if (filters.limit !== undefined) params.set("limit", String(filters.limit));
  if (filters.force_refresh) params.set("force_refresh", "true");
  if (filters.exclude_stale) params.set("exclude_stale", "true");
  if (filters.is_session_open !== undefined && filters.is_session_open !== null) {
    params.set("is_session_open", String(filters.is_session_open));
  }
  if (filters.allow_synthetic) {
    params.set("allow_synthetic", "true");
  }

  const query = params.toString();
  const endpoint = `/api/market-movers/overview${query ? `?${query}` : ""}`;
  return apiJson<MarketMoversOverviewResponse>(endpoint);
}

/**
 * Fetch 5-minute historical bar ingestion status across all tracked stocks.
 */
export async function fetchIntradayIngestionStatus(allow_synthetic: boolean = false): Promise<any> {
  return apiJson<any>(`/api/market-movers/intraday/status${allow_synthetic ? "?allow_synthetic=true" : ""}`);
}

/**
 * Seed 5-minute historical bars for all tracked stocks.
 */
export async function seedIntradayBars(sessions: number = 20, force: boolean = false): Promise<any> {
  return apiJson<any>(`/api/market-movers/intraday/seed?sessions=${sessions}&force=${force ? "true" : "false"}`, {
    method: "POST",
  });
}

/**
 * Evaluate configured intraday data providers.
 */
export async function fetchIntradayProviders(): Promise<any> {
  return apiJson<any>("/api/market-movers/intraday/providers");
}

export async function fetchIntradayIngestionRuns(limit: number = 50): Promise<any> {
  return apiJson<any>(`/api/market-movers/intraday/ingestions?limit=${limit}`);
}

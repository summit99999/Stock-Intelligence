import React, { useState, useEffect, useMemo } from "react";
import { LiveQuote } from "../api/marketFeed";

interface StockVolumeItem {
  rank?: number;
  symbol: string;
  company_name: string;
  sector: string;
  close: number;
  daily_change_pct: number;
  today_volume: number;
  adv_10: number;
  adv_20: number;
  adv_50: number;
  volume_change_pct: number;
  daily_rvol: number;
  intraday_rvol: number;
  intraday_rvol_method?: string;
  intraday_rvol_status?: string;
  historical_time_of_day_rvol?: number | null;
  linear_estimated_intraday_rvol?: number;
  intraday_rvol_explanation?: string;
  rvol_time_label: string;
  session_fraction: number;
  traded_value: number;
  traded_value_cr: number;
  traded_value_status?: string;
  turnover_type?: string;
  turnover_explanation?: string;
  close_location_buying_bias_pct?: number;
  close_location_selling_bias_pct?: number;
  money_flow_multiplier?: number;
  chaikin_money_flow_20?: number;
  close_location_explanation?: string;
  chaikin_money_flow_explanation?: string;
  buying_pressure_pct: number; // backward-compatible alias
  selling_pressure_pct: number; // backward-compatible alias
  cmf_20: number;
  price_volume_divergence: string;
  divergence_note: string;
  money_flow_classification: string;
  money_flow_note: string;
  institutional_flow?: {
    status: string;
    classification: string;
    provider?: string;
    disclosure?: string;
  };
  delivery_pct?: number | null;
  delivery_status: string;
  last_updated: string;
}

interface SectorFlowItem {
  sector: string;
  stock_count: number;
  average_change_pct: number;
  average_rvol: number;
  total_traded_value_cr: number;
  average_close_location_buying_bias?: number;
  average_close_location_selling_bias?: number;
  average_buying_pressure: number;
  average_selling_pressure: number;
  net_flow_bias: string;
  relative_strength_vs_market: number;
  rotation_quadrant: string;
  strongest_stock: string;
  strongest_change: number;
  weakest_stock: string;
  weakest_change: number;
}

interface MoneyFlowDashboardPayload {
  timestamp: string;
  universe: string;
  metadata: {
    provider: string;
    instrument: string;
    exchange: string;
    timeframe: string;
    data_mode: string;
    last_update_timestamp: string;
    is_stale: boolean;
    turnover_status?: string;
    institutional_flow_status?: string;
    disclaimer: string;
  };
  market_overview: {
    advances: number;
    declines: number;
    unchanged: number;
    advance_decline_ratio: number;
    breadth_pct: number;
    total_traded_value_cr: number;
    average_market_change: number;
    scanned_count: number;
    configured_universe_count: number;
    universe_label: string;
    coverage_pct: number;
  };
  money_flow_summary: {
    market_buying_pressure_pct: number;
    market_selling_pressure_pct: number;
    market_close_location_buying_bias_pct?: number;
    market_close_location_selling_bias_pct?: number;
    net_flow_bias: string;
    narrative: string;
    total_traded_value_cr: number;
    volume_expansion_count: number;
    volume_contraction_count: number;
    session_fraction: number;
    rvol_time_label: string;
    is_market_open: boolean;
    institutional_flow?: {
      status: string;
      classification: string;
      provider?: string;
      disclosure?: string;
    };
  };
  institutional_flow?: {
    status: string;
    classification: string;
    provider?: string;
    disclosure?: string;
  };
  volume_gainers: StockVolumeItem[];
  price_gainers: StockVolumeItem[];
  price_losers: StockVolumeItem[];
  combined_categories: {
    high_volume_price_gainers: StockVolumeItem[];
    high_volume_price_losers: StockVolumeItem[];
    high_volume_sideways: StockVolumeItem[];
    low_volume_breakouts: StockVolumeItem[];
  };
  sector_money_flow: SectorFlowItem[];
}

interface MoneyFlowIntelligenceViewProps {
  onSelectStock: (symbol: string, page?: string) => void;
  liveQuotes?: Record<string, LiveQuote>;
  initialSymbol?: string;
}

export default function MoneyFlowIntelligenceView({
  onSelectStock,
  liveQuotes = {},
  initialSymbol = "RELIANCE",
}: MoneyFlowIntelligenceViewProps) {
  const [universe, setUniverse] = useState<string>("all");
  const [data, setData] = useState<MoneyFlowDashboardPayload | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [minTradedValueCr, setMinTradedValueCr] = useState<string>("0");
  const [minVolumeK, setMinVolumeK] = useState<string>("0");
  const [searchQuery, setSearchQuery] = useState<string>("" );

  // Price Gainers vs Losers Toggle
  const [priceGainerTab, setPriceGainerTab] = useState<"gainers" | "losers">("gainers");

  // Selected stock for deep-dive Stock-Level Analysis
  const [selectedStock, setSelectedStock] = useState<string>(initialSymbol);
  const [selectedStockDetail, setSelectedStockDetail] = useState<StockVolumeItem | null>(null);
  const [stockDetailLoading, setStockDetailLoading] = useState<boolean>(false);

  const fetchDashboard = async (force: boolean = false) => {
    setLoading(true);
    setError(null);
    try {
      const minVal = parseFloat(minTradedValueCr) || 0;
      const minVol = (parseFloat(minVolumeK) || 0) * 1000;
      const res = await fetch(
        `http://127.0.0.1:8000/api/money-flow/overview?universe=${universe}&force_refresh=${force}&min_traded_value_cr=${minVal}&min_volume=${minVol}`
      );
      if (!res.ok) {
        throw new Error(`Failed to load money flow dashboard: HTTP ${res.status}`);
      }
      const json: MoneyFlowDashboardPayload = await res.json();
      setData(json);

      // Auto-select initial stock detail if not already loaded
      if (json.volume_gainers && json.volume_gainers.length > 0) {
        const found = json.volume_gainers.find((s) => s.symbol === selectedStock) || json.volume_gainers[0];
        setSelectedStock(found.symbol);
        setSelectedStockDetail(found);
      }
    } catch (err: any) {
      console.error("Error fetching money flow overview:", err);
      setError(err.message || "Failed to connect to money flow API.");
    } finally {
      setLoading(false);
    }
  };

  const fetchStockDetail = async (symbol: string) => {
    setStockDetailLoading(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/money-flow/stock/${symbol}`);
      if (res.ok) {
        const json = await res.json();
        setSelectedStockDetail(json.analysis);
      }
    } catch (err) {
      console.error(`Error loading stock detail for ${symbol}:`, err);
    } finally {
      setStockDetailLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboard(false);
  }, [universe]);

  useEffect(() => {
    if (selectedStock) {
      fetchStockDetail(selectedStock);
    }
  }, [selectedStock]);

  const handleRowClick = (symbol: string) => {
    setSelectedStock(symbol);
    // Smooth scroll down to section 8
    const elem = document.getElementById("stock-deep-dive-section");
    if (elem) {
      elem.scrollIntoView({ behavior: "smooth" });
    }
  };

  const formatVol = (v: number) => {
    if (!v) return "0";
    if (v >= 10000000) return `${(v / 10000000).toFixed(2)} Cr`;
    if (v >= 100000) return `${(v / 100000).toFixed(2)} L`;
    if (v >= 1000) return `${(v / 1000).toFixed(1)} K`;
    return v.toLocaleString();
  };

  return (
    <div style={{ padding: "20px 24px", color: "#e2e8f0", display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Header & Controls */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: "16px",
          borderBottom: "1px solid #1e2c40",
          paddingBottom: "16px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h2 style={{ margin: 0, fontSize: "22px", fontWeight: 800, color: "#f8fafc", letterSpacing: "-0.02em" }}>
              Money Flow & Daily Volume Intelligence
            </h2>
            <span
              style={{
                fontSize: "11px",
                fontWeight: 700,
                padding: "2px 8px",
                borderRadius: "4px",
                background: "rgba(56, 189, 248, 0.15)",
                color: "#38bdf8",
                border: "1px solid rgba(56, 189, 248, 0.3)",
              }}
            >
              PHASE 11.2 AUDITED
            </span>
          </div>
          <p style={{ margin: "6px 0 0", color: "#8c9bb0", fontSize: "13px" }}>
            Dual-method relative volume (RVOL), candle close-location price bias & qualified price-volume classification.
          </p>
        </div>

        {/* Universe Selector & Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          <div style={{ display: "flex", background: "#0a0f18", borderRadius: "8px", padding: "3px", border: "1px solid #1e2c40" }}>
            {[
              { id: "all", label: "All Stocks" },
              { id: "nifty50", label: "NIFTY 50" },
              { id: "nifty100", label: "NIFTY 100" },
              { id: "nifty500", label: "NIFTY 500" },
              { id: "fno", label: "F&O" },
            ].map((u) => (
              <button
                key={u.id}
                onClick={() => setUniverse(u.id)}
                style={{
                  background: universe === u.id ? "#2563eb" : "transparent",
                  color: universe === u.id ? "#fff" : "#8c9bb0",
                  border: "none",
                  padding: "6px 12px",
                  borderRadius: "6px",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {u.label}
              </button>
            ))}
          </div>

          <button
            onClick={() => fetchDashboard(true)}
            disabled={loading}
            style={{
              background: "#1e2c40",
              color: "#38bdf8",
              border: "1px solid #334155",
              padding: "7px 14px",
              borderRadius: "8px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {loading ? "Refreshing..." : "⟳ Refresh"}
          </button>
        </div>
      </div>

      {/* Transparent Disclaimer Banner */}
      <div
        style={{
          background: "#0d1520",
          border: "1px solid #1b2636",
          borderRadius: "6px",
          padding: "10px 16px",
          fontSize: "11px",
          color: "#94a3b8",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        <div>
          <strong style={{ color: "#38bdf8" }}>Data Integrity Note:</strong>{" "}
          {data?.metadata?.disclaimer ||
            "Volume represents total two-sided executed turnover. Candle close-location bias is an OHLCV-derived estimate, not actual buyer/seller order tape. Institutional daily flow is UNAVAILABLE without exchange-sourced settlement reports."}
        </div>
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <span>Updated: {data?.timestamp}</span>
          <span>|</span>
          <span>Coverage: {data?.market_overview?.coverage_pct}%</span>
        </div>
      </div>

      {/* =====================================================================
          SECTION 1: MARKET OVERVIEW
          ===================================================================== */}
      {data && (
        <div
          style={{
            background: "#111925",
            border: "1px solid #202d40",
            borderRadius: "10px",
            padding: "18px 22px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
            <h3 style={{ margin: 0, fontSize: "14px", color: "#f1f5f9", fontWeight: 700, textTransform: "uppercase" }}>
              1. Market Overview & Liquidity Pulse
            </h3>
            <span style={{ fontSize: "12px", color: "#38bdf8", fontWeight: 600 }}>
              Universe: {data.market_overview.universe_label} ({data.market_overview.scanned_count} Tracked)
            </span>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "14px" }}>
            <div style={{ background: "#0a0f18", border: "1px solid #1e2c40", borderRadius: "8px", padding: "12px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "10px", color: "#8c9bb0", textTransform: "uppercase", fontWeight: 700 }}>Total Traded Value</span>
                <span
                  style={{
                    fontSize: "9px",
                    fontWeight: 700,
                    padding: "1px 5px",
                    borderRadius: "3px",
                    background: "rgba(245,158,11,0.15)",
                    color: "#f59e0b",
                  }}
                  title="Estimated turnover calculated as executed volume × LTP"
                >
                  ESTIMATED
                </span>
              </div>
              <div style={{ fontSize: "20px", fontWeight: 800, color: "#fff", marginTop: "4px" }}>
                ₹{data.market_overview.total_traded_value_cr.toLocaleString()} Cr
              </div>
              <div style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>Cumulative Universe Turnover</div>
            </div>

            <div style={{ background: "#0a0f18", border: "1px solid #1e2c40", borderRadius: "8px", padding: "12px" }}>
              <div style={{ fontSize: "10px", color: "#8c9bb0", textTransform: "uppercase", fontWeight: 700 }}>Market Advances / Declines</div>
              <div style={{ fontSize: "16px", fontWeight: 800, marginTop: "4px" }}>
                <span style={{ color: "#26c78b" }}>▲ {data.market_overview.advances}</span> /{" "}
                <span style={{ color: "#ef6676" }}>▼ {data.market_overview.declines}</span>
              </div>
              <div style={{ fontSize: "10px", color: "#38bdf8", marginTop: "2px" }}>
                A/D Ratio: {data.market_overview.advance_decline_ratio}:1 ({data.market_overview.breadth_pct}% Advancing)
              </div>
            </div>

            <div style={{ background: "#0a0f18", border: "1px solid #1e2c40", borderRadius: "8px", padding: "12px" }}>
              <div style={{ fontSize: "10px", color: "#8c9bb0", textTransform: "uppercase", fontWeight: 700 }}>Average Market Move</div>
              <div style={{ fontSize: "20px", fontWeight: 800, color: data.market_overview.average_market_change >= 0 ? "#26c78b" : "#ef6676", marginTop: "4px" }}>
                {data.market_overview.average_market_change >= 0 ? "+" : ""}{data.market_overview.average_market_change}%
              </div>
              <div style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>Equal-Weighted Universe Mean</div>
            </div>

            <div style={{ background: "#0a0f18", border: "1px solid #1e2c40", borderRadius: "8px", padding: "12px" }}>
              <div style={{ fontSize: "10px", color: "#8c9bb0", textTransform: "uppercase", fontWeight: 700 }}>Volume Expansion vs Contraction</div>
              <div style={{ fontSize: "16px", fontWeight: 800, marginTop: "4px" }}>
                <span style={{ color: "#38bdf8" }}>{data.money_flow_summary.volume_expansion_count} Surge</span> /{" "}
                <span style={{ color: "#94a3b8" }}>{data.money_flow_summary.volume_contraction_count} Dry</span>
              </div>
              <div style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>RVOL &ge; 1.4x vs &le; 0.8x</div>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          SECTION 2: MONEY FLOW SUMMARY (QUALIFIED TERMINOLOGY)
          ===================================================================== */}
      {data && (
        <div
          style={{
            background: "#111925",
            border: "1px solid #202d40",
            borderRadius: "10px",
            padding: "18px 22px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", flexWrap: "wrap", gap: "8px" }}>
            <h3 style={{ margin: 0, fontSize: "14px", color: "#f1f5f9", fontWeight: 700, textTransform: "uppercase" }}>
              2. Money Flow Summary & Close-Location Price Bias
            </h3>
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <span
                style={{
                  fontSize: "10px",
                  fontWeight: 700,
                  padding: "2px 8px",
                  borderRadius: "4px",
                  background: "rgba(148, 163, 184, 0.15)",
                  color: "#94a3b8",
                  border: "1px solid rgba(148, 163, 184, 0.3)",
                }}
                title="Institutional daily FII/DII net cash flow is UNAVAILABLE without exchange-published settlement reports."
              >
                Institutional Flow: UNAVAILABLE
              </span>

              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  padding: "3px 8px",
                  borderRadius: "4px",
                  background: data.money_flow_summary.net_flow_bias.includes("UPWARD") ? "rgba(38,199,139,0.15)" : (data.money_flow_summary.net_flow_bias.includes("DOWNWARD") ? "rgba(239,102,118,0.15)" : "rgba(245,158,11,0.15)"),
                  color: data.money_flow_summary.net_flow_bias.includes("UPWARD") ? "#26c78b" : (data.money_flow_summary.net_flow_bias.includes("DOWNWARD") ? "#ef6676" : "#f59e0b"),
                }}
              >
                {data.money_flow_summary.net_flow_bias.replace(/_/g, " ")}
              </span>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "20px", flexWrap: "wrap", marginBottom: "12px" }}>
            <div style={{ flex: 1, minWidth: "280px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", fontWeight: 700, marginBottom: "6px" }}>
                <span style={{ color: "#26c78b" }}>
                  Upper Candle Close Bias: {data.money_flow_summary.market_close_location_buying_bias_pct ?? data.money_flow_summary.market_buying_pressure_pct}%
                </span>
                <span style={{ color: "#ef6676" }}>
                  Lower Candle Close Bias: {data.money_flow_summary.market_close_location_selling_bias_pct ?? data.money_flow_summary.market_selling_pressure_pct}%
                </span>
              </div>
              <div style={{ width: "100%", height: "10px", background: "#ef6676", borderRadius: "5px", overflow: "hidden", display: "flex" }}>
                <div style={{ width: `${data.money_flow_summary.market_close_location_buying_bias_pct ?? data.money_flow_summary.market_buying_pressure_pct}%`, height: "100%", background: "#26c78b" }} />
              </div>
              <div style={{ fontSize: "10px", color: "#64748b", marginTop: "4px" }}>
                *OHLCV-derived estimate based on candle close location [(Close-Low)-(High-Close)]/(High-Low) — not actual buyer/seller order tape.
              </div>
            </div>

            <div style={{ fontSize: "11px", color: "#94a3b8", maxWidth: "420px" }}>
              {data.money_flow_summary.narrative}
            </div>
          </div>

          <div style={{ fontSize: "11px", color: "#64748b", display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
            <span>Intraday RVOL Method: </span>
            <strong style={{ color: "#f59e0b" }}>
              {data.money_flow_summary.rvol_time_label}
            </strong>
          </div>
        </div>
      )}

      {/* Filter and Search Bar for Tables */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          background: "#0d1520",
          border: "1px solid #1b2636",
          borderRadius: "8px",
          padding: "10px 16px",
        }}
      >
        <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
          <span style={{ fontSize: "12px", color: "#8c9bb0", fontWeight: 600 }}>Liquidity Filters:</span>
          <input
            type="number"
            placeholder="Min Traded Value (₹ Cr)"
            value={minTradedValueCr}
            onChange={(e) => setMinTradedValueCr(e.target.value)}
            style={{
              background: "#0a0f18",
              border: "1px solid #1e2c40",
              padding: "5px 10px",
              borderRadius: "4px",
              color: "#fff",
              fontSize: "11px",
              width: "160px",
            }}
          />
          <button
            onClick={() => fetchDashboard(true)}
            style={{
              background: "#2563eb",
              color: "#fff",
              border: "none",
              padding: "5px 12px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Apply
          </button>
        </div>

        <div style={{ position: "relative", minWidth: "200px" }}>
          <input
            type="text"
            placeholder="Filter table stocks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: "100%",
              background: "#0a0f18",
              border: "1px solid #1e2c40",
              borderRadius: "6px",
              padding: "6px 10px",
              color: "#fff",
              fontSize: "12px",
            }}
          />
        </div>
      </div>

      {/* =====================================================================
          SECTION 3: TOP VOLUME GAINERS SCANNER
          ===================================================================== */}
      {data && (
        <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
            <div>
              <h3 style={{ margin: "0 0 4px", fontSize: "15px", color: "#f1f5f9", fontWeight: 700 }}>
                3. Top Volume Gainers (RVOL Ranked)
              </h3>
              <p style={{ margin: 0, fontSize: "12px", color: "#8c9bb0" }}>
                Ranked by Relative Volume (RVOL) vs 20-Day Average Daily Volume.
              </p>
            </div>
            <span style={{ fontSize: "11px", color: "#f59e0b" }}>
              ⚠️ High volume indicates heavy participation; does not automatically mean buying.
            </span>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "12px" }}>
              <thead>
                <tr style={{ background: "#0a0f18", borderBottom: "1px solid #1e2c40", color: "#8c9bb0", fontSize: "11px", textTransform: "uppercase" }}>
                  <th style={{ padding: "10px 12px", width: "40px" }}>Rank</th>
                  <th style={{ padding: "10px 12px" }}>Stock</th>
                  <th style={{ padding: "10px 12px", textAlign: "right" }}>LTP (₹)</th>
                  <th style={{ padding: "10px 12px", textAlign: "right" }}>Price Chg %</th>
                  <th style={{ padding: "10px 12px", textAlign: "right" }}>Today's Volume</th>
                  <th style={{ padding: "10px 12px", textAlign: "right" }}>20D Avg Vol</th>
                  <th style={{ padding: "10px 12px", textAlign: "right" }}>Daily RVOL</th>
                  <th style={{ padding: "10px 12px", textAlign: "right" }}>Intraday RVOL</th>
                  <th style={{ padding: "10px 12px", textAlign: "right" }}>Traded Value</th>
                  <th style={{ padding: "10px 12px" }}>Sector</th>
                  <th style={{ padding: "10px 12px", textAlign: "center" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {data.volume_gainers
                  .filter((s) => !searchQuery || s.symbol.toLowerCase().includes(searchQuery.toLowerCase()))
                  .slice(0, 15)
                  .map((st) => {
                    const isPos = st.daily_change_pct >= 0;
                    const isHighVol = st.daily_rvol >= 1.5;
                    const isSelected = selectedStock === st.symbol;
                    return (
                      <tr
                        key={st.symbol}
                        onClick={() => handleRowClick(st.symbol)}
                        style={{
                          borderBottom: "1px solid #16202e",
                          background: isSelected ? "#1a2a40" : "transparent",
                          cursor: "pointer",
                          transition: "background 0.15s ease",
                        }}
                        onMouseEnter={(e) => {
                          if (!isSelected) e.currentTarget.style.background = "#131d2a";
                        }}
                        onMouseLeave={(e) => {
                          if (!isSelected) e.currentTarget.style.background = "transparent";
                        }}
                      >
                        <td style={{ padding: "10px 12px", color: "#64748b", fontWeight: 700 }}>#{st.rank}</td>
                        <td style={{ padding: "10px 12px" }}>
                          <div style={{ fontWeight: 700, color: "#fff" }}>{st.symbol}</div>
                          <div style={{ fontSize: "10px", color: "#64748b" }}>{st.company_name}</div>
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "right", fontWeight: 700, color: "#f8fafc" }}>
                          ₹{st.close.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "right" }}>
                          <span
                            style={{
                              padding: "2px 6px",
                              borderRadius: "4px",
                              fontSize: "11px",
                              fontWeight: 700,
                              background: isPos ? "rgba(38,199,139,0.15)" : "rgba(239,102,118,0.15)",
                              color: isPos ? "#26c78b" : "#ef6676",
                            }}
                          >
                            {isPos ? "+" : ""}{st.daily_change_pct.toFixed(2)}%
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "right", color: "#cbd5e1" }}>
                          {formatVol(st.today_volume)}
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "right", color: "#94a3b8" }}>
                          {formatVol(st.adv_20)}
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "right" }}>
                          <span
                            style={{
                              padding: "2px 6px",
                              borderRadius: "4px",
                              fontWeight: 700,
                              fontSize: "11px",
                              background: isHighVol ? "rgba(56, 189, 248, 0.2)" : "transparent",
                              color: isHighVol ? "#38bdf8" : "#cbd5e1",
                            }}
                          >
                            {st.daily_rvol.toFixed(2)}x
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "right" }}>
                          <span
                            style={{
                              fontSize: "11px",
                              color: st.intraday_rvol_status === "HISTORICAL_TIME_OF_DAY" ? "#26c78b" : "#f59e0b",
                              fontWeight: 600,
                            }}
                            title={st.intraday_rvol_explanation || "Intraday RVOL calculation"}
                          >
                            {st.intraday_rvol.toFixed(2)}x
                            <span style={{ fontSize: "9px", opacity: 0.8, marginLeft: "3px" }}>
                              ({st.intraday_rvol_status === "HISTORICAL_TIME_OF_DAY" ? "Hist" : "Est"})
                            </span>
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "right", fontWeight: 600, color: "#f1f5f9" }}>
                          ₹{st.traded_value_cr.toFixed(1)} Cr
                          <span
                            style={{
                              marginLeft: "5px",
                              fontSize: "9px",
                              fontWeight: 700,
                              padding: "1px 4px",
                              borderRadius: "3px",
                              background: st.traded_value_status === "ACTUAL_TURNOVER" ? "rgba(38,199,139,0.15)" : "rgba(245,158,11,0.15)",
                              color: st.traded_value_status === "ACTUAL_TURNOVER" ? "#26c78b" : "#f59e0b",
                            }}
                            title={st.turnover_explanation || (st.traded_value_status === "ACTUAL_TURNOVER" ? "Actual exchange turnover" : "Estimated from Volume × LTP")}
                          >
                            {st.traded_value_status === "ACTUAL_TURNOVER" ? "ACTUAL" : "EST."}
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px", color: "#94a3b8" }}>{st.sector}</td>
                        <td style={{ padding: "10px 12px", textAlign: "center" }}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectStock(st.symbol, "chart");
                            }}
                            style={{
                              background: "#1e293b",
                              color: "#38bdf8",
                              border: "1px solid #334155",
                              padding: "3px 8px",
                              borderRadius: "4px",
                              fontSize: "10px",
                              fontWeight: 600,
                              cursor: "pointer",
                            }}
                          >
                            Chart
                          </button>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* =====================================================================
          SECTION 4: TOP PRICE GAINERS & LOSERS SCANNER
          ===================================================================== */}
      {data && (
        <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px", flexWrap: "wrap", gap: "10px" }}>
            <div>
              <h3 style={{ margin: "0 0 4px", fontSize: "15px", color: "#f1f5f9", fontWeight: 700 }}>
                4. {priceGainerTab === "gainers" ? "Top Price Gainers" : "Top Price Losers"}
              </h3>
              <p style={{ margin: 0, fontSize: "12px", color: "#8c9bb0" }}>
                Ranked by percentage price change from previous day close.
              </p>
            </div>

            <div style={{ display: "flex", background: "#0a0f18", padding: "3px", borderRadius: "6px", border: "1px solid #1e2c40" }}>
              <button
                onClick={() => setPriceGainerTab("gainers")}
                style={{
                  background: priceGainerTab === "gainers" ? "#244c40" : "transparent",
                  color: priceGainerTab === "gainers" ? "#58dfac" : "#8c9bb0",
                  border: "none",
                  padding: "5px 12px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Top Gainers (▲)
              </button>
              <button
                onClick={() => setPriceGainerTab("losers")}
                style={{
                  background: priceGainerTab === "losers" ? "#4c242c" : "transparent",
                  color: priceGainerTab === "losers" ? "#df586c" : "#8c9bb0",
                  border: "none",
                  padding: "5px 12px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Top Losers (▼)
              </button>
            </div>
          </div>

          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "12px" }}>
              <thead>
                <tr style={{ background: "#0a0f18", borderBottom: "1px solid #1e2c40", color: "#8c9bb0", fontSize: "11px", textTransform: "uppercase" }}>
                  <th style={{ padding: "10px 12px", width: "40px" }}>Rank</th>
                  <th style={{ padding: "10px 12px" }}>Stock</th>
                  <th style={{ padding: "10px 12px", textAlign: "right" }}>LTP (₹)</th>
                  <th style={{ padding: "10px 12px", textAlign: "right" }}>Price Chg %</th>
                  <th style={{ padding: "10px 12px", textAlign: "right" }}>RVOL</th>
                  <th style={{ padding: "10px 12px", textAlign: "right" }}>Traded Value</th>
                  <th style={{ padding: "10px 12px" }}>Price-Volume Classification</th>
                  <th style={{ padding: "10px 12px", textAlign: "center" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {(priceGainerTab === "gainers" ? data.price_gainers : data.price_losers)
                  .filter((s) => !searchQuery || s.symbol.toLowerCase().includes(searchQuery.toLowerCase()))
                  .slice(0, 10)
                  .map((st) => {
                    const isPos = st.daily_change_pct >= 0;
                    const isSelected = selectedStock === st.symbol;
                    return (
                      <tr
                        key={st.symbol}
                        onClick={() => handleRowClick(st.symbol)}
                        style={{
                          borderBottom: "1px solid #16202e",
                          background: isSelected ? "#1a2a40" : "transparent",
                          cursor: "pointer",
                        }}
                      >
                        <td style={{ padding: "10px 12px", color: "#64748b", fontWeight: 700 }}>#{st.rank}</td>
                        <td style={{ padding: "10px 12px" }}>
                          <div style={{ fontWeight: 700, color: "#fff" }}>{st.symbol}</div>
                          <div style={{ fontSize: "10px", color: "#64748b" }}>{st.company_name}</div>
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "right", fontWeight: 700, color: "#f8fafc" }}>
                          ₹{st.close.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "right" }}>
                          <span
                            style={{
                              padding: "2px 6px",
                              borderRadius: "4px",
                              fontSize: "11px",
                              fontWeight: 700,
                              background: isPos ? "rgba(38,199,139,0.15)" : "rgba(239,102,118,0.15)",
                              color: isPos ? "#26c78b" : "#ef6676",
                            }}
                          >
                            {isPos ? "+" : ""}{st.daily_change_pct.toFixed(2)}%
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "right", color: "#cbd5e1", fontWeight: 600 }}>
                          {st.daily_rvol.toFixed(2)}x
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "right", color: "#f1f5f9" }}>
                          ₹{st.traded_value_cr.toFixed(1)} Cr
                          <span
                            style={{
                              marginLeft: "5px",
                              fontSize: "9px",
                              fontWeight: 700,
                              padding: "1px 4px",
                              borderRadius: "3px",
                              background: st.traded_value_status === "ACTUAL_TURNOVER" ? "rgba(38,199,139,0.15)" : "rgba(245,158,11,0.15)",
                              color: st.traded_value_status === "ACTUAL_TURNOVER" ? "#26c78b" : "#f59e0b",
                            }}
                          >
                            {st.traded_value_status === "ACTUAL_TURNOVER" ? "ACTUAL" : "EST."}
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px" }}>
                          <span
                            style={{
                              fontSize: "10px",
                              fontWeight: 700,
                              padding: "2px 6px",
                              borderRadius: "4px",
                              background: st.money_flow_classification.includes("ADVANCE") ? "rgba(38,199,139,0.15)" : (st.money_flow_classification.includes("DECLINE") ? "rgba(239,102,118,0.15)" : "rgba(148,163,184,0.15)"),
                              color: st.money_flow_classification.includes("ADVANCE") ? "#26c78b" : (st.money_flow_classification.includes("DECLINE") ? "#ef6676" : "#cbd5e1"),
                            }}
                          >
                            {st.money_flow_classification.replace(/_/g, " ")}
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "center" }}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              onSelectStock(st.symbol, "chart");
                            }}
                            style={{
                              background: "#1e293b",
                              color: "#38bdf8",
                              border: "1px solid #334155",
                              padding: "3px 8px",
                              borderRadius: "4px",
                              fontSize: "10px",
                              fontWeight: 600,
                              cursor: "pointer",
                            }}
                          >
                            Chart
                          </button>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* =====================================================================
          SECTION 5 & 6: COMBINED VOLUME + PRICE SCREENING CATEGORIES
          ===================================================================== */}
      {data && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "16px" }}>
          {/* 5. Volume + Price Gainers */}
          <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "18px" }}>
            <h4 style={{ margin: "0 0 6px", fontSize: "14px", color: "#26c78b", fontWeight: 700 }}>
              5. High Volume + Price Gainers (Expanding Volume Advance)
            </h4>
            <p style={{ margin: "0 0 10px", fontSize: "11px", color: "#64748b" }}>
              Price rising (&gt;0.5%) with unusually high volume (&ge;1.3x RVOL).
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "180px", overflowY: "auto" }}>
              {data.combined_categories.high_volume_price_gainers.length === 0 ? (
                <div style={{ color: "#64748b", fontSize: "11px" }}>No stocks matching high-volume gainers.</div>
              ) : (
                data.combined_categories.high_volume_price_gainers.map((st) => (
                  <div
                    key={st.symbol}
                    onClick={() => handleRowClick(st.symbol)}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      background: "#0a0f18",
                      padding: "8px 12px",
                      borderRadius: "6px",
                      cursor: "pointer",
                    }}
                  >
                    <span style={{ fontWeight: 700, color: "#fff" }}>{st.symbol}</span>
                    <span style={{ color: "#26c78b", fontSize: "11px" }}>+{st.daily_change_pct}% | RVOL {st.daily_rvol}x</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* 6. Volume + Price Losers */}
          <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "18px" }}>
            <h4 style={{ margin: "0 0 6px", fontSize: "14px", color: "#ef6676", fontWeight: 700 }}>
              6. High Volume + Price Losers (Expanding Volume Decline)
            </h4>
            <p style={{ margin: "0 0 10px", fontSize: "11px", color: "#64748b" }}>
              Price falling (&lt;-0.5%) with unusually high volume (&ge;1.3x RVOL).
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "180px", overflowY: "auto" }}>
              {data.combined_categories.high_volume_price_losers.length === 0 ? (
                <div style={{ color: "#64748b", fontSize: "11px" }}>No stocks matching high-volume losers.</div>
              ) : (
                data.combined_categories.high_volume_price_losers.map((st) => (
                  <div
                    key={st.symbol}
                    onClick={() => handleRowClick(st.symbol)}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      background: "#0a0f18",
                      padding: "8px 12px",
                      borderRadius: "6px",
                      cursor: "pointer",
                    }}
                  >
                    <span style={{ fontWeight: 700, color: "#fff" }}>{st.symbol}</span>
                    <span style={{ color: "#ef6676", fontSize: "11px" }}>{st.daily_change_pct}% | RVOL {st.daily_rvol}x</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* High Volume Sideways */}
          <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "18px" }}>
            <h4 style={{ margin: "0 0 6px", fontSize: "14px", color: "#f59e0b", fontWeight: 700 }}>
              High Volume + Sideways Stocks (Range Churn / Absorption)
            </h4>
            <p style={{ margin: "0 0 10px", fontSize: "11px", color: "#64748b" }}>
              Unusual participation without price displacement (|&Delta;%| &le; 0.5%, RVOL &ge; 1.3x).
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "180px", overflowY: "auto" }}>
              {data.combined_categories.high_volume_sideways.length === 0 ? (
                <div style={{ color: "#64748b", fontSize: "11px" }}>No stocks in sideways churn today.</div>
              ) : (
                data.combined_categories.high_volume_sideways.map((st) => (
                  <div
                    key={st.symbol}
                    onClick={() => handleRowClick(st.symbol)}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      background: "#0a0f18",
                      padding: "8px 12px",
                      borderRadius: "6px",
                      cursor: "pointer",
                    }}
                  >
                    <span style={{ fontWeight: 700, color: "#fff" }}>{st.symbol}</span>
                    <span style={{ color: "#f59e0b", fontSize: "11px" }}>Move: {st.daily_change_pct}% | RVOL {st.daily_rvol}x</span>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Low Volume Breakouts */}
          <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "18px" }}>
            <h4 style={{ margin: "0 0 6px", fontSize: "14px", color: "#cbd5e1", fontWeight: 700 }}>
              Low Volume + Price Breakouts (Unconfirmed Moves)
            </h4>
            <p style={{ margin: "0 0 10px", fontSize: "11px", color: "#64748b" }}>
              Breakout move with below-average volume (&lt;1.0x RVOL); flagged as weaker volume confirmation.
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", maxHeight: "180px", overflowY: "auto" }}>
              {data.combined_categories.low_volume_breakouts.length === 0 ? (
                <div style={{ color: "#64748b", fontSize: "11px" }}>No unconfirmed low-volume breakouts.</div>
              ) : (
                data.combined_categories.low_volume_breakouts.map((st) => (
                  <div
                    key={st.symbol}
                    onClick={() => handleRowClick(st.symbol)}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      background: "#0a0f18",
                      padding: "8px 12px",
                      borderRadius: "6px",
                      cursor: "pointer",
                    }}
                  >
                    <span style={{ fontWeight: 700, color: "#fff" }}>{st.symbol}</span>
                    <span style={{ color: "#f43f5e", fontSize: "11px" }}>Move: {st.daily_change_pct}% | RVOL {st.daily_rvol}x (Weak)</span>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* =====================================================================
          SECTION 7: SECTOR MONEY FLOW / ROTATION
          ===================================================================== */}
      {data && (
        <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "20px" }}>
          <h3 style={{ margin: "0 0 4px", fontSize: "15px", color: "#f1f5f9", fontWeight: 700 }}>
            7. Sector Money Flow & Sector-Relative Strength Matrix
          </h3>
          <p style={{ margin: "0 0 14px", fontSize: "12px", color: "#8c9bb0" }}>
            Aggregated sector-level volume turnover, close-location price bias balance, and rotation quadrants.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "12px" }}>
            {data.sector_money_flow.map((sec) => {
              const isLeading = sec.rotation_quadrant === "LEADING";
              const isWeak = sec.rotation_quadrant === "LAGGING";
              return (
                <div
                  key={sec.sector}
                  style={{
                    background: "#0a0f18",
                    border: "1px solid #1e2c40",
                    borderRadius: "8px",
                    padding: "14px",
                    display: "flex",
                    flexDirection: "column",
                    gap: "8px",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <strong style={{ fontSize: "13px", color: "#fff" }}>{sec.sector}</strong>
                    <span
                      style={{
                        fontSize: "10px",
                        fontWeight: 700,
                        padding: "2px 6px",
                        borderRadius: "4px",
                        background: isLeading ? "rgba(38,199,139,0.15)" : isWeak ? "rgba(239,102,118,0.15)" : "rgba(245,158,11,0.15)",
                        color: isLeading ? "#26c78b" : isWeak ? "#ef6676" : "#f59e0b",
                      }}
                    >
                      {sec.rotation_quadrant}
                    </span>
                  </div>

                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#94a3b8" }}>
                    <span>Avg Chg: <strong style={{ color: sec.average_change_pct >= 0 ? "#26c78b" : "#ef6676" }}>{sec.average_change_pct}%</strong></span>
                    <span>Avg RVOL: <strong style={{ color: "#38bdf8" }}>{sec.average_rvol}x</strong></span>
                  </div>

                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#94a3b8" }}>
                    <span>Turnover: ₹{sec.total_traded_value_cr} Cr</span>
                    <span>RS vs Mkt: {sec.relative_strength_vs_market >= 0 ? "+" : ""}{sec.relative_strength_vs_market}%</span>
                  </div>

                  {/* Close location bias bar */}
                  <div style={{ width: "100%", height: "4px", background: "#ef6676", borderRadius: "2px", overflow: "hidden", display: "flex" }}>
                    <div style={{ width: `${sec.average_close_location_buying_bias ?? sec.average_buying_pressure}%`, height: "100%", background: "#26c78b" }} />
                  </div>

                  <div style={{ fontSize: "10px", color: "#64748b", display: "flex", justifyContent: "space-between", paddingTop: "4px", borderTop: "1px solid #141f2e" }}>
                    <span>Top: <strong style={{ color: "#fff" }}>{sec.strongest_stock}</strong> ({sec.strongest_change}%)</span>
                    <span>Bot: <strong style={{ color: "#fff" }}>{sec.weakest_stock}</strong> ({sec.weakest_change}%)</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* =====================================================================
          SECTION 8: STOCK-LEVEL MONEY FLOW ANALYSIS
          ===================================================================== */}
      <div id="stock-deep-dive-section" style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
          <div>
            <h3 style={{ margin: "0 0 4px", fontSize: "15px", color: "#f1f5f9", fontWeight: 700 }}>
              8. Stock-Level Money Flow & Volume Deep-Dive
            </h3>
            <p style={{ margin: 0, fontSize: "12px", color: "#8c9bb0" }}>
              Granular volume moving averages (10D/20D/50D), dual-method intraday RVOL, and price-volume divergence.
            </p>
          </div>

          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <span style={{ fontSize: "12px", color: "#94a3b8" }}>Inspect Stock:</span>
            <input
              type="text"
              value={selectedStock}
              onChange={(e) => setSelectedStock(e.target.value.toUpperCase())}
              style={{
                background: "#0a0f18",
                border: "1px solid #1e2c40",
                padding: "6px 12px",
                borderRadius: "6px",
                color: "#fff",
                fontSize: "12px",
                width: "120px",
                textTransform: "uppercase",
              }}
            />
            <button
              onClick={() => onSelectStock(selectedStock, "chart")}
              style={{
                background: "#2563eb",
                color: "#fff",
                border: "none",
                padding: "6px 14px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Open Technical Chart
            </button>
          </div>
        </div>

        {stockDetailLoading ? (
          <div style={{ padding: "40px", textAlign: "center", color: "#8c9bb0" }}>
            Loading stock volume intelligence for {selectedStock}...
          </div>
        ) : !selectedStockDetail ? (
          <div style={{ padding: "30px", textAlign: "center", color: "#8c9bb0" }}>
            Select a stock from the tables above to inspect its granular volume structure.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            {/* Top Metrics Row */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "12px" }}>
              <div style={{ background: "#0a0f18", border: "1px solid #1e2c40", borderRadius: "8px", padding: "12px" }}>
                <div style={{ fontSize: "10px", color: "#8c9bb0", textTransform: "uppercase" }}>Today's Traded Volume</div>
                <div style={{ fontSize: "20px", fontWeight: 800, color: "#fff", marginTop: "4px" }}>
                  {formatVol(selectedStockDetail.today_volume)}
                </div>
                <div style={{ fontSize: "10px", color: selectedStockDetail.volume_change_pct >= 0 ? "#26c78b" : "#ef6676", marginTop: "2px" }}>
                  {selectedStockDetail.volume_change_pct >= 0 ? "+" : ""}{selectedStockDetail.volume_change_pct}% vs 20D Avg
                </div>
              </div>

              <div style={{ background: "#0a0f18", border: "1px solid #1e2c40", borderRadius: "8px", padding: "12px" }}>
                <div style={{ fontSize: "10px", color: "#8c9bb0", textTransform: "uppercase" }}>Volume Moving Averages</div>
                <div style={{ fontSize: "12px", color: "#cbd5e1", marginTop: "6px" }}>
                  <div>10D ADV: <strong>{formatVol(selectedStockDetail.adv_10)}</strong></div>
                  <div>20D ADV: <strong>{formatVol(selectedStockDetail.adv_20)}</strong></div>
                  <div>50D ADV: <strong>{formatVol(selectedStockDetail.adv_50)}</strong></div>
                </div>
              </div>

              <div style={{ background: "#0a0f18", border: "1px solid #1e2c40", borderRadius: "8px", padding: "12px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "10px", color: "#8c9bb0", textTransform: "uppercase" }}>Daily & Intraday RVOL</span>
                  <span
                    style={{
                      fontSize: "9px",
                      fontWeight: 700,
                      padding: "1px 5px",
                      borderRadius: "3px",
                      background: selectedStockDetail.intraday_rvol_status === "HISTORICAL_TIME_OF_DAY" ? "rgba(38,199,139,0.15)" : "rgba(245,158,11,0.15)",
                      color: selectedStockDetail.intraday_rvol_status === "HISTORICAL_TIME_OF_DAY" ? "#26c78b" : "#f59e0b",
                    }}
                  >
                    {selectedStockDetail.intraday_rvol_status === "HISTORICAL_TIME_OF_DAY" ? "HISTORICAL TOD" : "ESTIMATED"}
                  </span>
                </div>
                <div style={{ fontSize: "18px", fontWeight: 800, color: "#38bdf8", marginTop: "4px" }}>
                  Daily: {selectedStockDetail.daily_rvol.toFixed(2)}x
                </div>
                <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "2px" }}>
                  Intraday: <strong>{selectedStockDetail.intraday_rvol.toFixed(2)}x</strong>
                </div>
                <div style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>
                  {selectedStockDetail.rvol_time_label}
                </div>
              </div>

              <div style={{ background: "#0a0f18", border: "1px solid #1e2c40", borderRadius: "8px", padding: "12px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "10px", color: "#8c9bb0", textTransform: "uppercase" }}>Traded Value & Delivery</span>
                  <span
                    style={{
                      fontSize: "9px",
                      fontWeight: 700,
                      padding: "1px 5px",
                      borderRadius: "3px",
                      background: selectedStockDetail.traded_value_status === "ACTUAL_TURNOVER" ? "rgba(38,199,139,0.15)" : "rgba(245,158,11,0.15)",
                      color: selectedStockDetail.traded_value_status === "ACTUAL_TURNOVER" ? "#26c78b" : "#f59e0b",
                    }}
                  >
                    {selectedStockDetail.traded_value_status === "ACTUAL_TURNOVER" ? "ACTUAL TURNOVER" : "ESTIMATED"}
                  </span>
                </div>
                <div style={{ fontSize: "18px", fontWeight: 800, color: "#fff", marginTop: "4px" }}>
                  ₹{selectedStockDetail.traded_value_cr.toFixed(1)} Cr
                </div>
                <div style={{ fontSize: "10px", color: "#64748b", marginTop: "2px" }}>
                  Delivery: {selectedStockDetail.delivery_status}
                </div>
              </div>
            </div>

            {/* Close-Location Price Bias & Divergence Bar */}
            <div
              style={{
                background: "#0a0f18",
                border: "1px solid #1e2c40",
                borderRadius: "8px",
                padding: "16px",
                display: "flex",
                flexDirection: "column",
                gap: "10px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
                <span style={{ fontSize: "13px", fontWeight: 700, color: "#fff" }}>
                  Price-Volume & Money Flow Analysis: {selectedStockDetail.symbol}
                </span>
                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                  <span
                    style={{
                      fontSize: "10px",
                      fontWeight: 700,
                      padding: "2px 6px",
                      borderRadius: "3px",
                      background: "rgba(148, 163, 184, 0.15)",
                      color: "#94a3b8",
                    }}
                  >
                    Institutional Flow: UNAVAILABLE
                  </span>
                  <span
                    style={{
                      fontSize: "11px",
                      fontWeight: 700,
                      padding: "3px 8px",
                      borderRadius: "4px",
                      background: selectedStockDetail.money_flow_classification.includes("ADVANCE") ? "rgba(38,199,139,0.15)" : (selectedStockDetail.money_flow_classification.includes("DECLINE") ? "rgba(239,102,118,0.15)" : "rgba(245,158,11,0.15)"),
                      color: selectedStockDetail.money_flow_classification.includes("ADVANCE") ? "#26c78b" : (selectedStockDetail.money_flow_classification.includes("DECLINE") ? "#ef6676" : "#f59e0b"),
                    }}
                  >
                    {selectedStockDetail.money_flow_classification.replace(/_/g, " ")}
                  </span>
                </div>
              </div>

              <div style={{ display: "flex", gap: "14px", alignItems: "center" }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", fontWeight: 700, marginBottom: "4px" }}>
                    <span style={{ color: "#26c78b" }}>
                      Close-Location Buying Bias: {selectedStockDetail.close_location_buying_bias_pct ?? selectedStockDetail.buying_pressure_pct}%
                    </span>
                    <span style={{ color: "#ef6676" }}>
                      Close-Location Selling Bias: {selectedStockDetail.close_location_selling_bias_pct ?? selectedStockDetail.selling_pressure_pct}%
                    </span>
                  </div>
                  <div style={{ width: "100%", height: "8px", background: "#ef6676", borderRadius: "4px", overflow: "hidden", display: "flex" }}>
                    <div style={{ width: `${selectedStockDetail.close_location_buying_bias_pct ?? selectedStockDetail.buying_pressure_pct}%`, height: "100%", background: "#26c78b" }} />
                  </div>
                  <div style={{ fontSize: "10px", color: "#64748b", marginTop: "3px" }}>
                    {selectedStockDetail.close_location_explanation || "*OHLCV-derived estimate measuring candle close location [(Close-Low)-(High-Close)]/(High-Low)."}
                  </div>
                </div>

                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: "10px", color: "#8c9bb0", textTransform: "uppercase" }}>Chaikin Money Flow</div>
                  <div style={{ fontSize: "15px", color: "#38bdf8", fontWeight: 700, marginTop: "2px" }}>
                    {selectedStockDetail.chaikin_money_flow_20 ?? selectedStockDetail.cmf_20}
                  </div>
                  <div style={{ fontSize: "9px", color: "#64748b" }}>20D Volume-Weighted</div>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#94a3b8", flexWrap: "wrap", gap: "8px", borderTop: "1px solid #141f2e", paddingTop: "8px" }}>
                <div>
                  <strong style={{ color: "#cbd5e1" }}>Divergence Status:</strong>{" "}
                  <span style={{ color: selectedStockDetail.price_volume_divergence === "BULLISH_DIVERGENCE" ? "#26c78b" : (selectedStockDetail.price_volume_divergence === "BEARISH_DIVERGENCE" ? "#ef6676" : "#8c9bb0") }}>
                    {selectedStockDetail.price_volume_divergence}
                  </span>{" "}
                  ({selectedStockDetail.divergence_note})
                </div>
                <div>
                  <strong style={{ color: "#cbd5e1" }}>Evidence Note:</strong> {selectedStockDetail.money_flow_note}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

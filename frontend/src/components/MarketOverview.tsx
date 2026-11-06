import { apiFetch } from "../api/client";
import React, { useState, useEffect, useMemo } from "react";
import { LiveQuote } from "../api/marketFeed";
import MarketMoversConfluenceView from "./MarketMoversConfluenceView";

interface IndexSummary {
  name: string;
  symbol: string;
  value: string;
  numeric_value?: number | null;
  change_pct?: number | null;
  high?: string;
  low?: string;
  positive?: boolean | null;
  data_mode?: string;
  is_estimated?: boolean;
  status?: string;
  source?: string;
  source_note?: string;
  disclaimer?: string;
}

interface StockItem {
  symbol: string;
  company_name: string;
  sector: string;
  close: number;
  daily_change_pct: number;
  relative_volume: number;
  pe?: number | null;
  week_52_high?: number;
  week_52_low?: number;
}

interface SectorItem {
  sector: string;
  stock_count: number;
  average_change_pct: number;
  average_rsi: number;
  average_rvol: number;
  advances: number;
  declines: number;
  unchanged: number;
  breadth_pct: number;
  relative_strength_vs_market: number;
  rotation_quadrant: "LEADING" | "WEAKENING" | "LAGGING" | "IMPROVING";
  quadrant_color: string;
  breakout_count: number;
  breakdown_count: number;
  strongest_stock: { symbol: string; change_pct: number; close: number };
  weakest_stock: { symbol: string; change_pct: number; close: number };
  prominent_stocks: string;
  positive: boolean;
}

interface DashboardData {
  timestamp: string;
  universe: string;
  universe_label: string;
  configured_universe_count: number;
  scanned_count: number;
  coverage_pct: number;
  coverage_note: string;
  indices: IndexSummary[];
  breadth: {
    advances: number;
    declines: number;
    unchanged: number;
    total_tracked: number;
    advance_decline_ratio: number;
    breadth_pct: number;
    average_market_change: number;
    average_relative_volume: number;
  };
  extremes_52w: {
    highs_count: number;
    lows_count: number;
    near_highs_count: number;
    near_lows_count: number;
    new_highs: StockItem[];
    new_lows: StockItem[];
    near_highs: StockItem[];
    near_lows: StockItem[];
  };
  market_regime: {
    regime: string;
    score: number;
    description: string;
    volatility_regime: string;
    vix_value: number;
  };
  leaders: {
    gainers: StockItem[];
    losers: StockItem[];
    volume_surge: StockItem[];
  };
  metadata: {
    provider: string;
    exchange: string;
    timeframe: string;
    data_mode: string;
    last_update_timestamp: string;
  };
}

interface MarketOverviewProps {
  liveQuotes?: Record<string, LiveQuote>;
  onSelectStock: (symbol: string, page?: string) => void;
}

export default function MarketOverview({ liveQuotes = {}, onSelectStock }: MarketOverviewProps) {
  const [universe, setUniverse] = useState<string>("all");
  const [loading, setLoading] = useState<boolean>(true);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [sectors, setSectors] = useState<SectorItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sectorFilter, setSectorFilter] = useState<string>("ALL");
  const [quadrantFilter, setQuadrantFilter] = useState<string>("ALL");
  const [moversViewTab, setMoversViewTab] = useState<"confluence" | "52w">("confluence");
  const [extremesTab, setExtremesTab] = useState<"near_highs" | "new_highs" | "near_lows" | "new_lows">("near_highs");

  const fetchData = async (force: boolean = false) => {
    setLoading(true);
    setError(null);
    setDashboard(null);
    setSectors([]);
    try {
      const [dashRes, secRes] = await Promise.all([
        apiFetch(`/api/market/intelligence/dashboard?universe=${universe}&force_refresh=${force}`),
        apiFetch(`/api/market/intelligence/sectors?universe=${universe}&force_refresh=${force}`),
      ]);

      if (!dashRes.ok) throw new Error(`Market overview API returned HTTP ${dashRes.status}.`);
      if (!secRes.ok) throw new Error(`Sector intelligence API returned HTTP ${secRes.status}.`);
      const [d, s] = await Promise.all([dashRes.json(), secRes.json()]);
      setDashboard(d);
      setSectors(s.sectors || []);
    } catch (err) {
      console.error("Error fetching market intelligence:", err);
      setError(err instanceof Error ? err.message : "Market intelligence service is unavailable.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData(false);
  }, [universe]);

  // Merge live quotes when available
  const currentIndices = useMemo(() => {
    if (!dashboard) return [];
    return dashboard.indices;
  }, [dashboard]);

  const filteredSectors = useMemo(() => {
    if (quadrantFilter === "ALL") return sectors;
    return sectors.filter((s) => s.rotation_quadrant === quadrantFilter);
  }, [sectors, quadrantFilter]);

  const displayedExtremesStocks = useMemo(() => {
    if (!dashboard) return [];
    let list: StockItem[] = [];
    if (extremesTab === "near_highs") list = dashboard.extremes_52w.near_highs;
    else if (extremesTab === "new_highs") list = dashboard.extremes_52w.new_highs;
    else if (extremesTab === "near_lows") list = dashboard.extremes_52w.near_lows;
    else if (extremesTab === "new_lows") list = dashboard.extremes_52w.new_lows;

    if (sectorFilter !== "ALL") {
      list = list.filter((s) => s.sector === sectorFilter);
    }

    return list.map((s) => {
      const q = liveQuotes[s.symbol];
      if (q && q.ltp) {
        return {
          ...s,
          close: q.ltp,
          daily_change_pct: q.change_percent ?? s.daily_change_pct,
        };
      }
      return s;
    });
  }, [dashboard, extremesTab, sectorFilter, liveQuotes]);

  const regimeColor = useMemo(() => {
    const reg = dashboard?.market_regime?.regime;
    if (reg === "STRONG_BULLISH") return "#26c78b";
    if (reg === "MODERATE_BULLISH") return "#10b981";
    if (reg === "NEUTRAL") return "#f59e0b";
    if (reg === "MODERATE_BEARISH") return "#f43f5e";
    if (reg === "STRONG_BEARISH") return "#ef4444";
    return "#8c9bb0";
  }, [dashboard]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Header Banner & Universe Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "#111925",
          border: "1px solid #202d40",
          borderRadius: "10px",
          padding: "18px 24px",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h2 style={{ fontSize: "20px", fontWeight: 700, margin: 0, color: "#f1f5f9" }}>
              Indian Market Intelligence & Overview
            </h2>
            <span
              style={{
                fontSize: "11px",
                fontWeight: 700,
                padding: "2px 8px",
                borderRadius: "4px",
                background: "rgba(59, 130, 246, 0.15)",
                color: "#60a5fa",
                border: "1px solid rgba(59, 130, 246, 0.3)",
              }}
            >
              DATA MODE: {dashboard?.metadata?.data_mode || "UNAVAILABLE"}
            </span>
          </div>
          <p style={{ margin: "6px 0 0", fontSize: "12px", color: "#8c9bb0" }}>
            Real-time equity market dynamics, advance/decline distribution, sector rotation, and 52-week extremes.
          </p>
        </div>

        {error && (
          <div className="notice" role="status">
            Market intelligence unavailable: {error} Historical or demo values are not substituted.
          </div>
        )}

        {/* Universe Selector & Refresh */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          <div style={{ display: "flex", background: "#0b121c", padding: "3px", borderRadius: "6px", border: "1px solid #1e293b" }}>
            {[
              { id: "all", label: "All Stocks" },
              { id: "nifty50", label: "NIFTY 50" },
              { id: "nifty100", label: "NIFTY 100" },
              { id: "nifty500", label: "NIFTY 500" },
              { id: "fno", label: "NSE F&O" },
            ].map((u) => (
              <button
                key={u.id}
                onClick={() => setUniverse(u.id)}
                style={{
                  background: universe === u.id ? "#2563eb" : "transparent",
                  color: universe === u.id ? "#ffffff" : "#94a3b8",
                  border: "none",
                  padding: "6px 12px",
                  borderRadius: "4px",
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
            onClick={() => fetchData(true)}
            style={{
              background: "#1e293b",
              color: "#cbd5e1",
              border: "1px solid #334155",
              padding: "7px 14px",
              borderRadius: "6px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {loading ? "Refreshing..." : "↻ Refresh"}
          </button>
        </div>
      </div>

      {/* Transparent Coverage Disclosure Banner */}
      {dashboard && (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: "#0d1520",
            border: "1px solid #1b2636",
            borderRadius: "6px",
            padding: "8px 16px",
            fontSize: "11px",
            color: "#94a3b8",
            flexWrap: "wrap",
            gap: "8px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <div>
              <strong style={{ color: "#38bdf8" }}>Universe Coverage:</strong> {dashboard.coverage_note}
            </div>
            <span
              style={{
                fontSize: "10px",
                fontWeight: 700,
                padding: "2px 6px",
                borderRadius: "4px",
                background: dashboard.coverage_pct >= 90 ? "rgba(38,199,139,0.15)" : "rgba(245,158,11,0.15)",
                color: dashboard.coverage_pct >= 90 ? "#26c78b" : "#f59e0b",
                border: `1px solid ${dashboard.coverage_pct >= 90 ? "rgba(38,199,139,0.3)" : "rgba(245,158,11,0.3)"}`,
              }}
            >
              {dashboard.scanned_count}/{dashboard.configured_universe_count} ({dashboard.coverage_pct}%)
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <span style={{ color: "#64748b" }}>
              Broker Stream: <span style={{ color: "#e2e8f0" }}>Dhan Inactive (Zero-Cost Research)</span>
            </span>
            <span>Last Updated: {dashboard.metadata.last_update_timestamp}</span>
          </div>
        </div>
      )}

      {/* Market Breadth & Market Regime Row */}
      {dashboard && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "16px" }}>
          {/* Breadth Meter Card */}
          <div
            style={{
              background: "#111925",
              border: "1px solid #202d40",
              borderRadius: "10px",
              padding: "16px 20px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <span style={{ fontSize: "11px", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                Market Breadth Distribution
              </span>
              <span style={{ fontSize: "12px", fontWeight: 700, color: "#38bdf8" }}>
                A/D Ratio: {dashboard.breadth.advance_decline_ratio}:1
              </span>
            </div>

            <div style={{ display: "flex", gap: "16px", alignItems: "center", marginBottom: "12px" }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", fontWeight: 700, marginBottom: "6px" }}>
                  <span style={{ color: "#26c78b" }}>▲ {dashboard.breadth.advances} Advances</span>
                  <span style={{ color: "#ef6676" }}>▼ {dashboard.breadth.declines} Declines</span>
                  <span style={{ color: "#8c9bb0" }}>● {dashboard.breadth.unchanged} Unch</span>
                </div>
                <div style={{ width: "100%", height: "8px", background: "#ef6676", borderRadius: "4px", overflow: "hidden", display: "flex" }}>
                  <div style={{ width: `${dashboard.breadth.breadth_pct}%`, height: "100%", background: "#26c78b" }} />
                  <div
                    style={{
                      width: `${(dashboard.breadth.unchanged / Math.max(dashboard.breadth.total_tracked, 1)) * 100}%`,
                      height: "100%",
                      background: "#64748b",
                    }}
                  />
                </div>
              </div>
              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: "20px", fontWeight: 800, color: "#f8fafc" }}>
                  {dashboard.breadth.breadth_pct}%
                </div>
                <div style={{ fontSize: "10px", color: "#64748b" }}>BULLISH BIAS</div>
              </div>
            </div>

            <div style={{ fontSize: "11px", color: "#64748b", display: "flex", justifyContent: "space-between" }}>
              <span>Avg Move: {dashboard.breadth.average_market_change > 0 ? "+" : ""}{dashboard.breadth.average_market_change}%</span>
              <span>Avg RVOL: {dashboard.breadth.average_relative_volume}x</span>
              <span>Total Tracked: {dashboard.breadth.total_tracked}</span>
            </div>
          </div>

          {/* Market Regime Card */}
          <div
            style={{
              background: "#111925",
              border: "1px solid #202d40",
              borderRadius: "10px",
              padding: "16px 20px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <span style={{ fontSize: "11px", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                Market Regime Classification
              </span>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  padding: "3px 8px",
                  borderRadius: "4px",
                  background: `${regimeColor}22`,
                  color: regimeColor,
                  border: `1px solid ${regimeColor}44`,
                }}
              >
                {dashboard.market_regime.regime.replace("_", " ")}
              </span>
            </div>

            <div style={{ display: "flex", alignItems: "baseline", gap: "12px", margin: "6px 0" }}>
              <div style={{ fontSize: "28px", fontWeight: 800, color: regimeColor }}>
                {dashboard.market_regime.score}
              </div>
              <span style={{ fontSize: "12px", color: "#64748b" }}>/ 100 Composite Trend Score</span>
              <div style={{ marginLeft: "auto", textAlign: "right" }}>
                <span style={{ fontSize: "11px", color: "#94a3b8" }}>Volatility: </span>
                <strong style={{ color: "#38bdf8", fontSize: "11px" }}>{dashboard.market_regime.volatility_regime}</strong>
                <span style={{ fontSize: "10px", color: "#64748b", display: "block" }}>
                  INDIA VIX: {dashboard.market_regime.vix_value || "UNAVAILABLE"}
                </span>
              </div>
            </div>

            <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#cbd5e1", lineHeight: 1.4 }}>
              {dashboard.market_regime.description}
            </p>
          </div>

          {/* 52-Week Extremes Card */}
          <div
            style={{
              background: "#111925",
              border: "1px solid #202d40",
              borderRadius: "10px",
              padding: "16px 20px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <span style={{ fontSize: "11px", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                52-Week Extremes
              </span>
              <span style={{ fontSize: "11px", color: "#64748b" }}>Within 3% Threshold</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <div style={{ background: "#0a1a12", border: "1px solid #14462b", borderRadius: "8px", padding: "10px" }}>
                <div style={{ fontSize: "10px", color: "#26c78b", fontWeight: 700 }}>52W HIGHS / NEAR HIGHS</div>
                <div style={{ fontSize: "20px", fontWeight: 800, color: "#26c78b", margin: "4px 0" }}>
                  {dashboard.extremes_52w.highs_count + dashboard.extremes_52w.near_highs_count}
                </div>
                <div style={{ fontSize: "10px", color: "#6ee7b7" }}>
                  {dashboard.extremes_52w.highs_count} new highs recorded
                </div>
              </div>

              <div style={{ background: "#1f0d11", border: "1px solid #4a151b", borderRadius: "8px", padding: "10px" }}>
                <div style={{ fontSize: "10px", color: "#ef6676", fontWeight: 700 }}>52W LOWS / NEAR LOWS</div>
                <div style={{ fontSize: "20px", fontWeight: 800, color: "#ef6676", margin: "4px 0" }}>
                  {dashboard.extremes_52w.lows_count + dashboard.extremes_52w.near_lows_count}
                </div>
                <div style={{ fontSize: "10px", color: "#fca5a5" }}>
                  {dashboard.extremes_52w.lows_count} new lows recorded
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Benchmark Indices Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: "14px" }}>
        {currentIndices.map((idx) => {
          const isUnavailable = idx.status === "UNAVAILABLE" || idx.value === "UNAVAILABLE";
          const isEstimated = idx.data_mode === "ESTIMATED" || idx.is_estimated;
          const isPos = idx.change_pct !== null && idx.change_pct !== undefined ? idx.change_pct >= 0 : false;
          return (
            <div
              key={idx.symbol}
              style={{
                background: "#111925",
                border: "1px solid #202d40",
                borderRadius: "10px",
                padding: "16px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", color: "#9aa8ba", fontSize: "11px", fontWeight: 700 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span>{idx.name}</span>
                  {isEstimated && (
                    <span
                      style={{
                        padding: "1px 5px",
                        borderRadius: "3px",
                        background: "rgba(245, 158, 11, 0.15)",
                        color: "#f59e0b",
                        fontSize: "9px",
                        fontWeight: 700,
                        border: "1px solid rgba(245, 158, 11, 0.3)",
                      }}
                      title="Estimated from component basket; not a direct live index feed."
                    >
                      ESTIMATED
                    </span>
                  )}
                  {isUnavailable && (
                    <span
                      style={{
                        padding: "1px 5px",
                        borderRadius: "3px",
                        background: "rgba(148, 163, 184, 0.15)",
                        color: "#94a3b8",
                        fontSize: "9px",
                        fontWeight: 700,
                        border: "1px solid rgba(148, 163, 184, 0.3)",
                      }}
                      title="Official exchange options-implied feed required"
                    >
                      UNAVAILABLE
                    </span>
                  )}
                </div>

                {!isUnavailable && idx.change_pct !== null && idx.change_pct !== undefined ? (
                  <span
                    style={{
                      padding: "2px 6px",
                      borderRadius: "4px",
                      background: isPos ? "rgba(38,199,139,0.15)" : "rgba(239,102,118,0.15)",
                      color: isPos ? "#26c78b" : "#ef6676",
                      fontSize: "11px",
                    }}
                  >
                    {isPos ? "+" : ""}{idx.change_pct.toFixed(2)}%
                  </span>
                ) : (
                  <span style={{ fontSize: "10px", color: "#64748b" }}>FEED REQUIRED</span>
                )}
              </div>
              <div style={{ fontSize: "22px", fontWeight: 700, margin: "10px 0 6px", color: isUnavailable ? "#94a3b8" : "#fff" }}>
                {idx.value}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", color: "#64748b" }}>
                <span>H: {idx.high || "—"}</span>
                <span>L: {idx.low || "—"}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Sector Intelligence & Rotation Matrix */}
      <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <h3 style={{ fontSize: "15px", fontWeight: 700, margin: "0 0 4px", color: "#f1f5f9" }}>
              Sector Rotation & Relative Performance
            </h3>
            <p style={{ margin: 0, fontSize: "12px", color: "#8c9bb0" }}>
              Quadrant positioning grounded in relative strength vs NIFTY benchmark and directional momentum.
            </p>
          </div>

          {/* Quadrant Filters */}
          <div style={{ display: "flex", gap: "6px", background: "#0b121c", padding: "3px", borderRadius: "6px", border: "1px solid #1e293b" }}>
            {[
              { id: "ALL", label: "All Sectors" },
              { id: "LEADING", label: "Leading" },
              { id: "WEAKENING", label: "Weakening" },
              { id: "LAGGING", label: "Lagging" },
              { id: "IMPROVING", label: "Improving" },
            ].map((q) => (
              <button
                key={q.id}
                onClick={() => setQuadrantFilter(q.id)}
                style={{
                  background: quadrantFilter === q.id ? "#1e293b" : "transparent",
                  color: quadrantFilter === q.id ? "#38bdf8" : "#94a3b8",
                  border: "none",
                  padding: "5px 10px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {q.label}
              </button>
            ))}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "12px" }}>
          {filteredSectors.map((sec) => {
            const isLeading = sec.rotation_quadrant === "LEADING";
            const isLagging = sec.rotation_quadrant === "LAGGING";
            const isWeakening = sec.rotation_quadrant === "WEAKENING";
            const isImproving = sec.rotation_quadrant === "IMPROVING";

            const badgeBg = isLeading ? "rgba(38,199,139,0.15)" : (isWeakening ? "rgba(245,158,11,0.15)" : (isLagging ? "rgba(239,68,68,0.15)" : "rgba(59,130,246,0.15)"));
            const badgeColor = isLeading ? "#26c78b" : (isWeakening ? "#f59e0b" : (isLagging ? "#ef4444" : "#3b82f6"));

            return (
              <div
                key={sec.sector}
                onClick={() => setSectorFilter(sectorFilter === sec.sector ? "ALL" : sec.sector)}
                style={{
                  background: sectorFilter === sec.sector ? "#172338" : "#0d1522",
                  border: sectorFilter === sec.sector ? "1px solid #3b82f6" : "1px solid #1f2b3e",
                  borderRadius: "8px",
                  padding: "14px",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                  <span style={{ fontSize: "13px", fontWeight: 700, color: "#f8fafc" }}>{sec.sector}</span>
                  <span
                    style={{
                      fontSize: "10px",
                      fontWeight: 700,
                      padding: "2px 6px",
                      borderRadius: "4px",
                      background: badgeBg,
                      color: badgeColor,
                    }}
                  >
                    {sec.rotation_quadrant}
                  </span>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "8px" }}>
                  <span style={{ fontSize: "18px", fontWeight: 800, color: sec.positive ? "#26c78b" : "#ef6676" }}>
                    {sec.positive ? "+" : ""}{sec.average_change_pct.toFixed(2)}%
                  </span>
                  <span style={{ fontSize: "11px", color: sec.relative_strength_vs_market >= 0 ? "#38bdf8" : "#f43f5e" }}>
                    RS vs NIFTY: {sec.relative_strength_vs_market >= 0 ? "+" : ""}{sec.relative_strength_vs_market.toFixed(2)}%
                  </span>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "#64748b", marginBottom: "6px" }}>
                  <span>Breadth: {sec.breadth_pct}% ({sec.advances}A / {sec.declines}D)</span>
                  <span>RVOL: {sec.average_rvol}x</span>
                </div>

                <div style={{ fontSize: "10px", color: "#94a3b8", display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "#26c78b" }}>Top: {sec.strongest_stock.symbol} ({sec.strongest_stock.change_pct}%)</span>
                  <span style={{ color: "#ef6676" }}>Lag: {sec.weakest_stock.symbol} ({sec.weakest_stock.change_pct}%)</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Upgraded Market Movers & Price–Volume Confluence Intelligence (Phase 14) */}
      <div style={{ marginTop: "24px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <h2 style={{ fontSize: "18px", fontWeight: 700, color: "#f8fafc", margin: "0 0 4px 0" }}>
              Market Movers & Price–Volume Confluence Intelligence
            </h2>
            <p style={{ fontSize: "12px", color: "#64748b", margin: 0 }}>
              Institutional momentum, volume surges, and automated price–volume confluence intersections
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              onClick={() => setMoversViewTab("confluence")}
              style={{
                background: moversViewTab === "confluence" ? "#1e293b" : "transparent",
                color: moversViewTab === "confluence" ? "#38bdf8" : "#94a3b8",
                border: moversViewTab === "confluence" ? "1px solid #38bdf8" : "1px solid #334155",
                padding: "6px 14px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              ⇅ Institutional Movers & Confluence
            </button>
            <button
              onClick={() => setMoversViewTab("52w")}
              style={{
                background: moversViewTab === "52w" ? "#1e293b" : "transparent",
                color: moversViewTab === "52w" ? "#38bdf8" : "#94a3b8",
                border: moversViewTab === "52w" ? "1px solid #38bdf8" : "1px solid #334155",
                padding: "6px 14px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              ★ 52-Week Extremes
            </button>
          </div>
        </div>

        {moversViewTab === "confluence" ? (
          <MarketMoversConfluenceView
            onSelectStock={onSelectStock}
            initialUniverse={universe}
          />
        ) : (
          <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
              <div style={{ display: "flex", gap: "8px" }}>
                {[
                  { id: "near_highs", label: "Near 52W Highs" },
                  { id: "new_highs", label: "New 52W Highs" },
                  { id: "near_lows", label: "Near 52W Lows" },
                  { id: "new_lows", label: "New 52W Lows" },
                ].map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setExtremesTab(t.id as any)}
                    style={{
                      background: extremesTab === t.id ? "#1e293b" : "transparent",
                      color: extremesTab === t.id ? "#38bdf8" : "#94a3b8",
                      border: extremesTab === t.id ? "1px solid #334155" : "1px solid transparent",
                      padding: "6px 14px",
                      borderRadius: "6px",
                      fontSize: "12px",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    {t.label}
                  </button>
                ))}
              </div>

              {sectorFilter !== "ALL" && (
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "11px", color: "#94a3b8" }}>Filtering by Sector: </span>
                  <span
                    style={{
                      fontSize: "11px",
                      padding: "3px 8px",
                      borderRadius: "4px",
                      background: "#2563eb",
                      color: "#fff",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                    onClick={() => setSectorFilter("ALL")}
                  >
                    {sectorFilter} ✕
                  </span>
                </div>
              )}
            </div>

            {/* Table View */}
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #1e293b", color: "#64748b", fontSize: "11px", textTransform: "uppercase" }}>
                    <th style={{ padding: "10px 12px" }}>Symbol</th>
                    <th style={{ padding: "10px 12px" }}>Sector</th>
                    <th style={{ padding: "10px 12px", textAlign: "right" }}>Price (₹)</th>
                    <th style={{ padding: "10px 12px", textAlign: "right" }}>Change %</th>
                    <th style={{ padding: "10px 12px", textAlign: "right" }}>52W High</th>
                    <th style={{ padding: "10px 12px", textAlign: "right" }}>52W Low</th>
                    <th style={{ padding: "10px 12px", textAlign: "center" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {displayedExtremesStocks.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ textAlign: "center", padding: "30px", color: "#64748b", fontSize: "13px" }}>
                        No stocks matching the current 52-week extreme criteria.
                      </td>
                    </tr>
                  ) : (
                    displayedExtremesStocks.map((stock) => {
                      const isPos = stock.daily_change_pct >= 0;
                      return (
                        <tr
                          key={stock.symbol}
                          style={{
                            borderBottom: "1px solid #16202e",
                            transition: "background 0.15s ease",
                          }}
                          onMouseEnter={(e) => (e.currentTarget.style.background = "#162233")}
                          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                        >
                          <td style={{ padding: "12px" }}>
                            <div style={{ fontWeight: 700, color: "#f8fafc", fontSize: "13px" }}>{stock.symbol}</div>
                            <div style={{ fontSize: "11px", color: "#64748b" }}>{stock.company_name}</div>
                          </td>
                          <td style={{ padding: "12px", fontSize: "12px", color: "#94a3b8" }}>{stock.sector}</td>
                          <td style={{ padding: "12px", textAlign: "right", fontSize: "13px", fontWeight: 700, color: "#f8fafc" }}>
                            ₹{stock.close.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                          </td>
                          <td style={{ padding: "12px", textAlign: "right" }}>
                            <span
                              style={{
                                padding: "3px 8px",
                                borderRadius: "4px",
                                fontSize: "12px",
                                fontWeight: 700,
                                background: isPos ? "rgba(38,199,139,0.15)" : "rgba(239,102,118,0.15)",
                                color: isPos ? "#26c78b" : "#ef6676",
                              }}
                            >
                              {isPos ? "+" : ""}{stock.daily_change_pct.toFixed(2)}%
                            </span>
                          </td>
                          <td style={{ padding: "12px", textAlign: "right", fontSize: "12px", color: "#38bdf8" }}>
                            {stock.week_52_high ? `₹${stock.week_52_high.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "—"}
                          </td>
                          <td style={{ padding: "12px", textAlign: "right", fontSize: "12px", color: "#f43f5e" }}>
                            {stock.week_52_low ? `₹${stock.week_52_low.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "—"}
                          </td>
                          <td style={{ padding: "12px", textAlign: "center" }}>
                            <button
                              onClick={() => onSelectStock(stock.symbol, "chart")}
                              style={{
                                background: "#1e293b",
                                color: "#38bdf8",
                                border: "1px solid #334155",
                                padding: "4px 10px",
                                borderRadius: "4px",
                                fontSize: "11px",
                                fontWeight: 600,
                                cursor: "pointer",
                              }}
                            >
                              Analyze Chart
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

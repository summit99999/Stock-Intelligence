import { apiFetch } from "../api/client";
import React, { useState, useEffect } from "react";

interface XRayStock {
  symbol: string;
  company_name: string;
  sector: string;
  price: number;
  change_pct: number;
  bullish_score: number;
  bearish_score: number;
  net_directional_strength: number;
  rvol: number;
  adr_50: number;
  norm_adr_move: number;
  is_choppy: boolean;
  choppiness_ratio: number;
  ob_proximity: string;
  sweep_status: string;
  score_components?: {
    move_from_open: number;
    norm_adr_move_pct: number;
    rvol: number;
    is_choppy: boolean;
    bullish_ma_align: boolean;
    bearish_ma_align: boolean;
  };
}

interface SectorRanking {
  sector: string;
  average_net_strength: number;
  stock_count: number;
  bias: "BULLISH" | "BEARISH" | "NEUTRAL";
}

interface MarketXRayData {
  universe_evaluated: number;
  market_breadth: {
    advances: number;
    declines: number;
    unchanged: number;
    average_net_score: number;
    overall_regime: string;
  };
  bullish_board: XRayStock[];
  bearish_board: XRayStock[];
  choppy_stocks: XRayStock[];
  sector_rankings: SectorRanking[];
}

interface MarketXRayViewProps {
  onSelectSymbol: (symbol: string) => void;
  onNavigate: (view: string) => void;
}

export default function MarketXRayView({ onSelectSymbol, onNavigate }: MarketXRayViewProps) {
  const [data, setData] = useState<MarketXRayData | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeBoard, setActiveBoard] = useState<"BULLISH" | "BEARISH" | "CHOPPY" | "SECTORS">("BULLISH");
  const [sectorFilter, setSectorFilter] = useState("ALL");
  const [lastRefreshed, setLastRefreshed] = useState<string>("");

  useEffect(() => {
    loadXRay();
    const interval = setInterval(loadXRay, 60000); // 1-minute auto refresh
    return () => clearInterval(interval);
  }, []);

  const loadXRay = async () => {
    setLoading(true);
    try {
      const res = await apiFetch("/api/smc/xray?limit=50");
      if (res.ok) {
        const json = await res.json();
        setData(json);
        setLastRefreshed(new Date().toLocaleTimeString());
      }
    } catch (e) {
      console.error("Failed to load Market X-Ray data:", e);
    } finally {
      setLoading(false);
    }
  };

  const filteredBullish = (data?.bullish_board || []).filter(
    (s) => sectorFilter === "ALL" || s.sector === sectorFilter
  );
  const filteredBearish = (data?.bearish_board || []).filter(
    (s) => sectorFilter === "ALL" || s.sector === sectorFilter
  );

  return (
    <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: "20px", color: "#e2e8f0" }}>
      {/* Top Banner / Breadth */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "14px" }}>
        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af" }}>MARKET REGIME</div>
          <div style={{ fontSize: "18px", fontWeight: "700", marginTop: "4px", color: "#38bdf8" }}>
            {data?.market_breadth?.overall_regime || "EVALUATING..."}
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>
            Avg Net Score: {data?.market_breadth?.average_net_score ?? 0}
          </div>
        </div>

        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af" }}>MARKET BREADTH</div>
          <div style={{ fontSize: "20px", fontWeight: "700", marginTop: "4px" }}>
            <span style={{ color: "#26c78b" }}>{data?.market_breadth?.advances ?? 0} Adv</span>
            <span style={{ color: "#6b7280", margin: "0 6px" }}>/</span>
            <span style={{ color: "#ef6676" }}>{data?.market_breadth?.declines ?? 0} Dec</span>
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>
            Universe: {data?.universe_evaluated ?? 0} stocks
          </div>
        </div>

        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af" }}>CHOPPY / RANGEBOUND</div>
          <div style={{ fontSize: "20px", fontWeight: "700", marginTop: "4px", color: "#f59e0b" }}>
            {data?.choppy_stocks?.length ?? 0} Stocks
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>
            Penalized for large wicks & small body
          </div>
        </div>

        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
          <button
            onClick={loadXRay}
            disabled={loading}
            style={{
              background: "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              padding: "10px 14px",
              fontWeight: "600",
              fontSize: "12px",
              cursor: "pointer",
            }}
          >
            {loading ? "Scanning Universe..." : "↻ Refresh X-Ray"}
          </button>
          <div style={{ fontSize: "10px", color: "#64748b", marginTop: "4px", textAlign: "center" }}>
            Last sync: {lastRefreshed || "Just now"} · 1m auto
          </div>
        </div>
      </div>

      {/* Navigation Tabs between Boards */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", background: "#111827", padding: "10px 16px", borderRadius: "8px", border: "1px solid #1f2937" }}>
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={() => setActiveBoard("BULLISH")}
            style={{
              background: activeBoard === "BULLISH" ? "#153329" : "#1f2937",
              color: activeBoard === "BULLISH" ? "#45d7a1" : "#9ca3af",
              border: `1px solid ${activeBoard === "BULLISH" ? "#26c78b" : "transparent"}`,
              borderRadius: "6px",
              padding: "8px 16px",
              fontSize: "12px",
              fontWeight: "700",
              cursor: "pointer",
            }}
          >
            ▲ BULLISH BOARD ({filteredBullish.length})
          </button>

          <button
            onClick={() => setActiveBoard("BEARISH")}
            style={{
              background: activeBoard === "BEARISH" ? "#381a1f" : "#1f2937",
              color: activeBoard === "BEARISH" ? "#ef6676" : "#9ca3af",
              border: `1px solid ${activeBoard === "BEARISH" ? "#ef6676" : "transparent"}`,
              borderRadius: "6px",
              padding: "8px 16px",
              fontSize: "12px",
              fontWeight: "700",
              cursor: "pointer",
            }}
          >
            ▼ BEARISH BOARD ({filteredBearish.length})
          </button>

          <button
            onClick={() => setActiveBoard("CHOPPY")}
            style={{
              background: activeBoard === "CHOPPY" ? "#332a15" : "#1f2937",
              color: activeBoard === "CHOPPY" ? "#f59e0b" : "#9ca3af",
              border: `1px solid ${activeBoard === "CHOPPY" ? "#f59e0b" : "transparent"}`,
              borderRadius: "6px",
              padding: "8px 16px",
              fontSize: "12px",
              fontWeight: "700",
              cursor: "pointer",
            }}
          >
            ⚡ CHOPPY STOCKS ({data?.choppy_stocks?.length ?? 0})
          </button>

          <button
            onClick={() => setActiveBoard("SECTORS")}
            style={{
              background: activeBoard === "SECTORS" ? "#1e293b" : "#1f2937",
              color: activeBoard === "SECTORS" ? "#38bdf8" : "#9ca3af",
              border: `1px solid ${activeBoard === "SECTORS" ? "#38bdf8" : "transparent"}`,
              borderRadius: "6px",
              padding: "8px 16px",
              fontSize: "12px",
              fontWeight: "700",
              cursor: "pointer",
            }}
          >
            🏢 SECTOR STRENGTH ({data?.sector_rankings?.length ?? 0})
          </button>
        </div>

        {/* Sector Filter */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <span style={{ fontSize: "11px", color: "#9ca3af" }}>SECTOR:</span>
          <select
            value={sectorFilter}
            onChange={(e) => setSectorFilter(e.target.value)}
            style={{
              background: "#0d1117",
              border: "1px solid #30363d",
              borderRadius: "6px",
              padding: "6px 10px",
              color: "#f8fafc",
              fontSize: "12px",
            }}
          >
            <option value="ALL">All Sectors</option>
            {Array.from(new Set(data?.sector_rankings?.map((s) => s.sector) || [])).map((sec) => (
              <option key={sec} value={sec}>{sec}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Main Board Table */}
      {(activeBoard === "BULLISH" || activeBoard === "BEARISH") && (
        <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "12px" }}>
            <thead>
              <tr style={{ background: "#1a2234", borderBottom: "1px solid #2d3748", color: "#9ca3af", fontSize: "11px" }}>
                <th style={{ padding: "12px 16px" }}>RANK & TICKER</th>
                <th style={{ padding: "12px 16px" }}>SECTOR</th>
                <th style={{ padding: "12px 16px", textAlign: "right" }}>PRICE (₹)</th>
                <th style={{ padding: "12px 16px", textAlign: "right" }}>DAY CHANGE %</th>
                <th style={{ padding: "12px 16px", textAlign: "right" }}>% ADR(50) MOVE</th>
                <th style={{ padding: "12px 16px", textAlign: "right" }}>RVOL</th>
                <th style={{ padding: "12px 16px", textAlign: "center" }}>
                  {activeBoard === "BULLISH" ? "BULLISH STRENGTH" : "BEARISH STRENGTH"}
                </th>
                <th style={{ padding: "12px 16px" }}>SMC PROXIMITY & SWEEP</th>
                <th style={{ padding: "12px 16px", textAlign: "center" }}>ACTIONS</th>
              </tr>
            </thead>
            <tbody>
              {(activeBoard === "BULLISH" ? filteredBullish : filteredBearish).map((stk, idx) => {
                const score = activeBoard === "BULLISH" ? stk.bullish_score : stk.bearish_score;
                const isPos = stk.change_pct >= 0;
                return (
                  <tr
                    key={stk.symbol}
                    style={{ borderBottom: "1px solid #1e293b", transition: "background 0.15s ease" }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "#172033")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    <td style={{ padding: "12px 16px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span style={{ fontSize: "11px", color: "#64748b", fontWeight: "700" }}>#{idx + 1}</span>
                        <div>
                          <strong style={{ color: "#f8fafc", fontSize: "13px" }}>{stk.symbol}</strong>
                          <div style={{ fontSize: "11px", color: "#64748b" }}>{stk.company_name}</div>
                        </div>
                      </div>
                    </td>

                    <td style={{ padding: "12px 16px" }}>
                      <span style={{ background: "#1e293b", color: "#93c5fd", padding: "3px 8px", borderRadius: "4px", fontSize: "10px" }}>
                        {stk.sector}
                      </span>
                    </td>

                    <td style={{ padding: "12px 16px", textAlign: "right", fontWeight: "700", color: "#f8fafc" }}>
                      ₹{stk.price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                    </td>

                    <td style={{ padding: "12px 16px", textAlign: "right", fontWeight: "700", color: isPos ? "#26c78b" : "#ef6676" }}>
                      {isPos ? "+" : ""}{stk.change_pct.toFixed(2)}%
                    </td>

                    <td style={{ padding: "12px 16px", textAlign: "right", fontWeight: "600", color: stk.norm_adr_move >= 0 ? "#26c78b" : "#ef6676" }}>
                      {stk.norm_adr_move > 0 ? "+" : ""}{stk.norm_adr_move}%
                      <div style={{ fontSize: "10px", color: "#64748b", fontWeight: "normal" }}>ADR ₹{stk.adr_50}</div>
                    </td>

                    <td style={{ padding: "12px 16px", textAlign: "right", fontWeight: "600", color: stk.rvol >= 1.5 ? "#26c78b" : "#cbd5e1" }}>
                      {stk.rvol}x
                    </td>

                    <td style={{ padding: "12px 16px", textAlign: "center" }}>
                      <div style={{ display: "inline-block", minWidth: "70px", padding: "4px 8px", borderRadius: "6px", background: activeBoard === "BULLISH" ? "rgba(38,199,139,0.15)" : "rgba(239,102,118,0.15)", border: `1px solid ${activeBoard === "BULLISH" ? "#26c78b" : "#ef6676"}` }}>
                        <strong style={{ fontSize: "13px", color: activeBoard === "BULLISH" ? "#26c78b" : "#ef6676" }}>
                          {score}/100
                        </strong>
                      </div>
                    </td>

                    <td style={{ padding: "12px 16px" }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
                        <span style={{ fontSize: "11px", color: stk.ob_proximity.startsWith("AT_") ? "#f59e0b" : "#94a3b8" }}>
                          OB: {stk.ob_proximity}
                        </span>
                        {stk.sweep_status !== "NONE" && (
                          <span style={{ fontSize: "10px", color: "#38bdf8", fontWeight: "bold" }}>
                            ⚡ {stk.sweep_status}
                          </span>
                        )}
                      </div>
                    </td>

                    <td style={{ padding: "12px 16px", textAlign: "center" }}>
                      <div style={{ display: "flex", gap: "6px", justifyContent: "center" }}>
                        <button
                          onClick={() => {
                            onSelectSymbol(stk.symbol);
                            onNavigate("Technical Analysis");
                          }}
                          style={{ background: "#1e293b", color: "#38bdf8", border: "1px solid #334155", borderRadius: "4px", padding: "4px 8px", fontSize: "10px", cursor: "pointer" }}
                        >
                          Chart
                        </button>
                        <button
                          onClick={() => {
                            onSelectSymbol(stk.symbol);
                            onNavigate("Smart Money Concepts");
                          }}
                          style={{ background: "#1e293b", color: "#a855f7", border: "1px solid #334155", borderRadius: "4px", padding: "4px 8px", fontSize: "10px", cursor: "pointer" }}
                        >
                          SMC
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {(activeBoard === "BULLISH" ? filteredBullish : filteredBearish).length === 0 && (
                <tr>
                  <td colSpan={9} style={{ textAlign: "center", padding: "32px", color: "#64748b" }}>
                    No stocks match the selected board and sector filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Choppy Stocks Board */}
      {activeBoard === "CHOPPY" && (
        <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
          <h3 style={{ margin: "0 0 12px 0", fontSize: "15px", color: "#f8fafc" }}>
            Choppy / Non-Directional Stocks ({data?.choppy_stocks?.length ?? 0})
          </h3>
          <p style={{ margin: "0 0 16px 0", fontSize: "12px", color: "#94a3b8" }}>
            These stocks are exhibiting wide range noise with little net directional displacement (high-to-low wick span &gt; 3.2× net body). Avoid breakout entries until clean expansion forms.
          </p>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: "12px" }}>
            {data?.choppy_stocks?.map((stk) => (
              <div
                key={stk.symbol}
                style={{ background: "#0d1117", border: "1px solid #1e293b", borderRadius: "8px", padding: "14px" }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong>{stk.symbol}</strong>
                  <span style={{ fontSize: "11px", color: "#f59e0b", background: "rgba(245,158,11,0.15)", padding: "2px 6px", borderRadius: "4px" }}>
                    Choppiness: {stk.choppiness_ratio}x
                  </span>
                </div>
                <div style={{ fontSize: "11px", color: "#64748b", marginTop: "4px" }}>{stk.company_name} · {stk.sector}</div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: "10px", fontSize: "12px" }}>
                  <span>Price: ₹{stk.price}</span>
                  <span style={{ color: stk.change_pct >= 0 ? "#26c78b" : "#ef6676" }}>{stk.change_pct}%</span>
                </div>
              </div>
            ))}
            {data?.choppy_stocks?.length === 0 && (
              <div style={{ color: "#64748b", fontSize: "12px" }}>No choppy stocks currently flagged in the universe.</div>
            )}
          </div>
        </div>
      )}

      {/* Sector Rankings Board */}
      {activeBoard === "SECTORS" && (
        <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
          <h3 style={{ margin: "0 0 16px 0", fontSize: "15px", color: "#f8fafc" }}>
            Sector Relative Strength & Directional Bias
          </h3>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: "14px" }}>
            {data?.sector_rankings?.map((sec) => (
              <div
                key={sec.sector}
                style={{
                  background: "#0d1117",
                  border: `1px solid ${sec.bias === "BULLISH" ? "rgba(38,199,139,0.3)" : (sec.bias === "BEARISH" ? "rgba(239,102,118,0.3)" : "#1e293b")}`,
                  borderRadius: "8px",
                  padding: "16px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong style={{ fontSize: "14px", color: "#f8fafc" }}>{sec.sector}</strong>
                  <span style={{
                    fontSize: "10px",
                    fontWeight: "bold",
                    padding: "3px 8px",
                    borderRadius: "4px",
                    background: sec.bias === "BULLISH" ? "rgba(38,199,139,0.2)" : (sec.bias === "BEARISH" ? "rgba(239,102,118,0.2)" : "rgba(100,116,139,0.2)"),
                    color: sec.bias === "BULLISH" ? "#26c78b" : (sec.bias === "BEARISH" ? "#ef6676" : "#94a3b8"),
                  }}>
                    {sec.bias}
                  </span>
                </div>

                <div style={{ fontSize: "20px", fontWeight: "700", marginTop: "8px", color: sec.average_net_strength >= 0 ? "#26c78b" : "#ef6676" }}>
                  {sec.average_net_strength > 0 ? "+" : ""}{sec.average_net_strength}
                </div>
                <div style={{ fontSize: "11px", color: "#64748b", marginTop: "2px" }}>
                  Basket: {sec.stock_count} stocks tracked
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

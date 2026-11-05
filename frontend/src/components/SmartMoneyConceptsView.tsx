import React, { useState, useEffect } from "react";

interface SwingPivot {
  type: "SWING_HIGH" | "SWING_LOW";
  label: "HH" | "HL" | "LH" | "LL";
  price: number;
  timestamp: string;
}

interface StructuralBreak {
  bar_index: number;
  timestamp: string;
  type: "BOS" | "CHoCH";
  direction: "BULLISH" | "BEARISH";
  broken_level: number;
  breakout_price: number;
  swing_timestamp: string;
}

interface OrderBlock {
  id: string;
  direction: "BULLISH" | "BEARISH";
  candle_index: number;
  timestamp: string;
  zone_high: number;
  zone_low: number;
  invalidation_level: number;
  displacement_atr: number;
  volume_expansion_ratio: number;
  associated_break: "BOS" | "CHoCH";
  status: "FRESH" | "TESTED" | "MITIGATED" | "INVALIDATED";
  retest_count: number;
  mitigation_pct: number;
}

interface FairValueGap {
  id: string;
  direction: "BULLISH" | "BEARISH";
  bar_index: number;
  timestamp: string;
  zone_high: number;
  zone_low: number;
  gap_size: number;
  fill_pct: number;
  is_filled: boolean;
  status: "UNFILLED" | "PARTIAL" | "FILLED";
}

interface SupplyDemandZone {
  id: string;
  type: "DEMAND" | "SUPPLY";
  pattern: "DBR" | "RBD" | "RBR" | "DBD";
  zone_high: number;
  zone_low: number;
  timestamp: string;
  tested: boolean;
}

interface LiquiditySweep {
  bar_index: number;
  timestamp: string;
  level_name: string;
  level_price: number;
  direction: string;
  sweep_price: number;
  close: number;
}

interface EqualLevel {
  price: number;
  bars: string[];
  type: string;
}

interface ScoreComponent {
  factor: string;
  weight: number;
  score: number;
  detail: string;
}

interface SMCAnalysisData {
  symbol: string;
  company_name: string;
  sector?: string;
  current_price: number;
  bars_evaluated: number;
  market_structure: {
    trend: "BULLISH" | "BEARISH" | "NEUTRAL";
    swings: SwingPivot[];
    breaks: StructuralBreak[];
    last_bos?: StructuralBreak | null;
    last_choch?: StructuralBreak | null;
  };
  order_blocks: {
    total_detected: number;
    bullish_active_count: number;
    bearish_active_count: number;
    all_zones: OrderBlock[];
  };
  fair_value_gaps: {
    total: number;
    unfilled_count: number;
    gaps: FairValueGap[];
  };
  supply_demand: SupplyDemandZone[];
  liquidity: {
    equal_highs: EqualLevel[];
    equal_lows: EqualLevel[];
    key_levels: {
      PDH: number;
      PDL: number;
      PWH: number;
      PWL: number;
    };
    sweeps: LiquiditySweep[];
  };
  premium_discount: {
    swing_high: number;
    swing_low: number;
    equilibrium: number;
    current_price: number;
    percentage_in_range: number;
    zone: string;
  };
  setup_score: {
    total_score: number;
    rating: string;
    active_order_block?: OrderBlock | null;
    components: ScoreComponent[];
  };
}

interface SmartMoneyConceptsViewProps {
  symbol: string;
  onSymbolChange: (symbol: string) => void;
  onNavigate: (view: string) => void;
}

const QUICK_STOCKS = [
  "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
  "TATAMOTORS", "SBIN", "BHARTIARTL", "ITC", "LT"
];

export default function SmartMoneyConceptsView({
  symbol,
  onSymbolChange,
  onNavigate,
}: SmartMoneyConceptsViewProps) {
  const [data, setData] = useState<SMCAnalysisData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<
    "SCORECARD" | "ORDER_BLOCKS" | "STRUCTURE" | "FVG" | "LIQUIDITY" | "PREMIUM_DISCOUNT"
  >("SCORECARD");
  const [searchInput, setSearchInput] = useState("");

  useEffect(() => {
    loadSMC(symbol);
  }, [symbol]);

  const loadSMC = async (sym: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/smc/analysis/${sym.toUpperCase()}?limit=120`);
      if (!res.ok) {
        throw new Error(`Failed to load SMC analysis for ${sym}`);
      }
      const json = await res.json();
      if (json.error) {
        throw new Error(json.error);
      }
      setData(json);
    } catch (e: any) {
      console.error(e);
      setError(e.message || "Failed to analyze Smart Money Concepts");
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      onSymbolChange(searchInput.trim().toUpperCase());
      setSearchInput("");
    }
  };

  const trend = data?.market_structure?.trend || "NEUTRAL";
  const trendColor = trend === "BULLISH" ? "#22c55e" : trend === "BEARISH" ? "#ef4444" : "#94a3b8";

  return (
    <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: "20px", color: "#e2e8f0" }}>
      {/* Top Header Bar & Symbol Selector */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          background: "#111827",
          padding: "16px 20px",
          borderRadius: "10px",
          border: "1px solid #1f2937",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <h2 style={{ margin: 0, fontSize: "20px", fontWeight: "800", color: "#fff" }}>
                {data?.symbol || symbol}
              </h2>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: "700",
                  padding: "3px 8px",
                  borderRadius: "4px",
                  background: `${trendColor}25`,
                  color: trendColor,
                }}
              >
                {trend} STRUCTURE
              </span>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: "700",
                  padding: "3px 8px",
                  borderRadius: "4px",
                  background: "#1e293b",
                  color: "#94a3b8",
                }}
              >
                {data?.sector || "NSE"}
              </span>
            </div>
            <div style={{ fontSize: "12px", color: "#9ca3af", marginTop: "4px" }}>
              {data?.company_name} · LTP:{" "}
              <strong style={{ color: "#fff", fontSize: "13px" }}>
                ₹{data?.current_price?.toFixed(2) || "0.00"}
              </strong>{" "}
              · {data?.bars_evaluated || 0} bars confirmed
            </div>
          </div>

          {/* Quick Stock Pills */}
          <div style={{ display: "flex", gap: "6px", marginLeft: "10px", flexWrap: "wrap" }}>
            {QUICK_STOCKS.map((s) => (
              <button
                key={s}
                onClick={() => onSymbolChange(s)}
                style={{
                  background: s === symbol ? "#2563eb" : "#1f2937",
                  color: s === symbol ? "#fff" : "#9ca3af",
                  border: "none",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: "600",
                  cursor: "pointer",
                }}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Search & Actions */}
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <form onSubmit={handleSearchSubmit} style={{ display: "flex" }}>
            <input
              type="text"
              placeholder="Change symbol (e.g. INFY)..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              style={{
                background: "#1f2937",
                color: "#fff",
                border: "1px solid #374151",
                borderTopLeftRadius: "6px",
                borderBottomLeftRadius: "6px",
                padding: "6px 12px",
                fontSize: "12px",
                outline: "none",
              }}
            />
            <button
              type="submit"
              style={{
                background: "#374151",
                color: "#fff",
                border: "none",
                borderTopRightRadius: "6px",
                borderBottomRightRadius: "6px",
                padding: "6px 12px",
                fontSize: "12px",
                cursor: "pointer",
              }}
            >
              Go
            </button>
          </form>

          <button
            onClick={() => onNavigate("Technical Analysis")}
            style={{
              background: "#1e293b",
              color: "#38bdf8",
              border: "1px solid #0284c7",
              borderRadius: "6px",
              padding: "6px 12px",
              fontSize: "12px",
              fontWeight: "600",
              cursor: "pointer",
            }}
          >
            Chart View
          </button>
          <button
            onClick={() => onNavigate("SMC Backtest")}
            style={{
              background: "#1e293b",
              color: "#f59e0b",
              border: "1px solid #d97706",
              borderRadius: "6px",
              padding: "6px 12px",
              fontSize: "12px",
              fontWeight: "600",
              cursor: "pointer",
            }}
          >
            Backtest
          </button>
        </div>
      </div>

      {loading && (
        <div style={{ textAlign: "center", padding: "40px", color: "#38bdf8" }}>
          Analyzing Smart Money Concepts & structural liquidity for {symbol}...
        </div>
      )}

      {error && !loading && (
        <div
          style={{
            background: "#450a0a",
            border: "1px solid #991b1b",
            color: "#fca5a5",
            padding: "16px",
            borderRadius: "8px",
          }}
        >
          {error}
        </div>
      )}

      {data && !loading && (
        <>
          {/* Top Confluence Summary Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "14px" }}>
            {/* Setup Score */}
            <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>INSTITUTIONAL SETUP SCORE</div>
              <div style={{ display: "flex", alignItems: "baseline", gap: "8px", marginTop: "4px" }}>
                <span
                  style={{
                    fontSize: "26px",
                    fontWeight: "800",
                    color:
                      data.setup_score.total_score >= 75
                        ? "#22c55e"
                        : data.setup_score.total_score >= 55
                        ? "#f59e0b"
                        : "#ef4444",
                  }}
                >
                  {data.setup_score.total_score}
                </span>
                <span style={{ fontSize: "12px", color: "#6b7280" }}>/ 100</span>
              </div>
              <div style={{ fontSize: "11px", fontWeight: "600", color: "#cbd5e1", marginTop: "4px" }}>
                {data.setup_score.rating}
              </div>
            </div>

            {/* Dealing Range Equilibrium */}
            <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>DEALING RANGE ZONE</div>
              <div style={{ fontSize: "16px", fontWeight: "700", marginTop: "4px", color: "#38bdf8" }}>
                {data.premium_discount.percentage_in_range}% in Range
              </div>
              <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "4px" }}>
                Eq (50%): ₹{data.premium_discount.equilibrium?.toFixed(2)}
              </div>
              <div style={{ fontSize: "10px", color: "#6b7280", marginTop: "2px" }}>
                {data.premium_discount.zone}
              </div>
            </div>

            {/* Active Order Blocks */}
            <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>ACTIVE ORDER BLOCKS</div>
              <div style={{ display: "flex", gap: "12px", marginTop: "4px", alignItems: "baseline" }}>
                <div>
                  <span style={{ fontSize: "20px", fontWeight: "700", color: "#22c55e" }}>
                    {data.order_blocks.bullish_active_count}
                  </span>{" "}
                  <span style={{ fontSize: "11px", color: "#9ca3af" }}>Bullish</span>
                </div>
                <div>
                  <span style={{ fontSize: "20px", fontWeight: "700", color: "#ef4444" }}>
                    {data.order_blocks.bearish_active_count}
                  </span>{" "}
                  <span style={{ fontSize: "11px", color: "#9ca3af" }}>Bearish</span>
                </div>
              </div>
              <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>
                Total detected: {data.order_blocks.total_detected}
              </div>
            </div>

            {/* Fair Value Gaps */}
            <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>FAIR VALUE GAPS (FVG)</div>
              <div style={{ fontSize: "20px", fontWeight: "700", marginTop: "4px", color: "#f59e0b" }}>
                {data.fair_value_gaps.unfilled_count}{" "}
                <span style={{ fontSize: "12px", color: "#9ca3af", fontWeight: "normal" }}>Unfilled</span>
              </div>
              <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>
                Total Gaps: {data.fair_value_gaps.total} · Imbalance Magnet
              </div>
            </div>
          </div>

          {/* Navigation Tabs */}
          <div style={{ display: "flex", borderBottom: "1px solid #1f2937", gap: "8px" }}>
            {[
              { id: "SCORECARD", label: "Institutional Scorecard (100 pts)" },
              { id: "ORDER_BLOCKS", label: `Order Blocks (${data.order_blocks.all_zones.length})` },
              { id: "STRUCTURE", label: `Structure & Breaks (${data.market_structure.breaks.length})` },
              { id: "FVG", label: `Fair Value Gaps (${data.fair_value_gaps.total})` },
              { id: "LIQUIDITY", label: `Liquidity & Sweeps (${data.liquidity.sweeps.length})` },
              { id: "PREMIUM_DISCOUNT", label: "Dealing Range (Equilibrium)" },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id as any)}
                style={{
                  background: "transparent",
                  border: "none",
                  borderBottom: activeTab === t.id ? "2px solid #38bdf8" : "2px solid transparent",
                  color: activeTab === t.id ? "#38bdf8" : "#9ca3af",
                  padding: "10px 14px",
                  fontSize: "13px",
                  fontWeight: "600",
                  cursor: "pointer",
                }}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Tab 1: Setup Scorecard */}
          {activeTab === "SCORECARD" && (
            <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px" }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: "16px", color: "#fff" }}>
                    Institutional Multi-Factor Setup Scorecard
                  </h3>
                  <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#9ca3af" }}>
                    Deterministic 100-point confluence model across 7 institutional factors.
                  </p>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: "24px", fontWeight: "800", color: "#22c55e" }}>
                    {data.setup_score.total_score} <span style={{ fontSize: "14px", color: "#6b7280" }}>/ 100</span>
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                {data.setup_score.components.map((comp) => {
                  const pct = (comp.score / comp.weight) * 100;
                  return (
                    <div
                      key={comp.factor}
                      style={{
                        background: "#1f2937",
                        padding: "12px 16px",
                        borderRadius: "8px",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <span style={{ fontWeight: "700", fontSize: "13px", color: "#fff" }}>{comp.factor}</span>
                          <span style={{ fontSize: "11px", color: "#9ca3af" }}>({comp.weight} pts max)</span>
                        </div>
                        <div style={{ fontWeight: "700", color: pct >= 80 ? "#22c55e" : pct >= 50 ? "#f59e0b" : "#ef4444" }}>
                          {comp.score} / {comp.weight}
                        </div>
                      </div>

                      <div style={{ height: "6px", background: "#374151", borderRadius: "3px", overflow: "hidden", marginBottom: "6px" }}>
                        <div
                          style={{
                            height: "100%",
                            width: `${pct}%`,
                            background: pct >= 80 ? "#22c55e" : pct >= 50 ? "#f59e0b" : "#ef4444",
                          }}
                        />
                      </div>
                      <div style={{ fontSize: "11px", color: "#9ca3af" }}>{comp.detail}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Tab 2: Order Blocks & Supply/Demand */}
          {activeTab === "ORDER_BLOCKS" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
              <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
                <h3 style={{ margin: "0 0 12px", fontSize: "16px", color: "#fff" }}>
                  Detected Order Blocks ({data.order_blocks.all_zones.length})
                </h3>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                    <thead>
                      <tr style={{ background: "#1f2937", color: "#9ca3af", textAlign: "left" }}>
                        <th style={{ padding: "8px 12px" }}>ID & CANDLE</th>
                        <th style={{ padding: "8px 12px" }}>DIRECTION</th>
                        <th style={{ padding: "8px 12px" }}>ZONE HIGH</th>
                        <th style={{ padding: "8px 12px" }}>ZONE LOW</th>
                        <th style={{ padding: "8px 12px" }}>INVALIDATION</th>
                        <th style={{ padding: "8px 12px" }}>DISPLACEMENT</th>
                        <th style={{ padding: "8px 12px" }}>VOLUME</th>
                        <th style={{ padding: "8px 12px" }}>BREAK</th>
                        <th style={{ padding: "8px 12px" }}>STATUS</th>
                        <th style={{ padding: "8px 12px" }}>MITIGATION</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.order_blocks.all_zones.map((ob) => {
                        const isBull = ob.direction === "BULLISH";
                        return (
                          <tr key={ob.id} style={{ borderBottom: "1px solid #1f2937" }}>
                            <td style={{ padding: "10px 12px" }}>
                              <strong>{ob.id}</strong>
                              <div style={{ fontSize: "10px", color: "#6b7280" }}>{ob.timestamp?.split("T")[0]}</div>
                            </td>
                            <td style={{ padding: "10px 12px" }}>
                              <span
                                style={{
                                  fontSize: "10px",
                                  fontWeight: "700",
                                  padding: "2px 6px",
                                  borderRadius: "4px",
                                  background: isBull ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)",
                                  color: isBull ? "#4ade80" : "#f87171",
                                }}
                              >
                                {ob.direction}
                              </span>
                            </td>
                            <td style={{ padding: "10px 12px" }}>₹{ob.zone_high.toFixed(2)}</td>
                            <td style={{ padding: "10px 12px" }}>₹{ob.zone_low.toFixed(2)}</td>
                            <td style={{ padding: "10px 12px", color: "#f87171" }}>₹{ob.invalidation_level.toFixed(2)}</td>
                            <td style={{ padding: "10px 12px", color: "#38bdf8" }}>{ob.displacement_atr}x ATR</td>
                            <td style={{ padding: "10px 12px", color: "#f59e0b" }}>{ob.volume_expansion_ratio}x Vol</td>
                            <td style={{ padding: "10px 12px" }}>{ob.associated_break}</td>
                            <td style={{ padding: "10px 12px" }}>
                              <span
                                style={{
                                  fontSize: "10px",
                                  fontWeight: "700",
                                  padding: "2px 6px",
                                  borderRadius: "4px",
                                  background:
                                    ob.status === "FRESH"
                                      ? "rgba(56, 189, 248, 0.2)"
                                      : ob.status === "TESTED"
                                      ? "rgba(245, 158, 11, 0.2)"
                                      : "rgba(107, 114, 128, 0.2)",
                                  color:
                                    ob.status === "FRESH"
                                      ? "#38bdf8"
                                      : ob.status === "TESTED"
                                      ? "#f59e0b"
                                      : "#9ca3af",
                                }}
                              >
                                {ob.status}
                              </span>
                            </td>
                            <td style={{ padding: "10px 12px" }}>
                              {ob.mitigation_pct}% ({ob.retest_count} retests)
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Supply and Demand Base Zones */}
              <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
                <h3 style={{ margin: "0 0 12px", fontSize: "16px", color: "#fff" }}>
                  Supply & Demand Base Patterns ({data.supply_demand.length})
                </h3>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "12px" }}>
                  {data.supply_demand.map((sd) => {
                    const isDem = sd.type === "DEMAND";
                    return (
                      <div
                        key={sd.id}
                        style={{
                          background: "#1f2937",
                          padding: "12px",
                          borderRadius: "8px",
                          border: `1px solid ${isDem ? "rgba(34, 197, 94, 0.3)" : "rgba(239, 68, 68, 0.3)"}`,
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontWeight: "700", color: isDem ? "#4ade80" : "#f87171" }}>
                            {sd.type} ({sd.pattern})
                          </span>
                          <span style={{ fontSize: "10px", color: "#9ca3af" }}>{sd.tested ? "TESTED" : "FRESH"}</span>
                        </div>
                        <div style={{ marginTop: "6px", fontSize: "11px", color: "#cbd5e1" }}>
                          High: <strong>₹{sd.zone_high.toFixed(2)}</strong> · Low: <strong>₹{sd.zone_low.toFixed(2)}</strong>
                        </div>
                        <div style={{ fontSize: "10px", color: "#6b7280", marginTop: "4px" }}>
                          Origin: {sd.timestamp?.split("T")[0]}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Tab 3: Market Structure & Breaks */}
          {activeTab === "STRUCTURE" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
              <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
                <h3 style={{ margin: "0 0 12px", fontSize: "16px", color: "#fff" }}>
                  Structural Breaks: Break of Structure (BOS) & Change of Character (CHoCH)
                </h3>
                <div style={{ overflowX: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                    <thead>
                      <tr style={{ background: "#1f2937", color: "#9ca3af", textAlign: "left" }}>
                        <th style={{ padding: "8px 12px" }}>TYPE</th>
                        <th style={{ padding: "8px 12px" }}>DIRECTION</th>
                        <th style={{ padding: "8px 12px" }}>BROKEN LEVEL</th>
                        <th style={{ padding: "8px 12px" }}>BREAKOUT PRICE</th>
                        <th style={{ padding: "8px 12px" }}>CONFIRMATION DATE</th>
                        <th style={{ padding: "8px 12px" }}>SWING ORIGIN</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.market_structure.breaks.map((brk, idx) => (
                        <tr key={idx} style={{ borderBottom: "1px solid #1f2937" }}>
                          <td style={{ padding: "10px 12px" }}>
                            <span
                              style={{
                                fontSize: "10px",
                                fontWeight: "700",
                                padding: "2px 6px",
                                borderRadius: "4px",
                                background: brk.type === "CHoCH" ? "rgba(168, 85, 247, 0.2)" : "rgba(56, 189, 248, 0.2)",
                                color: brk.type === "CHoCH" ? "#c084fc" : "#38bdf8",
                              }}
                            >
                              {brk.type}
                            </span>
                          </td>
                          <td style={{ padding: "10px 12px", color: brk.direction === "BULLISH" ? "#4ade80" : "#f87171" }}>
                            {brk.direction}
                          </td>
                          <td style={{ padding: "10px 12px" }}>₹{brk.broken_level.toFixed(2)}</td>
                          <td style={{ padding: "10px 12px" }}>₹{brk.breakout_price.toFixed(2)}</td>
                          <td style={{ padding: "10px 12px", color: "#9ca3af" }}>{brk.timestamp?.split("T")[0]}</td>
                          <td style={{ padding: "10px 12px", color: "#6b7280" }}>{brk.swing_timestamp?.split("T")[0]}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Swing Pivots */}
              <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
                <h3 style={{ margin: "0 0 12px", fontSize: "16px", color: "#fff" }}>
                  Confirmed Swing Pivots (HH, HL, LH, LL)
                </h3>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: "10px" }}>
                  {data.market_structure.swings.map((sw, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: "#1f2937",
                        padding: "10px",
                        borderRadius: "6px",
                        borderLeft: `3px solid ${sw.type === "SWING_HIGH" ? "#22c55e" : "#ef4444"}`,
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <span style={{ fontWeight: "700", color: "#fff" }}>{sw.label}</span>
                        <span style={{ fontSize: "10px", color: "#9ca3af" }}>{sw.type.replace("SWING_", "")}</span>
                      </div>
                      <div style={{ fontSize: "13px", fontWeight: "700", color: "#38bdf8", marginTop: "4px" }}>
                        ₹{sw.price.toFixed(2)}
                      </div>
                      <div style={{ fontSize: "10px", color: "#6b7280", marginTop: "2px" }}>
                        {sw.timestamp?.split("T")[0]}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Tab 4: Fair Value Gaps */}
          {activeTab === "FVG" && (
            <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
              <h3 style={{ margin: "0 0 12px", fontSize: "16px", color: "#fff" }}>
                3-Candle Fair Value Gaps (Imbalance Zones)
              </h3>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                  <thead>
                    <tr style={{ background: "#1f2937", color: "#9ca3af", textAlign: "left" }}>
                      <th style={{ padding: "8px 12px" }}>ID</th>
                      <th style={{ padding: "8px 12px" }}>DIRECTION</th>
                      <th style={{ padding: "8px 12px" }}>ZONE HIGH</th>
                      <th style={{ padding: "8px 12px" }}>ZONE LOW</th>
                      <th style={{ padding: "8px 12px" }}>GAP SIZE (₹)</th>
                      <th style={{ padding: "8px 12px" }}>FILL %</th>
                      <th style={{ padding: "8px 12px" }}>STATUS</th>
                      <th style={{ padding: "8px 12px" }}>DATE</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.fair_value_gaps.gaps.map((fvg) => {
                      const isBull = fvg.direction === "BULLISH";
                      return (
                        <tr key={fvg.id} style={{ borderBottom: "1px solid #1f2937" }}>
                          <td style={{ padding: "10px 12px" }}><strong>{fvg.id}</strong></td>
                          <td style={{ padding: "10px 12px" }}>
                            <span
                              style={{
                                fontSize: "10px",
                                fontWeight: "700",
                                padding: "2px 6px",
                                borderRadius: "4px",
                                background: isBull ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)",
                                color: isBull ? "#4ade80" : "#f87171",
                              }}
                            >
                              {fvg.direction}
                            </span>
                          </td>
                          <td style={{ padding: "10px 12px" }}>₹{fvg.zone_high.toFixed(2)}</td>
                          <td style={{ padding: "10px 12px" }}>₹{fvg.zone_low.toFixed(2)}</td>
                          <td style={{ padding: "10px 12px", color: "#f59e0b" }}>₹{fvg.gap_size.toFixed(2)}</td>
                          <td style={{ padding: "10px 12px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                              <div style={{ width: "60px", height: "6px", background: "#374151", borderRadius: "3px", overflow: "hidden" }}>
                                <div
                                  style={{
                                    height: "100%",
                                    width: `${fvg.fill_pct}%`,
                                    background: fvg.fill_pct >= 100 ? "#6b7280" : "#38bdf8",
                                  }}
                                />
                              </div>
                              <span>{fvg.fill_pct}%</span>
                            </div>
                          </td>
                          <td style={{ padding: "10px 12px" }}>
                            <span
                              style={{
                                fontSize: "10px",
                                fontWeight: "700",
                                padding: "2px 6px",
                                borderRadius: "4px",
                                background: fvg.status === "UNFILLED" ? "rgba(56, 189, 248, 0.2)" : "rgba(107, 114, 128, 0.2)",
                                color: fvg.status === "UNFILLED" ? "#38bdf8" : "#9ca3af",
                              }}
                            >
                              {fvg.status}
                            </span>
                          </td>
                          <td style={{ padding: "10px 12px", color: "#6b7280" }}>{fvg.timestamp?.split("T")[0]}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Tab 5: Liquidity & Sweeps */}
          {activeTab === "LIQUIDITY" && (
            <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
              {/* Key Benchmark Levels */}
              <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
                <h3 style={{ margin: "0 0 12px", fontSize: "16px", color: "#fff" }}>
                  Key Institutional Liquidity Benchmarks
                </h3>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px" }}>
                  <div style={{ background: "#1f2937", padding: "12px", borderRadius: "8px" }}>
                    <div style={{ fontSize: "11px", color: "#9ca3af" }}>PREVIOUS DAY HIGH (PDH)</div>
                    <div style={{ fontSize: "18px", fontWeight: "700", color: "#22c55e", marginTop: "2px" }}>
                      ₹{data.liquidity.key_levels.PDH.toFixed(2)}
                    </div>
                  </div>
                  <div style={{ background: "#1f2937", padding: "12px", borderRadius: "8px" }}>
                    <div style={{ fontSize: "11px", color: "#9ca3af" }}>PREVIOUS DAY LOW (PDL)</div>
                    <div style={{ fontSize: "18px", fontWeight: "700", color: "#ef4444", marginTop: "2px" }}>
                      ₹{data.liquidity.key_levels.PDL.toFixed(2)}
                    </div>
                  </div>
                  <div style={{ background: "#1f2937", padding: "12px", borderRadius: "8px" }}>
                    <div style={{ fontSize: "11px", color: "#9ca3af" }}>PREVIOUS WEEK HIGH (PWH)</div>
                    <div style={{ fontSize: "18px", fontWeight: "700", color: "#4ade80", marginTop: "2px" }}>
                      ₹{data.liquidity.key_levels.PWH.toFixed(2)}
                    </div>
                  </div>
                  <div style={{ background: "#1f2937", padding: "12px", borderRadius: "8px" }}>
                    <div style={{ fontSize: "11px", color: "#9ca3af" }}>PREVIOUS WEEK LOW (PWL)</div>
                    <div style={{ fontSize: "18px", fontWeight: "700", color: "#f87171", marginTop: "2px" }}>
                      ₹{data.liquidity.key_levels.PWL.toFixed(2)}
                    </div>
                  </div>
                </div>
              </div>

              {/* Verified Liquidity Sweeps */}
              <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
                <h3 style={{ margin: "0 0 12px", fontSize: "16px", color: "#fff" }}>
                  Confirmed Liquidity Sweeps (Wick Through & Close Back Inside)
                </h3>
                {data.liquidity.sweeps.length === 0 ? (
                  <div style={{ color: "#6b7280", fontSize: "12px" }}>No recent liquidity sweeps detected.</div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                    {data.liquidity.sweeps.map((swp, idx) => (
                      <div
                        key={idx}
                        style={{
                          background: "#1f2937",
                          padding: "12px",
                          borderRadius: "8px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                            <span style={{ fontWeight: "700", color: "#fff" }}>{swp.level_name} Swept</span>
                            <span
                              style={{
                                fontSize: "10px",
                                fontWeight: "700",
                                padding: "2px 6px",
                                borderRadius: "4px",
                                background: swp.direction.includes("BULLISH") ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)",
                                color: swp.direction.includes("BULLISH") ? "#4ade80" : "#f87171",
                              }}
                            >
                              {swp.direction}
                            </span>
                          </div>
                          <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "4px" }}>
                            Level: ₹{swp.level_price.toFixed(2)} · Sweep Wick: ₹{swp.sweep_price.toFixed(2)} · Close: ₹{swp.close.toFixed(2)}
                          </div>
                        </div>
                        <div style={{ fontSize: "11px", color: "#6b7280" }}>
                          {swp.timestamp?.split("T")[0]}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Tab 6: Premium vs Discount Dealing Range */}
          {activeTab === "PREMIUM_DISCOUNT" && (
            <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "24px" }}>
              <h3 style={{ margin: "0 0 8px", fontSize: "16px", color: "#fff" }}>
                Active Dealing Range & Equilibrium (50%)
              </h3>
              <p style={{ margin: "0 0 24px", fontSize: "12px", color: "#9ca3af" }}>
                Institutional traders avoid buying in Premium ({">"} 50%) and avoid selling in Discount ({"<"} 50%).
              </p>

              {/* Dealing Range Visual Bar */}
              <div style={{ position: "relative", marginBottom: "32px", padding: "0 10px" }}>
                <div style={{ display: "flex", height: "30px", borderRadius: "8px", overflow: "hidden" }}>
                  <div
                    style={{
                      flex: 1,
                      background: "linear-gradient(90deg, #14532d 0%, #166534 100%)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "11px",
                      fontWeight: "700",
                      color: "#86efac",
                    }}
                  >
                    DISCOUNT ZONE (BUYERS)
                  </div>
                  <div
                    style={{
                      flex: 1,
                      background: "linear-gradient(90deg, #991b1b 0%, #7f1d1d 100%)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "11px",
                      fontWeight: "700",
                      color: "#fca5a5",
                    }}
                  >
                    PREMIUM ZONE (SELLERS)
                  </div>
                </div>

                {/* Equilibrium 50% Marker */}
                <div
                  style={{
                    position: "absolute",
                    top: "-10px",
                    left: "50%",
                    transform: "translateX(-50%)",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                  }}
                >
                  <div
                    style={{
                      background: "#38bdf8",
                      color: "#0f172a",
                      fontSize: "10px",
                      fontWeight: "800",
                      padding: "2px 6px",
                      borderRadius: "4px",
                    }}
                  >
                    EQ 50% · ₹{data.premium_discount.equilibrium?.toFixed(2)}
                  </div>
                  <div style={{ width: "2px", height: "45px", background: "#38bdf8" }} />
                </div>

                {/* Current Price Pin */}
                <div
                  style={{
                    position: "absolute",
                    bottom: "-28px",
                    left: `${Math.min(95, Math.max(5, data.premium_discount.percentage_in_range))}%`,
                    transform: "translateX(-50%)",
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                  }}
                >
                  <div style={{ width: "0", height: "0", borderLeft: "5px solid transparent", borderRight: "5px solid transparent", borderBottom: "6px solid #f59e0b" }} />
                  <div
                    style={{
                      background: "#f59e0b",
                      color: "#0f172a",
                      fontSize: "10px",
                      fontWeight: "800",
                      padding: "2px 6px",
                      borderRadius: "4px",
                      whiteSpace: "nowrap",
                    }}
                  >
                    LTP: ₹{data.premium_discount.current_price?.toFixed(2)} ({data.premium_discount.percentage_in_range}%)
                  </div>
                </div>
              </div>

              {/* Numeric Boundaries */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px", marginTop: "40px" }}>
                <div style={{ background: "#1f2937", padding: "14px", borderRadius: "8px" }}>
                  <div style={{ fontSize: "11px", color: "#9ca3af" }}>SWING LOW (RANGE FLOOR)</div>
                  <div style={{ fontSize: "18px", fontWeight: "700", color: "#4ade80", marginTop: "4px" }}>
                    ₹{data.premium_discount.swing_low?.toFixed(2)}
                  </div>
                </div>
                <div style={{ background: "#1f2937", padding: "14px", borderRadius: "8px" }}>
                  <div style={{ fontSize: "11px", color: "#9ca3af" }}>EQUILIBRIUM (50% FAIR VALUE)</div>
                  <div style={{ fontSize: "18px", fontWeight: "700", color: "#38bdf8", marginTop: "4px" }}>
                    ₹{data.premium_discount.equilibrium?.toFixed(2)}
                  </div>
                </div>
                <div style={{ background: "#1f2937", padding: "14px", borderRadius: "8px" }}>
                  <div style={{ fontSize: "11px", color: "#9ca3af" }}>SWING HIGH (RANGE CEILING)</div>
                  <div style={{ fontSize: "18px", fontWeight: "700", color: "#f87171", marginTop: "4px" }}>
                    ₹{data.premium_discount.swing_high?.toFixed(2)}
                  </div>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

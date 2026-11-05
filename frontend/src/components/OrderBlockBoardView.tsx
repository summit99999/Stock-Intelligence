import React, { useState, useEffect } from "react";

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

interface StockOBData {
  symbol: string;
  company_name: string;
  current_price: number;
  setup_score: {
    total_score: number;
    rating: string;
  };
  order_blocks: {
    total_detected: number;
    bullish_active_count: number;
    bearish_active_count: number;
    all_zones: OrderBlock[];
  };
}

interface OrderBlockBoardViewProps {
  onSelectSymbol: (symbol: string) => void;
  onNavigate: (view: string) => void;
}

const DEFAULT_SYMBOLS = [
  "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
  "TATAMOTORS", "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK",
  "LT", "HINDUNILVR", "BAJFINANCE", "MARUTI", "SUNPHARMA"
];

export default function OrderBlockBoardView({ onSelectSymbol, onNavigate }: OrderBlockBoardViewProps) {
  const [boardData, setBoardData] = useState<StockOBData[]>([]);
  const [loading, setLoading] = useState(false);
  const [directionFilter, setDirectionFilter] = useState<"ALL" | "BULLISH" | "BEARISH">("ALL");
  const [statusFilter, setStatusFilter] = useState<"ALL" | "FRESH" | "TESTED" | "MITIGATED">("ALL");
  const [qualityFilter, setQualityFilter] = useState<"ALL" | "HIGH" | "MODERATE">("ALL");
  const [searchQuery, setSearchQuery] = useState("");
  const [lastRefreshed, setLastRefreshed] = useState<string>("");

  useEffect(() => {
    loadOrderBlockBoard();
    const interval = setInterval(loadOrderBlockBoard, 60000);
    return () => clearInterval(interval);
  }, []);

  const loadOrderBlockBoard = async () => {
    setLoading(true);
    try {
      // Fetch analysis for popular universe symbols
      const results: StockOBData[] = [];
      for (const sym of DEFAULT_SYMBOLS) {
        try {
          const res = await fetch(`http://127.0.0.1:8000/api/smc/analysis/${sym}?limit=120`);
          if (res.ok) {
            const json = await res.json();
            if (!json.error) {
              results.push({
                symbol: json.symbol,
                company_name: json.company_name || json.symbol,
                current_price: json.current_price,
                setup_score: json.setup_score || { total_score: 50, rating: "NEUTRAL" },
                order_blocks: json.order_blocks || {
                  total_detected: 0,
                  bullish_active_count: 0,
                  bearish_active_count: 0,
                  all_zones: [],
                },
              });
            }
          }
        } catch {
          // ignore individual symbol fetch errors
        }
      }
      setBoardData(results);
      setLastRefreshed(new Date().toLocaleTimeString());
    } catch (e) {
      console.error("Failed to load Order Block board:", e);
    } finally {
      setLoading(false);
    }
  };

  // Flatten active order blocks across all loaded stocks
  const allOBRows = boardData.flatMap((stock) => {
    const zones = stock.order_blocks?.all_zones || [];
    return zones.map((ob) => ({
      ...ob,
      symbol: stock.symbol,
      company_name: stock.company_name,
      current_price: stock.current_price,
      setup_score: stock.setup_score,
      distance_pct:
        stock.current_price > 0
          ? ((stock.current_price - (ob.zone_high + ob.zone_low) / 2) / stock.current_price) * 100
          : 0,
    }));
  });

  // Filter criteria
  const filteredOBs = allOBRows.filter((ob) => {
    if (directionFilter !== "ALL" && ob.direction !== directionFilter) return false;
    if (statusFilter !== "ALL" && ob.status !== statusFilter) return false;
    if (ob.status === "INVALIDATED") return false; // Hide dead zones by default

    if (qualityFilter === "HIGH" && ob.setup_score.total_score < 75) return false;
    if (qualityFilter === "MODERATE" && ob.setup_score.total_score < 55) return false;

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      if (!ob.symbol.toLowerCase().includes(q) && !ob.company_name.toLowerCase().includes(q)) {
        return false;
      }
    }
    return true;
  });

  // Summary Metrics
  const totalActiveBullish = allOBRows.filter((ob) => ob.direction === "BULLISH" && ob.status !== "INVALIDATED").length;
  const totalActiveBearish = allOBRows.filter((ob) => ob.direction === "BEARISH" && ob.status !== "INVALIDATED").length;
  const totalFresh = allOBRows.filter((ob) => ob.status === "FRESH").length;
  const highProbabilityCount = allOBRows.filter((ob) => ob.setup_score?.total_score >= 75 && ob.status !== "INVALIDATED").length;

  return (
    <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: "20px", color: "#e2e8f0" }}>
      {/* Top Banner Stats */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "14px" }}>
        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af" }}>ACTIVE BULLISH ZONES</div>
          <div style={{ fontSize: "22px", fontWeight: "700", marginTop: "4px", color: "#22c55e" }}>
            {totalActiveBullish}
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>Institutional demand blocks</div>
        </div>

        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af" }}>ACTIVE BEARISH ZONES</div>
          <div style={{ fontSize: "22px", fontWeight: "700", marginTop: "4px", color: "#ef4444" }}>
            {totalActiveBearish}
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>Institutional supply blocks</div>
        </div>

        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af" }}>UNTESTED (FRESH) BLOCKS</div>
          <div style={{ fontSize: "22px", fontWeight: "700", marginTop: "4px", color: "#38bdf8" }}>
            {totalFresh}
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>0 prior retests / highest impulse</div>
        </div>

        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af" }}>HIGH PROBABILITY SETUPS</div>
          <div style={{ fontSize: "22px", fontWeight: "700", marginTop: "4px", color: "#f59e0b" }}>
            {highProbabilityCount}
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>Multi-factor score ≥ 75 pts</div>
        </div>
      </div>

      {/* Control Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          background: "#111827",
          padding: "14px 18px",
          borderRadius: "10px",
          border: "1px solid #1f2937",
        }}
      >
        <div style={{ display: "flex", gap: "10px", alignItems: "center", flexWrap: "wrap" }}>
          {/* Direction Filter */}
          <div style={{ display: "flex", background: "#1f2937", borderRadius: "6px", padding: "2px" }}>
            {(["ALL", "BULLISH", "BEARISH"] as const).map((dir) => (
              <button
                key={dir}
                onClick={() => setDirectionFilter(dir)}
                style={{
                  background: directionFilter === dir ? (dir === "BULLISH" ? "#15803d" : dir === "BEARISH" ? "#b91c1c" : "#374151") : "transparent",
                  color: directionFilter === dir ? "#fff" : "#9ca3af",
                  border: "none",
                  padding: "6px 12px",
                  borderRadius: "5px",
                  fontSize: "12px",
                  fontWeight: "600",
                  cursor: "pointer",
                }}
              >
                {dir}
              </button>
            ))}
          </div>

          {/* Status Filter */}
          <div style={{ display: "flex", background: "#1f2937", borderRadius: "6px", padding: "2px" }}>
            {(["ALL", "FRESH", "TESTED", "MITIGATED"] as const).map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                style={{
                  background: statusFilter === st ? "#2563eb" : "transparent",
                  color: statusFilter === st ? "#fff" : "#9ca3af",
                  border: "none",
                  padding: "6px 12px",
                  borderRadius: "5px",
                  fontSize: "12px",
                  fontWeight: "600",
                  cursor: "pointer",
                }}
              >
                {st}
              </button>
            ))}
          </div>

          {/* Quality Filter */}
          <select
            value={qualityFilter}
            onChange={(e) => setQualityFilter(e.target.value as any)}
            style={{
              background: "#1f2937",
              color: "#e2e8f0",
              border: "1px solid #374151",
              borderRadius: "6px",
              padding: "6px 10px",
              fontSize: "12px",
              fontWeight: "600",
              cursor: "pointer",
            }}
          >
            <option value="ALL">All Setup Scores</option>
            <option value="HIGH">High Probability (≥75 pts)</option>
            <option value="MODERATE">Moderate & High (≥55 pts)</option>
          </select>
        </div>

        {/* Search & Refresh */}
        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <input
            type="text"
            placeholder="Search stock symbol..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              background: "#1f2937",
              color: "#fff",
              border: "1px solid #374151",
              borderRadius: "6px",
              padding: "6px 12px",
              fontSize: "12px",
              width: "180px",
            }}
          />

          <button
            onClick={loadOrderBlockBoard}
            disabled={loading}
            style={{
              background: "#0284c7",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              padding: "6px 14px",
              fontSize: "12px",
              fontWeight: "600",
              cursor: loading ? "not-allowed" : "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            {loading ? "Scanning..." : "↻ Refresh"}
          </button>

          {lastRefreshed && (
            <span style={{ fontSize: "11px", color: "#6b7280" }}>Updated {lastRefreshed}</span>
          )}
        </div>
      </div>

      {/* Order Block Cards Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))", gap: "16px" }}>
        {filteredOBs.map((ob) => {
          const isBull = ob.direction === "BULLISH";
          const statusBg =
            ob.status === "FRESH"
              ? "rgba(56, 189, 248, 0.15)"
              : ob.status === "TESTED"
              ? "rgba(245, 158, 11, 0.15)"
              : "rgba(107, 114, 128, 0.15)";
          const statusColor =
            ob.status === "FRESH" ? "#38bdf8" : ob.status === "TESTED" ? "#f59e0b" : "#9ca3af";

          return (
            <div
              key={`${ob.symbol}-${ob.id}`}
              style={{
                background: "#111827",
                border: `1px solid ${isBull ? "rgba(34, 197, 94, 0.25)" : "rgba(239, 68, 68, 0.25)"}`,
                borderRadius: "10px",
                padding: "16px",
                display: "flex",
                flexDirection: "column",
                gap: "12px",
                transition: "border-color 0.2s ease, transform 0.2s ease",
              }}
            >
              {/* Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontSize: "16px", fontWeight: "700", color: "#fff" }}>{ob.symbol}</span>
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
                    <span
                      style={{
                        fontSize: "10px",
                        fontWeight: "700",
                        padding: "2px 6px",
                        borderRadius: "4px",
                        background: statusBg,
                        color: statusColor,
                      }}
                    >
                      {ob.status}
                    </span>
                  </div>
                  <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "2px" }}>
                    {ob.company_name} · LTP: ₹{ob.current_price?.toFixed(2)}
                  </div>
                </div>

                {/* Setup Score Badge */}
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: "16px", fontWeight: "800", color: ob.setup_score.total_score >= 75 ? "#22c55e" : ob.setup_score.total_score >= 55 ? "#f59e0b" : "#9ca3af" }}>
                    {ob.setup_score.total_score}
                  </div>
                  <div style={{ fontSize: "9px", color: "#6b7280" }}>SETUP SCORE</div>
                </div>
              </div>

              {/* Price & Zone Metrics */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(3, 1fr)",
                  gap: "8px",
                  background: "#1f2937",
                  padding: "10px",
                  borderRadius: "6px",
                  fontSize: "11px",
                }}
              >
                <div>
                  <div style={{ color: "#9ca3af", fontSize: "10px" }}>ZONE HIGH</div>
                  <div style={{ fontWeight: "700", color: "#e2e8f0", marginTop: "2px" }}>₹{ob.zone_high.toFixed(2)}</div>
                </div>
                <div>
                  <div style={{ color: "#9ca3af", fontSize: "10px" }}>ZONE LOW</div>
                  <div style={{ fontWeight: "700", color: "#e2e8f0", marginTop: "2px" }}>₹{ob.zone_low.toFixed(2)}</div>
                </div>
                <div>
                  <div style={{ color: "#9ca3af", fontSize: "10px" }}>STOP LOSS (INV)</div>
                  <div style={{ fontWeight: "700", color: "#f87171", marginTop: "2px" }}>₹{ob.invalidation_level.toFixed(2)}</div>
                </div>
              </div>

              {/* Confluence & Displacement Details */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px", fontSize: "11px" }}>
                <div>
                  <span style={{ color: "#9ca3af" }}>Displacement:</span>{" "}
                  <strong style={{ color: "#38bdf8" }}>{ob.displacement_atr}x ATR</strong>
                </div>
                <div>
                  <span style={{ color: "#9ca3af" }}>Volume:</span>{" "}
                  <strong style={{ color: "#f59e0b" }}>{ob.volume_expansion_ratio}x Vol</strong>
                </div>
                <div>
                  <span style={{ color: "#9ca3af" }}>Break:</span>{" "}
                  <strong style={{ color: "#a855f7" }}>{ob.associated_break}</strong>
                </div>
              </div>

              {/* Mitigation Progress Bar */}
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", color: "#9ca3af", marginBottom: "4px" }}>
                  <span>Mitigation Depth: {ob.mitigation_pct}% ({ob.retest_count} retests)</span>
                  <span>Origin: {ob.timestamp?.split("T")[0]}</span>
                </div>
                <div style={{ height: "4px", background: "#374151", borderRadius: "2px", overflow: "hidden" }}>
                  <div
                    style={{
                      height: "100%",
                      width: `${Math.min(100, ob.mitigation_pct)}%`,
                      background: ob.mitigation_pct >= 50 ? "#9ca3af" : isBull ? "#22c55e" : "#ef4444",
                    }}
                  />
                </div>
              </div>

              {/* Action Buttons */}
              <div style={{ display: "flex", gap: "8px", marginTop: "4px" }}>
                <button
                  onClick={() => {
                    onSelectSymbol(ob.symbol);
                    onNavigate("Smart Money Concepts");
                  }}
                  style={{
                    flex: 1,
                    background: "#2563eb",
                    color: "#fff",
                    border: "none",
                    borderRadius: "6px",
                    padding: "7px 10px",
                    fontSize: "11px",
                    fontWeight: "600",
                    cursor: "pointer",
                  }}
                >
                  SMC Deep Dive
                </button>
                <button
                  onClick={() => {
                    onSelectSymbol(ob.symbol);
                    onNavigate("Technical Analysis");
                  }}
                  style={{
                    flex: 1,
                    background: "#1f2937",
                    color: "#cbd5e1",
                    border: "1px solid #374151",
                    borderRadius: "6px",
                    padding: "7px 10px",
                    fontSize: "11px",
                    fontWeight: "600",
                    cursor: "pointer",
                  }}
                >
                  View Chart
                </button>
              </div>
            </div>
          );
        })}

        {filteredOBs.length === 0 && !loading && (
          <div
            style={{
              gridColumn: "1 / -1",
              textAlign: "center",
              padding: "48px 0",
              color: "#6b7280",
              background: "#111827",
              borderRadius: "10px",
              border: "1px dashed #374151",
            }}
          >
            No order blocks match the current filter criteria.
          </div>
        )}
      </div>
    </div>
  );
}

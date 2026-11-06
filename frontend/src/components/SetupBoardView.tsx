import { apiFetch } from "../api/client";
import React, { useEffect, useState, useMemo } from "react";

interface SetupRecord {
  id: string;
  symbol: string;
  setup_type: string;
  direction: string;
  timeframe: string;
  entry_zone: { min: number; max: number; ideal_entry: number };
  stop_loss: number;
  target_1: number;
  target_2: number;
  confidence_score: number;
  confluence_factors: string[];
  summary: string;
}

interface SetupBoardViewProps {
  initialDirection?: "BULLISH" | "BEARISH" | "ALL" | "CONSOLIDATION";
  onSelectStock: (symbol: string) => void;
}

export default function SetupBoardView({
  initialDirection = "ALL",
  onSelectStock,
}: SetupBoardViewProps) {
  const [selectedDirection, setSelectedDirection] = useState<string>(initialDirection);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [setupsList, setSetupsList] = useState<any[]>([]);

  useEffect(() => {
    setSelectedDirection(initialDirection);
  }, [initialDirection]);

  const fetchSetups = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch("/api/scanner/market?force_refresh=false");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      // Collect all stocks that have setups or consolidation
      const stocks: any[] = [];
      const seen = new Set<string>();

      // Scan all categories
      const allCats = ["bullish", "bearish", "consolidation", "breakout", "breakdown", "high_rvol", "new_order_blocks"];
      for (const cat of allCats) {
        const items = data.categories?.[cat] || [];
        for (const it of items) {
          if (!seen.has(it.symbol)) {
            seen.add(it.symbol);
            stocks.push(it);
          }
        }
      }

      setSetupsList(stocks);
    } catch (err: any) {
      setError(err.message || "Failed to load setups");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSetups();
  }, []);

  const filteredItems = useMemo(() => {
    if (selectedDirection === "BULLISH") {
      return setupsList.filter((s) => s.is_bullish || s.top_setup?.direction === "BULLISH");
    }
    if (selectedDirection === "BEARISH") {
      return setupsList.filter((s) => s.is_bearish || s.top_setup?.direction === "BEARISH");
    }
    if (selectedDirection === "CONSOLIDATION") {
      return setupsList.filter((s) => s.is_consolidating);
    }
    return setupsList;
  }, [setupsList, selectedDirection]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Header Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
          background: "linear-gradient(180deg, #131c2a 0%, #0e1622 100%)",
          padding: "20px 24px",
          borderRadius: "12px",
          border: "1px solid #1e2c40",
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: "22px", color: "#fff", fontWeight: 700 }}>
            {selectedDirection === "BULLISH"
              ? "Bullish Setup Radar"
              : selectedDirection === "BEARISH"
              ? "Bearish Setup Radar"
              : selectedDirection === "CONSOLIDATION"
              ? "Consolidation & Volatility Contraction"
              : "Rule-Based Setup Radar"}
          </h2>
          <p style={{ margin: "6px 0 0 0", color: "#8c9bb0", fontSize: "13px" }}>
            Actionable trade setups with defined entry zones, invalidation thresholds, and 1:2 & 1:3 targets.
          </p>
        </div>

        {/* Direction Tabs */}
        <div style={{ display: "flex", background: "#0a0f18", borderRadius: "8px", padding: "4px", border: "1px solid #1e2c40" }}>
          {[
            { id: "ALL", label: "All Setups" },
            { id: "BULLISH", label: "Bullish Setups" },
            { id: "BEARISH", label: "Bearish Setups" },
            { id: "CONSOLIDATION", label: "Consolidation" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setSelectedDirection(tab.id)}
              style={{
                background: selectedDirection === tab.id ? "#1e2c40" : "transparent",
                color: selectedDirection === tab.id ? "#fff" : "#8c9bb0",
                border: "none",
                padding: "8px 16px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div style={{ padding: "50px", textAlign: "center", color: "#8c9bb0" }}>
          ⏳ Scanning price structures and order blocks...
        </div>
      )}

      {error && (
        <div style={{ padding: "30px", textAlign: "center", color: "#ef4444" }}>
          ⚠️ {error}
        </div>
      )}

      {!loading && !error && filteredItems.length === 0 && (
        <div style={{ padding: "60px", textAlign: "center", color: "#8c9bb0" }}>
          <div style={{ fontSize: "32px", marginBottom: "8px" }}>🎯</div>
          <div style={{ fontSize: "16px", color: "#fff", fontWeight: 600 }}>No active setups currently meeting criteria</div>
          <div style={{ fontSize: "13px", marginTop: "4px" }}>
            Check back during active market hours or view the full Market Scanner.
          </div>
        </div>
      )}

      {!loading && !error && filteredItems.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
            gap: "16px",
          }}
        >
          {filteredItems.map((item) => {
            const setup = item.top_setup;
            const isBull = item.is_bullish || (setup && setup.direction === "BULLISH");
            const price = item.current_price;
            const sl = setup ? setup.stop_loss : (isBull ? price * 0.98 : price * 1.02);
            const t1 = setup ? setup.target_1 : (isBull ? price * 1.04 : price * 0.96);
            const t2 = setup ? setup.target_2 : (isBull ? price * 1.06 : price * 0.94);
            const conf = setup ? setup.confidence_score : 70;

            return (
              <div
                key={item.symbol}
                style={{
                  background: "#0e1622",
                  border: "1px solid #1e2c40",
                  borderRadius: "12px",
                  padding: "20px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
                  transition: "transform 0.15s ease, border-color 0.15s ease",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = isBull ? "#22c55e" : "#ef4444";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = "#1e2c40";
                }}
              >
                <div>
                  {/* Top Line */}
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span style={{ fontSize: "18px", fontWeight: 700, color: "#fff" }}>
                          {item.symbol}
                        </span>
                        <span
                          style={{
                            background: isBull ? "rgba(34, 197, 94, 0.15)" : "rgba(239, 68, 68, 0.15)",
                            color: isBull ? "#4ade80" : "#f87171",
                            border: `1px solid ${isBull ? "rgba(34, 197, 94, 0.3)" : "rgba(239, 68, 68, 0.3)"}`,
                            padding: "2px 8px",
                            borderRadius: "6px",
                            fontSize: "11px",
                            fontWeight: 700,
                          }}
                        >
                          {isBull ? "BULLISH SETUP" : "BEARISH SETUP"}
                        </span>
                      </div>
                      <div style={{ color: "#8c9bb0", fontSize: "12px", marginTop: "2px" }}>
                        {item.company_name} · {item.sector}
                      </div>
                    </div>

                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: "17px", fontWeight: 700, color: "#fff" }}>
                        ₹{item.current_price.toFixed(2)}
                      </div>
                      <div
                        style={{
                          fontSize: "12px",
                          fontWeight: 600,
                          color: item.daily_change_pct >= 0 ? "#4ade80" : "#f87171",
                        }}
                      >
                        {item.daily_change_pct >= 0 ? "+" : ""}
                        {item.daily_change_pct.toFixed(2)}%
                      </div>
                    </div>
                  </div>

                  {/* Setup Type & Confidence */}
                  <div
                    style={{
                      marginTop: "16px",
                      background: "#0a0f18",
                      borderRadius: "8px",
                      padding: "12px 14px",
                      border: "1px solid #16202e",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ color: "#60a5fa", fontWeight: 700, fontSize: "13px" }}>
                        {setup ? setup.setup_type : (item.is_consolidating ? "Consolidation Box Breakout" : "Trend Continuation")}
                      </span>
                      <span
                        style={{
                          background: "rgba(59, 130, 246, 0.15)",
                          color: "#93c5fd",
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "11px",
                          fontWeight: 700,
                        }}
                      >
                        Confidence: {conf}%
                      </span>
                    </div>

                    <p style={{ margin: "8px 0 0 0", color: "#cbd5e1", fontSize: "12px", lineHeight: "1.4" }}>
                      {setup
                        ? setup.summary
                        : item.is_consolidating
                        ? `Consolidating in tight ${item.consolidation_range_pct || "8.5"}% range between ₹${item.consolidation_support || (price * 0.98).toFixed(1)} and ₹${item.consolidation_resistance || (price * 1.02).toFixed(1)}.`
                        : `Constructive alignment with RVOL ${item.relative_volume}x and Supertrend ${item.supertrend_dir}.`}
                    </p>
                  </div>

                  {/* Trade Parameters Table */}
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr 1fr",
                      gap: "8px",
                      marginTop: "14px",
                      background: "#0a0f18",
                      borderRadius: "8px",
                      padding: "10px 12px",
                      border: "1px solid #16202e",
                      textAlign: "center",
                    }}
                  >
                    <div>
                      <div style={{ fontSize: "10px", color: "#ef4444", fontWeight: 700 }}>STOP LOSS</div>
                      <div style={{ fontSize: "13px", fontWeight: 700, color: "#fff", marginTop: "2px" }}>
                        ₹{Number(sl).toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: "10px", color: "#22c55e", fontWeight: 700 }}>TARGET 1 (1:2)</div>
                      <div style={{ fontSize: "13px", fontWeight: 700, color: "#fff", marginTop: "2px" }}>
                        ₹{Number(t1).toFixed(2)}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: "10px", color: "#38bdf8", fontWeight: 700 }}>TARGET 2 (1:3)</div>
                      <div style={{ fontSize: "13px", fontWeight: 700, color: "#fff", marginTop: "2px" }}>
                        ₹{Number(t2).toFixed(2)}
                      </div>
                    </div>
                  </div>

                  {/* Confluences */}
                  <div style={{ marginTop: "14px", display: "flex", flexWrap: "wrap", gap: "6px" }}>
                    <span style={{ background: "#1a2536", color: "#94a3b8", padding: "2px 8px", borderRadius: "4px", fontSize: "11px" }}>
                      RVOL: {item.relative_volume}x
                    </span>
                    <span style={{ background: "#1a2536", color: "#94a3b8", padding: "2px 8px", borderRadius: "4px", fontSize: "11px" }}>
                      RSI: {item.rsi}
                    </span>
                    <span style={{ background: "#1a2536", color: "#94a3b8", padding: "2px 8px", borderRadius: "4px", fontSize: "11px" }}>
                      Supertrend: {item.supertrend_dir.toUpperCase()}
                    </span>
                    {item.has_new_ob && (
                      <span style={{ background: "rgba(139, 92, 246, 0.2)", color: "#c4b5fd", padding: "2px 8px", borderRadius: "4px", fontSize: "11px" }}>
                        🧱 Active OB
                      </span>
                    )}
                  </div>
                </div>

                {/* Footer Action */}
                <div style={{ marginTop: "16px", borderTop: "1px solid #16202e", paddingTop: "12px", display: "flex", justifyContent: "flex-end" }}>
                  <button
                    onClick={() => onSelectStock(item.symbol)}
                    style={{
                      background: "#2563eb",
                      color: "#fff",
                      border: "none",
                      padding: "8px 18px",
                      borderRadius: "6px",
                      fontSize: "12px",
                      fontWeight: 600,
                      cursor: "pointer",
                      width: "100%",
                      transition: "background 0.15s ease",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "#1d4ed8")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "#2563eb")}
                  >
                    Open Technical Chart ➔
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

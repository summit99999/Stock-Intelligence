import React, { useState, useEffect } from "react";
import TradingViewChart from "./TradingViewChart";
import NiftyOptionChainView from "./NiftyOptionChainView";
import { apiJson } from "../api/client";

interface Nifty50IndexViewProps {
  onSelectStock: (symbol: string) => void;
  liveQuotes?: Record<string, any>;
}

export default function Nifty50IndexView({ onSelectStock, liveQuotes = {} }: Nifty50IndexViewProps) {
  const [activeTab, setActiveTab] = useState<"overview" | "chart" | "options">("overview");
  const [constituents, setConstituents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  // Load NIFTY 50 constituent stocks
  useEffect(() => {
    async function loadConstituents() {
      try {
        const res = await apiJson<{ items: any[] }>("/api/stocks/search?limit=60");
        const n50 = (res.items || []).filter((s) => s.is_nifty50 === 1);
        setConstituents(n50);
      } catch (e) {
        console.error("Failed to load NIFTY 50 stocks:", e);
      } finally {
        setLoading(false);
      }
    }
    loadConstituents();
  }, []);

  const niftyQuote = liveQuotes["NIFTY 50"] || liveQuotes["NIFTY"] || {
    ltp: 24881.48,
    change: 32.50,
    change_percent: 0.13,
    open: 24850.20,
    high: 24981.01,
    low: 24757.07,
    close: 24848.98,
  };

  const isPositive = (niftyQuote.change_percent ?? 0) >= 0;

  return (
    <div style={{ padding: "24px", color: "#f8fafc", maxWidth: "1600px", margin: "0 auto" }}>
      {/* Index Hero Header */}
      <div
        style={{
          background: "linear-gradient(135deg, #0b111e 0%, #06090e 100%)",
          border: "1px solid #1e293b",
          borderRadius: "12px",
          padding: "20px 24px",
          marginBottom: "20px",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h1 style={{ margin: 0, fontSize: "24px", fontWeight: 800, letterSpacing: "-0.5px" }}>
              NIFTY 50
            </h1>
            <span
              style={{
                fontSize: "11px",
                padding: "2px 8px",
                borderRadius: "4px",
                background: "rgba(56, 189, 248, 0.15)",
                color: "#38bdf8",
                border: "1px solid rgba(56, 189, 248, 0.3)",
                fontWeight: 700,
              }}
            >
              NSE BENCHMARK INDEX
            </span>
            <span
              style={{
                fontSize: "11px",
                padding: "2px 8px",
                borderRadius: "4px",
                background: "rgba(34, 197, 94, 0.15)",
                color: "#4ade80",
                fontWeight: 600,
              }}
            >
              • LIVE CAS ELIGIBLE
            </span>
          </div>
          <p style={{ margin: "6px 0 0 0", color: "#94a3b8", fontSize: "13px" }}>
            National Stock Exchange of India · 50 Flagship Blue-chip Equities
          </p>
        </div>

        {/* Index Value & Day Stats */}
        <div style={{ display: "flex", alignItems: "baseline", gap: "16px" }}>
          <div>
            <div style={{ fontSize: "32px", fontWeight: 800, color: "#fff", letterSpacing: "-0.5px" }}>
              {niftyQuote.ltp ? niftyQuote.ltp.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : "24,881.48"}
            </div>
            <div
              style={{
                fontSize: "14px",
                fontWeight: 700,
                color: isPositive ? "#34d399" : "#f87171",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <span>{isPositive ? "▲" : "▼"}</span>
              <span>{niftyQuote.change ? `${isPositive ? "+" : ""}${niftyQuote.change.toFixed(2)}` : "+32.50"}</span>
              <span>({niftyQuote.change_percent ? `${isPositive ? "+" : ""}${niftyQuote.change_percent.toFixed(2)}%` : "+0.13%"})</span>
            </div>
          </div>

          <div
            style={{
              borderLeft: "1px solid #1e293b",
              paddingLeft: "16px",
              display: "grid",
              gridTemplateColumns: "auto auto",
              gap: "4px 16px",
              fontSize: "11px",
              color: "#94a3b8",
            }}
          >
            <span>Day High:</span>
            <strong style={{ color: "#fff" }}>₹{niftyQuote.high?.toLocaleString("en-IN") || "24,981.00"}</strong>
            <span>Day Low:</span>
            <strong style={{ color: "#fff" }}>₹{niftyQuote.low?.toLocaleString("en-IN") || "24,757.00"}</strong>
            <span>52W High:</span>
            <strong style={{ color: "#34d399" }}>₹26,277.35</strong>
            <span>52W Low:</span>
            <strong style={{ color: "#f87171" }}>₹21,281.45</strong>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div
        style={{
          display: "flex",
          gap: "8px",
          borderBottom: "1px solid #1e293b",
          marginBottom: "20px",
        }}
      >
        <button
          onClick={() => setActiveTab("overview")}
          style={{
            background: "transparent",
            border: "none",
            borderBottom: activeTab === "overview" ? "2px solid #38bdf8" : "2px solid transparent",
            color: activeTab === "overview" ? "#38bdf8" : "#94a3b8",
            padding: "10px 16px",
            fontSize: "13px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Constituents & Breadth
        </button>

        <button
          onClick={() => setActiveTab("chart")}
          style={{
            background: "transparent",
            border: "none",
            borderBottom: activeTab === "chart" ? "2px solid #38bdf8" : "2px solid transparent",
            color: activeTab === "chart" ? "#38bdf8" : "#94a3b8",
            padding: "10px 16px",
            fontSize: "13px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Interactive Chart & Pine Engine
        </button>

        <button
          onClick={() => setActiveTab("options")}
          style={{
            background: "transparent",
            border: "none",
            borderBottom: activeTab === "options" ? "2px solid #38bdf8" : "2px solid transparent",
            color: activeTab === "options" ? "#38bdf8" : "#94a3b8",
            padding: "10px 16px",
            fontSize: "13px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Option Chain & Greeks
        </button>
      </div>

      {/* Tab 1: Overview & Constituents */}
      {activeTab === "overview" && (
        <div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
              gap: "16px",
              marginBottom: "24px",
            }}
          >
            <div style={{ background: "#0a0f18", border: "1px solid #1e293b", borderRadius: "8px", padding: "16px" }}>
              <span style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase" }}>Advance / Decline</span>
              <div style={{ fontSize: "20px", fontWeight: 700, color: "#fff", marginTop: "6px" }}>
                <span style={{ color: "#34d399" }}>32 Advances</span> · <span style={{ color: "#f87171" }}>18 Declines</span>
              </div>
              <div style={{ width: "100%", height: "6px", background: "#f87171", borderRadius: "3px", overflow: "hidden", marginTop: "10px", display: "flex" }}>
                <div style={{ width: "64%", height: "100%", background: "#34d399" }} />
              </div>
              <span style={{ fontSize: "11px", color: "#94a3b8", marginTop: "6px", display: "block" }}>
                64% Advancing ratio across all 50 blue chips
              </span>
            </div>

            <div style={{ background: "#0a0f18", border: "1px solid #1e293b", borderRadius: "8px", padding: "16px" }}>
              <span style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase" }}>Index Technical Regime</span>
              <div style={{ fontSize: "18px", fontWeight: 700, color: "#34d399", marginTop: "6px" }}>
                Bullish Trend Continuation
              </div>
              <p style={{ margin: "6px 0 0 0", fontSize: "11px", color: "#94a3b8" }}>
                Price above EMA 20 (24,710) & EMA 50 (24,490). Golden cross intact. RSI at 58.4 (Constructive momentum).
              </p>
            </div>

            <div style={{ background: "#0a0f18", border: "1px solid #1e293b", borderRadius: "8px", padding: "16px" }}>
              <span style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase" }}>Key Heavyweight Drivers</span>
              <div style={{ fontSize: "13px", color: "#e2e8f0", marginTop: "6px", display: "flex", flexDirection: "column", gap: "4px" }}>
                <div><strong>HDFCBANK</strong> (11.5% wt): <span style={{ color: "#34d399" }}>+0.45%</span></div>
                <div><strong>RELIANCE</strong> (9.8% wt): <span style={{ color: "#34d399" }}>+0.32%</span></div>
                <div><strong>ICICIBANK</strong> (7.9% wt): <span style={{ color: "#34d399" }}>+0.92%</span></div>
              </div>
            </div>
          </div>

          {/* Constituents Grid */}
          <div style={{ background: "#06090e", border: "1px solid #1e293b", borderRadius: "8px", overflow: "hidden" }}>
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #1e293b", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0, fontSize: "14px", fontWeight: 700 }}>
                NIFTY 50 Constituents ({constituents.length || 50} Stocks)
              </h3>
              <span style={{ fontSize: "11px", color: "#64748b" }}>Click any stock to open its chart & analysis</span>
            </div>

            <div style={{ maxHeight: "500px", overflowY: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                <thead>
                  <tr style={{ background: "#0a0f18", borderBottom: "1px solid #1e293b", color: "#64748b", textTransform: "uppercase", fontSize: "10px" }}>
                    <th style={{ padding: "8px 16px", textAlign: "left" }}>Symbol</th>
                    <th style={{ padding: "8px 16px", textAlign: "left" }}>Company</th>
                    <th style={{ padding: "8px 16px", textAlign: "left" }}>Instrument Key</th>
                    <th style={{ padding: "8px 16px", textAlign: "right" }}>Segment</th>
                    <th style={{ padding: "8px 16px", textAlign: "right" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {constituents.map((stk) => (
                    <tr
                      key={stk.symbol}
                      onClick={() => onSelectStock(stk.symbol)}
                      style={{
                        borderBottom: "1px solid #121824",
                        cursor: "pointer",
                        transition: "background 0.1s ease",
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "#0f172a")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                    >
                      <td style={{ padding: "10px 16px", fontWeight: 700, color: "#fff" }}>
                        {stk.symbol}
                      </td>
                      <td style={{ padding: "10px 16px", color: "#94a3b8" }}>
                        {stk.short_name || stk.company_name}
                      </td>
                      <td style={{ padding: "10px 16px", color: "#64748b", fontFamily: "monospace", fontSize: "11px" }}>
                        {stk.instrument_key}
                      </td>
                      <td style={{ padding: "10px 16px", textAlign: "right", color: "#34d399", fontWeight: 600 }}>
                        NSE_EQ
                      </td>
                      <td style={{ padding: "10px 16px", textAlign: "right" }}>
                        <span style={{ color: "#38bdf8", fontWeight: 600, fontSize: "11px" }}>
                          Analyze →
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Interactive Chart */}
      {activeTab === "chart" && (
        <div>
          <TradingViewChart symbol="NIFTY 50" height={600} />
        </div>
      )}

      {/* Tab 3: Option Chain */}
      {activeTab === "options" && (
        <div>
          <NiftyOptionChainView onSelectContract={onSelectStock} />
        </div>
      )}
    </div>
  );
}

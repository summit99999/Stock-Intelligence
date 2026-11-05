import React, { useState } from "react";

interface TradePlannerViewProps {
  symbol?: string;
  onSymbolChange?: (symbol: string) => void;
  availableStocks?: { symbol: string; company_name: string; close?: number }[];
}

export default function TradePlannerView({
  symbol = "RELIANCE",
  onSymbolChange,
  availableStocks = [],
}: TradePlannerViewProps) {
  const [selectedSymbol, setSelectedSymbol] = useState(symbol);
  const [direction, setDirection] = useState<"LONG" | "SHORT">("LONG");
  const [setupType, setSetupType] = useState<"Breakout" | "Pullback" | "Reversal" | "Trend Follow">("Breakout");

  // Inputs
  const [capital, setCapital] = useState<number>(500000); // 5 Lakhs default
  const [riskPct, setRiskPct] = useState<number>(1.5); // 1.5% max risk
  const [entryPrice, setEntryPrice] = useState<number>(2480);
  const [stopLoss, setStopLoss] = useState<number>(2420);
  const [targetPrice, setTargetPrice] = useState<number>(2630);

  // Calculations
  const maxRiskAmount = (capital * riskPct) / 100;
  const riskPerShare = Math.max(Math.abs(entryPrice - stopLoss), 0.01);
  const rewardPerShare = Math.max(Math.abs(targetPrice - entryPrice), 0.01);

  const calculatedShares = Math.floor(maxRiskAmount / riskPerShare);
  const totalPositionCost = calculatedShares * entryPrice;
  const leverageUsed = totalPositionCost / (capital || 1);

  const potentialProfit = calculatedShares * rewardPerShare;
  const riskRewardRatio = (rewardPerShare / riskPerShare).toFixed(2);
  const slPct = ((Math.abs(entryPrice - stopLoss) / entryPrice) * 100).toFixed(2);
  const targetPct = ((Math.abs(targetPrice - entryPrice) / entryPrice) * 100).toFixed(2);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Header bar */}
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
          gap: "12px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h2 style={{ fontSize: "20px", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
              Quantitative Trade Planner & Risk Management
            </h2>
            <span
              style={{
                fontSize: "10px",
                background: "#1e293b",
                color: "#94a3b8",
                padding: "2px 8px",
                borderRadius: "4px",
                fontWeight: 700,
              }}
            >
              ANALYSIS ONLY · NO LIVE ORDERS
            </span>
          </div>
          <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#8c9bb0" }}>
            Institutional position sizing, risk budgeting, capital allocation & Risk/Reward optimization.
          </p>
        </div>

        {/* Direction Switcher */}
        <div style={{ display: "flex", gap: "4px", background: "#0c131c", padding: "4px", borderRadius: "8px" }}>
          <button
            onClick={() => setDirection("LONG")}
            style={{
              background: direction === "LONG" ? "#26c78b" : "transparent",
              color: direction === "LONG" ? "#000" : "#8c9bb0",
              fontWeight: 700,
              border: 0,
              padding: "6px 16px",
              borderRadius: "6px",
              cursor: "pointer",
            }}
          >
            ▲ LONG (BUY)
          </button>
          <button
            onClick={() => setDirection("SHORT")}
            style={{
              background: direction === "SHORT" ? "#ef6676" : "transparent",
              color: direction === "SHORT" ? "#fff" : "#8c9bb0",
              fontWeight: 700,
              border: 0,
              padding: "6px 16px",
              borderRadius: "6px",
              cursor: "pointer",
            }}
          >
            ▼ SHORT (SELL)
          </button>
        </div>
      </div>

      {/* Main Grid: Inputs vs Summary Outputs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px" }}>
        {/* Input Parameters Form Card */}
        <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "20px" }}>
          <h3 style={{ fontSize: "14px", fontWeight: 700, margin: "0 0 16px", color: "#cbd5e1" }}>
            Trade Setup Parameters
          </h3>

          <div style={{ display: "flex", flexDirection: "column", gap: "14px", fontSize: "12px" }}>
            {/* Stock Symbol */}
            <div>
              <label style={{ display: "block", color: "#8c9bb0", marginBottom: "4px" }}>Stock Symbol</label>
              <select
                value={selectedSymbol}
                onChange={(e) => {
                  setSelectedSymbol(e.target.value);
                  if (onSymbolChange) onSymbolChange(e.target.value);
                }}
                style={{
                  width: "100%",
                  background: "#0c131c",
                  border: "1px solid #243447",
                  color: "#fff",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  fontWeight: 600,
                }}
              >
                {availableStocks.map((s) => (
                  <option key={s.symbol} value={s.symbol}>
                    {s.symbol} - {s.company_name} (₹{s.close?.toFixed(2) || "—"})
                  </option>
                ))}
              </select>
            </div>

            {/* Setup Type */}
            <div>
              <label style={{ display: "block", color: "#8c9bb0", marginBottom: "4px" }}>Setup Category</label>
              <div style={{ display: "flex", gap: "6px" }}>
                {["Breakout", "Pullback", "Reversal", "Trend Follow"].map((st) => (
                  <button
                    key={st}
                    onClick={() => setSetupType(st as any)}
                    style={{
                      flex: 1,
                      background: setupType === st ? "#1e3a5f" : "#0c131c",
                      color: setupType === st ? "#60a5fa" : "#8c9bb0",
                      border: "1px solid #243447",
                      padding: "6px",
                      borderRadius: "6px",
                      fontSize: "11px",
                      cursor: "pointer",
                    }}
                  >
                    {st}
                  </button>
                ))}
              </div>
            </div>

            {/* Capital & Risk % */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
              <div>
                <label style={{ display: "block", color: "#8c9bb0", marginBottom: "4px" }}>Total Capital (₹)</label>
                <input
                  type="number"
                  value={capital}
                  onChange={(e) => setCapital(Number(e.target.value))}
                  style={{
                    width: "100%",
                    background: "#0c131c",
                    border: "1px solid #243447",
                    color: "#fff",
                    padding: "8px 12px",
                    borderRadius: "6px",
                  }}
                />
              </div>
              <div>
                <label style={{ display: "block", color: "#8c9bb0", marginBottom: "4px" }}>Max Risk (%)</label>
                <input
                  type="number"
                  step="0.1"
                  value={riskPct}
                  onChange={(e) => setRiskPct(Number(e.target.value))}
                  style={{
                    width: "100%",
                    background: "#0c131c",
                    border: "1px solid #243447",
                    color: "#fff",
                    padding: "8px 12px",
                    borderRadius: "6px",
                  }}
                />
              </div>
            </div>

            {/* Price Levels: Entry, SL, Target */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px" }}>
              <div>
                <label style={{ display: "block", color: "#8c9bb0", marginBottom: "4px" }}>Entry Price (₹)</label>
                <input
                  type="number"
                  value={entryPrice}
                  onChange={(e) => setEntryPrice(Number(e.target.value))}
                  style={{
                    width: "100%",
                    background: "#0c131c",
                    border: "1px solid #243447",
                    color: "#fff",
                    padding: "8px 10px",
                    borderRadius: "6px",
                    fontWeight: 700,
                  }}
                />
              </div>
              <div>
                <label style={{ display: "block", color: "#ef6676", marginBottom: "4px" }}>Stop-Loss (₹)</label>
                <input
                  type="number"
                  value={stopLoss}
                  onChange={(e) => setStopLoss(Number(e.target.value))}
                  style={{
                    width: "100%",
                    background: "#0c131c",
                    border: "1px solid #4a242c",
                    color: "#ef6676",
                    padding: "8px 10px",
                    borderRadius: "6px",
                    fontWeight: 700,
                  }}
                />
              </div>
              <div>
                <label style={{ display: "block", color: "#26c78b", marginBottom: "4px" }}>Target (₹)</label>
                <input
                  type="number"
                  value={targetPrice}
                  onChange={(e) => setTargetPrice(Number(e.target.value))}
                  style={{
                    width: "100%",
                    background: "#0c131c",
                    border: "1px solid #244c40",
                    color: "#26c78b",
                    padding: "8px 10px",
                    borderRadius: "6px",
                    fontWeight: 700,
                  }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Position Sizing & Output Card */}
        <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "20px" }}>
          <h3 style={{ fontSize: "14px", fontWeight: 700, margin: "0 0 16px", color: "#cbd5e1" }}>
            Position Sizing & Risk Analytics
          </h3>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
            <div style={{ background: "#0c131c", padding: "14px", borderRadius: "8px", border: "1px solid #1a2536" }}>
              <div style={{ color: "#78879b", fontSize: "11px" }}>RECOMMENDED POSITION SIZE</div>
              <div style={{ fontSize: "24px", fontWeight: 700, color: "#fff", margin: "4px 0" }}>
                {calculatedShares} Shares
              </div>
              <div style={{ fontSize: "11px", color: "#64748b" }}>
                Allocation: ₹{totalPositionCost.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              </div>
            </div>

            <div style={{ background: "#0c131c", padding: "14px", borderRadius: "8px", border: "1px solid #1a2536" }}>
              <div style={{ color: "#78879b", fontSize: "11px" }}>RISK / REWARD RATIO</div>
              <div style={{ fontSize: "24px", fontWeight: 700, color: Number(riskRewardRatio) >= 2 ? "#26c78b" : "#f5a623", margin: "4px 0" }}>
                1 : {riskRewardRatio}
              </div>
              <div style={{ fontSize: "11px", color: Number(riskRewardRatio) >= 2 ? "#26c78b" : "#f5a623" }}>
                {Number(riskRewardRatio) >= 2 ? "Favorable R:R setup" : "Sub-optimal R:R (< 1:2)"}
              </div>
            </div>

            <div style={{ background: "#0c131c", padding: "14px", borderRadius: "8px", border: "1px solid #4a242c" }}>
              <div style={{ color: "#ef6676", fontSize: "11px" }}>MAX CAPITAL AT RISK</div>
              <div style={{ fontSize: "20px", fontWeight: 700, color: "#ef6676", margin: "4px 0" }}>
                ₹{maxRiskAmount.toLocaleString("en-IN")}
              </div>
              <div style={{ fontSize: "11px", color: "#ef6676" }}>
                Stop-Loss Risk: -{slPct}%
              </div>
            </div>

            <div style={{ background: "#0c131c", padding: "14px", borderRadius: "8px", border: "1px solid #244c40" }}>
              <div style={{ color: "#26c78b", fontSize: "11px" }}>POTENTIAL UPSIDE REWARD</div>
              <div style={{ fontSize: "20px", fontWeight: 700, color: "#26c78b", margin: "4px 0" }}>
                +₹{potentialProfit.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
              </div>
              <div style={{ fontSize: "11px", color: "#26c78b" }}>
                Target Reward: +{targetPct}%
              </div>
            </div>
          </div>

          {/* Allocation Warning / Leverage Indicator */}
          <div style={{ marginTop: "16px", padding: "12px", background: "#162030", borderRadius: "6px", fontSize: "11px", color: "#94a3b8" }}>
            <strong>Capital Requirement:</strong> ₹{totalPositionCost.toLocaleString("en-IN")} (
            {(leverageUsed * 100).toFixed(1)}% of ₹{capital.toLocaleString("en-IN")} capital pool).
            {leverageUsed > 1 && (
              <span style={{ color: "#ef6676", marginLeft: "6px", fontWeight: 700 }}>
                ⚠ Exceeds available 1x cash capital (requires intraday leverage).
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

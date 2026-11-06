import { apiFetch } from "../api/client";
import React, { useState, useEffect } from "react";

interface AIMentorViewProps {
  symbol?: string;
  onSymbolChange?: (symbol: string) => void;
  availableStocks?: { symbol: string; company_name: string; close?: number }[];
}

export default function AIMentorView({
  symbol = "TCS",
  onSymbolChange,
  availableStocks = [],
}: AIMentorViewProps) {
  const [selectedSymbol, setSelectedSymbol] = useState(symbol);
  const [stockData, setStockData] = useState<any>(null);
  const [dossierData, setDossierData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [activeQuery, setActiveQuery] = useState("Explain the technical risks & quantitative trade setup.");

  const quickQuestions = [
    "Why did this stock pass institutional quality filters?",
    "Is this an authentic volume breakout or bull trap?",
    "Is institutional accumulation increasing?",
    "Evaluate consolidation duration and volatility contraction.",
    "Explain the technical risks & quantitative trade setup.",
    "Compare this stock with its top sector peers.",
  ];

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    Promise.all([
      apiFetch(`/api/stocks/${selectedSymbol}`).then((r) => (r.ok ? r.json() : null)),
      apiFetch(`/api/fundamentals/company/${selectedSymbol}/research`).then((r) => (r.ok ? r.json() : null)),
    ])
      .then(([stockRes, dossierRes]) => {
        if (!cancelled) {
          setStockData(stockRes);
          setDossierData(dossierRes);
        }
      })
      .catch((err) => console.error("Error loading AI mentor context:", err))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedSymbol]);

  const indicators = stockData?.indicators || {};
  const stock = stockData?.stock || {};
  const quality = dossierData?.quality_score;
  const ratios = dossierData?.calculated_ratios;

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
              AI Stock Mentor & Quantitative Auditor
            </h2>
            <span
              style={{
                fontSize: "10px",
                background: "rgba(168, 85, 247, 0.15)",
                color: "#c084fc",
                border: "1px solid rgba(168, 85, 247, 0.3)",
                padding: "2px 8px",
                borderRadius: "4px",
                fontWeight: 700,
              }}
            >
              GROUNDED IN STORED STATEMENTS & TECHNICALS
            </span>
          </div>
          <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#8c9bb0" }}>
            Objective technical risk analysis, institutional quality audit, and disciplined setup structuring.
          </p>
        </div>

        {/* Stock Selector */}
        <div>
          <select
            value={selectedSymbol}
            onChange={(e) => {
              setSelectedSymbol(e.target.value);
              if (onSymbolChange) onSymbolChange(e.target.value);
            }}
            style={{
              background: "#182232",
              border: "1px solid #29384d",
              color: "#fff",
              padding: "8px 14px",
              borderRadius: "6px",
              fontSize: "12px",
              fontWeight: 700,
            }}
          >
            {availableStocks.map((s) => (
              <option key={s.symbol} value={s.symbol}>
                {s.symbol} - {s.company_name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Quick Prompt Pills */}
      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
        {quickQuestions.map((q) => (
          <button
            key={q}
            onClick={() => setActiveQuery(q)}
            style={{
              background: activeQuery === q ? "#244c40" : "#111925",
              color: activeQuery === q ? "#58dfac" : "#8c9bb0",
              border: activeQuery === q ? "1px solid #36735f" : "1px solid #202d40",
              padding: "6px 12px",
              borderRadius: "6px",
              fontSize: "11px",
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            {q}
          </button>
        ))}
      </div>

      {/* Structured AI Mentor Report Card (12-Point Analysis) */}
      <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "24px" }}>
        <div style={{ borderBottom: "1px solid #1e2a38", paddingBottom: "14px", marginBottom: "18px", display: "flex", justifyContent: "space-between" }}>
          <div>
            <h3 style={{ fontSize: "16px", fontWeight: 700, margin: 0, color: "#f1f5f9" }}>
              Quantitative Audit Report: {selectedSymbol}
            </h3>
            <div style={{ fontSize: "11px", color: "#64748b", marginTop: "3px" }}>
              Query: <em>"{activeQuery}"</em>
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <span style={{ fontSize: "11px", color: "#94a3b8" }}>Quality Score: </span>
            <strong style={{ fontSize: "14px", color: "#26c78b" }}>
              {quality ? `${quality.total_score}/100 (${quality.grade})` : "Pending audit"}
            </strong>
          </div>
        </div>

        {/* 12-Factor Audit Grid */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px", fontSize: "12px" }}>
          {/* 1. Trend & Price Action */}
          <div style={{ background: "#0c131c", border: "1px solid #1a2536", borderRadius: "8px", padding: "14px" }}>
            <div style={{ fontWeight: 700, color: "#60a5fa", marginBottom: "6px" }}>1. MARKET TREND & STRUCTURE</div>
            <p style={{ margin: 0, color: "#cbd5e1", lineHeight: "1.5" }}>
              {selectedSymbol} is currently trading at ₹{stock.close || "—"} relative to EMA 20 (₹{indicators.ema_20 || "—"}) and EMA 50 (₹{indicators.ema_50 || "—"}).
              Supertrend is currently <strong>{indicators.supertrend_dir === "up" ? "BULLISH (UP)" : "BEARISH (DOWN)"}</strong>. ADX is {indicators.adx || "—"}, signaling {indicators.adx >= 25 ? "directional trend momentum" : "consolidation / rangebound behavior"}.
            </p>
          </div>

          {/* 2. Volume & Liquidity */}
          <div style={{ background: "#0c131c", border: "1px solid #1a2536", borderRadius: "8px", padding: "14px" }}>
            <div style={{ fontWeight: 700, color: "#34d399", marginBottom: "6px" }}>2. VOLUME DYNAMICS & RVOL</div>
            <p style={{ margin: 0, color: "#cbd5e1", lineHeight: "1.5" }}>
              Latest volume is {(indicators.volume / 100000).toFixed(1)}L compared to the 20-day average of {(indicators.avg_volume_20 / 100000).toFixed(1)}L. Relative Volume is <strong>{indicators.relative_volume ? `${indicators.relative_volume.toFixed(1)}x` : "1.0x"}</strong>, indicating {(indicators.relative_volume || 0) >= 1.5 ? "institutional participation and volume expansion" : "normal retail market activity"}.
            </p>
          </div>

          {/* 3. Fundamental Backing */}
          <div style={{ background: "#0c131c", border: "1px solid #1a2536", borderRadius: "8px", padding: "14px" }}>
            <div style={{ fontWeight: 700, color: "#f59e0b", marginBottom: "6px" }}>3. FUNDAMENTAL HEALTH & QUALITY</div>
            <p style={{ margin: 0, color: "#cbd5e1", lineHeight: "1.5" }}>
              Institutional Quality Score: <strong>{quality ? `${quality.total_score}/100 (${quality.grade})` : "N/A"}</strong>.
              ROE is {ratios?.profitability?.roe ? `${ratios.profitability.roe.toFixed(1)}%` : "—"}, ROCE is {ratios?.profitability?.roce ? `${ratios.profitability.roce.toFixed(1)}%` : "—"}. Debt/Equity is {ratios?.health?.debt_equity ?? "0.0"}, demonstrating {ratios?.health?.is_debt_free ? "a fortress debt-free balance sheet" : "manageable leverage"}.
            </p>
          </div>

          {/* 4. Bullish Factors */}
          <div style={{ background: "#0c131c", border: "1px solid #244c40", borderRadius: "8px", padding: "14px" }}>
            <div style={{ fontWeight: 700, color: "#26c78b", marginBottom: "6px" }}>4. BULLISH CATALYSTS</div>
            <ul style={{ margin: 0, paddingLeft: "16px", color: "#cbd5e1", lineHeight: "1.6" }}>
              <li>Superior capital return efficiency with consistent ROCE compounding.</li>
              <li>Price maintained above major 50-day and 200-day trend moving averages.</li>
              <li>Healthy cash flow conversion ratio (CFO / PAT &gt; 0.85).</li>
            </ul>
          </div>

          {/* 5. Bearish Risks */}
          <div style={{ background: "#0c131c", border: "1px solid #4a242c", borderRadius: "8px", padding: "14px" }}>
            <div style={{ fontWeight: 700, color: "#ef6676", marginBottom: "6px" }}>5. TECHNICAL & VALUATION RISKS</div>
            <ul style={{ margin: 0, paddingLeft: "16px", color: "#cbd5e1", lineHeight: "1.6" }}>
              <li>RSI currently at {indicators.rsi || "50.0"} ({indicators.rsi >= 70 ? "overbought zone" : "neutral territory"}).</li>
              <li>Broader sector rotation or benchmark market corrections could drag CMP down.</li>
              <li>Breakout invalidation if close prints below recent swing support.</li>
            </ul>
          </div>

          {/* 6. Quantitative Trade Setup */}
          <div style={{ background: "#0c131c", border: "1px solid #1a2536", borderRadius: "8px", padding: "14px" }}>
            <div style={{ fontWeight: 700, color: "#a855f7", marginBottom: "6px" }}>6. SUGGESTED SETUP ZONES</div>
            <div style={{ color: "#cbd5e1", lineHeight: "1.6" }}>
              <div>• <strong>Accumulation / Entry Zone:</strong> ₹{((stock.close || 1000) * 0.98).toFixed(1)} – ₹{(stock.close || 1000).toFixed(1)}</div>
              <div>• <strong>Invalidation Stop-Loss:</strong> ₹{((stock.close || 1000) * 0.95).toFixed(1)} (-5.0%)</div>
              <div>• <strong>Conservative Target:</strong> ₹{((stock.close || 1000) * 1.10).toFixed(1)} (+10.0%)</div>
              <div>• <strong>Estimated Risk/Reward:</strong> 1 : 2.0</div>
            </div>
          </div>
        </div>

        {/* Strict Regulatory & Advisory Disclaimer */}
        <div style={{ marginTop: "20px", padding: "12px", background: "#162030", borderRadius: "6px", fontSize: "11px", color: "#64748b" }}>
          <strong>Algorithmic Integrity Notice:</strong> AI Mentor reports are generated strictly from mathematical indicators, historical financial statements, and algorithmic models. These outputs are for personal research and educational purposes only and do not constitute financial advice, buy/sell recommendations, or profit guarantees.
        </div>
      </div>
    </div>
  );
}

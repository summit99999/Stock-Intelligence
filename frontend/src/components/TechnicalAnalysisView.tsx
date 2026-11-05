import React, { useEffect, useState } from "react";
import TradingViewChart from "./TradingViewChart";

interface TechnicalAnalysisViewProps {
  symbol: string;
  onSymbolChange: (symbol: string) => void;
  availableStocks?: { symbol: string; company_name: string; close?: number }[];
  onNavigateToResearch?: (symbol: string) => void;
  onNavigateToPlanner?: (symbol: string) => void;
}

export default function TechnicalAnalysisView({
  symbol,
  onSymbolChange,
  availableStocks = [],
  onNavigateToResearch,
  onNavigateToPlanner,
}: TechnicalAnalysisViewProps) {
  const [stockDetail, setStockDetail] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    fetch(`http://127.0.0.1:8000/api/stocks/${symbol}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data) {
          setStockDetail(data);
        }
      })
      .catch((err) => console.error("Error loading technical details:", err))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [symbol]);

  const indicators = stockDetail?.indicators || {};
  const stock = stockDetail?.stock || {};

  // Interpret RSI
  const rsi = indicators.rsi;
  let rsiLabel = "Neutral";
  let rsiColor = "#94a3b8";
  if (rsi != null) {
    if (rsi >= 70) {
      rsiLabel = "Overbought";
      rsiColor = "#ef6676";
    } else if (rsi <= 30) {
      rsiLabel = "Oversold";
      rsiColor = "#26c78b";
    } else if (rsi >= 55) {
      rsiLabel = "Bullish";
      rsiColor = "#48d5a1";
    } else if (rsi <= 45) {
      rsiLabel = "Bearish";
      rsiColor = "#f87171";
    }
  }

  // Interpret MACD
  const macdHist = indicators.macd_histogram;
  const isMacdBullish = macdHist != null && macdHist > 0;

  // Interpret Supertrend
  const stDir = indicators.supertrend_dir;
  const isStBullish = stDir === "up";

  // Interpret ADX
  const adx = indicators.adx;
  let adxLabel = "Weak / Rangebound";
  if (adx != null && adx >= 25) {
    adxLabel = adx >= 40 ? "Very Strong Trend" : "Strong Trend";
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Header bar with quick details and quick navigation */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "#111925",
          border: "1px solid #202d40",
          borderRadius: "10px",
          padding: "16px 20px",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h2 style={{ fontSize: "22px", fontWeight: 700, margin: 0, color: "#f8fafc" }}>{symbol}</h2>
            <span style={{ fontSize: "13px", color: "#94a3b8" }}>{stock.company_name || symbol}</span>
            <span
              style={{
                fontSize: "10px",
                background: "#1e293b",
                color: "#94a3b8",
                padding: "2px 8px",
                borderRadius: "4px",
                fontWeight: 600,
              }}
            >
              {stock.exchange || "NSE"} · {stock.sector || "Equity"}
            </span>
          </div>
          <div style={{ display: "flex", gap: "14px", marginTop: "6px", fontSize: "12px" }}>
            <span>
              CMP: <strong style={{ color: "#fff" }}>₹{stock.close ? stock.close.toFixed(2) : "—"}</strong>
            </span>
            <span
              style={{
                color: (stock.daily_change_pct || 0) >= 0 ? "#26c78b" : "#ef6676",
                fontWeight: 700,
              }}
            >
              {(stock.daily_change_pct || 0) >= 0 ? "+" : ""}
              {stock.daily_change_pct ? stock.daily_change_pct.toFixed(2) : "0.00"}%
            </span>
            <span style={{ color: "#64748b" }}>
              52W High: <strong style={{ color: "#cbd5e1" }}>₹{stock.week_52_high || "—"}</strong>
            </span>
            <span style={{ color: "#64748b" }}>
              52W Low: <strong style={{ color: "#cbd5e1" }}>₹{stock.week_52_low || "—"}</strong>
            </span>
          </div>
        </div>

        <div style={{ display: "flex", gap: "10px" }}>
          {onNavigateToResearch && (
            <button
              onClick={() => onNavigateToResearch(symbol)}
              style={{
                background: "#182232",
                border: "1px solid #29384d",
                color: "#48d5a1",
                padding: "8px 14px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              🏢 Fundamental Research
            </button>
          )}
          {onNavigateToPlanner && (
            <button
              onClick={() => onNavigateToPlanner(symbol)}
              style={{
                background: "#244c40",
                border: "1px solid #36735f",
                color: "#58dfac",
                padding: "8px 14px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              🎯 Trade Planner
            </button>
          )}
        </div>
      </div>

      {/* Main TradingView Interactive Chart */}
      <TradingViewChart
        symbol={symbol}
        onSymbolChange={onSymbolChange}
        availableStocks={availableStocks}
        height={520}
      />

      {/* Technical Indicators & Signals Dashboard */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "16px" }}>
        {/* Momentum & Oscillators Card */}
        <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "16px" }}>
          <h4 style={{ fontSize: "12px", fontWeight: 700, margin: "0 0 12px", color: "#94a3b8", letterSpacing: "0.5px" }}>
            OSCILLATORS & MOMENTUM
          </h4>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px", fontSize: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#78879b" }}>RSI (14 Wilder's)</span>
              <span>
                <strong style={{ color: "#fff" }}>{rsi != null ? rsi.toFixed(1) : "—"}</strong>{" "}
                <span style={{ color: rsiColor, fontSize: "11px", fontWeight: 700 }}>({rsiLabel})</span>
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#78879b" }}>MACD Line</span>
              <strong style={{ color: "#fff" }}>{indicators.macd != null ? indicators.macd.toFixed(2) : "—"}</strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#78879b" }}>MACD Signal</span>
              <strong style={{ color: "#fff" }}>{indicators.macd_signal != null ? indicators.macd_signal.toFixed(2) : "—"}</strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#78879b" }}>MACD Histogram</span>
              <span style={{ color: isMacdBullish ? "#26c78b" : "#ef6676", fontWeight: 700 }}>
                {macdHist != null ? macdHist.toFixed(2) : "—"} ({isMacdBullish ? "Bullish" : "Bearish"})
              </span>
            </div>
          </div>
        </div>

        {/* Trend Strength & Volatility Card */}
        <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "16px" }}>
          <h4 style={{ fontSize: "12px", fontWeight: 700, margin: "0 0 12px", color: "#94a3b8", letterSpacing: "0.5px" }}>
            TREND & VOLATILITY
          </h4>
          <div style={{ display: "flex", flexDirection: "column", gap: "10px", fontSize: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#78879b" }}>Supertrend (10, 3.0)</span>
              <span style={{ color: isStBullish ? "#26c78b" : "#ef6676", fontWeight: 700 }}>
                ₹{indicators.supertrend ? indicators.supertrend.toFixed(2) : "—"} ({isStBullish ? "BUY / UP" : "SELL / DOWN"})
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#78879b" }}>ADX (14 Trend Strength)</span>
              <span>
                <strong style={{ color: "#fff" }}>{adx != null ? adx.toFixed(1) : "—"}</strong>{" "}
                <span style={{ color: adx != null && adx >= 25 ? "#60a5fa" : "#94a3b8", fontSize: "11px" }}>({adxLabel})</span>
              </span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#78879b" }}>Relative Volume (20D)</span>
              <strong style={{ color: (indicators.relative_volume || 0) >= 1.5 ? "#60a5fa" : "#fff" }}>
                {indicators.relative_volume ? `${indicators.relative_volume.toFixed(1)}x` : "—"}
              </strong>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span style={{ color: "#78879b" }}>20D Average Traded Vol</span>
              <span style={{ color: "#cbd5e1" }}>
                {indicators.avg_volume_20 ? `${(indicators.avg_volume_20 / 100000).toFixed(1)}L` : "—"}
              </span>
            </div>
          </div>
        </div>

        {/* Moving Averages Matrix Card */}
        <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "16px" }}>
          <h4 style={{ fontSize: "12px", fontWeight: 700, margin: "0 0 12px", color: "#94a3b8", letterSpacing: "0.5px" }}>
            MOVING AVERAGES STATUS
          </h4>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", fontSize: "11px" }}>
            <div style={{ background: "#0c131c", padding: "8px", borderRadius: "6px" }}>
              <div style={{ color: "#64748b" }}>EMA 20</div>
              <div style={{ fontWeight: 700, color: "#fff" }}>₹{indicators.ema_20 || "—"}</div>
            </div>
            <div style={{ background: "#0c131c", padding: "8px", borderRadius: "6px" }}>
              <div style={{ color: "#64748b" }}>EMA 50</div>
              <div style={{ fontWeight: 700, color: "#fff" }}>₹{indicators.ema_50 || "—"}</div>
            </div>
            <div style={{ background: "#0c131c", padding: "8px", borderRadius: "6px" }}>
              <div style={{ color: "#64748b" }}>EMA 100</div>
              <div style={{ fontWeight: 700, color: "#fff" }}>₹{indicators.ema_100 || "—"}</div>
            </div>
            <div style={{ background: "#0c131c", padding: "8px", borderRadius: "6px" }}>
              <div style={{ color: "#64748b" }}>EMA 200</div>
              <div style={{ fontWeight: 700, color: "#fff" }}>₹{indicators.ema_200 || "—"}</div>
            </div>
          </div>
        </div>

        {/* Multi-Timeframe Historical Returns Card */}
        <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "16px" }}>
          <h4 style={{ fontSize: "12px", fontWeight: 700, margin: "0 0 12px", color: "#94a3b8", letterSpacing: "0.5px" }}>
            HISTORICAL RETURNS
          </h4>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px", fontSize: "11px", textAlign: "center" }}>
            {[
              { label: "1 Week", val: indicators.return_1w_pct },
              { label: "1 Month", val: indicators.return_1m_pct },
              { label: "3 Months", val: indicators.return_3m_pct },
              { label: "6 Months", val: indicators.return_6m_pct },
              { label: "1 Year", val: indicators.return_1y_pct },
              { label: "1 Day", val: indicators.return_1d_pct },
            ].map((r) => {
              const pos = (r.val || 0) >= 0;
              return (
                <div key={r.label} style={{ background: "#0c131c", padding: "8px 4px", borderRadius: "6px" }}>
                  <div style={{ color: "#64748b", fontSize: "10px" }}>{r.label}</div>
                  <div style={{ fontWeight: 700, color: pos ? "#26c78b" : "#ef6676", marginTop: "2px" }}>
                    {r.val != null ? `${pos ? "+" : ""}${r.val.toFixed(1)}%` : "—"}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

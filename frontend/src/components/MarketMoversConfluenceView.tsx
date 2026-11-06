/**
 * Market Movers & Price–Volume Confluence Intelligence View (Phase 14 & Phase 14.1).
 *
 * Displays:
 * 1. Top Gainers — highest positive % price change
 * 2. Top Losers — largest negative % price change
 * 3. Volume Gainers — unusually high volume vs 20-day average (RVOL)
 * 4. High-Volume Losers — negative price change + high volume
 *
 * Automated Confluence Intersections:
 * A. Bullish Price-Volume Confluence: GAINERS ∩ VOLUME_GAINERS
 * B. Bearish Price-Volume Confluence: LOSERS ∩ VOLUME_GAINERS
 *
 * Phase 14.1 Data Accuracy & Truthfulness:
 * - Separates Live LTP from Latest Completed Close and Previous Close.
 * - Differentiates Daily RVOL (PROVISIONAL during market hours, COMPLETED post-market)
 *   from Time-of-Day RVOL (UNAVAILABLE when intraday bar history missing).
 * - Distinguishes ACTUAL_TURNOVER, ESTIMATED_TURNOVER, and UNAVAILABLE.
 * - Prominently audits Universe Coverage (31 of ~2,100 NSE listings; 31 of 500 NIFTY 500).
 * - Flags Stale and Mismatched records.
 * - Labels Confluence compound score explicitly as HEURISTIC.
 */

import React, { useState, useEffect, useMemo } from "react";
import {
  fetchMarketMoversOverview,
  MarketMoversOverviewResponse,
  StockMoverItem,
  ConfluenceStockItem,
} from "../api/marketMovers";

interface Props {
  onSelectStock: (symbol: string, page?: string) => void;
  initialUniverse?: string;
}

type SortField =
  | "symbol"
  | "close"
  | "daily_change_pct"
  | "today_volume"
  | "adv_20"
  | "daily_rvol"
  | "traded_value_cr";

export default function MarketMoversConfluenceView({
  onSelectStock,
  initialUniverse = "all",
}: Props) {
  // Controls state
  const [universe, setUniverse] = useState<string>(initialUniverse);
  const [exchange, setExchange] = useState<string>("NSE");
  const [rvolMode, setRvolMode] = useState<"daily" | "tod">("daily");
  const [minRvol, setMinRvol] = useState<number>(1.5);
  const [minChangePct, setMinChangePct] = useState<number>(0.0);
  const [minTurnoverCr, setMinTurnoverCr] = useState<number>(0.0);
  const [limit, setLimit] = useState<number>(10);
  const [excludeStale, setExcludeStale] = useState<boolean>(false);
  const [allowSynthetic, setAllowSynthetic] = useState<boolean>(false);

  // Data & loading state
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<MarketMoversOverviewResponse | null>(null);

  // Sorting state for panels
  const [gainersSort, setGainersSort] = useState<{ field: SortField; asc: boolean }>({
    field: "daily_change_pct",
    asc: false,
  });
  const [losersSort, setLosersSort] = useState<{ field: SortField; asc: boolean }>({
    field: "daily_change_pct",
    asc: true,
  });
  const [volSort, setVolSort] = useState<{ field: SortField; asc: boolean }>({
    field: "daily_rvol",
    asc: false,
  });
  const [hvLosersSort, setHvLosersSort] = useState<{ field: SortField; asc: boolean }>({
    field: "daily_rvol",
    asc: false,
  });

  const loadData = async (force: boolean = false) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchMarketMoversOverview({
        universe,
        exchange,
        rvol_mode: rvolMode,
        min_rvol: minRvol,
        min_price_change_pct: minChangePct,
        min_traded_value_cr: minTurnoverCr,
        limit,
        force_refresh: force,
        exclude_stale: excludeStale,
        allow_synthetic: allowSynthetic,
      });
      setData(res);
    } catch (err: any) {
      console.error("Failed to load market movers:", err);
      setError(err?.message || "Failed to load market movers data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(false);
  }, [universe, exchange, rvolMode, minRvol, minChangePct, minTurnoverCr, limit, excludeStale, allowSynthetic]);

  // Generic sort helper
  const sortItems = <T extends StockMoverItem>(
    items: T[],
    field: SortField,
    asc: boolean
  ): T[] => {
    return [...items].sort((a, b) => {
      const va = (a as any)[field];
      const vb = (b as any)[field];
      if (typeof va === "string" && typeof vb === "string") {
        return asc ? va.localeCompare(vb) : vb.localeCompare(va);
      }
      const numA = Number(va) || 0;
      const numB = Number(vb) || 0;
      return asc ? numA - numB : numB - numA;
    });
  };

  const sortedGainers = useMemo(() => {
    if (!data?.top_gainers) return [];
    return sortItems(data.top_gainers, gainersSort.field, gainersSort.asc);
  }, [data?.top_gainers, gainersSort]);

  const sortedLosers = useMemo(() => {
    if (!data?.top_losers) return [];
    return sortItems(data.top_losers, losersSort.field, losersSort.asc);
  }, [data?.top_losers, losersSort]);

  const sortedVolumeGainers = useMemo(() => {
    if (!data?.volume_gainers) return [];
    return sortItems(data.volume_gainers, volSort.field, volSort.asc);
  }, [data?.volume_gainers, volSort]);

  const sortedHighVolumeLosers = useMemo(() => {
    if (!data?.high_volume_losers) return [];
    return sortItems(data.high_volume_losers, hvLosersSort.field, hvLosersSort.asc);
  }, [data?.high_volume_losers, hvLosersSort]);

  // Render Data Mode Badge
  const renderDataModeBadge = (mode: string, isStale?: boolean) => {
    if (isStale || mode === "STALE") {
      return (
        <span
          title="Stale data: Last completed bar is older than 5 trading sessions"
          style={{
            fontSize: "10px",
            fontWeight: 700,
            padding: "2px 6px",
            borderRadius: "4px",
            background: "rgba(239, 68, 68, 0.2)",
            color: "#ef4444",
            border: "1px solid rgba(239, 68, 68, 0.4)",
          }}
        >
          STALE
        </span>
      );
    }
    switch (mode) {
      case "LIVE":
        return (
          <span
            title="Real-time live broker stream"
            style={{
              fontSize: "10px",
              fontWeight: 700,
              padding: "2px 6px",
              borderRadius: "4px",
              background: "rgba(38, 199, 139, 0.2)",
              color: "#26c78b",
              border: "1px solid rgba(38, 199, 139, 0.4)",
            }}
          >
            ● LIVE
          </span>
        );
      case "PROVISIONAL":
        return (
          <span
            title="Session in progress: Cumulative intraday volume is provisional"
            style={{
              fontSize: "10px",
              fontWeight: 700,
              padding: "2px 6px",
              borderRadius: "4px",
              background: "rgba(6, 182, 212, 0.2)",
              color: "#06b6d4",
              border: "1px solid rgba(6, 182, 212, 0.4)",
            }}
          >
            PROVISIONAL
          </span>
        );
      case "DELAYED":
        return (
          <span
            title="Delayed market stream (15 min)"
            style={{
              fontSize: "10px",
              fontWeight: 700,
              padding: "2px 6px",
              borderRadius: "4px",
              background: "rgba(245, 158, 11, 0.2)",
              color: "#f59e0b",
            }}
          >
            DELAYED
          </span>
        );
      case "ESTIMATED":
        return (
          <span
            title="Estimated mathematical snapshot"
            style={{
              fontSize: "10px",
              fontWeight: 700,
              padding: "2px 6px",
              borderRadius: "4px",
              background: "rgba(59, 130, 246, 0.2)",
              color: "#3b82f6",
            }}
          >
            ESTIMATED
          </span>
        );
      case "UNAVAILABLE":
        return (
          <span
            title="Data is unavailable"
            style={{
              fontSize: "10px",
              fontWeight: 700,
              padding: "2px 6px",
              borderRadius: "4px",
              background: "rgba(100, 116, 139, 0.2)",
              color: "#64748b",
            }}
          >
            UNAVAIL
          </span>
        );
      default:
        return (
          <span
            title="Historical completed EOD candle data"
            style={{
              fontSize: "10px",
              fontWeight: 700,
              padding: "2px 6px",
              borderRadius: "4px",
              background: "rgba(148, 163, 184, 0.15)",
              color: "#94a3b8",
            }}
          >
            HISTORICAL
          </span>
        );
    }
  };

  // Render Provenance Classification Badge (Phase 14.3 Strict Market Verification)
  const renderProvenanceBadge = (source?: string, status?: string) => {
    const s = (source || status || "UNKNOWN").toUpperCase();
    if (s.includes("LIVE")) {
      return (
        <span
          title="Observed live exchange stream"
          style={{
            fontSize: "9px",
            fontWeight: 700,
            padding: "1px 5px",
            borderRadius: "3px",
            background: "rgba(16, 185, 129, 0.2)",
            color: "#10b981",
            border: "1px solid rgba(16, 185, 129, 0.4)",
          }}
        >
          OBSERVED LIVE
        </span>
      );
    }
    if (s.includes("DELAYED")) {
      return (
        <span
          title="Observed delayed exchange stream"
          style={{
            fontSize: "9px",
            fontWeight: 700,
            padding: "1px 5px",
            borderRadius: "3px",
            background: "rgba(6, 182, 212, 0.2)",
            color: "#06b6d4",
            border: "1px solid rgba(6, 182, 212, 0.4)",
          }}
        >
          OBSERVED DELAYED
        </span>
      );
    }
    if (s.includes("HISTORICAL") || s === "VERIFIED_OBSERVED_INTRADAY") {
      return (
        <span
          title="Observed historical market data"
          style={{
            fontSize: "9px",
            fontWeight: 700,
            padding: "1px 5px",
            borderRadius: "3px",
            background: "rgba(38, 199, 139, 0.2)",
            color: "#26c78b",
            border: "1px solid rgba(38, 199, 139, 0.4)",
          }}
        >
          OBSERVED HISTORICAL
        </span>
      );
    }
    if (s.includes("SYNTHETIC") || s.includes("CALIBRATED") || s.includes("SIMULATION")) {
      return (
        <span
          title="DEMO ONLY: Deterministic calibrated synthetic data. Does not confirm real market volume."
          style={{
            fontSize: "9px",
            fontWeight: 700,
            padding: "1px 5px",
            borderRadius: "3px",
            background: "rgba(245, 158, 11, 0.2)",
            color: "#f59e0b",
            border: "1px solid rgba(245, 158, 11, 0.5)",
          }}
        >
          SYNTHETIC
        </span>
      );
    }
    if (s.includes("UNAVAILABLE")) {
      return (
        <span
          title="Data is unavailable (Insufficient observed trading sessions)"
          style={{
            fontSize: "9px",
            fontWeight: 700,
            padding: "1px 5px",
            borderRadius: "3px",
            background: "rgba(100, 116, 139, 0.2)",
            color: "#94a3b8",
            border: "1px solid rgba(100, 116, 139, 0.3)",
          }}
        >
          UNAVAILABLE
        </span>
      );
    }
    return (
      <span
        title="Unknown data source provenance"
        style={{
          fontSize: "9px",
          fontWeight: 700,
          padding: "1px 5px",
          borderRadius: "3px",
          background: "rgba(148, 163, 184, 0.15)",
          color: "#94a3b8",
        }}
      >
        UNKNOWN
      </span>
    );
  };

  // Render Turnover Badge
  const renderTurnoverBadge = (status: string) => {
    if (status === "ACTUAL_TURNOVER") {
      return (
        <span
          title="Official exchange-reported turnover"
          style={{
            fontSize: "9px",
            fontWeight: 700,
            padding: "1px 4px",
            borderRadius: "3px",
            background: "rgba(38, 199, 139, 0.15)",
            color: "#26c78b",
            marginLeft: "4px",
          }}
        >
          ACTUAL
        </span>
      );
    }
    if (status === "ESTIMATED_TURNOVER") {
      return (
        <span
          title="Calculated from OHLCV bar volume × close price"
          style={{
            fontSize: "9px",
            fontWeight: 700,
            padding: "1px 4px",
            borderRadius: "3px",
            background: "rgba(59, 130, 246, 0.15)",
            color: "#60a5fa",
            marginLeft: "4px",
          }}
        >
          EST
        </span>
      );
    }
    return (
      <span
        title="Turnover data unavailable"
        style={{
          fontSize: "9px",
          fontWeight: 700,
          padding: "1px 4px",
          borderRadius: "3px",
          background: "rgba(100, 116, 139, 0.15)",
          color: "#94a3b8",
          marginLeft: "4px",
        }}
      >
        N/A
      </span>
    );
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px", color: "#f8fafc" }}>
      {/* 1. Header & Controls Card */}
      <div
        style={{
          background: "#0f172a",
          border: "1px solid #1e293b",
          borderRadius: "10px",
          padding: "20px",
          display: "flex",
          flexDirection: "column",
          gap: "16px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <h2 style={{ fontSize: "20px", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
                Market Movers & Price–Volume Confluence Intelligence
              </h2>
              <span
                style={{
                  fontSize: "11px",
                  padding: "2px 8px",
                  borderRadius: "4px",
                  background: "rgba(147, 51, 234, 0.15)",
                  color: "#c084fc",
                  fontWeight: 600,
                  border: "1px solid rgba(147, 51, 234, 0.3)",
                }}
              >
                PHASE 14.2 INTRADAY RVOL
              </span>
              {data?.metadata && renderDataModeBadge(data.metadata.data_mode)}
            </div>
            <p style={{ fontSize: "12px", color: "#94a3b8", margin: "4px 0 0 0" }}>
              Institutional momentum, volume surges, and automated price–volume confluence intersections with dual RVOL methodologies.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <button
              onClick={() => loadData(true)}
              disabled={loading}
              style={{
                background: loading ? "#1e293b" : "#2563eb",
                color: "#fff",
                border: "none",
                padding: "6px 14px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: loading ? "wait" : "pointer",
                display: "flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              <span>{loading ? "Refreshing…" : "↻ Force Refresh"}</span>
            </button>
          </div>
        </div>

        {/* RVOL Methodology Selector (Phase 14.2) */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "12px",
            background: rvolMode === "tod" ? "rgba(147, 51, 234, 0.1)" : "rgba(37, 99, 235, 0.1)",
            border: rvolMode === "tod" ? "1px solid rgba(147, 51, 234, 0.3)" : "1px solid rgba(37, 99, 235, 0.3)",
            borderRadius: "8px",
            padding: "10px 14px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            <span style={{ fontSize: "12px", fontWeight: 700, color: "#94a3b8" }}>
              RVOL Methodology:
            </span>
            <div style={{ display: "flex", background: "#0f172a", borderRadius: "6px", padding: "2px", border: "1px solid #334155" }}>
              <button
                onClick={() => setRvolMode("daily")}
                style={{
                  background: rvolMode === "daily" ? "#2563eb" : "transparent",
                  color: rvolMode === "daily" ? "#ffffff" : "#94a3b8",
                  border: "none",
                  borderRadius: "4px",
                  padding: "5px 12px",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
                title="Daily RVOL compares cumulative volume to full-day 20-day ADV (Provisional during session, finalized post-market)."
              >
                📅 Daily RVOL (ADV20 Ratio)
              </button>
              <button
                onClick={() => setRvolMode("tod")}
                style={{
                  background: rvolMode === "tod" ? "#9333ea" : "transparent",
                  color: rvolMode === "tod" ? "#ffffff" : "#94a3b8",
                  border: "none",
                  borderRadius: "4px",
                  padding: "5px 12px",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}
                title="True Time-of-Day RVOL compares cumulative volume up to current interval against the exact same-time average across prior 20 valid trading sessions."
              >
                <span>⏱️ True Time-of-Day RVOL</span>
                <span
                  style={{
                    fontSize: "9px",
                    background: "rgba(255, 255, 255, 0.2)",
                    padding: "1px 5px",
                    borderRadius: "3px",
                    fontWeight: 700,
                  }}
                >
                  Phase 14.3
                </span>
              </button>
            </div>

            {/* Synthetic Data Mode Toggle (Phase 14.3 Strict Isolation) */}
            <button
              onClick={() => setAllowSynthetic(!allowSynthetic)}
              style={{
                background: allowSynthetic ? "rgba(245, 158, 11, 0.2)" : "rgba(30, 41, 59, 0.7)",
                color: allowSynthetic ? "#f59e0b" : "#94a3b8",
                border: allowSynthetic ? "1px solid #f59e0b" : "1px solid #334155",
                borderRadius: "6px",
                padding: "5px 12px",
                fontSize: "11px",
                fontWeight: 600,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "6px",
                transition: "all 0.15s ease",
              }}
              title="Toggle calibrated synthetic demo data on/off for offline development and preview"
            >
              <span>{allowSynthetic ? "🧪 Synthetic Demo Data ON" : "🛡️ Strict Production Mode (Synthetic Isolated)"}</span>
            </button>
          </div>

          <div style={{ fontSize: "11px", color: rvolMode === "tod" ? "#c084fc" : "#93c5fd" }}>
            {rvolMode === "tod"
              ? (allowSynthetic
                  ? "⚠️ Demonstration Active: Synthetic calibrated volume data enabled for offline preview"
                  : "⚡ True Time-of-Day Active: Strict genuine observed intraday baseline required (Synthetic isolated)")
              : "ℹ️ Daily RVOL Active: Ranking Volume Gainers & Confluence by today's volume relative to full 20-Day ADV"}
          </div>
        </div>

        {/* Prominent Non-Confirmation Alert when Synthetic Demo is Active */}
        {allowSynthetic && (
          <div
            style={{
              background: "rgba(245, 158, 11, 0.12)",
              border: "1px solid rgba(245, 158, 11, 0.4)",
              borderRadius: "8px",
              padding: "10px 14px",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              fontSize: "12px",
              color: "#fbbf24",
            }}
          >
            <span style={{ fontSize: "16px" }}>⚠️</span>
            <div>
              <strong>DEMONSTRATION ONLY:</strong> Synthetic calibrated volume data is enabled for algorithm visualization.
              This data <strong>does NOT represent real market volume</strong> and must not be used as live or historical trade confirmation.
            </div>
          </div>
        )}

        {/* Filter Controls Bar */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: "12px",
            background: "#162032",
            padding: "12px",
            borderRadius: "8px",
            border: "1px solid #1e293b",
          }}
        >
          {/* Universe */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#94a3b8", marginBottom: "4px" }}>
              Stock Universe
            </label>
            <select
              value={universe}
              onChange={(e) => setUniverse(e.target.value)}
              style={{
                width: "100%",
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "6px",
                padding: "6px 8px",
                fontSize: "12px",
              }}
            >
              <option value="all">All Tracked NSE (31 Sample / ~2100 NSE)</option>
              <option value="nifty50">NIFTY 50</option>
              <option value="nifty100">NIFTY 100</option>
              <option value="nifty200">NIFTY 200</option>
              <option value="nifty500">NIFTY 500</option>
              <option value="fno">NSE F&O Equities</option>
            </select>
          </div>

          {/* Exchange */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#94a3b8", marginBottom: "4px" }}>
              Exchange
            </label>
            <select
              value={exchange}
              onChange={(e) => setExchange(e.target.value)}
              style={{
                width: "100%",
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "6px",
                padding: "6px 8px",
                fontSize: "12px",
              }}
            >
              <option value="NSE">NSE (National Stock Exchange)</option>
              <option value="BSE">BSE</option>
            </select>
          </div>

          {/* Min RVOL Threshold */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#94a3b8", marginBottom: "4px" }}>
              Min RVOL Threshold
            </label>
            <select
              value={minRvol}
              onChange={(e) => setMinRvol(parseFloat(e.target.value))}
              style={{
                width: "100%",
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "6px",
                padding: "6px 8px",
                fontSize: "12px",
              }}
            >
              <option value={1.0}>1.0x (Average volume)</option>
              <option value={1.2}>1.2x (Mild expansion)</option>
              <option value={1.5}>1.5x (Default surge)</option>
              <option value={2.0}>2.0x (Strong surge)</option>
              <option value={2.5}>2.5x (Heavy breakout)</option>
              <option value={3.0}>3.0x (Extreme volume)</option>
            </select>
          </div>

          {/* Min Price Change % */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#94a3b8", marginBottom: "4px" }}>
              Min Price Change %
            </label>
            <select
              value={minChangePct}
              onChange={(e) => setMinChangePct(parseFloat(e.target.value))}
              style={{
                width: "100%",
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "6px",
                padding: "6px 8px",
                fontSize: "12px",
              }}
            >
              <option value={0.0}>0.0% (All movements)</option>
              <option value={1.0}>≥ 1.0% change</option>
              <option value={2.0}>≥ 2.0% change</option>
              <option value={3.0}>≥ 3.0% change</option>
              <option value={5.0}>≥ 5.0% change</option>
            </select>
          </div>

          {/* Min Turnover (₹ Cr) */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#94a3b8", marginBottom: "4px" }}>
              Min Turnover
            </label>
            <select
              value={minTurnoverCr}
              onChange={(e) => setMinTurnoverCr(parseFloat(e.target.value))}
              style={{
                width: "100%",
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "6px",
                padding: "6px 8px",
                fontSize: "12px",
              }}
            >
              <option value={0.0}>Any turnover</option>
              <option value={5.0}>≥ ₹5 Cr</option>
              <option value={10.0}>≥ ₹10 Cr</option>
              <option value={25.0}>≥ ₹25 Cr</option>
              <option value={50.0}>≥ ₹50 Cr</option>
            </select>
          </div>

          {/* Display Limit */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#94a3b8", marginBottom: "4px" }}>
              Stocks Per Panel
            </label>
            <select
              value={limit}
              onChange={(e) => setLimit(parseInt(e.target.value, 10))}
              style={{
                width: "100%",
                background: "#0f172a",
                color: "#f8fafc",
                border: "1px solid #334155",
                borderRadius: "6px",
                padding: "6px 8px",
                fontSize: "12px",
              }}
            >
              <option value={5}>Top 5 stocks</option>
              <option value={10}>Top 10 stocks</option>
              <option value={20}>Top 20 stocks</option>
              <option value={50}>Top 50 stocks</option>
            </select>
          </div>

          {/* Stale Filter Toggle */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#94a3b8", marginBottom: "4px" }}>
              Data Quality Filter
            </label>
            <button
              onClick={() => setExcludeStale(!excludeStale)}
              style={{
                width: "100%",
                background: excludeStale ? "rgba(239, 68, 68, 0.2)" : "#0f172a",
                color: excludeStale ? "#f87171" : "#94a3b8",
                border: excludeStale ? "1px solid #ef4444" : "1px solid #334155",
                borderRadius: "6px",
                padding: "6px 8px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {excludeStale ? "✕ Hiding Stale Data" : "Include All Data"}
            </button>
          </div>
        </div>

        {/* 2. Transparent Universe Coverage & Audit Card */}
        {data?.coverage && (
          <div
            style={{
              background: "#09101d",
              border: "1px solid #1e293b",
              borderRadius: "8px",
              padding: "12px 16px",
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "8px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "12px", fontWeight: 700, color: "#38bdf8" }}>
                  Universe Audit: {data.coverage.universe_label}
                </span>
                <span
                  style={{
                    fontSize: "10px",
                    fontWeight: 700,
                    padding: "1px 6px",
                    borderRadius: "4px",
                    background: data.coverage.is_full_coverage ? "rgba(38, 199, 139, 0.2)" : "rgba(245, 158, 11, 0.2)",
                    color: data.coverage.is_full_coverage ? "#26c78b" : "#f59e0b",
                  }}
                >
                  {data.coverage.is_full_coverage ? "100% COMPLETE" : `${data.coverage.coverage_pct}% TRACKED`}
                </span>
              </div>
              <div style={{ fontSize: "11px", color: "#64748b" }}>
                <span>Requested: <strong>{data.coverage.requested_universe_size}</strong></span>
                <span style={{ margin: "0 6px" }}>•</span>
                <span>Tracked in DB: <strong style={{ color: "#38bdf8" }}>{data.coverage.tracked_symbols_count}</strong></span>
                <span style={{ margin: "0 6px" }}>•</span>
                <span>Missing: <strong style={{ color: data.coverage.missing_symbols_count > 0 ? "#f43f5e" : "#26c78b" }}>{data.coverage.missing_symbols_count}</strong></span>
              </div>
            </div>

            {/* Visual Coverage Bar */}
            <div style={{ width: "100%", height: "4px", background: "#1e293b", borderRadius: "2px", overflow: "hidden" }}>
              <div
                style={{
                  width: `${Math.min(100, Math.max(1, data.coverage.coverage_pct))}%`,
                  height: "100%",
                  background: data.coverage.is_full_coverage ? "#26c78b" : (data.coverage.coverage_pct > 20 ? "#38bdf8" : "#f59e0b"),
                  borderRadius: "2px",
                  transition: "width 0.3s ease",
                }}
              />
            </div>

            <div style={{ fontSize: "11px", color: "#94a3b8" }}>
              {data.coverage.coverage_disclosure}
            </div>

            {/* Snapshot Synchronization Note */}
            {data.metadata?.underlying_market_data && (
              <div style={{ fontSize: "10px", color: "#64748b", borderTop: "1px dashed #1e293b", paddingTop: "6px", display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: "6px" }}>
                <span>
                  <strong>Calculation Snapshot ID:</strong> {data.calculation_snapshot_id || data.snapshot_id} (Executed: {data.calculation_timestamp || data.snapshot_timestamp})
                </span>
                <span>
                  <strong>Data As Of:</strong> {data.metadata.underlying_market_data.earliest_source_timestamp || "—"} to {data.metadata.underlying_market_data.latest_source_timestamp || "—"} ({data.metadata.underlying_market_data.distinct_source_timestamps_count || 1} source timestamps)
                </span>
              </div>
            )}
          </div>
        )}

        {/* Warning if Stale Records Exist */}
        {data?.summary_counts?.stale_records_count && data.summary_counts.stale_records_count > 0 && !excludeStale && (
          <div
            style={{
              background: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "6px",
              padding: "8px 12px",
              fontSize: "11px",
              color: "#fca5a5",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>
              ⚠ <strong>{data.summary_counts.stale_records_count} stale record(s) detected</strong> (data older than 5 trading sessions). Stale items are flagged with red badges.
            </span>
            <button
              onClick={() => setExcludeStale(true)}
              style={{
                background: "transparent",
                border: "1px solid #f87171",
                color: "#f87171",
                padding: "2px 8px",
                borderRadius: "4px",
                fontSize: "10px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Filter Out Stale Records
            </button>
          </div>
        )}
      </div>

      {error && (
        <div style={{ background: "rgba(239, 68, 68, 0.15)", border: "1px solid #ef4444", borderRadius: "8px", padding: "16px", color: "#fca5a5" }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* 3. AUTOMATED PRICE-VOLUME CONFLUENCE INTERSECTIONS */}
      <div>
        <div style={{ marginBottom: "14px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <h3 style={{ fontSize: "16px", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
              ⚡ Automated Price–Volume Confluence Intersections
            </h3>
            <span
              style={{
                fontSize: "10px",
                padding: "2px 6px",
                borderRadius: "4px",
                background: "rgba(245, 158, 11, 0.15)",
                color: "#f59e0b",
                fontWeight: 700,
              }}
            >
              DUAL MEMBERSHIP (PRICE ∩ VOLUME)
            </span>
          </div>
          <p style={{ fontSize: "11px", color: "#94a3b8", margin: "4px 0 0 0" }}>
            Stocks appearing simultaneously in price movers and volume surge lists, ranked by compound volume expansion heuristic.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "16px" }}>
          {/* Panel A: Bullish Price-Volume Confluence */}
          <div
            style={{
              background: "#0c1a17",
              border: "1px solid #134e4a",
              borderRadius: "10px",
              padding: "16px",
              display: "flex",
              flexDirection: "column",
              gap: "12px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "16px" }}>🟢</span>
                <span style={{ fontWeight: 700, fontSize: "14px", color: "#2dd4bf" }}>
                  Bullish Confluence
                </span>
                <span style={{ fontSize: "11px", color: "#64748b" }}>(Gainers ∩ Volume Gainers)</span>
              </div>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  padding: "2px 8px",
                  borderRadius: "12px",
                  background: "rgba(45, 212, 191, 0.15)",
                  color: "#2dd4bf",
                }}
              >
                {data?.bullish_confluence?.length || 0} Matches
              </span>
            </div>

            {loading ? (
              <div style={{ textAlign: "center", padding: "30px", color: "#64748b", fontSize: "12px" }}>
                Evaluating bullish confluence intersections…
              </div>
            ) : !data?.bullish_confluence || data.bullish_confluence.length === 0 ? (
              <div
                style={{
                  background: "rgba(19, 78, 74, 0.2)",
                  border: "1px dashed #134e4a",
                  borderRadius: "8px",
                  padding: "24px",
                  textAlign: "center",
                  fontSize: "12px",
                  color: "#94a3b8",
                }}
              >
                <div style={{ fontWeight: 600, color: "#cbd5e1", marginBottom: "4px" }}>
                  No Bullish Confluence Found
                </div>
                <div>
                  No stocks in the evaluated universe currently meet both the positive price change threshold (≥ {minChangePct}%)
                  and the relative volume expansion threshold (≥ {minRvol}x RVOL).
                </div>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {data.bullish_confluence.map((item, idx) => (
                  <div
                    key={item.symbol}
                    onClick={() => onSelectStock(item.symbol, "chart")}
                    style={{
                      background: "#081513",
                      border: "1px solid #115e59",
                      borderRadius: "6px",
                      padding: "10px 12px",
                      cursor: "pointer",
                      transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "#0f2e29")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "#081513")}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span style={{ fontWeight: 700, fontSize: "13px", color: "#f8fafc" }}>
                          {item.symbol}
                        </span>
                        <span style={{ fontSize: "11px", color: "#64748b" }}>
                          {item.company_name}
                        </span>
                        {renderDataModeBadge(item.data_mode, item.is_stale)}
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <span style={{ fontWeight: 700, fontSize: "13px", color: "#26c78b" }}>
                          +{item.daily_change_pct.toFixed(2)}%
                        </span>
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11px" }}>
                      <div style={{ color: "#94a3b8" }}>
                        <span>
                          {item.ltp_available && item.ltp
                            ? `LTP: ₹${item.ltp.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`
                            : `Close: ₹${item.latest_completed_close.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`}
                        </span>
                        <span style={{ margin: "0 6px" }}>•</span>
                        <span>Vol: {item.volume_formatted}</span>
                        <span style={{ margin: "0 6px" }}>•</span>
                        <span>Turnover: {item.turnover_formatted}</span>
                        {renderTurnoverBadge(item.turnover_status)}
                      </div>
                      <div style={{ display: "flex", gap: "6px" }}>
                        <span
                          style={{
                            fontSize: "10px",
                            padding: "1px 5px",
                            borderRadius: "3px",
                            background: "rgba(38, 199, 139, 0.15)",
                            color: "#26c78b",
                            fontWeight: 600,
                          }}
                        >
                          #{item.rank_in_gainers || idx + 1} Gainer
                        </span>
                        <span
                          style={{
                            fontSize: "10px",
                            padding: "1px 5px",
                            borderRadius: "3px",
                            background: "rgba(56, 189, 248, 0.15)",
                            color: "#38bdf8",
                            fontWeight: 600,
                          }}
                        >
                          #{item.rank_in_volume_gainers} Vol Surge ({(item.active_rvol ?? item.daily_rvol).toFixed(2)}x {item.active_rvol_mode === "tod" ? "TOD" : "Daily"})
                        </span>
                      </div>
                    </div>

                    <div style={{ marginTop: "6px", fontSize: "10px", color: "#64748b", borderTop: "1px dashed #134e4a", paddingTop: "4px", display: "flex", justifyContent: "space-between" }}>
                      <span>{item.interpretation}</span>
                      <strong style={{ color: "#38bdf8" }}>Heuristic: {item.heuristic_compound_score ?? item.compound_score}</strong>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Panel B: Bearish Price-Volume Confluence */}
          <div
            style={{
              background: "#1c1012",
              border: "1px solid #4c1d24",
              borderRadius: "10px",
              padding: "16px",
              display: "flex",
              flexDirection: "column",
              gap: "12px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "16px" }}>🔴</span>
                <span style={{ fontWeight: 700, fontSize: "14px", color: "#fb7185" }}>
                  Bearish Confluence
                </span>
                <span style={{ fontSize: "11px", color: "#64748b" }}>(Losers ∩ Volume Gainers)</span>
              </div>
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  padding: "2px 8px",
                  borderRadius: "12px",
                  background: "rgba(251, 113, 133, 0.15)",
                  color: "#fb7185",
                }}
              >
                {data?.bearish_confluence?.length || 0} Matches
              </span>
            </div>

            {loading ? (
              <div style={{ textAlign: "center", padding: "30px", color: "#64748b", fontSize: "12px" }}>
                Evaluating bearish confluence intersections…
              </div>
            ) : !data?.bearish_confluence || data.bearish_confluence.length === 0 ? (
              <div
                style={{
                  background: "rgba(76, 29, 36, 0.2)",
                  border: "1px dashed #4c1d24",
                  borderRadius: "8px",
                  padding: "24px",
                  textAlign: "center",
                  fontSize: "12px",
                  color: "#94a3b8",
                }}
              >
                <div style={{ fontWeight: 600, color: "#cbd5e1", marginBottom: "4px" }}>
                  No Bearish Confluence Found
                </div>
                <div>
                  No stocks in the evaluated universe currently meet both the negative price decline threshold
                  and the relative volume expansion threshold (≥ {minRvol}x RVOL).
                </div>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {data.bearish_confluence.map((item, idx) => (
                  <div
                    key={item.symbol}
                    onClick={() => onSelectStock(item.symbol, "chart")}
                    style={{
                      background: "#160b0e",
                      border: "1px solid #5b1b26",
                      borderRadius: "6px",
                      padding: "10px 12px",
                      cursor: "pointer",
                      transition: "all 0.15s ease",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "#281217")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "#160b0e")}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span style={{ fontWeight: 700, fontSize: "13px", color: "#f8fafc" }}>
                          {item.symbol}
                        </span>
                        <span style={{ fontSize: "11px", color: "#64748b" }}>
                          {item.company_name}
                        </span>
                        {renderDataModeBadge(item.data_mode, item.is_stale)}
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <span style={{ fontWeight: 700, fontSize: "13px", color: "#ef6676" }}>
                          {item.daily_change_pct.toFixed(2)}%
                        </span>
                      </div>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11px" }}>
                      <div style={{ color: "#94a3b8" }}>
                        <span>
                          {item.ltp_available && item.ltp
                            ? `LTP: ₹${item.ltp.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`
                            : `Close: ₹${item.latest_completed_close.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`}
                        </span>
                        <span style={{ margin: "0 6px" }}>•</span>
                        <span>Vol: {item.volume_formatted}</span>
                        <span style={{ margin: "0 6px" }}>•</span>
                        <span>Turnover: {item.turnover_formatted}</span>
                        {renderTurnoverBadge(item.turnover_status)}
                      </div>
                      <div style={{ display: "flex", gap: "6px" }}>
                        <span
                          style={{
                            fontSize: "10px",
                            padding: "1px 5px",
                            borderRadius: "3px",
                            background: "rgba(239, 102, 118, 0.15)",
                            color: "#ef6676",
                            fontWeight: 600,
                          }}
                        >
                          #{item.rank_in_losers || idx + 1} Loser
                        </span>
                        <span
                          style={{
                            fontSize: "10px",
                            padding: "1px 5px",
                            borderRadius: "3px",
                            background: "rgba(56, 189, 248, 0.15)",
                            color: "#38bdf8",
                            fontWeight: 600,
                          }}
                        >
                          #{item.rank_in_volume_gainers} Vol Surge ({(item.active_rvol ?? item.daily_rvol).toFixed(2)}x {item.active_rvol_mode === "tod" ? "TOD" : "Daily"})
                        </span>
                      </div>
                    </div>

                    <div style={{ marginTop: "6px", fontSize: "10px", color: "#64748b", borderTop: "1px dashed #4c1d24", paddingTop: "4px", display: "flex", justifyContent: "space-between" }}>
                      <span>{item.interpretation}</span>
                      <strong style={{ color: "#f43f5e" }}>Heuristic: {item.heuristic_compound_score ?? item.compound_score}</strong>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Mandatory Confluence Disclaimer */}
        <div style={{ marginTop: "8px", fontSize: "10px", color: "#64748b", fontStyle: "italic" }}>
          * Confluence reflects the mathematical co-occurrence of price movement and volume expansion from OHLCV bars.
          Scores are descriptive heuristics (RVOL × |% Change|), NOT predictive probabilities, institutional clearing flow, or buy/sell execution guarantees.
        </div>
      </div>

      {/* 4. FOUR SPECIALIZED MARKET MOVERS PANELS */}
      <div>
        <div style={{ marginBottom: "14px" }}>
          <h3 style={{ fontSize: "16px", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
            📊 Market Movers (Ranked Panels)
          </h3>
          <p style={{ fontSize: "11px", color: "#94a3b8", margin: "4px 0 0 0" }}>
            Synchronized single-snapshot rankings evaluated across identical trading sessions.
          </p>
        </div>

        {/* Row 1: Top Gainers & Top Losers */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(460px, 1fr))", gap: "16px", marginBottom: "16px" }}>
          {/* Panel 1: Top Gainers */}
          <MoverTablePanel
            title="▲ Top Gainers"
            subtitle="Ranked by positive percentage price change"
            color="#26c78b"
            items={sortedGainers}
            loading={loading}
            sortState={gainersSort}
            onSort={(f) => setGainersSort({ field: f, asc: gainersSort.field === f ? !gainersSort.asc : false })}
            onSelectStock={onSelectStock}
            renderDataModeBadge={renderDataModeBadge}
            renderProvenanceBadge={renderProvenanceBadge}
            renderTurnoverBadge={renderTurnoverBadge}
            rvolMode={rvolMode}
            allowSynthetic={allowSynthetic}
          />

          {/* Panel 2: Top Losers */}
          <MoverTablePanel
            title="▼ Top Losers"
            subtitle="Ranked by negative percentage price change"
            color="#ef6676"
            items={sortedLosers}
            loading={loading}
            sortState={losersSort}
            onSort={(f) => setLosersSort({ field: f, asc: losersSort.field === f ? !losersSort.asc : true })}
            onSelectStock={onSelectStock}
            renderDataModeBadge={renderDataModeBadge}
            renderProvenanceBadge={renderProvenanceBadge}
            renderTurnoverBadge={renderTurnoverBadge}
            rvolMode={rvolMode}
            allowSynthetic={allowSynthetic}
          />
        </div>

        {/* Row 2: Volume Gainers & High-Volume Losers */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(460px, 1fr))", gap: "16px" }}>
          {/* Panel 3: Volume Gainers */}
          <MoverTablePanel
            title={rvolMode === "tod" ? "⚡ Volume Gainers (True TOD RVOL)" : "⚡ Volume Gainers (Daily RVOL)"}
            subtitle={
              rvolMode === "tod"
                ? `Ranked by True Time-of-Day RVOL vs same-time baseline (Threshold ≥ ${minRvol}x)`
                : `Ranked by Daily Relative Volume vs 20-day ADV (Threshold ≥ ${minRvol}x)`
            }
            color="#38bdf8"
            items={sortedVolumeGainers}
            loading={loading}
            sortState={volSort}
            onSort={(f) => setVolSort({ field: f, asc: volSort.field === f ? !volSort.asc : false })}
            onSelectStock={onSelectStock}
            renderDataModeBadge={renderDataModeBadge}
            renderProvenanceBadge={renderProvenanceBadge}
            renderTurnoverBadge={renderTurnoverBadge}
            rvolMode={rvolMode}
            allowSynthetic={allowSynthetic}
          />

          {/* Panel 4: High-Volume Losers */}
          <MoverTablePanel
            title="🩸 High-Volume Losers"
            subtitle={
              rvolMode === "tod"
                ? "Declining price combined with heavy Time-of-Day volume expansion"
                : "Declining price combined with heavy trading volume expansion"
            }
            color="#f43f5e"
            items={sortedHighVolumeLosers}
            loading={loading}
            sortState={hvLosersSort}
            onSort={(f) => setHvLosersSort({ field: f, asc: hvLosersSort.field === f ? !hvLosersSort.asc : false })}
            onSelectStock={onSelectStock}
            renderDataModeBadge={renderDataModeBadge}
            renderProvenanceBadge={renderProvenanceBadge}
            renderTurnoverBadge={renderTurnoverBadge}
            rvolMode={rvolMode}
            allowSynthetic={allowSynthetic}
          />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Reusable Mover Table Panel Component
// ---------------------------------------------------------------------------

interface MoverTablePanelProps {
  title: string;
  subtitle: string;
  color: string;
  items: StockMoverItem[];
  loading: boolean;
  sortState: { field: SortField; asc: boolean };
  onSort: (field: SortField) => void;
  onSelectStock: (symbol: string, page?: string) => void;
  renderDataModeBadge: (mode: string, isStale?: boolean) => React.ReactNode;
  renderProvenanceBadge?: (source?: string, status?: string) => React.ReactNode;
  renderTurnoverBadge: (status: string) => React.ReactNode;
  rvolMode?: "daily" | "tod";
  allowSynthetic?: boolean;
}

function MoverTablePanel({
  title,
  subtitle,
  color,
  items,
  loading,
  sortState,
  onSort,
  onSelectStock,
  renderDataModeBadge,
  renderProvenanceBadge,
  renderTurnoverBadge,
  rvolMode = "daily",
  allowSynthetic = false,
}: MoverTablePanelProps) {
  const renderSortIndicator = (field: SortField) => {
    if (sortState.field !== field) return <span style={{ color: "#475569" }}> ⇅</span>;
    return <span style={{ color }}>{sortState.asc ? " ▲" : " ▼"}</span>;
  };

  return (
    <div
      style={{
        background: "#0f172a",
        border: "1px solid #1e293b",
        borderRadius: "10px",
        padding: "16px",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h4 style={{ fontSize: "14px", fontWeight: 700, margin: 0, color }}>{title}</h4>
          <p style={{ fontSize: "11px", color: "#64748b", margin: "2px 0 0 0" }}>{subtitle}</p>
        </div>
        <span
          style={{
            fontSize: "11px",
            fontWeight: 700,
            padding: "2px 8px",
            borderRadius: "10px",
            background: "#1e293b",
            color: "#94a3b8",
          }}
        >
          {items.length} stocks
        </span>
      </div>

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "11px" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid #1e293b", color: "#64748b", textTransform: "uppercase" }}>
              <th style={{ padding: "8px 6px" }}>#</th>
              <th style={{ padding: "8px 6px", cursor: "pointer" }} onClick={() => onSort("symbol")}>
                Symbol {renderSortIndicator("symbol")}
              </th>
              <th style={{ padding: "8px 6px", textAlign: "right", cursor: "pointer" }} onClick={() => onSort("close")}>
                Price {renderSortIndicator("close")}
              </th>
              <th style={{ padding: "8px 6px", textAlign: "right", cursor: "pointer" }} onClick={() => onSort("daily_change_pct")}>
                Change % {renderSortIndicator("daily_change_pct")}
              </th>
              <th style={{ padding: "8px 6px", textAlign: "right", cursor: "pointer" }} onClick={() => onSort("today_volume")}>
                Volume {renderSortIndicator("today_volume")}
              </th>
              <th style={{ padding: "8px 6px", textAlign: "right", cursor: "pointer" }} onClick={() => onSort("daily_rvol")}>
                {rvolMode === "tod" ? "TOD RVOL" : "RVOL"} {renderSortIndicator("daily_rvol")}
              </th>
              <th style={{ padding: "8px 6px", textAlign: "right", cursor: "pointer" }} onClick={() => onSort("traded_value_cr")}>
                Turnover {renderSortIndicator("traded_value_cr")}
              </th>
              <th style={{ padding: "8px 6px", textAlign: "center" }}>Mode / Provenance</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} style={{ textAlign: "center", padding: "24px", color: "#64748b" }}>
                  Loading market data…
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={8} style={{ textAlign: "center", padding: "28px 16px", color: "#94a3b8" }}>
                  {rvolMode === "tod" && !allowSynthetic ? (
                    <div>
                      <div style={{ fontWeight: 600, color: "#f8fafc", marginBottom: "4px" }}>
                        No stocks qualify under True Time-of-Day RVOL
                      </div>
                      <div style={{ fontSize: "11px", color: "#64748b", maxWidth: "480px", margin: "0 auto" }}>
                        Observed intraday data is verified for pilot securities (RELIANCE, TCS, HDFCBANK) while 46,500 synthetic bars remain isolated. Adjust filters or toggle <strong>"Synthetic Demo Data ON"</strong> to preview simulated algorithmic calculations across all stocks.
                      </div>
                    </div>
                  ) : (
                    "No stocks match the filter criteria."
                  )}
                </td>
              </tr>
            ) : (
              items.map((st, i) => {
                const isPos = st.daily_change_pct >= 0;
                return (
                  <tr
                    key={st.symbol}
                    onClick={() => onSelectStock(st.symbol, "chart")}
                    style={{
                      borderBottom: "1px solid #16202e",
                      cursor: "pointer",
                      transition: "background 0.15s ease",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "#162233")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    <td style={{ padding: "8px 6px", color: "#64748b" }}>{st.rank || i + 1}</td>
                    <td style={{ padding: "8px 6px" }}>
                      <div style={{ fontWeight: 700, color: "#f8fafc" }}>{st.symbol}</div>
                      <div style={{ fontSize: "10px", color: "#64748b" }}>{st.company_name}</div>
                    </td>
                    <td style={{ padding: "8px 6px", textAlign: "right" }}>
                      <div style={{ fontWeight: 700, color: "#f8fafc" }}>
                        ₹{st.close.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </div>
                      <div style={{ fontSize: "9px", color: st.ltp_available ? "#26c78b" : "#64748b" }}>
                        {st.ltp_available ? "LTP" : "Close"}
                      </div>
                    </td>
                    <td style={{ padding: "8px 6px", textAlign: "right" }}>
                      <span
                        style={{
                          padding: "2px 6px",
                          borderRadius: "4px",
                          fontSize: "11px",
                          fontWeight: 700,
                          background: isPos ? "rgba(38, 199, 139, 0.15)" : "rgba(239, 102, 118, 0.15)",
                          color: isPos ? "#26c78b" : "#ef6676",
                        }}
                      >
                        {isPos ? "+" : ""}{st.daily_change_pct.toFixed(2)}%
                      </span>
                    </td>
                    <td style={{ padding: "8px 6px", textAlign: "right" }}>
                      <div style={{ color: "#cbd5e1" }}>{st.volume_formatted}</div>
                      <div style={{ fontSize: "9px", color: "#64748b" }}>ADV: {st.adv_20_formatted}</div>
                    </td>
                    <td style={{ padding: "8px 6px", textAlign: "right" }}>
                      {rvolMode === "tod" ? (
                        st.time_of_day_rvol != null ? (
                          <>
                            <div
                              style={{
                                fontWeight: 700,
                                color: st.tod_source === "SYNTHETIC" ? "#f59e0b" : "#c084fc",
                              }}
                            >
                              {st.time_of_day_rvol.toFixed(2)}x
                            </div>
                            <div
                              style={{
                                fontSize: "9px",
                                color: st.tod_source === "SYNTHETIC" ? "#fbbf24" : "#a855f7",
                              }}
                            >
                              {st.tod_source === "SYNTHETIC"
                                ? `SYNTHETIC (${st.tod_valid_sessions || 0}D)`
                                : `TOD ${st.tod_valid_sessions || 0}D`}
                            </div>
                          </>
                        ) : (
                          <>
                            <div style={{ fontWeight: 700, color: "#64748b" }}>--</div>
                            <div style={{ fontSize: "9px", color: "#64748b" }}>UNAVAILABLE</div>
                          </>
                        )
                      ) : (
                        <>
                          <div
                            style={{
                              fontWeight: 700,
                              color: st.daily_rvol >= 1.5 ? "#38bdf8" : "#cbd5e1",
                            }}
                          >
                            {st.daily_rvol.toFixed(2)}x
                          </div>
                          <div
                            style={{
                              fontSize: "9px",
                              color: st.daily_rvol_is_provisional ? "#06b6d4" : "#64748b",
                            }}
                          >
                            {st.daily_rvol_status}
                          </div>
                        </>
                      )}
                    </td>
                    <td style={{ padding: "8px 6px", textAlign: "right" }}>
                      <div style={{ color: "#cbd5e1" }}>
                        {st.turnover_formatted}
                        {renderTurnoverBadge(st.turnover_status)}
                      </div>
                      <div style={{ fontSize: "9px", color: "#64748b" }}>{st.turnover_note ? st.turnover_note.slice(0, 16) : ""}</div>
                    </td>
                    <td style={{ padding: "8px 6px", textAlign: "center" }}>
                      <div style={{ display: "flex", flexDirection: "column", gap: "2px", alignItems: "center" }}>
                        {renderDataModeBadge(st.data_mode, st.is_stale)}
                        {rvolMode === "tod" && renderProvenanceBadge && (
                          renderProvenanceBadge(st.tod_source, st.tod_rvol_status)
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

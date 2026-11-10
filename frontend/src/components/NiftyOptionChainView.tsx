import React, { useState, useEffect } from "react";
import { apiJson } from "../api/client";

interface OptionMetric {
  instrument_key: string;
  trading_symbol: string;
  lot_size: number;
  exchange_token?: string;
  ltp: number;
  change: number;
  change_pct: number;
  oi: number;
  oi_change: number;
  volume: number;
  iv: number;
  delta?: number;
  gamma?: number;
  theta?: number;
  vega?: number;
}

interface StrikeRow {
  strike_price: number;
  ce: OptionMetric | null;
  pe: OptionMetric | null;
  is_atm: boolean;
  spot_price: number;
}

interface ExpiryItem {
  expiry_ms: number;
  expiry_date: string;
  display: string;
  is_near: boolean;
}

interface OptionChainData {
  underlying: string;
  instrument_key: string;
  spot_price: number;
  atm_strike: number;
  max_pain_strike: number;
  pcr: number;
  total_call_oi: number;
  total_put_oi: number;
  selected_expiry: ExpiryItem;
  available_expiries: ExpiryItem[];
  days_to_expiry: number;
  chain: StrikeRow[];
}

interface NiftyOptionChainViewProps {
  onSelectContract?: (symbol: string) => void;
}

export default function NiftyOptionChainView({ onSelectContract }: NiftyOptionChainViewProps) {
  const [data, setData] = useState<OptionChainData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedExpiry, setSelectedExpiry] = useState<string>("");
  const [strikeRange, setStrikeRange] = useState<number>(15);
  const [showGreeks, setShowGreeks] = useState(false);

  const loadChain = async (exp?: string, range?: number) => {
    setLoading(true);
    setError(null);
    try {
      const url = `/api/options/nifty/chain?strike_range=${range || strikeRange}${
        exp ? `&expiry=${exp}` : ""
      }`;
      const res = await apiJson<OptionChainData>(url);
      setData(res);
      if (res.selected_expiry && !selectedExpiry) {
        setSelectedExpiry(res.selected_expiry.expiry_date);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to load NIFTY option chain");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadChain(selectedExpiry, strikeRange);
  }, [selectedExpiry, strikeRange]);

  const maxOI = data?.chain
    ? Math.max(
        ...data.chain.map((r) => Math.max(r.ce?.oi || 0, r.pe?.oi || 0)),
        1
      )
    : 1;

  return (
    <div style={{ padding: "20px", color: "#f8fafc", fontFamily: "sans-serif" }}>
      {/* Top Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
          marginBottom: "20px",
          paddingBottom: "16px",
          borderBottom: "1px solid #1e293b",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h2 style={{ margin: 0, fontSize: "20px", fontWeight: 700 }}>
              NIFTY 50 Option Chain
            </h2>
            <span
              style={{
                fontSize: "11px",
                padding: "2px 8px",
                borderRadius: "4px",
                background: "rgba(16, 185, 129, 0.15)",
                color: "#34d399",
                border: "1px solid rgba(16, 185, 129, 0.3)",
                fontWeight: 600,
              }}
            >
              DERIVATIVES · NSE
            </span>
          </div>
          <p style={{ margin: "4px 0 0 0", color: "#94a3b8", fontSize: "12px" }}>
            Official Upstox exchange-calibrated option chain with Black-Scholes Greeks, PCR & Max Pain
          </p>
        </div>

        {/* Controls */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ fontSize: "12px", color: "#94a3b8" }}>Expiry:</span>
            <select
              value={selectedExpiry}
              onChange={(e) => setSelectedExpiry(e.target.value)}
              style={{
                background: "#080c14",
                border: "1px solid #1e293b",
                color: "#f8fafc",
                padding: "6px 12px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                outline: "none",
                cursor: "pointer",
              }}
            >
              {(data?.available_expiries || []).map((exp) => (
                <option key={exp.expiry_date} value={exp.expiry_date}>
                  {exp.display} {exp.is_near ? "★" : ""}
                </option>
              ))}
            </select>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ fontSize: "12px", color: "#94a3b8" }}>Strikes:</span>
            <select
              value={strikeRange}
              onChange={(e) => setStrikeRange(Number(e.target.value))}
              style={{
                background: "#080c14",
                border: "1px solid #1e293b",
                color: "#f8fafc",
                padding: "6px 8px",
                borderRadius: "6px",
                fontSize: "12px",
                outline: "none",
                cursor: "pointer",
              }}
            >
              <option value={10}>± 10 Strikes</option>
              <option value={15}>± 15 Strikes</option>
              <option value={20}>± 20 Strikes</option>
              <option value={30}>± 30 Strikes</option>
            </select>
          </div>

          <button
            onClick={() => setShowGreeks(!showGreeks)}
            style={{
              background: showGreeks ? "rgba(56, 189, 248, 0.2)" : "#080c14",
              border: `1px solid ${showGreeks ? "#38bdf8" : "#1e293b"}`,
              color: showGreeks ? "#38bdf8" : "#94a3b8",
              padding: "6px 12px",
              borderRadius: "6px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {showGreeks ? "Hide Greeks" : "Show Greeks (Δ Γ Θ ν)"}
          </button>

          <button
            onClick={() => loadChain(selectedExpiry, strikeRange)}
            style={{
              background: "#131c2a",
              border: "1px solid #1e2c40",
              color: "#f8fafc",
              padding: "6px 12px",
              borderRadius: "6px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Summary KPI Cards */}
      {data && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
            gap: "12px",
            marginBottom: "20px",
          }}
        >
          <div
            style={{
              background: "#0a0f18",
              border: "1px solid #1e293b",
              borderRadius: "8px",
              padding: "12px",
            }}
          >
            <span style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase" }}>
              NIFTY SPOT
            </span>
            <div style={{ fontSize: "18px", fontWeight: 700, color: "#38bdf8", marginTop: "4px" }}>
              ₹{data.spot_price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </div>
            <span style={{ fontSize: "10px", color: "#94a3b8" }}>Underlying Index</span>
          </div>

          <div
            style={{
              background: "#0a0f18",
              border: "1px solid #1e293b",
              borderRadius: "8px",
              padding: "12px",
            }}
          >
            <span style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase" }}>
              ATM STRIKE
            </span>
            <div style={{ fontSize: "18px", fontWeight: 700, color: "#facc15", marginTop: "4px" }}>
              {data.atm_strike.toLocaleString("en-IN")}
            </div>
            <span style={{ fontSize: "10px", color: "#94a3b8" }}>At The Money</span>
          </div>

          <div
            style={{
              background: "#0a0f18",
              border: "1px solid #1e293b",
              borderRadius: "8px",
              padding: "12px",
            }}
          >
            <span style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase" }}>
              MAX PAIN
            </span>
            <div style={{ fontSize: "18px", fontWeight: 700, color: "#f43f5e", marginTop: "4px" }}>
              {data.max_pain_strike.toLocaleString("en-IN")}
            </div>
            <span style={{ fontSize: "10px", color: "#94a3b8" }}>Writer Hedging Pivot</span>
          </div>

          <div
            style={{
              background: "#0a0f18",
              border: "1px solid #1e293b",
              borderRadius: "8px",
              padding: "12px",
            }}
          >
            <span style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase" }}>
              PCR (OI)
            </span>
            <div
              style={{
                fontSize: "18px",
                fontWeight: 700,
                color: data.pcr > 1.2 ? "#34d399" : data.pcr < 0.8 ? "#f43f5e" : "#f8fafc",
                marginTop: "4px",
              }}
            >
              {data.pcr.toFixed(2)}
            </div>
            <span style={{ fontSize: "10px", color: "#94a3b8" }}>
              {data.pcr > 1.2 ? "Bullish Bias" : data.pcr < 0.8 ? "Bearish Bias" : "Neutral / Range"}
            </span>
          </div>

          <div
            style={{
              background: "#0a0f18",
              border: "1px solid #1e293b",
              borderRadius: "8px",
              padding: "12px",
            }}
          >
            <span style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase" }}>
              TOTAL CALL OI
            </span>
            <div style={{ fontSize: "16px", fontWeight: 700, color: "#f87171", marginTop: "4px" }}>
              {(data.total_call_oi / 100000).toFixed(2)}L
            </div>
            <span style={{ fontSize: "10px", color: "#94a3b8" }}>Contracts</span>
          </div>

          <div
            style={{
              background: "#0a0f18",
              border: "1px solid #1e293b",
              borderRadius: "8px",
              padding: "12px",
            }}
          >
            <span style={{ fontSize: "11px", color: "#64748b", textTransform: "uppercase" }}>
              TOTAL PUT OI
            </span>
            <div style={{ fontSize: "16px", fontWeight: 700, color: "#34d399", marginTop: "4px" }}>
              {(data.total_put_oi / 100000).toFixed(2)}L
            </div>
            <span style={{ fontSize: "10px", color: "#94a3b8" }}>Contracts</span>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div
          style={{
            padding: "16px",
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            borderRadius: "8px",
            color: "#f87171",
            fontSize: "13px",
            marginBottom: "16px",
          }}
        >
          {error}
        </div>
      )}

      {/* Loading state */}
      {loading && !data && (
        <div style={{ textAlign: "center", padding: "60px", color: "#64748b" }}>
          Loading NIFTY option chain...
        </div>
      )}

      {/* Option Chain Table */}
      {data && (
        <div
          style={{
            overflowX: "auto",
            background: "#06090e",
            border: "1px solid #1e293b",
            borderRadius: "8px",
          }}
        >
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
            <thead>
              <tr style={{ background: "#0c1322", borderBottom: "2px solid #1e293b" }}>
                <th
                  colSpan={showGreeks ? 8 : 4}
                  style={{
                    padding: "8px",
                    textAlign: "center",
                    color: "#f87171",
                    borderRight: "1px solid #1e293b",
                    fontWeight: 700,
                    letterSpacing: "1px",
                  }}
                >
                  CALLS (CE)
                </th>
                <th
                  style={{
                    padding: "8px",
                    textAlign: "center",
                    color: "#facc15",
                    borderRight: "1px solid #1e293b",
                    fontWeight: 700,
                    width: "90px",
                  }}
                >
                  STRIKE
                </th>
                <th
                  colSpan={showGreeks ? 8 : 4}
                  style={{
                    padding: "8px",
                    textAlign: "center",
                    color: "#34d399",
                    fontWeight: 700,
                    letterSpacing: "1px",
                  }}
                >
                  PUTS (PE)
                </th>
              </tr>
              <tr
                style={{
                  background: "#090d16",
                  borderBottom: "1px solid #1e293b",
                  color: "#64748b",
                  fontSize: "10px",
                  textTransform: "uppercase",
                }}
              >
                {/* Calls Headers */}
                {showGreeks && <th style={{ padding: "6px 8px" }}>Delta</th>}
                {showGreeks && <th style={{ padding: "6px 8px" }}>Theta</th>}
                {showGreeks && <th style={{ padding: "6px 8px" }}>IV %</th>}
                {showGreeks && <th style={{ padding: "6px 8px" }}>Volume</th>}
                <th style={{ padding: "6px 8px", textAlign: "right" }}>OI</th>
                <th style={{ padding: "6px 8px", textAlign: "right" }}>Chg OI</th>
                <th style={{ padding: "6px 8px", textAlign: "right" }}>LTP</th>
                <th style={{ padding: "6px 8px", textAlign: "right", borderRight: "1px solid #1e293b" }}>
                  Chg %
                </th>

                {/* Strike */}
                <th
                  style={{
                    padding: "6px 8px",
                    textAlign: "center",
                    borderRight: "1px solid #1e293b",
                    background: "#0f172a",
                    color: "#e2e8f0",
                  }}
                >
                  Strike
                </th>

                {/* Puts Headers */}
                <th style={{ padding: "6px 8px", textAlign: "left" }}>Chg %</th>
                <th style={{ padding: "6px 8px", textAlign: "left" }}>LTP</th>
                <th style={{ padding: "6px 8px", textAlign: "left" }}>Chg OI</th>
                <th style={{ padding: "6px 8px", textAlign: "left" }}>OI</th>
                {showGreeks && <th style={{ padding: "6px 8px" }}>Volume</th>}
                {showGreeks && <th style={{ padding: "6px 8px" }}>IV %</th>}
                {showGreeks && <th style={{ padding: "6px 8px" }}>Theta</th>}
                {showGreeks && <th style={{ padding: "6px 8px" }}>Delta</th>}
              </tr>
            </thead>
            <tbody>
              {data.chain.map((row) => {
                const isATM = row.is_atm;
                const isMaxPain = row.strike_price === data.max_pain_strike;
                const ceOIWidth = Math.min(100, Math.round(((row.ce?.oi || 0) / maxOI) * 100));
                const peOIWidth = Math.min(100, Math.round(((row.pe?.oi || 0) / maxOI) * 100));

                return (
                  <tr
                    key={row.strike_price}
                    style={{
                      borderBottom: "1px solid #121824",
                      background: isATM
                        ? "rgba(250, 204, 21, 0.08)"
                        : isMaxPain
                        ? "rgba(244, 63, 94, 0.05)"
                        : "transparent",
                    }}
                  >
                    {/* Calls data */}
                    {showGreeks && (
                      <td style={{ padding: "6px 8px", color: "#94a3b8" }}>
                        {row.ce?.delta?.toFixed(2) || "—"}
                      </td>
                    )}
                    {showGreeks && (
                      <td style={{ padding: "6px 8px", color: "#f87171" }}>
                        {row.ce?.theta?.toFixed(1) || "—"}
                      </td>
                    )}
                    {showGreeks && (
                      <td style={{ padding: "6px 8px", color: "#94a3b8" }}>
                        {row.ce?.iv?.toFixed(1)}%
                      </td>
                    )}
                    {showGreeks && (
                      <td style={{ padding: "6px 8px", color: "#64748b" }}>
                        {row.ce ? (row.ce.volume / 1000).toFixed(0) + "k" : "—"}
                      </td>
                    )}
                    <td style={{ padding: "6px 8px", textAlign: "right" }}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "flex-end",
                          gap: "6px",
                        }}
                      >
                        <div
                          style={{
                            width: "36px",
                            height: "4px",
                            background: "#1e293b",
                            borderRadius: "2px",
                            overflow: "hidden",
                          }}
                        >
                          <div
                            style={{
                              width: `${ceOIWidth}%`,
                              height: "100%",
                              background: "#f87171",
                            }}
                          />
                        </div>
                        <span>{row.ce ? (row.ce.oi / 1000).toFixed(0) + "k" : "—"}</span>
                      </div>
                    </td>
                    <td
                      style={{
                        padding: "6px 8px",
                        textAlign: "right",
                        color: (row.ce?.oi_change || 0) >= 0 ? "#34d399" : "#f87171",
                      }}
                    >
                      {row.ce?.oi_change ? `${row.ce.oi_change > 0 ? "+" : ""}${(row.ce.oi_change / 1000).toFixed(0)}k` : "—"}
                    </td>
                    <td
                      style={{
                        padding: "6px 8px",
                        textAlign: "right",
                        fontWeight: 600,
                        color: "#fff",
                        cursor: onSelectContract ? "pointer" : "default",
                      }}
                      onClick={() => row.ce && onSelectContract && onSelectContract(row.ce.trading_symbol)}
                    >
                      {row.ce ? `₹${row.ce.ltp.toFixed(2)}` : "—"}
                    </td>
                    <td
                      style={{
                        padding: "6px 8px",
                        textAlign: "right",
                        color: (row.ce?.change || 0) >= 0 ? "#34d399" : "#f87171",
                        borderRight: "1px solid #1e293b",
                      }}
                    >
                      {row.ce ? `${row.ce.change >= 0 ? "+" : ""}${row.ce.change.toFixed(2)}` : "—"}
                    </td>

                    {/* Strike Column */}
                    <td
                      style={{
                        padding: "6px 8px",
                        textAlign: "center",
                        fontWeight: isATM ? 800 : 700,
                        color: isATM ? "#facc15" : "#e2e8f0",
                        background: isATM ? "rgba(250, 204, 21, 0.15)" : "#0c1322",
                        borderRight: "1px solid #1e293b",
                      }}
                    >
                      {row.strike_price.toLocaleString("en-IN")}
                      {isATM && (
                        <span
                          style={{
                            marginLeft: "4px",
                            fontSize: "9px",
                            background: "#facc15",
                            color: "#000",
                            padding: "1px 3px",
                            borderRadius: "2px",
                            fontWeight: 800,
                          }}
                        >
                          ATM
                        </span>
                      )}
                    </td>

                    {/* Puts data */}
                    <td
                      style={{
                        padding: "6px 8px",
                        textAlign: "left",
                        color: (row.pe?.change || 0) >= 0 ? "#34d399" : "#f87171",
                      }}
                    >
                      {row.pe ? `${row.pe.change >= 0 ? "+" : ""}${row.pe.change.toFixed(2)}` : "—"}
                    </td>
                    <td
                      style={{
                        padding: "6px 8px",
                        textAlign: "left",
                        fontWeight: 600,
                        color: "#fff",
                        cursor: onSelectContract ? "pointer" : "default",
                      }}
                      onClick={() => row.pe && onSelectContract && onSelectContract(row.pe.trading_symbol)}
                    >
                      {row.pe ? `₹${row.pe.ltp.toFixed(2)}` : "—"}
                    </td>
                    <td
                      style={{
                        padding: "6px 8px",
                        textAlign: "left",
                        color: (row.pe?.oi_change || 0) >= 0 ? "#34d399" : "#f87171",
                      }}
                    >
                      {row.pe?.oi_change ? `${row.pe.oi_change > 0 ? "+" : ""}${(row.pe.oi_change / 1000).toFixed(0)}k` : "—"}
                    </td>
                    <td style={{ padding: "6px 8px", textAlign: "left" }}>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "flex-start",
                          gap: "6px",
                        }}
                      >
                        <span>{row.pe ? (row.pe.oi / 1000).toFixed(0) + "k" : "—"}</span>
                        <div
                          style={{
                            width: "36px",
                            height: "4px",
                            background: "#1e293b",
                            borderRadius: "2px",
                            overflow: "hidden",
                          }}
                        >
                          <div
                            style={{
                              width: `${peOIWidth}%`,
                              height: "100%",
                              background: "#34d399",
                            }}
                          />
                        </div>
                      </div>
                    </td>
                    {showGreeks && (
                      <td style={{ padding: "6px 8px", color: "#64748b" }}>
                        {row.pe ? (row.pe.volume / 1000).toFixed(0) + "k" : "—"}
                      </td>
                    )}
                    {showGreeks && (
                      <td style={{ padding: "6px 8px", color: "#94a3b8" }}>
                        {row.pe?.iv?.toFixed(1)}%
                      </td>
                    )}
                    {showGreeks && (
                      <td style={{ padding: "6px 8px", color: "#f87171" }}>
                        {row.pe?.theta?.toFixed(1) || "—"}
                      </td>
                    )}
                    {showGreeks && (
                      <td style={{ padding: "6px 8px", color: "#94a3b8" }}>
                        {row.pe?.delta?.toFixed(2) || "—"}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

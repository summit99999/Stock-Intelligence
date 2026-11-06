import { apiFetch } from "../api/client";
import React, { useState, useEffect } from "react";
import { LiveQuote } from "../api/marketFeed";

interface AlertRule {
  id: number;
  symbol: string;
  alert_type: string;
  target_value: number | null;
  timeframe: string;
  note: string;
  status: "ACTIVE" | "MUTED" | "TRIGGERED";
  created_at: string;
  last_triggered?: string | null;
  trigger_count: number;
}

interface TriggeredEvent {
  id: number;
  alert_id: number;
  symbol: string;
  alert_type: string;
  condition: string;
  triggered_value: string;
  message?: string;
  timestamp: string;
}

interface AlertsViewProps {
  onSelectSymbol: (symbol: string, page?: string) => void;
  onNavigate: (view: string) => void;
  liveQuotes?: Record<string, LiveQuote>;
}

export default function AlertsView({ onSelectSymbol, onNavigate, liveQuotes = {} }: AlertsViewProps) {
  const [alerts, setAlerts] = useState<AlertRule[]>([]);
  const [history, setHistory] = useState<TriggeredEvent[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [evaluating, setEvaluating] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Form State
  const [symbol, setSymbol] = useState("RELIANCE");
  const [alertType, setAlertType] = useState<string>("PRICE_ABOVE");
  const [targetValue, setTargetValue] = useState("2500.0");
  const [note, setNote] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("ALL");

  const loadAlerts = async () => {
    try {
      const res = await apiFetch("/api/alerts");
      if (!res.ok) throw new Error(`Alert rules API returned HTTP ${res.status}.`);
      const data = await res.json();
      setAlerts(data);
    } catch (err) {
      console.error(err);
      setLoadError(err instanceof Error ? err.message : "Alert rules are unavailable.");
    }
  };

  const loadHistory = async () => {
    try {
      const res = await apiFetch("/api/alerts/history?limit=50");
      if (!res.ok) throw new Error(`Alert history API returned HTTP ${res.status}.`);
      const data = await res.json();
      setHistory(data);
    } catch (err) {
      console.error(err);
      setLoadError(err instanceof Error ? err.message : "Alert history is unavailable.");
    }
  };

  const initData = async () => {
    setLoading(true);
    await Promise.all([loadAlerts(), loadHistory()]);
    setLoading(false);
  };

  useEffect(() => {
    initData();
  }, []);

  const handleCreateAlert = async (e: React.FormEvent) => {
    e.preventDefault();
    const val = targetValue ? parseFloat(targetValue) : null;
    const sym = symbol.trim().toUpperCase();
    if (!sym) return;

    try {
      const res = await apiFetch("/api/alerts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: sym,
          alert_type: alertType,
          target_value: val,
          timeframe: "1D",
          note: note.trim() || `${alertType} for ${sym}`,
        }),
      });
      if (res.ok) {
        setNote("");
        loadAlerts();
      }
    } catch (err) {
      alert("Failed to create alert.");
    }
  };

  const handleToggleStatus = async (rule: AlertRule) => {
    const nextStatus = rule.status === "ACTIVE" ? "MUTED" : "ACTIVE";
    try {
      const res = await apiFetch(`/api/alerts/${rule.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      if (res.ok) {
        loadAlerts();
      }
    } catch (err) {
      window.alert("Failed to update alert status.");
    }
  };

  const handleDelete = async (id: number) => {
    try {
      const res = await apiFetch(`/api/alerts/${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        loadAlerts();
      }
    } catch (err) {
      alert("Failed to delete alert.");
    }
  };

  const handleEvaluateRules = async () => {
    setEvaluating(true);
    try {
      const res = await apiFetch("/api/alerts/evaluate", {
        method: "POST",
      });
      if (res.ok) {
        const data = await res.json();
        alert(`Evaluation complete: ${data.triggered_count} rules triggered!`);
        await Promise.all([loadAlerts(), loadHistory()]);
      }
    } catch (err) {
      alert("Failed to evaluate alert rules.");
    } finally {
      setEvaluating(false);
    }
  };

  const handleClearHistory = async () => {
    const ok = confirm("Clear all alert trigger history?");
    if (!ok) return;
    try {
      const res = await apiFetch("/api/alerts/history", {
        method: "DELETE",
      });
      if (res.ok) {
        loadHistory();
      }
    } catch (err) {
      alert("Failed to clear history.");
    }
  };

  const filteredAlerts = alerts.filter((a) => {
    if (filterStatus === "ALL") return true;
    return a.status === filterStatus;
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {loadError && (
        <div className="notice" role="status">
          Alert data unavailable: {loadError} No alert data is being substituted.
        </div>
      )}
      {/* Top Banner & Control Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "linear-gradient(180deg, #131c2a 0%, #0e1622 100%)",
          padding: "20px 24px",
          borderRadius: "12px",
          border: "1px solid #1e2c40",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h2 style={{ margin: 0, fontSize: "22px", color: "#fff", fontWeight: 700 }}>
              Market Alerts & Rules Engine
            </h2>
            <span
              style={{
                background: "rgba(59, 130, 246, 0.15)",
                color: "#60a5fa",
                border: "1px solid rgba(59, 130, 246, 0.3)",
                padding: "3px 10px",
                borderRadius: "6px",
                fontSize: "11px",
                fontWeight: 600,
              }}
            >
              SQLITE & AUTOMATED
            </span>
          </div>
          <p style={{ margin: "6px 0 0", color: "#8c9bb0", fontSize: "13px" }}>
            Rule-based alerts for price breakouts, RSI levels, volume spikes, and SMC Order Block & FVG retests.
          </p>
        </div>

        <div style={{ display: "flex", gap: "10px" }}>
          <button
            onClick={handleEvaluateRules}
            disabled={evaluating}
            style={{
              background: "#2563eb",
              color: "#fff",
              border: "none",
              padding: "8px 18px",
              borderRadius: "8px",
              fontSize: "12px",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            {evaluating ? "Evaluating..." : "⚡ Evaluate Rules Now"}
          </button>
        </div>
      </div>

      {/* Main Grid: Create Form on Left, Active Rules on Right */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "20px" }}>
        {/* Create Alert Form Card */}
        <div
          style={{
            background: "#0e1622",
            border: "1px solid #1e2c40",
            borderRadius: "12px",
            padding: "20px",
          }}
        >
          <h3 style={{ margin: "0 0 16px", color: "#f8fafc", fontSize: "15px", fontWeight: 700 }}>
            Create New Market Alert Rule
          </h3>
          <form onSubmit={handleCreateAlert} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            <div>
              <label style={{ fontSize: "12px", color: "#94a3b8" }}>Stock Symbol *</label>
              <input
                type="text"
                required
                value={symbol}
                onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                style={{
                  width: "100%",
                  background: "#0a0f18",
                  border: "1px solid #1e2c40",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  color: "#fff",
                  fontSize: "13px",
                  marginTop: "4px",
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: "12px", color: "#94a3b8" }}>Alert Condition Type *</label>
              <select
                value={alertType}
                onChange={(e) => setAlertType(e.target.value)}
                style={{
                  width: "100%",
                  background: "#0a0f18",
                  border: "1px solid #1e2c40",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  color: "#fff",
                  fontSize: "13px",
                  marginTop: "4px",
                }}
              >
                <option value="PRICE_ABOVE">Price Above (Resistance Breakout)</option>
                <option value="PRICE_BELOW">Price Below (Support Breakdown)</option>
                <option value="RSI_ABOVE">RSI Above (Overbought / Momentum)</option>
                <option value="RSI_BELOW">RSI Below (Oversold Dip)</option>
                <option value="VOLUME_SPIKE">Volume Spike (RVOL Multiple)</option>
                <option value="BREAKOUT_52W">52-Week High Breakout Test</option>
                <option value="EMA_CROSSOVER">Price Crosses Above 20 EMA</option>
                <option value="OB_RETEST">SMC Order Block Retest (2% Proximity)</option>
                <option value="FVG_RETEST">SMC Fair Value Gap Retest</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: "12px", color: "#94a3b8" }}>Target Threshold Value</label>
              <input
                type="number"
                step="any"
                placeholder="Target value (optional for SMC/52W)"
                value={targetValue}
                onChange={(e) => setTargetValue(e.target.value)}
                style={{
                  width: "100%",
                  background: "#0a0f18",
                  border: "1px solid #1e2c40",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  color: "#fff",
                  fontSize: "13px",
                  marginTop: "4px",
                }}
              />
            </div>

            <div>
              <label style={{ fontSize: "12px", color: "#94a3b8" }}>Note / Rationale</label>
              <input
                type="text"
                placeholder="e.g. Major swing resistance breakout test"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                style={{
                  width: "100%",
                  background: "#0a0f18",
                  border: "1px solid #1e2c40",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  color: "#fff",
                  fontSize: "13px",
                  marginTop: "4px",
                }}
              />
            </div>

            <button
              type="submit"
              style={{
                background: "#2563eb",
                color: "#fff",
                border: "none",
                padding: "10px",
                borderRadius: "6px",
                fontWeight: 700,
                fontSize: "13px",
                cursor: "pointer",
                marginTop: "6px",
              }}
            >
              + Create Alert Rule
            </button>
          </form>
        </div>

        {/* Active Alert Rules List */}
        <div
          style={{
            background: "#0e1622",
            border: "1px solid #1e2c40",
            borderRadius: "12px",
            padding: "20px",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <h3 style={{ margin: 0, color: "#f8fafc", fontSize: "15px", fontWeight: 700 }}>
              Configured Alert Rules ({filteredAlerts.length})
            </h3>
            <div style={{ display: "flex", gap: "6px" }}>
              {["ALL", "ACTIVE", "MUTED"].map((st) => (
                <button
                  key={st}
                  onClick={() => setFilterStatus(st)}
                  style={{
                    background: filterStatus === st ? "#1e2c40" : "transparent",
                    color: filterStatus === st ? "#38bdf8" : "#94a3b8",
                    border: "none",
                    padding: "4px 8px",
                    borderRadius: "4px",
                    fontSize: "11px",
                    cursor: "pointer",
                  }}
                >
                  {st}
                </button>
              ))}
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px", overflowY: "auto", maxHeight: "380px" }}>
            {filteredAlerts.length === 0 ? (
              <div style={{ textAlign: "center", padding: "40px", color: "#64748b" }}>
                {loadError ? "Alert rules could not be loaded from the server." : "No alert rules match this status filter."}
              </div>
            ) : (
              filteredAlerts.map((alert) => (
                <div
                  key={alert.id}
                  style={{
                    background: "#0a0f18",
                    border: "1px solid #1e2c40",
                    borderRadius: "8px",
                    padding: "12px 16px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <span style={{ fontWeight: 700, color: "#fff", fontSize: "14px" }}>{alert.symbol}</span>
                      <span
                        style={{
                          fontSize: "10px",
                          fontWeight: 700,
                          padding: "2px 6px",
                          borderRadius: "4px",
                          background: alert.status === "ACTIVE" ? "rgba(38,199,139,0.15)" : "rgba(100,116,139,0.15)",
                          color: alert.status === "ACTIVE" ? "#26c78b" : "#94a3b8",
                        }}
                      >
                        {alert.status}
                      </span>
                      <span style={{ fontSize: "11px", color: "#38bdf8", fontWeight: 600 }}>{alert.alert_type}</span>
                    </div>

                    <div style={{ fontSize: "12px", color: "#cbd5e1", marginTop: "4px" }}>
                      {alert.target_value ? `Target: ₹${alert.target_value.toLocaleString()}` : "Rule-based trigger"}
                      {alert.note ? ` — ${alert.note}` : ""}
                    </div>

                    <div style={{ fontSize: "10px", color: "#64748b", marginTop: "4px" }}>
                      Triggers: {alert.trigger_count} {alert.last_triggered ? `| Last: ${alert.last_triggered}` : ""}
                    </div>
                  </div>

                  <div style={{ display: "flex", gap: "6px" }}>
                    <button
                      onClick={() => handleToggleStatus(alert)}
                      style={{
                        background: "#1e2c40",
                        color: alert.status === "ACTIVE" ? "#f59e0b" : "#26c78b",
                        border: "1px solid #334155",
                        padding: "5px 10px",
                        borderRadius: "4px",
                        fontSize: "11px",
                        cursor: "pointer",
                      }}
                    >
                      {alert.status === "ACTIVE" ? "Mute" : "Activate"}
                    </button>
                    <button
                      onClick={() => handleDelete(alert.id)}
                      style={{
                        background: "#371b20",
                        color: "#ef4444",
                        border: "1px solid #4a1d24",
                        padding: "5px 10px",
                        borderRadius: "4px",
                        fontSize: "11px",
                        cursor: "pointer",
                      }}
                    >
                      ✕
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* Alert Trigger History Table */}
      <div
        style={{
          background: "#0e1622",
          border: "1px solid #1e2c40",
          borderRadius: "12px",
          padding: "20px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h3 style={{ margin: "0 0 4px", color: "#f8fafc", fontSize: "15px", fontWeight: 700 }}>
              Recent Alert Trigger Events History
            </h3>
            <p style={{ margin: 0, fontSize: "12px", color: "#8c9bb0" }}>
              Permanent audit log of triggered alerts evaluated by the server engine.
            </p>
          </div>

          {history.length > 0 && (
            <button
              onClick={handleClearHistory}
              style={{
                background: "#1e2c40",
                color: "#94a3b8",
                border: "1px solid #334155",
                padding: "5px 12px",
                borderRadius: "6px",
                fontSize: "11px",
                cursor: "pointer",
              }}
            >
              Clear Log
            </button>
          )}
        </div>

        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "12px" }}>
            <thead>
              <tr style={{ background: "#0a0f18", borderBottom: "1px solid #1e2c40", color: "#8c9bb0", fontSize: "11px", textTransform: "uppercase" }}>
                <th style={{ padding: "10px 14px" }}>Timestamp</th>
                <th style={{ padding: "10px 14px" }}>Symbol</th>
                <th style={{ padding: "10px 14px" }}>Alert Type</th>
                <th style={{ padding: "10px 14px" }}>Condition</th>
                <th style={{ padding: "10px 14px" }}>Triggered Metric</th>
                <th style={{ padding: "10px 14px" }}>Message</th>
                <th style={{ padding: "10px 14px", textAlign: "center" }}>Action</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: "30px", color: "#64748b" }}>
                    {loadError
                      ? "Alert history could not be loaded from the server."
                      : 'No alert trigger history logged yet. Click "⚡ Evaluate Rules Now" to test active rules.'}
                  </td>
                </tr>
              ) : (
                history.map((ev) => (
                  <tr
                    key={ev.id}
                    style={{
                      borderBottom: "1px solid #16202e",
                    }}
                  >
                    <td style={{ padding: "10px 14px", color: "#64748b" }}>{ev.timestamp}</td>
                    <td style={{ padding: "10px 14px", fontWeight: 700, color: "#fff" }}>{ev.symbol}</td>
                    <td style={{ padding: "10px 14px", color: "#38bdf8" }}>{ev.alert_type}</td>
                    <td style={{ padding: "10px 14px", color: "#cbd5e1" }}>{ev.condition}</td>
                    <td style={{ padding: "10px 14px", fontWeight: 600, color: "#26c78b" }}>{ev.triggered_value}</td>
                    <td style={{ padding: "10px 14px", color: "#94a3b8" }}>{ev.message || "—"}</td>
                    <td style={{ padding: "10px 14px", textAlign: "center" }}>
                      <button
                        onClick={() => onSelectSymbol(ev.symbol, "chart")}
                        style={{
                          background: "#1e2c40",
                          color: "#38bdf8",
                          border: "1px solid #334155",
                          padding: "3px 8px",
                          borderRadius: "4px",
                          fontSize: "11px",
                          cursor: "pointer",
                        }}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

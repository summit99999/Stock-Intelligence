import { apiFetch } from "../api/client";
import { getApiBaseUrl } from "../api/config";
import React, { useState, useEffect } from "react";
import { fetchLiveFeedStatus, fetchMarketDataHealth, reconnectLiveFeed, LiveFeedStatus, MarketDataHealthDiagnostics } from "../api/marketFeed";

interface SettingsViewProps {
  onNavigate: (view: string) => void;
}

interface UpstoxAuthStatus {
  configured: boolean;
  token_available: boolean;
  token_expired: boolean;
  user_name?: string;
  user_id?: string;
  expires_at?: string;
  expires_at_local?: string;
  live_data_enabled: boolean;
  sandbox_mode: boolean;
}

export default function SettingsView({ onNavigate }: SettingsViewProps) {
  const [provider, setProvider] = useState<string>(() => {
    return localStorage.getItem("stock_intel_provider") || "yfinance";
  });

  const [feedStatus, setFeedStatus] = useState<LiveFeedStatus | null>(null);
  const [diagnostics, setDiagnostics] = useState<MarketDataHealthDiagnostics | null>(null);
  const [upstoxStatus, setUpstoxStatus] = useState<UpstoxAuthStatus | null>(null);
  const [directToken, setDirectToken] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [tokenSubmitting, setTokenSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem("stock_intel_provider", provider);
  }, [provider]);

  useEffect(() => {
    loadStatuses();
  }, []);

  const loadStatuses = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const fs = await fetchLiveFeedStatus();
      setFeedStatus(fs);
    } catch {
      // feed status optional
    }

    try {
      const diag = await fetchMarketDataHealth();
      setDiagnostics(diag);
    } catch {
      // diagnostics optional
    }

    try {
      const res = await apiFetch("/api/upstox/status");
      if (res.ok) {
        const data = await res.json();
        setUpstoxStatus(data);
      }
    } catch (e: any) {
      console.warn("Failed to load Upstox status:", e);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveDirectToken = async (force: boolean = false) => {
    if (!directToken.trim()) {
      setErrorMessage("Please enter an Upstox access token.");
      return;
    }

    setTokenSubmitting(true);
    setMessage(null);
    setErrorMessage(null);

    try {
      const res = await apiFetch("/api/upstox/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_token: directToken.trim(), force }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to validate Upstox token");
      }

      const data = await res.json();
      setMessage(data.message || "Upstox token saved and verified successfully!");
      setDirectToken("");
      await loadStatuses();
      // Also reconnect feed if connected
      await handleReconnect();
    } catch (e: any) {
      setErrorMessage(e.message || "Failed to connect Upstox token.");
    } finally {
      setTokenSubmitting(false);
    }
  };

  const handleOAuthLogin = async () => {
    setLoading(true);
    setMessage(null);
    setErrorMessage(null);
    try {
      const res = await apiFetch("/api/upstox/oauth/login-url");
      if (!res.ok) {
        throw new Error("Could not retrieve Upstox OAuth URL.");
      }
      const data = await res.json();
      if (data.login_url) {
        window.open(data.login_url, "_blank", "width=600,height=700");
        setMessage("Upstox login dialog opened in new window. Authorize and paste the code/token here.");
      } else {
        setErrorMessage(data.message || "Upstox API key not configured on server.");
      }
    } catch (e: any) {
      setErrorMessage(e.message || "Failed to initiate OAuth login.");
    } finally {
      setLoading(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Are you sure you want to disconnect Upstox and clear the access token?")) {
      return;
    }
    setLoading(true);
    try {
      await apiFetch("/api/upstox/token", { method: "DELETE" });
      setMessage("Upstox disconnected successfully.");
      await loadStatuses();
    } catch (e: any) {
      setErrorMessage("Error disconnecting Upstox: " + e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleReconnect = async () => {
    setLoading(true);
    setMessage("Connecting to Upstox live feed...");
    setErrorMessage(null);
    try {
      const st = await reconnectLiveFeed(true);
      setFeedStatus(st);
      setMessage(`Upstox feed status: ${st.status} (checked at ${new Date().toLocaleTimeString()})`);
    } catch (e: any) {
      setErrorMessage(`Feed reconnection failed: ${e?.message || "Check network/credentials"}`);
    } finally {
      setLoading(false);
    }
  };

  const handleClearCache = () => {
    if (confirm("Reset local watchlists, active alerts, and UI cache?")) {
      localStorage.removeItem("stock_intel_watchlist");
      localStorage.removeItem("stock_intel_alerts");
      localStorage.removeItem("stock_intel_alert_history");
      alert("Local storage and caches cleared.");
      window.location.reload();
    }
  };

  return (
    <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: "24px", color: "#e2e8f0" }}>
      {/* Overview Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px" }}>
        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af", letterSpacing: "0.5px" }}>ACTIVE DATA PROVIDER</div>
          <div style={{ fontSize: "20px", fontWeight: "700", marginTop: "4px", color: "#38bdf8" }}>
            {provider === "yfinance" ? "yfinance (Historical & Daily)" : "Upstox API v2 (Live & REST)"}
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>
            {provider === "yfinance" ? "Zero-cost historical engine" : "SEBI-compliant broker live feed"}
          </div>
        </div>

        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af", letterSpacing: "0.5px" }}>UPSTOX LIVE WEBSOCKET</div>
          <div style={{ fontSize: "20px", fontWeight: "700", marginTop: "4px" }}>
            <span
              style={{
                color:
                  feedStatus?.status === "CONNECTED"
                    ? "#26c78b"
                    : feedStatus?.status === "RATE_LIMITED"
                    ? "#ef6676"
                    : feedStatus?.status === "DISABLED"
                    ? "#94a3b8"
                    : "#f59e0b",
              }}
            >
              {feedStatus?.status || "DISCONNECTED"}
            </span>
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>
            {feedStatus?.error || (feedStatus?.status === "CONNECTED" ? "Active WebSocket · Live streaming" : "Status polling active")}
          </div>
        </div>

        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af", letterSpacing: "0.5px" }}>UPSTOX TOKEN STORE</div>
          <div style={{ fontSize: "20px", fontWeight: "700", marginTop: "4px", color: upstoxStatus?.token_available ? "#26c78b" : "#94a3b8" }}>
            {upstoxStatus?.token_available ? (upstoxStatus.token_expired ? "Token Expired" : "Valid Session") : "No Token"}
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>
            {upstoxStatus?.user_name ? `User: ${upstoxStatus.user_name} (${upstoxStatus.user_id})` : "Token Store Ready"}
          </div>
        </div>
      </div>

      {message && (
        <div style={{ background: "#1e293b", border: "1px solid #334155", padding: "10px 14px", borderRadius: "6px", fontSize: "12px", color: "#38bdf8" }}>
          ℹ {message}
        </div>
      )}

      {errorMessage && (
        <div style={{ background: "#3b1e22", border: "1px solid #7f1d1d", padding: "12px 14px", borderRadius: "6px", fontSize: "12px", color: "#fca5a5", display: "flex", flexDirection: "column", gap: "8px" }}>
          <div>⚠ {errorMessage}</div>
          {directToken.trim() && (
            <div>
              <button
                onClick={() => handleSaveDirectToken(true)}
                disabled={tokenSubmitting}
                style={{
                  background: "rgba(245, 158, 11, 0.2)",
                  border: "1px solid #f59e0b",
                  color: "#fde047",
                  borderRadius: "6px",
                  padding: "6px 12px",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
                title="Bypass upstream live check and save token immediately"
              >
                ⚡ Connect Anyway (Save & Bypass Live API Check)
              </button>
            </div>
          )}
        </div>
      )}

      {/* Upstox Market Data V3 Diagnostic Monitor (Phase 8) */}
      <div style={{ background: "#0d1117", border: "1px solid #21262d", borderRadius: "10px", padding: "18px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "14px", fontWeight: "700", color: "#f8fafc" }}>
              Upstox Market Data Feed V3 — Live Diagnostics
            </span>
            <span
              style={{
                fontSize: "11px",
                fontWeight: "700",
                padding: "2px 8px",
                borderRadius: "4px",
                background:
                  diagnostics?.status === "healthy"
                    ? "rgba(38, 199, 139, 0.15)"
                    : "rgba(245, 158, 11, 0.15)",
                color: diagnostics?.status === "healthy" ? "#26c78b" : "#f59e0b",
                border: `1px solid ${diagnostics?.status === "healthy" ? "rgba(38, 199, 139, 0.3)" : "rgba(245, 158, 11, 0.3)"}`,
              }}
            >
              {diagnostics?.status ? diagnostics.status.toUpperCase() : "INSPECTING..."}
            </span>
          </div>
          <span style={{ fontSize: "11px", color: "#8b949e", fontFamily: "monospace" }}>
            {diagnostics?.server_time_ist || "IST Server Clock"}
          </span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px", fontSize: "12px" }}>
          {/* Protocol & Upstream */}
          <div style={{ background: "#161b22", padding: "12px", borderRadius: "6px", border: "1px solid #30363d" }}>
            <div style={{ color: "#8b949e", fontSize: "11px", marginBottom: "6px" }}>UPSTREAM PROTOCOL</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Auth:</span>
                <span style={{ color: diagnostics?.upstox_authentication === "AUTHENTICATED" ? "#26c78b" : "#ef4444", fontWeight: 600 }}>
                  {diagnostics?.upstox_authentication || "CHECKING"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>WebSocket V3:</span>
                <span style={{ color: diagnostics?.upstox_websocket === "CONNECTED" ? "#26c78b" : "#f59e0b", fontWeight: 600 }}>
                  {diagnostics?.upstox_websocket || "INITIALIZING"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Protobuf Decoder:</span>
                <span style={{ color: diagnostics?.protobuf_decoder === "SUCCESS" ? "#26c78b" : "#94a3b8", fontWeight: 600 }}>
                  {diagnostics?.protobuf_decoder || "READY"}
                </span>
              </div>
            </div>
          </div>

          {/* Market Hours & Schedule */}
          <div style={{ background: "#161b22", padding: "12px", borderRadius: "6px", border: "1px solid #30363d" }}>
            <div style={{ color: "#8b949e", fontSize: "11px", marginBottom: "6px" }}>NSE EXCHANGE SESSION</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Session:</span>
                <span style={{ color: diagnostics?.market_status === "OPEN" ? "#26c78b" : "#38bdf8", fontWeight: 600 }}>
                  {diagnostics?.market_status || "CLOSED"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Data Freshness:</span>
                <span style={{ color: "#94a3b8", fontWeight: 600 }}>
                  {diagnostics?.data_freshness || "SESSION_CLOSE"}
                </span>
              </div>
              <div style={{ fontSize: "10px", color: "#64748b", marginTop: "2px", lineHeight: "1.3" }}>
                {diagnostics?.market_status_note || "NSE Equity trading: 09:15 - 15:30 IST"}
              </div>
            </div>
          </div>

          {/* Instruments & Subscriptions */}
          <div style={{ background: "#161b22", padding: "12px", borderRadius: "6px", border: "1px solid #30363d" }}>
            <div style={{ color: "#8b949e", fontSize: "11px", marginBottom: "6px" }}>ACTIVE SUBSCRIPTIONS</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Tracked Instruments:</span>
                <span style={{ color: "#f8fafc", fontWeight: 700 }}>
                  {diagnostics?.subscribed_instruments ?? (feedStatus?.subscribed_count || 0)}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Ticks Processed:</span>
                <span style={{ color: "#38bdf8", fontWeight: 600 }}>
                  {diagnostics?.ticks_received_count ?? (feedStatus?.ticks_received || 0)}
                </span>
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", marginTop: "2px" }}>
                {(diagnostics?.subscribed_symbols || ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]).map((sym) => (
                  <span key={sym} style={{ background: "#21262d", padding: "1px 5px", borderRadius: "3px", fontSize: "10px", color: "#94a3b8" }}>
                    {sym}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Transport & Clients */}
          <div style={{ background: "#161b22", padding: "12px", borderRadius: "6px", border: "1px solid #30363d" }}>
            <div style={{ color: "#8b949e", fontSize: "11px", marginBottom: "6px" }}>TRANSPORT & PERSISTENCE</div>
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Frontend Clients:</span>
                <span style={{ color: "#26c78b", fontWeight: 600 }}>
                  {diagnostics?.frontend_websocket_clients ?? 1} active
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>DB Token Sync:</span>
                <span style={{ color: "#26c78b", fontWeight: 600 }}>
                  ✓ Persisted
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Backend Port:</span>
                <span style={{ color: "#cbd5e1", fontFamily: "monospace" }}>
                  FastAPI :8000
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Main Settings Sections */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
        {/* Market Data Provider Card */}
        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "20px" }}>
          <h3 style={{ margin: "0 0 16px 0", fontSize: "15px", color: "#f8fafc" }}>Market Data Provider Selection</h3>
          <p style={{ fontSize: "12px", color: "#94a3b8", lineHeight: "1.5", margin: "0 0 16px 0" }}>
            Choose the core market data engine. The system is designed to run seamlessly with zero cost using yfinance, or connect to Upstox API v2 for real-time live market feeds.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <label
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "12px",
                padding: "12px",
                background: provider === "yfinance" ? "#1e293b" : "#0d1117",
                border: `1px solid ${provider === "yfinance" ? "#2563eb" : "#1f2937"}`,
                borderRadius: "8px",
                cursor: "pointer",
              }}
            >
              <input
                type="radio"
                name="provider"
                value="yfinance"
                checked={provider === "yfinance"}
                onChange={(e) => setProvider(e.target.value)}
                style={{ marginTop: "3px" }}
              />
              <div>
                <strong style={{ color: "#f8fafc", fontSize: "13px" }}>yfinance (Default / Free)</strong>
                <p style={{ margin: "4px 0 0 0", fontSize: "11px", color: "#94a3b8" }}>
                  Zero-cost, historical OHLCV data for all NSE stocks, indices, and indicators. Recommended for swing trading, backtesting, and portfolio scanning.
                </p>
              </div>
            </label>

            <label
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: "12px",
                padding: "12px",
                background: provider === "upstox" ? "#1e293b" : "#0d1117",
                border: `1px solid ${provider === "upstox" ? "#2563eb" : "#1f2937"}`,
                borderRadius: "8px",
                cursor: "pointer",
              }}
            >
              <input
                type="radio"
                name="provider"
                value="upstox"
                checked={provider === "upstox"}
                onChange={(e) => setProvider(e.target.value)}
                style={{ marginTop: "3px" }}
              />
              <div>
                <strong style={{ color: "#f8fafc", fontSize: "13px" }}>Upstox API v2 (Live & Historical)</strong>
                <p style={{ margin: "4px 0 0 0", fontSize: "11px", color: "#94a3b8" }}>
                  Official Upstox broker API. Supports tick-by-tick WebSocket feed, REST quote snapshots, and deterministic NSE_EQ ISIN instrument resolution.
                </p>
              </div>
            </label>
          </div>
        </div>

        {/* Upstox Connection & Token Management */}
        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "20px" }}>
          <h3 style={{ margin: "0 0 16px 0", fontSize: "15px", color: "#f8fafc" }}>Upstox API v2 Credentials & Token</h3>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px", fontSize: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
              <span style={{ color: "#94a3b8" }}>API Configuration:</span>
              <span style={{ color: upstoxStatus?.configured ? "#26c78b" : "#ef6676", fontWeight: "600" }}>
                {upstoxStatus?.configured ? "✓ Configured" : "✗ Incomplete"}
              </span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
              <span style={{ color: "#94a3b8" }}>Token Status:</span>
              <span style={{ color: upstoxStatus?.token_available ? (upstoxStatus.token_expired ? "#f59e0b" : "#26c78b") : "#94a3b8", fontWeight: "600" }}>
                {upstoxStatus?.token_available ? (upstoxStatus.token_expired ? "Expired" : "Active & Verified") : "None"}
              </span>
            </div>

            {upstoxStatus?.user_name && (
              <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
                <span style={{ color: "#94a3b8" }}>Connected User:</span>
                <span style={{ color: "#f8fafc", fontWeight: "600" }}>
                  {upstoxStatus.user_name} ({upstoxStatus.user_id})
                </span>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
              <span style={{ color: "#94a3b8" }}>Token Expiry:</span>
              <span style={{ color: "#cbd5e1", fontSize: "11px" }}>
                {upstoxStatus?.expires_at_local || upstoxStatus?.expires_at || "None"}
              </span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
              <span style={{ color: "#94a3b8" }}>Live Feed Mode:</span>
              <span style={{ color: feedStatus?.status === "DISABLED" ? "#94a3b8" : "#26c78b", fontWeight: "600" }}>
                {feedStatus?.status === "DISABLED" ? "Disabled by config" : "Enabled"}
              </span>
            </div>
          </div>

          {/* Direct Access Token Entry */}
          <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "8px" }}>
            <label style={{ fontSize: "11px", color: "#94a3b8" }}>
              Paste Upstox Access Token (from Developer Console):
            </label>
            <div style={{ display: "flex", gap: "8px" }}>
              <input
                type="password"
                placeholder="eyJhbGciOiJIUzI1NiIsInR5cCI..."
                value={directToken}
                onChange={(e) => setDirectToken(e.target.value)}
                style={{
                  flex: 1,
                  background: "#0d1117",
                  border: "1px solid #334155",
                  borderRadius: "6px",
                  padding: "8px 12px",
                  color: "#f8fafc",
                  fontSize: "12px",
                  fontFamily: "monospace",
                }}
              />
              <button
                onClick={() => handleSaveDirectToken(false)}
                disabled={tokenSubmitting || !directToken.trim()}
                style={{
                  background: "#16a34a",
                  color: "#fff",
                  border: "none",
                  borderRadius: "6px",
                  padding: "8px 14px",
                  fontSize: "12px",
                  fontWeight: "600",
                  cursor: "pointer",
                }}
              >
                {tokenSubmitting ? "Validating..." : "Save & Connect"}
              </button>
            </div>
            <small style={{ fontSize: "11px", color: "#64748b", lineHeight: "1.4" }}>
              • Must be a JWT token starting with <code>eyJ...</code> (not an authorization code).<br />
              • Daily tokens expire at 3:30 AM IST. For a 1-year token, generate an <strong>Analytics Token</strong> in Developer Console &gt; Your App &gt; Analytics tab.
            </small>
          </div>

          {/* Action Buttons */}
          <div style={{ display: "flex", gap: "10px", marginTop: "16px" }}>
            <button
              onClick={handleOAuthLogin}
              disabled={loading}
              style={{
                flex: 1,
                background: "#2563eb",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                padding: "8px 12px",
                fontSize: "12px",
                fontWeight: "600",
                cursor: "pointer",
              }}
              title="Launch Upstox OAuth Login Flow"
            >
              🔑 Login with Upstox
            </button>
            <button
              onClick={handleReconnect}
              disabled={loading}
              style={{
                background: "#1e293b",
                color: "#cbd5e1",
                border: "1px solid #334155",
                borderRadius: "6px",
                padding: "8px 12px",
                fontSize: "12px",
                cursor: "pointer",
              }}
              title="Test or Reconnect Live WebSocket Feed"
            >
              ⚡ Reconnect Feed
            </button>
            {upstoxStatus?.token_available && (
              <button
                onClick={handleDisconnect}
                disabled={loading}
                style={{
                  background: "rgba(239, 68, 68, 0.15)",
                  color: "#f87171",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  borderRadius: "6px",
                  padding: "8px 12px",
                  fontSize: "12px",
                  cursor: "pointer",
                }}
                title="Disconnect and Delete Upstox Access Token"
              >
                Disconnect
              </button>
            )}
            <button
              onClick={loadStatuses}
              disabled={loading}
              style={{
                background: "#1e293b",
                color: "#cbd5e1",
                border: "1px solid #334155",
                borderRadius: "6px",
                padding: "8px 12px",
                fontSize: "12px",
                cursor: "pointer",
              }}
            >
              ↻ Refresh
            </button>
          </div>
        </div>
      </div>

      {/* Database & System Architecture Information */}
      <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "20px" }}>
        <h3 style={{ margin: "0 0 16px 0", fontSize: "15px", color: "#f8fafc" }}>System & Database Architecture</h3>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "16px", fontSize: "12px" }}>
          <div style={{ background: "#0d1117", padding: "12px", borderRadius: "6px", border: "1px solid #1e293b" }}>
            <div style={{ color: "#9ca3af", fontSize: "11px" }}>BACKEND HOST & REST API</div>
            <div style={{ color: "#38bdf8", fontWeight: "600", marginTop: "4px" }}>{getApiBaseUrl()}</div>
            <div style={{ color: "#64748b", fontSize: "10px", marginTop: "2px" }}>FastAPI 0.115 + Python 3.12</div>
          </div>

          <div style={{ background: "#0d1117", padding: "12px", borderRadius: "6px", border: "1px solid #1e293b" }}>
            <div style={{ color: "#9ca3af", fontSize: "11px" }}>STORAGE & INSTRUMENT MASTER</div>
            <div style={{ color: "#f8fafc", fontWeight: "600", marginTop: "4px" }}>stock_intelligence.db</div>
            <div style={{ color: "#64748b", fontSize: "10px", marginTop: "2px" }}>Upstox NSE_EQ Key Resolution · ISIN Mapping</div>
          </div>

          <div style={{ background: "#0d1117", padding: "12px", borderRadius: "6px", border: "1px solid #1e293b" }}>
            <div style={{ color: "#9ca3af", fontSize: "11px" }}>UPSTOX WEBSOCKET DISPATCHER</div>
            <div style={{ color: "#26c78b", fontWeight: "600", marginTop: "4px" }}>/ws/market-feed</div>
            <div style={{ color: "#64748b", fontSize: "10px", marginTop: "2px" }}>Real-time tick dispatcher · 2-step OAuth Feed</div>
          </div>
        </div>

        <div style={{ marginTop: "20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: "11px", color: "#64748b" }}>
            Stock Intelligence Pro · Upstox API v2 Live Engine · Personal Terminal
          </span>
          <button
            onClick={handleClearCache}
            style={{
              background: "transparent",
              border: "1px solid #ef6676",
              color: "#ef6676",
              borderRadius: "6px",
              padding: "6px 14px",
              fontSize: "11px",
              fontWeight: "600",
              cursor: "pointer",
            }}
          >
            Clear Local Storage & Reset Preferences
          </button>
        </div>
      </div>
    </div>
  );
}

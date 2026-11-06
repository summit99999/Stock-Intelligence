import { apiFetch } from "../api/client";
import { getApiBaseUrl } from "../api/config";
import React, { useState, useEffect } from "react";
import { fetchLiveFeedStatus, reconnectLiveFeed, LiveFeedStatus } from "../api/marketFeed";

interface SettingsViewProps {
  onNavigate: (view: string) => void;
}

interface DhanAuthStatus {
  configured: boolean;
  token_available: boolean;
  token_expired: boolean;
  dhan_client_name?: string;
  expires_at?: string;
  keyring_available?: boolean;
}

export default function SettingsView({ onNavigate }: SettingsViewProps) {
  const [provider, setProvider] = useState<string>(() => {
    return localStorage.getItem("stock_intel_provider") || "yfinance";
  });

  const [feedStatus, setFeedStatus] = useState<LiveFeedStatus | null>(null);
  const [dhanStatus, setDhanStatus] = useState<DhanAuthStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    localStorage.setItem("stock_intel_provider", provider);
  }, [provider]);

  useEffect(() => {
    loadStatuses();
  }, []);

  const loadStatuses = async () => {
    setLoading(true);
    try {
      const fs = await fetchLiveFeedStatus();
      setFeedStatus(fs);
    } catch {
      // ignore
    }

    try {
      const res = await apiFetch("/api/dhan/status");
      if (res.ok) {
        const data = await res.json();
        setDhanStatus(data);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  };

  const handleReconnect = async () => {
    setLoading(true);
    setMessage("Connecting to live feed...");
    try {
      const st = await reconnectLiveFeed(true);
      setFeedStatus(st);
      setMessage(`Feed status: ${st.status} (checked at ${new Date().toLocaleTimeString()})`);
    } catch (e: any) {
      setMessage(`Connection failed: ${e?.message || "Check network/credentials"}`);
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
          <div style={{ fontSize: "11px", color: "#9ca3af" }}>ACTIVE DATA PROVIDER</div>
          <div style={{ fontSize: "20px", fontWeight: "700", marginTop: "4px", color: "#38bdf8" }}>
            {provider === "yfinance" ? "yfinance (Historical & Daily)" : "DhanHQ (Live & REST)"}
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>
            {provider === "yfinance" ? "Free, robust, zero API billing" : "Direct Indian broker feed"}
          </div>
        </div>

        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "16px" }}>
          <div style={{ fontSize: "11px", color: "#9ca3af" }}>DHAN LIVE WEBSOCKET</div>
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
          <div style={{ fontSize: "11px", color: "#9ca3af" }}>DHAN TOKEN STORE</div>
          <div style={{ fontSize: "20px", fontWeight: "700", marginTop: "4px", color: dhanStatus?.token_available ? "#26c78b" : "#94a3b8" }}>
            {dhanStatus?.token_available ? (dhanStatus.token_expired ? "Token Expired" : "Valid Session") : "No Token"}
          </div>
          <div style={{ fontSize: "11px", color: "#6b7280", marginTop: "4px" }}>
            {dhanStatus?.dhan_client_name ? `Client: ${dhanStatus.dhan_client_name}` : "Windows Vault Keyring"}
          </div>
        </div>
      </div>

      {message && (
        <div style={{ background: "#1e293b", border: "1px solid #334155", padding: "10px 14px", borderRadius: "6px", fontSize: "12px", color: "#38bdf8" }}>
          ℹ {message}
        </div>
      )}

      {/* Main Settings Sections */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
        {/* Market Data Provider Card */}
        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "20px" }}>
          <h3 style={{ margin: "0 0 16px 0", fontSize: "15px", color: "#f8fafc" }}>Market Data Provider Selection</h3>
          <p style={{ fontSize: "12px", color: "#94a3b8", lineHeight: "1.5", margin: "0 0 16px 0" }}>
            Choose the core market data engine. The system is designed to run seamlessly with zero cost using yfinance, or connect to DhanHQ for real-time live market feeds.
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
                background: provider === "dhan" ? "#1e293b" : "#0d1117",
                border: `1px solid ${provider === "dhan" ? "#2563eb" : "#1f2937"}`,
                borderRadius: "8px",
                cursor: "pointer",
              }}
            >
              <input
                type="radio"
                name="provider"
                value="dhan"
                checked={provider === "dhan"}
                onChange={(e) => setProvider(e.target.value)}
                style={{ marginTop: "3px" }}
              />
              <div>
                <strong style={{ color: "#f8fafc", fontSize: "13px" }}>DhanHQ Live & Historical API</strong>
                <p style={{ margin: "4px 0 0 0", fontSize: "11px", color: "#94a3b8" }}>
                  Requires active Dhan trading account & Data API credentials. Supports 200 Hz WebSocket live tick feed and official scrip master resolution.
                </p>
              </div>
            </label>
          </div>
        </div>

        {/* Dhan Connection & Diagnostics */}
        <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "20px" }}>
          <h3 style={{ margin: "0 0 16px 0", fontSize: "15px", color: "#f8fafc" }}>Dhan API & Security Diagnostics</h3>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px", fontSize: "12px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
              <span style={{ color: "#94a3b8" }}>Credentials in .env:</span>
              <span style={{ color: dhanStatus?.configured ? "#26c78b" : "#ef6676", fontWeight: "600" }}>
                {dhanStatus?.configured ? "✓ Configured" : "✗ Missing"}
              </span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
              <span style={{ color: "#94a3b8" }}>Windows Vault Keyring:</span>
              <span style={{ color: dhanStatus?.keyring_available ? "#26c78b" : "#f59e0b", fontWeight: "600" }}>
                {dhanStatus?.keyring_available ? "✓ Available" : "File Fallback"}
              </span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
              <span style={{ color: "#94a3b8" }}>Token Expiry Timestamp:</span>
              <span style={{ color: "#cbd5e1", fontSize: "11px" }}>
                {dhanStatus?.expires_at ? dhanStatus.expires_at : "None"}
              </span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid #1e293b" }}>
              <span style={{ color: "#94a3b8" }}>Feed Mode:</span>
              <span style={{ color: feedStatus?.status === "DISABLED" ? "#94a3b8" : "#26c78b", fontWeight: "600" }}>
                {feedStatus?.status === "DISABLED" ? "Disabled by config" : "Enabled"}
              </span>
            </div>
          </div>

          <div style={{ display: "flex", gap: "10px", marginTop: "20px" }}>
            <button
              onClick={handleReconnect}
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
            >
              {loading ? "Testing..." : "⚡ Test / Reconnect Feed"}
            </button>
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
            <div style={{ color: "#9ca3af", fontSize: "11px" }}>SQLITE LOCAL STORAGE</div>
            <div style={{ color: "#f8fafc", fontWeight: "600", marginTop: "4px" }}>stock_intelligence.db</div>
            <div style={{ color: "#64748b", fontSize: "10px", marginTop: "2px" }}>Tables: stocks, ohlcv, fundamentals</div>
          </div>

          <div style={{ background: "#0d1117", padding: "12px", borderRadius: "6px", border: "1px solid #1e293b" }}>
            <div style={{ color: "#9ca3af", fontSize: "11px" }}>WEBSOCKET FEED SERVER</div>
            <div style={{ color: "#26c78b", fontWeight: "600", marginTop: "4px" }}>ws://127.0.0.1:8000/api/market-feed/ws</div>
            <div style={{ color: "#64748b", fontSize: "10px", marginTop: "2px" }}>Real-time tick dispatcher</div>
          </div>
        </div>

        <div style={{ marginTop: "20px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: "11px", color: "#64748b" }}>
            Stock Intelligence Pro · VolumeLens-Inspired Personal Terminal
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

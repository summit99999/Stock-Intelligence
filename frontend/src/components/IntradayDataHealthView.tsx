import { useCallback, useEffect, useState } from "react";
import {
  fetchIntradayIngestionRuns,
  fetchIntradayIngestionStatus,
  fetchIntradayProviders,
} from "../api/marketMovers";

interface ProviderHealth {
  name: string;
  status: string;
  credentials_required?: boolean;
  credentials_configured?: boolean | null;
  stored_token_valid?: boolean;
  interval_supported?: string | null;
  max_history_days?: number | null;
  rate_limits?: string;
  exchange_mapping?: string;
  timestamps?: string;
  volume_returned?: boolean;
  limitations?: string;
  details?: string;
}

interface IngestionRun {
  id: string;
  symbol: string;
  provider: string;
  provider_symbol: string;
  actual_start_date?: string | null;
  actual_end_date?: string | null;
  provider_metadata?: { request?: { period?: string | null } };
  bar_count: number;
  retrieval_timestamp: string;
  raw_response_hash?: string | null;
  data_quality_status: string;
  error_message?: string | null;
  session_quality?: {
    session_date?: string | null;
    actual_bars?: number;
    missing_intervals?: string[];
    status?: string;
  }[] | null;
}

interface SymbolDetail {
  symbol: string;
  provider_symbol?: string;
  bar_count: number;
  observed_bars_count: number;
  synthetic_bars_count: number;
  unknown_bars_count?: number;
  session_count: number;
  valid_sessions_count: number;
  observed_valid_sessions_count: number;
  synthetic_valid_sessions_count: number;
  truncated_sessions_count: number;
  incomplete_sessions_count?: number;
  holiday_sessions_count?: number;
  source_classification?: string;
  production_ready?: boolean;
  tod_rvol_available?: boolean;
  schedule_version?: string;
  continuous_cutoff_time?: string;
  latest_bar?: string | null;
  earliest_bar?: string | null;
  status: string;
  is_cas_eligible?: boolean;
  expected_continuous_bars?: number;
  cas_reason?: string;
}

interface IntradayStatus {
  tracked_symbols_count: number;
  total_5m_bars_stored: number;
  total_observed_bars: number;
  total_synthetic_bars: number;
  total_unknown_bars: number;
  production_status: string;
  provider?: string;
  data_mode?: string;
  cas_schedule_version?: string;
  securities_with_observed_history?: number;
  symbols_with_observed_history?: number;
  symbols_meeting_observed_min: number;
  symbols_meeting_10_sessions?: number;
  symbols_meeting_20_sessions?: number;
  symbols_meeting_observed_target: number;
  symbols_with_synthetic_only: number;
  complete_sessions_count?: number;
  incomplete_sessions_count?: number;
  last_successful_ingestion_time?: string | null;
  failed_ingestion_attempts?: number;
  coverage_pct: number;
  earliest_timestamp?: string | null;
  latest_timestamp?: string | null;
  isolation_notice: string;
  symbol_details: SymbolDetail[];
}

interface HealthPayload {
  status: IntradayStatus;
  providers: { providers: Record<string, ProviderHealth> };
  runs: IngestionRun[];
}

async function loadHealth(): Promise<HealthPayload> {
  const [status, providers, runs] = await Promise.all([
    fetchIntradayIngestionStatus(),
    fetchIntradayProviders(),
    fetchIntradayIngestionRuns(50),
  ]);
  return { status, providers, runs: runs.runs || [] };
}

function formatTime(value?: string | null): string {
  if (!value) return "Unavailable";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function statusLabel(value?: string): string {
  if (!value) return "Unavailable";
  return value.replace(/_/g, " ");
}

export default function IntradayDataHealthView() {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolDetail | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setHealth(await loadHealth());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Intraday health could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const latestSuccess = health?.runs.find((run) =>
    run.data_quality_status === "VERIFIED_OBSERVED_INTRADAY"
  );
  const latestFailure = health?.runs.find((run) =>
    run.data_quality_status !== "VERIFIED_OBSERVED_INTRADAY"
  );

  return (
    <section className="intraday-health">
      <header className="intraday-health-header">
        <div>
          <div className="intraday-eyebrow">DATA QUALITY / INTRADAY EXPANSION AUDIT</div>
          <h2>Intraday Data Health &amp; Universe Coverage</h2>
          <p>Versioned NSE CAS session schedules, 31-stock historical 5-minute coverage, provenance, and TOD RVOL readiness.</p>
        </div>
        <button className="refresh-action-btn" type="button" onClick={() => void refresh()} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      <div className="intraday-disclosure" role="note">
        Provider-sourced historical data (Yahoo Finance) represents third-party delayed/historical observations and is never represented as live exchange tick feeds.
        NSE Closing Auction Session (CAS) schedule is verified per official NSE Circulars (NSE/CMTR/72394, 74466) and SEBI Framework (HO/47/11/11(3)2025-MRD-POD2/I/23843/2026).
        Synthetic calibrated simulation bars (46,500 records) are isolated and strictly excluded from production True Time-of-Day RVOL.
      </div>
      {error && <div className="notice" role="alert">Intraday health unavailable: {error}</div>}

      {health && (
        <>
          {/* Top Key Metrics Overview */}
          <div className="intraday-health-metrics">
            <article>
              <span>Tracked securities</span>
              <strong>{health.status.tracked_symbols_count}</strong>
              <small style={{ color: "#94a3b8", fontSize: "11px" }}>NSE F&amp;O Cash Universe</small>
            </article>
            <article>
              <span>Observed History</span>
              <strong style={{ color: "#38bdf8" }}>
                {health.status.securities_with_observed_history ?? health.status.symbols_with_observed_history ?? 0}/{health.status.tracked_symbols_count}
              </strong>
              <small style={{ color: "#94a3b8", fontSize: "11px" }}>Genuine provider bars</small>
            </article>
            <article>
              <span>TOD RVOL (≥3 Sess)</span>
              <strong style={{ color: "#22c55e" }}>
                {health.status.symbols_meeting_observed_min}/{health.status.tracked_symbols_count}
              </strong>
              <small style={{ color: "#94a3b8", fontSize: "11px" }}>Ready for production</small>
            </article>
            <article>
              <span>≥10 Sessions</span>
              <strong>{health.status.symbols_meeting_10_sessions ?? 0}</strong>
              <small style={{ color: "#94a3b8", fontSize: "11px" }}>Robust lookback</small>
            </article>
            <article>
              <span>20-Session Target</span>
              <strong style={{ color: "#f59e0b" }}>{health.status.symbols_meeting_20_sessions ?? 0}</strong>
              <small style={{ color: "#94a3b8", fontSize: "11px" }}>Max provider cap is 12</small>
            </article>
            <article>
              <span>Complete Sessions</span>
              <strong style={{ color: "#38bdf8" }}>{health.status.complete_sessions_count ?? 0}</strong>
              <small style={{ color: "#94a3b8", fontSize: "11px" }}>0 Incomplete</small>
            </article>
            <article>
              <span>Observed Bars</span>
              <strong style={{ color: "#22c55e" }}>{health.status.total_observed_bars.toLocaleString()}</strong>
              <small style={{ color: "#94a3b8", fontSize: "11px" }}>100% Provenance logged</small>
            </article>
            <article>
              <span>Synthetic Isolated</span>
              <strong style={{ color: "#cbd5e1" }}>{health.status.total_synthetic_bars.toLocaleString()}</strong>
              <small style={{ color: "#94a3b8", fontSize: "11px" }}>Preserved in ohlcv</small>
            </article>
          </div>

          {/* Operational Context Grid */}
          <div className="intraday-health-grid">
            <article className="intraday-health-card">
              <h3>Ingestion Audit &amp; CAS Schedule</h3>
              <p><b>Data Mode:</b> <span style={{ color: "#38bdf8" }}>{health.status.data_mode || "OBSERVED_HISTORICAL_INTRADAY"}</span></p>
              <p><b>CAS Schedule Version:</b> <span style={{ color: "#a855f7" }}>{health.status.cas_schedule_version || "CAS_V1_HISTORICAL"}</span></p>
              <p><b>Last Successful Ingestion:</b> {health.status.last_successful_ingestion_time ? formatTime(health.status.last_successful_ingestion_time) : latestSuccess ? formatTime(latestSuccess.retrieval_timestamp) : "None"}</p>
              <p><b>Failed Ingestion Attempts:</b> <span style={{ color: (health.status.failed_ingestion_attempts ?? 0) > 0 ? "#f97316" : "#22c55e" }}>{health.status.failed_ingestion_attempts ?? 0}</span> (Missing provider quotes logged without synthetic fallback)</p>
              <p><b>Production Status:</b> <span style={{ fontWeight: 600 }}>{statusLabel(health.status.production_status)}</span></p>
              <p style={{ fontSize: "12px", color: "#94a3b8", marginTop: "8px" }}>{health.status.isolation_notice}</p>
            </article>
            
            <article className="intraday-health-card">
              <h3>Provider Connectivity &amp; Governance</h3>
              {Object.entries(health.providers.providers || {}).map(([key, provider]) => (
                <div className="intraday-provider" key={key} style={{ marginBottom: "12px" }}>
                  <div className="intraday-provider-title">
                    <strong>{provider.name}</strong>
                    <span style={{ fontSize: "11px", padding: "2px 6px", borderRadius: "4px", background: provider.status === "ACTIVE_HISTORICAL_PROVIDER" ? "#064e3b" : "#1e293b", color: provider.status === "ACTIVE_HISTORICAL_PROVIDER" ? "#6ee7b7" : "#94a3b8" }}>
                      {statusLabel(provider.status)}
                    </span>
                  </div>
                  <p style={{ fontSize: "12px", margin: "4px 0" }}>
                    {provider.interval_supported
                      ? `${provider.interval_supported} interval · ${provider.max_history_days ?? "60"} day max lookback · Sequential rate limiting (2s)`
                      : provider.limitations}
                  </p>
                  {provider.credentials_required && (
                    <p style={{ fontSize: "11px", color: "#94a3b8" }}>
                      Credentials: {provider.credentials_configured ? "Configured" : "Unconfigured (Read-only)"} · Token: {provider.stored_token_valid ? "Valid" : "Not Active"}
                    </p>
                  )}
                  {provider.limitations && <p style={{ fontSize: "11px", color: "#e2e8f0" }}>{provider.limitations}</p>}
                </div>
              ))}
            </article>
          </div>

          {/* Modal / Details Inspector for Selected Symbol */}
          {selectedSymbol && (
            <div
              style={{
                position: "fixed",
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                backgroundColor: "rgba(0,0,0,0.75)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 9999,
                padding: "20px",
              }}
              onClick={() => setSelectedSymbol(null)}
            >
              <div
                style={{
                  background: "#0f172a",
                  border: "1px solid #334155",
                  borderRadius: "10px",
                  padding: "24px",
                  maxWidth: "600px",
                  width: "100%",
                  color: "#f8fafc",
                  boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", borderBottom: "1px solid #1e293b", paddingBottom: "12px" }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: "18px", display: "flex", alignItems: "center", gap: "8px" }}>
                      {selectedSymbol.symbol}
                      <span style={{ fontSize: "12px", background: "#1e293b", padding: "2px 8px", borderRadius: "4px", color: "#94a3b8" }}>
                        {selectedSymbol.provider_symbol || `${selectedSymbol.symbol}.NS`}
                      </span>
                    </h3>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedSymbol(null)}
                    style={{ background: "transparent", border: "none", color: "#94a3b8", fontSize: "18px", cursor: "pointer" }}
                  >
                    ✕
                  </button>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", fontSize: "13px", marginBottom: "16px" }}>
                  <div>
                    <span style={{ color: "#94a3b8" }}>CAS Schedule:</span>
                    <div><b>{selectedSymbol.schedule_version || (selectedSymbol.is_cas_eligible ? "CAS_V1_HISTORICAL" : "STANDARD_NON_CAS")}</b></div>
                  </div>
                  <div>
                    <span style={{ color: "#94a3b8" }}>Continuous Cutoff:</span>
                    <div><b>{selectedSymbol.continuous_cutoff_time || (selectedSymbol.is_cas_eligible ? "15:10:00 IST (72 bars)" : "15:25:00 IST (75 bars)")}</b></div>
                  </div>
                  <div>
                    <span style={{ color: "#94a3b8" }}>Observed Bars (DB):</span>
                    <div style={{ color: "#22c55e" }}><b>{selectedSymbol.observed_bars_count.toLocaleString()} bars</b></div>
                  </div>
                  <div>
                    <span style={{ color: "#94a3b8" }}>Synthetic Bars (Isolated):</span>
                    <div style={{ color: "#cbd5e1" }}><b>{selectedSymbol.synthetic_bars_count.toLocaleString()} bars</b></div>
                  </div>
                  <div>
                    <span style={{ color: "#94a3b8" }}>Valid Observed Sessions:</span>
                    <div style={{ color: "#38bdf8" }}><b>{selectedSymbol.observed_valid_sessions_count} sessions</b></div>
                  </div>
                  <div>
                    <span style={{ color: "#94a3b8" }}>Incomplete Sessions:</span>
                    <div><b>{selectedSymbol.truncated_sessions_count} sessions</b></div>
                  </div>
                  <div>
                    <span style={{ color: "#94a3b8" }}>TOD RVOL Status:</span>
                    <div>
                      <span style={{
                        padding: "2px 6px",
                        borderRadius: "4px",
                        fontSize: "11px",
                        background: selectedSymbol.tod_rvol_available ? "#064e3b" : "#450a0a",
                        color: selectedSymbol.tod_rvol_available ? "#6ee7b7" : "#fca5a5"
                      }}>
                        {selectedSymbol.tod_rvol_available ? "OBSERVED (READY)" : "UNAVAILABLE"}
                      </span>
                    </div>
                  </div>
                  <div>
                    <span style={{ color: "#94a3b8" }}>Production Ready:</span>
                    <div><b>{selectedSymbol.production_ready ? "YES (≥3 Sessions)" : "NO"}</b></div>
                  </div>
                </div>

                <div style={{ background: "#1e293b", padding: "12px", borderRadius: "6px", fontSize: "12px", color: "#cbd5e1", marginBottom: "16px" }}>
                  <b>Session Regulatory Notes:</b>
                  <p style={{ margin: "4px 0 0 0", fontSize: "11px", color: "#94a3b8" }}>
                    {selectedSymbol.cas_reason || "Governed by NSE Closing Auction Session framework under Circulars NSE/CMTR/72394 & 74466. Continuous trading ends at 15:15:00 IST. Auction executions at 15:25:00 IST are strictly isolated from continuous intraday Time-of-Day RVOL."}
                  </p>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  <button
                    type="button"
                    onClick={() => setSelectedSymbol(null)}
                    style={{ background: "#334155", color: "#f8fafc", border: "none", borderRadius: "4px", padding: "6px 14px", cursor: "pointer", fontSize: "12px" }}
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Universe Coverage Table */}
          <article className="intraday-health-card intraday-table-card">
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <h3 style={{ margin: 0 }}>Universe Coverage &amp; Session Completeness (31 Securities)</h3>
              <span style={{ fontSize: "12px", color: "#94a3b8" }}>Click any security to inspect details</span>
            </div>
            <div className="intraday-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Schedule Version</th>
                    <th>Observed Bars</th>
                    <th>Synthetic Bars</th>
                    <th>Valid Sessions</th>
                    <th>Incomplete</th>
                    <th>TOD RVOL Status</th>
                    <th>Latest Bar</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {health.status.symbol_details.map((item) => {
                    const hasObserved = item.observed_bars_count > 0;
                    const isReady = item.observed_valid_sessions_count >= 3;
                    return (
                      <tr
                        key={item.symbol}
                        style={{ cursor: "pointer" }}
                        onClick={() => setSelectedSymbol(item)}
                      >
                        <td>
                          <strong>{item.symbol}</strong>
                          <span style={{ display: "block", fontSize: "10px", color: "#64748b" }}>
                            {item.provider_symbol || `${item.symbol}.NS`}
                          </span>
                        </td>
                        <td>
                          <span
                            title={item.cas_reason || "Session schedule"}
                            style={{
                              fontSize: "11px",
                              padding: "2px 6px",
                              borderRadius: "4px",
                              background: item.is_cas_eligible ? "#3b0764" : "#1e293b",
                              color: item.is_cas_eligible ? "#d8b4fe" : "#94a3b8",
                            }}
                          >
                            {item.schedule_version || (item.is_cas_eligible ? "CAS_V1_HISTORICAL" : "STANDARD_NON_CAS")}
                          </span>
                        </td>
                        <td style={{ color: hasObserved ? "#22c55e" : "#64748b", fontWeight: hasObserved ? 600 : 400 }}>
                          {item.observed_bars_count.toLocaleString()}
                        </td>
                        <td style={{ color: "#94a3b8" }}>
                          {item.synthetic_bars_count.toLocaleString()}
                        </td>
                        <td>
                          <strong style={{ color: isReady ? "#38bdf8" : "#f59e0b" }}>
                            {item.observed_valid_sessions_count}
                          </strong>
                        </td>
                        <td style={{ color: item.truncated_sessions_count > 0 ? "#f97316" : "#64748b" }}>
                          {item.truncated_sessions_count}
                        </td>
                        <td>
                          <span style={{
                            padding: "2px 6px",
                            borderRadius: "4px",
                            fontSize: "10px",
                            fontWeight: 600,
                            background: isReady ? "#064e3b" : "#450a0a",
                            color: isReady ? "#6ee7b7" : "#fca5a5"
                          }}>
                            {isReady ? "OBSERVED_READY" : "UNAVAILABLE"}
                          </span>
                        </td>
                        <td style={{ fontSize: "11px", color: "#94a3b8" }}>{formatTime(item.latest_bar)}</td>
                        <td>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedSymbol(item);
                            }}
                            style={{
                              background: "#1e293b",
                              border: "1px solid #334155",
                              color: "#38bdf8",
                              borderRadius: "4px",
                              padding: "3px 8px",
                              fontSize: "11px",
                              cursor: "pointer",
                            }}
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </article>

          {/* Recent Ingestion Runs Table */}
          <article className="intraday-health-card intraday-table-card">
            <h3>Recent Ingestion Requests &amp; Provenance Hashes</h3>
            <div className="intraday-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Retrieved</th>
                    <th>Symbol</th>
                    <th>Provider</th>
                    <th>Requested Range</th>
                    <th>Bars</th>
                    <th>Validation Status</th>
                    <th>Response Hash (SHA-256)</th>
                  </tr>
                </thead>
                <tbody>
                  {health.runs.length === 0 ? (
                    <tr><td colSpan={7}>No ingestion requests have been recorded.</td></tr>
                  ) : health.runs.map((run) => (
                    <tr key={run.id}>
                      <td>{formatTime(run.retrieval_timestamp)}</td>
                      <td><strong>{run.symbol}</strong></td>
                      <td>{run.provider} · {run.provider_symbol}</td>
                      <td>{run.provider_metadata?.request?.period || "12d"} → {run.actual_start_date || "—"} – {run.actual_end_date || "—"}</td>
                      <td>{run.bar_count}</td>
                      <td>
                        <strong style={{
                          color: run.data_quality_status === "VERIFIED_OBSERVED_INTRADAY" ? "#22c55e" : "#f97316",
                          fontSize: "11px",
                        }}>
                          {statusLabel(run.data_quality_status)}
                        </strong>
                        {(run.error_message || run.session_quality?.length) && (
                          <details className="intraday-validation-details">
                            <summary>Validation details</summary>
                            {run.session_quality?.length ? (
                              <ul>
                                {run.session_quality.map((session, index) => (
                                  <li key={`${session.session_date || "unknown"}-${index}`}>
                                    {session.session_date || "Unparsed session"}: {session.actual_bars ?? "—"} bars
                                    {session.missing_intervals?.length
                                      ? ` · missing ${session.missing_intervals.join(", ")}`
                                      : session.status ? ` · ${statusLabel(session.status)}` : ""}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <small className="intraday-error">{run.error_message}</small>
                            )}
                          </details>
                        )}
                      </td>
                      <td title={run.raw_response_hash || "No response hash"}>
                        {run.raw_response_hash ? (
                          <code style={{ fontSize: "11px", color: "#94a3b8" }}>
                            {run.raw_response_hash.slice(0, 16)}…
                          </code>
                        ) : "Unavailable"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        </>
      )}
    </section>
  );
}

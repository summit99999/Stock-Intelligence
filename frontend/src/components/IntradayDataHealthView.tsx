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

interface IntradayStatus {
  tracked_symbols_count: number;
  total_5m_bars_stored: number;
  total_observed_bars: number;
  total_synthetic_bars: number;
  total_unknown_bars: number;
  production_status: string;
  symbols_meeting_observed_min: number;
  symbols_meeting_observed_target: number;
  symbol_details: {
    symbol: string;
    observed_bars_count: number;
    synthetic_bars_count: number;
    observed_valid_sessions_count: number;
    synthetic_valid_sessions_count: number;
    truncated_sessions_count: number;
    latest_bar?: string | null;
    status: string;
    is_cas_eligible?: boolean;
    expected_continuous_bars?: number;
    cas_reason?: string;
  }[];
  isolation_notice: string;
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
          <div className="intraday-eyebrow">DATA QUALITY / PROVIDER AUDIT</div>
          <h2>Intraday Data Health</h2>
          <p>Historical 5-minute coverage, provenance, provider access and session validation.</p>
        </div>
        <button className="refresh-action-btn" type="button" onClick={() => void refresh()} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      <div className="intraday-disclosure" role="note">
        Provider-sourced historical data is not direct NSE data and is never represented as LIVE.
        NSE Closing Auction Session (CAS) schedule is validated for eligible F&amp;O equities (72 continuous 5m bars + auction window) per NSE/CMTR/74466.
        Synthetic simulation bars are tracked separately and are excluded from production TOD RVOL.
      </div>
      {error && <div className="notice" role="alert">Intraday health unavailable: {error}</div>}

      {health && (
        <>
          <div className="intraday-health-metrics">
            <article><span>Tracked symbols</span><strong>{health.status.tracked_symbols_count}</strong></article>
            <article><span>Observed 5-minute bars</span><strong>{health.status.total_observed_bars.toLocaleString()}</strong></article>
            <article><span>Synthetic bars preserved</span><strong>{health.status.total_synthetic_bars.toLocaleString()}</strong></article>
            <article><span>TOD RVOL readiness</span><strong>{health.status.symbols_meeting_observed_min}/{health.status.tracked_symbols_count}</strong></article>
          </div>

          <div className="intraday-health-grid">
            <article className="intraday-health-card">
              <h3>Ingestion history</h3>
              <p><b>Last validated ingestion:</b> {latestSuccess ? `${latestSuccess.symbol} · ${formatTime(latestSuccess.retrieval_timestamp)}` : "None"}</p>
              <p><b>Last failed or incomplete:</b> {latestFailure ? `${latestFailure.symbol} · ${formatTime(latestFailure.retrieval_timestamp)}` : "None"}</p>
              <p><b>Production readiness:</b> {statusLabel(health.status.production_status)}</p>
              <p>{health.status.isolation_notice}</p>
            </article>
            <article className="intraday-health-card">
              <h3>Provider availability</h3>
              {Object.entries(health.providers.providers || {}).map(([key, provider]) => (
                <div className="intraday-provider" key={key}>
                  <div className="intraday-provider-title">
                    <strong>{provider.name}</strong>
                    <span>{statusLabel(provider.status)}</span>
                  </div>
                  <p>
                    {provider.interval_supported
                      ? `${provider.interval_supported} interval · ${provider.max_history_days ?? "Unknown"} day lookback`
                      : provider.limitations}
                  </p>
                  {provider.credentials_required && (
                    <p>Credentials configured: {provider.credentials_configured ? "Yes" : "No"} · Valid token: {provider.stored_token_valid ? "Yes" : "No"}</p>
                  )}
                  {provider.rate_limits && <p>{provider.rate_limits}</p>}
                  {provider.exchange_mapping && <p>{provider.exchange_mapping}</p>}
                  {provider.timestamps && <p>{provider.timestamps}</p>}
                  {provider.volume_returned != null && <p>Volume returned: {provider.volume_returned ? "Yes" : "No"}</p>}
                  {(provider.details || provider.limitations) && <p>{provider.details || provider.limitations}</p>}
                </div>
              ))}
            </article>
          </div>

          <article className="intraday-health-card intraday-table-card">
            <h3>Coverage by symbol</h3>
            <div className="intraday-table-wrap">
              <table>
                <thead><tr><th>Symbol</th><th>Schedule</th><th>Observed bars</th><th>Synthetic bars</th><th>Observed sessions</th><th>Incomplete sessions</th><th>Last bar</th><th>Status</th></tr></thead>
                <tbody>
                  {health.status.symbol_details.map((item) => (
                    <tr key={item.symbol}>
                      <td><strong>{item.symbol}</strong></td>
                      <td><span title={item.cas_reason || "Session structure"}>{item.is_cas_eligible ? "CAS (72b)" : "Std (75b)"}</span></td>
                      <td>{item.observed_bars_count.toLocaleString()}</td>
                      <td>{item.synthetic_bars_count.toLocaleString()}</td>
                      <td>{item.observed_valid_sessions_count}</td>
                      <td>{item.truncated_sessions_count}</td>
                      <td>{formatTime(item.latest_bar)}</td>
                      <td>{statusLabel(item.status)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>

          <article className="intraday-health-card intraday-table-card">
            <h3>Recent provider requests</h3>
            <div className="intraday-table-wrap">
              <table>
                <thead><tr><th>Retrieved</th><th>Symbol</th><th>Provider</th><th>Requested range</th><th>Bars</th><th>Validation</th><th>Response hash</th></tr></thead>
                <tbody>
                  {health.runs.length === 0 ? (
                    <tr><td colSpan={7}>No ingestion requests have been recorded.</td></tr>
                  ) : health.runs.map((run) => (
                    <tr key={run.id}>
                      <td>{formatTime(run.retrieval_timestamp)}</td>
                      <td>{run.symbol}</td>
                      <td>{run.provider} · {run.provider_symbol}</td>
                      <td>{run.provider_metadata?.request?.period || "Range unavailable"} → {run.actual_start_date || "—"} – {run.actual_end_date || "—"}</td>
                      <td>{run.bar_count}</td>
                      <td>
                        <strong>{statusLabel(run.data_quality_status)}</strong>
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
                        {run.raw_response_hash ? `${run.raw_response_hash.slice(0, 12)}…` : "Unavailable"}
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

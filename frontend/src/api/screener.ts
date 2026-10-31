/** API client for the Stock Screener backend. */

import type { ScreenRequest, ScreenResponse, ScreenerMetadata, SavedScreener } from "../types/screener";

const API_BASE = "http://127.0.0.1:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json();
}

/** Run the screener with filters. */
export async function runScreener(request: ScreenRequest): Promise<ScreenResponse> {
  // Strip undefined values and client-side IDs from condition groups
  const body = cleanRequest(request);
  return apiFetch<ScreenResponse>("/api/screener/run", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Get screener metadata (sectors, exchanges, filter definitions). */
export async function getScreenerMetadata(): Promise<ScreenerMetadata> {
  return apiFetch<ScreenerMetadata>("/api/screener/metadata");
}

/** Export results as CSV — returns a downloadable blob. */
export async function exportCSV(request: ScreenRequest): Promise<void> {
  const body = cleanRequest(request);
  const res = await fetch(`${API_BASE}/api/screener/export-csv`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "screener_results.csv";
  a.click();
  URL.revokeObjectURL(url);
}

/** List saved presets. */
export async function getPresets(): Promise<SavedScreener[]> {
  return apiFetch<SavedScreener[]>("/api/screener/presets");
}

/** Save a preset. */
export async function savePreset(name: string, description: string, config: ScreenRequest): Promise<SavedScreener> {
  const body = { name, description, config: cleanRequest(config) };
  return apiFetch<SavedScreener>("/api/screener/presets", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Delete a preset. */
export async function deletePreset(id: number): Promise<void> {
  await apiFetch<unknown>(`/api/screener/presets/${id}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function cleanRequest(req: ScreenRequest): Record<string, unknown> {
  const obj: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(req)) {
    if (v === undefined || v === null || v === "") continue;
    if (k === "condition_groups" && Array.isArray(v)) {
      // Strip client-side IDs
      obj[k] = v.map((g: Record<string, unknown>) => ({
        logic: g.logic,
        conditions: (g.conditions as Record<string, unknown>[]).map((c) => ({
          field: c.field,
          operator: c.operator,
          value: c.value,
          ...(c.value2 !== undefined && c.value2 !== null ? { value2: c.value2 } : {}),
        })),
      }));
    } else {
      obj[k] = v;
    }
  }
  return obj;
}

// ---------------------------------------------------------------------------
// Market Data API
// ---------------------------------------------------------------------------

export interface MarketDataStatus {
  provider_name: string | null;
  provider_data_type: string | null;
  provider_available: boolean;
  total_stocks: number;
  stocks_with_data: number;
  total_bars: number;
  updates: {
    symbol: string;
    provider: string;
    last_updated: string | null;
    bars_count: number;
    status: string;
  }[];
}

export interface UpdateResponse {
  job_id: string;
  status: string;
  message: string;
  symbols_count: number;
}

export interface JobStatus {
  job_id: string;
  status: string;
  total: number;
  completed_count: number;
  failed_count: number;
  started_at: string | null;
  finished_at: string | null;
  symbols_done: string[];
}

/** Get market data status. */
export async function getMarketDataStatus(): Promise<MarketDataStatus> {
  return apiFetch<MarketDataStatus>("/api/market-data/status");
}

/** Trigger a background data update. */
export async function triggerDataUpdate(
  symbols?: string[],
  period: string = "1y",
  force: boolean = false,
): Promise<UpdateResponse> {
  return apiFetch<UpdateResponse>("/api/market-data/update", {
    method: "POST",
    body: JSON.stringify({ symbols: symbols ?? [], period, force }),
  });
}

/** Get the status of a background update job. */
export async function getJobStatus(jobId: string): Promise<JobStatus> {
  return apiFetch<JobStatus>(`/api/market-data/jobs/${jobId}`);
}

/** API client for Fundamental Research, Scoring, Peer Comparison, and CSV Import. */

import type {
  CalculatedRatiosResult,
  CompanyResearchDossier,
  PeerComparisonResponse,
  QualityScoreResult,
  ScreenerCsvImportResponse,
} from "../types/fundamentals";

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

/** Get full research dossier for a company. */
export async function fetchCompanyResearch(symbol: string): Promise<CompanyResearchDossier> {
  return apiFetch<CompanyResearchDossier>(`/api/fundamentals/company/${symbol.toUpperCase()}/research`);
}

/** Get calculated financial ratios (CAGRs, ROE/ROCE, valuation). */
export async function fetchCalculatedRatios(
  symbol: string,
  statementType = "consolidated"
): Promise<CalculatedRatiosResult> {
  return apiFetch<CalculatedRatiosResult>(
    `/api/fundamentals/company/${symbol.toUpperCase()}/calculated-ratios?statement_type=${statementType}`
  );
}

/** Get 100-point fundamental quality score & deduction audit. */
export async function fetchQualityScore(symbol: string): Promise<QualityScoreResult> {
  return apiFetch<QualityScoreResult>(`/api/fundamentals/company/${symbol.toUpperCase()}/quality-score`);
}

/** Compare 2 to 5 peers side-by-side. */
export async function comparePeers(
  symbols: string[],
  targetSymbol?: string,
  statementType = "consolidated"
): Promise<PeerComparisonResponse> {
  return apiFetch<PeerComparisonResponse>("/api/fundamentals/peers/compare", {
    method: "POST",
    body: JSON.stringify({
      symbols,
      target_symbol: targetSymbol,
      statement_type: statementType,
    }),
  });
}

/** Import fundamental data from Screener.in CSV export with overwrite protection. */
export async function importScreenerCsv(
  fileOrContent: File | string,
  symbol?: string,
  overwriteVerified = false
): Promise<ScreenerCsvImportResponse> {
  let url = `${API_BASE}/api/fundamentals/import/screener-csv?overwrite_verified=${overwriteVerified}`;
  if (symbol) {
    url += `&symbol=${encodeURIComponent(symbol.toUpperCase())}`;
  }

  let res: Response;
  if (typeof fileOrContent === "string") {
    res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "text/plain" },
      body: fileOrContent,
    });
  } else {
    const formData = new FormData();
    formData.append("file", fileOrContent);
    if (symbol) formData.append("symbol", symbol.toUpperCase());
    formData.append("overwrite_verified", String(overwriteVerified));
    res = await fetch(url, {
      method: "POST",
      body: formData,
    });
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Upload failed: ${res.status} - ${text}`);
  }
  return res.json();
}

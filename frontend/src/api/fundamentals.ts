/** API client for Fundamental Research, Scoring, Peer Comparison, and CSV Import. */

import type {
  CalculatedRatiosResult,
  CompanyResearchDossier,
  PeerComparisonResponse,
  QualityScoreResult,
  ScreenerCsvImportResponse,
} from "../types/fundamentals";
import { apiJson, apiFetch } from "./client";

/** Get full research dossier for a company. */
export async function fetchCompanyResearch(symbol: string): Promise<CompanyResearchDossier> {
  return apiJson<CompanyResearchDossier>(`/api/fundamentals/company/${symbol.toUpperCase()}/research`);
}

/** Get calculated financial ratios for a company. */
export async function fetchCalculatedRatios(
  symbol: string,
  statementType = "consolidated"
): Promise<CalculatedRatiosResult> {
  return apiJson<CalculatedRatiosResult>(
    `/api/fundamentals/company/${symbol.toUpperCase()}/ratios/calculated?statement_type=${statementType}`
  );
}

/** Get 100-point institutional quality score for a company. */
export async function fetchQualityScore(symbol: string): Promise<QualityScoreResult> {
  return apiJson<QualityScoreResult>(`/api/fundamentals/company/${symbol.toUpperCase()}/scoring/quality-score`);
}

/** Get peer comparison matrix. */
export async function fetchPeerComparison(
  symbols: string[],
  targetSymbol?: string
): Promise<PeerComparisonResponse> {
  const target = targetSymbol || symbols[0] || "TCS";
  return apiJson<PeerComparisonResponse>("/api/fundamentals/peers/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols, target_symbol: target }),
  });
}

/** Import fundamental data from Screener.in CSV export with overwrite protection. */
export async function importScreenerCsv(
  fileOrContent: File | string,
  symbol?: string,
  overwriteVerified = false
): Promise<ScreenerCsvImportResponse> {
  let path = `/api/fundamentals/import/screener-csv?overwrite_verified=${overwriteVerified}`;
  if (symbol) {
    path += `&symbol=${encodeURIComponent(symbol.toUpperCase())}`;
  }

  let res: Response;
  if (typeof fileOrContent === "string") {
    res = await apiFetch(path, {
      method: "POST",
      headers: { "Content-Type": "text/plain" },
      body: fileOrContent,
    });
  } else {
    const formData = new FormData();
    formData.append("file", fileOrContent);
    if (symbol) formData.append("symbol", symbol.toUpperCase());
    formData.append("overwrite_verified", String(overwriteVerified));
    res = await apiFetch(path, {
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

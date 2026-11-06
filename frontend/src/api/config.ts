/**
 * Frontend Cloud & Environment Configuration.
 * 
 * Supports dynamic configuration via Vite environment variables:
 * - VITE_API_BASE_URL: Backend FastAPI URL (Render / Local)
 * - VITE_SUPABASE_URL: Supabase Project URL
 * - VITE_SUPABASE_ANON_KEY: Browser-safe anonymous public key
 */

export function getApiBaseUrl(): string {
  const envUrl = import.meta.env.VITE_API_BASE_URL;
  if (envUrl && typeof envUrl === "string" && envUrl.trim()) {
    return envUrl.trim().replace(/\/+$/, "");
  }
  // Fallback to local development port
  return "http://127.0.0.1:8000";
}

export const SUPABASE_URL = (import.meta.env.VITE_SUPABASE_URL || "").trim();
export const SUPABASE_ANON_KEY = (import.meta.env.VITE_SUPABASE_ANON_KEY || "").trim();

export const isAuthEnabled = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

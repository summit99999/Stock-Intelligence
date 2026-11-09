/**
 * Frontend Cloud & Environment Configuration.
 * 
 * Supports dynamic configuration via Vite or generic environment variables:
 * - VITE_API_BASE_URL / NEXT_PUBLIC_API_BASE_URL / API_BASE_URL: Backend FastAPI URL
 * - VITE_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_URL
 * - VITE_SUPABASE_ANON_KEY / NEXT_PUBLIC_SUPABASE_ANON_KEY
 */

const DEFAULT_PROD_API_BASE = "https://stock-intelligence-api-2esm.onrender.com";

export function getApiBaseUrl(): string {
  const envUrl =
    import.meta.env.VITE_API_BASE_URL ||
    (import.meta.env as any).NEXT_PUBLIC_API_BASE_URL ||
    (import.meta.env as any).REACT_APP_API_BASE_URL ||
    (import.meta.env as any).API_BASE_URL;

  if (envUrl && typeof envUrl === "string" && envUrl.trim()) {
    return envUrl.trim().replace(/\/+$/, "");
  }

  // Automatic production fallback when running on Vercel or cloud domain
  if (typeof window !== "undefined" && window.location) {
    const host = window.location.hostname;
    if (host !== "localhost" && host !== "127.0.0.1" && !host.startsWith("192.168.")) {
      return DEFAULT_PROD_API_BASE;
    }
  }

  // Fallback to local development port
  return "http://127.0.0.1:8000";
}

export const SUPABASE_URL = (
  import.meta.env.VITE_SUPABASE_URL ||
  (import.meta.env as any).NEXT_PUBLIC_SUPABASE_URL ||
  ""
).trim();

export const SUPABASE_ANON_KEY = (
  import.meta.env.VITE_SUPABASE_ANON_KEY ||
  (import.meta.env as any).NEXT_PUBLIC_SUPABASE_ANON_KEY ||
  ""
).trim();

export const isAuthEnabled = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

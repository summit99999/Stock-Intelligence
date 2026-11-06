import { getApiBaseUrl } from "./config";
import { getAuthToken } from "./supabaseClient";

/**
 * Resolve an API path to a fully qualified URL using VITE_API_BASE_URL.
 */
export function apiUrl(path: string): string {
  const base = getApiBaseUrl();
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${cleanPath}`;
}

/**
 * Enhanced fetch wrapper that attaches Supabase Bearer JWT tokens when authenticated.
 */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = apiUrl(path);
  const headers = new Headers(init?.headers || {});

  // Attach auth token if available
  const token = await getAuthToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  // Ensure JSON content type for body payloads
  if (init?.body && !headers.has("Content-Type") && typeof init.body === "string") {
    headers.set("Content-Type", "application/json");
  }

  return fetch(url, {
    ...init,
    headers,
  });
}

/**
 * Typed JSON fetch helper with standard production error handling.
 */
export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    let errDetail = `HTTP ${response.status} (${response.statusText})`;
    try {
      const errBody = await response.json();
      if (errBody && errBody.detail) {
        errDetail = typeof errBody.detail === "string" ? errBody.detail : JSON.stringify(errBody.detail);
      }
    } catch {
      // Ignore JSON parse error on non-JSON response
    }
    throw new Error(errDetail);
  }
  return response.json() as Promise<T>;
}

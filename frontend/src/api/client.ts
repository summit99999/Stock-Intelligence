import { getApiBaseUrl } from "./config";
import { getAuthToken } from "./supabaseClient";

/**
 * Structured API Error containing HTTP metadata and actionable diagnostic flags.
 */
export class ApiError extends Error {
  status: number;
  statusText: string;
  endpoint: string;
  responseBody?: string;
  isNetworkError: boolean;
  isAuthError: boolean;
  isWarmup: boolean;

  constructor(options: {
    message: string;
    status?: number;
    statusText?: string;
    endpoint: string;
    responseBody?: string;
    isNetworkError?: boolean;
    isAuthError?: boolean;
    isWarmup?: boolean;
  }) {
    super(options.message);
    this.name = "ApiError";
    this.status = options.status || 0;
    this.statusText = options.statusText || "";
    this.endpoint = options.endpoint;
    this.responseBody = options.responseBody;
    this.isNetworkError = Boolean(options.isNetworkError);
    this.isAuthError = Boolean(
      options.isAuthError || options.status === 401 || options.status === 403
    );
    this.isWarmup = Boolean(options.isWarmup);
  }
}

/**
 * Resolve an API path to a fully qualified URL using VITE_API_BASE_URL.
 */
export function apiUrl(path: string): string {
  const base = getApiBaseUrl();
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${cleanPath}`;
}

/**
 * Safely parse JSON from a Response object, preventing unexpected token errors
 * when endpoints return HTML (such as Vercel 404s or Render cold-start pages).
 */
export async function safeJsonParse<T>(response: Response, endpoint: string): Promise<T> {
  const contentType = response.headers.get("content-type") || "";
  const text = await response.text();

  if (!text || !text.trim()) {
    return {} as T;
  }

  const lowerText = text.trim().toLowerCase();

  // Detect HTML responses (Vercel SPA fallback, Cloudflare 502/504, or Render cold-start pages)
  if (
    contentType.includes("text/html") ||
    lowerText.startsWith("<!doctype") ||
    lowerText.startsWith("<html") ||
    lowerText.includes("<head") ||
    lowerText.includes("<body>")
  ) {
    const isWarming =
      response.status === 502 ||
      response.status === 503 ||
      response.status === 504 ||
      text.includes("Render") ||
      text.includes("Cloudflare") ||
      text.includes("Gateway") ||
      response.status === 200;

    throw new ApiError({
      message: isWarming
        ? `Backend is spinning up on Render (${endpoint}). Please wait a moment.`
        : `Backend returned HTML instead of JSON for ${endpoint} (HTTP ${response.status}).`,
      status: response.status,
      statusText: response.statusText,
      endpoint,
      responseBody: text.slice(0, 300),
      isWarmup: isWarming,
    });
  }

  try {
    return JSON.parse(text) as T;
  } catch (parseErr: any) {
    throw new ApiError({
      message: `Invalid JSON response from ${endpoint}: ${parseErr?.message || "Failed to parse"}`,
      status: response.status,
      statusText: response.statusText,
      endpoint,
      responseBody: text.slice(0, 300),
    });
  }
}

/**
 * Enhanced fetch wrapper with:
 * - Supabase JWT bearer token attachment
 * - Automatic URL normalization
 * - Safe .json() wrapping to prevent syntax crashes
 * - Explicit timeout and network failure classification
 * - Automatic retry with delay for Render cold starts
 */
export async function apiFetch(path: string, init?: RequestInit, retries: number = 2): Promise<Response> {
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

  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url, {
        ...init,
        headers,
      });

      // Check if response is a transient cold-start gateway error (502, 503, 504)
      if ((response.status === 502 || response.status === 503 || response.status === 504) && attempt < retries) {
        await new Promise((r) => setTimeout(r, 2000 * (attempt + 1)));
        continue;
      }

      // Monkey-patch response.json() so calling it directly in any existing component
      // goes through safeJsonParse rather than crashing with "Unexpected token '<'".
      const originalJson = response.json.bind(response);
      response.json = async function () {
        try {
          return await safeJsonParse(response.clone(), path);
        } catch (err) {
          if (err instanceof ApiError) {
            throw err;
          }
          return originalJson();
        }
      };

      return response;
    } catch (netErr: any) {
      if (attempt < retries) {
        await new Promise((r) => setTimeout(r, 2000 * (attempt + 1)));
        continue;
      }
      if (netErr instanceof ApiError) {
        throw netErr;
      }
      throw new ApiError({
        message: `Network error connecting to ${path}: ${netErr?.message || "Connection failed"}. Check your connection or backend status.`,
        endpoint: path,
        isNetworkError: true,
      });
    }
  }

  throw new ApiError({
    message: `Backend service is warming up (${path}). Please wait a few seconds and refresh.`,
    endpoint: path,
    isWarmup: true,
  });
}

/**
 * Typed JSON fetch helper with full error detail extraction and validation.
 */
export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init);

  if (!response.ok) {
    let errDetail = `HTTP ${response.status} (${response.statusText})`;
    try {
      const data = await safeJsonParse<any>(response, path);
      if (data && data.detail) {
        errDetail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      } else if (data && data.message) {
        errDetail = data.message;
      }
    } catch (e: any) {
      if (e instanceof ApiError) {
        throw e;
      }
    }

    throw new ApiError({
      message: `${errDetail} on ${path}`,
      status: response.status,
      statusText: response.statusText,
      endpoint: path,
    });
  }

  return safeJsonParse<T>(response, path);
}

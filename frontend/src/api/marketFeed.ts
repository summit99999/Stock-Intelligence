/**
 * Upstox Live Market Feed Client (REST snapshot & WebSocket streaming)
 */

export interface LiveQuote {
  symbol: string;
  security_id: string;
  exchange_segment: string;
  ltp: number;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  change?: number;
  change_percent?: number;
  volume?: number;
  atp?: number;
  ltt?: string;
  source: "LIVE" | "DELAYED" | "HISTORICAL" | "DEMO";
  updated_at: string;
}

export interface LiveFeedStatus {
  status: "CONNECTED" | "DISCONNECTED" | "AUTHENTICATION_REQUIRED" | "CONNECTING" | "RATE_LIMITED" | "DISABLED";
  authenticated: boolean;
  live_data_enabled?: boolean;
  subscribed_symbols: string[];
  subscribed_count: number;
  last_tick_time?: string;
  ticks_received: number;
  connected_clients: number;
  error?: string;
  retry_in_seconds?: number;
}

export interface LiveQuotesResponse {
  quotes: Record<string, LiveQuote>;
  source: "LIVE" | "DELAYED" | "HISTORICAL" | "DEMO" | "HYBRID";
  count: number;
}

export interface MarketDataHealthDiagnostics {
  status: "healthy" | "degraded" | "unhealthy";
  backend_status: string;
  upstox_authentication: "AUTHENTICATED" | "AUTHENTICATION_REQUIRED" | "EXPIRED";
  upstox_websocket: "CONNECTED" | "CONNECTING" | "DISCONNECTED" | "DISABLED";
  frontend_websocket: string;
  frontend_websocket_clients: number;
  protobuf_decoder: "SUCCESS" | "IDLE" | "ERROR";
  subscription_status: "ACTIVE" | "IDLE" | "EMPTY";
  subscribed_instruments: number;
  subscribed_symbols: string[];
  last_message_received?: string;
  last_message_processed?: string;
  ticks_received_count: number;
  market_status: "OPEN" | "CLOSED" | "PRE_OPEN";
  market_status_note: string;
  data_freshness: "FRESH" | "STALE" | "SESSION_CLOSE";
  last_tick?: Record<string, any>;
  last_error?: string;
  server_time_ist: string;
  database_persisted: boolean;
}

import { getApiBaseUrl } from "./config";
import { apiFetch } from "./client";

const API_BASE = getApiBaseUrl();
const WS_BASE = API_BASE.replace(/^http/, "ws");

export async function fetchLiveQuotes(symbols?: string[]): Promise<LiveQuotesResponse> {
  const query = symbols && symbols.length > 0 ? `?symbols=${symbols.join(",")}` : "";
  const res = await apiFetch(`/api/market/live/quotes${query}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch live quotes: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchLiveFeedStatus(): Promise<LiveFeedStatus> {
  const res = await apiFetch(`/api/market/live/status`);
  if (!res.ok) {
    throw new Error(`Failed to fetch live feed status: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchMarketDataHealth(): Promise<MarketDataHealthDiagnostics> {
  const res = await apiFetch(`/api/health/market-data`);
  if (!res.ok) {
    throw new Error(`Failed to fetch market data diagnostics: ${res.statusText}`);
  }
  return res.json();
}

export async function refreshLiveQuotes(): Promise<LiveQuotesResponse> {
  const res = await apiFetch(`/api/market/live/refresh`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Failed to refresh quotes: ${res.statusText}`);
  }
  return res.json();
}

export async function reconnectLiveFeed(enable: boolean = false): Promise<LiveFeedStatus> {
  const query = enable ? "?enable=true" : "";
  const res = await apiFetch(`/api/market/live/reconnect${query}`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Failed to reconnect live feed: ${res.statusText}`);
  }
  return res.json();
}

export function subscribeMarketFeed(callbacks: {
  onTick?: (quote: LiveQuote) => void;
  onSnapshot?: (quotes: Record<string, LiveQuote>, feedStatus?: LiveFeedStatus) => void;
  onStatusChange?: (status: LiveFeedStatus) => void;
}): () => void {
  let ws: WebSocket | null = null;
  let isClosed = false;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function connect() {
    if (isClosed) return;
    try {
      ws = new WebSocket(`${WS_BASE}/ws/market-feed`);

      ws.onopen = () => {
        // Send initial ping to verify connection
        ws?.send(JSON.stringify({ type: "PING" }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "TICK" && data.quote && callbacks.onTick) {
            callbacks.onTick(data.quote);
          } else if (data.type === "SNAPSHOT" && data.quotes && callbacks.onSnapshot) {
            callbacks.onSnapshot(data.quotes, data.feed_status);
          } else if (data.type === "STATUS_UPDATE" && data.feed_status && callbacks.onStatusChange) {
            callbacks.onStatusChange(data.feed_status);
          }
        } catch {
          // ignore non-json frames
        }
      };

      ws.onclose = () => {
        if (!isClosed) {
          reconnectTimer = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        ws?.close();
      };
    } catch {
      if (!isClosed) {
        reconnectTimer = setTimeout(connect, 3000);
      }
    }
  }

  connect();

  return () => {
    isClosed = true;
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (ws) ws.close();
  };
}

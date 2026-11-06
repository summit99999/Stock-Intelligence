import { useEffect, useState } from "react";
import type { FormEvent } from "react";

const API_BASE = "";

interface Stock {
  symbol: string;
  company_name?: string;
  sector?: string;
  close?: number;
  daily_change_pct?: number;
  relative_volume?: number;
  setup_score?: number;
  relative_strength_vs_market?: number;
}

interface MarketDashboard {
  timestamp?: string;
  universe_label?: string;
  coverage_note?: string;
  scanned_count?: number;
  configured_universe_count?: number;
  coverage_pct?: number;
  indices?: {
    name: string;
    symbol: string;
    value: string;
    change_pct?: number | null;
    data_mode?: string;
    status?: string;
  }[];
  breadth?: {
    advances: number;
    declines: number;
    unchanged: number;
    total_tracked: number;
    breadth_pct: number;
    advance_decline_ratio: number;
  };
  leaders?: {
    gainers: Stock[];
    losers: Stock[];
    volume_surge: Stock[];
  };
  metadata?: { data_mode?: string; provider?: string; last_update_timestamp?: string };
}

interface SectorData {
  sectors?: {
    sector: string;
    average_change_pct: number;
    relative_strength_vs_market: number;
    rotation_quadrant: string;
    breakout_count: number;
    strongest_stock?: { symbol: string; company_name?: string; change_pct: number; close: number };
  }[];
}

interface MoneyFlowData {
  metadata?: { data_mode?: string; disclaimer?: string };
  market_overview?: { coverage_pct?: number; scanned_count?: number; universe_label?: string };
  money_flow_summary?: {
    market_close_location_buying_bias_pct?: number;
    market_close_location_selling_bias_pct?: number;
    market_buying_pressure_pct?: number;
    market_selling_pressure_pct?: number;
    net_flow_bias?: string;
    rvol_time_label?: string;
    volume_expansion_count?: number;
    institutional_flow?: { status?: string; disclosure?: string };
  };
  volume_gainers?: Stock[];
  sector_money_flow?: { sector: string; average_rvol: number; net_flow_bias: string }[];
}

interface AlertEvent {
  id: number;
  symbol: string;
  alert_type: string;
  message?: string;
  timestamp: string;
}

interface DashboardHomeProps {
  onSelectStock: (symbol: string) => void;
  onNavigate: (page: string) => void;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) throw new Error(`API returned HTTP ${response.status}`);
  return response.json() as Promise<T>;
}

function EmptyState({ reason }: { reason: string }) {
  return <div className="dashboard-empty">{reason}</div>;
}

function StockTable({
  stocks,
  onSelectStock,
  label,
  metricLabel = "RVOL",
}: {
  stocks: Stock[];
  onSelectStock: (symbol: string) => void;
  label: string;
  metricLabel?: "RVOL" | "RS VS MKT";
}) {
  if (stocks.length === 0) return <EmptyState reason={label} />;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>STOCK</th><th>PRICE</th><th>CHANGE</th><th>{metricLabel}</th></tr>
        </thead>
        <tbody>
          {stocks.slice(0, 5).map((stock) => (
            <tr key={stock.symbol} onClick={() => onSelectStock(stock.symbol)} className="dashboard-stock-row">
              <td><strong>{stock.symbol}</strong><small>{stock.company_name || stock.sector || "Equity"}</small></td>
              <td>{stock.close == null ? "—" : `₹${stock.close.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`}</td>
              <td className={(stock.daily_change_pct ?? 0) >= 0 ? "positive" : "negative"}>
                {stock.daily_change_pct == null ? "—" : `${stock.daily_change_pct > 0 ? "+" : ""}${stock.daily_change_pct.toFixed(2)}%`}
              </td>
              <td>{metricLabel === "RS VS MKT"
                ? stock.relative_strength_vs_market == null ? "—" : `${stock.relative_strength_vs_market > 0 ? "+" : ""}${stock.relative_strength_vs_market.toFixed(2)}%`
                : stock.relative_volume == null ? "—" : `${stock.relative_volume.toFixed(2)}x`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function DashboardHome({ onSelectStock, onNavigate }: DashboardHomeProps) {
  const [market, setMarket] = useState<MarketDashboard | null>(null);
  const [sectorData, setSectorData] = useState<SectorData | null>(null);
  const [flow, setFlow] = useState<MoneyFlowData | null>(null);
  const [setups, setSetups] = useState<Stock[]>([]);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");

  useEffect(() => {
    let active = true;
    const load = async <T,>(name: string, request: Promise<T>, apply: (value: T) => void) => {
      try {
        const value = await request;
        if (active) apply(value);
      } catch (error) {
        if (active) {
          setErrors((previous) => ({
            ...previous,
            [name]: error instanceof Error ? error.message : "Could not reach the service.",
          }));
        }
      }
    };

    Promise.all([
      load("Market overview", getJson<MarketDashboard>("/api/market/intelligence/dashboard?universe=all"), setMarket),
      load("Sector data", getJson<SectorData>("/api/market/intelligence/sectors?universe=all"), setSectorData),
      load("Money flow", getJson<MoneyFlowData>("/api/money-flow/overview?universe=all"), setFlow),
      load("Breakout candidates", getJson<{ items?: Stock[] }>("/api/research/discovery?universe=all&direction=BULLISH&min_score=60&page_size=5"), (value) => setSetups(value.items || [])),
      load("Recent alerts", getJson<AlertEvent[]>("/api/alerts/history?limit=5"), setAlerts),
    ]).finally(() => {
      if (active) setLoading(false);
    });

    return () => { active = false; };
  }, []);

  const dataMode = market?.metadata?.data_mode || "UNAVAILABLE";
  const isLive = dataMode.toUpperCase() === "LIVE";
  const strongestSectors = [...(sectorData?.sectors || [])]
    .sort((a, b) => b.relative_strength_vs_market - a.relative_strength_vs_market)
    .slice(0, 5);
  const relativeStrengthStocks: Stock[] = strongestSectors
    .filter((sector) => sector.strongest_stock)
    .map((sector) => ({
      symbol: sector.strongest_stock!.symbol,
      company_name: sector.strongest_stock!.company_name || sector.sector,
      sector: sector.sector,
      close: sector.strongest_stock!.close,
      daily_change_pct: sector.strongest_stock!.change_pct,
      relative_strength_vs_market: sector.relative_strength_vs_market,
    }));
  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const symbol = search.trim().toUpperCase();
    if (symbol) onSelectStock(symbol);
  };

  return (
    <div className="dashboard-home">
      <section className="welcome-row">
        <div>
          <h2>Market at a glance</h2>
          <p>Evidence-led market context, stock leadership and flow signals.</p>
        </div>
        <span className={`data-mode-chip ${isLive ? "is-live" : ""}`}>
          <i /> {isLive ? "LIVE" : dataMode}
        </span>
      </section>

      <form className="dashboard-search" onSubmit={submitSearch}>
        <span aria-hidden="true">⌕</span>
        <input aria-label="Search a stock symbol" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search a stock symbol, e.g. RELIANCE" />
        <button type="submit">Open chart</button>
      </form>

      {market && (
        <section className="dashboard-metrics">
          {(market.indices || []).map((index) => (
            <article className="index-card" key={index.symbol}>
              <div className="card-top"><span>{index.name}</span><span className="badge-demo">{index.status === "UNAVAILABLE" ? "UNAVAILABLE" : index.data_mode || dataMode}</span></div>
              <div className="index-value">{index.value || "—"}</div>
              <div className="index-bottom">
                <span className={index.change_pct == null ? "" : index.change_pct >= 0 ? "positive" : "negative"}>
                  {index.change_pct == null ? "Change unavailable" : `${index.change_pct > 0 ? "+" : ""}${index.change_pct.toFixed(2)}%`}
                </span>
              </div>
            </article>
          ))}
          {market.indices?.length === 0 && <EmptyState reason="No benchmark index data is available from the market intelligence service." />}
        </section>
      )}
      {!market && <EmptyState reason={errors["Market overview"] ? `Market overview unavailable: ${errors["Market overview"]}` : "Loading market overview…"} />}

      <div className="dashboard-coverage">
        <span><strong>Coverage</strong> {market ? `${market.scanned_count ?? 0} / ${market.configured_universe_count ?? 0} stocks · ${market.coverage_pct ?? 0}%` : "Unavailable"}</span>
        <span>{market?.coverage_note || errors["Market overview"] || "Coverage detail unavailable."}</span>
        <span>Updated {market?.metadata?.last_update_timestamp || "—"} · {market?.metadata?.provider || "Source unavailable"}</span>
      </div>

      <section className="content-grid dashboard-overview-grid">
        <article className="panel">
          <div className="panel-heading"><div><h3>Market breadth</h3><p>Tracked universe advance / decline</p></div></div>
          {market?.breadth ? (
            <>
              <div className="breadth-numbers">
                <div><strong className="positive">{market.breadth.advances}</strong><span>Advances</span></div>
                <div><strong className="negative">{market.breadth.declines}</strong><span>Declines</span></div>
                <div><strong>{market.breadth.unchanged}</strong><span>Unchanged</span></div>
              </div>
              <div className="breadth-bar">
                <span className="advance-bar" style={{ width: `${market.breadth.breadth_pct}%` }} />
                <span className="decline-bar" />
              </div>
              <div className="breadth-legend"><span>{market.breadth.breadth_pct}% advancing · A/D {market.breadth.advance_decline_ratio}</span><span>{market.breadth.total_tracked} tracked</span></div>
            </>
          ) : <EmptyState reason={errors["Market overview"] || (loading ? "Loading breadth…" : "Breadth data is unavailable.")} />}
        </article>
        <article className="panel">
          <div className="panel-heading">
            <div><h3>Sector leadership</h3><p>Relative strength vs. market</p></div>
            <button className="text-action" onClick={() => onNavigate("Sector Rotation")}>View rotation</button>
          </div>
          {strongestSectors.length ? <div className="sector-list">
            {strongestSectors.map((sector) => (
              <div className="sector-row" key={sector.sector}>
                <span>{sector.sector}</span><div className="sector-track"><span className={sector.average_change_pct >= 0 ? "sector-positive" : "sector-negative"} style={{ width: `${Math.min(100, Math.max(12, Math.abs(sector.average_change_pct) * 24))}%` }} /></div>
                <strong className={sector.average_change_pct >= 0 ? "positive" : "negative"}>{sector.average_change_pct > 0 ? "+" : ""}{sector.average_change_pct.toFixed(2)}%</strong>
              </div>
            ))}
          </div> : <EmptyState reason={errors["Sector data"] || (loading ? "Loading sectors…" : "Sector performance is unavailable.")} />}
        </article>
      </section>

      <section className="content-grid dashboard-lists-grid">
        <article className="panel">
          <div className="panel-heading"><div><h3>Top gainers</h3><p>Market intelligence · tracked universe</p></div><button className="text-action" onClick={() => onNavigate("Market Movers")}>Confluence View →</button></div>
          <StockTable stocks={market?.leaders?.gainers || []} onSelectStock={onSelectStock} label={errors["Market overview"] || (loading ? "Loading gainers…" : "No gainers returned for this universe.")} />
        </article>
        <article className="panel">
          <div className="panel-heading"><div><h3>Top losers</h3><p>Market intelligence · tracked universe</p></div></div>
          <StockTable stocks={market?.leaders?.losers || []} onSelectStock={onSelectStock} label={errors["Market overview"] || (loading ? "Loading losers…" : "No losers returned for this universe.")} />
        </article>
        <article className="panel">
          <div className="panel-heading"><div><h3>High volume</h3><p>Ranked by relative volume</p></div></div>
          <StockTable stocks={market?.leaders?.volume_surge || []} onSelectStock={onSelectStock} label={errors["Market overview"] || (loading ? "Loading volume leaders…" : "No high-volume stocks returned.")} />
        </article>
        <article className="panel">
          <div className="panel-heading"><div><h3>Breakout candidates</h3><p>Research discovery · bullish setup score ≥ 60</p></div></div>
          <StockTable stocks={setups} onSelectStock={onSelectStock} label={errors["Breakout candidates"] || (loading ? "Loading candidates…" : "No candidates met the requested setup threshold.")} />
        </article>
        <article className="panel">
          <div className="panel-heading"><div><h3>Relative strength leaders</h3><p>Leading stock within each strongest sector</p></div></div>
          <StockTable stocks={relativeStrengthStocks} onSelectStock={onSelectStock} label={errors["Sector data"] || (loading ? "Loading relative strength…" : "No sector leaders are currently available.")} metricLabel="RS VS MKT" />
        </article>
      </section>

      <section className="content-grid dashboard-bottom-grid">
        <article className="panel">
          <div className="panel-heading"><div><h3>Money flow pulse</h3><p>OHLCV-derived indicators, not order-tape flow</p></div><button className="text-action" onClick={() => onNavigate("Money Flow Intelligence")}>Explore flow</button></div>
          {flow?.money_flow_summary ? (
            <>
              <div className="flow-summary">
                <div><span>Close-location buying bias</span><strong className="positive">{flow.money_flow_summary.market_close_location_buying_bias_pct ?? flow.money_flow_summary.market_buying_pressure_pct ?? "—"}{flow.money_flow_summary.market_close_location_buying_bias_pct == null && flow.money_flow_summary.market_buying_pressure_pct == null ? "" : "%"}</strong></div>
                <div><span>Close-location selling bias</span><strong className="negative">{flow.money_flow_summary.market_close_location_selling_bias_pct ?? flow.money_flow_summary.market_selling_pressure_pct ?? "—"}{flow.money_flow_summary.market_close_location_selling_bias_pct == null && flow.money_flow_summary.market_selling_pressure_pct == null ? "" : "%"}</strong></div>
                <div><span>Net flow bias</span><strong>{flow.money_flow_summary.net_flow_bias?.replace(/_/g, " ") || "Unavailable"}</strong></div>
                <div><span>RVOL basis</span><strong>{flow.money_flow_summary.rvol_time_label || "Unavailable"}</strong></div>
                <div><span>Institutional flow</span><strong>{flow.money_flow_summary.institutional_flow?.status || "UNAVAILABLE"}</strong></div>
              </div>
              <p className="dashboard-disclaimer">{flow.metadata?.disclaimer || "Close-location bias is derived from OHLCV and is not actual buyer/seller order flow. Institutional flow requires exchange settlement data."}</p>
            </>
          ) : <EmptyState reason={errors["Money flow"] || (loading ? "Loading money flow…" : "Money flow summary is unavailable.")} />}
        </article>
        <article className="panel">
          <div className="panel-heading"><div><h3>Recent alerts</h3><p>Latest server-recorded alert events</p></div><button className="text-action" onClick={() => onNavigate("Alerts")}>All alerts</button></div>
          {alerts.length ? <div className="dashboard-alert-list">
            {alerts.map((alert) => <button key={alert.id} onClick={() => onSelectStock(alert.symbol)}>
              <span><strong>{alert.symbol}</strong><small>{alert.message || alert.alert_type}</small></span><time>{alert.timestamp}</time>
            </button>)}
          </div> : <EmptyState reason={errors["Recent alerts"] || (loading ? "Loading alerts…" : "No alert events have been recorded.")} />}
        </article>
      </section>
      <footer className="page-footer"><span>STOCK INTELLIGENCE PRO</span><span>Market status is not inferred from historical prices · Historical data is not LIVE.</span></footer>
    </div>
  );
}

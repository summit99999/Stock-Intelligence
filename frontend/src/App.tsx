import { useEffect, useMemo, useState } from "react";
import "./style.css";
import StockScreener from "./components/StockScreener";
import CompanyResearch from "./components/CompanyResearch";
import MarketOverview from "./components/MarketOverview";
import MarketMoversConfluenceView from "./components/MarketMoversConfluenceView";
import TechnicalAnalysisView from "./components/TechnicalAnalysisView";
import VolumeAnalyticsView from "./components/VolumeAnalyticsView";
import FootprintOrderFlowView from "./components/FootprintOrderFlowView";
import AIMentorView from "./components/AIMentorView";
import TradePlannerView from "./components/TradePlannerView";
import WatchlistView from "./components/WatchlistView";
import AlertsView from "./components/AlertsView";
import SettingsView from "./components/SettingsView";
import MarketXRayView from "./components/MarketXRayView";
import OrderBlockBoardView from "./components/OrderBlockBoardView";
import SmartMoneyConceptsView from "./components/SmartMoneyConceptsView";
import SMCBacktestView from "./components/SMCBacktestView";
import MarketScannerView from "./components/MarketScannerView";
import SetupBoardView from "./components/SetupBoardView";
import MoneyFlowIntelligenceView from "./components/MoneyFlowIntelligenceView";
import UnifiedResearchDashboardView from "./components/UnifiedResearchDashboardView";
import DashboardHome from "./components/DashboardHome";
import IntradayDataHealthView from "./components/IntradayDataHealthView";
import { isAuthEnabled } from "./api/config";
import { getCurrentSession, subscribeAuthState, signOutUser } from "./api/supabaseClient";
import AuthGateway from "./components/AuthGateway";
import type { Session } from "@supabase/supabase-js";
import {
  fetchLiveFeedStatus,
  fetchLiveQuotes,
  refreshLiveQuotes,
  reconnectLiveFeed,
  subscribeMarketFeed,
  LiveFeedStatus,
  LiveQuote,
} from "./api/marketFeed";

const defaultIndices = [
  { name: "NIFTY 50", value: "24,850.50", change: "+0.72%", positive: true, points: "0,36 15,31 30,34 45,20 60,25 75,13 90,17 105,5" },
  { name: "BANK NIFTY", value: "56,240.20", change: "+0.45%", positive: true, points: "0,32 15,25 30,29 45,16 60,22 75,10 90,15 105,8" },
  { name: "SENSEX", value: "81,450.30", change: "-0.18%", positive: false, points: "0,8 15,13 30,9 45,23 60,17 75,30 90,25 105,37" },
  { name: "INDIA VIX", value: "14.25", change: "-2.15%", positive: false, points: "0,5 15,12 30,9 45,22 60,18 75,30 90,28 105,38" },
];

const sectors = [
  { name: "IT", change: 1.85 },
  { name: "BANKING", change: 1.12 },
  { name: "AUTO", change: 0.94 },
  { name: "PHARMA", change: 0.63 },
  { name: "FMCG", change: 0.28 },
  { name: "METAL", change: -0.42 },
  { name: "REALTY", change: -0.85 },
  { name: "ENERGY", change: -1.14 },
];

const defaultMovers = [
  { symbol: "TRENT", name: "Trent Limited", price: "6,245.00", change: 4.82, volume: "12.5L" },
  { symbol: "BEL", name: "Bharat Electronics", price: "312.40", change: 3.65, volume: "84.2L" },
  { symbol: "HAL", name: "Hindustan Aeronautics", price: "4,120.00", change: 2.91, volume: "18.4L" },
  { symbol: "TMPV", name: "Tata Motors PV", price: "292.30", change: -2.35, volume: "46.1L" },
  { symbol: "ONGC", name: "Oil & Natural Gas Corp.", price: "268.10", change: -1.82, volume: "32.8L" },
];

const defaultWatchlist = [
  { symbol: "RELIANCE", name: "Reliance Industries", price: "1,420.50", change: 1.25 },
  { symbol: "TCS", name: "Tata Consultancy Services", price: "3,450.00", change: -0.65 },
  { symbol: "INFY", name: "Infosys Limited", price: "1,520.80", change: 1.82 },
  { symbol: "ICICIBANK", name: "ICICI Bank", price: "1,285.40", change: 0.92 },
  { symbol: "SUNPHARMA", name: "Sun Pharmaceutical", price: "1,735.00", change: -0.35 },
];

interface NavItemDef {
  name: string;
  icon: string;
  section: string;
  tag?: string;
}

const navSections: { section: string; items: NavItemDef[] }[] = [
  {
    section: "MARKET",
    items: [
      { name: "Overview", icon: "▦", section: "MARKET" },
      { name: "Market Intelligence", icon: "◫", section: "MARKET" },
      { name: "Market Movers", icon: "⇅", section: "MARKET", tag: "NEW" },
      { name: "Stock Scanner", icon: "⌕", section: "MARKET" },
      { name: "Money Flow Intelligence", icon: "↗", section: "MARKET", tag: "FLOW" },
      { name: "Sector Rotation", icon: "◌", section: "MARKET" },
    ],
  },
  {
    section: "RESEARCH",
    items: [
      { name: "Advanced Charts", icon: "⌁", section: "RESEARCH", tag: "PRO" },
      { name: "Intraday Data Health", icon: "◉", section: "RESEARCH" },
      { name: "Fundamental Analysis", icon: "▤", section: "RESEARCH" },
      { name: "SMC Analysis", icon: "⌗", section: "RESEARCH", tag: "SMC" },
      { name: "Backtesting", icon: "◷", section: "RESEARCH" },
    ],
  },
  {
    section: "WORKSPACE",
    items: [
      { name: "Watchlists", icon: "☆", section: "WORKSPACE" },
      { name: "Alerts", icon: "♧", section: "WORKSPACE" },
      { name: "Settings", icon: "⚙", section: "WORKSPACE" },
    ],
  },
];

function Sparkline({ points, positive }: { points: string; positive: boolean }) {
  return (
    <svg viewBox="0 0 110 44" className="sparkline" preserveAspectRatio="none">
      <polyline
        points={points}
        fill="none"
        stroke={positive ? "#26c78b" : "#ef6676"}
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function App() {
  const [activePage, setActivePage] = useState("Overview");
  const [currentSymbol, setCurrentSymbol] = useState("RELIANCE");
  const [search, setSearch] = useState("");
  const [period, setPeriod] = useState("1D");

  const [session, setSession] = useState<Session | null>(null);
  const [authLoading, setAuthLoading] = useState<boolean>(isAuthEnabled);

  const [liveQuotes, setLiveQuotes] = useState<Record<string, LiveQuote>>({});
  const [feedStatus, setFeedStatus] = useState<LiveFeedStatus | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    if (isAuthEnabled) {
      getCurrentSession().then((sess) => {
        setSession(sess);
        setAuthLoading(false);
      });
      const subscription = subscribeAuthState((newSess) => {
        setSession(newSess);
        setAuthLoading(false);
      });
      return () => {
        subscription?.unsubscribe();
      };
    } else {
      setAuthLoading(false);
    }
  }, []);

  useEffect(() => {
    // Initial fetch of feed status and quotes
    fetchLiveFeedStatus().then(setFeedStatus).catch(() => {});
    fetchLiveQuotes()
      .then((res) => {
        if (res.quotes) setLiveQuotes(res.quotes);
      })
      .catch(() => {});

    // Subscribe to live WebSocket feed
    const unsubscribe = subscribeMarketFeed({
      onTick: (quote) => {
        setLiveQuotes((prev) => ({ ...prev, [quote.symbol]: quote }));
      },
      onSnapshot: (quotes, status) => {
        setLiveQuotes((prev) => ({ ...prev, ...quotes }));
        if (status) setFeedStatus(status);
      },
      onStatusChange: (status) => {
        setFeedStatus(status);
      },
    });

    return () => {
      unsubscribe();
    };
  }, []);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      const res = await refreshLiveQuotes();
      if (res.quotes) {
        setLiveQuotes((prev) => ({ ...prev, ...res.quotes }));
      }
      const st = await fetchLiveFeedStatus();
      setFeedStatus(st);
    } catch (e) {
      console.error("Refresh failed:", e);
    } finally {
      setIsRefreshing(false);
    }
  };

  const isLiveConnected = feedStatus?.status === "CONNECTED";
  const isRateLimited = feedStatus?.status === "RATE_LIMITED";
  const isDisabled = feedStatus?.status === "DISABLED";
  const hasLiveQuotes = Object.values(liveQuotes).some((q) => q.source === "LIVE");

  const displayIndices = useMemo(() => {
    return defaultIndices.map((base) => {
      const q = liveQuotes[base.name] || liveQuotes[base.name.replace(" 50", "")];
      if (q) {
        const positive = (q.change ?? 0) >= 0;
        const formattedVal = q.ltp.toLocaleString("en-IN", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        });
        const changeStr = `${positive ? "+" : ""}${(q.change_percent ?? 0).toFixed(2)}%`;
        return {
          ...base,
          value: formattedVal,
          change: changeStr,
          positive,
          source: q.source,
        };
      }
      return { ...base, source: "DEMO" };
    });
  }, [liveQuotes]);

  const displayWatchlist = useMemo(() => {
    return defaultWatchlist.map((item) => {
      const q = liveQuotes[item.symbol];
      if (q) {
        return {
          ...item,
          price: q.ltp.toLocaleString("en-IN", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          }),
          change: q.change_percent ?? item.change,
          source: q.source,
        };
      }
      return { ...item, source: "DEMO" };
    });
  }, [liveQuotes]);

  const filteredWatchlist = useMemo(
    () =>
      displayWatchlist.filter(
        (stock) =>
          stock.symbol.toLowerCase().includes(search.toLowerCase()) ||
          stock.name.toLowerCase().includes(search.toLowerCase())
      ),
    [displayWatchlist, search]
  );

  const displayMovers = useMemo(() => {
    return defaultMovers.map((item) => {
      const q = liveQuotes[item.symbol];
      if (q) {
        return {
          ...item,
          price: q.ltp.toLocaleString("en-IN", {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
          }),
          change: q.change_percent ?? item.change,
          volume: q.volume ? `${(q.volume / 100000).toFixed(1)}L` : item.volume,
          source: q.source,
        };
      }
      return { ...item, source: "DEMO" };
    });
  }, [liveQuotes]);

  const handleOpenChart = (sym: string) => {
    setCurrentSymbol(sym);
    setActivePage("Advanced Charts");
  };

  const handleOpenResearch = (sym: string) => {
    setCurrentSymbol(sym);
    setActivePage("Fundamental Analysis");
  };

  const handleOpenPlanner = (sym: string) => {
    setCurrentSymbol(sym);
    setActivePage("Trade Planner");
  };

  if (authLoading) {
    return (
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          minHeight: "100vh",
          background: "#080c14",
          color: "#60a5fa",
          fontSize: "14px",
          fontWeight: 600,
          fontFamily: "'Inter', sans-serif",
        }}
      >
        Initializing Stock Intelligence Pro Session...
      </div>
    );
  }

  if (isAuthEnabled && !session) {
    return <AuthGateway onSuccess={() => setAuthLoading(false)} />;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">S</div>
          <div>
            <h2>Stock Intelligence</h2>
            <span>PRO TERMINAL</span>
          </div>
        </div>

        <nav>
          {navSections.map((sec) => (
            <div key={sec.section} style={{ display: "grid", gap: "2px", marginBottom: "6px" }}>
              <div className="nav-label">{sec.section}</div>
              {sec.items.map((item) => (
                <button
                  key={item.name}
                  className={`nav-item ${activePage === item.name ? "active" : ""}`}
                  onClick={() => setActivePage(item.name)}
                >
                  <span className="nav-icon">{item.icon}</span>
                  {item.name}
                  {item.tag && <span className="nav-tag">{item.tag}</span>}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <nav className="mobile-nav" aria-label="Primary navigation">
          {navSections.flatMap((section) => section.items).map((item) => (
            <button
              key={item.name}
              className={`nav-item ${activePage === item.name ? "active" : ""}`}
              onClick={() => setActivePage(item.name)}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.name}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="data-status">
            <span
              className={`status-dot ${
                isLiveConnected
                  ? "live"
                  : isRateLimited
                  ? "rate-limited"
                  : isDisabled
                  ? "disabled"
                  : "demo"
              }`}
            />
            <div>
              <strong>
                {isLiveConnected
                  ? "Upstox Live Feed"
                  : isRateLimited
                  ? "Rate Limited (HTTP 429)"
                  : isDisabled
                  ? "Live Feed Disabled"
                  : "yfinance / Demo Mode"}
              </strong>
              <small>
                {isLiveConnected
                  ? "Active WebSocket · Live streaming"
                  : isRateLimited
                  ? "Data API inactive / Cooldown"
                  : isDisabled
                  ? "UPSTOX_LIVE_DATA_ENABLED=false"
                  : "Historical & offline fallback"}
              </small>
            </div>
          </div>
          <div className="sidebar-footer">STOCK INTELLIGENCE PRO v2.0</div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <div className="breadcrumb">WORKSPACE / <strong>{activePage.toUpperCase()}</strong></div>
            <h1>{activePage}</h1>
          </div>
          <div className="topbar-right">
            <form
              className="topbar-search"
              onSubmit={(event) => {
                event.preventDefault();
                const symbol = search.trim().toUpperCase();
                if (symbol) handleOpenChart(symbol);
              }}
            >
              <span aria-hidden="true">⌕</span>
              <input
                aria-label="Search stocks"
                placeholder="Search stocks"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
              <kbd>↵</kbd>
            </form>
            {(isRateLimited || isDisabled) && (
              <button
                className="refresh-action-btn"
                onClick={async () => {
                  setIsRefreshing(true);
                  try {
                    const st = await reconnectLiveFeed(true);
                    setFeedStatus(st);
                  } catch (e) {
                    console.error("Manual reconnect failed:", e);
                  } finally {
                    setIsRefreshing(false);
                  }
                }}
                disabled={isRefreshing}
                title="Manually retry Upstox WebSocket connection"
                style={{ borderColor: isRateLimited ? "#ef6676" : "#4a5568", color: isRateLimited ? "#ef6676" : "#a0aec0" }}
              >
                {isRefreshing ? "Connecting..." : "⚡ Reconnect Feed"}
              </button>
            )}
            <button
              className="refresh-action-btn"
              onClick={handleRefresh}
              disabled={isRefreshing}
              title="Trigger immediate snapshot refresh from API"
            >
              {isRefreshing ? "↻ Refreshing..." : "↻ Refresh Feed"}
            </button>
            <span
              className={`market-status ${
                isLiveConnected
                  ? "live"
                  : isRateLimited
                  ? "rate-limited"
                  : isDisabled
                  ? "disabled"
                  : "demo"
              }`}
            >
              <span
                className={`status-dot ${
                  isLiveConnected
                    ? "live"
                    : isRateLimited
                    ? "rate-limited"
                    : isDisabled
                    ? "disabled"
                    : "demo"
                }`}
              />
              {isLiveConnected
                ? "LIVE FEED (UPSTOX)"
                : isRateLimited
                ? "RATE LIMITED"
                : isDisabled
                ? "FEED DISABLED"
                : "DEMO MODE"}
            </span>
            {session && (
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "11px", color: "#94a3b8", background: "#131c2a", padding: "4px 8px", borderRadius: "6px", border: "1px solid #1e2c40" }}>
                  👤 {session.user?.email}
                </span>
                <button
                  onClick={() => signOutUser()}
                  style={{
                    background: "rgba(239, 68, 68, 0.15)",
                    color: "#f87171",
                    border: "1px solid rgba(239, 68, 68, 0.3)",
                    borderRadius: "6px",
                    padding: "4px 8px",
                    fontSize: "11px",
                    cursor: "pointer",
                    fontWeight: 600,
                  }}
                  title="Sign out of Stock Intelligence Pro"
                >
                  Sign Out
                </button>
              </div>
            )}
            <button className="topbar-icon-button" aria-label="Open alerts" onClick={() => setActivePage("Alerts")}>♧</button>
            <button className="profile-avatar" aria-label="Open settings" onClick={() => setActivePage("Settings")}>SI</button>
          </div>
        </header>

        {activePage === "Overview" && (
          <DashboardHome
            onSelectStock={handleOpenChart}
            onNavigate={setActivePage}
            liveQuotes={liveQuotes}
          />
        )}

        {activePage === "Intraday Data Health" && <IntradayDataHealthView />}

        {(activePage === "Market Intelligence" || activePage === "Sector Rotation") && (
          <MarketOverview
            onSelectStock={(sym, page) => {
              setCurrentSymbol(sym);
              setActivePage(page === "Company Research" ? "Fundamental Analysis" : "Advanced Charts");
            }}
            liveQuotes={liveQuotes}
          />
        )}

        {activePage === "Market Movers" && (
          <MarketMoversConfluenceView
            onSelectStock={(sym, page) => {
              setCurrentSymbol(sym);
              setActivePage(page === "Company Research" ? "Fundamental Analysis" : "Advanced Charts");
            }}
          />
        )}

        {activePage === "Stock Scanner" && (
          <MarketScannerView onSelectStock={handleOpenChart} />
        )}

        {activePage === "Advanced Charts" && (
          <TechnicalAnalysisView
            symbol={currentSymbol}
            onSymbolChange={setCurrentSymbol}
            onNavigateToResearch={handleOpenResearch}
            onNavigateToPlanner={handleOpenPlanner}
          />
        )}

        {activePage === "Fundamental Analysis" && (
          <CompanyResearch initialSymbol={currentSymbol} onSelectStock={setCurrentSymbol} />
        )}

        {activePage === "SMC Analysis" && (
          <SmartMoneyConceptsView
            symbol={currentSymbol}
            onSymbolChange={setCurrentSymbol}
            onNavigate={setActivePage}
          />
        )}

        {activePage === "Backtesting" && (
          <SMCBacktestView
            symbol={currentSymbol}
            onSymbolChange={setCurrentSymbol}
            onNavigate={setActivePage}
          />
        )}

        {activePage === "Watchlists" && (
          <WatchlistView onSelectSymbol={setCurrentSymbol} onNavigate={setActivePage} liveQuotes={liveQuotes} />
        )}

        {/* 1. Dashboard View */}
        {activePage === "Dashboard" && false && (
          <>
            <section className="welcome-row">
              <div>
                <h2>Market at a glance</h2>
                <p>Indian equity market overview and key market indicators.</p>
              </div>
              <div className="period-selector">
                {["1D", "1W", "1M", "3M"].map((p) => (
                  <button
                    key={p}
                    className={period === p ? "selected" : ""}
                    onClick={() => setPeriod(p)}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </section>

            <div className={`notice ${isLiveConnected || hasLiveQuotes ? "live-notice" : ""}`}>
              <span>ⓘ</span>
              {isLiveConnected || hasLiveQuotes
                ? "LIVE MARKET FEED — Prices and index quotes streamed from DhanHQ API."
                : "DEMONSTRATION & HISTORICAL DATA — Figures are illustrative and are not current exchange prices."}
            </div>

            <section className="index-grid">
              {displayIndices.map((index) => (
                <article className="index-card" key={index.name}>
                  <div className="card-top">
                    <span>{index.name}</span>
                    <span className={index.source === "LIVE" ? "badge-live" : "badge-demo"}>
                      {index.source}
                    </span>
                  </div>
                  <div className="index-value">{index.value}</div>
                  <div className="index-bottom">
                    <span className={index.positive ? "positive" : "negative"}>
                      {index.change}
                    </span>
                    <Sparkline points={index.points} positive={index.positive} />
                  </div>
                </article>
              ))}
            </section>

            <section className="content-grid">
              <article className="panel breadth-panel">
                <div className="panel-heading">
                  <div>
                    <h3>Market breadth</h3>
                    <p>Advance / decline distribution</p>
                  </div>
                  <span className="panel-menu">···</span>
                </div>
                <div className="breadth-numbers">
                  <div><strong className="positive">32</strong><span>Advances</span></div>
                  <div><strong className="negative">18</strong><span>Declines</span></div>
                  <div><strong>0</strong><span>Unchanged</span></div>
                </div>
                <div className="breadth-bar">
                  <span className="advance-bar" />
                  <span className="decline-bar" />
                </div>
                <div className="breadth-legend">
                  <span><i className="green-dot" /> Advancing stocks</span>
                  <span><i className="red-dot" /> Declining stocks</span>
                </div>
              </article>

              <article className="panel sector-panel">
                <div className="panel-heading">
                  <div>
                    <h3>Sector performance</h3>
                    <p>Daily sector rotation index</p>
                  </div>
                  <span className="panel-menu">···</span>
                </div>
                <div className="sector-list">
                  {sectors.map((sector) => (
                    <div className="sector-row" key={sector.name}>
                      <span>{sector.name}</span>
                      <div className="sector-track">
                        <span
                          className={sector.change >= 0 ? "sector-positive" : "sector-negative"}
                          style={{ width: `${Math.max(12, Math.abs(sector.change) / 2 * 100)}%` }}
                        />
                      </div>
                      <strong className={sector.change >= 0 ? "positive" : "negative"}>
                        {sector.change > 0 ? "+" : ""}{sector.change.toFixed(2)}%
                      </strong>
                    </div>
                  ))}
                </div>
              </article>
            </section>

            <section className="content-grid lower-grid">
              <article className="panel movers-panel">
                <div className="panel-heading">
                  <div>
                    <h3>Market movers</h3>
                    <p>Selected stocks · Real-time and illustrative prices</p>
                  </div>
                  <span className={hasLiveQuotes ? "badge-live" : "table-label"}>
                    {hasLiveQuotes ? "LIVE STREAM" : "SAMPLE"}
                  </span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>STOCK</th>
                        <th>PRICE (₹)</th>
                        <th>CHANGE</th>
                        <th>VOLUME</th>
                        <th>STATUS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {displayMovers.map((stock) => (
                        <tr
                          key={stock.symbol}
                          style={{ cursor: "pointer" }}
                          onClick={() => handleOpenChart(stock.symbol)}
                          title="Click to view full Technical Chart"
                        >
                          <td><strong>{stock.symbol}</strong><small>{stock.name}</small></td>
                          <td>{stock.price}</td>
                          <td className={stock.change >= 0 ? "positive" : "negative"}>
                            {stock.change > 0 ? "+" : ""}{stock.change.toFixed(2)}%
                          </td>
                          <td>{stock.volume}</td>
                          <td>
                            <span className={stock.source === "LIVE" ? "badge-live" : "badge-demo"}>
                              {stock.source}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>

              <article className="panel watchlist-panel">
                <div className="panel-heading">
                  <div>
                    <h3>Quick Watchlist</h3>
                    <p>Featured stocks to monitor</p>
                  </div>
                  <span className="watch-count">{filteredWatchlist.length} STOCKS</span>
                </div>
                <input
                  className="watch-search"
                  placeholder="Search quick watchlist..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <div className="watch-items">
                  {filteredWatchlist.map((stock) => (
                    <div
                      className="watch-item"
                      key={stock.symbol}
                      style={{ cursor: "pointer" }}
                      onClick={() => handleOpenChart(stock.symbol)}
                      title="Click to view full Technical Chart"
                    >
                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <strong>{stock.symbol}</strong>
                          <span className={stock.source === "LIVE" ? "badge-live" : "badge-demo"}>
                            {stock.source}
                          </span>
                        </div>
                        <small>{stock.name}</small>
                      </div>
                      <div className="watch-price">
                        <strong>₹{stock.price}</strong>
                        <small className={stock.change >= 0 ? "positive" : "negative"}>
                          {stock.change > 0 ? "+" : ""}{stock.change.toFixed(2)}%
                        </small>
                      </div>
                    </div>
                  ))}
                  {filteredWatchlist.length === 0 && (
                    <p className="empty-state">No matching stocks found.</p>
                  )}
                </div>
              </article>
            </section>

            <footer className="page-footer">
              <span>STOCK INTELLIGENCE PRO</span>
              <span>
                {isLiveConnected
                  ? "Connected to Upstox Live Market Feed (v2)"
                  : "yfinance historical engine · Zero-cost research mode"}
              </span>
            </footer>
          </>
        )}

        {/* Unified Research & Decision Engine (Phase 12) */}
        {activePage === "Unified Research" && (
          <UnifiedResearchDashboardView
            onSelectStock={(sym) => {
              setCurrentSymbol(sym);
            }}
          />
        )}

        {/* 2. Market Overview */}
        {activePage === "Market Overview" && (
          <MarketOverview
            onSelectStock={(sym, pg) => {
              setCurrentSymbol(sym);
              if (pg === "Company Research") {
                setActivePage("Fundamental Research");
              } else {
                setActivePage("Technical Analysis");
              }
            }}
            liveQuotes={liveQuotes}
          />
        )}

        {/* 2b. Market Movers & Confluence Intelligence (Phase 14) */}
        {activePage === "Market Movers" && (
          <MarketMoversConfluenceView
            onSelectStock={(sym, pg) => {
              setCurrentSymbol(sym);
              if (pg === "Company Research") {
                setActivePage("Fundamental Analysis");
              } else {
                setActivePage("Advanced Charts");
              }
            }}
          />
        )}

        {/* 2b. Money Flow & Daily Volume Intelligence */}
        {activePage === "Money Flow Intelligence" && (
          <MoneyFlowIntelligenceView
            onSelectStock={(sym) => {
              setCurrentSymbol(sym);
              setActivePage("Technical Charts");
            }}
            liveQuotes={liveQuotes}
            initialSymbol={currentSymbol}
          />
        )}

        {/* 3. Market Scanner (VolumeLens-Inspired) */}
        {activePage === "Market Scanner" && (
          <MarketScannerView
            onSelectStock={(sym) => {
              setCurrentSymbol(sym);
              setActivePage("Technical Charts");
            }}
          />
        )}

        {/* 3b. Legacy Screener */}
        {activePage === "Legacy Stock Scanner" && (
          <StockScreener
            onOpenResearch={handleOpenResearch}
          />
        )}

        {/* 3c. Bullish Setups */}
        {activePage === "Bullish Setups" && (
          <SetupBoardView
            initialDirection="BULLISH"
            onSelectStock={(sym) => {
              setCurrentSymbol(sym);
              setActivePage("Technical Charts");
            }}
          />
        )}

        {/* 3d. Bearish Setups */}
        {activePage === "Bearish Setups" && (
          <SetupBoardView
            initialDirection="BEARISH"
            onSelectStock={(sym) => {
              setCurrentSymbol(sym);
              setActivePage("Technical Charts");
            }}
          />
        )}

        {/* 3e. Consolidation */}
        {activePage === "Consolidation" && (
          <SetupBoardView
            initialDirection="CONSOLIDATION"
            onSelectStock={(sym) => {
              setCurrentSymbol(sym);
              setActivePage("Technical Charts");
            }}
          />
        )}

        {/* 4. Technical Analysis / Technical Charts */}
        {(activePage === "Technical Analysis" || activePage === "Technical Charts") && (
          <TechnicalAnalysisView
            symbol={currentSymbol}
            onSymbolChange={setCurrentSymbol}
            onNavigateToResearch={handleOpenResearch}
            onNavigateToPlanner={handleOpenPlanner}
          />
        )}

        {/* 5. Volume Analytics */}
        {activePage === "Volume Analytics" && (
          <VolumeAnalyticsView
            symbol={currentSymbol}
            onSymbolChange={setCurrentSymbol}
          />
        )}

        {/* 6. Footprint & Order Flow */}
        {activePage === "Footprint & Order Flow" && (
          <FootprintOrderFlowView
            symbol={currentSymbol}
            onSymbolChange={setCurrentSymbol}
          />
        )}

        {/* 7. Fundamental Research */}
        {activePage === "Fundamental Research" && (
          <CompanyResearch
            initialSymbol={currentSymbol}
            onSelectStock={setCurrentSymbol}
          />
        )}

        {/* 8. AI Mentor */}
        {activePage === "AI Mentor" && (
          <AIMentorView
            symbol={currentSymbol}
            onSymbolChange={setCurrentSymbol}
          />
        )}

        {/* 9. Trade Planner */}
        {activePage === "Trade Planner" && (
          <TradePlannerView
            symbol={currentSymbol}
            onSymbolChange={setCurrentSymbol}
          />
        )}

        {/* 10. Watchlist */}
        {activePage === "Watchlist" && (
          <WatchlistView
            onSelectSymbol={setCurrentSymbol}
            onNavigate={setActivePage}
            liveQuotes={liveQuotes}
          />
        )}

        {/* 11. Alerts */}
        {activePage === "Alerts" && (
          <AlertsView
            onSelectSymbol={setCurrentSymbol}
            onNavigate={setActivePage}
            liveQuotes={liveQuotes}
          />
        )}

        {/* 12. Settings */}
        {activePage === "Settings" && (
          <SettingsView
            onNavigate={setActivePage}
          />
        )}

        {/* 13. Market X-Ray */}
        {activePage === "Market X-Ray" && (
          <MarketXRayView
            onSelectSymbol={(sym) => setCurrentSymbol(sym)}
            onNavigate={setActivePage}
          />
        )}

        {/* 14. Order Block Board */}
        {(activePage === "Order Block Board" || activePage === "Order Blocks") && (
          <OrderBlockBoardView
            onSelectSymbol={(sym) => setCurrentSymbol(sym)}
            onNavigate={setActivePage}
          />
        )}

        {/* 15. Smart Money Concepts */}
        {activePage === "Smart Money Concepts" && (
          <SmartMoneyConceptsView
            symbol={currentSymbol}
            onSymbolChange={setCurrentSymbol}
            onNavigate={setActivePage}
          />
        )}

        {/* 16. SMC Backtest */}
        {(activePage === "SMC Backtest" || activePage === "Backtesting") && (
          <SMCBacktestView
            symbol={currentSymbol}
            onSymbolChange={setCurrentSymbol}
            onNavigate={setActivePage}
          />
        )}
      </main>
    </div>
  );
}

export default App;

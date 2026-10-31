
import { useMemo, useState } from "react";
import "./style.css";
import StockScreener from "./components/StockScreener";

const indices = [
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

const movers = [
  { symbol: "TRENT", name: "Trent Limited", price: "6,245.00", change: 4.82, volume: "12.5L" },
  { symbol: "BEL", name: "Bharat Electronics", price: "312.40", change: 3.65, volume: "84.2L" },
  { symbol: "HAL", name: "Hindustan Aeronautics", price: "4,120.00", change: 2.91, volume: "18.4L" },
  { symbol: "TATAMOTORS", name: "Tata Motors", price: "725.30", change: -2.35, volume: "46.1L" },
  { symbol: "ONGC", name: "Oil & Natural Gas Corp.", price: "268.10", change: -1.82, volume: "32.8L" },
];

const watchlist = [
  { symbol: "RELIANCE", name: "Reliance Industries", price: "1,420.50", change: 1.25 },
  { symbol: "TCS", name: "Tata Consultancy Services", price: "3,450.00", change: -0.65 },
  { symbol: "INFY", name: "Infosys Limited", price: "1,520.80", change: 1.82 },
  { symbol: "ICICIBANK", name: "ICICI Bank", price: "1,285.40", change: 0.92 },
  { symbol: "SUNPHARMA", name: "Sun Pharmaceutical", price: "1,735.00", change: -0.35 },
];

const navigation = [
  { name: "Dashboard", icon: "▦" },
  { name: "Stock Screener", icon: "⌕" },
  { name: "Market Overview", icon: "◫" },
  { name: "Charts & Analysis", icon: "⌁" },
  { name: "My Watchlist", icon: "☆" },
  { name: "Backtesting", icon: "◷" },
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
  const [activePage, setActivePage] = useState("Dashboard");
  const [search, setSearch] = useState("");
  const [period, setPeriod] = useState("1D");

  const filteredWatchlist = useMemo(
    () =>
      watchlist.filter(
        (stock) =>
          stock.symbol.toLowerCase().includes(search.toLowerCase()) ||
          stock.name.toLowerCase().includes(search.toLowerCase())
      ),
    [search]
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">S</div>
          <div>
            <h2>Stock Intelligence</h2>
            <span>MARKET TERMINAL</span>
          </div>
        </div>

        <div className="nav-label">WORKSPACE</div>
        <nav>
          {navigation.map((item) => (
            <button
              key={item.name}
              className={`nav-item ${activePage === item.name ? "active" : ""}`}
              onClick={() => setActivePage(item.name)}
            >
              <span className="nav-icon">{item.icon}</span>
              {item.name}
              {item.name === "Stock Screener" && <span className="nav-tag">NEW</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="data-status">
            <span className="status-dot" />
            <div>
              <strong>Demo environment</strong>
              <small>Sample data · Not live</small>
            </div>
          </div>
          <div className="sidebar-footer">STOCK INTELLIGENCE v1.0</div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div>
            <div className="breadcrumb">WORKSPACE / <strong>{activePage.toUpperCase()}</strong></div>
            <h1>{activePage}</h1>
          </div>
          <div className="topbar-right">
            <span className="market-status"><span className="status-dot" /> DEMO MODE</span>
            <div className="profile-avatar">SI</div>
          </div>
        </header>

        {activePage === "Dashboard" ? (
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

            <div className="notice">
              <span>ⓘ</span>
              DEMONSTRATION DATA — Figures are illustrative and are not current exchange prices.
            </div>

            <section className="index-grid">
              {indices.map((index) => (
                <article className="index-card" key={index.name}>
                  <div className="card-top">
                    <span>{index.name}</span>
                    <span className="card-menu">···</span>
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
                    <p>Illustrative advance / decline distribution</p>
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
                    <p>Illustrative percentage change</p>
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
                    <p>Selected stocks · Illustrative prices</p>
                  </div>
                  <span className="table-label">SAMPLE</span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr><th>STOCK</th><th>PRICE (₹)</th><th>CHANGE</th><th>VOLUME</th></tr>
                    </thead>
                    <tbody>
                      {movers.map((stock) => (
                        <tr key={stock.symbol}>
                          <td><strong>{stock.symbol}</strong><small>{stock.name}</small></td>
                          <td>{stock.price}</td>
                          <td className={stock.change >= 0 ? "positive" : "negative"}>
                            {stock.change > 0 ? "+" : ""}{stock.change.toFixed(2)}%
                          </td>
                          <td>{stock.volume}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>

              <article className="panel watchlist-panel">
                <div className="panel-heading">
                  <div>
                    <h3>My watchlist</h3>
                    <p>Stocks to keep an eye on</p>
                  </div>
                  <span className="watch-count">{filteredWatchlist.length} STOCKS</span>
                </div>
                <input
                  className="watch-search"
                  placeholder="Search your watchlist..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
                <div className="watch-items">
                  {filteredWatchlist.map((stock) => (
                    <div className="watch-item" key={stock.symbol}>
                      <div><strong>{stock.symbol}</strong><small>{stock.name}</small></div>
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
              <span>STOCK INTELLIGENCE</span>
              <span>Illustrative dashboard · No live market connection</span>
            </footer>
          </>
        ) : activePage === "Stock Screener" ? (
          <StockScreener />
        ) : (
          <section className="coming-soon">
            <div className="coming-icon">⌁</div>
            <h2>{activePage}</h2>
            <p>This module is planned for the next development phase.</p>
            <button onClick={() => setActivePage("Dashboard")}>Back to Dashboard</button>
          </section>
        )}
      </main>
    </div>
  );
}

export default App;

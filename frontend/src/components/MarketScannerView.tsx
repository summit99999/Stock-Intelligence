import { apiFetch } from "../api/client";
import React, { useEffect, useState, useMemo } from "react";

interface SetupRecord {
  id: string;
  symbol: string;
  setup_type: string;
  direction: string;
  timeframe: string;
  entry_zone: { min: number; max: number; ideal_entry: number };
  stop_loss: number;
  target_1: number;
  target_2: number;
  confidence_score: number;
  confluence_factors: string[];
  summary: string;
}

interface ScannedStock {
  rank?: number;
  rank_score?: number;
  rank_reason?: string;
  symbol: string;
  company_name: string;
  sector: string;
  close: number;
  daily_change_pct: number;
  relative_volume: number;
  rsi: number;
  supertrend_dir: string;
  ema_20?: number | null;
  ema_50?: number | null;
  ema_200?: number | null;
  volume_spike?: boolean;
  is_consolidating?: boolean;
  consolidation_range_pct?: number | null;
  is_breakout?: boolean;
  breakout_type?: string;
  has_fresh_ob?: boolean;
  has_fvg?: boolean;
  structure_trend?: string;
  pe?: number | null;
  roe?: number | null;
  roce?: number | null;
  debt_equity?: number | null;
  profit_growth_pct?: number | null;
  opm_pct?: number | null;
  setup_count?: number;
  top_setup?: SetupRecord;
}

interface ScannerData {
  timestamp: string;
  universe: string;
  universe_label?: string;
  scanned_count?: number;
  configured_universe_count?: number;
  coverage_pct?: number;
  total_records: number;
  page: number;
  page_size: number;
  total_pages: number;
  ranking_preset?: string;
  items: ScannedStock[];
  metadata?: any;
}

interface SavedScannerRecord {
  id: number;
  name: string;
  description: string;
  universe: string;
  logic_mode: string;
  conditions: any;
  created_at: string;
}

interface WatchlistSummary {
  id: number;
  name: string;
  symbol_count: number;
}

interface MarketScannerViewProps {
  onSelectStock: (symbol: string, page?: string) => void;
  initialCategory?: string;
}

export default function MarketScannerView({
  onSelectStock,
  initialCategory = "BULLISH_OPPORTUNITY",
}: MarketScannerViewProps) {
  const [universe, setUniverse] = useState<string>("all");
  const [activePreset, setActivePreset] = useState<string>(initialCategory);
  const [search, setSearch] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [scannerData, setScannerData] = useState<ScannerData | null>(null);
  const [sortField, setSortField] = useState<string>("rank_score");
  const [sortAsc, setSortAsc] = useState<boolean>(false);
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);

  // Advanced Filter Drawer State
  const [showFilters, setShowFilters] = useState<boolean>(false);
  const [logicMode, setLogicMode] = useState<"AND" | "OR">("AND");
  const [filterPriceAboveEma20, setFilterPriceAboveEma20] = useState<boolean>(false);
  const [filterPriceAboveEma50, setFilterPriceAboveEma50] = useState<boolean>(false);
  const [filterPriceAboveEma200, setFilterPriceAboveEma200] = useState<boolean>(false);
  const [filterSupertrendUp, setFilterSupertrendUp] = useState<boolean>(false);
  const [filterMinRsi, setFilterMinRsi] = useState<string>("");
  const [filterMaxRsi, setFilterMaxRsi] = useState<string>("");
  const [filterMinRvol, setFilterMinRvol] = useState<string>("");
  const [filterBbSqueeze, setFilterBbSqueeze] = useState<boolean>(false);
  const [filterMacdBullish, setFilterMacdBullish] = useState<boolean>(false);
  const [filterMinRoe, setFilterMinRoe] = useState<string>("");
  const [filterMaxDebtEquity, setFilterMaxDebtEquity] = useState<string>("");
  const [filterMinProfitGrowth, setFilterMinProfitGrowth] = useState<string>("");
  const [filterFreshOrderBlock, setFilterFreshOrderBlock] = useState<boolean>(false);
  const [filterFairValueGap, setFilterFairValueGap] = useState<boolean>(false);
  const [filterBreakout, setFilterBreakout] = useState<boolean>(false);
  const [filterStructureTrend, setFilterStructureTrend] = useState<string>("");
  const [minimumSetupScore, setMinimumSetupScore] = useState<string>("");

  // Custom Saved Scanners Modal State
  const [showSavedModal, setShowSavedModal] = useState<boolean>(false);
  const [showSaveCurrentModal, setShowSaveCurrentModal] = useState<boolean>(false);
  const [customScannerName, setCustomScannerName] = useState<string>("");
  const [customScannerDesc, setCustomScannerDesc] = useState<string>("");
  const [savedScanners, setSavedScanners] = useState<SavedScannerRecord[]>([]);

  // Watchlists for "Add to Watchlist" action
  const [watchlists, setWatchlists] = useState<WatchlistSummary[]>([]);
  const [selectedStockForWl, setSelectedStockForWl] = useState<string | null>(null);
  const [showWlSelectModal, setShowWlSelectModal] = useState<boolean>(false);

  const presetsDef = [
    { key: "BULLISH_OPPORTUNITY", label: "Bullish Opportunity", icon: "▲", color: "#22c55e" },
    { key: "BEARISH_WEAKNESS", label: "Bearish Weakness", icon: "▼", color: "#ef4444" },
    { key: "BREAKOUT_CANDIDATES", label: "Breakout Candidates", icon: "🚀", color: "#3b82f6" },
    { key: "BREAKDOWN_CANDIDATES", label: "Breakdown Candidates", icon: "⚡", color: "#f97316" },
    { key: "HIGH_RELATIVE_STRENGTH", label: "High Relative Strength", icon: "💪", color: "#10b981" },
    { key: "HIGH_VOLUME_ACCUMULATION", label: "Volume Accumulation", icon: "🔥", color: "#ec4899" },
    { key: "CONSOLIDATION_CANDIDATES", label: "Consolidation Candidates", icon: "▤", color: "#eab308" },
  ];

  const fetchScan = async () => {
    setLoading(true);
    setError(null);
    try {
      const filtersObj: any = {};
      if (filterPriceAboveEma20) filtersObj.price_above_ema20 = true;
      if (filterPriceAboveEma50) filtersObj.price_above_ema50 = true;
      if (filterPriceAboveEma200) filtersObj.price_above_ema200 = true;
      if (filterSupertrendUp) filtersObj.supertrend_dir = "up";
      if (filterMinRsi) filtersObj.min_rsi = parseFloat(filterMinRsi);
      if (filterMaxRsi) filtersObj.max_rsi = parseFloat(filterMaxRsi);
      if (filterMinRvol) filtersObj.min_rvol = parseFloat(filterMinRvol);
      if (filterBbSqueeze) filtersObj.bb_squeeze = true;
      if (filterMacdBullish) filtersObj.macd_bullish_cross = true;
      if (filterMinRoe) filtersObj.min_roe = parseFloat(filterMinRoe);
      if (filterMaxDebtEquity) filtersObj.max_debt_equity = parseFloat(filterMaxDebtEquity);
      if (filterMinProfitGrowth) filtersObj.min_profit_growth = parseFloat(filterMinProfitGrowth);
      if (filterFreshOrderBlock) filtersObj.has_fresh_ob = true;
      if (filterFairValueGap) filtersObj.has_fvg = true;
      if (filterBreakout) filtersObj.is_breakout = true;
      if (filterStructureTrend) filtersObj.structure_trend = filterStructureTrend;

      const payload = {
        universe,
        ranking_preset: activePreset,
        logic_mode: logicMode,
        filters: filtersObj,
        sort_by: sortField,
        sort_order: sortAsc ? "asc" : "desc",
        page,
        page_size: pageSize,
      };

      const res = await apiFetch("/api/scanner/advanced/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(`Failed to load scanner: HTTP ${res.status}`);
      }

      const data: ScannerData = await res.json();
      setScannerData(data);
    } catch (err: any) {
      setError(err.message || "Failed to load market scanner");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchScan();
  }, [universe, activePreset, page, pageSize, sortField, sortAsc, logicMode]);

  // Load Watchlists & Saved Scanners
  const loadSavedScanners = async () => {
    try {
      const res = await apiFetch("/api/scanner/custom/saved");
      if (res.ok) {
        const data = await res.json();
        setSavedScanners(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const loadWatchlists = async () => {
    try {
      const res = await apiFetch("/api/watchlists");
      if (res.ok) {
        const data = await res.json();
        setWatchlists(data);
      }
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadSavedScanners();
    loadWatchlists();
  }, []);

  const handleSaveCustomScanner = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customScannerName.trim()) return;

    const filtersObj: any = {};
    if (filterPriceAboveEma20) filtersObj.price_above_ema20 = true;
    if (filterPriceAboveEma50) filtersObj.price_above_ema50 = true;
    if (filterPriceAboveEma200) filtersObj.price_above_ema200 = true;
    if (filterSupertrendUp) filtersObj.supertrend_dir = "up";
    if (filterMinRsi) filtersObj.min_rsi = parseFloat(filterMinRsi);
    if (filterMaxRsi) filtersObj.max_rsi = parseFloat(filterMaxRsi);
    if (filterMinRvol) filtersObj.min_rvol = parseFloat(filterMinRvol);
    if (filterBbSqueeze) filtersObj.bb_squeeze = true;
    if (filterMacdBullish) filtersObj.macd_bullish_cross = true;
    if (filterMinRoe) filtersObj.min_roe = parseFloat(filterMinRoe);
    if (filterMaxDebtEquity) filtersObj.max_debt_equity = parseFloat(filterMaxDebtEquity);
    if (filterMinProfitGrowth) filtersObj.min_profit_growth = parseFloat(filterMinProfitGrowth);
    if (filterFreshOrderBlock) filtersObj.has_fresh_ob = true;
    if (filterFairValueGap) filtersObj.has_fvg = true;
    if (filterBreakout) filtersObj.is_breakout = true;
    if (filterStructureTrend) filtersObj.structure_trend = filterStructureTrend;

    try {
      const res = await apiFetch("/api/scanner/custom/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: customScannerName.trim(),
          description: customScannerDesc.trim(),
          universe,
          timeframe: "1D",
          logic_mode: logicMode,
          conditions: filtersObj,
        }),
      });
      if (res.ok) {
        alert("Custom Scanner successfully saved to database!");
        setShowSaveCurrentModal(false);
        setCustomScannerName("");
        setCustomScannerDesc("");
        loadSavedScanners();
      }
    } catch (err) {
      alert("Failed to save custom scanner.");
    }
  };

  const handleAddSymbolToWl = async (wlId: number) => {
    if (!selectedStockForWl) return;
    try {
      const res = await apiFetch(`/api/watchlists/${wlId}/symbols`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: selectedStockForWl }),
      });
      if (res.ok) {
        alert(`${selectedStockForWl} added to watchlist!`);
        setShowWlSelectModal(false);
        setSelectedStockForWl(null);
        loadWatchlists();
      }
    } catch (err) {
      alert("Failed to add symbol to watchlist.");
    }
  };

  const handleExportCsv = () => {
    window.open(`/api/scanner/advanced/export-csv?universe=${universe}&ranking_preset=${activePreset}&logic_mode=${logicMode}`, "_blank");
  };

  const filteredItems = useMemo(() => {
    if (!scannerData?.items) return [];
    const q = search.toLowerCase();
    return scannerData.items.filter(
      (s) => {
        const matchesSearch = !q ||
          s.symbol.toLowerCase().includes(q) ||
          s.company_name.toLowerCase().includes(q) ||
          s.sector.toLowerCase().includes(q);
        const minimumScore = parseFloat(minimumSetupScore);
        return matchesSearch && (!Number.isFinite(minimumScore) || (s.rank_score != null && s.rank_score >= minimumScore));
      }
    );
  }, [scannerData, search, minimumSetupScore]);

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Header Bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
          background: "linear-gradient(180deg, #131c2a 0%, #0e1622 100%)",
          padding: "20px 24px",
          borderRadius: "12px",
          border: "1px solid #1e2c40",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h2 style={{ margin: 0, fontSize: "22px", color: "#fff", fontWeight: 700 }}>
              Advanced Market Scanner & Stock Ranking Engine
            </h2>
            <span
              style={{
                background: "rgba(59, 130, 246, 0.15)",
                color: "#60a5fa",
                border: "1px solid rgba(59, 130, 246, 0.3)",
                padding: "3px 10px",
                borderRadius: "6px",
                fontSize: "11px",
                fontWeight: 600,
                letterSpacing: "0.5px",
              }}
            >
              MARKET SCAN
            </span>
          </div>
          <p style={{ margin: "6px 0 0 0", color: "#8c9bb0", fontSize: "13px" }}>
            Multi-condition technical & fundamental stock screening with 7 institutional ranking presets, AND/OR logic, and persistence.
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          {/* Universe selection */}
          <div style={{ display: "flex", background: "#0a0f18", borderRadius: "8px", padding: "3px", border: "1px solid #1e2c40" }}>
            {[
              { id: "all", label: "All Stocks" },
              { id: "nifty50", label: "NIFTY 50" },
              { id: "nifty100", label: "NIFTY 100" },
              { id: "nifty500", label: "NIFTY 500" },
              { id: "fno", label: "F&O" },
            ].map((u) => (
              <button
                key={u.id}
                onClick={() => {
                  setUniverse(u.id);
                  setPage(1);
                }}
                style={{
                  background: universe === u.id ? "#2563eb" : "transparent",
                  color: universe === u.id ? "#fff" : "#8c9bb0",
                  border: "none",
                  padding: "6px 12px",
                  borderRadius: "6px",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {u.label}
              </button>
            ))}
          </div>

          {/* Filter Drawer Toggle */}
          <button
            onClick={() => setShowFilters(!showFilters)}
            style={{
              background: showFilters ? "#2563eb" : "#1e2c40",
              color: "#fff",
              border: "1px solid #2d3f58",
              padding: "7px 14px",
              borderRadius: "8px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            ⚙ Filters {showFilters ? "▲" : "▼"}
          </button>

          {/* Custom Scanners Modal Button */}
          <button
            onClick={() => setShowSavedModal(true)}
            style={{
              background: "#1e2c40",
              color: "#38bdf8",
              border: "1px solid #2d3f58",
              padding: "7px 14px",
              borderRadius: "8px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Saved Scanners ({savedScanners.length})
          </button>

          {/* CSV Export Button */}
          <button
            onClick={handleExportCsv}
            style={{
              background: "#14532d",
              color: "#86efac",
              border: "1px solid #166534",
              padding: "7px 14px",
              borderRadius: "8px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            ⬇ Export CSV
          </button>

          {/* Rescan Button */}
          <button
            onClick={() => fetchScan()}
            disabled={loading}
            style={{
              background: "#1e2c40",
              color: "#60a5fa",
              border: "1px solid #2d3f58",
              padding: "7px 14px",
              borderRadius: "8px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            {loading ? "Scanning..." : "⟳ Rescan"}
          </button>
        </div>
      </div>

      {/* Transparent Universe Coverage Notice */}
      {scannerData?.metadata && (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            background: "#0d1520",
            border: "1px solid #1b2636",
            borderRadius: "6px",
            padding: "8px 16px",
            fontSize: "11px",
            color: "#94a3b8",
            flexWrap: "wrap",
            gap: "8px",
          }}
        >
          <div>
            <strong style={{ color: "#38bdf8" }}>Coverage Disclosure:</strong> Scanned{" "}
            {scannerData.metadata.scanned_count} of {scannerData.metadata.configured_universe_count} constituents in{" "}
            {scannerData.metadata.universe_label} tracked in local database ({scannerData.metadata.coverage_pct}% coverage).
          </div>
          <div>
            <span>Data Mode: HISTORICAL</span> | <span>Last Scanned: {scannerData.timestamp}</span>
          </div>
        </div>
      )}

      {/* Expandable Advanced Multi-Condition Filter Panel */}
      {showFilters && (
        <div
          style={{
            background: "#0d1522",
            border: "1px solid #1e2c40",
            borderRadius: "10px",
            padding: "18px 22px",
            display: "flex",
            flexDirection: "column",
            gap: "14px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h4 style={{ margin: 0, fontSize: "14px", color: "#f1f5f9", fontWeight: 700 }}>
              Technical, Fundamental, Volume & SMC Filters
            </h4>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <span style={{ fontSize: "12px", color: "#8c9bb0" }}>Logic Combination:</span>
              <div style={{ display: "flex", background: "#0a0f18", padding: "2px", borderRadius: "6px", border: "1px solid #1e293b" }}>
                <button
                  onClick={() => setLogicMode("AND")}
                  style={{
                    background: logicMode === "AND" ? "#2563eb" : "transparent",
                    color: logicMode === "AND" ? "#fff" : "#94a3b8",
                    border: "none",
                    padding: "4px 10px",
                    borderRadius: "4px",
                    fontSize: "11px",
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                >
                  AND (All Match)
                </button>
                <button
                  onClick={() => setLogicMode("OR")}
                  style={{
                    background: logicMode === "OR" ? "#2563eb" : "transparent",
                    color: logicMode === "OR" ? "#fff" : "#94a3b8",
                    border: "none",
                    padding: "4px 10px",
                    borderRadius: "4px",
                    fontSize: "11px",
                    fontWeight: 700,
                    cursor: "pointer",
                  }}
                >
                  OR (Any Match)
                </button>
              </div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px" }}>
            {/* Technical Toggles */}
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <span style={{ fontSize: "11px", fontWeight: 700, color: "#38bdf8", textTransform: "uppercase" }}>Moving Averages & Trend</span>
              <label style={{ fontSize: "12px", color: "#cbd5e1", display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input type="checkbox" checked={filterPriceAboveEma20} onChange={(e) => setFilterPriceAboveEma20(e.target.checked)} />
                Price &gt; EMA 20
              </label>
              <label style={{ fontSize: "12px", color: "#cbd5e1", display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input type="checkbox" checked={filterPriceAboveEma50} onChange={(e) => setFilterPriceAboveEma50(e.target.checked)} />
                Price &gt; EMA 50
              </label>
              <label style={{ fontSize: "12px", color: "#cbd5e1", display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input type="checkbox" checked={filterPriceAboveEma200} onChange={(e) => setFilterPriceAboveEma200(e.target.checked)} />
                Price &gt; EMA 200 (Long Term)
              </label>
              <label style={{ fontSize: "12px", color: "#cbd5e1", display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input type="checkbox" checked={filterSupertrendUp} onChange={(e) => setFilterSupertrendUp(e.target.checked)} />
                Supertrend Bullish
              </label>
            </div>

            {/* Momentum & Volatility */}
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <span style={{ fontSize: "11px", fontWeight: 700, color: "#38bdf8", textTransform: "uppercase" }}>Momentum & Volume</span>
              <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                <input
                  type="number"
                  placeholder="Min RSI (e.g. 50)"
                  value={filterMinRsi}
                  onChange={(e) => setFilterMinRsi(e.target.value)}
                  style={{ width: "100%", background: "#0a0f18", border: "1px solid #1e2c40", padding: "6px 10px", borderRadius: "6px", color: "#fff", fontSize: "11px" }}
                />
                <input
                  type="number"
                  placeholder="Max RSI (e.g. 70)"
                  value={filterMaxRsi}
                  onChange={(e) => setFilterMaxRsi(e.target.value)}
                  style={{ width: "100%", background: "#0a0f18", border: "1px solid #1e2c40", padding: "6px 10px", borderRadius: "6px", color: "#fff", fontSize: "11px" }}
                />
              </div>
              <input
                type="number"
                step="0.1"
                placeholder="Min RVOL (e.g. 1.5)"
                value={filterMinRvol}
                onChange={(e) => setFilterMinRvol(e.target.value)}
                style={{ width: "100%", background: "#0a0f18", border: "1px solid #1e2c40", padding: "6px 10px", borderRadius: "6px", color: "#fff", fontSize: "11px" }}
              />
              <label style={{ fontSize: "12px", color: "#cbd5e1", display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input type="checkbox" checked={filterBbSqueeze} onChange={(e) => setFilterBbSqueeze(e.target.checked)} />
                Bollinger Band Squeeze (&le;8%)
              </label>
              <label style={{ fontSize: "12px", color: "#cbd5e1", display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input type="checkbox" checked={filterMacdBullish} onChange={(e) => setFilterMacdBullish(e.target.checked)} />
                MACD Bullish Crossover
              </label>
            </div>

            {/* Fundamental Filters */}
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <span style={{ fontSize: "11px", fontWeight: 700, color: "#38bdf8", textTransform: "uppercase" }}>Fundamental Quality</span>
              <input
                type="number"
                placeholder="Min ROE % (e.g. 15)"
                value={filterMinRoe}
                onChange={(e) => setFilterMinRoe(e.target.value)}
                style={{ width: "100%", background: "#0a0f18", border: "1px solid #1e2c40", padding: "6px 10px", borderRadius: "6px", color: "#fff", fontSize: "11px" }}
              />
              <input
                type="number"
                step="0.1"
                placeholder="Max Debt/Equity (e.g. 1.0)"
                value={filterMaxDebtEquity}
                onChange={(e) => setFilterMaxDebtEquity(e.target.value)}
                style={{ width: "100%", background: "#0a0f18", border: "1px solid #1e2c40", padding: "6px 10px", borderRadius: "6px", color: "#fff", fontSize: "11px" }}
              />
              <input
                type="number"
                placeholder="Min Profit Growth % (e.g. 12)"
                value={filterMinProfitGrowth}
                onChange={(e) => setFilterMinProfitGrowth(e.target.value)}
                style={{ width: "100%", background: "#0a0f18", border: "1px solid #1e2c40", padding: "6px 10px", borderRadius: "6px", color: "#fff", fontSize: "11px" }}
              />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <span style={{ fontSize: "11px", fontWeight: 700, color: "#38bdf8", textTransform: "uppercase" }}>Smart Money Concepts</span>
              <label style={{ fontSize: "12px", color: "#cbd5e1", display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input type="checkbox" checked={filterFreshOrderBlock} onChange={(e) => setFilterFreshOrderBlock(e.target.checked)} />
                Fresh order block
              </label>
              <label style={{ fontSize: "12px", color: "#cbd5e1", display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input type="checkbox" checked={filterFairValueGap} onChange={(e) => setFilterFairValueGap(e.target.checked)} />
                Fair value gap
              </label>
              <label style={{ fontSize: "12px", color: "#cbd5e1", display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                <input type="checkbox" checked={filterBreakout} onChange={(e) => setFilterBreakout(e.target.checked)} />
                Confirmed breakout
              </label>
              <select
                value={filterStructureTrend}
                onChange={(e) => setFilterStructureTrend(e.target.value)}
                style={{ width: "100%", background: "#0a0f18", border: "1px solid #1e2c40", padding: "6px 10px", borderRadius: "6px", color: "#fff", fontSize: "11px" }}
              >
                <option value="">Any market structure</option>
                <option value="Bullish">Bullish structure</option>
                <option value="Bearish">Bearish structure</option>
              </select>
              <input
                type="number"
                min="0"
                max="100"
                placeholder="Minimum setup score (current page)"
                value={minimumSetupScore}
                onChange={(e) => setMinimumSetupScore(e.target.value)}
                style={{ width: "100%", background: "#0a0f18", border: "1px solid #1e2c40", padding: "6px 10px", borderRadius: "6px", color: "#fff", fontSize: "11px" }}
              />
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "10px" }}>
            <button
              onClick={() => {
                setFilterPriceAboveEma20(false);
                setFilterPriceAboveEma50(false);
                setFilterPriceAboveEma200(false);
                setFilterSupertrendUp(false);
                setFilterMinRsi("");
                setFilterMaxRsi("");
                setFilterMinRvol("");
                setFilterBbSqueeze(false);
                setFilterMacdBullish(false);
                setFilterMinRoe("");
                setFilterMaxDebtEquity("");
                setFilterMinProfitGrowth("");
                setFilterFreshOrderBlock(false);
                setFilterFairValueGap(false);
                setFilterBreakout(false);
                setFilterStructureTrend("");
                setMinimumSetupScore("");
              }}
              style={{ background: "#1e293b", color: "#cbd5e1", border: "1px solid #334155", padding: "6px 14px", borderRadius: "6px", fontSize: "12px", cursor: "pointer" }}
            >
              Reset Filters
            </button>
            <button
              onClick={() => setShowSaveCurrentModal(true)}
              style={{ background: "#1e293b", color: "#38bdf8", border: "1px solid #334155", padding: "6px 14px", borderRadius: "6px", fontSize: "12px", cursor: "pointer" }}
            >
              Save As Custom Scanner
            </button>
            <button
              onClick={() => {
                setPage(1);
                fetchScan();
              }}
              style={{ background: "#2563eb", color: "#fff", border: "none", padding: "6px 18px", borderRadius: "6px", fontSize: "12px", fontWeight: 700, cursor: "pointer" }}
            >
              Apply Filters
            </button>
          </div>
        </div>
      )}

      {/* 7 Preset Ranking Systems Tabs & Search */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          borderBottom: "1px solid #1e2c40",
          paddingBottom: "12px",
        }}
      >
        <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
          {presetsDef.map((preset) => {
            const isActive = activePreset === preset.key;
            return (
              <button
                key={preset.key}
                onClick={() => {
                  setActivePreset(preset.key);
                  setPage(1);
                }}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  background: isActive ? "rgba(59, 130, 246, 0.15)" : "#0e1622",
                  color: isActive ? "#fff" : "#8c9bb0",
                  border: isActive ? `1px solid ${preset.color}` : "1px solid #1e2c40",
                  padding: "8px 14px",
                  borderRadius: "8px",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                <span>{preset.icon}</span>
                <span>{preset.label}</span>
              </button>
            );
          })}
        </div>

        {/* Search Bar */}
        <div style={{ position: "relative", minWidth: "220px" }}>
          <input
            type="text"
            placeholder="Search scanned stocks..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              width: "100%",
              background: "#0a0f18",
              border: "1px solid #1e2c40",
              borderRadius: "8px",
              padding: "8px 12px 8px 32px",
              color: "#fff",
              fontSize: "12px",
              outline: "none",
            }}
          />
          <span style={{ position: "absolute", left: "10px", top: "8px", color: "#60a5fa", fontSize: "14px" }}>
            🔍
          </span>
        </div>
      </div>

      {/* Main Results Table */}
      <div
        style={{
          background: "#0e1622",
          border: "1px solid #1e2c40",
          borderRadius: "12px",
          overflow: "hidden",
        }}
      >
        {loading && (
          <div style={{ padding: "40px", textAlign: "center", color: "#8c9bb0" }}>
            <div style={{ fontSize: "24px", marginBottom: "8px" }}>⏳</div>
            <div>Executing multi-condition technical & fundamental scan...</div>
          </div>
        )}

        {error && (
          <div style={{ padding: "30px", textAlign: "center", color: "#ef4444" }}>
            <div>⚠️ {error}</div>
            <button
              onClick={() => fetchScan()}
              style={{
                marginTop: "12px",
                background: "#1e2c40",
                color: "#fff",
                border: "none",
                padding: "6px 14px",
                borderRadius: "6px",
                cursor: "pointer",
              }}
            >
              Retry Scan
            </button>
          </div>
        )}

        {!loading && !error && filteredItems.length === 0 && (
          <div style={{ padding: "50px", textAlign: "center", color: "#8c9bb0" }}>
            <div style={{ fontSize: "28px", marginBottom: "8px" }}>📋</div>
            <div style={{ fontSize: "15px", color: "#fff", fontWeight: 600 }}>No stocks match this filter configuration</div>
            <div style={{ fontSize: "12px", marginTop: "4px" }}>
              Try broadening your criteria, switching the logic mode to OR, or picking another ranking preset.
            </div>
          </div>
        )}

        {!loading && !error && filteredItems.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "13px" }}>
              <thead>
                <tr style={{ background: "#0a0f18", borderBottom: "1px solid #1e2c40", color: "#8c9bb0", fontSize: "11px", textTransform: "uppercase" }}>
                  <th style={{ padding: "12px 14px", width: "50px" }}>Rank</th>
                  <th style={{ padding: "12px 14px", cursor: "pointer" }} onClick={() => handleSort("symbol")}>
                    Stock {sortField === "symbol" ? (sortAsc ? "▲" : "▼") : ""}
                  </th>
                  <th style={{ padding: "12px 14px" }}>Sector</th>
                  <th style={{ padding: "12px 14px", textAlign: "right", cursor: "pointer" }} onClick={() => handleSort("close")}>
                    LTP (₹) {sortField === "close" ? (sortAsc ? "▲" : "▼") : ""}
                  </th>
                  <th style={{ padding: "12px 14px", textAlign: "right", cursor: "pointer" }} onClick={() => handleSort("daily_change_pct")}>
                    Change % {sortField === "daily_change_pct" ? (sortAsc ? "▲" : "▼") : ""}
                  </th>
                  <th style={{ padding: "12px 14px", textAlign: "right", cursor: "pointer" }} onClick={() => handleSort("relative_volume")}>
                    RVOL {sortField === "relative_volume" ? (sortAsc ? "▲" : "▼") : ""}
                  </th>
                  <th style={{ padding: "12px 14px", textAlign: "right", cursor: "pointer" }} onClick={() => handleSort("rsi")}>
                    RSI {sortField === "rsi" ? (sortAsc ? "▲" : "▼") : ""}
                  </th>
                  <th style={{ padding: "12px 14px", textAlign: "center" }}>Supertrend</th>
                  <th style={{ padding: "12px 14px", cursor: "pointer" }} onClick={() => handleSort("rank_score")}>
                    Rank Score & Rationale {sortField === "rank_score" ? (sortAsc ? "▲" : "▼") : ""}
                  </th>
                  <th style={{ padding: "12px 14px", textAlign: "center" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map((stock, idx) => {
                  const isPos = stock.daily_change_pct >= 0;
                  const rankNum = stock.rank || (page - 1) * pageSize + idx + 1;
                  return (
                    <tr
                      key={stock.symbol}
                      style={{
                        borderBottom: "1px solid #16202e",
                        transition: "background 0.15s ease",
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "#131d2a")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                    >
                      <td style={{ padding: "12px 14px", color: "#64748b", fontWeight: 700 }}>
                        #{rankNum}
                      </td>
                      <td style={{ padding: "12px 14px" }}>
                        <div style={{ fontWeight: 700, color: "#fff", fontSize: "14px" }}>{stock.symbol}</div>
                        <div style={{ fontSize: "11px", color: "#64748b" }}>{stock.company_name}</div>
                      </td>
                      <td style={{ padding: "12px 14px", fontSize: "12px", color: "#94a3b8" }}>
                        {stock.sector}
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontWeight: 700, color: "#f8fafc" }}>
                        ₹{stock.close.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right" }}>
                        <span
                          style={{
                            padding: "3px 8px",
                            borderRadius: "4px",
                            fontSize: "12px",
                            fontWeight: 700,
                            background: isPos ? "rgba(38,199,139,0.15)" : "rgba(239,102,118,0.15)",
                            color: isPos ? "#26c78b" : "#ef6676",
                          }}
                        >
                          {isPos ? "+" : ""}{stock.daily_change_pct.toFixed(2)}%
                        </span>
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontSize: "12px", color: stock.relative_volume >= 1.4 ? "#38bdf8" : "#cbd5e1" }}>
                        {stock.relative_volume.toFixed(2)}x
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontSize: "12px", color: stock.rsi >= 60 ? "#26c78b" : (stock.rsi <= 40 ? "#ef6676" : "#cbd5e1") }}>
                        {stock.rsi.toFixed(1)}
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "center" }}>
                        <span
                          style={{
                            padding: "2px 7px",
                            borderRadius: "4px",
                            fontSize: "10px",
                            fontWeight: 700,
                            background: stock.supertrend_dir === "up" ? "rgba(38,199,139,0.15)" : "rgba(239,102,118,0.15)",
                            color: stock.supertrend_dir === "up" ? "#26c78b" : "#ef6676",
                            textTransform: "uppercase",
                          }}
                        >
                          {stock.supertrend_dir}
                        </span>
                      </td>
                      <td style={{ padding: "12px 14px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <span style={{ fontSize: "13px", fontWeight: 800, color: "#38bdf8" }}>
                            {stock.rank_score}
                          </span>
                          <span style={{ fontSize: "11px", color: "#94a3b8" }}>
                            {stock.rank_reason || "Ranked candidate"}
                          </span>
                        </div>
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "center" }}>
                        <div style={{ display: "flex", gap: "6px", justifyContent: "center" }}>
                          <button
                            onClick={() => onSelectStock(stock.symbol, "chart")}
                            style={{
                              background: "#1e293b",
                              color: "#38bdf8",
                              border: "1px solid #334155",
                              padding: "4px 8px",
                              borderRadius: "4px",
                              fontSize: "11px",
                              fontWeight: 600,
                              cursor: "pointer",
                            }}
                          >
                            Chart
                          </button>
                          <button
                            onClick={() => {
                              setSelectedStockForWl(stock.symbol);
                              setShowWlSelectModal(true);
                            }}
                            title="Add to Watchlist"
                            style={{
                              background: "#1e293b",
                              color: "#f59e0b",
                              border: "1px solid #334155",
                              padding: "4px 8px",
                              borderRadius: "4px",
                              fontSize: "11px",
                              fontWeight: 600,
                              cursor: "pointer",
                            }}
                          >
                            + Watchlist
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Footer */}
        {scannerData && scannerData.total_records > 0 && (
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "12px 20px",
              background: "#0a0f18",
              borderTop: "1px solid #1e2c40",
              fontSize: "12px",
              color: "#94a3b8",
              flexWrap: "wrap",
              gap: "12px",
            }}
          >
            <div>
              Showing {((scannerData.page - 1) * scannerData.page_size) + 1} to{" "}
              {Math.min(scannerData.page * scannerData.page_size, scannerData.total_records)} of{" "}
              {scannerData.total_records} records
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <span>Rows per page:</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(parseInt(e.target.value));
                  setPage(1);
                }}
                style={{
                  background: "#1e2c40",
                  color: "#fff",
                  border: "1px solid #334155",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "12px",
                }}
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
              </select>

              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                style={{
                  background: page <= 1 ? "#111827" : "#1e2c40",
                  color: page <= 1 ? "#475569" : "#fff",
                  border: "1px solid #334155",
                  padding: "4px 10px",
                  borderRadius: "4px",
                  cursor: page <= 1 ? "not-allowed" : "pointer",
                }}
              >
                ◀ Prev
              </button>
              <span>
                Page {scannerData.page} of {scannerData.total_pages}
              </span>
              <button
                disabled={page >= scannerData.total_pages}
                onClick={() => setPage((p) => Math.min(scannerData.total_pages, p + 1))}
                style={{
                  background: page >= scannerData.total_pages ? "#111827" : "#1e2c40",
                  color: page >= scannerData.total_pages ? "#475569" : "#fff",
                  border: "1px solid #334155",
                  padding: "4px 10px",
                  borderRadius: "4px",
                  cursor: page >= scannerData.total_pages ? "not-allowed" : "pointer",
                }}
              >
                Next ▶
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Save Current Custom Scanner Modal */}
      {showSaveCurrentModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.7)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "#111925",
              border: "1px solid #202d40",
              borderRadius: "12px",
              padding: "24px",
              width: "440px",
              maxWidth: "90%",
            }}
          >
            <h3 style={{ margin: "0 0 12px", color: "#f8fafc", fontSize: "16px" }}>
              Save Custom Scanner Preset
            </h3>
            <form onSubmit={handleSaveCustomScanner} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <div>
                <label style={{ fontSize: "12px", color: "#94a3b8" }}>Scanner Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. My High Momentum Breakout"
                  value={customScannerName}
                  onChange={(e) => setCustomScannerName(e.target.value)}
                  style={{
                    width: "100%",
                    background: "#0a0f18",
                    border: "1px solid #1e2c40",
                    padding: "8px 12px",
                    borderRadius: "6px",
                    color: "#fff",
                    fontSize: "13px",
                    marginTop: "4px",
                  }}
                />
              </div>

              <div>
                <label style={{ fontSize: "12px", color: "#94a3b8" }}>Description</label>
                <textarea
                  placeholder="Notes on the strategy rationale..."
                  value={customScannerDesc}
                  onChange={(e) => setCustomScannerDesc(e.target.value)}
                  style={{
                    width: "100%",
                    background: "#0a0f18",
                    border: "1px solid #1e2c40",
                    padding: "8px 12px",
                    borderRadius: "6px",
                    color: "#fff",
                    fontSize: "13px",
                    marginTop: "4px",
                    minHeight: "70px",
                  }}
                />
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "12px" }}>
                <button
                  type="button"
                  onClick={() => setShowSaveCurrentModal(false)}
                  style={{
                    background: "#1e293b",
                    color: "#cbd5e1",
                    border: "none",
                    padding: "8px 16px",
                    borderRadius: "6px",
                    cursor: "pointer",
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  style={{
                    background: "#2563eb",
                    color: "#fff",
                    border: "none",
                    padding: "8px 18px",
                    borderRadius: "6px",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Save Preset
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Saved Scanners Management Modal */}
      {showSavedModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.7)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "#111925",
              border: "1px solid #202d40",
              borderRadius: "12px",
              padding: "24px",
              width: "560px",
              maxWidth: "90%",
              maxHeight: "80vh",
              overflowY: "auto",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
              <h3 style={{ margin: 0, color: "#f8fafc", fontSize: "16px" }}>Saved Custom Scanners</h3>
              <button
                onClick={() => setShowSavedModal(false)}
                style={{ background: "transparent", border: "none", color: "#94a3b8", fontSize: "18px", cursor: "pointer" }}
              >
                ✕
              </button>
            </div>

            {savedScanners.length === 0 ? (
              <div style={{ textAlign: "center", padding: "30px", color: "#64748b" }}>
                No custom scanners saved yet. Use the "⚙ Filters" panel to design and save your custom scans.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {savedScanners.map((sc) => (
                  <div
                    key={sc.id}
                    style={{
                      background: "#0d1522",
                      border: "1px solid #1e2c40",
                      borderRadius: "8px",
                      padding: "12px 16px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 700, color: "#f8fafc", fontSize: "13px" }}>{sc.name}</div>
                      <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "2px" }}>{sc.description || "No description"}</div>
                      <div style={{ fontSize: "10px", color: "#64748b", marginTop: "4px" }}>
                        Universe: {sc.universe.toUpperCase()} | Logic: {sc.logic_mode}
                      </div>
                    </div>

                    <div style={{ display: "flex", gap: "8px" }}>
                      <button
                        onClick={async () => {
                          const ok = confirm(`Delete custom scanner '${sc.name}'?`);
                          if (ok) {
                            await apiFetch(`/api/scanner/custom/${sc.id}`, { method: "DELETE" });
                            loadSavedScanners();
                          }
                        }}
                        style={{
                          background: "#371b20",
                          color: "#ef4444",
                          border: "1px solid #4a1d24",
                          padding: "5px 10px",
                          borderRadius: "4px",
                          fontSize: "11px",
                          cursor: "pointer",
                        }}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Add Symbol to Watchlist Modal */}
      {showWlSelectModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.7)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "#111925",
              border: "1px solid #202d40",
              borderRadius: "12px",
              padding: "24px",
              width: "400px",
              maxWidth: "90%",
            }}
          >
            <h3 style={{ margin: "0 0 12px", color: "#f8fafc", fontSize: "16px" }}>
              Add {selectedStockForWl} to Watchlist
            </h3>
            <p style={{ margin: "0 0 14px", fontSize: "12px", color: "#8c9bb0" }}>
              Select which watchlist you want to add this stock to:
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: "8px", maxHeight: "200px", overflowY: "auto" }}>
              {watchlists.map((wl) => (
                <button
                  key={wl.id}
                  onClick={() => handleAddSymbolToWl(wl.id)}
                  style={{
                    background: "#0d1522",
                    border: "1px solid #1e2c40",
                    borderRadius: "6px",
                    padding: "10px 14px",
                    textAlign: "left",
                    color: "#fff",
                    fontSize: "13px",
                    cursor: "pointer",
                    display: "flex",
                    justifyContent: "space-between",
                  }}
                >
                  <span>{wl.name}</span>
                  <span style={{ fontSize: "11px", color: "#64748b" }}>{wl.symbol_count} items</span>
                </button>
              ))}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "16px" }}>
              <button
                onClick={() => {
                  setShowWlSelectModal(false);
                  setSelectedStockForWl(null);
                }}
                style={{
                  background: "#1e293b",
                  color: "#cbd5e1",
                  border: "none",
                  padding: "8px 16px",
                  borderRadius: "6px",
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

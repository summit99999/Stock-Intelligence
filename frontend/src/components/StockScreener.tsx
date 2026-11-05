/**
 * StockScreener — Professional Indian equity screening interface.
 *
 * Features:
 *   - Universe selection (exchange, sector, cap category, search)
 *   - Fundamental filters (market cap, P/E, ROE, ROCE, etc.)
 *   - Technical filters (RSI, MACD, EMA, returns, etc.)
 *   - Advanced AND/OR filter builder
 *   - Sortable, paginated results table
 *   - CSV export, save/load screening strategies
 *
 * All data is demo/illustrative and clearly labelled.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  ConditionGroup,
  FilterCondition,
  Operator,
  SavedScreener,
  ScreenerMetadata,
  ScreenRequest,
  ScreenResponse,
  SortOrder,
  StockResult,
} from "../types/screener";
import {
  deletePreset,
  exportCSV,
  getDefaultPresets,
  getJobStatus,
  getMarketDataStatus,
  getPresets,
  getScreenerMetadata,
  runScreener,
  savePreset,
  triggerDataUpdate,
} from "../api/screener";
import type { MarketDataStatus, JobStatus } from "../api/screener";
import CsvImportModal from "./CsvImportModal";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _idCounter = 0;
function uid(): string {
  return `c${++_idCounter}_${Date.now()}`;
}

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("en-IN");
}

function changeClass(v: number | null | undefined): string {
  if (v === null || v === undefined) return "";
  return v >= 0 ? "positive" : "negative";
}

// All filterable fields for the advanced builder
const ALL_FIELDS = [
  { value: "market_cap_cr", label: "Market Cap (Cr)" },
  { value: "close", label: "Price" },
  { value: "pe", label: "P/E" },
  { value: "pb", label: "P/B" },
  { value: "roe", label: "ROE (%)" },
  { value: "roce", label: "ROCE (%)" },
  { value: "debt_equity", label: "Debt/Equity" },
  { value: "revenue_growth_pct", label: "Revenue Growth (%)" },
  { value: "profit_growth_pct", label: "Profit Growth (%)" },
  { value: "opm_pct", label: "OPM (%)" },
  { value: "free_cash_flow_cr", label: "FCF (Cr)" },
  { value: "promoter_holding", label: "Promoter Holding (%)" },
  { value: "promoter_pledging", label: "Promoter Pledging (%)" },
  { value: "fii_holding", label: "FII Holding (%)" },
  { value: "dii_holding", label: "DII Holding (%)" },
  { value: "rsi", label: "RSI (14)" },
  { value: "macd", label: "MACD" },
  { value: "macd_signal", label: "MACD Signal" },
  { value: "adx", label: "ADX" },
  { value: "relative_volume", label: "Relative Volume" },
  { value: "volume", label: "Volume" },
  { value: "return_1d_pct", label: "Daily Return (%)" },
  { value: "return_1w_pct", label: "Weekly Return (%)" },
  { value: "return_1m_pct", label: "1M Return (%)" },
  { value: "return_3m_pct", label: "3M Return (%)" },
  { value: "return_6m_pct", label: "6M Return (%)" },
  { value: "return_1y_pct", label: "1Y Return (%)" },
  { value: "ema_20", label: "EMA 20" },
  { value: "ema_50", label: "EMA 50" },
  { value: "ema_100", label: "EMA 100" },
  { value: "ema_200", label: "EMA 200" },
  { value: "sma_20", label: "SMA 20" },
  { value: "sma_50", label: "SMA 50" },
  { value: "sma_100", label: "SMA 100" },
  { value: "sma_200", label: "SMA 200" },
  { value: "revenue_cagr_3y", label: "Revenue CAGR 3Y (%)" },
  { value: "pat_cagr_3y", label: "PAT CAGR 3Y (%)" },
  { value: "interest_coverage", label: "Interest Coverage" },
  { value: "cfo_pat_ratio", label: "CFO / PAT" },
  { value: "peg", label: "PEG Ratio" },
  { value: "quality_score", label: "Quality Score (0-100)" },
];

const OPERATORS: { value: Operator; label: string }[] = [
  { value: ">=", label: ">=" },
  { value: "<=", label: "<=" },
  { value: ">", label: ">" },
  { value: "<", label: "<" },
  { value: "==", label: "=" },
  { value: "!=", label: "!=" },
  { value: "between", label: "Between" },
];

// Table column definitions
const TABLE_COLUMNS: { key: keyof StockResult; label: string; align?: string; format?: (v: unknown) => string; colorize?: boolean }[] = [
  { key: "symbol", label: "SYMBOL" },
  { key: "company_name", label: "COMPANY" },
  { key: "exchange", label: "EXCH" },
  { key: "sector", label: "SECTOR" },
  { key: "close", label: "PRICE (₹)", align: "right", format: (v) => `₹${fmt(v as number)}` },
  { key: "daily_change_pct", label: "CHG %", align: "right", format: (v) => v != null ? `${(v as number) > 0 ? "+" : ""}${fmt(v as number)}%` : "—", colorize: true },
  { key: "quality_score", label: "SCORE", align: "right", format: (v) => v != null ? `${v}/100` : "—" },
  { key: "market_cap_cr", label: "MCAP (Cr)", align: "right", format: (v) => fmtInt(v as number) },
  { key: "pe", label: "P/E", align: "right", format: (v) => fmt(v as number, 1) },
  { key: "roe", label: "ROE %", align: "right", format: (v) => fmt(v as number, 1) },
  { key: "roce", label: "ROCE %", align: "right", format: (v) => fmt(v as number, 1) },
  { key: "revenue_cagr_3y", label: "REV CAGR 3Y", align: "right", format: (v) => v != null ? `${fmt(v as number, 1)}%` : "—", colorize: true },
  { key: "profit_growth_pct", label: "PAT GR %", align: "right", format: (v) => fmt(v as number, 1), colorize: true },
  { key: "rsi", label: "RSI", align: "right", format: (v) => fmt(v as number, 1) },
  { key: "relative_volume", label: "REL VOL", align: "right", format: (v) => fmt(v as number, 1) },
];

// ---------------------------------------------------------------------------
// Default filter state
// ---------------------------------------------------------------------------

function defaultFilters(): ScreenRequest {
  return {
    page: 1,
    page_size: 20,
    sort_by: "market_cap_cr",
    sort_order: "desc",
  };
}

function emptyCondition(): FilterCondition {
  return { id: uid(), field: "market_cap_cr", operator: ">=", value: 0 };
}

function emptyGroup(): ConditionGroup {
  return { id: uid(), logic: "AND", conditions: [emptyCondition()] };
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================

interface StockScreenerProps {
  onOpenResearch?: (symbol: string) => void;
}

export default function StockScreener({ onOpenResearch }: StockScreenerProps = {}) {
  // --- State ---
  const [filters, setFilters] = useState<ScreenRequest>(defaultFilters());
  const [response, setResponse] = useState<ScreenResponse | null>(null);
  const [metadata, setMetadata] = useState<ScreenerMetadata | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Advanced builder
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [groups, setGroups] = useState<ConditionGroup[]>([]);

  // Saved presets & institutional presets
  const [presets, setPresets] = useState<SavedScreener[]>([]);
  const [defaultPresets, setDefaultPresets] = useState<SavedScreener[]>([]);
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [presetName, setPresetName] = useState("");
  const [presetDesc, setPresetDesc] = useState("");
  const [showPresets, setShowPresets] = useState(false);
  const [isCsvModalOpen, setIsCsvModalOpen] = useState(false);

  // Collapsible sections
  const [expandFundamental, setExpandFundamental] = useState(true);
  const [expandTechnical, setExpandTechnical] = useState(false);

  // Market data status
  const [dataStatus, setDataStatus] = useState<MarketDataStatus | null>(null);
  const [updating, setUpdating] = useState(false);
  const [updateJobId, setUpdateJobId] = useState<string | null>(null);
  const [updateProgress, setUpdateProgress] = useState<JobStatus | null>(null);

  // --- Fetch metadata + data status on mount ---
  useEffect(() => {
    getScreenerMetadata()
      .then(setMetadata)
      .catch(() => {
        /* metadata is optional — gracefully degrade */
      });
    getPresets()
      .then(setPresets)
      .catch(() => {});
    getDefaultPresets()
      .then(setDefaultPresets)
      .catch(() => {});
    getMarketDataStatus()
      .then(setDataStatus)
      .catch(() => {});
  }, []);

  // --- Run screener ---
  const runScreen = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const req: ScreenRequest = {
        ...filters,
        ...(groups.length > 0 ? { condition_groups: groups } : {}),
      };
      const res = await runScreener(req);
      setResponse(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Screening failed");
    } finally {
      setLoading(false);
    }
  }, [filters, groups]);

  // --- Auto-run: debounced re-screen whenever filters or groups change ---
  // We use a ref to track whether the initial mount has fired, so we don't
  // double-run on mount.  Sort and pagination changes are included in
  // `filters` state, so they also trigger auto-run immediately.
  const hasMounted = useRef(false);

  // Auto-run on first mount
  useEffect(() => {
    runScreen();
    // Mark that mount has fired after a tick
    const id = setTimeout(() => { hasMounted.current = true; }, 50);
    return () => clearTimeout(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-run when filters or groups change (debounced for text inputs)
  useEffect(() => {
    if (!hasMounted.current) return; // skip initial mount (handled above)
    const timer = setTimeout(() => {
      runScreen();
    }, 350); // 350ms debounce — fast enough for dropdowns, safe for typing
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, groups]);

  // --- Filter updaters ---
  const setFilter = useCallback((key: string, value: string | number | undefined) => {
    setFilters((prev) => {
      const next = { ...prev, [key]: value === "" ? undefined : value, page: 1 };
      return next;
    });
  }, []);

  const clearAll = useCallback(() => {
    setFilters(defaultFilters());
    setGroups([]);
    setShowAdvanced(false);
  }, []);

  // --- Sort ---
  const handleSort = useCallback((col: string) => {
    setFilters((prev) => ({
      ...prev,
      sort_by: col,
      sort_order: prev.sort_by === col && prev.sort_order === "desc" ? ("asc" as SortOrder) : ("desc" as SortOrder),
      page: 1,
    }));
  }, []);

  // --- Pagination ---
  const goPage = useCallback((p: number) => {
    setFilters((prev) => ({ ...prev, page: p }));
  }, []);

  // --- Export ---
  const handleExport = useCallback(async () => {
    try {
      const req: ScreenRequest = {
        ...filters,
        ...(groups.length > 0 ? { condition_groups: groups } : {}),
      };
      await exportCSV(req);
    } catch {
      setError("Export failed");
    }
  }, [filters, groups]);

  // --- Presets ---
  const handleSavePreset = useCallback(async () => {
    if (!presetName.trim()) return;
    try {
      const req: ScreenRequest = {
        ...filters,
        ...(groups.length > 0 ? { condition_groups: groups } : {}),
      };
      await savePreset(presetName, presetDesc, req);
      setShowSaveModal(false);
      setPresetName("");
      setPresetDesc("");
      const updated = await getPresets();
      setPresets(updated);
    } catch {
      setError("Failed to save preset");
    }
  }, [filters, groups, presetName, presetDesc]);

  const loadPreset = useCallback((preset: SavedScreener) => {
    try {
      const config = JSON.parse(preset.config_json) as ScreenRequest;
      setFilters(config);
      if (config.condition_groups) {
        setGroups(config.condition_groups.map((g) => ({
          ...g,
          id: uid(),
          conditions: g.conditions.map((c) => ({ ...c, id: uid() })),
        })));
        setShowAdvanced(true);
      } else {
        setGroups([]);
      }
      setShowPresets(false);
    } catch {
      setError("Failed to load preset");
    }
  }, []);

  const handleDeletePreset = useCallback(async (id: number) => {
    try {
      await deletePreset(id);
      setPresets((prev) => prev.filter((p) => p.id !== id));
    } catch {
      setError("Failed to delete preset");
    }
  }, []);

  // --- Data update ---
  const handleUpdateData = useCallback(async (period: string = "1y") => {
    setUpdating(true);
    setError(null);
    try {
      const res = await triggerDataUpdate(undefined, period, false);
      setUpdateJobId(res.job_id);
      // Poll job progress
      const poll = setInterval(async () => {
        try {
          const status = await getJobStatus(res.job_id);
          setUpdateProgress(status);
          if (status.status === "completed" || status.status === "failed") {
            clearInterval(poll);
            setUpdating(false);
            setUpdateJobId(null);
            // Refresh data status and re-run screen
            getMarketDataStatus().then(setDataStatus).catch(() => {});
            runScreen();
          }
        } catch {
          clearInterval(poll);
          setUpdating(false);
        }
      }, 2000);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Data update failed");
      setUpdating(false);
    }
  }, [runScreen]);

  // --- Active filter count ---
  const activeFilterCount = useMemo(() => {
    let count = 0;
    const skip = new Set(["page", "page_size", "sort_by", "sort_order"]);
    for (const [k, v] of Object.entries(filters)) {
      if (skip.has(k)) continue;
      if (v !== undefined && v !== null && v !== "") count++;
    }
    count += groups.reduce((a, g) => a + g.conditions.length, 0);
    return count;
  }, [filters, groups]);

  // --- Render ---
  return (
    <div className="screener-container">
      {/* Header bar */}
      <div className="screener-header">
        <div>
          <h2>Stock Screener</h2>
          <p className="screener-subtitle">
            Screen {metadata ? `${metadata.sectors.length} sectors` : "NSE/BSE stocks"} with fundamental & technical filters
          </p>
        </div>
        <div className="screener-actions">
          <button className="scr-btn scr-btn-outline" onClick={() => setIsCsvModalOpen(true)}>
            📥 Import CSV
          </button>
          <button className="scr-btn scr-btn-outline" onClick={() => setShowPresets(!showPresets)}>
            {showPresets ? "Hide" : "Presets"} ({presets.length})
          </button>
          <button className="scr-btn scr-btn-outline" onClick={() => setShowSaveModal(true)}>
            Save Strategy
          </button>
          <button className="scr-btn scr-btn-outline" onClick={handleExport}>
            Export CSV
          </button>
          <button className="scr-btn scr-btn-ghost" onClick={clearAll}>
            Clear All
          </button>
          <button className="scr-btn scr-btn-primary" onClick={runScreen} disabled={loading}>
            {loading ? "Screening..." : "Run Screen"}
          </button>
        </div>
      </div>

      {/* Institutional Presets Bar */}
      {defaultPresets.length > 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, overflowX: "auto", paddingBottom: 8, marginBottom: 10 }}>
          <span style={{ fontSize: "0.75rem", fontWeight: 700, color: "#26c78b", whiteSpace: "nowrap" }}>
            Institutional Strategies:
          </span>
          {defaultPresets.map((p) => (
            <button
              key={p.id}
              onClick={() => loadPreset(p)}
              className="scr-btn scr-btn-ghost"
              style={{
                fontSize: "0.75rem",
                padding: "3px 10px",
                borderRadius: "14px",
                background: "#161c28",
                border: "1px solid #2a3547",
                color: "#e2e8f0",
                whiteSpace: "nowrap",
                cursor: "pointer",
              }}
              title={p.description}
            >
              {p.name}
            </button>
          ))}
        </div>
      )}

      {/* Data status bar */}
      <div className="notice" style={{ marginBottom: 14 }}>
        <span>&#9432;</span>
        {dataStatus && dataStatus.stocks_with_data > 0 ? (
          <>
            <strong>HISTORICAL DATA</strong> — {dataStatus.stocks_with_data}/{dataStatus.total_stocks} stocks with{" "}
            {dataStatus.total_bars.toLocaleString()} price bars
            {dataStatus.provider_name && <> · Source: {dataStatus.provider_name}</>}
            {" · "}
            <em>Not live exchange prices</em>
            <button
              className="scr-btn scr-btn-ghost"
              style={{ marginLeft: 12, padding: "2px 8px", fontSize: "0.8em" }}
              onClick={() => handleUpdateData("1y")}
              disabled={updating}
            >
              {updating
                ? `Updating${updateProgress ? ` (${updateProgress.completed_count}/${updateProgress.total})` : "..."}`
                : "↻ Update Data"}
            </button>
          </>
        ) : (
          <>
            DEMONSTRATION DATA — All figures are illustrative. Not current exchange prices.
            {dataStatus?.provider_available && (
              <button
                className="scr-btn scr-btn-ghost"
                style={{ marginLeft: 12, padding: "2px 8px", fontSize: "0.8em" }}
                onClick={() => handleUpdateData("1y")}
                disabled={updating}
              >
                {updating ? "Downloading..." : "⬇ Download Historical Data"}
              </button>
            )}
          </>
        )}
      </div>

      {/* Presets dropdown */}
      {showPresets && presets.length > 0 && (
        <div className="presets-dropdown">
          <div className="presets-title">Saved Strategies</div>
          {presets.map((p) => (
            <div key={p.id} className="preset-item">
              <div className="preset-info" onClick={() => loadPreset(p)}>
                <strong>{p.name}</strong>
                {p.description && <small>{p.description}</small>}
              </div>
              <button className="preset-del" onClick={() => handleDeletePreset(p.id)} title="Delete">×</button>
            </div>
          ))}
        </div>
      )}

      {/* Save modal */}
      {showSaveModal && (
        <div className="scr-modal-overlay" onClick={() => setShowSaveModal(false)}>
          <div className="scr-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Save Screening Strategy</h3>
            <input
              className="scr-input"
              placeholder="Strategy name"
              value={presetName}
              onChange={(e) => setPresetName(e.target.value)}
              autoFocus
            />
            <input
              className="scr-input"
              placeholder="Description (optional)"
              value={presetDesc}
              onChange={(e) => setPresetDesc(e.target.value)}
            />
            <div className="scr-modal-actions">
              <button className="scr-btn scr-btn-ghost" onClick={() => setShowSaveModal(false)}>Cancel</button>
              <button className="scr-btn scr-btn-primary" onClick={handleSavePreset}>Save</button>
            </div>
          </div>
        </div>
      )}

      <div className="screener-body">
        {/* LEFT: Filter panel */}
        <aside className="filter-panel">
          {/* Universe */}
          <div className="filter-section">
            <div className="filter-section-title">Stock Universe</div>
            <div className="filter-grid">
              <div className="filter-field">
                <label>Exchange</label>
                <select
                  className="scr-select"
                  value={filters.exchange || ""}
                  onChange={(e) => setFilter("exchange", e.target.value)}
                >
                  <option value="">All</option>
                  {(metadata?.exchanges || ["NSE", "BSE"]).map((ex) => (
                    <option key={ex} value={ex}>{ex}</option>
                  ))}
                </select>
              </div>
              <div className="filter-field">
                <label>Category</label>
                <select
                  className="scr-select"
                  value={filters.cap_category || ""}
                  onChange={(e) => setFilter("cap_category", e.target.value)}
                >
                  <option value="">All Caps</option>
                  <option value="large_cap">Large Cap</option>
                  <option value="mid_cap">Mid Cap</option>
                  <option value="small_cap">Small Cap</option>
                </select>
              </div>
              <div className="filter-field">
                <label>Sector</label>
                <select
                  className="scr-select"
                  value={filters.sector || ""}
                  onChange={(e) => setFilter("sector", e.target.value)}
                >
                  <option value="">All Sectors</option>
                  {(metadata?.sectors || []).map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
              <div className="filter-field">
                <label>Search</label>
                <input
                  className="scr-input"
                  placeholder="Name or symbol..."
                  value={filters.search || ""}
                  onChange={(e) => setFilter("search", e.target.value)}
                />
              </div>
            </div>
          </div>

          {/* Fundamental filters */}
          <div className="filter-section">
            <div
              className="filter-section-title clickable"
              onClick={() => setExpandFundamental(!expandFundamental)}
            >
              Fundamental Filters
              <span className="section-toggle">{expandFundamental ? "▾" : "▸"}</span>
            </div>
            {expandFundamental && (
              <div className="filter-grid">
                <RangeFilter label="Market Cap (₹ Cr)" minKey="min_market_cap_cr" maxKey="max_market_cap_cr" filters={filters} setFilter={setFilter} />
                <RangeFilter label="Price (₹)" minKey="min_price" maxKey="max_price" filters={filters} setFilter={setFilter} />
                <RangeFilter label="P/E Ratio" minKey="min_pe" maxKey="max_pe" filters={filters} setFilter={setFilter} />
                <RangeFilter label="P/B Ratio" minKey="min_pb" maxKey="max_pb" filters={filters} setFilter={setFilter} />
                <RangeFilter label="ROE (%)" minKey="min_roe" maxKey="max_roe" filters={filters} setFilter={setFilter} />
                <RangeFilter label="ROCE (%)" minKey="min_roce" maxKey="max_roce" filters={filters} setFilter={setFilter} />
                <RangeFilter label="Debt/Equity" minKey="min_debt_equity" maxKey="max_debt_equity" filters={filters} setFilter={setFilter} />
                <RangeFilter label="Revenue Growth (%)" minKey="min_revenue_growth" maxKey="max_revenue_growth" filters={filters} setFilter={setFilter} />
                <RangeFilter label="Profit Growth (%)" minKey="min_profit_growth" maxKey="max_profit_growth" filters={filters} setFilter={setFilter} />
                <RangeFilter label="OPM (%)" minKey="min_opm" maxKey="max_opm" filters={filters} setFilter={setFilter} />
                <SingleFilter label="Min Promoter Hold (%)" filterKey="min_promoter_holding" filters={filters} setFilter={setFilter} />
                <SingleFilter label="Max Promoter Pledge (%)" filterKey="max_promoter_pledging" filters={filters} setFilter={setFilter} />
                <SingleFilter label="Min FII Holding (%)" filterKey="min_fii_holding" filters={filters} setFilter={setFilter} />
                <SingleFilter label="Min DII Holding (%)" filterKey="min_dii_holding" filters={filters} setFilter={setFilter} />
                <SingleFilter label="Min Quality Score (0-100)" filterKey="min_quality_score" filters={filters} setFilter={setFilter} />
                <SingleFilter label="Min 3Y Rev CAGR (%)" filterKey="min_revenue_cagr_3y" filters={filters} setFilter={setFilter} />
                <SingleFilter label="Min 3Y PAT CAGR (%)" filterKey="min_pat_cagr_3y" filters={filters} setFilter={setFilter} />
                <SingleFilter label="Min CFO / PAT" filterKey="min_cfo_pat_ratio" filters={filters} setFilter={setFilter} />
                <SingleFilter label="Min Interest Coverage" filterKey="min_interest_coverage" filters={filters} setFilter={setFilter} />
                <SingleFilter label="Max PEG Ratio" filterKey="max_peg" filters={filters} setFilter={setFilter} />
              </div>
            )}
          </div>

          {/* Technical filters */}
          <div className="filter-section">
            <div
              className="filter-section-title clickable"
              onClick={() => setExpandTechnical(!expandTechnical)}
            >
              Technical Filters
              <span className="section-toggle">{expandTechnical ? "▾" : "▸"}</span>
            </div>
            {expandTechnical && (
              <div className="filter-grid">
                <RangeFilter label="RSI (14)" minKey="min_rsi" maxKey="max_rsi" filters={filters} setFilter={setFilter} />
                <SingleFilter label="Min ADX" filterKey="min_adx" filters={filters} setFilter={setFilter} />
                <RangeFilter label="Relative Volume" minKey="min_relative_volume" maxKey="max_relative_volume" filters={filters} setFilter={setFilter} />
                <RangeFilter label="1M Return (%)" minKey="min_return_1m" maxKey="max_return_1m" filters={filters} setFilter={setFilter} />
                <RangeFilter label="3M Return (%)" minKey="min_return_3m" maxKey="max_return_3m" filters={filters} setFilter={setFilter} />
                <RangeFilter label="1Y Return (%)" minKey="min_return_1y" maxKey="max_return_1y" filters={filters} setFilter={setFilter} />
              </div>
            )}
          </div>

          {/* Advanced filter builder toggle */}
          <div className="filter-section">
            <button
              className="scr-btn scr-btn-outline full-width"
              onClick={() => {
                setShowAdvanced(!showAdvanced);
                if (!showAdvanced && groups.length === 0) {
                  setGroups([emptyGroup()]);
                }
              }}
            >
              {showAdvanced ? "Hide" : "Show"} Advanced Filter Builder
            </button>
          </div>

          {/* Advanced builder */}
          {showAdvanced && (
            <div className="filter-section advanced-builder">
              <div className="filter-section-title">
                Advanced Conditions
                <small className="section-hint">Groups are AND-joined. Within each group, choose AND or OR.</small>
              </div>
              {groups.map((group, gi) => (
                <div key={group.id} className="condition-group">
                  <div className="group-header">
                    <span className="group-label">Group {gi + 1}</span>
                    <select
                      className="scr-select small"
                      value={group.logic}
                      onChange={(e) => {
                        const updated = [...groups];
                        updated[gi] = { ...group, logic: e.target.value as "AND" | "OR" };
                        setGroups(updated);
                      }}
                    >
                      <option value="AND">AND</option>
                      <option value="OR">OR</option>
                    </select>
                    <button
                      className="group-remove"
                      onClick={() => setGroups(groups.filter((_, i) => i !== gi))}
                      title="Remove group"
                    >×</button>
                  </div>
                  {group.conditions.map((cond, ci) => (
                    <div key={cond.id} className="condition-row">
                      <select
                        className="scr-select"
                        value={cond.field}
                        onChange={(e) => {
                          const updated = [...groups];
                          updated[gi].conditions[ci] = { ...cond, field: e.target.value };
                          setGroups(updated);
                        }}
                      >
                        {ALL_FIELDS.map((f) => (
                          <option key={f.value} value={f.value}>{f.label}</option>
                        ))}
                      </select>
                      <select
                        className="scr-select small"
                        value={cond.operator}
                        onChange={(e) => {
                          const updated = [...groups];
                          updated[gi].conditions[ci] = { ...cond, operator: e.target.value as Operator };
                          setGroups(updated);
                        }}
                      >
                        {OPERATORS.map((o) => (
                          <option key={o.value} value={o.value}>{o.label}</option>
                        ))}
                      </select>
                      <input
                        className="scr-input small"
                        type="number"
                        value={cond.value}
                        onChange={(e) => {
                          const updated = [...groups];
                          updated[gi].conditions[ci] = { ...cond, value: parseFloat(e.target.value) || 0 };
                          setGroups(updated);
                        }}
                      />
                      {cond.operator === "between" && (
                        <>
                          <span className="between-label">to</span>
                          <input
                            className="scr-input small"
                            type="number"
                            value={cond.value2 ?? ""}
                            onChange={(e) => {
                              const updated = [...groups];
                              updated[gi].conditions[ci] = { ...cond, value2: parseFloat(e.target.value) || 0 };
                              setGroups(updated);
                            }}
                          />
                        </>
                      )}
                      <button
                        className="cond-remove"
                        onClick={() => {
                          const updated = [...groups];
                          updated[gi] = {
                            ...group,
                            conditions: group.conditions.filter((_, i) => i !== ci),
                          };
                          setGroups(updated);
                        }}
                        title="Remove condition"
                      >×</button>
                    </div>
                  ))}
                  <button
                    className="scr-btn scr-btn-ghost small"
                    onClick={() => {
                      const updated = [...groups];
                      updated[gi] = {
                        ...group,
                        conditions: [...group.conditions, emptyCondition()],
                      };
                      setGroups(updated);
                    }}
                  >
                    + Add Condition
                  </button>
                </div>
              ))}
              <button
                className="scr-btn scr-btn-outline small"
                onClick={() => setGroups([...groups, emptyGroup()])}
              >
                + Add Group
              </button>
            </div>
          )}

          {/* Run button (bottom of filter panel) */}
          <div className="filter-section">
            <button className="scr-btn scr-btn-primary full-width" onClick={runScreen} disabled={loading}>
              {loading ? "Screening..." : `Screen Stocks${activeFilterCount > 0 ? ` (${activeFilterCount} filters)` : ""}`}
            </button>
          </div>
        </aside>

        {/* RIGHT: Results */}
        <section className="results-panel">
          {error && (
            <div className="scr-error">
              {error}
              <button onClick={() => setError(null)}>×</button>
            </div>
          )}

          {response && (
            <>
              <div className="results-header">
                <span className="results-count">
                  {response.total} stock{response.total !== 1 ? "s" : ""} found
                </span>
                <span className="results-data-mode">
                  Data: <strong className={response.data_mode === "demo" ? "" : "positive"}>
                    {response.data_mode === "demo" ? "DEMO" : "HISTORICAL"}
                  </strong> · Page {response.page}/{response.total_pages}
                </span>
              </div>

              <div className="results-table-wrap">
                <table className="results-table">
                  <thead>
                    <tr>
                      {TABLE_COLUMNS.map((col) => (
                        <th
                          key={col.key}
                          className={`sortable ${col.align === "right" ? "right" : ""}`}
                          onClick={() => handleSort(col.key)}
                        >
                          {col.label}
                          {filters.sort_by === col.key && (
                            <span className="sort-arrow">{filters.sort_order === "asc" ? " ▲" : " ▼"}</span>
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {response.items.length === 0 ? (
                      <tr>
                        <td colSpan={TABLE_COLUMNS.length} className="no-results">
                          No stocks match the current filters. Try relaxing your criteria.
                        </td>
                      </tr>
                    ) : (
                      response.items.map((stock) => (
                        <tr key={stock.symbol}>
                          {TABLE_COLUMNS.map((col) => {
                            const raw = stock[col.key];
                            const display = col.format ? col.format(raw) : (raw ?? "—");
                            const cls = col.colorize ? changeClass(raw as number) : "";
                            return (
                              <td
                                key={col.key}
                                className={`${col.align === "right" ? "right" : ""} ${cls}`}
                              >
                                {col.key === "symbol" ? (
                                  <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                                    <strong
                                      style={{ cursor: onOpenResearch ? "pointer" : "default" }}
                                      onClick={() => onOpenResearch?.(stock.symbol)}
                                    >
                                      {display}
                                    </strong>
                                    {onOpenResearch && (
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          onOpenResearch(stock.symbol);
                                        }}
                                        title="Open in Company Research"
                                        style={{
                                          fontSize: "10px",
                                          padding: "1px 5px",
                                          borderRadius: "4px",
                                          background: "rgba(38, 199, 139, 0.15)",
                                          color: "#26c78b",
                                          border: "1px solid rgba(38, 199, 139, 0.3)",
                                          cursor: "pointer",
                                        }}
                                      >
                                        Research
                                      </button>
                                    )}
                                  </span>
                                ) : (
                                  display
                                )}
                              </td>
                            );
                          })}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              {response.total_pages > 1 && (
                <div className="pagination">
                  <button
                    className="scr-btn scr-btn-ghost"
                    disabled={response.page <= 1}
                    onClick={() => goPage(response.page - 1)}
                  >
                    Previous
                  </button>
                  {Array.from({ length: response.total_pages }, (_, i) => i + 1)
                    .filter((p) => {
                      const curr = response.page;
                      return p === 1 || p === response.total_pages || Math.abs(p - curr) <= 2;
                    })
                    .map((p, idx, arr) => (
                      <span key={p}>
                        {idx > 0 && arr[idx - 1] !== p - 1 && <span className="page-ellipsis">...</span>}
                        <button
                          className={`scr-btn ${p === response.page ? "scr-btn-primary" : "scr-btn-ghost"}`}
                          onClick={() => goPage(p)}
                        >
                          {p}
                        </button>
                      </span>
                    ))}
                  <button
                    className="scr-btn scr-btn-ghost"
                    disabled={response.page >= response.total_pages}
                    onClick={() => goPage(response.page + 1)}
                  >
                    Next
                  </button>
                </div>
              )}
            </>
          )}

          {!response && !loading && !error && (
            <div className="screener-empty">
              <div className="screener-empty-icon">&#x2315;</div>
              <h3>Configure filters and run the screener</h3>
              <p>Use the filter panel on the left to set your screening criteria, then click "Run Screen".</p>
            </div>
          )}

          {loading && !response && (
            <div className="screener-empty">
              <div className="screener-empty-icon loading-spin">&#x25CE;</div>
              <h3>Screening...</h3>
            </div>
          )}
        </section>
      </div>

      <footer className="page-footer">
        <span>STOCK SCREENER</span>
        <span>
          {dataStatus && dataStatus.stocks_with_data > 0
            ? `Historical data · ${dataStatus.provider_name ?? "Yahoo Finance"} · Not live prices`
            : "Illustrative sample data · Not live market data"}
          {" · "}{response?.total ?? 0} results
        </span>
      </footer>

      {/* CSV Import Modal */}
      <CsvImportModal
        isOpen={isCsvModalOpen}
        onClose={() => setIsCsvModalOpen(false)}
        onImportSuccess={() => {
          setIsCsvModalOpen(false);
          runScreen();
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RangeFilter({
  label,
  minKey,
  maxKey,
  filters,
  setFilter,
}: {
  label: string;
  minKey: string;
  maxKey: string;
  filters: ScreenRequest;
  setFilter: (key: string, value: string | number | undefined) => void;
}) {
  const f = filters as Record<string, unknown>;
  const minVal = f[minKey] as number | undefined;
  const maxVal = f[maxKey] as number | undefined;
  return (
    <div className="filter-field range-field">
      <label>{label}</label>
      <div className="range-inputs">
        <input
          className="scr-input"
          type="number"
          placeholder="Min"
          value={minVal ?? ""}
          onChange={(e) => setFilter(minKey, e.target.value === "" ? undefined : parseFloat(e.target.value))}
        />
        <span className="range-dash">—</span>
        <input
          className="scr-input"
          type="number"
          placeholder="Max"
          value={maxVal ?? ""}
          onChange={(e) => setFilter(maxKey, e.target.value === "" ? undefined : parseFloat(e.target.value))}
        />
      </div>
    </div>
  );
}

function SingleFilter({
  label,
  filterKey,
  filters,
  setFilter,
}: {
  label: string;
  filterKey: string;
  filters: ScreenRequest;
  setFilter: (key: string, value: string | number | undefined) => void;
}) {
  const f = filters as Record<string, unknown>;
  const val = f[filterKey] as number | undefined;
  return (
    <div className="filter-field">
      <label>{label}</label>
      <input
        className="scr-input"
        type="number"
        placeholder="Value"
        value={val ?? ""}
        onChange={(e) => setFilter(filterKey, e.target.value === "" ? undefined : parseFloat(e.target.value))}
      />
    </div>
  );
}

import React, { useEffect, useState, useMemo } from "react";
import { fetchCompanyResearch } from "../api/fundamentals";
import type {
  CompanyResearchDossier,
  DeductionDetail,
  Performance1Y,
  RelativeStrengthData,
  DvmScoresData,
  ChecklistSwotData,
  SectorPeersData,
} from "../types/fundamentals";
import CsvImportModal from "./CsvImportModal";

interface CompanyResearchProps {
  initialSymbol?: string;
  onSelectStock?: (symbol: string) => void;
}

export default function CompanyResearch({
  initialSymbol = "TCS",
  onSelectStock,
}: CompanyResearchProps) {
  const [symbol, setSymbol] = useState(initialSymbol);
  const [searchInput, setSearchInput] = useState(initialSymbol);
  const [dossier, setDossier] = useState<CompanyResearchDossier | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeStatementTab, setActiveStatementTab] = useState<
    "quarterly" | "annual" | "balance_sheet" | "cash_flow" | "shareholding"
  >("quarterly");
  const [quarterlyViewMode, setQuarterlyViewMode] = useState<"values" | "yoy" | "qoq">("values");
  const [isCsvModalOpen, setIsCsvModalOpen] = useState(false);
  const [showDeductions, setShowDeductions] = useState(false);
  const [showDvmMethodology, setShowDvmMethodology] = useState(false);

  const loadData = async (sym: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCompanyResearch(sym);
      setDossier(data);
      setSymbol(sym);
      if (onSelectStock) onSelectStock(sym);
    } catch (err: any) {
      setError(err?.message || `Failed to load institutional research for ${sym}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData(initialSymbol);
  }, [initialSymbol]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      loadData(searchInput.trim().toUpperCase());
    }
  };

  const getDvmColor = (cls?: string) => {
    switch (cls) {
      case "Excellent":
        return "text-emerald-400 border-emerald-500/40 bg-emerald-500/10";
      case "Strong":
        return "text-cyan-400 border-cyan-500/40 bg-cyan-500/10";
      case "Moderate":
        return "text-amber-400 border-amber-500/40 bg-amber-500/10";
      case "Weak":
        return "text-rose-400 border-rose-500/40 bg-rose-500/10";
      default:
        return "text-red-500 border-red-500/40 bg-red-500/10";
    }
  };

  const getGradeColor = (grade: string) => {
    if (grade.startsWith("A")) return "text-emerald-400 border-emerald-500/40 bg-emerald-500/10";
    if (grade.startsWith("B")) return "text-cyan-400 border-cyan-500/40 bg-cyan-500/10";
    if (grade.startsWith("C")) return "text-amber-400 border-amber-500/40 bg-amber-500/10";
    return "text-rose-400 border-rose-500/40 bg-rose-500/10";
  };

  const formatNumber = (val?: number | null, decimals = 1, prefix = "", suffix = "") => {
    if (val === null || val === undefined || isNaN(val)) return "—";
    return `${prefix}${val.toLocaleString("en-IN", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })}${suffix}`;
  };

  const ratios = dossier?.calculated_ratios;
  const growth = ratios?.growth;
  const prof = ratios?.profitability;
  const hlth = ratios?.financial_health || (ratios as any)?.health;
  const val = ratios?.valuation;
  const prov = dossier?.provenance;
  const perf1y: Performance1Y | undefined = dossier?.performance_1y || undefined;
  const rsData: RelativeStrengthData | undefined = dossier?.relative_strength || undefined;
  const dvmData: DvmScoresData | undefined = dossier?.dvm_scores || undefined;
  const swotData: ChecklistSwotData | undefined = dossier?.checklist_swot || undefined;
  const sectorPeers: SectorPeersData | undefined = dossier?.sector_peers || undefined;

  // Mini SVG area chart for 1-Year price series
  const render1YChartSvg = () => {
    if (!perf1y?.history_series || perf1y.history_series.length < 5) {
      return (
        <div className="h-28 flex items-center justify-center text-xs text-gray-500 bg-[#0b0e14] rounded-lg border border-gray-800">
          Insufficient 1-year historical candle data.
        </div>
      );
    }

    const series = perf1y.history_series;
    const closes = series.map((s) => s.close);
    const minP = Math.min(...closes);
    const maxP = Math.max(...closes);
    const range = maxP - minP || 1;
    const width = 500;
    const height = 90;
    const padding = 6;

    const points = series.map((s, i) => {
      const x = padding + (i / (series.length - 1)) * (width - 2 * padding);
      const y = height - padding - ((s.close - minP) / range) * (height - 2 * padding);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });

    const isPositive = (perf1y.return_pct ?? 0) >= 0;
    const strokeColor = isPositive ? "#26c78b" : "#f43f5e";
    const fillColor = isPositive ? "rgba(38, 199, 139, 0.15)" : "rgba(244, 63, 94, 0.15)";
    const pathD = `M ${points.join(" L ")}`;
    const areaD = `${pathD} L ${width - padding},${height} L ${padding},${height} Z`;

    return (
      <div className="relative bg-[#0b0e14] rounded-lg p-2 border border-gray-800/80">
        <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-24 overflow-visible">
          <defs>
            <linearGradient id="perf1yGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={strokeColor} stopOpacity="0.3" />
              <stop offset="100%" stopColor={strokeColor} stopOpacity="0.0" />
            </linearGradient>
          </defs>
          <path d={areaD} fill="url(#perf1yGrad)" />
          <path d={pathD} fill="none" stroke={strokeColor} strokeWidth="1.8" strokeLinecap="round" />
        </svg>
        <div className="flex justify-between items-center text-[10px] text-gray-500 mt-1 font-mono">
          <span>{perf1y.start_date} (₹{perf1y.start_price.toFixed(1)})</span>
          <span>{perf1y.trading_days_analyzed} Days</span>
          <span>{perf1y.end_date} (₹{perf1y.end_price.toFixed(1)})</span>
        </div>
      </div>
    );
  };

  // Quarterly Results Helper for 10 line items
  const quarterlyStatements = useMemo(() => {
    return [...(dossier?.quarterly_income_statements || [])];
  }, [dossier]);

  const quarterlyLineItems = [
    { key: "revenue", label: "Sales / Revenue (₹ Cr)", getter: (s: any) => s.revenue_cr ?? s.revenue_from_operations_cr },
    { key: "opex", label: "Operating Expenses (₹ Cr)", getter: (s: any) => s.operating_expenses_cr ?? s.total_expenses_cr },
    { key: "operating_profit", label: "Operating Profit (₹ Cr)", getter: (s: any) => s.operating_profit_cr ?? s.ebitda_cr },
    { key: "opm", label: "OPM %", getter: (s: any) => s.opm_pct ?? (s.revenue_cr ? ((s.operating_profit_cr ?? s.ebitda_cr) / s.revenue_cr) * 100 : null), suffix: "%" },
    { key: "depreciation", label: "Depreciation (₹ Cr)", getter: (s: any) => s.depreciation_cr },
    { key: "interest", label: "Interest (₹ Cr)", getter: (s: any) => s.interest_expense_cr ?? s.finance_costs_cr },
    { key: "pbt", label: "Profit before tax (₹ Cr)", getter: (s: any) => s.profit_before_tax_cr },
    { key: "tax", label: "Tax Expense (₹ Cr)", getter: (s: any) => s.tax_expense_cr },
    { key: "net_profit", label: "Net Profit (₹ Cr)", getter: (s: any) => s.net_profit_cr, highlight: true },
    { key: "eps", label: "EPS in Rs", getter: (s: any) => s.eps, highlight: true },
  ];

  return (
    <div className="space-y-6 animate-fade-in text-gray-200">
      {/* Top Search & Actions Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-xl bg-[#11141c] border border-gray-800">
        <form onSubmit={handleSearchSubmit} className="flex items-center gap-2">
          <div className="relative">
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value.toUpperCase())}
              placeholder="Search ticker (e.g. TCS, INFY, ETERNAL, BEL, TRENT)..."
              className="bg-[#0b0e14] border border-gray-700 rounded-lg px-3 py-2 text-sm w-80 focus:outline-none focus:border-emerald-500 uppercase tracking-wider font-semibold text-white placeholder-gray-500"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-sm font-semibold transition-colors disabled:opacity-50"
          >
            {loading ? "Loading..." : "Research"}
          </button>
        </form>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsCsvModalOpen(true)}
            className="flex items-center gap-2 px-3 py-2 bg-[#1b2230] hover:bg-[#222b3d] text-emerald-400 border border-emerald-500/30 rounded-lg text-sm font-medium transition-colors"
          >
            <span>📥</span> Import Screener CSV
          </button>
          <button
            onClick={() => loadData(symbol)}
            className="px-3 py-2 bg-[#1b2230] hover:bg-[#222b3d] text-gray-300 border border-gray-700 rounded-lg text-sm font-medium transition-colors"
          >
            ⟳ Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-500/15 border border-rose-500/30 rounded-xl text-rose-300 text-sm">
          {error}
        </div>
      )}

      {loading && !dossier && (
        <div className="text-center py-20 text-gray-400 space-y-2">
          <div className="text-3xl animate-spin">⟳</div>
          <div>Loading institutional research dossier for {symbol}...</div>
        </div>
      )}

      {dossier && (
        <>
          {/* 1. Header Overview: Company Name, Price & PROMINENT RELATIVE STRENGTH BADGE */}
          <div className="p-6 rounded-xl bg-[#11141c] border border-gray-800 space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-3 flex-wrap">
                  <h1 className="text-2xl font-bold text-white tracking-wide">
                    {dossier.company_name}
                  </h1>
                  <span className="text-sm font-semibold px-2 py-0.5 rounded bg-gray-800 text-gray-300 font-mono">
                    {dossier.symbol}
                  </span>
                  {/* Provenance Badge */}
                  <span
                    className={`text-xs px-2.5 py-0.5 rounded-full font-bold uppercase tracking-wider border ${
                      prov?.verification_status === "verified"
                        ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                        : prov?.verification_status === "imported"
                        ? "bg-sky-500/15 text-sky-300 border-sky-500/30"
                        : "bg-gray-700 text-gray-300 border-gray-600"
                    }`}
                  >
                    {prov?.verification_status === "verified"
                      ? "✓ VERIFIED OFFICIAL"
                      : prov?.verification_status === "imported"
                      ? "📥 SCREENER CSV"
                      : "EXCHANGE GROUNDED"}
                  </span>
                  {/* Price Freshness */}
                  {prov?.is_price_stale ? (
                    <span className="text-xs px-2 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 font-medium">
                      ⚠ Stale Price ({prov?.price_date || "> 5d"})
                    </span>
                  ) : (
                    <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-medium">
                      ● Live Market Price
                    </span>
                  )}
                </div>
                <div className="text-sm text-gray-400 mt-1 flex items-center gap-2">
                  <span>{dossier.sector || "General"}</span>
                  {dossier.industry && <span>• {dossier.industry}</span>}
                  {dossier.isin && <span className="text-gray-500 font-mono text-xs">ISIN: {dossier.isin}</span>}
                </div>
              </div>

              {/* Price Snapshot with PROMINENT RELATIVE STRENGTH BADGE IMMEDIATELY BELOW */}
              <div className="text-right flex flex-col items-end">
                <div className="text-3xl font-bold font-mono text-white">
                  ₹{formatNumber(dossier.current_price || dossier.close, 2)}
                </div>
                <div
                  className={`text-sm font-semibold ${
                    (dossier.daily_change_pct ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {(dossier.daily_change_pct ?? 0) >= 0 ? "▲ +" : "▼ "}
                  {formatNumber(dossier.daily_change_pct, 2)}%
                </div>

                {/* Relative Strength (RS) Badge immediately below stock price */}
                {rsData && (
                  <div className="mt-2.5 p-2 rounded-lg bg-[#0b0e14] border border-gray-800 flex flex-col items-end gap-1">
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-gray-400 font-semibold">RS vs {rsData.benchmark_symbol}:</span>
                      <span className="text-xs font-bold font-mono px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                        {rsData.rs_rating.toFixed(1)} / 100
                      </span>
                      <span
                        className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                          rsData.is_outperforming
                            ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                            : "bg-rose-950 text-rose-400 border border-rose-800"
                        }`}
                      >
                        {rsData.rs_status}
                      </span>
                    </div>
                    <div className="text-[10px] text-gray-400 flex items-center gap-2 font-mono">
                      <span>
                        1M Rel:{" "}
                        <strong className={rsData.relative_performance_1m >= 0 ? "text-emerald-400" : "text-rose-400"}>
                          {rsData.relative_performance_1m >= 0 ? "+" : ""}{rsData.relative_performance_1m.toFixed(1)}%
                        </strong>
                      </span>
                      <span>•</span>
                      <span>
                        3M Rel:{" "}
                        <strong className={rsData.relative_performance_3m >= 0 ? "text-emerald-400" : "text-rose-400"}>
                          {rsData.relative_performance_3m >= 0 ? "+" : ""}{rsData.relative_performance_3m.toFixed(1)}%
                        </strong>
                      </span>
                      <span>•</span>
                      <span>
                        12M Rel:{" "}
                        <strong className={rsData.relative_performance_12m >= 0 ? "text-emerald-400" : "text-rose-400"}>
                          {rsData.relative_performance_12m >= 0 ? "+" : ""}{rsData.relative_performance_12m.toFixed(1)}%
                        </strong>
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Quick Metrics Bar */}
            <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-3 pt-3 border-t border-gray-800/80 text-xs">
              <div className="bg-[#0b0e14] p-3 rounded-lg border border-gray-800/60">
                <div className="text-gray-500 font-medium">Market Cap</div>
                <div className="font-semibold text-gray-200 mt-0.5 text-sm">
                  ₹{formatNumber(dossier.market_cap_cr, 0)} Cr
                </div>
              </div>
              <div className="bg-[#0b0e14] p-3 rounded-lg border border-gray-800/60">
                <div className="text-gray-500 font-medium">P/E Ratio</div>
                <div className="font-semibold text-gray-200 mt-0.5 text-sm">
                  {formatNumber(val?.pe, 1, "", "x")}
                </div>
              </div>
              <div className="bg-[#0b0e14] p-3 rounded-lg border border-gray-800/60">
                <div className="text-gray-500 font-medium">ROCE (Avg)</div>
                <div className="font-semibold text-emerald-400 mt-0.5 text-sm">
                  {formatNumber(prof?.roce, 1, "", "%")}
                </div>
              </div>
              <div className="bg-[#0b0e14] p-3 rounded-lg border border-gray-800/60">
                <div className="text-gray-500 font-medium">ROE (Avg)</div>
                <div className="font-semibold text-emerald-400 mt-0.5 text-sm">
                  {formatNumber(prof?.roe, 1, "", "%")}
                </div>
              </div>
              <div className="bg-[#0b0e14] p-3 rounded-lg border border-gray-800/60">
                <div className="text-gray-500 font-medium">Debt / Equity</div>
                <div className="font-semibold text-gray-200 mt-0.5 text-sm">
                  {hlth?.is_debt_free ? (
                    <span className="text-emerald-400">0.0 (Debt Free)</span>
                  ) : (
                    formatNumber(hlth?.debt_equity, 2)
                  )}
                </div>
              </div>
              <div className="bg-[#0b0e14] p-3 rounded-lg border border-gray-800/60">
                <div className="text-gray-500 font-medium">52W Range</div>
                <div className="font-semibold text-gray-200 mt-0.5 text-xs truncate">
                  ₹{formatNumber(dossier.week_52_low, 0)} - ₹{formatNumber(dossier.week_52_high, 0)}
                </div>
              </div>
            </div>
          </div>

          {/* 2. 1-Year Historical Price Performance & 52-Week Range Position */}
          {perf1y && (
            <div className="p-6 rounded-xl bg-[#11141c] border border-gray-800 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <span>📈</span> 1-Year Price Performance & Range Analysis
                  </h2>
                  <p className="text-xs text-gray-400">
                    Calculated over {perf1y.trading_days_analyzed} actual trading days from {perf1y.start_date} to {perf1y.end_date}.
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <span className="text-xs text-gray-400">1-Year Absolute Change: </span>
                    <span className={`font-mono font-bold ${perf1y.absolute_change >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {perf1y.absolute_change >= 0 ? "+" : ""}₹{perf1y.absolute_change.toFixed(2)}
                    </span>
                  </div>
                  <div
                    className={`px-3 py-1 rounded-lg border text-base font-bold font-mono ${
                      perf1y.return_pct >= 0 ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-rose-500/15 text-rose-400 border-rose-500/30"
                    }`}
                  >
                    {perf1y.return_pct >= 0 ? "+" : ""}{perf1y.return_pct.toFixed(2)}%
                  </div>
                </div>
              </div>

              {/* 52-Week Range Progress Bar */}
              <div className="p-4 rounded-xl bg-[#0b0e14] border border-gray-800/80 space-y-2">
                <div className="flex justify-between items-center text-xs">
                  <span className="text-gray-400">52W Low: <strong className="text-white font-mono">₹{perf1y.week_52_low.toFixed(2)}</strong></span>
                  <span className="font-semibold text-emerald-400">
                    Current: ₹{perf1y.end_price.toFixed(2)} ({perf1y.current_position_in_52w_range_pct.toFixed(1)}% of 52W range)
                  </span>
                  <span className="text-gray-400">52W High: <strong className="text-white font-mono">₹{perf1y.week_52_high.toFixed(2)}</strong></span>
                </div>
                <div className="relative w-full h-3 bg-gray-800 rounded-full overflow-hidden">
                  <div
                    className="absolute top-0 bottom-0 left-0 bg-gradient-to-r from-rose-500 via-amber-500 to-emerald-500 rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(100, Math.max(0, perf1y.current_position_in_52w_range_pct))}%` }}
                  />
                </div>
              </div>

              {/* 1-Year SVG Chart */}
              {render1YChartSvg()}
            </div>
          )}

          {/* 3. Original DVM Scoring Engine (Durability, Valuation, Momentum) */}
          {dvmData && (
            <div className="p-6 rounded-xl bg-[#11141c] border border-gray-800 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <span>🛡️</span> Original DVM Scoring Framework
                    <span className="text-xs text-gray-400 font-normal">
                      (Durability • Valuation • Momentum)
                    </span>
                  </h2>
                  <p className="text-xs text-gray-400">
                    Quantitatively weighted: 40% Durability + 30% Valuation + 30% Momentum.
                  </p>
                </div>

                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">
                      Overall Score
                    </div>
                    <div className="text-3xl font-black font-mono text-white">
                      {dvmData.overall_score.toFixed(1)}
                      <span className="text-lg text-gray-500 font-normal">/100</span>
                    </div>
                  </div>
                  <div
                    className={`px-4 py-2 rounded-xl border text-lg font-black tracking-wider ${getDvmColor(
                      dvmData.classification
                    )}`}
                  >
                    {dvmData.classification}
                  </div>
                </div>
              </div>

              {/* 3 Score Dials: Durability, Valuation, Momentum */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {/* Durability */}
                <div className="p-4 rounded-xl bg-[#0b0e14] border border-gray-800/80 space-y-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-bold text-emerald-400 uppercase">Durability (Quality)</span>
                    <span className="font-mono text-lg font-bold text-emerald-400">
                      {dvmData.durability.score.toFixed(1)}/100
                    </span>
                  </div>
                  <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-emerald-500 h-2 rounded-full"
                      style={{ width: `${dvmData.durability.score}%` }}
                    />
                  </div>
                  <p className="text-[11px] text-gray-400">{dvmData.durability.description}</p>
                </div>

                {/* Valuation */}
                <div className="p-4 rounded-xl bg-[#0b0e14] border border-gray-800/80 space-y-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-bold text-amber-400 uppercase">Valuation (Attractiveness)</span>
                    <span className="font-mono text-lg font-bold text-amber-400">
                      {dvmData.valuation.score.toFixed(1)}/100
                    </span>
                  </div>
                  <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-amber-500 h-2 rounded-full"
                      style={{ width: `${dvmData.valuation.score}%` }}
                    />
                  </div>
                  <p className="text-[11px] text-gray-400">{dvmData.valuation.description}</p>
                </div>

                {/* Momentum */}
                <div className="p-4 rounded-xl bg-[#0b0e14] border border-gray-800/80 space-y-2">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-bold text-cyan-400 uppercase">Momentum (Technical & Flow)</span>
                    <span className="font-mono text-lg font-bold text-cyan-400">
                      {dvmData.momentum.score.toFixed(1)}/100
                    </span>
                  </div>
                  <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-cyan-500 h-2 rounded-full"
                      style={{ width: `${dvmData.momentum.score}%` }}
                    />
                  </div>
                  <p className="text-[11px] text-gray-400">{dvmData.momentum.description}</p>
                </div>
              </div>

              {/* Methodology Audit Toggle */}
              <div className="pt-2 border-t border-gray-800/80">
                <button
                  onClick={() => setShowDvmMethodology(!showDvmMethodology)}
                  className="flex items-center justify-between w-full text-xs font-semibold text-gray-400 hover:text-white transition-colors"
                >
                  <span className="flex items-center gap-1.5 text-cyan-400">
                    <span>🔬</span> View DVM Scoring Component Audit & Weights
                  </span>
                  <span>{showDvmMethodology ? "▲ Hide Audit" : "▼ Show Audit"}</span>
                </button>

                {showDvmMethodology && (
                  <div className="mt-3 p-4 rounded-xl bg-[#0b0e14] border border-gray-800 text-xs space-y-4 font-mono">
                    <div className="text-gray-400">
                      Formula: <strong className="text-white">{dvmData.methodology_audit.formula}</strong>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                      {/* Durability Breakdown */}
                      <div className="space-y-2">
                        <div className="text-emerald-400 font-bold border-b border-gray-800 pb-1">Durability Breakdown</div>
                        {dvmData.durability.components.map((c, i) => (
                          <div key={i} className="text-[11px] flex justify-between">
                            <span className="text-gray-400">{c.metric} ({c.weight_pct}%):</span>
                            <span className="text-emerald-400 font-bold">{c.score.toFixed(1)} pts</span>
                          </div>
                        ))}
                      </div>

                      {/* Valuation Breakdown */}
                      <div className="space-y-2">
                        <div className="text-amber-400 font-bold border-b border-gray-800 pb-1">Valuation Breakdown</div>
                        {dvmData.valuation.components.map((c, i) => (
                          <div key={i} className="text-[11px] flex justify-between">
                            <span className="text-gray-400">{c.metric} ({c.weight_pct}%):</span>
                            <span className="text-amber-400 font-bold">{c.score.toFixed(1)} pts</span>
                          </div>
                        ))}
                      </div>

                      {/* Momentum Breakdown */}
                      <div className="space-y-2">
                        <div className="text-cyan-400 font-bold border-b border-gray-800 pb-1">Momentum Breakdown</div>
                        {dvmData.momentum.components.map((c, i) => (
                          <div key={i} className="text-[11px] flex justify-between">
                            <span className="text-gray-400">{c.metric} ({c.weight_pct}%):</span>
                            <span className="text-cyan-400 font-bold">{c.score.toFixed(1)} pts</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* 4. Automated Fundamental Checklist & SWOT Analysis */}
          {swotData && (
            <div className="p-6 rounded-xl bg-[#11141c] border border-gray-800 space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <span>📋</span> Fundamental Checklist & SWOT Synthesis
                  </h2>
                  <p className="text-xs text-gray-400">
                    Algorithmic 9-point quality checklist with grounded financial strengths and risks.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">Passed:</span>
                  <span className="px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-bold text-xs border border-emerald-500/30">
                    {swotData.passed_count} / {swotData.total_criteria} ({swotData.pass_percentage.toFixed(0)}%)
                  </span>
                </div>
              </div>

              {/* 9-Point Checklist Grid */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {swotData.checklist.map((item) => (
                  <div
                    key={item.id}
                    className={`p-3 rounded-lg border text-xs space-y-1.5 ${
                      item.status === "PASSED"
                        ? "bg-emerald-950/20 border-emerald-500/30"
                        : item.status === "FAILED"
                        ? "bg-rose-950/20 border-rose-500/30"
                        : "bg-gray-900 border-gray-800"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white flex items-center gap-1.5">
                        <span>{item.status === "PASSED" ? "✓" : item.status === "FAILED" ? "✕" : "○"}</span>
                        {item.title}
                      </span>
                      <span
                        className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                          item.status === "PASSED"
                            ? "bg-emerald-500/20 text-emerald-400"
                            : item.status === "FAILED"
                            ? "bg-rose-500/20 text-rose-400"
                            : "bg-gray-800 text-gray-400"
                        }`}
                      >
                        {item.status}
                      </span>
                    </div>
                    <div className="text-gray-400 text-[11px]">{item.criterion}</div>
                    <div className="font-mono text-gray-300 text-[11px]">
                      Value: <strong className="text-white">{item.observed_value}</strong>
                    </div>
                  </div>
                ))}
              </div>

              {/* 4-Quadrant SWOT */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                {/* Strengths */}
                <div className="p-4 rounded-xl bg-[#0b0e14] border border-emerald-500/30 space-y-2">
                  <div className="text-xs font-bold text-emerald-400 flex items-center gap-1.5 uppercase">
                    <span>💪</span> Strengths ({swotData.swot.strengths.length})
                  </div>
                  <ul className="space-y-1.5 text-xs text-gray-300">
                    {swotData.swot.strengths.map((s, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-emerald-500 font-bold">•</span>
                        <span>{s}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Weaknesses */}
                <div className="p-4 rounded-xl bg-[#0b0e14] border border-rose-500/30 space-y-2">
                  <div className="text-xs font-bold text-rose-400 flex items-center gap-1.5 uppercase">
                    <span>⚠️</span> Weaknesses ({swotData.swot.weaknesses.length})
                  </div>
                  <ul className="space-y-1.5 text-xs text-gray-300">
                    {swotData.swot.weaknesses.map((w, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-rose-500 font-bold">•</span>
                        <span>{w}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Opportunities */}
                <div className="p-4 rounded-xl bg-[#0b0e14] border border-sky-500/30 space-y-2">
                  <div className="text-xs font-bold text-sky-400 flex items-center gap-1.5 uppercase">
                    <span>🚀</span> Opportunities ({swotData.swot.opportunities.length})
                  </div>
                  <ul className="space-y-1.5 text-xs text-gray-300">
                    {swotData.swot.opportunities.map((o, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-sky-500 font-bold">•</span>
                        <span>{o}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Threats */}
                <div className="p-4 rounded-xl bg-[#0b0e14] border border-amber-500/30 space-y-2">
                  <div className="text-xs font-bold text-amber-400 flex items-center gap-1.5 uppercase">
                    <span>⚡</span> Threats & Risks ({swotData.swot.threats.length})
                  </div>
                  <ul className="space-y-1.5 text-xs text-gray-300">
                    {swotData.swot.threats.map((t, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-amber-500 font-bold">•</span>
                        <span>{t}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* 5. Advanced Financial Statements (Matching Reference Screenshot 2: Sticky Metric Column) */}
          <div className="p-6 rounded-xl bg-[#11141c] border border-gray-800 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-gray-800 pb-3">
              <div>
                <h2 className="text-lg font-bold text-white flex items-center gap-2">
                  <span>📑</span> Financial Statements & Multi-Quarter Results
                </h2>
                <p className="text-xs text-gray-400">
                  Fixed metric labels on horizontal scroll with YoY & QoQ growth toggles.
                </p>
              </div>

              {/* Statement Tabs & Growth Toggles */}
              <div className="flex flex-wrap items-center gap-3">
                {activeStatementTab === "quarterly" && (
                  <div className="flex bg-[#0b0e14] p-1 rounded-lg border border-gray-800 text-xs">
                    {(["values", "yoy", "qoq"] as const).map((mode) => (
                      <button
                        key={mode}
                        onClick={() => setQuarterlyViewMode(mode)}
                        className={`px-2.5 py-1 rounded font-semibold uppercase text-[11px] transition-colors ${
                          quarterlyViewMode === mode
                            ? "bg-emerald-600 text-white"
                            : "text-gray-400 hover:text-white"
                        }`}
                      >
                        {mode === "values" ? "Values" : mode === "yoy" ? "YoY %" : "QoQ %"}
                      </button>
                    ))}
                  </div>
                )}

                <div className="flex gap-1.5">
                  {[
                    { id: "quarterly", label: "Quarterly Results" },
                    { id: "annual", label: "Annual P&L" },
                    { id: "balance_sheet", label: "Balance Sheet" },
                    { id: "cash_flow", label: "Cash Flows" },
                    { id: "shareholding", label: "Shareholding" },
                  ].map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => setActiveStatementTab(tab.id as any)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                        activeStatementTab === tab.id
                          ? "bg-emerald-600 text-white"
                          : "bg-[#0b0e14] text-gray-400 hover:text-gray-200 border border-gray-800"
                      }`}
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* A. Advanced Quarterly Table (Sticky Left Column) */}
            {activeStatementTab === "quarterly" && (
              <div className="overflow-x-auto relative">
                <table className="w-full text-xs text-left border-collapse">
                  <thead className="bg-[#0b0e14] text-gray-400 uppercase font-semibold border-b border-gray-800">
                    <tr>
                      <th className="py-3 px-4 sticky left-0 bg-[#0e131d] z-20 shadow-md min-w-[200px]">
                        Metric
                      </th>
                      {quarterlyStatements.map((q, idx) => (
                        <th key={idx} className="py-3 px-4 text-right min-w-[110px] font-mono">
                          {q.period}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60 font-mono">
                    {quarterlyStatements.length === 0 ? (
                      <tr>
                        <td colSpan={10} className="py-8 text-center text-gray-500 font-sans">
                          No quarterly results statements available for {symbol}.
                        </td>
                      </tr>
                    ) : (
                      quarterlyLineItems.map((item) => (
                        <tr key={item.key} className="hover:bg-gray-800/30">
                          {/* STICKY COLUMN: Metric Name fixed on left during horizontal scroll */}
                          <td
                            className={`py-2.5 px-4 sticky left-0 bg-[#0e131d] z-10 font-sans shadow-md border-r border-gray-800/80 ${
                              item.highlight ? "font-bold text-white" : "text-gray-300 font-medium"
                            }`}
                          >
                            {item.label}
                          </td>

                          {quarterlyStatements.map((q, idx) => {
                            const rawVal = item.getter(q);

                            if (quarterlyViewMode === "values") {
                              return (
                                <td
                                  key={idx}
                                  className={`py-2.5 px-4 text-right ${
                                    item.highlight ? "font-bold text-emerald-400" : "text-gray-200"
                                  }`}
                                >
                                  {rawVal !== null && rawVal !== undefined
                                    ? `${rawVal.toLocaleString("en-IN", { maximumFractionDigits: 2 })}${item.suffix || ""}`
                                    : "—"}
                                </td>
                              );
                            }

                            // Growth Calculation (YoY: idx + 4, QoQ: idx + 1)
                            const compareIdx = quarterlyViewMode === "yoy" ? idx + 4 : idx + 1;
                            const prevStmt = quarterlyStatements[compareIdx];
                            const prevVal = prevStmt ? item.getter(prevStmt) : null;

                            if (rawVal == null || prevVal == null || prevVal === 0) {
                              return (
                                <td key={idx} className="py-2.5 px-4 text-right text-gray-500">
                                  —
                                </td>
                              );
                            }

                            const growthPct = ((rawVal - prevVal) / Math.abs(prevVal)) * 100;
                            const isPos = growthPct >= 0;

                            return (
                              <td
                                key={idx}
                                className={`py-2.5 px-4 text-right font-semibold ${
                                  isPos ? "text-emerald-400" : "text-rose-400"
                                }`}
                              >
                                {isPos ? "+" : ""}{growthPct.toFixed(1)}%
                              </td>
                            );
                          })}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {/* B. Annual Income Statements */}
            {activeStatementTab === "annual" && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-[#0b0e14] text-gray-400 uppercase font-semibold border-b border-gray-800">
                    <tr>
                      <th className="py-2.5 px-3">Period</th>
                      <th className="py-2.5 px-3 text-right">Revenue (₹ Cr)</th>
                      <th className="py-2.5 px-3 text-right">Expenses (₹ Cr)</th>
                      <th className="py-2.5 px-3 text-right">EBITDA (₹ Cr)</th>
                      <th className="py-2.5 px-3 text-right">OPM %</th>
                      <th className="py-2.5 px-3 text-right">Interest (₹ Cr)</th>
                      <th className="py-2.5 px-3 text-right">Depreciation</th>
                      <th className="py-2.5 px-3 text-right">Net Profit (₹ Cr)</th>
                      <th className="py-2.5 px-3 text-right">EPS (₹)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60 font-mono">
                    {dossier.annual_income_statements.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="py-6 text-center text-gray-500 font-sans">
                          No annual income statements available.
                        </td>
                      </tr>
                    ) : (
                      dossier.annual_income_statements.map((stmt, idx) => (
                        <tr key={idx} className="hover:bg-gray-800/30">
                          <td className="py-2.5 px-3 font-semibold text-gray-200 font-sans">
                            {stmt.period}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            {formatNumber(stmt.revenue_from_operations_cr ?? (stmt as any).revenue_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-400">
                            {formatNumber(stmt.total_expenses_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-emerald-400">
                            {formatNumber(stmt.ebitda_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            {formatNumber(stmt.opm_pct, 1, "", "%")}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-400">
                            {formatNumber(stmt.finance_costs_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-400">
                            {formatNumber(stmt.depreciation_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right font-bold text-emerald-400">
                            {formatNumber(stmt.net_profit_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-200">
                            {formatNumber(stmt.eps, 1)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {/* C. Balance Sheet */}
            {activeStatementTab === "balance_sheet" && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-[#0b0e14] text-gray-400 uppercase font-semibold border-b border-gray-800">
                    <tr>
                      <th className="py-2.5 px-3">Period</th>
                      <th className="py-2.5 px-3 text-right">Equity Capital</th>
                      <th className="py-2.5 px-3 text-right">Reserves</th>
                      <th className="py-2.5 px-3 text-right">Total Equity</th>
                      <th className="py-2.5 px-3 text-right">Borrowings / Debt</th>
                      <th className="py-2.5 px-3 text-right">Total Assets</th>
                      <th className="py-2.5 px-3 text-right">Book Value / Share</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60 font-mono">
                    {dossier.balance_sheets.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-6 text-center text-gray-500 font-sans">
                          No balance sheet records available.
                        </td>
                      </tr>
                    ) : (
                      dossier.balance_sheets.map((bs, idx) => (
                        <tr key={idx} className="hover:bg-gray-800/30">
                          <td className="py-2.5 px-3 font-semibold text-gray-200 font-sans">
                            {bs.period}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-300">
                            {formatNumber(bs.share_capital_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-300">
                            {formatNumber(bs.reserves_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right font-semibold text-emerald-400">
                            {formatNumber(bs.total_equity_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-amber-400">
                            {formatNumber(bs.borrowings_cr ?? bs.total_debt_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right font-bold text-gray-200">
                            {formatNumber(bs.total_assets_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-200">
                            ₹{formatNumber(bs.book_value_per_share, 1)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {/* D. Cash Flows */}
            {activeStatementTab === "cash_flow" && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-[#0b0e14] text-gray-400 uppercase font-semibold border-b border-gray-800">
                    <tr>
                      <th className="py-2.5 px-3">Period</th>
                      <th className="py-2.5 px-3 text-right">Operating Cash Flow (CFO)</th>
                      <th className="py-2.5 px-3 text-right">Capex</th>
                      <th className="py-2.5 px-3 text-right">Free Cash Flow (FCF)</th>
                      <th className="py-2.5 px-3 text-right">Investing Cash Flow</th>
                      <th className="py-2.5 px-3 text-right">Financing Cash Flow</th>
                      <th className="py-2.5 px-3 text-right">Net Cash Flow</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60 font-mono">
                    {dossier.cash_flows.length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-6 text-center text-gray-500 font-sans">
                          No cash flow records available.
                        </td>
                      </tr>
                    ) : (
                      dossier.cash_flows.map((cf, idx) => (
                        <tr key={idx} className="hover:bg-gray-800/30">
                          <td className="py-2.5 px-3 font-semibold text-gray-200 font-sans">
                            {cf.period}
                          </td>
                          <td className="py-2.5 px-3 text-right font-bold text-emerald-400">
                            {formatNumber(cf.operating_cash_flow_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-400">
                            {formatNumber(cf.capex_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right font-bold text-emerald-400">
                            {formatNumber(cf.free_cash_flow_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-400">
                            {formatNumber(cf.investing_cash_flow_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-400">
                            {formatNumber(cf.financing_cash_flow_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-200">
                            {formatNumber(cf.net_cash_flow_cr, 0)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {/* E. Shareholding */}
            {activeStatementTab === "shareholding" && (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-[#0b0e14] text-gray-400 uppercase font-semibold border-b border-gray-800">
                    <tr>
                      <th className="py-2.5 px-3">Period</th>
                      <th className="py-2.5 px-3 text-right">Promoter %</th>
                      <th className="py-2.5 px-3 text-right">Pledged %</th>
                      <th className="py-2.5 px-3 text-right">FII %</th>
                      <th className="py-2.5 px-3 text-right">DII %</th>
                      <th className="py-2.5 px-3 text-right">Public %</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60 font-mono">
                    {dossier.shareholding.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-6 text-center text-gray-500 font-sans">
                          No shareholding pattern records available.
                        </td>
                      </tr>
                    ) : (
                      dossier.shareholding.map((sh, idx) => (
                        <tr key={idx} className="hover:bg-gray-800/30">
                          <td className="py-2.5 px-3 font-semibold text-gray-200 font-sans">
                            {sh.period}
                          </td>
                          <td className="py-2.5 px-3 text-right font-bold text-gray-200">
                            {formatNumber(sh.promoter_holding, 2, "", "%")}
                          </td>
                          <td className="py-2.5 px-3 text-right text-amber-400">
                            {formatNumber(sh.promoter_pledging, 2, "", "%")}
                          </td>
                          <td className="py-2.5 px-3 text-right text-sky-400">
                            {formatNumber(sh.fii_holding, 2, "", "%")}
                          </td>
                          <td className="py-2.5 px-3 text-right text-indigo-400">
                            {formatNumber(sh.dii_holding, 2, "", "%")}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-400">
                            {formatNumber(sh.public_holding, 2, "", "%")}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* 6. Sector Peer Comparison Matrix with DVM & Valuation Multiples */}
          {sectorPeers && sectorPeers.peers.length > 0 && (
            <div className="p-6 rounded-xl bg-[#11141c] border border-gray-800 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <span>⚔</span> Sector Peer Comparison Matrix
                    <span className="text-xs text-gray-400 font-normal">
                      ({sectorPeers.sector} Sector • {sectorPeers.peer_count} Companies)
                    </span>
                  </h2>
                  <p className="text-xs text-gray-400">
                    Comprehensive cross-sectional comparison across valuation, margins, growth, and DVM scores.
                  </p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-[#0b0e14] text-gray-400 uppercase font-semibold border-b border-gray-800">
                    <tr>
                      <th className="py-2.5 px-3">Company</th>
                      <th className="py-2.5 px-3 text-right">Price (₹)</th>
                      <th className="py-2.5 px-3 text-right">1D %</th>
                      <th className="py-2.5 px-3 text-right">Mkt Cap (₹ Cr)</th>
                      <th className="py-2.5 px-3 text-right">P/E</th>
                      <th className="py-2.5 px-3 text-right">P/B</th>
                      <th className="py-2.5 px-3 text-right">ROE %</th>
                      <th className="py-2.5 px-3 text-right">ROCE %</th>
                      <th className="py-2.5 px-3 text-right">OPM %</th>
                      <th className="py-2.5 px-3 text-right">D/E</th>
                      <th className="py-2.5 px-3 text-right">DVM Score</th>
                      <th className="py-2.5 px-3 text-right">Rating</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60 font-mono">
                    {sectorPeers.peers.map((p) => {
                      const isCurrent = p.symbol === dossier.symbol;
                      return (
                        <tr
                          key={p.symbol}
                          onClick={() => {
                            setSearchInput(p.symbol);
                            loadData(p.symbol);
                          }}
                          className={`cursor-pointer transition-colors ${
                            isCurrent
                              ? "bg-emerald-950/30 hover:bg-emerald-900/40 font-bold"
                              : "hover:bg-gray-800/40"
                          }`}
                        >
                          <td className="py-2.5 px-3 font-sans">
                            <span className={isCurrent ? "text-emerald-400 font-bold" : "text-white"}>
                              {p.company_name}
                            </span>
                            <span className="text-gray-500 font-mono text-[10px] ml-1.5">
                              ({p.symbol})
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-200">
                            ₹{formatNumber(p.close, 1)}
                          </td>
                          <td
                            className={`py-2.5 px-3 text-right font-bold ${
                              p.daily_change_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                            }`}
                          >
                            {p.daily_change_pct >= 0 ? "+" : ""}{formatNumber(p.daily_change_pct, 2)}%
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-300">
                            {formatNumber(p.market_cap_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-300">
                            {formatNumber(p.pe, 1)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-300">
                            {formatNumber(p.pb, 1)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-emerald-400">
                            {formatNumber(p.roe, 1, "", "%")}
                          </td>
                          <td className="py-2.5 px-3 text-right text-emerald-400">
                            {formatNumber(p.roce, 1, "", "%")}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-200">
                            {formatNumber(p.opm_pct, 1, "", "%")}
                          </td>
                          <td className="py-2.5 px-3 text-right text-gray-300">
                            {formatNumber(p.debt_equity, 2)}
                          </td>
                          <td className="py-2.5 px-3 text-right font-bold text-white">
                            {formatNumber(p.dvm_overall, 1)}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            <span
                              className={`px-2 py-0.5 rounded text-[11px] font-bold ${getDvmColor(
                                p.dvm_classification || ""
                              )}`}
                            >
                              {p.dvm_classification || "—"}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* CSV Import Modal */}
      <CsvImportModal
        isOpen={isCsvModalOpen}
        onClose={() => setIsCsvModalOpen(false)}
        defaultSymbol={symbol}
        onImportSuccess={() => {
          setIsCsvModalOpen(false);
          loadData(symbol);
        }}
      />
    </div>
  );
}

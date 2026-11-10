import React, { useEffect, useState } from "react";
import { fetchCompanyResearch } from "../api/fundamentals";
import type {
  CompanyResearchDossier,
  DeductionDetail,
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
    "annual" | "quarterly" | "balance_sheet" | "cash_flow" | "shareholding"
  >("annual");
  const [isCsvModalOpen, setIsCsvModalOpen] = useState(false);
  const [showDeductions, setShowDeductions] = useState(true);

  const loadData = async (sym: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCompanyResearch(sym);
      setDossier(data);
      setSymbol(sym);
      if (onSelectStock) onSelectStock(sym);
    } catch (err: any) {
      setError(err?.message || `Failed to load data for ${sym}`);
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

  const getGradeColor = (grade: string) => {
    if (grade.startsWith("A")) return "text-emerald-400 border-emerald-500/40 bg-emerald-500/10";
    if (grade.startsWith("B")) return "text-cyan-400 border-cyan-500/40 bg-cyan-500/10";
    if (grade.startsWith("C")) return "text-amber-400 border-amber-500/40 bg-amber-500/10";
    return "text-rose-400 border-rose-500/40 bg-rose-500/10";
  };

  const ratios = dossier?.calculated_ratios;
  const growth = ratios?.growth;
  const prof = ratios?.profitability;
  const hlth = ratios?.financial_health || (ratios as any)?.health;
  const val = ratios?.valuation;
  const prov = dossier?.provenance;

  const formatNumber = (val?: number | null, decimals = 1, prefix = "", suffix = "") => {
    if (val === null || val === undefined || isNaN(val)) return "—";
    return `${prefix}${val.toLocaleString("en-IN", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })}${suffix}`;
  };

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
              placeholder="Search ticker (e.g. TCS, INFY, RELIANCE)..."
              className="bg-[#0b0e14] border border-gray-700 rounded-lg px-3 py-2 text-sm w-72 focus:outline-none focus:border-emerald-500 uppercase tracking-wider font-semibold text-white placeholder-gray-500"
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
          {/* Company Overview Header */}
          <div className="p-6 rounded-xl bg-[#11141c] border border-gray-800 space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <div className="flex items-center gap-3">
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
                      : "DEMO DATA"}
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

              {/* Price Snapshot */}
              <div className="text-right">
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

          {/* 100-Point Fundamental Quality Score Card */}
          {dossier.quality_score && (
            <div className="p-6 rounded-xl bg-[#11141c] border border-gray-800 space-y-5">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <span>🏆</span> Fundamental Quality Score
                    <span className="text-xs text-gray-400 font-normal">
                      (Institutional 100-Point Framework)
                    </span>
                  </h2>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {dossier.quality_score.summary_verdict}
                  </p>
                </div>

                {/* Big Score Gauge */}
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <div className="text-xs text-gray-400 uppercase tracking-wider font-semibold">
                      Quality Score
                    </div>
                    <div className="text-3xl font-black font-mono text-white">
                      {dossier.quality_score.total_score ?? "—"}
                      <span className="text-lg text-gray-500 font-normal">/100</span>
                    </div>
                  </div>
                  <div
                    className={`px-4 py-2 rounded-xl border text-xl font-black tracking-wider ${getGradeColor(
                      dossier.quality_score.grade
                    )}`}
                  >
                    {dossier.quality_score.grade}
                  </div>
                </div>
              </div>

              {/* 6 Category Score Bars */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
                {Object.entries(dossier.quality_score.category_scores).map(([key, cat]) => (
                  <div
                    key={key}
                    className="p-3.5 bg-[#0b0e14] rounded-lg border border-gray-800/80 space-y-2"
                  >
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-semibold text-gray-300">{cat.category}</span>
                      <span className="font-mono text-emerald-400 font-bold">
                        {cat.points_awarded.toFixed(1)} / {cat.max_points} pts
                      </span>
                    </div>
                    {/* Progress Bar */}
                    <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-emerald-500 h-2 rounded-full transition-all duration-500"
                        style={{ width: `${Math.min(100, Math.max(0, cat.percentage))}%` }}
                      />
                    </div>
                    <div className="text-[11px] text-gray-500 truncate">{cat.description}</div>
                  </div>
                ))}
              </div>

              {/* Transparent Deduction Audit */}
              {dossier.quality_score.deductions.length > 0 && (
                <div className="mt-4 pt-4 border-t border-gray-800/80">
                  <button
                    onClick={() => setShowDeductions(!showDeductions)}
                    className="flex items-center justify-between w-full text-xs font-semibold text-gray-300 hover:text-white transition-colors"
                  >
                    <span className="flex items-center gap-1.5 text-amber-400">
                      <span>⚖</span> Transparent Deduction Audit ({dossier.quality_score.deductions.length} criteria penalized)
                    </span>
                    <span>{showDeductions ? "▲ Hide" : "▼ Show"}</span>
                  </button>

                  {showDeductions && (
                    <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2.5">
                      {dossier.quality_score.deductions.map((d: DeductionDetail, i: number) => (
                        <div
                          key={i}
                          className="flex items-start gap-2.5 p-2.5 rounded bg-amber-500/5 border border-amber-500/20 text-xs"
                        >
                          <span className="text-amber-400 font-bold font-mono whitespace-nowrap">
                            -{d.points_lost} pts
                          </span>
                          <div className="space-y-0.5">
                            <div className="font-semibold text-gray-200">
                              {d.category}: {d.metric}
                            </div>
                            <div className="text-gray-400 text-[11px]">{d.reason}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Calculated Ratios Grid */}
          {dossier.calculated_ratios && (
            <div className="p-6 rounded-xl bg-[#11141c] border border-gray-800 space-y-6">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <span>📊</span> Key Fundamental Ratios
                <span className="text-xs text-gray-400 font-normal">
                  (Reporting Period: {ratios?.reporting_period || "Latest"} • {ratios?.statement_type || "Consolidated"})
                </span>
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                {/* Growth */}
                <div className="p-4 rounded-xl bg-[#0b0e14] border border-gray-800/80 space-y-3">
                  <div className="text-xs font-bold text-emerald-400 uppercase tracking-wider">
                    Growth Trends (CAGR)
                  </div>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">3Y Revenue CAGR:</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(growth?.revenue_cagr_3y, 1, "", "%")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">5Y Revenue CAGR:</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(growth?.revenue_cagr_5y, 1, "", "%")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">3Y PAT CAGR:</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(growth?.pat_cagr_3y, 1, "", "%")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">5Y PAT CAGR:</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(growth?.pat_cagr_5y, 1, "", "%")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-gray-400">Latest Qtr YoY Growth:</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(growth?.quarterly_rev_growth_yoy, 1, "", "%")}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Profitability */}
                <div className="p-4 rounded-xl bg-[#0b0e14] border border-gray-800/80 space-y-3">
                  <div className="text-xs font-bold text-sky-400 uppercase tracking-wider">
                    Profitability & Returns
                  </div>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">Return on Equity (ROE):</span>
                      <span className="font-semibold text-emerald-400">
                        {formatNumber(prof?.roe, 1, "", "%")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">ROCE (Avg Capital):</span>
                      <span className="font-semibold text-emerald-400">
                        {formatNumber(prof?.roce, 1, "", "%")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">Return on Assets (ROA):</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(prof?.roa, 1, "", "%")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">Operating Margin (OPM):</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(prof?.operating_margin_pct, 1, "", "%")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-gray-400">Net Profit Margin (NPM):</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(prof?.net_profit_margin_pct, 1, "", "%")}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Financial Health */}
                <div className="p-4 rounded-xl bg-[#0b0e14] border border-gray-800/80 space-y-3">
                  <div className="text-xs font-bold text-amber-400 uppercase tracking-wider">
                    Solvency & Cash Flow
                  </div>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">Debt to Equity:</span>
                      <span className="font-semibold text-gray-200">
                        {hlth?.is_debt_free
                          ? "Debt Free (0.0)"
                          : formatNumber(hlth?.debt_equity, 2)}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">Interest Coverage:</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(hlth?.interest_coverage, 1, "", "x")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">CFO / PAT (Quality):</span>
                      <span className="font-semibold text-emerald-400">
                        {formatNumber(hlth?.cfo_pat_ratio, 2, "", "x")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">Free Cash Flow:</span>
                      <span className="font-semibold text-gray-200">
                        ₹{formatNumber(hlth?.free_cash_flow_cr, 0)} Cr
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-gray-400">Cash Conversion (CFO/EBITDA):</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(hlth?.cash_conversion_ratio, 2)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Valuation */}
                <div className="p-4 rounded-xl bg-[#0b0e14] border border-gray-800/80 space-y-3">
                  <div className="text-xs font-bold text-purple-400 uppercase tracking-wider">
                    Valuation Multiples
                  </div>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">Price to Earnings (P/E):</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(val?.pe, 1, "", "x")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">Price to Book (P/B):</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(val?.pb, 1, "", "x")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">PEG Ratio:</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(val?.peg, 2)}
                      </span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-gray-800/60">
                      <span className="text-gray-400">EV / EBITDA:</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(val?.ev_ebitda, 1, "", "x")}
                      </span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-gray-400">Dividend Yield:</span>
                      <span className="font-semibold text-gray-200">
                        {formatNumber(val?.dividend_yield, 2, "", "%")}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Historical Statements Viewer */}
          <div className="p-6 rounded-xl bg-[#11141c] border border-gray-800 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-4 border-b border-gray-800 pb-3">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <span>📑</span> Financial Statements
              </h2>

              {/* Statement Tabs */}
              <div className="flex gap-2">
                {[
                  { id: "annual", label: "Annual P&L" },
                  { id: "quarterly", label: "Quarterly P&L" },
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

            {/* Statement Table Content */}
            <div className="overflow-x-auto">
              {activeStatementTab === "annual" && (
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
              )}

              {activeStatementTab === "quarterly" && (
                <table className="w-full text-xs text-left">
                  <thead className="bg-[#0b0e14] text-gray-400 uppercase font-semibold border-b border-gray-800">
                    <tr>
                      <th className="py-2.5 px-3">Quarter</th>
                      <th className="py-2.5 px-3 text-right">Revenue (₹ Cr)</th>
                      <th className="py-2.5 px-3 text-right">EBITDA (₹ Cr)</th>
                      <th className="py-2.5 px-3 text-right">OPM %</th>
                      <th className="py-2.5 px-3 text-right">Net Profit (₹ Cr)</th>
                      <th className="py-2.5 px-3 text-right">EPS (₹)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60 font-mono">
                    {dossier.quarterly_income_statements.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-6 text-center text-gray-500 font-sans">
                          No quarterly statements available.
                        </td>
                      </tr>
                    ) : (
                      dossier.quarterly_income_statements.map((stmt, idx) => (
                        <tr key={idx} className="hover:bg-gray-800/30">
                          <td className="py-2.5 px-3 font-semibold text-gray-200 font-sans">
                            {stmt.period}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            {formatNumber(stmt.revenue_from_operations_cr ?? (stmt as any).revenue_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right text-emerald-400">
                            {formatNumber(stmt.ebitda_cr, 0)}
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            {formatNumber(stmt.opm_pct, 1, "", "%")}
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
              )}

              {activeStatementTab === "balance_sheet" && (
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
              )}

              {activeStatementTab === "cash_flow" && (
                <table className="w-full text-xs text-left">
                  <thead className="bg-[#0b0e14] text-gray-400 uppercase font-semibold border-b border-gray-800">
                    <tr>
                      <th className="py-2.5 px-3">Period</th>
                      <th className="py-2.5 px-3 text-right">Cash from Operations (CFO)</th>
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
              )}

              {activeStatementTab === "shareholding" && (
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
              )}
            </div>
          </div>

          {/* Peer Comparison Section */}
          {dossier.peers && dossier.peers.companies.length > 1 && (
            <div className="p-6 rounded-xl bg-[#11141c] border border-gray-800 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-white flex items-center gap-2">
                    <span>⚔</span> Peer Comparison
                    <span className="text-xs text-gray-400 font-normal">
                      ({dossier.peers.sector || "Industry Peers"} • Aligned to {dossier.peers.reporting_period})
                    </span>
                  </h2>
                  <p className="text-xs text-gray-400">
                    Standardized side-by-side comparison across 13 core operational metrics
                  </p>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-[#0b0e14] text-gray-400 uppercase font-semibold border-b border-gray-800">
                    <tr>
                      <th className="py-2.5 px-3">Metric</th>
                      {dossier.peers.companies.map((c) => (
                        <th
                          key={c.symbol}
                          className={`py-2.5 px-3 text-right ${
                            c.symbol === dossier.symbol ? "text-emerald-400 font-bold bg-emerald-500/5" : ""
                          }`}
                        >
                          <div>{c.company_name}</div>
                          <div className="text-[10px] font-mono text-gray-500 font-normal">
                            ({c.symbol})
                          </div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60 font-mono">
                    {/* Quality Score Row */}
                    <tr className="bg-gray-800/20 font-sans">
                      <td className="py-2.5 px-3 font-semibold text-gray-200">
                        Quality Score (0-100)
                      </td>
                      {dossier.peers.companies.map((c) => (
                        <td
                          key={c.symbol}
                          className={`py-2.5 px-3 text-right font-bold ${
                            c.symbol === dossier.symbol ? "bg-emerald-500/5" : ""
                          }`}
                        >
                          <span
                            className={`px-2 py-0.5 rounded text-xs ${getGradeColor(
                              c.quality_grade
                            )}`}
                          >
                            {c.quality_score ?? "—"} ({c.quality_grade})
                          </span>
                        </td>
                      ))}
                    </tr>

                    {/* Standard Metrics Rows */}
                    {dossier.peers.metrics.map((m) => (
                      <tr key={m.metric_key} className="hover:bg-gray-800/30">
                        <td className="py-2 px-3 font-sans text-gray-300 font-medium">
                          {m.label} {m.unit && <span className="text-gray-500">({m.unit})</span>}
                        </td>
                        {dossier.peers!.companies.map((c) => {
                          const val = m.values[c.symbol];
                          const isBest = m.best_symbol === c.symbol;
                          const isTarget = c.symbol === dossier.symbol;

                          return (
                            <td
                              key={c.symbol}
                              className={`py-2 px-3 text-right ${
                                isTarget ? "bg-emerald-500/5" : ""
                              } ${isBest ? "text-emerald-400 font-bold" : "text-gray-300"}`}
                            >
                              {val !== null && val !== undefined ? (
                                <>
                                  {val.toFixed(1)}
                                  {isBest && <span className="ml-1 text-[10px]">★</span>}
                                </>
                              ) : (
                                "—"
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
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

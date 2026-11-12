import React, { useEffect, useState } from "react";
import { apiFetch, apiJson } from "../api/client";

interface TradeRecord {
  symbol: string;
  entry_date: string;
  exit_date: string;
  entry_price: number;
  exit_price: number;
  quantity: number;
  entry_turnover: number;
  exit_turnover: number;
  gross_pnl: number;
  net_pnl: number;
  return_pct: number;
  exit_reason: string;
  holding_days: number;
  entry_cost: number;
  exit_cost: number;
  total_transaction_cost: number;
  cost_breakdown: {
    itemized: {
      brokerage: number;
      stt: number;
      exchange_txn_charge: number;
      sebi_turnover_fee: number;
      stamp_duty: number;
      gst: number;
      dp_charge: number;
      ipft: number;
    };
    slippage_total: number;
  };
}

interface DailyEquityPoint {
  date: string;
  cash: number;
  invested_value: number;
  total_equity: number;
  daily_return_pct: number;
  cumulative_return_pct: number;
  drawdown_pct: number;
  high_water_mark: number;
  open_positions_count: number;
  benchmark_equity: number;
}

interface MonthlyReturnRow {
  year: number;
  returns: Record<string, number | null>;
  year_total_pct: number;
}

interface StockPerformance {
  symbol: string;
  trades_count: number;
  wins_count: number;
  losses_count: number;
  win_rate_pct: number;
  net_pnl: number;
  avg_trade_pnl: number;
  total_transaction_cost: number;
  total_turnover: number;
}

interface DataQualityReport {
  symbol: string;
  total_bars: number;
  start_date: string;
  end_date: string;
  expected_sessions: number;
  coverage_pct: number;
  missing_sessions_count: number;
  anomalies: string[];
  data_quality_score: number;
  data_source: string;
  status: string;
}

interface PerformanceSummary {
  initial_capital: number;
  final_equity: number;
  gross_profit: number;
  net_profit: number;
  net_return_pct: number;
  cagr_pct: number;
  total_days: number;
  total_sessions: number;
  max_drawdown_pct: number;
  max_drawdown_inr: number;
  annualized_volatility_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  risk_free_rate_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate_pct: number;
  profit_factor: number;
  avg_trade_pnl: number;
  avg_winning_trade: number;
  avg_losing_trade: number;
  payoff_ratio: number;
  expectancy_inr: number;
  avg_holding_period_days: number;
  total_transaction_costs: number;
  brokerage_total: number;
  stt_total: number;
  slippage_total: number;
  benchmark_symbol: string;
  benchmark_final_equity: number;
  benchmark_return_pct: number;
  benchmark_cagr_pct: number;
  alpha_pct: number;
  exposure_pct: number;
}

interface BacktestApiResponse {
  status: string;
  universe_id: string;
  scanned_symbols_count: number;
  total_signals_detected: number;
  summary: PerformanceSummary;
  equity_curve: DailyEquityPoint[];
  trades: TradeRecord[];
  monthly_returns: MonthlyReturnRow[];
  stock_performance: StockPerformance[];
  cost_summary: Record<string, number>;
  data_quality: Record<string, DataQualityReport>;
}

export default function ConsolidationBreakoutBacktestView() {
  // Configuration State
  const [universeId, setUniverseId] = useState("LIQUID_MOMENTUM");
  const [customSymbolsInput, setCustomSymbolsInput] = useState("BEL, RELIANCE, TRENT, HAL");
  const [initialCapital, setInitialCapital] = useState(100000);
  const [startDate, setStartDate] = useState("2021-11-12");
  const [endDate, setEndDate] = useState("2026-11-09");

  // Strategy Parameters
  const [lookback, setLookback] = useState(20);
  const [maxRangePct, setMaxRangePct] = useState(8.0);
  const [volMultiplier, setVolMultiplier] = useState(1.5);
  const [rewardToRisk, setRewardToRisk] = useState(2.0);
  const [trailingStop, setTrailingStop] = useState(true);
  const [maxHoldingSessions, setMaxHoldingSessions] = useState(20);
  const [slippageBps, setSlippageBps] = useState(5.0);

  // Execution State
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestApiResponse | null>(null);
  const [tradeFilter, setTradeFilter] = useState("");
  const [activeTab, setActiveTab] = useState<"overview" | "trades" | "monthly" | "quality" | "costs">("overview");

  // Initial Backtest on mount
  useEffect(() => {
    handleRunBacktest();
  }, []);

  const handleRunBacktest = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload: any = {
        universe_id: universeId,
        initial_capital: Number(initialCapital),
        start_date: startDate,
        end_date: endDate,
        consolidation_lookback: Number(lookback),
        max_consolidation_range_pct: Number(maxRangePct),
        breakout_volume_multiplier: Number(volMultiplier),
        reward_to_risk_ratio: Number(rewardToRisk),
        use_trailing_stop: trailingStop,
        use_profit_target: true,
        use_max_holding_period: true,
        max_holding_period_sessions: Number(maxHoldingSessions),
        risk_per_trade_pct: 1.0,
        max_positions: 5,
        max_allocation_pct: 20.0,
        slippage_bps: Number(slippageBps),
        force_data_refresh: false,
      };

      if (universeId === "CUSTOM") {
        payload.custom_symbols = customSymbolsInput
          .split(",")
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean);
      }

      const res = await apiFetch("/api/backtest/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Backtest failed with status ${res.status}`);
      }

      const data: BacktestApiResponse = await res.json();
      setResult(data);
    } catch (err: any) {
      setError(err?.message || "Failed to execute backtest");
    } finally {
      setLoading(false);
    }
  };

  const handleExportCsv = async () => {
    if (!result || !result.trades.length) return;
    try {
      const res = await apiFetch("/api/backtest/export-csv", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trades: result.trades }),
      });

      if (!res.ok) throw new Error("CSV Export failed");

      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `backtest_consolidation_breakout_${startDate}_${endDate}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e: any) {
      alert(e?.message || "Could not export CSV");
    }
  };

  const summary = result?.summary;
  const equityCurve = result?.equity_curve || [];
  const filteredTrades = (result?.trades || []).filter(
    (t) =>
      t.symbol.toLowerCase().includes(tradeFilter.toLowerCase()) ||
      t.exit_reason.toLowerCase().includes(tradeFilter.toLowerCase())
  );

  return (
    <div className="p-4 md:p-6 space-y-6 max-w-7xl mx-auto text-gray-200 bg-[#090d14] min-h-screen">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[#1e293b] pb-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
              <span className="text-emerald-400">⚡</span> Consolidation Breakout Engine
            </h1>
            <span className="px-2.5 py-0.5 text-xs font-semibold rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              V1 PRODUCTION
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            5-Year NSE Equity Delivery Backtest • Upstox Statutory Cost Schedule • Zero Look-Ahead Bias
          </p>
        </div>

        <div className="flex items-center gap-3">
          {result && (
            <button
              onClick={handleExportCsv}
              className="px-3.5 py-2 text-xs font-medium bg-[#131b2a] hover:bg-[#1a253a] text-gray-200 border border-[#27354f] rounded-lg transition-colors flex items-center gap-1.5"
            >
              📥 Export CSV
            </button>
          )}
          <button
            onClick={handleRunBacktest}
            disabled={loading}
            className="px-5 py-2 text-xs font-semibold bg-emerald-500 hover:bg-emerald-400 text-black rounded-lg transition-all shadow-lg shadow-emerald-500/20 disabled:opacity-50 flex items-center gap-2"
          >
            {loading ? (
              <>
                <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-black border-t-transparent rounded-full" />
                Simulating 5 Years...
              </>
            ) : (
              <>▶ Run Backtest</>
            )}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-950/40 border border-red-800/60 rounded-xl text-red-200 text-sm flex items-center gap-3">
          <span>⚠️</span>
          <span>{error}</span>
        </div>
      )}

      {/* Control Panel Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 p-4 bg-[#0d131f] border border-[#1e293b] rounded-xl text-xs">
        {/* Col 1: Universe & Capital */}
        <div className="space-y-3">
          <div>
            <label className="block text-gray-400 font-medium mb-1">Stock Universe</label>
            <select
              value={universeId}
              onChange={(e) => setUniverseId(e.target.value)}
              className="w-full bg-[#131b2a] border border-[#27354f] rounded-lg px-2.5 py-1.5 text-white focus:outline-none focus:border-emerald-500"
            >
              <option value="LIQUID_MOMENTUM">Liquid Momentum (TRENT, BEL, HAL, DIXON...)</option>
              <option value="DEFENCE_AND_PSU">Defence & PSU Growth (BEL, HAL, NTPC, ONGC...)</option>
              <option value="NIFTY_50">NIFTY 50 Bluechip (50 Equities)</option>
              <option value="CUSTOM">Custom Symbol List</option>
            </select>
          </div>

          {universeId === "CUSTOM" && (
            <div>
              <label className="block text-gray-400 font-medium mb-1">Custom Symbols (CSV)</label>
              <input
                type="text"
                value={customSymbolsInput}
                onChange={(e) => setCustomSymbolsInput(e.target.value)}
                className="w-full bg-[#131b2a] border border-[#27354f] rounded-lg px-2.5 py-1.5 text-white"
                placeholder="RELIANCE, BEL, TCS, INFY"
              />
            </div>
          )}

          <div>
            <label className="block text-gray-400 font-medium mb-1">Initial Capital (₹)</label>
            <input
              type="number"
              value={initialCapital}
              onChange={(e) => setInitialCapital(Number(e.target.value))}
              className="w-full bg-[#131b2a] border border-[#27354f] rounded-lg px-2.5 py-1.5 text-white"
            />
          </div>
        </div>

        {/* Col 2: Date Range */}
        <div className="space-y-3">
          <div>
            <label className="block text-gray-400 font-medium mb-1">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="w-full bg-[#131b2a] border border-[#27354f] rounded-lg px-2.5 py-1.5 text-white"
            />
          </div>
          <div>
            <label className="block text-gray-400 font-medium mb-1">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="w-full bg-[#131b2a] border border-[#27354f] rounded-lg px-2.5 py-1.5 text-white"
            />
          </div>
          <div className="text-[11px] text-gray-400 flex items-center gap-1.5 pt-1">
            <span>📅</span> Full 5-year window with NSE holiday exclusions.
          </div>
        </div>

        {/* Col 3: Strategy Invariants */}
        <div className="space-y-3">
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="block text-gray-400 font-medium mb-1">Lookback (Bars)</label>
              <input
                type="number"
                value={lookback}
                onChange={(e) => setLookback(Number(e.target.value))}
                className="w-full bg-[#131b2a] border border-[#27354f] rounded-lg px-2.5 py-1.5 text-white"
              />
            </div>
            <div className="flex-1">
              <label className="block text-gray-400 font-medium mb-1">Max Range (%)</label>
              <input
                type="number"
                step="0.5"
                value={maxRangePct}
                onChange={(e) => setMaxRangePct(Number(e.target.value))}
                className="w-full bg-[#131b2a] border border-[#27354f] rounded-lg px-2.5 py-1.5 text-white"
              />
            </div>
          </div>

          <div className="flex gap-2">
            <div className="flex-1">
              <label className="block text-gray-400 font-medium mb-1">Vol Multiplier</label>
              <input
                type="number"
                step="0.1"
                value={volMultiplier}
                onChange={(e) => setVolMultiplier(Number(e.target.value))}
                className="w-full bg-[#131b2a] border border-[#27354f] rounded-lg px-2.5 py-1.5 text-white"
              />
            </div>
            <div className="flex-1">
              <label className="block text-gray-400 font-medium mb-1">Target (R:R)</label>
              <input
                type="number"
                step="0.5"
                value={rewardToRisk}
                onChange={(e) => setRewardToRisk(Number(e.target.value))}
                className="w-full bg-[#131b2a] border border-[#27354f] rounded-lg px-2.5 py-1.5 text-white"
              />
            </div>
          </div>
        </div>

        {/* Col 4: Execution & Risk */}
        <div className="space-y-3">
          <div className="flex gap-2">
            <div className="flex-1">
              <label className="block text-gray-400 font-medium mb-1">Max Hold (Bars)</label>
              <input
                type="number"
                value={maxHoldingSessions}
                onChange={(e) => setMaxHoldingSessions(Number(e.target.value))}
                className="w-full bg-[#131b2a] border border-[#27354f] rounded-lg px-2.5 py-1.5 text-white"
              />
            </div>
            <div className="flex-1">
              <label className="block text-gray-400 font-medium mb-1">Slippage (bps)</label>
              <input
                type="number"
                value={slippageBps}
                onChange={(e) => setSlippageBps(Number(e.target.value))}
                className="w-full bg-[#131b2a] border border-[#27354f] rounded-lg px-2.5 py-1.5 text-white"
              />
            </div>
          </div>

          <div className="pt-2">
            <label className="flex items-center gap-2 cursor-pointer text-gray-300">
              <input
                type="checkbox"
                checked={trailingStop}
                onChange={(e) => setTrailingStop(e.target.checked)}
                className="rounded border-[#27354f] text-emerald-500 focus:ring-0"
              />
              <span>Enable SMA20 Trailing Stop</span>
            </label>
          </div>

          <div className="text-[11px] text-gray-400">
            Allocation: Max 20% / trade • 1% risk of equity
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-[#1e293b] gap-2 text-xs font-semibold">
        {[
          { id: "overview", label: "📊 Performance Overview" },
          { id: "trades", label: `📜 Trade History (${result?.trades.length || 0})` },
          { id: "monthly", label: "🗓️ Monthly Returns Heatmap" },
          { id: "costs", label: "💰 Upstox Statutory Charges" },
          { id: "quality", label: "🛡️ Data Quality & Coverage" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            className={`pb-2.5 px-3 border-b-2 transition-colors ${
              activeTab === tab.id
                ? "border-emerald-500 text-emerald-400 font-bold"
                : "border-transparent text-gray-400 hover:text-gray-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* TAB 1: OVERVIEW */}
      {activeTab === "overview" && summary && (
        <div className="space-y-6">
          {/* 12 Key Performance Metrics Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <MetricCard
              label="Ending Equity"
              value={`₹${summary.final_equity.toLocaleString("en-IN")}`}
              subValue={`${summary.net_return_pct >= 0 ? "+" : ""}${summary.net_return_pct}%`}
              isPositive={summary.net_return_pct >= 0}
            />
            <MetricCard
              label="CAGR"
              value={`${summary.cagr_pct}%`}
              subValue={`Bench: ${summary.benchmark_cagr_pct}%`}
              isPositive={summary.cagr_pct >= summary.benchmark_cagr_pct}
            />
            <MetricCard
              label="Alpha vs NIFTY 50"
              value={`${summary.alpha_pct >= 0 ? "+" : ""}${summary.alpha_pct}%`}
              subValue={`NIFTY: ${summary.benchmark_return_pct}%`}
              isPositive={summary.alpha_pct >= 0}
            />
            <MetricCard
              label="Max Drawdown"
              value={`-${summary.max_drawdown_pct.toFixed(2)}%`}
              subValue={`₹${summary.max_drawdown_inr.toLocaleString("en-IN")}`}
              isPositive={false}
            />
            <MetricCard
              label="Sharpe Ratio (6.5%)"
              value={summary.sharpe_ratio.toFixed(2)}
              subValue={`Sortino: ${summary.sortino_ratio.toFixed(2)}`}
              isPositive={summary.sharpe_ratio > 0}
            />
            <MetricCard
              label="Win Rate"
              value={`${summary.win_rate_pct.toFixed(1)}%`}
              subValue={`${summary.winning_trades}W / ${summary.losing_trades}L`}
              isPositive={summary.win_rate_pct >= 50}
            />
            <MetricCard
              label="Profit Factor"
              value={summary.profit_factor.toFixed(2)}
              subValue={`Payoff: ${summary.payoff_ratio.toFixed(2)}x`}
              isPositive={summary.profit_factor >= 1.5}
            />
            <MetricCard
              label="Trade Expectancy"
              value={`₹${summary.expectancy_inr.toLocaleString("en-IN")}`}
              subValue={`Avg P&L: ₹${summary.avg_trade_pnl}`}
              isPositive={summary.expectancy_inr > 0}
            />
            <MetricCard
              label="Total Trades"
              value={summary.total_trades.toString()}
              subValue={`Avg Hold: ${summary.avg_holding_period_days}d`}
            />
            <MetricCard
              label="Capital Exposure"
              value={`${summary.exposure_pct}%`}
              subValue={`${summary.total_sessions} Sessions`}
            />
            <MetricCard
              label="Transaction Costs"
              value={`₹${summary.total_transaction_costs.toLocaleString("en-IN")}`}
              subValue={`Brokerage: ₹${summary.brokerage_total}`}
              isPositive={false}
            />
            <MetricCard
              label="Annualized Volatility"
              value={`${summary.annualized_volatility_pct.toFixed(1)}%`}
              subValue={`Calmar: ${summary.calmar_ratio.toFixed(2)}`}
            />
          </div>

          {/* Interactive Equity Curve & Drawdown Chart */}
          <div className="p-5 bg-[#0d131f] border border-[#1e293b] rounded-xl space-y-4">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-[#1e293b] pb-3">
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <span>📈</span> Portfolio Equity Curve vs NIFTY 50 Benchmark
                </h3>
                <p className="text-xs text-gray-400">Mark-to-market daily portfolio valuation across all positions</p>
              </div>
              <div className="flex items-center gap-4 text-xs">
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-0.5 bg-emerald-400 inline-block" /> Strategy Portfolio
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="w-3 h-0.5 bg-blue-400 inline-block" /> NIFTY 50 (Buy & Hold)
                </span>
              </div>
            </div>

            {equityCurve.length > 0 ? (
              <SimpleSvgEquityChart points={equityCurve} />
            ) : (
              <div className="h-48 flex items-center justify-center text-gray-500 text-xs">
                No equity curve data available.
              </div>
            )}
          </div>

          {/* Stock Performance Ranking Table */}
          <div className="p-5 bg-[#0d131f] border border-[#1e293b] rounded-xl space-y-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>🏆</span> Individual Stock Performance Attribution
            </h3>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr className="text-gray-400 border-b border-[#1e293b]">
                    <th className="py-2.5 px-3">SYMBOL</th>
                    <th className="py-2.5 px-3">TRADES</th>
                    <th className="py-2.5 px-3">WIN RATE</th>
                    <th className="py-2.5 px-3">NET P&L (₹)</th>
                    <th className="py-2.5 px-3">AVG P&L / TRADE</th>
                    <th className="py-2.5 px-3">TOTAL COSTS (₹)</th>
                    <th className="py-2.5 px-3">TOTAL TURNOVER (₹)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#172033]">
                  {result.stock_performance.map((s) => (
                    <tr key={s.symbol} className="hover:bg-[#131b2a] transition-colors">
                      <td className="py-2.5 px-3 font-bold text-white">{s.symbol}</td>
                      <td className="py-2.5 px-3 text-gray-300">{s.trades_count}</td>
                      <td className="py-2.5 px-3">
                        <span className={s.win_rate_pct >= 50 ? "text-emerald-400" : "text-amber-400"}>
                          {s.win_rate_pct.toFixed(1)}%
                        </span>
                      </td>
                      <td className={`py-2.5 px-3 font-semibold ${s.net_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                        {s.net_pnl >= 0 ? "+" : ""}₹{s.net_pnl.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                      </td>
                      <td className={`py-2.5 px-3 ${s.avg_trade_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                        ₹{s.avg_trade_pnl.toFixed(2)}
                      </td>
                      <td className="py-2.5 px-3 text-gray-400">₹{s.total_transaction_cost.toFixed(2)}</td>
                      <td className="py-2.5 px-3 text-gray-400">₹{s.total_turnover.toLocaleString("en-IN")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: TRADES */}
      {activeTab === "trades" && (
        <div className="p-5 bg-[#0d131f] border border-[#1e293b] rounded-xl space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-bold text-white">Itemized Trade Execution Log</h3>
              <p className="text-xs text-gray-400">Every trade executed at T+1 Open with full statutory charges</p>
            </div>
            <input
              type="text"
              placeholder="Search symbol or exit reason..."
              value={tradeFilter}
              onChange={(e) => setTradeFilter(e.target.value)}
              className="bg-[#131b2a] border border-[#27354f] rounded-lg px-3 py-1.5 text-xs text-white placeholder-gray-500 w-64"
            />
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="text-gray-400 border-b border-[#1e293b]">
                  <th className="py-2.5 px-2">#</th>
                  <th className="py-2.5 px-2">SYMBOL</th>
                  <th className="py-2.5 px-2">ENTRY DATE</th>
                  <th className="py-2.5 px-2">EXIT DATE</th>
                  <th className="py-2.5 px-2">DAYS</th>
                  <th className="py-2.5 px-2">QTY</th>
                  <th className="py-2.5 px-2">ENTRY PRICE</th>
                  <th className="py-2.5 px-2">EXIT PRICE</th>
                  <th className="py-2.5 px-2">GROSS P&L</th>
                  <th className="py-2.5 px-2">COSTS</th>
                  <th className="py-2.5 px-2">NET P&L</th>
                  <th className="py-2.5 px-2">RETURN</th>
                  <th className="py-2.5 px-2">EXIT REASON</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#172033]">
                {filteredTrades.map((t, idx) => (
                  <tr key={idx} className="hover:bg-[#131b2a] transition-colors">
                    <td className="py-2 px-2 text-gray-500">{idx + 1}</td>
                    <td className="py-2 px-2 font-bold text-white">{t.symbol}</td>
                    <td className="py-2 px-2 text-gray-300">{t.entry_date}</td>
                    <td className="py-2 px-2 text-gray-300">{t.exit_date}</td>
                    <td className="py-2 px-2 text-gray-400">{t.holding_days}d</td>
                    <td className="py-2 px-2 text-gray-300">{t.quantity}</td>
                    <td className="py-2 px-2 text-gray-200">₹{t.entry_price.toFixed(2)}</td>
                    <td className="py-2 px-2 text-gray-200">₹{t.exit_price.toFixed(2)}</td>
                    <td className={`py-2 px-2 font-medium ${t.gross_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      ₹{t.gross_pnl.toFixed(2)}
                    </td>
                    <td className="py-2 px-2 text-amber-400">₹{t.total_transaction_cost.toFixed(2)}</td>
                    <td className={`py-2 px-2 font-bold ${t.net_pnl >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {t.net_pnl >= 0 ? "+" : ""}₹{t.net_pnl.toFixed(2)}
                    </td>
                    <td className={`py-2 px-2 font-semibold ${t.return_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {t.return_pct >= 0 ? "+" : ""}{t.return_pct.toFixed(2)}%
                    </td>
                    <td className="py-2 px-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-[#172033] text-gray-300 border border-[#27354f]">
                        {t.exit_reason}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 3: MONTHLY HEATMAP */}
      {activeTab === "monthly" && result && (
        <div className="p-5 bg-[#0d131f] border border-[#1e293b] rounded-xl space-y-4">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>🗓️</span> Mark-to-Market Monthly Returns Heatmap (%)
            </h3>
            <p className="text-xs text-gray-400">Calendar month returns calculated from daily portfolio equity values</p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-center border-collapse">
              <thead>
                <tr className="text-gray-400 border-b border-[#1e293b]">
                  <th className="py-2 px-3 text-left">YEAR</th>
                  {["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].map((m) => (
                    <th key={m} className="py-2 px-2">{m}</th>
                  ))}
                  <th className="py-2 px-3 text-right">YEAR TOTAL</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#172033]">
                {result.monthly_returns.map((row) => (
                  <tr key={row.year} className="hover:bg-[#131b2a]">
                    <td className="py-2 px-3 font-bold text-white text-left">{row.year}</td>
                    {["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].map((m) => {
                      const val = row.returns[m];
                      if (val === null || val === undefined) {
                        return <td key={m} className="py-2 px-2 text-gray-600">—</td>;
                      }
                      const isPos = val >= 0;
                      const intensity = Math.min(100, Math.abs(val) * 15);
                      const bg = isPos
                        ? `rgba(16, 185, 129, ${0.1 + intensity / 300})`
                        : `rgba(239, 68, 68, ${0.1 + intensity / 300})`;
                      const textColor = isPos ? "text-emerald-400" : "text-red-400";
                      return (
                        <td key={m} style={{ backgroundColor: bg }} className={`py-2 px-2 font-medium ${textColor}`}>
                          {val > 0 ? "+" : ""}{val.toFixed(2)}%
                        </td>
                      );
                    })}
                    <td className={`py-2 px-3 font-bold text-right ${row.year_total_pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                      {row.year_total_pct >= 0 ? "+" : ""}{row.year_total_pct.toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 4: UPSTOX COSTS */}
      {activeTab === "costs" && result && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="p-5 bg-[#0d131f] border border-[#1e293b] rounded-xl space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>🧾</span> Upstox Delivery Cost Schedule (Audited)
            </h3>
            <p className="text-xs text-gray-400">
              Date-effective regulatory and broker charges applied strictly to every executed order.
            </p>

            <div className="space-y-2 text-xs divide-y divide-[#172033]">
              <div className="flex justify-between py-2">
                <span className="text-gray-400">Brokerage</span>
                <span className="text-white font-medium">₹20 flat or 2.5% (whichever is lower)</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-gray-400">STT (Securities Transaction Tax)</span>
                <span className="text-white font-medium">0.1% on Buy + 0.1% on Sell turnover</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-gray-400">NSE Transaction Charges</span>
                <span className="text-white font-medium">₹297 to ₹345 / crore (date-effective)</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-gray-400">DP Charges (Delivery Sell)</span>
                <span className="text-white font-medium">₹18.50 + 18% GST (₹21.83 / sell instruction)</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-gray-400">SEBI Turnover Fees</span>
                <span className="text-white font-medium">₹10 / crore (0.0001% of turnover)</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-gray-400">Stamp Duty</span>
                <span className="text-white font-medium">0.015% on Buy turnover only</span>
              </div>
              <div className="flex justify-between py-2">
                <span className="text-gray-400">GST</span>
                <span className="text-white font-medium">18% on (Brokerage + Txn Charges + SEBI Fees)</span>
              </div>
            </div>
          </div>

          <div className="p-5 bg-[#0d131f] border border-[#1e293b] rounded-xl space-y-4">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>💳</span> Cumulative Transaction Cost Breakdown
            </h3>
            <p className="text-xs text-gray-400">Sum of all fees deducted from portfolio cash balance</p>

            {result.cost_summary && (
              <div className="space-y-2 text-xs divide-y divide-[#172033]">
                <div className="flex justify-between py-2">
                  <span className="text-gray-400">Total Brokerage</span>
                  <span className="text-white font-bold">₹{result.cost_summary.brokerage?.toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-2">
                  <span className="text-gray-400">Total STT</span>
                  <span className="text-white font-bold">₹{result.cost_summary.stt?.toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-2">
                  <span className="text-gray-400">Total NSE Txn Charges</span>
                  <span className="text-white font-bold">₹{result.cost_summary.exchange_txn_charges?.toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-2">
                  <span className="text-gray-400">Total DP Charges</span>
                  <span className="text-white font-bold">₹{result.cost_summary.dp_charges?.toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-2">
                  <span className="text-gray-400">Total GST</span>
                  <span className="text-white font-bold">₹{result.cost_summary.gst?.toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-2">
                  <span className="text-gray-400">Total SEBI + Stamp Duty</span>
                  <span className="text-white font-bold">
                    ₹{((result.cost_summary.sebi_fees || 0) + (result.cost_summary.stamp_duty || 0)).toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between py-2">
                  <span className="text-gray-400">Estimated Execution Slippage</span>
                  <span className="text-white font-bold">₹{result.cost_summary.slippage?.toFixed(2)}</span>
                </div>
                <div className="flex justify-between py-2.5 text-sm font-bold border-t border-emerald-500/30">
                  <span className="text-emerald-400">Total Outflow</span>
                  <span className="text-emerald-400">
                    ₹{result.cost_summary.total_transaction_costs?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 5: DATA QUALITY */}
      {activeTab === "quality" && result && (
        <div className="p-5 bg-[#0d131f] border border-[#1e293b] rounded-xl space-y-4">
          <div>
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <span>🛡️</span> Exchange Calendar Data Quality & Completeness Audit
            </h3>
            <p className="text-xs text-gray-400">
              Verified against official NSE trading calendars (2021–2026). Zero price fabrication.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.values(result.data_quality).map((dq) => (
              <div key={dq.symbol} className="p-4 bg-[#131b2a] border border-[#27354f] rounded-lg space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-white text-sm">{dq.symbol}</span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                      dq.status === "VALID"
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                        : "bg-amber-500/10 text-amber-400 border border-amber-500/20"
                    }`}
                  >
                    {dq.status} ({dq.data_quality_score} / 100)
                  </span>
                </div>

                <div className="text-gray-400 space-y-1">
                  <div className="flex justify-between">
                    <span>Bars Cached:</span>
                    <span className="text-gray-200">{dq.total_bars} / {dq.expected_sessions} ({dq.coverage_pct}%)</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Period:</span>
                    <span className="text-gray-200">{dq.start_date} to {dq.end_date}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Provider Source:</span>
                    <span className="text-gray-200 uppercase font-mono">{dq.data_source}</span>
                  </div>
                </div>

                {dq.anomalies.length > 0 && (
                  <div className="pt-2 border-t border-[#1e293b]">
                    <div className="text-[10px] text-amber-400 font-semibold mb-1">Anomalies Detected:</div>
                    <div className="flex flex-wrap gap-1">
                      {dq.anomalies.map((a, i) => (
                        <span key={i} className="px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 text-[10px]">
                          {a}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({
  label,
  value,
  subValue,
  isPositive,
}: {
  label: string;
  value: string;
  subValue?: string;
  isPositive?: boolean;
}) {
  return (
    <div className="p-3.5 bg-[#0d131f] border border-[#1e293b] rounded-xl flex flex-col justify-between">
      <div className="text-[11px] font-medium text-gray-400 truncate">{label}</div>
      <div className="mt-1">
        <div
          className={`text-base font-bold truncate ${
            isPositive === true
              ? "text-emerald-400"
              : isPositive === false
              ? "text-red-400"
              : "text-white"
          }`}
        >
          {value}
        </div>
        {subValue && <div className="text-[10px] text-gray-400 mt-0.5 truncate">{subValue}</div>}
      </div>
    </div>
  );
}

function SimpleSvgEquityChart({ points }: { points: DailyEquityPoint[] }) {
  if (points.length < 2) return null;

  const width = 800;
  const height = 240;
  const padding = { top: 20, right: 30, bottom: 30, left: 60 };

  const chartWidth = width - padding.left - padding.right;
  const chartHeight = height - padding.top - padding.bottom;

  // Compute min/max equity
  const allEquities = points.flatMap((p) => [p.total_equity, p.benchmark_equity]);
  const minEquity = Math.min(...allEquities) * 0.98;
  const maxEquity = Math.max(...allEquities) * 1.02;

  const getX = (idx: number) => padding.left + (idx / (points.length - 1)) * chartWidth;
  const getY = (val: number) => padding.top + chartHeight - ((val - minEquity) / (maxEquity - minEquity)) * chartHeight;

  // Build SVG path strings
  let stratPath = `M ${getX(0)} ${getY(points[0].total_equity)}`;
  let benchPath = `M ${getX(0)} ${getY(points[0].benchmark_equity)}`;

  points.forEach((p, i) => {
    if (i > 0) {
      stratPath += ` L ${getX(i)} ${getY(p.total_equity)}`;
      benchPath += ` L ${getX(i)} ${getY(p.benchmark_equity)}`;
    }
  });

  // Sample X axis labels (5 dates)
  const labelIndices = [
    0,
    Math.floor(points.length * 0.25),
    Math.floor(points.length * 0.5),
    Math.floor(points.length * 0.75),
    points.length - 1,
  ];

  return (
    <div className="w-full overflow-hidden">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
        {/* Horizontal Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
          const yVal = minEquity + (maxEquity - minEquity) * (1 - pct);
          const yPos = padding.top + chartHeight * pct;
          return (
            <g key={pct}>
              <line
                x1={padding.left}
                y1={yPos}
                x2={width - padding.right}
                y2={yPos}
                stroke="#172033"
                strokeDasharray="4 4"
              />
              <text x={padding.left - 8} y={yPos + 4} textAnchor="end" fill="#64748b" fontSize="10">
                ₹{Math.round(yVal / 1000)}k
              </text>
            </g>
          );
        })}

        {/* Benchmark line (Blue) */}
        <path d={benchPath} fill="none" stroke="#60a5fa" strokeWidth="1.5" strokeOpacity="0.8" />

        {/* Strategy portfolio line (Emerald) */}
        <path d={stratPath} fill="none" stroke="#10b981" strokeWidth="2.2" />

        {/* X Axis dates */}
        {labelIndices.map((idx) => (
          <text
            key={idx}
            x={getX(idx)}
            y={height - 8}
            textAnchor="middle"
            fill="#64748b"
            fontSize="10"
          >
            {points[idx]?.date}
          </text>
        ))}
      </svg>
    </div>
  );
}

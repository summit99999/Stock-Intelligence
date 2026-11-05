import React, { useState } from "react";

interface TradeRecord {
  trade_id: number;
  direction: "BULLISH" | "BEARISH";
  entry_bar: number;
  entry_time: string;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  exit_bar: number;
  exit_time: string;
  exit_price: number;
  outcome: "WIN" | "LOSS" | "MAX_HOLD";
  regime?: string;
  gross_pnl?: number;
  fees?: number;
  slippage?: number;
  net_pnl?: number;
  raw_pnl_pct: number;
  net_pnl_pct: number;
  realized_r?: number;
}

interface EquityPoint {
  bar: number;
  timestamp: string;
  equity: number;
}

interface PerformanceSubgroup {
  trades_count: number;
  win_rate_pct: number;
  net_pnl: number;
}

interface BacktestSummary {
  total_trades: number;
  win_count: number;
  loss_count: number;
  win_rate_pct: number;
  win_rate_95_ci_pct?: [number, number];
  profit_factor: number;
  expectancy_inr?: number;
  expectancy_pct?: number;
  average_r?: number;
  sharpe_ratio?: number;
  max_drawdown_pct: number;
  average_holding_bars?: number;
  net_return_pct: number;
  final_equity: number;
  total_statutory_fees?: number;
  total_slippage?: number;
  transaction_cost_bps: number;
  brokerage_model?: string;
  sample_size_assessment?: {
    tier: string;
    is_statistically_reliable: boolean;
    warning: string;
  };
}

interface BacktestResponse {
  symbol: string;
  strategy: string;
  error?: string;
  sample_size?: number;
  bars_count?: number;
  trades: TradeRecord[];
  summary: BacktestSummary;
  performance_breakdown?: {
    long: PerformanceSubgroup;
    short: PerformanceSubgroup;
  };
  equity_curve: EquityPoint[];
}

interface WalkForwardResponse {
  symbol: string;
  strategy: string;
  train_period: {
    bars: number;
    start: string;
    end: string;
    summary: BacktestSummary;
  };
  test_period_oos: {
    bars: number;
    start: string;
    end: string;
    summary: BacktestSummary;
  };
  regime_breakdown: Record<string, PerformanceSubgroup>;
  overfitting_audit: {
    in_sample_win_rate: number;
    out_of_sample_win_rate: number;
    degradation_pts: number;
    is_statistically_robust: boolean;
    verdict: string;
  };
}

interface ParameterSensitivityResponse {
  symbol: string;
  strategy: string;
  grid_evaluations: number;
  metrics_distribution: {
    win_rate_mean: number;
    win_rate_std: number;
    win_rate_min: number;
    win_rate_max: number;
    profit_factor_mean: number;
    profit_factor_std: number;
  };
  robustness_verdict: string;
  detailed_grid: Array<{
    target_rr: number;
    max_holding_bars: number;
    trades: number;
    win_rate_pct: number;
    profit_factor: number;
    net_return_pct: number;
  }>;
}

interface SMCBacktestViewProps {
  symbol: string;
  onSymbolChange: (symbol: string) => void;
  onNavigate: (view: string) => void;
}

const PRESET_STOCKS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "TATAMOTORS", "SBIN"];

export default function SMCBacktestView({
  symbol,
  onSymbolChange,
  onNavigate,
}: SMCBacktestViewProps) {
  const [strategyType, setStrategyType] = useState<
    "ORDER_BLOCK_RETEST" | "FVG_FILL_REVERSAL" | "BOS_CONTINUATION" | "LIQUIDITY_SWEEP_REVERSAL" | "SMC_VOLUME_CONFIRMATION"
  >("ORDER_BLOCK_RETEST");
  const [targetRR, setTargetRR] = useState<number>(2.0);
  const [costBps, setCostBps] = useState<number>(5.0);
  const [tradeType, setTradeType] = useState<"delivery" | "intraday">("delivery");
  const [brokerageModel, setBrokerageModel] = useState<"dhan" | "zerodha" | "flat_20">("dhan");
  const [maxHoldingBars, setMaxHoldingBars] = useState<number>(15);
  const [useIndianCosts, setUseIndianCosts] = useState<boolean>(true);
  const [allowOverlapping, setAllowOverlapping] = useState<boolean>(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [wfResult, setWfResult] = useState<WalkForwardResponse | null>(null);
  const [sensResult, setSensResult] = useState<ParameterSensitivityResponse | null>(null);
  const [activeSubTab, setActiveSubTab] = useState<"BACKTEST" | "WALK_FORWARD" | "SENSITIVITY">("BACKTEST");
  const [error, setError] = useState<string | null>(null);

  const handleRunBacktest = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("http://127.0.0.1:8000/api/smc/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: symbol.toUpperCase(),
          strategy_type: strategyType,
          target_rr: targetRR,
          cost_bps: costBps,
          trade_type: tradeType,
          brokerage_model: brokerageModel,
          max_holding_bars: maxHoldingBars,
          use_indian_costs: useIndianCosts,
          allow_overlapping: allowOverlapping,
        }),
      });

      if (!res.ok) {
        throw new Error(`Backtest failed with status ${res.status}`);
      }

      const json = await res.json();
      if (json.error) {
        throw new Error(json.error);
      }
      setResult(json);
      setActiveSubTab("BACKTEST");
    } catch (e: any) {
      setError(e.message || "Failed to execute backtest");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const handleRunWalkForward = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `http://127.0.0.1:8000/api/smc/walk-forward/${symbol.toUpperCase()}?strategy_type=${strategyType}&target_rr=${targetRR}&cost_bps=${costBps}&trade_type=${tradeType}&brokerage_model=${brokerageModel}`
      );
      if (!res.ok) throw new Error(`Walk-forward failed with status ${res.status}`);
      const json = await res.json();
      if (json.error) throw new Error(json.error);
      setWfResult(json);
      setActiveSubTab("WALK_FORWARD");
    } catch (e: any) {
      setError(e.message || "Failed to execute walk-forward validation");
    } finally {
      setLoading(false);
    }
  };

  const handleRunSensitivity = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `http://127.0.0.1:8000/api/smc/sensitivity/${symbol.toUpperCase()}?strategy_type=${strategyType}`
      );
      if (!res.ok) throw new Error(`Sensitivity failed with status ${res.status}`);
      const json = await res.json();
      if (json.error) throw new Error(json.error);
      setSensResult(json);
      setActiveSubTab("SENSITIVITY");
    } catch (e: any) {
      setError(e.message || "Failed to execute parameter sensitivity grid");
    } finally {
      setLoading(false);
    }
  };

  // Compute SVG Equity Curve coordinates
  const renderEquityCurve = (curve: EquityPoint[]) => {
    if (!curve || curve.length < 2) return null;

    const equities = curve.map((p) => p.equity);
    const minEq = Math.min(...equities) * 0.98;
    const maxEq = Math.max(...equities) * 1.02;
    const width = 800;
    const height = 180;

    const points = curve
      .map((p, idx) => {
        const x = (idx / (curve.length - 1)) * width;
        const y = height - ((p.equity - minEq) / (maxEq - minEq || 1)) * height;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

    const isPositive = (curve[curve.length - 1]?.equity || 100000) >= 100000;

    return (
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{ width: "100%", height: "180px", overflow: "visible" }}
      >
        <defs>
          <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={isPositive ? "#22c55e" : "#ef4444"} stopOpacity="0.3" />
            <stop offset="100%" stopColor={isPositive ? "#22c55e" : "#ef4444"} stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* 100k Benchmark line */}
        {(() => {
          const base100kY = height - ((100000 - minEq) / (maxEq - minEq || 1)) * height;
          return (
            <line
              x1="0"
              y1={base100kY}
              x2={width}
              y2={base100kY}
              stroke="#475569"
              strokeDasharray="4 4"
              strokeWidth="1"
            />
          );
        })()}

        {/* Fill polygon */}
        <polygon
          points={`0,${height} ${points} ${width},${height}`}
          fill="url(#equityGrad)"
        />

        {/* Main curve */}
        <polyline
          points={points}
          fill="none"
          stroke={isPositive ? "#22c55e" : "#ef4444"}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  };

  return (
    <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: "20px", color: "#e2e8f0" }}>
      {/* Configuration Header */}
      <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px", marginBottom: "16px" }}>
          <div>
            <h2 style={{ margin: 0, fontSize: "18px", color: "#fff" }}>
              SMC Quantitative Backtesting & Walk-Forward Audit
            </h2>
            <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#9ca3af" }}>
              Next-executable candle execution, conservative same-bar resolution, and statutory Indian equity fee models.
            </p>
          </div>

          <div style={{ display: "flex", gap: "6px" }}>
            {PRESET_STOCKS.map((s) => (
              <button
                key={s}
                onClick={() => onSymbolChange(s)}
                style={{
                  background: s === symbol ? "#2563eb" : "#1f2937",
                  color: s === symbol ? "#fff" : "#9ca3af",
                  border: "none",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: "600",
                  cursor: "pointer",
                }}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {/* Form Inputs Grid */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px", alignItems: "flex-end" }}>
          {/* Symbol */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#9ca3af", marginBottom: "4px" }}>
              STOCK SYMBOL
            </label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => onSymbolChange(e.target.value.toUpperCase())}
              style={{
                width: "100%",
                background: "#1f2937",
                border: "1px solid #374151",
                borderRadius: "6px",
                padding: "8px 12px",
                color: "#fff",
                fontSize: "13px",
                fontWeight: "700",
              }}
            />
          </div>

          {/* Strategy */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#9ca3af", marginBottom: "4px" }}>
              INDEPENDENT STRATEGY
            </label>
            <select
              value={strategyType}
              onChange={(e) => setStrategyType(e.target.value as any)}
              style={{
                width: "100%",
                background: "#1f2937",
                border: "1px solid #374151",
                borderRadius: "6px",
                padding: "8px 12px",
                color: "#fff",
                fontSize: "12px",
                cursor: "pointer",
              }}
            >
              <option value="ORDER_BLOCK_RETEST">A. Order Block Retest</option>
              <option value="FVG_FILL_REVERSAL">B. Fair Value Gap 50% Fill</option>
              <option value="BOS_CONTINUATION">C. BOS Continuation</option>
              <option value="LIQUIDITY_SWEEP_REVERSAL">D. Liquidity Sweep Reversal</option>
              <option value="SMC_VOLUME_CONFIRMATION">E. SMC Volume Surge Setup</option>
            </select>
          </div>

          {/* Trade Type */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#9ca3af", marginBottom: "4px" }}>
              TRADE TYPE (SCHEDULE)
            </label>
            <select
              value={tradeType}
              onChange={(e) => setTradeType(e.target.value as any)}
              style={{
                width: "100%",
                background: "#1f2937",
                border: "1px solid #374151",
                borderRadius: "6px",
                padding: "8px 12px",
                color: "#fff",
                fontSize: "12px",
                cursor: "pointer",
              }}
            >
              <option value="delivery">Delivery / Swing (0.1% STT + DP)</option>
              <option value="intraday">Intraday (0.025% STT, ₹0 DP)</option>
            </select>
          </div>

          {/* Broker Profile */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#9ca3af", marginBottom: "4px" }}>
              BROKER PROFILE
            </label>
            <select
              value={brokerageModel}
              onChange={(e) => setBrokerageModel(e.target.value as any)}
              style={{
                width: "100%",
                background: "#1f2937",
                border: "1px solid #374151",
                borderRadius: "6px",
                padding: "8px 12px",
                color: "#fff",
                fontSize: "12px",
                cursor: "pointer",
              }}
            >
              <option value="dhan">Dhan Retail (Default - ₹0 Del, ₹14.75 DP)</option>
              <option value="zerodha">Zerodha Retail (₹0 Del, ₹15.93 DP)</option>
              <option value="flat_20">Flat ₹20 Discount Broker</option>
            </select>
          </div>

          {/* Target R:R */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#9ca3af", marginBottom: "4px" }}>
              TARGET R:R ({targetRR}x)
            </label>
            <input
              type="range"
              min="1.0"
              max="5.0"
              step="0.5"
              value={targetRR}
              onChange={(e) => setTargetRR(parseFloat(e.target.value))}
              style={{ width: "100%", cursor: "pointer" }}
            />
          </div>

          {/* Slippage & Friction */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#9ca3af", marginBottom: "4px" }}>
              SLIPPAGE: {costBps} bps ({(costBps / 100).toFixed(2)}%)
            </label>
            <input
              type="range"
              min="0.0"
              max="20.0"
              step="1.0"
              value={costBps}
              onChange={(e) => setCostBps(parseFloat(e.target.value))}
              style={{ width: "100%", cursor: "pointer" }}
            />
          </div>

          {/* Max Holding Bars */}
          <div>
            <label style={{ display: "block", fontSize: "11px", color: "#9ca3af", marginBottom: "4px" }}>
              MAX HOLD BARS: {maxHoldingBars}
            </label>
            <input
              type="range"
              min="5"
              max="30"
              step="1"
              value={maxHoldingBars}
              onChange={(e) => setMaxHoldingBars(parseInt(e.target.value))}
              style={{ width: "100%", cursor: "pointer" }}
            />
          </div>
        </div>

        {/* Checkbox Toggles & Action Buttons */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "16px", flexWrap: "wrap", gap: "10px" }}>
          <div style={{ display: "flex", gap: "16px", alignItems: "center" }}>
            <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "#cbd5e1", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={useIndianCosts}
                onChange={(e) => setUseIndianCosts(e.target.checked)}
              />
              Indian Statutory Fees (STT, GST, Stamp, Exchange, SEBI)
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "#cbd5e1", cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={allowOverlapping}
                onChange={(e) => setAllowOverlapping(e.target.checked)}
              />
              Allow Overlapping Positions
            </label>
          </div>

          <div style={{ display: "flex", gap: "8px" }}>
            <button
              onClick={handleRunBacktest}
              disabled={loading}
              style={{
                background: "#0284c7",
                color: "#fff",
                border: "none",
                borderRadius: "6px",
                padding: "8px 16px",
                fontSize: "12px",
                fontWeight: "700",
                cursor: loading ? "not-allowed" : "pointer",
              }}
            >
              {loading ? "Simulating..." : "▶ Run Backtest"}
            </button>
            <button
              onClick={handleRunWalkForward}
              disabled={loading}
              style={{
                background: "#1e293b",
                color: "#38bdf8",
                border: "1px solid #0284c7",
                borderRadius: "6px",
                padding: "8px 14px",
                fontSize: "12px",
                fontWeight: "600",
                cursor: loading ? "not-allowed" : "pointer",
              }}
            >
              Walk-Forward Regimes
            </button>
            <button
              onClick={handleRunSensitivity}
              disabled={loading}
              style={{
                background: "#1e293b",
                color: "#f59e0b",
                border: "1px solid #d97706",
                borderRadius: "6px",
                padding: "8px 14px",
                fontSize: "12px",
                fontWeight: "600",
                cursor: loading ? "not-allowed" : "pointer",
              }}
            >
              Parameter Grid
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div
          style={{
            background: "#450a0a",
            border: "1px solid #991b1b",
            color: "#fca5a5",
            padding: "16px",
            borderRadius: "8px",
          }}
        >
          {error}
        </div>
      )}

      {/* View Switcher Tabs */}
      {(result || wfResult || sensResult) && (
        <div style={{ display: "flex", gap: "8px", borderBottom: "1px solid #1f2937" }}>
          {result && (
            <button
              onClick={() => setActiveSubTab("BACKTEST")}
              style={{
                background: "transparent",
                border: "none",
                borderBottom: activeSubTab === "BACKTEST" ? "2px solid #38bdf8" : "2px solid transparent",
                color: activeSubTab === "BACKTEST" ? "#38bdf8" : "#9ca3af",
                padding: "8px 14px",
                fontSize: "13px",
                fontWeight: "600",
                cursor: "pointer",
              }}
            >
              Simulation Results ({result.trades.length} trades)
            </button>
          )}
          {wfResult && (
            <button
              onClick={() => setActiveSubTab("WALK_FORWARD")}
              style={{
                background: "transparent",
                border: "none",
                borderBottom: activeSubTab === "WALK_FORWARD" ? "2px solid #38bdf8" : "2px solid transparent",
                color: activeSubTab === "WALK_FORWARD" ? "#38bdf8" : "#9ca3af",
                padding: "8px 14px",
                fontSize: "13px",
                fontWeight: "600",
                cursor: "pointer",
              }}
            >
              Walk-Forward Out-Of-Sample & Regimes
            </button>
          )}
          {sensResult && (
            <button
              onClick={() => setActiveSubTab("SENSITIVITY")}
              style={{
                background: "transparent",
                border: "none",
                borderBottom: activeSubTab === "SENSITIVITY" ? "2px solid #38bdf8" : "2px solid transparent",
                color: activeSubTab === "SENSITIVITY" ? "#38bdf8" : "#9ca3af",
                padding: "8px 14px",
                fontSize: "13px",
                fontWeight: "600",
                cursor: "pointer",
              }}
            >
              Parameter Robustness Grid ({sensResult.grid_evaluations} runs)
            </button>
          )}
        </div>
      )}

      {/* Main Simulation View */}
      {activeSubTab === "BACKTEST" && result && (
        <>
          {/* Summary Metrics Banner */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: "12px" }}>
            <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "14px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>WIN RATE</div>
              <div
                style={{
                  fontSize: "22px",
                  fontWeight: "800",
                  marginTop: "4px",
                  color: result.summary.win_rate_pct >= 50 ? "#22c55e" : "#ef4444",
                }}
              >
                {result.summary.win_rate_pct}%
              </div>
              <div style={{ fontSize: "10px", color: "#6b7280", marginTop: "2px" }}>
                {result.summary.win_count}W / {result.summary.loss_count}L ({result.summary.total_trades} total)
              </div>
            </div>

            <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "14px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>PROFIT FACTOR</div>
              <div style={{ fontSize: "22px", fontWeight: "800", marginTop: "4px", color: "#38bdf8" }}>
                {result.summary.profit_factor}
              </div>
              <div style={{ fontSize: "10px", color: "#6b7280", marginTop: "2px" }}>Gross profit / gross loss</div>
            </div>

            <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "14px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>EXPECTANCY</div>
              <div
                style={{
                  fontSize: "22px",
                  fontWeight: "800",
                  marginTop: "4px",
                  color: (result.summary.expectancy_inr || 0) >= 0 ? "#22c55e" : "#ef4444",
                }}
              >
                ₹{result.summary.expectancy_inr || 0}
              </div>
              <div style={{ fontSize: "10px", color: "#6b7280", marginTop: "2px" }}>
                Avg R: {result.summary.average_r || 0}R ({result.summary.expectancy_pct || 0}%)
              </div>
            </div>

            <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "14px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>SHARPE RATIO</div>
              <div style={{ fontSize: "22px", fontWeight: "800", marginTop: "4px", color: "#f59e0b" }}>
                {result.summary.sharpe_ratio || 0}
              </div>
              <div style={{ fontSize: "10px", color: "#6b7280", marginTop: "2px" }}>Annualized trade estimate</div>
            </div>

            <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "14px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>MAX DRAWDOWN</div>
              <div style={{ fontSize: "22px", fontWeight: "800", marginTop: "4px", color: "#f87171" }}>
                {result.summary.max_drawdown_pct}%
              </div>
              <div style={{ fontSize: "10px", color: "#6b7280", marginTop: "2px" }}>Peak-to-trough drop</div>
            </div>

            <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "10px", padding: "14px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>NET RETURN</div>
              <div
                style={{
                  fontSize: "22px",
                  fontWeight: "800",
                  marginTop: "4px",
                  color: result.summary.net_return_pct >= 0 ? "#22c55e" : "#ef4444",
                }}
              >
                {result.summary.net_return_pct > 0 ? "+" : ""}{result.summary.net_return_pct}%
              </div>
              <div style={{ fontSize: "10px", color: "#6b7280", marginTop: "2px" }}>
                Equity: ₹{result.summary.final_equity.toLocaleString()}
              </div>
            </div>
          </div>

          {/* Long vs Short Breakdown & Cost Audit */}
          {result.performance_breakdown && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "12px" }}>
              <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "8px", padding: "12px" }}>
                <div style={{ fontSize: "11px", color: "#9ca3af" }}>LONG SETUPS</div>
                <div style={{ fontSize: "16px", fontWeight: "700", color: "#4ade80", marginTop: "2px" }}>
                  {result.performance_breakdown.long.trades_count} Trades · {result.performance_breakdown.long.win_rate_pct}% WR
                </div>
                <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "2px" }}>
                  Net P&L: ₹{result.performance_breakdown.long.net_pnl.toLocaleString()}
                </div>
              </div>

              <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "8px", padding: "12px" }}>
                <div style={{ fontSize: "11px", color: "#9ca3af" }}>SHORT SETUPS</div>
                <div style={{ fontSize: "16px", fontWeight: "700", color: "#f87171", marginTop: "2px" }}>
                  {result.performance_breakdown.short.trades_count} Trades · {result.performance_breakdown.short.win_rate_pct}% WR
                </div>
                <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "2px" }}>
                  Net P&L: ₹{result.performance_breakdown.short.net_pnl.toLocaleString()}
                </div>
              </div>

              <div style={{ background: "#111827", border: "1px solid #1f2937", borderRadius: "8px", padding: "12px" }}>
                <div style={{ fontSize: "11px", color: "#9ca3af" }}>STATUTORY FEES & FRICTION</div>
                <div style={{ fontSize: "16px", fontWeight: "700", color: "#f59e0b", marginTop: "2px" }}>
                  ₹{(result.summary.total_statutory_fees || 0).toLocaleString()} Fees
                </div>
                <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "2px" }}>
                  Slippage: ₹{(result.summary.total_slippage || 0).toLocaleString()}
                </div>
              </div>
            </div>
          )}

          {/* Equity Progression Panel */}
          <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
              <h3 style={{ margin: 0, fontSize: "15px", color: "#fff" }}>
                Simulated Equity Progression Curve (Base ₹1,00,000)
              </h3>
              <span style={{ fontSize: "11px", color: "#9ca3af" }}>
                Includes STT, Exchange fees, GST, Stamp Duty & Slippage
              </span>
            </div>
            {renderEquityCurve(result.equity_curve)}
          </div>

          {/* Chronological Trade Log Table */}
          <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
            <h3 style={{ margin: "0 0 14px", fontSize: "15px", color: "#fff" }}>
              Chronological Trade Log ({result.trades.length} Executions)
            </h3>
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
                <thead>
                  <tr style={{ background: "#1f2937", color: "#9ca3af", textAlign: "left" }}>
                    <th style={{ padding: "8px 10px" }}>#</th>
                    <th style={{ padding: "8px 10px" }}>DIRECTION</th>
                    <th style={{ padding: "8px 10px" }}>REGIME</th>
                    <th style={{ padding: "8px 10px" }}>ENTRY</th>
                    <th style={{ padding: "8px 10px" }}>STOP LOSS</th>
                    <th style={{ padding: "8px 10px" }}>TARGET</th>
                    <th style={{ padding: "8px 10px" }}>EXIT</th>
                    <th style={{ padding: "8px 10px" }}>OUTCOME</th>
                    <th style={{ padding: "8px 10px" }}>NET P&L (₹)</th>
                    <th style={{ padding: "8px 10px" }}>NET %</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((tr) => {
                    const isWin = tr.outcome === "WIN";
                    const isBull = tr.direction === "BULLISH";
                    return (
                      <tr key={tr.trade_id} style={{ borderBottom: "1px solid #1f2937" }}>
                        <td style={{ padding: "8px 10px", color: "#9ca3af" }}>{tr.trade_id}</td>
                        <td style={{ padding: "8px 10px" }}>
                          <span
                            style={{
                              fontSize: "10px",
                              fontWeight: "700",
                              padding: "2px 6px",
                              borderRadius: "4px",
                              background: isBull ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)",
                              color: isBull ? "#4ade80" : "#f87171",
                            }}
                          >
                            {tr.direction}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px", color: "#cbd5e1", fontSize: "11px" }}>
                          {tr.regime || "GENERAL"}
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          <strong>₹{tr.entry_price.toFixed(2)}</strong>
                          <div style={{ fontSize: "10px", color: "#6b7280" }}>{tr.entry_time?.split("T")[0]}</div>
                        </td>
                        <td style={{ padding: "8px 10px", color: "#f87171" }}>₹{tr.stop_loss.toFixed(2)}</td>
                        <td style={{ padding: "8px 10px", color: "#4ade80" }}>₹{tr.take_profit.toFixed(2)}</td>
                        <td style={{ padding: "8px 10px" }}>
                          <strong>₹{tr.exit_price.toFixed(2)}</strong>
                          <div style={{ fontSize: "10px", color: "#6b7280" }}>{tr.exit_time?.split("T")[0]}</div>
                        </td>
                        <td style={{ padding: "8px 10px" }}>
                          <span
                            style={{
                              fontSize: "10px",
                              fontWeight: "700",
                              padding: "2px 6px",
                              borderRadius: "4px",
                              background: isWin ? "rgba(34, 197, 94, 0.2)" : "rgba(239, 68, 68, 0.2)",
                              color: isWin ? "#4ade80" : "#f87171",
                            }}
                          >
                            {tr.outcome}
                          </span>
                        </td>
                        <td style={{ padding: "8px 10px", fontWeight: "700", color: (tr.net_pnl || 0) >= 0 ? "#22c55e" : "#ef4444" }}>
                          ₹{tr.net_pnl?.toFixed(2) || "0.00"}
                        </td>
                        <td
                          style={{
                            padding: "8px 10px",
                            fontWeight: "700",
                            color: tr.net_pnl_pct >= 0 ? "#22c55e" : "#ef4444",
                          }}
                        >
                          {tr.net_pnl_pct > 0 ? "+" : ""}{tr.net_pnl_pct}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Walk-Forward Out-Of-Sample Sub-Tab */}
      {activeSubTab === "WALK_FORWARD" && wfResult && (
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
            <h3 style={{ margin: "0 0 8px", fontSize: "16px", color: "#fff" }}>
              Walk-Forward Out-Of-Sample Audit Verdict
            </h3>
            <div
              style={{
                fontSize: "15px",
                fontWeight: "700",
                color: wfResult.overfitting_audit.is_statistically_robust ? "#22c55e" : "#f59e0b",
                marginBottom: "12px",
              }}
            >
              {wfResult.overfitting_audit.verdict}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "12px" }}>
              <div style={{ background: "#1f2937", padding: "12px", borderRadius: "8px" }}>
                <div style={{ fontSize: "11px", color: "#9ca3af" }}>IN-SAMPLE (TRAIN) WIN RATE</div>
                <div style={{ fontSize: "20px", fontWeight: "700", color: "#38bdf8", marginTop: "2px" }}>
                  {wfResult.overfitting_audit.in_sample_win_rate}%
                </div>
                <div style={{ fontSize: "10px", color: "#6b7280" }}>{wfResult.train_period.bars} candles</div>
              </div>
              <div style={{ background: "#1f2937", padding: "12px", borderRadius: "8px" }}>
                <div style={{ fontSize: "11px", color: "#9ca3af" }}>OUT-OF-SAMPLE (TEST) WIN RATE</div>
                <div style={{ fontSize: "20px", fontWeight: "700", color: "#22c55e", marginTop: "2px" }}>
                  {wfResult.overfitting_audit.out_of_sample_win_rate}%
                </div>
                <div style={{ fontSize: "10px", color: "#6b7280" }}>{wfResult.test_period_oos.bars} candles</div>
              </div>
              <div style={{ background: "#1f2937", padding: "12px", borderRadius: "8px" }}>
                <div style={{ fontSize: "11px", color: "#9ca3af" }}>DEGRADATION PTS</div>
                <div style={{ fontSize: "20px", fontWeight: "700", color: wfResult.overfitting_audit.degradation_pts <= 15 ? "#22c55e" : "#f87171", marginTop: "2px" }}>
                  {wfResult.overfitting_audit.degradation_pts} pts
                </div>
                <div style={{ fontSize: "10px", color: "#6b7280" }}>Max tolerance: 15.0 pts</div>
              </div>
            </div>
          </div>

          {/* Regime Breakdown */}
          <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
            <h3 style={{ margin: "0 0 12px", fontSize: "15px", color: "#fff" }}>
              Strategy Performance Across Market Regimes
            </h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "10px" }}>
              {Object.entries(wfResult.regime_breakdown).map(([regime, stats]) => (
                <div key={regime} style={{ background: "#1f2937", padding: "12px", borderRadius: "8px" }}>
                  <div style={{ fontSize: "11px", fontWeight: "700", color: "#38bdf8" }}>{regime}</div>
                  <div style={{ fontSize: "18px", fontWeight: "800", color: "#fff", marginTop: "4px" }}>
                    {stats.win_rate_pct}% WR
                  </div>
                  <div style={{ fontSize: "11px", color: "#9ca3af", marginTop: "2px" }}>
                    {stats.trades_count} Trades · Net: ₹{stats.net_pnl.toLocaleString()}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Parameter Robustness Grid Sub-Tab */}
      {activeSubTab === "SENSITIVITY" && sensResult && (
        <div style={{ background: "#111827", borderRadius: "10px", border: "1px solid #1f2937", padding: "20px" }}>
          <h3 style={{ margin: "0 0 6px", fontSize: "16px", color: "#fff" }}>
            Parameter Sensitivity & Overfitting Grid
          </h3>
          <div style={{ fontSize: "13px", fontWeight: "700", color: "#22c55e", marginBottom: "16px" }}>
            {sensResult.robustness_verdict}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "12px", marginBottom: "20px" }}>
            <div style={{ background: "#1f2937", padding: "12px", borderRadius: "8px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>MEAN WIN RATE</div>
              <div style={{ fontSize: "18px", fontWeight: "700", color: "#38bdf8", marginTop: "2px" }}>
                {sensResult.metrics_distribution.win_rate_mean}%
              </div>
            </div>
            <div style={{ background: "#1f2937", padding: "12px", borderRadius: "8px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>WIN RATE STD DEV</div>
              <div style={{ fontSize: "18px", fontWeight: "700", color: "#f59e0b", marginTop: "2px" }}>
                ±{sensResult.metrics_distribution.win_rate_std}%
              </div>
            </div>
            <div style={{ background: "#1f2937", padding: "12px", borderRadius: "8px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>MIN / MAX WIN RATE</div>
              <div style={{ fontSize: "18px", fontWeight: "700", color: "#fff", marginTop: "2px" }}>
                {sensResult.metrics_distribution.win_rate_min}% - {sensResult.metrics_distribution.win_rate_max}%
              </div>
            </div>
            <div style={{ background: "#1f2937", padding: "12px", borderRadius: "8px" }}>
              <div style={{ fontSize: "11px", color: "#9ca3af" }}>MEAN PROFIT FACTOR</div>
              <div style={{ fontSize: "18px", fontWeight: "700", color: "#22c55e", marginTop: "2px" }}>
                {sensResult.metrics_distribution.profit_factor_mean}
              </div>
            </div>
          </div>

          {/* Grid Table */}
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px" }}>
              <thead>
                <tr style={{ background: "#1f2937", color: "#9ca3af", textAlign: "left" }}>
                  <th style={{ padding: "8px 10px" }}>TARGET R:R</th>
                  <th style={{ padding: "8px 10px" }}>MAX HOLD BARS</th>
                  <th style={{ padding: "8px 10px" }}>TRADES</th>
                  <th style={{ padding: "8px 10px" }}>WIN RATE %</th>
                  <th style={{ padding: "8px 10px" }}>PROFIT FACTOR</th>
                  <th style={{ padding: "8px 10px" }}>NET RETURN %</th>
                </tr>
              </thead>
              <tbody>
                {sensResult.detailed_grid.map((row, idx) => (
                  <tr key={idx} style={{ borderBottom: "1px solid #1f2937" }}>
                    <td style={{ padding: "8px 10px", fontWeight: "700" }}>{row.target_rr}x</td>
                    <td style={{ padding: "8px 10px" }}>{row.max_holding_bars} bars</td>
                    <td style={{ padding: "8px 10px" }}>{row.trades}</td>
                    <td style={{ padding: "8px 10px", color: row.win_rate_pct >= 50 ? "#22c55e" : "#f87171" }}>
                      {row.win_rate_pct}%
                    </td>
                    <td style={{ padding: "8px 10px" }}>{row.profit_factor}</td>
                    <td style={{ padding: "8px 10px", fontWeight: "700", color: row.net_return_pct >= 0 ? "#22c55e" : "#ef4444" }}>
                      {row.net_return_pct > 0 ? "+" : ""}{row.net_return_pct}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

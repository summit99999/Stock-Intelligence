import React, { useState, useEffect, useMemo } from "react";

interface Metadata {
  data_mode: string;
  provider: string;
  instrument: string;
  timeframe: string;
  last_updated: string;
  universe?: string;
  coverage?: {
    configured_instruments: number;
    tracked_instruments: number;
    coverage_pct: number;
    disclosure: string;
  };
}

interface ComponentScore {
  score: number;
  max: number;
  rationale: string;
}

interface StockSetupItem {
  rank?: number;
  symbol: string;
  company_name: string;
  sector: string;
  close: number;
  daily_change_pct: number;
  relative_volume: number;
  setup_score: number;
  setup_category: string;
  direction: "BULLISH" | "BEARISH";
  available_components_count: number;
  total_components_count: number;
  component_breakdown: Record<string, ComponentScore>;
  top_setup?: any;
  probability_disclaimer: string;
}

interface SectorRotationItem {
  sector: string;
  stock_count: number;
  average_change_pct: number;
  breadth_pct: number;
  relative_strength_vs_market: number;
  rotation_quadrant: "LEADING" | "WEAKENING" | "DECLINING" | "IMPROVING" | "NEUTRAL";
  quadrant_color: string;
  strongest_stock: { symbol: string; change_pct: number; close: number };
  weakest_stock: { symbol: string; change_pct: number; close: number };
}

interface MarketRegimeData {
  timestamp: string;
  universe: string;
  universe_label: string;
  regime: string;
  score: number;
  composite_score: number;
  description: string;
  regime_color: string;
  evidence: {
    breadth: {
      advances: number;
      declines: number;
      unchanged: number;
      total_tracked: number;
      advance_decline_ratio: number;
      breadth_pct: number;
      score_contribution: number;
      max_score: number;
    };
    ema_participation: {
      pct_above_ema20: number;
      pct_above_ema50: number;
      pct_above_ema200: number;
      score_contribution: number;
      max_score: number;
    };
    sector_participation: {
      total_sectors: number;
      advancing_sectors: number;
      advancing_sectors_pct: number;
      score_contribution: number;
      max_score: number;
    };
    trend_strength: {
      average_adx: number;
      pct_strong_adx: number;
      pct_supertrend_bullish: number;
      score_contribution: number;
      max_score: number;
    };
    momentum: {
      average_market_change_pct: number;
      return_dispersion_std_pct: number;
      score_contribution: number;
      max_score: number;
    };
  };
  volatility_context: {
    vix_status: string;
    return_dispersion_std_pct: number;
    disclaimer: string;
  };
  coverage: {
    configured_instruments: number;
    tracked_instruments: number;
    coverage_pct: number;
    disclosure: string;
  };
  limitations: string;
}

interface TradePlan {
  symbol: string;
  company_name: string;
  sector: string;
  direction: string;
  setup_score: number;
  setup_category: string;
  current_market_price: number;
  entry_plan: {
    entry_type: string;
    ideal_entry: number;
    entry_zone_min: number;
    entry_zone_max: number;
  };
  exit_plan: {
    stop_loss: number;
    stop_distance: number;
    stop_reason: string;
    invalidation_condition: string;
    target_1: { price: number; risk_reward_ratio: number; description: string };
    target_2: { price: number; risk_reward_ratio: number; description: string };
  };
  position_sizing: {
    account_capital: number;
    risk_per_trade_pct: number;
    risk_amount_inr: number;
    recommended_shares: number;
    capital_allocated_inr: number;
    portfolio_heat_pct: number;
  };
  guardrail_warnings: string[];
  risk_factors: string[];
  evidence_list: { component: string; score: number; max: number; weight_pct: number; rationale: string }[];
  disclaimer: string;
}

interface HistoricalValidation {
  symbol: string;
  company_name: string;
  setup_type: string;
  sample_size_assessment: {
    total_occurrences: number;
    is_statistically_reliable: boolean;
    reliability_tier: string;
    warning: string;
  };
  performance_metrics: {
    win_rate_pct: number;
    wilson_ci_95: { lower_bound_pct?: number; upper_bound_pct?: number; center_pct?: number };
    profit_factor: number;
    target_risk_reward: number;
    max_drawdown_pct: number;
    average_holding_bars: number;
    gross_profit: number;
    gross_loss: number;
    total_statutory_fees: number;
    total_slippage: number;
  };
  regime_dependence: Record<string, { trades: number; win_rate_pct: number; profit_factor: number; net_pnl: number }>;
  recent_trades: any[];
  disclaimers: string[];
}

interface UnifiedResearchDashboardViewProps {
  onSelectStock?: (symbol: string) => void;
}

export default function UnifiedResearchDashboardView({
  onSelectStock,
}: UnifiedResearchDashboardViewProps) {
  // Navigation tabs
  const [activeTab, setActiveTab] = useState<"overview" | "trade_planner" | "validation" | "saved_plans" | "notes">("overview");

  // Filters
  const [universe, setUniverse] = useState<string>("all");
  const [directionFilter, setDirectionFilter] = useState<string>("ALL");
  const [minScore, setMinScore] = useState<number>(0);
  const [sectorFilter, setSectorFilter] = useState<string>("ALL");

  // Data states
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [marketRegime, setMarketRegime] = useState<MarketRegimeData | null>(null);
  const [sectorsData, setSectorsData] = useState<{ sectors: SectorRotationItem[] } | null>(null);
  const [discoveredStocks, setDiscoveredStocks] = useState<StockSetupItem[]>([]);
  const [totalRecords, setTotalRecords] = useState<number>(0);

  // Trade Plan Generator State
  const [planSymbol, setPlanSymbol] = useState<string>("RELIANCE");
  const [planCapital, setPlanCapital] = useState<number>(100000);
  const [planRiskPct, setPlanRiskPct] = useState<number>(1.0);
  const [planTargetRR, setPlanTargetRR] = useState<number>(2.0);
  const [generatedPlan, setGeneratedPlan] = useState<TradePlan | null>(null);
  const [planLoading, setPlanLoading] = useState<boolean>(false);
  const [planSaveMsg, setPlanSaveMsg] = useState<string | null>(null);

  // Saved Plans & Notes
  const [savedPlans, setSavedPlans] = useState<any[]>([]);
  const [savedNotes, setSavedNotes] = useState<any[]>([]);
  const [newNoteText, setNewNoteText] = useState<string>("");
  const [newNoteTitle, setNewNoteTitle] = useState<string>("");

  // Validation State
  const [valSymbol, setValSymbol] = useState<string>("RELIANCE");
  const [valSetupType, setValSetupType] = useState<string>("ORDER_BLOCK_RETEST");
  const [validationResult, setValidationResult] = useState<HistoricalValidation | null>(null);
  const [valLoading, setValLoading] = useState<boolean>(false);

  // Stock Detail Modal Dossier
  const [modalSymbol, setModalSymbol] = useState<string | null>(null);
  const [dossierData, setDossierData] = useState<any | null>(null);
  const [dossierLoading, setDossierLoading] = useState<boolean>(false);

  // ---------------------------------------------------------------------------
  // Load Overview Data
  // ---------------------------------------------------------------------------
  const fetchOverviewData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [regimeRes, sectorsRes, discRes] = await Promise.all([
        fetch(`http://127.0.0.1:8000/api/research/regime?universe=${universe}`),
        fetch(`http://127.0.0.1:8000/api/research/sectors?universe=${universe}`),
        fetch(
          `http://127.0.0.1:8000/api/research/discovery?universe=${universe}&direction=${directionFilter === "ALL" ? "" : directionFilter}&min_score=${minScore}&sector=${sectorFilter === "ALL" ? "" : sectorFilter}&page_size=50`
        ),
      ]);

      if (regimeRes.ok) setMarketRegime(await regimeRes.json());
      if (sectorsRes.ok) setSectorsData(await sectorsRes.json());
      if (discRes.ok) {
        const d = await discRes.json();
        setDiscoveredStocks(d.items || []);
        setTotalRecords(d.total_records || 0);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load research data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOverviewData();
  }, [universe, directionFilter, minScore, sectorFilter]);

  // Load Saved Plans
  const fetchSavedPlans = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/api/research/trade-plans");
      if (res.ok) setSavedPlans(await res.json());
    } catch (e) {
      console.error("Error loading trade plans:", e);
    }
  };

  // Load Notes
  const fetchSavedNotes = async (sym?: string) => {
    try {
      const url = sym ? `http://127.0.0.1:8000/api/research/notes/${sym}` : `http://127.0.0.1:8000/api/research/notes/RELIANCE`;
      const res = await fetch(url);
      if (res.ok) setSavedNotes(await res.json());
    } catch (e) {
      console.error("Error loading notes:", e);
    }
  };

  useEffect(() => {
    fetchSavedPlans();
    fetchSavedNotes();
  }, []);

  // ---------------------------------------------------------------------------
  // Action Handlers
  // ---------------------------------------------------------------------------
  const handleGenerateTradePlan = async (symbolToPlan?: string) => {
    const sym = symbolToPlan || planSymbol;
    setPlanSymbol(sym);
    setPlanLoading(true);
    setPlanSaveMsg(null);
    try {
      const res = await fetch("http://127.0.0.1:8000/api/research/trade-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: sym,
          account_capital: planCapital,
          risk_pct: planRiskPct,
          target_rr: planTargetRR,
        }),
      });
      if (res.ok) {
        setGeneratedPlan(await res.json());
        setActiveTab("trade_planner");
      }
    } catch (e: any) {
      console.error("Error generating trade plan:", e);
    } finally {
      setPlanLoading(false);
    }
  };

  const handleSaveTradePlan = async () => {
    if (!generatedPlan) return;
    try {
      const payload = {
        symbol: generatedPlan.symbol,
        direction: generatedPlan.direction,
        setup_type: generatedPlan.setup_category,
        entry_type: generatedPlan.entry_plan.entry_type,
        entry_min: generatedPlan.entry_plan.entry_zone_min,
        entry_max: generatedPlan.entry_plan.entry_zone_max,
        ideal_entry: generatedPlan.entry_plan.ideal_entry,
        stop_loss: generatedPlan.exit_plan.stop_loss,
        target_1: generatedPlan.exit_plan.target_1.price,
        target_2: generatedPlan.exit_plan.target_2.price,
        risk_reward_ratio: generatedPlan.exit_plan.target_1.risk_reward_ratio,
        position_size: generatedPlan.position_sizing.recommended_shares,
        risk_amount: generatedPlan.position_sizing.risk_amount_inr,
        capital_allocated: generatedPlan.position_sizing.capital_allocated_inr,
        invalidation_condition: generatedPlan.exit_plan.invalidation_condition,
        failure_risks: JSON.stringify(generatedPlan.risk_factors),
        evidence: JSON.stringify(generatedPlan.evidence_list),
        notes: `Hypothetical trade plan generated for ${generatedPlan.symbol}`,
      };
      const res = await fetch("http://127.0.0.1:8000/api/research/trade-plans/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        setPlanSaveMsg("✓ Plan successfully saved to research watchlist.");
        fetchSavedPlans();
      }
    } catch (e) {
      setPlanSaveMsg("Failed to save plan.");
    }
  };

  const handleDeleteSavedPlan = async (id: number) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/research/trade-plans/${id}`, { method: "DELETE" });
      if (res.ok) fetchSavedPlans();
    } catch (e) {
      console.error(e);
    }
  };

  const handleUpdatePlanStatus = async (id: number, newStatus: string) => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/research/trade-plans/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
      if (res.ok) fetchSavedPlans();
    } catch (e) {
      console.error(e);
    }
  };

  const handleValidateSetup = async () => {
    setValLoading(true);
    try {
      const res = await fetch("http://127.0.0.1:8000/api/research/validate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: valSymbol,
          setup_type: valSetupType,
          initial_capital: 100000,
          risk_pct: 1.0,
          target_rr: 2.0,
        }),
      });
      if (res.ok) setValidationResult(await res.json());
    } catch (e) {
      console.error("Error validating setup:", e);
    } finally {
      setValLoading(false);
    }
  };

  const handleOpenDossier = async (symbol: string) => {
    setModalSymbol(symbol);
    setDossierLoading(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/research/stock/${symbol}`);
      if (res.ok) setDossierData(await res.json());
    } catch (e) {
      console.error(e);
    } finally {
      setDossierLoading(false);
    }
  };

  const handleAddNote = async () => {
    if (!newNoteText.trim()) return;
    try {
      const sym = modalSymbol || planSymbol;
      const res = await fetch("http://127.0.0.1:8000/api/research/notes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol: sym,
          title: newNoteTitle || "Research Observation",
          note: newNoteText,
          tags: "manual,analysis",
        }),
      });
      if (res.ok) {
        setNewNoteText("");
        setNewNoteTitle("");
        fetchSavedNotes(sym);
      }
    } catch (e) {
      console.error(e);
    }
  };

  // Filtered Opportunities Lists
  const topBullish = useMemo(
    () => discoveredStocks.filter((s) => s.direction === "BULLISH").slice(0, 5),
    [discoveredStocks]
  );
  const topBearish = useMemo(
    () => discoveredStocks.filter((s) => s.direction === "BEARISH").slice(0, 5),
    [discoveredStocks]
  );
  const developingSetups = useMemo(
    () => discoveredStocks.filter((s) => s.setup_category === "DEVELOPING SETUP"),
    [discoveredStocks]
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px", color: "#e2e8f0" }}>
      {/* --------------------------------------------------------------------- */}
      {/* 1. Header & Navigation Controls */}
      {/* --------------------------------------------------------------------- */}
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
            <span style={{ fontSize: "24px" }}>🔬</span>
            <h1 style={{ margin: 0, fontSize: "22px", color: "#fff", fontWeight: 700, letterSpacing: "0.5px" }}>
              UNIFIED TRADING RESEARCH & DECISION ENGINE
            </h1>
            <span
              style={{
                fontSize: "11px",
                padding: "3px 8px",
                borderRadius: "4px",
                background: "rgba(59, 130, 246, 0.2)",
                color: "#60a5fa",
                border: "1px solid rgba(59, 130, 246, 0.3)",
                fontWeight: 600,
              }}
            >
              PHASE 12
            </span>
            <span
              style={{
                fontSize: "11px",
                padding: "3px 8px",
                borderRadius: "4px",
                background: "rgba(239, 68, 68, 0.2)",
                color: "#f87171",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                fontWeight: 600,
              }}
            >
              DECISION-SUPPORT ONLY • NO AUTO TRADING
            </span>
          </div>
          <p style={{ margin: "6px 0 0 0", color: "#8c9bb0", fontSize: "13px" }}>
            Evidence-based synthesis connecting Market Regime, Sector Rotation, 100-Point Setup Confluence,
            and Statistically Validated Trade Plans.
          </p>
        </div>

        {/* Global Controls & Refresh */}
        <div style={{ display: "flex", gap: "12px", alignItems: "center" }}>
          <select
            value={universe}
            onChange={(e) => setUniverse(e.target.value)}
            style={{
              background: "#0a0f18",
              color: "#e2e8f0",
              border: "1px solid #2d3f58",
              borderRadius: "6px",
              padding: "8px 12px",
              fontSize: "13px",
              fontWeight: 500,
            }}
          >
            <option value="all">All Tracked NSE Stocks</option>
            <option value="nifty50">NIFTY 50 Universe</option>
            <option value="nifty100">NIFTY 100 Universe</option>
            <option value="nifty500">NIFTY 500 Universe</option>
            <option value="fno">NSE F&O Equities</option>
          </select>

          <button
            onClick={() => fetchOverviewData()}
            disabled={loading}
            style={{
              background: loading ? "#1e2c40" : "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              padding: "8px 16px",
              fontSize: "13px",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "Scanning..." : "⟳ Refresh Scan"}
          </button>
        </div>
      </div>

      {/* Navigation Tabs Bar */}
      <div style={{ display: "flex", gap: "8px", borderBottom: "1px solid #1e2c40", paddingBottom: "12px" }}>
        {[
          { id: "overview", label: "Overview & Multi-Factor Discovery", icon: "🌐" },
          { id: "trade_planner", label: "Trade Plan Generator & Position Sizing", icon: "📐" },
          { id: "validation", label: "Historical Setup Validation", icon: "⏱" },
          { id: "saved_plans", label: `Saved Trade Plans (${savedPlans.length})`, icon: "📋" },
          { id: "notes", label: `Research Notes (${savedNotes.length})`, icon: "📝" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as any)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              padding: "10px 16px",
              borderRadius: "8px",
              background: activeTab === tab.id ? "#1e293b" : "transparent",
              color: activeTab === tab.id ? "#60a5fa" : "#94a3b8",
              border: activeTab === tab.id ? "1px solid #3b82f6" : "1px solid transparent",
              fontWeight: activeTab === tab.id ? 700 : 500,
              cursor: "pointer",
              fontSize: "13px",
            }}
          >
            <span>{tab.icon}</span>
            <span>{tab.label}</span>
          </button>
        ))}
      </div>

      {error && (
        <div style={{ padding: "12px 16px", background: "rgba(239, 68, 68, 0.15)", border: "1px solid #ef4444", borderRadius: "8px", color: "#fca5a5" }}>
          ⚠️ {error}
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* TAB 1: OVERVIEW & MULTI-FACTOR DISCOVERY */}
      {/* --------------------------------------------------------------------- */}
      {activeTab === "overview" && (
        <>
          {/* Section 1: Market Regime Engine Card */}
          {marketRegime && (
            <div
              style={{
                background: "linear-gradient(180deg, #131c2a 0%, #0b111a 100%)",
                borderRadius: "12px",
                border: "1px solid #1e2c40",
                padding: "24px",
                display: "flex",
                flexDirection: "column",
                gap: "20px",
              }}
            >
              {/* Top Banner */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                    <span style={{ fontSize: "12px", textTransform: "uppercase", color: "#94a3b8", fontWeight: 700, letterSpacing: "1px" }}>
                      SECTION 1 • MARKET REGIME ENGINE
                    </span>
                    <span
                      style={{
                        padding: "4px 12px",
                        borderRadius: "20px",
                        fontSize: "13px",
                        fontWeight: 800,
                        background: marketRegime.regime_color || "#3b82f6",
                        color: "#fff",
                        letterSpacing: "0.5px",
                      }}
                    >
                      {marketRegime.regime}
                    </span>
                    <span style={{ fontSize: "14px", fontWeight: 700, color: "#fff" }}>
                      Score: {marketRegime.score.toFixed(1)} / 100
                    </span>
                  </div>
                  <p style={{ margin: "8px 0 0 0", color: "#cbd5e1", fontSize: "14px", maxWidth: "800px" }}>
                    {marketRegime.description}
                  </p>
                </div>

                {/* VIX & Coverage Tag */}
                <div style={{ display: "flex", flexDirection: "column", gap: "6px", alignItems: "flex-end" }}>
                  <div style={{ display: "flex", gap: "8px" }}>
                    <span style={{ fontSize: "11px", background: "rgba(245, 158, 11, 0.2)", color: "#f59e0b", padding: "3px 8px", borderRadius: "4px", border: "1px solid rgba(245, 158, 11, 0.3)" }}>
                      INDIA VIX: UNAVAILABLE (Options Feed Inactive)
                    </span>
                    <span style={{ fontSize: "11px", background: "rgba(96, 165, 250, 0.2)", color: "#60a5fa", padding: "3px 8px", borderRadius: "4px", border: "1px solid rgba(96, 165, 250, 0.3)" }}>
                      Sample: {marketRegime.coverage?.tracked_instruments} / {marketRegime.coverage?.configured_instruments} ({marketRegime.coverage?.coverage_pct}%)
                    </span>
                  </div>
                  <span style={{ fontSize: "11px", color: "#64748b" }}>
                    Dispersion Proxy Std: {marketRegime.volatility_context?.return_dispersion_std_pct}%
                  </span>
                </div>
              </div>

              {/* 5 Evidence Factor Cards Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px" }}>
                {/* Breadth */}
                <div style={{ background: "#0a0f18", padding: "14px", borderRadius: "8px", border: "1px solid #1a2636" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#94a3b8", fontWeight: 600 }}>1. Market Breadth</span>
                    <span style={{ fontSize: "12px", color: "#38bdf8", fontWeight: 700 }}>
                      {marketRegime.evidence?.breadth?.score_contribution.toFixed(1)} / 25
                    </span>
                  </div>
                  <div style={{ fontSize: "16px", fontWeight: 700, color: "#fff", marginBottom: "4px" }}>
                    {marketRegime.evidence?.breadth?.advance_decline_ratio.toFixed(2)} : 1 A/D
                  </div>
                  <div style={{ fontSize: "12px", color: "#64748b" }}>
                    ▲ {marketRegime.evidence?.breadth?.advances} | ▼ {marketRegime.evidence?.breadth?.declines} ({marketRegime.evidence?.breadth?.breadth_pct.toFixed(1)}%)
                  </div>
                </div>

                {/* EMA Participation */}
                <div style={{ background: "#0a0f18", padding: "14px", borderRadius: "8px", border: "1px solid #1a2636" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#94a3b8", fontWeight: 600 }}>2. EMA Participation</span>
                    <span style={{ fontSize: "12px", color: "#38bdf8", fontWeight: 700 }}>
                      {marketRegime.evidence?.ema_participation?.score_contribution.toFixed(1)} / 25
                    </span>
                  </div>
                  <div style={{ fontSize: "16px", fontWeight: 700, color: "#fff", marginBottom: "4px" }}>
                    {marketRegime.evidence?.ema_participation?.pct_above_ema50.toFixed(1)}% &gt; EMA 50
                  </div>
                  <div style={{ fontSize: "12px", color: "#64748b" }}>
                    &gt; EMA20: {marketRegime.evidence?.ema_participation?.pct_above_ema20.toFixed(1)}% | &gt; EMA200: {marketRegime.evidence?.ema_participation?.pct_above_ema200.toFixed(1)}%
                  </div>
                </div>

                {/* Sector Strength */}
                <div style={{ background: "#0a0f18", padding: "14px", borderRadius: "8px", border: "1px solid #1a2636" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#94a3b8", fontWeight: 600 }}>3. Sector Participation</span>
                    <span style={{ fontSize: "12px", color: "#38bdf8", fontWeight: 700 }}>
                      {marketRegime.evidence?.sector_participation?.score_contribution.toFixed(1)} / 20
                    </span>
                  </div>
                  <div style={{ fontSize: "16px", fontWeight: 700, color: "#fff", marginBottom: "4px" }}>
                    {marketRegime.evidence?.sector_participation?.advancing_sectors_pct.toFixed(1)}% Advancing
                  </div>
                  <div style={{ fontSize: "12px", color: "#64748b" }}>
                    {marketRegime.evidence?.sector_participation?.advancing_sectors} of {marketRegime.evidence?.sector_participation?.total_sectors} sectors positive
                  </div>
                </div>

                {/* Trend Strength */}
                <div style={{ background: "#0a0f18", padding: "14px", borderRadius: "8px", border: "1px solid #1a2636" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#94a3b8", fontWeight: 600 }}>4. Trend Strength</span>
                    <span style={{ fontSize: "12px", color: "#38bdf8", fontWeight: 700 }}>
                      {marketRegime.evidence?.trend_strength?.score_contribution.toFixed(1)} / 15
                    </span>
                  </div>
                  <div style={{ fontSize: "16px", fontWeight: 700, color: "#fff", marginBottom: "4px" }}>
                    ADX: {marketRegime.evidence?.trend_strength?.average_adx.toFixed(1)}
                  </div>
                  <div style={{ fontSize: "12px", color: "#64748b" }}>
                    Strong ADX: {marketRegime.evidence?.trend_strength?.pct_strong_adx.toFixed(1)}% | Supertrend: {marketRegime.evidence?.trend_strength?.pct_supertrend_bullish.toFixed(1)}%
                  </div>
                </div>

                {/* Momentum */}
                <div style={{ background: "#0a0f18", padding: "14px", borderRadius: "8px", border: "1px solid #1a2636" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                    <span style={{ fontSize: "12px", color: "#94a3b8", fontWeight: 600 }}>5. Relative Momentum</span>
                    <span style={{ fontSize: "12px", color: "#38bdf8", fontWeight: 700 }}>
                      {marketRegime.evidence?.momentum?.score_contribution.toFixed(1)} / 15
                    </span>
                  </div>
                  <div style={{ fontSize: "16px", fontWeight: 700, color: "#fff", marginBottom: "4px" }}>
                    {marketRegime.evidence?.momentum?.average_market_change_pct.toFixed(2)}% Avg Chg
                  </div>
                  <div style={{ fontSize: "12px", color: "#64748b" }}>
                    Cross-constituent dispersion: ±{marketRegime.evidence?.momentum?.return_dispersion_std_pct.toFixed(2)}%
                  </div>
                </div>
              </div>

              {/* Strict Limitations Footer */}
              <div style={{ fontSize: "11px", color: "#64748b", borderTop: "1px solid #1e2c40", paddingTop: "12px" }}>
                ℹ️ <strong>Truth in Data:</strong> {marketRegime.limitations}
              </div>
            </div>
          )}

          {/* Section 2: Sector Rotation Engine (4 Quadrants) */}
          {sectorsData && (
            <div style={{ background: "#111827", borderRadius: "12px", border: "1px solid #1e293b", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: "16px", color: "#fff", fontWeight: 700 }}>
                    SECTION 2 • SECTOR ROTATION ENGINE (4 QUADRANTS)
                  </h3>
                  <p style={{ margin: "4px 0 0 0", color: "#94a3b8", fontSize: "12px" }}>
                    Leading vs Lagging quadrants evaluated via relative strength and internal sector breadth (% &gt; EMA 20).
                  </p>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "14px" }}>
                {sectorsData.sectors.map((sec) => (
                  <div
                    key={sec.sector}
                    style={{
                      background: "#0f172a",
                      border: `1px solid ${sec.quadrant_color || "#334155"}`,
                      borderRadius: "8px",
                      padding: "14px",
                      display: "flex",
                      flexDirection: "column",
                      gap: "8px",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: 700, color: "#fff", fontSize: "14px" }}>{sec.sector}</span>
                      <span
                        style={{
                          fontSize: "10px",
                          fontWeight: 700,
                          padding: "2px 8px",
                          borderRadius: "4px",
                          background: sec.quadrant_color || "#3b82f6",
                          color: "#fff",
                        }}
                      >
                        {sec.rotation_quadrant}
                      </span>
                    </div>

                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", color: "#94a3b8" }}>
                      <span>Avg Return: <strong style={{ color: sec.average_change_pct >= 0 ? "#10b981" : "#ef4444" }}>{sec.average_change_pct.toFixed(2)}%</strong></span>
                      <span>Breadth: <strong style={{ color: "#e2e8f0" }}>{sec.breadth_pct.toFixed(1)}%</strong></span>
                      <span>RS vs Mkt: <strong style={{ color: sec.relative_strength_vs_market >= 0 ? "#10b981" : "#ef4444" }}>{sec.relative_strength_vs_market > 0 ? "+" : ""}{sec.relative_strength_vs_market.toFixed(2)}%</strong></span>
                    </div>

                    <div style={{ fontSize: "11px", color: "#64748b", borderTop: "1px solid #1e293b", paddingTop: "6px" }}>
                      Top: <strong style={{ color: "#38bdf8" }}>{sec.strongest_stock?.symbol}</strong> ({sec.strongest_stock?.change_pct?.toFixed(2)}%) • Low: <strong style={{ color: "#f87171" }}>{sec.weakest_stock?.symbol}</strong> ({sec.weakest_stock?.change_pct?.toFixed(2)}%)
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Section 3 & 4: Top Opportunities (100-Point Setup Ranking) */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
            {/* Top Bullish Opportunities */}
            <div style={{ background: "#111827", borderRadius: "12px", border: "1px solid #1e293b", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: "15px", color: "#10b981", fontWeight: 700 }}>
                    ▲ TOP BULLISH OPPORTUNITIES (RANKED BY 100-PT SCORE)
                  </h3>
                  <span style={{ fontSize: "11px", color: "#64748b" }}>
                    Multi-factor confluence (7 components). Heuristic rating, NOT win probability.
                  </span>
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {topBullish.map((item) => (
                  <div
                    key={item.symbol}
                    style={{
                      background: "#0f172a",
                      border: "1px solid #1e293b",
                      borderRadius: "8px",
                      padding: "12px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <strong style={{ color: "#fff", fontSize: "14px", cursor: "pointer" }} onClick={() => handleOpenDossier(item.symbol)}>
                          {item.symbol}
                        </strong>
                        <span style={{ fontSize: "11px", color: "#94a3b8" }}>{item.sector}</span>
                        <span style={{ fontSize: "11px", color: "#10b981", fontWeight: 700 }}>
                          +{item.daily_change_pct.toFixed(2)}%
                        </span>
                      </div>
                      <div style={{ fontSize: "11px", color: "#64748b", marginTop: "4px" }}>
                        CMP: ₹{item.close.toFixed(2)} • RVOL: {item.relative_volume.toFixed(2)}x • {item.setup_category}
                      </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: "16px", fontWeight: 800, color: "#10b981" }}>
                          {item.setup_score.toFixed(1)}
                        </div>
                        <span style={{ fontSize: "10px", color: "#64748b" }}>/ 100 PTS</span>
                      </div>

                      <button
                        onClick={() => handleGenerateTradePlan(item.symbol)}
                        style={{
                          background: "#065f46",
                          color: "#34d399",
                          border: "1px solid #059669",
                          borderRadius: "4px",
                          padding: "6px 10px",
                          fontSize: "11px",
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Trade Plan 📐
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Top Bearish Opportunities */}
            <div style={{ background: "#111827", borderRadius: "12px", border: "1px solid #1e293b", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: "15px", color: "#f87171", fontWeight: 700 }}>
                    ▼ TOP BEARISH OPPORTUNITIES (RANKED BY 100-PT SCORE)
                  </h3>
                  <span style={{ fontSize: "11px", color: "#64748b" }}>
                    Supply zones, breakdowns & negative money flow. Intraday equity shorting.
                  </span>
                </div>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {topBearish.map((item) => (
                  <div
                    key={item.symbol}
                    style={{
                      background: "#0f172a",
                      border: "1px solid #1e293b",
                      borderRadius: "8px",
                      padding: "12px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <strong style={{ color: "#fff", fontSize: "14px", cursor: "pointer" }} onClick={() => handleOpenDossier(item.symbol)}>
                          {item.symbol}
                        </strong>
                        <span style={{ fontSize: "11px", color: "#94a3b8" }}>{item.sector}</span>
                        <span style={{ fontSize: "11px", color: "#f87171", fontWeight: 700 }}>
                          {item.daily_change_pct.toFixed(2)}%
                        </span>
                      </div>
                      <div style={{ fontSize: "11px", color: "#64748b", marginTop: "4px" }}>
                        CMP: ₹{item.close.toFixed(2)} • RVOL: {item.relative_volume.toFixed(2)}x • {item.setup_category}
                      </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: "16px", fontWeight: 800, color: "#f87171" }}>
                          {item.setup_score.toFixed(1)}
                        </div>
                        <span style={{ fontSize: "10px", color: "#64748b" }}>/ 100 PTS</span>
                      </div>

                      <button
                        onClick={() => handleGenerateTradePlan(item.symbol)}
                        style={{
                          background: "#881337",
                          color: "#fda4af",
                          border: "1px solid #be123c",
                          borderRadius: "4px",
                          padding: "6px 10px",
                          fontSize: "11px",
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Trade Plan 📐
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Section 8: Developing Setups (Clearly Separated) */}
          {developingSetups.length > 0 && (
            <div style={{ background: "#111827", borderRadius: "12px", border: "1px solid #f59e0b", padding: "20px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
                <span style={{ fontSize: "18px" }}>⏳</span>
                <div>
                  <h3 style={{ margin: 0, fontSize: "15px", color: "#fbbf24", fontWeight: 700 }}>
                    SECTION 8 • DEVELOPING SETUPS (NOT YET CONFIRMED)
                  </h3>
                  <span style={{ fontSize: "11px", color: "#94a3b8" }}>
                    Price is approaching key structural zones or candles are forming. DO NOT execute until confirmed.
                  </span>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "12px" }}>
                {developingSetups.map((dev) => (
                  <div key={dev.symbol} style={{ background: "#0a0f18", border: "1px solid #2d3748", borderRadius: "8px", padding: "12px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <strong style={{ color: "#fff", cursor: "pointer" }} onClick={() => handleOpenDossier(dev.symbol)}>
                        {dev.symbol}
                      </strong>
                      <span style={{ fontSize: "11px", color: "#fbbf24", background: "rgba(245, 158, 11, 0.15)", padding: "2px 6px", borderRadius: "4px" }}>
                        DEVELOPING
                      </span>
                    </div>
                    <p style={{ margin: "6px 0 0 0", fontSize: "12px", color: "#94a3b8" }}>
                      Setup score: {dev.setup_score} • CMP: ₹{dev.close} • Pending confirmation candle close.
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Section: Complete Stock Discovery Table */}
          <div style={{ background: "#111827", borderRadius: "12px", border: "1px solid #1e293b", padding: "20px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
              <div>
                <h3 style={{ margin: 0, fontSize: "16px", color: "#fff", fontWeight: 700 }}>
                  UNIFIED STOCK DISCOVERY SCAN ({totalRecords} EQUITIES EVALUATED)
                </h3>
                <span style={{ fontSize: "12px", color: "#64748b" }}>
                  Evidence-based ranking combining Technicals, Fundamentals, Money Flow & SMC Structure
                </span>
              </div>

              {/* Filters */}
              <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                <select
                  value={directionFilter}
                  onChange={(e) => setDirectionFilter(e.target.value)}
                  style={{ background: "#0f172a", color: "#fff", border: "1px solid #334155", borderRadius: "6px", padding: "6px 10px", fontSize: "12px" }}
                >
                  <option value="ALL">All Directions</option>
                  <option value="BULLISH">Bullish Only</option>
                  <option value="BEARISH">Bearish Only</option>
                </select>

                <select
                  value={minScore}
                  onChange={(e) => setMinScore(Number(e.target.value))}
                  style={{ background: "#0f172a", color: "#fff", border: "1px solid #334155", borderRadius: "6px", padding: "6px 10px", fontSize: "12px" }}
                >
                  <option value="0">Min Score: Any</option>
                  <option value="50">Min Score: &gt; 50</option>
                  <option value="70">Min Score: &gt; 70</option>
                  <option value="85">Min Score: &gt; 85</option>
                </select>
              </div>
            </div>

            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
                <thead>
                  <tr style={{ background: "#0f172a", borderBottom: "1px solid #1e293b", textAlign: "left" }}>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Rank</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Symbol</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Sector</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>CMP (₹)</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Chg %</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>RVOL</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Setup Score</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Category</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {discoveredStocks.map((stock) => (
                    <tr
                      key={stock.symbol}
                      style={{ borderBottom: "1px solid #1e293b", cursor: "pointer" }}
                      onClick={() => handleOpenDossier(stock.symbol)}
                    >
                      <td style={{ padding: "10px", color: "#64748b" }}>#{stock.rank || "-"}</td>
                      <td style={{ padding: "10px", fontWeight: 700, color: "#fff" }}>{stock.symbol}</td>
                      <td style={{ padding: "10px", color: "#94a3b8" }}>{stock.sector}</td>
                      <td style={{ padding: "10px", color: "#fff" }}>₹{stock.close?.toFixed(2)}</td>
                      <td style={{ padding: "10px", color: stock.daily_change_pct >= 0 ? "#10b981" : "#ef4444", fontWeight: 600 }}>
                        {stock.daily_change_pct > 0 ? "+" : ""}{stock.daily_change_pct?.toFixed(2)}%
                      </td>
                      <td style={{ padding: "10px", color: stock.relative_volume >= 1.5 ? "#f59e0b" : "#94a3b8" }}>
                        {stock.relative_volume?.toFixed(2)}x
                      </td>
                      <td style={{ padding: "10px" }}>
                        <span
                          style={{
                            padding: "2px 8px",
                            borderRadius: "4px",
                            fontWeight: 700,
                            background: stock.setup_score >= 70 ? "rgba(16, 185, 129, 0.2)" : stock.setup_score >= 50 ? "rgba(59, 130, 246, 0.2)" : "rgba(100, 116, 139, 0.2)",
                            color: stock.setup_score >= 70 ? "#34d399" : stock.setup_score >= 50 ? "#60a5fa" : "#94a3b8",
                          }}
                        >
                          {stock.setup_score?.toFixed(1)}
                        </span>
                      </td>
                      <td style={{ padding: "10px", fontSize: "11px", color: "#94a3b8" }}>
                        {stock.setup_category}
                      </td>
                      <td style={{ padding: "10px" }}>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleGenerateTradePlan(stock.symbol);
                          }}
                          style={{
                            background: "#1e293b",
                            border: "1px solid #3b82f6",
                            color: "#60a5fa",
                            borderRadius: "4px",
                            padding: "4px 8px",
                            fontSize: "11px",
                            cursor: "pointer",
                          }}
                        >
                          Trade Plan 📐
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* TAB 2: TRADE PLAN GENERATOR (SECTION 9) */}
      {/* --------------------------------------------------------------------- */}
      {activeTab === "trade_planner" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {/* Sizing & Parameter Controls */}
          <div style={{ background: "#111827", borderRadius: "12px", border: "1px solid #1e293b", padding: "20px" }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: "16px", color: "#fff", fontWeight: 700 }}>
              SECTION 9 • TRADE PLAN GENERATOR & QUANTITATIVE POSITION SIZING
            </h3>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "16px", alignItems: "flex-end" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "6px" }}>Stock Symbol</label>
                <input
                  type="text"
                  value={planSymbol}
                  onChange={(e) => setPlanSymbol(e.target.value.toUpperCase())}
                  style={{ width: "100%", background: "#0a0f18", border: "1px solid #334155", borderRadius: "6px", padding: "8px 12px", color: "#fff", fontSize: "14px", fontWeight: 700 }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "6px" }}>Account Capital (₹)</label>
                <input
                  type="number"
                  value={planCapital}
                  onChange={(e) => setPlanCapital(Number(e.target.value))}
                  style={{ width: "100%", background: "#0a0f18", border: "1px solid #334155", borderRadius: "6px", padding: "8px 12px", color: "#fff", fontSize: "14px" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "6px" }}>Risk Per Trade (%)</label>
                <input
                  type="number"
                  step="0.1"
                  value={planRiskPct}
                  onChange={(e) => setPlanRiskPct(Number(e.target.value))}
                  style={{ width: "100%", background: "#0a0f18", border: "1px solid #334155", borderRadius: "6px", padding: "8px 12px", color: "#fff", fontSize: "14px" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "6px" }}>Target Risk-Reward</label>
                <input
                  type="number"
                  step="0.5"
                  value={planTargetRR}
                  onChange={(e) => setPlanTargetRR(Number(e.target.value))}
                  style={{ width: "100%", background: "#0a0f18", border: "1px solid #334155", borderRadius: "6px", padding: "8px 12px", color: "#fff", fontSize: "14px" }}
                />
              </div>

              <button
                onClick={() => handleGenerateTradePlan()}
                disabled={planLoading}
                style={{
                  background: "#2563eb",
                  color: "#fff",
                  border: "none",
                  borderRadius: "6px",
                  padding: "10px 20px",
                  fontSize: "14px",
                  fontWeight: 600,
                  cursor: planLoading ? "not-allowed" : "pointer",
                }}
              >
                {planLoading ? "Generating..." : "Generate Trade Plan"}
              </button>
            </div>
          </div>

          {/* Generated Trade Plan Display */}
          {generatedPlan && (
            <div style={{ background: "#0f172a", borderRadius: "12px", border: "1px solid #1e293b", padding: "24px", display: "flex", flexDirection: "column", gap: "20px" }}>
              {/* Header */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <span
                      style={{
                        padding: "4px 10px",
                        borderRadius: "4px",
                        fontWeight: 800,
                        fontSize: "12px",
                        background: generatedPlan.direction === "LONG" ? "#065f46" : "#881337",
                        color: generatedPlan.direction === "LONG" ? "#34d399" : "#fda4af",
                      }}
                    >
                      {generatedPlan.direction}
                    </span>
                    <h2 style={{ margin: 0, fontSize: "20px", color: "#fff" }}>
                      {generatedPlan.symbol} • ₹{generatedPlan.current_market_price.toFixed(2)}
                    </h2>
                    <span style={{ fontSize: "12px", color: "#94a3b8" }}>({generatedPlan.company_name})</span>
                  </div>
                  <div style={{ fontSize: "12px", color: "#64748b", marginTop: "4px" }}>
                    Setup Rating: {generatedPlan.setup_score} / 100 • {generatedPlan.setup_category}
                  </div>
                </div>

                <div style={{ display: "flex", gap: "10px" }}>
                  <button
                    onClick={handleSaveTradePlan}
                    style={{
                      background: "#10b981",
                      color: "#fff",
                      border: "none",
                      borderRadius: "6px",
                      padding: "8px 16px",
                      fontSize: "13px",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    💾 Save Plan to Watchlist
                  </button>
                </div>
              </div>

              {planSaveMsg && (
                <div style={{ padding: "10px 14px", background: "rgba(16, 185, 129, 0.15)", border: "1px solid #10b981", borderRadius: "6px", color: "#6ee7b7", fontSize: "13px" }}>
                  {planSaveMsg}
                </div>
              )}

              {/* Guardrail Warnings */}
              {generatedPlan.guardrail_warnings && generatedPlan.guardrail_warnings.length > 0 && (
                <div style={{ background: "rgba(239, 68, 68, 0.15)", border: "1px solid #ef4444", borderRadius: "8px", padding: "12px", color: "#fca5a5" }}>
                  <strong>⚠️ Risk Guardrail Alert:</strong>
                  <ul style={{ margin: "6px 0 0 16px", padding: 0 }}>
                    {generatedPlan.guardrail_warnings.map((w, idx) => (
                      <li key={idx}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Execution Structure Cards Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "14px" }}>
                {/* Entry Zone */}
                <div style={{ background: "#0a0f18", padding: "16px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                  <span style={{ fontSize: "11px", color: "#94a3b8", textTransform: "uppercase", fontWeight: 600 }}>Entry Execution</span>
                  <div style={{ fontSize: "18px", fontWeight: 800, color: "#fff", margin: "6px 0 2px 0" }}>
                    ₹{generatedPlan.entry_plan.ideal_entry.toFixed(2)}
                  </div>
                  <div style={{ fontSize: "12px", color: "#64748b" }}>
                    Zone: ₹{generatedPlan.entry_plan.entry_zone_min.toFixed(2)} – ₹{generatedPlan.entry_plan.entry_zone_max.toFixed(2)}
                  </div>
                  <div style={{ fontSize: "11px", color: "#38bdf8", marginTop: "4px" }}>
                    {generatedPlan.entry_plan.entry_type}
                  </div>
                </div>

                {/* Stop Loss & Invalidation */}
                <div style={{ background: "#0a0f18", padding: "16px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                  <span style={{ fontSize: "11px", color: "#f87171", textTransform: "uppercase", fontWeight: 600 }}>Structural Stop Loss</span>
                  <div style={{ fontSize: "18px", fontWeight: 800, color: "#f87171", margin: "6px 0 2px 0" }}>
                    ₹{generatedPlan.exit_plan.stop_loss.toFixed(2)}
                  </div>
                  <div style={{ fontSize: "12px", color: "#64748b" }}>
                    Risk Distance: ₹{generatedPlan.exit_plan.stop_distance.toFixed(2)} per share
                  </div>
                  <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "4px" }}>
                    {generatedPlan.exit_plan.stop_reason}
                  </div>
                </div>

                {/* Target 1 */}
                <div style={{ background: "#0a0f18", padding: "16px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                  <span style={{ fontSize: "11px", color: "#10b981", textTransform: "uppercase", fontWeight: 600 }}>Target 1 (Liquidity)</span>
                  <div style={{ fontSize: "18px", fontWeight: 800, color: "#10b981", margin: "6px 0 2px 0" }}>
                    ₹{generatedPlan.exit_plan.target_1.price.toFixed(2)}
                  </div>
                  <div style={{ fontSize: "12px", color: "#64748b" }}>
                    R:R: 1 : {generatedPlan.exit_plan.target_1.risk_reward_ratio.toFixed(2)}
                  </div>
                  <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "4px" }}>
                    {generatedPlan.exit_plan.target_1.description}
                  </div>
                </div>

                {/* Target 2 */}
                <div style={{ background: "#0a0f18", padding: "16px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                  <span style={{ fontSize: "11px", color: "#34d399", textTransform: "uppercase", fontWeight: 600 }}>Target 2 (Runner)</span>
                  <div style={{ fontSize: "18px", fontWeight: 800, color: "#34d399", margin: "6px 0 2px 0" }}>
                    ₹{generatedPlan.exit_plan.target_2.price.toFixed(2)}
                  </div>
                  <div style={{ fontSize: "12px", color: "#64748b" }}>
                    R:R: 1 : {generatedPlan.exit_plan.target_2.risk_reward_ratio.toFixed(2)}
                  </div>
                  <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "4px" }}>
                    {generatedPlan.exit_plan.target_2.description}
                  </div>
                </div>
              </div>

              {/* Position Sizing Card */}
              <div style={{ background: "#0a0f18", padding: "16px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                <h4 style={{ margin: "0 0 12px 0", fontSize: "13px", color: "#fff", textTransform: "uppercase" }}>
                  Quantitative Position Sizing Architecture
                </h4>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: "12px" }}>
                  <div>
                    <span style={{ fontSize: "11px", color: "#64748b" }}>Risk Budget</span>
                    <div style={{ fontSize: "14px", fontWeight: 700, color: "#fff" }}>
                      ₹{generatedPlan.position_sizing.risk_amount_inr.toFixed(2)} ({generatedPlan.position_sizing.risk_per_trade_pct}%)
                    </div>
                  </div>
                  <div>
                    <span style={{ fontSize: "11px", color: "#64748b" }}>Recommended Quantity</span>
                    <div style={{ fontSize: "14px", fontWeight: 700, color: "#38bdf8" }}>
                      {generatedPlan.position_sizing.recommended_shares} Shares
                    </div>
                  </div>
                  <div>
                    <span style={{ fontSize: "11px", color: "#64748b" }}>Capital Allocated</span>
                    <div style={{ fontSize: "14px", fontWeight: 700, color: "#fff" }}>
                      ₹{generatedPlan.position_sizing.capital_allocated_inr.toFixed(2)}
                    </div>
                  </div>
                  <div>
                    <span style={{ fontSize: "11px", color: "#64748b" }}>Portfolio Heat</span>
                    <div style={{ fontSize: "14px", fontWeight: 700, color: generatedPlan.position_sizing.portfolio_heat_pct > 50 ? "#f59e0b" : "#10b981" }}>
                      {generatedPlan.position_sizing.portfolio_heat_pct.toFixed(2)}%
                    </div>
                  </div>
                </div>
              </div>

              {/* Invalidation Rule & Failure Risks */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                <div style={{ background: "#0a0f18", padding: "14px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                  <strong style={{ fontSize: "12px", color: "#f87171" }}>Invalidation Condition:</strong>
                  <p style={{ margin: "6px 0 0 0", fontSize: "12px", color: "#cbd5e1" }}>
                    {generatedPlan.exit_plan.invalidation_condition}
                  </p>
                </div>

                <div style={{ background: "#0a0f18", padding: "14px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                  <strong style={{ fontSize: "12px", color: "#f59e0b" }}>What Would Make This Trade Fail:</strong>
                  <ul style={{ margin: "6px 0 0 16px", padding: 0, fontSize: "12px", color: "#cbd5e1" }}>
                    {generatedPlan.risk_factors.map((rf, i) => (
                      <li key={i}>{rf}</li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Research Disclaimer */}
              <div style={{ background: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.2)", borderRadius: "8px", padding: "12px", fontSize: "12px", color: "#fca5a5" }}>
                ⚖️ <strong>Regulatory & Analytical Disclosure:</strong> {generatedPlan.disclaimer}
              </div>
            </div>
          )}
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* TAB 3: HISTORICAL VALIDATION (SECTION 10) */}
      {/* --------------------------------------------------------------------- */}
      {activeTab === "validation" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          <div style={{ background: "#111827", borderRadius: "12px", border: "1px solid #1e293b", padding: "20px" }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: "16px", color: "#fff", fontWeight: 700 }}>
              SECTION 10 • HISTORICAL SETUP VALIDATION & STATISTICAL SAMPLE RELIABILITY
            </h3>

            <div style={{ display: "flex", gap: "16px", alignItems: "flex-end", flexWrap: "wrap" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "6px" }}>Stock Symbol</label>
                <input
                  type="text"
                  value={valSymbol}
                  onChange={(e) => setValSymbol(e.target.value.toUpperCase())}
                  style={{ background: "#0a0f18", border: "1px solid #334155", borderRadius: "6px", padding: "8px 12px", color: "#fff", fontSize: "14px", fontWeight: 700 }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", color: "#94a3b8", marginBottom: "6px" }}>Setup Type to Backtest</label>
                <select
                  value={valSetupType}
                  onChange={(e) => setValSetupType(e.target.value)}
                  style={{ background: "#0a0f18", color: "#fff", border: "1px solid #334155", borderRadius: "6px", padding: "8px 12px", fontSize: "13px" }}
                >
                  <option value="ORDER_BLOCK_RETEST">ORDER_BLOCK_RETEST</option>
                  <option value="FVG_FILL_REVERSAL">FVG_FILL_REVERSAL</option>
                  <option value="BOS_CONTINUATION">BOS_CONTINUATION</option>
                  <option value="LIQUIDITY_SWEEP_REVERSAL">LIQUIDITY_SWEEP_REVERSAL</option>
                  <option value="SMC_VOLUME_CONFIRMATION">SMC_VOLUME_CONFIRMATION</option>
                </select>
              </div>

              <button
                onClick={handleValidateSetup}
                disabled={valLoading}
                style={{
                  background: "#2563eb",
                  color: "#fff",
                  border: "none",
                  borderRadius: "6px",
                  padding: "9px 20px",
                  fontSize: "13px",
                  fontWeight: 600,
                  cursor: valLoading ? "not-allowed" : "pointer",
                }}
              >
                {valLoading ? "Validating..." : "Run Historical Validation"}
              </button>
            </div>
          </div>

          {validationResult && (
            <div style={{ background: "#0f172a", borderRadius: "12px", border: "1px solid #1e293b", padding: "24px", display: "flex", flexDirection: "column", gap: "20px" }}>
              {/* Sample Size Assessment Banner */}
              <div
                style={{
                  background: validationResult.sample_size_assessment.is_statistically_reliable ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
                  border: `1px solid ${validationResult.sample_size_assessment.is_statistically_reliable ? "#10b981" : "#f59e0b"}`,
                  borderRadius: "8px",
                  padding: "14px",
                  color: validationResult.sample_size_assessment.is_statistically_reliable ? "#6ee7b7" : "#fcd34d",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <strong>
                    {validationResult.sample_size_assessment.is_statistically_reliable ? "✓ SUFFICIENT SAMPLE SIZE" : "⚠️ STATISTICALLY UNVERIFIED (SAMPLE < 30)"}
                  </strong>
                  <span>{validationResult.sample_size_assessment.total_occurrences} Historical Trades</span>
                </div>
                <p style={{ margin: "6px 0 0 0", fontSize: "12px" }}>
                  {validationResult.sample_size_assessment.warning}
                </p>
              </div>

              {/* Metrics Grid */}
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "14px" }}>
                <div style={{ background: "#0a0f18", padding: "14px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                  <span style={{ fontSize: "11px", color: "#94a3b8" }}>Win Rate</span>
                  <div style={{ fontSize: "18px", fontWeight: 800, color: "#fff", margin: "4px 0" }}>
                    {validationResult.performance_metrics.win_rate_pct.toFixed(1)}%
                  </div>
                  <div style={{ fontSize: "10px", color: "#64748b" }}>
                    Wilson 95% CI: [{validationResult.performance_metrics.wilson_ci_95?.lower_bound_pct || 0}% – {validationResult.performance_metrics.wilson_ci_95?.upper_bound_pct || 0}%]
                  </div>
                </div>

                <div style={{ background: "#0a0f18", padding: "14px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                  <span style={{ fontSize: "11px", color: "#94a3b8" }}>Profit Factor</span>
                  <div style={{ fontSize: "18px", fontWeight: 800, color: "#fff", margin: "4px 0" }}>
                    {validationResult.performance_metrics.profit_factor.toFixed(2)}
                  </div>
                  <div style={{ fontSize: "10px", color: "#64748b" }}>
                    Target R:R: 1 : {validationResult.performance_metrics.target_risk_reward}
                  </div>
                </div>

                <div style={{ background: "#0a0f18", padding: "14px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                  <span style={{ fontSize: "11px", color: "#94a3b8" }}>Max Drawdown</span>
                  <div style={{ fontSize: "18px", fontWeight: 800, color: "#f87171", margin: "4px 0" }}>
                    {validationResult.performance_metrics.max_drawdown_pct.toFixed(2)}%
                  </div>
                  <div style={{ fontSize: "10px", color: "#64748b" }}>Peak-to-trough decline</div>
                </div>

                <div style={{ background: "#0a0f18", padding: "14px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                  <span style={{ fontSize: "11px", color: "#94a3b8" }}>Avg Holding Period</span>
                  <div style={{ fontSize: "18px", fontWeight: 800, color: "#38bdf8", margin: "4px 0" }}>
                    {validationResult.performance_metrics.average_holding_bars.toFixed(1)} Bars
                  </div>
                  <div style={{ fontSize: "10px", color: "#64748b" }}>Daily session candles</div>
                </div>
              </div>

              {/* Regime Dependence */}
              {Object.keys(validationResult.regime_dependence).length > 0 && (
                <div style={{ background: "#0a0f18", padding: "16px", borderRadius: "8px", border: "1px solid #1e293b" }}>
                  <h4 style={{ margin: "0 0 10px 0", fontSize: "13px", color: "#fff" }}>
                    Market Regime Dependence Breakdown
                  </h4>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "10px" }}>
                    {Object.entries(validationResult.regime_dependence).map(([rName, rStats]) => (
                      <div key={rName} style={{ background: "#111827", padding: "10px", borderRadius: "6px" }}>
                        <span style={{ fontSize: "11px", color: "#38bdf8", fontWeight: 700 }}>{rName}</span>
                        <div style={{ fontSize: "12px", color: "#cbd5e1", marginTop: "4px" }}>
                          Trades: {rStats.trades} • Win: {rStats.win_rate_pct}% • PF: {rStats.profit_factor}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Realism & Disclaimers */}
              <div style={{ fontSize: "11px", color: "#64748b", borderTop: "1px solid #1e293b", paddingTop: "12px" }}>
                {validationResult.disclaimers.map((d, i) => (
                  <div key={i}>• {d}</div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* TAB 4: SAVED TRADE PLANS */}
      {/* --------------------------------------------------------------------- */}
      {activeTab === "saved_plans" && (
        <div style={{ background: "#111827", borderRadius: "12px", border: "1px solid #1e293b", padding: "20px" }}>
          <h3 style={{ margin: "0 0 16px 0", fontSize: "16px", color: "#fff", fontWeight: 700 }}>
            PERSISTENT RESEARCH TRADE PLANS ({savedPlans.length})
          </h3>

          {savedPlans.length === 0 ? (
            <div style={{ color: "#64748b", fontSize: "13px" }}>No trade plans saved yet. Generate a plan and click "Save Plan".</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "13px" }}>
                <thead>
                  <tr style={{ background: "#0f172a", borderBottom: "1px solid #1e293b", textAlign: "left" }}>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Symbol</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Direction</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Ideal Entry</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Stop Loss</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Target 1</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Shares</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Status</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Update</th>
                    <th style={{ padding: "10px", color: "#94a3b8" }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {savedPlans.map((plan) => (
                    <tr key={plan.id} style={{ borderBottom: "1px solid #1e293b" }}>
                      <td style={{ padding: "10px", fontWeight: 700, color: "#fff" }}>{plan.symbol}</td>
                      <td style={{ padding: "10px", color: plan.direction === "LONG" ? "#10b981" : "#ef4444", fontWeight: 600 }}>
                        {plan.direction}
                      </td>
                      <td style={{ padding: "10px", color: "#fff" }}>₹{plan.ideal_entry}</td>
                      <td style={{ padding: "10px", color: "#f87171" }}>₹{plan.stop_loss}</td>
                      <td style={{ padding: "10px", color: "#10b981" }}>₹{plan.target_1}</td>
                      <td style={{ padding: "10px", color: "#38bdf8" }}>{plan.position_size}</td>
                      <td style={{ padding: "10px" }}>
                        <span
                          style={{
                            fontSize: "11px",
                            padding: "2px 6px",
                            borderRadius: "4px",
                            background: plan.status === "MONITORING" ? "#1e3a8a" : plan.status.includes("HIT") ? "#065f46" : "#450a0a",
                            color: plan.status === "MONITORING" ? "#93c5fd" : plan.status.includes("HIT") ? "#6ee7b7" : "#fca5a5",
                          }}
                        >
                          {plan.status}
                        </span>
                      </td>
                      <td style={{ padding: "10px" }}>
                        <select
                          value={plan.status}
                          onChange={(e) => handleUpdatePlanStatus(plan.id, e.target.value)}
                          style={{ background: "#0a0f18", color: "#fff", border: "1px solid #334155", borderRadius: "4px", padding: "4px 8px", fontSize: "11px" }}
                        >
                          <option value="MONITORING">MONITORING</option>
                          <option value="TARGET_1_HIT">TARGET_1_HIT</option>
                          <option value="TARGET_2_HIT">TARGET_2_HIT</option>
                          <option value="INVALIDATED">INVALIDATED</option>
                          <option value="EXPIRED">EXPIRED</option>
                        </select>
                      </td>
                      <td style={{ padding: "10px" }}>
                        <button
                          onClick={() => handleDeleteSavedPlan(plan.id)}
                          style={{ background: "transparent", border: "1px solid #ef4444", color: "#ef4444", borderRadius: "4px", padding: "2px 6px", fontSize: "11px", cursor: "pointer" }}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* TAB 5: RESEARCH NOTES */}
      {/* --------------------------------------------------------------------- */}
      {activeTab === "notes" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
          {/* Note Input */}
          <div style={{ background: "#111827", borderRadius: "12px", border: "1px solid #1e293b", padding: "20px" }}>
            <h3 style={{ margin: "0 0 12px 0", fontSize: "16px", color: "#fff", fontWeight: 700 }}>
              QUALITATIVE RESEARCH NOTES
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              <input
                type="text"
                placeholder="Note Title / Catalyst (e.g. Q4 Order Inflow, Management Guidance)"
                value={newNoteTitle}
                onChange={(e) => setNewNoteTitle(e.target.value)}
                style={{ background: "#0a0f18", border: "1px solid #334155", borderRadius: "6px", padding: "8px 12px", color: "#fff", fontSize: "13px" }}
              />
              <textarea
                placeholder="Write your research observations, institutional order flow findings, or thesis..."
                rows={3}
                value={newNoteText}
                onChange={(e) => setNewNoteText(e.target.value)}
                style={{ background: "#0a0f18", border: "1px solid #334155", borderRadius: "6px", padding: "8px 12px", color: "#fff", fontSize: "13px", resize: "vertical" }}
              />
              <button
                onClick={handleAddNote}
                style={{ alignSelf: "flex-start", background: "#2563eb", color: "#fff", border: "none", borderRadius: "6px", padding: "8px 16px", fontSize: "13px", fontWeight: 600, cursor: "pointer" }}
              >
                Add Research Note
              </button>
            </div>
          </div>

          {/* Notes List */}
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            {savedNotes.map((note) => (
              <div key={note.id} style={{ background: "#0f172a", borderRadius: "8px", border: "1px solid #1e293b", padding: "14px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <strong style={{ color: "#38bdf8" }}>{note.symbol}</strong>
                    <span style={{ fontWeight: 600, color: "#fff", fontSize: "13px" }}>{note.title || "Note"}</span>
                  </div>
                  <span style={{ fontSize: "11px", color: "#64748b" }}>{note.created_at}</span>
                </div>
                <p style={{ margin: "8px 0 0 0", color: "#cbd5e1", fontSize: "13px" }}>{note.note}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* STOCK RESEARCH DOSSIER MODAL */}
      {/* --------------------------------------------------------------------- */}
      {modalSymbol && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.75)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            zIndex: 9999,
            padding: "20px",
          }}
          onClick={() => setModalSymbol(null)}
        >
          <div
            style={{
              background: "#0f172a",
              border: "1px solid #334155",
              borderRadius: "12px",
              width: "100%",
              maxWidth: "850px",
              maxHeight: "90vh",
              overflowY: "auto",
              padding: "24px",
              display: "flex",
              flexDirection: "column",
              gap: "20px",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {dossierLoading || !dossierData ? (
              <div style={{ color: "#fff", textAlign: "center", padding: "40px" }}>Loading Dossier for {modalSymbol}...</div>
            ) : (
              <>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <h2 style={{ margin: 0, fontSize: "22px", color: "#fff" }}>{dossierData.symbol}</h2>
                      <span style={{ fontSize: "13px", color: "#94a3b8" }}>{dossierData.company_name}</span>
                      <span style={{ fontSize: "12px", padding: "2px 8px", borderRadius: "4px", background: "#1e293b", color: "#38bdf8" }}>
                        {dossierData.sector}
                      </span>
                    </div>
                    <div style={{ fontSize: "13px", color: "#cbd5e1", marginTop: "4px" }}>
                      CMP: ₹{dossierData.close} • Daily: {dossierData.daily_change_pct}% • Setup Score: <strong>{dossierData.setup_evaluation?.setup_score} / 100</strong>
                    </div>
                  </div>

                  <button
                    onClick={() => setModalSymbol(null)}
                    style={{ background: "transparent", border: "none", color: "#94a3b8", fontSize: "20px", cursor: "pointer" }}
                  >
                    ✕
                  </button>
                </div>

                {/* 7-Component Breakdown */}
                <div>
                  <h4 style={{ margin: "0 0 10px 0", fontSize: "14px", color: "#fff" }}>
                    7-Factor Quantitative Confluence Breakdown
                  </h4>
                  <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                    {Object.entries(dossierData.setup_evaluation?.component_breakdown || {}).map(([key, val]: any) => (
                      <div key={key} style={{ background: "#0a0f18", padding: "10px", borderRadius: "6px", border: "1px solid #1e293b" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", fontWeight: 600 }}>
                          <span style={{ color: "#94a3b8", textTransform: "capitalize" }}>{key.replace("_", " ")}</span>
                          <span style={{ color: "#38bdf8" }}>{val.score} / {val.max} PTS</span>
                        </div>
                        <div style={{ fontSize: "11px", color: "#64748b", marginTop: "4px" }}>{val.rationale}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Key Technicals & Fundamentals */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                  <div style={{ background: "#0a0f18", padding: "12px", borderRadius: "8px" }}>
                    <h5 style={{ margin: "0 0 8px 0", color: "#fff", fontSize: "12px" }}>Technical Signals</h5>
                    <div style={{ fontSize: "12px", color: "#cbd5e1" }}>
                      RSI (14): {dossierData.indicators?.rsi?.toFixed(1) || "-"} • ADX: {dossierData.indicators?.adx?.toFixed(1) || "-"} • Supertrend: {dossierData.indicators?.supertrend_dir || "-"}
                    </div>
                  </div>

                  <div style={{ background: "#0a0f18", padding: "12px", borderRadius: "8px" }}>
                    <h5 style={{ margin: "0 0 8px 0", color: "#fff", fontSize: "12px" }}>Fundamental Quality</h5>
                    <div style={{ fontSize: "12px", color: "#cbd5e1" }}>
                      ROE: {dossierData.fundamentals?.profitability?.roe || "-"}% • D/E: {dossierData.fundamentals?.health?.debt_equity || "-"} • PAT Gr: {dossierData.fundamentals?.growth?.quarterly_pat_growth_qoq || "-"}%
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
                  <button
                    onClick={() => {
                      setModalSymbol(null);
                      handleGenerateTradePlan(dossierData.symbol);
                    }}
                    style={{ background: "#2563eb", color: "#fff", border: "none", borderRadius: "6px", padding: "8px 16px", fontSize: "13px", fontWeight: 600, cursor: "pointer" }}
                  >
                    Generate Trade Plan 📐
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

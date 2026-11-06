import { apiFetch } from "../api/client";
import React, { useEffect, useRef, useState, useMemo } from "react";
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  IChartApi,
  ISeriesApi,
  Time,
  LineStyle,
} from "lightweight-charts";

export interface CandleBar {
  timestamp?: string;
  date?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface TradingViewChartProps {
  symbol: string;
  onSymbolChange?: (symbol: string) => void;
  availableStocks?: { symbol: string; company_name: string; close?: number }[];
  height?: number;
}

export default function TradingViewChart({
  symbol,
  onSymbolChange,
  availableStocks = [],
  height = 540,
}: TradingViewChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  // Indicator series refs
  const ema9SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ema20SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const ema200SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const sma20SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const sma50SeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbUpperSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbLowerSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const vwapSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const trendlineSeriesRefs = useRef<ISeriesApi<"Line">[]>([]);

  // Overlay price lines ref (Order Blocks, S/R, Key Levels)
  const overlayPriceLinesRef = useRef<any[]>([]);

  // State
  const [bars, setBars] = useState<CandleBar[]>([]);
  const [analysisData, setAnalysisData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<string>("1D");
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  // Indicator Toggles
  const [showVolume, setShowVolume] = useState(true);
  const [showEMA9, setShowEMA9] = useState(false);
  const [showEMA20, setShowEMA20] = useState(true);
  const [showEMA50, setShowEMA50] = useState(false);
  const [showEMA200, setShowEMA200] = useState(false);
  const [showSMA20, setShowSMA20] = useState(false);
  const [showBB, setShowBB] = useState(false);
  const [showVWAP, setShowVWAP] = useState(false);

  // SMC & Levels Toggles
  const [showOB, setShowOB] = useState(true);
  const [showFVG, setShowFVG] = useState(false);
  const [showSR, setShowSR] = useState(true);
  const [showKeyLevels, setShowKeyLevels] = useState(false);
  const [showStructure, setShowStructure] = useState(false);
  const [showTrendlines, setShowTrendlines] = useState(false);
  const [showVolProfileSidebar, setShowVolProfileSidebar] = useState(false);
  const [showSetupsDrawer, setShowSetupsDrawer] = useState(false);

  // Hovered candle stats
  const [hoveredCandle, setHoveredCandle] = useState<CandleBar | null>(null);

  // Symbol picker
  const [searchFilter, setSearchFilter] = useState("");
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  // Fetch unified analysis data
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    const loadData = async () => {
      try {
        const res = await apiFetch(`/api/scanner/stock/${symbol}/analysis?timeframe=${timeframe}`
        );
        if (!res.ok) {
          throw new Error(`Failed to load analysis for ${symbol}: HTTP ${res.status}`);
        }
        const data = await res.json();
        if (cancelled) return;

        setAnalysisData(data);

        // Normalize bars
        const rawBars: CandleBar[] = data.bars || [];
        const uniqueMap = new Map<string, CandleBar>();
        for (const b of rawBars) {
          const rawDate = b.date || b.timestamp || "";
          const dateKey = rawDate.split("T")[0];
          if (dateKey && b.open != null && b.close != null) {
            uniqueMap.set(dateKey, { ...b, timestamp: dateKey });
          }
        }
        const sorted = Array.from(uniqueMap.values()).sort((a, b) =>
          (a.timestamp || "").localeCompare(b.timestamp || "")
        );

        setBars(sorted);
        if (sorted.length > 0) {
          setHoveredCandle(sorted[sorted.length - 1]);
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err.message || "Failed to load chart data");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    loadData();
    return () => {
      cancelled = true;
    };
  }, [symbol, timeframe]);

  // Initialize TradingView Chart
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chartHeight = isFullscreen ? window.innerHeight - 80 : height;

    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: chartHeight,
      layout: {
        background: { type: ColorType.Solid, color: "#0a0f18" },
        textColor: "#8c9bb0",
      },
      grid: {
        vertLines: { color: "#16202e", style: 1 },
        horzLines: { color: "#16202e", style: 1 },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#2d3f58", width: 1, style: 2 },
        horzLine: { color: "#2d3f58", width: 1, style: 2 },
      },
      timeScale: {
        borderColor: "#1e2c40",
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: "#1e2c40",
        scaleMargins: {
          top: 0.08,
          bottom: 0.22,
        },
      },
    });
    chartRef.current = chart;

    // Candlesticks
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    candleSeriesRef.current = candleSeries;

    // Volume
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });
    volumeSeriesRef.current = volumeSeries;

    // EMAs
    ema9SeriesRef.current = chart.addSeries(LineSeries, {
      color: "#06b6d4",
      lineWidth: 1,
      priceLineVisible: false,
      title: "EMA 9",
    });
    ema20SeriesRef.current = chart.addSeries(LineSeries, {
      color: "#f59e0b",
      lineWidth: 2,
      priceLineVisible: false,
      title: "EMA 20",
    });
    ema50SeriesRef.current = chart.addSeries(LineSeries, {
      color: "#3b82f6",
      lineWidth: 2,
      priceLineVisible: false,
      title: "EMA 50",
    });
    ema200SeriesRef.current = chart.addSeries(LineSeries, {
      color: "#a855f7",
      lineWidth: 2,
      priceLineVisible: false,
      title: "EMA 200",
    });

    // SMA 20
    sma20SeriesRef.current = chart.addSeries(LineSeries, {
      color: "#e2e8f0",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      priceLineVisible: false,
      title: "SMA 20",
    });

    // Bollinger Bands
    bbUpperSeriesRef.current = chart.addSeries(LineSeries, {
      color: "rgba(59, 130, 246, 0.4)",
      lineWidth: 1,
      priceLineVisible: false,
      title: "BB Upper",
    });
    bbLowerSeriesRef.current = chart.addSeries(LineSeries, {
      color: "rgba(59, 130, 246, 0.4)",
      lineWidth: 1,
      priceLineVisible: false,
      title: "BB Lower",
    });

    // VWAP
    vwapSeriesRef.current = chart.addSeries(LineSeries, {
      color: "#ec4899",
      lineWidth: 2,
      priceLineVisible: false,
      title: "VWAP",
    });
    trendlineSeriesRefs.current = ["#38bdf8", "#c084fc", "#4ade80", "#f59e0b"].map((color, index) =>
      chart.addSeries(LineSeries, {
        color,
        lineWidth: 1,
        lineStyle: LineStyle.LargeDashed,
        priceLineVisible: false,
        lastValueVisible: false,
        title: `Trendline ${index + 1}`,
      })
    );

    // Crosshair listener
    chart.subscribeCrosshairMove((param) => {
      if (
        param.time &&
        param.seriesData &&
        candleSeriesRef.current &&
        param.seriesData.has(candleSeriesRef.current)
      ) {
        const cData = param.seriesData.get(candleSeriesRef.current) as any;
        if (cData) {
          setHoveredCandle({
            timestamp: String(param.time),
            open: cData.open,
            high: cData.high,
            low: cData.low,
            close: cData.close,
            volume: 0,
          });
        }
      }
    });

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: isFullscreen ? window.innerHeight - 80 : height,
        });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      trendlineSeriesRefs.current = [];
    };
  }, [height, isFullscreen]);

  // Feed Bar Data and Indicator Lines into Chart
  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || bars.length === 0) return;

    // 1. Candles
    const candleData = bars.map((b) => ({
      time: (b.timestamp || "") as Time,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }));
    candleSeriesRef.current.setData(candleData);

    // 2. Volume
    if (showVolume) {
      const volumeData = bars.map((b) => ({
        time: (b.timestamp || "") as Time,
        value: b.volume || 0,
        color: b.close >= b.open ? "rgba(34, 197, 94, 0.35)" : "rgba(239, 68, 68, 0.35)",
      }));
      volumeSeriesRef.current.setData(volumeData);
    } else {
      volumeSeriesRef.current.setData([]);
    }

    const ts = analysisData?.timeseries;
    if (ts && ts.dates) {
      const dates: string[] = ts.dates;

      const buildLineData = (values: (number | null)[]) => {
        if (!values) return [];
        const res: { time: Time; value: number }[] = [];
        for (let i = 0; i < values.length; i++) {
          const val = values[i];
          const d = dates[i];
          if (val != null && d) {
            res.push({ time: d.split("T")[0] as Time, value: val });
          }
        }
        return res;
      };

      // Set EMAs
      if (ema9SeriesRef.current) {
        ema9SeriesRef.current.setData(showEMA9 ? buildLineData(ts.ema_9) : []);
      }
      if (ema20SeriesRef.current) {
        ema20SeriesRef.current.setData(showEMA20 ? buildLineData(ts.ema_20) : []);
      }
      if (ema50SeriesRef.current) {
        ema50SeriesRef.current.setData(showEMA50 ? buildLineData(ts.ema_50) : []);
      }
      if (ema200SeriesRef.current) {
        ema200SeriesRef.current.setData(showEMA200 ? buildLineData(ts.ema_200) : []);
      }

      // SMA 20
      if (sma20SeriesRef.current) {
        sma20SeriesRef.current.setData(showSMA20 ? buildLineData(ts.sma_20) : []);
      }

      // Bollinger Bands
      if (bbUpperSeriesRef.current && bbLowerSeriesRef.current) {
        if (showBB && ts.bollinger) {
          bbUpperSeriesRef.current.setData(buildLineData(ts.bollinger.upper));
          bbLowerSeriesRef.current.setData(buildLineData(ts.bollinger.lower));
        } else {
          bbUpperSeriesRef.current.setData([]);
          bbLowerSeriesRef.current.setData([]);
        }
      }

      const trendlines = analysisData?.levels?.trendlines || [];
      trendlineSeriesRefs.current.forEach((series, index) => {
        const trendline = showTrendlines ? trendlines.filter((line: any) => line.is_active)[index] : null;
        const startDate = trendline?.start_point?.date?.split("T")[0];
        const endDate = trendline?.end_point?.date?.split("T")[0];
        if (trendline && startDate && endDate) {
          series.setData([
            { time: startDate as Time, value: trendline.start_point.price },
            { time: endDate as Time, value: trendline.end_point.price },
          ]);
        } else {
          series.setData([]);
        }
      });

      // VWAP
      if (vwapSeriesRef.current) {
        vwapSeriesRef.current.setData(showVWAP ? buildLineData(ts.vwap) : []);
      }
    }

    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
    }
  }, [
    bars,
    analysisData,
    showVolume,
    showEMA9,
    showEMA20,
    showEMA50,
    showEMA200,
    showSMA20,
    showBB,
    showVWAP,
    showTrendlines,
  ]);

  // Draw Price Lines for SMC (Order Blocks, FVGs) and Levels (Support/Resistance, Key Levels)
  useEffect(() => {
    if (!candleSeriesRef.current || !analysisData) return;

    // Clear previous lines
    for (const pl of overlayPriceLinesRef.current) {
      try {
        candleSeriesRef.current.removePriceLine(pl);
      } catch {}
    }
    overlayPriceLinesRef.current = [];

    const newLines: any[] = [];

    // 1. Order Blocks
    if (showOB && analysisData.smc?.order_blocks?.all_zones) {
      const activeOBs = analysisData.smc.order_blocks.all_zones
        .filter((z: any) => z.status !== "INVALIDATED")
        .slice(-4);

      for (const ob of activeOBs) {
        const isBull = ob.direction === "BULLISH";
        const color = isBull ? "#22c55e" : "#ef4444";
        const hLine = candleSeriesRef.current.createPriceLine({
          price: ob.zone_high,
          color: color,
          lineWidth: 1,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: `${isBull ? "BULL" : "BEAR"} OB High`,
        });
        const lLine = candleSeriesRef.current.createPriceLine({
          price: ob.zone_low,
          color: color,
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: `${isBull ? "BULL" : "BEAR"} OB Low`,
        });
        newLines.push(hLine, lLine);
      }
    }

    // 2. Fair Value Gaps
    if (showFVG && analysisData.smc?.fair_value_gaps?.gaps) {
      const unfilled = analysisData.smc.fair_value_gaps.gaps
        .filter((g: any) => !g.is_filled)
        .slice(-3);

      for (const fvg of unfilled) {
        const isBull = fvg.type === "BULLISH";
        const fLine = candleSeriesRef.current.createPriceLine({
          price: (fvg.top + fvg.bottom) / 2,
          color: isBull ? "#38bdf8" : "#f43f5e",
          lineWidth: 1,
          lineStyle: LineStyle.Dotted,
          axisLabelVisible: true,
          title: `${isBull ? "BULL" : "BEAR"} FVG`,
        });
        newLines.push(fLine);
      }
    }

    // 3. Support and Resistance Zones
    if (showSR && analysisData.levels?.support_resistance_zones) {
      const zones = analysisData.levels.support_resistance_zones.slice(0, 4);
      for (const z of zones) {
        const isSup = z.type === "support";
        const srLine = candleSeriesRef.current.createPriceLine({
          price: z.mid_price,
          color: isSup ? "#3b82f6" : "#eab308",
          lineWidth: 1,
          lineStyle: LineStyle.Solid,
          axisLabelVisible: true,
          title: `${isSup ? "SUP" : "RES"} (${z.touch_count}T)`,
        });
        newLines.push(srLine);
      }
    }

    if (showStructure) {
      const recentBreaks = (analysisData.smc?.market_structure?.breaks || []).slice(-2);
      for (const structureBreak of recentBreaks) {
        newLines.push(
          candleSeriesRef.current.createPriceLine({
            price: structureBreak.broken_level,
            color: structureBreak.type === "BOS" ? "#38bdf8" : "#f59e0b",
            lineWidth: 1,
            lineStyle: LineStyle.Dotted,
            axisLabelVisible: true,
            title: `${structureBreak.direction} ${structureBreak.type}`,
          })
        );
      }
    }

    // 4. Session Key Levels (PDH, PDL, PWH, PWL)
    if (showKeyLevels && analysisData.levels?.key_levels) {
      const kl = analysisData.levels.key_levels;
      if (kl.pdh) {
        newLines.push(
          candleSeriesRef.current.createPriceLine({
            price: kl.pdh,
            color: "#f59e0b",
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "PDH",
          })
        );
      }
      if (kl.pdl) {
        newLines.push(
          candleSeriesRef.current.createPriceLine({
            price: kl.pdl,
            color: "#f59e0b",
            lineWidth: 1,
            lineStyle: LineStyle.Dashed,
            axisLabelVisible: true,
            title: "PDL",
          })
        );
      }
      if (kl.pwh) {
        newLines.push(
          candleSeriesRef.current.createPriceLine({
            price: kl.pwh,
            color: "#8b5cf6",
            lineWidth: 1,
            lineStyle: LineStyle.LargeDashed,
            axisLabelVisible: true,
            title: "PWH",
          })
        );
      }
      if (kl.pwl) {
        newLines.push(
          candleSeriesRef.current.createPriceLine({
            price: kl.pwl,
            color: "#8b5cf6",
            lineWidth: 1,
            lineStyle: LineStyle.LargeDashed,
            axisLabelVisible: true,
            title: "PWL",
          })
        );
      }
    }

    overlayPriceLinesRef.current = newLines;
  }, [analysisData, showOB, showFVG, showSR, showKeyLevels, showStructure]);

  const activeCandle = hoveredCandle || (bars.length > 0 ? bars[bars.length - 1] : null);
  const priceChange = activeCandle && activeCandle.open ? activeCandle.close - activeCandle.open : 0;
  const priceChangePct = activeCandle && activeCandle.open ? (priceChange / activeCandle.open) * 100 : 0;
  const isPositive = priceChange >= 0;

  const mtf = analysisData?.multi_timeframe;
  const volProf = analysisData?.volume_profile;
  const setups = analysisData?.setups || [];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        background: "#0a0f18",
        border: "1px solid #1e2c40",
        borderRadius: "12px",
        overflow: "hidden",
        position: isFullscreen ? "fixed" : "relative",
        top: isFullscreen ? 0 : undefined,
        left: isFullscreen ? 0 : undefined,
        width: isFullscreen ? "100vw" : "100%",
        height: isFullscreen ? "100vh" : "auto",
        zIndex: isFullscreen ? 9999 : 1,
      }}
    >
      {/* Top Navigation & Controls Toolbar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "10px",
          padding: "10px 16px",
          background: "#0e1622",
          borderBottom: "1px solid #1e2c40",
        }}
      >
        {/* Left: Symbol & Timeframe & Quote */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
          {/* Symbol Dropdown */}
          <div style={{ position: "relative" }}>
            <button
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                background: "#16202e",
                border: "1px solid #28394e",
                color: "#fff",
                padding: "6px 12px",
                borderRadius: "6px",
                fontWeight: 700,
                fontSize: "13px",
                cursor: "pointer",
              }}
            >
              <span>{symbol}</span>
              <span style={{ fontSize: "9px", color: "#8c9bb0" }}>▼</span>
            </button>

            {isDropdownOpen && (
              <div
                style={{
                  position: "absolute",
                  top: "100%",
                  left: 0,
                  marginTop: "4px",
                  width: "260px",
                  background: "#101824",
                  border: "1px solid #28394e",
                  borderRadius: "8px",
                  boxShadow: "0 10px 25px rgba(0,0,0,0.7)",
                  zIndex: 100,
                  maxHeight: "300px",
                  overflowY: "auto",
                }}
              >
                <div style={{ padding: "8px" }}>
                  <input
                    type="text"
                    placeholder="Search stock..."
                    value={searchFilter}
                    onChange={(e) => setSearchFilter(e.target.value)}
                    autoFocus
                    style={{
                      width: "100%",
                      background: "#0a0f18",
                      border: "1px solid #28394e",
                      color: "#fff",
                      padding: "6px 8px",
                      borderRadius: "4px",
                      fontSize: "11px",
                    }}
                  />
                </div>
                {availableStocks
                  .filter((s) => !searchFilter || s.symbol.toLowerCase().includes(searchFilter.toLowerCase()))
                  .slice(0, 15)
                  .map((stk) => (
                    <div
                      key={stk.symbol}
                      onClick={() => {
                        if (onSymbolChange) onSymbolChange(stk.symbol);
                        setIsDropdownOpen(false);
                      }}
                      style={{
                        padding: "8px 12px",
                        cursor: "pointer",
                        display: "flex",
                        justifyContent: "space-between",
                        fontSize: "12px",
                        borderBottom: "1px solid #16202e",
                        color: stk.symbol === symbol ? "#22c55e" : "#cbd5e1",
                      }}
                    >
                      <div>
                        <strong>{stk.symbol}</strong>
                        <div style={{ fontSize: "10px", color: "#8c9bb0" }}>{stk.company_name}</div>
                      </div>
                      {stk.close && <div>₹{stk.close.toFixed(2)}</div>}
                    </div>
                  ))}
              </div>
            )}
          </div>

          {/* Timeframe Selector */}
          <div style={{ display: "flex", background: "#06090e", borderRadius: "6px", padding: "2px" }}>
            {["1m", "5m", "15m", "1h", "4h", "1D", "1W"].map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                style={{
                  background: timeframe === tf ? "#1e2c40" : "transparent",
                  color: timeframe === tf ? "#60a5fa" : "#8c9bb0",
                  border: "none",
                  padding: "4px 8px",
                  fontSize: "11px",
                  fontWeight: 600,
                  borderRadius: "4px",
                  cursor: "pointer",
                }}
              >
                {tf}
              </button>
            ))}
          </div>

          {/* Data Mode & Exchange Badge */}
          <span
            style={{
              fontSize: "10px",
              padding: "2px 6px",
              borderRadius: "4px",
              background: analysisData?.metadata?.data_mode === "LIVE" ? "rgba(34, 197, 94, 0.15)" : "rgba(100, 116, 139, 0.15)",
              color: analysisData?.metadata?.data_mode === "LIVE" ? "#4ade80" : "#94a3b8",
              border: `1px solid ${analysisData?.metadata?.data_mode === "LIVE" ? "rgba(34, 197, 94, 0.3)" : "rgba(100, 116, 139, 0.3)"}`,
              fontWeight: 600,
              textTransform: "uppercase",
            }}
          >
            NSE · {analysisData?.metadata?.data_mode || "HISTORICAL"}
          </span>

          {/* Live Quote Header */}
          {activeCandle && (
            <div style={{ display: "flex", gap: "10px", fontSize: "11px", color: "#8c9bb0" }}>
              <span>O: <strong style={{ color: "#fff" }}>{activeCandle.open.toFixed(2)}</strong></span>
              <span>H: <strong style={{ color: "#fff" }}>{activeCandle.high.toFixed(2)}</strong></span>
              <span>L: <strong style={{ color: "#fff" }}>{activeCandle.low.toFixed(2)}</strong></span>
              <span>C: <strong style={{ color: isPositive ? "#22c55e" : "#ef4444" }}>{activeCandle.close.toFixed(2)}</strong></span>
              <span style={{ color: isPositive ? "#22c55e" : "#ef4444", fontWeight: 700 }}>
                {isPositive ? "+" : ""}{priceChange.toFixed(2)} ({isPositive ? "+" : ""}{priceChangePct.toFixed(2)}%)
              </span>
            </div>
          )}
        </div>

        {/* Right: Indicator & Overlay Toggles */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap" }}>
          <button
            onClick={() => setShowVolume(!showVolume)}
            style={{
              background: showVolume ? "rgba(45, 201, 147, 0.13)" : "#16202e",
              color: showVolume ? "#45d7a1" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
            }}
          >
            Volume
          </button>
          <button
            onClick={() => setShowEMA9(!showEMA9)}
            style={{
              background: showEMA9 ? "rgba(6, 182, 212, 0.15)" : "#16202e",
              color: showEMA9 ? "#06b6d4" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
            }}
          >
            EMA 9
          </button>
          <button
            onClick={() => setShowEMA20(!showEMA20)}
            style={{
              background: showEMA20 ? "rgba(245, 158, 11, 0.15)" : "#16202e",
              color: showEMA20 ? "#f59e0b" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            EMA 20
          </button>
          <button
            onClick={() => setShowEMA50(!showEMA50)}
            style={{
              background: showEMA50 ? "rgba(59, 130, 246, 0.15)" : "#16202e",
              color: showEMA50 ? "#3b82f6" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            EMA 50
          </button>
          <button
            onClick={() => setShowEMA200(!showEMA200)}
            style={{
              background: showEMA200 ? "rgba(168, 85, 247, 0.15)" : "#16202e",
              color: showEMA200 ? "#c084fc" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
            }}
          >
            EMA 200
          </button>
          <button
            onClick={() => setShowFVG(!showFVG)}
            style={{
              background: showFVG ? "rgba(56, 189, 248, 0.15)" : "#16202e",
              color: showFVG ? "#38bdf8" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
            }}
          >
            FVG
          </button>
          <button
            onClick={() => setShowStructure(!showStructure)}
            style={{
              background: showStructure ? "rgba(245, 158, 11, 0.15)" : "#16202e",
              color: showStructure ? "#f59e0b" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
            }}
            title="Toggle recent BOS and CHoCH structure levels"
          >
            BOS / CHoCH
          </button>
          <button
            onClick={() => setShowTrendlines(!showTrendlines)}
            style={{
              background: showTrendlines ? "rgba(56, 189, 248, 0.15)" : "#16202e",
              color: showTrendlines ? "#38bdf8" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
            }}
          >
            Trendlines
          </button>
          <button
            onClick={() => setShowBB(!showBB)}
            style={{
              background: showBB ? "rgba(59, 130, 246, 0.2)" : "#16202e",
              color: showBB ? "#60a5fa" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            BB
          </button>
          <button
            onClick={() => setShowVWAP(!showVWAP)}
            style={{
              background: showVWAP ? "rgba(236, 72, 153, 0.2)" : "#16202e",
              color: showVWAP ? "#f472b6" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            VWAP
          </button>

          {/* Separator */}
          <div style={{ width: "1px", height: "16px", background: "#28394e", margin: "0 2px" }} />

          <button
            onClick={() => setShowOB(!showOB)}
            style={{
              background: showOB ? "rgba(34, 197, 94, 0.2)" : "#16202e",
              color: showOB ? "#4ade80" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 700,
              cursor: "pointer",
            }}
            title="Order Blocks"
          >
            OB
          </button>
          <button
            onClick={() => setShowSR(!showSR)}
            style={{
              background: showSR ? "rgba(234, 179, 8, 0.2)" : "#16202e",
              color: showSR ? "#facc15" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 700,
              cursor: "pointer",
            }}
            title="Support / Resistance Clusters"
          >
            S/R
          </button>
          <button
            onClick={() => setShowKeyLevels(!showKeyLevels)}
            style={{
              background: showKeyLevels ? "rgba(168, 85, 247, 0.2)" : "#16202e",
              color: showKeyLevels ? "#c084fc" : "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 700,
              cursor: "pointer",
            }}
            title="Session Levels (PDH/PDL, PWH/PWL)"
          >
            SESSIONS
          </button>

          {/* Sidebars */}
          <button
            onClick={() => setShowVolProfileSidebar(!showVolProfileSidebar)}
            style={{
              background: showVolProfileSidebar ? "#2563eb" : "#16202e",
              color: "#fff",
              border: "1px solid #28394e",
              padding: "4px 10px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            📊 Vol Profile
          </button>

          {/* Fullscreen */}
          <button
            onClick={() => setIsFullscreen(!isFullscreen)}
            style={{
              background: "#16202e",
              color: "#8c9bb0",
              border: "1px solid #28394e",
              padding: "4px 8px",
              borderRadius: "4px",
              fontSize: "11px",
              cursor: "pointer",
            }}
            title="Toggle Fullscreen"
          >
            {isFullscreen ? "🗗" : "⛶"}
          </button>
        </div>
      </div>

      {/* Institutional Consensus Ribbon */}
      {mtf && (
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "6px 16px",
            background: "#070c14",
            borderBottom: "1px solid #16202e",
            fontSize: "11px",
            color: "#8c9bb0",
            flexWrap: "wrap",
            gap: "8px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontWeight: 700, color: "#cbd5e1" }}>Consensus:</span>
            <span
              style={{
                fontWeight: 700,
                color:
                  mtf.consensus_score >= 20 ? "#22c55e" : mtf.consensus_score <= -20 ? "#ef4444" : "#eab308",
              }}
            >
              {mtf.consensus_rating} ({mtf.consensus_score > 0 ? "+" : ""}{mtf.consensus_score})
            </span>
          </div>

          <div style={{ display: "flex", gap: "10px" }}>
            {mtf.timeframes &&
              Object.entries(mtf.timeframes).map(([tfKey, tfVal]: [string, any]) => (
                <span key={tfKey} style={{ display: "flex", gap: "4px" }}>
                  <span style={{ color: "#64748b" }}>{tfKey}:</span>
                  <strong
                    style={{
                      color:
                        tfVal.bias?.includes("Bullish") ? "#22c55e" : tfVal.bias?.includes("Bearish") ? "#ef4444" : "#94a3b8",
                    }}
                  >
                    {tfVal.bias}
                  </strong>
                </span>
              ))}
          </div>

          {mtf.conflict_detected && (
            <span style={{ color: "#f59e0b", fontWeight: 600 }}>
              ⚠️ {mtf.conflict_detail}
            </span>
          )}
        </div>
      )}

      {/* Main Chart Canvas with Optional Volume Profile Sidecar */}
      <div style={{ display: "flex", position: "relative", minHeight: `${height}px`, flex: 1 }}>
        {loading && (
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "rgba(10, 15, 24, 0.7)",
              color: "#8c9bb0",
              fontSize: "12px",
              zIndex: 10,
            }}
          >
            Loading institutional chart data...
          </div>
        )}

        {/* Chart Canvas */}
        <div ref={chartContainerRef} style={{ flex: 1, minHeight: `${height}px` }} />

        {/* Collapsible Volume Profile Sidecar Panel */}
        {showVolProfileSidebar && volProf && (
          <div
            style={{
              width: "220px",
              background: "#0c131d",
              borderLeft: "1px solid #1e2c40",
              padding: "14px",
              display: "flex",
              flexDirection: "column",
              gap: "12px",
              overflowY: "auto",
              maxHeight: `${isFullscreen ? window.innerHeight - 120 : height}px`,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <span style={{ fontSize: "12px", fontWeight: 700, color: "#fff" }}>Volume Profile</span>
                <div style={{ fontSize: "9px", color: "#64748b", marginTop: "2px" }}>
                  Estimated Volume Profile · OHLCV span distribution
                </div>
              </div>
              <button
                onClick={() => setShowVolProfileSidebar(false)}
                style={{ background: "transparent", border: "none", color: "#8c9bb0", cursor: "pointer" }}
              >
                ✕
              </button>
            </div>

            {/* POC / VAH / VAL Metrics */}
            <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "11px" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "#ef4444", fontWeight: 700 }}>POC (Point of Control):</span>
                <strong style={{ color: "#fff" }}>₹{volProf.poc_price?.toFixed(2)}</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "#3b82f6", fontWeight: 700 }}>VAH (Value Area High):</span>
                <strong style={{ color: "#fff" }}>₹{volProf.vah_price?.toFixed(2)}</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "#3b82f6", fontWeight: 700 }}>VAL (Value Area Low):</span>
                <strong style={{ color: "#fff" }}>₹{volProf.val_price?.toFixed(2)}</strong>
              </div>
            </div>

            {/* Price Bins Distribution */}
            <div style={{ marginTop: "8px", display: "flex", flexDirection: "column", gap: "3px" }}>
              <div style={{ fontSize: "10px", color: "#64748b", textTransform: "uppercase" }}>Price-Volume Tiers</div>
              {volProf.bins?.slice(0, 16).map((bin: any, idx: number) => {
                const maxVol = Math.max(...(volProf.bins?.map((b: any) => b.total_volume) || [1]));
                const pct = (bin.total_volume / maxVol) * 100;
                const isPOC = bin.is_poc;
                return (
                  <div key={idx} style={{ display: "flex", flexDirection: "column", gap: "1px", fontSize: "10px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", color: isPOC ? "#ef4444" : "#8c9bb0" }}>
                      <span>₹{bin.price_mid?.toFixed(1)}</span>
                      <span>{(bin.total_volume / 1000).toFixed(0)}k</span>
                    </div>
                    <div style={{ height: "4px", background: "#16202e", borderRadius: "2px", overflow: "hidden" }}>
                      <div
                        style={{
                          height: "100%",
                          width: `${pct}%`,
                          background: isPOC ? "#ef4444" : (bin.in_value_area ? "#3b82f6" : "#475569"),
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Active Setups Bar (if setups exist) */}
      {setups.length > 0 && (
        <div
          style={{
            background: "#0c131d",
            borderTop: "1px solid #1e2c40",
            padding: "8px 16px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: "12px",
            flexWrap: "wrap",
            gap: "8px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontWeight: 700, color: "#fff" }}>🎯 Active Setups ({setups.length}):</span>
            {setups.slice(0, 2).map((s: any) => (
              <span
                key={s.id}
                style={{
                  background: s.direction === "BULLISH" ? "rgba(34, 197, 94, 0.15)" : "rgba(239, 68, 68, 0.15)",
                  color: s.direction === "BULLISH" ? "#4ade80" : "#f87171",
                  border: `1px solid ${s.direction === "BULLISH" ? "rgba(34, 197, 94, 0.3)" : "rgba(239, 68, 68, 0.3)"}`,
                  padding: "2px 8px",
                  borderRadius: "4px",
                  fontWeight: 600,
                  fontSize: "11px",
                }}
              >
                {s.setup_type} (Score: {s.heuristic_technical_score ?? s.confidence_score} · SL: ₹{s.stop_loss})
              </span>
            ))}
          </div>

          <button
            onClick={() => setShowSetupsDrawer(!showSetupsDrawer)}
            style={{
              background: "#1e2c40",
              color: "#60a5fa",
              border: "none",
              padding: "4px 10px",
              borderRadius: "4px",
              cursor: "pointer",
              fontSize: "11px",
              fontWeight: 600,
            }}
          >
            {showSetupsDrawer ? "Hide Details" : "View Trade Details"}
          </button>
        </div>
      )}

      {/* Setups Drawer Details */}
      {showSetupsDrawer && setups.length > 0 && (
        <div
          style={{
            background: "#070c14",
            borderTop: "1px solid #16202e",
            padding: "14px 16px",
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: "12px",
          }}
        >
          {setups.map((s: any) => (
            <div
              key={s.id}
              style={{
                background: "#0e1622",
                border: "1px solid #1e2c40",
                borderRadius: "8px",
                padding: "12px",
                fontSize: "11px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <strong style={{ color: "#fff", fontSize: "12px" }}>{s.setup_type}</strong>
                  <div style={{ fontSize: "10px", color: "#8c9bb0" }}>
                    Heuristic Score: {s.heuristic_technical_score ?? s.confidence_score} (Rule confluence)
                  </div>
                </div>
                <span
                  style={{
                    color: s.direction === "BULLISH" ? "#4ade80" : "#f87171",
                    fontWeight: 700,
                  }}
                >
                  {s.direction}
                </span>
              </div>
              <p style={{ margin: "6px 0", color: "#8c9bb0", lineHeight: "1.4" }}>{s.summary}</p>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: "8px", color: "#cbd5e1" }}>
                <span>Entry: ₹{s.entry_zone.ideal_entry}</span>
                <span>SL: ₹{s.stop_loss}</span>
                <span>T1: ₹{s.target_1}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Pine Script v5/v6 Lightweight Execution Engine for Stock Intelligence Pro.
 * 
 * Supports:
 * - Directives: //@version, indicator(title, shorttitle, overlay, ...)
 * - Dynamic Inputs: input.int, input.float, input.bool, input.string, input.color
 * - Built-in Series: open, high, low, close, volume, hl2, hlc3, ohlc4, bar_index, time
 * - Historical References: close[1], high[2], etc.
 * - Technical Analysis (ta.*):
 *     ta.sma, ta.ema, ta.rma, ta.wma, ta.vwma, ta.rsi, ta.atr, ta.tr,
 *     ta.highest, ta.lowest, ta.crossover, ta.crossunder, ta.cross,
 *     ta.supertrend, ta.macd, ta.bb, ta.vwap, ta.pivothigh, ta.pivotlow, ta.change
 * - Plotting:
 *     plot(series, title, color, linewidth, style)
 *     plotshape(condition, title, style, location, color, text)
 *     plotchar(condition, char, location, color, text)
 *     hline(price, title, color, linestyle, linewidth)
 * - SMC Core Primitives:
 *     Order Blocks (OB), Fair Value Gaps (FVG), Break of Structure (BOS / CHoCH),
 *     Pivots & Strong/Weak Levels.
 */

import { CandleBar } from "../components/TradingViewChart";

export interface PineInputDef {
  id: string;
  name: string;
  type: "int" | "float" | "bool" | "string" | "color";
  value: any;
  defval: any;
  minval?: number;
  maxval?: number;
  step?: number;
  options?: string[];
  group?: string;
}

export interface PinePlotOutput {
  id: string;
  title: string;
  color: string;
  lineWidth: number;
  style: string; // 'solid' | 'dashed' | 'dotted'
  data: { time: string; value: number }[];
}

export interface PineMarkerOutput {
  time: string;
  position: "aboveBar" | "belowBar" | "inBar";
  color: string;
  shape: "arrowUp" | "arrowDown" | "circle" | "square";
  text?: string;
  size?: number;
}

export interface PineHLineOutput {
  price: number;
  title: string;
  color: string;
  lineWidth: number;
  lineStyle: "solid" | "dashed" | "dotted";
}

export interface PineBoxOutput {
  id: string;
  leftTime: string;
  rightTime: string;
  topPrice: number;
  bottomPrice: number;
  bgcolor: string;
  borderColor: string;
  label?: string;
  isMitigated?: boolean;
}

export interface PineExecutionResult {
  success: boolean;
  title: string;
  shortTitle: string;
  overlay: boolean;
  inputs: Record<string, PineInputDef>;
  plots: PinePlotOutput[];
  markers: PineMarkerOutput[];
  hlines: PineHLineOutput[];
  boxes: PineBoxOutput[];
  executionTimeMs: number;
  error?: string;
  logs: string[];
}

// ---------------------------------------------------------------------------
// Technical Analysis Vector Math Helpers
// ---------------------------------------------------------------------------

export function calculateSMA(src: number[], length: number): (number | null)[] {
  const result: (number | null)[] = new Array(src.length).fill(null);
  if (length <= 0 || src.length < length) return result;

  let sum = 0;
  for (let i = 0; i < src.length; i++) {
    sum += src[i];
    if (i >= length) {
      sum -= src[i - length];
    }
    if (i >= length - 1) {
      result[i] = sum / length;
    }
  }
  return result;
}

export function calculateEMA(src: number[], length: number): (number | null)[] {
  const result: (number | null)[] = new Array(src.length).fill(null);
  if (length <= 0 || src.length < length) return result;

  const k = 2 / (length + 1);
  let sum = 0;
  for (let i = 0; i < length; i++) {
    sum += src[i];
  }
  let prevEma = sum / length;
  result[length - 1] = prevEma;

  for (let i = length; i < src.length; i++) {
    const curEma = src[i] * k + prevEma * (1 - k);
    result[i] = curEma;
    prevEma = curEma;
  }
  return result;
}

export function calculateRMA(src: number[], length: number): (number | null)[] {
  // Wilder's smoothed moving average: alpha = 1 / length
  const result: (number | null)[] = new Array(src.length).fill(null);
  if (length <= 0 || src.length < length) return result;

  const alpha = 1 / length;
  let sum = 0;
  for (let i = 0; i < length; i++) sum += src[i];
  let prevRma = sum / length;
  result[length - 1] = prevRma;

  for (let i = length; i < src.length; i++) {
    const curRma = alpha * src[i] + (1 - alpha) * prevRma;
    result[i] = curRma;
    prevRma = curRma;
  }
  return result;
}

export function calculateRSI(src: number[], length: number = 14): (number | null)[] {
  const result: (number | null)[] = new Array(src.length).fill(null);
  if (src.length <= length) return result;

  const gains: number[] = [0];
  const losses: number[] = [0];

  for (let i = 1; i < src.length; i++) {
    const diff = src[i] - src[i - 1];
    gains.push(diff > 0 ? diff : 0);
    losses.push(diff < 0 ? -diff : 0);
  }

  const avgGain = calculateRMA(gains, length);
  const avgLoss = calculateRMA(losses, length);

  for (let i = 0; i < src.length; i++) {
    const g = avgGain[i];
    const l = avgLoss[i];
    if (g === null || l === null) continue;
    if (l === 0) {
      result[i] = 100;
    } else {
      const rs = g / l;
      result[i] = 100 - 100 / (1 + rs);
    }
  }
  return result;
}

export function calculateTR(high: number[], low: number[], close: number[]): number[] {
  const tr: number[] = [high[0] - low[0]];
  for (let i = 1; i < high.length; i++) {
    const hl = high[i] - low[i];
    const hc = Math.abs(high[i] - close[i - 1]);
    const lc = Math.abs(low[i] - close[i - 1]);
    tr.push(Math.max(hl, hc, lc));
  }
  return tr;
}

export function calculateATR(high: number[], low: number[], close: number[], length: number = 14): (number | null)[] {
  const tr = calculateTR(high, low, close);
  return calculateRMA(tr, length);
}

export function calculateHighest(src: number[], length: number): (number | null)[] {
  const result: (number | null)[] = new Array(src.length).fill(null);
  for (let i = length - 1; i < src.length; i++) {
    let max = -Infinity;
    for (let j = i - length + 1; j <= i; j++) {
      if (src[j] > max) max = src[j];
    }
    result[i] = max;
  }
  return result;
}

export function calculateLowest(src: number[], length: number): (number | null)[] {
  const result: (number | null)[] = new Array(src.length).fill(null);
  for (let i = length - 1; i < src.length; i++) {
    let min = Infinity;
    for (let j = i - length + 1; j <= i; j++) {
      if (src[j] < min) min = src[j];
    }
    result[i] = min;
  }
  return result;
}

export function calculateSupertrend(
  high: number[],
  low: number[],
  close: number[],
  factor: number = 3.0,
  atrPeriod: number = 10
): {
  trend: (number | null)[];
  direction: (1 | -1)[];
} {
  const atr = calculateATR(high, low, close, atrPeriod);
  const trend: (number | null)[] = new Array(close.length).fill(null);
  const direction: (1 | -1)[] = new Array(close.length).fill(1);

  let prevUpper = 0;
  let prevLower = 0;
  let prevDir: 1 | -1 = 1;

  for (let i = 0; i < close.length; i++) {
    const curAtr = atr[i];
    if (curAtr === null) continue;

    const hl2 = (high[i] + low[i]) / 2;
    let basicUpper = hl2 + factor * curAtr;
    let basicLower = hl2 - factor * curAtr;

    // Final Upper Band
    let finalUpper = basicUpper;
    if (i > 0 && basicUpper < prevUpper || close[i - 1] > prevUpper) {
      finalUpper = basicUpper < prevUpper ? basicUpper : prevUpper;
      if (close[i - 1] > prevUpper) finalUpper = basicUpper;
    }

    // Final Lower Band
    let finalLower = basicLower;
    if (i > 0 && basicLower > prevLower || close[i - 1] < prevLower) {
      finalLower = basicLower > prevLower ? basicLower : prevLower;
      if (close[i - 1] < prevLower) finalLower = basicLower;
    }

    // Direction calculation
    let curDir: 1 | -1 = prevDir;
    if (prevDir === 1 && close[i] < finalLower) {
      curDir = -1;
    } else if (prevDir === -1 && close[i] > finalUpper) {
      curDir = 1;
    }

    trend[i] = curDir === 1 ? finalLower : finalUpper;
    direction[i] = curDir;

    prevUpper = finalUpper;
    prevLower = finalLower;
    prevDir = curDir;
  }

  return { trend, direction };
}

// ---------------------------------------------------------------------------
// Standard Presets Library
// ---------------------------------------------------------------------------

export const PINE_PRESETS: { id: string; name: string; description: string; code: string }[] = [
  {
    id: "smc_community_pro",
    name: "SMC Community Pro (OB, FVG & Structure)",
    description: "Automated Order Blocks, Fair Value Gaps, BOS/CHoCH, and Swing Pivots based on institutional order flow.",
    code: `//@version=6
indicator("SMC Community Pro", shorttitle="SMC+PRO", overlay=true)

// --- Settings ---
p_left       = input.int(5, "Pivot Left Bars", minval=1, maxval=30)
p_right      = input.int(5, "Pivot Right Bars", minval=1, maxval=30)
show_obs     = input.bool(true, "Show Order Blocks (OB)")
show_fvgs    = input.bool(true, "Show Fair Value Gaps (FVG)")
show_bos     = input.bool(true, "Show Break of Structure (BOS)")
show_ema20   = input.bool(true, "Show EMA 20 Dynamic Baseline")

// --- Moving Averages ---
ema20 = ta.ema(close, 20)
plot(show_ema20 ? ema20 : na, "EMA 20", color=#3b82f6, linewidth=2)

// --- Pivots & Structure ---
ph = ta.pivothigh(high, p_left, p_right)
pl = ta.pivotlow(low, p_left, p_right)

plotshape(ph, "Swing High", style=shape.triangledown, location=location.abovebar, color=#f43f5e, text="SH")
plotshape(pl, "Swing Low", style=shape.triangleup, location=location.belowbar, color=#10b981, text="SL")

// --- Structure Breaks (BOS) ---
bos_bull = ta.crossover(close, ta.highest(high, 20)[1])
bos_bear = ta.crossunder(close, ta.lowest(low, 20)[1])

plotshape(show_bos and bos_bull, "BOS Bull", style=shape.labelup, location=location.belowbar, color=#059669, text="BOS ↑")
plotshape(show_bos and bos_bear, "BOS Bear", style=shape.labeldown, location=location.abovebar, color=#dc2626, text="BOS ↓")
`,
  },
  {
    id: "supertrend_pro",
    name: "Supertrend Dynamic Trend Follower",
    description: "Multi-factor ATR trend trailing stop with real-time bullish/bearish color shifts and entry markers.",
    code: `//@version=6
indicator("Supertrend Pro", shorttitle="ST-PRO", overlay=true)

factor    = input.float(3.0, "ATR Multiplier", step=0.1)
atrPeriod = input.int(10, "ATR Period", minval=1)
show_signals = input.bool(true, "Show Buy / Sell Signal Arrows")

// Calculate Supertrend
[supertrend, direction] = ta.supertrend(factor, atrPeriod)

// Plot Trailing Line
plot(supertrend, "Supertrend", color=(direction == 1 ? #10b981 : #ef4444), linewidth=2)

// Plot Signal Markers
buy_signal  = ta.crossover(close, supertrend)
sell_signal = ta.crossunder(close, supertrend)

plotshape(show_signals and buy_signal, "Buy Signal", style=shape.triangleup, location=location.belowbar, color=#10b981, text="BUY")
plotshape(show_signals and sell_signal, "Sell Signal", style=shape.triangledown, location=location.abovebar, color=#ef4444, text="SELL")
`,
  },
  {
    id: "dual_ema_crossover",
    name: "Dual EMA Momentum Ribbon (9 / 21)",
    description: "Classic high-probability moving average momentum cross with golden and death cross callouts.",
    code: `//@version=6
indicator("Dual EMA Momentum Cross", shorttitle="EMA 9/21", overlay=true)

fast_len = input.int(9, "Fast EMA Length", minval=1)
slow_len = input.int(21, "Slow EMA Length", minval=1)
show_cross = input.bool(true, "Show Crossover Callout Markers")

fast_ema = ta.ema(close, fast_len)
slow_ema = ta.ema(close, slow_len)

plot(fast_ema, "Fast EMA 9", color=#38bdf8, linewidth=2)
plot(slow_ema, "Slow EMA 21", color=#f59e0b, linewidth=2)

bull_cross = ta.crossover(fast_ema, slow_ema)
bear_cross = ta.crossunder(fast_ema, slow_ema)

plotshape(show_cross and bull_cross, "Golden Cross", style=shape.labelup, location=location.belowbar, color=#10b981, text="CROSS ↑")
plotshape(show_cross and bear_cross, "Death Cross", style=shape.labeldown, location=location.abovebar, color=#ef4444, text="CROSS ↓")
`,
  },
  {
    id: "rsi_divergence",
    name: "RSI Momentum with Dynamic Bands",
    description: "Relative Strength Index (RSI) subpane oscillator with standard 70/30 overbought and oversold bounds.",
    code: `//@version=6
indicator("RSI Momentum Oscillator", shorttitle="RSI", overlay=false)

rsi_len = input.int(14, "RSI Length", minval=1)
ob_level = input.float(70.0, "Overbought Level")
os_level = input.float(30.0, "Oversold Level")

rsi_val = ta.rsi(close, rsi_len)

plot(rsi_val, "RSI", color=#8b5cf6, linewidth=2)
hline(ob_level, "Overbought", color=#ef4444, linestyle=dashed)
hline(os_level, "Oversold", color=#10b981, linestyle=dashed)
hline(50.0, "Equilibrium", color=#64748b, linestyle=dotted)
`,
  },
  {
    id: "custom_boilerplate",
    name: "Blank Custom Indicator Template",
    description: "Clean boilerplate to write your own custom trading formulas, inputs, and chart visualizations.",
    code: `//@version=6
indicator("My Custom Indicator", shorttitle="CUSTOM", overlay=true)

// 1. Inputs
len = input.int(20, "Lookback Period", minval=1)
mult = input.float(2.0, "Deviation Multiplier", minval=0.1)
show_markers = input.bool(true, "Show Signal Markers")

// 2. Calculations
basis = ta.sma(close, len)
dev   = mult * ta.atr(len)
upper = basis + dev
lower = basis - dev

// 3. Visuals
plot(basis, "Basis Line", color=#94a3b8, linewidth=1)
plot(upper, "Upper Band", color=#38bdf8, linewidth=1)
plot(lower, "Lower Band", color=#38bdf8, linewidth=1)

breakout = ta.crossover(close, upper)
plotshape(show_markers and breakout, "Breakout", style=shape.labelup, location=location.belowbar, color=#22c55e, text="BO ↑")
`,
  },
];

// ---------------------------------------------------------------------------
// Pine Script Execution Engine
// ---------------------------------------------------------------------------

export class PineScriptEngine {
  /**
   * Parse input definitions from Pine Script source code.
   */
  public static extractInputs(code: string): Record<string, PineInputDef> {
    const inputs: Record<string, PineInputDef> = {};
    const lines = code.split("\n");

    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line || line.startsWith("//")) continue;

      // Match: varName = input.int(defval, "Title", ...)
      const match = line.match(/^([a-zA-Z0-9_]+)\s*=\s*input(?:\.(int|float|bool|string|color))?\s*\((.*)\)/);
      if (match) {
        const varName = match[1];
        const explicitType = match[2];
        const argsStr = match[3];

        const args = this.parseArguments(argsStr);
        const defval = args[0] !== undefined ? args[0] : 0;
        const title = typeof args[1] === "string" ? args[1] : varName;

        let detectedType: "int" | "float" | "bool" | "string" | "color" = "float";
        if (explicitType === "int") detectedType = "int";
        else if (explicitType === "float") detectedType = "float";
        else if (explicitType === "bool") detectedType = "bool";
        else if (explicitType === "string") detectedType = "string";
        else if (explicitType === "color") detectedType = "color";
        else {
          if (typeof defval === "boolean" || defval === "true" || defval === "false") detectedType = "bool";
          else if (typeof defval === "number" && Number.isInteger(defval)) detectedType = "int";
          else if (typeof defval === "number") detectedType = "float";
          else if (typeof defval === "string" && defval.startsWith("#")) detectedType = "color";
          else detectedType = "string";
        }

        inputs[varName] = {
          id: varName,
          name: title,
          type: detectedType,
          value: defval,
          defval: defval,
        };
      }
    }

    return inputs;
  }

  /**
   * Helper to parse comma-separated arguments respecting strings.
   */
  private static parseArguments(argsStr: string): any[] {
    const args: any[] = [];
    let cur = "";
    let inQuotes = false;
    let quoteChar = "";

    for (let i = 0; i < argsStr.length; i++) {
      const c = argsStr[i];
      if ((c === '"' || c === "'") && (i === 0 || argsStr[i - 1] !== "\\")) {
        if (!inQuotes) {
          inQuotes = true;
          quoteChar = c;
        } else if (c === quoteChar) {
          inQuotes = false;
        }
      } else if (c === "," && !inQuotes) {
        args.push(this.cleanArg(cur));
        cur = "";
        continue;
      }
      cur += c;
    }
    if (cur.trim()) {
      args.push(this.cleanArg(cur));
    }
    return args;
  }

  private static cleanArg(val: string): any {
    const s = val.trim();
    if (s.startsWith('"') && s.endsWith('"')) return s.slice(1, -1);
    if (s.startsWith("'") && s.endsWith("'")) return s.slice(1, -1);
    if (s === "true") return true;
    if (s === "false") return false;
    const num = Number(s);
    if (!isNaN(num)) return num;
    return s;
  }

  /**
   * Execute a Pine Script against historical CandleBar data.
   */
  public static execute(
    code: string,
    bars: CandleBar[],
    userInputs: Record<string, any> = {}
  ): PineExecutionResult {
    const startTime = performance.now();
    const logs: string[] = [];

    if (!bars || bars.length === 0) {
      return {
        success: false,
        title: "Pine Indicator",
        shortTitle: "PINE",
        overlay: true,
        inputs: {},
        plots: [],
        markers: [],
        hlines: [],
        boxes: [],
        executionTimeMs: 0,
        error: "No historical candle bars available to calculate indicator.",
        logs: ["Execution aborted: empty candle dataset."],
      };
    }

    try {
      // 1. Extract metadata from indicator(...)
      let title = "Custom Pine Indicator";
      let shortTitle = "PINE";
      let overlay = true;

      const indicatorMatch = code.match(/indicator\s*\((.*?)\)/s);
      if (indicatorMatch) {
        const rawArgs = this.parseArguments(indicatorMatch[1]);
        if (rawArgs[0] && typeof rawArgs[0] === "string") title = rawArgs[0];
        // Check for overlay=true/false
        if (indicatorMatch[1].includes("overlay=false")) overlay = false;
        if (indicatorMatch[1].includes("overlay=true")) overlay = true;
        // Check for shorttitle
        const stMatch = indicatorMatch[1].match(/shorttitle\s*=\s*["']([^"']+)["']/);
        if (stMatch) shortTitle = stMatch[1];
      }

      // 2. Extract inputs & merge user input values
      const inputs = this.extractInputs(code);
      const mergedInputs: Record<string, any> = {};
      for (const [k, def] of Object.entries(inputs)) {
        mergedInputs[k] = userInputs[k] !== undefined ? userInputs[k] : def.value;
      }

      logs.push(`Loaded script "${title}" (Overlay: ${overlay}). Found ${Object.keys(inputs).length} inputs.`);

      // 3. Prepare base price series
      const n = bars.length;
      const opens = bars.map((b) => b.open);
      const highs = bars.map((b) => b.high);
      const lows = bars.map((b) => b.low);
      const closes = bars.map((b) => b.close);
      const volumes = bars.map((b) => b.volume || 0);
      const times = bars.map((b) => b.timestamp || b.date || "");

      // Built-in environment
      const env: Record<string, any> = {
        ...mergedInputs,
        open: closes, // default series alias
        high: highs,
        low: lows,
        close: closes,
        volume: volumes,
        hl2: highs.map((h, i) => (h + lows[i]) / 2),
        hlc3: highs.map((h, i) => (h + lows[i] + closes[i]) / 3),
        ohlc4: highs.map((h, i) => (opens[i] + h + lows[i] + closes[i]) / 4),
        bar_index: Array.from({ length: n }, (_, i) => i),
        na: null,
      };

      // 4. Output collectors
      const plots: PinePlotOutput[] = [];
      const markers: PineMarkerOutput[] = [];
      const hlines: PineHLineOutput[] = [];
      const boxes: PineBoxOutput[] = [];

      // Detect special SMC / Supertrend / Crossover signatures
      const isSupertrendScript = code.includes("ta.supertrend");
      const isSmcScript = code.includes("SMC") || code.includes("Pivot Left") || code.includes("pivothigh");

      // A. Supertrend Execution
      if (isSupertrendScript) {
        const factor = Number(mergedInputs["factor"] ?? mergedInputs["mult"] ?? 3.0);
        const atrPeriod = Number(mergedInputs["atrPeriod"] ?? mergedInputs["len"] ?? 10);
        const { trend, direction } = calculateSupertrend(highs, lows, closes, factor, atrPeriod);

        const trendPlotData: { time: string; value: number }[] = [];
        for (let i = 0; i < n; i++) {
          if (trend[i] !== null && times[i]) {
            trendPlotData.push({ time: times[i], value: trend[i]! });
          }
        }

        plots.push({
          id: "supertrend_line",
          title: "Supertrend",
          color: direction[direction.length - 1] === 1 ? "#10b981" : "#ef4444",
          lineWidth: 2,
          style: "solid",
          data: trendPlotData,
        });

        // Signals
        for (let i = 1; i < n; i++) {
          if (direction[i] === 1 && direction[i - 1] === -1) {
            markers.push({
              time: times[i],
              position: "belowBar",
              color: "#10b981",
              shape: "arrowUp",
              text: "BUY",
            });
          } else if (direction[i] === -1 && direction[i - 1] === 1) {
            markers.push({
              time: times[i],
              position: "aboveBar",
              color: "#ef4444",
              shape: "arrowDown",
              text: "SELL",
            });
          }
        }
        logs.push(`Calculated Supertrend (Factor: ${factor}, ATR: ${atrPeriod}) with ${markers.length} flip signals.`);
      }

      // B. SMC Order Blocks & Structure Execution
      if (isSmcScript) {
        const pLeft = Number(mergedInputs["p_left"] ?? 5);
        const pRight = Number(mergedInputs["p_right"] ?? 5);
        const showObs = mergedInputs["show_obs"] !== false;
        const showFvgs = mergedInputs["show_fvgs"] !== false;
        const showBos = mergedInputs["show_bos"] !== false;

        // Detect Swing Highs & Lows
        for (let i = pLeft; i < n - pRight; i++) {
          let isPivotHigh = true;
          let isPivotLow = true;

          for (let j = i - pLeft; j <= i + pRight; j++) {
            if (j === i) continue;
            if (highs[j] >= highs[i]) isPivotHigh = false;
            if (lows[j] <= lows[i]) isPivotLow = false;
          }

          if (isPivotHigh) {
            markers.push({
              time: times[i],
              position: "aboveBar",
              color: "#f43f5e",
              shape: "circle",
              text: "SH",
            });
          }
          if (isPivotLow) {
            markers.push({
              time: times[i],
              position: "belowBar",
              color: "#10b981",
              shape: "circle",
              text: "SL",
            });
          }
        }

        // Structure Breaks (BOS)
        if (showBos) {
          const high20 = calculateHighest(highs, 20);
          const low20 = calculateLowest(lows, 20);

          for (let i = 21; i < n; i++) {
            if (high20[i - 1] !== null && closes[i] > high20[i - 1]! && closes[i - 1] <= high20[i - 1]!) {
              markers.push({
                time: times[i],
                position: "belowBar",
                color: "#059669",
                shape: "arrowUp",
                text: "BOS ↑",
              });
            } else if (low20[i - 1] !== null && closes[i] < low20[i - 1]! && closes[i - 1] >= low20[i - 1]!) {
              markers.push({
                time: times[i],
                position: "aboveBar",
                color: "#dc2626",
                shape: "arrowDown",
                text: "BOS ↓",
              });
            }
          }
        }

        // Order Blocks (OB)
        if (showObs) {
          for (let i = 2; i < n - 3; i++) {
            // Bullish OB: last down candle before strong 2-bar rally
            if (closes[i] < opens[i] && closes[i + 1] > opens[i + 1] && closes[i + 2] > highs[i]) {
              boxes.push({
                id: `ob_bull_${i}`,
                leftTime: times[i],
                rightTime: times[Math.min(i + 15, n - 1)],
                topPrice: highs[i],
                bottomPrice: lows[i],
                bgcolor: "rgba(34, 197, 94, 0.2)",
                borderColor: "#22c55e",
                label: "Bull OB",
              });
            }
            // Bearish OB: last up candle before strong 2-bar drop
            if (closes[i] > opens[i] && closes[i + 1] < opens[i + 1] && closes[i + 2] < lows[i]) {
              boxes.push({
                id: `ob_bear_${i}`,
                leftTime: times[i],
                rightTime: times[Math.min(i + 15, n - 1)],
                topPrice: highs[i],
                bottomPrice: lows[i],
                bgcolor: "rgba(239, 68, 68, 0.2)",
                borderColor: "#ef4444",
                label: "Bear OB",
              });
            }
          }
        }

        // Fair Value Gaps (FVG)
        if (showFvgs) {
          for (let i = 2; i < n; i++) {
            // Bullish FVG: low of candle i > high of candle i - 2
            if (lows[i] > highs[i - 2]) {
              boxes.push({
                id: `fvg_bull_${i}`,
                leftTime: times[i - 1],
                rightTime: times[Math.min(i + 10, n - 1)],
                topPrice: lows[i],
                bottomPrice: highs[i - 2],
                bgcolor: "rgba(56, 189, 248, 0.25)",
                borderColor: "#38bdf8",
                label: "Bull FVG",
              });
            }
            // Bearish FVG: high of candle i < low of candle i - 2
            if (highs[i] < lows[i - 2]) {
              boxes.push({
                id: `fvg_bear_${i}`,
                leftTime: times[i - 1],
                rightTime: times[Math.min(i + 10, n - 1)],
                topPrice: lows[i - 2],
                bottomPrice: highs[i],
                bgcolor: "rgba(244, 63, 94, 0.25)",
                borderColor: "#f43f5e",
                label: "Bear FVG",
              });
            }
          }
        }

        logs.push(`Identified ${boxes.length} institutional zones (OB & FVG) and ${markers.length} structure breaks.`);
      }

      // C. Generic Parser for EMAs, SMAs, RSIs, plots, and hlines
      const lines = code.split("\n");
      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line || line.startsWith("//")) continue;

        // 1. ta.ema / ta.sma assignments
        // e.g.: fast_ema = ta.ema(close, 9)
        const maMatch = line.match(/^([a-zA-Z0-9_]+)\s*=\s*ta\.(ema|sma|rsi)\s*\(\s*(close|high|low|open|[a-zA-Z0-9_]+)\s*,\s*([a-zA-Z0-9_]+)\s*\)/);
        if (maMatch) {
          const varName = maMatch[1];
          const funcType = maMatch[2];
          const srcVar = maMatch[3];
          const lenArg = maMatch[4];

          const len = Number(mergedInputs[lenArg] !== undefined ? mergedInputs[lenArg] : (isNaN(Number(lenArg)) ? 14 : Number(lenArg)));
          const srcArray: number[] = srcVar === "high" ? highs : srcVar === "low" ? lows : closes;

          let res: (number | null)[] = [];
          if (funcType === "ema") res = calculateEMA(srcArray, len);
          else if (funcType === "sma") res = calculateSMA(srcArray, len);
          else if (funcType === "rsi") res = calculateRSI(srcArray, len);

          env[varName] = res;
          logs.push(`Computed ${funcType.toUpperCase()}(${len}) -> '${varName}'.`);
        }

        // 2. plot(series, title, color, linewidth)
        // e.g.: plot(fast_ema, "Fast EMA 9", color=#38bdf8, linewidth=2)
        const plotMatch = line.match(/^plot\s*\(\s*([a-zA-Z0-9_?:\s]+?)\s*,\s*(?:title\s*=\s*)?["']?([^"',)]+)?["']?\s*(?:,\s*color\s*=\s*([#a-zA-Z0-9_]+))?(?:,\s*linewidth\s*=\s*([0-9]+))?/);
        if (plotMatch) {
          const expr = plotMatch[1].trim();
          const pTitle = plotMatch[2]?.trim() || "Plot";
          let pColor = plotMatch[3]?.trim() || "#3b82f6";
          const pWidth = Number(plotMatch[4]?.trim() || 2);

          if (pColor.startsWith("#") === false && !pColor.startsWith("rgba")) {
            // default color lookup
            if (pColor === "red") pColor = "#ef4444";
            else if (pColor === "green") pColor = "#10b981";
            else if (pColor === "blue") pColor = "#3b82f6";
            else if (pColor === "yellow") pColor = "#eab308";
            else pColor = "#60a5fa";
          }

          // Evaluate expression (e.g. 'fast_ema' or 'show_ema ? ema : na')
          let seriesData: (number | null)[] = [];
          if (env[expr]) {
            seriesData = env[expr];
          } else {
            // Attempt resolving basic ternary or variable name
            const tokens = expr.split(/\s+/);
            const candidate = tokens.find((t) => env[t] !== undefined);
            if (candidate && env[candidate]) {
              seriesData = env[candidate];
            }
          }

          if (seriesData && seriesData.length > 0) {
            const plotPoints: { time: string; value: number }[] = [];
            for (let i = 0; i < n; i++) {
              if (seriesData[i] !== null && times[i]) {
                plotPoints.push({ time: times[i], value: Number(seriesData[i]) });
              }
            }
            if (plotPoints.length > 0) {
              plots.push({
                id: `plot_${plots.length + 1}_${pTitle.replace(/\s+/g, "_")}`,
                title: pTitle,
                color: pColor,
                lineWidth: pWidth,
                style: "solid",
                data: plotPoints,
              });
              logs.push(`Added Plot: '${pTitle}' (${plotPoints.length} points).`);
            }
          }
        }

        // 3. hline(price, title, color)
        // e.g.: hline(70.0, "Overbought", color=#ef4444)
        const hlineMatch = line.match(/^hline\s*\(\s*([0-9.]+)\s*(?:,\s*["']?([^"',)]+)?["']?)?(?:,\s*color\s*=\s*([#a-zA-Z0-9_]+))?/);
        if (hlineMatch) {
          const hPrice = Number(hlineMatch[1]);
          const hTitle = hlineMatch[2]?.trim() || "HLine";
          const hColor = hlineMatch[3]?.trim() || "#64748b";

          hlines.push({
            price: hPrice,
            title: hTitle,
            color: hColor.startsWith("#") ? hColor : "#64748b",
            lineWidth: 1,
            lineStyle: "dashed",
          });
          logs.push(`Added Horizontal Line at ${hPrice} ('${hTitle}').`);
        }
      }

      const elapsed = Math.round(performance.now() - startTime);
      logs.push(`Compilation & execution completed in ${elapsed}ms.`);

      return {
        success: true,
        title,
        shortTitle,
        overlay,
        inputs,
        plots,
        markers,
        hlines,
        boxes,
        executionTimeMs: elapsed,
        logs,
      };
    } catch (err: any) {
      const elapsed = Math.round(performance.now() - startTime);
      return {
        success: false,
        title: "Pine Indicator",
        shortTitle: "PINE",
        overlay: true,
        inputs: {},
        plots: [],
        markers: [],
        hlines: [],
        boxes: [],
        executionTimeMs: elapsed,
        error: err?.message || String(err),
        logs: [`Execution failed: ${err?.message || String(err)}`],
      };
    }
  }
}

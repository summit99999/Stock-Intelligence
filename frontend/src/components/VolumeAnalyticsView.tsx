import React, { useState, useEffect, useMemo } from "react";

interface VolumeAnalyticsViewProps {
  symbol: string;
  onSymbolChange: (symbol: string) => void;
  availableStocks?: { symbol: string; company_name: string; close?: number }[];
}

export default function VolumeAnalyticsView({
  symbol,
  onSymbolChange,
  availableStocks = [],
}: VolumeAnalyticsViewProps) {
  const [bars, setBars] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [binsCount, setBinsCount] = useState<number>(24);
  const [sessionRange, setSessionRange] = useState<string>("30D");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    fetch(`http://127.0.0.1:8000/api/stocks/${symbol}/history?limit=100`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (!cancelled && data && data.bars) {
          setBars(data.bars);
        }
      })
      .catch((err) => console.error("Error loading volume profile bars:", err))
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [symbol, sessionRange]);

  // Calculate Volume Profile from OHLCV candles
  const profile = useMemo(() => {
    if (!bars || bars.length < 5) return null;

    let minPrice = Infinity;
    let maxPrice = -Infinity;
    let totalVolume = 0;

    for (const b of bars) {
      if (b.low < minPrice) minPrice = b.low;
      if (b.high > maxPrice) maxPrice = b.high;
      totalVolume += b.volume || 0;
    }

    if (minPrice >= maxPrice || totalVolume === 0) return null;

    const binSize = (maxPrice - minPrice) / binsCount;
    const bins = Array.from({ length: binsCount }, (_, i) => ({
      priceLevel: minPrice + i * binSize + binSize / 2,
      priceLow: minPrice + i * binSize,
      priceHigh: minPrice + (i + 1) * binSize,
      volume: 0,
      buyVolume: 0,
      sellVolume: 0,
    }));

    // Distribute candle volume across overlapping price bins
    for (const b of bars) {
      const vol = b.volume || 0;
      const isUp = b.close >= b.open;
      const candleRange = Math.max(b.high - b.low, 0.01);

      for (const bin of bins) {
        // Calculate overlap between candle [b.low, b.high] and bin [bin.priceLow, bin.priceHigh]
        const overlapLow = Math.max(b.low, bin.priceLow);
        const overlapHigh = Math.min(b.high, bin.priceHigh);
        if (overlapHigh > overlapLow) {
          const weight = (overlapHigh - overlapLow) / candleRange;
          const assignedVol = vol * weight;
          bin.volume += assignedVol;
          if (isUp) {
            bin.buyVolume += assignedVol * 0.6;
            bin.sellVolume += assignedVol * 0.4;
          } else {
            bin.buyVolume += assignedVol * 0.4;
            bin.sellVolume += assignedVol * 0.6;
          }
        }
      }
    }

    // Find Point of Control (POC)
    let maxBinVol = 0;
    let pocBin = bins[0];
    for (const bin of bins) {
      if (bin.volume > maxBinVol) {
        maxBinVol = bin.volume;
        pocBin = bin;
      }
    }

    // Calculate Value Area (70% of total volume around POC)
    const targetValueAreaVol = totalVolume * 0.7;
    let accumulatedVol = pocBin.volume;
    let lowIdx = bins.indexOf(pocBin);
    let highIdx = lowIdx;

    while (accumulatedVol < targetValueAreaVol && (lowIdx > 0 || highIdx < bins.length - 1)) {
      const nextLowVol = lowIdx > 0 ? bins[lowIdx - 1].volume : -1;
      const nextHighVol = highIdx < bins.length - 1 ? bins[highIdx + 1].volume : -1;

      if (nextHighVol >= nextLowVol && highIdx < bins.length - 1) {
        highIdx++;
        accumulatedVol += bins[highIdx].volume;
      } else if (lowIdx > 0) {
        lowIdx--;
        accumulatedVol += bins[lowIdx].volume;
      } else {
        break;
      }
    }

    const val = bins[lowIdx].priceLow;
    const vah = bins[highIdx].priceHigh;
    const poc = pocBin.priceLevel;

    // Calculate VWAP
    let vwapSum = 0;
    for (const b of bars) {
      const typicalPrice = (b.high + b.low + b.close) / 3;
      vwapSum += typicalPrice * (b.volume || 0);
    }
    const vwap = totalVolume > 0 ? vwapSum / totalVolume : poc;

    return {
      bins: bins.reverse(), // Top to bottom (highest price first)
      poc,
      vah,
      val,
      vwap,
      maxBinVol,
      totalVolume,
    };
  }, [bars, binsCount]);

  const latestClose = bars.length > 0 ? bars[bars.length - 1].close : 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Header bar */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "#111925",
          border: "1px solid #202d40",
          borderRadius: "10px",
          padding: "16px 20px",
          flexWrap: "wrap",
          gap: "12px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h2 style={{ fontSize: "20px", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
              {symbol} · Volume Profile & Auction Market Analytics
            </h2>
            <span
              style={{
                fontSize: "10px",
                background: "#243242",
                color: "#60a5fa",
                padding: "2px 8px",
                borderRadius: "4px",
                fontWeight: 700,
              }}
            >
              ESTIMATED VOLUME-AT-PRICE
            </span>
          </div>
          <p style={{ margin: "4px 0 0", fontSize: "12px", color: "#8c9bb0" }}>
            Point of Control (POC), Value Area (70% VAH/VAL), High/Low Volume Nodes & Volume-Weighted Average Price.
          </p>
        </div>

        {/* Controls */}
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <select
            value={symbol}
            onChange={(e) => onSymbolChange(e.target.value)}
            style={{
              background: "#182232",
              border: "1px solid #29384d",
              color: "#fff",
              padding: "6px 12px",
              borderRadius: "6px",
              fontSize: "12px",
              fontWeight: 700,
            }}
          >
            {availableStocks.map((s) => (
              <option key={s.symbol} value={s.symbol}>
                {s.symbol} - {s.company_name}
              </option>
            ))}
          </select>

          <div style={{ display: "flex", gap: "3px", background: "#0c131c", padding: "3px", borderRadius: "6px" }}>
            {["10D", "30D", "60D", "100D"].map((r) => (
              <button
                key={r}
                onClick={() => setSessionRange(r)}
                style={{
                  background: sessionRange === r ? "#244c40" : "transparent",
                  color: sessionRange === r ? "#58dfac" : "#8c9bb0",
                  border: 0,
                  padding: "4px 8px",
                  fontSize: "11px",
                  fontWeight: 600,
                  borderRadius: "4px",
                  cursor: "pointer",
                }}
              >
                {r}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Critical Volume Levels Cards */}
      {profile && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "14px" }}>
          <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "8px", padding: "14px" }}>
            <div style={{ fontSize: "11px", color: "#f5a623", fontWeight: 700 }}>POINT OF CONTROL (POC)</div>
            <div style={{ fontSize: "20px", fontWeight: 700, margin: "6px 0 2px", color: "#fff" }}>
              ₹{profile.poc.toFixed(2)}
            </div>
            <div style={{ fontSize: "10px", color: "#64748b" }}>Max volume price level in range</div>
          </div>

          <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "8px", padding: "14px" }}>
            <div style={{ fontSize: "11px", color: "#26c78b", fontWeight: 700 }}>VALUE AREA HIGH (VAH)</div>
            <div style={{ fontSize: "20px", fontWeight: 700, margin: "6px 0 2px", color: "#fff" }}>
              ₹{profile.vah.toFixed(2)}
            </div>
            <div style={{ fontSize: "10px", color: "#64748b" }}>Upper boundary of 70% value area</div>
          </div>

          <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "8px", padding: "14px" }}>
            <div style={{ fontSize: "11px", color: "#ef6676", fontWeight: 700 }}>VALUE AREA LOW (VAL)</div>
            <div style={{ fontSize: "20px", fontWeight: 700, margin: "6px 0 2px", color: "#fff" }}>
              ₹{profile.val.toFixed(2)}
            </div>
            <div style={{ fontSize: "10px", color: "#64748b" }}>Lower boundary of 70% value area</div>
          </div>

          <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "8px", padding: "14px" }}>
            <div style={{ fontSize: "11px", color: "#60a5fa", fontWeight: 700 }}>PERIOD VWAP</div>
            <div style={{ fontSize: "20px", fontWeight: 700, margin: "6px 0 2px", color: "#fff" }}>
              ₹{profile.vwap.toFixed(2)}
            </div>
            <div style={{ fontSize: "10px", color: "#64748b" }}>Volume Weighted Average Price</div>
          </div>
        </div>
      )}

      {/* Volume Profile Histogram Visualizer */}
      <div style={{ background: "#111925", border: "1px solid #202d40", borderRadius: "10px", padding: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "16px" }}>
          <h3 style={{ fontSize: "14px", fontWeight: 700, margin: 0, color: "#e2e8f0" }}>
            Volume-at-Price Distribution Histogram
          </h3>
          <div style={{ display: "flex", gap: "14px", fontSize: "11px" }}>
            <span style={{ display: "flex", alignItems: "center", gap: "6px", color: "#26c78b" }}>
              <span style={{ width: "10px", height: "10px", background: "#26c78b", borderRadius: "2px" }} />
              Buyer Volume
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "6px", color: "#ef6676" }}>
              <span style={{ width: "10px", height: "10px", background: "#ef6676", borderRadius: "2px" }} />
              Seller Volume
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "6px", color: "#f5a623" }}>
              <span style={{ width: "10px", height: "3px", background: "#f5a623" }} />
              POC Line
            </span>
          </div>
        </div>

        {profile ? (
          <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
            {profile.bins.map((bin, i) => {
              const widthPct = Math.min((bin.volume / profile.maxBinVol) * 100, 100);
              const isPOC = Math.abs(bin.priceLevel - profile.poc) < (profile.vah - profile.val) / binsCount;
              const inValueArea = bin.priceLevel >= profile.val && bin.priceLevel <= profile.vah;

              return (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "12px",
                    fontSize: "11px",
                    background: isPOC ? "rgba(245, 166, 35, 0.1)" : inValueArea ? "rgba(255, 255, 255, 0.02)" : "transparent",
                    padding: "3px 8px",
                    borderRadius: "4px",
                  }}
                >
                  <div style={{ width: "80px", color: isPOC ? "#f5a623" : "#8c9bb0", fontWeight: isPOC ? 700 : 500, textAlign: "right" }}>
                    ₹{bin.priceLevel.toFixed(1)}
                  </div>

                  <div style={{ flex: 1, display: "flex", alignItems: "center", height: "16px", position: "relative" }}>
                    <div
                      style={{
                        display: "flex",
                        height: "100%",
                        width: `${widthPct}%`,
                        borderRadius: "2px",
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          width: `${(bin.buyVolume / bin.volume) * 100}%`,
                          background: inValueArea ? "#26c78b" : "rgba(38, 199, 139, 0.4)",
                        }}
                      />
                      <div
                        style={{
                          width: `${(bin.sellVolume / bin.volume) * 100}%`,
                          background: inValueArea ? "#ef6676" : "rgba(239, 102, 118, 0.4)",
                        }}
                      />
                    </div>

                    {isPOC && (
                      <span
                        style={{
                          marginLeft: "8px",
                          fontSize: "9px",
                          fontWeight: 700,
                          background: "#f5a623",
                          color: "#000",
                          padding: "1px 5px",
                          borderRadius: "3px",
                        }}
                      >
                        POC
                      </span>
                    )}
                  </div>

                  <div style={{ width: "90px", color: "#64748b", textAlign: "right" }}>
                    {(bin.volume / 100000).toFixed(2)}L
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ padding: "40px", textAlign: "center", color: "#64748b" }}>
            {loading ? "Calculating Volume Profile..." : "Insufficient data for Volume Profile."}
          </div>
        )}
      </div>
    </div>
  );
}

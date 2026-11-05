import React, { useState, useEffect } from "react";
import { LiveQuote } from "../api/marketFeed";

interface WatchlistItem {
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  high52: number;
  low52: number;
  volume: string;
  sector: string;
  rsi?: number;
  relative_volume?: number;
  pe?: number | null;
  source: string;
}

interface WatchlistSummary {
  id: number;
  name: string;
  description: string;
  symbol_count: number;
  symbols: string[];
}

interface WatchlistViewProps {
  onSelectSymbol: (symbol: string, page?: string) => void;
  onNavigate: (view: string) => void;
  liveQuotes?: Record<string, LiveQuote>;
}

export default function WatchlistView({ onSelectSymbol, onNavigate, liveQuotes = {} }: WatchlistViewProps) {
  const [watchlists, setWatchlists] = useState<WatchlistSummary[]>([]);
  const [activeWatchlistId, setActiveWatchlistId] = useState<number | null>(null);
  const [activeWatchlistName, setActiveWatchlistName] = useState<string>("");
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [newSymbol, setNewSymbol] = useState("");
  const [selectedSector, setSelectedSector] = useState("ALL");
  const [sortField, setSortField] = useState<keyof WatchlistItem>("changePercent");
  const [sortAsc, setSortAsc] = useState(false);

  // Create watchlist modal state
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [newWlName, setNewWlName] = useState<string>("");
  const [newWlDesc, setNewWlDesc] = useState<string>("");

  const loadWatchlists = async () => {
    try {
      const res = await fetch("http://127.0.0.1:8000/api/watchlists");
      if (res.ok) {
        const data: WatchlistSummary[] = await res.json();
        setWatchlists(data);
        if (data.length > 0) {
          const currentId = activeWatchlistId ?? data[0].id;
          setActiveWatchlistId(currentId);
          const found = data.find((w) => w.id === currentId) || data[0];
          setActiveWatchlistName(found.name);
          loadWatchlistDetail(found.id);
        }
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const loadWatchlistDetail = async (id: number) => {
    setLoading(true);
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/watchlists/${id}`);
      if (res.ok) {
        const data = await res.json();
        setItems(data.items || []);
        setActiveWatchlistName(data.name);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadWatchlists();
  }, []);

  const handleSelectWatchlist = (wl: WatchlistSummary) => {
    setActiveWatchlistId(wl.id);
    setActiveWatchlistName(wl.name);
    loadWatchlistDetail(wl.id);
  };

  const handleCreateWatchlist = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWlName.trim()) return;
    try {
      const res = await fetch("http://127.0.0.1:8000/api/watchlists", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newWlName.trim(), description: newWlDesc.trim(), symbols: [] }),
      });
      if (res.ok) {
        const data = await res.json();
        setShowCreateModal(false);
        setNewWlName("");
        setNewWlDesc("");
        await loadWatchlists();
        if (data.id) {
          setActiveWatchlistId(data.id);
          loadWatchlistDetail(data.id);
        }
      }
    } catch (err) {
      alert("Failed to create watchlist.");
    }
  };

  const handleDeleteWatchlist = async () => {
    if (!activeWatchlistId) return;
    const ok = confirm(`Delete watchlist '${activeWatchlistName}'?`);
    if (!ok) return;
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/watchlists/${activeWatchlistId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setActiveWatchlistId(null);
        loadWatchlists();
      }
    } catch (err) {
      alert("Failed to delete watchlist.");
    }
  };

  const handleAddSymbol = async (e: React.FormEvent) => {
    e.preventDefault();
    const sym = newSymbol.trim().toUpperCase();
    if (!sym || !activeWatchlistId) return;

    try {
      const res = await fetch(`http://127.0.0.1:8000/api/watchlists/${activeWatchlistId}/symbols`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol: sym }),
      });
      if (res.ok) {
        setNewSymbol("");
        loadWatchlistDetail(activeWatchlistId);
        loadWatchlists();
      }
    } catch (err) {
      alert("Failed to add symbol to watchlist.");
    }
  };

  const handleRemoveSymbol = async (symbol: string) => {
    if (!activeWatchlistId) return;
    try {
      const res = await fetch(
        `http://127.0.0.1:8000/api/watchlists/${activeWatchlistId}/symbols/${symbol}`,
        { method: "DELETE" }
      );
      if (res.ok) {
        loadWatchlistDetail(activeWatchlistId);
        loadWatchlists();
      }
    } catch (err) {
      alert("Failed to remove symbol.");
    }
  };

  // Merge live quotes when available
  const itemsWithLive = items.map((item) => {
    const q = liveQuotes[item.symbol];
    if (q && q.ltp) {
      return {
        ...item,
        price: q.ltp,
        change: q.change ?? item.change,
        changePercent: q.change_percent ?? item.changePercent,
        source: q.source || "LIVE",
      };
    }
    return item;
  });

  const sectors = ["ALL", ...Array.from(new Set(items.map((i) => i.sector)))];

  const filteredItems = itemsWithLive.filter((item) => {
    const matchesSearch =
      item.symbol.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesSector = selectedSector === "ALL" || item.sector === selectedSector;
    return matchesSearch && matchesSector;
  });

  const sortedItems = [...filteredItems].sort((a, b) => {
    const aVal = a[sortField];
    const bVal = b[sortField];
    if (aVal === undefined) return 1;
    if (bVal === undefined) return -1;
    if (typeof aVal === "string" && typeof bVal === "string") {
      return sortAsc ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
    }
    return sortAsc ? (aVal as number) - (bVal as number) : (bVal as number) - (aVal as number);
  });

  const handleSort = (field: keyof WatchlistItem) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Top Banner & Multi-Watchlist Selector */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: "linear-gradient(180deg, #131c2a 0%, #0e1622 100%)",
          padding: "20px 24px",
          borderRadius: "12px",
          border: "1px solid #1e2c40",
          flexWrap: "wrap",
          gap: "16px",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h2 style={{ margin: 0, fontSize: "22px", color: "#fff", fontWeight: 700 }}>
              Custom Watchlists
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
              }}
            >
              SQLITE PERSISTENT
            </span>
          </div>
          <p style={{ margin: "6px 0 0", color: "#8c9bb0", fontSize: "13px" }}>
            Create and track multiple portfolios, breakout setups, and high-priority institutional targets.
          </p>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
          {/* Watchlist Tabs */}
          <div style={{ display: "flex", background: "#0a0f18", borderRadius: "8px", padding: "3px", border: "1px solid #1e2c40" }}>
            {watchlists.map((wl) => (
              <button
                key={wl.id}
                onClick={() => handleSelectWatchlist(wl)}
                style={{
                  background: activeWatchlistId === wl.id ? "#2563eb" : "transparent",
                  color: activeWatchlistId === wl.id ? "#fff" : "#94a3b8",
                  border: "none",
                  padding: "6px 14px",
                  borderRadius: "6px",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {wl.name} ({wl.symbol_count})
              </button>
            ))}
          </div>

          <button
            onClick={() => setShowCreateModal(true)}
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
            + New Watchlist
          </button>

          {watchlists.length > 1 && (
            <button
              onClick={handleDeleteWatchlist}
              style={{
                background: "#371b20",
                color: "#ef4444",
                border: "1px solid #4a1d24",
                padding: "7px 12px",
                borderRadius: "8px",
                fontSize: "12px",
                cursor: "pointer",
              }}
            >
              Delete Watchlist
            </button>
          )}
        </div>
      </div>

      {/* Control Bar: Add Stock, Search & Sector filter */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          background: "#0e1622",
          border: "1px solid #1e2c40",
          borderRadius: "10px",
          padding: "14px 18px",
        }}
      >
        <form onSubmit={handleAddSymbol} style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <input
            type="text"
            placeholder="Add NSE Symbol (e.g. INFY)"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value)}
            style={{
              background: "#0a0f18",
              border: "1px solid #1e2c40",
              padding: "8px 12px",
              borderRadius: "6px",
              color: "#fff",
              fontSize: "12px",
              width: "220px",
              textTransform: "uppercase",
            }}
          />
          <button
            type="submit"
            style={{
              background: "#2563eb",
              color: "#fff",
              border: "none",
              padding: "8px 16px",
              borderRadius: "6px",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            + Add Stock
          </button>
        </form>

        <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
          <input
            type="text"
            placeholder="Search watchlist..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              background: "#0a0f18",
              border: "1px solid #1e2c40",
              padding: "8px 12px",
              borderRadius: "6px",
              color: "#fff",
              fontSize: "12px",
              width: "180px",
            }}
          />

          <select
            value={selectedSector}
            onChange={(e) => setSelectedSector(e.target.value)}
            style={{
              background: "#0a0f18",
              border: "1px solid #1e2c40",
              padding: "8px 12px",
              borderRadius: "6px",
              color: "#94a3b8",
              fontSize: "12px",
            }}
          >
            {sectors.map((sec) => (
              <option key={sec} value={sec}>
                {sec}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Main Table */}
      <div
        style={{
          background: "#0e1622",
          border: "1px solid #1e2c40",
          borderRadius: "12px",
          overflow: "hidden",
        }}
      >
        {loading ? (
          <div style={{ padding: "40px", textAlign: "center", color: "#8c9bb0" }}>
            Loading watchlist data...
          </div>
        ) : sortedItems.length === 0 ? (
          <div style={{ padding: "50px", textAlign: "center", color: "#8c9bb0" }}>
            <div style={{ fontSize: "28px", marginBottom: "8px" }}>📝</div>
            <div style={{ fontSize: "15px", color: "#fff", fontWeight: 600 }}>
              This watchlist is empty
            </div>
            <div style={{ fontSize: "12px", marginTop: "4px" }}>
              Add a symbol using the form above or use the "+ Watchlist" button from the Market Scanner.
            </div>
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "13px" }}>
              <thead>
                <tr style={{ background: "#0a0f18", borderBottom: "1px solid #1e2c40", color: "#8c9bb0", fontSize: "11px", textTransform: "uppercase" }}>
                  <th style={{ padding: "12px 16px", cursor: "pointer" }} onClick={() => handleSort("symbol")}>
                    Symbol {sortField === "symbol" ? (sortAsc ? "▲" : "▼") : ""}
                  </th>
                  <th style={{ padding: "12px 14px" }}>Sector</th>
                  <th style={{ padding: "12px 14px", textAlign: "right", cursor: "pointer" }} onClick={() => handleSort("price")}>
                    Price (₹) {sortField === "price" ? (sortAsc ? "▲" : "▼") : ""}
                  </th>
                  <th style={{ padding: "12px 14px", textAlign: "right", cursor: "pointer" }} onClick={() => handleSort("changePercent")}>
                    Daily Change {sortField === "changePercent" ? (sortAsc ? "▲" : "▼") : ""}
                  </th>
                  <th style={{ padding: "12px 14px", textAlign: "right" }}>RSI</th>
                  <th style={{ padding: "12px 14px", textAlign: "right" }}>RVOL</th>
                  <th style={{ padding: "12px 14px", textAlign: "right" }}>52W Range</th>
                  <th style={{ padding: "12px 16px", textAlign: "center" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {sortedItems.map((item) => {
                  const isPos = item.changePercent >= 0;
                  return (
                    <tr
                      key={item.symbol}
                      style={{
                        borderBottom: "1px solid #16202e",
                        transition: "background 0.15s ease",
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "#131d2a")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                    >
                      <td style={{ padding: "12px 16px" }}>
                        <div style={{ fontWeight: 700, color: "#fff", fontSize: "14px" }}>{item.symbol}</div>
                        <div style={{ fontSize: "11px", color: "#64748b" }}>{item.name}</div>
                      </td>
                      <td style={{ padding: "12px 14px", fontSize: "12px", color: "#94a3b8" }}>{item.sector}</td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontWeight: 700, color: "#f8fafc" }}>
                        ₹{item.price.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
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
                          {isPos ? "+" : ""}{item.changePercent.toFixed(2)}%
                        </span>
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontSize: "12px", color: (item.rsi || 50) >= 60 ? "#26c78b" : ((item.rsi || 50) <= 40 ? "#ef6676" : "#cbd5e1") }}>
                        {item.rsi ? item.rsi.toFixed(1) : "—"}
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontSize: "12px", color: (item.relative_volume || 1) >= 1.4 ? "#38bdf8" : "#cbd5e1" }}>
                        {item.relative_volume ? `${item.relative_volume.toFixed(2)}x` : "—"}
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right", fontSize: "11px", color: "#64748b" }}>
                        H: ₹{item.high52.toLocaleString()} | L: ₹{item.low52.toLocaleString()}
                      </td>
                      <td style={{ padding: "12px 16px", textAlign: "center" }}>
                        <div style={{ display: "flex", gap: "6px", justifyContent: "center" }}>
                          <button
                            onClick={() => onSelectSymbol(item.symbol, "chart")}
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
                            onClick={() => handleRemoveSymbol(item.symbol)}
                            style={{
                              background: "#371b20",
                              color: "#ef4444",
                              border: "1px solid #4a1d24",
                              padding: "4px 8px",
                              borderRadius: "4px",
                              fontSize: "11px",
                              cursor: "pointer",
                            }}
                          >
                            ✕
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
      </div>

      {/* Create Watchlist Modal */}
      {showCreateModal && (
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
              width: "420px",
              maxWidth: "90%",
            }}
          >
            <h3 style={{ margin: "0 0 12px", color: "#f8fafc", fontSize: "16px" }}>
              Create New Watchlist
            </h3>
            <form onSubmit={handleCreateWatchlist} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <div>
                <label style={{ fontSize: "12px", color: "#94a3b8" }}>Watchlist Name *</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Breakout Radar"
                  value={newWlName}
                  onChange={(e) => setNewWlName(e.target.value)}
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
                <input
                  type="text"
                  placeholder="e.g. Swing trade candidates"
                  value={newWlDesc}
                  onChange={(e) => setNewWlDesc(e.target.value)}
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

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "12px" }}>
                <button
                  type="button"
                  onClick={() => setShowCreateModal(false)}
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
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

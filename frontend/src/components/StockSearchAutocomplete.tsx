import React, { useState, useEffect, useRef } from "react";
import { apiJson } from "../api/client";

export interface StockSearchResult {
  symbol: string;
  company_name: string;
  short_name?: string;
  isin?: string;
  instrument_key: string;
  is_nifty50?: number;
  is_fno?: number;
  exchange?: string;
}

interface StockSearchAutocompleteProps {
  onSelect: (symbol: string) => void;
  placeholder?: string;
  initialValue?: string;
  className?: string;
  autoFocus?: boolean;
}

export default function StockSearchAutocomplete({
  onSelect,
  placeholder = "Search NSE stocks, indices, F&O...",
  initialValue = "",
  className = "",
  autoFocus = false,
}: StockSearchAutocompleteProps) {
  const [query, setQuery] = useState(initialValue);
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Debounced search
  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    const timer = setTimeout(async () => {
      setIsLoading(true);
      try {
        const res = await apiJson<{ items: StockSearchResult[] }>(
          `/api/stocks/search?q=${encodeURIComponent(query.trim())}&limit=12`
        );
        setResults(res.items || []);
        setIsOpen(true);
        setSelectedIndex(0);
      } catch (err) {
        console.error("Stock search failed:", err);
      } finally {
        setIsLoading(false);
      }
    }, 150);

    return () => clearTimeout(timer);
  }, [query]);

  // Click outside to close
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen || results.length === 0) {
      if (e.key === "Enter" && query.trim()) {
        e.preventDefault();
        onSelect(query.trim().toUpperCase());
        setIsOpen(false);
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % results.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      const chosen = results[selectedIndex];
      if (chosen) {
        onSelect(chosen.symbol);
        setQuery(chosen.symbol);
        setIsOpen(false);
      }
    } else if (e.key === "Escape") {
      setIsOpen(false);
    }
  };

  const selectItem = (stk: StockSearchResult) => {
    onSelect(stk.symbol);
    setQuery(stk.symbol);
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%" }} className={className}>
      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
        <span
          style={{
            position: "absolute",
            left: "12px",
            color: "#64748b",
            fontSize: "14px",
            pointerEvents: "none",
          }}
        >
          ⌕
        </span>
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => {
            if (results.length > 0) setIsOpen(true);
          }}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          autoFocus={autoFocus}
          style={{
            width: "100%",
            padding: "8px 36px 8px 32px",
            background: "#080c14",
            border: "1px solid #1e293b",
            borderRadius: "6px",
            color: "#f8fafc",
            fontSize: "13px",
            outline: "none",
            transition: "border-color 0.15s ease",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#334155")}
          onMouseLeave={(e) => {
            if (document.activeElement !== e.currentTarget) {
              e.currentTarget.style.borderColor = "#1e293b";
            }
          }}
        />
        {isLoading ? (
          <span
            style={{
              position: "absolute",
              right: "12px",
              color: "#64748b",
              fontSize: "11px",
            }}
          >
            ...
          </span>
        ) : query ? (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setResults([]);
              setIsOpen(false);
              inputRef.current?.focus();
            }}
            style={{
              position: "absolute",
              right: "10px",
              background: "transparent",
              border: "none",
              color: "#64748b",
              cursor: "pointer",
              fontSize: "14px",
              padding: "2px 6px",
            }}
          >
            ×
          </button>
        ) : null}
      </div>

      {isOpen && results.length > 0 && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            left: 0,
            right: 0,
            background: "#080c14",
            border: "1px solid #1e293b",
            borderRadius: "8px",
            boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.8)",
            zIndex: 9999,
            maxHeight: "360px",
            overflowY: "auto",
            padding: "4px",
          }}
        >
          {results.map((stk, idx) => {
            const isSelected = idx === selectedIndex;
            return (
              <div
                key={stk.symbol}
                onClick={() => selectItem(stk)}
                onMouseEnter={() => setSelectedIndex(idx)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "8px 12px",
                  borderRadius: "5px",
                  cursor: "pointer",
                  background: isSelected ? "#131c2e" : "transparent",
                  borderLeft: isSelected ? "2px solid #38bdf8" : "2px solid transparent",
                  transition: "background 0.1s ease",
                }}
              >
                <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontWeight: 700, color: "#f8fafc", fontSize: "13px" }}>
                      {stk.symbol}
                    </span>
                    <span
                      style={{
                        fontSize: "9px",
                        padding: "1px 5px",
                        borderRadius: "3px",
                        background: "#1e293b",
                        color: "#94a3b8",
                        fontWeight: 600,
                      }}
                    >
                      {stk.exchange || "NSE"}
                    </span>
                    {stk.is_nifty50 === 1 && (
                      <span
                        style={{
                          fontSize: "9px",
                          padding: "1px 5px",
                          borderRadius: "3px",
                          background: "rgba(16, 185, 129, 0.15)",
                          color: "#34d399",
                          border: "1px solid rgba(16, 185, 129, 0.3)",
                          fontWeight: 600,
                        }}
                      >
                        NIFTY 50
                      </span>
                    )}
                    {stk.is_fno === 1 && (
                      <span
                        style={{
                          fontSize: "9px",
                          padding: "1px 5px",
                          borderRadius: "3px",
                          background: "rgba(168, 85, 247, 0.15)",
                          color: "#c084fc",
                          border: "1px solid rgba(168, 85, 247, 0.3)",
                          fontWeight: 600,
                        }}
                      >
                        F&O
                      </span>
                    )}
                  </div>
                  <span style={{ fontSize: "11px", color: "#64748b" }}>
                    {stk.short_name || stk.company_name}
                  </span>
                </div>

                <div style={{ fontSize: "10px", color: "#475569" }}>
                  {stk.isin ? stk.isin.slice(0, 6) + "..." : ""}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

import React, { useState, useEffect, useRef } from "react";
import {
  PineScriptEngine,
  PineExecutionResult,
  PINE_PRESETS,
  PineInputDef,
} from "../services/pineScriptEngine";
import { CandleBar } from "./TradingViewChart";

interface PineScriptEditorProps {
  bars: CandleBar[];
  onApply: (result: PineExecutionResult | null) => void;
  onClose: () => void;
  isOpen: boolean;
}

const STORAGE_KEY_SCRIPTS = "stock_intelligence_pine_scripts";
const STORAGE_KEY_ACTIVE = "stock_intelligence_active_pine_script";

export default function PineScriptEditor({
  bars,
  onApply,
  onClose,
  isOpen,
}: PineScriptEditorProps) {
  const [selectedPresetId, setSelectedPresetId] = useState<string>("smc_community_pro");
  const [scriptCode, setScriptCode] = useState<string>(() => {
    const saved = localStorage.getItem(STORAGE_KEY_ACTIVE);
    if (saved) return saved;
    return PINE_PRESETS[0].code;
  });

  const [activeTab, setActiveTab] = useState<"code" | "inputs" | "console">("code");
  const [userInputs, setUserInputs] = useState<Record<string, any>>({});
  const [detectedInputs, setDetectedInputs] = useState<Record<string, PineInputDef>>({});
  const [executionResult, setExecutionResult] = useState<PineExecutionResult | null>(null);
  const [isCompiling, setIsCompiling] = useState<boolean>(false);
  const [isMaximized, setIsMaximized] = useState<boolean>(false);
  const [savedScripts, setSavedScripts] = useState<{ id: string; name: string; code: string }[]>([]);
  const [scriptName, setScriptName] = useState<string>("SMC Community Pro");
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load saved scripts from localStorage on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY_SCRIPTS);
      if (raw) {
        setSavedScripts(JSON.parse(raw));
      }
    } catch {
      // ignore
    }
  }, []);

  // Update detected inputs whenever code changes
  useEffect(() => {
    const extracted = PineScriptEngine.extractInputs(scriptCode);
    setDetectedInputs(extracted);
  }, [scriptCode]);

  // Execute and apply script to chart
  const handleCompileAndApply = () => {
    setIsCompiling(true);
    setStatusMessage("Compiling Pine Script...");

    setTimeout(() => {
      const result = PineScriptEngine.execute(scriptCode, bars, userInputs);
      setExecutionResult(result);
      setIsCompiling(false);

      if (result.success) {
        localStorage.setItem(STORAGE_KEY_ACTIVE, scriptCode);
        onApply(result);
        setStatusMessage(
          `✓ Applied "${result.title}" (${result.plots.length} plots, ${result.markers.length} markers, ${result.boxes.length} zones) in ${result.executionTimeMs}ms`
        );
      } else {
        setStatusMessage(`❌ Error: ${result.error}`);
        setActiveTab("console");
      }
    }, 50);
  };

  // Keyboard shortcut Ctrl+Enter or Cmd+Enter to compile
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      handleCompileAndApply();
    }
  };

  // Change preset
  const handleSelectPreset = (presetId: string) => {
    const preset = PINE_PRESETS.find((p) => p.id === presetId);
    if (preset) {
      setSelectedPresetId(preset.id);
      setScriptCode(preset.code);
      setScriptName(preset.name);
      setUserInputs({});
      setStatusMessage(`Loaded preset "${preset.name}"`);
    }
  };

  // Save current script to custom library
  const handleSaveScript = () => {
    const name = prompt("Enter a name for this custom Pine Script:", scriptName || "My Indicator");
    if (!name) return;

    const id = "custom_" + Date.now();
    const updated = [...savedScripts, { id, name, code: scriptCode }];
    setSavedScripts(updated);
    localStorage.setItem(STORAGE_KEY_SCRIPTS, JSON.stringify(updated));
    setScriptName(name);
    setStatusMessage(`Saved "${name}" to your Custom Scripts library.`);
  };

  // Load custom script
  const handleLoadCustomScript = (id: string) => {
    const found = savedScripts.find((s) => s.id === id);
    if (found) {
      setScriptCode(found.code);
      setScriptName(found.name);
      setUserInputs({});
      setStatusMessage(`Loaded custom script "${found.name}"`);
    }
  };

  // Export script to .pine file
  const handleExportFile = () => {
    const blob = new Blob([scriptCode], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${(scriptName || "indicator").toLowerCase().replace(/[^a-z0-9]/g, "_")}.pine`;
    link.click();
    URL.revokeObjectURL(url);
  };

  // Import script from .pine file
  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      if (content) {
        setScriptCode(content);
        setScriptName(file.name.replace(/\.pine$/, ""));
        setUserInputs({});
        setStatusMessage(`Imported "${file.name}" (${(content.length / 1024).toFixed(1)} KB).`);
      }
    };
    reader.readAsText(file);
    e.target.value = "";
  };

  // Remove indicator from chart
  const handleRemoveFromChart = () => {
    onApply(null);
    setExecutionResult(null);
    setStatusMessage("Indicator removed from chart.");
  };

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: isMaximized ? "fixed" : "relative",
        inset: isMaximized ? 0 : "auto",
        zIndex: isMaximized ? 9999 : 20,
        background: "#080d16",
        borderTop: "2px solid #1e2c40",
        display: "flex",
        flexDirection: "column",
        height: isMaximized ? "100vh" : "360px",
        boxShadow: "0 -8px 24px rgba(0,0,0,0.5)",
        fontFamily: "inherit",
      }}
    >
      {/* Hidden File Input for .pine import */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleImportFile}
        accept=".pine,.txt"
        style={{ display: "none" }}
      />

      {/* Header Toolbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "6px 14px",
          background: "#0c1422",
          borderBottom: "1px solid #1e2c40",
          flexWrap: "wrap",
          gap: "8px",
        }}
      >
        {/* Left: Brand & Presets */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <span style={{ fontSize: "14px" }}>🌲</span>
            <span style={{ fontSize: "12px", fontWeight: 700, color: "#f8fafc", letterSpacing: "0.5px" }}>
              PINE SCRIPT EDITOR
            </span>
          </div>

          {/* Preset Selector */}
          <select
            value={selectedPresetId}
            onChange={(e) => handleSelectPreset(e.target.value)}
            style={{
              background: "#162235",
              color: "#e2e8f0",
              border: "1px solid #28394e",
              borderRadius: "4px",
              padding: "3px 8px",
              fontSize: "11px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <optgroup label="Official Presets">
              {PINE_PRESETS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </optgroup>
            {savedScripts.length > 0 && (
              <optgroup label="My Saved Scripts">
                {savedScripts.map((s) => (
                  <option key={s.id} value={s.id}>
                    ⭐ {s.name}
                  </option>
                ))}
              </optgroup>
            )}
          </select>

          {/* Load specific saved script if selected from optgroup */}
          {savedScripts.some((s) => s.id === selectedPresetId) && (
            <button
              onClick={() => handleLoadCustomScript(selectedPresetId)}
              style={{
                background: "#2563eb",
                color: "#fff",
                border: "none",
                borderRadius: "3px",
                padding: "2px 6px",
                fontSize: "10px",
                cursor: "pointer",
              }}
            >
              Load
            </button>
          )}
        </div>

        {/* Center: Tabs */}
        <div style={{ display: "flex", gap: "2px", background: "#080d16", padding: "2px", borderRadius: "5px" }}>
          <button
            onClick={() => setActiveTab("code")}
            style={{
              background: activeTab === "code" ? "#1e2c40" : "transparent",
              color: activeTab === "code" ? "#60a5fa" : "#8c9bb0",
              border: "none",
              padding: "4px 10px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Code
          </button>
          <button
            onClick={() => setActiveTab("inputs")}
            style={{
              background: activeTab === "inputs" ? "#1e2c40" : "transparent",
              color: activeTab === "inputs" ? "#60a5fa" : "#8c9bb0",
              border: "none",
              padding: "4px 10px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "4px",
            }}
          >
            <span>Inputs</span>
            {Object.keys(detectedInputs).length > 0 && (
              <span
                style={{
                  background: "#2563eb",
                  color: "#fff",
                  padding: "1px 5px",
                  borderRadius: "10px",
                  fontSize: "9px",
                }}
              >
                {Object.keys(detectedInputs).length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab("console")}
            style={{
              background: activeTab === "console" ? "#1e2c40" : "transparent",
              color: activeTab === "console" ? "#60a5fa" : "#8c9bb0",
              border: "none",
              padding: "4px 10px",
              borderRadius: "4px",
              fontSize: "11px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Console
          </button>
        </div>

        {/* Right: Actions */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          {/* Apply / Update Button */}
          <button
            onClick={handleCompileAndApply}
            disabled={isCompiling}
            style={{
              background: isCompiling ? "#475569" : "#10b981",
              color: "#ffffff",
              border: "none",
              borderRadius: "4px",
              padding: "5px 12px",
              fontSize: "11px",
              fontWeight: 700,
              cursor: isCompiling ? "wait" : "pointer",
              display: "flex",
              alignItems: "center",
              gap: "5px",
              boxShadow: "0 2px 8px rgba(16, 185, 129, 0.3)",
            }}
            title="Execute script and apply directly to chart (Ctrl+Enter)"
          >
            <span>{isCompiling ? "⏳" : "▶"}</span>
            <span>{executionResult ? "Update on Chart" : "Add to Chart"}</span>
          </button>

          {/* Remove from chart if active */}
          {executionResult && (
            <button
              onClick={handleRemoveFromChart}
              style={{
                background: "#1e2c40",
                color: "#f87171",
                border: "1px solid #334155",
                borderRadius: "4px",
                padding: "4px 8px",
                fontSize: "11px",
                fontWeight: 600,
                cursor: "pointer",
              }}
              title="Remove this indicator from chart"
            >
              Clear
            </button>
          )}

          {/* Save Script */}
          <button
            onClick={handleSaveScript}
            style={{
              background: "#162235",
              color: "#cbd5e1",
              border: "1px solid #28394e",
              borderRadius: "4px",
              padding: "4px 8px",
              fontSize: "11px",
              cursor: "pointer",
            }}
            title="Save custom script"
          >
            💾 Save
          </button>

          {/* Import .pine */}
          <button
            onClick={() => fileInputRef.current?.click()}
            style={{
              background: "#162235",
              color: "#cbd5e1",
              border: "1px solid #28394e",
              borderRadius: "4px",
              padding: "4px 8px",
              fontSize: "11px",
              cursor: "pointer",
            }}
            title="Import a .pine script from your computer"
          >
            ⬆️ Import
          </button>

          {/* Export .pine */}
          <button
            onClick={handleExportFile}
            style={{
              background: "#162235",
              color: "#cbd5e1",
              border: "1px solid #28394e",
              borderRadius: "4px",
              padding: "4px 8px",
              fontSize: "11px",
              cursor: "pointer",
            }}
            title="Download script as .pine file"
          >
            ⬇️ Export
          </button>

          {/* Maximize / Dock Toggle */}
          <button
            onClick={() => setIsMaximized(!isMaximized)}
            style={{
              background: "#162235",
              color: "#8c9bb0",
              border: "1px solid #28394e",
              borderRadius: "4px",
              padding: "4px 8px",
              fontSize: "11px",
              cursor: "pointer",
            }}
            title={isMaximized ? "Restore view" : "Maximize editor"}
          >
            {isMaximized ? "🗗" : "⛶"}
          </button>

          {/* Close Panel */}
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              color: "#8c9bb0",
              border: "none",
              padding: "4px 8px",
              fontSize: "14px",
              cursor: "pointer",
            }}
            title="Close Pine Editor"
          >
            ✕
          </button>
        </div>
      </div>

      {/* Status Bar */}
      {statusMessage && (
        <div
          style={{
            padding: "4px 14px",
            background: statusMessage.startsWith("❌") ? "#3f1218" : "#0d1b2a",
            color: statusMessage.startsWith("❌") ? "#fca5a5" : "#93c5fd",
            fontSize: "11px",
            borderBottom: "1px solid #1e2c40",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <span>{statusMessage}</span>
          <span style={{ color: "#64748b", fontSize: "10px" }}>Press Ctrl+Enter to Run</span>
        </div>
      )}

      {/* Editor Body */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden", position: "relative" }}>
        {/* Tab 1: Code Editor */}
        {activeTab === "code" && (
          <div style={{ flex: 1, display: "flex", height: "100%", background: "#0a0f18" }}>
            <textarea
              value={scriptCode}
              onChange={(e) => setScriptCode(e.target.value)}
              onKeyDown={handleKeyDown}
              spellCheck={false}
              style={{
                flex: 1,
                height: "100%",
                background: "transparent",
                color: "#e2e8f0",
                fontFamily: "'JetBrains Mono', 'Fira Code', 'Consolas', 'Courier New', monospace",
                fontSize: "12px",
                lineHeight: "1.6",
                padding: "12px 16px",
                border: "none",
                outline: "none",
                resize: "none",
                whiteSpace: "pre",
                overflowY: "auto",
              }}
              placeholder="// Write or paste Pine Script code here..."
            />
          </div>
        )}

        {/* Tab 2: Inputs Inspector */}
        {activeTab === "inputs" && (
          <div
            style={{
              flex: 1,
              padding: "16px 20px",
              overflowY: "auto",
              background: "#0a0f18",
              display: "flex",
              flexDirection: "column",
              gap: "12px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong style={{ color: "#f8fafc", fontSize: "13px" }}>Indicator Input Parameters</strong>
              <button
                onClick={handleCompileAndApply}
                style={{
                  background: "#2563eb",
                  color: "#fff",
                  border: "none",
                  padding: "4px 10px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Apply Parameters
              </button>
            </div>

            {Object.keys(detectedInputs).length === 0 ? (
              <div style={{ color: "#64748b", fontSize: "12px", marginTop: "12px" }}>
                No input definitions (input.int, input.float, input.bool) detected in this script.
              </div>
            ) : (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
                  gap: "12px",
                  marginTop: "8px",
                }}
              >
                {Object.values(detectedInputs).map((inp) => {
                  const curVal = userInputs[inp.id] !== undefined ? userInputs[inp.id] : inp.value;

                  return (
                    <div
                      key={inp.id}
                      style={{
                        background: "#111827",
                        border: "1px solid #1f2937",
                        borderRadius: "6px",
                        padding: "10px 12px",
                        display: "flex",
                        flexDirection: "column",
                        gap: "6px",
                      }}
                    >
                      <label style={{ fontSize: "11px", fontWeight: 600, color: "#94a3b8" }}>
                        {inp.name} ({inp.id})
                      </label>

                      {inp.type === "bool" ? (
                        <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
                          <input
                            type="checkbox"
                            checked={Boolean(curVal)}
                            onChange={(e) => setUserInputs({ ...userInputs, [inp.id]: e.target.checked })}
                          />
                          <span style={{ fontSize: "11px", color: "#e2e8f0" }}>{curVal ? "Enabled" : "Disabled"}</span>
                        </label>
                      ) : inp.type === "int" || inp.type === "float" ? (
                        <input
                          type="number"
                          step={inp.type === "float" ? "0.1" : "1"}
                          value={curVal}
                          onChange={(e) => setUserInputs({ ...userInputs, [inp.id]: Number(e.target.value) })}
                          style={{
                            background: "#1f2937",
                            color: "#fff",
                            border: "1px solid #374151",
                            borderRadius: "4px",
                            padding: "4px 8px",
                            fontSize: "11px",
                          }}
                        />
                      ) : (
                        <input
                          type="text"
                          value={curVal}
                          onChange={(e) => setUserInputs({ ...userInputs, [inp.id]: e.target.value })}
                          style={{
                            background: "#1f2937",
                            color: "#fff",
                            border: "1px solid #374151",
                            borderRadius: "4px",
                            padding: "4px 8px",
                            fontSize: "11px",
                          }}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Tab 3: Execution Console */}
        {activeTab === "console" && (
          <div
            style={{
              flex: 1,
              padding: "14px 18px",
              background: "#06090e",
              overflowY: "auto",
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: "11px",
              color: "#cbd5e1",
              display: "flex",
              flexDirection: "column",
              gap: "4px",
            }}
          >
            <div style={{ color: "#64748b", borderBottom: "1px solid #1e2c40", paddingBottom: "6px" }}>
              --- Pine Script Compilation & Runtime Log ---
            </div>
            {executionResult?.logs && executionResult.logs.length > 0 ? (
              executionResult.logs.map((log, idx) => (
                <div
                  key={idx}
                  style={{
                    color: log.includes("failed") || log.includes("Error") ? "#ef4444" : "#94a3b8",
                  }}
                >
                  [{new Date().toLocaleTimeString()}] {log}
                </div>
              ))
            ) : (
              <div style={{ color: "#64748b" }}>No execution logs yet. Click "Add to Chart" or press Ctrl+Enter.</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

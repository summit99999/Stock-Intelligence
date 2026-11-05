import React, { useState } from "react";
import { importScreenerCsv } from "../api/fundamentals";
import type { ScreenerCsvImportResponse } from "../types/fundamentals";

interface CsvImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultSymbol?: string;
  onImportSuccess?: (res: ScreenerCsvImportResponse) => void;
}

export default function CsvImportModal({
  isOpen,
  onClose,
  defaultSymbol = "",
  onImportSuccess,
}: CsvImportModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [overwriteVerified, setOverwriteVerified] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [activeTab, setActiveTab] = useState<"file" | "paste">("file");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<ScreenerCsvImportResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
      setError(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      let res: ScreenerCsvImportResponse;
      if (activeTab === "file") {
        if (!file) {
          setError("Please select a CSV file to upload.");
          setLoading(false);
          return;
        }
        res = await importScreenerCsv(file, symbol || undefined, overwriteVerified);
      } else {
        if (!pasteText.trim()) {
          setError("Please paste CSV content.");
          setLoading(false);
          return;
        }
        res = await importScreenerCsv(pasteText, symbol || undefined, overwriteVerified);
      }

      setResult(res);
      if (res.status === "ok" && onImportSuccess) {
        onImportSuccess(res);
      }
    } catch (err: any) {
      setError(err?.message || "Failed to import CSV");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
      <div className="bg-[#121620] border border-gray-800 rounded-xl w-full max-w-lg overflow-hidden shadow-2xl animate-fade-in text-gray-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-800 bg-[#161c28]">
          <div className="flex items-center gap-2">
            <span className="text-emerald-400 text-lg">📥</span>
            <h3 className="font-semibold text-lg text-white">Import Screener.in CSV</h3>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors text-xl leading-none"
          >
            &times;
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Format selection */}
          <div className="flex border-b border-gray-800 pb-2 gap-4">
            <button
              type="button"
              className={`text-sm font-medium pb-2 border-b-2 transition-colors ${
                activeTab === "file"
                  ? "border-emerald-500 text-emerald-400"
                  : "border-transparent text-gray-400 hover:text-gray-200"
              }`}
              onClick={() => setActiveTab("file")}
            >
              Upload CSV File
            </button>
            <button
              type="button"
              className={`text-sm font-medium pb-2 border-b-2 transition-colors ${
                activeTab === "paste"
                  ? "border-emerald-500 text-emerald-400"
                  : "border-transparent text-gray-400 hover:text-gray-200"
              }`}
              onClick={() => setActiveTab("paste")}
            >
              Paste CSV Text
            </button>
          </div>

          {activeTab === "file" ? (
            <div className="border-2 border-dashed border-gray-700 rounded-lg p-6 text-center hover:border-emerald-500/60 transition-colors bg-[#0f131c]">
              <input
                type="file"
                accept=".csv,text/csv"
                onChange={handleFileChange}
                className="hidden"
                id="screener-csv-file"
              />
              <label htmlFor="screener-csv-file" className="cursor-pointer block">
                <div className="text-3xl mb-2">📄</div>
                <div className="text-sm font-medium text-gray-300">
                  {file ? file.name : "Click to select or drag & drop Screener.in CSV"}
                </div>
                <div className="text-xs text-gray-500 mt-1">
                  Supports exported watchlist queries or multi-year company financial sheets
                </div>
              </label>
            </div>
          ) : (
            <div>
              <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
                CSV Content
              </label>
              <textarea
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                placeholder="Report Date,Mar 2023,Mar 2024&#10;Sales,225458,240893&#10;Expenses,167448,178000..."
                rows={6}
                className="w-full bg-[#0d1017] border border-gray-800 rounded-lg p-3 text-xs font-mono text-gray-300 focus:outline-none focus:border-emerald-500"
              />
            </div>
          )}

          {/* Optional Symbol */}
          <div>
            <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">
              Company Symbol (Optional for multi-company screen, required for statement sheet)
            </label>
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="e.g. TCS, RELIANCE, INFY"
              className="w-full bg-[#0d1017] border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-emerald-500"
            />
          </div>

          {/* Overwrite Protection */}
          <div className="flex items-start gap-3 p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
            <input
              type="checkbox"
              id="overwrite-verified"
              checked={overwriteVerified}
              onChange={(e) => setOverwriteVerified(e.target.checked)}
              className="mt-1 accent-amber-500 cursor-pointer"
            />
            <label htmlFor="overwrite-verified" className="text-xs text-amber-200/90 cursor-pointer">
              <span className="font-semibold block text-amber-300">Overwrite Verified Data</span>
              When unchecked, existing verified records from official feeds will be protected and preserved. Check only if you wish to override verified statements.
            </label>
          </div>

          {/* Error display */}
          {error && (
            <div className="p-3 bg-rose-500/15 border border-rose-500/30 rounded-lg text-rose-300 text-xs">
              {error}
            </div>
          )}

          {/* Result summary */}
          {result && (
            <div className={`p-4 rounded-lg text-xs space-y-1 ${
              result.status === "ok" ? "bg-emerald-500/15 border border-emerald-500/30 text-emerald-300" : "bg-amber-500/15 border border-amber-500/30 text-amber-300"
            }`}>
              <div className="font-semibold text-sm">
                {result.status === "ok" ? "✓ Import Completed" : "Import Notice"}
              </div>
              <div>Records imported: <span className="font-bold">{result.rows_imported}</span></div>
              {result.rows_skipped > 0 && (
                <div>Records skipped: <span className="font-bold">{result.rows_skipped}</span> (protected or unmapped)</div>
              )}
              {result.warnings.length > 0 && (
                <div className="mt-2 text-[11px] text-amber-300/80">
                  {result.warnings.slice(0, 3).map((w, idx) => (
                    <div key={idx}>• {w}</div>
                  ))}
                  {result.warnings.length > 3 && <div>• +{result.warnings.length - 3} more warnings</div>}
                </div>
              )}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm text-gray-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="px-5 py-2 rounded-lg text-sm font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors disabled:opacity-50 flex items-center gap-2 shadow-lg shadow-emerald-900/30"
            >
              {loading ? (
                <>
                  <span className="animate-spin text-sm">⟳</span> Importing...
                </>
              ) : (
                "Import Data"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

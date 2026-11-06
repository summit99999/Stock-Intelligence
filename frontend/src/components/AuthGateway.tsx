import React, { useState } from "react";
import { signInWithEmail } from "../api/supabaseClient";

interface AuthGatewayProps {
  onSuccess?: () => void;
}

export default function AuthGateway({ onSuccess }: AuthGatewayProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      setErrorMsg("Please enter both email and password.");
      return;
    }

    setLoading(true);
    setErrorMsg(null);

    try {
      const { data, error } = await signInWithEmail(email.trim(), password);
      if (error) {
        setErrorMsg(error.message || "Invalid authentication credentials.");
      } else if (data.session) {
        if (onSuccess) onSuccess();
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to authenticate with Supabase.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
        background: "#080c14",
        padding: "20px",
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "420px",
          background: "linear-gradient(180deg, #131c2a 0%, #0d1420 100%)",
          border: "1px solid #1e2c40",
          borderRadius: "14px",
          padding: "32px",
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.7)",
        }}
      >
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: "28px" }}>
          <div
            style={{
              width: "48px",
              height: "48px",
              borderRadius: "12px",
              background: "linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto 16px auto",
              fontSize: "24px",
              boxShadow: "0 0 20px rgba(37, 99, 235, 0.4)",
            }}
          >
            📈
          </div>
          <h2 style={{ margin: 0, fontSize: "20px", fontWeight: 700, color: "#fff", letterSpacing: "0.5px" }}>
            STOCK INTELLIGENCE PRO
          </h2>
          <p style={{ margin: "8px 0 0 0", color: "#8c9bb0", fontSize: "13px" }}>
            Private Quantitative Research & Trading Intelligence
          </p>
          <div
            style={{
              display: "inline-block",
              marginTop: "10px",
              padding: "3px 10px",
              borderRadius: "20px",
              fontSize: "11px",
              fontWeight: 600,
              background: "rgba(59, 130, 246, 0.15)",
              color: "#60a5fa",
              border: "1px solid rgba(59, 130, 246, 0.3)",
            }}
          >
            🔒 AUTHORIZED PRIVATE ACCESS ONLY
          </div>
        </div>

        {errorMsg && (
          <div
            style={{
              padding: "12px 14px",
              background: "rgba(239, 68, 68, 0.15)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "8px",
              color: "#fca5a5",
              fontSize: "13px",
              marginBottom: "20px",
              lineHeight: "1.4",
            }}
          >
            ⚠️ {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "#cbd5e1", marginBottom: "6px" }}>
              Email Address
            </label>
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="operator@stockintelligence.pro"
              disabled={loading}
              style={{
                width: "100%",
                background: "#0a0f18",
                border: "1px solid #2d3f58",
                borderRadius: "8px",
                padding: "10px 14px",
                color: "#fff",
                fontSize: "14px",
                outline: "none",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "#cbd5e1", marginBottom: "6px" }}>
              Private Master Password
            </label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••••••"
              disabled={loading}
              style={{
                width: "100%",
                background: "#0a0f18",
                border: "1px solid #2d3f58",
                borderRadius: "8px",
                padding: "10px 14px",
                color: "#fff",
                fontSize: "14px",
                outline: "none",
                boxSizing: "border-box",
              }}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              marginTop: "8px",
              background: loading ? "#1e293b" : "#2563eb",
              color: "#fff",
              border: "none",
              borderRadius: "8px",
              padding: "12px",
              fontSize: "14px",
              fontWeight: 700,
              cursor: loading ? "not-allowed" : "pointer",
              transition: "background 0.2s",
              boxShadow: "0 4px 12px rgba(37, 99, 235, 0.3)",
            }}
          >
            {loading ? "Authenticating Session..." : "Enter Workspace →"}
          </button>
        </form>

        <div style={{ marginTop: "24px", textAlign: "center", borderTop: "1px solid #1a2636", paddingTop: "16px" }}>
          <span style={{ fontSize: "11px", color: "#64748b" }}>
            Secured by Supabase Auth with Row-Level Security (RLS)
          </span>
        </div>
      </div>
    </div>
  );
}

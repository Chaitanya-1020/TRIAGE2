"use client";

import { useState } from "react";
import Navbar from "@/components/layout/Navbar";
import { escalateCase } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import type { User, RiskAssessmentResponse, EscalationResponse, WSMessage } from "@/types";
import type { View } from "@/app/page";

interface ResultsPageProps {
    user: User;
    assessment: RiskAssessmentResponse;
    escalation: EscalationResponse | null;
    onLogout: () => void;
    onBack: () => void;
    onEscalationComplete: (e: EscalationResponse) => void;
    onNewIntake: () => void;
    navigateTo: (view: View) => void;
}

const RISK_CONFIG = {
    critical: {
        color: "var(--critical)",
        glow: "var(--critical-glow)",
        bg: "var(--critical-bg)",
        gradient: "var(--gradient-critical)",
        icon: "🔴",
        label: "CRITICAL",
        borderColor: "rgba(239,68,68,0.4)",
        animation: "blink-red 1.5s ease-in-out infinite",
    },
    high: {
        color: "var(--high)",
        glow: "var(--high-glow)",
        bg: "var(--high-bg)",
        gradient: "var(--gradient-high)",
        icon: "🟠",
        label: "HIGH",
        borderColor: "rgba(249,115,22,0.4)",
        animation: "none",
    },
    moderate: {
        color: "var(--moderate)",
        glow: "var(--moderate-glow)",
        bg: "var(--moderate-bg)",
        gradient: "var(--gradient-moderate)",
        icon: "🟡",
        label: "MODERATE",
        borderColor: "rgba(234,179,8,0.4)",
        animation: "none",
    },
    low: {
        color: "var(--low)",
        glow: "var(--low-glow)",
        bg: "var(--low-bg)",
        gradient: "var(--gradient-low)",
        icon: "🟢",
        label: "LOW",
        borderColor: "rgba(34,197,94,0.4)",
        animation: "none",
    },
};

export default function ResultsPage({
    user,
    assessment,
    escalation,
    onLogout,
    onBack,
    onEscalationComplete,
    onNewIntake,
    navigateTo,
}: ResultsPageProps) {
    const [escalating, setEscalating] = useState(false);
    const [escalationReason, setEscalationReason] = useState(
        assessment.recommendation.slice(0, 200)
    );
    const [showEscalateModal, setShowEscalateModal] = useState(false);
    const [wsMessages, setWsMessages] = useState<WSMessage[]>([]);

    const cfg = RISK_CONFIG[assessment.final_risk_level];

    // WebSocket connection to case room
    useWebSocket({
        caseId: assessment.case_id,
        enabled: !escalation, // only before escalation is complete
        onMessage: (msg) => {
            setWsMessages((prev) => [msg, ...prev].slice(0, 10));
        },
    });

    const handleEscalate = async () => {
        setEscalating(true);
        try {
            const result = await escalateCase(assessment.case_id, escalationReason);
            onEscalationComplete(result);
            setShowEscalateModal(false);
        } catch {
            // Demo fallback
            const demoResult: EscalationResponse = {
                case_id: assessment.case_id,
                specialist_magic_link: `${window.location.origin}/?token=demo-specialist-token-${Date.now()}`,
                sbar: {
                    situation: `Patient with ${assessment.final_risk_level.toUpperCase()} risk. Risk score: ${(assessment.final_risk_score * 100).toFixed(0)}%.`,
                    background: `Assessment ID: ${assessment.assessment_id}. Evaluated by PHW ${user.full_name}.`,
                    assessment: `AI classified ${assessment.final_risk_level.toUpperCase()} (score ${assessment.final_risk_score.toFixed(3)}). ${assessment.rule_engine.triggered ? "Rule engine triggered: " + assessment.rule_engine.reasons.join("; ") : "ML-driven assessment."}`,
                    recommendation: assessment.recommendation,
                },
                escalated_at: new Date().toISOString(),
            };
            onEscalationComplete(demoResult);
            setShowEscalateModal(false);
        } finally {
            setEscalating(false);
        }
    };

    const maxShap = Math.max(...(assessment.ml_result?.shap_features.map((f) => Math.abs(f.shap_value)) ?? [1]));

    return (
        <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
            <Navbar user={user} currentView="results" onLogout={onLogout} navigateTo={navigateTo} />

            <div
                style={{
                    maxWidth: 1100,
                    margin: "0 auto",
                    padding: "32px 24px",
                    animation: "fadeIn 0.4s ease forwards",
                }}
            >
                {/* Header */}
                <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 28 }}>
                    <button className="btn btn-ghost btn-sm" onClick={onBack}>← Dashboard</button>
                    <div>
                        <h2 style={{ marginBottom: 2 }}>Risk Assessment Results</h2>
                        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontFamily: "JetBrains Mono, monospace" }}>
                            {assessment.assessment_id}
                        </p>
                    </div>
                    <div style={{ marginLeft: "auto", display: "flex", gap: 10 }}>
                        <button className="btn btn-ghost btn-sm" onClick={onNewIntake} id="new-intake-btn">
                            + New Patient
                        </button>
                    </div>
                </div>

                {/* Escalation success banner */}
                {escalation && (
                    <div
                        className="alert alert-low"
                        style={{ marginBottom: 24, animation: "slideInLeft 0.4s ease forwards" }}
                    >
                        <span style={{ fontSize: "1.2rem" }}>✅</span>
                        <div>
                            <div style={{ fontWeight: 700 }}>Case Escalated Successfully</div>
                            <div style={{ fontSize: "0.82rem", marginTop: 4 }}>
                                Specialist magic link:{" "}
                                <a
                                    href={escalation.specialist_magic_link}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    style={{ color: "var(--accent-blue)", fontFamily: "monospace", wordBreak: "break-all" }}
                                >
                                    {escalation.specialist_magic_link}
                                </a>
                            </div>
                        </div>
                    </div>
                )}

                {/* WS live messages */}
                {wsMessages.length > 0 && (
                    <div className="card" style={{ marginBottom: 20, padding: 16 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                            <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--low)", boxShadow: "0 0 8px var(--low)", animation: "pulse 2s infinite" }} />
                            <span style={{ fontSize: "0.8rem", fontWeight: 600, color: "var(--low)" }}>Live Updates</span>
                        </div>
                        {wsMessages.map((m, i) => (
                            <div key={i} style={{ fontSize: "0.8rem", color: "var(--text-secondary)", fontFamily: "monospace", padding: "3px 0" }}>
                                [{new Date().toLocaleTimeString()}] {m.type}: {JSON.stringify(m).slice(0, 120)}
                            </div>
                        ))}
                    </div>
                )}

                <div className="grid" style={{ gridTemplateColumns: "1fr 2fr", gap: 20, alignItems: "start" }}>
                    {/* Left column */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                        {/* Risk Level Hero */}
                        <div
                            className="card"
                            style={{
                                padding: 28,
                                textAlign: "center",
                                borderColor: cfg.borderColor,
                                boxShadow: `0 0 30px ${cfg.glow}, var(--shadow-card)`,
                                animation: cfg.animation,
                            }}
                        >
                            <div style={{ fontSize: "3.5rem", marginBottom: 8 }}>{cfg.icon}</div>
                            <div
                                style={{
                                    fontSize: "1.8rem",
                                    fontWeight: 900,
                                    color: cfg.color,
                                    letterSpacing: "0.05em",
                                    marginBottom: 4,
                                }}
                            >
                                {cfg.label}
                            </div>
                            <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: 16 }}>
                                Risk Level
                            </div>

                            {/* Risk score bar */}
                            <div style={{ marginBottom: 16 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Risk Score</span>
                                    <span style={{ fontSize: "0.85rem", fontWeight: 800, fontFamily: "monospace", color: cfg.color }}>
                                        {(assessment.final_risk_score * 100).toFixed(1)}%
                                    </span>
                                </div>
                                <div className="progress-bar">
                                    <div
                                        className="progress-fill"
                                        style={{
                                            width: `${assessment.final_risk_score * 100}%`,
                                            background: cfg.gradient,
                                            boxShadow: `0 0 8px ${cfg.glow}`,
                                        }}
                                    />
                                </div>
                            </div>

                            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                    Assessed: {new Date(assessment.assessed_at).toLocaleTimeString()}
                                </div>
                                {assessment.escalation_suggested && !escalation && (
                                    <button
                                        id="escalate-btn"
                                        className="btn btn-danger btn-full"
                                        onClick={() => setShowEscalateModal(true)}
                                    >
                                        📡 Escalate to Specialist
                                    </button>
                                )}
                                {escalation && (
                                    <div
                                        style={{
                                            padding: "8px",
                                            background: "var(--low-bg)",
                                            borderRadius: "var(--radius-md)",
                                            fontSize: "0.8rem",
                                            color: "var(--low)",
                                        }}
                                    >
                                        ✅ Escalated
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Rule Engine */}
                        <div className="card" style={{ padding: 20 }}>
                            <h4 style={{ marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
                                <span>⚙️</span> Rule Engine
                                {assessment.rule_engine.triggered && (
                                    <span className="badge badge-critical">Triggered</span>
                                )}
                            </h4>
                            {assessment.rule_engine.triggered ? (
                                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                    {assessment.rule_engine.reasons.map((r, i) => (
                                        <div
                                            key={i}
                                            style={{
                                                fontSize: "0.82rem",
                                                color: "var(--critical)",
                                                padding: "8px 12px",
                                                background: "var(--critical-bg)",
                                                borderRadius: "var(--radius-sm)",
                                                borderLeft: "3px solid var(--critical)",
                                            }}
                                        >
                                            ⚠️ {r}
                                        </div>
                                    ))}
                                    {assessment.rule_engine.override_ml && (
                                        <span className="badge badge-critical" style={{ width: "fit-content" }}>
                                            Overrides ML Output
                                        </span>
                                    )}
                                </div>
                            ) : (
                                <div style={{ fontSize: "0.85rem", color: "var(--low)", display: "flex", gap: 8, alignItems: "center" }}>
                                    <span>✅</span>
                                    <span>No critical thresholds exceeded</span>
                                </div>
                            )}
                        </div>

                        {/* Medication Warnings */}
                        {assessment.med_warnings.length > 0 && (
                            <div className="card" style={{ padding: 20 }}>
                                <h4 style={{ marginBottom: 14, display: "flex", alignItems: "center", gap: 8 }}>
                                    <span>💊</span> Medication Alerts
                                    <span className="badge badge-high">{assessment.med_warnings.length}</span>
                                </h4>
                                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                                    {assessment.med_warnings.map((w, i) => (
                                        <div
                                            key={i}
                                            className={`alert alert-${w.severity === "contraindicated" || w.severity === "severe" ? "critical" : w.severity === "moderate" ? "high" : "moderate"}`}
                                            style={{ fontSize: "0.82rem" }}
                                        >
                                            <span>💊</span>
                                            <div>
                                                <strong>{w.drug1}{w.drug2 ? ` + ${w.drug2}` : ""}</strong>
                                                <div style={{ marginTop: 3 }}>{w.message}</div>
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Right column */}
                    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                        {/* Recommendation */}
                        <div
                            className="card"
                            style={{
                                padding: 24,
                                borderLeft: `4px solid ${cfg.color}`,
                            }}
                        >
                            <h4 style={{ marginBottom: 14, color: "var(--text-secondary)" }}>
                                🩺 Clinical Recommendation
                            </h4>
                            <p style={{ color: "var(--text-primary)", fontSize: "0.95rem", lineHeight: 1.7, fontWeight: 500 }}>
                                {assessment.recommendation}
                            </p>
                        </div>

                        {/* SHAP Feature Explanations */}
                        {assessment.ml_result && (
                            <div className="card" style={{ padding: 24 }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", marginBottom: 20 }}>
                                    <div>
                                        <h4 style={{ marginBottom: 4 }}>🤖 AI Explanation (SHAP)</h4>
                                        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                                            Top 5 features driving this assessment
                                        </p>
                                    </div>
                                    <div style={{ textAlign: "right" }}>
                                        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>ML Score</div>
                                        <div
                                            style={{
                                                fontSize: "1.3rem",
                                                fontWeight: 800,
                                                fontFamily: "monospace",
                                                color: cfg.color,
                                            }}
                                        >
                                            {(assessment.ml_result.risk_probability * 100).toFixed(1)}%
                                        </div>
                                    </div>
                                </div>

                                <p
                                    style={{
                                        fontSize: "0.875rem",
                                        color: "var(--text-secondary)",
                                        marginBottom: 20,
                                        padding: "12px 16px",
                                        background: "var(--bg-secondary)",
                                        borderRadius: "var(--radius-md)",
                                        lineHeight: 1.6,
                                        fontStyle: "italic",
                                    }}
                                >
                                    &ldquo;{assessment.ml_result.shap_text}&rdquo;
                                </p>

                                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                                    {assessment.ml_result.shap_features.map((feat, i) => {
                                        const pct = (Math.abs(feat.shap_value) / maxShap) * 100;
                                        return (
                                            <div key={i}>
                                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                                                    <span style={{ fontSize: "0.85rem", fontWeight: 500, color: "var(--text-primary)" }}>
                                                        {feat.label}
                                                    </span>
                                                    <span
                                                        style={{
                                                            fontSize: "0.75rem",
                                                            fontFamily: "monospace",
                                                            color: feat.shap_value > 0.2 ? cfg.color : "var(--text-muted)",
                                                        }}
                                                    >
                                                        {feat.shap_value > 0 ? "+" : ""}{feat.shap_value.toFixed(3)}
                                                    </span>
                                                </div>
                                                <div className="shap-bar">
                                                    <div
                                                        className="shap-fill"
                                                        style={{
                                                            width: `${pct}%`,
                                                            background:
                                                                i === 0
                                                                    ? cfg.gradient
                                                                    : i === 1
                                                                        ? "linear-gradient(90deg, #6366f1, #8b5cf6)"
                                                                        : "linear-gradient(90deg, #0ea5e9, #22d3ee)",
                                                        }}
                                                    />
                                                </div>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {/* SBAR (if escalated) */}
                        {escalation && (
                            <div className="card" style={{ padding: 24, animation: "slideInRight 0.4s ease forwards" }}>
                                <h4 style={{ marginBottom: 16 }}>
                                    📋 SBAR — AI-Generated Clinical Handover
                                </h4>
                                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                                    {escalation.sbar &&
                                        (["situation", "background", "assessment", "recommendation"] as const).map(
                                            (key) => (
                                                <div key={key} className="sbar-section">
                                                    <div className="sbar-label">{key}</div>
                                                    <div className="sbar-text">{escalation.sbar[key] || "—"}</div>
                                                </div>
                                            )
                                        )}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Escalation Modal */}
            {showEscalateModal && (
                <div
                    style={{
                        position: "fixed",
                        inset: 0,
                        background: "rgba(0,0,0,0.7)",
                        backdropFilter: "blur(8px)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        zIndex: 1000,
                        padding: 24,
                        animation: "fadeIn 0.2s ease forwards",
                    }}
                >
                    <div
                        className="card"
                        style={{ width: "100%", maxWidth: 520, padding: 32 }}
                    >
                        <div
                            style={{
                                display: "flex",
                                alignItems: "center",
                                gap: 12,
                                marginBottom: 20,
                            }}
                        >
                            <div style={{ fontSize: "1.8rem" }}>📡</div>
                            <div>
                                <h3 style={{ marginBottom: 2 }}>Escalate to Specialist</h3>
                                <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                                    This will generate a magic link and SBAR summary for the specialist.
                                </p>
                            </div>
                        </div>

                        <div className="form-group" style={{ marginBottom: 20 }}>
                            <label htmlFor="escalation-reason">Escalation Reason *</label>
                            <textarea
                                id="escalation-reason"
                                value={escalationReason}
                                onChange={(e) => setEscalationReason(e.target.value)}
                                style={{ minHeight: 100 }}
                            />
                        </div>

                        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
                            <button
                                className="btn btn-ghost"
                                onClick={() => setShowEscalateModal(false)}
                                id="cancel-escalate-btn"
                            >
                                Cancel
                            </button>
                            <button
                                id="confirm-escalate-btn"
                                className="btn btn-danger"
                                onClick={handleEscalate}
                                disabled={escalating || escalationReason.length < 10}
                            >
                                {escalating ? (
                                    <>
                                        <div className="spinner" />
                                        Escalating…
                                    </>
                                ) : (
                                    "📡 Confirm Escalation"
                                )}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

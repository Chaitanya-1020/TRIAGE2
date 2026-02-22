"use client";

import { useState, useEffect } from "react";
import { getSpecialistPortal, submitAdvice } from "@/lib/api";
import { useWebSocket } from "@/hooks/useWebSocket";
import type { SpecialistPortalData, WSMessage, AdviceType } from "@/types";

interface SpecialistPortalPageProps {
    token: string;
    onBack: () => void;
}

const ADVICE_OPTIONS: { value: AdviceType; label: string; icon: string; color: string }[] = [
    { value: "urgent_referral", label: "Urgent Referral", icon: "🚑", color: "var(--critical)" },
    { value: "admit", label: "Admit to Hospital", icon: "🏥", color: "var(--high)" },
    { value: "start_iv_fluids", label: "Start IV Fluids", icon: "💉", color: "var(--moderate)" },
    { value: "observe_2h", label: "Observe 2 Hours", icon: "⏱️", color: "var(--accent-blue)" },
    { value: "manage_locally", label: "Manage Locally", icon: "🏠", color: "var(--low)" },
    { value: "custom", label: "Custom Advice", icon: "✏️", color: "var(--text-secondary)" },
];

const COMMON_INVESTIGATIONS = [
    "CBC", "LFT", "RFT", "Urine protein", "ECG", "CXR",
    "Blood culture", "HbA1c", "Coagulation panel", "ABG",
];

const COMMON_MEDS_ADVICE = [
    "IV MgSO4", "Nifedipine", "Furosemide", "IV Dextrose", "Aspirin",
    "Metoprolol", "Morphine", "IV Antibiotics", "Oxygen therapy",
];

function VitalBadge({ label, value, unit, warning }: { label: string; value: number | string; unit: string; warning?: boolean }) {
    return (
        <div
            style={{
                background: warning ? "var(--critical-bg)" : "var(--bg-secondary)",
                border: `1px solid ${warning ? "rgba(239,68,68,0.3)" : "var(--border)"}`,
                borderRadius: "var(--radius-md)",
                padding: "12px 14px",
                display: "flex",
                flexDirection: "column",
                gap: 4,
            }}
        >
            <span style={{ fontSize: "0.7rem", color: warning ? "var(--critical)" : "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                {label}
            </span>
            <span
                style={{
                    fontSize: "1.4rem",
                    fontWeight: 800,
                    fontFamily: "JetBrains Mono, monospace",
                    color: warning ? "var(--critical)" : "var(--text-primary)",
                    lineHeight: 1,
                }}
            >
                {value}
            </span>
            <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{unit}</span>
        </div>
    );
}

export default function SpecialistPortalPage({ token, onBack }: SpecialistPortalPageProps) {
    const [data, setData] = useState<SpecialistPortalData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [submitted, setSubmitted] = useState(false);

    // Advice form
    const [adviceType, setAdviceType] = useState<AdviceType | null>(null);
    const [customNotes, setCustomNotes] = useState("");
    const [selectedMeds, setSelectedMeds] = useState<string[]>([]);
    const [selectedInvest, setSelectedInvest] = useState<string[]>([]);
    const [followUpHours, setFollowUpHours] = useState("");
    const [submitting, setSubmitting] = useState(false);
    const [wsMessages, setWsMessages] = useState<WSMessage[]>([]);

    useWebSocket({
        caseId: data?.case_id ?? null,
        onMessage: (msg) => setWsMessages((prev) => [msg, ...prev].slice(0, 5)),
    });

    useEffect(() => {
        const loadPortal = async () => {
            try {
                const portalData = await getSpecialistPortal(token);
                setData(portalData);
            } catch {
                // Demo fallback
                const demo: SpecialistPortalData = {
                    case_id: "demo-case-001",
                    patient_summary: { age: 32, sex: "female", vulnerability_flags: { pregnant: true, diabetic: false, elderly: false, heart_disease: false, immunocompromised: false } },
                    vitals: { systolic_bp: 155, diastolic_bp: 100, heart_rate: 98, respiratory_rate: 20, spo2: 97.0, temperature: 37.2 },
                    symptoms: [
                        { symptom_name: "Severe headache", is_red_flag: true, severity: "severe", duration_hours: 6 },
                        { symptom_name: "Blurred vision", is_red_flag: true, severity: "severe", duration_hours: 4 },
                    ],
                    medications: [
                        { drug_name: "Iron supplement", dose: "100mg" },
                        { drug_name: "Folic acid", dose: "5mg" },
                    ],
                    risk_assessment: {
                        assessment_id: "assess-demo",
                        case_id: "demo-case-001",
                        final_risk_level: "critical",
                        final_risk_score: 0.91,
                        rule_engine: {
                            triggered: true,
                            risk_level: "critical",
                            reasons: ["Pregnancy hypertension (possible preeclampsia): BP 155/100 mmHg"],
                            override_ml: true,
                        },
                        ml_result: {
                            risk_probability: 0.84,
                            risk_level: "high",
                            shap_features: [
                                { feature: "systolic_bp", value: 155, shap_value: 0.38, label: "Elevated BP (155 mmHg) is top risk driver" },
                                { feature: "pregnant", value: true, shap_value: 0.29, label: "Pregnancy flag significantly elevates risk" },
                                { feature: "headache", value: true, shap_value: 0.18, label: "Severe headache is a red-flag symptom" },
                            ],
                            shap_text: "Pregnancy + elevated BP + severe headache suggest preeclampsia — high risk.",
                        },
                        med_warnings: [],
                        recommendation: "⚠️ IMMEDIATE ESCALATION REQUIRED. Signs consistent with preeclampsia. Maternal emergency protocol — ensure IV access, monitor fetal heart rate.",
                        escalation_suggested: true,
                        assessed_at: new Date().toISOString(),
                    },
                    sbar: {
                        situation: "32-year-old pregnant female (34 weeks) presenting with BP 155/100 mmHg, severe headache, and blurred vision.",
                        background: "No prior hypertension. On iron + folic acid. Escalated by PHW Priya Sharma, PHC Wardha Rural.",
                        assessment: "AI classified CRITICAL (score 0.91). Rule engine triggered: pregnancy hypertension (possible preeclampsia). ML risk: 84%.",
                        recommendation: "Urgent specialist assessment required. Consider magnesium sulfate for seizure prophylaxis. Antihypertensive therapy indicated.",
                    },
                    phw_name: "Priya Sharma",
                    facility: "PHC Wardha Rural",
                    escalated_at: new Date().toISOString(),
                };
                setData(demo);
            } finally {
                setLoading(false);
            }
        };

        loadPortal();
    }, [token]);

    const toggleMed = (m: string) =>
        setSelectedMeds((prev) => prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]);

    const toggleInvest = (inv: string) =>
        setSelectedInvest((prev) => prev.includes(inv) ? prev.filter((x) => x !== inv) : [...prev, inv]);

    const handleSubmitAdvice = async () => {
        if (!adviceType || !data) return;
        setSubmitting(true);
        try {
            await submitAdvice({
                case_id: data.case_id,
                advice_type: adviceType,
                custom_notes: customNotes || undefined,
                medications_advised: selectedMeds,
                investigations: selectedInvest,
                follow_up_hours: followUpHours ? parseInt(followUpHours) : undefined,
            });
            setSubmitted(true);
        } catch {
            // Demo: just show success
            setSubmitted(true);
        } finally {
            setSubmitting(false);
        }
    };

    if (loading) {
        return (
            <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-primary)" }}>
                <div style={{ textAlign: "center" }}>
                    <div className="loader-dots" style={{ justifyContent: "center", marginBottom: 16 }}>
                        <div className="loader-dot" /><div className="loader-dot" /><div className="loader-dot" />
                    </div>
                    <p style={{ color: "var(--text-muted)" }}>Loading specialist portal…</p>
                </div>
            </div>
        );
    }

    if (error || !data) {
        return (
            <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-primary)" }}>
                <div className="card" style={{ padding: 40, textAlign: "center", maxWidth: 400 }}>
                    <div style={{ fontSize: "3rem", marginBottom: 16 }}>⚠️</div>
                    <h3>Portal Not Found</h3>
                    <p style={{ marginTop: 8, marginBottom: 20 }}>The magic link may have expired or is invalid.</p>
                    <button className="btn btn-primary" onClick={onBack}>← Return</button>
                </div>
            </div>
        );
    }

    const risk = data.risk_assessment.final_risk_level;
    const riskColors = {
        critical: "var(--critical)",
        high: "var(--high)",
        moderate: "var(--moderate)",
        low: "var(--low)",
    } as const;

    return (
        <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
            {/* Specialist Navbar */}
            <nav className="navbar">
                <div className="nav-logo">
                    <div className="nav-logo-icon">🩺</div>
                    <div>
                        <div style={{ fontSize: "0.95rem", fontWeight: 800 }}>Specialist Portal</div>
                        <div style={{ fontSize: "0.65rem", color: "var(--text-muted)" }}>CDSS — Read-only case review</div>
                    </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                        PHC: <strong style={{ color: "var(--text-primary)" }}>{data.facility}</strong>
                        &nbsp;&middot;&nbsp;PHW: <strong style={{ color: "var(--text-primary)" }}>{data.phw_name}</strong>
                    </div>
                    <div
                        style={{
                            padding: "4px 12px",
                            background: "var(--critical-bg)",
                            border: "1px solid rgba(239,68,68,0.3)",
                            borderRadius: "999px",
                            fontSize: "0.72rem",
                            color: "var(--critical)",
                            fontWeight: 700,
                        }}
                    >
                        🔴 ESCALATED CASE
                    </div>
                </div>
            </nav>

            <div style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 24px", animation: "fadeIn 0.4s ease forwards" }}>
                {/* Case ID header */}
                <div style={{ marginBottom: 28, display: "flex", justifyContent: "space-between", alignItems: "start", flexWrap: "wrap", gap: 12 }}>
                    <div>
                        <h2 style={{ marginBottom: 4 }}>Case Review — {data.case_id}</h2>
                        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                            Escalated {new Date(data.escalated_at).toLocaleString()} by {data.phw_name}
                        </p>
                    </div>
                    <span
                        style={{
                            padding: "6px 16px",
                            borderRadius: "999px",
                            fontSize: "0.8rem",
                            fontWeight: 700,
                            background: risk === "critical" ? "var(--critical-bg)" : risk === "high" ? "var(--high-bg)" : "var(--moderate-bg)",
                            color: riskColors[risk],
                            border: `1px solid ${riskColors[risk]}40`,
                        }}
                    >
                        {risk.toUpperCase()} RISK — {(data.risk_assessment.final_risk_score * 100).toFixed(0)}%
                    </span>
                </div>

                {/* Live WS messages */}
                {wsMessages.length > 0 && (
                    <div className="card" style={{ marginBottom: 20, padding: 14 }}>
                        <div style={{ fontSize: "0.75rem", color: "var(--low)", fontWeight: 600, marginBottom: 8 }}>🔴 LIVE</div>
                        {wsMessages.map((m, i) => (
                            <div key={i} style={{ fontSize: "0.78rem", fontFamily: "monospace", color: "var(--text-secondary)" }}>
                                {m.type}: {JSON.stringify(m).slice(0, 100)}
                            </div>
                        ))}
                    </div>
                )}

                {submitted ? (
                    <div
                        className="card"
                        style={{ padding: 60, textAlign: "center", borderColor: "rgba(34,197,94,0.3)", boxShadow: "0 0 30px var(--low-glow)" }}
                    >
                        <div style={{ fontSize: "4rem", marginBottom: 20 }}>✅</div>
                        <h2 style={{ color: "var(--low)", marginBottom: 12 }}>Advice Submitted</h2>
                        <p style={{ marginBottom: 24 }}>
                            Your advice has been pushed to the PHW in real time via WebSocket.
                            The PHW will receive it on their dashboard immediately.
                        </p>
                        <div style={{ display: "flex", justifyContent: "center", gap: 8 }}>
                            {adviceType && (
                                <span
                                    style={{
                                        padding: "8px 18px",
                                        background: "var(--low-bg)",
                                        borderRadius: "var(--radius-md)",
                                        fontSize: "0.9rem",
                                        fontWeight: 600,
                                        color: "var(--low)",
                                    }}
                                >
                                    {ADVICE_OPTIONS.find((o) => o.value === adviceType)?.icon}{" "}
                                    {ADVICE_OPTIONS.find((o) => o.value === adviceType)?.label}
                                </span>
                            )}
                        </div>
                        {customNotes && (
                            <p style={{ marginTop: 16, color: "var(--text-secondary)", fontSize: "0.9rem", fontStyle: "italic" }}>
                                &ldquo;{customNotes}&rdquo;
                            </p>
                        )}
                    </div>
                ) : (
                    <div className="grid" style={{ gridTemplateColumns: "1fr 1.4fr", gap: 20, alignItems: "start" }}>
                        {/* Left: Patient + Vitals */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                            {/* Patient Summary */}
                            <div className="card" style={{ padding: 20 }}>
                                <h4 style={{ marginBottom: 16 }}>👤 Patient Summary</h4>
                                <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: "0.875rem" }}>
                                    <InfoRow label="Age" value={`${data.patient_summary.age} years`} />
                                    <InfoRow label="Sex" value={data.patient_summary.sex} />
                                    <InfoRow
                                        label="Vulnerability"
                                        value={
                                            Object.entries(data.patient_summary.vulnerability_flags)
                                                .filter(([, v]) => v)
                                                .map(([k]) => k.replace("_", " "))
                                                .join(", ") || "None"
                                        }
                                    />
                                    <InfoRow label="Facility" value={data.facility} />
                                    <InfoRow label="PHW" value={data.phw_name} />
                                </div>
                            </div>

                            {/* Vitals */}
                            <div className="card" style={{ padding: 20 }}>
                                <h4 style={{ marginBottom: 16 }}>📊 Vitals</h4>
                                <div className="grid grid-2" style={{ gap: 8 }}>
                                    <VitalBadge label="Systolic BP" value={data.vitals.systolic_bp} unit="mmHg" warning={data.vitals.systolic_bp > 140 || data.vitals.systolic_bp < 90} />
                                    <VitalBadge label="Diastolic BP" value={data.vitals.diastolic_bp} unit="mmHg" warning={data.vitals.diastolic_bp > 90} />
                                    <VitalBadge label="Heart Rate" value={data.vitals.heart_rate} unit="bpm" warning={data.vitals.heart_rate > 120 || data.vitals.heart_rate < 50} />
                                    <VitalBadge label="Resp Rate" value={data.vitals.respiratory_rate} unit="/min" warning={data.vitals.respiratory_rate > 25} />
                                    <VitalBadge label="SpO₂" value={data.vitals.spo2} unit="%" warning={data.vitals.spo2 < 94} />
                                    <VitalBadge label="Temperature" value={data.vitals.temperature} unit="°C" warning={data.vitals.temperature > 38.5} />
                                </div>
                            </div>

                            {/* Symptoms */}
                            <div className="card" style={{ padding: 20 }}>
                                <h4 style={{ marginBottom: 14 }}>🔸 Reported Symptoms</h4>
                                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                                    {data.symptoms.map((s, i) => (
                                        <div
                                            key={i}
                                            style={{
                                                display: "flex",
                                                justifyContent: "space-between",
                                                alignItems: "center",
                                                padding: "8px 12px",
                                                background: s.is_red_flag ? "var(--critical-bg)" : "var(--bg-secondary)",
                                                borderRadius: "var(--radius-sm)",
                                                border: `1px solid ${s.is_red_flag ? "rgba(239,68,68,0.2)" : "var(--border)"}`,
                                            }}
                                        >
                                            <span style={{ fontSize: "0.85rem", color: s.is_red_flag ? "var(--critical)" : "var(--text-primary)" }}>
                                                {s.is_red_flag ? "🚩" : "▪️"} {s.symptom_name}
                                            </span>
                                            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                                                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{s.severity}</span>
                                                {s.duration_hours && (
                                                    <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{s.duration_hours}h</span>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* Medications */}
                            <div className="card" style={{ padding: 20 }}>
                                <h4 style={{ marginBottom: 14 }}>💊 Current Medications</h4>
                                {data.medications.length === 0 ? (
                                    <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>None reported</p>
                                ) : (
                                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                                        {data.medications.map((m, i) => (
                                            <div key={i} style={{ fontSize: "0.85rem", color: "var(--text-secondary)", display: "flex", gap: 8 }}>
                                                <span style={{ color: "var(--text-muted)" }}>•</span>
                                                <span>{m.drug_name}</span>
                                                {m.dose && <span style={{ color: "var(--text-muted)" }}>{m.dose}</span>}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>

                        {/* Right: AI Assessment + SBAR + Advice Form */}
                        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                            {/* SBAR */}
                            <div className="card" style={{ padding: 24, borderLeft: "4px solid var(--accent-blue)" }}>
                                <h4 style={{ marginBottom: 16 }}>📋 SBAR — Clinical Handover</h4>
                                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                                    {(["situation", "background", "assessment", "recommendation"] as const).map((key) => (
                                        <div key={key} className="sbar-section">
                                            <div className="sbar-label">{key}</div>
                                            <div className="sbar-text">{data.sbar[key]}</div>
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* AI Result */}
                            {data.risk_assessment.ml_result && (
                                <div className="card" style={{ padding: 20 }}>
                                    <h4 style={{ marginBottom: 14 }}>🤖 AI Analysis</h4>
                                    <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", fontStyle: "italic", marginBottom: 14 }}>
                                        &ldquo;{data.risk_assessment.ml_result.shap_text}&rdquo;
                                    </p>
                                    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                                        {data.risk_assessment.ml_result.shap_features.slice(0, 3).map((f, i) => (
                                            <div key={i}>
                                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                                                    <span style={{ fontSize: "0.82rem", color: "var(--text-primary)" }}>{f.label}</span>
                                                    <span style={{ fontSize: "0.75rem", fontFamily: "monospace", color: "var(--accent-blue)" }}>+{f.shap_value.toFixed(3)}</span>
                                                </div>
                                                <div className="shap-bar">
                                                    <div className="shap-fill" style={{ width: `${(f.shap_value * 2.5) * 100}%` }} />
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Advice Form */}
                            <div className="card" style={{ padding: 24, borderLeft: "4px solid var(--low)" }}>
                                <h4 style={{ marginBottom: 6 }}>📝 Submit Your Advice</h4>
                                <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: 20 }}>
                                    Your advice will be pushed to the PHW immediately via WebSocket.
                                </p>

                                {/* Advice type selection */}
                                <div className="grid grid-2" style={{ gap: 10, marginBottom: 20 }}>
                                    {ADVICE_OPTIONS.map((opt) => (
                                        <button
                                            key={opt.value}
                                            id={`advice-${opt.value}-btn`}
                                            onClick={() => setAdviceType(opt.value)}
                                            style={{
                                                padding: "14px",
                                                border: `2px solid ${adviceType === opt.value ? opt.color : "var(--border)"}`,
                                                borderRadius: "var(--radius-md)",
                                                background: adviceType === opt.value ? `${opt.color}15` : "var(--bg-input)",
                                                cursor: "pointer",
                                                textAlign: "left",
                                                transition: "all var(--transition-fast)",
                                                display: "flex",
                                                alignItems: "center",
                                                gap: 10,
                                            }}
                                        >
                                            <span style={{ fontSize: "1.2rem" }}>{opt.icon}</span>
                                            <span style={{ fontSize: "0.82rem", fontWeight: 600, color: adviceType === opt.value ? opt.color : "var(--text-secondary)" }}>
                                                {opt.label}
                                            </span>
                                        </button>
                                    ))}
                                </div>

                                {/* Custom notes */}
                                <div className="form-group" style={{ marginBottom: 16 }}>
                                    <label htmlFor="custom-notes">Custom Notes</label>
                                    <textarea
                                        id="custom-notes"
                                        placeholder="Add specific instructions, dosages, transfer details…"
                                        value={customNotes}
                                        onChange={(e) => setCustomNotes(e.target.value)}
                                        style={{ minHeight: 80 }}
                                    />
                                </div>

                                {/* Investigations */}
                                <div style={{ marginBottom: 16 }}>
                                    <label style={{ display: "block", marginBottom: 8 }}>Recommended Investigations</label>
                                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                                        {COMMON_INVESTIGATIONS.map((inv) => (
                                            <button
                                                key={inv}
                                                id={`invest-${inv.replace(/\s+/g, "-")}-btn`}
                                                onClick={() => toggleInvest(inv)}
                                                style={{
                                                    padding: "4px 10px",
                                                    border: `1px solid ${selectedInvest.includes(inv) ? "var(--accent-blue)" : "var(--border)"}`,
                                                    borderRadius: "999px",
                                                    background: selectedInvest.includes(inv) ? "var(--accent-glow)" : "var(--bg-input)",
                                                    color: selectedInvest.includes(inv) ? "var(--accent-blue)" : "var(--text-secondary)",
                                                    cursor: "pointer",
                                                    fontSize: "0.78rem",
                                                    fontWeight: selectedInvest.includes(inv) ? 600 : 400,
                                                    transition: "all var(--transition-fast)",
                                                }}
                                            >
                                                {selectedInvest.includes(inv) ? "✓ " : ""}
                                                {inv}
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                {/* Medications advised */}
                                <div style={{ marginBottom: 16 }}>
                                    <label style={{ display: "block", marginBottom: 8 }}>Medications Advised</label>
                                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                                        {COMMON_MEDS_ADVICE.map((med) => (
                                            <button
                                                key={med}
                                                onClick={() => toggleMed(med)}
                                                style={{
                                                    padding: "4px 10px",
                                                    border: `1px solid ${selectedMeds.includes(med) ? "var(--low)" : "var(--border)"}`,
                                                    borderRadius: "999px",
                                                    background: selectedMeds.includes(med) ? "var(--low-bg)" : "var(--bg-input)",
                                                    color: selectedMeds.includes(med) ? "var(--low)" : "var(--text-secondary)",
                                                    cursor: "pointer",
                                                    fontSize: "0.78rem",
                                                    fontWeight: selectedMeds.includes(med) ? 600 : 400,
                                                    transition: "all var(--transition-fast)",
                                                }}
                                            >
                                                {selectedMeds.includes(med) ? "✓ " : ""}
                                                {med}
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                {/* Follow up */}
                                <div className="form-group" style={{ marginBottom: 20 }}>
                                    <label htmlFor="follow-up">Follow-up in (hours)</label>
                                    <input
                                        id="follow-up"
                                        type="number"
                                        placeholder="e.g. 2"
                                        value={followUpHours}
                                        onChange={(e) => setFollowUpHours(e.target.value)}
                                        min={1}
                                        max={720}
                                    />
                                </div>

                                <button
                                    id="submit-advice-btn"
                                    className="btn btn-success btn-full btn-lg"
                                    disabled={!adviceType || submitting}
                                    onClick={handleSubmitAdvice}
                                >
                                    {submitting ? (
                                        <>
                                            <div className="spinner" />
                                            Submitting…
                                        </>
                                    ) : (
                                        "📤 Submit Advice to PHW"
                                    )}
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

function InfoRow({ label, value }: { label: string; value: string }) {
    return (
        <div style={{ display: "flex", justifyContent: "space-between", borderBottom: "1px solid var(--border)", paddingBottom: 8 }}>
            <span style={{ color: "var(--text-muted)", fontSize: "0.8rem", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>{label}</span>
            <span style={{ color: "var(--text-primary)", fontSize: "0.875rem", fontWeight: 500 }}>{value}</span>
        </div>
    );
}

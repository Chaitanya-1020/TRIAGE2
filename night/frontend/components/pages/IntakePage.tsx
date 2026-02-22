"use client";

import { useState } from "react";
import Navbar from "@/components/layout/Navbar";
import { analyzeRisk } from "@/lib/api";
import type {
    User,
    MedicationInput,
    SymptomInput,
    RiskAssessmentResponse,
    VulnerabilityFlags,
    VitalsInput,
    SexEnum,
} from "@/types";
import type { View } from "@/app/page";

interface IntakePageProps {
    user: User;
    onLogout: () => void;
    onBack: () => void;
    onComplete: (result: RiskAssessmentResponse) => void;
    navigateTo: (view: View) => void;
}

interface FormState {
    // Step 1: Demographics
    patient_name: string;
    age: string;
    sex: SexEnum | "";
    village: string;
    district: string;
    pregnant: boolean;
    diabetic: boolean;
    elderly: boolean;
    heart_disease: boolean;
    immunocompromised: boolean;
    // Step 2: Vitals
    systolic_bp: string;
    diastolic_bp: string;
    heart_rate: string;
    respiratory_rate: string;
    spo2: string;
    temperature: string;
    blood_glucose_mgdl: string;
    weight_kg: string;
    gcs_score: string;
    // Step 3: Medications & Symptoms
    medications: MedicationInput[];
    symptoms: SymptomInput[];
    // Step 4: Chief Complaint
    chief_complaint: string;
}

const STEPS = [
    { label: "Demographics", icon: "👤" },
    { label: "Vitals", icon: "❤️" },
    { label: "Medications & Symptoms", icon: "💊" },
    { label: "Complaint & Submit", icon: "📝" },
];

const INITIAL: FormState = {
    patient_name: "",
    age: "",
    sex: "",
    village: "",
    district: "",
    pregnant: false,
    diabetic: false,
    elderly: false,
    heart_disease: false,
    immunocompromised: false,
    systolic_bp: "",
    diastolic_bp: "",
    heart_rate: "",
    respiratory_rate: "",
    spo2: "",
    temperature: "",
    blood_glucose_mgdl: "",
    weight_kg: "",
    gcs_score: "",
    medications: [],
    symptoms: [],
    chief_complaint: "",
};

const COMMON_SYMPTOMS = [
    "Fever", "Headache", "Chest pain", "Shortness of breath", "Nausea",
    "Vomiting", "Abdominal pain", "Dizziness", "Weakness", "Cough",
    "Blurred vision", "Leg swelling", "Palpitations", "Back pain", "Confusion",
];

const COMMON_MEDS = [
    "Paracetamol", "Aspirin", "Iron supplement", "Folic acid", "Metformin",
    "Amlodipine", "Atorvastatin", "Warfarin", "Carbamazepine", "Amoxicillin",
];

function VitalInput({
    label, id, value, onChange, unit, min, max, step = 1, required = true,
}: {
    label: string; id: string; value: string; onChange: (v: string) => void;
    unit: string; min: number; max: number; step?: number; required?: boolean;
}) {
    const num = parseFloat(value);
    const inRange = !value || (num >= min && num <= max);
    return (
        <div className="form-group">
            <label htmlFor={id}>
                {label} <span style={{ color: "var(--text-muted)", fontWeight: 400, textTransform: "none" }}>({unit})</span>
            </label>
            <div style={{ position: "relative" }}>
                <input
                    id={id}
                    type="number"
                    placeholder={`${min}–${max}`}
                    value={value}
                    min={min}
                    max={max}
                    step={step}
                    required={required}
                    onChange={(e) => onChange(e.target.value)}
                    style={{ borderColor: !inRange && value ? "var(--critical)" : undefined }}
                />
                {value && (
                    <span
                        style={{
                            position: "absolute",
                            right: 12,
                            top: "50%",
                            transform: "translateY(-50%)",
                            fontSize: "0.75rem",
                            color: inRange ? "var(--low)" : "var(--critical)",
                        }}
                    >
                        {inRange ? "✓" : "⚠"}
                    </span>
                )}
            </div>
            {!inRange && value && (
                <p style={{ fontSize: "0.73rem", color: "var(--critical)", marginTop: 2 }}>
                    Value must be between {min} and {max}
                </p>
            )}
        </div>
    );
}

export default function IntakePage({
    user, onLogout, onBack, onComplete, navigateTo,
}: IntakePageProps) {
    const [step, setStep] = useState(0);
    const [form, setForm] = useState<FormState>(INITIAL);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Medication add
    const [newMed, setNewMed] = useState("");
    const [medDose, setMedDose] = useState("");
    // Symptom add
    const [newSym, setNewSym] = useState("");
    const [symSeverity, setSymSeverity] = useState<"mild" | "moderate" | "severe">("mild");
    const [symRedFlag, setSymRedFlag] = useState(false);
    const [symDuration, setSymDuration] = useState("");

    const update = (key: keyof FormState, value: unknown) =>
        setForm((f) => ({ ...f, [key]: value }));

    const addMed = (name?: string) => {
        const drugName = name ?? newMed.trim();
        if (!drugName) return;
        update("medications", [
            ...form.medications,
            { drug_name: drugName, dose: medDose || undefined },
        ]);
        setNewMed("");
        setMedDose("");
    };

    const removeMed = (i: number) =>
        update("medications", form.medications.filter((_, idx) => idx !== i));

    const addSym = (name?: string) => {
        const symName = name ?? newSym.trim();
        if (!symName) return;
        update("symptoms", [
            ...form.symptoms,
            {
                symptom_name: symName,
                is_red_flag: symRedFlag,
                severity: symSeverity,
                duration_hours: symDuration ? parseInt(symDuration) : undefined,
            },
        ]);
        setNewSym("");
        setSymSeverity("mild");
        setSymRedFlag(false);
        setSymDuration("");
    };

    const removeSym = (i: number) =>
        update("symptoms", form.symptoms.filter((_, idx) => idx !== i));

    const handleSubmit = async () => {
        setError(null);
        setLoading(true);
        try {
            const result = await analyzeRisk({
                patient_name: form.patient_name,
                age: parseInt(form.age),
                sex: form.sex as SexEnum,
                village: form.village || undefined,
                district: form.district || undefined,
                vulnerability_flags: {
                    pregnant: form.pregnant,
                    diabetic: form.diabetic,
                    elderly: form.elderly,
                    heart_disease: form.heart_disease,
                    immunocompromised: form.immunocompromised,
                } as VulnerabilityFlags,
                vitals: {
                    systolic_bp: parseInt(form.systolic_bp),
                    diastolic_bp: parseInt(form.diastolic_bp),
                    heart_rate: parseInt(form.heart_rate),
                    respiratory_rate: parseInt(form.respiratory_rate),
                    spo2: parseFloat(form.spo2),
                    temperature: parseFloat(form.temperature),
                    blood_glucose_mgdl: form.blood_glucose_mgdl ? parseInt(form.blood_glucose_mgdl) : undefined,
                    weight_kg: form.weight_kg ? parseFloat(form.weight_kg) : undefined,
                    gcs_score: form.gcs_score ? parseInt(form.gcs_score) : undefined,
                } as VitalsInput,
                medications: form.medications,
                symptoms: form.symptoms,
                chief_complaint: form.chief_complaint,
            });
            onComplete(result);
        } catch (err: any) {
            setError(err.message || "An unexpected error occurred during AI analysis. Please check your inputs.");
        } finally {
            setLoading(false);
        }
    };

    // ── Step validation ────────────────────────────────────────────────
    const canProceed = [
        form.patient_name && form.age && form.sex,
        form.systolic_bp && form.diastolic_bp && form.heart_rate &&
        form.respiratory_rate && form.spo2 && form.temperature,
        true, // medications/symptoms optional
        form.chief_complaint.length >= 5,
    ][step];

    return (
        <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
            <Navbar user={user} currentView="intake" onLogout={onLogout} navigateTo={navigateTo} />

            <div
                style={{
                    maxWidth: 860,
                    margin: "0 auto",
                    padding: "32px 24px",
                    animation: "fadeIn 0.4s ease forwards",
                }}
            >
                {/* Header */}
                <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 32 }}>
                    <button className="btn btn-ghost btn-sm" onClick={onBack}>
                        ← Back
                    </button>
                    <div>
                        <h2 style={{ marginBottom: 2 }}>New Patient Intake</h2>
                        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                            Complete all steps to run the hybrid AI risk assessment
                        </p>
                    </div>
                </div>

                {/* Step indicator */}
                <div className="step-indicator" style={{ marginBottom: 32, display: "flex", justifyContent: "space-between", position: "relative" }}>
                    {STEPS.map((s, i) => (
                        <div key={i} className="step-item" style={{ flex: 1, flexDirection: "column", position: "relative", alignItems: "center" }}>
                            {i < STEPS.length - 1 && (
                                <div
                                    className={`step-line ${i < step ? "completed" : ""}`}
                                    style={{
                                        position: "absolute",
                                        top: 17,
                                        left: "50%",
                                        width: "100%",
                                        zIndex: 0
                                    }}
                                />
                            )}
                            <div
                                className={`step-dot ${i < step ? "completed" : i === step ? "active" : ""}`}
                                style={{ zIndex: 1, position: "relative", background: i === step ? undefined : "var(--bg-primary)" }}
                            >
                                {i < step ? "✓" : s.icon}
                            </div>
                            <div
                                style={{
                                    fontSize: "0.8rem",
                                    textAlign: "center",
                                    marginTop: 8,
                                    color: i === step ? "var(--accent-blue)" : "var(--text-muted)",
                                    fontWeight: i === step ? 600 : 500,
                                    whiteSpace: "nowrap",
                                }}
                            >
                                {s.label}
                            </div>
                        </div>
                    ))}
                </div>

                {/* Step Cards */}
                <div className="card" style={{ animation: "slideInRight 0.3s ease forwards" }} key={step}>

                    {/* ── Step 0: Demographics ─────────────────────────────────── */}
                    {step === 0 && (
                        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                            <h3>Patient Demographics</h3>

                            <div className="grid grid-2" style={{ gap: 16 }}>
                                <div className="form-group" style={{ gridColumn: "1 / -1" }}>
                                    <label htmlFor="patient-name">Full Name *</label>
                                    <input
                                        id="patient-name"
                                        type="text"
                                        placeholder="e.g. Meena Devi"
                                        value={form.patient_name}
                                        onChange={(e) => update("patient_name", e.target.value)}
                                        required
                                    />
                                </div>
                                <div className="form-group">
                                    <label htmlFor="patient-age">Age (years) *</label>
                                    <input
                                        id="patient-age"
                                        type="number"
                                        placeholder="0–120"
                                        value={form.age}
                                        min={0} max={120}
                                        onChange={(e) => update("age", e.target.value)}
                                        required
                                    />
                                </div>
                                <div className="form-group">
                                    <label htmlFor="patient-sex">Biological Sex *</label>
                                    <select
                                        id="patient-sex"
                                        value={form.sex}
                                        onChange={(e) => update("sex", e.target.value)}
                                        required
                                    >
                                        <option value="">Select sex</option>
                                        <option value="male">Male</option>
                                        <option value="female">Female</option>
                                        <option value="other">Other</option>
                                    </select>
                                </div>
                                <div className="form-group">
                                    <label htmlFor="village">Village</label>
                                    <input
                                        id="village"
                                        type="text"
                                        placeholder="e.g. Wardha"
                                        value={form.village}
                                        onChange={(e) => update("village", e.target.value)}
                                    />
                                </div>
                                <div className="form-group">
                                    <label htmlFor="district">District</label>
                                    <input
                                        id="district"
                                        type="text"
                                        placeholder="e.g. Nagpur"
                                        value={form.district}
                                        onChange={(e) => update("district", e.target.value)}
                                    />
                                </div>
                            </div>

                            <div className="divider" />
                            <h4 style={{ color: "var(--text-secondary)" }}>Vulnerability Flags</h4>
                            <div className="grid grid-2" style={{ gap: 10 }}>
                                {([
                                    ["pregnant", "🤰 Pregnant", form.sex === "male"],
                                    ["diabetic", "🩸 Diabetic", false],
                                    ["elderly", "👴 Elderly (65+)", false],
                                    ["heart_disease", "❤️ Heart Disease", false],
                                    ["immunocompromised", "🛡️ Immunocompromised", false],
                                ] as [keyof FormState, string, boolean][]).map(([key, label, disabled]) => (
                                    <label
                                        key={key}
                                        className={`checkbox-group ${form[key] ? "checked" : ""} ${disabled ? "btn:disabled" : ""}`}
                                        style={{ opacity: disabled ? 0.4 : 1, cursor: disabled ? "not-allowed" : "pointer" }}
                                    >
                                        <input
                                            type="checkbox"
                                            id={`flag-${key}`}
                                            checked={!!form[key]}
                                            disabled={disabled}
                                            onChange={(e) => update(key, e.target.checked)}
                                        />
                                        <span style={{ fontSize: "0.875rem", fontWeight: 500, color: "var(--text-primary)" }}>
                                            {label}
                                        </span>
                                    </label>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* ── Step 1: Vitals ────────────────────────────────────────── */}
                    {step === 1 && (
                        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <h3>Vital Signs</h3>
                                <span className="badge badge-blue">All required fields marked *</span>
                            </div>
                            <div
                                className="alert alert-info"
                                style={{ fontSize: "0.82rem", padding: "12px 16px" }}
                            >
                                <span>⚠️</span>
                                <span>
                                    Values outside normal ranges will be highlighted. NEWS2 critical thresholds: SpO₂ &lt;90%,
                                    Systolic BP &lt;90 mmHg, RR &gt;25/min.
                                </span>
                            </div>

                            <div className="grid grid-3" style={{ gap: 16 }}>
                                <VitalInput
                                    label="Systolic BP *" id="systolic-bp"
                                    value={form.systolic_bp} onChange={(v) => update("systolic_bp", v)}
                                    unit="mmHg" min={40} max={350}
                                />
                                <VitalInput
                                    label="Diastolic BP *" id="diastolic-bp"
                                    value={form.diastolic_bp} onChange={(v) => update("diastolic_bp", v)}
                                    unit="mmHg" min={20} max={250}
                                />
                                <VitalInput
                                    label="Heart Rate *" id="heart-rate"
                                    value={form.heart_rate} onChange={(v) => update("heart_rate", v)}
                                    unit="bpm" min={20} max={350}
                                />
                                <VitalInput
                                    label="Respiratory Rate *" id="respiratory-rate"
                                    value={form.respiratory_rate} onChange={(v) => update("respiratory_rate", v)}
                                    unit="/min" min={4} max={80}
                                />
                                <VitalInput
                                    label="SpO₂ *" id="spo2"
                                    value={form.spo2} onChange={(v) => update("spo2", v)}
                                    unit="%" min={50} max={100} step={0.1}
                                />
                                <VitalInput
                                    label="Temperature *" id="temperature"
                                    value={form.temperature} onChange={(v) => update("temperature", v)}
                                    unit="°C" min={30} max={45} step={0.1}
                                />
                                <VitalInput
                                    label="Blood Glucose" id="blood-glucose"
                                    value={form.blood_glucose_mgdl} onChange={(v) => update("blood_glucose_mgdl", v)}
                                    unit="mg/dL" min={20} max={1000} required={false}
                                />
                                <VitalInput
                                    label="Weight" id="weight-kg"
                                    value={form.weight_kg} onChange={(v) => update("weight_kg", v)}
                                    unit="kg" min={1} max={300} step={0.1} required={false}
                                />
                                <VitalInput
                                    label="GCS Score" id="gcs-score"
                                    value={form.gcs_score} onChange={(v) => update("gcs_score", v)}
                                    unit="3–15" min={3} max={15} required={false}
                                />
                            </div>
                        </div>
                    )}

                    {/* ── Step 2: Medications & Symptoms ──────────────────────── */}
                    {step === 2 && (
                        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 24 }}>
                            <h3>Medications & Symptoms</h3>

                            {/* Medications */}
                            <div>
                                <h4 style={{ color: "var(--text-secondary)", marginBottom: 12 }}>
                                    Current Medications
                                </h4>
                                <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
                                    <input
                                        id="med-name-input"
                                        type="text"
                                        placeholder="Drug name"
                                        value={newMed}
                                        onChange={(e) => setNewMed(e.target.value)}
                                        onKeyDown={(e) => e.key === "Enter" && addMed()}
                                        style={{ flex: 2 }}
                                    />
                                    <input
                                        id="med-dose-input"
                                        type="text"
                                        placeholder="Dose (e.g. 500mg)"
                                        value={medDose}
                                        onChange={(e) => setMedDose(e.target.value)}
                                        style={{ flex: 1 }}
                                    />
                                    <button className="btn btn-primary btn-sm" id="add-med-btn" onClick={() => addMed()}>
                                        + Add
                                    </button>
                                </div>
                                {/* Quick add common */}
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
                                    {COMMON_MEDS.filter(
                                        (m) => !form.medications.find((fm) => fm.drug_name === m)
                                    ).map((m) => (
                                        <button
                                            key={m}
                                            className="tag"
                                            style={{ cursor: "pointer", background: "var(--bg-input)" }}
                                            onClick={() => addMed(m)}
                                        >
                                            + {m}
                                        </button>
                                    ))}
                                </div>
                                {/* Added meds */}
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                                    {form.medications.map((m, i) => (
                                        <span key={i} className="tag" style={{ background: "var(--accent-glow)", borderColor: "var(--border-hover)" }}>
                                            💊 {m.drug_name}{m.dose ? ` (${m.dose})` : ""}
                                            <button className="tag-remove" onClick={() => removeMed(i)}>×</button>
                                        </span>
                                    ))}
                                    {form.medications.length === 0 && (
                                        <span style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>No medications added</span>
                                    )}
                                </div>
                            </div>

                            <div className="divider" />

                            {/* Symptoms */}
                            <div>
                                <h4 style={{ color: "var(--text-secondary)", marginBottom: 12 }}>Symptoms</h4>
                                <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr auto", gap: 8, marginBottom: 10 }}>
                                    <input
                                        id="symptom-name-input"
                                        type="text"
                                        placeholder="Symptom name"
                                        value={newSym}
                                        onChange={(e) => setNewSym(e.target.value)}
                                        onKeyDown={(e) => e.key === "Enter" && addSym()}
                                    />
                                    <select
                                        id="symptom-severity-select"
                                        value={symSeverity}
                                        onChange={(e) => setSymSeverity(e.target.value as "mild" | "moderate" | "severe")}
                                    >
                                        <option value="mild">Mild</option>
                                        <option value="moderate">Moderate</option>
                                        <option value="severe">Severe</option>
                                    </select>
                                    <input
                                        id="symptom-duration-input"
                                        type="number"
                                        placeholder="Hours"
                                        value={symDuration}
                                        onChange={(e) => setSymDuration(e.target.value)}
                                        min={0}
                                    />
                                    <button className="btn btn-primary btn-sm" id="add-sym-btn" onClick={() => addSym()}>
                                        + Add
                                    </button>
                                </div>
                                <label
                                    className={`checkbox-group ${symRedFlag ? "checked" : ""}`}
                                    style={{ width: "fit-content", marginBottom: 10, cursor: "pointer" }}
                                >
                                    <input
                                        type="checkbox"
                                        id="symptom-redflag-check"
                                        checked={symRedFlag}
                                        onChange={(e) => setSymRedFlag(e.target.checked)}
                                    />
                                    <span style={{ fontSize: "0.875rem", color: "var(--critical)" }}>
                                        🚩 Mark as Red Flag
                                    </span>
                                </label>
                                {/* Quick add common symptoms */}
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 12 }}>
                                    {COMMON_SYMPTOMS.filter(
                                        (s) => !form.symptoms.find((fs) => fs.symptom_name === s)
                                    ).map((s) => (
                                        <button
                                            key={s}
                                            className="tag"
                                            style={{ cursor: "pointer" }}
                                            onClick={() => addSym(s)}
                                        >
                                            + {s}
                                        </button>
                                    ))}
                                </div>
                                {/* Added symptoms */}
                                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                                    {form.symptoms.map((s, i) => (
                                        <span
                                            key={i}
                                            className="tag"
                                            style={{
                                                background: s.is_red_flag ? "var(--critical-bg)" : "var(--accent-glow)",
                                                borderColor: s.is_red_flag ? "rgba(239,68,68,0.3)" : "var(--border-hover)",
                                                color: s.is_red_flag ? "var(--critical)" : "var(--text-secondary)",
                                            }}
                                        >
                                            {s.is_red_flag ? "🚩" : "🔹"} {s.symptom_name} ({s.severity})
                                            <button className="tag-remove" onClick={() => removeSym(i)}>×</button>
                                        </span>
                                    ))}
                                    {form.symptoms.length === 0 && (
                                        <span style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>No symptoms added</span>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}

                    {/* ── Step 3: Chief Complaint & Submit ─────────────────────── */}
                    {step === 3 && (
                        <div className="card-body" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                            <h3>Chief Complaint & Review</h3>

                            <div className="form-group">
                                <label htmlFor="chief-complaint">
                                    Chief Complaint *{" "}
                                    <span style={{ color: "var(--text-muted)", textTransform: "none", fontWeight: 400 }}>
                                        (min. 5 chars)
                                    </span>
                                </label>
                                <textarea
                                    id="chief-complaint"
                                    placeholder="Describe the main reason for this consult, relevant history, and any urgent concerns…"
                                    value={form.chief_complaint}
                                    onChange={(e) => update("chief_complaint", e.target.value)}
                                    style={{ minHeight: 120 }}
                                />
                                <span style={{ fontSize: "0.75rem", color: form.chief_complaint.length >= 5 ? "var(--low)" : "var(--text-muted)" }}>
                                    {form.chief_complaint.length} characters
                                </span>
                            </div>

                            {/* Summary review */}
                            <div
                                style={{
                                    background: "var(--bg-secondary)",
                                    borderRadius: "var(--radius-md)",
                                    padding: 20,
                                    display: "flex",
                                    flexDirection: "column",
                                    gap: 12,
                                }}
                            >
                                <h4 style={{ color: "var(--accent-blue)", marginBottom: 4 }}>📋 Intake Summary</h4>
                                <div className="grid grid-2" style={{ gap: 8, fontSize: "0.85rem" }}>
                                    <SummaryRow label="Patient" value={`${form.patient_name}, ${form.age}y (${form.sex})`} />
                                    <SummaryRow label="Location" value={[form.village, form.district].filter(Boolean).join(", ") || "—"} />
                                    <SummaryRow label="Vitals" value={`BP ${form.systolic_bp}/${form.diastolic_bp}, HR ${form.heart_rate}, RR ${form.respiratory_rate}, SpO₂ ${form.spo2}%, Temp ${form.temperature}°C`} />
                                    <SummaryRow
                                        label="Flags"
                                        value={
                                            [
                                                form.pregnant && "Pregnant",
                                                form.diabetic && "Diabetic",
                                                form.elderly && "Elderly",
                                                form.heart_disease && "Heart Disease",
                                                form.immunocompromised && "Immunocompromised",
                                            ]
                                                .filter(Boolean)
                                                .join(", ") || "None"
                                        }
                                    />
                                    <SummaryRow label="Medications" value={form.medications.map((m) => m.drug_name).join(", ") || "None"} />
                                    <SummaryRow label="Symptoms" value={form.symptoms.map((s) => s.symptom_name).join(", ") || "None"} />
                                </div>
                            </div>

                            {error && (
                                <div className="alert alert-critical" style={{ fontSize: "0.85rem" }}>
                                    <span>⚠️</span>
                                    <span>{error}</span>
                                </div>
                            )}

                            <div
                                className="alert alert-info"
                                style={{ fontSize: "0.82rem", padding: "12px 16px" }}
                            >
                                <span>🤖</span>
                                <span>
                                    Submitting will run the <strong>Hybrid AI Pipeline</strong>: NEWS2 rules +
                                    XGBoost ML + Medication engine — in parallel. Results include SHAP
                                    explanations and escalation recommendation.
                                </span>
                            </div>
                        </div>
                    )}

                    {/* Navigation buttons */}
                    <div
                        className="card-header"
                        style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            borderTop: "1px solid var(--border)",
                            borderBottom: "none",
                        }}
                    >
                        <button
                            className="btn btn-ghost"
                            onClick={() => (step === 0 ? onBack() : setStep(step - 1))}
                        >
                            ← {step === 0 ? "Dashboard" : "Previous"}
                        </button>

                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                                Step {step + 1} of {STEPS.length}
                            </span>
                            {step < STEPS.length - 1 ? (
                                <button
                                    id="next-step-btn"
                                    className="btn btn-primary"
                                    disabled={!canProceed}
                                    onClick={() => setStep(step + 1)}
                                >
                                    Continue →
                                </button>
                            ) : (
                                <button
                                    id="submit-analysis-btn"
                                    className="btn btn-danger btn-lg"
                                    disabled={!canProceed || loading}
                                    onClick={handleSubmit}
                                >
                                    {loading ? (
                                        <>
                                            <div className="spinner" />
                                            Running AI Analysis…
                                        </>
                                    ) : (
                                        "🤖 Run Risk Assessment →"
                                    )}
                                </button>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
    return (
        <div>
            <span style={{ color: "var(--text-muted)", fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em" }}>
                {label}
            </span>
            <div style={{ color: "var(--text-primary)", fontSize: "0.85rem", marginTop: 2 }}>{value}</div>
        </div>
    );
}

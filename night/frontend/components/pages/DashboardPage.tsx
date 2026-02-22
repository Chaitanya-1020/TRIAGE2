"use client";

import { useState, useEffect } from "react";
import Navbar from "@/components/layout/Navbar";
import type { User, Case } from "@/types";
import type { View } from "@/app/page";

interface DashboardPageProps {
    user: User;
    onLogout: () => void;
    onNewIntake: () => void;
    navigateTo: (view: View) => void;
}

const MOCK_CASES: Case[] = [
    {
        id: "case-001",
        patient_name: "Meena Devi",
        age: 32,
        sex: "female",
        chief_complaint: "Severe headache and visual disturbance at 34 weeks pregnancy",
        risk_level: "critical",
        risk_score: 0.91,
        status: "escalated",
        created_at: new Date(Date.now() - 15 * 60000).toISOString(),
        phw_name: "Priya Sharma",
    },
    {
        id: "case-002",
        patient_name: "Raju Patel",
        age: 58,
        sex: "male",
        chief_complaint: "Chest pain radiating to jaw, sweating",
        risk_level: "high",
        risk_score: 0.78,
        status: "active",
        created_at: new Date(Date.now() - 45 * 60000).toISOString(),
        phw_name: "Suresh Kumar",
    },
    {
        id: "case-003",
        patient_name: "Lata Verma",
        age: 44,
        sex: "female",
        chief_complaint: "Persistent cough, low-grade fever for 3 weeks",
        risk_level: "moderate",
        risk_score: 0.52,
        status: "advised",
        created_at: new Date(Date.now() - 2 * 3600000).toISOString(),
        phw_name: "Anita Singh",
    },
    {
        id: "case-004",
        patient_name: "Dhruv Shah",
        age: 28,
        sex: "male",
        chief_complaint: "Mild fever, body ache for 2 days",
        risk_level: "low",
        risk_score: 0.18,
        status: "closed",
        created_at: new Date(Date.now() - 5 * 3600000).toISOString(),
        phw_name: "Priya Sharma",
    },
];

const STATS = [
    { label: "Active Cases", value: "4", color: "var(--accent-blue)" },
    { label: "Critical Today", value: "1", color: "var(--critical)" },
    { label: "Escalated", value: "2", color: "var(--high)" },
    { label: "Resolved", value: "12", color: "var(--low)" },
];

function RiskBadge({ level }: { level: string }) {
    return (
        <span className={`badge badge-${level}`}>
            {level === "critical" && "🔴 "}
            {level === "high" && "🟠 "}
            {level === "moderate" && "🟡 "}
            {level === "low" && "🟢 "}
            {level.toUpperCase()}
        </span>
    );
}

function StatusBadge({ status }: { status: Case["status"] }) {
    const config = {
        active: { color: "var(--accent-blue)", bg: "rgba(14,165,233,0.08)", label: "Active" },
        escalated: { color: "var(--high)", bg: "rgba(249,115,22,0.08)", label: "Escalated" },
        advised: { color: "var(--low)", bg: "rgba(34,197,94,0.08)", label: "Advised" },
        closed: { color: "var(--text-muted)", bg: "rgba(74,101,128,0.1)", label: "Closed" },
    };
    const { color, bg, label } = config[status];
    return (
        <span
            style={{
                padding: "2px 9px",
                borderRadius: "999px",
                fontSize: "0.72rem",
                fontWeight: 600,
                color,
                background: bg,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
            }}
        >
            {label}
        </span>
    );
}

function timeAgo(iso: string): string {
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    return `${Math.floor(hours / 24)}d ago`;
}

export default function DashboardPage({
    user,
    onLogout,
    onNewIntake,
    navigateTo,
}: DashboardPageProps) {
    const [cases] = useState<Case[]>(MOCK_CASES);
    const [filter, setFilter] = useState<"all" | Case["risk_level"]>("all");
    const [, setTick] = useState(0);

    // Refresh time-ago every minute
    useEffect(() => {
        const interval = setInterval(() => setTick((t) => t + 1), 60000);
        return () => clearInterval(interval);
    }, []);

    const filtered =
        filter === "all" ? cases : cases.filter((c) => c.risk_level === filter);

    return (
        <div style={{ minHeight: "100vh", background: "var(--bg-primary)" }}>
            <Navbar
                user={user}
                currentView="dashboard"
                onLogout={onLogout}
                navigateTo={navigateTo}
            />

            <div
                style={{
                    maxWidth: 1280,
                    margin: "0 auto",
                    padding: "32px 24px",
                    animation: "fadeIn 0.4s ease forwards",
                }}
            >
                {/* Page header */}
                <div
                    style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        marginBottom: 32,
                        flexWrap: "wrap",
                        gap: 16,
                    }}
                >
                    <div>
                        <h1 style={{ marginBottom: 6 }}>
                            Good day,{" "}
                            <span
                                style={{
                                    background: "var(--gradient-primary)",
                                    WebkitBackgroundClip: "text",
                                    WebkitTextFillColor: "transparent",
                                    backgroundClip: "text",
                                }}
                            >
                                {user.full_name.split(" ")[0]}
                            </span>{" "}
                            
                        </h1>
                        <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>
                            {user.role === "phw"
                                ? "PHW Dashboard — Manage patient cases and risk assessments"
                                : "Specialist Dashboard — Review escalated cases and provide advice"}
                        </p>
                    </div>

                    {user.role === "phw" && (
                        <button
                            id="new-patient-btn"
                            className="btn btn-primary btn-lg"
                            onClick={onNewIntake}
                        >
                            ➕ New Patient Intake
                        </button>
                    )}
                </div>

                {/* Stats Row */}
                <div className="grid grid-4" style={{ gap: 16, marginBottom: 32 }}>
                    {STATS.map((s) => (
                        <div
                            key={s.label}
                            className="card"
                            style={{ padding: 20, borderLeft: `3px solid ${s.color}` }}
                        >
                            <div style={{ fontSize: "1.6rem", marginBottom: 8 }}>{s.icon}</div>
                            <div
                                style={{
                                    fontSize: "2.2rem",
                                    fontWeight: 800,
                                    fontFamily: "JetBrains Mono, monospace",
                                    color: s.color,
                                    lineHeight: 1,
                                    marginBottom: 4,
                                }}
                            >
                                {s.value}
                            </div>
                            <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontWeight: 500 }}>
                                {s.label}
                            </div>
                        </div>
                    ))}
                </div>

                {/* Cases section */}
                <div className="card">
                    <div
                        className="card-header"
                        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}
                    >
                        <div>
                            <h3 style={{ marginBottom: 2 }}>Recent Cases</h3>
                            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                                {cases.length} total cases
                            </p>
                        </div>
                        {/* Filter pills */}
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                            {(["all", "critical", "high", "moderate", "low"] as const).map((f) => (
                                <button
                                    key={f}
                                    id={`filter-${f}-btn`}
                                    onClick={() => setFilter(f)}
                                    style={{
                                        padding: "5px 14px",
                                        borderRadius: "999px",
                                        border: "1px solid",
                                        fontSize: "0.78rem",
                                        fontWeight: 600,
                                        cursor: "pointer",
                                        transition: "all var(--transition-fast)",
                                        background:
                                            filter === f
                                                ? f === "all"
                                                    ? "var(--gradient-primary)"
                                                    : f === "critical"
                                                        ? "var(--gradient-critical)"
                                                        : f === "high"
                                                            ? "var(--gradient-high)"
                                                            : f === "moderate"
                                                                ? "var(--gradient-moderate)"
                                                                : "var(--gradient-low)"
                                                : "transparent",
                                        borderColor:
                                            filter === f
                                                ? "transparent"
                                                : "var(--border)",
                                        color: filter === f ? "#fff" : "var(--text-muted)",
                                    }}
                                >
                                    {f.charAt(0).toUpperCase() + f.slice(1)}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="card-body" style={{ padding: 0 }}>
                        <div style={{ overflowX: "auto" }}>
                            <table style={{ width: "100%", borderCollapse: "collapse" }}>
                                <thead>
                                    <tr>
                                        {["Patient", "Age / Sex", "Chief Complaint", "Risk", "Status", "PHW", "Time", "Action"].map(
                                            (col) => (
                                                <th
                                                    key={col}
                                                    style={{
                                                        textAlign: "left",
                                                        padding: "12px 20px",
                                                        fontSize: "0.73rem",
                                                        fontWeight: 700,
                                                        textTransform: "uppercase",
                                                        letterSpacing: "0.07em",
                                                        color: "var(--text-muted)",
                                                        borderBottom: "1px solid var(--border)",
                                                    }}
                                                >
                                                    {col}
                                                </th>
                                            )
                                        )}
                                    </tr>
                                </thead>
                                <tbody>
                                    {filtered.map((c, i) => (
                                        <tr
                                            key={c.id}
                                            style={{
                                                borderBottom: i < filtered.length - 1 ? "1px solid var(--border)" : "none",
                                                transition: "background var(--transition-fast)",
                                            }}
                                            onMouseOver={(e) => {
                                                e.currentTarget.style.background = "var(--bg-card-hover)";
                                            }}
                                            onMouseOut={(e) => {
                                                e.currentTarget.style.background = "transparent";
                                            }}
                                        >
                                            <td style={{ padding: "14px 20px" }}>
                                                <div style={{ fontWeight: 600, fontSize: "0.9rem" }}>{c.patient_name}</div>
                                            </td>
                                            <td style={{ padding: "14px 20px", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                                                {c.age}y · {c.sex}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "14px 20px",
                                                    fontSize: "0.82rem",
                                                    color: "var(--text-secondary)",
                                                    maxWidth: 200,
                                                }}
                                            >
                                                <div
                                                    style={{
                                                        overflow: "hidden",
                                                        textOverflow: "ellipsis",
                                                        whiteSpace: "nowrap",
                                                    }}
                                                    title={c.chief_complaint}
                                                >
                                                    {c.chief_complaint}
                                                </div>
                                            </td>
                                            <td style={{ padding: "14px 20px" }}>
                                                <RiskBadge level={c.risk_level} />
                                            </td>
                                            <td style={{ padding: "14px 20px" }}>
                                                <StatusBadge status={c.status} />
                                            </td>
                                            <td
                                                style={{
                                                    padding: "14px 20px",
                                                    fontSize: "0.8rem",
                                                    color: "var(--text-muted)",
                                                }}
                                            >
                                                {c.phw_name}
                                            </td>
                                            <td
                                                style={{
                                                    padding: "14px 20px",
                                                    fontSize: "0.8rem",
                                                    color: "var(--text-muted)",
                                                    whiteSpace: "nowrap",
                                                }}
                                            >
                                                {timeAgo(c.created_at)}
                                            </td>
                                            <td style={{ padding: "14px 20px" }}>
                                                <button
                                                    className="btn btn-ghost btn-sm"
                                                    id={`view-case-${c.id}-btn`}
                                                    onClick={() => {
                                                        // In a real app navigate to case detail
                                                        alert(`Case ${c.id} — Feature coming soon`);
                                                    }}
                                                >
                                                    View →
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                {/* Quick tips */}
                <div
                   
                >
                </div>
            </div>
        </div>
    );
}

"use client";

import { useState } from "react";
import { login, setToken } from "@/lib/api";
import type { User } from "@/types";

interface LoginPageProps {
    onSuccess: (user: User) => void;
}

const DEMO_ACCOUNTS = [
    { email: "phw@phc.in", password: "demo123", role: "PHW", name: "Priya Sharma", id: "phw-001" },
    { email: "doctor@hospital.in", password: "demo123", role: "Specialist", name: "Dr. Arjun Mehta", id: "spec-001" },
];

export default function LoginPage({ onSuccess }: LoginPageProps) {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [showPass, setShowPass] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setLoading(true);

        try {
            const data = await login({ username: email, password });
            onSuccess({
                id: "user-" + Date.now(),
                email,
                full_name: data.full_name,
                role: data.role as "phw" | "specialist",
            });
        } catch (err: unknown) {
            // Demo mode fallback — match credentials locally
            const demo = DEMO_ACCOUNTS.find(
                (a) => a.email === email && a.password === password
            );
            if (demo) {
                setToken("demo-token-" + demo.role);
                onSuccess({
                    id: demo.id,
                    email: demo.email,
                    full_name: demo.name,
                    role: demo.role === "PHW" ? "phw" : "specialist",
                });
            } else {
                setError(
                    err instanceof Error
                        ? err.message
                        : "Invalid credentials. Try demo accounts below."
                );
            }
        } finally {
            setLoading(false);
        }
    };

    const fillDemo = (acc: (typeof DEMO_ACCOUNTS)[0]) => {
        setEmail(acc.email);
        setPassword(acc.password);
        setError(null);
    };

    return (
        <div
            className="bg-pattern"
            style={{
                minHeight: "100vh",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: "24px",
                background: "var(--bg-primary)",
            }}
        >
            {/* Glowing orbs */}
            <div
                style={{
                    position: "fixed",
                    top: "-20%",
                    left: "-10%",
                    width: "50vw",
                    height: "50vw",
                    borderRadius: "50%",
                    background: "radial-gradient(circle, rgba(14,165,233,0.07) 0%, transparent 70%)",
                    pointerEvents: "none",
                }}
            />
            <div
                style={{
                    position: "fixed",
                    bottom: "-20%",
                    right: "-10%",
                    width: "40vw",
                    height: "40vw",
                    borderRadius: "50%",
                    background: "radial-gradient(circle, rgba(99,102,241,0.06) 0%, transparent 70%)",
                    pointerEvents: "none",
                }}
            />

            <div style={{ width: "100%", maxWidth: "460px", animation: "fadeIn 0.5s ease forwards" }}>
                {/* Header */}
                <div style={{ textAlign: "center", marginBottom: "40px" }}>
                    <div
                        style={{
                            width: "72px",
                            height: "72px",
                            background: "var(--gradient-primary)",
                            borderRadius: "20px",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            fontSize: "2rem",
                            margin: "0 auto 20px",
                            boxShadow: "0 8px 32px rgba(14,165,233,0.4)",
                        }}
                    >
                        ⚕️
                    </div>
                    <h1 style={{ fontSize: "1.8rem", fontWeight: 800, color: "var(--text-primary)", marginBottom: 8 }}>
                        CDSS Portal
                    </h1>
                    <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>
                        Hybrid Clinical Decision Support System
                    </p>
                    <div
                        style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 6,
                            marginTop: 12,
                            padding: "4px 14px",
                            background: "rgba(34,197,94,0.08)",
                            border: "1px solid rgba(34,197,94,0.2)",
                            borderRadius: "999px",
                            fontSize: "0.72rem",
                            color: "var(--low)",
                            fontWeight: 600,
                        }}
                    >
                        <span
                            style={{
                                width: 6,
                                height: 6,
                                borderRadius: "50%",
                                background: "var(--low)",
                                display: "inline-block",
                                animation: "pulse 2s ease-in-out infinite",
                            }}
                        />
                        System Online
                    </div>
                </div>

                {/* Login Card */}
                <div className="card" style={{ padding: "36px" }}>
                    <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                        <div className="form-group">
                            <label htmlFor="login-email">Email Address</label>
                            <input
                                id="login-email"
                                type="email"
                                autoComplete="username"
                                placeholder="phw@phc.in"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                required
                            />
                        </div>

                        <div className="form-group">
                            <label htmlFor="login-password">Password</label>
                            <div style={{ position: "relative" }}>
                                <input
                                    id="login-password"
                                    type={showPass ? "text" : "password"}
                                    autoComplete="current-password"
                                    placeholder="••••••••"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    required
                                    style={{ paddingRight: "44px" }}
                                />
                                <button
                                    type="button"
                                    onClick={() => setShowPass(!showPass)}
                                    style={{
                                        position: "absolute",
                                        right: "12px",
                                        top: "50%",
                                        transform: "translateY(-50%)",
                                        background: "none",
                                        border: "none",
                                        cursor: "pointer",
                                        color: "var(--text-muted)",
                                        fontSize: "1rem",
                                        padding: 0,
                                    }}
                                    aria-label={showPass ? "Hide password" : "Show password"}
                                >
                                    {showPass ? "🙈" : "👁️"}
                                </button>
                            </div>
                        </div>

                        {error && (
                            <div className="alert alert-critical" style={{ fontSize: "0.85rem" }}>
                                <span>⚠️</span>
                                <span>{error}</span>
                            </div>
                        )}

                        <button
                            type="submit"
                            className="btn btn-primary btn-full btn-lg"
                            id="login-submit-btn"
                            disabled={loading}
                        >
                            {loading ? (
                                <>
                                    <div className="spinner" />
                                    Authenticating…
                                </>
                            ) : (
                                "Sign In →"
                            )}
                        </button>
                    </form>
                </div>

                {/* Demo Accounts */}
                <div style={{ marginTop: 24 }}>
                    <p
                        style={{
                            textAlign: "center",
                            fontSize: "0.8rem",
                            color: "var(--text-muted)",
                            marginBottom: 12,
                            textTransform: "uppercase",
                            letterSpacing: "0.07em",
                            fontWeight: 600,
                        }}
                    >
                        Demo Accounts
                    </p>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                        {DEMO_ACCOUNTS.map((acc) => (
                            <button
                                key={acc.email}
                                onClick={() => fillDemo(acc)}
                                id={`demo-${acc.role.toLowerCase()}-btn`}
                                style={{
                                    background: "var(--bg-card)",
                                    border: "1px solid var(--border)",
                                    borderRadius: "var(--radius-md)",
                                    padding: "14px",
                                    cursor: "pointer",
                                    textAlign: "left",
                                    transition: "all var(--transition-fast)",
                                    color: "var(--text-primary)",
                                }}
                                onMouseOver={(e) => {
                                    e.currentTarget.style.borderColor = "var(--border-hover)";
                                    e.currentTarget.style.background = "var(--bg-card-hover)";
                                }}
                                onMouseOut={(e) => {
                                    e.currentTarget.style.borderColor = "var(--border)";
                                    e.currentTarget.style.background = "var(--bg-card)";
                                }}
                            >
                                <div
                                    style={{
                                        fontSize: "0.7rem",
                                        fontWeight: 700,
                                        textTransform: "uppercase",
                                        letterSpacing: "0.07em",
                                        color: "var(--accent-blue)",
                                        marginBottom: 4,
                                    }}
                                >
                                    {acc.role}
                                </div>
                                <div style={{ fontSize: "0.82rem", fontWeight: 600 }}>{acc.name}</div>
                                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 2 }}>
                                    {acc.email}
                                </div>
                            </button>
                        ))}
                    </div>
                </div>

                {/* Footer */}
                <p
                    style={{
                        textAlign: "center",
                        marginTop: 32,
                        fontSize: "0.72rem",
                        color: "var(--text-muted)",
                    }}
                >
                    Powered by XGBoost · Gemini AI · FastAPI
                </p>
            </div>
        </div>
    );
}

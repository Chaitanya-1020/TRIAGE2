"use client";

import type { User } from "@/types";
import type { View } from "@/app/page";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

interface NavbarProps {
    user: User;
    currentView: View;
    onLogout: () => void;
    navigateTo: (view: View) => void;
}

export default function Navbar({ user, currentView, onLogout, navigateTo }: NavbarProps) {
    const { theme, setTheme } = useTheme();
    const [mounted, setMounted] = useState(false);

    useEffect(() => {
        setMounted(true);
    }, []);

    const initials = user.full_name
        .split(" ")
        .slice(0, 2)
        .map((n) => n[0])
        .join("")
        .toUpperCase();

    const isPhw = user.role === "phw";

    return (
        <nav className="navbar">
            {/* Logo */}
            <button
                className="nav-logo"
                onClick={() => navigateTo("dashboard")}
                style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
            >
                <div
                    className="nav-logo-icon"
                    style={{
                        background: "none",
                        boxShadow: "none",
                        width: 84,
                        height: 84,
                        marginRight: 8
                    }}
                >
                    <img src="/logo.png" alt="TRIAGE+" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
                </div>
                <div style={{ textAlign: "left" }}>
                    <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "0.02em" }}>
                        TRIAGE<span style={{ color: "var(--accent-cyan)" }}>+</span>
                    </div>
                    <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", fontWeight: 500, letterSpacing: "0.05em", textTransform: "uppercase" }}>
                        Clinical Decision Support
                    </div>
                </div>
            </button>

            {/* Nav links */}
            <div className="nav-links">
                <button
                    className={`nav-link ${currentView === "dashboard" ? "active" : ""}`}
                    onClick={() => navigateTo("dashboard")}
                >
                    📊 Dashboard
                </button>
                {isPhw && (
                    <button
                        className={`nav-link ${currentView === "intake" ? "active" : ""}`}
                        onClick={() => navigateTo("intake")}
                    >
                        ➕ New Patient
                    </button>
                )}
                <button className="nav-link" style={{ pointerEvents: "none", opacity: 0.5 }}>
                    📋 Cases
                </button>
            </div>

            {/* User info */}
            <div className="nav-user">
                {/* Live indicator */}
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <div
                        style={{
                            width: 8,
                            height: 8,
                            borderRadius: "50%",
                            background: "var(--low)",
                            boxShadow: "0 0 8px var(--low)",
                            animation: "pulse 2s ease-in-out infinite",
                        }}
                    />
                    <span className="text-xs text-muted">Live</span>
                </div>

                <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--text-primary)" }}>
                        {user.full_name}
                    </div>
                    <div style={{ fontSize: "0.7rem", color: "var(--accent-blue)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                        {user.role === "phw" ? "PHW" : "Specialist"}
                    </div>
                </div>

                <div className="avatar">{initials}</div>

                {mounted && (
                    <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
                        style={{ padding: "6px 10px", fontSize: "1.2rem", borderRadius: "var(--radius-full)" }}
                        title="Toggle Theme"
                    >
                        {theme === 'dark' ? '☀️' : '🌙'}
                    </button>
                )}

                <button className="btn btn-ghost btn-sm" onClick={onLogout}>
                    Sign out
                </button>
            </div>
        </nav>
    );
}

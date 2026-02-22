"use client";

import { useState, useEffect } from "react";
import LoginPage from "@/components/pages/LoginPage";
import DashboardPage from "@/components/pages/DashboardPage";
import IntakePage from "@/components/pages/IntakePage";
import ResultsPage from "@/components/pages/ResultsPage";
import SpecialistPortalPage from "@/components/pages/SpecialistPortalPage";
import { getToken } from "@/lib/api";
import type { User, RiskAssessmentResponse, EscalationResponse } from "@/types";

export type View =
  | "login"
  | "dashboard"
  | "intake"
  | "results"
  | "specialist-portal";

export default function Home() {
  const [view, setView] = useState<View>("login");
  const [user, setUser] = useState<User | null>(null);
  const [assessment, setAssessment] = useState<RiskAssessmentResponse | null>(null);
  const [escalation, setEscalation] = useState<EscalationResponse | null>(null);
  const [specialistToken, setSpecialistToken] = useState<string | null>(null);

  // Check if there's a specialist token in the URL
  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const token = params.get("token");
      if (token) {
        setSpecialistToken(token);
        setView("specialist-portal");
        return;
      }

      // Restore session
      const savedToken = getToken();
      const savedUser = localStorage.getItem("cdss_user");
      if (savedToken && savedUser) {
        try {
          setUser(JSON.parse(savedUser));
          setView("dashboard");
        } catch {
          // ignore
        }
      }
    }
  }, []);

  const handleLoginSuccess = (userData: User) => {
    setUser(userData);
    setView("dashboard");
    localStorage.setItem("cdss_user", JSON.stringify(userData));
  };

  const handleLogout = () => {
    setUser(null);
    setAssessment(null);
    setEscalation(null);
    localStorage.removeItem("cdss_user");
    setView("login");
  };

  const handleAssessmentComplete = (
    result: RiskAssessmentResponse
  ) => {
    setAssessment(result);
    setView("results");
  };

  const handleEscalationComplete = (result: EscalationResponse) => {
    setEscalation(result);
  };

  const handleBackToDashboard = () => {
    setAssessment(null);
    setEscalation(null);
    setView("dashboard");
  };

  // Render
  if (view === "specialist-portal") {
    return (
      <SpecialistPortalPage
        token={specialistToken ?? ""}
        onBack={() => setView("login")}
      />
    );
  }

  if (view === "login") {
    return <LoginPage onSuccess={handleLoginSuccess} />;
  }

  if (!user) {
    return <LoginPage onSuccess={handleLoginSuccess} />;
  }

  if (view === "intake") {
    return (
      <IntakePage
        user={user}
        onLogout={handleLogout}
        onBack={() => setView("dashboard")}
        onComplete={handleAssessmentComplete}
        navigateTo={setView}
      />
    );
  }

  if (view === "results" && assessment) {
    return (
      <ResultsPage
        user={user}
        assessment={assessment}
        escalation={escalation}
        onLogout={handleLogout}
        onBack={handleBackToDashboard}
        onEscalationComplete={handleEscalationComplete}
        onNewIntake={() => setView("intake")}
        navigateTo={setView}
      />
    );
  }

  return (
    <DashboardPage
      user={user}
      onLogout={handleLogout}
      onNewIntake={() => setView("intake")}
      navigateTo={setView}
    />
  );
}
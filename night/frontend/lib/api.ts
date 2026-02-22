/**
 * API Client — Centralised HTTP + WebSocket interface for the CDSS backend.
 * Base URL defaults to http://localhost:8000
 */

import type {
    LoginRequest,
    TokenResponse,
    PatientIntakeRequest,
    RiskAssessmentResponse,
    EscalationResponse,
    SpecialistPortalData,
    SpecialistAdviceRequest,
    Case,
    WSMessage,
} from "@/types";

const BASE_URL =
    process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// ── Token Storage ─────────────────────────────────────────────────────────────

let _token: string | null = null;

export function setToken(token: string | null) {
    _token = token;
    if (typeof window !== "undefined") {
        if (token) {
            localStorage.setItem("cdss_token", token);
        } else {
            localStorage.removeItem("cdss_token");
        }
    }
}

export function getToken(): string | null {
    if (_token) return _token;
    if (typeof window !== "undefined") {
        _token = localStorage.getItem("cdss_token");
    }
    return _token;
}

export function clearToken() {
    setToken(null);
}

// ── HTTP Helpers ──────────────────────────────────────────────────────────────

async function request<T>(
    path: string,
    options: RequestInit = {},
    auth = true
): Promise<T> {
    const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(options.headers as Record<string, string>),
    };

    if (auth) {
        const token = getToken();
        if (token) headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`${BASE_URL}${path}`, {
        ...options,
        headers,
    });

    if (!response.ok) {
        let errorMsg = `HTTP ${response.status}`;
        try {
            const err = await response.json();
            errorMsg = err.detail ?? err.error ?? errorMsg;
        } catch {
            // ignore parse errors
        }
        throw new Error(errorMsg);
    }

    // 204 No Content
    if (response.status === 204) return undefined as unknown as T;

    return response.json() as Promise<T>;
}

function get<T>(path: string, auth = true): Promise<T> {
    return request<T>(path, { method: "GET" }, auth);
}

function post<T>(path: string, body: unknown, auth = true): Promise<T> {
    return request<T>(path, { method: "POST", body: JSON.stringify(body) }, auth);
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function login(creds: LoginRequest): Promise<TokenResponse> {
    // FastAPI OAuth2 form
    const form = new URLSearchParams();
    form.append("username", creds.username);
    form.append("password", creds.password);

    const response = await fetch(`${BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: form.toString(),
    });

    if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail ?? "Login failed");
    }

    const data = (await response.json()) as TokenResponse;
    setToken(data.access_token);
    return data;
}

export function logout() {
    clearToken();
}

// ── Cases ─────────────────────────────────────────────────────────────────────

export function getCases(): Promise<Case[]> {
    return get<Case[]>("/cases");
}

export function getCase(caseId: string): Promise<Case> {
    return get<Case>(`/cases/${caseId}`);
}

// ── Analysis ──────────────────────────────────────────────────────────────────

export function analyzeRisk(
    payload: PatientIntakeRequest
): Promise<RiskAssessmentResponse> {
    return post<RiskAssessmentResponse>("/analyze/risk", payload);
}

// ── Escalation ────────────────────────────────────────────────────────────────

export function escalateCase(
    caseId: string,
    reason: string,
    specialistId?: string
): Promise<EscalationResponse> {
    return post<EscalationResponse>("/escalate", {
        case_id: caseId,
        escalation_reason: reason,
        specialist_id: specialistId,
    });
}

// ── Specialist ────────────────────────────────────────────────────────────────

export function getSpecialistPortal(token: string): Promise<SpecialistPortalData> {
    return get<SpecialistPortalData>(`/specialist/portal/${token}`, false);
}

export function submitAdvice(
    advice: SpecialistAdviceRequest
): Promise<{ status: string; case_id: string }> {
    return post<{ status: string; case_id: string }>(
        `/specialist/advice`,
        advice,
        false
    );
}

// ── Health ────────────────────────────────────────────────────────────────────

export function healthCheck(): Promise<{
    status: string;
    models_loaded: boolean;
    version: string;
}> {
    const healthUrl =
        process.env.NEXT_PUBLIC_API_URL
            ? process.env.NEXT_PUBLIC_API_URL.replace("/api/v1", "")
            : "http://localhost:8000";
    return fetch(`${healthUrl}/health`).then((r) => r.json());
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

export function createCaseWebSocket(
    caseId: string,
    onMessage: (msg: WSMessage) => void,
    onError?: (e: Event) => void
): WebSocket {
    const WS_BASE =
        process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
    const token = getToken();
    const url = `${WS_BASE}/ws/case/${caseId}${token ? `?token=${token}` : ""}`;
    const ws = new WebSocket(url);

    ws.onmessage = (event) => {
        try {
            const msg = JSON.parse(event.data) as WSMessage;
            onMessage(msg);
        } catch {
            console.warn("WS parse error", event.data);
        }
    };

    ws.onerror = onError ?? ((e) => console.error("WS error", e));

    return ws;
}

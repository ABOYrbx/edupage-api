const BASE = "/api/v1";

export interface ApiError extends Error {
  code?: string;
  status?: number;
}

/** Fired when an admin session is gone, so the shell can send the user to /login. */
let unauthorizedHandler: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

function csrf(): string | undefined {
  const m = document.cookie.match(/epa_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : undefined;
}

/** Fallback texts for codes the server did not phrase itself. */
const MESSAGES: Record<string, string> = {
  TOKEN_INVALID: "Sitzung abgelaufen – bitte neu anmelden.",
  TOKEN_EXPIRED: "Der Key ist abgelaufen. Bitte einen neuen erstellen.",
  BAD_CREDENTIALS: "Benutzername oder Passwort ist falsch.",
  RATE_LIMITED: "Zu viele Versuche. Bitte einen Moment warten.",
  FORBIDDEN: "Dafür fehlt die Berechtigung.",
  NOT_FOUND: "Nicht gefunden.",
  CONFIG_MISSING: "Server-Konfiguration unvollständig.",
  UPSTREAM: "EduPage hat nicht wie erwartet geantwortet.",
};

type ErrorBody = { error?: string; code?: string };

export async function api<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers: Record<string, string> = {
    ...(init.body ? { "Content-Type": "application/json" } : {}),
    ...((init.headers as Record<string, string>) || {}),
  };
  if (method !== "GET") {
    const token = csrf();
    if (token) headers["X-CSRF-Token"] = token;
  }

  const res = await fetch(BASE + path, { credentials: "same-origin", ...init, headers });
  const data = (await res.json().catch(() => ({}))) as ErrorBody & {
    detail?: ErrorBody;
  };

  if (!res.ok) {
    const code = data.code || data.detail?.code;
    const message = data.error || data.detail?.error || (code ? MESSAGES[code] : undefined) || res.statusText;
    const error = new Error(message) as ApiError;
    error.code = code;
    error.status = res.status;
    if (res.status === 401 && code === "TOKEN_INVALID" && !path.startsWith("/admin/login")) {
      unauthorizedHandler?.();
    }
    throw error;
  }
  return data as T;
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value.endsWith("Z") ? value : `${value}Z`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtDay(value: string | null | undefined): string {
  if (!value) return "—";
  const days = Math.ceil((new Date(value.endsWith("Z") ? value : `${value}Z`).getTime() - Date.now()) / 86_400_000);
  if (days < 0) return "abgelaufen";
  if (days === 0) return "läuft heute ab";
  if (days === 1) return "noch 1 Tag";
  return `noch ${days} Tage`;
}

export function copy(text: string): Promise<void> {
  return navigator.clipboard?.writeText(text) ?? Promise.reject(new Error("Kopieren nicht möglich"));
}

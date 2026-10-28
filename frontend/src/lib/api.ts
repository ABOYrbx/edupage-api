const BASE = "/api/v1";

function csrf(): string | undefined {
  const m = document.cookie.match(/epa_csrf=([^;]+)/);
  return m ? m[1] : undefined;
}

export async function api<T = any>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init?.headers as any) };
  const method = (init?.method || "GET").toUpperCase();
  if (method !== "GET" && csrf()) headers["X-CSRF-Token"] = csrf()!;
  const res = await fetch(BASE + path, { credentials: "include", ...init, headers });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail?.error || data?.error || res.statusText);
  return data as T;
}

export function fmtDate(v: string | null | undefined): string {
  if (!v) return "—";
  try { return new Date(v).toLocaleString(); } catch { return v; }
}

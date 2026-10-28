import type { ReactNode } from "react";

const STYLES: Record<string, string> = {
  ok: "bg-green-100 text-green-700",
  active: "bg-green-100 text-green-700",
  revoked: "bg-slate-200 text-slate-600",
  expired: "bg-amber-100 text-amber-700",
  login_failed: "bg-red-100 text-red-700",
  "2fa_required": "bg-amber-100 text-amber-700",
  error: "bg-red-100 text-red-700",
};

const LABELS: Record<string, string> = {
  ok: "aktiv",
  active: "aktiv",
  revoked: "widerrufen",
  expired: "abgelaufen",
  login_failed: "Login fehlgeschlagen",
  "2fa_required": "2FA nötig",
};

export function Badge({ value, children }: { value: string; children?: ReactNode }) {
  return <span className={`badge ${STYLES[value] ?? "bg-slate-100 text-slate-600"}`}>{children ?? LABELS[value] ?? value}</span>;
}

export function Alert({ kind = "error", children }: { kind?: "error" | "success" | "info"; children: ReactNode }) {
  if (!children) return null;
  const styles = {
    error: "border-red-200 bg-red-50 text-red-700",
    success: "border-green-200 bg-green-50 text-green-700",
    info: "border-blue-200 bg-blue-50 text-blue-700",
  }[kind];
  return <div className={`rounded-lg border px-3 py-2 text-sm ${styles}`}>{children}</div>;
}

export function Empty({ colSpan, children }: { colSpan: number; children: ReactNode }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-3 py-10 text-center text-sm text-slate-500">
        {children}
      </td>
    </tr>
  );
}

export function Spinner({ label = "Lade …" }: { label?: string }) {
  return <div className="px-3 py-10 text-center text-sm text-slate-500">{label}</div>;
}

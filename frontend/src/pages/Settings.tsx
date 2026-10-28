import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Alert } from "../components/ui";

type Settings = {
  values: Record<string, number | string>;
  features: { weather: boolean; secure_cookies: boolean };
  note: string;
};

const LABELS: Record<string, string> = {
  cache_ttl_messages: "Cache: Nachrichten (s)",
  cache_ttl_grades: "Cache: Noten (s)",
  cache_ttl_timetable: "Cache: Stundenplan (s)",
  cache_ttl_weather: "Cache: Wetter (s)",
  session_cache_ttl: "EduPage-Session (s)",
  admin_login_limit: "Login-Limit (Admin)",
  agent_limit: "Limit pro Key",
};

export default function Settings() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [cleared, setCleared] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Settings>("/admin/settings")
      .then(setSettings)
      .catch((err) => setError((err as Error).message));
  }, []);

  async function clear() {
    if (!confirm("Zwischengespeicherte EduPage-Daten löschen? Sie werden beim nächsten Abruf neu geladen."))
      return;
    setError("");
    setCleared(null);
    setBusy(true);
    try {
      const res = await api<{ cleared: number }>("/admin/cache-clear", { method: "POST", body: "{}" });
      setCleared(res.cleared);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Einstellungen</h1>
        <p className="text-sm text-slate-500">Laufzeitwerte aus der <code>.env</code>.</p>
      </div>

      <Alert>{error}</Alert>

      <div className="card p-6">
        <h2 className="font-semibold">Zwischenspeicher</h2>
        <p className="mt-1 text-sm text-slate-500">
          EduPage-Antworten werden kurz gecacht, damit Agenten nicht bei jedem Aufruf neu einloggen müssen.
        </p>
        <button className="btn-secondary mt-3" onClick={clear} disabled={busy}>
          Cache leeren
        </button>
        {cleared !== null && (
          <div className="mt-3">
            <Alert kind="success">{cleared} Einträge gelöscht.</Alert>
          </div>
        )}
      </div>

      {settings?.features && (
        <div className="card p-6">
          <h2 className="font-semibold">Funktionen</h2>
          <ul className="mt-3 divide-y divide-slate-100 text-sm">
            <li className="flex items-center justify-between gap-4 py-2">
              <span className="text-slate-600">Wetter (`/wetter`, `/wetter/suche`)</span>
              <span className={settings.features.weather ? "text-green-700" : "text-slate-400"}>
                {settings.features.weather ? "aktiv" : "nicht konfiguriert (OPENWEATHER_API_KEY)"}
              </span>
            </li>
            <li className="flex items-center justify-between gap-4 py-2">
              <span className="text-slate-600">Secure-Cookies</span>
              <span className={settings.features.secure_cookies ? "text-green-700" : "text-amber-700"}>
                {settings.features.secure_cookies ? "an" : "aus (COOKIE_SECURE=true hinter HTTPS setzen)"}
              </span>
            </li>
          </ul>
        </div>
      )}

      <div className="card p-6">
        <h2 className="font-semibold">System</h2>
        {settings ? (
          <>
            <dl className="mt-3 divide-y divide-slate-100 text-sm">
              {Object.entries(settings.values).map(([key, value]) => (
                <div key={key} className="flex justify-between gap-4 py-2">
                  <dt className="text-slate-600">{LABELS[key] || key}</dt>
                  <dd className="font-mono text-slate-900">{String(value)}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-3 text-xs text-slate-500">{settings.note}</p>
          </>
        ) : (
          <p className="mt-3 text-sm text-slate-500">Lade …</p>
        )}
      </div>
    </div>
  );
}

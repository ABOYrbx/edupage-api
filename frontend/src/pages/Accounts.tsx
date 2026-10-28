import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate } from "../lib/api";
import { Alert, Badge, Empty, Spinner } from "../components/ui";

export type Account = {
  id: string;
  alias: string | null;
  subdomain: string;
  username: string;
  status: string;
  last_error: string | null;
  last_used_at: string | null;
  created_at: string;
  key_count: number;
  active_key_count: number;
};

const EMPTY_FORM = { alias: "", subdomain: "login1", username: "", password: "" };

export default function Accounts() {
  const [items, setItems] = useState<Account[] | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [pending, setPending] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await api<{ items: Account[] }>("/admin/accounts");
      setItems(res.items);
    } catch (err) {
      setError((err as Error).message);
      setItems([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function reset() {
    setShowAdd(false);
    setPending(null);
    setCode("");
    setForm(EMPTY_FORM);
  }

  async function add(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = await api<{ status: string; pending_token?: string }>("/admin/accounts", {
        method: "POST",
        body: JSON.stringify(form),
      });
      if (res.status === "2fa_required" && res.pending_token) {
        setPending(res.pending_token);
      } else {
        reset();
        await load();
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function finish2fa(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/admin/accounts/2fa", {
        method: "POST",
        body: JSON.stringify({ pending_token: pending, code }),
      });
      reset();
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function del(account: Account) {
    const label = account.alias || account.username;
    if (!confirm(`Konto „${label}“ mit allen Keys löschen?`)) return;
    setError("");
    try {
      await api(`/admin/accounts/${account.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function test(account: Account) {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const res = await api<Account>(`/admin/accounts/${account.id}/test`, { method: "POST" });
      setItems((prev) => prev?.map((item) => (item.id === res.id ? { ...item, ...res } : item)) ?? []);
      if (res.status === "ok") setNotice(`Login für „${account.alias || account.username}“ erfolgreich.`);
      else setError(res.last_error || `Login-Status: ${res.status}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function refresh(account: Account) {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const res = await api<Account>(`/admin/accounts/${account.id}/refresh`, { method: "POST" });
      setItems((prev) => prev?.map((item) => (item.id === res.id ? { ...item, ...res } : item)) ?? []);
      if (res.status === "ok") setNotice("Zwischenspeicher geleert und Sitzung erneuert.");
      else setError(res.last_error || `Login-Status: ${res.status}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">EduPage-Konten</h1>
          <p className="text-sm text-slate-500">Jedes Konto bekommt eigene API-Keys für Agenten.</p>
        </div>
        <button className="btn-primary" onClick={() => (showAdd ? reset() : setShowAdd(true))}>
          {showAdd ? "Abbrechen" : "Konto hinzufügen"}
        </button>
      </div>

      <Alert>{error}</Alert>
      <Alert kind="success">{notice}</Alert>

      {showAdd && (
        <div className="card p-6">
          {pending ? (
            <form onSubmit={finish2fa} className="space-y-3">
              <h2 className="font-semibold">Zwei-Faktor-Code</h2>
              <p className="text-sm text-slate-500">
                EduPage hat einen Code an dein Gerät oder deine E-Mail geschickt. Der Vorgang läuft in 10 Minuten
                ab.
              </p>
              <input
                className="input max-w-40 text-center font-mono tracking-widest"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="123456"
                inputMode="numeric"
                autoFocus
                autoComplete="one-time-code"
              />
              <div className="flex gap-2">
                <button className="btn-primary" disabled={busy || code.trim().length === 0}>
                  Bestätigen
                </button>
                <button type="button" className="btn-secondary" onClick={reset}>
                  Abbrechen
                </button>
              </div>
            </form>
          ) : (
            <form onSubmit={add} className="grid gap-3 sm:grid-cols-2">
              <div className="sm:col-span-2">
                <label className="label">Alias (optional)</label>
                <input
                  className="input"
                  placeholder="z. B. Mein Konto"
                  value={form.alias}
                  onChange={(e) => setForm({ ...form, alias: e.target.value })}
                />
              </div>
              <div>
                <label className="label">Subdomain</label>
                <input
                  className="input"
                  placeholder="login1 oder gyk"
                  value={form.subdomain}
                  onChange={(e) => setForm({ ...form, subdomain: e.target.value })}
                />
                <p className="mt-1 text-xs text-slate-500">Aus https://&lt;subdomain&gt;.edupage.org</p>
              </div>
              <div>
                <label className="label">Benutzername</label>
                <input
                  className="input"
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  required
                  autoComplete="username"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="label">Passwort</label>
                <input
                  className="input"
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  required
                  autoComplete="current-password"
                />
              </div>
              <div className="sm:col-span-2">
                <button className="btn-primary" disabled={busy}>
                  {busy ? "Verbinde …" : "Konto hinzufügen"}
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      <div className="card overflow-x-auto">
        {items === null ? (
          <Spinner />
        ) : (
          <table className="w-full min-w-[760px]">
            <thead className="border-b border-slate-200 bg-slate-50">
              <tr>
                <th className="th">Konto</th>
                <th className="th">Schule</th>
                <th className="th">Status</th>
                <th className="th">Keys</th>
                <th className="th">Zuletzt benutzt</th>
                <th className="th" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((account) => (
                <tr key={account.id}>
                  <td className="td">
                    <div className="font-medium">{account.alias || account.username}</div>
                    <div className="text-xs text-slate-500">{account.username}</div>
                  </td>
                  <td className="td text-slate-600">{account.subdomain}</td>
                  <td className="td">
                    <Badge value={account.status} />
                    {account.status !== "ok" && account.last_error && (
                      <div className="mt-1 max-w-56 truncate text-xs text-red-600" title={account.last_error}>
                        {account.last_error}
                      </div>
                    )}
                  </td>
                  <td className="td text-slate-600">
                    {account.active_key_count} aktiv
                    {account.key_count > account.active_key_count && (
                      <span className="text-slate-400"> / {account.key_count}</span>
                    )}
                  </td>
                  <td className="td text-slate-600">{fmtDate(account.last_used_at)}</td>
                  <td className="td">
                    <div className="flex justify-end gap-1">
                      <Link className="btn-secondary" to={`/keys?account=${account.id}`}>
                        Keys
                      </Link>
                      <button className="btn-secondary" onClick={() => test(account)} disabled={busy}>
                        Testen
                      </button>
                      <button className="btn-secondary" onClick={() => refresh(account)} disabled={busy}>
                        Cache leeren
                      </button>
                      <button className="btn-danger" onClick={() => del(account)}>
                        Löschen
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {items.length === 0 && <Empty colSpan={6}>Noch keine Konten. Füge zuerst ein EduPage-Konto hinzu.</Empty>}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

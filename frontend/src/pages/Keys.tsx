import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, copy, fmtDate, fmtDay } from "../lib/api";
import { Alert, Badge, Empty, Spinner } from "../components/ui";
import type { Account } from "./Accounts";

export type ApiKey = {
  id: string;
  account_id: string;
  name: string;
  prefix: string;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  last_used_at: string | null;
  can_write: boolean;
  status: string;
  key?: string;
};

const DAY_CHOICES = [7, 30, 90, 365];

export default function Keys() {
  const [params, setParams] = useSearchParams();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, setSelected] = useState(params.get("account") || "");
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [created, setCreated] = useState<ApiKey | null>(null);
  const [name, setName] = useState("");
  const [days, setDays] = useState(30);
  const [canWrite, setCanWrite] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<{ items: Account[] }>("/admin/accounts")
      .then((res) => {
        setAccounts(res.items);
        setSelected((current) => current || res.items[0]?.id || "");
      })
      .catch((err) => setError((err as Error).message));
  }, []);

  const load = useCallback(async (accountId: string) => {
    if (!accountId) {
      setKeys([]);
      return;
    }
    try {
      const res = await api<{ items: ApiKey[] }>(`/admin/keys?account=${accountId}`);
      setKeys(res.items);
    } catch (err) {
      setError((err as Error).message);
      setKeys([]);
    }
  }, []);

  useEffect(() => {
    void load(selected);
  }, [selected, load]);

  function pick(accountId: string) {
    setSelected(accountId);
    setParams(accountId ? { account: accountId } : {});
  }

  async function create(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy(true);
    try {
      const res = await api<ApiKey>("/admin/keys", {
        method: "POST",
        body: JSON.stringify({ account_id: selected, name, expires_in_days: days, can_write: canWrite }),
      });
      setCreated(res);
      setName("");
      await load(selected);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function revoke(key: ApiKey) {
    if (!confirm(`Key „${key.name}“ widerrufen? Agenten damit verlieren sofort den Zugriff.`)) return;
    setError("");
    try {
      await api(`/admin/keys/${key.id}/revoke`, { method: "POST" });
      await load(selected);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function rotate(key: ApiKey) {
    if (!confirm(`Key „${key.name}“ rotieren? Der bisherige Key wird sofort ungültig.`)) return;
    setError("");
    try {
      const res = await api<ApiKey>(`/admin/keys/${key.id}/rotate`, { method: "POST" });
      setCreated(res);
      await load(selected);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const account = accounts.find((item) => item.id === selected);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">API-Keys</h1>
        <p className="text-sm text-slate-500">
          Ein Key pro Agent. Er wird genau einmal angezeigt – danach nur noch als Prefix.
        </p>
      </div>

      <Alert>{error}</Alert>
      <Alert kind="success">{notice}</Alert>

      {accounts.length === 0 ? (
        <div className="card p-6 text-sm text-slate-500">Lege zuerst ein EduPage-Konto an.</div>
      ) : (
        <>
          <div className="card flex flex-wrap items-center gap-3 p-4">
            <label className="label mb-0" htmlFor="account">
              Konto
            </label>
            <select id="account" className="input max-w-xs" value={selected} onChange={(e) => pick(e.target.value)}>
              {accounts.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.alias || item.username} ({item.subdomain})
                </option>
              ))}
            </select>
            {account && <span className="text-xs text-slate-500">{account.username}</span>}
          </div>

          {created && (
            <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">
              <p className="font-semibold text-amber-900">Neuer Key – jetzt kopieren!</p>
              <p className="mt-1 text-sm text-amber-800">
                Dieser Wert wird nie wieder angezeigt. Geht er verloren, rotiere den Key.
              </p>
              <code className="mt-3 block select-all break-all rounded-lg bg-white p-3 font-mono text-sm">
                {created.key}
              </code>
              <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">
{`curl -H "Authorization: Bearer ${created.key}" \\\n  ${window.location.origin}/api/v1/messages?limit=5`}
              </pre>
              <div className="mt-3 flex gap-2">
                <button
                  className="btn-primary"
                  onClick={() =>
                    copy(created.key!)
                      .then(() => setNotice("Key in die Zwischenablage kopiert."))
                      .catch(() => setNotice("Kopieren nicht möglich – bitte manuell markieren."))
                  }
                >
                  Kopieren
                </button>
                <button className="btn-secondary" onClick={() => setCreated(null)}>
                  Als gespeichert markieren
                </button>
              </div>
            </div>
          )}

          <form onSubmit={create} className="card grid gap-3 p-6 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <h2 className="font-semibold">Neuen Key erstellen</h2>
            </div>
            <div>
              <label className="label" htmlFor="key-name">
                Name
              </label>
              <input
                id="key-name"
                className="input"
                placeholder="z. B. Claude Desktop"
                value={name}
                onChange={(e) => setName(e.target.value)}
                maxLength={80}
                required
              />
            </div>
            <div>
              <label className="label" htmlFor="key-days">
                Gültig für
              </label>
              <div className="flex gap-2">
                <select
                  id="key-days"
                  className="input"
                  value={days}
                  onChange={(e) => setDays(Number(e.target.value))}
                >
                  {DAY_CHOICES.map((choice) => (
                    <option key={choice} value={choice}>
                      {choice} Tage
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  className="input w-24"
                  min={1}
                  max={3650}
                  value={days}
                  onChange={(e) => setDays(Number(e.target.value))}
                  aria-label="Tage"
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm sm:col-span-2">
              <input type="checkbox" checked={canWrite} onChange={(e) => setCanWrite(e.target.checked)} />
              Schreibzugriff erlauben (Nachrichten senden, Hausaufgaben abhaken)
            </label>
            <div className="sm:col-span-2">
              <button className="btn-primary" disabled={busy || !name.trim() || !selected}>
                {busy ? "Erstelle …" : "Key erstellen"}
              </button>
            </div>
          </form>

          <div className="card overflow-x-auto">
            {keys === null ? (
              <Spinner />
            ) : (
              <table className="w-full min-w-[700px]">
                <thead className="border-b border-slate-200 bg-slate-50">
                  <tr>
                    <th className="th">Name</th>
                    <th className="th">Prefix</th>
                    <th className="th">Zugriff</th>
                    <th className="th">Läuft ab</th>
                    <th className="th">Zuletzt benutzt</th>
                    <th className="th">Status</th>
                    <th className="th" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {keys.map((key) => (
                    <tr key={key.id}>
                      <td className="td font-medium">{key.name}</td>
                      <td className="td font-mono text-xs text-slate-600">{key.prefix}…</td>
                      <td className="td text-slate-600">{key.can_write ? "lesen + schreiben" : "nur lesen"}</td>
                      <td className="td text-slate-600">
                        <div>{fmtDate(key.expires_at)}</div>
                        {key.status === "active" && <div className="text-xs text-slate-400">{fmtDay(key.expires_at)}</div>}
                      </td>
                      <td className="td text-slate-600">{fmtDate(key.last_used_at)}</td>
                      <td className="td">
                        <Badge value={key.status} />
                      </td>
                      <td className="td">
                        <div className="flex justify-end gap-1">
                          <button className="btn-secondary" onClick={() => rotate(key)} disabled={key.status === "revoked"}>
                            Rotieren
                          </button>
                          <button className="btn-danger" onClick={() => revoke(key)} disabled={key.status === "revoked"}>
                            Widerrufen
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                  {keys.length === 0 && <Empty colSpan={7}>Für dieses Konto gibt es noch keine Keys.</Empty>}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}

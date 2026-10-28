import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "../lib/api";
import { Alert, Empty, Spinner } from "../components/ui";
import type { Account } from "./Accounts";

type Event = {
  id: string;
  account_id: string | null;
  actor: string;
  action: string;
  outcome: string;
  detail: string | null;
  created_at: string;
};

const PAGE_SIZE = 50;

const ACTION_LABEL: Record<string, string> = {
  "account.added": "Konto hinzugefügt",
  "account.tested": "Konto getestet",
  "key.created": "Key erstellt",
  "key.revoked": "Key widerrufen",
  "key.rotated": "Key rotiert",
};

export default function Activity() {
  const [items, setItems] = useState<Event[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [account, setAccount] = useState("");
  const [action, setAction] = useState("");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api<{ items: Account[] }>("/admin/accounts")
      .then((res) => setAccounts(res.items))
      .catch(() => setAccounts([]));
  }, []);

  const load = useCallback(async () => {
    const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (account) query.set("account", account);
    if (action) query.set("action", action);
    try {
      const res = await api<{ items: Event[]; total: number }>(`/admin/activity?${query}`);
      setItems(res.items);
      setTotal(res.total);
    } catch (err) {
      setError((err as Error).message);
      setItems([]);
    }
  }, [offset, account, action]);

  useEffect(() => {
    void load();
  }, [load]);

  function accountName(id: string | null): string {
    if (!id) return "—";
    const match = accounts.find((item) => item.id === id);
    return match ? match.alias || match.username : id.slice(0, 8);
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Aktivität</h1>
        <p className="text-sm text-slate-500">Alle Verwaltungsaktionen, ohne Zugangsdaten.</p>
      </div>

      <Alert>{error}</Alert>

      <div className="card flex flex-wrap items-end gap-3 p-4">
        <div>
          <label className="label" htmlFor="filter-account">
            Konto
          </label>
          <select
            id="filter-account"
            className="input w-56"
            value={account}
            onChange={(e) => {
              setOffset(0);
              setAccount(e.target.value);
            }}
          >
            <option value="">Alle Konten</option>
            {accounts.map((item) => (
              <option key={item.id} value={item.id}>
                {item.alias || item.username}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="filter-action">
            Aktion
          </label>
          <select
            id="filter-action"
            className="input w-56"
            value={action}
            onChange={(e) => {
              setOffset(0);
              setAction(e.target.value);
            }}
          >
            <option value="">Alle Aktionen</option>
            {Object.entries(ACTION_LABEL).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <span className="ml-auto text-sm text-slate-500">{total} Einträge</span>
      </div>

      <div className="card overflow-x-auto">
        {items === null ? (
          <Spinner />
        ) : (
          <table className="w-full min-w-[640px]">
            <thead className="border-b border-slate-200 bg-slate-50">
              <tr>
                <th className="th">Zeit</th>
                <th className="th">Aktion</th>
                <th className="th">Konto</th>
                <th className="th">Ergebnis</th>
                <th className="th">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((event) => (
                <tr key={event.id}>
                  <td className="td whitespace-nowrap text-slate-600">{fmtDate(event.created_at)}</td>
                  <td className="td font-medium">{ACTION_LABEL[event.action] || event.action}</td>
                  <td className="td text-slate-600">{accountName(event.account_id)}</td>
                  <td className="td">
                    <span
                      className={`badge ${event.outcome === "ok" ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}
                    >
                      {event.outcome}
                    </span>
                  </td>
                  <td className="td max-w-72 truncate text-slate-500" title={event.detail || ""}>
                    {event.detail || ""}
                  </td>
                </tr>
              ))}
              {items.length === 0 && <Empty colSpan={5}>Noch keine Aktivität.</Empty>}
            </tbody>
          </table>
        )}
      </div>

      <div className="flex items-center justify-between">
        <button className="btn-secondary" onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} disabled={offset === 0}>
          Zurück
        </button>
        <span className="text-sm text-slate-500">
          {total === 0 ? "0" : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)}`} von {total}
        </span>
        <button
          className="btn-secondary"
          onClick={() => setOffset(offset + PAGE_SIZE)}
          disabled={offset + PAGE_SIZE >= total}
        >
          Weiter
        </button>
      </div>
    </div>
  );
}

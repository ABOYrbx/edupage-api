import { useEffect, useState } from "react";
import { api, fmtDate } from "../lib/api";

type Key = { id: string; name: string; prefix: string; created_at: string; expires_at: string; revoked_at: string | null; last_used_at: string | null; can_write: boolean; active: boolean };
type Account = { id: string; alias: string | null; username: string; subdomain: string };

export default function Keys() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [keys, setKeys] = useState<Key[]>([]);
  const [newKey, setNewKey] = useState<any>(null);
  const [form, setForm] = useState({ name: "", expires_in_days: 30, can_write: false });
  const [err, setErr] = useState("");

  useEffect(() => {
    api<{ items: Account[] }>("/admin/accounts").then((r) => {
      setAccounts(r.items);
      if (r.items.length) setSelected(r.items[0].id);
    }).catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    if (!selected) return;
    api<{ items: Key[] }>(`/admin/keys?account=${selected}`).then((r) => setKeys(r.items)).catch((e) => setErr(e.message));
  }, [selected]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      const r = await api("/admin/keys", { method: "POST", body: JSON.stringify({ account_id: selected, ...form }) });
      setNewKey(r);
      const rr = await api<{ items: Key[] }>(`/admin/keys?account=${selected}`);
      setKeys(rr.items);
    } catch (e: any) { setErr(e.message); }
  }

  async function revoke(id: string) {
    if (!confirm("Key widerrufen?")) return;
    await api(`/admin/keys/${id}/revoke`, { method: "POST" });
    const rr = await api<{ items: Key[] }>(`/admin/keys?account=${selected}`);
    setKeys(rr.items);
  }

  async function rotate(id: string) {
    const r: any = await api(`/admin/keys/${id}/rotate`, { method: "POST" });
    setNewKey(r);
    const rr = await api<{ items: Key[] }>(`/admin/keys?account=${selected}`);
    setKeys(rr.items);
  }

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold">API-Keys</h1>
      {err && <p className="text-red-600 text-sm">{err}</p>}

      <div className="flex items-center gap-3">
        <label className="text-sm">Konto:</label>
        <select className="border rounded px-3 py-2" value={selected} onChange={(e) => setSelected(e.target.value)}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.alias || a.username} ({a.subdomain})</option>)}
        </select>
      </div>

      {newKey && (
        <div className="bg-amber-50 border border-amber-300 rounded-xl p-4 space-y-2">
          <p className="font-semibold">Neuer Key (nur einmal sichtbar!):</p>
          <code className="block bg-white p-2 rounded break-all">{newKey.key}</code>
          <button onClick={() => { navigator.clipboard.writeText(newKey.key); }} className="text-blue-600 text-sm">Kopieren</button>
          <button onClick={() => setNewKey(null)} className="ml-3 text-gray-600 text-sm">Schließen</button>
        </div>
      )}

      <form onSubmit={create} className="bg-white shadow rounded-xl p-6 space-y-3">
        <h2 className="font-semibold">Neuen Key erstellen</h2>
        <input className="border rounded px-3 py-2 w-full" placeholder="Name (z. B. Claude)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        <div className="flex gap-3">
          <input type="number" className="border rounded px-3 py-2 w-32" value={form.expires_in_days} onChange={(e) => setForm({ ...form, expires_in_days: Number(e.target.value) })} />
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.can_write} onChange={(e) => setForm({ ...form, can_write: e.target.checked })} /> Schreibzugriff</label>
        </div>
        <button className="bg-blue-600 text-white rounded px-4 py-2">Erstellen</button>
      </form>

      <div className="bg-white shadow rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-100">
            <tr><th className="text-left p-3">Name</th><th className="text-left p-3">Prefix</th><th className="text-left p-3">Ablauf</th><th className="text-left p-3">Zuletzt</th><th className="text-left p-3">Status</th><th className="p-3"></th></tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k.id} className="border-t">
                <td className="p-3">{k.name}</td>
                <td className="p-3 font-mono text-xs">{k.prefix}</td>
                <td className="p-3">{fmtDate(k.expires_at)}</td>
                <td className="p-3">{fmtDate(k.last_used_at)}</td>
                <td className="p-3">{k.active ? (k.can_write ? "read+write" : "read") : "inaktiv"}</td>
                <td className="p-3 space-x-2">
                  <button onClick={() => revoke(k.id)} className="text-red-600">Widerrufen</button>
                  <button onClick={() => rotate(k.id)} className="text-blue-600">Rotieren</button>
                </td>
              </tr>
            ))}
            {keys.length === 0 && <tr><td colSpan={6} className="p-6 text-center text-gray-500">Keine Keys</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

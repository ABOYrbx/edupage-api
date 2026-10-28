import { useEffect, useState } from "react";
import { api, fmtDate } from "../lib/api";

type Account = { id: string; alias: string | null; subdomain: string; username: string; status: string; last_used_at: string | null; created_at: string; key_count: number };

export default function Accounts() {
  const [items, setItems] = useState<Account[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ alias: "", subdomain: "login1", username: "", password: "" });
  const [pending, setPending] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");

  async function load() {
    const r = await api<{ items: Account[] }>("/admin/accounts");
    setItems(r.items);
  }
  useEffect(() => { load().catch((e) => setErr(e.message)); }, []);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      const r: any = await api("/admin/accounts", { method: "POST", body: JSON.stringify(form) });
      if (r.status === "2fa_required") {
        setPending(r.pending_token);
      } else {
        setShowAdd(false);
        setForm({ alias: "", subdomain: "login1", username: "", password: "" });
        await load();
      }
    } catch (e: any) { setErr(e.message); }
  }

  async function finish2fa(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await api("/admin/accounts/2fa", { method: "POST", body: JSON.stringify({ pending_token: pending, code }) });
      setPending(null);
      setCode("");
      setShowAdd(false);
      setForm({ alias: "", subdomain: "login1", username: "", password: "" });
      await load();
    } catch (e: any) { setErr(e.message); }
  }

  async function del(id: string) {
    if (!confirm("Konto wirklich löschen?")) return;
    await api(`/admin/accounts/${id}`, { method: "DELETE" });
    await load();
  }

  async function test(id: string) {
    await api(`/admin/accounts/${id}/test`, { method: "POST" });
    await load();
  }

  return (
    <div className="max-w-5xl mx-auto p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">EduPage-Konten</h1>
        <button onClick={() => setShowAdd(!showAdd)} className="bg-blue-600 text-white rounded px-4 py-2">+ Konto hinzufügen</button>
      </div>
      {err && <p className="text-red-600 text-sm">{err}</p>}

      {showAdd && (
        <div className="bg-white shadow rounded-xl p-6 space-y-3">
          {pending ? (
            <form onSubmit={finish2fa} className="space-y-3">
              <p className="text-sm">2FA-Code eingeben:</p>
              <input className="border rounded px-3 py-2 w-full" value={code} onChange={(e) => setCode(e.target.value)} placeholder="123456" />
              <button className="bg-blue-600 text-white rounded px-4 py-2">Bestätigen</button>
            </form>
          ) : (
            <form onSubmit={add} className="space-y-3">
              <input className="border rounded px-3 py-2 w-full" placeholder="Alias (optional)" value={form.alias} onChange={(e) => setForm({ ...form, alias: e.target.value })} />
              <input className="border rounded px-3 py-2 w-full" placeholder="Subdomain" value={form.subdomain} onChange={(e) => setForm({ ...form, subdomain: e.target.value })} />
              <input className="border rounded px-3 py-2 w-full" placeholder="Benutzername" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
              <input className="border rounded px-3 py-2 w-full" type="password" placeholder="Passwort" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
              <button className="bg-blue-600 text-white rounded px-4 py-2">Hinzufügen</button>
            </form>
          )}
        </div>
      )}

      <div className="bg-white shadow rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-100">
            <tr>
              <th className="text-left p-3">Alias</th>
              <th className="text-left p-3">Subdomain</th>
              <th className="text-left p-3">Benutzer</th>
              <th className="text-left p-3">Status</th>
              <th className="text-left p-3">Keys</th>
              <th className="text-left p-3">Zuletzt</th>
              <th className="p-3"></th>
            </tr>
          </thead>
          <tbody>
            {items.map((a) => (
              <tr key={a.id} className="border-t">
                <td className="p-3">{a.alias || "—"}</td>
                <td className="p-3">{a.subdomain}</td>
                <td className="p-3">{a.username}</td>
                <td className="p-3">
                  <span className={`px-2 py-1 rounded text-xs ${a.status === "ok" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>{a.status}</span>
                </td>
                <td className="p-3">{a.key_count}</td>
                <td className="p-3">{fmtDate(a.last_used_at)}</td>
                <td className="p-3 space-x-2">
                  <button onClick={() => test(a.id)} className="text-blue-600">Test</button>
                  <button onClick={() => del(a.id)} className="text-red-600">Löschen</button>
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-gray-500">Keine Konten</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

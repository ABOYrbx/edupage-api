import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";

export default function Login() {
  const [pw, setPw] = useState("");
  const [user, setUser] = useState("admin");
  const [err, setErr] = useState("");
  const nav = useNavigate();
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await api("/admin/login", { method: "POST", body: JSON.stringify({ username: user, password: pw }) });
      nav("/accounts");
    } catch (e: any) {
      setErr(e.message);
    }
  }
  return (
    <div className="min-h-screen flex items-center justify-center">
      <form onSubmit={submit} className="bg-white shadow rounded-xl p-8 w-full max-w-sm space-y-4">
        <h1 className="text-2xl font-bold">edupage-api</h1>
        <p className="text-sm text-gray-500">Admin-Login</p>
        <input className="input w-full border rounded px-3 py-2" placeholder="Benutzername" value={user} onChange={(e) => setUser(e.target.value)} />
        <input className="input w-full border rounded px-3 py-2" type="password" placeholder="Passwort" value={pw} onChange={(e) => setPw(e.target.value)} />
        {err && <p className="text-red-600 text-sm">{err}</p>}
        <button className="w-full bg-blue-600 text-white rounded py-2 font-medium">Anmelden</button>
      </form>
    </div>
  );
}

import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { Alert } from "../components/ui";

export default function Login() {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const location = useLocation();
  const target = (location.state as { from?: string } | null)?.from || "/accounts";

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api("/admin/login", { method: "POST", body: JSON.stringify({ username, password }) });
      nav(target, { replace: true });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">edupage-api</h1>
          <p className="mt-1 text-sm text-slate-500">Anmeldung für die Verwaltung</p>
        </div>
        <div>
          <label className="label" htmlFor="username">
            Benutzername
          </label>
          <input
            id="username"
            className="input"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="password">
            Passwort
          </label>
          <input
            id="password"
            className="input"
            type="password"
            autoComplete="current-password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        <Alert>{error}</Alert>
        <button className="btn-primary w-full" disabled={busy}>
          {busy ? "Anmelden …" : "Anmelden"}
        </button>
      </form>
    </div>
  );
}

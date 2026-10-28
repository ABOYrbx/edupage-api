import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, setUnauthorizedHandler } from "../lib/api";

const NAV = [
  { to: "/accounts", label: "Konten" },
  { to: "/keys", label: "API-Keys" },
  { to: "/activity", label: "Aktivität" },
  { to: "/settings", label: "Einstellungen" },
];

export default function Layout() {
  const [username, setUsername] = useState<string | null>(null);
  const [checked, setChecked] = useState(false);
  const nav = useNavigate();
  const location = useLocation();

  useEffect(() => {
    // A 401 anywhere in the app drops the shell back to the login screen once.
    setUnauthorizedHandler(() => {
      setUsername(null);
      nav("/login", { replace: true, state: { from: location.pathname } });
    });
    return () => setUnauthorizedHandler(null);
  }, [nav, location.pathname]);

  useEffect(() => {
    api<{ username: string }>("/admin/me")
      .then((r) => setUsername(r.username))
      .catch(() => nav("/login", { replace: true, state: { from: location.pathname } }))
      .finally(() => setChecked(true));
  }, [nav, location.pathname]);

  async function logout() {
    try {
      await api("/admin/logout", { method: "POST" });
    } finally {
      setUsername(null);
      nav("/login", { replace: true });
    }
  }

  if (!checked) {
    return <div className="p-10 text-center text-sm text-slate-500">Lade …</div>;
  }
  if (username === null) {
    return <div className="p-10 text-center text-sm text-slate-500">Weiterleitung zur Anmeldung …</div>;
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <span className="font-semibold tracking-tight">edupage-api</span>
          <nav className="order-3 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto sm:flex-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `whitespace-nowrap rounded-lg px-3 py-1.5 text-sm ${
                    isActive ? "bg-slate-100 font-medium text-slate-900" : "text-slate-600 hover:bg-slate-50"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
          <span className="ml-auto hidden text-xs text-slate-500 sm:inline">{username}</span>
          <button onClick={logout} className="btn-secondary">
            Abmelden
          </button>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}

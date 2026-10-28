import { useEffect, useState } from "react";
import { api } from "../lib/api";

export default function Settings() {
  const [values, setValues] = useState<any>(null);
  const [cleared, setCleared] = useState<number | null>(null);
  useEffect(() => { api("/admin/settings").then((r: any) => setValues(r.values)).catch(() => {}); }, []);
  async function clear() {
    const r: any = await api("/admin/cache-clear", { method: "POST", body: JSON.stringify({}) });
    setCleared(r.cleared);
  }
  return (
    <div className="max-w-3xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold">Einstellungen</h1>
      <div className="bg-white shadow rounded-xl p-6 space-y-3">
        <h2 className="font-semibold">Cache</h2>
        <button onClick={clear} className="bg-gray-200 rounded px-4 py-2">Cache leeren</button>
        {cleared !== null && <p className="text-sm text-green-600">{cleared} Einträge gelöscht</p>}
      </div>
      <div className="bg-white shadow rounded-xl p-6">
        <h2 className="font-semibold mb-2">System</h2>
        <pre className="text-xs bg-gray-100 p-3 rounded overflow-auto">{JSON.stringify(values, null, 2)}</pre>
      </div>
    </div>
  );
}

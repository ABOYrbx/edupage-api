import { useEffect, useState } from "react";
import { api, fmtDate } from "../lib/api";

export default function Activity() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  useEffect(() => {
    api<{ items: any[]; total: number }>("/admin/activity?limit=100").then((r) => { setItems(r.items); setTotal(r.total); }).catch(() => {});
  }, []);
  return (
    <div className="max-w-5xl mx-auto p-6 space-y-4">
      <h1 className="text-2xl font-bold">Aktivität ({total})</h1>
      <div className="bg-white shadow rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-100"><tr><th className="text-left p-3">Zeit</th><th className="text-left p-3">Akteur</th><th className="text-left p-3">Aktion</th><th className="text-left p-3">Ergebnis</th><th className="text-left p-3">Detail</th></tr></thead>
          <tbody>
            {items.map((e) => (
              <tr key={e.id} className="border-t">
                <td className="p-3">{fmtDate(e.created_at)}</td>
                <td className="p-3">{e.actor}</td>
                <td className="p-3">{e.action}</td>
                <td className="p-3">{e.outcome}</td>
                <td className="p-3 text-gray-500">{e.detail || ""}</td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={5} className="p-6 text-center text-gray-500">Keine Events</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

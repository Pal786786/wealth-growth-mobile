import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, inr, fmtDate } from "../lib/api";
import { Filter, Download, ArrowDownLeft, ArrowUpRight } from "lucide-react";

export default function Transactions() {
  const [category, setCategory] = useState("");
  const [ttype, setTtype] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["admin-tx", category, ttype],
    queryFn: async () => (await api.get("/admin/transactions", {
      params: { category: category || undefined, ttype: ttype || undefined, limit: 200 },
    })).data as { items: any[]; total: number },
  });

  const exportCSV = () => {
    if (!data?.items) return;
    const headers = ["tx_id", "user_id", "type", "category", "amount", "description", "status", "created_at"];
    const rows = data.items.map((t) => headers.map((h) => JSON.stringify((t as any)[h] ?? "")).join(","));
    const blob = new Blob([headers.join(",") + "\n" + rows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = "mfb-transactions.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy">Transactions</h2>
          <p className="text-sm text-slate-500">{data?.total ?? "—"} total · live ledger across all users.</p>
        </div>
        <button onClick={exportCSV} className="btn-primary gap-2"><Download className="w-4 h-4" /> Export CSV</button>
      </div>

      <div className="card">
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <div className="flex items-center gap-1 text-xs font-bold text-slate-500"><Filter className="w-3.5 h-3.5" /> FILTERS</div>
          <select className="input !py-2 !w-auto" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">All categories</option>
            <option value="topup">Top-up</option>
            <option value="send">Send</option>
            <option value="recharge">Recharge</option>
            <option value="bill">Bill</option>
            <option value="investment">Investment</option>
            <option value="travel">Travel</option>
            <option value="insurance">Insurance</option>
            <option value="cashback">Cashback</option>
            <option value="admin_adjust">Admin adjust</option>
          </select>
          <select className="input !py-2 !w-auto" value={ttype} onChange={(e) => setTtype(e.target.value)}>
            <option value="">All types</option>
            <option value="credit">Credit</option>
            <option value="debit">Debit</option>
          </select>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs font-bold text-slate-500 uppercase tracking-wide">
              <tr className="border-b border-slate-200">
                <th className="py-3 pr-4">Tx ID</th>
                <th className="py-3 pr-4">User</th>
                <th className="py-3 pr-4">Description</th>
                <th className="py-3 pr-4">Category</th>
                <th className="py-3 pr-4 text-right">Amount</th>
                <th className="py-3 pr-4">Status</th>
                <th className="py-3 pr-4">Date</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={7} className="py-6 text-center text-slate-400">Loading…</td></tr>
              ) : data?.items.length === 0 ? (
                <tr><td colSpan={7} className="py-6 text-center text-slate-400">No transactions</td></tr>
              ) : data?.items.map((t) => (
                <tr key={t.tx_id} className="border-b border-slate-100 hover:bg-slate-50/60">
                  <td className="py-3 pr-4 font-mono text-xs">{t.tx_id}</td>
                  <td className="py-3 pr-4 font-mono text-xs">{t.user_id}</td>
                  <td className="py-3 pr-4 max-w-xs truncate">{t.description}</td>
                  <td className="py-3 pr-4"><span className="badge badge-info">{t.category}</span></td>
                  <td className={`py-3 pr-4 text-right font-bold ${t.type === "credit" ? "text-emerald-600" : "text-red-600"}`}>
                    <span className="inline-flex items-center gap-1">
                      {t.type === "credit" ? <ArrowDownLeft className="w-3.5 h-3.5" /> : <ArrowUpRight className="w-3.5 h-3.5" />}
                      {t.type === "credit" ? "+" : "−"}{inr(t.amount)}
                    </span>
                  </td>
                  <td className="py-3 pr-4">
                    {t.status === "success" ? <span className="badge badge-ok">{t.status}</span>
                      : t.status === "failed" ? <span className="badge badge-bad">{t.status}</span>
                      : <span className="badge badge-warn">{t.status}</span>}
                  </td>
                  <td className="py-3 pr-4 text-xs text-slate-500 whitespace-nowrap">{fmtDate(t.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

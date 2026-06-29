import { useEffect, useMemo, useState } from "react";
import { api, inr } from "../lib/api";
import { Wallet, TrendingUp, TrendingDown, Activity, Download, Search, X, RefreshCw } from "lucide-react";

type Tx = {
  tx_id: string; user_id: string; type: "credit"|"debit"; category: string;
  amount: number; status: string; description: string; counterparty?: string;
  provider?: string; reference_id?: string; created_at: string;
};
type Analytics = { series: { date: string; credits: number; debits: number; count: number }[]; totals: { credits: number; debits: number; count: number } };
type PayLogs = { intents: any[]; webhooks: any[]; stats: { intents_total: number; intents_completed: number; intents_pending: number; webhooks_total: number } };

const CATS = ["all", "topup", "deposit", "send", "recharge", "billpay", "booking", "withdraw", "cashback", "reward", "bonus", "referral", "admin_credit", "admin_debit"];

export default function AdminWalletAnalytics() {
  const [tab, setTab] = useState<"transactions"|"analytics"|"payments"|"adjust">("transactions");
  const [txs, setTxs] = useState<Tx[]>([]); const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState({ q: "", type: "all", category: "all", status: "all", date_from: "", date_to: "", user_id: "" });
  const [days, setDays] = useState(30); const [analytics, setAnalytics] = useState<Analytics|null>(null);
  const [payLogs, setPayLogs] = useState<PayLogs|null>(null);
  const [adjust, setAdjust] = useState({ user_id: "", amount: "", reason: "" });
  const [adjMsg, setAdjMsg] = useState(""); const [loading, setLoading] = useState(false);

  const queryParams = useMemo(() => {
    const p = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => { if (v) p.set(k, v as string); });
    return p.toString();
  }, [filters]);

  const loadTxs = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/wallet/transactions?limit=100&${queryParams}`);
      setTxs(data.items || []); setTotal(data.total || 0);
    } finally { setLoading(false); }
  };
  const loadAnalytics = async () => {
    const { data } = await api.get(`/admin/wallet/analytics?days=${days}`);
    setAnalytics(data);
  };
  const loadPayLogs = async () => {
    const { data } = await api.get(`/admin/wallet/payment-logs?limit=50`);
    setPayLogs(data);
  };

  useEffect(() => {
    if (tab === "transactions") loadTxs();
    if (tab === "analytics") loadAnalytics();
    if (tab === "payments") loadPayLogs();
     
  }, [tab, queryParams, days]);

  const exportCSV = () => {
    const token = localStorage.getItem("mfb_admin_token");
    const url = `/api/admin/wallet/transactions.csv?${queryParams}`;
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then(r => r.blob())
      .then(blob => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `MFB_Transactions_${new Date().toISOString().slice(0,10)}.csv`;
        a.click();
      });
  };

  const submitAdjust = async (e: React.FormEvent) => {
    e.preventDefault();
    setAdjMsg("");
    try {
      const { data } = await api.post("/admin/wallet/adjust", {
        user_id: adjust.user_id, amount: Number(adjust.amount), reason: adjust.reason,
      });
      setAdjMsg(`✅ Adjustment posted: ${data.tx?.tx_id}`);
      setAdjust({ user_id: "", amount: "", reason: "" });
    } catch (err: any) {
      setAdjMsg(`❌ ${err?.response?.data?.detail || err.message}`);
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Wallet className="w-6 h-6 text-amber-500" /> Wallet & Payment Gateway
          </h1>
          <p className="text-slate-500 text-sm mt-1">Double-entry ledger · Transactions · Payments · Analytics · Adjustments</p>
        </div>
      </div>

      <div className="flex gap-1 border-b border-slate-200 mb-6">
        {(["transactions","analytics","payments","adjust"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize border-b-2 transition ${tab===t ? "border-amber-500 text-amber-600" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {t === "transactions" ? "Transactions" : t === "analytics" ? "Analytics" : t === "payments" ? "Payment Logs" : "Wallet Adjust"}
          </button>
        ))}
      </div>

      {tab === "transactions" && (
        <div>
          <div className="bg-white border border-slate-200 rounded-xl p-4 mb-4 grid grid-cols-2 md:grid-cols-7 gap-3">
            <div className="col-span-2 relative">
              <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
              <input value={filters.q} onChange={e => setFilters({...filters, q: e.target.value})} placeholder="Search desc / tx_id / counterparty"
                className="w-full border border-slate-200 rounded-lg pl-9 pr-3 py-2 text-sm focus:border-amber-400 outline-none" />
            </div>
            <select value={filters.type} onChange={e => setFilters({...filters, type: e.target.value})}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm">
              <option value="all">All types</option><option value="credit">Credit</option><option value="debit">Debit</option>
            </select>
            <select value={filters.category} onChange={e => setFilters({...filters, category: e.target.value})}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm">
              {CATS.map(c => <option key={c} value={c}>{c === "all" ? "All categories" : c}</option>)}
            </select>
            <select value={filters.status} onChange={e => setFilters({...filters, status: e.target.value})}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm">
              <option value="all">All status</option><option value="success">Success</option><option value="pending">Pending</option><option value="failed">Failed</option>
            </select>
            <input type="date" value={filters.date_from} onChange={e => setFilters({...filters, date_from: e.target.value})}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm" />
            <input type="date" value={filters.date_to} onChange={e => setFilters({...filters, date_to: e.target.value})}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm text-slate-600">{loading ? "Loading…" : <><b>{total}</b> transactions found</>}</div>
            <div className="flex gap-2">
              <button onClick={() => setFilters({ q:"", type:"all", category:"all", status:"all", date_from:"", date_to:"", user_id:"" })}
                className="text-sm px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 flex items-center gap-1"><X className="w-3.5 h-3.5" /> Clear</button>
              <button onClick={loadTxs}
                className="text-sm px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 flex items-center gap-1"><RefreshCw className="w-3.5 h-3.5" /> Refresh</button>
              <button onClick={exportCSV}
                className="text-sm px-3 py-1.5 bg-gradient-to-r from-amber-500 to-amber-600 text-white rounded-lg shadow-sm hover:shadow flex items-center gap-1"><Download className="w-3.5 h-3.5" /> Export CSV</button>
            </div>
          </div>
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
                <tr>
                  <th className="p-3 text-left">Date</th><th className="p-3 text-left">Tx ID</th>
                  <th className="p-3 text-left">User</th><th className="p-3 text-left">Category</th>
                  <th className="p-3 text-left">Description</th><th className="p-3 text-center">Status</th>
                  <th className="p-3 text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {txs.map(t => (
                  <tr key={t.tx_id} className="border-t border-slate-100 hover:bg-slate-50">
                    <td className="p-3 text-slate-500 text-xs">{new Date(t.created_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</td>
                    <td className="p-3 font-mono text-xs">{t.tx_id}</td>
                    <td className="p-3 font-mono text-xs text-slate-500">{t.user_id?.slice(0,16)}…</td>
                    <td className="p-3 capitalize">{t.category?.replace("_"," ")}</td>
                    <td className="p-3 max-w-xs truncate" title={t.description}>{t.description}</td>
                    <td className="p-3 text-center">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${t.status==="success" ? "bg-emerald-50 text-emerald-700" : t.status==="pending" ? "bg-amber-50 text-amber-700" : "bg-rose-50 text-rose-700"}`}>{t.status}</span>
                    </td>
                    <td className={`p-3 text-right font-semibold ${t.type==="credit" ? "text-emerald-600" : "text-rose-600"}`}>
                      {t.type==="credit" ? "+" : "-"}{inr(t.amount)}
                    </td>
                  </tr>
                ))}
                {!txs.length && !loading && (
                  <tr><td colSpan={7} className="p-8 text-center text-slate-400">No transactions match these filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "analytics" && analytics && (
        <div>
          <div className="flex gap-2 mb-4">
            {[7, 30, 90, 180].map(d => (
              <button key={d} onClick={() => setDays(d)} className={`px-3 py-1.5 text-sm rounded-lg border ${days===d ? "bg-amber-500 text-white border-amber-500" : "bg-white border-slate-200 hover:bg-slate-50"}`}>{d}d</button>
            ))}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <StatCard icon={TrendingUp} label="Total Credits" value={inr(analytics.totals.credits)} tone="emerald" />
            <StatCard icon={TrendingDown} label="Total Debits" value={inr(analytics.totals.debits)} tone="rose" />
            <StatCard icon={Activity} label="Transaction Count" value={String(analytics.totals.count)} tone="sky" />
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-5">
            <h3 className="font-bold mb-3">Daily Flow ({days}d)</h3>
            <Bars series={analytics.series} />
          </div>
        </div>
      )}

      {tab === "payments" && payLogs && (
        <div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard label="Total Intents" value={String(payLogs.stats.intents_total)} tone="slate" />
            <StatCard label="Completed" value={String(payLogs.stats.intents_completed)} tone="emerald" />
            <StatCard label="Pending" value={String(payLogs.stats.intents_pending)} tone="amber" />
            <StatCard label="Webhooks Received" value={String(payLogs.stats.webhooks_total)} tone="sky" />
          </div>
          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 bg-slate-50 font-semibold text-sm">Payment Intents</div>
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
                <tr><th className="p-3 text-left">Created</th><th className="p-3 text-left">Intent</th><th className="p-3 text-left">User</th><th className="p-3 text-left">Provider</th><th className="p-3 text-center">Status</th><th className="p-3 text-right">Amount</th></tr>
              </thead>
              <tbody>
                {payLogs.intents.map((p, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="p-3 text-xs text-slate-500">{new Date(p.created_at).toLocaleString("en-IN")}</td>
                    <td className="p-3 font-mono text-xs">{p.intent_id}</td>
                    <td className="p-3 font-mono text-xs text-slate-500">{p.user_id?.slice(0,16)}…</td>
                    <td className="p-3 capitalize">{p.provider}</td>
                    <td className="p-3 text-center"><span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${p.status==="completed" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>{p.status}</span></td>
                    <td className="p-3 text-right font-semibold">{inr(p.amount)}</td>
                  </tr>
                ))}
                {!payLogs.intents.length && <tr><td colSpan={6} className="p-8 text-center text-slate-400">No payment intents yet. Trigger one from the app via /api/wallet/v2/payments/create.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "adjust" && (
        <div className="max-w-xl">
          <form onSubmit={submitAdjust} className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
            <h3 className="text-lg font-bold">Manual Wallet Adjustment</h3>
            <p className="text-sm text-slate-500">Posts a ledger entry. Positive = credit (give user money). Negative = debit (deduct). Every adjustment is audit-logged.</p>
            <input value={adjust.user_id} onChange={e => setAdjust({...adjust, user_id: e.target.value})} required
              placeholder="User ID (e.g. usr_xxxxxxxxxxxx)" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:border-amber-400 outline-none" />
            <input value={adjust.amount} onChange={e => setAdjust({...adjust, amount: e.target.value})} required type="number" step="0.01"
              placeholder="Amount (positive = credit, negative = debit)" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
            <textarea value={adjust.reason} onChange={e => setAdjust({...adjust, reason: e.target.value})} required rows={3}
              placeholder="Reason for adjustment (required, audited)" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
            <button type="submit" className="w-full px-4 py-2 bg-gradient-to-r from-amber-500 to-amber-600 text-white font-semibold rounded-lg shadow-sm hover:shadow">Post Adjustment</button>
            {adjMsg && <div className="text-sm p-3 rounded-lg bg-slate-50 border border-slate-200">{adjMsg}</div>}
          </form>
        </div>
      )}
    </div>
  );
}

function StatCard({ icon: Icon, label, value, tone }: { icon?: any; label: string; value: string; tone: "emerald"|"rose"|"sky"|"amber"|"slate" }) {
  const tones: any = {
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-100",
    rose: "bg-rose-50 text-rose-700 border-rose-100",
    sky: "bg-sky-50 text-sky-700 border-sky-100",
    amber: "bg-amber-50 text-amber-700 border-amber-100",
    slate: "bg-slate-50 text-slate-700 border-slate-100",
  };
  return (
    <div className={`p-5 border rounded-xl ${tones[tone]}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold uppercase tracking-wider opacity-80">{label}</span>
        {Icon && <Icon className="w-5 h-5 opacity-50" />}
      </div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}

function Bars({ series }: { series: any[] }) {
  const max = Math.max(1, ...series.map(s => Math.max(s.credits, s.debits)));
  return (
    <div className="flex items-end gap-1 h-48">
      {series.map((s, i) => (
        <div key={i} className="flex-1 flex flex-col items-center gap-1" title={`${s.date}: ₹${s.credits.toFixed(0)} in / ₹${s.debits.toFixed(0)} out`}>
          <div className="w-full flex flex-col-reverse gap-0.5" style={{ height: "160px" }}>
            <div className="bg-emerald-400 rounded-t" style={{ height: `${(s.credits / max) * 100}%` }} />
            <div className="bg-rose-400" style={{ height: `${(s.debits / max) * 100}%` }} />
          </div>
          <span className="text-[9px] text-slate-400 rotate-45 origin-left whitespace-nowrap">{s.date.slice(5)}</span>
        </div>
      ))}
      {!series.length && <div className="w-full text-center text-slate-400 py-12">No data in this period.</div>}
    </div>
  );
}

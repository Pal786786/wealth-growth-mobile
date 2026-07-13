/**
 * Sprint 12.3 · Phase B — Admin Finance Console
 *
 * Single-page hub with 4 tabs:
 *   1. Dashboard      — KPI cards + Recharts (deposits vs withdrawals, provider status)
 *   2. Reconciliation  — mismatch queue + resolve/retry/ignore/notes
 *   3. Settlements     — Razorpay + Cashfree settlement lists
 *   4. Reports         — on-demand PDF/Excel/CSV exports with filters
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Wallet, ArrowDownLeft, ArrowUpRight, Banknote, PieChart as PieIcon,
  AlertTriangle, RefreshCw, FileText, Download,
  Activity, Zap, X,
} from "lucide-react";
import {
  ResponsiveContainer, ComposedChart, Line, Area, Bar, BarChart,
  XAxis, YAxis, Tooltip, Legend, CartesianGrid, PieChart, Pie, Cell,
} from "recharts";
import { api } from "../lib/api";

// ---------------------------------------------------------------- types
type KpiAmount = { amount: number; count: number };
type Dashboard = {
  range: { key: string; start: string; end: string };
  kpis: {
    total_deposits: KpiAmount; total_withdrawals: KpiAmount;
    wallet_balance: number; platform_liability: number;
    provider_balance: Record<string, number>;
    todays_revenue: number; fees: KpiAmount; gst: KpiAmount;
    refunds: KpiAmount; failed_payments: number;
    pending_withdrawals: number; pending_settlements: number;
    net_revenue: number;
  };
  breakdown: Record<string, KpiAmount>;
  providers: Record<string, { status: string; last_seen: string | null }>;
  charts: { deposits_vs_withdrawals: { deposits: any[]; withdrawals: any[] } };
};

type MismatchRow = {
  pair_key: string; module: string; reference_id: string;
  user_id?: string; status: string; reason: string;
  expected: any; actual: any; delta: { amount: number };
  ran_at: string; admin_notes?: any[];
};

const INR = (n: number | null | undefined) => {
  if (n == null) return "—";
  return "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });
};

const STATUS_COLOR: Record<string, string> = {
  matched: "bg-emerald-100 text-emerald-700 border-emerald-200",
  mismatch: "bg-rose-100 text-rose-700 border-rose-200",
  pending: "bg-amber-100 text-amber-700 border-amber-200",
  manual_review: "bg-orange-100 text-orange-700 border-orange-200",
  resolved_matched: "bg-teal-100 text-teal-700 border-teal-200",
  ignored: "bg-slate-100 text-slate-600 border-slate-200",
  captured: "bg-emerald-100 text-emerald-700 border-emerald-200",
  failed: "bg-rose-100 text-rose-700 border-rose-200",
};

// ---------------------------------------------------------------- Component
export default function AdminFinance() {
  const [tab, setTab] = useState<"dashboard" | "reconciliation" | "settlements" | "reports" | "alerts" | "health">("dashboard");

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black text-brand-navy flex items-center gap-2">
            <Wallet className="w-6 h-6" /> Finance Console
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Reconciliation · Settlements · Reports · Alerts · Health — read-only over the immutable finance journal.
          </p>
        </div>
      </div>

      <div className="flex gap-2 border-b border-slate-200 flex-wrap">
        {(["dashboard", "reconciliation", "settlements", "reports", "alerts", "health"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
                  className={`px-4 py-2 text-sm font-bold ${tab === t
                    ? "text-brand-primary border-b-2 border-brand-primary"
                    : "text-slate-500 hover:text-slate-800"}`}>
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === "dashboard" && <DashboardTab />}
      {tab === "reconciliation" && <ReconciliationTab />}
      {tab === "settlements" && <SettlementsTab />}
      {tab === "reports" && <ReportsTab />}
      {tab === "alerts" && <AlertsTab />}
      {tab === "health" && <HealthTab />}
    </div>
  );
}

// ---------------------------------------------------------------- Dashboard
function DashboardTab() {
  const [range, setRange] = useState<"today" | "week" | "month" | "quarter" | "year">("month");
  const [data, setData] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get<Dashboard>("/admin/finance/dashboard", { params: { range } });
      setData(data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [range]);
  useEffect(() => { load(); }, [load]);

  const chartData = useMemo(() => {
    if (!data) return [];
    const deposits = data.charts.deposits_vs_withdrawals.deposits;
    const withdrawals = data.charts.deposits_vs_withdrawals.withdrawals;
    const byDate: Record<string, any> = {};
    deposits.forEach((d) => (byDate[d.date] = { date: d.date, deposits: d.amount, withdrawals: 0 }));
    withdrawals.forEach((w) => {
      byDate[w.date] = byDate[w.date] || { date: w.date, deposits: 0 };
      byDate[w.date].withdrawals = w.amount;
    });
    return Object.values(byDate).sort((a: any, b: any) => a.date.localeCompare(b.date));
  }, [data]);

  const providerBalancePie = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.kpis.provider_balance).map(([name, val]) => ({
      name, value: Math.abs(Number(val)) || 0,
    }));
  }, [data]);

  const providerColors = ["#0ea5e9", "#8b5cf6", "#f59e0b", "#10b981", "#ef4444", "#64748b"];

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        {(["today", "week", "month", "quarter", "year"] as const).map((r) => (
          <button key={r} onClick={() => setRange(r)}
                  className={`px-3 py-1.5 text-xs font-bold rounded-lg ${range === r
                    ? "bg-brand-navy text-white"
                    : "bg-white text-slate-700 border border-slate-200 hover:border-slate-300"}`}>
            {r.toUpperCase()}
          </button>
        ))}
        <button onClick={load} className="ml-auto p-1.5 text-slate-600 hover:text-brand-navy" aria-label="Refresh">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* KPI grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KpiCard icon={<ArrowDownLeft className="w-5 h-5" />} label="Total Deposits"
                  value={INR(data?.kpis.total_deposits.amount)} sub={`${data?.kpis.total_deposits.count || 0} txns`}
                  tint="emerald" />
        <KpiCard icon={<ArrowUpRight className="w-5 h-5" />} label="Total Withdrawals"
                  value={INR(data?.kpis.total_withdrawals.amount)} sub={`${data?.kpis.total_withdrawals.count || 0} txns`}
                  tint="rose" />
        <KpiCard icon={<Wallet className="w-5 h-5" />} label="Wallet Balance"
                  value={INR(data?.kpis.wallet_balance)} sub="On-platform liability" tint="sky" />
        <KpiCard icon={<Activity className="w-5 h-5" />} label="Net Revenue"
                  value={INR(data?.kpis.net_revenue)} sub="Fees + Forex − Referral" tint="indigo" />
        <KpiCard icon={<Banknote className="w-5 h-5" />} label="Fees Earned"
                  value={INR(data?.kpis.fees.amount)} sub={`${data?.kpis.fees.count || 0} events`} tint="teal" />
        <KpiCard icon={<PieIcon className="w-5 h-5" />} label="GST"
                  value={INR(data?.kpis.gst.amount)} tint="amber" />
        <KpiCard icon={<AlertTriangle className="w-5 h-5" />} label="Pending Withdrawals"
                  value={String(data?.kpis.pending_withdrawals ?? 0)} sub={`${data?.kpis.pending_settlements ?? 0} pending settle`}
                  tint="orange" />
        <KpiCard icon={<Zap className="w-5 h-5" />} label="Failed Payments"
                  value={String(data?.kpis.failed_payments ?? 0)} tint="slate" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-5">
          <p className="font-black text-brand-navy mb-3">Deposits vs Withdrawals</p>
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={chartData}>
              <defs>
                <linearGradient id="depGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" fontSize={10} />
              <YAxis fontSize={10} tickFormatter={(v) => (v > 1000 ? `${(v / 1000).toFixed(0)}k` : v)} />
              <Tooltip formatter={(v: any) => INR(v as number)} />
              <Legend />
              <Area type="monotone" dataKey="deposits" fill="url(#depGrad)" stroke="#10b981" strokeWidth={2} />
              <Bar dataKey="withdrawals" fill="#f43f5e" barSize={16} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-5">
          <p className="font-black text-brand-navy mb-3">Provider Balance</p>
          {providerBalancePie.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={providerBalancePie} innerRadius={45} outerRadius={80} dataKey="value" paddingAngle={2}>
                  {providerBalancePie.map((_, i) => (<Cell key={i} fill={providerColors[i % providerColors.length]} />))}
                </Pie>
                <Tooltip formatter={(v: any) => INR(v as number)} />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-xs text-slate-500 italic text-center py-10">No provider balances</p>
          )}
        </div>
      </div>

      {/* Provider status */}
      <div className="bg-white rounded-2xl border border-slate-200 p-5">
        <p className="font-black text-brand-navy mb-3">Provider Status</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {data && Object.entries(data.providers).map(([name, p]) => (
            <div key={name} className="flex items-center gap-3 p-3 bg-slate-50 rounded-lg border border-slate-100">
              <div className={`w-2.5 h-2.5 rounded-full ${p.status === "healthy" ? "bg-emerald-500 animate-pulse" : p.status === "idle" ? "bg-amber-500" : "bg-slate-400"}`} />
              <div>
                <p className="text-sm font-black text-brand-navy">{name.toUpperCase()}</p>
                <p className="text-[10px] text-slate-500">
                  {p.status.toUpperCase()} · last seen {p.last_seen ? new Date(p.last_seen).toLocaleString() : "—"}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function KpiCard({ icon, label, value, sub, tint }: { icon: React.ReactNode; label: string; value: string; sub?: string; tint: string }) {
  const tintClasses: Record<string, string> = {
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
    rose: "bg-rose-50 text-rose-700 border-rose-200",
    sky: "bg-sky-50 text-sky-700 border-sky-200",
    indigo: "bg-indigo-50 text-indigo-700 border-indigo-200",
    teal: "bg-teal-50 text-teal-700 border-teal-200",
    amber: "bg-amber-50 text-amber-700 border-amber-200",
    orange: "bg-orange-50 text-orange-700 border-orange-200",
    slate: "bg-slate-50 text-slate-700 border-slate-200",
  };
  return (
    <div className={`p-4 rounded-2xl border ${tintClasses[tint]}`}>
      <div className="flex items-center gap-2 mb-1">{icon}<span className="text-[10px] font-bold uppercase tracking-wide">{label}</span></div>
      <p className="text-xl font-black">{value}</p>
      {sub && <p className="text-[10px] text-slate-500 mt-1">{sub}</p>}
    </div>
  );
}

// ---------------------------------------------------------------- Recon Tab
function ReconciliationTab() {
  const [rows, setRows] = useState<MismatchRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [moduleFilter, setModuleFilter] = useState<string>("");
  const [selected, setSelected] = useState<MismatchRow | null>(null);
  const [noteText, setNoteText] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/admin/finance/mismatches", {
        params: { status: statusFilter || undefined, module: moduleFilter || undefined, limit: 100 },
      });
      setRows(data.items);
    } finally { setLoading(false); }
  }, [statusFilter, moduleFilter]);
  useEffect(() => { load(); }, [load]);

  const runRecon = async () => {
    setRunning(true);
    try {
      await api.post("/admin/finance/reconcile", {});
      await load();
    } catch (e) { console.error(e); }
    finally { setRunning(false); }
  };

  const action = async (kind: "retry" | "resolve" | "ignore" | "note", row: MismatchRow, note?: string) => {
    const enc = encodeURIComponent(row.pair_key);
    try {
      await api.post(`/admin/finance/mismatches/${enc}/${kind}`,
                      kind === "retry" ? undefined : { note });
      await load();
      if (kind !== "note") setSelected(null);
      setNoteText("");
    } catch (e: any) { alert(e?.response?.data?.detail || "Failed"); }
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={runRecon} disabled={running}
                className="px-4 py-2 rounded-lg bg-brand-primary text-white font-bold text-sm inline-flex items-center gap-2 disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${running ? "animate-spin" : ""}`} />
          {running ? "Reconciling…" : "Run Reconciliation"}
        </button>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                className="px-3 py-2 rounded-lg border border-slate-200 text-sm">
          <option value="">All statuses (unmatched)</option>
          <option value="mismatch">Mismatch</option>
          <option value="pending">Pending</option>
          <option value="manual_review">Manual Review</option>
          <option value="resolved_matched">Resolved</option>
          <option value="ignored">Ignored</option>
          <option value="matched">Matched</option>
        </select>
        <select value={moduleFilter} onChange={(e) => setModuleFilter(e.target.value)}
                className="px-3 py-2 rounded-lg border border-slate-200 text-sm">
          <option value="">All modules</option>
          {["payments", "withdrawals", "wallet", "gold", "mutual_funds", "forex"].map((m) =>
            <option key={m} value={m}>{m}</option>
          )}
        </select>
        <p className="ml-auto text-xs text-slate-500">{rows.length} row(s)</p>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200 text-xs">
            <tr className="text-slate-600 text-left">
              <th className="p-3">Module</th>
              <th className="p-3">Reference</th>
              <th className="p-3">Status</th>
              <th className="p-3">Reason</th>
              <th className="p-3 text-right">Δ Amount</th>
              <th className="p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="p-8 text-center text-slate-400">Loading…</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={6} className="p-8 text-center text-slate-400">No mismatches ✨</td></tr>
            ) : rows.map((r) => (
              <tr key={r.pair_key} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="p-3 font-mono text-xs">{r.module}</td>
                <td className="p-3 font-mono text-xs">{r.reference_id.slice(0, 22)}…</td>
                <td className="p-3">
                  <span className={`inline-flex px-2 py-0.5 rounded-full border text-[10px] font-bold ${STATUS_COLOR[r.status] || "bg-slate-100 text-slate-700"}`}>
                    {r.status.toUpperCase()}
                  </span>
                </td>
                <td className="p-3 text-xs text-slate-500 italic">{r.reason || "—"}</td>
                <td className="p-3 text-right font-bold text-xs">{r.delta?.amount ? INR(r.delta.amount) : "—"}</td>
                <td className="p-3">
                  <div className="flex gap-1">
                    <button onClick={() => action("retry", r)} className="px-2 py-1 text-[10px] rounded bg-sky-100 text-sky-700 font-bold" title="Retry recon">Retry</button>
                    <button onClick={() => setSelected(r)} className="px-2 py-1 text-[10px] rounded bg-slate-100 text-slate-700 font-bold">Detail</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="fixed inset-0 bg-black/50 z-40 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-2xl w-full max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between p-5 border-b border-slate-200">
              <div>
                <p className="font-black text-brand-navy">Mismatch detail</p>
                <p className="text-xs text-slate-500 font-mono">{selected.pair_key}</p>
              </div>
              <button onClick={() => setSelected(null)} className="p-1"><X className="w-5 h-5" /></button>
            </div>
            <div className="p-5 space-y-3">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <Info label="Status" value={selected.status.toUpperCase()} />
                <Info label="Reason" value={selected.reason || "—"} />
                <Info label="Module" value={selected.module} />
                <Info label="Δ Amount" value={selected.delta?.amount ? INR(selected.delta.amount) : "—"} />
              </div>
              <details className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                <summary className="text-xs font-bold text-slate-600 cursor-pointer">Expected</summary>
                <pre className="text-[10px] mt-2 overflow-auto">{JSON.stringify(selected.expected, null, 2)}</pre>
              </details>
              <details className="bg-slate-50 rounded-lg p-3 border border-slate-200">
                <summary className="text-xs font-bold text-slate-600 cursor-pointer">Actual</summary>
                <pre className="text-[10px] mt-2 overflow-auto">{JSON.stringify(selected.actual, null, 2)}</pre>
              </details>
              {selected.admin_notes && selected.admin_notes.length > 0 && (
                <div>
                  <p className="text-xs font-bold text-slate-600 mb-2">Admin Notes</p>
                  {selected.admin_notes.map((n: any, i: number) => (
                    <div key={i} className="p-2 bg-amber-50 border border-amber-200 rounded text-xs mb-1">
                      <span className="font-bold">{n.action}</span> · {n.by} · {new Date(n.at).toLocaleString()}
                      <p className="text-slate-700 mt-1">{n.note}</p>
                    </div>
                  ))}
                </div>
              )}
              <div className="pt-3">
                <input value={noteText} onChange={(e) => setNoteText(e.target.value)}
                       className="w-full p-2 border border-slate-200 rounded text-sm"
                       placeholder="Add a note (for resolve/ignore/note)" />
              </div>
              <div className="flex gap-2 pt-2">
                <button onClick={() => action("resolve", selected, noteText)}
                        className="flex-1 py-2 text-sm font-bold rounded-lg bg-emerald-600 text-white">Resolve</button>
                <button onClick={() => action("ignore", selected, noteText)}
                        className="flex-1 py-2 text-sm font-bold rounded-lg bg-slate-600 text-white">Ignore</button>
                <button onClick={() => noteText && action("note", selected, noteText)}
                        disabled={!noteText}
                        className="flex-1 py-2 text-sm font-bold rounded-lg bg-amber-500 text-white disabled:opacity-40">Note</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-50 rounded-lg p-3">
      <p className="text-[10px] text-slate-500 font-bold uppercase">{label}</p>
      <p className="font-bold text-slate-800 mt-1">{value}</p>
    </div>
  );
}

// ---------------------------------------------------------------- Settlements
function SettlementsTab() {
  const [provider, setProvider] = useState<"razorpay" | "cashfree">("razorpay");
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.get(`/admin/finance/settlements/${provider}`, { params: { limit: 200 } })
      .then((r) => setRows(r.data.items))
      .finally(() => setLoading(false));
  }, [provider]);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        {(["razorpay", "cashfree"] as const).map((p) => (
          <button key={p} onClick={() => setProvider(p)}
                  className={`px-4 py-2 text-xs font-bold rounded-lg ${provider === p
                    ? "bg-brand-navy text-white"
                    : "bg-white text-slate-700 border border-slate-200"}`}>
            {p.toUpperCase()}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200 text-xs">
            <tr className="text-slate-600 text-left">
              <th className="p-3">Settlement ID</th>
              <th className="p-3">Date</th>
              <th className="p-3 text-right">Amount</th>
              <th className="p-3">Status</th>
              <th className="p-3">UTR</th>
              <th className="p-3 text-right">Delay (h)</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (<tr><td colSpan={6} className="p-8 text-center text-slate-400">Loading…</td></tr>) :
              rows.length === 0 ? (<tr><td colSpan={6} className="p-8 text-center text-slate-400">No settlements yet</td></tr>) :
                rows.map((r) => (
                  <tr key={r.settlement_id} className="border-t border-slate-100">
                    <td className="p-3 font-mono text-xs">{(r.settlement_id || "").slice(0, 26)}</td>
                    <td className="p-3 text-xs">{r.date ? new Date(r.date).toLocaleString() : "—"}</td>
                    <td className="p-3 text-right font-bold">{INR(r.amount)}</td>
                    <td className="p-3"><span className={`inline-flex px-2 py-0.5 rounded-full border text-[10px] font-bold ${STATUS_COLOR[r.status] || "bg-slate-100 text-slate-700"}`}>{(r.status || "").toUpperCase()}</span></td>
                    <td className="p-3 font-mono text-xs">{r.utr || "—"}</td>
                    <td className="p-3 text-right text-xs">{r.delay_hours != null ? r.delay_hours : "—"}</td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Reports
function ReportsTab() {
  const [reportType, setReportType] = useState("monthly");
  const [format, setFormat] = useState<"pdf" | "xlsx" | "csv">("pdf");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [provider, setProvider] = useState("");
  const [busy, setBusy] = useState(false);

  const TYPES = ["daily", "weekly", "monthly", "quarterly", "yearly",
                  "deposit", "withdrawal", "gold", "mf", "forex", "fees", "tax"];

  const download = async () => {
    setBusy(true);
    try {
      const params: any = {};
      if (dateFrom) params.date_from = dateFrom;
      if (dateTo) params.date_to = dateTo;
      if (provider) params.provider = provider;
      const r = await api.get(`/admin/finance/reports/${reportType}.${format}`, {
        params, responseType: "blob",
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mfb_${reportType}_${Date.now()}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      alert(e?.response?.data?.detail || "Export failed");
    } finally { setBusy(false); }
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
        <p className="font-black text-brand-navy flex items-center gap-2"><FileText className="w-4 h-4" />Generate Report</p>
        <Field label="Report Type">
          <select value={reportType} onChange={(e) => setReportType(e.target.value)}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold">
            {TYPES.map((t) => <option key={t} value={t}>{t.toUpperCase()}</option>)}
          </select>
        </Field>
        <Field label="Format">
          <div className="flex gap-2">
            {(["pdf", "xlsx", "csv"] as const).map((f) => (
              <button key={f} onClick={() => setFormat(f)}
                      className={`flex-1 py-2 rounded-lg text-xs font-bold ${format === f
                        ? "bg-brand-primary text-white"
                        : "bg-slate-100 text-slate-700"}`}>
                {f.toUpperCase()}
              </button>
            ))}
          </div>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Date From">
            <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)}
                   className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm" />
          </Field>
          <Field label="Date To">
            <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)}
                   className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm" />
          </Field>
        </div>
        <Field label="Provider (optional)">
          <select value={provider} onChange={(e) => setProvider(e.target.value)}
                  className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold">
            <option value="">All</option>
            <option value="razorpay">Razorpay</option>
            <option value="cashfree">Cashfree</option>
            <option value="gold">Gold</option>
            <option value="mutual_funds">Mutual Funds</option>
          </select>
        </Field>
        <button onClick={download} disabled={busy}
                className="w-full py-3 rounded-xl bg-gradient-to-r from-sky-600 to-blue-700 text-white font-black inline-flex items-center justify-center gap-2">
          {busy ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
          {busy ? "Generating…" : `Download ${format.toUpperCase()}`}
        </button>
        <p className="text-[10px] text-slate-400 italic text-center">Fresh generation each request. Nothing stored server-side.</p>
      </div>

      <div className="bg-gradient-to-br from-slate-50 to-slate-100 rounded-2xl border border-slate-200 p-5">
        <p className="font-black text-brand-navy mb-3">Report Contents</p>
        <ul className="text-xs space-y-2 text-slate-700">
          <li>✓ Executive Summary (KPIs: deposits, withdrawals, wallet balance, liability, revenue, fees, GST)</li>
          <li>✓ Reconciliation Summary (matched / mismatch / pending / manual review by module)</li>
          <li>✓ Settlement Summary (Razorpay + Cashfree)</li>
          <li>✓ Transaction table (first 200 in PDF; full in Excel/CSV)</li>
          <li>✓ Footer with generation timestamp + page numbers</li>
          <li>✓ Company branding (MFB)</li>
        </ul>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[11px] font-bold text-slate-600 uppercase mb-1.5">{label}</label>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------- Alerts Tab
const SEV_TINT: Record<string, string> = {
  critical: "bg-rose-100 text-rose-700 border-rose-300",
  warning: "bg-amber-100 text-amber-700 border-amber-300",
  info: "bg-sky-100 text-sky-700 border-sky-300",
};
const ALERT_STATUS_TINT: Record<string, string> = {
  active: "bg-rose-500 text-white",
  acknowledged: "bg-amber-500 text-white",
  resolved: "bg-emerald-500 text-white",
};

function AlertsTab() {
  const [rows, setRows] = useState<any[]>([]);
  const [summary, setSummary] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("");
  const [sevFilter, setSevFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<any>(null);
  const [noteText, setNoteText] = useState("");
  const [running, setRunning] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [lst, sm] = await Promise.all([
        api.get("/admin/finance/alerts", {
          params: {
            status: statusFilter || undefined,
            severity: sevFilter || undefined,
            type: typeFilter || undefined, q: q || undefined, limit: 200,
          },
        }),
        api.get("/admin/finance/alerts/summary"),
      ]);
      setRows(lst.data.items); setSummary(sm.data);
    } finally { setLoading(false); }
  }, [statusFilter, sevFilter, typeFilter, q]);
  useEffect(() => { load(); }, [load]);

  const evaluate = async () => {
    setRunning(true);
    try { await api.post("/admin/finance/alerts/evaluate"); await load(); }
    finally { setRunning(false); }
  };

  const action = async (kind: "ack" | "resolve" | "note", id: string, note?: string) => {
    await api.post(`/admin/finance/alerts/${id}/${kind}`, { note });
    await load();
    if (kind !== "note") setSelected(null);
    setNoteText("");
  };

  return (
    <div className="space-y-3">
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KpiCard icon={<AlertTriangle className="w-5 h-5" />} label="Critical"
                    value={String(summary.by_severity?.critical || 0)} tint="rose" />
          <KpiCard icon={<AlertTriangle className="w-5 h-5" />} label="Warning"
                    value={String(summary.by_severity?.warning || 0)} tint="amber" />
          <KpiCard icon={<AlertTriangle className="w-5 h-5" />} label="Active"
                    value={String(summary.by_status?.active || 0)} tint="rose" />
          <KpiCard icon={<AlertTriangle className="w-5 h-5" />} label="Resolved"
                    value={String(summary.by_status?.resolved || 0)} tint="emerald" />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button onClick={evaluate} disabled={running}
                className="px-4 py-2 rounded-lg bg-brand-primary text-white font-bold text-sm inline-flex items-center gap-2 disabled:opacity-50">
          <RefreshCw className={`w-4 h-4 ${running ? "animate-spin" : ""}`} />
          {running ? "Evaluating…" : "Evaluate Rules Now"}
        </button>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
                className="px-3 py-2 rounded-lg border border-slate-200 text-sm">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
        </select>
        <select value={sevFilter} onChange={(e) => setSevFilter(e.target.value)}
                className="px-3 py-2 rounded-lg border border-slate-200 text-sm">
          <option value="">All severities</option>
          <option value="critical">Critical</option>
          <option value="warning">Warning</option>
          <option value="info">Info</option>
        </select>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…"
               className="px-3 py-2 rounded-lg border border-slate-200 text-sm w-40" />
        <p className="ml-auto text-xs text-slate-500">{rows.length} row(s)</p>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200 text-xs">
            <tr className="text-slate-600 text-left">
              <th className="p-3">Type</th><th className="p-3">Severity</th>
              <th className="p-3">Status</th><th className="p-3">Message</th>
              <th className="p-3">Created</th><th className="p-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (<tr><td colSpan={6} className="p-8 text-center text-slate-400">Loading…</td></tr>) :
              rows.length === 0 ? (<tr><td colSpan={6} className="p-8 text-center text-slate-400">No alerts ✨</td></tr>) :
                rows.map((r) => (
                  <tr key={r.alert_id} className="border-t border-slate-100 hover:bg-slate-50">
                    <td className="p-3 text-xs font-mono">{r.type}</td>
                    <td className="p-3"><span className={`inline-flex px-2 py-0.5 rounded-full border text-[10px] font-bold ${SEV_TINT[r.severity] || ""}`}>{r.severity.toUpperCase()}</span></td>
                    <td className="p-3"><span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${ALERT_STATUS_TINT[r.status] || "bg-slate-500 text-white"}`}>{r.status.toUpperCase()}</span></td>
                    <td className="p-3 text-xs">{r.message}</td>
                    <td className="p-3 text-[10px] text-slate-500">{new Date(r.created_at).toLocaleString()}</td>
                    <td className="p-3">
                      <div className="flex gap-1">
                        {r.status === "active" && <button onClick={() => action("ack", r.alert_id)} className="px-2 py-1 text-[10px] rounded bg-amber-100 text-amber-700 font-bold">Ack</button>}
                        {r.status !== "resolved" && <button onClick={() => action("resolve", r.alert_id)} className="px-2 py-1 text-[10px] rounded bg-emerald-100 text-emerald-700 font-bold">Resolve</button>}
                        <button onClick={() => setSelected(r)} className="px-2 py-1 text-[10px] rounded bg-slate-100 text-slate-700 font-bold">Detail</button>
                      </div>
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="fixed inset-0 bg-black/50 z-40 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 max-w-xl w-full max-h-[85vh] overflow-y-auto">
            <div className="flex items-center justify-between p-5 border-b border-slate-200">
              <div>
                <p className="font-black text-brand-navy">{selected.label || selected.type}</p>
                <p className="text-xs text-slate-500 font-mono">{selected.alert_id}</p>
              </div>
              <button onClick={() => setSelected(null)} className="p-1"><X className="w-5 h-5" /></button>
            </div>
            <div className="p-5 space-y-3">
              <Info label="Severity" value={selected.severity.toUpperCase()} />
              <Info label="Status" value={selected.status.toUpperCase()} />
              <Info label="Message" value={selected.message} />
              {selected.entity_id && <Info label="Entity" value={selected.entity_id} />}
              {selected.context && (
                <details className="bg-slate-50 rounded p-2 border border-slate-200">
                  <summary className="text-xs font-bold text-slate-600 cursor-pointer">Context</summary>
                  <pre className="text-[10px] mt-2 overflow-auto">{JSON.stringify(selected.context, null, 2)}</pre>
                </details>
              )}
              {selected.notes && selected.notes.length > 0 && (
                <div>
                  <p className="text-xs font-bold text-slate-600 mb-2">Notes</p>
                  {selected.notes.map((n: any, i: number) => (
                    <div key={i} className="p-2 bg-amber-50 border border-amber-200 rounded text-xs mb-1">
                      <span className="font-bold">{n.action}</span> · {n.by} · {new Date(n.at).toLocaleString()}
                      <p className="mt-1">{n.note}</p>
                    </div>
                  ))}
                </div>
              )}
              <input value={noteText} onChange={(e) => setNoteText(e.target.value)}
                     className="w-full p-2 border border-slate-200 rounded text-sm"
                     placeholder="Add a note" />
              <div className="flex gap-2">
                {selected.status === "active" && <button onClick={() => action("ack", selected.alert_id, noteText)} className="flex-1 py-2 text-sm font-bold rounded-lg bg-amber-500 text-white">Acknowledge</button>}
                {selected.status !== "resolved" && <button onClick={() => action("resolve", selected.alert_id, noteText)} className="flex-1 py-2 text-sm font-bold rounded-lg bg-emerald-600 text-white">Resolve</button>}
                <button onClick={() => noteText && action("note", selected.alert_id, noteText)}
                        disabled={!noteText}
                        className="flex-1 py-2 text-sm font-bold rounded-lg bg-slate-600 text-white disabled:opacity-40">Note</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- Health Tab
function HealthTab() {
  const [providers, setProviders] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    const r = await api.get("/admin/finance/health");
    setProviders(r.data.providers);
    setLoading(false);
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]);
  const trigger = async () => {
    await api.post("/admin/finance/jobs/health/trigger");
    await load();
  };
  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <p className="text-xs text-slate-500">Auto-refreshes every 60s. Read-only.</p>
        <button onClick={trigger} className="px-3 py-1.5 rounded-lg bg-brand-navy text-white text-xs font-bold inline-flex items-center gap-1">
          <RefreshCw className={`w-3 h-3 ${loading ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {providers.map((p) => (
          <div key={p.provider} className="bg-white rounded-2xl border border-slate-200 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <p className="font-black text-brand-navy uppercase">{p.provider}</p>
              <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${
                p.status === "online" ? "bg-emerald-100 text-emerald-700" :
                p.status === "degraded" ? "bg-amber-100 text-amber-700" :
                "bg-rose-100 text-rose-700"}`}>{p.status.toUpperCase()}</span>
            </div>
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div><p className="text-slate-500">Requests 24h</p><p className="font-bold">{p.requests_24h ?? 0}</p></div>
              <div><p className="text-slate-500">Error %</p><p className={`font-bold ${p.error_rate_pct > 10 ? "text-rose-600" : "text-slate-800"}`}>{p.error_rate_pct?.toFixed(1) ?? 0}%</p></div>
              <div><p className="text-slate-500">Last Success</p><p className="font-bold text-[10px]">{p.last_success_at ? new Date(p.last_success_at).toLocaleString() : "—"}</p></div>
              <div><p className="text-slate-500">Last Failure</p><p className="font-bold text-[10px]">{p.last_failure_at ? new Date(p.last_failure_at).toLocaleString() : "—"}</p></div>
              <div><p className="text-slate-500">Circuit</p><p className={`font-bold ${p.circuit_breaker === "open" ? "text-rose-600" : "text-emerald-600"}`}>{p.circuit_breaker?.toUpperCase()}</p></div>
              <div><p className="text-slate-500">Backoff</p><p className="font-bold">{p.backoff?.toUpperCase()}</p></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


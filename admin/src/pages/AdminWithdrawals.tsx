import { useEffect, useMemo, useState } from "react";
import { api, inr, fmtDate } from "../lib/api";
import {
  Wallet, Clock, ShieldCheck, XCircle, CheckCircle2, RefreshCw,
  Search, Download, Filter, ChevronRight, X, AlertTriangle,
  TrendingUp, PiggyBank, Timer, RotateCcw, Settings2, Users,
  Landmark, FileText, ArrowRight,
} from "lucide-react";

type Withdrawal = {
  withdrawal_id: string; user_id: string; amount: number; charge: number;
  net_amount: number; status: string; reference_no: string; reason?: string;
  bank_snapshot: { holder_name: string; bank_name: string; ifsc: string; account_masked: string };
  reason_admin?: string; created_at: string; updated_at: string;
  refunded?: boolean; verified_at?: string; approved_at?: string;
  processing_at?: string; completed_at?: string; rejected_at?: string; failed_at?: string;
  user?: { full_name?: string; email?: string; mobile?: string };
};
type Dash = {
  stats: {
    today_count: number;
    pending: { amount: number; count: number };
    approved: { amount: number; count: number };
    processing: { amount: number; count: number };
    completed: { amount: number; count: number };
    rejected: { amount: number; count: number };
    failed: { amount: number; count: number };
  };
  chart: { date: string; by_status: Record<string, { count: number; amount: number }> }[];
};
type Settings = {
  min_amount: number; max_amount: number; daily_max_amount: number; daily_max_count: number;
  charge_type: "flat" | "percentage"; charge_flat: number; charge_percent: number;
  free_threshold: number; promo_waiver: boolean;
  otp_expiry_seconds: number; otp_max_attempts: number; otp_resend_cooldown: number;
  rate_limit_per_hour: number; duplicate_window_seconds: number; processing_time_hours: number;
};

const STATUS_TONE: Record<string, string> = {
  pending: "bg-slate-100 text-slate-700 border-slate-200",
  under_review: "bg-amber-50 text-amber-700 border-amber-200",
  approved: "bg-sky-50 text-sky-700 border-sky-200",
  processing: "bg-indigo-50 text-indigo-700 border-indigo-200",
  completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  rejected: "bg-rose-50 text-rose-700 border-rose-200",
  failed: "bg-red-50 text-red-700 border-red-200",
  cancelled: "bg-slate-100 text-slate-500 border-slate-200",
};
const STATUS_LABEL: Record<string, string> = {
  pending: "Awaiting OTP",
  under_review: "Under Review",
  approved: "Approved",
  processing: "Processing",
  completed: "Completed",
  rejected: "Rejected",
  failed: "Failed",
  cancelled: "Cancelled",
};

export default function AdminWithdrawals() {
  const [tab, setTab] = useState<"dashboard" | "queue" | "settings">("dashboard");
  const [dash, setDash] = useState<Dash | null>(null);
  const [items, setItems] = useState<Withdrawal[]>([]);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState({ q: "", status: "under_review" });
  const [selected, setSelected] = useState<string[]>([]);
  const [detail, setDetail] = useState<Withdrawal | null>(null);
  const [detailTimeline, setDetailTimeline] = useState<any[]>([]);
  const [rejectModal, setRejectModal] = useState<Withdrawal | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  const query = useMemo(() => {
    const p = new URLSearchParams();
    if (filters.q) p.set("q", filters.q);
    if (filters.status && filters.status !== "all") p.set("status", filters.status);
    return p.toString();
  }, [filters]);

  const flashToast = (type: "success" | "error", msg: string) => {
    setToast({ type, msg });
    setTimeout(() => setToast(null), 2600);
  };

  const loadDash = async () => {
    try {
      const { data } = await api.get("/admin/withdrawals/dashboard");
      setDash(data);
    } catch (e: any) {
      flashToast("error", e?.response?.data?.detail || "Failed to load dashboard");
    }
  };
  const loadList = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/withdrawals?limit=200&${query}`);
      setItems(data.items || []);
      setTotal(data.total || 0);
      setSelected([]);
    } catch (e: any) {
      flashToast("error", e?.response?.data?.detail || "Failed to load queue");
    } finally {
      setLoading(false);
    }
  };
  const loadSettings = async () => {
    try {
      const { data } = await api.get("/admin/withdrawals/settings");
      setSettings(data);
    } catch (e: any) {
      flashToast("error", e?.response?.data?.detail || "Failed to load settings");
    }
  };

  useEffect(() => {
    if (tab === "dashboard") loadDash();
    if (tab === "queue") loadList();
    if (tab === "settings") loadSettings();
     
  }, [tab, query]);

  const openDetail = async (w: Withdrawal) => {
    setDetail(w);
    try {
      const { data } = await api.get(`/admin/withdrawals?q=${w.reference_no}`);
      const fresh: Withdrawal | undefined = (data.items || []).find((x: Withdrawal) => x.withdrawal_id === w.withdrawal_id);
      if (fresh) setDetail(fresh);
      const { data: tl } = await api.get(`/admin/withdrawals?limit=1&q=${w.withdrawal_id}`);
      // timeline is embedded in list via separate call; for now show state fields:
      setDetailTimeline(buildTimeline(fresh || w));
      void tl;
    } catch { /* no-op */ }
  };

  const buildTimeline = (w: Withdrawal) => {
    const rows: { at: string; label: string; tone: string }[] = [];
    if (w.created_at) rows.push({ at: w.created_at, label: "Requested", tone: "slate" });
    if (w.verified_at) rows.push({ at: w.verified_at, label: "OTP verified · Under Review", tone: "amber" });
    if (w.approved_at) rows.push({ at: w.approved_at, label: "Approved", tone: "sky" });
    if (w.processing_at) rows.push({ at: w.processing_at, label: "Processing", tone: "indigo" });
    if (w.completed_at) rows.push({ at: w.completed_at, label: "Completed", tone: "emerald" });
    if (w.rejected_at) rows.push({ at: w.rejected_at, label: `Rejected · ${w.reason_admin || ""}`, tone: "rose" });
    if (w.failed_at) rows.push({ at: w.failed_at, label: `Failed · ${w.reason_admin || ""}`, tone: "red" });
    return rows;
  };

  const doAction = async (wid: string, action: "approve" | "processing" | "completed" | "reject" | "failed" | "refund", reason?: string) => {
    setBusyId(wid);
    try {
      if (action === "reject" || action === "failed") {
        await api.post(`/admin/withdrawals/${wid}/${action}`, { reason });
      } else {
        await api.post(`/admin/withdrawals/${wid}/${action}`);
      }
      flashToast("success", `Withdrawal ${action === "reject" ? "rejected" : action}`);
      await Promise.all([loadList(), loadDash()]);
      if (detail?.withdrawal_id === wid) setDetail(null);
      setRejectModal(null); setRejectReason("");
    } catch (e: any) {
      flashToast("error", e?.response?.data?.detail || "Action failed");
    } finally {
      setBusyId(null);
    }
  };

  const doBulk = async (action: "approve" | "processing" | "completed" | "reject", reason?: string) => {
    if (!selected.length) return;
    try {
      const { data } = await api.post("/admin/withdrawals/bulk", { action, ids: selected, reason });
      flashToast("success", `${data.processed}/${data.requested} withdrawals ${action === "reject" ? "rejected" : action}`);
      await loadList();
      await loadDash();
    } catch (e: any) {
      flashToast("error", e?.response?.data?.detail || "Bulk action failed");
    }
  };

  const exportCSV = async () => {
    try {
      const t = localStorage.getItem("mfb_admin_token");
      const r = await fetch("/api/admin/withdrawals/export.csv", { headers: { Authorization: `Bearer ${t}` } });
      const b = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(b);
      a.download = `MFB_Withdrawals_${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      URL.revokeObjectURL(a.href);
      flashToast("success", "CSV exported");
    } catch {
      flashToast("error", "Export failed");
    }
  };

  const saveSettings = async (patch: Partial<Settings>) => {
    if (!settings) return;
    setSavingSettings(true);
    try {
      const { data } = await api.put("/admin/withdrawals/settings", patch);
      setSettings(data.settings);
      flashToast("success", "Settings saved");
    } catch (e: any) {
      flashToast("error", e?.response?.data?.detail || "Save failed");
    } finally {
      setSavingSettings(false);
    }
  };

  return (
    <div className="space-y-6">
      {toast && (
        <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-bold ${toast.type === "success" ? "bg-emerald-600 text-white" : "bg-rose-600 text-white"}`}>
          {toast.msg}
        </div>
      )}

      {/* HERO */}
      <div className="rounded-3xl bg-gradient-to-br from-sky-600 via-blue-700 to-slate-900 p-6 text-white relative overflow-hidden">
        <div className="absolute -right-8 -top-8 opacity-20">
          <Wallet className="w-40 h-40" />
        </div>
        <div className="flex items-center gap-2 text-xs font-bold tracking-widest text-sky-200 uppercase">
          <ShieldCheck className="w-4 h-4" /> Sprint 2 · Withdrawals
        </div>
        <h1 className="text-3xl font-black mt-1">Withdrawal Management</h1>
        <p className="text-sky-100 text-sm mt-1">Approve, reject and settle user bank withdrawals with a full audit trail.</p>
      </div>

      {/* TABS */}
      <div className="flex gap-2 flex-wrap">
        {[
          { k: "dashboard", label: "Overview", icon: TrendingUp },
          { k: "queue", label: `Pending Queue${dash?.stats?.pending?.count ? ` · ${dash.stats.pending.count}` : ""}`, icon: Clock },
          { k: "settings", label: "Limits & Charges", icon: Settings2 },
        ].map((t) => (
          <button
            key={t.k}
            onClick={() => setTab(t.k as any)}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition ${
              tab === t.k ? "bg-brand-navy text-white shadow-lg" : "bg-white border border-slate-200 text-slate-600 hover:border-brand-primary"
            }`}
          >
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {tab === "dashboard" && dash && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: "Today", value: dash.stats.today_count, sub: "requests", icon: Timer, tone: "from-sky-500 to-blue-600" },
              { label: "Under Review", value: dash.stats.pending.count, sub: inr(dash.stats.pending.amount), icon: Clock, tone: "from-amber-500 to-orange-600" },
              { label: "Approved / Processing", value: dash.stats.approved.count + dash.stats.processing.count, sub: inr(dash.stats.approved.amount + dash.stats.processing.amount), icon: ShieldCheck, tone: "from-indigo-500 to-blue-700" },
              { label: "Completed", value: dash.stats.completed.count, sub: inr(dash.stats.completed.amount), icon: CheckCircle2, tone: "from-emerald-500 to-teal-600" },
            ].map((c) => (
              <div key={c.label} className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
                <div className={`w-11 h-11 rounded-xl bg-gradient-to-br ${c.tone} flex items-center justify-center text-white mb-3`}>
                  <c.icon className="w-5 h-5" />
                </div>
                <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">{c.label}</p>
                <p className="text-3xl font-black text-brand-navy mt-1">{c.value}</p>
                <p className="text-xs text-slate-500 font-semibold mt-1">{c.sub}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 bg-white rounded-2xl p-5 border border-slate-200">
              <div className="flex items-center justify-between mb-4">
                <p className="font-black text-brand-navy">Last 7 Days · By Status</p>
                <button onClick={loadDash} className="text-xs text-brand-primary hover:underline inline-flex items-center gap-1"><RefreshCw className="w-3 h-3" />Refresh</button>
              </div>
              <div className="grid grid-cols-7 gap-2">
                {dash.chart.map((d) => {
                  const totalAmt = Object.values(d.by_status).reduce((a, b) => a + b.amount, 0);
                  const totalCount = Object.values(d.by_status).reduce((a, b) => a + b.count, 0);
                  const maxAmt = Math.max(1, ...dash.chart.map((x) => Object.values(x.by_status).reduce((a, b) => a + b.amount, 0)));
                  const h = Math.max(6, Math.round((totalAmt / maxAmt) * 100));
                  return (
                    <div key={d.date} className="flex flex-col items-center gap-1">
                      <div className="w-full h-32 bg-slate-50 rounded-lg relative flex items-end overflow-hidden">
                        <div className="w-full bg-gradient-to-t from-sky-500 to-brand-primary" style={{ height: `${h}%` }} />
                        <div className="absolute inset-0 flex items-center justify-center text-[10px] font-black text-brand-navy">{totalCount || ""}</div>
                      </div>
                      <p className="text-[9px] text-slate-500 font-bold">{d.date.slice(5)}</p>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="bg-gradient-to-br from-brand-navy to-slate-800 rounded-2xl p-5 text-white">
              <p className="text-xs font-bold uppercase tracking-widest text-sky-300">Failed / Rejected</p>
              <div className="mt-4 space-y-3">
                <div className="flex justify-between items-baseline">
                  <span className="text-sm">Rejected</span>
                  <span className="font-black">{dash.stats.rejected.count} · {inr(dash.stats.rejected.amount)}</span>
                </div>
                <div className="flex justify-between items-baseline">
                  <span className="text-sm">Failed</span>
                  <span className="font-black">{dash.stats.failed.count} · {inr(dash.stats.failed.amount)}</span>
                </div>
                <div className="pt-3 border-t border-white/10 text-xs text-sky-200">
                  All rejections & failures automatically refund money back to the user wallet.
                </div>
              </div>
              <button
                onClick={() => { setTab("queue"); setFilters({ q: "", status: "under_review" }); }}
                className="w-full mt-4 py-2.5 rounded-xl bg-brand-primary text-white font-bold text-sm inline-flex items-center justify-center gap-2 hover:bg-sky-500"
              >
                Open Pending Queue <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {tab === "queue" && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-200 flex flex-wrap items-center gap-3">
            <div className="flex-1 min-w-[220px] relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                placeholder="Search by reference, ID, holder…"
                value={filters.q}
                onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
                className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 text-sm focus:border-brand-primary focus:ring-2 focus:ring-sky-100 outline-none"
              />
            </div>
            <select
              value={filters.status}
              onChange={(e) => setFilters((f) => ({ ...f, status: e.target.value }))}
              className="px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold"
            >
              <option value="all">All Statuses</option>
              <option value="under_review">Under Review</option>
              <option value="approved">Approved</option>
              <option value="processing">Processing</option>
              <option value="completed">Completed</option>
              <option value="rejected">Rejected</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
              <option value="pending">Pending (OTP)</option>
            </select>
            <button onClick={loadList} className="px-3 py-2.5 rounded-xl border border-slate-200 text-slate-600 hover:border-brand-primary" title="Refresh"><RefreshCw className="w-4 h-4" /></button>
            <button onClick={exportCSV} className="inline-flex items-center gap-2 px-3 py-2.5 rounded-xl bg-slate-900 text-white text-sm font-bold hover:bg-black"><Download className="w-4 h-4" />CSV</button>
          </div>

          {selected.length > 0 && (
            <div className="px-4 py-3 bg-sky-50 border-b border-sky-200 flex items-center gap-3 flex-wrap">
              <span className="text-sm font-bold text-brand-navy">{selected.length} selected</span>
              <button onClick={() => doBulk("approve")} className="px-3 py-1.5 rounded-lg bg-sky-600 text-white text-xs font-bold hover:bg-sky-700">Approve</button>
              <button onClick={() => doBulk("processing")} className="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-bold hover:bg-indigo-700">Mark Processing</button>
              <button onClick={() => doBulk("completed")} className="px-3 py-1.5 rounded-lg bg-emerald-600 text-white text-xs font-bold hover:bg-emerald-700">Mark Completed</button>
              <button onClick={() => { const r = prompt("Rejection reason?"); if (r) doBulk("reject", r); }} className="px-3 py-1.5 rounded-lg bg-rose-600 text-white text-xs font-bold hover:bg-rose-700">Reject</button>
              <button onClick={() => setSelected([])} className="ml-auto text-xs text-slate-500 hover:underline">Clear</button>
            </div>
          )}

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs font-black text-slate-500 uppercase tracking-wide">
                <tr>
                  <th className="p-3 text-left w-8">
                    <input type="checkbox" checked={items.length > 0 && selected.length === items.length} onChange={(e) => setSelected(e.target.checked ? items.map((x) => x.withdrawal_id) : [])} />
                  </th>
                  <th className="p-3 text-left">Reference</th>
                  <th className="p-3 text-left">User</th>
                  <th className="p-3 text-left">Bank</th>
                  <th className="p-3 text-right">Amount</th>
                  <th className="p-3 text-left">Status</th>
                  <th className="p-3 text-left">Requested</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading ? (
                  <tr><td colSpan={8} className="p-10 text-center text-slate-400"><RefreshCw className="w-5 h-5 mx-auto animate-spin" /></td></tr>
                ) : items.length === 0 ? (
                  <tr><td colSpan={8} className="p-16 text-center text-slate-400"><PiggyBank className="w-10 h-10 mx-auto mb-2 opacity-40" /><p className="font-semibold">No withdrawals in this filter.</p></td></tr>
                ) : items.map((w) => (
                  <tr key={w.withdrawal_id} className="hover:bg-slate-50">
                    <td className="p-3">
                      <input type="checkbox" checked={selected.includes(w.withdrawal_id)} onChange={(e) => setSelected((s) => e.target.checked ? [...s, w.withdrawal_id] : s.filter((x) => x !== w.withdrawal_id))} />
                    </td>
                    <td className="p-3">
                      <p className="font-black text-brand-navy">{w.reference_no}</p>
                      <p className="text-[10px] text-slate-400 font-mono">{w.withdrawal_id}</p>
                    </td>
                    <td className="p-3">
                      <p className="font-bold text-slate-800">{w.user?.full_name || "—"}</p>
                      <p className="text-[11px] text-slate-500">{w.user?.mobile || w.user?.email || w.user_id.slice(0, 12)}</p>
                    </td>
                    <td className="p-3">
                      <p className="font-bold text-slate-800 truncate max-w-[180px]">{w.bank_snapshot.bank_name}</p>
                      <p className="text-[11px] text-slate-500 font-mono">{w.bank_snapshot.account_masked} · {w.bank_snapshot.ifsc}</p>
                    </td>
                    <td className="p-3 text-right">
                      <p className="font-black text-brand-navy">{inr(w.amount)}</p>
                      {w.charge > 0 && <p className="text-[10px] text-slate-400">chg {inr(w.charge)}</p>}
                    </td>
                    <td className="p-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] font-bold ${STATUS_TONE[w.status] || ""}`}>
                        {STATUS_LABEL[w.status] || w.status}
                      </span>
                      {w.refunded && <p className="text-[10px] text-emerald-600 font-bold mt-1">✓ Refunded</p>}
                    </td>
                    <td className="p-3 text-xs text-slate-500">{fmtDate(w.created_at)}</td>
                    <td className="p-3 text-right">
                      <button onClick={() => openDetail(w)} className="text-brand-primary text-xs font-bold hover:underline inline-flex items-center gap-1">
                        Manage <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="p-3 border-t border-slate-100 text-xs text-slate-500">
            Showing {items.length} of {total}
          </div>
        </div>
      )}

      {tab === "settings" && settings && (
        <SettingsPanel settings={settings} onSave={saveSettings} saving={savingSettings} />
      )}

      {/* DETAIL DRAWER */}
      {detail && (
        <div className="fixed inset-0 z-40 flex" onClick={() => setDetail(null)}>
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
          <div className="ml-auto relative w-full max-w-xl h-full bg-white shadow-2xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 bg-gradient-to-r from-sky-600 to-blue-700 text-white p-5 flex items-start justify-between">
              <div>
                <p className="text-xs font-bold tracking-widest uppercase text-sky-200">Withdrawal · {detail.reference_no}</p>
                <p className="text-2xl font-black mt-1">{inr(detail.amount)}</p>
                <p className="text-xs text-sky-100 mt-1">to {detail.bank_snapshot.holder_name} · {detail.bank_snapshot.account_masked}</p>
              </div>
              <button onClick={() => setDetail(null)} className="p-1 hover:bg-white/10 rounded"><X className="w-5 h-5" /></button>
            </div>

            <div className="p-5 space-y-5">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="bg-slate-50 p-3 rounded-lg">
                  <p className="text-[10px] uppercase text-slate-500 font-bold tracking-wide">Status</p>
                  <p className="mt-1">
                    <span className={`inline-flex px-2 py-0.5 rounded-full border text-xs font-bold ${STATUS_TONE[detail.status]}`}>{STATUS_LABEL[detail.status]}</span>
                  </p>
                </div>
                <div className="bg-slate-50 p-3 rounded-lg">
                  <p className="text-[10px] uppercase text-slate-500 font-bold tracking-wide">Net after charge</p>
                  <p className="font-black text-brand-navy">{inr(detail.net_amount)}</p>
                </div>
                <div className="bg-slate-50 p-3 rounded-lg col-span-2">
                  <p className="text-[10px] uppercase text-slate-500 font-bold tracking-wide">Bank</p>
                  <p className="font-bold text-slate-800">{detail.bank_snapshot.bank_name}</p>
                  <p className="text-xs text-slate-500 font-mono">{detail.bank_snapshot.ifsc} · {detail.bank_snapshot.account_masked}</p>
                </div>
                {detail.reason && (
                  <div className="bg-slate-50 p-3 rounded-lg col-span-2">
                    <p className="text-[10px] uppercase text-slate-500 font-bold tracking-wide">User note</p>
                    <p className="text-sm text-slate-700">{detail.reason}</p>
                  </div>
                )}
                {detail.reason_admin && (
                  <div className="bg-rose-50 p-3 rounded-lg col-span-2 border border-rose-200">
                    <p className="text-[10px] uppercase text-rose-600 font-bold tracking-wide">Admin action reason</p>
                    <p className="text-sm text-rose-700 font-semibold">{detail.reason_admin}</p>
                  </div>
                )}
              </div>

              {/* USER */}
              <div className="border border-slate-200 rounded-xl p-3 flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-brand-primary/20 text-brand-primary flex items-center justify-center font-black">
                  <Users className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-bold text-slate-800 truncate">{detail.user?.full_name || detail.user_id}</p>
                  <p className="text-xs text-slate-500 truncate">{detail.user?.email} · {detail.user?.mobile}</p>
                </div>
              </div>

              {/* TIMELINE */}
              <div>
                <p className="font-black text-brand-navy mb-2 flex items-center gap-2"><Clock className="w-4 h-4" /> Status timeline</p>
                <div className="space-y-2">
                  {detailTimeline.map((t, i) => (
                    <div key={i} className="flex gap-3 items-start">
                      <div className={`w-2 h-2 rounded-full mt-2 bg-${t.tone}-500`} />
                      <div className="flex-1 border-l-2 border-slate-100 pl-3 pb-2">
                        <p className="text-sm font-bold text-slate-800">{t.label}</p>
                        <p className="text-[11px] text-slate-500">{fmtDate(t.at)}</p>
                      </div>
                    </div>
                  ))}
                  {detailTimeline.length === 0 && <p className="text-xs text-slate-500">—</p>}
                </div>
              </div>

              {/* ACTIONS */}
              <div className="space-y-2">
                <p className="font-black text-brand-navy">Actions</p>
                <div className="grid grid-cols-2 gap-2">
                  {detail.status === "under_review" && (
                    <>
                      <button disabled={busyId === detail.withdrawal_id} onClick={() => doAction(detail.withdrawal_id, "approve")} className="py-2.5 rounded-lg bg-sky-600 text-white font-bold text-sm hover:bg-sky-700 disabled:opacity-50 inline-flex items-center justify-center gap-2"><ShieldCheck className="w-4 h-4" />Approve</button>
                      <button disabled={busyId === detail.withdrawal_id} onClick={() => setRejectModal(detail)} className="py-2.5 rounded-lg bg-rose-600 text-white font-bold text-sm hover:bg-rose-700 disabled:opacity-50 inline-flex items-center justify-center gap-2"><XCircle className="w-4 h-4" />Reject</button>
                    </>
                  )}
                  {detail.status === "approved" && (
                    <>
                      <button disabled={busyId === detail.withdrawal_id} onClick={() => doAction(detail.withdrawal_id, "processing")} className="py-2.5 rounded-lg bg-indigo-600 text-white font-bold text-sm hover:bg-indigo-700 disabled:opacity-50 inline-flex items-center justify-center gap-2"><Timer className="w-4 h-4" />Mark Processing</button>
                      <button disabled={busyId === detail.withdrawal_id} onClick={() => doAction(detail.withdrawal_id, "completed")} className="py-2.5 rounded-lg bg-emerald-600 text-white font-bold text-sm hover:bg-emerald-700 disabled:opacity-50 inline-flex items-center justify-center gap-2"><CheckCircle2 className="w-4 h-4" />Mark Completed</button>
                    </>
                  )}
                  {detail.status === "processing" && (
                    <>
                      <button disabled={busyId === detail.withdrawal_id} onClick={() => doAction(detail.withdrawal_id, "completed")} className="py-2.5 rounded-lg bg-emerald-600 text-white font-bold text-sm hover:bg-emerald-700 disabled:opacity-50 inline-flex items-center justify-center gap-2"><CheckCircle2 className="w-4 h-4" />Mark Completed</button>
                      <button disabled={busyId === detail.withdrawal_id} onClick={() => { const r = prompt("Failure reason?"); if (r) doAction(detail.withdrawal_id, "failed", r); }} className="py-2.5 rounded-lg bg-red-600 text-white font-bold text-sm hover:bg-red-700 disabled:opacity-50 inline-flex items-center justify-center gap-2"><AlertTriangle className="w-4 h-4" />Mark Failed</button>
                    </>
                  )}
                  {detail.status === "completed" && !detail.refunded && (
                    <button disabled={busyId === detail.withdrawal_id} onClick={() => { if (confirm(`Refund ${inr(detail.amount)} back to user wallet? This is irreversible.`)) doAction(detail.withdrawal_id, "refund"); }} className="col-span-2 py-2.5 rounded-lg bg-amber-600 text-white font-bold text-sm hover:bg-amber-700 disabled:opacity-50 inline-flex items-center justify-center gap-2"><RotateCcw className="w-4 h-4" />Refund to Wallet</button>
                  )}
                  {["rejected", "failed", "cancelled"].includes(detail.status) && (
                    <div className="col-span-2 bg-emerald-50 border border-emerald-200 rounded-lg p-3 text-xs text-emerald-700 font-semibold flex items-start gap-2">
                      <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
                      <span>Funds have been auto-refunded to the user&apos;s wallet on state transition.</span>
                    </div>
                  )}
                </div>
                <a
                  href={`/api/wallet/withdrawals/${detail.withdrawal_id}/receipt.pdf`}
                  target="_blank" rel="noreferrer"
                  className="w-full mt-2 py-2.5 rounded-lg border border-slate-200 text-slate-700 font-bold text-sm hover:bg-slate-50 inline-flex items-center justify-center gap-2"
                >
                  <FileText className="w-4 h-4" /> View PDF Receipt
                </a>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* REJECT MODAL */}
      {rejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 shadow-2xl">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-11 h-11 rounded-xl bg-rose-100 text-rose-600 flex items-center justify-center"><XCircle className="w-6 h-6" /></div>
              <div>
                <h3 className="font-black text-brand-navy">Reject Withdrawal</h3>
                <p className="text-xs text-slate-500">{rejectModal.reference_no} · {inr(rejectModal.amount)}</p>
              </div>
            </div>
            <p className="text-sm text-slate-600 mb-2">Funds will be automatically refunded to the user&apos;s wallet and they&apos;ll be notified.</p>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={3}
              placeholder="Reason (visible to user)"
              className="w-full p-3 rounded-xl border border-slate-200 text-sm focus:border-rose-500 outline-none"
            />
            <div className="flex gap-2 mt-4">
              <button onClick={() => { setRejectModal(null); setRejectReason(""); }} className="flex-1 py-2.5 rounded-xl border border-slate-200 font-bold text-sm">Cancel</button>
              <button
                disabled={!rejectReason.trim() || busyId === rejectModal.withdrawal_id}
                onClick={() => doAction(rejectModal.withdrawal_id, "reject", rejectReason.trim())}
                className="flex-1 py-2.5 rounded-xl bg-rose-600 text-white font-bold text-sm hover:bg-rose-700 disabled:opacity-50"
              >
                Reject & Refund
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SettingsPanel({ settings, onSave, saving }: { settings: Settings; onSave: (p: Partial<Settings>) => Promise<void>; saving: boolean }) {
  const [s, setS] = useState<Settings>(settings);
  useEffect(() => setS(settings), [settings]);
  const num = (k: keyof Settings) => ({
    value: s[k] as any,
    onChange: (e: any) => setS({ ...s, [k]: parseFloat(e.target.value) || 0 }),
    type: "number" as const,
    className: "w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold focus:border-brand-primary outline-none",
  });
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
        <p className="font-black text-brand-navy flex items-center gap-2"><Landmark className="w-4 h-4" />Amount Limits</p>
        <Field label="Minimum per request (₹)" hint="Users can't withdraw below this."><input {...num("min_amount")} /></Field>
        <Field label="Maximum per request (₹)" hint="Cap on a single withdrawal."><input {...num("max_amount")} /></Field>
        <Field label="Daily cap – amount (₹)" hint="Cumulative daily ceiling per user."><input {...num("daily_max_amount")} /></Field>
        <Field label="Daily cap – count" hint="Max # requests per user per day."><input {...num("daily_max_count")} /></Field>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
        <p className="font-black text-brand-navy flex items-center gap-2"><TrendingUp className="w-4 h-4" />Charges</p>
        <Field label="Global waiver (promo)" hint="If ON, zero charges regardless of below.">
          <label className="inline-flex items-center gap-2">
            <input type="checkbox" checked={s.promo_waiver} onChange={(e) => setS({ ...s, promo_waiver: e.target.checked })} />
            <span className="text-sm font-semibold">{s.promo_waiver ? "Free for everyone" : "Charges apply"}</span>
          </label>
        </Field>
        <Field label="Charge type">
          <select value={s.charge_type} onChange={(e) => setS({ ...s, charge_type: e.target.value as any })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold">
            <option value="flat">Flat (₹)</option>
            <option value="percentage">Percentage (%)</option>
          </select>
        </Field>
        {s.charge_type === "flat" ? (
          <Field label="Flat charge (₹)"><input {...num("charge_flat")} /></Field>
        ) : (
          <Field label="Percentage (%)"><input {...num("charge_percent")} step="0.01" /></Field>
        )}
        <Field label="Free above (₹)" hint="Set 0 to disable. Amounts ≥ this threshold are free."><input {...num("free_threshold")} /></Field>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
        <p className="font-black text-brand-navy flex items-center gap-2"><ShieldCheck className="w-4 h-4" />OTP & Security</p>
        <Field label="OTP validity (seconds)"><input {...num("otp_expiry_seconds")} /></Field>
        <Field label="Max OTP attempts"><input {...num("otp_max_attempts")} /></Field>
        <Field label="OTP resend cooldown (seconds)"><input {...num("otp_resend_cooldown")} /></Field>
        <Field label="Rate limit (requests/hour)"><input {...num("rate_limit_per_hour")} /></Field>
        <Field label="Duplicate window (seconds)"><input {...num("duplicate_window_seconds")} /></Field>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
        <p className="font-black text-brand-navy flex items-center gap-2"><Timer className="w-4 h-4" />SLA</p>
        <Field label="Advertised processing time (hours)" hint="Shown to users in the app."><input {...num("processing_time_hours")} /></Field>
        <div className="pt-3">
          <button
            onClick={() => onSave(s)}
            disabled={saving}
            className="w-full py-3 rounded-xl bg-gradient-to-r from-sky-600 to-blue-700 text-white font-black text-sm inline-flex items-center justify-center gap-2 hover:from-sky-700 hover:to-blue-800 disabled:opacity-50"
          >
            {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <CheckCircle2 className="w-4 h-4" />}
            {saving ? "Saving..." : "Save All Settings"}
          </button>
          <p className="text-xs text-slate-500 mt-2 text-center">Changes apply immediately to new withdrawals. Audit-logged.</p>
        </div>
      </div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs font-bold text-slate-600 uppercase tracking-wide block mb-1">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-slate-400 mt-1">{hint}</p>}
    </div>
  );
}

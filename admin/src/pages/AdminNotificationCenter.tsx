import { useEffect, useMemo, useState } from "react";
import { api, fmtDate } from "../lib/api";
import {
  Bell, Send, RefreshCw, Search, Users, User, PieChart, TrendingUp,
  Image as ImageIcon, Clock, X, ChevronRight, ShieldCheck, AlertTriangle,
  MousePointerClick, Check, Ban,
} from "lucide-react";

type Campaign = {
  campaign_id: string; title: string; body: string; category: string; priority: string;
  target_type: string; target_segment?: string; target_user_id?: string;
  status: string; total_targets: number; sent_count: number; skipped_count: number; opened: number;
  created_at: string; sent_at?: string; schedule_at?: string; expires_at?: string;
  deeplink?: string; image?: string;
};
type Analytics = {
  range_days: number;
  totals: { sent: number; delivered: number; opened: number; failed: number; ctr_pct: number; campaigns: number };
  chart: { date: string; sent: number; opened: number }[];
  per_category: { category: string; label: string; sent: number; opened: number; ctr_pct: number }[];
};

const CATEGORIES = [
  { k: "wallet", label: "Wallet" }, { k: "withdrawals", label: "Withdrawals" },
  { k: "kyc", label: "KYC" }, { k: "ai", label: "AI Advisor" },
  { k: "investments", label: "Investments" }, { k: "gold", label: "Gold" }, { k: "sip", label: "SIP" },
  { k: "promotions", label: "Promotions" }, { k: "security", label: "Security" },
  { k: "announcements", label: "Announcements" }, { k: "system", label: "System" },
];
const SEGMENTS = [
  { k: "kyc_pending", label: "KYC Pending" }, { k: "kyc_approved", label: "KYC Approved" },
  { k: "wallet_users", label: "Wallet Users (bal > 0)" }, { k: "premium_users", label: "Premium Users" },
];
const PRIORITIES = ["low", "normal", "high", "critical"];

export default function AdminNotificationCenter() {
  const [tab, setTab] = useState<"compose" | "campaigns" | "analytics" | "audit">("compose");
  return (
    <div className="space-y-6">
      <div className="rounded-3xl bg-gradient-to-br from-indigo-700 via-blue-700 to-slate-900 p-6 text-white relative overflow-hidden">
        <div className="absolute -right-6 -top-8 opacity-20"><Bell className="w-40 h-40" /></div>
        <div className="flex items-center gap-2 text-xs font-bold tracking-widest uppercase text-sky-200">
          <ShieldCheck className="w-4 h-4" /> Sprint 5 · Notification Center
        </div>
        <h1 className="text-3xl font-black mt-1">Push Notifications</h1>
        <p className="text-sky-100 text-sm mt-1">Compose, target, schedule and analyse — all with preference-aware delivery.</p>
      </div>

      <div className="flex gap-2 flex-wrap">
        {[
          { k: "compose", label: "Compose", icon: Send },
          { k: "campaigns", label: "Campaigns", icon: Bell },
          { k: "analytics", label: "Analytics", icon: TrendingUp },
          { k: "audit", label: "Audit", icon: ShieldCheck },
        ].map((t) => (
          <button key={t.k} onClick={() => setTab(t.k as any)}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition ${tab === t.k ? "bg-brand-navy text-white shadow-lg" : "bg-white border border-slate-200 text-slate-600 hover:border-brand-primary"}`}>
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {tab === "compose" && <Compose />}
      {tab === "campaigns" && <Campaigns />}
      {tab === "analytics" && <AnalyticsView />}
      {tab === "audit" && <Audit />}
    </div>
  );
}

function Compose() {
  const [form, setForm] = useState({
    title: "", body: "", category: "announcements", priority: "normal",
    target_type: "all" as "all" | "user" | "segment",
    target_user_id: "", target_segment: "kyc_approved",
    deeplink: "/", image: "", action_label: "", schedule_at: "", expires_at: "", send_push: true,
  });
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ type: "ok" | "err"; msg: string } | null>(null);
  const [preview, setPreview] = useState(false);

  const canSend = form.title.trim().length >= 2 && form.body.trim().length >= 2 &&
    (form.target_type !== "user" || form.target_user_id.trim().length > 0);

  const send = async () => {
    setBusy(true);
    try {
      const payload: any = { ...form };
      if (!payload.schedule_at) delete payload.schedule_at;
      if (!payload.expires_at) delete payload.expires_at;
      if (!payload.image) delete payload.image;
      if (!payload.action_label) delete payload.action_label;
      const { data } = await api.post("/admin/notifications/compose", payload);
      setToast({ type: "ok", msg: `Campaign ${data.campaign.status === "scheduled" ? "scheduled" : "sent"} · ${data.campaign.total_targets} target(s)` });
      setTimeout(() => setToast(null), 3600);
      setForm({ ...form, title: "", body: "" });
    } catch (e: any) {
      setToast({ type: "err", msg: e?.response?.data?.detail || "Failed" });
      setTimeout(() => setToast(null), 3600);
    } finally { setBusy(false); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      {toast && (<div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-bold ${toast.type === "ok" ? "bg-emerald-600 text-white" : "bg-rose-600 text-white"}`}>{toast.msg}</div>)}
      <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
        <p className="font-black text-brand-navy">Message</p>
        <Field label="Title"><input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} maxLength={140} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold focus:border-brand-primary outline-none" placeholder="Important update..." /></Field>
        <Field label={`Body (${form.body.length}/1000)`}><textarea value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} rows={4} maxLength={1000} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm focus:border-brand-primary outline-none" placeholder="Message body — supports emojis 🎉" /></Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Category"><select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold">{CATEGORIES.map((c) => <option key={c.k} value={c.k}>{c.label}</option>)}</select></Field>
          <Field label="Priority"><select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold">{PRIORITIES.map((p) => <option key={p} value={p}>{p.toUpperCase()}</option>)}</select></Field>
        </div>

        <Field label="Deep Link (in-app route)"><input value={form.deeplink} onChange={(e) => setForm({ ...form, deeplink: e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-mono" placeholder="/wallet or /withdrawals" /></Field>
        <Field label="Image URL (optional)"><input value={form.image} onChange={(e) => setForm({ ...form, image: e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-mono" placeholder="https://..." /></Field>
        <Field label="Action Button Label (optional)"><input value={form.action_label} onChange={(e) => setForm({ ...form, action_label: e.target.value })} maxLength={30} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm" placeholder="View Details" /></Field>

        <div className="border-t border-slate-100 pt-4 space-y-3">
          <p className="font-black text-brand-navy">Target</p>
          <div className="flex gap-2">
            {[
              { k: "all", label: "All Users", icon: Users },
              { k: "user", label: "Single User", icon: User },
              { k: "segment", label: "Segment", icon: PieChart },
            ].map((t) => (
              <button key={t.k} onClick={() => setForm({ ...form, target_type: t.k as any })}
                className={`flex-1 py-2.5 rounded-xl text-sm font-bold inline-flex items-center justify-center gap-2 border transition ${form.target_type === t.k ? "bg-brand-primary text-white border-brand-primary" : "bg-white border-slate-200 text-slate-600 hover:border-brand-primary"}`}>
                <t.icon className="w-4 h-4" /> {t.label}
              </button>
            ))}
          </div>
          {form.target_type === "user" && (
            <Field label="User ID"><input value={form.target_user_id} onChange={(e) => setForm({ ...form, target_user_id: e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-mono" placeholder="usr_xxxxxxxxx" /></Field>
          )}
          {form.target_type === "segment" && (
            <Field label="Segment"><select value={form.target_segment} onChange={(e) => setForm({ ...form, target_segment: e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold">{SEGMENTS.map((s) => <option key={s.k} value={s.k}>{s.label}</option>)}</select></Field>
          )}
        </div>

        <div className="border-t border-slate-100 pt-4 grid grid-cols-2 gap-3">
          <Field label="Schedule (optional)" hint="Leave empty to send immediately"><input type="datetime-local" value={form.schedule_at} onChange={(e) => setForm({ ...form, schedule_at: e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm" /></Field>
          <Field label="Expires at (optional)" hint="Hide after this time"><input type="datetime-local" value={form.expires_at} onChange={(e) => setForm({ ...form, expires_at: e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm" /></Field>
        </div>

        <label className="flex items-center gap-2 pt-2">
          <input type="checkbox" checked={form.send_push} onChange={(e) => setForm({ ...form, send_push: e.target.checked })} />
          <span className="text-sm font-bold">Also deliver as push (if user has push enabled)</span>
        </label>

        <div className="flex gap-2 pt-2">
          <button onClick={() => setPreview(!preview)} className="px-4 py-2.5 rounded-xl bg-slate-100 text-slate-700 font-bold text-sm hover:bg-slate-200">Preview</button>
          <button onClick={send} disabled={!canSend || busy} className="flex-1 py-2.5 rounded-xl bg-gradient-to-r from-sky-600 to-blue-700 text-white font-black text-sm inline-flex items-center justify-center gap-2 hover:from-sky-700 hover:to-blue-800 disabled:opacity-50">
            {busy ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            {form.schedule_at ? "Schedule" : "Send Now"}
          </button>
        </div>
      </div>

      <div>
        <p className="font-black text-brand-navy mb-3">Preview</p>
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="bg-gradient-to-br from-sky-500 to-blue-700 p-4 text-white">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest opacity-80"><Bell className="w-3 h-3" /> {CATEGORIES.find((c) => c.k === form.category)?.label || form.category}</div>
            <p className="text-lg font-black mt-2">{form.title || "Notification title"}</p>
          </div>
          {form.image && (<img src={form.image} className="w-full h-40 object-cover" onError={(e) => (e.target as HTMLImageElement).style.display = "none"} />)}
          <div className="p-4">
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{form.body || "Message body will appear here…"}</p>
            {form.action_label && (
              <div className="mt-3">
                <button className="px-3 py-1.5 rounded-lg bg-brand-primary text-white text-xs font-bold">{form.action_label}</button>
              </div>
            )}
            <p className="text-[10px] text-slate-400 mt-3">Deep link → <span className="font-mono">{form.deeplink}</span></p>
          </div>
        </div>
        <p className="text-xs text-slate-500 mt-2">Preview mirrors how the mobile card appears in the notification center.</p>
      </div>
    </div>
  );
}

function Campaigns() {
  const [items, setItems] = useState<Campaign[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [detail, setDetail] = useState<any | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/notifications/campaigns?limit=100${q ? `&q=${encodeURIComponent(q)}` : ""}${status ? `&status=${status}` : ""}`);
      setItems(data.items || []); setTotal(data.total || 0);
    } finally { setLoading(false); }
  };
  useEffect(() => { load();  }, [status]);
  useEffect(() => { const t = setTimeout(load, 300); return () => clearTimeout(t);  }, [q]);

  const openDetail = async (id: string) => {
    const { data } = await api.get(`/admin/notifications/campaigns/${id}`);
    setDetail(data.campaign);
  };
  const cancel = async (id: string) => {
    await api.post(`/admin/notifications/campaigns/${id}/cancel`);
    load();
  };
  const resend = async (id: string) => {
    await api.post(`/admin/notifications/campaigns/${id}/resend`);
    load();
  };

  return (
    <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
      <div className="p-4 border-b border-slate-200 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input placeholder="Search by title or campaign id…" value={q} onChange={(e) => setQ(e.target.value)} className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 text-sm focus:border-brand-primary focus:ring-2 focus:ring-sky-100 outline-none" />
        </div>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold">
          <option value="">All Status</option>
          <option value="sending">Sending</option>
          <option value="sent">Sent</option>
          <option value="scheduled">Scheduled</option>
          <option value="cancelled">Cancelled</option>
        </select>
        <button onClick={load} className="px-3 py-2.5 rounded-xl border border-slate-200"><RefreshCw className="w-4 h-4" /></button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs font-black text-slate-500 uppercase tracking-wide">
            <tr><th className="p-3 text-left">Campaign</th><th className="p-3 text-left">Target</th><th className="p-3 text-right">Sent</th><th className="p-3 text-right">Opened</th><th className="p-3 text-left">Status</th><th className="p-3 text-left">Created</th><th></th></tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loading ? (<tr><td colSpan={7} className="p-10 text-center"><RefreshCw className="w-5 h-5 mx-auto animate-spin text-brand-primary" /></td></tr>)
              : items.length === 0 ? (<tr><td colSpan={7} className="p-16 text-center text-slate-400"><Bell className="w-10 h-10 mx-auto mb-2 opacity-40" /><p>No campaigns yet.</p></td></tr>)
              : items.map((c) => (
                <tr key={c.campaign_id} className="hover:bg-slate-50">
                  <td className="p-3">
                    <p className="font-black text-brand-navy truncate max-w-[260px]">{c.title}</p>
                    <p className="text-[10px] text-slate-400 font-mono">{c.campaign_id}</p>
                  </td>
                  <td className="p-3">
                    <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-slate-100">{c.target_type === "segment" ? c.target_segment : c.target_type}</span>
                    <p className="text-[11px] text-slate-500 mt-1">{c.total_targets} target(s)</p>
                  </td>
                  <td className="p-3 text-right font-black text-brand-navy">{c.sent_count}</td>
                  <td className="p-3 text-right font-bold text-emerald-700">{c.opened}</td>
                  <td className="p-3">
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${c.status === "sent" ? "bg-emerald-100 text-emerald-700" : c.status === "scheduled" ? "bg-amber-100 text-amber-700" : c.status === "cancelled" ? "bg-slate-100 text-slate-500" : "bg-sky-100 text-sky-700"}`}>{c.status.toUpperCase()}</span>
                  </td>
                  <td className="p-3 text-xs text-slate-500">{fmtDate(c.created_at)}</td>
                  <td className="p-3 text-right">
                    <div className="inline-flex gap-1">
                      <button onClick={() => openDetail(c.campaign_id)} className="text-brand-primary text-xs font-bold hover:underline inline-flex items-center gap-1">View<ChevronRight className="w-3 h-3" /></button>
                      {c.status === "sent" && (<button onClick={() => resend(c.campaign_id)} title="Resend" className="p-1 text-slate-500 hover:text-brand-primary"><Send className="w-3.5 h-3.5" /></button>)}
                      {c.status === "scheduled" && (<button onClick={() => cancel(c.campaign_id)} title="Cancel" className="p-1 text-slate-500 hover:text-rose-600"><Ban className="w-3.5 h-3.5" /></button>)}
                    </div>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
      <div className="p-3 border-t border-slate-100 text-xs text-slate-500">Showing {items.length} of {total}</div>

      {detail && (
        <div className="fixed inset-0 z-40 flex" onClick={() => setDetail(null)}>
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
          <div className="ml-auto relative w-full max-w-lg h-full bg-white shadow-2xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 bg-gradient-to-r from-sky-600 to-blue-700 text-white p-5">
              <div className="flex justify-between items-start">
                <div>
                  <p className="text-xs font-bold tracking-widest uppercase text-sky-200">Campaign · {detail.campaign_id}</p>
                  <p className="text-lg font-black mt-1">{detail.title}</p>
                </div>
                <button onClick={() => setDetail(null)}><X className="w-5 h-5" /></button>
              </div>
            </div>
            <div className="p-5 space-y-3 text-sm">
              <p className="text-slate-700 whitespace-pre-wrap">{detail.body}</p>
              {detail.image && <img src={detail.image} className="w-full rounded-lg" />}
              <div className="grid grid-cols-2 gap-2 text-xs">
                <Info label="Target" value={`${detail.target_type}${detail.target_segment ? ' · ' + detail.target_segment : ''}${detail.target_user_id ? ' · ' + detail.target_user_id : ''}`} />
                <Info label="Priority" value={detail.priority?.toUpperCase()} />
                <Info label="Status" value={detail.status.toUpperCase()} />
                <Info label="Total targets" value={String(detail.total_targets)} />
                <Info label="Sent" value={String(detail.sent_count || 0)} />
                <Info label="Skipped (prefs)" value={String(detail.skipped_count || 0)} />
                <Info label="Delivered" value={String(detail.delivered || 0)} />
                <Info label="Opened" value={`${detail.opened || 0} · ${detail.ctr_pct || 0}%`} />
                <Info label="Deeplink" value={detail.deeplink || '/'} />
                <Info label="Created" value={fmtDate(detail.created_at)} />
                {detail.schedule_at && <Info label="Scheduled" value={fmtDate(detail.schedule_at)} />}
                {detail.expires_at && <Info label="Expires" value={fmtDate(detail.expires_at)} />}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (<div className="bg-slate-50 rounded-lg p-2">
    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">{label}</p>
    <p className="text-xs font-bold text-slate-800 mt-0.5 break-words">{value}</p>
  </div>);
}

function AnalyticsView() {
  const [data, setData] = useState<Analytics | null>(null);
  const [days, setDays] = useState(7);

  useEffect(() => { api.get(`/admin/notifications/analytics?days=${days}`).then((r) => setData(r.data)); }, [days]);

  if (!data) return <div className="p-10 text-center text-slate-400"><RefreshCw className="w-5 h-5 mx-auto animate-spin" /></div>;
  const t = data.totals;
  const maxSent = Math.max(1, ...data.chart.map((c) => c.sent));

  return (
    <div className="space-y-6">
      <div className="flex gap-2">
        {[7, 14, 30].map((d) => (
          <button key={d} onClick={() => setDays(d)} className={`px-3 py-1.5 rounded-lg text-xs font-bold ${days === d ? "bg-brand-navy text-white" : "bg-white border border-slate-200 text-slate-600"}`}>Last {d} days</button>
        ))}
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {[
          { label: "Sent", value: t.sent, icon: Send, tone: "from-sky-500 to-blue-600" },
          { label: "Delivered", value: t.delivered, icon: Check, tone: "from-emerald-500 to-teal-600" },
          { label: "Opened", value: t.opened, icon: MousePointerClick, tone: "from-indigo-500 to-purple-600" },
          { label: "Failed", value: t.failed, icon: AlertTriangle, tone: "from-rose-500 to-red-600" },
          { label: "CTR", value: `${t.ctr_pct}%`, icon: TrendingUp, tone: "from-amber-500 to-orange-600" },
        ].map((c) => (
          <div key={c.label} className="bg-white rounded-2xl p-4 border border-slate-200">
            <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${c.tone} flex items-center justify-center text-white mb-2`}><c.icon className="w-4 h-4" /></div>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">{c.label}</p>
            <p className="text-2xl font-black text-brand-navy mt-1">{c.value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 bg-white rounded-2xl p-5 border border-slate-200">
          <p className="font-black text-brand-navy mb-4">Sent vs Opened · Last {days} days</p>
          <div className="flex items-end gap-2 h-40">
            {data.chart.map((c) => {
              const h = Math.round((c.sent / maxSent) * 100);
              const oh = c.sent ? Math.round((c.opened / c.sent) * h) : 0;
              return (
                <div key={c.date} className="flex flex-col items-center flex-1 gap-1">
                  <div className="w-full h-32 bg-slate-50 rounded-lg relative flex items-end overflow-hidden">
                    <div className="w-full bg-sky-500" style={{ height: `${h}%` }} />
                    <div className="w-full bg-emerald-500 absolute bottom-0" style={{ height: `${oh}%` }} />
                  </div>
                  <p className="text-[9px] text-slate-500 font-bold">{c.date.slice(5)}</p>
                </div>
              );
            })}
          </div>
          <div className="flex gap-3 mt-3 text-[11px]">
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-sky-500" />Sent</span>
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500" />Opened</span>
          </div>
        </div>
        <div className="bg-white rounded-2xl p-5 border border-slate-200">
          <p className="font-black text-brand-navy mb-3">By Category</p>
          {data.per_category.length === 0 ? <p className="text-sm text-slate-400">No data</p> :
            data.per_category.slice(0, 8).map((c) => (
              <div key={c.category} className="py-1.5">
                <div className="flex justify-between text-xs font-bold">
                  <span className="text-slate-700">{c.label}</span>
                  <span className="text-slate-500">{c.sent} · {c.ctr_pct}%</span>
                </div>
                <div className="h-1.5 bg-slate-100 rounded-full mt-1"><div className="h-1.5 bg-gradient-to-r from-sky-500 to-brand-primary rounded-full" style={{ width: `${Math.min(100, (c.sent / Math.max(1, data.per_category[0].sent)) * 100)}%` }} /></div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

function Audit() {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => { api.get("/admin/notifications/audit").then((r) => setItems(r.data.items || [])); }, []);
  return (
    <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-xs font-black text-slate-500 uppercase tracking-wide">
          <tr><th className="p-3 text-left">Action</th><th className="p-3 text-left">Actor</th><th className="p-3 text-left">Meta</th><th className="p-3 text-left">When</th></tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {items.length === 0 ? <tr><td colSpan={4} className="p-10 text-center text-slate-400">No audit entries yet.</td></tr>
            : items.map((a, i) => (
              <tr key={i}>
                <td className="p-3"><span className="text-xs font-bold px-2 py-0.5 rounded-full bg-indigo-100 text-indigo-700">{a.action}</span></td>
                <td className="p-3 text-xs font-mono">{a.user_id}</td>
                <td className="p-3 text-xs text-slate-600 truncate max-w-md">{JSON.stringify(a.meta)}</td>
                <td className="p-3 text-xs text-slate-500">{fmtDate(a.ts)}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (<div><label className="text-xs font-bold text-slate-600 uppercase tracking-wide block mb-1">{label}</label>{children}{hint && <p className="text-[11px] text-slate-400 mt-1">{hint}</p>}</div>);
}

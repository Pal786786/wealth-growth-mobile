/**
 * Admin — Copy Trading Console (Sprint 7B.3)
 * Tabbed page for Trader Management, Simulation, Master Trades, Followers,
 * Analytics, System Health, Configuration.
 */
import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import {
  Users, Play, Pause, Square, Radio, LineChart, Activity, Settings as SettingsIcon,
  Plus, Edit2, Trash2, CheckCircle2, XCircle, ShieldCheck, RotateCcw, Search,
  TrendingUp, TrendingDown, RefreshCw, Zap, ChevronRight,
} from "lucide-react";

type TabId = "traders" | "simulation" | "master-trades" | "followers" | "analytics" | "health" | "config";
const TABS: { id: TabId; label: string; icon: any }[] = [
  { id: "traders", label: "Traders", icon: Users },
  { id: "simulation", label: "Simulation", icon: Play },
  { id: "master-trades", label: "Master Trades", icon: Radio },
  { id: "followers", label: "Followers", icon: Users },
  { id: "analytics", label: "Analytics", icon: LineChart },
  { id: "health", label: "System Health", icon: Activity },
  { id: "config", label: "Configuration", icon: SettingsIcon },
];

export default function AdminCopyTrading() {
  const [tab, setTab] = useState<TabId>("traders");

  return (
    <div className="p-6">
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 rounded-lg bg-indigo-100 text-indigo-700"><Users className="w-5 h-5" /></div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Copy Trading Console</h1>
          <p className="text-sm text-slate-500">Sprint 7B.3 — Traders, Simulation, Trades, Followers, Analytics, Health, Config</p>
        </div>
      </div>

      <div className="flex gap-1 mb-5 border-b border-slate-200 overflow-x-auto">
        {TABS.map((t) => {
          const Ic = t.icon;
          const active = t.id === tab;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold whitespace-nowrap border-b-2 transition ${
                active
                  ? "border-indigo-600 text-indigo-700"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              <Ic className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === "traders" && <TradersTab />}
      {tab === "simulation" && <SimulationTab />}
      {tab === "master-trades" && <MasterTradesTab />}
      {tab === "followers" && <FollowersTab />}
      {tab === "analytics" && <AnalyticsTab />}
      {tab === "health" && <HealthTab />}
      {tab === "config" && <ConfigTab />}
    </div>
  );
}

// =====================================================================
// TRADERS TAB
// =====================================================================
function TradersTab() {
  const qc = useQueryClient();
  const [category, setCategory] = useState<string>("");
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<any | null>(null);
  const [creating, setCreating] = useState(false);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["admin-traders", category, search],
    queryFn: async () => (await api.get("/copy_trading/admin/traders", {
      params: { category: category || undefined, search: search || undefined, limit: 200 },
    })).data as { items: any[]; total: number },
    refetchInterval: 30000,
  });

  const deleteTrader = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/copy_trading/admin/traders/${id}`)).data,
    onSuccess: () => { refetch(); qc.invalidateQueries({ queryKey: ["admin-traders"] }); },
  });
  const setVerified = useMutation({
    mutationFn: async ({ id, verified }: any) => (await api.post(`/copy_trading/admin/traders/${id}/${verified ? "verify" : "unverify"}`)).data,
    onSuccess: () => refetch(),
  });
  const setDisabled = useMutation({
    mutationFn: async ({ id, disabled }: any) => (await api.post(`/copy_trading/admin/traders/${id}/${disabled ? "disable" : "enable"}`)).data,
    onSuccess: () => refetch(),
  });
  const resetOverlay = useMutation({
    mutationFn: async (id: string) => (await api.post(`/copy_trading/admin/traders/${id}/reset-overlay`)).data,
    onSuccess: () => refetch(),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1 bg-slate-100 p-1 rounded-lg">
          {["", "system", "verified", "custom", "disabled"].map((c) => (
            <button
              key={c || "all"}
              onClick={() => setCategory(c)}
              className={`px-3 py-1.5 rounded-md text-xs font-bold ${category === c ? "bg-white text-indigo-700 shadow-sm" : "text-slate-600"}`}
            >
              {c ? c.toUpperCase() : "ALL"}
            </button>
          ))}
        </div>
        <div className="flex-1 min-w-[220px] relative">
          <Search className="w-4 h-4 absolute left-2.5 top-2.5 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or country"
            className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-sm"
          />
        </div>
        <button
          onClick={() => setCreating(true)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold rounded-lg"
        >
          <Plus className="w-4 h-4" /> Create Custom Trader
        </button>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-[11px] uppercase font-bold">
            <tr>
              <th className="text-left px-4 py-3">Trader</th>
              <th className="text-left px-3 py-3">Style</th>
              <th className="text-left px-3 py-3">Category</th>
              <th className="text-right px-3 py-3">ROI</th>
              <th className="text-right px-3 py-3">Win %</th>
              <th className="text-right px-3 py-3">Risk</th>
              <th className="text-center px-3 py-3">Level</th>
              <th className="text-center px-3 py-3">Status</th>
              <th className="text-right px-3 py-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr><td colSpan={9} className="p-8 text-center text-slate-400">Loading…</td></tr>
            )}
            {!isLoading && data?.items?.length === 0 && (
              <tr><td colSpan={9} className="p-8 text-center text-slate-400">No traders match your filters</td></tr>
            )}
            {data?.items?.map((t) => (
              <tr key={t.id} className={`border-t border-slate-100 hover:bg-slate-50/60 ${t.disabled ? "opacity-60" : ""}`}>
                <td className="px-4 py-2.5">
                  <div className="flex items-center gap-2.5">
                    {t.avatar_url ? <img src={t.avatar_url} alt="" className="w-8 h-8 rounded-full bg-slate-200" /> : <div className="w-8 h-8 rounded-full bg-slate-200" />}
                    <div>
                      <div className="font-semibold text-slate-800 flex items-center gap-1">
                        {t.name} {t.verified && <ShieldCheck className="w-3.5 h-3.5 text-blue-500" />}
                      </div>
                      <div className="text-[11px] text-slate-500">{t.country_name || t.country_code} · {t.id}</div>
                    </div>
                  </div>
                </td>
                <td className="px-3 py-2.5 text-slate-600">{t.style}</td>
                <td className="px-3 py-2.5">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${t.kind === "custom" ? "bg-purple-100 text-purple-700" : "bg-slate-100 text-slate-600"}`}>
                    {t.kind?.toUpperCase() || "SYSTEM"}
                  </span>
                </td>
                <td className={`px-3 py-2.5 text-right font-bold tabular-nums ${t.stats.total_roi_pct >= 0 ? "text-green-600" : "text-red-600"}`}>
                  {t.stats.total_roi_pct >= 0 ? "+" : ""}{t.stats.total_roi_pct.toFixed(1)}%
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums">{t.stats.win_rate_pct.toFixed(1)}%</td>
                <td className="px-3 py-2.5 text-right"><span className="text-xs font-bold">{t.risk.risk_score}/10</span></td>
                <td className="px-3 py-2.5 text-center">
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-indigo-50 text-indigo-700">
                    {(t.approval_level || "—").toUpperCase()}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-center">
                  {t.disabled ? (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-700">DISABLED</span>
                  ) : (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-green-100 text-green-700">ACTIVE</span>
                  )}
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex justify-end gap-1">
                    <IconBtn title="Edit" onClick={() => setEditing(t)}><Edit2 className="w-3.5 h-3.5" /></IconBtn>
                    <IconBtn title={t.verified ? "Unverify" : "Verify"} onClick={() => setVerified.mutate({ id: t.id, verified: !t.verified })}>
                      {t.verified ? <XCircle className="w-3.5 h-3.5 text-orange-500" /> : <CheckCircle2 className="w-3.5 h-3.5 text-blue-500" />}
                    </IconBtn>
                    <IconBtn title={t.disabled ? "Enable" : "Disable"} onClick={() => setDisabled.mutate({ id: t.id, disabled: !t.disabled })}>
                      {t.disabled ? <Play className="w-3.5 h-3.5 text-green-600" /> : <Pause className="w-3.5 h-3.5 text-orange-500" />}
                    </IconBtn>
                    {t.kind === "system" && (t as any)._edited && (
                      <IconBtn title="Reset overlay" onClick={() => resetOverlay.mutate(t.id)}>
                        <RotateCcw className="w-3.5 h-3.5 text-slate-500" />
                      </IconBtn>
                    )}
                    {t.kind === "custom" && (
                      <IconBtn title="Delete" onClick={() => {
                        if (confirm(`Delete ${t.name}? This also removes all copy relationships.`)) deleteTrader.mutate(t.id);
                      }}>
                        <Trash2 className="w-3.5 h-3.5 text-red-500" />
                      </IconBtn>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing && <TraderEditor trader={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); refetch(); }} />}
      {creating && <TraderCreator onClose={() => setCreating(false)} onCreated={() => { setCreating(false); refetch(); }} />}
    </div>
  );
}

function IconBtn({ children, onClick, title }: any) {
  return (
    <button onClick={onClick} title={title} className="p-1.5 rounded hover:bg-slate-100">
      {children}
    </button>
  );
}

// -------------------------------------------------------------------
// Trader Editor / Creator
// -------------------------------------------------------------------
function TraderEditor({ trader, onClose, onSaved }: any) {
  const isCustom = trader.kind === "custom";
  const [form, setForm] = useState<any>({
    name: trader.name || "",
    bio: trader.bio || "",
    country_code: trader.country_code || "US",
    country_name: trader.country_name || "",
    style: trader.style || "Day Trading",
    verified: !!trader.verified,
    approval_level: trader.approval_level || "verified",
    risk_tier: trader.risk?.risk_tier || "Moderate",
    experience_years: trader.experience_years || 3,
    avatar_url: trader.avatar_url || "",
    visible: trader.visible !== false,
    disabled: !!trader.disabled,
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const styles = ["Scalping","Day Trading","Swing","Position","Trend Following","Mean Reversion","News Trader","Breakout","Grid","Arbitrage"];
  const levels = ["verified","professional","elite","master"];
  const tiers = ["Conservative","Moderate","Aggressive"];

  const save = async () => {
    setSaving(true); setErr(null);
    try {
      const payload: any = { ...form };
      // For custom traders you can also edit truth
      await api.put(`/copy_trading/admin/traders/${trader.id}`, payload);
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "Save failed");
    } finally { setSaving(false); }
  };

  const handleFile = (e: any) => {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = () => {
      setForm((s: any) => ({ ...s, avatar_url: reader.result as string }));
    };
    reader.readAsDataURL(f);
  };

  return (
    <Modal title={`Edit ${trader.name}${isCustom ? "" : " (system overlay)"}`} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name" value={form.name} onChange={(v: string) => setForm({ ...form, name: v })} disabled={!isCustom} />
        <Field label="Country code (2)" value={form.country_code} onChange={(v: string) => setForm({ ...form, country_code: v.toUpperCase() })} />
        <Field label="Country name" value={form.country_name} onChange={(v: string) => setForm({ ...form, country_name: v })} />
        <Select label="Style" value={form.style} options={styles} onChange={(v: string) => setForm({ ...form, style: v })} />
        <Select label="Approval level" value={form.approval_level} options={levels} onChange={(v: string) => setForm({ ...form, approval_level: v })} />
        <Select label="Risk tier" value={form.risk_tier} options={tiers} onChange={(v: string) => setForm({ ...form, risk_tier: v })} />
        <Field label="Experience (years)" type="number" value={form.experience_years} onChange={(v: any) => setForm({ ...form, experience_years: +v })} />
        <div className="col-span-2">
          <label className="block text-xs font-bold text-slate-500 mb-1">Bio</label>
          <textarea value={form.bio} onChange={(e) => setForm({ ...form, bio: e.target.value })} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" rows={2} />
        </div>
        <div className="col-span-2 flex items-center gap-4 flex-wrap">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.verified} onChange={(e) => setForm({ ...form, verified: e.target.checked })} /> Verified</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.visible} onChange={(e) => setForm({ ...form, visible: e.target.checked })} /> Visible</label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={form.disabled} onChange={(e) => setForm({ ...form, disabled: e.target.checked })} /> Disabled</label>
        </div>
        <div className="col-span-2">
          <label className="block text-xs font-bold text-slate-500 mb-1">Avatar</label>
          <div className="flex gap-3 items-center">
            {form.avatar_url && <img src={form.avatar_url} alt="" className="w-14 h-14 rounded-full bg-slate-200" />}
            <input type="file" accept="image/*" onChange={handleFile} className="text-xs" />
            <input type="text" value={form.avatar_url} onChange={(e) => setForm({ ...form, avatar_url: e.target.value })} placeholder="or paste URL" className="flex-1 border border-slate-200 rounded px-2 py-1.5 text-xs" />
          </div>
        </div>
      </div>
      {err && <div className="mt-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded p-2">{err}</div>}
      <div className="mt-5 flex justify-end gap-2">
        <button onClick={onClose} className="px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100 rounded-lg">Cancel</button>
        <button disabled={saving} onClick={save} className="px-4 py-2 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg disabled:opacity-60">
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </Modal>
  );
}

function TraderCreator({ onClose, onCreated }: any) {
  const [form, setForm] = useState<any>({
    name: "", country_code: "US", country_name: "United States",
    style: "Day Trading", experience_years: 3, bio: "",
    verified: false, approval_level: "verified",
    avatar_url: "",
    truth: { win_rate: 0.55, payoff_ratio: 1.6, avg_lot: 0.8, annual_target_roi_pct: 0.5 },
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const styles = ["Scalping","Day Trading","Swing","Position","Trend Following","Mean Reversion","News Trader","Breakout","Grid","Arbitrage"];

  const handleFile = (e: any) => {
    const f = e.target.files?.[0]; if (!f) return;
    const reader = new FileReader();
    reader.onload = () => setForm({ ...form, avatar_url: reader.result });
    reader.readAsDataURL(f);
  };

  const save = async () => {
    setSaving(true); setErr(null);
    try {
      await api.post("/copy_trading/admin/traders", form);
      onCreated();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "Create failed");
    } finally { setSaving(false); }
  };

  return (
    <Modal title="Create Custom Trader" onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name *" value={form.name} onChange={(v: any) => setForm({ ...form, name: v })} />
        <Select label="Style *" value={form.style} options={styles} onChange={(v: any) => setForm({ ...form, style: v })} />
        <Field label="Country code (2)" value={form.country_code} onChange={(v: any) => setForm({ ...form, country_code: v.toUpperCase() })} />
        <Field label="Country name" value={form.country_name} onChange={(v: any) => setForm({ ...form, country_name: v })} />
        <Field label="Experience (years)" type="number" value={form.experience_years} onChange={(v: any) => setForm({ ...form, experience_years: +v })} />
        <Select label="Approval level" value={form.approval_level} options={["verified","professional","elite","master"]} onChange={(v: any) => setForm({ ...form, approval_level: v })} />
        <div className="col-span-2">
          <label className="block text-xs font-bold text-slate-500 mb-1">Bio</label>
          <textarea rows={2} value={form.bio} onChange={(e) => setForm({ ...form, bio: e.target.value })} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div className="col-span-2 grid grid-cols-4 gap-2">
          <Field label="Win Rate" type="number" value={form.truth.win_rate} onChange={(v: any) => setForm({ ...form, truth: { ...form.truth, win_rate: +v } })} />
          <Field label="Payoff Ratio" type="number" value={form.truth.payoff_ratio} onChange={(v: any) => setForm({ ...form, truth: { ...form.truth, payoff_ratio: +v } })} />
          <Field label="Avg Lot" type="number" value={form.truth.avg_lot} onChange={(v: any) => setForm({ ...form, truth: { ...form.truth, avg_lot: +v } })} />
          <Field label="Target ROI/yr" type="number" value={form.truth.annual_target_roi_pct} onChange={(v: any) => setForm({ ...form, truth: { ...form.truth, annual_target_roi_pct: +v } })} />
        </div>
        <div className="col-span-2">
          <label className="block text-xs font-bold text-slate-500 mb-1">Avatar</label>
          <div className="flex gap-2 items-center">
            {form.avatar_url && <img src={form.avatar_url} alt="" className="w-12 h-12 rounded-full bg-slate-200" />}
            <input type="file" accept="image/*" onChange={handleFile} className="text-xs" />
          </div>
        </div>
        <label className="col-span-2 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.verified} onChange={(e) => setForm({ ...form, verified: e.target.checked })} /> Mark as Verified
        </label>
      </div>
      {err && <div className="mt-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded p-2">{err}</div>}
      <div className="mt-5 flex justify-end gap-2">
        <button onClick={onClose} className="px-4 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-100 rounded-lg">Cancel</button>
        <button disabled={saving} onClick={save} className="px-4 py-2 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg disabled:opacity-60">
          {saving ? "Creating…" : "Create Trader"}
        </button>
      </div>
    </Modal>
  );
}

function Modal({ title, onClose, children }: any) {
  return (
    <div className="fixed inset-0 bg-slate-900/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl p-6 max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-slate-900">{title}</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700"><XCircle className="w-5 h-5" /></button>
        </div>
        {children}
      </div>
    </div>
  );
}
function Field({ label, value, onChange, type = "text", disabled }: any) {
  return (
    <div>
      <label className="block text-xs font-bold text-slate-500 mb-1">{label}</label>
      <input type={type} value={value ?? ""} onChange={(e) => onChange(e.target.value)} disabled={disabled}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm disabled:bg-slate-50 disabled:text-slate-400" />
    </div>
  );
}
function Select({ label, value, options, onChange }: any) {
  return (
    <div>
      <label className="block text-xs font-bold text-slate-500 mb-1">{label}</label>
      <select value={value ?? ""} onChange={(e) => onChange(e.target.value)}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">
        {options.map((o: string) => <option key={o} value={o}>{o}</option>)}
      </select>
    </div>
  );
}

// =====================================================================
// SIMULATION TAB
// =====================================================================
function SimulationTab() {
  const qc = useQueryClient();
  const { data: status, refetch } = useQuery({
    queryKey: ["sim-status"],
    queryFn: async () => (await api.get("/copy_trading/admin/simulation/status")).data,
    refetchInterval: 3000,
  });
  const { data: traders } = useQuery({
    queryKey: ["admin-traders-min"],
    queryFn: async () => (await api.get("/copy_trading/admin/traders", { params: { limit: 200 } })).data.items as any[],
  });

  const [forceOpenTrader, setForceOpenTrader] = useState("");
  const [forceOpenSide, setForceOpenSide] = useState<"buy" | "sell" | "">("");

  const pause = useMutation({ mutationFn: () => api.post("/copy_trading/admin/simulation/pause"), onSuccess: () => refetch() });
  const resume = useMutation({ mutationFn: () => api.post("/copy_trading/admin/simulation/resume"), onSuccess: () => refetch() });
  const setSpeed = useMutation({ mutationFn: (speed: string) => api.post("/copy_trading/admin/simulation/speed", { speed }), onSuccess: () => refetch() });
  const forceOpen = useMutation({
    mutationFn: () => api.post("/copy_trading/admin/simulation/force-open", { trader_id: forceOpenTrader, side: forceOpenSide || undefined }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-master-trades"] }); },
  });

  const enabled = status?.enabled;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <StatCard label="Status" value={enabled ? "Running" : "Paused"} tint={enabled ? "green" : "amber"} icon={enabled ? Play : Pause} />
        <StatCard label="Speed" value={(status?.speed || "—").toUpperCase()} icon={Zap} />
        <StatCard label="Active Simulators" value={status?.active_traders ?? 0} icon={Users} />
        <StatCard label="Open Master Trades" value={status?.open_master_trades ?? 0} icon={Radio} />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-bold text-slate-700 mb-3">Master switch</h3>
        <div className="flex gap-2 flex-wrap">
          <button onClick={() => resume.mutate()} disabled={enabled} className="flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-bold rounded-lg disabled:opacity-40">
            <Play className="w-4 h-4" /> Start / Resume
          </button>
          <button onClick={() => pause.mutate()} disabled={!enabled} className="flex items-center gap-2 px-4 py-2 bg-orange-500 hover:bg-orange-600 text-white text-sm font-bold rounded-lg disabled:opacity-40">
            <Pause className="w-4 h-4" /> Pause / Stop
          </button>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-bold text-slate-700 mb-3">Simulation Speed</h3>
        <div className="flex gap-2">
          {["slow", "normal", "fast"].map((sp) => (
            <button
              key={sp}
              onClick={() => setSpeed.mutate(sp)}
              className={`flex-1 px-4 py-2.5 rounded-lg text-sm font-bold border ${status?.speed === sp ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-slate-700 border-slate-200"}`}
            >
              {sp.toUpperCase()}
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500">Slow: 2× intervals · Normal: 1× · Fast: 0.3× (great for demos)</p>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-bold text-slate-700 mb-3">Force a master trade</h3>
        <div className="flex flex-wrap gap-2 items-end">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-bold text-slate-500 mb-1">Trader</label>
            <select value={forceOpenTrader} onChange={(e) => setForceOpenTrader(e.target.value)}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">
              <option value="">Choose a trader…</option>
              {traders?.map((t) => <option key={t.id} value={t.id}>{t.name} ({t.style})</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-bold text-slate-500 mb-1">Side</label>
            <select value={forceOpenSide} onChange={(e) => setForceOpenSide(e.target.value as any)}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm">
              <option value="">Random</option>
              <option value="buy">BUY</option>
              <option value="sell">SELL</option>
            </select>
          </div>
          <button
            disabled={!forceOpenTrader}
            onClick={() => forceOpen.mutate()}
            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold rounded-lg disabled:opacity-40"
          >
            Open master trade
          </button>
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// MASTER TRADES TAB
// =====================================================================
function MasterTradesTab() {
  const [statusFilter, setStatusFilter] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["admin-master-trades", statusFilter],
    queryFn: async () => (await api.get("/copy_trading/admin/master-trades", {
      params: { limit: 100, status: statusFilter || undefined },
    })).data as { trades: any[] },
    refetchInterval: 2000,   // 2s polling per requirement
  });
  const qc = useQueryClient();
  const forceClose = useMutation({
    mutationFn: (mid: string) => api.post(`/copy_trading/admin/simulation/force-close/${mid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-master-trades"] }),
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="text-xs font-bold text-slate-500">FILTER</div>
        {["", "open", "closed"].map((s) => (
          <button
            key={s || "all"}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded-full text-xs font-bold ${statusFilter === s ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-700"}`}
          >
            {s ? s.toUpperCase() : "ALL"}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 text-xs text-slate-500">
          <RefreshCw className="w-3 h-3 animate-spin" /> Live · 2s refresh
        </div>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-[11px] uppercase font-bold">
            <tr>
              <th className="text-left px-3 py-2.5">Trader</th>
              <th className="text-left px-3 py-2.5">Symbol</th>
              <th className="text-center px-3 py-2.5">Side</th>
              <th className="text-right px-3 py-2.5">Lot</th>
              <th className="text-right px-3 py-2.5">Entry</th>
              <th className="text-right px-3 py-2.5">SL</th>
              <th className="text-right px-3 py-2.5">TP</th>
              <th className="text-right px-3 py-2.5">Exit</th>
              <th className="text-right px-3 py-2.5">P&L%</th>
              <th className="text-center px-3 py-2.5">Status</th>
              <th className="text-center px-3 py-2.5">Followers</th>
              <th className="text-left px-3 py-2.5">Opened</th>
              <th className="text-right px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {isLoading && <tr><td colSpan={13} className="text-center p-6 text-slate-400">Loading…</td></tr>}
            {data?.trades?.map((t) => (
              <tr key={t.master_id} className="border-t border-slate-100 text-xs">
                <td className="px-3 py-2 font-semibold text-slate-700">{t.trader_id}</td>
                <td className="px-3 py-2">{t.symbol}</td>
                <td className="px-3 py-2 text-center">
                  <span className={`px-2 py-0.5 rounded font-bold ${t.side === "buy" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
                    {t.side?.toUpperCase()}
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{t.lot_size}</td>
                <td className="px-3 py-2 text-right tabular-nums">{t.entry_price}</td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-400">{t.sl ?? "—"}</td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-400">{t.tp ?? "—"}</td>
                <td className="px-3 py-2 text-right tabular-nums">{t.exit_price ?? "—"}</td>
                <td className={`px-3 py-2 text-right tabular-nums font-bold ${(t.pnl_pct ?? 0) >= 0 ? "text-green-600" : "text-red-600"}`}>
                  {t.pnl_pct != null ? `${t.pnl_pct >= 0 ? "+" : ""}${Number(t.pnl_pct).toFixed(3)}%` : "—"}
                </td>
                <td className="px-3 py-2 text-center">
                  <span className={`px-2 py-0.5 rounded font-bold ${t.status === "open" ? "bg-blue-100 text-blue-700" : "bg-slate-100 text-slate-700"}`}>
                    {t.status?.toUpperCase()}
                  </span>
                </td>
                <td className="px-3 py-2 text-center font-bold">{t.followers_copied ?? 0}</td>
                <td className="px-3 py-2 text-slate-500">{fmtDate(t.opened_at)}</td>
                <td className="px-3 py-2 text-right">
                  {t.status === "open" && (
                    <button onClick={() => forceClose.mutate(t.master_id)} title="Force close" className="text-red-500 hover:text-red-700">
                      <Square className="w-3.5 h-3.5" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {!isLoading && !data?.trades?.length && (
              <tr><td colSpan={13} className="text-center p-6 text-slate-400">No master trades yet — simulator warming up</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// =====================================================================
// FOLLOWERS TAB
// =====================================================================
function FollowersTab() {
  const [selected, setSelected] = useState<string | null>(null);
  const { data: summary } = useQuery({
    queryKey: ["admin-followers-summary"],
    queryFn: async () => (await api.get("/copy_trading/admin/followers/summary")).data,
    refetchInterval: 5000,
  });
  const { data: followers } = useQuery({
    queryKey: ["admin-trader-followers", selected],
    queryFn: async () => selected ? (await api.get(`/copy_trading/admin/traders/${selected}/followers`)).data : null,
    enabled: !!selected,
    refetchInterval: 5000,
  });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard label="Total Followers" value={summary?.unique_followers ?? 0} icon={Users} />
        <StatCard label="Active" value={summary?.active ?? 0} tint="green" icon={CheckCircle2} />
        <StatCard label="Paused" value={summary?.paused ?? 0} tint="amber" icon={Pause} />
        <StatCard label="Stopped" value={summary?.stopped ?? 0} icon={Square} />
        <StatCard label="Halted" value={summary?.halted ?? 0} tint="red" icon={XCircle} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 font-bold text-sm text-slate-700">Top Traders by Followers</div>
          {(summary?.top_traders || []).map((t: any) => (
            <button key={t.trader_id} onClick={() => setSelected(t.trader_id)}
              className={`w-full flex items-center justify-between px-4 py-2.5 hover:bg-slate-50 text-left border-b border-slate-100 last:border-b-0 ${selected === t.trader_id ? "bg-indigo-50" : ""}`}>
              <div>
                <div className="text-sm font-semibold text-slate-800">{t.trader_name}</div>
                <div className="text-xs text-slate-500">{t.trader_id}</div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-sm font-bold text-indigo-600">{t.follower_count}</span>
                <ChevronRight className="w-4 h-4 text-slate-400" />
              </div>
            </button>
          ))}
          {!summary?.top_traders?.length && <div className="p-6 text-center text-slate-400 text-sm">No active copy relationships yet</div>}
        </div>

        <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 font-bold text-sm text-slate-700">
            {followers?.trader ? `${followers.trader.name} — Followers (${followers.followers.length})` : "Select a trader to view followers"}
          </div>
          <div className="max-h-[500px] overflow-y-auto">
            {followers?.followers?.map((f: any) => (
              <div key={f.copy_id} className="px-4 py-2.5 border-b border-slate-100 text-xs">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-semibold text-slate-800">{f.user?.full_name || f.user_id}</div>
                    <div className="text-slate-500">{f.user?.email || f.user?.mobile || "—"}</div>
                  </div>
                  <div className="text-right">
                    <span className={`px-2 py-0.5 rounded font-bold text-[10px] ${f.status === "active" ? "bg-green-100 text-green-700" : f.status === "paused" ? "bg-amber-100 text-amber-700" : f.status === "halted" ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-500"}`}>
                      {f.status?.toUpperCase()}
                    </span>
                    <div className={`mt-1 tabular-nums font-bold ${f.live?.lifetime_pnl_usd >= 0 ? "text-green-600" : "text-red-600"}`}>
                      {f.live?.lifetime_pnl_usd >= 0 ? "+" : ""}${(f.live?.lifetime_pnl_usd || 0).toFixed(2)}
                    </div>
                    <div className="text-slate-500">Open: {f.live?.open_positions || 0}</div>
                  </div>
                </div>
                <div className="mt-1 text-slate-500">
                  Mode: <b>{f.settings?.mode}</b> · Since {fmtDate(f.started_at)}
                  {f.halt_reason && <span className="ml-2 text-red-500">· Halted: {f.halt_reason}</span>}
                </div>
              </div>
            ))}
            {selected && !followers?.followers?.length && (
              <div className="p-6 text-center text-slate-400 text-sm">No followers on this trader</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// =====================================================================
// ANALYTICS TAB
// =====================================================================
function AnalyticsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-copy-analytics"],
    queryFn: async () => (await api.get("/copy_trading/admin/analytics")).data,
    refetchInterval: 15000,
  });
  if (isLoading) return <div className="p-8 text-center text-slate-400">Loading analytics…</div>;
  if (!data) return null;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Total Master Trades" value={data.trades.total_master} icon={Radio} />
        <StatCard label="Total Mirrored" value={data.trades.total_mirrored} icon={Users} />
        <StatCard label="Open Positions" value={data.trades.open_positions} tint="blue" icon={Activity} />
        <StatCard label="Closed Trades" value={data.trades.closed_trades} icon={CheckCircle2} />

        <StatCard label="Total Profit" value={`$${data.pnl.total_profit_usd.toFixed(2)}`} tint="green" icon={TrendingUp} />
        <StatCard label="Total Loss" value={`$${Math.abs(data.pnl.total_loss_usd).toFixed(2)}`} tint="red" icon={TrendingDown} />
        <StatCard label="Net P&L" value={`${data.pnl.net_usd >= 0 ? "+" : ""}$${data.pnl.net_usd.toFixed(2)}`} tint={data.pnl.net_usd >= 0 ? "green" : "red"} icon={LineChart} />
        <StatCard label="Win Rate" value={`${data.pnl.win_rate_pct}%`} icon={CheckCircle2} />

        <StatCard label="Daily ROI ($)" value={`$${data.roi.daily_usd.toFixed(2)}`} tint={data.roi.daily_usd >= 0 ? "green" : "red"} icon={TrendingUp} />
        <StatCard label="Weekly ROI ($)" value={`$${data.roi.weekly_usd.toFixed(2)}`} tint={data.roi.weekly_usd >= 0 ? "green" : "red"} icon={TrendingUp} />
        <StatCard label="Monthly ROI ($)" value={`$${data.roi.monthly_usd.toFixed(2)}`} tint={data.roi.monthly_usd >= 0 ? "green" : "red"} icon={TrendingUp} />
        <StatCard label="Avg Trader Risk" value={`${data.roi.avg_trader_risk}/10`} icon={Activity} />

        <StatCard label="Active Copies" value={data.copies.active} tint="green" icon={Users} />
        <StatCard label="Daily New Copies" value={data.copies.daily_new} icon={Users} />
        <StatCard label="Monthly New Copies" value={data.copies.monthly_new} icon={Users} />
        <StatCard label="Unique Followers" value={data.copies.unique_followers} icon={Users} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <LeaderCard title="Highest ROI Trader" leader={data.leaders.highest_roi} field="total_roi_pct" suffix="%" />
        <LeaderCard title="Highest Win Rate" leader={data.leaders.highest_win_rate} field="win_rate_pct" suffix="%" />
        <LeaderCard title="Highest AUM" leader={data.leaders.highest_aum} field="aum_usd" prefix="$" />
      </div>

      {data.copies.most_copied && (
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <div className="text-xs font-bold text-slate-500 uppercase mb-2">Most Copied Trader</div>
          <div className="flex items-baseline justify-between">
            <div className="text-xl font-bold text-slate-900">{data.copies.most_copied.name}</div>
            <div className="text-2xl font-bold text-indigo-600">{data.copies.most_copied.follower_count} followers</div>
          </div>
        </div>
      )}
    </div>
  );
}
function LeaderCard({ title, leader, field, prefix = "", suffix = "" }: any) {
  if (!leader) return <div className="bg-white border border-slate-200 rounded-xl p-5"><div className="text-xs font-bold text-slate-500 uppercase mb-2">{title}</div><div className="text-slate-400 text-sm">—</div></div>;
  const val = leader[field];
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5">
      <div className="text-xs font-bold text-slate-500 uppercase mb-2">{title}</div>
      <div className="text-lg font-bold text-slate-900">{leader.name}</div>
      <div className="text-xs text-slate-500 mb-2">{leader.style}</div>
      <div className="text-2xl font-black text-indigo-600 tabular-nums">
        {prefix}{typeof val === "number" ? val.toLocaleString() : val}{suffix}
      </div>
    </div>
  );
}

// =====================================================================
// SYSTEM HEALTH TAB
// =====================================================================
function HealthTab() {
  const { data } = useQuery({
    queryKey: ["admin-system-health"],
    queryFn: async () => (await api.get("/copy_trading/admin/system-health")).data,
    refetchInterval: 3000,
  });
  if (!data) return <div className="p-8 text-center text-slate-400">Loading system health…</div>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Event Queue" value={data.event_queue_size} icon={Radio} />
        <StatCard label="Active Simulators" value={data.active_simulators} icon={Play} tint="green" />
        <StatCard label="Active Followers" value={data.active_followers} icon={Users} />
        <StatCard label="Active Copy Sessions" value={data.active_copy_sessions} icon={Activity} />

        <StatCard label="Avg Fan-Out" value={`${data.avg_fanout_ms} ms`} icon={Zap} />
        <StatCard label="Avg Execution" value={`${data.avg_exec_ms} ms`} icon={Zap} />
        <StatCard label="Events Processed" value={data.events_processed} icon={Radio} />
        <StatCard label="Failed Mirrors" value={data.failed_mirrors} tint={data.failed_mirrors > 0 ? "red" : undefined} icon={XCircle} />

        <StatCard label="Retry Queue" value={data.retry_queue_size} tint={data.retry_queue_size > 0 ? "amber" : undefined} icon={RefreshCw} />
        <StatCard label="Broker" value={data.broker?.name} tint={data.broker?.ok ? "green" : "red"} icon={ShieldCheck} />
        <StatCard label="Server" value={data.server?.ok ? "OK" : "DOWN"} tint={data.server?.ok ? "green" : "red"} icon={CheckCircle2} />
        <StatCard label="Database" value={data.database?.ok ? "OK" : "DOWN"} tint={data.database?.ok ? "green" : "red"} icon={CheckCircle2} />
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-bold text-slate-700 mb-3">Simulator</h3>
        <div className="text-xs text-slate-500 grid grid-cols-2 md:grid-cols-3 gap-3">
          <KV label="Enabled" value={String(data.simulator?.enabled)} />
          <KV label="Speed" value={data.simulator?.speed} />
          <KV label="Active Traders" value={data.simulator?.active_traders} />
          <KV label="Open Master Trades" value={data.simulator?.open_master_trades} />
          <KV label="Lifetime Master Trades" value={data.simulator?.lifetime_master_trades} />
          <KV label="Server Uptime" value={`${Math.round(data.server?.uptime_sec / 60)} min`} />
        </div>
      </div>
    </div>
  );
}
function KV({ label, value }: any) {
  return (
    <div>
      <div className="text-[10px] font-bold uppercase text-slate-400">{label}</div>
      <div className="text-sm font-bold text-slate-800">{String(value)}</div>
    </div>
  );
}

// =====================================================================
// CONFIG TAB
// =====================================================================
function ConfigTab() {
  const { data, refetch } = useQuery({
    queryKey: ["admin-copy-config"],
    queryFn: async () => (await api.get("/copy_trading/admin/config")).data,
  });
  const [form, setForm] = useState<any>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data?.defaults) setForm(data.defaults);
  }, [data]);

  const save = async () => {
    setSaving(true); setSaved(false);
    try {
      await api.put("/copy_trading/admin/config/defaults", form);
      setSaved(true);
      refetch();
      setTimeout(() => setSaved(false), 2500);
    } finally { setSaving(false); }
  };

  if (!data) return <div className="p-8 text-center text-slate-400">Loading…</div>;

  const numField = (key: string, label: string, step = 0.1) => (
    <div>
      <label className="block text-xs font-bold text-slate-500 mb-1">{label}</label>
      <input
        type="number" step={step}
        value={form[key] ?? ""}
        onChange={(e) => setForm({ ...form, [key]: e.target.value === "" ? "" : Number(e.target.value) })}
        className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
      />
    </div>
  );
  const boolField = (key: string, label: string) => (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={!!form[key]} onChange={(e) => setForm({ ...form, [key]: e.target.checked })} />
      {label}
    </label>
  );

  return (
    <div className="space-y-5">
      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-bold text-slate-700 mb-3">Default Copy Settings</h3>
        <p className="text-xs text-slate-500 mb-4">Applied to new copies. Existing copies keep their own overrides.</p>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <div>
            <label className="block text-xs font-bold text-slate-500 mb-1">Default Mode</label>
            <select value={form.mode ?? ""} onChange={(e) => setForm({ ...form, mode: e.target.value })}
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">
              <option value="multiplier">multiplier</option>
              <option value="fixed_lot">fixed_lot</option>
              <option value="equity_percent">equity_percent</option>
            </select>
          </div>
          {numField("multiplier", "Default Multiplier")}
          {numField("fixed_lot", "Default Fixed Lot")}
          {numField("equity_percent", "Default Equity %")}
          {numField("max_daily_loss_pct", "Max Daily Loss %")}
          {numField("max_drawdown_pct", "Max Drawdown %")}
          {numField("equity_protection_pct", "Equity Protection %")}
          {numField("max_open_trades", "Max Open Trades", 1)}
          {numField("min_lot_size", "Min Lot Size", 0.01)}
          {numField("max_lot_size", "Max Lot Size", 0.1)}
          {numField("slippage_pips", "Slippage (pips)", 1)}
        </div>

        <div className="mt-5 flex flex-wrap gap-5">
          {boolField("auto_close_on_equity_protection", "Auto-close on Equity Protection")}
          {boolField("auto_pause_on_daily_loss", "Auto-pause on Daily Loss")}
          {boolField("auto_copy_new_trades", "Auto-copy New Trades")}
          {boolField("copy_existing_open_trades", "Copy Existing Open Trades")}
        </div>

        <div className="mt-5 flex items-center gap-3">
          <button disabled={saving} onClick={save}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-bold rounded-lg disabled:opacity-60">
            {saving ? "Saving…" : "Save Defaults"}
          </button>
          {saved && <span className="text-sm text-green-600 font-bold">Saved ✓</span>}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-bold text-slate-700 mb-3">Simulation Config (read-only preview)</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <KV label="Enabled" value={String(data.sim?.enabled)} />
          <KV label="Speed" value={data.sim?.speed} />
        </div>
        <p className="mt-2 text-xs text-slate-500">Simulation runtime state is edited via the Simulation tab.</p>
      </div>
    </div>
  );
}

// =====================================================================
// Shared
// =====================================================================
function StatCard({ label, value, icon: Ic, tint }: any) {
  const tintClass = tint === "green" ? "text-green-600 bg-green-50"
    : tint === "red" ? "text-red-600 bg-red-50"
    : tint === "amber" ? "text-amber-600 bg-amber-50"
    : tint === "blue" ? "text-blue-600 bg-blue-50"
    : "text-slate-700 bg-slate-100";
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[10px] font-bold uppercase text-slate-400">{label}</div>
          <div className="mt-1 text-xl font-bold text-slate-900 tabular-nums">{value}</div>
        </div>
        {Ic && <div className={`p-2 rounded-lg ${tintClass}`}><Ic className="w-4 h-4" /></div>}
      </div>
    </div>
  );
}

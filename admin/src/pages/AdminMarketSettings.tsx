import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { LineChart, RefreshCw, Save, Settings2, Server, Cpu, PowerOff, Power } from "lucide-react";

type S = {
  provider: string; refresh_seconds: number; cache_seconds: number; maintenance: boolean;
  enabled_instruments: string[]; news_provider: string; calendar_provider: string;
};
type Status = { settings: S; api_keys_masked: Record<string, string>; providers_registered: string[]; instruments: string[]; cache_entries: number; watchers: number };

export default function AdminMarketSettings() {
  const [status, setStatus] = useState<Status | null>(null);
  const [s, setS] = useState<S | null>(null);
  const [keys, setKeys] = useState<Record<string, string>>({ alpha_vantage: "", twelve_data: "", polygon: "" });
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ ok: boolean; msg: string } | null>(null);

  const load = () => api.get("/admin/market/status").then((r) => { setStatus(r.data); setS(r.data.settings); });
  useEffect(() => { load(); }, []);

  const flash = (ok: boolean, msg: string) => { setToast({ ok, msg }); setTimeout(() => setToast(null), 3000); };

  const save = async () => {
    if (!s) return;
    setSaving(true);
    try {
      const payload: any = { ...s };
      const nonEmpty = Object.fromEntries(Object.entries(keys).filter(([, v]) => v.trim().length > 0));
      if (Object.keys(nonEmpty).length) payload.api_keys = nonEmpty;
      await api.put("/admin/market/settings", payload);
      await load(); flash(true, "Saved");
    } catch (e: any) { flash(false, e?.response?.data?.detail || "Failed"); }
    finally { setSaving(false); }
  };

  const forceRefresh = async () => { await api.post("/admin/market/refresh"); flash(true, "Cache cleared"); load(); };

  const toggleInstrument = (sym: string) => {
    if (!s) return;
    const set = new Set(s.enabled_instruments);
    if (set.has(sym)) set.delete(sym); else set.add(sym);
    setS({ ...s, enabled_instruments: Array.from(set) });
  };

  if (!s || !status) return <div className="p-10 text-slate-400 text-center"><RefreshCw className="w-6 h-6 mx-auto animate-spin" /></div>;

  return (
    <div className="space-y-6">
      {toast && <div className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-bold ${toast.ok ? "bg-emerald-600" : "bg-rose-600"} text-white`}>{toast.msg}</div>}

      <div className="rounded-3xl bg-gradient-to-br from-sky-600 via-blue-700 to-slate-900 p-6 text-white relative overflow-hidden">
        <div className="absolute -right-6 -top-8 opacity-20"><LineChart className="w-40 h-40" /></div>
        <div className="flex items-center gap-2 text-xs font-bold tracking-widest uppercase text-sky-200"><Settings2 className="w-4 h-4" /> Sprint 6 · Market Intelligence</div>
        <h1 className="text-3xl font-black mt-1">Market Settings</h1>
        <p className="text-sky-100 text-sm mt-1">Configure providers, instruments, cache and maintenance mode.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "Provider", value: s.provider.toUpperCase(), icon: Server, tone: "from-indigo-500 to-blue-700" },
          { label: "Enabled Instruments", value: s.enabled_instruments.length, icon: LineChart, tone: "from-emerald-500 to-teal-600" },
          { label: "Cache entries", value: status.cache_entries, icon: Cpu, tone: "from-amber-500 to-orange-600" },
          { label: "Watchers", value: status.watchers, icon: Server, tone: "from-sky-500 to-blue-600" },
        ].map((c) => (
          <div key={c.label} className="bg-white rounded-2xl p-4 border border-slate-200">
            <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${c.tone} flex items-center justify-center text-white mb-2`}><c.icon className="w-4 h-4" /></div>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wide">{c.label}</p>
            <p className="text-2xl font-black text-brand-navy mt-1">{c.value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
          <p className="font-black text-brand-navy">Provider</p>
          <Field label="Data Provider"><select value={s.provider} onChange={(e) => setS({ ...s, provider: e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold">{status.providers_registered.map((p) => <option key={p} value={p}>{p}</option>)}</select></Field>
          <Field label="News Provider"><select value={s.news_provider} onChange={(e) => setS({ ...s, news_provider: e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold"><option value="mock">mock</option></select></Field>
          <Field label="Calendar Provider"><select value={s.calendar_provider} onChange={(e) => setS({ ...s, calendar_provider: e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold"><option value="mock">mock</option></select></Field>
          <Field label="Refresh interval (sec)"><input type="number" min={5} max={300} value={s.refresh_seconds} onChange={(e) => setS({ ...s, refresh_seconds: +e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold" /></Field>
          <Field label="Cache TTL (sec)"><input type="number" min={2} max={120} value={s.cache_seconds} onChange={(e) => setS({ ...s, cache_seconds: +e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold" /></Field>
          <div className="pt-2 border-t border-slate-100">
            <label className="flex items-center gap-3 cursor-pointer">
              <button onClick={() => setS({ ...s, maintenance: !s.maintenance })} className={`w-11 h-6 rounded-full p-0.5 transition ${s.maintenance ? "bg-rose-600" : "bg-emerald-500"}`}>
                <div className={`w-5 h-5 rounded-full bg-white transition ${s.maintenance ? "translate-x-5" : ""}`} />
              </button>
              <div><p className="text-sm font-black text-brand-navy">{s.maintenance ? "Maintenance ON" : "Live"}</p><p className="text-[11px] text-slate-500">{s.maintenance ? "All read endpoints return 503" : "Users see live data"}</p></div>
            </label>
          </div>
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-3">
          <p className="font-black text-brand-navy">API Keys</p>
          <p className="text-xs text-slate-500">Stored securely; masked on read. Filled keys enable future providers.</p>
          {Object.entries(status.api_keys_masked).map(([k, masked]) => (
            <Field key={k} label={k.replace(/_/g, " ").toUpperCase()} hint={masked ? `Current: ${masked}` : "Not set"}>
              <input value={keys[k] || ""} onChange={(e) => setKeys({ ...keys, [k]: e.target.value })} placeholder={masked ? "(set) — enter new to update" : "Enter key"}
                className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-mono" />
            </Field>
          ))}
        </div>

        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-5 space-y-3">
          <p className="font-black text-brand-navy">Enabled Instruments</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {status.instruments.map((sym) => {
              const on = s.enabled_instruments.includes(sym);
              return (
                <button key={sym} onClick={() => toggleInstrument(sym)} className={`px-3 py-2 rounded-lg border text-sm font-bold text-left inline-flex items-center justify-between ${on ? "bg-brand-primary/10 border-brand-primary text-brand-primary" : "bg-white border-slate-200 text-slate-500"}`}>
                  <span className="font-mono text-xs">{sym}</span>
                  {on ? <Power className="w-3.5 h-3.5" /> : <PowerOff className="w-3.5 h-3.5 opacity-50" />}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <button onClick={forceRefresh} className="px-4 py-2.5 rounded-xl border border-slate-200 text-sm font-bold inline-flex items-center gap-2"><RefreshCw className="w-4 h-4" />Force Refresh Cache</button>
        <button onClick={save} disabled={saving} className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-sky-600 to-blue-700 text-white font-black text-sm inline-flex items-center gap-2 disabled:opacity-50">
          {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save
        </button>
      </div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <div><label className="text-xs font-bold text-slate-600 uppercase tracking-wide block mb-1">{label}</label>{children}{hint && <p className="text-[11px] text-slate-400 mt-1">{hint}</p>}</div>;
}

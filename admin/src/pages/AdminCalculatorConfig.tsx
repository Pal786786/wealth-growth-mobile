import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Calculator, Save, RefreshCw, AlertTriangle } from "lucide-react";

type TypeCfg = { enabled: boolean; return_min: number; return_max: number; return_default: number; label: string };
type Config = { enabled: boolean; min_amount: number; max_amount: number; types: Record<string, TypeCfg> };

const TABS = [
  { id: "onetime", title: "One Time Investment" },
  { id: "sip", title: "SIP" },
  { id: "daily", title: "Daily Profit" },
  { id: "compound", title: "Compound Growth" },
];

export default function AdminCalculatorConfig() {
  const qc = useQueryClient();
  const [cfg, setCfg] = useState<Config | null>(null);
  const [dirty, setDirty] = useState(false);

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["calc-config"],
    queryFn: async () => (await api.get("/admin/calculator/config")).data as Config,
  });

  useEffect(() => { if (data && !dirty) setCfg(JSON.parse(JSON.stringify(data))); }, [data]);

  const save = useMutation({
    mutationFn: async () => (await api.put("/admin/calculator/config", cfg)).data,
    onSuccess: () => { setDirty(false); qc.invalidateQueries({ queryKey: ["calc-config"] }); },
  });

  if (!cfg) return <div className="text-slate-400 p-6">Loading…</div>;

  const update = (patch: Partial<Config>) => { setCfg({ ...cfg, ...patch }); setDirty(true); };
  const updateType = (id: string, patch: Partial<TypeCfg>) => {
    setCfg({ ...cfg, types: { ...cfg.types, [id]: { ...cfg.types[id], ...patch } } });
    setDirty(true);
  };

  const errors: string[] = [];
  if (cfg.min_amount >= cfg.max_amount) errors.push("Min amount must be less than Max amount");
  TABS.forEach(t => {
    const tc = cfg.types[t.id];
    if (tc && tc.return_min >= tc.return_max) errors.push(`${t.title}: return min must be less than max`);
  });

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2"><Calculator className="w-6 h-6" /> Calculator Settings</h2>
          <p className="text-sm text-slate-500 mt-1">Configure investment calculator limits and types. Changes apply instantly to mobile users.</p>
        </div>
        <button onClick={() => refetch()} className="btn-ghost gap-2 text-sm"><RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Reload</button>
      </div>

      {errors.length > 0 ? (
        <div className="card bg-red-50 border-red-200 border">
          <p className="font-bold text-red-800 mb-1"><AlertTriangle className="w-4 h-4 inline mr-1" /> Validation issues</p>
          <ul className="list-disc list-inside text-sm text-red-700">{errors.map((e,i)=><li key={i}>{e}</li>)}</ul>
        </div>
      ) : null}

      {/* Master switch */}
      <div className="card">
        <label className="flex items-center gap-3 cursor-pointer">
          <input type="checkbox" checked={cfg.enabled} onChange={e => update({ enabled: e.target.checked })} className="w-5 h-5" />
          <div>
            <p className="font-bold text-brand-navy">Calculator Module Enabled</p>
            <p className="text-xs text-slate-500">When OFF, mobile app shows "calculator disabled" message</p>
          </div>
        </label>
      </div>

      {/* Amount range */}
      <div className="card space-y-3">
        <p className="font-bold text-brand-navy">Amount Range</p>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs font-bold text-slate-600">Minimum (₹)</label>
            <input type="number" className="input mt-1" value={cfg.min_amount} onChange={e => update({ min_amount: Number(e.target.value) })} />
          </div>
          <div>
            <label className="text-xs font-bold text-slate-600">Maximum (₹)</label>
            <input type="number" className="input mt-1" value={cfg.max_amount} onChange={e => update({ max_amount: Number(e.target.value) })} />
          </div>
        </div>
      </div>

      {/* Per-calculator config */}
      <div className="grid md:grid-cols-2 gap-3">
        {TABS.map(t => {
          const tc = cfg.types[t.id];
          if (!tc) return null;
          return (
            <div key={t.id} className="card space-y-3">
              <div className="flex items-center justify-between">
                <p className="font-bold text-brand-navy">{t.title}</p>
                <label className="flex items-center gap-2 cursor-pointer text-xs">
                  <input type="checkbox" checked={tc.enabled} onChange={e => updateType(t.id, { enabled: e.target.checked })} />
                  <span className={tc.enabled ? "text-emerald-600 font-bold" : "text-slate-400"}>{tc.enabled ? "Enabled" : "Disabled"}</span>
                </label>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <NumField label="Min %" value={tc.return_min} onChange={v => updateType(t.id, { return_min: v })} />
                <NumField label="Max %" value={tc.return_max} onChange={v => updateType(t.id, { return_max: v })} />
                <NumField label="Default %" value={tc.return_default} onChange={v => updateType(t.id, { return_default: v })} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Save bar */}
      <div className="card sticky bottom-3 bg-white border-2 border-brand-primary/30 flex justify-end gap-2">
        <button onClick={() => { setDirty(false); setCfg(JSON.parse(JSON.stringify(data))); }} disabled={!dirty} className="btn-ghost text-sm">Discard</button>
        <button onClick={() => save.mutate()} disabled={!dirty || save.isPending || errors.length > 0} className="btn-primary text-sm gap-2">
          <Save className="w-4 h-4" /> {save.isPending ? "Saving…" : dirty ? "Save & Apply" : "No changes"}
        </button>
        {save.isSuccess && !dirty ? <span className="text-xs text-emerald-600 self-center">✓ Saved. Mobile calculator using new values.</span> : null}
      </div>
    </div>
  );
}

function NumField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <label className="text-[11px] font-bold text-slate-500 block mb-0.5">{label}</label>
      <input type="number" step={0.1} className="input text-sm" value={value} onChange={e => onChange(Number(e.target.value))} />
    </div>
  );
}

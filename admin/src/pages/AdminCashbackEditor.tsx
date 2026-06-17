import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import {
  Trophy, Plus, X, Save, History as HistoryIcon, RotateCcw, AlertTriangle,
  GripVertical, Eye, EyeOff, RefreshCw, TrendingUp, Users as UsersIcon, ChevronUp, ChevronDown,
} from "lucide-react";

type Perk = { text: string; enabled: boolean };
type Tier = {
  id: string; name: string; min: number; rate: number; color?: string;
  emoji?: string; tagline?: string; points_multiplier: number; perks: Perk[];
  users_affected?: number;
};

const TIER_GRAD: Record<string, string> = {
  bronze: "from-orange-200 to-orange-400",
  silver: "from-slate-200 to-slate-400",
  gold: "from-yellow-300 to-amber-500",
  platinum: "from-sky-300 to-blue-500",
  diamond: "from-violet-300 to-fuchsia-500",
};

export default function AdminCashbackEditor() {
  const qc = useQueryClient();
  const [tiers, setTiers] = useState<Tier[]>([]);
  const [dirty, setDirty] = useState(false);
  const [reason, setReason] = useState("");
  const [showHistory, setShowHistory] = useState(false);

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["tier-config"],
    queryFn: async () => (await api.get("/admin/tier-config")).data,
  });

  const maxCashback = data?.max_cashback_rate_pct ?? 10;

  useEffect(() => {
    if (data?.tiers && !dirty) setTiers(JSON.parse(JSON.stringify(data.tiers)));
  }, [data?.updated_at]);

  const saveMut = useMutation({
    mutationFn: async () => (await api.put("/admin/tier-config", {
      tiers: tiers.map((t) => ({
        id: t.id, name: t.name, min: t.min, rate: t.rate, color: t.color,
        emoji: t.emoji, tagline: t.tagline, points_multiplier: t.points_multiplier,
        perks: t.perks,
      })),
      reason: reason || "Admin update",
    })).data,
    onSuccess: () => {
      setDirty(false); setReason("");
      qc.invalidateQueries({ queryKey: ["tier-config"] });
      qc.invalidateQueries({ queryKey: ["tier-analytics"] });
    },
  });

  const update = (idx: number, patch: Partial<Tier>) => {
    setTiers((curr) => curr.map((t, i) => i === idx ? { ...t, ...patch } : t));
    setDirty(true);
  };
  const addPerk = (idx: number) => update(idx, { perks: [...tiers[idx].perks, { text: "New benefit", enabled: true }] });
  const updatePerk = (tIdx: number, pIdx: number, patch: Partial<Perk>) =>
    update(tIdx, { perks: tiers[tIdx].perks.map((p, i) => i === pIdx ? { ...p, ...patch } : p) });
  const delPerk = (tIdx: number, pIdx: number) =>
    update(tIdx, { perks: tiers[tIdx].perks.filter((_, i) => i !== pIdx) });
  const movePerk = (tIdx: number, pIdx: number, dir: -1 | 1) => {
    const list = [...tiers[tIdx].perks];
    const j = pIdx + dir;
    if (j < 0 || j >= list.length) return;
    [list[pIdx], list[j]] = [list[j], list[pIdx]];
    update(tIdx, { perks: list });
  };

  // Validation
  const errors = useMemo(() => {
    const errs: string[] = [];
    for (let i = 0; i < tiers.length; i++) {
      const t = tiers[i];
      if (t.rate * 100 > maxCashback) errs.push(`${t.name}: cashback ${(t.rate*100).toFixed(2)}% exceeds max ${maxCashback}%`);
      if (i > 0 && t.min <= tiers[i-1].min && t.min !== 0) errs.push(`${t.name} threshold (${t.min}) must be greater than ${tiers[i-1].name} (${tiers[i-1].min})`);
      if (i > 0 && t.rate < tiers[i-1].rate) errs.push(`${t.name} cashback (${(t.rate*100).toFixed(2)}%) must be ≥ ${tiers[i-1].name} (${(tiers[i-1].rate*100).toFixed(2)}%)`);
    }
    return errs;
  }, [tiers, maxCashback]);

  // Impact preview
  const impact = useMemo(() => {
    if (!data?.tiers) return [];
    const out: string[] = [];
    tiers.forEach((nt, i) => {
      const ot = data.tiers[i];
      if (!ot) return;
      if (ot.rate !== nt.rate)
        out.push(`${nt.name}: cashback ${(ot.rate*100).toFixed(2)}% → ${(nt.rate*100).toFixed(2)}% · affects ${nt.users_affected || 0} users`);
      if (ot.min !== nt.min)
        out.push(`${nt.name}: threshold ${ot.min} → ${nt.min} pts`);
      if (ot.points_multiplier !== nt.points_multiplier)
        out.push(`${nt.name}: points multiplier ${ot.points_multiplier}× → ${nt.points_multiplier}×`);
    });
    return out;
  }, [tiers, data]);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2">
            <Trophy className="w-6 h-6" /> Cashback & Tier Editor
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Edit cashback %, thresholds, multipliers, and benefits for every loyalty tier.
            Changes apply instantly — no redeploy. Last updated: {data?.updated_at ? fmtDate(data.updated_at) : "—"}
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setShowHistory(true)} className="btn-ghost gap-2 text-sm">
            <HistoryIcon className="w-4 h-4" /> History
          </button>
          <button onClick={() => refetch()} className="btn-ghost gap-2 text-sm">
            <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Reload
          </button>
        </div>
      </div>

      <div className="bg-sky-50 border border-sky-200 rounded-2xl px-4 py-3 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-sky-600 mt-0.5" />
        <div className="text-sm text-sky-900">
          <p className="font-extrabold">Live configuration</p>
          <p>All tier settings are stored in MongoDB and read on every transaction. Maximum allowed cashback per tier: <b>{maxCashback}%</b>. Every change is audited and previous configurations are kept for rollback.</p>
        </div>
      </div>

      {/* Validation errors */}
      {errors.length > 0 ? (
        <div className="card bg-red-50 border-red-200 border">
          <p className="font-bold text-red-800 mb-1">⚠ Validation issues</p>
          <ul className="list-disc list-inside text-sm text-red-700 space-y-0.5">
            {errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      ) : null}

      {/* Tier cards */}
      <div className="grid lg:grid-cols-2 gap-4">
        {tiers.map((t, i) => (
          <div key={t.id} className="card space-y-3">
            <div className={`rounded-xl p-3 bg-gradient-to-br ${TIER_GRAD[t.id] || "from-slate-200 to-slate-300"} flex items-center gap-3 text-slate-900`}>
              <span className="text-3xl">{t.emoji}</span>
              <div className="flex-1">
                <p className="font-extrabold text-lg">{t.name}</p>
                <p className="text-xs opacity-80 flex items-center gap-2">
                  <UsersIcon className="w-3 h-3" /> {t.users_affected ?? 0} users · {(t.rate * 100).toFixed(2)}% cashback
                </p>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <Field label="Cashback %" type="number" step={0.05} min={0} max={maxCashback}
                     value={(t.rate * 100).toFixed(2)} onChange={(v) => update(i, { rate: Number(v) / 100 })} />
              <Field label="Threshold (pts)" type="number" min={0} step={50}
                     value={t.min} onChange={(v) => update(i, { min: Number(v) })} />
              <Field label="Points multiplier" type="number" step={0.5} min={0.5} max={20}
                     value={t.points_multiplier} onChange={(v) => update(i, { points_multiplier: Number(v) })} />
            </div>

            <div className="grid grid-cols-3 gap-2">
              <Field label="Display name" value={t.name} onChange={(v) => update(i, { name: v })} />
              <Field label="Emoji" value={t.emoji || ""} onChange={(v) => update(i, { emoji: v })} />
              <Field label="Color (hex)" value={t.color || ""} onChange={(v) => update(i, { color: v })} />
            </div>
            <Field label="Tagline (celebration message)" value={t.tagline || ""} onChange={(v) => update(i, { tagline: v })} />

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-[11px] font-bold uppercase text-slate-500 tracking-wide">Benefits</p>
                <button onClick={() => addPerk(i)} className="text-xs text-brand-primary font-bold hover:underline flex items-center gap-1">
                  <Plus className="w-3 h-3" /> Add benefit
                </button>
              </div>
              <div className="space-y-1.5">
                {t.perks.map((p, pi) => (
                  <div key={pi} className={`flex items-center gap-2 rounded-lg border px-2 py-1.5 ${p.enabled ? "bg-white border-slate-200" : "bg-slate-50 border-slate-200 opacity-60"}`}>
                    <div className="flex flex-col">
                      <button onClick={() => movePerk(i, pi, -1)} className="text-slate-400 hover:text-slate-700" title="Move up"><ChevronUp className="w-3 h-3" /></button>
                      <button onClick={() => movePerk(i, pi, 1)} className="text-slate-400 hover:text-slate-700" title="Move down"><ChevronDown className="w-3 h-3" /></button>
                    </div>
                    <input value={p.text} onChange={(e) => updatePerk(i, pi, { text: e.target.value })}
                           className="flex-1 text-sm focus:outline-none bg-transparent" />
                    <button onClick={() => updatePerk(i, pi, { enabled: !p.enabled })} className={p.enabled ? "text-emerald-600" : "text-slate-400"} title={p.enabled ? "Disable" : "Enable"}>
                      {p.enabled ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
                    </button>
                    <button onClick={() => delPerk(i, pi)} className="text-rose-500 hover:text-rose-700" title="Delete">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
                {t.perks.length === 0 ? <p className="text-xs text-slate-400 italic">No benefits configured.</p> : null}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Impact preview */}
      {dirty && impact.length > 0 ? (
        <div className="card bg-amber-50 border-amber-200 border">
          <p className="font-bold text-amber-800 mb-1 flex items-center gap-2"><TrendingUp className="w-4 h-4" /> Estimated impact</p>
          <ul className="list-disc list-inside text-sm text-amber-900 space-y-0.5">{impact.map((i, idx) => <li key={idx}>{i}</li>)}</ul>
        </div>
      ) : null}

      {/* Save row */}
      <div className="card sticky bottom-3 bg-white border-2 border-brand-primary/30 flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[200px]">
          <label className="text-[11px] font-bold uppercase text-slate-500">Change reason (audit log)</label>
          <input value={reason} onChange={(e) => setReason(e.target.value)} className="input mt-1" placeholder="e.g. Q3 cashback boost for Platinum/Diamond" />
        </div>
        <div className="flex gap-2">
          <button onClick={() => { setDirty(false); setTiers(JSON.parse(JSON.stringify(data?.tiers || []))); }}
                  disabled={!dirty}
                  className="btn-ghost text-sm">Discard</button>
          <button onClick={() => saveMut.mutate()}
                  disabled={!dirty || saveMut.isPending || errors.length > 0}
                  className="btn-primary text-sm gap-2">
            <Save className="w-4 h-4" />
            {saveMut.isPending ? "Saving…" : dirty ? "Save & Apply" : "No changes"}
          </button>
        </div>
        {saveMut.isError ? <p className="text-xs text-red-600 w-full">Save failed. Check validation errors and try again.</p> : null}
        {saveMut.isSuccess && !dirty ? <p className="text-xs text-emerald-600 w-full">✓ Changes applied. Mobile app + cashback engine using new values immediately.</p> : null}
      </div>

      {showHistory ? <HistoryDrawer onClose={() => setShowHistory(false)} onRollback={() => { refetch(); setDirty(false); }} /> : null}
    </div>
  );
}

function Field({ label, value, onChange, type, step, min, max }: any) {
  return (
    <div>
      <label className="text-[11px] font-bold uppercase text-slate-500 tracking-wide block mb-0.5">{label}</label>
      <input className="input" type={type || "text"} value={value} onChange={(e) => onChange(e.target.value)}
             step={step} min={min} max={max} />
    </div>
  );
}

function HistoryDrawer({ onClose, onRollback }: { onClose: () => void; onRollback: () => void }) {
  const { data, refetch } = useQuery({
    queryKey: ["tier-history"],
    queryFn: async () => (await api.get("/admin/tier-config/history?limit=20")).data,
  });
  const rollback = useMutation({
    mutationFn: async (id: string) => (await api.post(`/admin/tier-config/rollback/${id}`)).data,
    onSuccess: () => { refetch(); onRollback(); },
  });

  return (
    <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm flex items-stretch justify-end" onClick={onClose}>
      <div className="w-full max-w-xl bg-white h-full overflow-y-auto shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-white border-b border-slate-200 px-5 py-4 flex items-center justify-between z-10">
          <p className="font-extrabold text-brand-navy flex items-center gap-2"><HistoryIcon className="w-5 h-5" /> Rollback History</p>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-3">
          <p className="text-xs text-slate-500">Snapshots are taken automatically before every save and rollback. Click "Restore" to revert to that configuration.</p>
          {(data?.items || []).map((h: any) => (
            <div key={h.history_id} className="card">
              <div className="flex justify-between items-start mb-2">
                <div>
                  <p className="font-bold text-sm text-brand-navy">{h.action === "pre_rollback" ? "Before rollback" : "Replaced"}</p>
                  <p className="text-xs text-slate-500">{fmtDate(h.at)} · by {h.updated_by?.slice(0, 14)}…</p>
                  {h.reason ? <p className="text-xs italic text-slate-600 mt-1">"{h.reason}"</p> : null}
                </div>
                <button
                  onClick={() => { if (confirm("Restore this configuration? Current settings will be saved as a new history entry first.")) rollback.mutate(h.history_id); }}
                  disabled={rollback.isPending}
                  className="btn-ghost text-xs gap-1 border border-slate-200"
                >
                  <RotateCcw className="w-3.5 h-3.5" /> Restore
                </button>
              </div>
              <div className="grid grid-cols-5 gap-1.5">
                {(h.snapshot || []).map((t: Tier) => (
                  <div key={t.id} className={`rounded-md p-1.5 bg-gradient-to-br ${TIER_GRAD[t.id] || "from-slate-200 to-slate-300"} text-center`}>
                    <p className="text-[18px]">{t.emoji}</p>
                    <p className="text-[10px] font-bold">{(t.rate*100).toFixed(1)}%</p>
                  </div>
                ))}
              </div>
            </div>
          ))}
          {!data?.items?.length ? <p className="text-sm text-slate-400 text-center py-6">No history yet.</p> : null}
        </div>
      </div>
    </div>
  );
}

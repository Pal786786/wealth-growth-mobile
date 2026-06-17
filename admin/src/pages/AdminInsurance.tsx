import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate, fmtCurrency } from "../lib/api";
import {
  Shield, Heart, Car, Plane, Search, RefreshCw, CheckCircle2, AlertTriangle,
  FileText, Briefcase,
} from "lucide-react";

type Policy = {
  policy_id: string;
  user_id: string;
  plan_id: string;
  plan_name: string;
  plan_type: "health" | "life" | "motor" | "travel";
  premium: number;
  cover_amount?: number;
  status: string;
  starts_at?: string;
  expires_at?: string;
  created_at?: string;
};

const TYPE_META: Record<string, { Icon: any; label: string; cls: string }> = {
  health: { Icon: Heart,  label: "Health", cls: "bg-red-50 text-red-700 border-red-200" },
  life:   { Icon: Shield, label: "Life",   cls: "bg-sky-50 text-sky-700 border-sky-200" },
  motor:  { Icon: Car,    label: "Motor",  cls: "bg-amber-50 text-amber-700 border-amber-200" },
  travel: { Icon: Plane,  label: "Travel", cls: "bg-violet-50 text-violet-700 border-violet-200" },
};

export default function AdminInsurance() {
  const _qc = useQueryClient();
  void _qc;
  const [tab, setTab] = useState<"policies" | "catalog">("policies");
  const [planType, setPlanType] = useState("all");
  const [search, setSearch] = useState("");

  const { data: policies, isLoading: pLoading, isFetching: pFetching, refetch } = useQuery({
    queryKey: ["admin-policies"],
    queryFn: async () => (await api.get<Policy[]>("/admin/super/policies?limit=300")).data,
  });

  const { data: catalog } = useQuery({
    queryKey: ["insurance-catalog"],
    queryFn: async () => (await api.get("/insurance/plans")).data as any[],
  });

  const filtered = useMemo(() => {
    const items = policies || [];
    return items.filter((p) => {
      if (planType !== "all" && p.plan_type !== planType) return false;
      if (search) {
        const q = search.toLowerCase();
        if (![p.plan_name, p.user_id, p.policy_id].some((v) => (v || "").toLowerCase().includes(q))) return false;
      }
      return true;
    });
  }, [policies, planType, search]);

  const stats = useMemo(() => {
    const items = policies || [];
    return {
      total: items.length,
      active: items.filter((p) => p.status === "active").length,
      gwp: items.reduce((s, p) => s + (p.premium || 0), 0),
      by_type: {
        health: items.filter((p) => p.plan_type === "health").length,
        life:   items.filter((p) => p.plan_type === "life").length,
        motor:  items.filter((p) => p.plan_type === "motor").length,
        travel: items.filter((p) => p.plan_type === "travel").length,
      },
    };
  }, [policies]);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2">
            <Shield className="w-6 h-6" /> Insurance Management
          </h2>
          <p className="text-sm text-slate-500 mt-1">All purchased policies and plan catalog.</p>
        </div>
        <div className="flex gap-2">
          <div className="flex gap-1 bg-slate-100 rounded-xl p-1">
            {(["policies", "catalog"] as const).map((t) => (
              <button key={t} onClick={() => setTab(t)} className={`px-3 py-1.5 text-xs font-bold rounded-lg ${tab === t ? "bg-white shadow text-brand-navy" : "text-slate-500"}`}>
                {t === "policies" ? "Policies" : "Plan Catalog"}
              </button>
            ))}
          </div>
          <button onClick={() => refetch()} className="btn-ghost gap-2 text-sm">
            <RefreshCw className={`w-4 h-4 ${pFetching ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Total policies" value={stats.total} cls="from-sky-500 to-blue-600" Icon={Briefcase} />
        <Stat label="Active policies" value={stats.active} cls="from-emerald-500 to-emerald-600" Icon={CheckCircle2} />
        <Stat label="Gross premium" value={fmtCurrency(stats.gwp)} cls="from-violet-500 to-fuchsia-600" Icon={FileText} />
        <Stat label="Plans in catalog" value={catalog?.length || 0} cls="from-amber-500 to-orange-600" Icon={Shield} />
      </div>

      {tab === "policies" ? (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {Object.entries(TYPE_META).map(([k, m]) => (
              <div key={k} className="card flex items-center gap-3">
                <div className={`p-2 rounded-xl ${m.cls} border`}><m.Icon className="w-5 h-5" /></div>
                <div>
                  <p className="text-xs text-slate-500 font-bold uppercase">{m.label}</p>
                  <p className="text-xl font-extrabold text-brand-navy">{(stats.by_type as any)[k] || 0}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="card flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2 flex-1 min-w-[220px]">
              <Search className="w-4 h-4 text-slate-400" />
              <input className="input" placeholder="Search plan, user, policy id…" value={search} onChange={(e) => setSearch(e.target.value)} />
            </div>
            <select className="input max-w-[180px]" value={planType} onChange={(e) => setPlanType(e.target.value)}>
              <option value="all">All types</option>
              <option value="health">Health</option>
              <option value="life">Life</option>
              <option value="motor">Motor</option>
              <option value="travel">Travel</option>
            </select>
          </div>

          <div className="card overflow-hidden">
            {pLoading ? <div className="text-slate-400 py-8 text-center">Loading…</div> : null}
            {!pLoading && filtered.length === 0 ? <div className="text-slate-400 py-10 text-center">No policies match your filters.</div> : null}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 uppercase font-bold border-b border-slate-200">
                    <th className="py-2 px-1">Type</th>
                    <th className="py-2 px-1">Plan</th>
                    <th className="py-2 px-1">User</th>
                    <th className="py-2 px-1 text-right">Premium</th>
                    <th className="py-2 px-1 text-right">Cover</th>
                    <th className="py-2 px-1">Status</th>
                    <th className="py-2 px-1">Bought</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((p) => {
                    const m = TYPE_META[p.plan_type] || TYPE_META.health;
                    return (
                      <tr key={p.policy_id} className="border-b border-slate-100 hover:bg-slate-50">
                        <td className="py-2 px-1"><span className={`badge ${m.cls}`}><m.Icon className="w-3 h-3 inline mr-1" />{m.label}</span></td>
                        <td className="py-2 px-1 font-semibold text-slate-800 max-w-[220px] truncate">{p.plan_name}</td>
                        <td className="py-2 px-1 font-mono text-xs text-slate-500">{p.user_id.slice(0, 12)}…</td>
                        <td className="py-2 px-1 text-right font-bold">{fmtCurrency(p.premium)}</td>
                        <td className="py-2 px-1 text-right">{p.cover_amount ? fmtCurrency(p.cover_amount) : "—"}</td>
                        <td className="py-2 px-1">
                          {p.status === "active" ? <span className="badge bg-emerald-50 text-emerald-700 border border-emerald-200">Active</span> :
                           <span className="badge bg-amber-50 text-amber-700 border border-amber-200">{p.status}</span>}
                        </td>
                        <td className="py-2 px-1 text-xs text-slate-500">{fmtDate(p.created_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      ) : null}

      {tab === "catalog" ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {(catalog || []).map((p: any) => {
            const m = TYPE_META[p.type] || TYPE_META.health;
            return (
              <div key={p.id} className="card flex flex-col gap-2">
                <div className="flex items-center gap-2">
                  <div className={`p-2 rounded-xl ${m.cls} border`}><m.Icon className="w-5 h-5" /></div>
                  <div className="flex-1">
                    <p className="font-extrabold text-brand-navy text-sm">{p.name}</p>
                    <p className="text-xs text-slate-500">{m.label}</p>
                  </div>
                </div>
                <p className="text-xs text-slate-600 line-clamp-2">{p.description || ""}</p>
                <div className="flex justify-between text-xs pt-2 border-t border-slate-100">
                  <span className="text-slate-500">Premium</span><span className="font-bold">{fmtCurrency(p.premium)}</span>
                </div>
                {p.cover ? <div className="flex justify-between text-xs"><span className="text-slate-500">Cover</span><span className="font-bold">{fmtCurrency(p.cover)}</span></div> : null}
              </div>
            );
          })}
          {!catalog?.length ? <div className="text-slate-400 col-span-full py-10 text-center">Catalog loading…</div> : null}
        </div>
      ) : null}

      <div className="card bg-amber-50 border border-amber-200 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
        <div className="text-sm text-amber-900">
          <p className="font-extrabold">Demo mode</p>
          <p>Insurance plans use formula-based premiums. Connect Karza/IDfy/Insurer API via <b>API Management → KYC Verification</b> for live underwriting and claim integration.</p>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, cls, Icon }: { label: string; value: any; cls: string; Icon: any }) {
  return (
    <div className={`rounded-2xl p-3 text-white bg-gradient-to-br ${cls} flex items-center gap-3`}>
      <Icon className="w-8 h-8 opacity-70" />
      <div>
        <p className="text-[11px] font-bold opacity-80">{label}</p>
        <p className="text-2xl font-extrabold mt-1">{value}</p>
      </div>
    </div>
  );
}

/**
 * Admin Mutual Funds Console (Sprint 11)
 * Tabs: Overview · Funds · Investors · Transactions · SIPs · Providers · Analytics · Settings
 *
 * Uses read-mostly APIs; Settings + Provider switching mutate config.
 * Reuses admin analytics framework (CSV export helper, StatCard) — no duplication.
 */
import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import {
  Activity, TrendingUp, TrendingDown, ArrowLeftRight, Users, Repeat, Server,
  BarChart3, Settings as SettingsIcon, Package, RefreshCw, Download,
  CheckCircle2, AlertTriangle, Play, Pause,
} from "lucide-react";

type Tab = "overview" | "funds" | "investors" | "transactions" | "sips" | "providers" | "analytics" | "settings";
const TABS: { id: Tab; label: string; icon: any }[] = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "funds", label: "Funds", icon: Package },
  { id: "investors", label: "Investors", icon: Users },
  { id: "transactions", label: "Transactions", icon: ArrowLeftRight },
  { id: "sips", label: "SIPs", icon: Repeat },
  { id: "providers", label: "Providers", icon: Server },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
  { id: "settings", label: "Settings", icon: SettingsIcon },
];

const inr = (n: any) =>
  n == null ? "—" : "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const pct = (n: any) => (n == null ? "—" : `${Number(n).toFixed(2)}%`);

export default function AdminMutualFundsConsole() {
  const [tab, setTab] = useState<Tab>("overview");
  return (
    <div className="p-6">
      <div className="flex items-center gap-3 mb-4">
        <Repeat className="w-6 h-6 text-indigo-600" />
        <h1 className="text-2xl font-black text-brand-navy">Mutual Funds & SIP Console</h1>
        <span className="text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded bg-indigo-600 text-white">Sprint 11</span>
      </div>

      <div className="flex flex-wrap gap-2 mb-4 border-b border-slate-200 pb-2">
        {TABS.map((t) => {
          const I = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold transition ${
                tab === t.id ? "bg-brand-navy text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              <I className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "funds" && <FundsTab />}
      {tab === "investors" && <InvestorsTab />}
      {tab === "transactions" && <TransactionsTab />}
      {tab === "sips" && <SipsTab />}
      {tab === "providers" && <ProvidersTab />}
      {tab === "analytics" && <AnalyticsTab />}
      {tab === "settings" && <SettingsTab />}
    </div>
  );
}

// ===================== OVERVIEW =====================
function OverviewTab() {
  const { data, refetch, isLoading } = useQuery({
    queryKey: ["adm_mf_dashboard"],
    queryFn: async () => (await api.get("/admin/mf/dashboard")).data,
    refetchInterval: 20000,
  });
  if (isLoading || !data) return <div className="p-8 text-center text-slate-400">Loading…</div>;
  const t = data.totals || {};
  const p = data.provider_status || {};

  return (
    <div className="space-y-4">
      {/* Trading status banner */}
      <div className={`p-4 rounded-xl border-2 ${data.config?.maintenance_mode ? "border-amber-300 bg-amber-50" : "border-emerald-200 bg-emerald-50"}`}>
        <div className="flex items-center gap-3">
          <div className="text-3xl">{data.config?.maintenance_mode ? "⚠️" : "🟢"}</div>
          <div className="flex-1">
            <div className="text-[10px] font-bold uppercase tracking-widest opacity-70">Platform Status</div>
            <div className="text-xl font-black">
              {data.config?.maintenance_mode ? "MAINTENANCE" : "LIVE"} · Provider {p.active}
            </div>
            <div className="text-xs opacity-80 mt-1">
              {p.configured ? "Provider configured" : "Using mock/simulated feed"} · Registry: {p.registry?.join(" · ")}
            </div>
          </div>
          <button onClick={() => refetch()} className="p-2 hover:bg-white/40 rounded-lg" title="Refresh">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="AUM (Invested)" value={inr(t.aum)} sub={`Across ${t.total_funds || 0} funds`} tint="emerald" />
        <Stat label="Active Investors" value={t.active_investors} sub={`${t.total_orders || 0} orders total`} tint="blue" />
        <Stat label="Active SIPs" value={t.active_sips} sub={`${t.paused_sips || 0} paused · ${t.failed_sips || 0} failed`} tint="amber" />
        <Stat label="Pending Redemptions" value={t.pending_redemptions} sub="Under processing" tint="violet" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Stat label="SIP Success Rate" value={pct(t.sip_success_rate)} sub="of all attempts" tint="emerald" />
        <Stat label="SIP Failure Rate" value={pct(t.sip_failure_rate)} sub="requires attention" tint={t.sip_failure_rate > 5 ? "red" : "slate"} />
        <Stat label="Avg SIP Amount" value={inr(t.avg_sip_amount)} sub="per SIP" tint="blue" />
        <Stat label="Avg Investment" value={inr(t.avg_investment_size)} sub="per lumpsum" tint="blue" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Stat label="Highest AUM AMC" value={t.highest_aum_amc || "—"} sub="Concentration" tint="amber" />
        <Stat label="Fastest Growing Category" value={t.fastest_growing_category || "—"} sub="This period" tint="emerald" />
        <Stat label="Avg Holding Period" value={`${(t.avg_holding_days || 0).toFixed(0)} days`} sub="Across all cohorts" tint="slate" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="p-4 bg-white border border-slate-200 rounded-xl">
          <div className="text-xs font-bold text-slate-700 mb-3">TOP AMCs BY AUM</div>
          {data.by_amc.slice(0, 6).map((row: any, i: number) => (
            <div key={row.name} className="flex items-center gap-2 py-1.5 text-sm">
              <span className="text-slate-400 w-4">{i + 1}</span>
              <span className="flex-1 truncate">{row.name}</span>
              <span className="font-bold">{inr(row.invested)}</span>
            </div>
          ))}
        </div>
        <div className="p-4 bg-white border border-slate-200 rounded-xl">
          <div className="text-xs font-bold text-slate-700 mb-3">TOP FUNDS</div>
          {data.top_funds.slice(0, 6).map((row: any, i: number) => (
            <div key={row.fund_id} className="flex items-center gap-2 py-1.5 text-sm">
              <span className="text-slate-400 w-4">{i + 1}</span>
              <span className="flex-1 truncate">{row.fund_name}</span>
              <span className="text-slate-500 text-xs mr-2">{row.unique_users} users</span>
              <span className="font-bold">{inr(row.invested)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ===================== FUNDS =====================
function FundsTab() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["adm_mf_funds", q, category],
    queryFn: async () => (await api.get("/admin/mf/funds", { params: { q: q || undefined, category: category || undefined, limit: 300 } })).data,
    refetchInterval: 60000,
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search fund…" className="border border-slate-300 rounded px-3 py-1.5 text-xs flex-1 max-w-xs" />
        <select value={category} onChange={(e) => setCategory(e.target.value)} className="border border-slate-300 rounded px-3 py-1.5 text-xs">
          <option value="">All categories</option>
          {["equity", "debt", "hybrid", "index", "elss", "international", "gold", "liquid", "small_cap", "mid_cap", "large_cap"].map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
        <button onClick={() => exportCsv(data?.items || [], "mf-funds")} className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 rounded bg-emerald-600 text-white text-xs font-bold">
          <Download className="w-3.5 h-3.5" /> CSV
        </button>
      </div>

      {isLoading ? <div className="p-8 text-center text-slate-400">Loading…</div> : (
        <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">Fund</th>
                <th className="text-left px-3 py-2">AMC</th>
                <th className="text-left px-3 py-2">Cat</th>
                <th className="text-left px-3 py-2">Risk</th>
                <th className="text-right px-3 py-2">NAV</th>
                <th className="text-right px-3 py-2">1Y%</th>
                <th className="text-right px-3 py-2">3Y%</th>
                <th className="text-right px-3 py-2">Exp %</th>
                <th className="text-right px-3 py-2">AUM Cr</th>
                <th className="text-right px-3 py-2">★</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((f: any) => (
                <tr key={f.fund_id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 font-medium max-w-[240px] truncate" title={f.name}>{f.name}</td>
                  <td className="px-3 py-2 text-slate-500 text-[10px]">{f.amc.replace(" Mutual Fund", "")}</td>
                  <td className="px-3 py-2 uppercase text-[10px]">{f.category}</td>
                  <td className="px-3 py-2 uppercase text-[10px]">{f.risk?.replace("_", " ")}</td>
                  <td className="px-3 py-2 text-right">{inr(f.current_nav)}</td>
                  <td className={`px-3 py-2 text-right font-bold ${(f.returns?.y1 ?? 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>{(f.returns?.y1 ?? 0).toFixed(2)}</td>
                  <td className={`px-3 py-2 text-right font-bold ${(f.returns?.y3 ?? 0) >= 0 ? "text-emerald-700" : "text-red-700"}`}>{(f.returns?.y3 ?? 0).toFixed(2)}</td>
                  <td className="px-3 py-2 text-right">{f.expense_ratio}</td>
                  <td className="px-3 py-2 text-right">{Number(f.aum_cr).toLocaleString("en-IN")}</td>
                  <td className="px-3 py-2 text-right text-amber-600">{f.star_rating}★</td>
                </tr>
              ))}
              {!data?.items?.length && <tr><td colSpan={10} className="text-center py-8 text-slate-400">No funds</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ===================== INVESTORS =====================
function InvestorsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["adm_mf_investors"],
    queryFn: async () => (await api.get("/admin/mf/investors", { params: { limit: 200 } })).data,
    refetchInterval: 30000,
  });
  const rows = data?.items || [];
  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <div className="text-xs text-slate-500">Top {rows.length} investors by amount invested.</div>
        <button onClick={() => exportCsv(rows, "mf-investors")} className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-emerald-600 text-white text-xs font-bold">
          <Download className="w-3.5 h-3.5" /> CSV
        </button>
      </div>
      {isLoading ? <div className="p-8 text-center text-slate-400">Loading…</div> : (
        <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">#</th>
                <th className="text-left px-3 py-2">User</th>
                <th className="text-right px-3 py-2">Invested</th>
                <th className="text-right px-3 py-2">Funds</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: any, i: number) => (
                <tr key={r.user_id} className="border-t border-slate-100">
                  <td className="px-3 py-2 text-slate-400">{i + 1}</td>
                  <td className="px-3 py-2 font-mono text-[10px]">{r.user_id?.slice(-10)}</td>
                  <td className="px-3 py-2 text-right font-bold">{inr(r.invested)}</td>
                  <td className="px-3 py-2 text-right">{r.funds}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={4} className="text-center py-8 text-slate-400">No investors yet</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ===================== TRANSACTIONS / ORDERS =====================
function TransactionsTab() {
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [uid, setUid] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["adm_mf_orders", kind, status, uid],
    queryFn: async () => (await api.get("/admin/mf/orders", { params: { kind: kind || undefined, status: status || undefined, user_id: uid || undefined, limit: 300 } })).data,
    refetchInterval: 15000,
  });
  const rows = data?.items || [];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <select value={kind} onChange={(e) => setKind(e.target.value)} className="border rounded px-3 py-1.5 text-xs">
          <option value="">All kinds</option>
          <option value="lumpsum">Lumpsum</option>
          <option value="redeem">Redemption</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="border rounded px-3 py-1.5 text-xs">
          <option value="">All status</option>
          {["created", "pending_payment", "processing", "allocated", "completed", "failed", "redeemed"].map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <input value={uid} onChange={(e) => setUid(e.target.value)} placeholder="User id…" className="border rounded px-3 py-1.5 text-xs flex-1 max-w-xs" />
        <button onClick={() => exportCsv(rows, "mf-orders")} className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 rounded bg-emerald-600 text-white text-xs font-bold">
          <Download className="w-3.5 h-3.5" /> CSV
        </button>
      </div>
      {isLoading ? <div className="p-8 text-center text-slate-400">Loading…</div> : (
        <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">Order</th>
                <th className="text-left px-3 py-2">User</th>
                <th className="text-left px-3 py-2">Fund</th>
                <th className="text-left px-3 py-2">Kind</th>
                <th className="text-right px-3 py-2">Amount</th>
                <th className="text-right px-3 py-2">Units</th>
                <th className="text-right px-3 py-2">NAV</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-left px-3 py-2">When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o: any) => (
                <tr key={o.order_id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono text-[10px]">{o.order_id?.slice(-12)}</td>
                  <td className="px-3 py-2 font-mono text-[10px]">{o.user_id?.slice(-10)}</td>
                  <td className="px-3 py-2 max-w-[200px] truncate">{o.fund_name}</td>
                  <td className="px-3 py-2 uppercase text-[10px]">{o.kind}</td>
                  <td className="px-3 py-2 text-right font-bold">{inr(o.amount)}</td>
                  <td className="px-3 py-2 text-right">{Number(o.units).toFixed(4)}</td>
                  <td className="px-3 py-2 text-right">{o.nav}</td>
                  <td className="px-3 py-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                      o.status === "completed" ? "bg-emerald-100 text-emerald-700" :
                      o.status === "failed" ? "bg-red-100 text-red-700" :
                      "bg-amber-100 text-amber-700"
                    }`}>{o.status.replace(/_/g, " ")}</span>
                  </td>
                  <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{fmtDate(o.created_at)}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={9} className="text-center py-8 text-slate-400">No orders</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ===================== SIPs =====================
function SipsTab() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["adm_mf_sips", status],
    queryFn: async () => (await api.get("/admin/mf/sips", { params: { status: status || undefined, limit: 300 } })).data,
    refetchInterval: 15000,
  });
  const execute = useMutation({
    mutationFn: async (dry_run: boolean) => (await api.post("/admin/mf/sips/execute-due", null, { params: { dry_run } })).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["adm_mf_sips"] }); qc.invalidateQueries({ queryKey: ["adm_mf_dashboard"] }); },
  });
  const rows = data?.items || [];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="border rounded px-3 py-1.5 text-xs">
          <option value="">All status</option>
          {["active", "paused", "cancelled", "failed", "completed"].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <button onClick={() => execute.mutate(true)} disabled={execute.isPending} className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-slate-600 text-white text-xs font-bold">
          <Play className="w-3.5 h-3.5" /> Dry run
        </button>
        <button onClick={() => execute.mutate(false)} disabled={execute.isPending} className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-indigo-600 text-white text-xs font-bold">
          <Play className="w-3.5 h-3.5" /> Execute due SIPs
        </button>
        {execute.isSuccess && (
          <span className="text-xs text-emerald-600">
            ✓ considered {execute.data?.considered}, success {execute.data?.success}, failed {execute.data?.failed}
          </span>
        )}
        <button onClick={() => exportCsv(rows, "mf-sips")} className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 rounded bg-emerald-600 text-white text-xs font-bold">
          <Download className="w-3.5 h-3.5" /> CSV
        </button>
      </div>
      {isLoading ? <div className="p-8 text-center text-slate-400">Loading…</div> : (
        <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">SIP</th>
                <th className="text-left px-3 py-2">User</th>
                <th className="text-left px-3 py-2">Fund</th>
                <th className="text-right px-3 py-2">Amount</th>
                <th className="text-left px-3 py-2">Freq · Day</th>
                <th className="text-right px-3 py-2">Runs (✓/✗)</th>
                <th className="text-left px-3 py-2">Next Run</th>
                <th className="text-left px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s: any) => (
                <tr key={s.sip_id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono text-[10px]">{s.sip_id?.slice(-12)}</td>
                  <td className="px-3 py-2 font-mono text-[10px]">{s.user_id?.slice(-10)}</td>
                  <td className="px-3 py-2 max-w-[220px] truncate">{s.fund_name}</td>
                  <td className="px-3 py-2 text-right font-bold">{inr(s.amount)}</td>
                  <td className="px-3 py-2 uppercase text-[10px]">{s.frequency} · {s.day_of_month}</td>
                  <td className="px-3 py-2 text-right">
                    <span className="text-emerald-700">{s.success_count || 0}</span> / <span className="text-red-700">{s.failure_count || 0}</span>
                  </td>
                  <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{fmtDate(s.next_run_at)}</td>
                  <td className="px-3 py-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                      s.status === "active" ? "bg-emerald-100 text-emerald-700" :
                      s.status === "paused" ? "bg-amber-100 text-amber-700" :
                      s.status === "failed" ? "bg-red-100 text-red-700" :
                      "bg-slate-100 text-slate-600"
                    }`}>{s.status}</span>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">No SIPs</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ===================== PROVIDERS =====================
function ProvidersTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["adm_mf_providers"],
    queryFn: async () => (await api.get("/admin/mf/providers")).data,
  });
  const setProvider = useMutation({
    mutationFn: async (p: string) => (await api.put("/admin/mf/config", { provider: p })).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["adm_mf_providers"] }); qc.invalidateQueries({ queryKey: ["adm_mf_dashboard"] }); },
  });
  if (!data) return <div className="p-8 text-center text-slate-400">Loading…</div>;
  return (
    <div className="space-y-3">
      <div className="text-xs text-slate-500">Active provider: <b className="text-slate-800">{data.active}</b>. Switching is immediate.</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {(data.providers || []).map((p: any) => {
          const active = p.name === data.active;
          return (
            <div key={p.name} className={`p-4 rounded-xl border-2 ${active ? "border-indigo-400 bg-indigo-50" : "border-slate-200 bg-white"}`}>
              <div className="flex items-start gap-3">
                <div className={`w-10 h-10 rounded-full grid place-items-center ${p.configured ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                  {p.configured ? <CheckCircle2 className="w-5 h-5" /> : <AlertTriangle className="w-5 h-5" />}
                </div>
                <div className="flex-1">
                  <div className="font-black text-slate-800 uppercase">{p.name}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {p.real ? "Real feed" : "Simulated"} · {p.configured ? "Configured" : "Not configured"}
                  </div>
                </div>
                {active ? (
                  <span className="text-[10px] font-black uppercase text-indigo-700 bg-indigo-100 border border-indigo-300 rounded px-2 py-0.5">ACTIVE</span>
                ) : (
                  <button onClick={() => setProvider.mutate(p.name)} disabled={setProvider.isPending} className="text-xs font-bold text-brand-navy hover:underline">Set active →</button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ===================== ANALYTICS =====================
function AnalyticsTab() {
  const [range, setRange] = useState<"today" | "week" | "month" | "year" | "all">("month");
  const { data: dash } = useQuery({ queryKey: ["adm_mf_dashboard_a"], queryFn: async () => (await api.get("/admin/mf/dashboard")).data, refetchInterval: 30000 });
  const { data: orders } = useQuery({ queryKey: ["adm_mf_orders_a"], queryFn: async () => (await api.get("/admin/mf/orders", { params: { limit: 500 } })).data, refetchInterval: 30000 });

  const kpis = useMemo(() => {
    if (!dash || !orders) return null;
    const now = Date.now();
    const cutoff = range === "today" ? now - 86400000 : range === "week" ? now - 7 * 86400000 : range === "month" ? now - 30 * 86400000 : range === "year" ? now - 365 * 86400000 : 0;
    const rows = (orders.items || []).filter((o: any) => (cutoff ? new Date(o.created_at).getTime() >= cutoff : true));

    const days: { d: string; buy: number; sell: number }[] = [];
    for (let i = 13; i >= 0; i--) days.push({ d: new Date(now - i * 86400000).toISOString().slice(0, 10), buy: 0, sell: 0 });
    (orders.items || []).forEach((o: any) => {
      const key = new Date(o.created_at).toISOString().slice(0, 10);
      const row = days.find((r) => r.d === key);
      if (!row) return;
      if (o.kind === "lumpsum") row.buy += o.amount || 0;
      else row.sell += o.amount || 0;
    });

    let volBuy = 0, volSell = 0;
    rows.forEach((o: any) => { if (o.kind === "lumpsum") volBuy += o.amount; else volSell += o.amount; });

    return { days, volBuy, volSell, txCount: rows.length };
  }, [dash, orders, range]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-center">
        {(["today", "week", "month", "year", "all"] as const).map((r) => (
          <button key={r} onClick={() => setRange(r)} className={`px-3 py-1.5 rounded-full text-xs font-bold uppercase ${range === r ? "bg-brand-navy text-white" : "bg-slate-100 text-slate-700"}`}>{r}</button>
        ))}
        <button onClick={() => exportCsv(orders?.items || [], "mf-orders-full")} className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 rounded bg-emerald-600 text-white text-xs font-bold">
          <Download className="w-3.5 h-3.5" /> Full CSV
        </button>
      </div>

      {!dash ? <div className="p-8 text-center text-slate-400">Loading…</div> : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <Stat label="Buy Volume" value={inr(kpis?.volBuy)} sub={`${kpis?.txCount || 0} tx in ${range}`} tint="emerald" />
            <Stat label="Sell Volume" value={inr(kpis?.volSell)} sub="Redemptions" tint="red" />
            <Stat label="AUM" value={inr(dash.totals.aum)} sub={`${dash.totals.active_investors} investors`} tint="amber" />
            <Stat label="Active SIPs" value={dash.totals.active_sips} sub={`Avg ${inr(dash.totals.avg_sip_amount)}`} tint="blue" />
          </div>

          <div className="p-4 bg-white border border-slate-200 rounded-xl">
            <div className="text-xs font-bold text-slate-700 mb-2">DAILY LUMPSUM VS REDEMPTION · LAST 14 DAYS</div>
            <BuySellChart days={kpis?.days || []} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="p-4 bg-white border border-slate-200 rounded-xl">
              <div className="text-xs font-bold text-slate-700 mb-3">CATEGORY DISTRIBUTION</div>
              {(dash.by_category || []).slice(0, 8).map((r: any, i: number) => {
                const total = (dash.by_category || []).reduce((a: number, x: any) => a + x.invested, 0) || 1;
                const p = (r.invested / total) * 100;
                return (
                  <div key={r.name} className="py-1.5">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-bold uppercase">{r.name?.replace("_", " ")}</span>
                      <span className="font-bold">{p.toFixed(1)}% · {inr(r.invested)}</span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded overflow-hidden"><div className="h-2 bg-indigo-500 rounded" style={{ width: `${p}%` }} /></div>
                  </div>
                );
              })}
            </div>
            <div className="p-4 bg-white border border-slate-200 rounded-xl">
              <div className="text-xs font-bold text-slate-700 mb-3">AMC DISTRIBUTION</div>
              {(dash.by_amc || []).slice(0, 8).map((r: any, i: number) => {
                const total = (dash.by_amc || []).reduce((a: number, x: any) => a + x.invested, 0) || 1;
                const p = (r.invested / total) * 100;
                return (
                  <div key={r.name} className="py-1.5">
                    <div className="flex justify-between text-xs mb-1">
                      <span className="font-bold truncate flex-1 mr-2">{r.name}</span>
                      <span className="font-bold whitespace-nowrap">{p.toFixed(1)}% · {inr(r.invested)}</span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded overflow-hidden"><div className="h-2 bg-amber-500 rounded" style={{ width: `${p}%` }} /></div>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function BuySellChart({ days }: { days: any[] }) {
  const maxV = Math.max(1, ...days.flatMap((d: any) => [d.buy, d.sell]));
  return (
    <div>
      <div className="flex items-end gap-1 h-40">
        {days.map((d: any) => (
          <div key={d.d} className="flex-1 flex flex-col items-center gap-1">
            <div className="flex-1 w-full flex flex-col justify-end gap-0.5">
              <div className="w-full bg-emerald-500 rounded-t" style={{ height: `${(d.buy / maxV) * 100}%`, minHeight: d.buy > 0 ? 2 : 0 }} title={`Buy ${inr(d.buy)}`} />
              <div className="w-full bg-red-500 rounded-t" style={{ height: `${(d.sell / maxV) * 100}%`, minHeight: d.sell > 0 ? 2 : 0 }} title={`Sell ${inr(d.sell)}`} />
            </div>
            <div className="text-[9px] text-slate-500 whitespace-nowrap">{d.d.slice(5)}</div>
          </div>
        ))}
      </div>
      <div className="flex gap-3 mt-3 text-xs justify-center">
        <span className="inline-flex items-center gap-1"><span className="w-3 h-3 bg-emerald-500 rounded" /> Lumpsum</span>
        <span className="inline-flex items-center gap-1"><span className="w-3 h-3 bg-red-500 rounded" /> Redemption</span>
      </div>
    </div>
  );
}

// ===================== SETTINGS =====================
function SettingsTab() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["adm_mf_config"], queryFn: async () => (await api.get("/admin/mf/config")).data });
  const [form, setForm] = useState<any>({});
  const patch = useMutation({
    mutationFn: async (body: any) => (await api.put("/admin/mf/config", body)).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["adm_mf_config"] }); qc.invalidateQueries({ queryKey: ["adm_mf_dashboard"] }); setForm({}); },
  });
  if (!data) return <div className="p-8 text-center text-slate-400">Loading…</div>;
  const val = (k: string) => (form[k] !== undefined ? form[k] : data[k]);
  return (
    <div className="space-y-4">
      <div className="p-4 rounded-xl border border-slate-200 bg-white">
        <div className="text-xs font-bold text-slate-700 mb-3">CURRENT SETTINGS</div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
          <KV label="Provider" value={data.provider} />
          <KV label="Min Lumpsum" value={inr(data.min_lumpsum_inr)} />
          <KV label="Min SIP" value={inr(data.min_sip_inr)} />
          <KV label="SIP Retry Max" value={data.sip_retry_max} />
          <KV label="SIP Retry Hours" value={data.sip_retry_hours} />
          <KV label="Maintenance" value={data.maintenance_mode ? "ON" : "off"} />
          <KV label="Redemption KYC" value={data.redemption_kyc_required ? "Required" : "Not required"} />
          <KV label="Platform Fee" value={`${(data.platform_fee_bps / 100).toFixed(2)}%`} />
          <KV label="NAV Sync (hrs)" value={data.nav_sync_interval_hours} />
        </div>
      </div>

      <div className="p-4 rounded-xl border-2 border-brand-navy/20 bg-brand-navy/5">
        <div className="text-xs font-bold text-brand-navy mb-3">UPDATE SETTINGS</div>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <F label="Min Lumpsum ₹" val={val("min_lumpsum_inr")} onChange={(v) => setForm({ ...form, min_lumpsum_inr: Number(v) })} />
          <F label="Min SIP ₹" val={val("min_sip_inr")} onChange={(v) => setForm({ ...form, min_sip_inr: Number(v) })} />
          <F label="SIP Retry Max" val={val("sip_retry_max")} onChange={(v) => setForm({ ...form, sip_retry_max: Number(v) })} />
          <F label="SIP Retry Hours" val={val("sip_retry_hours")} onChange={(v) => setForm({ ...form, sip_retry_hours: Number(v) })} />
          <F label="Platform Fee (bps)" val={val("platform_fee_bps")} onChange={(v) => setForm({ ...form, platform_fee_bps: Number(v) })} />
          <F label="NAV Sync (hrs)" val={val("nav_sync_interval_hours")} onChange={(v) => setForm({ ...form, nav_sync_interval_hours: Number(v) })} />
          <label className="flex items-center gap-2 mt-6"><input type="checkbox" checked={val("maintenance_mode")} onChange={(e) => setForm({ ...form, maintenance_mode: e.target.checked })} /><span>Maintenance mode</span></label>
          <label className="flex items-center gap-2 mt-6"><input type="checkbox" checked={val("redemption_kyc_required")} onChange={(e) => setForm({ ...form, redemption_kyc_required: e.target.checked })} /><span>Require KYC for redemption</span></label>
        </div>
        <div className="mt-4 flex gap-2 items-center">
          <button onClick={() => patch.mutate(form)} disabled={Object.keys(form).length === 0 || patch.isPending} className="px-4 py-2 rounded-lg bg-brand-navy text-white text-sm font-bold disabled:opacity-50">{patch.isPending ? "Saving…" : "Save Settings"}</button>
          <button onClick={() => setForm({})} className="px-3 py-2 rounded text-sm text-slate-600 hover:bg-slate-100">Reset</button>
          <button onClick={() => patch.mutate({ maintenance_mode: !data.maintenance_mode })} className={`ml-auto inline-flex items-center gap-1 px-3 py-2 rounded-lg text-sm font-bold ${data.maintenance_mode ? "bg-emerald-600 text-white" : "bg-red-600 text-white"}`}>
            {data.maintenance_mode ? <><Play className="w-3.5 h-3.5" /> Resume</> : <><Pause className="w-3.5 h-3.5" /> Pause All Trading</>}
          </button>
          {patch.isSuccess && <span className="text-xs text-emerald-600 ml-2">✓ Saved</span>}
        </div>
      </div>
    </div>
  );
}

// ===================== Helpers =====================
function Stat({ label, value, sub, tint }: any) {
  const map: Record<string, string> = { emerald: "border-emerald-200 bg-emerald-50", blue: "border-blue-200 bg-blue-50", violet: "border-violet-200 bg-violet-50", amber: "border-amber-200 bg-amber-50", red: "border-red-200 bg-red-50", slate: "border-slate-200 bg-slate-50" };
  return (
    <div className={`p-4 rounded-xl border-2 ${map[tint || "blue"]}`}>
      <div className="text-[10px] font-bold uppercase tracking-widest text-slate-600">{label}</div>
      <div className="text-2xl font-black mt-1">{value ?? "—"}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}
function KV({ label, value }: any) {
  return <div className="flex flex-col"><span className="text-[9px] font-bold text-slate-500 uppercase">{label}</span><span className="text-slate-800 font-bold">{value}</span></div>;
}
function F({ label, val, onChange }: { label: string; val: any; onChange: (v: string) => void }) {
  return <label>{label}<input type="number" value={val ?? ""} onChange={(e) => onChange(e.target.value)} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1" /></label>;
}
function exportCsv(rows: any[], filename: string) {
  if (!rows || rows.length === 0) return;
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r).filter((k) => !Array.isArray(r[k]) && typeof r[k] !== "object"))));
  const esc = (v: any) => { if (v == null) return ""; const s = typeof v === "string" ? v : JSON.stringify(v); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${filename}-${new Date().toISOString().slice(0, 10)}.csv`; a.click();
}

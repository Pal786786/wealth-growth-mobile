/**
 * Admin — Live Market Console (Sprint 7.5)
 * 4 tabs: Overview / Providers / Cache / History
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import {
  Activity, Zap, Database, History as HistoryIcon, RefreshCw, CheckCircle2, XCircle,
  Key, Trash2, Play, Pause,
} from "lucide-react";

type Tab = "overview" | "providers" | "cache" | "history";
const TABS: { id: Tab; label: string; icon: any }[] = [
  { id: "overview",  label: "Overview",  icon: Activity },
  { id: "providers", label: "Providers", icon: Zap },
  { id: "cache",     label: "Cache",     icon: Database },
  { id: "history",   label: "History",   icon: HistoryIcon },
];

export default function AdminLiveMarket() {
  const [tab, setTab] = useState<Tab>("overview");
  return (
    <div className="p-6">
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 rounded-lg bg-emerald-100 text-emerald-700"><Zap className="w-5 h-5" /></div>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Live Market</h1>
          <p className="text-sm text-slate-500">Sprint 7.5 — Provider architecture with TwelveData → Alpha Vantage → Mock fallback</p>
        </div>
      </div>
      <div className="flex gap-1 mb-5 border-b border-slate-200 overflow-x-auto">
        {TABS.map((t) => {
          const Ic = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-semibold whitespace-nowrap border-b-2 transition ${
                t.id === tab ? "border-emerald-600 text-emerald-700" : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              <Ic className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>
      {tab === "overview" && <OverviewTab />}
      {tab === "providers" && <ProvidersTab />}
      {tab === "cache" && <CacheTab />}
      {tab === "history" && <HistoryTab />}
    </div>
  );
}

function OverviewTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["market-status"],
    queryFn: async () => (await api.get("/market_providers/status")).data,
    refetchInterval: 3000,
  });
  const refresh = useMutation({
    mutationFn: () => api.post("/market_providers/refresh"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["market-status"] }),
  });
  const setFallback = useMutation({
    mutationFn: (enabled: boolean) => api.put("/market_providers/auto-fallback", { enabled }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["market-status"] }),
  });
  const setManual = useMutation({
    mutationFn: (provider: string | null) => api.put("/market_providers/manual-provider", { provider }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["market-status"] }),
  });

  if (!data) return <div className="p-8 text-center text-slate-400">Loading…</div>;
  const activeClass = data.active_provider === "mock" ? "text-amber-600 bg-amber-50"
    : data.active_provider === "twelvedata" ? "text-emerald-600 bg-emerald-50"
    : data.active_provider === "alphavantage" ? "text-blue-600 bg-blue-50"
    : "text-slate-600 bg-slate-50";

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Active Provider" value={(data.active_provider || "—").toUpperCase()} tint={data.active_provider === "twelvedata" ? "green" : data.active_provider === "mock" ? "amber" : "blue"} icon={Zap} />
        <StatCard label="Auto Fallback" value={data.auto_fallback ? "ENABLED" : "DISABLED"} tint={data.auto_fallback ? "green" : "amber"} icon={Activity} />
        <StatCard label="Refresh Interval" value={`${data.refresh_interval_sec}s`} icon={RefreshCw} />
        <StatCard label="Symbols" value={data.universe?.length ?? 0} icon={Database} />
        <StatCard label="Cache — Fresh" value={data.cache?.fresh ?? 0} tint="green" icon={CheckCircle2} />
        <StatCard label="Cache — Stale" value={data.cache?.stale ?? 0} tint={data.cache?.stale > 0 ? "amber" : undefined} icon={XCircle} />
        <StatCard label="TTL" value={`${data.cache?.ttl_sec ?? 30}s`} icon={Activity} />
        <StatCard label="Last Refresh" value={data.last_refresh_at ? fmtDate(data.last_refresh_at) : "—"} icon={RefreshCw} />
      </div>

      {data.last_refresh_error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
          <b>Last refresh error:</b> {data.last_refresh_error}
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-bold text-slate-700 mb-3">Manual Provider Override</h3>
        <div className="flex flex-wrap gap-2 items-center">
          <button onClick={() => setManual.mutate(null)}
            className={`px-4 py-2 rounded-lg text-sm font-bold border ${!data.manual_provider ? "bg-emerald-600 text-white border-emerald-600" : "bg-white text-slate-700 border-slate-200"}`}>
            AUTO
          </button>
          {["twelvedata", "alphavantage", "mock"].map((p) => (
            <button key={p} onClick={() => setManual.mutate(p)}
              className={`px-4 py-2 rounded-lg text-sm font-bold border ${data.manual_provider === p ? "bg-indigo-600 text-white border-indigo-600" : "bg-white text-slate-700 border-slate-200"}`}>
              {p.toUpperCase()}
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs text-slate-500">
          When AUTO is on, the manager picks the highest-priority configured provider (TwelveData → Alpha Vantage → Mock).
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-5">
        <h3 className="text-sm font-bold text-slate-700 mb-3">Actions</h3>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => refresh.mutate()} disabled={refresh.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-lg disabled:opacity-50">
            <RefreshCw className={`w-4 h-4 ${refresh.isPending ? "animate-spin" : ""}`} /> Refresh Now
          </button>
          <button onClick={() => setFallback.mutate(!data.auto_fallback)}
            className="flex items-center gap-2 px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-sm font-bold rounded-lg">
            {data.auto_fallback ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
            {data.auto_fallback ? "Disable Auto-Fallback" : "Enable Auto-Fallback"}
          </button>
        </div>
      </div>
    </div>
  );
}

function ProvidersTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["market-status"],
    queryFn: async () => (await api.get("/market_providers/status")).data,
    refetchInterval: 3000,
  });
  const { data: health } = useQuery({
    queryKey: ["market-health"],
    queryFn: async () => (await api.get("/market_providers/health")).data,
    refetchInterval: 15000,
  });
  const testProvider = useMutation({
    mutationFn: async (name: string) => (await api.get("/market_providers/health", { params: { provider: name } })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["market-health"] }),
  });
  const setKey = useMutation({
    mutationFn: (payload: { provider: string; key: string }) => api.put("/market_providers/api-key", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["market-status"] }),
  });
  const [tdKey, setTdKey] = useState("");
  const [avKey, setAvKey] = useState("");

  if (!data) return <div className="p-8 text-center text-slate-400">Loading…</div>;

  return (
    <div className="space-y-4">
      {data.providers.map((p: any) => {
        const h = health?.[p.name];
        return (
          <div key={p.name} className="bg-white border border-slate-200 rounded-xl p-5">
            <div className="flex items-start justify-between flex-wrap gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-bold text-slate-900">{p.name.toUpperCase()}</h3>
                  <span className="text-xs text-slate-500">priority {p.priority}</span>
                  {p.configured ? (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-700">CONFIGURED</span>
                  ) : (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-700">NO API KEY</span>
                  )}
                  {p.circuit?.open && (
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-red-100 text-red-700">CIRCUIT OPEN</span>
                  )}
                </div>
                <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-1 text-xs">
                  <KV label="Total Requests"  value={p.total_requests} />
                  <KV label="Successful"      value={p.successful_requests} />
                  <KV label="Failed"          value={p.failed_requests} />
                  <KV label="Rate-limited"    value={p.rate_limited_requests} />
                  <KV label="Error Rate"      value={`${p.error_rate_pct}%`} />
                  <KV label="Avg Response"    value={`${p.avg_response_ms} ms`} />
                  <KV label="Credits Used"    value={p.daily_credits_used} />
                  <KV label="Credits Remaining" value={p.credits_remaining ?? "∞"} />
                  <KV label="Last Success"    value={p.last_success_at ? fmtDate(p.last_success_at) : "—"} />
                  <KV label="Last Error"      value={p.last_error_at ? fmtDate(p.last_error_at) : "—"} />
                </div>
                {p.last_error && <div className="mt-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1">{p.last_error}</div>}
              </div>
              <div className="flex flex-col items-end gap-2">
                <button onClick={() => testProvider.mutate(p.name)}
                  className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold rounded-lg">
                  Test Connection
                </button>
                {h && (
                  <div className={`text-xs font-bold ${h.ok ? "text-green-600" : "text-red-600"}`}>
                    {h.ok ? `OK · ${h.latency_ms}ms` : "FAILED"}
                  </div>
                )}
                {h?.note && <div className="text-[10px] text-slate-500 max-w-[220px] text-right">{h.note}</div>}
              </div>
            </div>

            {p.name === "twelvedata" && (
              <div className="mt-4 flex gap-2 items-end">
                <div className="flex-1">
                  <label className="block text-xs font-bold text-slate-500 mb-1">API Key (from twelvedata.com)</label>
                  <input type="password" value={tdKey} onChange={(e) => setTdKey(e.target.value)}
                    placeholder="paste key here"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
                </div>
                <button onClick={() => setKey.mutate({ provider: "twelvedata", key: tdKey })}
                  disabled={!tdKey.trim()}
                  className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-lg disabled:opacity-40">
                  <Key className="w-4 h-4" /> Save
                </button>
              </div>
            )}
            {p.name === "alphavantage" && (
              <div className="mt-4 flex gap-2 items-end">
                <div className="flex-1">
                  <label className="block text-xs font-bold text-slate-500 mb-1">API Key (from alphavantage.co)</label>
                  <input type="password" value={avKey} onChange={(e) => setAvKey(e.target.value)}
                    placeholder="paste key here"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm" />
                </div>
                <button onClick={() => setKey.mutate({ provider: "alphavantage", key: avKey })}
                  disabled={!avKey.trim()}
                  className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-lg disabled:opacity-40">
                  <Key className="w-4 h-4" /> Save
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function CacheTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["market-quotes"],
    queryFn: async () => (await api.get("/market_providers/quotes")).data as { quotes: any[] },
    refetchInterval: 3000,
  });
  const clear = useMutation({
    mutationFn: () => api.delete("/market_providers/cache"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["market-quotes"] }),
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs font-bold text-slate-500">{data?.quotes?.length ?? 0} SYMBOLS · refreshes every 3s</div>
        <button onClick={() => clear.mutate()}
          className="flex items-center gap-2 px-3 py-1.5 bg-red-500 hover:bg-red-600 text-white text-xs font-bold rounded-lg">
          <Trash2 className="w-3 h-3" /> Clear Cache
        </button>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-[11px] uppercase font-bold">
            <tr>
              <th className="text-left px-3 py-2.5">Symbol</th>
              <th className="text-right px-3 py-2.5">Price</th>
              <th className="text-right px-3 py-2.5">Bid</th>
              <th className="text-right px-3 py-2.5">Ask</th>
              <th className="text-right px-3 py-2.5">24h%</th>
              <th className="text-center px-3 py-2.5">Provider</th>
              <th className="text-right px-3 py-2.5">Age</th>
              <th className="text-left px-3 py-2.5">Updated</th>
            </tr>
          </thead>
          <tbody>
            {data?.quotes?.map((q) => (
              <tr key={q.symbol} className="border-t border-slate-100 text-xs">
                <td className="px-3 py-2 font-bold text-slate-800">{q.symbol}</td>
                <td className="px-3 py-2 text-right tabular-nums font-semibold">{Number(q.price).toLocaleString(undefined, { maximumFractionDigits: 5 })}</td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-500">{q.bid ?? "—"}</td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-500">{q.ask ?? "—"}</td>
                <td className={`px-3 py-2 text-right tabular-nums font-bold ${q.change_pct >= 0 ? "text-green-600" : "text-red-600"}`}>
                  {q.change_pct != null ? `${q.change_pct >= 0 ? "+" : ""}${Number(q.change_pct).toFixed(2)}%` : "—"}
                </td>
                <td className="px-3 py-2 text-center">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${q.provider === "mock" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>
                    {q.provider?.toUpperCase()}
                  </span>
                </td>
                <td className={`px-3 py-2 text-right ${q.stale ? "text-red-600" : "text-slate-500"} font-bold`}>{q.age_sec}s</td>
                <td className="px-3 py-2 text-slate-500">{fmtDate(q.updated_at)}</td>
              </tr>
            ))}
            {!data?.quotes?.length && <tr><td colSpan={8} className="text-center p-6 text-slate-400">Cache is empty — wait for the next refresh</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function HistoryTab() {
  const { data } = useQuery({
    queryKey: ["market-history"],
    queryFn: async () => (await api.get("/market_providers/history", { params: { limit: 100 } })).data as { history: any[] },
    refetchInterval: 5000,
  });
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="px-4 py-3 border-b border-slate-100 font-bold text-sm text-slate-700">
        Provider Activity ({data?.history?.length ?? 0} recent events)
      </div>
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-slate-500 text-[11px] uppercase font-bold">
          <tr>
            <th className="text-left px-3 py-2.5">Time</th>
            <th className="text-left px-3 py-2.5">Provider</th>
            <th className="text-center px-3 py-2.5">Status</th>
            <th className="text-right px-3 py-2.5">Latency</th>
            <th className="text-right px-3 py-2.5">Quotes</th>
            <th className="text-left px-3 py-2.5">Error</th>
          </tr>
        </thead>
        <tbody>
          {data?.history?.map((h: any, i: number) => (
            <tr key={i} className="border-t border-slate-100 text-xs">
              <td className="px-3 py-2 text-slate-500">{fmtDate(h.at)}</td>
              <td className="px-3 py-2 font-semibold">{h.provider}</td>
              <td className="px-3 py-2 text-center">
                {h.ok
                  ? <CheckCircle2 className="w-4 h-4 text-green-600 inline" />
                  : <XCircle className="w-4 h-4 text-red-600 inline" />}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">{h.latency_ms}ms</td>
              <td className="px-3 py-2 text-right">{h.count}</td>
              <td className="px-3 py-2 text-red-600">{h.error || ""}</td>
            </tr>
          ))}
          {!data?.history?.length && <tr><td colSpan={6} className="text-center p-6 text-slate-400">No events yet</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function KV({ label, value }: any) {
  return (
    <div>
      <div className="text-[10px] font-bold uppercase text-slate-400">{label}</div>
      <div className="text-xs font-bold text-slate-800">{String(value ?? "—")}</div>
    </div>
  );
}

function StatCard({ label, value, icon: Ic, tint }: any) {
  const tintClass = tint === "green" ? "text-green-600 bg-green-50"
    : tint === "red" ? "text-red-600 bg-red-50"
    : tint === "amber" ? "text-amber-600 bg-amber-50"
    : tint === "blue" ? "text-blue-600 bg-blue-50"
    : "text-slate-700 bg-slate-100";
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <div className="text-[10px] font-bold uppercase text-slate-400">{label}</div>
          <div className="mt-1 text-xl font-bold text-slate-900 tabular-nums truncate">{value}</div>
        </div>
        {Ic && <div className={`p-2 rounded-lg ${tintClass}`}><Ic className="w-4 h-4" /></div>}
      </div>
    </div>
  );
}

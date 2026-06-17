import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import { Bell, CheckCircle2, XCircle, RefreshCw, Search, RotateCcw, AlertTriangle, Clock } from "lucide-react";

type Log = {
  log_id: string; batch_id?: string; title: string; message: string;
  recipients_count: number; recipients_sample: string[]; ok: boolean;
  status: string; provider_response?: string; error?: string;
  latency_ms?: number; at: string;
};

export default function AdminPushLogs() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<string>("all");
  const [search, setSearch] = useState("");

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["push-logs", status],
    queryFn: async () => (await api.get("/admin/push-logs", { params: { status: status === "all" ? undefined : status, limit: 200 } })).data as { items: Log[]; total: number; success_count: number; failed_count: number; recent_24h: number; success_rate: number },
    refetchInterval: 15000,
  });

  const filtered = useMemo(() => {
    const items = data?.items || [];
    if (!search) return items;
    const q = search.toLowerCase();
    return items.filter((r) => [r.title, r.message, r.error, r.log_id].some((v) => (v || "").toLowerCase().includes(q)));
  }, [data, search]);

  const retry = useMutation({
    mutationFn: async (logId: string) => (await api.post(`/admin/push-logs/${logId}/retry`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["push-logs"] }),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2"><Bell className="w-6 h-6" /> Push Delivery Logs</h2>
          <p className="text-sm text-slate-500 mt-1">Every push attempt with provider response & retry option.</p>
        </div>
        <button onClick={() => refetch()} className="btn-ghost gap-2 text-sm"><RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh</button>
      </div>

      <div className="grid sm:grid-cols-4 gap-3">
        <Stat label="Total sends" value={data?.total || 0} cls="from-sky-500 to-blue-600" Icon={Bell} />
        <Stat label="Success" value={data?.success_count || 0} cls="from-emerald-500 to-emerald-600" Icon={CheckCircle2} />
        <Stat label="Failed" value={data?.failed_count || 0} cls="from-red-500 to-rose-600" Icon={XCircle} />
        <Stat label="Success rate" value={`${data?.success_rate ?? 0}%`} cls="from-violet-500 to-fuchsia-600" Icon={AlertTriangle} />
      </div>

      {(data?.failed_count || 0) > 0 && (data?.success_count || 0) === 0 ? (
        <div className="bg-red-50 border border-red-200 rounded-2xl px-4 py-3 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5" />
          <div className="text-sm text-red-900">
            <p className="font-extrabold">All pushes are failing!</p>
            <p>Most common cause: <b>EMERGENT_PUSH_KEY is still &apos;placeholder&apos;</b>. Re-publish your app with google-services.json uploaded, OR confirm the server env has the real FCM server key set.</p>
          </div>
        </div>
      ) : null}

      <div className="card flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-400" />
          <input className="input" placeholder="Search title, message, error…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="input max-w-[150px]" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="all">All status</option>
          <option value="success">Success</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      <div className="card overflow-hidden">
        {isLoading ? <div className="text-slate-400 py-8 text-center">Loading…</div> : null}
        {!isLoading && filtered.length === 0 ? <div className="text-slate-400 py-10 text-center">No push delivery logs yet. Send a broadcast to see entries.</div> : null}
        <div className="divide-y divide-slate-100">
          {filtered.map((r) => (
            <div key={r.log_id} className="py-3 px-1 hover:bg-slate-50 flex items-start gap-3">
              <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${r.ok ? "bg-emerald-50 text-emerald-600" : "bg-red-50 text-red-600"}`}>
                {r.ok ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-slate-800 text-sm truncate max-w-[300px]">{r.title}</span>
                  <span className="badge bg-slate-100 text-slate-600 text-[10px]">{r.recipients_count} recipient{r.recipients_count !== 1 ? "s" : ""}</span>
                  {r.latency_ms ? <span className="badge bg-slate-100 text-slate-500 text-[10px]"><Clock className="w-3 h-3 inline" /> {r.latency_ms}ms</span> : null}
                </div>
                <p className="text-xs text-slate-500 mt-0.5 truncate">{r.message}</p>
                {r.error ? <p className="text-xs text-red-700 mt-1 font-mono bg-red-50 px-2 py-1 rounded inline-block">{r.error}</p> : null}
                {r.provider_response && !r.error ? <p className="text-xs text-slate-400 mt-1 font-mono">{r.provider_response}</p> : null}
              </div>
              <div className="text-right shrink-0">
                <p className="text-xs text-slate-400">{fmtDate(r.at)}</p>
                {!r.ok ? (
                  <button onClick={() => retry.mutate(r.log_id)} disabled={retry.isPending} className="mt-1 text-xs text-brand-primary font-bold hover:underline flex items-center gap-1">
                    <RotateCcw className="w-3 h-3" /> Retry
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, cls, Icon }: { label: string; value: any; cls: string; Icon: any }) {
  return (
    <div className={`rounded-2xl p-3 text-white bg-gradient-to-br ${cls} flex items-center gap-3`}>
      <Icon className="w-8 h-8 opacity-70" />
      <div><p className="text-[11px] font-bold opacity-80">{label}</p><p className="text-xl font-extrabold mt-1">{value}</p></div>
    </div>
  );
}

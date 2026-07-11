/**
 * Admin — AI Console (Sprint 7C.2)
 * 4 tabs: Overview · News · Calendar · Summary · Analytics
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import {
  Newspaper, CalendarClock, FileText, BarChart3, Zap, Trash2,
  RefreshCw, Plus, Play, Sparkles, Activity,
} from "lucide-react";

type Tab = "overview" | "news" | "calendar" | "summary" | "analytics";
const TABS: { id: Tab; label: string; icon: any }[] = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "news", label: "News", icon: Newspaper },
  { id: "calendar", label: "Economic Calendar", icon: CalendarClock },
  { id: "summary", label: "Market Summary", icon: FileText },
  { id: "analytics", label: "Signal Analytics", icon: BarChart3 },
];

export default function AdminAIConsole() {
  const [tab, setTab] = useState<Tab>("overview");
  return (
    <div className="p-6">
      <div className="flex items-center gap-3 mb-4">
        <Sparkles className="w-6 h-6 text-brand-navy" />
        <h1 className="text-2xl font-black text-brand-navy">AI Console</h1>
        <span className="text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded bg-brand-navy text-white">Sprint 7C.2</span>
      </div>

      <div className="flex flex-wrap gap-2 mb-4 border-b border-slate-200 pb-2">
        {TABS.map((t) => {
          const I = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold transition ${tab === t.id ? "bg-brand-navy text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"}`}>
              <I className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "news" && <NewsTab />}
      {tab === "calendar" && <CalendarTab />}
      {tab === "summary" && <SummaryTab />}
      {tab === "analytics" && <AnalyticsTab />}
    </div>
  );
}

// ================ OVERVIEW ================
function OverviewTab() {
  const { data, refetch } = useQuery({
    queryKey: ["ai_console_overview"],
    queryFn: async () => (await api.get("/ai/admin/console")).data,
    refetchInterval: 20000,
  });
  if (!data) return <div className="p-8 text-center text-slate-400">Loading…</div>;
  const a = data.analytics;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <StatCard label="News total" value={data.news.total} sub={`${data.news.pending_broadcast} awaiting broadcast`} tint="blue" />
        <StatCard label="Upcoming events" value={data.calendar.upcoming_events} sub="next 90 days" tint="emerald" />
        <StatCard label="Signals tracked (30d)" value={a.total_signals} sub={`${a.resolved_signals} resolved · ${a.pending_signals} open`} tint="violet" />
        <StatCard label="Win rate (30d)" value={`${a.win_rate_pct}%`} sub={`ROI ${a.sum_roi_pct >= 0 ? "+" : ""}${a.sum_roi_pct}%`} tint={a.win_rate_pct >= 50 ? "emerald" : "amber"} />
      </div>
      <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl">
        <div className="flex items-center gap-2 mb-2">
          <FileText className="w-4 h-4 text-slate-500" />
          <span className="font-bold text-slate-700 text-sm">Latest Daily Summary</span>
          <button onClick={() => refetch()} className="ml-auto text-xs text-slate-500 hover:text-slate-700"><RefreshCw className="w-3.5 h-3.5" /></button>
        </div>
        {data.summary.latest_daily ? (
          <>
            <div className="font-black text-slate-900">{data.summary.latest_daily.headline}</div>
            <div className="text-xs text-slate-500 mt-1">Generated {fmtDate(data.summary.latest_daily.generated_at)} · sentiment: <b className="uppercase">{data.summary.latest_daily.sentiment}</b></div>
            <div className="text-sm text-slate-700 mt-2 leading-relaxed">{data.summary.latest_daily.body}</div>
          </>
        ) : (
          <div className="text-sm text-slate-500">No summary yet — regenerate from the Summary tab.</div>
        )}
      </div>
      <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl grid grid-cols-2 md:grid-cols-6 gap-3 text-xs">
        <KV label="TP1 hit" value={`${a.tp1_hit_rate_pct}%`} />
        <KV label="TP2 hit" value={`${a.tp2_hit_rate_pct}%`} />
        <KV label="TP3 hit" value={`${a.tp3_hit_rate_pct}%`} />
        <KV label="SL hits" value={a.sl_hits} />
        <KV label="Avg conf" value={`${a.avg_confidence_pct}%`} />
        <KV label="Conf edge" value={`${a.confidence_edge_pct >= 0 ? "+" : ""}${a.confidence_edge_pct}%`} />
      </div>
      <div className="p-3 bg-slate-100 rounded-lg text-xs text-slate-500">
        Broadcaster runs every {data.news.broadcaster_interval_sec}s · News auto-broadcast to all users on high_impact=true.
      </div>
    </div>
  );
}

// ================ NEWS ================
function NewsTab() {
  const qc = useQueryClient();
  const [cat, setCat] = useState<string>("all");
  const { data, isLoading } = useQuery({
    queryKey: ["ai_admin_news", cat],
    queryFn: async () => (await api.get("/ai/admin/news", { params: { category: cat, limit: 100 } })).data,
  });
  const genMut = useMutation({
    mutationFn: async () => (await api.post("/ai/admin/news/generate", { per_category: 2 })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai_admin_news"] }),
  });
  const delMut = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/ai/admin/news/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai_admin_news"] }),
  });
  const patchMut = useMutation({
    mutationFn: async ({ id, patch }: { id: string; patch: any }) => (await api.put(`/ai/admin/news/${id}`, patch)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai_admin_news"] }),
  });

  const cats = ["all", "forex", "crypto", "indices", "commodities", "indian_market", "global"];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        {cats.map((c) => (
          <button key={c} onClick={() => setCat(c)}
            className={`px-3 py-1.5 rounded-full text-xs font-bold ${cat === c ? "bg-brand-navy text-white" : "bg-slate-100 text-slate-700"}`}>
            {c === "all" ? "All" : c.replace(/_/g, " ")}
          </button>
        ))}
        <div className="ml-auto flex gap-2">
          <button onClick={() => genMut.mutate()} disabled={genMut.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-600 text-white text-sm font-bold disabled:opacity-50">
            <Plus className="w-4 h-4" /> Generate batch
          </button>
        </div>
      </div>
      {isLoading ? <div className="p-8 text-center text-slate-400">Loading…</div> : (
        <div className="space-y-2">
          {(data?.items || []).map((n: any) => (
            <div key={n.news_id} className="bg-white border border-slate-200 rounded-lg p-3">
              <div className="flex items-center gap-2 flex-wrap mb-1">
                <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-slate-100 text-slate-700">{n.category_label}</span>
                {n.high_impact && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-red-100 text-red-700"><Zap className="w-3 h-3" /> High Impact</span>
                )}
                <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${n.sentiment?.includes("bullish") ? "bg-emerald-100 text-emerald-700" : n.sentiment?.includes("bearish") ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-500"}`}>{n.sentiment}</span>
                {!n.is_published && <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-amber-100 text-amber-700">Unpublished</span>}
                <span className="text-[10px] text-slate-500">{fmtDate(n.published_at)}</span>
                <div className="ml-auto flex items-center gap-1">
                  <button onClick={() => patchMut.mutate({ id: n.news_id, patch: { high_impact: !n.high_impact } })}
                    className="text-[11px] px-2 py-1 rounded border border-slate-200 hover:bg-slate-50">
                    {n.high_impact ? "Unmark HI" : "Mark HI"}
                  </button>
                  <button onClick={() => patchMut.mutate({ id: n.news_id, patch: { is_published: !n.is_published } })}
                    className="text-[11px] px-2 py-1 rounded border border-slate-200 hover:bg-slate-50">
                    {n.is_published ? "Unpublish" : "Publish"}
                  </button>
                  <button onClick={() => confirm("Delete this news item?") && delMut.mutate(n.news_id)}
                    className="text-[11px] p-1 rounded border border-red-200 text-red-600 hover:bg-red-50">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
              <div className="font-black text-slate-900 text-sm">{n.title}</div>
              <div className="text-xs text-slate-600 mt-1">{n.summary}</div>
              <div className="flex gap-3 mt-2 text-[10px] text-slate-500">
                {n.symbols?.[0] && <span>Symbol: {n.symbols[0]}</span>}
                {n.broadcast_at ? <span>Broadcast: {fmtDate(n.broadcast_at)}</span> : n.high_impact && <span className="text-amber-600">Awaiting broadcast</span>}
              </div>
            </div>
          ))}
          {(data?.items || []).length === 0 && (
            <div className="p-8 text-center text-slate-400 text-sm">No news items in this category. Click &quot;Generate batch&quot; to create some.</div>
          )}
        </div>
      )}
    </div>
  );
}

// ================ CALENDAR ================
function CalendarTab() {
  const qc = useQueryClient();
  const [impact, setImpact] = useState<string>("");
  const [showAdd, setShowAdd] = useState(false);
  const { data, isLoading } = useQuery({
    queryKey: ["ai_admin_calendar", impact],
    queryFn: async () => (await api.get("/ai/calendar", { params: { impact: impact || undefined, days_ahead: 90, include_past: true, limit: 200 } })).data,
  });
  const delMut = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/ai/admin/calendar/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai_admin_calendar"] }),
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        {["", "high", "medium", "low"].map((imp) => (
          <button key={imp || "all"} onClick={() => setImpact(imp)}
            className={`px-3 py-1.5 rounded-full text-xs font-bold ${impact === imp ? "bg-brand-navy text-white" : "bg-slate-100 text-slate-700"}`}>
            {imp ? imp.toUpperCase() : "All"}
          </button>
        ))}
        <button onClick={() => setShowAdd(true)} className="ml-auto inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-600 text-white text-sm font-bold">
          <Plus className="w-4 h-4" /> Add Event
        </button>
      </div>
      {showAdd && <AddEventForm onClose={() => setShowAdd(false)} onCreated={() => { setShowAdd(false); qc.invalidateQueries({ queryKey: ["ai_admin_calendar"] }); }} />}
      {isLoading ? <div className="p-8 text-center text-slate-400">Loading…</div> : (
        <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">Time (UTC)</th>
                <th className="text-left px-3 py-2">Countdown</th>
                <th className="text-left px-3 py-2">Event</th>
                <th className="text-left px-3 py-2">Region</th>
                <th className="text-left px-3 py-2">Impact</th>
                <th className="text-left px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(data?.events || []).map((e: any) => (
                <tr key={e.event_id} className="border-t border-slate-100">
                  <td className="px-3 py-2 font-mono">{new Date(e.event_time).toISOString().replace("T", " ").slice(0, 16)}</td>
                  <td className="px-3 py-2 text-slate-500">{formatCd(e.countdown_sec)}</td>
                  <td className="px-3 py-2"><b>{e.title}</b><div className="text-[10px] text-slate-500">{e.category}</div></td>
                  <td className="px-3 py-2">{e.country} · <span className="text-slate-500">{e.currency}</span></td>
                  <td className="px-3 py-2">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${e.impact === "high" ? "bg-red-100 text-red-700" : e.impact === "medium" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-500"}`}>{e.impact}</span>
                  </td>
                  <td className="px-3 py-2">
                    <button onClick={() => confirm(`Delete event "${e.title}"?`) && delMut.mutate(e.event_id)} className="text-red-600 hover:text-red-800"><Trash2 className="w-3.5 h-3.5" /></button>
                  </td>
                </tr>
              ))}
              {(data?.events || []).length === 0 && (
                <tr><td colSpan={6} className="text-center py-8 text-slate-400">No events.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function AddEventForm({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [f, setF] = useState({
    title: "", country: "US", currency: "USD", impact: "high",
    category: "General", event_time: "", description: "",
    forecast: "", previous: "",
  });
  const mut = useMutation({
    mutationFn: async () => (await api.post("/ai/admin/calendar", { ...f, event_time: new Date(f.event_time).toISOString() })).data,
    onSuccess: () => onCreated(),
  });
  return (
    <div className="bg-white border-2 border-emerald-300 rounded-lg p-4">
      <div className="text-sm font-black text-slate-700 mb-2">Add Economic Event</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
        <input placeholder="Title" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} className="col-span-2 border border-slate-200 rounded px-2 py-1.5" />
        <input placeholder="Country (US)" value={f.country} onChange={(e) => setF({ ...f, country: e.target.value })} className="border border-slate-200 rounded px-2 py-1.5" />
        <input placeholder="Currency (USD)" value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })} className="border border-slate-200 rounded px-2 py-1.5" />
        <input type="datetime-local" value={f.event_time} onChange={(e) => setF({ ...f, event_time: e.target.value })} className="border border-slate-200 rounded px-2 py-1.5" />
        <select value={f.impact} onChange={(e) => setF({ ...f, impact: e.target.value })} className="border border-slate-200 rounded px-2 py-1.5">
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
        <input placeholder="Category" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} className="border border-slate-200 rounded px-2 py-1.5" />
        <input placeholder="Forecast (optional)" value={f.forecast} onChange={(e) => setF({ ...f, forecast: e.target.value })} className="border border-slate-200 rounded px-2 py-1.5" />
        <input placeholder="Description" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} className="col-span-full border border-slate-200 rounded px-2 py-1.5" />
      </div>
      <div className="flex gap-2 mt-3 text-xs">
        <button onClick={() => mut.mutate()} disabled={!f.title || !f.event_time || mut.isPending} className="px-3 py-1.5 rounded bg-emerald-600 text-white font-bold disabled:opacity-50">Create</button>
        <button onClick={onClose} className="px-3 py-1.5 rounded bg-slate-200 text-slate-700 font-bold">Cancel</button>
        {mut.error && <span className="text-red-600 self-center">{(mut.error as any)?.message}</span>}
      </div>
    </div>
  );
}

// ================ SUMMARY ================
function SummaryTab() {
  const qc = useQueryClient();
  const [type, setType] = useState<"intraday" | "daily" | "weekly">("daily");
  const { data, isLoading } = useQuery({
    queryKey: ["ai_summary_history", type],
    queryFn: async () => (await api.get("/ai/summary/history", { params: { type, limit: 10 } })).data,
  });
  const genMut = useMutation({
    mutationFn: async () => (await api.post("/ai/admin/summary/generate", null, { params: { type } })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai_summary_history"] }),
  });
  const delMut = useMutation({
    mutationFn: async (id: string) => (await api.delete(`/ai/admin/summary/${id}`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai_summary_history"] }),
  });
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        {(["intraday", "daily", "weekly"] as const).map((t) => (
          <button key={t} onClick={() => setType(t)}
            className={`px-3 py-1.5 rounded-full text-xs font-bold ${type === t ? "bg-brand-navy text-white" : "bg-slate-100 text-slate-700"}`}>
            {t.toUpperCase()}
          </button>
        ))}
        <button onClick={() => genMut.mutate()} disabled={genMut.isPending}
          className="ml-auto inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-600 text-white text-sm font-bold disabled:opacity-50">
          <Play className="w-4 h-4" /> Regenerate {type}
        </button>
      </div>
      {isLoading ? <div className="p-8 text-center text-slate-400">Loading…</div> : (
        <div className="space-y-3">
          {(data?.items || []).map((s: any) => (
            <div key={s.summary_id} className="bg-white border border-slate-200 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${s.sentiment?.includes("bullish") ? "bg-emerald-100 text-emerald-700" : s.sentiment?.includes("bearish") ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-500"}`}>{s.sentiment}</span>
                <span className="text-[10px] text-slate-500">{fmtDate(s.generated_at)}</span>
                {s.is_ai_generated && <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-violet-100 text-violet-700">AI</span>}
                <button onClick={() => confirm("Delete this summary?") && delMut.mutate(s.summary_id)} className="ml-auto text-red-600 hover:text-red-800"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
              <div className="font-black text-slate-900">{s.headline}</div>
              <div className="text-xs text-slate-600 mt-1 leading-relaxed">{s.body}</div>
              {(s.key_movers?.length || 0) > 0 && (
                <div className="mt-2 flex flex-wrap gap-2">
                  {s.key_movers.map((m: any) => (
                    <span key={m.symbol} className={`text-[10px] px-2 py-0.5 rounded font-bold ${(m.change_pct ?? 0) >= 0 ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
                      {m.symbol} {(m.change_pct ?? 0) >= 0 ? "+" : ""}{m.change_pct?.toFixed(2)}%
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
          {(data?.items || []).length === 0 && (
            <div className="p-8 text-center text-slate-400 text-sm">No {type} summaries yet.</div>
          )}
        </div>
      )}
    </div>
  );
}

// ================ ANALYTICS ================
function AnalyticsTab() {
  const qc = useQueryClient();
  const [windowDays, setWindowDays] = useState<number | null>(30);
  const { data: ov } = useQuery({
    queryKey: ["ai_analytics_overview", windowDays],
    queryFn: async () => (await api.get("/ai/analytics/overview", { params: windowDays ? { window_days: windowDays } : {} })).data,
    refetchInterval: 60000,
  });
  const { data: bySym } = useQuery({
    queryKey: ["ai_analytics_symbol", windowDays],
    queryFn: async () => (await api.get("/ai/analytics/by-symbol", { params: { window_days: windowDays, limit: 20 } })).data,
  });
  const { data: byTf } = useQuery({
    queryKey: ["ai_analytics_tf", windowDays],
    queryFn: async () => (await api.get("/ai/analytics/by-timeframe", { params: windowDays ? { window_days: windowDays } : {} })).data,
  });
  const tickMut = useMutation({
    mutationFn: async () => (await api.post("/ai/admin/analytics/tick")).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ai_analytics_overview"] }),
  });
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        {[7, 30, 90, null].map((d) => (
          <button key={String(d)} onClick={() => setWindowDays(d)}
            className={`px-3 py-1.5 rounded-full text-xs font-bold ${windowDays === d ? "bg-brand-navy text-white" : "bg-slate-100 text-slate-700"}`}>
            {d ? `${d}d` : "All-time"}
          </button>
        ))}
        <button onClick={() => tickMut.mutate()} disabled={tickMut.isPending}
          className="ml-auto inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-brand-navy text-white text-sm font-bold disabled:opacity-50">
          <RefreshCw className="w-4 h-4" /> Force tick
        </button>
      </div>
      {ov && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Win rate" value={`${ov.win_rate_pct}%`} sub={`${ov.tp_hits} wins / ${ov.resolved_signals} resolved`} tint={ov.win_rate_pct >= 50 ? "emerald" : "amber"} />
            <StatCard label="TP hit distribution" value={`${ov.tp1_hit_rate_pct}%`} sub={`TP1 · TP2 ${ov.tp2_hit_rate_pct}% · TP3 ${ov.tp3_hit_rate_pct}%`} tint="blue" />
            <StatCard label="Sum ROI" value={`${ov.sum_roi_pct >= 0 ? "+" : ""}${ov.sum_roi_pct}%`} sub={`avg ${ov.avg_roi_pct >= 0 ? "+" : ""}${ov.avg_roi_pct}%`} tint={ov.sum_roi_pct >= 0 ? "emerald" : "red"} />
            <StatCard label="Confidence edge" value={`${ov.confidence_edge_pct >= 0 ? "+" : ""}${ov.confidence_edge_pct}%`} sub={`wins ${ov.win_avg_confidence_pct}% vs losses ${ov.loss_avg_confidence_pct}%`} tint={ov.confidence_edge_pct >= 0 ? "emerald" : "red"} />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="bg-white border border-slate-200 rounded-lg p-3">
              <div className="text-xs font-bold text-slate-700 mb-2">BY SYMBOL</div>
              <table className="w-full text-xs">
                <thead className="text-slate-500"><tr><th className="text-left">Symbol</th><th className="text-right">Resolved</th><th className="text-right">Win %</th><th className="text-right">ROI</th></tr></thead>
                <tbody>
                  {(bySym?.rows || []).map((r: any) => (
                    <tr key={r.symbol} className="border-t border-slate-100">
                      <td className="py-1.5 font-bold">{r.symbol}</td>
                      <td className="py-1.5 text-right">{r.resolved}</td>
                      <td className="py-1.5 text-right">{r.win_rate_pct}%</td>
                      <td className={`py-1.5 text-right font-bold ${r.sum_roi >= 0 ? "text-emerald-600" : "text-red-600"}`}>{r.sum_roi >= 0 ? "+" : ""}{r.sum_roi}%</td>
                    </tr>
                  ))}
                  {(bySym?.rows || []).length === 0 && <tr><td colSpan={4} className="text-center py-3 text-slate-400">No resolved signals yet.</td></tr>}
                </tbody>
              </table>
            </div>
            <div className="bg-white border border-slate-200 rounded-lg p-3">
              <div className="text-xs font-bold text-slate-700 mb-2">BY TIMEFRAME</div>
              <table className="w-full text-xs">
                <thead className="text-slate-500"><tr><th className="text-left">TF</th><th className="text-right">Resolved</th><th className="text-right">Win %</th><th className="text-right">ROI</th></tr></thead>
                <tbody>
                  {(byTf?.rows || []).map((r: any) => (
                    <tr key={r.timeframe} className="border-t border-slate-100">
                      <td className="py-1.5 font-bold">{r.timeframe}</td>
                      <td className="py-1.5 text-right">{r.resolved}</td>
                      <td className="py-1.5 text-right">{r.win_rate_pct}%</td>
                      <td className={`py-1.5 text-right font-bold ${r.sum_roi >= 0 ? "text-emerald-600" : "text-red-600"}`}>{r.sum_roi >= 0 ? "+" : ""}{r.sum_roi}%</td>
                    </tr>
                  ))}
                  {(byTf?.rows || []).length === 0 && <tr><td colSpan={4} className="text-center py-3 text-slate-400">No resolved signals yet.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
          {tickMut.data && (
            <div className="text-xs text-slate-500">Last tick: tracked <b>{tickMut.data.tracked}</b> new / resolved <b>{tickMut.data.resolved}</b></div>
          )}
        </>
      )}
    </div>
  );
}

// ================ helpers ================
function StatCard({ label, value, sub, tint }: any) {
  const map: Record<string, string> = {
    emerald: "border-emerald-200 bg-emerald-50",
    blue: "border-blue-200 bg-blue-50",
    violet: "border-violet-200 bg-violet-50",
    amber: "border-amber-200 bg-amber-50",
    red: "border-red-200 bg-red-50",
  };
  return (
    <div className={`p-4 rounded-xl border-2 ${map[tint || "blue"]}`}>
      <div className="text-[10px] font-bold uppercase tracking-widest text-slate-600">{label}</div>
      <div className="text-2xl font-black mt-1">{value}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

function KV({ label, value }: any) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] font-bold text-slate-500 uppercase">{label}</span>
      <span className="text-slate-800 font-bold">{value}</span>
    </div>
  );
}

function formatCd(sec: number | null | undefined): string {
  if (sec == null) return "—";
  if (sec <= 0) return "past";
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import {
  KeyRound, CheckCircle2, AlertTriangle, Ban, Save, Beaker, ChevronDown,
  ChevronUp, Search, ShieldCheck, RefreshCw, Power,
} from "lucide-react";

type ApiItem = {
  api_name: string;
  display_name: string;
  category: string;
  description: string;
  fields: string[];
  test_kind: string;
  has_key: boolean;
  api_key_masked: string;
  extra: Record<string, any>;
  is_enabled: boolean;
  force_demo: boolean;
  status: "live" | "demo" | "disabled";
  updated_at?: string;
};

const STATUS_META: Record<string, { label: string; cls: string; dot: string }> = {
  live: { label: "🟢 Live", cls: "bg-emerald-50 text-emerald-700 border border-emerald-200", dot: "bg-emerald-500" },
  demo: { label: "🟡 Demo", cls: "bg-amber-50 text-amber-700 border border-amber-200", dot: "bg-amber-400" },
  disabled: { label: "🔴 Disabled", cls: "bg-red-50 text-red-700 border border-red-200", dot: "bg-red-500" },
};

const CATEGORY_LABEL: Record<string, string> = {
  payments: "Payments",
  messaging: "Messaging & Notifications",
  investments: "Investments",
  travel: "Travel",
  compliance: "Compliance / KYC",
  other: "Other",
};

export default function ApiManagement() {
  const qc = useQueryClient();
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["api-settings"],
    queryFn: async () => (await api.get("/admin/api-settings")).data as { items: ApiItem[]; demo_count: number; live_count: number; disabled_count: number; total: number },
  });

  const [openName, setOpenName] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "demo" | "live" | "disabled">("all");

  const grouped = useMemo(() => {
    const items = (data?.items || []).filter((i) => {
      if (filter !== "all" && i.status !== filter) return false;
      if (query && !`${i.display_name} ${i.api_name} ${i.category}`.toLowerCase().includes(query.toLowerCase())) return false;
      return true;
    });
    const map: Record<string, ApiItem[]> = {};
    for (const it of items) {
      const cat = it.category || "other";
      (map[cat] ||= []).push(it);
    }
    return map;
  }, [data, filter, query]);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2">
            <KeyRound className="w-6 h-6" /> API Management
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Add or update third-party API keys. Demo mode is used automatically when a key is missing.
          </p>
        </div>
        <button onClick={() => refetch()} className="btn-ghost gap-2 text-sm">
          <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      {/* Demo banner */}
      {data && data.demo_count > 0 ? (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl px-4 py-3 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5 shrink-0" />
          <div className="flex-1">
            <p className="font-extrabold text-amber-900">Demo Mode Active</p>
            <p className="text-sm text-amber-800">
              Live API keys are not configured yet for <b>{data.demo_count}</b> integration{data.demo_count > 1 ? "s" : ""}. Demo data is being used. Configure the keys below — switching to Live happens automatically, no redeploy needed.
            </p>
          </div>
        </div>
      ) : null}

      {/* Stats */}
      {data ? (
        <div className="grid sm:grid-cols-3 gap-3">
          <StatCard label="🟢 Live" value={data.live_count} sub="Connected & active" cls="from-emerald-500 to-emerald-600" />
          <StatCard label="🟡 Demo" value={data.demo_count} sub="No key — using demo data" cls="from-amber-400 to-orange-500" />
          <StatCard label="🔴 Disabled" value={data.disabled_count} sub="Turned off by admin" cls="from-red-500 to-rose-600" />
        </div>
      ) : null}

      {/* Filters */}
      <div className="card flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-400" />
          <input className="input" placeholder="Search by name or category…" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="flex gap-1 bg-slate-100 rounded-xl p-1">
          {(["all", "live", "demo", "disabled"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-xs font-bold rounded-lg transition ${filter === f ? "bg-white shadow text-brand-navy" : "text-slate-500"}`}
            >
              {f === "all" ? "All" : STATUS_META[f].label}
            </button>
          ))}
        </div>
      </div>

      {/* Loader */}
      {isLoading ? <div className="card text-slate-400 text-sm">Loading APIs…</div> : null}

      {/* Grouped list */}
      {Object.keys(grouped)
        .sort()
        .map((cat) => (
          <div key={cat} className="space-y-2">
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-wider px-1">{CATEGORY_LABEL[cat] || cat}</h3>
            <div className="space-y-2">
              {grouped[cat].map((it) => (
                <ApiRow
                  key={it.api_name}
                  item={it}
                  expanded={openName === it.api_name}
                  onToggle={() => setOpenName(openName === it.api_name ? null : it.api_name)}
                  onChanged={() => qc.invalidateQueries({ queryKey: ["api-settings"] })}
                />
              ))}
            </div>
          </div>
        ))}

      {/* Empty state */}
      {!isLoading && data && Object.keys(grouped).length === 0 ? (
        <div className="card text-center text-slate-400 py-10">No APIs match your filter.</div>
      ) : null}

      <div className="card bg-slate-50 border-dashed">
        <div className="flex items-start gap-3">
          <ShieldCheck className="w-5 h-5 text-brand-primary mt-0.5" />
          <div className="text-sm text-slate-600">
            <p className="font-bold text-slate-700">Security note</p>
            <p>API keys are stored in MongoDB and never exposed to the mobile app. Saved keys are masked here for safety. Keys are decrypted only when making outbound requests on the server.</p>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, cls }: { label: string; value: number; sub: string; cls: string }) {
  return (
    <div className={`rounded-2xl p-4 text-white bg-gradient-to-br ${cls} shadow-glow`}>
      <p className="text-xs font-bold opacity-80">{label}</p>
      <p className="text-3xl font-extrabold mt-1">{value}</p>
      <p className="text-xs opacity-90">{sub}</p>
    </div>
  );
}

function ApiRow({ item, expanded, onToggle, onChanged }: { item: ApiItem; expanded: boolean; onToggle: () => void; onChanged: () => void }) {
  const [form, setForm] = useState<{ api_key: string; extra: Record<string, string>; force_demo: boolean }>({
    api_key: "",
    extra: { ...(item.extra || {}) } as any,
    force_demo: item.force_demo,
  });
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    setForm({ api_key: "", extra: { ...(item.extra || {}) } as any, force_demo: item.force_demo });
    setTestResult(null);
  }, [item.api_name, item.updated_at]);

  const save = useMutation({
    mutationFn: async (body: any) => (await api.put(`/admin/api-settings/${item.api_name}`, body)).data,
    onSuccess: () => onChanged(),
  });
  const toggleEnabled = useMutation({
    mutationFn: async () => (await api.put(`/admin/api-settings/${item.api_name}`, { is_enabled: !item.is_enabled })).data,
    onSuccess: () => onChanged(),
  });
  const testConn = useMutation({
    mutationFn: async () => (await api.post(`/admin/api-settings/${item.api_name}/test`)).data,
    onSuccess: (d) => setTestResult({ ok: d.ok, message: d.message }),
    onError: () => setTestResult({ ok: false, message: "Test request failed." }),
  });

  const meta = STATUS_META[item.status];
  const extraFields = item.fields.filter((f) => f !== "api_key");

  return (
    <div className="border border-slate-200 rounded-2xl bg-white shadow-sm overflow-hidden">
      {/* Header row */}
      <button onClick={onToggle} className="w-full px-4 py-3 flex items-center gap-3 hover:bg-slate-50 transition text-left">
        <span className={`w-2.5 h-2.5 rounded-full ${meta.dot}`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="font-extrabold text-slate-800 truncate">{item.display_name}</p>
            <span className={`badge ${meta.cls}`}>{meta.label}</span>
            {item.has_key ? <span className="badge badge-info">Key set</span> : null}
            {item.force_demo ? <span className="badge badge-warn">Force-demo</span> : null}
          </div>
          <p className="text-xs text-slate-500 mt-0.5 truncate">{item.description}</p>
        </div>
        {expanded ? <ChevronUp className="w-4 h-4 text-slate-400" /> : <ChevronDown className="w-4 h-4 text-slate-400" />}
      </button>

      {/* Expanded form */}
      {expanded ? (
        <div className="border-t border-slate-100 p-4 space-y-3 bg-slate-50/50">
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-600">API Key {item.has_key ? <span className="text-slate-400">(current: {item.api_key_masked})</span> : null}</label>
              <input
                type="password"
                autoComplete="new-password"
                className="input mt-1 font-mono text-sm"
                placeholder={item.has_key ? "Leave blank to keep current key" : "Paste API key here"}
                value={form.api_key}
                onChange={(e) => setForm({ ...form, api_key: e.target.value })}
              />
            </div>
            {extraFields.map((f) => (
              <div key={f}>
                <label className="text-xs font-semibold text-slate-600">{labelize(f)}</label>
                <input
                  className="input mt-1 font-mono text-sm"
                  placeholder={f}
                  value={form.extra[f] || ""}
                  onChange={(e) => setForm({ ...form, extra: { ...form.extra, [f]: e.target.value } })}
                />
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between gap-3 flex-wrap">
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="w-4 h-4 accent-brand-primary"
                checked={form.force_demo}
                onChange={(e) => setForm({ ...form, force_demo: e.target.checked })}
              />
              <span>Force demo mode (ignore live key)</span>
            </label>
            <div className="flex gap-2 flex-wrap">
              <button
                onClick={() => toggleEnabled.mutate()}
                disabled={toggleEnabled.isPending}
                className={`btn-ghost gap-2 text-sm ${item.is_enabled ? "" : "!text-emerald-700"}`}
              >
                <Power className="w-4 h-4" /> {item.is_enabled ? "Disable" : "Enable"}
              </button>
              <button onClick={() => testConn.mutate()} disabled={testConn.isPending} className="btn-ghost gap-2 text-sm">
                <Beaker className="w-4 h-4" /> {testConn.isPending ? "Testing…" : "Test Connection"}
              </button>
              <button
                onClick={() =>
                  save.mutate({
                    api_key: form.api_key || undefined,
                    extra: form.extra,
                    force_demo: form.force_demo,
                  })
                }
                disabled={save.isPending}
                className="btn-primary gap-2 text-sm"
              >
                <Save className="w-4 h-4" /> {save.isPending ? "Saving…" : "Save"}
              </button>
            </div>
          </div>

          {testResult ? (
            <div className={`rounded-xl px-3 py-2 text-sm flex items-start gap-2 ${testResult.ok ? "bg-emerald-50 text-emerald-800 border border-emerald-200" : "bg-amber-50 text-amber-800 border border-amber-200"}`}>
              {testResult.ok ? <CheckCircle2 className="w-4 h-4 mt-0.5" /> : <AlertTriangle className="w-4 h-4 mt-0.5" />}
              <span>{testResult.message}</span>
            </div>
          ) : null}

          {save.isSuccess ? (
            <p className="text-xs text-emerald-700 flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Saved.</p>
          ) : null}
          {save.isError ? (
            <p className="text-xs text-red-700 flex items-center gap-1"><Ban className="w-3 h-3" /> Failed to save — try again.</p>
          ) : null}

          <p className="text-[11px] text-slate-400">Last updated: {fmtDate(item.updated_at)}</p>
        </div>
      ) : null}
    </div>
  );
}

function labelize(s: string) {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

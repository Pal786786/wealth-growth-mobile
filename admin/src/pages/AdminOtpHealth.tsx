import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import {
  Activity, RefreshCw, CheckCircle2, XCircle, Search, Radio,
  AlertTriangle, FlaskConical, Send,
} from "lucide-react";

type SmsLog = {
  mobile: string;
  purpose: string;
  provider?: string;
  ok?: boolean;
  error?: string | null;
  demo?: boolean;
  at: string;
};

type ApiResponse = {
  items: SmsLog[];
  count: number;
  mode: string;
  stats_24h: { total: number; sent: number; failed: number };
};

type StatusFilter = "all" | "sent" | "failed";

const MODE_LABEL: Record<string, { label: string; cls: string }> = {
  live_msg91_widget: { label: "LIVE — MSG91 Widget", cls: "bg-emerald-100 text-emerald-800 border-emerald-300" },
  demo: { label: "DEMO MODE", cls: "bg-amber-100 text-amber-800 border-amber-300" },
};

export default function AdminOtpHealth() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");

  const { data, isFetching, refetch } = useQuery<ApiResponse>({
    queryKey: ["sms-logs"],
    queryFn: async () => (await api.get("/admin/sms-logs?limit=150")).data,
    refetchInterval: 10000,
  });

  const items = data?.items || [];
  const stats = data?.stats_24h || { total: 0, sent: 0, failed: 0 };
  const mode = data?.mode || "demo";
  const modeInfo = MODE_LABEL[mode] || {
    label: `LIVE — ${mode.replace("live_", "").toUpperCase()}`,
    cls: "bg-emerald-100 text-emerald-800 border-emerald-300",
  };

  const filtered = useMemo(() => {
    let rows = items;
    if (status === "sent") rows = rows.filter((r) => r.ok);
    if (status === "failed") rows = rows.filter((r) => !r.ok);
    if (search.trim()) {
      const q = search.trim();
      rows = rows.filter((r) => r.mobile.includes(q) || (r.error || "").toLowerCase().includes(q.toLowerCase()));
    }
    return rows;
  }, [items, search, status]);

  const lastFailure = items.find((r) => !r.ok && r.error);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2">
            <Activity className="w-6 h-6" /> OTP Delivery Health
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            <span className={`badge border mr-2 ${modeInfo.cls}`}>
              <Radio className="w-3 h-3 inline mr-1" /> {modeInfo.label}
            </span>
            Every SMS/OTP attempt with the provider&apos;s exact result · Auto-refreshes every 10s
          </p>
        </div>
        <button onClick={() => refetch()} className="btn-ghost gap-2 text-sm">
          <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      {lastFailure ? (
        <div className="bg-red-50 border border-red-200 rounded-2xl px-4 py-3 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600 mt-0.5 shrink-0" />
          <div className="text-sm text-red-900 min-w-0">
            <p className="font-extrabold">Most recent failure ({fmtDate(lastFailure.at)})</p>
            <p className="break-words">{lastFailure.error}</p>
            <p className="text-xs text-red-700 mt-1">
              If the error mentions KYC / verification / balance or an empty response: complete
              KYC verification and add wallet balance in the MSG91 dashboard, then re-run
              <b> Test Connection</b> in API Management.
            </p>
          </div>
        </div>
      ) : null}

      <div className="grid sm:grid-cols-4 gap-3">
        <Stat label="Attempts (24h)" value={stats.total} cls="from-slate-500 to-slate-700" Icon={Send} />
        <Stat label="Sent (24h)" value={stats.sent} cls="from-emerald-500 to-emerald-600" Icon={CheckCircle2} />
        <Stat label="Failed (24h)" value={stats.failed} cls="from-rose-500 to-red-600" Icon={XCircle} />
        <Stat label="Mode" value={mode === "demo" ? "Demo" : "Live"} cls="from-violet-500 to-fuchsia-600" Icon={FlaskConical} />
      </div>

      <div className="card flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-400" />
          <input
            className="input"
            placeholder="Search by mobile or error text…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {(["all", "sent", "failed"] as StatusFilter[]).map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`px-3 py-1.5 rounded-full text-xs font-bold capitalize border transition ${
                status === s
                  ? "bg-brand-navy text-white border-brand-navy"
                  : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="card overflow-hidden">
        {filtered.length === 0 ? (
          <div className="text-slate-400 py-12 text-center">
            <Activity className="w-10 h-10 mx-auto opacity-40 mb-2" />
            <p className="font-bold">No delivery attempts recorded</p>
            <p className="text-xs mt-1">
              Attempts appear here when users request OTPs or when you press Test Connection in API Management
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 uppercase font-bold border-b border-slate-200">
                  <th className="py-2 px-2">Time</th>
                  <th className="py-2 px-2">Mobile</th>
                  <th className="py-2 px-2">Purpose</th>
                  <th className="py-2 px-2">Provider</th>
                  <th className="py-2 px-2">Result</th>
                  <th className="py-2 px-2">Error Detail</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r, i) => (
                  <tr key={`${r.mobile}-${r.at}-${i}`} className="border-b border-slate-100 hover:bg-slate-50 align-top">
                    <td className="py-2 px-2 text-xs text-slate-500 whitespace-nowrap">{fmtDate(r.at)}</td>
                    <td className="py-2 px-2 font-mono whitespace-nowrap">{r.mobile}</td>
                    <td className="py-2 px-2">
                      <span className={`badge capitalize ${r.purpose === "test_connection" ? "bg-violet-50 text-violet-700 border border-violet-200" : "bg-slate-100 text-slate-700"}`}>
                        {r.purpose === "test_connection" ? "Test Connection" : r.purpose}
                      </span>
                    </td>
                    <td className="py-2 px-2 whitespace-nowrap">
                      <span className="badge bg-slate-100 text-slate-700">{r.provider || "—"}</span>
                      {r.demo ? <span className="badge bg-amber-50 text-amber-700 border border-amber-200 ml-1">demo</span> : null}
                    </td>
                    <td className="py-2 px-2 whitespace-nowrap">
                      {r.ok ? (
                        <span className="badge bg-emerald-50 text-emerald-700 border border-emerald-200">
                          <CheckCircle2 className="w-3 h-3 inline mr-1" /> Sent
                        </span>
                      ) : (
                        <span className="badge bg-red-50 text-red-700 border border-red-200">
                          <XCircle className="w-3 h-3 inline mr-1" /> Failed
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-2 text-xs text-slate-600 max-w-[420px]">
                      {r.error ? <span className="break-words">{r.error}</span> : <span className="text-slate-300">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card bg-slate-50 border-dashed text-sm text-slate-600">
        <p className="font-bold text-slate-700 mb-1">Reading this page</p>
        <ol className="list-decimal list-inside space-y-1 text-xs">
          <li><b>Sent</b> = the provider accepted the message (for MSG91 Widget: a request ID was returned)</li>
          <li><b>Failed</b> = the provider rejected or ignored the request — the exact provider response is in Error Detail (secrets always redacted)</li>
          <li>MSG91 requires a <b>KYC-verified account</b> and <b>wallet balance &gt; ₹0</b> before it sends any SMS</li>
          <li>Live failures never fall back to demo OTPs — users see an honest &quot;try again&quot; error instead</li>
        </ol>
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
        <p className="text-xl font-extrabold mt-1">{value}</p>
      </div>
    </div>
  );
}

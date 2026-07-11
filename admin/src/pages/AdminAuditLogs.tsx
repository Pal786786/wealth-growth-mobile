import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import {
  ScrollText, Search, RefreshCw, Download, ShieldCheck, User, Coins, Settings, Bell,
  KeyRound, FileCheck2, Users, Clock,
} from "lucide-react";

type Log = {
  id?: string;
  admin_id?: string;
  actor_name?: string;
  action: string;
  target?: string;
  meta?: Record<string, any>;
  at: string;
};

const ACTION_ICONS: Record<string, any> = {
  "login": ShieldCheck,
  "user": Users,
  "kyc": FileCheck2,
  "wallet": Coins,
  "notif": Bell,
  "api_settings": KeyRound,
  "settings": Settings,
};

function iconFor(action: string) {
  for (const [k, Icon] of Object.entries(ACTION_ICONS)) {
    if (action.startsWith(k)) return Icon;
  }
  return User;
}

function colorFor(action: string) {
  if (action.includes("delete") || action.includes("ban") || action.includes("reject")) return "text-red-600 bg-red-50";
  if (action.includes("approve") || action.includes("grant") || action.includes("create")) return "text-emerald-600 bg-emerald-50";
  if (action.includes("update") || action.includes("edit")) return "text-sky-600 bg-sky-50";
  return "text-slate-600 bg-slate-50";
}

export default function AdminAuditLogs() {
  const [search, setSearch] = useState("");
  const [action, setAction] = useState("");
  const [days, setDays] = useState("");
  const [limit, setLimit] = useState("200");

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["admin-audit", action, days, limit],
    queryFn: async () => (await api.get<{ items: Log[]; total: number }>("/admin/audit", {
      params: {
        action: action || undefined,
        since_days: days ? Number(days) : undefined,
        limit: Number(limit) || 200,
      },
    })).data,
    refetchInterval: 30000,
  });

  const filtered = useMemo(() => {
    const items = data?.items || [];
    if (!search) return items;
    const q = search.toLowerCase();
    return items.filter((r) =>
      [r.action, r.target, r.actor_name, r.admin_id].some((v) => (v || "").toLowerCase().includes(q))
    );
  }, [data, search]);

  const stats = useMemo(() => {
    const items = data?.items || [];
    const byActor: Record<string, number> = {};
    for (const r of items) byActor[r.actor_name || "system"] = (byActor[r.actor_name || "system"] || 0) + 1;
    return {
      total: items.length,
      actors: Object.keys(byActor).length,
      top: Object.entries(byActor).sort((a, b) => b[1] - a[1]).slice(0, 3),
      logins: items.filter((r) => r.action.includes("login")).length,
    };
  }, [data]);

  const exportCsv = () => {
    const rows = filtered.map((r) =>
      [r.at, r.actor_name || r.admin_id, r.action, r.target || "", JSON.stringify(r.meta || {})]
        .map((v) => `"${String(v).replace(/"/g, '""')}"`).join(",")
    );
    const blob = new Blob(["timestamp,actor,action,target,meta\n" + rows.join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `audit-logs-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2">
            <ScrollText className="w-6 h-6" /> Audit Logs
          </h2>
          <p className="text-sm text-slate-500 mt-1">Every admin action, login event and security change in chronological order.</p>
        </div>
        <div className="flex gap-2">
          <button onClick={exportCsv} className="btn-ghost gap-2 text-sm" disabled={!filtered.length}>
            <Download className="w-4 h-4" /> Export CSV
          </button>
          <button onClick={() => refetch()} className="btn-ghost gap-2 text-sm">
            <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Stat label="Total events" value={stats.total} cls="from-sky-500 to-blue-600" Icon={ScrollText} />
        <Stat label="Distinct admins" value={stats.actors} cls="from-violet-500 to-fuchsia-600" Icon={Users} />
        <Stat label="Login events" value={stats.logins} cls="from-emerald-500 to-emerald-600" Icon={ShieldCheck} />
        <Stat label="Most active" value={stats.top[0]?.[0] || "—"} cls="from-amber-500 to-orange-600" Icon={User} sub={stats.top[0] ? `${stats.top[0][1]} actions` : ""} />
      </div>

      <div className="card flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-400" />
          <input className="input" placeholder="Search actor, action, target…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="input max-w-[170px]" value={action} onChange={(e) => setAction(e.target.value)}>
          <option value="">All actions</option>
          <option value="login">Login</option>
          <option value="user">User mgmt</option>
          <option value="kyc">KYC</option>
          <option value="wallet">Wallet adjust</option>
          <option value="api_settings">API settings</option>
          <option value="notif">Notifications</option>
          <option value="settings">Settings</option>
        </select>
        <select className="input max-w-[140px]" value={days} onChange={(e) => setDays(e.target.value)}>
          <option value="">All time</option>
          <option value="1">Last 24h</option>
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
        </select>
        <select className="input max-w-[120px]" value={limit} onChange={(e) => setLimit(e.target.value)}>
          <option value="100">100 rows</option>
          <option value="200">200 rows</option>
          <option value="500">500 rows</option>
        </select>
      </div>

      <div className="card overflow-hidden">
        {isLoading ? <div className="text-slate-400 py-8 text-center">Loading logs…</div> : null}
        {!isLoading && filtered.length === 0 ? <div className="text-slate-400 py-10 text-center">No matching events.</div> : null}
        <div className="divide-y divide-slate-100">
          {filtered.map((r, i) => {
            const Icon = iconFor(r.action);
            const cls = colorFor(r.action);
            return (
              <div key={r.id || i} className="py-3 flex gap-3 items-start hover:bg-slate-50 px-1">
                <div className={`w-9 h-9 rounded-xl flex items-center justify-center shrink-0 ${cls}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-bold text-slate-800 text-sm">{r.action}</span>
                    {r.target ? <span className="badge bg-slate-100 text-slate-600 text-[10px]">→ {typeof r.target === "string" ? r.target : JSON.stringify(r.target)}</span> : null}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5">
                    by <b>{r.actor_name || r.admin_id || "system"}</b>
                    {r.meta && Object.keys(r.meta).length ? <span className="text-slate-400 ml-2 font-mono">{JSON.stringify(r.meta).slice(0, 80)}{JSON.stringify(r.meta).length > 80 ? "…" : ""}</span> : null}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  <p className="text-xs text-slate-400 flex items-center gap-1"><Clock className="w-3 h-3" />{fmtDate(r.at)}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, cls, Icon, sub }: { label: string; value: any; cls: string; Icon: any; sub?: string }) {
  return (
    <div className={`rounded-2xl p-3 text-white bg-gradient-to-br ${cls} flex items-center gap-3`}>
      <Icon className="w-8 h-8 opacity-70" />
      <div className="min-w-0">
        <p className="text-[11px] font-bold opacity-80">{label}</p>
        <p className="text-xl font-extrabold mt-1 truncate">{value}</p>
        {sub ? <p className="text-[10px] opacity-80">{sub}</p> : null}
      </div>
    </div>
  );
}

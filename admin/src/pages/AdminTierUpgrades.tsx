import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import {
  Crown, TrendingUp, Users as UsersIcon, RefreshCw, Search,
  ArrowUpRight, Award, Activity, BarChart3,
} from "lucide-react";

type Upgrade = {
  upgrade_id: string;
  user_id: string;
  user_name?: string;
  old_tier_id: string;
  old_tier_name: string;
  new_tier_id: string;
  new_tier_name: string;
  points_at_upgrade: number;
  trigger: string;
  trigger_detail?: string;
  at: string;
};

type Tier = {
  id: string; name: string; min: number; rate: number; color?: string;
  emoji?: string; tagline?: string; cashback_rate_pct?: number;
  points_multiplier?: number; perks?: string[];
};

type Analytics = {
  users_total: number;
  users_per_tier: Array<{ tier_id: string; tier_name: string; count: number; color?: string }>;
  migrations: Array<{ old: string; new: string; count: number }>;
  trend_30d: Array<{ date: string; count: number }>;
  by_trigger: Array<{ trigger: string; count: number }>;
  total_upgrades: number;
  tiers: Tier[];
};

const TIER_COLORS: Record<string, { bg: string; text: string; ring: string }> = {
  bronze:   { bg: "from-orange-200 to-orange-400",  text: "text-orange-900",  ring: "ring-orange-300" },
  silver:   { bg: "from-slate-200 to-slate-400",    text: "text-slate-900",   ring: "ring-slate-300" },
  gold:     { bg: "from-yellow-300 to-amber-500",   text: "text-amber-950",   ring: "ring-amber-300" },
  platinum: { bg: "from-sky-300 to-blue-500",       text: "text-blue-950",    ring: "ring-sky-300" },
  diamond:  { bg: "from-violet-300 to-fuchsia-500", text: "text-fuchsia-950", ring: "ring-violet-300" },
};

export default function AdminTierUpgrades() {
  const [search, setSearch] = useState("");
  const [tierFilter, setTierFilter] = useState<string>("all");

  const { data: analytics, isFetching: aFetching, refetch: aRefetch } = useQuery({
    queryKey: ["tier-analytics"],
    queryFn: async () => (await api.get("/admin/tier-upgrades/analytics")).data as Analytics,
    refetchInterval: 30000,
  });

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["tier-upgrades", tierFilter, search],
    queryFn: async () => {
      const params: any = { limit: 200 };
      if (tierFilter !== "all") params.tier = tierFilter;
      if (search.trim()) params.search = search.trim();
      return (await api.get("/admin/tier-upgrades", { params })).data as { items: Upgrade[]; total: number };
    },
  });

  const items = data?.items || [];

  const maxTrend = useMemo(() => Math.max(1, ...(analytics?.trend_30d?.map((t) => t.count) || [1])), [analytics]);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2">
            <Crown className="w-6 h-6" /> Tier Upgrades
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Loyalty tier progression of all users. Notifications fire automatically on every tier increase.
          </p>
        </div>
        <button onClick={() => { refetch(); aRefetch(); }} className="btn-ghost gap-2 text-sm">
          <RefreshCw className={`w-4 h-4 ${(isFetching || aFetching) ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      {/* Users-per-tier strip */}
      {analytics ? (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {analytics.users_per_tier.map((t) => {
            const c = TIER_COLORS[t.tier_id] || TIER_COLORS.bronze;
            const pct = analytics.users_total > 0 ? Math.round((t.count / analytics.users_total) * 100) : 0;
            const tierInfo = analytics.tiers.find((tt) => tt.id === t.tier_id);
            return (
              <div key={t.tier_id} className={`rounded-2xl p-4 bg-gradient-to-br ${c.bg} ${c.text} shadow-sm`}>
                <p className="text-xs font-bold opacity-80 flex items-center gap-1">
                  {tierInfo?.emoji} {t.tier_name}
                </p>
                <p className="text-3xl font-extrabold mt-1">{t.count}</p>
                <p className="text-xs opacity-80 mt-0.5">
                  {pct}% of users · {tierInfo?.cashback_rate_pct ?? 0}% cashback
                </p>
              </div>
            );
          })}
        </div>
      ) : null}

      {/* High-level KPIs */}
      {analytics ? (
        <div className="grid sm:grid-cols-3 gap-3">
          <Kpi label="Total upgrades (all-time)" value={analytics.total_upgrades} Icon={Award} cls="from-emerald-500 to-emerald-600" />
          <Kpi label="Active users" value={analytics.users_total} Icon={UsersIcon} cls="from-sky-500 to-blue-600" />
          <Kpi label="Last 30 d upgrades" value={analytics.trend_30d.reduce((s, t) => s + t.count, 0)} Icon={TrendingUp} cls="from-violet-500 to-fuchsia-600" />
        </div>
      ) : null}

      {/* Trend chart (last 30 days) */}
      {analytics && analytics.trend_30d.length > 0 ? (
        <div className="card">
          <p className="text-sm font-bold text-brand-navy mb-2 flex items-center gap-2"><BarChart3 className="w-4 h-4" /> Last 30 days · upgrades trend</p>
          <div className="flex items-end gap-1.5 h-32">
            {analytics.trend_30d.map((t, i) => (
              <div key={i} className="flex-1 flex flex-col items-center gap-1 min-w-0">
                <div
                  className="w-full rounded-t bg-gradient-to-t from-brand-primary to-brand-secondary"
                  style={{ height: `${(t.count / maxTrend) * 100}%` }}
                  title={`${t.date}: ${t.count} upgrades`}
                />
              </div>
            ))}
          </div>
          <p className="text-[10px] text-slate-400 mt-1">
            Earliest: {analytics.trend_30d[0]?.date} · Latest: {analytics.trend_30d[analytics.trend_30d.length - 1]?.date}
          </p>
        </div>
      ) : null}

      {/* Trigger breakdown */}
      {analytics && analytics.by_trigger.length > 0 ? (
        <div className="card">
          <p className="text-sm font-bold text-brand-navy mb-2 flex items-center gap-2"><Activity className="w-4 h-4" /> Top upgrade triggers</p>
          <div className="flex flex-wrap gap-2">
            {analytics.by_trigger.map((b) => (
              <span key={b.trigger} className="badge bg-sky-50 text-sky-800 border border-sky-200">
                {b.trigger} · <b>{b.count}</b>
              </span>
            ))}
          </div>
        </div>
      ) : null}

      {/* Filters */}
      <div className="card flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-400" />
          <input className="input" placeholder="Search by user name or user ID…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="input max-w-[200px]" value={tierFilter} onChange={(e) => setTierFilter(e.target.value)}>
          <option value="all">All tiers</option>
          {(analytics?.tiers || []).map((t) => (
            <option key={t.id} value={t.id}>Upgraded → {t.name}</option>
          ))}
        </select>
      </div>

      {/* Upgrades table */}
      <div className="card overflow-hidden">
        {items.length === 0 ? (
          <div className="text-slate-400 py-12 text-center">
            <Crown className="w-10 h-10 mx-auto opacity-40 mb-2" />
            <p className="font-bold">No tier upgrades yet</p>
            <p className="text-xs mt-1">Upgrade events appear here as users cross point thresholds.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 uppercase font-bold border-b border-slate-200">
                  <th className="py-2 px-2">User</th>
                  <th className="py-2 px-2">Old → New</th>
                  <th className="py-2 px-2 text-right">Points</th>
                  <th className="py-2 px-2">Trigger</th>
                  <th className="py-2 px-2">When</th>
                </tr>
              </thead>
              <tbody>
                {items.map((u) => {
                  const oldC = TIER_COLORS[u.old_tier_id] || TIER_COLORS.bronze;
                  const newC = TIER_COLORS[u.new_tier_id] || TIER_COLORS.bronze;
                  return (
                    <tr key={u.upgrade_id} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="py-3 px-2">
                        <p className="font-semibold text-slate-800">{u.user_name || "—"}</p>
                        <p className="text-[11px] font-mono text-slate-500">{u.user_id.slice(0, 18)}…</p>
                      </td>
                      <td className="py-3 px-2">
                        <div className="flex items-center gap-1.5">
                          <span className={`px-2 py-0.5 rounded text-[11px] font-bold bg-gradient-to-br ${oldC.bg} ${oldC.text}`}>{u.old_tier_name}</span>
                          <ArrowUpRight className="w-3.5 h-3.5 text-slate-400" />
                          <span className={`px-2 py-0.5 rounded text-[11px] font-bold bg-gradient-to-br ${newC.bg} ${newC.text}`}>{u.new_tier_name}</span>
                        </div>
                      </td>
                      <td className="py-3 px-2 text-right font-bold">{u.points_at_upgrade}</td>
                      <td className="py-3 px-2">
                        <p className="text-xs font-semibold text-slate-700">{u.trigger}</p>
                        {u.trigger_detail ? <p className="text-[10px] text-slate-500">{u.trigger_detail}</p> : null}
                      </td>
                      <td className="py-3 px-2 text-xs text-slate-500">{fmtDate(u.at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Migration matrix */}
      {analytics && analytics.migrations.length > 0 ? (
        <div className="card">
          <p className="text-sm font-bold text-brand-navy mb-3 flex items-center gap-2"><ArrowUpRight className="w-4 h-4" /> Tier migrations</p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {analytics.migrations.map((m, i) => {
              const oldC = TIER_COLORS[m.old] || TIER_COLORS.bronze;
              const newC = TIER_COLORS[m.new] || TIER_COLORS.bronze;
              return (
                <div key={i} className="flex items-center justify-between bg-slate-50 rounded-xl px-3 py-2">
                  <div className="flex items-center gap-1.5">
                    <span className={`px-2 py-0.5 rounded text-[11px] font-bold bg-gradient-to-br ${oldC.bg} ${oldC.text} capitalize`}>{m.old}</span>
                    <ArrowUpRight className="w-3 h-3 text-slate-400" />
                    <span className={`px-2 py-0.5 rounded text-[11px] font-bold bg-gradient-to-br ${newC.bg} ${newC.text} capitalize`}>{m.new}</span>
                  </div>
                  <span className="font-extrabold text-brand-navy">{m.count}</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Kpi({ label, value, Icon, cls }: { label: string; value: any; Icon: any; cls: string }) {
  return (
    <div className={`rounded-2xl p-4 text-white bg-gradient-to-br ${cls} flex items-center gap-3`}>
      <Icon className="w-9 h-9 opacity-70" />
      <div>
        <p className="text-xs font-bold opacity-80">{label}</p>
        <p className="text-2xl font-extrabold mt-1">{value}</p>
      </div>
    </div>
  );
}

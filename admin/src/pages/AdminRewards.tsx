/**
 * Sprint 14 · MFB Rewards & Ecosystem — Admin Console
 * ----------------------------------------------------
 * 8-tab console for the internal MFB Token platform:
 *   Overview · Users · Campaigns · Transactions · Leaderboards · Achievements · Settings · Analytics
 */
import React, { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import {
  Trophy, Gift, Users, Coins, Sparkles, ListChecks,
  Settings as SettingsIcon, BarChart3, Plus, Trash2, RefreshCw, X,
} from "lucide-react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  PieChart, Pie, Cell, BarChart, Bar, Legend,
} from "recharts";

const TAB = [
  { id: "overview",     label: "Overview",     icon: Trophy },
  { id: "users",         label: "Users",         icon: Users },
  { id: "campaigns",     label: "Campaigns",     icon: Sparkles },
  { id: "transactions", label: "Transactions", icon: Coins },
  { id: "leaderboards", label: "Leaderboards", icon: BarChart3 },
  { id: "achievements", label: "Achievements", icon: ListChecks },
  { id: "settings",     label: "Settings",     icon: SettingsIcon },
  { id: "analytics",     label: "Analytics",     icon: Gift },
] as const;
type TabId = (typeof TAB)[number]["id"];

const PIE_COLORS = ["#F59E0B", "#3B82F6", "#10B981", "#EF4444", "#8B5CF6", "#EC4899", "#14B8A6", "#F97316"];

export default function AdminRewards() {
  const [tab, setTab] = useState<TabId>("overview");
  return (
    <div className="p-6 space-y-6">
      <header className="flex items-center gap-3">
        <Trophy className="w-6 h-6 text-amber-500" />
        <h1 className="text-2xl font-bold text-slate-900">MFB Rewards Console</h1>
        <span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-semibold">Sprint 14</span>
      </header>

      <div className="border-b border-slate-200 flex overflow-x-auto">
        {TAB.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-semibold whitespace-nowrap border-b-2 ${
              tab === t.id ? "border-amber-500 text-amber-700" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            <t.icon className="w-4 h-4" />
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview"     && <Overview />}
      {tab === "users"         && <UsersTab />}
      {tab === "campaigns"     && <CampaignsTab />}
      {tab === "transactions" && <TransactionsTab />}
      {tab === "leaderboards" && <LeaderboardsTab />}
      {tab === "achievements" && <AchievementsTab />}
      {tab === "settings"     && <SettingsTab />}
      {tab === "analytics"     && <AnalyticsTab />}
    </div>
  );
}

// -------------------- Overview --------------------
function Overview() {
  const { data: kpi, refetch, isFetching } = useQuery({
    queryKey: ["mfb-kpi"],
    queryFn: async () => (await api.get("/admin/mfb-rewards/overview")).data,
    refetchInterval: 30000,
  });
  const cards = [
    { k: "total_issued",       label: "Total Issued",     tone: "amber" },
    { k: "total_burned",       label: "Total Burned",     tone: "rose" },
    { k: "circulating",         label: "Circulating",       tone: "emerald" },
    { k: "active_users_30d",   label: "Active Users (30d)", tone: "sky" },
    { k: "total_wallets",       label: "Total Wallets",     tone: "violet" },
    { k: "daily_login_today", label: "Daily Logins Today", tone: "cyan" },
    { k: "achievements_unlocked", label: "Achievements", tone: "orange" },
    { k: "referrals_total",     label: "Total Referrals",   tone: "pink" },
    { k: "active_campaigns",   label: "Active Campaigns", tone: "indigo" },
  ] as const;
  return (
    <div>
      <div className="flex justify-end mb-3">
        <button onClick={() => refetch()} className="flex items-center gap-1 text-xs text-slate-600 hover:text-slate-900">
          <RefreshCw className={`w-3 h-3 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {cards.map((c) => (
          <div key={c.k} className={`bg-white border border-slate-200 rounded-xl p-4`}>
            <div className={`text-xs font-semibold text-${c.tone}-700`}>{c.label}</div>
            <div className="text-2xl font-bold text-slate-900 mt-1">{(kpi?.[c.k] ?? 0).toLocaleString()}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// -------------------- Users --------------------
function UsersTab() {
  const [sort, setSort] = useState("lifetime_earned");
  const { data } = useQuery({
    queryKey: ["mfb-users", sort],
    queryFn: async () => (await api.get("/admin/mfb-rewards/users", { params: { sort, limit: 100 } })).data,
  });
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <label className="text-sm text-slate-600">Sort by</label>
        <select value={sort} onChange={(e) => setSort(e.target.value)} className="border rounded px-2 py-1 text-sm">
          <option value="lifetime_earned">Lifetime Earned</option>
          <option value="xp">XP</option>
          <option value="balance">Balance</option>
          <option value="referral_count">Referrals</option>
          <option value="level">Level</option>
        </select>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600 text-left text-xs uppercase">
            <tr><th className="px-3 py-2">User</th><th>Balance</th><th>Lifetime</th><th>XP</th><th>Level</th><th>Tier</th><th>Referrals</th><th>Streak</th></tr>
          </thead>
          <tbody>
            {(data?.items || []).map((u: any) => (
              <tr key={u.user_id} className="border-t border-slate-100">
                <td className="px-3 py-2 font-mono text-xs">{u.user_id}</td>
                <td className="font-semibold">{u.balance}</td>
                <td>{u.lifetime_earned}</td>
                <td>{u.xp}</td>
                <td>{u.level}</td>
                <td><span className="text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700 font-semibold">{u.tier}</span></td>
                <td>{u.referral_count}</td>
                <td>{u.streak_current}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// -------------------- Campaigns --------------------
function CampaignsTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["mfb-campaigns"],
    queryFn: async () => (await api.get("/admin/mfb-rewards/campaigns")).data,
  });
  const [showNew, setShowNew] = useState(false);
  const del = useMutation({
    mutationFn: async (id: string) => api.delete(`/admin/mfb-rewards/campaigns/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mfb-campaigns"] }),
  });
  const setStatus = useMutation({
    mutationFn: async ({ id, status }: { id: string; status: string }) =>
      api.patch(`/admin/mfb-rewards/campaigns/${id}`, { status }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mfb-campaigns"] }),
  });

  return (
    <div>
      <div className="flex justify-between mb-3">
        <h2 className="text-lg font-semibold text-slate-800">Campaigns</h2>
        <button onClick={() => setShowNew(true)} className="flex items-center gap-1 bg-amber-500 hover:bg-amber-600 text-white text-sm font-semibold px-3 py-1.5 rounded">
          <Plus className="w-4 h-4" /> New Campaign
        </button>
      </div>
      {showNew && <NewCampaignModal onClose={() => { setShowNew(false); qc.invalidateQueries({ queryKey: ["mfb-campaigns"] }); }} />}
      <div className="grid gap-3">
        {(data?.items || []).map((c: any) => (
          <div key={c.campaign_id} className="bg-white border border-slate-200 rounded-xl p-4">
            <div className="flex justify-between items-start">
              <div>
                <div className="font-semibold text-slate-900">{c.name}</div>
                {c.description && <div className="text-xs text-slate-600">{c.description}</div>}
                <div className="text-xs text-slate-500 mt-1">
                  {new Date(c.start_date).toLocaleDateString()} → {new Date(c.end_date).toLocaleDateString()}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold text-amber-600">+{c.reward}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-semibold ${
                  c.status === "active" ? "bg-emerald-100 text-emerald-700" :
                  c.status === "draft" ? "bg-slate-100 text-slate-700" :
                  c.status === "paused" ? "bg-amber-100 text-amber-700" :
                  "bg-slate-200 text-slate-500"}`}>{c.status}</span>
                <select
                  value={c.status}
                  onChange={(e) => setStatus.mutate({ id: c.campaign_id, status: e.target.value })}
                  className="text-xs border rounded px-1 py-0.5"
                >
                  <option value="draft">draft</option>
                  <option value="active">active</option>
                  <option value="paused">paused</option>
                  <option value="ended">ended</option>
                </select>
                <button onClick={() => del.mutate(c.campaign_id)} className="text-rose-600 hover:bg-rose-50 p-1 rounded"><Trash2 className="w-4 h-4" /></button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function NewCampaignModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [reward, setReward] = useState(100);
  const [days, setDays] = useState(7);
  const [saving, setSaving] = useState(false);
  const create = async () => {
    setSaving(true);
    try {
      const now = new Date();
      const end = new Date(now.getTime() + days * 86400_000);
      await api.post("/admin/mfb-rewards/campaigns", {
        name, description, reward,
        start_date: now.toISOString(),
        end_date:   end.toISOString(),
      });
      onClose();
    } finally { setSaving(false); }
  };
  return (
    <div className="fixed inset-0 bg-slate-900/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-full max-w-md relative">
        <button onClick={onClose} className="absolute right-4 top-4 text-slate-400 hover:text-slate-800"><X className="w-4 h-4" /></button>
        <h3 className="text-lg font-bold text-slate-900 mb-3">New Campaign</h3>
        <div className="space-y-3">
          <label className="block"><span className="text-xs text-slate-600">Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} className="w-full border rounded px-2 py-1.5 mt-1 text-sm" />
          </label>
          <label className="block"><span className="text-xs text-slate-600">Description</span>
            <input value={description} onChange={(e) => setDescription(e.target.value)} className="w-full border rounded px-2 py-1.5 mt-1 text-sm" />
          </label>
          <div className="flex gap-3">
            <label className="flex-1"><span className="text-xs text-slate-600">Reward (MFB)</span>
              <input type="number" value={reward} onChange={(e) => setReward(+e.target.value)} className="w-full border rounded px-2 py-1.5 mt-1 text-sm" />
            </label>
            <label className="flex-1"><span className="text-xs text-slate-600">Duration (days)</span>
              <input type="number" value={days} onChange={(e) => setDays(+e.target.value)} className="w-full border rounded px-2 py-1.5 mt-1 text-sm" />
            </label>
          </div>
        </div>
        <button
          onClick={create}
          disabled={saving || !name || reward < 1}
          className="mt-4 w-full bg-amber-500 hover:bg-amber-600 disabled:bg-slate-300 text-white font-semibold py-2 rounded"
        >{saving ? "Creating…" : "Create Campaign (as draft)"}</button>
      </div>
    </div>
  );
}

// -------------------- Transactions --------------------
function TransactionsTab() {
  const [source, setSource] = useState("");
  const { data } = useQuery({
    queryKey: ["mfb-txs", source],
    queryFn: async () => (await api.get("/admin/mfb-rewards/transactions", { params: { source: source || undefined, limit: 200 } })).data,
    refetchInterval: 30000,
  });
  return (
    <div>
      <div className="mb-3 flex items-center gap-2">
        <label className="text-sm text-slate-600">Filter by source:</label>
        <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="e.g. signup, daily_login" className="border rounded px-2 py-1 text-sm" />
      </div>
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs text-left uppercase text-slate-600"><tr>
            <th className="px-3 py-2">Time</th><th>User</th><th>Source</th><th>Amount</th><th>Reason</th><th>Migration</th>
          </tr></thead>
          <tbody>
            {(data?.items || []).map((t: any) => (
              <tr key={t.tx_id} className="border-t border-slate-100">
                <td className="px-3 py-2 text-xs">{new Date(t.created_at).toLocaleString()}</td>
                <td className="font-mono text-xs">{t.user_id}</td>
                <td>{t.source}</td>
                <td className={`font-semibold ${t.amount >= 0 ? "text-emerald-600" : "text-rose-600"}`}>{t.amount >= 0 ? "+" : ""}{t.amount}</td>
                <td className="text-slate-700">{t.reason}</td>
                <td className="text-xs">
                  <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{t.migration_status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// -------------------- Leaderboards --------------------
function LeaderboardsTab() {
  const qc = useQueryClient();
  const [period, setPeriod] = useState<"weekly" | "monthly" | "all_time">("weekly");
  const [category, setCategory] = useState<"earners" | "referrers" | "investors" | "traders">("earners");
  const { data } = useQuery({
    queryKey: ["mfb-lb", period, category],
    queryFn: async () => (await api.get("/mfb-rewards/leaderboard", { params: { period, category } })).data,
  });
  const rebuild = useMutation({
    mutationFn: async () => api.post("/admin/mfb-rewards/leaderboards/rebuild"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mfb-lb"] }),
  });
  return (
    <div>
      <div className="flex gap-2 mb-3">
        {(["weekly", "monthly", "all_time"] as const).map((p) => (
          <button key={p} onClick={() => setPeriod(p)}
                  className={`px-3 py-1 text-xs font-semibold rounded ${period === p ? "bg-amber-500 text-white" : "bg-white border border-slate-200"}`}>{p}</button>
        ))}
        <span className="text-slate-300 mx-2">|</span>
        {(["earners", "referrers", "investors", "traders"] as const).map((c) => (
          <button key={c} onClick={() => setCategory(c)}
                  className={`px-3 py-1 text-xs font-semibold rounded ${category === c ? "bg-amber-500 text-white" : "bg-white border border-slate-200"}`}>{c}</button>
        ))}
        <button onClick={() => rebuild.mutate()} className="ml-auto flex items-center gap-1 text-xs text-slate-600 hover:text-slate-900">
          <RefreshCw className={`w-3 h-3 ${rebuild.isPending ? "animate-spin" : ""}`} /> Rebuild all
        </button>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-600"><tr><th className="px-3 py-2 text-left">Rank</th><th className="text-left">User</th><th>Value</th></tr></thead>
          <tbody>
            {(data?.entries || []).map((e: any) => (
              <tr key={e.user_id} className="border-t border-slate-100">
                <td className="px-3 py-2 font-bold text-amber-600">#{e.rank}</td>
                <td className="font-mono text-xs">{e.user_id}</td>
                <td className="font-semibold">{e.value.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// -------------------- Achievements --------------------
function AchievementsTab() {
  const { data } = useQuery({
    queryKey: ["mfb-ach"],
    queryFn: async () => (await api.get("/admin/mfb-rewards/achievements")).data,
  });
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
      {(data?.items || []).map((a: any) => (
        <div key={a.code} className="bg-white border border-slate-200 rounded-xl p-4 text-center">
          <div className="text-4xl">{a.emoji}</div>
          <div className="font-semibold text-slate-900 mt-2">{a.title}</div>
          <div className="text-xs text-slate-500 mt-1">Tier {a.tier}</div>
          <code className="text-[10px] text-slate-400 block mt-1">{a.code}</code>
        </div>
      ))}
    </div>
  );
}

// -------------------- Settings --------------------
function SettingsTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["mfb-settings"],
    queryFn: async () => (await api.get("/admin/mfb-rewards/settings")).data,
  });
  const upd = useMutation({
    mutationFn: async ({ key, value }: { key: string; value: any }) =>
      api.post("/admin/mfb-rewards/settings", { key, value }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mfb-settings"] }),
  });
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-xs uppercase text-slate-600"><tr>
          <th className="px-3 py-2 text-left">Key</th><th className="text-left">Value</th><th className="text-left">Updated By</th><th></th>
        </tr></thead>
        <tbody>
          {(data?.items || []).map((s: any) => (
            <SettingRow key={s.key} s={s} onSave={(v) => upd.mutate({ key: s.key, value: v })} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SettingRow({ s, onSave }: { s: any; onSave: (v: any) => void }) {
  const [txt, setTxt] = useState(JSON.stringify(s.value));
  const [editing, setEditing] = useState(false);
  return (
    <tr className="border-t border-slate-100">
      <td className="px-3 py-2 font-mono text-xs">{s.key}</td>
      <td>
        {editing ? (
          <input value={txt} onChange={(e) => setTxt(e.target.value)} className="w-full border rounded px-2 py-1 text-xs font-mono" />
        ) : (
          <code className="text-xs">{JSON.stringify(s.value)}</code>
        )}
      </td>
      <td className="text-xs text-slate-500">{s.updated_by}</td>
      <td className="text-right pr-3">
        {editing ? (
          <>
            <button onClick={() => { try { onSave(JSON.parse(txt)); setEditing(false); } catch { alert("Invalid JSON"); } }}
                    className="text-xs bg-emerald-500 text-white px-2 py-0.5 rounded mr-1">Save</button>
            <button onClick={() => { setEditing(false); setTxt(JSON.stringify(s.value)); }}
                    className="text-xs text-slate-500">Cancel</button>
          </>
        ) : (
          <button onClick={() => setEditing(true)} className="text-xs text-amber-600 hover:underline">Edit</button>
        )}
      </td>
    </tr>
  );
}

// -------------------- Analytics --------------------
function AnalyticsTab() {
  const { data: daily } = useQuery({
    queryKey: ["mfb-daily"],
    queryFn: async () => (await api.get("/admin/mfb-rewards/analytics/daily", { params: { days: 30 } })).data,
  });
  const { data: dist } = useQuery({
    queryKey: ["mfb-dist"],
    queryFn: async () => (await api.get("/admin/mfb-rewards/analytics/distribution")).data,
  });
  const distItems = (dist?.items || []).slice(0, 8);
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <div className="bg-white border border-slate-200 rounded-xl p-4">
        <div className="font-semibold text-slate-800 mb-2">MFB issued per day (30d)</div>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={daily?.items || []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" fontSize={10} />
            <YAxis fontSize={10} />
            <Tooltip />
            <Line type="monotone" dataKey="issued" stroke="#F59E0B" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl p-4">
        <div className="font-semibold text-slate-800 mb-2">Distribution by source</div>
        <ResponsiveContainer width="100%" height={260}>
          <PieChart>
            <Pie data={distItems} dataKey="total" nameKey="source" outerRadius={100}
                 label={(e) => e.source}>
              {distItems.map((_: any, i: number) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl p-4 lg:col-span-2">
        <div className="font-semibold text-slate-800 mb-2">TX count per day</div>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={daily?.items || []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
            <XAxis dataKey="date" fontSize={10} />
            <YAxis fontSize={10} />
            <Tooltip />
            <Legend />
            <Bar dataKey="count" fill="#3B82F6" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtCurrency } from "../lib/api";
import {
  Trophy, Gift, Users, IndianRupee, RefreshCw, Sparkles, Crown, Plus,
  TrendingUp, Search,
} from "lucide-react";

type Summary = {
  total_points_in_circulation: number;
  total_cashback_paid: number;
  cashback_count: number;
  top_referrers: { full_name?: string; referral_code?: string; count?: number; reward_points?: number }[];
  tiers: { id: string; name: string; min: number; rate: number; color: string }[];
};

export default function AdminRewards() {
  const qc = useQueryClient();
  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["admin-rewards-summary"],
    queryFn: async () => (await api.get<Summary>("/admin/super/rewards-summary")).data,
  });

  const [userId, setUserId] = useState("");
  const [points, setPoints] = useState("");
  const [cashback, setCashback] = useState("");
  const [note, setNote] = useState("Admin bonus");
  const [searchUsr, setSearchUsr] = useState("");
  const [userResults, setUserResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);

  const grant = useMutation({
    mutationFn: async () => (await api.post("/admin/super/grant-bonus", {
      user_id: userId,
      points: Number(points) || 0,
      cashback: Number(cashback) || 0,
      note,
    })).data,
    onSuccess: () => {
      setUserId(""); setPoints(""); setCashback(""); setNote("Admin bonus");
      qc.invalidateQueries({ queryKey: ["admin-rewards-summary"] });
    },
  });

  const findUser = async () => {
    if (!searchUsr) return;
    setSearching(true);
    try {
      const { data } = await api.get("/admin/users", { params: { search: searchUsr, limit: 10 } });
      setUserResults((data?.items || data) as any[]);
    } finally { setSearching(false); }
  };

  const tiers = data?.tiers || [];
  const maxTierUsers = useMemo(() => Math.max(1, ...(data?.top_referrers || []).map((r) => r.count || 0)), [data]);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2">
            <Trophy className="w-6 h-6" /> Rewards &amp; Referral
          </h2>
          <p className="text-sm text-slate-500 mt-1">Loyalty tiers, cashback distribution and referrer leaderboard.</p>
        </div>
        <button onClick={() => refetch()} className="btn-ghost gap-2 text-sm">
          <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      {/* Stats */}
      <div className="grid sm:grid-cols-3 gap-3">
        <Stat label="Points in circulation" value={(data?.total_points_in_circulation || 0).toLocaleString()} cls="from-violet-500 to-fuchsia-600" Icon={Sparkles} />
        <Stat label="Total cashback paid" value={fmtCurrency(data?.total_cashback_paid || 0)} cls="from-emerald-500 to-emerald-600" Icon={IndianRupee} />
        <Stat label="Cashback transactions" value={data?.cashback_count || 0} cls="from-sky-500 to-blue-600" Icon={Gift} />
      </div>

      {/* Loyalty tiers */}
      <div className="card">
        <h3 className="font-extrabold text-brand-navy mb-3 flex items-center gap-2"><Crown className="w-5 h-5 text-amber-500" />Loyalty tiers</h3>
        <div className="grid sm:grid-cols-5 gap-3">
          {tiers.map((t) => (
            <div key={t.id} className="rounded-xl p-3 text-white" style={{ background: `linear-gradient(135deg, ${t.color}, ${t.color}aa)` }}>
              <p className="font-extrabold">{t.name}</p>
              <p className="text-xs opacity-90">≥ {t.min.toLocaleString()} pts</p>
              <p className="text-xs opacity-90 mt-1">{(t.rate * 100).toFixed(2)}% cashback</p>
            </div>
          ))}
        </div>
      </div>

      {/* Leaderboard */}
      <div className="card">
        <h3 className="font-extrabold text-brand-navy mb-3 flex items-center gap-2"><TrendingUp className="w-5 h-5 text-brand-primary" />Top referrers</h3>
        {(data?.top_referrers || []).length === 0 ? (
          <p className="text-sm text-slate-400 py-6 text-center">No referrals yet.</p>
        ) : (
          <div className="space-y-2">
            {(data?.top_referrers || []).map((r, i) => {
              const width = ((r.count || 0) / maxTierUsers) * 100;
              return (
                <div key={r.referral_code || i} className="flex items-center gap-3">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-amber-400 to-orange-500 text-white flex items-center justify-center font-extrabold text-sm shrink-0">{i + 1}</div>
                  <div className="flex-1 min-w-0">
                    <p className="font-bold text-slate-800 truncate">{r.full_name || "User"} <span className="text-slate-400 text-xs font-mono">({r.referral_code || "-"})</span></p>
                    <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden mt-1">
                      <div className="h-full bg-gradient-to-r from-amber-400 to-orange-500" style={{ width: `${width}%` }} />
                    </div>
                  </div>
                  <div className="text-right">
                    <p className="font-extrabold text-brand-navy">{r.count || 0} <span className="text-xs text-slate-500">refs</span></p>
                    <p className="text-xs text-slate-500">{(r.reward_points || 0).toLocaleString()} pts</p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Grant bonus */}
      <div className="card">
        <h3 className="font-extrabold text-brand-navy mb-3 flex items-center gap-2"><Plus className="w-5 h-5 text-emerald-500" />Grant bonus to user</h3>
        <div className="flex flex-col sm:flex-row gap-3 mb-3">
          <div className="flex items-center gap-2 flex-1">
            <Search className="w-4 h-4 text-slate-400" />
            <input className="input" placeholder="Search user by name or email" value={searchUsr} onChange={(e) => setSearchUsr(e.target.value)} onKeyDown={(e) => e.key === "Enter" && findUser()} />
          </div>
          <button onClick={findUser} disabled={searching} className="btn-ghost text-sm">{searching ? "Searching…" : "Find user"}</button>
        </div>
        {userResults.length > 0 ? (
          <div className="flex flex-wrap gap-2 mb-3">
            {userResults.slice(0, 6).map((u: any) => (
              <button key={u.user_id} onClick={() => { setUserId(u.user_id); setUserResults([]); }} className="badge bg-slate-100 hover:bg-slate-200 text-slate-700">
                {u.full_name || u.email} · <span className="font-mono">{u.user_id.slice(0,10)}…</span>
              </button>
            ))}
          </div>
        ) : null}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <input className="input" placeholder="user_id" value={userId} onChange={(e) => setUserId(e.target.value)} />
          <input className="input" type="number" placeholder="Points" value={points} onChange={(e) => setPoints(e.target.value)} />
          <input className="input" type="number" step="0.01" placeholder="Cashback (₹)" value={cashback} onChange={(e) => setCashback(e.target.value)} />
          <input className="input" placeholder="Note" value={note} onChange={(e) => setNote(e.target.value)} />
        </div>
        <div className="flex items-center justify-end gap-2 mt-3">
          {grant.isSuccess ? <span className="text-emerald-600 text-sm font-bold">✓ Bonus granted</span> : null}
          {grant.isError ? <span className="text-red-600 text-sm">Failed</span> : null}
          <button
            onClick={() => grant.mutate()}
            disabled={!userId || grant.isPending || (Number(points) === 0 && Number(cashback) === 0)}
            className="btn-primary text-sm gap-2"
          >
            <Users className="w-4 h-4" />{grant.isPending ? "Granting…" : "Grant Bonus"}
          </button>
        </div>
      </div>

      {isLoading ? <p className="text-slate-400 text-center">Loading rewards…</p> : null}
    </div>
  );
}

function Stat({ label, value, cls, Icon }: { label: string; value: any; cls: string; Icon: any }) {
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

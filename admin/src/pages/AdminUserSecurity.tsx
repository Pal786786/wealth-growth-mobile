import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import { ShieldCheck, ShieldOff, KeyRound, Lock, Unlock, RefreshCw, Search, AlertTriangle, CheckCircle2 } from "lucide-react";

type U = {
  user_id: string; full_name?: string; email?: string; mobile?: string;
  password_set: boolean; password_updated_at?: string; login_method: string;
  failed_logins?: number; last_login_at?: string; disabled?: boolean;
  locked_until?: string; force_password_reset?: boolean; kyc_status?: string;
};

export default function AdminUserSecurity() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["user-security", search],
    queryFn: async () => (await api.get("/admin/users-security", { params: { search: search || undefined, limit: 200 } })).data as { items: U[]; total: number },
  });

  const act = useMutation({
    mutationFn: async ({ user_id, action }: { user_id: string; action: string }) =>
      (await api.post(`/admin/users/${user_id}/security-action`, { action })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["user-security"] }),
  });

  const stats = useMemo(() => {
    const items = data?.items || [];
    return {
      total: items.length,
      noPassword: items.filter((u) => !u.password_set).length,
      disabled: items.filter((u) => u.disabled).length,
      forceReset: items.filter((u) => u.force_password_reset).length,
    };
  }, [data]);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2"><ShieldCheck className="w-6 h-6" /> User Security</h2>
          <p className="text-sm text-slate-500 mt-1">Manage account security. Passwords are stored bcrypt-hashed and never visible here.</p>
        </div>
        <button onClick={() => refetch()} className="btn-ghost gap-2 text-sm"><RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh</button>
      </div>

      <div className="grid sm:grid-cols-4 gap-3">
        <Stat label="Total users" value={stats.total} cls="from-sky-500 to-blue-600" Icon={ShieldCheck} />
        <Stat label="No password set" value={stats.noPassword} cls="from-amber-500 to-orange-600" Icon={KeyRound} />
        <Stat label="Disabled" value={stats.disabled} cls="from-red-500 to-rose-600" Icon={ShieldOff} />
        <Stat label="Force reset" value={stats.forceReset} cls="from-violet-500 to-fuchsia-600" Icon={AlertTriangle} />
      </div>

      <div className="card bg-slate-50 border border-slate-200 flex items-start gap-3">
        <Lock className="w-5 h-5 text-slate-600 mt-0.5" />
        <div className="text-sm text-slate-700">
          <p className="font-bold">Security guarantee</p>
          <p>Passwords are bcrypt-hashed on creation. Admins can <b>force a reset</b>, <b>disable login</b> or <b>unlock</b> accounts — but never see the actual password.</p>
        </div>
      </div>

      <div className="card flex items-center gap-2">
        <Search className="w-4 h-4 text-slate-400" />
        <input className="input" placeholder="Search by name, email, mobile…" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      <div className="card overflow-hidden">
        {isLoading ? <div className="text-slate-400 py-8 text-center">Loading…</div> : null}
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500 uppercase font-bold border-b border-slate-200">
                <th className="py-2 px-1">User</th>
                <th className="py-2 px-1">Login Method</th>
                <th className="py-2 px-1">Password</th>
                <th className="py-2 px-1">Failed Logins</th>
                <th className="py-2 px-1">Last Login</th>
                <th className="py-2 px-1">Status</th>
                <th className="py-2 px-1 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((u) => (
                <tr key={u.user_id} className="border-b border-slate-100 hover:bg-slate-50">
                  <td className="py-2 px-1">
                    <p className="font-bold text-slate-800">{u.full_name || "—"}</p>
                    <p className="text-xs text-slate-500">{u.email || u.mobile || u.user_id.slice(0, 12) + "…"}</p>
                  </td>
                  <td className="py-2 px-1"><span className="badge bg-slate-100 text-slate-700 capitalize">{u.login_method}</span></td>
                  <td className="py-2 px-1">
                    {u.password_set ? <span className="badge bg-emerald-50 text-emerald-700 border border-emerald-200"><CheckCircle2 className="w-3 h-3 inline mr-1" />Set</span> :
                      <span className="badge bg-amber-50 text-amber-700 border border-amber-200">Not set</span>}
                    {u.password_updated_at ? <p className="text-[10px] text-slate-400 mt-0.5">{fmtDate(u.password_updated_at)}</p> : null}
                  </td>
                  <td className="py-2 px-1">
                    <span className={`font-bold ${(u.failed_logins || 0) >= 3 ? "text-red-600" : "text-slate-700"}`}>{u.failed_logins || 0}</span>
                  </td>
                  <td className="py-2 px-1 text-xs text-slate-500">{u.last_login_at ? fmtDate(u.last_login_at) : "—"}</td>
                  <td className="py-2 px-1">
                    {u.disabled ? <span className="badge bg-red-50 text-red-700 border border-red-200">Disabled</span> :
                     u.force_password_reset ? <span className="badge bg-amber-50 text-amber-700 border border-amber-200">Reset required</span> :
                     u.locked_until ? <span className="badge bg-amber-50 text-amber-700 border border-amber-200">Locked</span> :
                     <span className="badge bg-emerald-50 text-emerald-700 border border-emerald-200">Active</span>}
                  </td>
                  <td className="py-2 px-1 text-right">
                    <div className="flex gap-1 justify-end flex-wrap">
                      {!u.force_password_reset ? (
                        <button onClick={() => act.mutate({ user_id: u.user_id, action: "force_reset" })} className="text-xs px-2 py-1 rounded bg-amber-100 text-amber-800 hover:bg-amber-200 font-bold">Force Reset</button>
                      ) : null}
                      {u.disabled ? (
                        <button onClick={() => act.mutate({ user_id: u.user_id, action: "enable_login" })} className="text-xs px-2 py-1 rounded bg-emerald-100 text-emerald-800 hover:bg-emerald-200 font-bold">Enable</button>
                      ) : (
                        <button onClick={() => act.mutate({ user_id: u.user_id, action: "disable_login" })} className="text-xs px-2 py-1 rounded bg-red-100 text-red-800 hover:bg-red-200 font-bold">Disable</button>
                      )}
                      {(u.locked_until || (u.failed_logins || 0) >= 3) ? (
                        <button onClick={() => act.mutate({ user_id: u.user_id, action: "unlock" })} className="text-xs px-2 py-1 rounded bg-sky-100 text-sky-800 hover:bg-sky-200 font-bold inline-flex items-center gap-1"><Unlock className="w-3 h-3" />Unlock</button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
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

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, inr, fmtDate } from "../lib/api";
import { Search, ShieldOff, ShieldCheck, RotateCcw } from "lucide-react";

export default function Users() {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState<"all" | "suspended" | "active">("all");
  const qc = useQueryClient();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["admin-users", q, filter],
    queryFn: async () => {
      const params: any = { q, limit: 100 };
      if (filter === "suspended") params.suspended = true;
      if (filter === "active") params.suspended = false;
      return (await api.get("/admin/users", { params })).data as { items: any[]; total: number };
    },
  });

  const actionMut = useMutation({
    mutationFn: ({ user_id, action }: { user_id: string; action: "suspend" | "activate" }) =>
      api.post(`/admin/users/${user_id}/action`, { action }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-users"] }); refetch(); },
  });

  // Sprint 15.1 — Demo Account Reset (demo trading wallet only; real wallet untouched)
  const demoResetMut = useMutation({
    mutationFn: (user_id: string) => api.post(`/admin/demo/reset/${user_id}`),
    onSuccess: (res) => {
      const d = res.data;
      window.alert(
        `Demo account reset ✓\n\nPrevious balance: ₹${Number(d.previous_balance).toLocaleString("en-IN")}\nNew balance: ₹${Number(d.new_balance).toLocaleString("en-IN")}\nPositions closed: ${d.positions_closed}\nCopied trades closed: ${d.copy_trades_closed}\n\nReal wallet was NOT affected.`
      );
    },
    onError: (e: any) => window.alert(e?.response?.data?.detail || "Demo reset failed"),
  });

  const handleDemoReset = (u: any) => {
    if (!window.confirm(
      `Reset DEMO account for ${u.full_name}?\n\nThis closes all open demo positions, cancels pending demo orders, archives demo history and restores the default demo balance.\n\nThe user's REAL wallet is never affected.`
    )) return;
    demoResetMut.mutate(u.user_id);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy">Users</h2>
          <p className="text-sm text-slate-500">{data?.total ?? "—"} total · Manage all customers.</p>
        </div>
      </div>

      <div className="card">
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <div className="relative flex-1 min-w-[260px]">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input className="input pl-10" placeholder="Search by name, email, mobile, user_id…" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="flex bg-slate-100 rounded-xl p-1">
            {(["all", "active", "suspended"] as const).map((f) => (
              <button key={f} onClick={() => setFilter(f)} className={`px-3 py-1.5 rounded-lg text-sm font-semibold capitalize ${filter === f ? "bg-white shadow text-brand-navy" : "text-slate-500"}`}>
                {f}
              </button>
            ))}
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs font-bold text-slate-500 uppercase tracking-wide">
              <tr className="border-b border-slate-200">
                <th className="py-3 pr-4">Customer</th>
                <th className="py-3 pr-4">Mobile</th>
                <th className="py-3 pr-4">Wallet</th>
                <th className="py-3 pr-4">KYC</th>
                <th className="py-3 pr-4">Status</th>
                <th className="py-3 pr-4">Joined</th>
                <th className="py-3 pr-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr><td colSpan={7} className="py-6 text-center text-slate-400">Loading…</td></tr>
              ) : data?.items.length === 0 ? (
                <tr><td colSpan={7} className="py-6 text-center text-slate-400">No users found</td></tr>
              ) : data?.items.map((u) => (
                <tr key={u.user_id} className="border-b border-slate-100 hover:bg-slate-50/60">
                  <td className="py-3 pr-4">
                    <p className="font-bold text-slate-900">{u.full_name}</p>
                    <p className="text-xs text-slate-500">{u.email}</p>
                  </td>
                  <td className="py-3 pr-4 text-slate-700">+91 {u.mobile}</td>
                  <td className="py-3 pr-4 font-bold text-slate-900">{inr(u.wallet_balance)}</td>
                  <td className="py-3 pr-4">
                    {u.kyc_status === "verified" ? <span className="badge badge-ok">verified</span>
                      : u.kyc_status === "rejected" ? <span className="badge badge-bad">rejected</span>
                      : <span className="badge badge-warn">pending</span>}
                  </td>
                  <td className="py-3 pr-4">
                    {u.suspended ? <span className="badge badge-bad">suspended</span> : <span className="badge badge-info">active</span>}
                  </td>
                  <td className="py-3 pr-4 text-xs text-slate-500">{fmtDate(u.created_at)}</td>
                  <td className="py-3 pr-4 text-right">
                    <div className="flex justify-end gap-2">
                      <button onClick={() => handleDemoReset(u)} disabled={demoResetMut.isPending}
                        title="Reset demo trading account (real wallet untouched)"
                        className="btn-ghost !py-1.5 !px-3 !text-xs gap-1 !text-amber-600 !border-amber-200 hover:!bg-amber-50">
                        <RotateCcw className="w-3.5 h-3.5" /> Reset Demo
                      </button>
                      {u.suspended ? (
                        <button onClick={() => actionMut.mutate({ user_id: u.user_id, action: "activate" })} className="btn-ghost !py-1.5 !px-3 !text-xs gap-1">
                          <ShieldCheck className="w-3.5 h-3.5" /> Activate
                        </button>
                      ) : (
                        <button onClick={() => actionMut.mutate({ user_id: u.user_id, action: "suspend" })} className="btn-ghost !py-1.5 !px-3 !text-xs gap-1 !text-red-600 !border-red-200 hover:!bg-red-50">
                          <ShieldOff className="w-3.5 h-3.5" /> Suspend
                        </button>
                      )}
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

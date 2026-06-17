import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import { useAdminAuth } from "../lib/auth";
import { Plus, Trash2, UserPlus, ShieldAlert, ShieldCheck } from "lucide-react";

export default function AdminUsers() {
  const qc = useQueryClient();
  const { admin: me } = useAdminAuth();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "support_manager" });
  const [err, setErr] = useState("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["admin-admins"],
    queryFn: async () => (await api.get("/admin/admins")).data as { items: any[]; roles: { id: string; label: string }[] },
    retry: false,
  });

  const create = useMutation({
    mutationFn: () => api.post("/admin/admins", form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-admins"] });
      setShowForm(false); setForm({ name: "", email: "", password: "", role: "support_manager" }); setErr("");
    },
    onError: (e: any) => setErr(e?.response?.data?.detail || "Failed"),
  });

  const del = useMutation({
    mutationFn: (id: string) => api.delete(`/admin/admins/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-admins"] }),
  });

  if (error && (error as any)?.response?.status === 403) {
    return (
      <div className="card flex items-center gap-3 max-w-xl">
        <ShieldAlert className="w-8 h-8 text-amber-500" />
        <div>
          <p className="font-extrabold text-slate-900">Super-admin only</p>
          <p className="text-sm text-slate-500">You don't have permission to manage admin users. Ask a super_admin to invite you.</p>
        </div>
      </div>
    );
  }

  const roleBadge = (r: string) => {
    if (r === "super_admin") return <span className="badge badge-bad">{r}</span>;
    if (r === "admin") return <span className="badge badge-info">{r}</span>;
    return <span className="badge badge-warn">{r.replace("_", " ")}</span>;
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-end flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy">Admin Users</h2>
          <p className="text-sm text-slate-500">Invite Finance, Support, and Investment managers with restricted roles.</p>
        </div>
        <button onClick={() => setShowForm((v) => !v)} className="btn-primary gap-2">
          <UserPlus className="w-4 h-4" /> {showForm ? "Cancel" : "Invite admin"}
        </button>
      </div>

      {showForm ? (
        <div className="card space-y-3 max-w-2xl">
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Name</label>
              <input className="input mt-1" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Email</label>
              <input className="input mt-1" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Temporary Password</label>
              <input className="input mt-1" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="min 8 chars" />
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Role</label>
              <select className="input mt-1" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                {data?.roles.map((r) => (
                  <option key={r.id} value={r.id}>{r.label}</option>
                ))}
              </select>
            </div>
          </div>
          {err ? <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{err}</p> : null}
          <button onClick={() => create.mutate()} disabled={!form.name || !form.email || !form.password || create.isPending} className="btn-primary gap-2">
            <Plus className="w-4 h-4" /> {create.isPending ? "Creating…" : "Create admin"}
          </button>
        </div>
      ) : null}

      <div className="card">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs font-bold text-slate-500 uppercase tracking-wide">
              <tr className="border-b border-slate-200">
                <th className="py-3 pr-4">Name</th>
                <th className="py-3 pr-4">Email</th>
                <th className="py-3 pr-4">Role</th>
                <th className="py-3 pr-4">Joined</th>
                <th className="py-3 pr-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? <tr><td colSpan={5} className="py-6 text-center text-slate-400">Loading…</td></tr> :
                data?.items.map((a) => (
                  <tr key={a.admin_id} className="border-b border-slate-100 hover:bg-slate-50/60">
                    <td className="py-3 pr-4">
                      <div className="flex items-center gap-2">
                        <p className="font-bold text-slate-900">{a.name}</p>
                        {a.admin_id === me?.admin_id ? <span className="badge badge-ok">you</span> : null}
                      </div>
                    </td>
                    <td className="py-3 pr-4 text-slate-700">{a.email}</td>
                    <td className="py-3 pr-4">{roleBadge(a.role)}</td>
                    <td className="py-3 pr-4 text-xs text-slate-500">{fmtDate(a.created_at)}</td>
                    <td className="py-3 pr-4 text-right">
                      {a.admin_id === me?.admin_id ? (
                        <span className="inline-flex items-center gap-1 text-xs text-emerald-600 font-semibold"><ShieldCheck className="w-3.5 h-3.5" /> current</span>
                      ) : (
                        <button onClick={() => del.mutate(a.admin_id)} className="btn-ghost !py-1.5 !px-3 !text-xs gap-1 !text-red-600 !border-red-200 hover:!bg-red-50">
                          <Trash2 className="w-3.5 h-3.5" /> Delete
                        </button>
                      )}
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

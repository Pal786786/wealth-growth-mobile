import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import { CheckCircle2, XCircle, FileCheck2 } from "lucide-react";
import { useState } from "react";

export default function KYC() {
  const qc = useQueryClient();
  const [notes, setNotes] = useState<Record<string, string>>({});

  const { data, isLoading } = useQuery({
    queryKey: ["admin-kyc-pending"],
    queryFn: async () => (await api.get("/admin/kyc/pending")).data as any[],
  });

  const mut = useMutation({
    mutationFn: (p: { user_id: string; action: "approve" | "reject"; note?: string }) =>
      api.post("/admin/kyc/action", p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-kyc-pending"] }),
  });

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-extrabold text-brand-navy">KYC Review Queue</h2>
        <p className="text-sm text-slate-500">{data?.length ?? "—"} pending verification</p>
      </div>

      {isLoading ? (
        <div className="card text-slate-500">Loading…</div>
      ) : data?.length === 0 ? (
        <div className="card text-center py-12">
          <FileCheck2 className="w-12 h-12 mx-auto text-emerald-500 mb-3" />
          <p className="font-bold text-slate-900">All caught up!</p>
          <p className="text-sm text-slate-500">No pending KYC submissions.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {data?.map((u) => (
            <div key={u.user_id} className="card flex flex-col lg:flex-row lg:items-center gap-4">
              <div className="flex-1">
                <p className="font-bold text-slate-900">{u.full_name}</p>
                <p className="text-sm text-slate-500">{u.email} · +91 {u.mobile}</p>
                <p className="text-xs text-slate-400 mt-1">Submitted {fmtDate(u.created_at)}</p>
              </div>
              <input
                className="input lg:w-64"
                placeholder="Verification note (optional)"
                value={notes[u.user_id] || ""}
                onChange={(e) => setNotes((p) => ({ ...p, [u.user_id]: e.target.value }))}
              />
              <div className="flex gap-2">
                <button onClick={() => mut.mutate({ user_id: u.user_id, action: "approve", note: notes[u.user_id] })} className="btn-primary !py-2 gap-1">
                  <CheckCircle2 className="w-4 h-4" /> Approve
                </button>
                <button onClick={() => mut.mutate({ user_id: u.user_id, action: "reject", note: notes[u.user_id] })} className="btn-ghost !py-2 gap-1 !text-red-600 !border-red-200 hover:!bg-red-50">
                  <XCircle className="w-4 h-4" /> Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

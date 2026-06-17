import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, inr } from "../lib/api";
import { Plus, Minus, AlertCircle, CheckCircle2 } from "lucide-react";

export default function Wallet() {
  const [userId, setUserId] = useState("");
  const [amount, setAmount] = useState("");
  const [type, setType] = useState<"credit" | "debit">("credit");
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState<{ kind: "ok" | "bad"; text: string } | null>(null);
  const qc = useQueryClient();

  const { data: usersData } = useQuery({
    queryKey: ["admin-users-pick"],
    queryFn: async () => (await api.get("/admin/users", { params: { limit: 200 } })).data as { items: any[]; total: number },
  });

  const mut = useMutation({
    mutationFn: () => api.post("/admin/wallet/adjust", { user_id: userId, amount: parseFloat(amount), type, note }),
    onSuccess: (r) => {
      setMsg({ kind: "ok", text: `Done · New balance: ${inr(r.data.new_balance)}` });
      setAmount(""); setNote("");
      qc.invalidateQueries({ queryKey: ["admin-users-pick"] });
      qc.invalidateQueries({ queryKey: ["admin-tx"] });
    },
    onError: (e: any) => setMsg({ kind: "bad", text: e?.response?.data?.detail || "Failed" }),
  });

  const selected = usersData?.items.find((u) => u.user_id === userId);

  return (
    <div className="space-y-4 max-w-2xl">
      <div>
        <h2 className="text-2xl font-extrabold text-brand-navy">Wallet Adjust</h2>
        <p className="text-sm text-slate-500">Credit or debit a user's wallet. All actions are audit-logged.</p>
      </div>

      <div className="card space-y-4">
        <div>
          <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Select User</label>
          <select className="input mt-1" value={userId} onChange={(e) => { setUserId(e.target.value); setMsg(null); }}>
            <option value="">— pick a user —</option>
            {usersData?.items.map((u) => (
              <option key={u.user_id} value={u.user_id}>
                {u.full_name} · {u.email} · {inr(u.wallet_balance)}
              </option>
            ))}
          </select>
        </div>

        {selected ? (
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-sm">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-bold text-slate-900">{selected.full_name}</p>
                <p className="text-xs text-slate-500">{selected.user_id}</p>
              </div>
              <p className="text-xl font-extrabold text-brand-navy">{inr(selected.wallet_balance)}</p>
            </div>
          </div>
        ) : null}

        <div>
          <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Action</label>
          <div className="flex bg-slate-100 rounded-xl p-1 mt-1 w-fit">
            <button onClick={() => setType("credit")} className={`px-4 py-2 rounded-lg text-sm font-semibold inline-flex items-center gap-2 ${type === "credit" ? "bg-emerald-500 text-white shadow" : "text-slate-600"}`}>
              <Plus className="w-4 h-4" /> Credit
            </button>
            <button onClick={() => setType("debit")} className={`px-4 py-2 rounded-lg text-sm font-semibold inline-flex items-center gap-2 ${type === "debit" ? "bg-red-500 text-white shadow" : "text-slate-600"}`}>
              <Minus className="w-4 h-4" /> Debit
            </button>
          </div>
        </div>

        <div>
          <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Amount (₹)</label>
          <input type="number" min="1" step="0.01" className="input mt-1" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Reason / Note</label>
          <input className="input mt-1" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Goodwill credit, refund, dispute resolution…" />
        </div>

        {msg ? (
          <div className={`flex items-center gap-2 text-sm px-3 py-2 rounded-lg border ${msg.kind === "ok" ? "bg-emerald-50 text-emerald-700 border-emerald-200" : "bg-red-50 text-red-700 border-red-200"}`}>
            {msg.kind === "ok" ? <CheckCircle2 className="w-4 h-4" /> : <AlertCircle className="w-4 h-4" />}
            {msg.text}
          </div>
        ) : null}

        <button
          disabled={!userId || !amount || mut.isPending}
          onClick={() => mut.mutate()}
          className="btn-primary w-full disabled:opacity-50"
        >
          {mut.isPending ? "Processing…" : `${type === "credit" ? "Credit" : "Debit"} wallet`}
        </button>
      </div>
    </div>
  );
}

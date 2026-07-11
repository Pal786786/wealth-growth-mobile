/**
 * Admin — Payments (Sprint 8)
 * 6 tabs: Overview · Orders · Transactions · Refunds · Reconciliation · Audit · Config
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import {
  Activity, ShoppingBag, CreditCard, Undo2, RefreshCw, ScrollText, Settings, Zap,
  TrendingUp, AlertTriangle, CheckCircle2, XCircle, PlayCircle,
} from "lucide-react";

type Tab = "overview" | "orders" | "transactions" | "refunds" | "reconcile" | "audit" | "config";
const TABS: { id: Tab; label: string; icon: any }[] = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "orders", label: "Orders", icon: ShoppingBag },
  { id: "transactions", label: "Transactions", icon: CreditCard },
  { id: "refunds", label: "Refunds", icon: Undo2 },
  { id: "reconcile", label: "Reconciliation", icon: RefreshCw },
  { id: "audit", label: "Audit Log", icon: ScrollText },
  { id: "config", label: "Config", icon: Settings },
];

function paiseToInr(p: number | undefined | null) {
  if (p == null) return "—";
  return "₹" + (p / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

export default function AdminPayments() {
  const [tab, setTab] = useState<Tab>("overview");
  return (
    <div className="p-6">
      <div className="flex items-center gap-3 mb-4">
        <CreditCard className="w-6 h-6 text-brand-navy" />
        <h1 className="text-2xl font-black text-brand-navy">Payments</h1>
        <span className="text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded bg-brand-navy text-white">Sprint 8 · Razorpay</span>
      </div>
      <div className="flex flex-wrap gap-2 mb-4 border-b border-slate-200 pb-2">
        {TABS.map((t) => {
          const I = t.icon;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold transition ${tab === t.id ? "bg-brand-navy text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"}`}>
              <I className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>
      {tab === "overview" && <OverviewTab />}
      {tab === "orders" && <OrdersTab />}
      {tab === "transactions" && <TxTab />}
      {tab === "refunds" && <RefundsTab />}
      {tab === "reconcile" && <ReconcileTab />}
      {tab === "audit" && <AuditTab />}
      {tab === "config" && <ConfigTab />}
    </div>
  );
}

function OverviewTab() {
  const { data, refetch } = useQuery({
    queryKey: ["adm_payments_dashboard"],
    queryFn: async () => (await api.get("/admin/payments/dashboard")).data,
    refetchInterval: 15000,
  });
  if (!data) return <div className="p-8 text-center text-slate-400">Loading…</div>;
  const cfg = data.config;
  return (
    <div className="space-y-4">
      <div className={`p-4 rounded-xl border-2 ${cfg.demo_mode ? "border-amber-200 bg-amber-50" : "border-emerald-200 bg-emerald-50"}`}>
        <div className="flex items-center gap-3">
          <div className="text-3xl">{cfg.demo_mode ? "🧪" : "🟢"}</div>
          <div>
            <div className="text-[10px] font-bold uppercase tracking-widest opacity-70">Current Mode</div>
            <div className="text-xl font-black">
              {cfg.demo_mode ? "DEMO MODE" : `LIVE — ${cfg.mode.toUpperCase()}`}
            </div>
            <div className="text-xs opacity-80 mt-1">
              {cfg.demo_mode
                ? "Wallet credits simulated locally. Toggle in Config tab to enable Razorpay."
                : `Provider configured with key ${cfg.key_id_public} · webhooks ${cfg.has_webhook_secret ? "enabled" : "MISSING"}`}
            </div>
          </div>
          <button onClick={() => refetch()} className="ml-auto text-slate-600 hover:text-slate-800"><RefreshCw className="w-4 h-4" /></button>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <StatCard label="Gross 24h" value={paiseToInr(data.gross_24h_paise)} sub={`${data.gross_24h_count} payments`} tint="emerald" />
        <StatCard label="Gross 7d" value={paiseToInr(data.gross_7d_paise)} sub={`${data.gross_7d_count} payments`} tint="blue" />
        <StatCard label="Refunds 24h" value={paiseToInr(data.refunds_24h_paise)} sub={`${data.refunds_24h_count} refunds`} tint="amber" />
        <StatCard label="Failed / Pending" value={`${data.failed_orders_24h} · ${data.pending_orders}`} sub="24h failed · pending" tint={data.failed_orders_24h > 5 ? "red" : "slate"} />
      </div>
      <div className="p-4 bg-white border border-slate-200 rounded-xl">
        <div className="text-xs font-bold text-slate-700 mb-2">METHOD MIX · 7 DAYS</div>
        {data.method_mix.length === 0 ? (
          <div className="text-xs text-slate-400 py-4 text-center">No transactions yet</div>
        ) : (
          <div className="space-y-1">
            {data.method_mix.map((m: any) => (
              <div key={m.method} className="flex items-center gap-3">
                <span className="text-xs font-bold uppercase w-24 text-slate-600">{m.method}</span>
                <span className="text-xs text-slate-500 w-14">{m.count}×</span>
                <div className="flex-1 h-2 bg-slate-100 rounded">
                  <div className="h-2 bg-emerald-500 rounded" style={{ width: `${Math.min(100, (m.sum_paise / (data.method_mix[0].sum_paise || 1)) * 100)}%` }} />
                </div>
                <span className="text-xs font-bold w-24 text-right">{paiseToInr(m.sum_paise)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function OrdersTab() {
  const [status, setStatus] = useState<string>("");
  const [detailId, setDetailId] = useState<string | null>(null);
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["adm_payments_orders", status],
    queryFn: async () => (await api.get("/admin/payments/orders", { params: { status: status || undefined, limit: 100 } })).data,
    refetchInterval: 10000,
  });
  const retryMut = useMutation({
    mutationFn: async (id: string) => (await api.post(`/admin/payments/orders/${id}/retry`, { reason: "admin_manual_retry" })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["adm_payments_orders"] }),
  });
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {["", "created", "attempted", "captured", "failed", "expired", "refunded", "partially_refunded"].map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)}
            className={`px-3 py-1.5 rounded-full text-xs font-bold ${status === s ? "bg-brand-navy text-white" : "bg-slate-100 text-slate-700"}`}>
            {s ? s.replace(/_/g, " ") : "All"}
          </button>
        ))}
      </div>
      {isLoading ? <div className="p-8 text-center text-slate-400">Loading…</div> : (
        <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">Order</th>
                <th className="text-left px-3 py-2">User</th>
                <th className="text-right px-3 py-2">Amount</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-left px-3 py-2">Method</th>
                <th className="text-left px-3 py-2">Created</th>
                <th className="text-left px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items || []).map((o: any) => (
                <tr key={o.order_id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono text-[10px]"><button onClick={() => setDetailId(o.order_id)} className="text-brand-navy hover:underline">{o.order_id.slice(-12)}</button>{o.is_demo && <span className="ml-1 px-1 rounded bg-amber-100 text-amber-700 text-[9px] font-bold">DEMO</span>}</td>
                  <td className="px-3 py-2 font-mono text-[10px]">{o.user_id?.slice(-10) || "—"}</td>
                  <td className="px-3 py-2 text-right font-bold">{paiseToInr(o.amount_paise)}</td>
                  <td className="px-3 py-2"><StatusPill s={o.status} /></td>
                  <td className="px-3 py-2 text-slate-500">{o.method_hint || "—"}</td>
                  <td className="px-3 py-2 text-slate-500">{fmtDate(o.created_at)}</td>
                  <td className="px-3 py-2">
                    {(o.status === "failed" || o.status === "expired") && (
                      <button onClick={() => retryMut.mutate(o.order_id)} className="text-xs text-emerald-700 hover:underline"><PlayCircle className="w-3.5 h-3.5 inline mr-1" />Retry</button>
                    )}
                  </td>
                </tr>
              ))}
              {(data?.items || []).length === 0 && <tr><td colSpan={7} className="text-center py-8 text-slate-400">No orders.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {detailId && <OrderDetailModal orderId={detailId} onClose={() => setDetailId(null)} />}
    </div>
  );
}

function OrderDetailModal({ orderId, onClose }: { orderId: string; onClose: () => void }) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["adm_pay_order_detail", orderId],
    queryFn: async () => (await api.get(`/admin/payments/orders/${orderId}`)).data,
  });
  const [refundAmt, setRefundAmt] = useState<string>("");
  const [refundReason, setRefundReason] = useState<string>("customer_request");
  const refundMut = useMutation({
    mutationFn: async () => (await api.post("/admin/payments/refunds", {
      payment_id: data?.transaction?.payment_id,
      amount_paise: refundAmt ? parseInt(refundAmt) : null,
      reason: refundReason,
    })).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["adm_pay_order_detail", orderId] }); qc.invalidateQueries({ queryKey: ["adm_payments_orders"] }); qc.invalidateQueries({ queryKey: ["adm_payments_refunds"] }); setRefundAmt(""); },
  });
  return (
    <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-xl max-w-2xl w-full max-h-[85vh] overflow-auto p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-3 mb-3">
          <h2 className="text-lg font-black">Order {orderId.slice(-12)}</h2>
          <button onClick={onClose} className="ml-auto text-slate-400 hover:text-slate-600"><XCircle className="w-5 h-5" /></button>
        </div>
        {!data ? <div className="p-4 text-center text-slate-400">Loading…</div> : (
          <>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <KV label="Order ID" value={data.order.order_id} mono />
              <KV label="Razorpay Order" value={data.order.provider_order_id} mono />
              <KV label="Amount" value={paiseToInr(data.order.amount_paise)} />
              <KV label="Refunded" value={paiseToInr(data.order.amount_refunded_paise || 0)} />
              <KV label="Status" value={<StatusPill s={data.order.status} />} />
              <KV label="User" value={data.order.user_id} mono />
              <KV label="Idempotency" value={data.order.idempotency_key || "—"} mono />
              <KV label="Created" value={fmtDate(data.order.created_at)} />
            </div>
            {data.transaction && (
              <>
                <h3 className="text-sm font-bold text-slate-700 mt-4 mb-1">Payment</h3>
                <div className="grid grid-cols-2 gap-3 text-xs bg-slate-50 p-3 rounded">
                  <KV label="Payment ID" value={data.transaction.payment_id} mono />
                  <KV label="Razorpay Pay" value={data.transaction.provider_payment_id} mono />
                  <KV label="Method" value={<span className="uppercase font-bold">{data.transaction.method}</span>} />
                  <KV label="Captured" value={fmtDate(data.transaction.captured_at)} />
                </div>
                <h3 className="text-sm font-bold text-slate-700 mt-4 mb-1">Issue refund</h3>
                <div className="flex gap-2 items-center">
                  <input type="number" placeholder={`≤ ${data.order.amount_paise - (data.order.amount_refunded_paise || 0)} paise (blank = full remainder)`} value={refundAmt} onChange={(e) => setRefundAmt(e.target.value)} className="border border-slate-300 rounded px-2 py-1.5 text-xs flex-1" />
                  <input type="text" placeholder="Reason" value={refundReason} onChange={(e) => setRefundReason(e.target.value)} className="border border-slate-300 rounded px-2 py-1.5 text-xs w-40" />
                  <button onClick={() => refundMut.mutate()} disabled={refundMut.isPending || data.order.status === "refunded"} className="px-3 py-1.5 rounded bg-red-600 text-white text-xs font-bold disabled:opacity-50">{refundMut.isPending ? "Refunding…" : "Refund"}</button>
                </div>
                {refundMut.error && <div className="text-xs text-red-600 mt-1">{(refundMut.error as any)?.response?.data?.detail || (refundMut.error as any)?.message}</div>}
              </>
            )}
            {data.refunds?.length > 0 && (
              <>
                <h3 className="text-sm font-bold text-slate-700 mt-4 mb-1">Refund History</h3>
                <div className="space-y-1 text-xs">
                  {data.refunds.map((r: any) => (
                    <div key={r.refund_id} className="flex items-center gap-2 bg-slate-50 p-2 rounded">
                      <span className="font-mono text-[10px]">{r.refund_id.slice(-10)}</span>
                      <span className="font-bold">{paiseToInr(r.amount_paise)}</span>
                      <StatusPill s={r.status} />
                      <span className="text-slate-500">{r.reason}</span>
                      <span className="ml-auto text-slate-500">{fmtDate(r.created_at)}</span>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function TxTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["adm_pay_tx"],
    queryFn: async () => (await api.get("/admin/payments/transactions", { params: { limit: 100 } })).data,
  });
  if (isLoading) return <div className="p-8 text-center text-slate-400">Loading…</div>;
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
      <table className="min-w-full text-xs">
        <thead className="bg-slate-50 text-slate-600"><tr>
          <th className="text-left px-3 py-2">Payment</th>
          <th className="text-left px-3 py-2">Order</th>
          <th className="text-left px-3 py-2">User</th>
          <th className="text-right px-3 py-2">Amount</th>
          <th className="text-right px-3 py-2">Refunded</th>
          <th className="text-left px-3 py-2">Method</th>
          <th className="text-left px-3 py-2">Status</th>
          <th className="text-left px-3 py-2">Captured</th>
        </tr></thead>
        <tbody>
          {(data?.items || []).map((t: any) => (
            <tr key={t.payment_id} className="border-t border-slate-100">
              <td className="px-3 py-2 font-mono text-[10px]">{t.payment_id.slice(-12)}</td>
              <td className="px-3 py-2 font-mono text-[10px]">{t.order_id.slice(-12)}</td>
              <td className="px-3 py-2 font-mono text-[10px]">{t.user_id?.slice(-10)}</td>
              <td className="px-3 py-2 text-right font-bold">{paiseToInr(t.amount_paise)}</td>
              <td className="px-3 py-2 text-right text-red-600">{paiseToInr(t.amount_refunded_paise)}</td>
              <td className="px-3 py-2 uppercase">{t.method}</td>
              <td className="px-3 py-2"><StatusPill s={t.status} /></td>
              <td className="px-3 py-2 text-slate-500">{fmtDate(t.captured_at)}</td>
            </tr>
          ))}
          {(data?.items || []).length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">No transactions.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function RefundsTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["adm_payments_refunds"],
    queryFn: async () => (await api.get("/admin/payments/refunds", { params: { limit: 100 } })).data,
  });
  if (isLoading) return <div className="p-8 text-center text-slate-400">Loading…</div>;
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
      <table className="min-w-full text-xs">
        <thead className="bg-slate-50 text-slate-600"><tr>
          <th className="text-left px-3 py-2">Refund</th>
          <th className="text-left px-3 py-2">Payment</th>
          <th className="text-right px-3 py-2">Amount</th>
          <th className="text-left px-3 py-2">Status</th>
          <th className="text-left px-3 py-2">Reason</th>
          <th className="text-left px-3 py-2">Initiated By</th>
          <th className="text-left px-3 py-2">Created</th>
        </tr></thead>
        <tbody>
          {(data?.items || []).map((r: any) => (
            <tr key={r.refund_id} className="border-t border-slate-100">
              <td className="px-3 py-2 font-mono text-[10px]">{r.refund_id.slice(-12)}</td>
              <td className="px-3 py-2 font-mono text-[10px]">{r.payment_id.slice(-12)}</td>
              <td className="px-3 py-2 text-right font-bold">{paiseToInr(r.amount_paise)}</td>
              <td className="px-3 py-2"><StatusPill s={r.status} /></td>
              <td className="px-3 py-2">{r.reason}</td>
              <td className="px-3 py-2 font-mono text-[10px]">{r.initiated_by?.slice(-10)}</td>
              <td className="px-3 py-2 text-slate-500">{fmtDate(r.created_at)}</td>
            </tr>
          ))}
          {(data?.items || []).length === 0 && <tr><td colSpan={7} className="text-center py-8 text-slate-400">No refunds.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function ReconcileTab() {
  const qc = useQueryClient();
  const { data: st } = useQuery({
    queryKey: ["adm_pay_recon_status"],
    queryFn: async () => (await api.get("/admin/payments/reconciliation-status")).data,
    refetchInterval: 10000,
  });
  const { data: history } = useQuery({
    queryKey: ["adm_pay_recon_history"],
    queryFn: async () => (await api.get("/admin/payments/reconciliation-history", { params: { limit: 20 } })).data,
  });
  const runMut = useMutation({
    mutationFn: async () => (await api.post("/admin/payments/reconcile?window_hours=24")).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["adm_pay_recon_status"] }); qc.invalidateQueries({ queryKey: ["adm_pay_recon_history"] }); },
  });
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <div className="text-sm text-slate-600">Auto-runs every <b>{Math.round((st?.interval_sec || 0) / 60)} min</b>. Reconciliation queries Razorpay for pending orders and heals missed webhooks.</div>
        <button onClick={() => runMut.mutate()} disabled={runMut.isPending} className="ml-auto px-3 py-2 rounded-lg bg-brand-navy text-white text-sm font-bold disabled:opacity-50">
          <RefreshCw className="w-4 h-4 inline mr-1" /> Run Now
        </button>
      </div>
      {st?.latest && (
        <div className={`p-3 rounded-lg border ${st.latest.skipped ? "bg-amber-50 border-amber-200" : "bg-emerald-50 border-emerald-200"}`}>
          <div className="text-xs font-bold text-slate-700 mb-1">LATEST RUN · {st.latest.run_id}</div>
          {st.latest.skipped ? (
            <div className="text-xs text-amber-700">Skipped: <b>{st.latest.skipped}</b> (configure real Razorpay keys to enable)</div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
              <KV label="Scanned" value={st.latest.scanned} />
              <KV label="Healed" value={st.latest.healed} />
              <KV label="Failed" value={st.latest.failed} />
              <KV label="Expired" value={st.latest.expired} />
              <KV label="Duration" value={`${st.latest.duration_ms}ms`} />
            </div>
          )}
          <div className="text-[10px] text-slate-500 mt-1">Triggered by: {st.latest.triggered_by} · finished {fmtDate(st.latest.finished_at)}</div>
        </div>
      )}
      <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
        <table className="min-w-full text-xs">
          <thead className="bg-slate-50 text-slate-600"><tr>
            <th className="text-left px-3 py-2">Run</th>
            <th className="text-left px-3 py-2">Triggered</th>
            <th className="text-right px-3 py-2">Scanned</th>
            <th className="text-right px-3 py-2">Healed</th>
            <th className="text-right px-3 py-2">Failed</th>
            <th className="text-right px-3 py-2">Expired</th>
            <th className="text-right px-3 py-2">Duration</th>
            <th className="text-left px-3 py-2">Started</th>
          </tr></thead>
          <tbody>
            {(history?.items || []).map((r: any) => (
              <tr key={r.run_id} className="border-t border-slate-100">
                <td className="px-3 py-2 font-mono text-[10px]">{r.run_id}</td>
                <td className="px-3 py-2 text-slate-500">{r.triggered_by}</td>
                <td className="px-3 py-2 text-right">{r.scanned}</td>
                <td className="px-3 py-2 text-right text-emerald-600 font-bold">{r.healed}</td>
                <td className="px-3 py-2 text-right text-red-600">{r.failed}</td>
                <td className="px-3 py-2 text-right text-amber-600">{r.expired}</td>
                <td className="px-3 py-2 text-right">{r.duration_ms}ms</td>
                <td className="px-3 py-2 text-slate-500">{fmtDate(r.started_at)}</td>
              </tr>
            ))}
            {(history?.items || []).length === 0 && <tr><td colSpan={8} className="text-center py-8 text-slate-400">No runs yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AuditTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["adm_pay_audit"],
    queryFn: async () => (await api.get("/admin/payments/audit-log", { params: { limit: 100 } })).data,
    refetchInterval: 15000,
  });
  if (isLoading) return <div className="p-8 text-center text-slate-400">Loading…</div>;
  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
      <table className="min-w-full text-xs">
        <thead className="bg-slate-50 text-slate-600"><tr>
          <th className="text-left px-3 py-2">When</th>
          <th className="text-left px-3 py-2">Action</th>
          <th className="text-left px-3 py-2">Actor</th>
          <th className="text-left px-3 py-2">Target</th>
          <th className="text-left px-3 py-2">Meta</th>
        </tr></thead>
        <tbody>
          {(data?.items || []).map((a: any) => (
            <tr key={a.audit_id} className="border-t border-slate-100">
              <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{fmtDate(a.at)}</td>
              <td className="px-3 py-2 font-bold">{a.action}</td>
              <td className="px-3 py-2 font-mono text-[10px]">{a.actor_type}:{a.actor_id?.slice(-8)}</td>
              <td className="px-3 py-2 font-mono text-[10px]">{a.target_type}:{a.target_id?.slice(-12)}</td>
              <td className="px-3 py-2 text-slate-500">{JSON.stringify(a.after || a.meta || {}).slice(0, 100)}</td>
            </tr>
          ))}
          {(data?.items || []).length === 0 && <tr><td colSpan={5} className="text-center py-8 text-slate-400">Empty audit log.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function ConfigTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["adm_payments_config"],
    queryFn: async () => (await api.get("/admin/payments/config")).data,
  });
  const [form, setForm] = useState<any>({});
  const patchMut = useMutation({
    mutationFn: async (patch: any) => (await api.put("/admin/payments/config", patch)).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["adm_payments_config"] }); setForm({}); },
  });
  if (!data) return <div className="p-8 text-center text-slate-400">Loading…</div>;
  return (
    <div className="space-y-4">
      <div className="p-4 rounded-xl border border-slate-200 bg-white">
        <div className="text-xs font-bold text-slate-700 mb-3">CURRENT CONFIG</div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
          <KV label="Mode" value={<span className={`px-2 py-0.5 rounded font-bold ${data.mode === "live" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"}`}>{data.mode.toUpperCase()}</span>} />
          <KV label="Demo Mode" value={data.demo_mode ? <span className="text-amber-600 font-bold">ON</span> : <span className="text-emerald-600 font-bold">OFF</span>} />
          <KV label="Configured" value={data.configured ? <CheckCircle2 className="w-4 h-4 text-emerald-600 inline" /> : <XCircle className="w-4 h-4 text-red-600 inline" />} />
          <KV label="Key ID" value={data.key_id_public || "—"} mono />
          <KV label="Has Key Secret" value={data.has_key_secret ? "Yes" : "No"} />
          <KV label="Has Webhook Secret" value={data.has_webhook_secret ? "Yes" : "No"} />
          <KV label="Min Top-up" value={paiseToInr(data.min_topup_paise)} />
          <KV label="Max Top-up" value={paiseToInr(data.max_topup_paise)} />
          <KV label="Last Updated" value={fmtDate(data.last_updated_at)} />
        </div>
      </div>
      <div className="p-4 rounded-xl border-2 border-brand-navy/20 bg-brand-navy/5">
        <div className="text-xs font-bold text-brand-navy mb-3">UPDATE CONFIG</div>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <label>Mode
            <select value={form.mode ?? data.mode} onChange={(e) => setForm({ ...form, mode: e.target.value })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1">
              <option value="test">Test</option><option value="live">Live</option>
            </select>
          </label>
          <label className="flex items-center gap-2 mt-6">
            <input type="checkbox" checked={form.demo_mode ?? data.demo_mode} onChange={(e) => setForm({ ...form, demo_mode: e.target.checked })} />
            <span>Demo Mode (simulate locally, skip Razorpay)</span>
          </label>
          <label>Min top-up (paise)
            <input type="number" value={form.min_topup_paise ?? data.min_topup_paise} onChange={(e) => setForm({ ...form, min_topup_paise: parseInt(e.target.value || "0") })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1" />
          </label>
          <label>Max top-up (paise)
            <input type="number" value={form.max_topup_paise ?? data.max_topup_paise} onChange={(e) => setForm({ ...form, max_topup_paise: parseInt(e.target.value || "0") })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1" />
          </label>
          <label>Key ID (rzp_test_… / rzp_live_…)
            <input type="text" placeholder="Leave blank to keep current" onChange={(e) => setForm({ ...form, key_id: e.target.value || undefined })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1 font-mono" />
          </label>
          <label>Key Secret
            <input type="password" placeholder="Leave blank to keep current" onChange={(e) => setForm({ ...form, key_secret: e.target.value || undefined })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1 font-mono" />
          </label>
          <label className="col-span-2">Webhook Secret
            <input type="password" placeholder="Leave blank to keep current" onChange={(e) => setForm({ ...form, webhook_secret: e.target.value || undefined })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1 font-mono" />
          </label>
        </div>
        <div className="mt-3 flex gap-2 items-center">
          <button onClick={() => patchMut.mutate(form)} disabled={Object.keys(form).length === 0 || patchMut.isPending} className="px-4 py-2 rounded-lg bg-brand-navy text-white text-sm font-bold disabled:opacity-50">{patchMut.isPending ? "Saving…" : "Save Config"}</button>
          <button onClick={() => setForm({})} className="px-3 py-2 rounded text-sm text-slate-600 hover:bg-slate-100">Reset</button>
          {patchMut.error && <span className="text-xs text-red-600 ml-2">{(patchMut.error as any)?.response?.data?.detail}</span>}
          {patchMut.isSuccess && <span className="text-xs text-emerald-600 ml-2">✓ Saved</span>}
        </div>
        <div className="mt-3 text-[10px] text-slate-500 leading-relaxed">
          🔒 <b>Security note:</b> Key Secret and Webhook Secret are stored server-side only and never returned by any endpoint. They&apos;re also never logged (JSON logger redacts them).
        </div>
      </div>
    </div>
  );
}

// ============ helpers ============
function StatCard({ label, value, sub, tint }: any) {
  const map: Record<string, string> = {
    emerald: "border-emerald-200 bg-emerald-50",
    blue: "border-blue-200 bg-blue-50",
    violet: "border-violet-200 bg-violet-50",
    amber: "border-amber-200 bg-amber-50",
    red: "border-red-200 bg-red-50",
    slate: "border-slate-200 bg-slate-50",
  };
  return (
    <div className={`p-4 rounded-xl border-2 ${map[tint || "blue"]}`}>
      <div className="text-[10px] font-bold uppercase tracking-widest text-slate-600">{label}</div>
      <div className="text-2xl font-black mt-1">{value}</div>
      {sub && <div className="text-[11px] text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}
function KV({ label, value, mono }: any) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] font-bold text-slate-500 uppercase">{label}</span>
      <span className={`text-slate-800 ${mono ? "font-mono text-[10px]" : "font-bold"}`}>{value}</span>
    </div>
  );
}
function StatusPill({ s }: { s: string }) {
  const map: Record<string, string> = {
    created: "bg-slate-100 text-slate-700",
    attempted: "bg-blue-100 text-blue-700",
    captured: "bg-emerald-100 text-emerald-700",
    failed: "bg-red-100 text-red-700",
    expired: "bg-slate-200 text-slate-600",
    refunded: "bg-amber-100 text-amber-700",
    partially_refunded: "bg-amber-50 text-amber-700",
    processed: "bg-emerald-100 text-emerald-700",
    pending: "bg-blue-100 text-blue-700",
  };
  return <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${map[s] || "bg-slate-100 text-slate-600"}`}>{s?.replace(/_/g, " ")}</span>;
}

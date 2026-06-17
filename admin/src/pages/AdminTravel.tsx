import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fmtCurrency, fmtDate } from "../lib/api";
import { useAdminAuth } from "../lib/auth";
import {
  Plane, Hotel, Bus, Train, Search, RefreshCw, X, CheckCircle2,
  XCircle, Clock, AlertTriangle, IndianRupee, ChevronRight, FileText,
  History as HistoryIcon, Ban, Wallet,
} from "lucide-react";

type Booking = {
  booking_id: string;
  user_id: string;
  user_name?: string; user_mobile?: string; user_email?: string;
  booking_type: string;
  title: string;
  from_loc?: string; to_loc?: string; travel_date?: string;
  passengers?: number;
  amount: number;
  status: string;
  refund_status?: string;
  refund_amount?: number; refund_pct?: number;
  cancel_reason?: string; refund_admin_note?: string;
  cancelled_at?: string;
  created_at: string; updated_at?: string;
  history?: Array<{ event: string; by: string; by_id: string; note?: string; at: string; amount?: number; refund_amount?: number }>;
};

const TYPE_ICON: Record<string, any> = { flight: Plane, hotel: Hotel, bus: Bus, train: Train };

const STATUS_META: Record<string, { label: string; cls: string }> = {
  booked:     { label: "Booked",     cls: "bg-sky-50 text-sky-700 border-sky-200" },
  confirmed:  { label: "Confirmed",  cls: "bg-sky-50 text-sky-700 border-sky-200" },
  pending:    { label: "Pending",    cls: "bg-amber-50 text-amber-700 border-amber-200" },
  completed:  { label: "Completed",  cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  cancelled:  { label: "Cancelled",  cls: "bg-red-50 text-red-700 border-red-200" },
};
const REFUND_META: Record<string, { label: string; cls: string }> = {
  none:      { label: "—",             cls: "bg-slate-100 text-slate-500 border-slate-200" },
  pending:   { label: "Refund Pending",   cls: "bg-amber-50 text-amber-700 border-amber-200" },
  approved:  { label: "Refund Approved",  cls: "bg-sky-50 text-sky-700 border-sky-200" },
  rejected:  { label: "Refund Rejected",  cls: "bg-red-50 text-red-700 border-red-200" },
  processed: { label: "Refund Paid",      cls: "bg-emerald-50 text-emerald-700 border-emerald-200" },
};

export default function AdminTravel() {
  const qc = useQueryClient();
  const { admin } = useAdminAuth();
  const canCancel = ["super_admin", "admin", "support_manager"].includes(admin?.role || "");
  const canDecide = ["super_admin", "admin", "finance_manager"].includes(admin?.role || "");

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [refundFilter, setRefundFilter] = useState("all");
  const [openBooking, setOpenBooking] = useState<string | null>(null);

  const { data: analytics } = useQuery({
    queryKey: ["travel-analytics"],
    queryFn: async () => (await api.get("/admin/travel/analytics")).data,
    refetchInterval: 20000,
  });

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["travel-bookings", statusFilter, typeFilter, refundFilter, search],
    queryFn: async () => {
      const params: any = { limit: 200 };
      if (statusFilter !== "all") params.status = statusFilter;
      if (typeFilter !== "all") params.booking_type = typeFilter;
      if (refundFilter !== "all") params.refund_status = refundFilter;
      if (search.trim()) params.search = search.trim();
      return (await api.get("/admin/travel/bookings", { params })).data as { items: Booking[]; total: number };
    },
  });

  const items = data?.items || [];

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2">
            <Plane className="w-6 h-6" /> Travel Bookings & Refunds
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Cancel bookings, approve refunds, and credit wallets. Every action is audited.
          </p>
        </div>
        <button onClick={() => { refetch(); qc.invalidateQueries({ queryKey: ["travel-analytics"] }); }} className="btn-ghost gap-2 text-sm">
          <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      {/* KPIs */}
      {analytics ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <Kpi label="Total bookings" value={analytics.total_bookings} cls="from-sky-500 to-blue-600" Icon={FileText} />
          <Kpi label="Cancelled" value={analytics.cancelled_bookings} cls="from-red-500 to-rose-600" Icon={Ban} />
          <Kpi label="Refund paid" value={fmtCurrency(analytics.refund_amount_paid)} cls="from-emerald-500 to-emerald-600" Icon={Wallet} />
          <Kpi label="Pending refunds" value={analytics.pending_refunds} cls="from-amber-400 to-orange-500" Icon={Clock} />
          <Kpi label="In pipeline" value={fmtCurrency(analytics.refund_amount_in_pipeline)} cls="from-violet-500 to-fuchsia-600" Icon={IndianRupee} />
        </div>
      ) : null}

      {analytics && analytics.by_type?.length > 0 ? (
        <div className="card">
          <p className="text-sm font-bold text-brand-navy mb-2">Booking type breakdown</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {analytics.by_type.map((t: any) => {
              const Icon = TYPE_ICON[t.type] || Plane;
              return (
                <div key={t.type} className="bg-slate-50 rounded-xl p-3 flex items-center gap-3">
                  <div className="p-2 rounded-lg bg-brand-primary/10 text-brand-primary"><Icon className="w-5 h-5" /></div>
                  <div className="flex-1">
                    <p className="text-xs text-slate-500 capitalize">{t.type}</p>
                    <p className="font-extrabold text-brand-navy">{t.count}</p>
                    <p className="text-[10px] text-slate-500">{fmtCurrency(t.revenue)}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* Filters */}
      <div className="card flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-400" />
          <input className="input" placeholder="Search by booking ID, user, mobile, title…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <select className="input max-w-[150px]" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="booked">Booked</option>
          <option value="confirmed">Confirmed</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
          <option value="pending">Pending</option>
        </select>
        <select className="input max-w-[140px]" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="all">All types</option>
          <option value="flight">Flight</option>
          <option value="hotel">Hotel</option>
          <option value="bus">Bus</option>
          <option value="train">Train</option>
        </select>
        <select className="input max-w-[170px]" value={refundFilter} onChange={(e) => setRefundFilter(e.target.value)}>
          <option value="all">All refund states</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="processed">Processed</option>
        </select>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        {items.length === 0 ? (
          <div className="text-slate-400 py-12 text-center">
            <Plane className="w-10 h-10 mx-auto opacity-40 mb-2" />
            <p className="font-bold">No bookings match your filters</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 uppercase font-bold border-b border-slate-200">
                  <th className="py-2 px-2">Booking</th>
                  <th className="py-2 px-2">User</th>
                  <th className="py-2 px-2 text-right">Amount</th>
                  <th className="py-2 px-2">Status</th>
                  <th className="py-2 px-2">Refund</th>
                  <th className="py-2 px-2">Booked</th>
                  <th className="py-2 px-2"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((b) => {
                  const Icon = TYPE_ICON[b.booking_type] || Plane;
                  const sm = STATUS_META[b.status] || STATUS_META.confirmed;
                  const rm = REFUND_META[b.refund_status || "none"] || REFUND_META.none;
                  return (
                    <tr key={b.booking_id} className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer" onClick={() => setOpenBooking(b.booking_id)}>
                      <td className="py-3 px-2">
                        <p className="font-semibold text-slate-800 flex items-center gap-1.5"><Icon className="w-3.5 h-3.5 text-slate-500" />{b.title}</p>
                        <p className="text-[11px] font-mono text-slate-500">{b.booking_id.slice(0, 18)}…</p>
                      </td>
                      <td className="py-3 px-2">
                        <p className="font-semibold text-slate-800">{b.user_name || "—"}</p>
                        <p className="text-xs text-slate-500">{b.user_mobile || b.user_email}</p>
                      </td>
                      <td className="py-3 px-2 text-right">
                        <p className="font-bold">{fmtCurrency(b.amount)}</p>
                        {b.refund_amount ? (
                          <p className="text-xs text-emerald-600 font-semibold">↻ {fmtCurrency(b.refund_amount)}</p>
                        ) : null}
                      </td>
                      <td className="py-3 px-2"><span className={`badge ${sm.cls} border`}>{sm.label}</span></td>
                      <td className="py-3 px-2"><span className={`badge ${rm.cls} border`}>{rm.label}</span></td>
                      <td className="py-3 px-2 text-xs text-slate-500">{fmtDate(b.created_at)}</td>
                      <td className="py-3 px-2 text-right"><ChevronRight className="w-4 h-4 text-slate-400" /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {openBooking ? (
        <BookingDrawer
          bookingId={openBooking}
          canCancel={canCancel} canDecide={canDecide}
          onClose={() => setOpenBooking(null)}
          onChanged={() => { qc.invalidateQueries({ queryKey: ["travel-bookings"] }); qc.invalidateQueries({ queryKey: ["travel-analytics"] }); }}
        />
      ) : null}
    </div>
  );
}

function Kpi({ label, value, cls, Icon }: { label: string; value: any; cls: string; Icon: any }) {
  return (
    <div className={`rounded-2xl p-3 text-white bg-gradient-to-br ${cls} flex items-center gap-3`}>
      <Icon className="w-8 h-8 opacity-70" />
      <div>
        <p className="text-[11px] font-bold opacity-80">{label}</p>
        <p className="text-xl font-extrabold mt-1">{value}</p>
      </div>
    </div>
  );
}

function BookingDrawer({ bookingId, canCancel, canDecide, onClose, onChanged }: {
  bookingId: string; canCancel: boolean; canDecide: boolean; onClose: () => void; onChanged: () => void;
}) {
  const [reason, setReason] = useState("");
  const [preset, setPreset] = useState("high");
  const [override, setOverride] = useState<string>("");
  const [note, setNote] = useState("");
  const [action, setAction] = useState<"cancel" | "approve" | "reject" | "process" | null>(null);

  const { data: b, refetch } = useQuery({
    queryKey: ["booking", bookingId],
    queryFn: async () => (await api.get(`/admin/travel/bookings/${bookingId}`)).data as Booking,
  });

  const cancelBk = useMutation({
    mutationFn: async () => (await api.post(`/admin/travel/bookings/${bookingId}/cancel`, {
      reason, refund_preset: preset,
      refund_amount_override: override ? Number(override) : undefined,
    })).data,
    onSuccess: () => { setReason(""); setOverride(""); setAction(null); refetch(); onChanged(); },
  });
  const approveR = useMutation({
    mutationFn: async () => (await api.post(`/admin/travel/bookings/${bookingId}/refund/approve`, {
      admin_note: note, refund_amount_override: override ? Number(override) : undefined,
    })).data,
    onSuccess: () => { setNote(""); setOverride(""); setAction(null); refetch(); onChanged(); },
  });
  const rejectR = useMutation({
    mutationFn: async () => (await api.post(`/admin/travel/bookings/${bookingId}/refund/reject`, { admin_note: note })).data,
    onSuccess: () => { setNote(""); setAction(null); refetch(); onChanged(); },
  });
  const processR = useMutation({
    mutationFn: async () => (await api.post(`/admin/travel/bookings/${bookingId}/refund/process`, {})).data,
    onSuccess: () => { setAction(null); refetch(); onChanged(); },
  });

  const busy = cancelBk.isPending || approveR.isPending || rejectR.isPending || processR.isPending;
  const isCancelled = b?.status === "cancelled";
  const refundStatus = b?.refund_status || "none";

  const submit = () => {
    if (action === "cancel") { if (reason.trim().length < 3) return; cancelBk.mutate(); }
    else if (action === "approve") { if (note.trim().length < 3) return; approveR.mutate(); }
    else if (action === "reject") { if (note.trim().length < 3) return; rejectR.mutate(); }
    else if (action === "process") { processR.mutate(); }
  };

  return (
    <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm flex items-stretch justify-end" onClick={onClose}>
      <div className="w-full max-w-2xl bg-white h-full overflow-y-auto shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="sticky top-0 bg-white border-b border-slate-200 px-5 py-4 flex items-center justify-between z-10">
          <div className="min-w-0">
            <p className="font-extrabold text-brand-navy truncate">Booking Details</p>
            <p className="text-xs font-mono text-slate-500 truncate">{bookingId}</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg"><X className="w-5 h-5" /></button>
        </div>

        {!b ? <div className="p-10 text-center text-slate-400">Loading…</div> : (
          <div className="p-5 space-y-5">
            {/* Status banners */}
            <div className="grid grid-cols-2 gap-2">
              <div className={`rounded-xl px-3 py-2 border text-sm font-bold ${STATUS_META[b.status]?.cls || ""}`}>
                {STATUS_META[b.status]?.label || b.status}
              </div>
              <div className={`rounded-xl px-3 py-2 border text-sm font-bold ${REFUND_META[refundStatus]?.cls || ""}`}>
                {REFUND_META[refundStatus]?.label || refundStatus}
                {b.refund_amount ? ` · ${fmtCurrency(b.refund_amount)} (${b.refund_pct}%)` : ""}
              </div>
            </div>

            {/* Booking & user */}
            <div className="grid sm:grid-cols-2 gap-3">
              <div className="card space-y-1.5">
                <p className="text-xs font-bold text-slate-500 uppercase">Booking</p>
                <Row k="Title" v={b.title} />
                <Row k="Type" v={b.booking_type} cap />
                <Row k="Route" v={`${b.from_loc || "—"} → ${b.to_loc || "—"}`} />
                <Row k="Travel date" v={b.travel_date || "—"} />
                <Row k="Passengers" v={b.passengers || 1} />
                <Row k="Amount paid" v={fmtCurrency(b.amount)} bold />
              </div>
              <div className="card space-y-1.5">
                <p className="text-xs font-bold text-slate-500 uppercase">User</p>
                <Row k="Name" v={b.user_name || "—"} />
                <Row k="Email" v={b.user_email || "—"} />
                <Row k="Mobile" v={b.user_mobile || "—"} mono />
                <Row k="User ID" v={b.user_id} mono small />
              </div>
            </div>

            {b.cancel_reason ? (
              <div className="card bg-red-50 border border-red-200">
                <p className="text-xs font-bold text-red-700 uppercase">Cancellation reason</p>
                <p className="text-sm text-red-900 mt-1">{b.cancel_reason}</p>
              </div>
            ) : null}

            {b.refund_admin_note ? (
              <div className="card bg-sky-50 border border-sky-200">
                <p className="text-xs font-bold text-sky-700 uppercase">Refund admin note</p>
                <p className="text-sm text-sky-900 mt-1">{b.refund_admin_note}</p>
              </div>
            ) : null}

            {/* History */}
            <div className="card">
              <p className="text-xs font-bold text-slate-500 uppercase flex items-center gap-1.5 mb-2"><HistoryIcon className="w-3.5 h-3.5" /> History</p>
              {(b.history || []).length === 0 ? (
                <p className="text-xs text-slate-400">No history yet — booking was created without state changes.</p>
              ) : (
                <div className="space-y-3">
                  {(b.history || []).map((h, i) => (
                    <div key={i} className="flex gap-3 text-sm">
                      <div className="w-2 h-2 mt-1.5 rounded-full bg-brand-primary shrink-0" />
                      <div className="flex-1">
                        <p className="font-bold text-slate-800 text-xs">{h.event}</p>
                        <p className="text-[11px] text-slate-500">by {h.by} · {fmtDate(h.at)}</p>
                        {h.note ? <p className="text-xs italic text-slate-600 mt-0.5">"{h.note}"</p> : null}
                        {h.refund_amount ? <p className="text-xs text-emerald-600 font-semibold">Refund: {fmtCurrency(h.refund_amount)}</p> : null}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Action panel */}
            <div className="card border-2 border-brand-primary/20 bg-sky-50/40 space-y-3">
              <p className="font-extrabold text-brand-navy">Take action</p>
              <div className="flex gap-2 flex-wrap">
                {!isCancelled && canCancel ? (
                  <ActionBtn onClick={() => setAction("cancel")} active={action === "cancel"} Icon={Ban} label="Cancel & Refund" cls="bg-red-600" />
                ) : null}
                {refundStatus === "pending" && canDecide ? (
                  <>
                    <ActionBtn onClick={() => setAction("approve")} active={action === "approve"} Icon={CheckCircle2} label="Approve Refund" cls="bg-sky-600" />
                    <ActionBtn onClick={() => setAction("reject")} active={action === "reject"} Icon={XCircle} label="Reject Refund" cls="bg-rose-600" />
                  </>
                ) : null}
                {refundStatus === "approved" && canDecide ? (
                  <ActionBtn onClick={() => setAction("process")} active={action === "process"} Icon={Wallet} label="Process Refund (Credit Wallet)" cls="bg-emerald-600" />
                ) : null}
              </div>

              {action === "cancel" ? (
                <div className="space-y-2 pt-2 border-t border-slate-200">
                  <div>
                    <label className="text-xs font-bold text-slate-600">Cancellation reason <span className="text-red-500">*</span></label>
                    <textarea className="input mt-1 min-h-[60px]" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. User requested via support call" />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <label className="text-xs font-bold text-slate-600">Refund preset</label>
                      <select className="input mt-1" value={preset} onChange={(e) => setPreset(e.target.value)}>
                        <option value="full">100% — Full refund</option>
                        <option value="high">90% — Cancelled early</option>
                        <option value="partial_75">75% — Partial</option>
                        <option value="partial_50">50% — Late cancellation</option>
                        <option value="none">0% — No refund</option>
                      </select>
                    </div>
                    <div>
                      <label className="text-xs font-bold text-slate-600">Override amount (optional)</label>
                      <input type="number" className="input mt-1" value={override} onChange={(e) => setOverride(e.target.value)} placeholder={`Max ${b.amount}`} max={b.amount} />
                    </div>
                  </div>
                  <ActionsRow onCancel={() => setAction(null)} onSubmit={submit} busy={busy} label="Cancel Booking & Queue Refund" disabled={reason.trim().length < 3} />
                </div>
              ) : null}

              {(action === "approve" || action === "reject") ? (
                <div className="space-y-2 pt-2 border-t border-slate-200">
                  {action === "approve" ? (
                    <div>
                      <label className="text-xs font-bold text-slate-600">Override approved amount (optional)</label>
                      <input type="number" className="input mt-1" value={override} onChange={(e) => setOverride(e.target.value)} placeholder={`Suggested: ${b.refund_amount}`} max={b.amount} />
                    </div>
                  ) : null}
                  <div>
                    <label className="text-xs font-bold text-slate-600">Admin note <span className="text-red-500">*</span></label>
                    <textarea className="input mt-1 min-h-[60px]" value={note} onChange={(e) => setNote(e.target.value)} placeholder={action === "approve" ? "Refund verified, ready to process" : "Reason for rejection"} />
                  </div>
                  <ActionsRow onCancel={() => setAction(null)} onSubmit={submit} busy={busy} label={action === "approve" ? "Approve Refund" : "Reject Refund"} disabled={note.trim().length < 3} />
                </div>
              ) : null}

              {action === "process" ? (
                <div className="space-y-2 pt-2 border-t border-slate-200">
                  <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-3 text-sm text-emerald-900">
                    This will credit <b>{fmtCurrency(b.refund_amount || 0)}</b> to <b>{b.user_name || b.user_id}</b>'s MFB Wallet and notify the user. Action is irreversible.
                  </div>
                  <ActionsRow onCancel={() => setAction(null)} onSubmit={submit} busy={busy} label="Confirm & Credit Wallet" />
                </div>
              ) : null}

              {!canCancel && !canDecide ? (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-start gap-2 text-sm text-amber-900">
                  <AlertTriangle className="w-4 h-4 mt-0.5" />
                  Your role has view-only access on this page.
                </div>
              ) : null}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Row({ k, v, mono, small, bold, cap }: { k: string; v: any; mono?: boolean; small?: boolean; bold?: boolean; cap?: boolean }) {
  return (
    <div className="flex justify-between gap-3 text-sm">
      <span className="text-slate-500">{k}</span>
      <span className={`text-right ${mono ? "font-mono" : ""} ${small ? "text-[11px]" : ""} ${bold ? "font-extrabold text-brand-navy" : "font-semibold text-slate-800"} ${cap ? "capitalize" : ""} truncate max-w-[60%]`}>{v}</span>
    </div>
  );
}

function ActionBtn({ onClick, active, Icon, label, cls }: any) {
  return (
    <button onClick={onClick} className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-bold border transition ${active ? `text-white ${cls} border-transparent shadow` : "bg-white text-slate-700 border-slate-200 hover:border-slate-300"}`}>
      <Icon className="w-4 h-4" /> {label}
    </button>
  );
}

function ActionsRow({ onCancel, onSubmit, busy, label, disabled }: { onCancel: () => void; onSubmit: () => void; busy?: boolean; label: string; disabled?: boolean }) {
  return (
    <div className="flex justify-end gap-2">
      <button onClick={onCancel} className="btn-ghost text-sm">Cancel</button>
      <button onClick={onSubmit} disabled={!!disabled || !!busy} className="btn-primary text-sm">{busy ? "Saving…" : label}</button>
    </div>
  );
}

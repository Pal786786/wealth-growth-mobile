import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fmtCurrency, fmtDate } from "../lib/api";
import { useAdminAuth } from "../lib/auth";
import {
  Shield, Heart, Car, Plane, Search, RefreshCw, CheckCircle2, XCircle,
  Clock, AlertTriangle, FileText, MessageSquareWarning, Eye, X, IndianRupee,
  TrendingUp, ChevronRight, History as HistoryIcon, User as UserIcon, FileSearch,
} from "lucide-react";

type Claim = {
  claim_id: string;
  policy_id: string;
  plan_name: string;
  plan_type: "health" | "life" | "motor" | "travel";
  user_id: string;
  user_name?: string;
  user_email?: string;
  user_mobile?: string;
  claim_type: string;
  claim_amount: number;
  approved_amount: number;
  incident_date?: string;
  description?: string;
  status: "submitted" | "under_review" | "approved" | "rejected" | "info_requested";
  admin_note?: string;
  decided_by_admin_id?: string | null;
  decided_at?: string | null;
  created_at: string;
  updated_at: string;
  history?: Array<{ event: string; by: string; by_id: string; note?: string; at: string; approved_amount?: number }>;
  documents?: Array<{ name: string; mime: string; has_file?: boolean }>;
};

const STATUS_META: Record<string, { label: string; cls: string; Icon: any }> = {
  submitted:      { label: "Submitted",      cls: "bg-slate-100 text-slate-700 border-slate-200",  Icon: FileText },
  under_review:   { label: "Under Review",   cls: "bg-sky-50 text-sky-700 border-sky-200",         Icon: Clock },
  info_requested: { label: "Info Requested", cls: "bg-amber-50 text-amber-700 border-amber-200",   Icon: MessageSquareWarning },
  approved:       { label: "Approved",       cls: "bg-emerald-50 text-emerald-700 border-emerald-200", Icon: CheckCircle2 },
  rejected:       { label: "Rejected",       cls: "bg-red-50 text-red-700 border-red-200",         Icon: XCircle },
};

const TYPE_ICON: Record<string, any> = {
  health: Heart, life: Shield, motor: Car, travel: Plane,
};

export default function AdminInsuranceClaims() {
  const qc = useQueryClient();
  const { admin } = useAdminAuth();
  const canDecide = admin?.role === "super_admin" || admin?.role === "admin";

  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [openClaim, setOpenClaim] = useState<string | null>(null);

  const { data: stats } = useQuery({
    queryKey: ["claims-stats"],
    queryFn: async () => (await api.get("/admin/insurance/claims/stats")).data,
    refetchInterval: 15000,
  });

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["claims-list", statusFilter, typeFilter, search],
    queryFn: async () => {
      const params: any = { limit: 200 };
      if (statusFilter !== "all") params.status = statusFilter;
      if (typeFilter !== "all") params.plan_type = typeFilter;
      if (search.trim()) params.search = search.trim();
      return (await api.get("/admin/insurance/claims", { params })).data as { items: Claim[]; total: number };
    },
  });

  const items = data?.items || [];

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2">
            <FileSearch className="w-6 h-6" /> Insurance Claims
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            Review, approve, or reject policyholder claims. Approved payouts are credited instantly to user wallets.
          </p>
        </div>
        <button onClick={() => { refetch(); qc.invalidateQueries({ queryKey: ["claims-stats"] }); }} className="btn-ghost gap-2 text-sm">
          <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      {/* Stats */}
      {stats ? (
        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3">
          <Stat label="Total claims" value={stats.total} cls="from-slate-500 to-slate-700" Icon={FileText} />
          <Stat label="Pending" value={stats.pending} cls="from-amber-400 to-orange-500" Icon={Clock} />
          <Stat label="Approved" value={stats.approved} cls="from-emerald-500 to-emerald-600" Icon={CheckCircle2} />
          <Stat label="Rejected" value={stats.rejected} cls="from-red-500 to-rose-600" Icon={XCircle} />
          <Stat label="Total payout" value={fmtCurrency(stats.total_approved_payout || 0)} cls="from-sky-500 to-blue-600" Icon={IndianRupee} />
        </div>
      ) : null}

      {stats && stats.approval_rate >= 0 && (stats.approved + stats.rejected) > 0 ? (
        <div className="card flex items-center gap-3 bg-gradient-to-br from-emerald-50 to-sky-50 border-emerald-100">
          <TrendingUp className="w-5 h-5 text-emerald-600" />
          <div className="text-sm">
            <span className="font-extrabold text-slate-800">{stats.approval_rate}%</span>{" "}
            <span className="text-slate-600">approval rate across {stats.approved + stats.rejected} decided claims</span>
          </div>
        </div>
      ) : null}

      {/* Filters */}
      <div className="card flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-400" />
          <input
            className="input"
            placeholder="Search by claim ID, user, email, mobile, plan…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select className="input max-w-[180px]" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="submitted">Submitted</option>
          <option value="under_review">Under Review</option>
          <option value="info_requested">Info Requested</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
        </select>
        <select className="input max-w-[160px]" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="all">All types</option>
          <option value="health">Health</option>
          <option value="life">Life</option>
          <option value="motor">Motor</option>
          <option value="travel">Travel</option>
        </select>
      </div>

      {/* List */}
      <div className="card overflow-hidden">
        {items.length === 0 ? (
          <div className="text-slate-400 py-12 text-center">
            <FileText className="w-10 h-10 mx-auto opacity-40 mb-2" />
            <p className="font-bold">No claims match your filters</p>
            <p className="text-xs mt-1">Claims will appear here as users file them from the mobile app.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 uppercase font-bold border-b border-slate-200">
                  <th className="py-2 px-2">Claim ID</th>
                  <th className="py-2 px-2">User</th>
                  <th className="py-2 px-2">Plan / Type</th>
                  <th className="py-2 px-2 text-right">Amount</th>
                  <th className="py-2 px-2">Status</th>
                  <th className="py-2 px-2">Submitted</th>
                  <th className="py-2 px-2"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => {
                  const m = STATUS_META[c.status] || STATUS_META.submitted;
                  const TypeIcon = TYPE_ICON[c.plan_type] || Shield;
                  return (
                    <tr key={c.claim_id} className="border-b border-slate-100 hover:bg-slate-50 cursor-pointer" onClick={() => setOpenClaim(c.claim_id)}>
                      <td className="py-3 px-2 font-mono text-xs">{c.claim_id.slice(0, 16)}…</td>
                      <td className="py-3 px-2">
                        <p className="font-semibold text-slate-800">{c.user_name || "—"}</p>
                        <p className="text-xs text-slate-500">{c.user_mobile || c.user_email}</p>
                      </td>
                      <td className="py-3 px-2">
                        <p className="font-semibold text-slate-800 max-w-[220px] truncate flex items-center gap-1.5">
                          <TypeIcon className="w-3.5 h-3.5 text-slate-500" />
                          {c.plan_name}
                        </p>
                        <p className="text-xs text-slate-500 capitalize">{c.claim_type.replace(/_/g, " ")}</p>
                      </td>
                      <td className="py-3 px-2 text-right">
                        <p className="font-bold">{fmtCurrency(c.claim_amount)}</p>
                        {c.status === "approved" && c.approved_amount > 0 ? (
                          <p className="text-xs text-emerald-600 font-semibold">✓ {fmtCurrency(c.approved_amount)}</p>
                        ) : null}
                      </td>
                      <td className="py-3 px-2">
                        <span className={`badge ${m.cls} border`}>
                          <m.Icon className="w-3 h-3 inline mr-1" /> {m.label}
                        </span>
                      </td>
                      <td className="py-3 px-2 text-xs text-slate-500">{fmtDate(c.created_at)}</td>
                      <td className="py-3 px-2 text-right">
                        <ChevronRight className="w-4 h-4 text-slate-400" />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {openClaim ? (
        <ClaimDrawer
          claimId={openClaim}
          canDecide={!!canDecide}
          onClose={() => setOpenClaim(null)}
          onChanged={() => { qc.invalidateQueries({ queryKey: ["claims-list"] }); qc.invalidateQueries({ queryKey: ["claims-stats"] }); }}
        />
      ) : null}
    </div>
  );
}

function Stat({ label, value, cls, Icon }: { label: string; value: any; cls: string; Icon: any }) {
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

function ClaimDrawer({ claimId, canDecide, onClose, onChanged }: {
  claimId: string; canDecide: boolean; onClose: () => void; onChanged: () => void;
}) {
  const [note, setNote] = useState("");
  const [approvedAmt, setApprovedAmt] = useState<string>("");
  const [action, setAction] = useState<"approve" | "reject" | "info" | "review" | null>(null);

  const { data: claim, isLoading, refetch } = useQuery({
    queryKey: ["claim", claimId],
    queryFn: async () => (await api.get(`/admin/insurance/claims/${claimId}`)).data as Claim,
  });

  useEffect(() => {
    if (claim) setApprovedAmt(String(claim.approved_amount > 0 ? claim.approved_amount : claim.claim_amount));
  }, [claim?.claim_id]);

  const approve = useMutation({
    mutationFn: async () => (await api.post(`/admin/insurance/claims/${claimId}/approve`, {
      admin_note: note,
      approved_amount: Number(approvedAmt) || claim?.claim_amount,
    })).data,
    onSuccess: () => { setNote(""); setAction(null); refetch(); onChanged(); },
  });
  const reject = useMutation({
    mutationFn: async () => (await api.post(`/admin/insurance/claims/${claimId}/reject`, { admin_note: note })).data,
    onSuccess: () => { setNote(""); setAction(null); refetch(); onChanged(); },
  });
  const requestInfo = useMutation({
    mutationFn: async () => (await api.post(`/admin/insurance/claims/${claimId}/request-info`, { admin_note: note })).data,
    onSuccess: () => { setNote(""); setAction(null); refetch(); onChanged(); },
  });
  const moveToReview = useMutation({
    mutationFn: async () => (await api.post(`/admin/insurance/claims/${claimId}/under-review`, { admin_note: note || "Moving to review queue" })).data,
    onSuccess: () => { setNote(""); setAction(null); refetch(); onChanged(); },
  });

  const m = claim ? STATUS_META[claim.status] : null;
  const TypeIcon = claim ? (TYPE_ICON[claim.plan_type] || Shield) : Shield;
  const isFinal = claim ? ["approved", "rejected"].includes(claim.status) : false;

  const submit = () => {
    if (!note.trim() || note.trim().length < 3) return;
    if (action === "approve") approve.mutate();
    else if (action === "reject") reject.mutate();
    else if (action === "info") requestInfo.mutate();
    else if (action === "review") moveToReview.mutate();
  };

  const busy = approve.isPending || reject.isPending || requestInfo.isPending || moveToReview.isPending;

  return (
    <div className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm flex items-stretch justify-end" onClick={onClose}>
      <div className="w-full max-w-2xl bg-white h-full overflow-y-auto shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="sticky top-0 bg-white border-b border-slate-200 px-5 py-4 flex items-center justify-between z-10">
          <div className="flex items-center gap-3 min-w-0">
            <FileSearch className="w-6 h-6 text-brand-navy shrink-0" />
            <div className="min-w-0">
              <p className="font-extrabold text-brand-navy truncate">Claim Details</p>
              <p className="text-xs font-mono text-slate-500 truncate">{claimId}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-100 rounded-lg"><X className="w-5 h-5" /></button>
        </div>

        {isLoading || !claim ? (
          <div className="p-10 text-center text-slate-400">Loading claim…</div>
        ) : (
          <div className="p-5 space-y-5">
            {/* Status banner */}
            {m ? (
              <div className={`rounded-2xl px-4 py-3 border ${m.cls} flex items-center gap-3`}>
                <m.Icon className="w-5 h-5" />
                <div className="flex-1">
                  <p className="font-extrabold">{m.label}</p>
                  {claim.decided_at ? (
                    <p className="text-xs opacity-80">Decided on {fmtDate(claim.decided_at)}</p>
                  ) : null}
                </div>
                {claim.status === "approved" && claim.approved_amount > 0 ? (
                  <p className="font-extrabold">{fmtCurrency(claim.approved_amount)}</p>
                ) : null}
              </div>
            ) : null}

            {/* User + Policy */}
            <div className="grid sm:grid-cols-2 gap-3">
              <Box title="Policyholder" Icon={UserIcon}>
                <Row k="Name" v={claim.user_name || "—"} />
                <Row k="Email" v={claim.user_email || "—"} />
                <Row k="Mobile" v={claim.user_mobile || "—"} mono />
                <Row k="User ID" v={claim.user_id} mono small />
              </Box>
              <Box title="Policy" Icon={TypeIcon}>
                <Row k="Plan" v={claim.plan_name} />
                <Row k="Type" v={claim.plan_type} cap />
                <Row k="Policy ID" v={claim.policy_id} mono small />
              </Box>
            </div>

            {/* Claim details */}
            <Box title="Claim Details" Icon={FileText}>
              <Row k="Type" v={claim.claim_type.replace(/_/g, " ")} cap />
              <Row k="Amount claimed" v={fmtCurrency(claim.claim_amount)} bold />
              {claim.incident_date ? <Row k="Incident date" v={claim.incident_date} /> : null}
              {claim.description ? (
                <div className="pt-2 mt-2 border-t border-slate-100">
                  <p className="text-[11px] font-bold text-slate-500 uppercase mb-1">Description</p>
                  <p className="text-sm text-slate-700 whitespace-pre-wrap">{claim.description}</p>
                </div>
              ) : null}
              {(claim.documents?.length || 0) > 0 ? (
                <div className="pt-2 mt-2 border-t border-slate-100">
                  <p className="text-[11px] font-bold text-slate-500 uppercase mb-2">Attachments ({claim.documents!.length})</p>
                  <div className="flex flex-wrap gap-2">
                    {claim.documents!.map((d, i) => (
                      <a
                        key={i}
                        href="#"
                        onClick={async (e) => {
                          e.preventDefault();
                          try {
                            const r = await api.get(`/admin/insurance/claims/${claimId}/document/${i}`);
                            const data = r.data as { name: string; mime: string; base64: string };
                            const win = window.open();
                            if (win && data.base64) {
                              if ((data.mime || "").startsWith("image/")) {
                                win.document.write(`<img src="data:${data.mime};base64,${data.base64}" />`);
                              } else {
                                win.document.write(`<iframe style="width:100%;height:100vh;border:0" src="data:${data.mime};base64,${data.base64}"></iframe>`);
                              }
                            }
                          } catch { /* noop */ }
                        }}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-semibold"
                      >
                        <Eye className="w-3.5 h-3.5" /> {d.name}
                      </a>
                    ))}
                  </div>
                </div>
              ) : null}
            </Box>

            {/* Last admin note */}
            {claim.admin_note ? (
              <Box title="Last Admin Note" Icon={MessageSquareWarning}>
                <p className="text-sm text-slate-700 whitespace-pre-wrap">{claim.admin_note}</p>
              </Box>
            ) : null}

            {/* History timeline */}
            <Box title="Claim History" Icon={HistoryIcon}>
              <div className="space-y-3">
                {(claim.history || []).map((h, i) => {
                  const meta = STATUS_META[h.event] || { label: h.event, cls: "bg-slate-100 text-slate-700 border-slate-200", Icon: FileText };
                  return (
                    <div key={i} className="flex gap-3">
                      <div className="flex flex-col items-center">
                        <div className={`w-7 h-7 rounded-full ${meta.cls} border flex items-center justify-center`}>
                          <meta.Icon className="w-3.5 h-3.5" />
                        </div>
                        {i < (claim.history || []).length - 1 ? <div className="flex-1 w-px bg-slate-200 my-1"></div> : null}
                      </div>
                      <div className="flex-1 pb-3">
                        <p className="font-bold text-sm text-slate-800 capitalize">{meta.label}</p>
                        <p className="text-[11px] text-slate-500">
                          by <span className="capitalize">{h.by}</span>
                          {h.by === "admin" ? ` (${h.by_id?.slice(0, 14)}…)` : ""} · {fmtDate(h.at)}
                        </p>
                        {h.note ? <p className="text-xs text-slate-600 mt-0.5 italic">"{h.note}"</p> : null}
                        {h.approved_amount ? <p className="text-xs text-emerald-600 font-semibold mt-0.5">Payout: {fmtCurrency(h.approved_amount)}</p> : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            </Box>

            {/* Action panel */}
            {!isFinal && canDecide ? (
              <div className="card border-2 border-brand-primary/20 bg-sky-50/40 space-y-3">
                <p className="font-extrabold text-brand-navy">Take action</p>
                <div className="flex gap-2 flex-wrap">
                  {claim.status === "submitted" ? (
                    <ActionBtn onClick={() => setAction("review")} active={action === "review"} Icon={Clock} label="Move to Review" cls="bg-sky-600" />
                  ) : null}
                  <ActionBtn onClick={() => setAction("approve")} active={action === "approve"} Icon={CheckCircle2} label="Approve" cls="bg-emerald-600" />
                  <ActionBtn onClick={() => setAction("reject")} active={action === "reject"} Icon={XCircle} label="Reject" cls="bg-red-600" />
                  <ActionBtn onClick={() => setAction("info")} active={action === "info"} Icon={MessageSquareWarning} label="Request Info" cls="bg-amber-600" />
                </div>

                {action ? (
                  <div className="space-y-2 pt-2 border-t border-slate-200">
                    {action === "approve" ? (
                      <div>
                        <label className="text-xs font-bold text-slate-600">Approved amount (₹)</label>
                        <input
                          type="number" min={1} max={claim.claim_amount}
                          className="input mt-1"
                          value={approvedAmt}
                          onChange={(e) => setApprovedAmt(e.target.value)}
                        />
                        <p className="text-[11px] text-slate-500 mt-1">Claimed: {fmtCurrency(claim.claim_amount)}. You can approve up to this amount.</p>
                      </div>
                    ) : null}
                    <div>
                      <label className="text-xs font-bold text-slate-600">
                        Admin note <span className="text-red-500">*</span>
                      </label>
                      <textarea
                        className="input mt-1 min-h-[80px]"
                        placeholder={
                          action === "approve" ? "e.g. Documents verified. Payout approved." :
                          action === "reject" ? "e.g. Hospital not in network. Out-of-policy expense." :
                          action === "info" ? "e.g. Please share the discharge summary and original bills." :
                          "Why move this to review?"
                        }
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                      />
                      <p className="text-[11px] text-slate-500 mt-1">
                        This note is shown to the user{action === "approve" || action === "reject" ? " and is permanent" : ""}. Min 3 characters.
                      </p>
                    </div>
                    <div className="flex justify-end gap-2">
                      <button onClick={() => setAction(null)} className="btn-ghost text-sm">Cancel</button>
                      <button
                        onClick={submit}
                        disabled={busy || note.trim().length < 3}
                        className="btn-primary text-sm gap-2"
                      >
                        {busy ? "Saving…" : action === "approve" ? "Approve & Credit Wallet" : action === "reject" ? "Reject Claim" : action === "info" ? "Request Info" : "Move to Review"}
                      </button>
                    </div>
                    {(approve.isError || reject.isError || requestInfo.isError || moveToReview.isError) ? (
                      <p className="text-xs text-red-700">Action failed. Check role permissions and try again.</p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : !canDecide ? (
              <div className="card bg-amber-50 border-amber-200 border flex items-start gap-3">
                <AlertTriangle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                <div className="text-sm text-amber-900">
                  <p className="font-bold">View-only access</p>
                  <p>Only super_admin and admin roles can approve, reject, or request info on claims.</p>
                </div>
              </div>
            ) : (
              <div className="card bg-slate-50 border-slate-200 border text-sm text-slate-600">
                This claim has reached a final decision and cannot be changed.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Box({ title, Icon, children }: { title: string; Icon: any; children: any }) {
  return (
    <div className="card space-y-1.5">
      <p className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5"><Icon className="w-3.5 h-3.5" />{title}</p>
      <div className="space-y-1 pt-1">{children}</div>
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

function ActionBtn({ onClick, active, Icon, label, cls }: { onClick: () => void; active: boolean; Icon: any; label: string; cls: string }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-bold border transition ${
        active ? `text-white ${cls} border-transparent shadow` : "bg-white text-slate-700 border-slate-200 hover:border-slate-300"
      }`}
    >
      <Icon className="w-4 h-4" /> {label}
    </button>
  );
}

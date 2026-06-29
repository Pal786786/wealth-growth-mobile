import { useEffect, useMemo, useState } from "react";
import { api, inr } from "../lib/api";
import { ShieldCheck, ShieldAlert, Clock, FileCheck2, Users, Download, Search, X, RefreshCw, AlertTriangle, CheckCircle2, XCircle, Unlock, MessageSquare, ChevronRight, FileWarning, TrendingUp } from "lucide-react";

type Profile = {
  user_id: string; status: string; locked: boolean; completion: number; risk: "low"|"medium"|"high";
  steps: any; docs: any; submitted_at?: string; approved_at?: string; rejected_at?: string;
  expires_at?: string; reject_reason?: string; reupload_fields?: string[]; missing: string[];
  user?: { full_name?: string; email?: string; mobile?: string };
  admin_notes?: any[]; _dup_flags?: string[];
};
type Dash = { stats: any; weekly: { date: string; submitted: number; approved: number }[] };
type Detail = { profile: Profile; user: any; timeline: any[]; documents: any[] };

const STATUS_TONE: Record<string,string> = {
  not_started: "bg-slate-100 text-slate-600",
  in_progress: "bg-blue-50 text-blue-700",
  submitted: "bg-amber-50 text-amber-700",
  under_review: "bg-amber-50 text-amber-700",
  approved: "bg-emerald-50 text-emerald-700",
  rejected: "bg-rose-50 text-rose-700",
  reupload_required: "bg-orange-50 text-orange-700",
};
const RISK_TONE: Record<string,string> = {
  low: "bg-emerald-50 text-emerald-700",
  medium: "bg-amber-50 text-amber-700",
  high: "bg-rose-50 text-rose-700",
};

export default function AdminKYCDashboard() {
  const [tab, setTab] = useState<"queue"|"dashboard"|"duplicates">("dashboard");
  const [dash, setDash] = useState<Dash|null>(null);
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState({ q: "", status: "all", risk: "all" });
  const [detail, setDetail] = useState<Detail|null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [dups, setDups] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const queryStr = useMemo(() => {
    const p = new URLSearchParams();
    Object.entries(filters).forEach(([k,v]) => { if (v && v !== "all") p.set(k, v as string); });
    return p.toString();
  }, [filters]);

  const loadDash = async () => {
    const { data } = await api.get("/admin/kyc/dashboard");
    setDash(data);
  };
  const loadList = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/kyc?limit=100&${queryStr}`);
      setProfiles(data.items || []); setTotal(data.total || 0);
    } finally { setLoading(false); }
  };
  const loadDups = async () => {
    const { data } = await api.get("/admin/kyc/duplicates");
    setDups(data);
  };
  const openDetail = async (uid: string) => {
    const { data } = await api.get(`/admin/kyc/${uid}`);
    setDetail(data);
  };

  useEffect(() => {
    if (tab === "dashboard") loadDash();
    if (tab === "queue") loadList();
    if (tab === "duplicates") loadDups();
     
  }, [tab, queryStr]);

  const exportCSV = () => {
    const t = localStorage.getItem("mfb_admin_token");
    fetch("/api/admin/kyc/export.csv", { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.blob()).then(b => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = `MFB_KYC_${new Date().toISOString().slice(0,10)}.csv`;
        a.click();
      });
  };
  const downloadZip = (uid: string) => {
    const t = localStorage.getItem("mfb_admin_token");
    fetch(`/api/admin/kyc/${uid}/documents.zip`, { headers: { Authorization: `Bearer ${t}` } })
      .then(r => r.blob()).then(b => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(b);
        a.download = `KYC_${uid}.zip`;
        a.click();
      });
  };

  const approve = async (uid: string) => {
    if (!confirm("Approve this KYC?")) return;
    await api.post(`/admin/kyc/${uid}/approve`); loadList(); loadDash(); if (detail) openDetail(uid);
  };
  const reject = async (uid: string) => {
    const reason = prompt("Reason for rejection:");
    if (!reason) return;
    await api.post(`/admin/kyc/${uid}/reject`, { reason }); loadList(); loadDash(); if (detail) openDetail(uid);
  };
  const requestReupload = async (uid: string) => {
    const fieldsStr = prompt("Fields to re-upload (comma-separated, e.g. pan,selfie):");
    if (!fieldsStr) return;
    const note = prompt("Note for user (optional):") || "";
    const fields = fieldsStr.split(",").map(s => s.trim()).filter(Boolean);
    await api.post(`/admin/kyc/${uid}/request-reupload`, { fields, note });
    loadList(); if (detail) openDetail(uid);
  };
  const unlock = async (uid: string) => {
    if (!confirm("Unlock this approved KYC for re-submission?")) return;
    await api.post(`/admin/kyc/${uid}/unlock`); loadList(); if (detail) openDetail(uid);
  };
  const addNote = async (uid: string) => {
    const note = prompt("Internal note (visible to admins only):");
    if (!note) return;
    await api.post(`/admin/kyc/${uid}/note`, { note }); if (detail) openDetail(uid);
  };
  const bulkAction = async (action: "approve"|"reject") => {
    if (!selected.length) return;
    let reason = "Bulk action";
    if (action === "reject") {
      reason = prompt("Bulk reject reason:") || "";
      if (!reason) return;
    }
    if (!confirm(`${action.toUpperCase()} ${selected.length} KYC profiles?`)) return;
    await api.post("/admin/kyc/bulk", { action, user_ids: selected, reason });
    setSelected([]); loadList(); loadDash();
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <ShieldCheck className="w-6 h-6 text-amber-500" /> KYC & Compliance
          </h1>
          <p className="text-slate-500 text-sm mt-1">7-step verification · Risk scoring · Duplicate detection · Audit timeline</p>
        </div>
        <button onClick={exportCSV} className="text-sm px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 flex items-center gap-1">
          <Download className="w-3.5 h-3.5" /> Export CSV
        </button>
      </div>

      <div className="flex gap-1 border-b border-slate-200 mb-6">
        {(["dashboard","queue","duplicates"] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium capitalize border-b-2 transition ${tab===t ? "border-amber-500 text-amber-600" : "border-transparent text-slate-500 hover:text-slate-800"}`}>
            {t === "queue" ? "Review Queue" : t === "dashboard" ? "Dashboard" : "Duplicates"}
          </button>
        ))}
      </div>

      {tab === "dashboard" && dash && (
        <div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <KPI icon={Clock} label="Pending Review" value={dash.stats.under_review + dash.stats.submitted} tone="amber" />
            <KPI icon={CheckCircle2} label="Approved" value={dash.stats.approved} tone="emerald" />
            <KPI icon={XCircle} label="Rejected" value={dash.stats.rejected} tone="rose" />
            <KPI icon={TrendingUp} label="Submissions Today" value={dash.stats.today_submissions} tone="sky" />
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <KPI icon={Users} label="Total Profiles" value={dash.stats.total} tone="slate" />
            <KPI icon={FileWarning} label="In Progress" value={dash.stats.in_progress} tone="sky" />
            <KPI icon={AlertTriangle} label="High Risk" value={dash.stats.high_risk} tone="rose" />
            <KPI icon={FileCheck2} label="Re-upload" value={dash.stats.reupload} tone="amber" />
          </div>
          <div className="bg-white border border-slate-200 rounded-xl p-5">
            <h3 className="font-bold mb-4">Weekly Trend (last 7 days)</h3>
            <Bars series={dash.weekly} />
            <div className="flex items-center gap-4 mt-3 text-xs text-slate-500">
              <span className="flex items-center gap-1"><span className="w-3 h-3 bg-amber-400 rounded" /> Submissions</span>
              <span className="flex items-center gap-1"><span className="w-3 h-3 bg-emerald-500 rounded" /> Approvals</span>
            </div>
          </div>
        </div>
      )}

      {tab === "queue" && (
        <div>
          <div className="bg-white border border-slate-200 rounded-xl p-4 mb-4 grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="col-span-2 relative">
              <Search className="absolute left-3 top-2.5 w-4 h-4 text-slate-400" />
              <input value={filters.q} onChange={e => setFilters({...filters, q: e.target.value})} placeholder="Search user_id, name, PAN"
                className="w-full border border-slate-200 rounded-lg pl-9 pr-3 py-2 text-sm focus:border-amber-400 outline-none" />
            </div>
            <select value={filters.status} onChange={e => setFilters({...filters, status: e.target.value})}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm">
              <option value="all">All statuses</option>
              <option value="under_review">Under Review</option>
              <option value="in_progress">In Progress</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="reupload_required">Re-upload Required</option>
            </select>
            <select value={filters.risk} onChange={e => setFilters({...filters, risk: e.target.value})}
              className="border border-slate-200 rounded-lg px-3 py-2 text-sm">
              <option value="all">All risk</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </div>

          <div className="flex items-center justify-between mb-3">
            <div className="text-sm text-slate-600">{loading ? "Loading…" : <><b>{total}</b> KYC profiles · {selected.length} selected</>}</div>
            <div className="flex gap-2">
              {selected.length > 0 && (<>
                <button onClick={() => bulkAction("approve")} className="text-sm px-3 py-1.5 bg-emerald-500 text-white rounded-lg shadow-sm hover:bg-emerald-600">Bulk Approve ({selected.length})</button>
                <button onClick={() => bulkAction("reject")} className="text-sm px-3 py-1.5 bg-rose-500 text-white rounded-lg shadow-sm hover:bg-rose-600">Bulk Reject</button>
              </>)}
              <button onClick={() => setFilters({ q:"", status:"all", risk:"all" })} className="text-sm px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 flex items-center gap-1"><X className="w-3.5 h-3.5" /> Clear</button>
              <button onClick={loadList} className="text-sm px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 flex items-center gap-1"><RefreshCw className="w-3.5 h-3.5" /> Refresh</button>
            </div>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600 text-xs uppercase">
                <tr>
                  <th className="p-3 w-8"><input type="checkbox" checked={selected.length>0 && selected.length===profiles.length} onChange={e => setSelected(e.target.checked ? profiles.map(p=>p.user_id) : [])} /></th>
                  <th className="p-3 text-left">User</th>
                  <th className="p-3 text-left">Status</th>
                  <th className="p-3 text-left">Progress</th>
                  <th className="p-3 text-left">Risk</th>
                  <th className="p-3 text-left">Submitted</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map(p => (
                  <tr key={p.user_id} className="border-t border-slate-100 hover:bg-slate-50 cursor-pointer" onClick={() => openDetail(p.user_id)}>
                    <td className="p-3" onClick={e=>e.stopPropagation()}>
                      <input type="checkbox" checked={selected.includes(p.user_id)} onChange={e => setSelected(e.target.checked ? [...selected, p.user_id] : selected.filter(x=>x!==p.user_id))} />
                    </td>
                    <td className="p-3">
                      <div className="font-semibold">{p.user?.full_name || p.steps?.["1"]?.full_name || "Unnamed"}</div>
                      <div className="text-xs text-slate-500 font-mono">{p.user_id.slice(0,18)}… · {p.user?.mobile || p.user?.email}</div>
                    </td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_TONE[p.status] || "bg-slate-100 text-slate-600"}`}>
                        {p.status.replace(/_/g, " ")}
                      </span>
                      {p.locked && <span className="ml-1 text-[10px] text-slate-400">🔒</span>}
                    </td>
                    <td className="p-3">
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full bg-gradient-to-r from-amber-400 to-amber-600" style={{ width: `${p.completion}%` }} />
                        </div>
                        <span className="text-xs font-semibold text-slate-600">{p.completion}%</span>
                      </div>
                    </td>
                    <td className="p-3"><span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${RISK_TONE[p.risk]}`}>{p.risk}</span></td>
                    <td className="p-3 text-xs text-slate-500">{p.submitted_at ? new Date(p.submitted_at).toLocaleDateString("en-IN") : "—"}</td>
                    <td className="p-3 text-right" onClick={e=>e.stopPropagation()}>
                      <button onClick={() => openDetail(p.user_id)} className="text-amber-600 hover:underline text-xs font-semibold">Open <ChevronRight className="w-3 h-3 inline" /></button>
                    </td>
                  </tr>
                ))}
                {!profiles.length && !loading && (
                  <tr><td colSpan={7} className="p-8 text-center text-slate-400">No KYC profiles match these filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "duplicates" && dups && (
        <div className="space-y-5">
          <DupSection title="Duplicate PAN" items={dups.pan} keyField="pan" />
          <DupSection title="Duplicate Aadhaar" items={dups.aadhaar} keyField="aadhaar" />
          <DupSection title="Duplicate Mobile" items={dups.mobile} keyField="mobile" />
          <DupSection title="Duplicate Email" items={dups.email} keyField="email" />
        </div>
      )}

      {/* Detail Drawer */}
      {detail && (
        <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-stretch justify-end" onClick={() => setDetail(null)}>
          <div className="w-full max-w-2xl bg-white shadow-2xl overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="sticky top-0 bg-gradient-to-r from-slate-900 to-slate-800 text-white p-5 flex items-center justify-between">
              <div>
                <div className="text-xs text-amber-300 font-semibold uppercase tracking-wider">KYC Profile</div>
                <h2 className="text-xl font-bold">{detail.user?.full_name || detail.profile.user_id}</h2>
                <div className="text-xs text-slate-300 mt-0.5">{detail.user?.email} · {detail.user?.mobile}</div>
              </div>
              <button onClick={() => setDetail(null)} className="p-2 hover:bg-white/10 rounded-lg"><X className="w-5 h-5" /></button>
            </div>

            <div className="p-5 space-y-5">
              <div className="flex items-center gap-3 flex-wrap">
                <span className={`px-3 py-1 rounded-full text-sm font-semibold ${STATUS_TONE[detail.profile.status]}`}>{detail.profile.status.replace(/_/g," ")}</span>
                <span className={`px-3 py-1 rounded-full text-sm font-semibold ${RISK_TONE[detail.profile.risk]}`}>Risk: {detail.profile.risk}</span>
                {detail.profile.locked && <span className="px-3 py-1 rounded-full text-sm bg-slate-100 text-slate-700">🔒 Locked</span>}
                <span className="text-sm text-slate-500">{detail.profile.completion}% complete</span>
              </div>

              {detail.profile.reject_reason && (
                <div className="bg-rose-50 border border-rose-200 p-3 rounded-lg text-sm text-rose-700">
                  <b>Rejection reason:</b> {detail.profile.reject_reason}
                </div>
              )}
              {(detail.profile._dup_flags?.length ?? 0) > 0 && (
                <div className="bg-amber-50 border border-amber-200 p-3 rounded-lg text-sm text-amber-800">
                  <b>⚠️ Duplicate flags:</b> {detail.profile._dup_flags!.join(", ")}
                </div>
              )}

              {/* Actions */}
              <div className="flex flex-wrap gap-2">
                {detail.profile.status !== "approved" && (
                  <button onClick={() => approve(detail.profile.user_id)} className="px-4 py-2 bg-emerald-500 text-white rounded-lg text-sm font-semibold flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4" /> Approve</button>
                )}
                {detail.profile.status !== "rejected" && (
                  <button onClick={() => reject(detail.profile.user_id)} className="px-4 py-2 bg-rose-500 text-white rounded-lg text-sm font-semibold flex items-center gap-1.5"><XCircle className="w-4 h-4" /> Reject</button>
                )}
                <button onClick={() => requestReupload(detail.profile.user_id)} className="px-4 py-2 border border-amber-300 text-amber-700 rounded-lg text-sm font-semibold flex items-center gap-1.5"><FileWarning className="w-4 h-4" /> Request Re-upload</button>
                {detail.profile.locked && (
                  <button onClick={() => unlock(detail.profile.user_id)} className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm font-semibold flex items-center gap-1.5"><Unlock className="w-4 h-4" /> Unlock for Re-KYC</button>
                )}
                <button onClick={() => addNote(detail.profile.user_id)} className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm font-semibold flex items-center gap-1.5"><MessageSquare className="w-4 h-4" /> Add Note</button>
                <button onClick={() => downloadZip(detail.profile.user_id)} className="px-4 py-2 border border-slate-300 text-slate-700 rounded-lg text-sm font-semibold flex items-center gap-1.5"><Download className="w-4 h-4" /> Documents (ZIP)</button>
              </div>

              {/* Step Data */}
              <div className="space-y-3">
                <h3 className="font-bold text-slate-700">Submitted Information</h3>
                {[1,2,3,4,5,6,7].map(i => {
                  const s = detail.profile.steps?.[String(i)];
                  const titles: Record<number,string> = {1:"Personal Details",2:"Address",3:"PAN Verification",4:"Aadhaar Verification",5:"Selfie",6:"Bank Account",7:"Nominee"};
                  return (
                    <details key={i} className="border border-slate-200 rounded-lg overflow-hidden" open={!!s}>
                      <summary className="px-4 py-3 bg-slate-50 cursor-pointer font-semibold text-sm flex items-center justify-between">
                        <span>Step {i} · {titles[i]}</span>
                        {s ? <CheckCircle2 className="w-4 h-4 text-emerald-500" /> : <Clock className="w-4 h-4 text-slate-400" />}
                      </summary>
                      {s && (
                        <div className="p-4 text-xs grid grid-cols-2 gap-2">
                          {Object.entries(s).map(([k,v]: any) => (
                            <div key={k}><span className="text-slate-500">{k}:</span> <b className="text-slate-800">{String(v).slice(0,40)}</b></div>
                          ))}
                        </div>
                      )}
                    </details>
                  );
                })}
              </div>

              {/* Admin Notes */}
              {(detail.profile.admin_notes?.length ?? 0) > 0 && (
                <div>
                  <h3 className="font-bold text-slate-700 mb-2">Internal Notes</h3>
                  <div className="space-y-2">
                    {detail.profile.admin_notes!.map((n: any) => (
                      <div key={n.note_id} className="bg-amber-50 border border-amber-100 p-3 rounded-lg">
                        <p className="text-sm">{n.text}</p>
                        <p className="text-[10px] text-slate-500 mt-1">by {n.by} · {new Date(n.at).toLocaleString("en-IN")}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Timeline */}
              <div>
                <h3 className="font-bold text-slate-700 mb-2">Activity Timeline ({detail.timeline.length})</h3>
                <div className="space-y-1.5">
                  {detail.timeline.map((e: any) => (
                    <div key={e.event_id} className="flex items-start gap-3 text-sm py-1.5 border-b border-slate-100">
                      <div className="w-2 h-2 rounded-full bg-amber-400 mt-1.5 shrink-0" />
                      <div className="flex-1">
                        <div className="font-semibold text-slate-800">{e.event.replace(/_/g," ").replace(/\./g, " → ")}</div>
                        <div className="text-xs text-slate-500">by {e.actor} · {new Date(e.at).toLocaleString("en-IN")}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function KPI({ icon: Icon, label, value, tone }: { icon: any; label: string; value: any; tone: string }) {
  const t: any = { amber: "bg-amber-50 border-amber-100 text-amber-700", emerald:"bg-emerald-50 border-emerald-100 text-emerald-700", rose:"bg-rose-50 border-rose-100 text-rose-700", sky:"bg-sky-50 border-sky-100 text-sky-700", slate:"bg-slate-50 border-slate-100 text-slate-700" };
  return (
    <div className={`p-5 border rounded-xl ${t[tone] || t.slate}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-semibold uppercase tracking-wider opacity-80">{label}</span>
        <Icon className="w-5 h-5 opacity-60" />
      </div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}

function Bars({ series }: { series: { date: string; submitted: number; approved: number }[] }) {
  const max = Math.max(1, ...series.flatMap(s => [s.submitted, s.approved]));
  return (
    <div className="flex items-end gap-3 h-40">
      {series.map(s => (
        <div key={s.date} className="flex-1 flex flex-col items-center gap-1">
          <div className="flex items-end gap-1 w-full" style={{ height: 130 }}>
            <div className="flex-1 bg-amber-400 rounded-t" style={{ height: `${(s.submitted / max) * 100}%` }} title={`${s.submitted} submitted`} />
            <div className="flex-1 bg-emerald-500 rounded-t" style={{ height: `${(s.approved / max) * 100}%` }} title={`${s.approved} approved`} />
          </div>
          <span className="text-[10px] text-slate-500">{s.date.slice(5)}</span>
        </div>
      ))}
    </div>
  );
}

function DupSection({ title, items, keyField }: { title: string; items: any[]; keyField: string }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="px-4 py-3 bg-slate-50 font-bold border-b border-slate-100 flex items-center gap-2">
        <AlertTriangle className="w-4 h-4 text-amber-500" /> {title} <span className="text-slate-400 font-normal">({items.length})</span>
      </div>
      {items.length === 0 ? (
        <p className="p-6 text-center text-slate-400 text-sm">No duplicates found 🎉</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr><th className="p-3 text-left">Value</th><th className="p-3 text-left">Affected Users</th><th className="p-3 text-center">Count</th></tr>
          </thead>
          <tbody>
            {items.map((it, i) => (
              <tr key={i} className="border-t border-slate-100">
                <td className="p-3 font-mono text-xs">{it[keyField]}</td>
                <td className="p-3 font-mono text-xs text-slate-600">{(it.users || []).slice(0,3).join(", ")}{it.users?.length > 3 ? `… (+${it.users.length-3})` : ""}</td>
                <td className="p-3 text-center font-bold text-rose-600">{it.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

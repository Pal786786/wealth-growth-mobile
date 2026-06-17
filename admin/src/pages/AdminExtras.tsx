import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate, inr } from "../lib/api";
import { Send, Trash2, Plus, Save, Download, CheckCircle2 } from "lucide-react";

// ===================== Notifications =====================
export function Notifications() {
  const qc = useQueryClient();
  const [title, setTitle] = useState(""); const [body, setBody] = useState("");
  const [target, setTarget] = useState<"all" | "segment">("all");
  const [segment, setSegment] = useState("active");
  const [msg, setMsg] = useState("");
  const { data: history } = useQuery({ queryKey: ["notif-hist"], queryFn: async () => (await api.get("/admin/notifications/history")).data });
  const send = useMutation({
    mutationFn: () => api.post("/admin/notifications/send", { title, body, target, segment }),
    onSuccess: (r) => { setMsg(`Sent to ${r.data.recipients} users`); setTitle(""); setBody(""); qc.invalidateQueries({ queryKey: ["notif-hist"] }); },
    onError: (e: any) => setMsg(e?.response?.data?.detail || "Failed"),
  });
  return (
    <div className="space-y-4 max-w-4xl">
      <div><h2 className="text-2xl font-extrabold text-brand-navy">Notification Center</h2><p className="text-sm text-slate-500">Broadcast to all users or a segment.</p></div>
      <div className="card space-y-3">
        <input className="input" placeholder="Title (e.g. SIP installment due)" value={title} onChange={(e) => setTitle(e.target.value)} />
        <textarea className="input min-h-[90px]" placeholder="Message body…" value={body} onChange={(e) => setBody(e.target.value)} />
        <div className="flex items-center gap-3 flex-wrap">
          <select className="input !w-auto" value={target} onChange={(e) => setTarget(e.target.value as any)}>
            <option value="all">All users</option><option value="segment">Segment</option>
          </select>
          {target === "segment" ? (
            <select className="input !w-auto" value={segment} onChange={(e) => setSegment(e.target.value)}>
              <option value="active">Active users</option>
              <option value="kyc_pending">KYC pending</option>
              <option value="investors">Investors only</option>
            </select>
          ) : null}
          <button disabled={!title || !body || send.isPending} onClick={() => send.mutate()} className="btn-primary gap-2">
            <Send className="w-4 h-4" /> {send.isPending ? "Sending…" : "Send"}
          </button>
        </div>
        {msg ? <p className="text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">{msg}</p> : null}
      </div>
      <div className="card">
        <h3 className="font-extrabold mb-3">Recent broadcasts</h3>
        <div className="space-y-2">
          {history?.length === 0 ? <p className="text-slate-400 text-sm">No broadcasts yet.</p> :
            history?.map((h: any) => (
              <div key={h.batch_id} className="border border-slate-200 rounded-xl p-3 flex justify-between items-start">
                <div><p className="font-bold">{h.title}</p><p className="text-sm text-slate-500">{h.body}</p></div>
                <div className="text-right text-xs text-slate-500"><span className="badge badge-info">{h.recipients} sent</span><br />{fmtDate(h.sent_at)}</div>
              </div>
            ))}
        </div>
      </div>
    </div>
  );
}

// ===================== Investment Manager =====================
export function InvestmentManager() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"funds" | "fds" | "govt" | "gold">("funds");
  const tabs = [{ k: "funds", l: "Mutual Funds" }, { k: "fds", l: "Fixed Deposits" }, { k: "govt", l: "Govt Schemes" }, { k: "gold", l: "Gold Rate" }] as const;
  return (
    <div className="space-y-4">
      <div><h2 className="text-2xl font-extrabold text-brand-navy">Investment Manager</h2><p className="text-sm text-slate-500">Curate the products users invest in.</p></div>
      <div className="flex bg-slate-100 rounded-xl p-1 w-fit">
        {tabs.map((t) => (
          <button key={t.k} onClick={() => setTab(t.k as any)} className={`px-4 py-2 rounded-lg text-sm font-semibold ${tab === t.k ? "bg-white shadow text-brand-navy" : "text-slate-500"}`}>{t.l}</button>
        ))}
      </div>
      {tab === "funds" && <FundsEditor qc={qc} />}
      {tab === "fds" && <FDsEditor qc={qc} />}
      {tab === "govt" && <GovtEditor qc={qc} />}
      {tab === "gold" && <GoldEditor />}
    </div>
  );
}

function CrudList<T extends { id?: string }>({ title, items, fields, onSave, onDelete, isLoading }: any) {
  const [editing, setEditing] = useState<any | null>(null);
  return (
    <div className="card">
      <div className="flex justify-between mb-3">
        <h3 className="font-extrabold">{title}</h3>
        <button onClick={() => setEditing(fields.reduce((a: any, f: any) => ({ ...a, [f.key]: f.default ?? "" }), {}))} className="btn-primary !py-1.5 !px-3 !text-xs gap-1"><Plus className="w-3.5 h-3.5" /> Add</button>
      </div>
      {isLoading ? <p className="text-slate-400">Loading…</p> : (
        <div className="space-y-2">
          {items?.map((it: any) => (
            <div key={it.id} className="border border-slate-200 rounded-xl p-3 flex justify-between items-center">
              <div>
                <p className="font-bold">{it.name}</p>
                <p className="text-xs text-slate-500">{fields.slice(1).map((f: any) => `${f.label}: ${it[f.key]}`).join(" · ")}</p>
              </div>
              <div className="flex gap-2">
                <button onClick={() => setEditing(it)} className="btn-ghost !py-1.5 !px-3 !text-xs">Edit</button>
                <button onClick={() => onDelete(it.id)} className="btn-ghost !py-1.5 !px-3 !text-xs !text-red-600 !border-red-200 hover:!bg-red-50"><Trash2 className="w-3.5 h-3.5" /></button>
              </div>
            </div>
          ))}
        </div>
      )}
      {editing ? (
        <div className="mt-4 border border-brand-primary/30 bg-sky-50/50 rounded-xl p-4 space-y-3">
          <p className="font-bold">{editing.id ? "Edit" : "New"}</p>
          {fields.map((f: any) => (
            <div key={f.key}>
              <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">{f.label}</label>
              <input type={f.type || "text"} className="input mt-1" value={editing[f.key] ?? ""} onChange={(e) => setEditing({ ...editing, [f.key]: f.type === "number" ? Number(e.target.value) : e.target.value })} />
            </div>
          ))}
          <div className="flex gap-2">
            <button onClick={() => { onSave(editing); setEditing(null); }} className="btn-primary gap-1"><Save className="w-4 h-4" /> Save</button>
            <button onClick={() => setEditing(null)} className="btn-ghost">Cancel</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function FundsEditor({ qc }: any) {
  const { data, isLoading } = useQuery({ queryKey: ["admin-funds"], queryFn: async () => (await api.get("/admin/invest/funds")).data });
  const save = useMutation({ mutationFn: (d: any) => api.post("/admin/invest/funds", d), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-funds"] }) });
  const del = useMutation({ mutationFn: (id: string) => api.delete(`/admin/invest/funds/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-funds"] }) });
  return <CrudList title="Mutual Funds" items={data} isLoading={isLoading} onSave={save.mutate} onDelete={del.mutate}
    fields={[{ key: "name", label: "Name" }, { key: "category", label: "Category" }, { key: "nav", label: "NAV", type: "number" }, { key: "returns_1y", label: "1Y Returns %", type: "number" }, { key: "risk", label: "Risk" }]} />;
}
function FDsEditor({ qc }: any) {
  const { data, isLoading } = useQuery({ queryKey: ["admin-fds"], queryFn: async () => (await api.get("/admin/invest/fds")).data });
  const save = useMutation({ mutationFn: (d: any) => api.post("/admin/invest/fds", d), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-fds"] }) });
  const del = useMutation({ mutationFn: (id: string) => api.delete(`/admin/invest/fds/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-fds"] }) });
  return <CrudList title="Fixed Deposits" items={data} isLoading={isLoading} onSave={save.mutate} onDelete={del.mutate}
    fields={[{ key: "name", label: "Bank/Name" }, { key: "tenure_months", label: "Tenure (months)", type: "number" }, { key: "interest_rate", label: "Rate %", type: "number" }]} />;
}
function GovtEditor({ qc }: any) {
  const { data, isLoading } = useQuery({ queryKey: ["admin-govt"], queryFn: async () => (await api.get("/admin/invest/govt")).data });
  const save = useMutation({ mutationFn: (d: any) => api.post("/admin/invest/govt", d), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-govt"] }) });
  const del = useMutation({ mutationFn: (id: string) => api.delete(`/admin/invest/govt/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-govt"] }) });
  return <CrudList title="Government Schemes" items={data} isLoading={isLoading} onSave={save.mutate} onDelete={del.mutate}
    fields={[{ key: "name", label: "Name" }, { key: "rate", label: "Rate %", type: "number" }, { key: "tenure", label: "Tenure" }]} />;
}
function GoldEditor() {
  const [price, setPrice] = useState("");
  const [ok, setOk] = useState(false);
  const mut = useMutation({ mutationFn: () => api.post("/admin/invest/gold-rate", { price_per_gram: parseFloat(price) }), onSuccess: () => { setOk(true); setTimeout(() => setOk(false), 2000); } });
  return (
    <div className="card max-w-md">
      <h3 className="font-extrabold mb-3">Update Digital Gold Rate</h3>
      <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Price per gram (₹)</label>
      <input type="number" step="0.01" className="input mt-1" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="e.g. 7820.50" />
      <button onClick={() => mut.mutate()} disabled={!price || mut.isPending} className="btn-primary mt-3 w-full gap-2">
        {ok ? <><CheckCircle2 className="w-4 h-4" /> Updated</> : "Update gold rate"}
      </button>
    </div>
  );
}

// ===================== Content Manager =====================
export function ContentManager() {
  const qc = useQueryClient();
  const [tab, setTab] = useState<"banners" | "offers">("banners");
  return (
    <div className="space-y-4">
      <div><h2 className="text-2xl font-extrabold text-brand-navy">Content Manager</h2><p className="text-sm text-slate-500">Banners & promotional offers shown in the mobile app.</p></div>
      <div className="flex bg-slate-100 rounded-xl p-1 w-fit">
        <button onClick={() => setTab("banners")} className={`px-4 py-2 rounded-lg text-sm font-semibold ${tab === "banners" ? "bg-white shadow" : "text-slate-500"}`}>Banners</button>
        <button onClick={() => setTab("offers")} className={`px-4 py-2 rounded-lg text-sm font-semibold ${tab === "offers" ? "bg-white shadow" : "text-slate-500"}`}>Offers</button>
      </div>
      {tab === "banners" ? <BannersEditor qc={qc} /> : <OffersEditor qc={qc} />}
    </div>
  );
}
function BannersEditor({ qc }: any) {
  const { data, isLoading } = useQuery({ queryKey: ["admin-banners"], queryFn: async () => (await api.get("/admin/content/banners")).data });
  const save = useMutation({ mutationFn: (d: any) => api.post("/admin/content/banners", d), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-banners"] }) });
  const del = useMutation({ mutationFn: (id: string) => api.delete(`/admin/content/banners/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-banners"] }) });
  return <CrudList title="Home Banners" items={data} isLoading={isLoading} onSave={save.mutate} onDelete={del.mutate}
    fields={[{ key: "title", label: "Title" }, { key: "subtitle", label: "Subtitle" }, { key: "cta_label", label: "CTA Label" }, { key: "cta_route", label: "CTA Route" }, { key: "order", label: "Order", type: "number" }, { key: "active", label: "Active (true/false)" }]} />;
}
function OffersEditor({ qc }: any) {
  const { data, isLoading } = useQuery({ queryKey: ["admin-offers"], queryFn: async () => (await api.get("/admin/content/offers")).data });
  const save = useMutation({ mutationFn: (d: any) => api.post("/admin/content/offers", d), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-offers"] }) });
  const del = useMutation({ mutationFn: (id: string) => api.delete(`/admin/content/offers/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-offers"] }) });
  // Use first field as 'title' (CrudList shows item.name) — alias:
  const items = (data || []).map((o: any) => ({ ...o, name: o.title }));
  return <CrudList title="Promotional Offers" items={items} isLoading={isLoading} onSave={(d: any) => save.mutate({ ...d, title: d.title || d.name })} onDelete={del.mutate}
    fields={[{ key: "title", label: "Title" }, { key: "description", label: "Description" }, { key: "code", label: "Promo Code" }, { key: "discount_pct", label: "Discount %", type: "number" }, { key: "active", label: "Active (true/false)" }]} />;
}

// ===================== Reports =====================
export function Reports() {
  const [start, setStart] = useState(""); const [end, setEnd] = useState("");
  const download = async (kind: string) => {
    const url = `/api/admin/reports/${kind}?${start ? `start=${start}&` : ""}${end ? `end=${end}` : ""}`;
    const t = localStorage.getItem("mfb_admin_token");
    const r = await fetch(url, { headers: { Authorization: `Bearer ${t}` } });
    const blob = await r.blob();
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `mfb_${kind}.csv`; a.click();
  };
  const reports = [
    { kind: "users", label: "User Report", desc: "All customers, KYC + status" },
    { kind: "transactions", label: "Transaction Report", desc: "All money movement" },
    { kind: "investments", label: "Investment Report", desc: "MF/Stock/Gold/FD/Govt holdings" },
    { kind: "bookings", label: "Booking Report", desc: "Flights, hotels & travel" },
  ];
  return (
    <div className="space-y-4">
      <div><h2 className="text-2xl font-extrabold text-brand-navy">Reports</h2><p className="text-sm text-slate-500">Export filtered CSVs for finance & compliance.</p></div>
      <div className="card flex items-end gap-3 flex-wrap">
        <div><label className="text-xs font-semibold text-slate-600">From</label><input type="date" className="input mt-1" value={start} onChange={(e) => setStart(e.target.value)} /></div>
        <div><label className="text-xs font-semibold text-slate-600">To</label><input type="date" className="input mt-1" value={end} onChange={(e) => setEnd(e.target.value)} /></div>
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        {reports.map((r) => (
          <div key={r.kind} className="card flex items-center justify-between">
            <div><p className="font-extrabold">{r.label}</p><p className="text-xs text-slate-500">{r.desc}</p></div>
            <button onClick={() => download(r.kind)} className="btn-primary gap-2"><Download className="w-4 h-4" /> CSV</button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ===================== Settings =====================
export function Settings() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-settings"], queryFn: async () => (await api.get("/admin/settings")).data });
  const [form, setForm] = useState<any>({});
  const merged = { ...data, ...form };
  const save = useMutation({ mutationFn: () => api.put("/admin/settings", form), onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-settings"] }); setForm({}); } });
  const num = (k: string, label: string, sub?: string) => (
    <div className="card">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{label}</p>
      <input type="number" step="0.01" className="input mt-2" value={merged?.[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: parseFloat(e.target.value) })} />
      {sub ? <p className="text-xs text-slate-400 mt-1">{sub}</p> : null}
    </div>
  );
  const bool = (k: string, label: string) => (
    <div className="card flex items-center justify-between">
      <div><p className="font-bold">{label}</p></div>
      <button onClick={() => setForm({ ...form, [k]: !(merged?.[k]) })}
        className={`w-12 h-7 rounded-full transition ${merged?.[k] ? "bg-emerald-500" : "bg-slate-300"}`}>
        <span className={`block w-5 h-5 bg-white rounded-full transition ${merged?.[k] ? "ml-6" : "ml-1"}`} />
      </button>
    </div>
  );
  return (
    <div className="space-y-4 max-w-3xl">
      <div className="flex justify-between items-end">
        <div><h2 className="text-2xl font-extrabold text-brand-navy">Settings</h2><p className="text-sm text-slate-500">Global app configuration.</p></div>
        <button onClick={() => save.mutate()} disabled={Object.keys(form).length === 0 || save.isPending} className="btn-primary gap-2"><Save className="w-4 h-4" /> Save</button>
      </div>
      <div className="grid sm:grid-cols-2 gap-3">
        {num("welcome_bonus", "Welcome Bonus (₹)", "Credited to new signups")}
        {num("referral_bonus", "Referral Bonus (₹)", "Per successful referral")}
        {num("cashback_pct", "Cashback %", "On recharge & bill pay")}
        {num("sip_min_amount", "SIP Minimum (₹)", "Lowest allowed SIP")}
        {bool("otp_enabled", "OTP login enabled")}
        {bool("maintenance_mode", "Maintenance mode")}
      </div>
    </div>
  );
}

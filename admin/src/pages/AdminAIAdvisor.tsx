import { useEffect, useMemo, useState } from "react";
import { api, inr, fmtDate } from "../lib/api";
import {
  Bot, MessageSquare, Users as UsersIcon, Coins, Sparkles, RefreshCw,
  Search, X, ChevronRight, ThumbsUp, ThumbsDown, Send, User as UserIcon,
  Settings2, Save, ToggleRight, ToggleLeft, ClipboardList, TrendingUp,
  Activity, DollarSign,
} from "lucide-react";

type Dash = {
  stats: {
    total_conversations: number;
    total_messages: number;
    messages_24h: number;
    active_users_7d: number;
    total_tokens_est: number;
    tokens_7d: number;
    est_cost_usd: number;
    est_cost_usd_7d: number;
    goals_total: number;
    feedback: { up: number; down: number; neutral: number };
  };
  chart: { date: string; messages: number; tokens: number }[];
  top_users: { user_id: string; messages: number; tokens: number; user: { full_name?: string; email?: string; mobile?: string } }[];
};
type Conv = {
  conversation_id: string; user_id: string; title: string; message_count: number;
  tokens_est: number; created_at: string; updated_at: string;
  user: { full_name?: string; email?: string; mobile?: string };
};
type Msg = { message_id: string; role: string; content: string; created_at: string; tokens_est?: number; rating?: number; feedback_note?: string; model?: string };
type Settings = {
  provider: string; model: string;
  features: { chat: boolean; portfolio_analysis: boolean; goals: boolean; investment_suggestions: boolean };
  rate_limit_per_hour: number; max_tokens_response: number; temperature: number;
  system_prompt: string; suggested_questions: string[]; portfolio_cache_minutes: number;
  max_messages_context: number;
};

export default function AdminAIAdvisor() {
  const [tab, setTab] = useState<"dashboard" | "conversations" | "feedback" | "settings">("dashboard");
  const [dash, setDash] = useState<Dash | null>(null);
  const [convs, setConvs] = useState<Conv[]>([]);
  const [detail, setDetail] = useState<{ conversation: Conv; user: any; messages: Msg[] } | null>(null);
  const [feedback, setFeedback] = useState<Msg[]>([]);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [savingSettings, setSavingSettings] = useState(false);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  const flash = (type: "success" | "error", msg: string) => {
    setToast({ type, msg }); setTimeout(() => setToast(null), 4000);
  };

  useEffect(() => {
    if (tab === "dashboard") api.get("/admin/ai/dashboard").then((r) => setDash(r.data)).catch((e) => flash("error", e?.response?.data?.detail || "Failed to load"));
    if (tab === "conversations") loadConvs();
    if (tab === "feedback") api.get("/admin/ai/feedback").then((r) => setFeedback(r.data.items || [])).catch(() => {});
    if (tab === "settings") api.get("/admin/ai/settings").then((r) => setSettings(r.data.settings)).catch(() => {});
     
  }, [tab]);
  useEffect(() => { if (tab === "conversations") { const t = setTimeout(() => loadConvs(), 300); return () => clearTimeout(t); }  }, [q]);

  const loadConvs = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/ai/conversations?limit=100${q ? `&q=${encodeURIComponent(q)}` : ""}`);
      setConvs(data.items || []);
    } finally { setLoading(false); }
  };

  const openDetail = async (cid: string) => {
    try {
      const { data } = await api.get(`/admin/ai/conversations/${cid}`);
      setDetail(data);
    } catch (e: any) { flash("error", e?.response?.data?.detail || "Failed to load"); }
  };

  const savePatch = async (patch: Partial<Settings>) => {
    if (!settings) return;
    setSavingSettings(true);
    try {
      const { data } = await api.put("/admin/ai/settings", patch);
      setSettings(data.settings);
      flash("success", "Settings saved");
    } catch (e: any) { flash("error", e?.response?.data?.detail || "Save failed"); }
    finally { setSavingSettings(false); }
  };

  return (
    <div className="space-y-6">
        {toast && (
          <div aria-live="polite" className={`fixed top-4 right-4 z-50 px-4 py-3 rounded-xl shadow-lg text-sm font-bold ${toast.type === "success" ? "bg-emerald-600 text-white" : "bg-rose-600 text-white"}`}>{toast.msg}</div>
        )}

      {/* HERO */}
      <div className="rounded-3xl bg-gradient-to-br from-indigo-700 via-blue-800 to-slate-900 p-6 text-white relative overflow-hidden">
        <div className="absolute -right-6 -top-8 opacity-20"><Bot className="w-40 h-40" /></div>
        <div className="flex items-center gap-2 text-xs font-bold tracking-widest uppercase text-indigo-200"><Sparkles className="w-4 h-4" /> Sprint 4 · AI Wealth Advisor</div>
        <h1 className="text-3xl font-black mt-1">AI Console</h1>
        <p className="text-indigo-100 text-sm mt-1">Monitor conversations, feedback and cost. Fine-tune prompts and toggle features.</p>
      </div>

      <div className="flex gap-2 flex-wrap">
        {[
          { k: "dashboard", label: "Overview", icon: TrendingUp },
          { k: "conversations", label: `Conversations${dash?.stats.total_conversations ? ` · ${dash.stats.total_conversations}` : ""}`, icon: MessageSquare },
          { k: "feedback", label: `Feedback${dash?.stats.feedback ? ` · ${dash.stats.feedback.up + dash.stats.feedback.down}` : ""}`, icon: ThumbsUp },
          { k: "settings", label: "Settings", icon: Settings2 },
        ].map((t) => (
          <button key={t.k} onClick={() => setTab(t.k as any)}
            className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition ${tab === t.k ? "bg-brand-navy text-white shadow-lg" : "bg-white border border-slate-200 text-slate-600 hover:border-brand-primary"}`}>
            <t.icon className="w-4 h-4" /> {t.label}
          </button>
        ))}
      </div>

      {tab === "dashboard" && dash && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: "Messages · 24h", value: dash.stats.messages_24h, sub: `${dash.stats.total_messages} all-time`, icon: MessageSquare, tone: "from-indigo-500 to-blue-700" },
              { label: "Active Users · 7d", value: dash.stats.active_users_7d, sub: `${dash.stats.total_conversations} conversations`, icon: UsersIcon, tone: "from-sky-500 to-blue-600" },
              { label: "Tokens · 7d", value: dash.stats.tokens_7d.toLocaleString(), sub: `${dash.stats.total_tokens_est.toLocaleString()} total`, icon: Activity, tone: "from-emerald-500 to-teal-600" },
              { label: "Cost · 7d (est)", value: `$${dash.stats.est_cost_usd_7d.toFixed(4)}`, sub: `$${dash.stats.est_cost_usd.toFixed(4)} total`, icon: DollarSign, tone: "from-amber-500 to-orange-600" },
            ].map((c) => (
              <div key={c.label} className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
                <div className={`w-11 h-11 rounded-xl bg-gradient-to-br ${c.tone} flex items-center justify-center text-white mb-3`}><c.icon className="w-5 h-5" /></div>
                <p className="text-xs font-bold text-slate-500 uppercase tracking-wide">{c.label}</p>
                <p className="text-2xl font-black text-brand-navy mt-1">{c.value}</p>
                <p className="text-xs text-slate-500 font-semibold mt-1">{c.sub}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <div className="lg:col-span-2 bg-white rounded-2xl p-5 border border-slate-200">
              <p className="font-black text-brand-navy mb-4">Last 7 Days · Messages & Tokens</p>
              <div className="grid grid-cols-7 gap-2">
                {dash.chart.map((d) => {
                  const maxMsg = Math.max(1, ...dash.chart.map((x) => x.messages));
                  const h = Math.max(6, Math.round((d.messages / maxMsg) * 100));
                  return (
                    <div key={d.date} className="flex flex-col items-center gap-1">
                      <div className="w-full h-32 bg-slate-50 rounded-lg relative flex items-end overflow-hidden">
                        <div className="w-full bg-gradient-to-t from-indigo-500 to-blue-600" style={{ height: `${h}%` }} />
                        <div className="absolute inset-0 flex items-center justify-center text-[10px] font-black text-white drop-shadow">{d.messages || ""}</div>
                      </div>
                      <p className="text-[9px] text-slate-500 font-bold">{d.date.slice(5)}</p>
                      <p className="text-[8px] text-slate-400">{d.tokens > 999 ? `${(d.tokens/1000).toFixed(1)}k` : d.tokens} tok</p>
                    </div>
                  );
                })}
              </div>
            </div>
            <div className="bg-white rounded-2xl p-5 border border-slate-200">
              <p className="font-black text-brand-navy mb-3">Top Users · 7d</p>
              {dash.top_users.length === 0 ? (
                <p className="text-sm text-slate-500">No activity yet.</p>
              ) : (
                <div className="space-y-2">
                  {dash.top_users.map((u) => (
                    <div key={u.user_id} className="flex items-center gap-2 p-2 rounded-lg hover:bg-slate-50">
                      <div className="w-8 h-8 rounded-full bg-brand-primary/15 text-brand-primary flex items-center justify-center"><UserIcon className="w-4 h-4" /></div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-bold truncate">{u.user?.full_name || u.user_id}</p>
                        <p className="text-[10px] text-slate-500">{u.messages} msgs · {u.tokens} tokens</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              <div className="mt-4 pt-3 border-t border-slate-100">
                <p className="text-xs font-bold text-slate-500 uppercase">Feedback</p>
                <div className="flex gap-3 mt-2">
                  <span className="inline-flex items-center gap-1 text-sm font-bold text-emerald-600"><ThumbsUp className="w-4 h-4" /> {dash.stats.feedback.up}</span>
                  <span className="inline-flex items-center gap-1 text-sm font-bold text-rose-600"><ThumbsDown className="w-4 h-4" /> {dash.stats.feedback.down}</span>
                  <span className="inline-flex items-center gap-1 text-sm font-bold text-slate-500">Goals: {dash.stats.goals_total}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === "conversations" && (
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="p-4 border-b border-slate-200 flex flex-wrap gap-3 items-center">
            <div className="relative flex-1 min-w-[220px]">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input placeholder="Search by user_id, conversation_id or title…" value={q} onChange={(e) => setQ(e.target.value)}
                className="w-full pl-9 pr-3 py-2.5 rounded-xl border border-slate-200 text-sm focus:border-brand-primary focus:ring-2 focus:ring-sky-100 outline-none" />
            </div>
            <button onClick={loadConvs} className="px-3 py-2.5 rounded-xl border border-slate-200 hover:border-brand-primary"><RefreshCw className="w-4 h-4" /></button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs font-black text-slate-500 uppercase tracking-wide">
                <tr><th className="p-3 text-left">Conversation</th><th className="p-3 text-left">User</th><th className="p-3 text-right">Msgs</th><th className="p-3 text-right">Tokens</th><th className="p-3 text-left">Updated</th><th className="p-3"></th></tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loading ? (
                  <tr><td colSpan={6} className="p-10 text-center"><RefreshCw className="w-5 h-5 mx-auto animate-spin text-brand-primary" /></td></tr>
                ) : convs.length === 0 ? (
                  <tr><td colSpan={6} className="p-16 text-center text-slate-400"><Bot className="w-10 h-10 mx-auto mb-2 opacity-40" /><p className="font-semibold">No conversations found.</p></td></tr>
                ) : convs.map((c) => (
                  <tr key={c.conversation_id} className="hover:bg-slate-50">
                    <td className="p-3">
                      <p className="font-black text-brand-navy truncate max-w-[280px]">{c.title || "(no title)"}</p>
                      <p className="text-[10px] text-slate-400 font-mono">{c.conversation_id}</p>
                    </td>
                    <td className="p-3">
                      <p className="font-bold text-slate-800">{c.user?.full_name || "—"}</p>
                      <p className="text-[11px] text-slate-500">{c.user?.email || c.user_id.slice(0, 12)}</p>
                    </td>
                    <td className="p-3 text-right font-black text-brand-navy">{c.message_count}</td>
                    <td className="p-3 text-right font-bold text-slate-700">{c.tokens_est.toLocaleString()}</td>
                    <td className="p-3 text-xs text-slate-500">{fmtDate(c.updated_at)}</td>
                    <td className="p-3 text-right">
                      <button onClick={() => openDetail(c.conversation_id)} className="text-brand-primary text-xs font-bold hover:underline inline-flex items-center gap-1">Open<ChevronRight className="w-3.5 h-3.5" /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === "feedback" && (
        <div className="grid grid-cols-1 gap-3">
          {feedback.length === 0 ? (
            <div className="bg-white p-10 rounded-2xl border border-slate-200 text-center text-slate-500">No feedback yet.</div>
          ) : feedback.map((m) => (
            <div key={m.message_id} className="bg-white rounded-2xl p-4 border border-slate-200 flex items-start gap-3">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${m.rating === 1 ? "bg-emerald-100 text-emerald-600" : m.rating === -1 ? "bg-rose-100 text-rose-600" : "bg-slate-100 text-slate-500"}`}>
                {m.rating === 1 ? <ThumbsUp className="w-5 h-5" /> : m.rating === -1 ? <ThumbsDown className="w-5 h-5" /> : <MessageSquare className="w-5 h-5" />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-slate-800 line-clamp-3">{m.content}</p>
                {m.feedback_note && <p className="text-xs mt-1 text-slate-500 italic">"{m.feedback_note}"</p>}
                <p className="text-[10px] text-slate-400 mt-1">{fmtDate(m.created_at)}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === "settings" && settings && (
        <SettingsPanel settings={settings} onSave={savePatch} saving={savingSettings} />
      )}

      {/* DETAIL DRAWER */}
      {detail && (
        <div className="fixed inset-0 z-40 flex" onClick={() => setDetail(null)}>
          <div className="absolute inset-0 bg-black/40 backdrop-blur-sm" />
          <div className="ml-auto relative w-full max-w-2xl h-full bg-white shadow-2xl overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="sticky top-0 bg-gradient-to-r from-indigo-700 to-blue-800 text-white p-5 flex items-start justify-between">
              <div>
                <p className="text-xs font-bold tracking-widest uppercase text-indigo-200">Conversation</p>
                <p className="text-lg font-black mt-1">{detail.conversation.title}</p>
                <p className="text-xs text-indigo-100 mt-1">{detail.user?.full_name} · {detail.user?.email || detail.conversation.user_id}</p>
                <p className="text-[10px] text-indigo-200 font-mono mt-0.5">{detail.conversation.conversation_id}</p>
              </div>
              <button onClick={() => setDetail(null)} className="p-1 hover:bg-white/10 rounded"><X className="w-5 h-5" /></button>
            </div>
            <div className="p-4 space-y-3 bg-slate-50">
              {detail.messages.map((m) => (
                <div key={m.message_id} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`max-w-[85%] rounded-2xl p-3 shadow-sm ${m.role === "user" ? "bg-brand-primary text-white" : "bg-white border border-slate-200"}`}>
                    <div className="flex items-center gap-2 mb-1 text-[10px] font-bold uppercase tracking-wide opacity-80">
                      {m.role === "user" ? <UserIcon className="w-3 h-3" /> : <Bot className="w-3 h-3" />}
                      {m.role}
                      {m.rating === 1 && <ThumbsUp className="w-3 h-3 text-emerald-500" />}
                      {m.rating === -1 && <ThumbsDown className="w-3 h-3 text-rose-500" />}
                    </div>
                    <div className={`text-sm whitespace-pre-wrap ${m.role === "user" ? "text-white" : "text-slate-800"}`}>{m.content}</div>
                    <p className={`text-[10px] mt-1 ${m.role === "user" ? "text-white/70" : "text-slate-400"}`}>{fmtDate(m.created_at)} {m.tokens_est ? `· ${m.tokens_est} tok` : ""}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SettingsPanel({ settings, onSave, saving }: { settings: Settings; onSave: (p: Partial<Settings>) => Promise<void>; saving: boolean }) {
  const [s, setS] = useState<Settings>(settings);
  useEffect(() => setS(settings), [settings]);
  const [newQ, setNewQ] = useState("");

  const toggleFeat = (k: keyof Settings["features"]) => setS({ ...s, features: { ...s.features, [k]: !s.features[k] } });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
        <p className="font-black text-brand-navy flex items-center gap-2"><ToggleRight className="w-4 h-4" />AI Features</p>
        {(["chat","portfolio_analysis","goals","investment_suggestions"] as const).map((k) => (
          <label key={k} className="flex items-center justify-between cursor-pointer">
            <span className="text-sm font-bold text-slate-700">{k.replace("_"," ")}</span>
            <button onClick={() => toggleFeat(k)} className={`w-11 h-6 rounded-full p-0.5 transition ${s.features[k] ? "bg-brand-primary" : "bg-slate-300"}`}>
              <div className={`w-5 h-5 rounded-full bg-white transition ${s.features[k] ? "translate-x-5" : ""}`} />
            </button>
          </label>
        ))}
        <p className="text-[11px] text-slate-500">Disabling a feature returns 403 for user requests. Existing conversations persist.</p>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
        <p className="font-black text-brand-navy flex items-center gap-2"><Bot className="w-4 h-4" />Model</p>
        <Field label="Provider">
          <select value={s.provider} onChange={(e) => setS({ ...s, provider: e.target.value })} className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold">
            <option value="anthropic">Anthropic (Claude)</option>
            <option value="openai">OpenAI</option>
            <option value="gemini">Gemini</option>
          </select>
        </Field>
        <Field label="Model ID">
          <input value={s.model} onChange={(e) => setS({ ...s, model: e.target.value })}
            className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-mono focus:border-brand-primary outline-none" />
        </Field>
        <Field label="Temperature" hint="0 = deterministic · 1 = creative">
          <input type="number" step="0.05" min="0" max="1" value={s.temperature}
            onChange={(e) => setS({ ...s, temperature: parseFloat(e.target.value) || 0 })}
            className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold" />
        </Field>
        <Field label="Max response tokens">
          <input type="number" value={s.max_tokens_response} onChange={(e) => setS({ ...s, max_tokens_response: parseInt(e.target.value) || 0 })}
            className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold" />
        </Field>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4 lg:col-span-2">
        <p className="font-black text-brand-navy flex items-center gap-2"><ClipboardList className="w-4 h-4" />System Prompt Template</p>
        <textarea value={s.system_prompt} onChange={(e) => setS({ ...s, system_prompt: e.target.value })} rows={10}
          className="w-full p-3 rounded-xl border border-slate-200 text-sm font-mono focus:border-brand-primary outline-none" />
        <p className="text-[11px] text-slate-500">Injected as system message every turn. The user's live financial profile is appended automatically inside <code>&lt;user_profile&gt;</code> tags.</p>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
        <p className="font-black text-brand-navy flex items-center gap-2"><Sparkles className="w-4 h-4" />Suggested Questions</p>
        <div className="space-y-2">
          {s.suggested_questions.map((q, i) => (
            <div key={i} className="flex gap-2">
              <input value={q} onChange={(e) => { const cp = [...s.suggested_questions]; cp[i] = e.target.value; setS({ ...s, suggested_questions: cp }); }}
                className="flex-1 px-3 py-2 rounded-lg border border-slate-200 text-sm" />
              <button onClick={() => setS({ ...s, suggested_questions: s.suggested_questions.filter((_, j) => j !== i) })} className="p-2 rounded-lg text-slate-500 hover:bg-rose-50 hover:text-rose-600"><X className="w-4 h-4" /></button>
            </div>
          ))}
          <div className="flex gap-2">
            <input value={newQ} onChange={(e) => setNewQ(e.target.value)} placeholder="+ Add new question"
              className="flex-1 px-3 py-2 rounded-lg border border-slate-200 text-sm" />
            <button onClick={() => { if (newQ.trim()) { setS({ ...s, suggested_questions: [...s.suggested_questions, newQ.trim()] }); setNewQ(""); } }} className="px-3 py-2 rounded-lg bg-brand-primary text-white text-sm font-bold"><Send className="w-4 h-4" /></button>
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4">
        <p className="font-black text-brand-navy flex items-center gap-2"><Coins className="w-4 h-4" />Rate limits & context</p>
        <Field label="Rate limit / hour (per user)">
          <input type="number" value={s.rate_limit_per_hour} onChange={(e) => setS({ ...s, rate_limit_per_hour: parseInt(e.target.value) || 0 })}
            className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold" />
        </Field>
        <Field label="Max messages carried in context">
          <input type="number" value={s.max_messages_context} onChange={(e) => setS({ ...s, max_messages_context: parseInt(e.target.value) || 0 })}
            className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold" />
        </Field>
        <Field label="Portfolio analysis cache (min)">
          <input type="number" value={s.portfolio_cache_minutes} onChange={(e) => setS({ ...s, portfolio_cache_minutes: parseInt(e.target.value) || 0 })}
            className="w-full px-3 py-2.5 rounded-xl border border-slate-200 text-sm font-semibold" />
        </Field>
      </div>

      <div className="lg:col-span-2 flex justify-end">
        <button onClick={() => onSave(s)} disabled={saving}
          className="py-3 px-6 rounded-xl bg-gradient-to-r from-indigo-700 to-blue-800 text-white font-black text-sm inline-flex items-center justify-center gap-2 hover:from-indigo-800 hover:to-blue-900 disabled:opacity-50">
          {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? "Saving..." : "Save All Settings"}
        </button>
      </div>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="text-xs font-bold text-slate-600 uppercase tracking-wide block mb-1">{label}</label>
      {children}
      {hint && <p className="text-[11px] text-slate-400 mt-1">{hint}</p>}
    </div>
  );
}

/**
 * Admin — Cashfree Bank Verification config & history (Sprint 12.1).
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import { ShieldCheck, RefreshCw, CheckCircle2, XCircle, Play } from "lucide-react";

export default function AdminBankVerification() {
  const qc = useQueryClient();
  const [form, setForm] = useState<any>({});
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<any>(null);

  const { data: cfg } = useQuery({
    queryKey: ["adm_bv_cfg"],
    queryFn: async () => (await api.get("/admin/bank-verification/config")).data,
  });
  const { data: providers } = useQuery({
    queryKey: ["adm_bv_prov"],
    queryFn: async () => (await api.get("/admin/bank-verification/providers")).data,
  });
  const { data: history } = useQuery({
    queryKey: ["adm_bv_hist"],
    queryFn: async () => (await api.get("/admin/bank-verification/history?limit=100")).data,
    refetchInterval: 30000,
  });

  const patch = useMutation({
    mutationFn: async (body: any) => (await api.put("/admin/bank-verification/config", body)).data,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["adm_bv_cfg"] }); setForm({}); },
  });

  const testConn = async () => {
    setTesting(true); setTestResult(null);
    try {
      const r = await api.post("/admin/bank-verification/test-connection");
      setTestResult(r.data);
    } catch (e: any) { setTestResult({ ok: false, error: e?.message }); }
    finally { setTesting(false); }
  };

  if (!cfg) return <div className="p-8 text-center text-slate-400">Loading…</div>;
  const val = (k: string) => (form[k] !== undefined ? form[k] : cfg[k]);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <ShieldCheck className="w-6 h-6 text-emerald-600" />
        <h1 className="text-2xl font-black text-brand-navy">Bank Verification (Cashfree)</h1>
        <span className="text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded bg-emerald-600 text-white">Sprint 12.1</span>
      </div>

      {/* Config */}
      <div className="p-5 rounded-xl border-2 border-slate-200 bg-white">
        <div className="text-xs font-bold text-slate-700 mb-3">PROVIDER CONFIG</div>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <label>Provider
            <select value={val("provider")} onChange={(e) => setForm({ ...form, provider: e.target.value })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1">
              {(providers?.registry || []).map((p: string) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label>Environment
            <select value={val("env")} onChange={(e) => setForm({ ...form, env: e.target.value })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1">
              <option value="sandbox">Sandbox</option>
              <option value="production">Production</option>
            </select>
          </label>
          <label className="col-span-2">Client ID
            <input value={val("client_id") || ""} onChange={(e) => setForm({ ...form, client_id: e.target.value })} placeholder="Cashfree client_id" className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1 font-mono" />
          </label>
          <label className="col-span-2">Client Secret
            <input type="password" defaultValue={cfg.client_secret || ""} onChange={(e) => setForm({ ...form, client_secret: e.target.value })} placeholder="Enter to update — leave blank to keep existing" className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1 font-mono" />
            {cfg.client_secret ? <span className="text-[10px] text-slate-500">Currently stored: {cfg.client_secret}</span> : null}
          </label>
          <label>Webhook Secret
            <input value={val("webhook_secret") || ""} onChange={(e) => setForm({ ...form, webhook_secret: e.target.value })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1 font-mono" />
          </label>
          <label>Min Name Match Score
            <input type="number" value={val("min_name_match_score")} onChange={(e) => setForm({ ...form, min_name_match_score: Number(e.target.value) })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1" />
          </label>
          <label>Dedup Window (hours)
            <input type="number" value={val("dedup_window_hours")} onChange={(e) => setForm({ ...form, dedup_window_hours: Number(e.target.value) })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1" />
          </label>
          <label className="flex items-center gap-2 mt-6">
            <input type="checkbox" checked={!!val("auto_switch_on_failure")} onChange={(e) => setForm({ ...form, auto_switch_on_failure: e.target.checked })} />
            <span>Auto-switch to Demo on provider failure</span>
          </label>
        </div>

        <div className="mt-4 flex gap-2 items-center">
          <button onClick={() => patch.mutate(form)} disabled={Object.keys(form).length === 0 || patch.isPending} className="px-4 py-2 rounded-lg bg-brand-navy text-white text-sm font-bold disabled:opacity-50">
            {patch.isPending ? "Saving…" : "Save Config"}
          </button>
          <button onClick={() => setForm({})} className="px-3 py-2 rounded text-sm text-slate-600 hover:bg-slate-100">Reset</button>
          <button onClick={testConn} disabled={testing} className="ml-auto inline-flex items-center gap-1 px-3 py-2 rounded-lg text-sm font-bold bg-emerald-600 text-white disabled:opacity-50">
            {testing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />} Test Connection
          </button>
          {patch.isSuccess && <span className="text-xs text-emerald-600 ml-2">✓ Saved</span>}
        </div>

        {testResult ? (
          <div className={`mt-3 p-3 rounded-lg text-xs ${testResult.ok ? "bg-emerald-50 border border-emerald-200 text-emerald-800" : "bg-red-50 border border-red-200 text-red-800"}`}>
            {testResult.ok ? <CheckCircle2 className="inline w-4 h-4 mr-1" /> : <XCircle className="inline w-4 h-4 mr-1" />}
            <b>{testResult.provider}</b>: {testResult.reachable ? "Reachable" : "Failed"} {testResult.note ? `· ${testResult.note}` : ""} {testResult.error ? `· ${testResult.error}` : ""}
          </div>
        ) : null}
      </div>

      {/* History */}
      <div className="p-4 rounded-xl border border-slate-200 bg-white">
        <div className="text-xs font-bold text-slate-700 mb-3">VERIFICATION HISTORY</div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">When</th>
                <th className="text-left px-3 py-2">User</th>
                <th className="text-left px-3 py-2">Bank</th>
                <th className="text-left px-3 py-2">IFSC · A/C</th>
                <th className="text-left px-3 py-2">Provider</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-right px-3 py-2">Match %</th>
                <th className="text-left px-3 py-2">Ref</th>
              </tr>
            </thead>
            <tbody>
              {(history?.items || []).map((r: any) => (
                <tr key={r.verification_id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 whitespace-nowrap text-slate-500">{fmtDate(r.created_at)}</td>
                  <td className="px-3 py-2 font-mono text-[10px]">{r.user_id?.slice(-10)}</td>
                  <td className="px-3 py-2">{r.holder_name}</td>
                  <td className="px-3 py-2 font-mono text-[10px]">{r.ifsc} · ****{r.account_masked}</td>
                  <td className="px-3 py-2 uppercase text-[10px]">{r.provider}</td>
                  <td className="px-3 py-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                      r.status === "verified" ? "bg-emerald-100 text-emerald-700" :
                      r.status === "failed" || r.status === "error" ? "bg-red-100 text-red-700" :
                      "bg-amber-100 text-amber-700"
                    }`}>{r.status}</span>
                  </td>
                  <td className="px-3 py-2 text-right">{r.name_match_score ?? "—"}</td>
                  <td className="px-3 py-2 font-mono text-[10px]">{r.reference_id || "—"}</td>
                </tr>
              ))}
              {!(history?.items || []).length && <tr><td colSpan={8} className="text-center py-8 text-slate-400">No verifications yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

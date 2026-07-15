import { useEffect, useState } from "react";
import { api } from "../lib/api";

type SymCfg = { enabled: boolean; spread_pips: number; min_lot: number; max_lot: number };
type Config = {
  enabled: boolean;
  demo_mode: boolean;
  live_mode: boolean;
  default_demo_balance: number;
  margin_per_lot: number;
  min_lot: number;
  max_lot: number;
  usd_inr: number;
  twelve_data_api_key_masked?: string;
  trading_costs?: { commission_per_lot: number; commission_type: string; commission_currency: string };
  symbols: Record<string, SymCfg>;
  diagnostics: any;
};

const SYMBOL_LIST = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"];

export default function AdminForexSettings() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [tdKey, setTdKey] = useState("");
  const [stats, setStats] = useState<any>(null);
  const [commReport, setCommReport] = useState<any>(null);
  const [commGroup, setCommGroup] = useState("day");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const [c, s] = await Promise.all([
        api.get<Config>("/admin/forex/settings"),
        api.get("/admin/forex/stats"),
      ]);
      setCfg(c.data);
      setStats(s.data);
      setError(null);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || "Failed to load");
    }
  };

  const loadCommReport = async (g: string) => {
    try {
      const r = await api.get("/admin/forex/commission-report", { params: { group_by: g } });
      setCommReport(r.data);
    } catch { /* section stays empty */ }
  };
  useEffect(() => { loadCommReport(commGroup); }, [commGroup]);

  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, []);

  if (!cfg) {
    return <div className="p-6 text-slate-500">{error || "Loading forex settings…"}</div>;
  }

  const update = (patch: Partial<Config>) => setCfg({ ...cfg, ...patch });
  const updateSym = (id: string, patch: Partial<SymCfg>) =>
    setCfg({ ...cfg, symbols: { ...cfg.symbols, [id]: { ...cfg.symbols[id], ...patch } } });

  const save = async () => {
    setSaving(true); setError(null);
    try {
      const payload: any = {
        enabled: cfg.enabled,
        demo_mode: cfg.demo_mode,
        live_mode: cfg.live_mode,
        default_demo_balance: cfg.default_demo_balance,
        margin_per_lot: cfg.margin_per_lot,
        min_lot: cfg.min_lot,
        max_lot: cfg.max_lot,
        symbols: cfg.symbols,
        trading_costs: cfg.trading_costs || { commission_per_lot: 0, commission_type: "fixed_per_lot", commission_currency: "INR" },
      };
      if (tdKey.trim()) payload.twelve_data_api_key = tdKey.trim();
      await api.put("/admin/forex/settings", payload);
      setTdKey("");
      await load();
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Forex Trading Settings</h1>
          <p className="text-sm text-slate-400">Configure paper trading, symbol controls, and market data providers.</p>
        </div>
        <button onClick={save} disabled={saving}
          className="px-5 py-2 rounded-lg bg-sky-500 hover:bg-sky-600 disabled:opacity-50 text-white font-semibold">
          {saving ? "Saving…" : "Save Changes"}
        </button>
      </div>

      {error && <div className="p-3 rounded-lg bg-red-900/30 border border-red-700 text-red-300 text-sm">{error}</div>}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Stat label="Active traders" value={stats.active_traders} />
          <Stat label="Open positions" value={stats.open_positions} />
          <Stat label="Closed positions" value={stats.closed_positions} />
          <Stat label="Total realized P&L" value={`₹${(stats.total_realized_pnl_inr || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`} />
        </div>
      )}

      {/* Module controls */}
      <Section title="Module Controls">
        <Toggle label="Enable Forex Module" checked={cfg.enabled} onChange={(v) => update({ enabled: v })} />
        <Toggle label="Demo Mode (paper trading only)" checked={cfg.demo_mode} onChange={(v) => update({ demo_mode: v })} />
        <Toggle label="Live Market Data (Twelve Data + Binance)" checked={cfg.live_mode}
          onChange={(v) => update({ live_mode: v })} hint={cfg.live_mode ? "Using live feed when key is set" : "Using simulated prices"} />
      </Section>

      {/* Defaults */}
      <Section title="Trading Defaults">
        <Field label="Default Demo Balance (₹)" type="number" value={cfg.default_demo_balance}
          onChange={(v) => update({ default_demo_balance: Number(v) })} />
        <Field label="Margin per Lot (₹)" type="number" value={cfg.margin_per_lot}
          onChange={(v) => update({ margin_per_lot: Number(v) })} />
        <div className="grid grid-cols-2 gap-3">
          <Field label="Min Lot Size" type="number" step={0.01} value={cfg.min_lot}
            onChange={(v) => update({ min_lot: Number(v) })} />
          <Field label="Max Lot Size" type="number" step={1} value={cfg.max_lot}
            onChange={(v) => update({ max_lot: Number(v) })} />
        </div>
      </Section>

      {/* Sprint 16.1 — Trading Costs (commission engine) */}
      <Section title="Trading Costs (Commission Engine)">
        <div className="text-xs text-slate-400">
          Snapshotted onto every trade at open — changing these values only affects NEW trades.
          Applies identically to demo, copy, AI and (future) real trading.
        </div>
        <div className="grid grid-cols-3 gap-3">
          <Field label="Commission per Lot" type="number" step={1}
            value={cfg.trading_costs?.commission_per_lot ?? 0}
            onChange={(v) => update({ trading_costs: { ...(cfg.trading_costs || { commission_type: "fixed_per_lot", commission_currency: "INR" }), commission_per_lot: Number(v) } as any })} />
          <label className="block">
            <span className="text-xs font-semibold text-slate-400">Commission Type</span>
            <select value={cfg.trading_costs?.commission_type ?? "fixed_per_lot"}
              onChange={(e) => update({ trading_costs: { ...(cfg.trading_costs || { commission_per_lot: 0, commission_currency: "INR" }), commission_type: e.target.value } as any })}
              className="w-full mt-1 px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100">
              <option value="fixed_per_lot">Fixed per lot</option>
              <option value="per_side">Per side (open + close)</option>
              <option value="round_turn">Round turn</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-semibold text-slate-400">Currency</span>
            <select value={cfg.trading_costs?.commission_currency ?? "INR"}
              onChange={(e) => update({ trading_costs: { ...(cfg.trading_costs || { commission_per_lot: 0, commission_type: "fixed_per_lot" }), commission_currency: e.target.value } as any })}
              className="w-full mt-1 px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100">
              <option value="INR">INR (₹)</option>
              <option value="USD">USD ($)</option>
            </select>
          </label>
        </div>
      </Section>

      {/* Sprint 16.1 — Commission reporting */}
      <Section title="Commission Collected">
        <div className="flex items-center gap-2">
          {["day", "week", "month", "symbol", "user"].map((g) => (
            <button key={g} onClick={() => setCommGroup(g)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold border ${commGroup === g ? "bg-sky-500 text-white border-sky-500" : "bg-slate-900 text-slate-300 border-slate-700"}`}>
              {g}
            </button>
          ))}
          <div className="ml-auto text-sm text-emerald-400 font-bold">
            Total: ₹{(commReport?.total_commission_collected || 0).toLocaleString("en-IN")}
            <span className="text-slate-500 font-normal"> · {commReport?.total_commissioned_trades || 0} trades</span>
          </div>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-400 border-b border-slate-700">
              <th className="text-left py-2">{commGroup}</th>
              <th className="text-right py-2">Trades</th>
              <th className="text-right py-2">Commission</th>
              <th className="text-right py-2">Gross PnL</th>
              <th className="text-right py-2">Net PnL</th>
            </tr>
          </thead>
          <tbody>
            {(commReport?.rows || []).slice(0, 15).map((r: any) => (
              <tr key={r.key} className="border-b border-slate-800 text-slate-200">
                <td className="py-1.5 font-mono">{String(r.key).slice(0, 18)}</td>
                <td className="text-right py-1.5">{r.trades}</td>
                <td className="text-right py-1.5 text-emerald-400">₹{r.commission.toLocaleString("en-IN")}</td>
                <td className="text-right py-1.5">₹{r.gross_pnl.toLocaleString("en-IN")}</td>
                <td className="text-right py-1.5">₹{r.net_pnl.toLocaleString("en-IN")}</td>
              </tr>
            ))}
            {!(commReport?.rows || []).length && (
              <tr><td colSpan={5} className="py-3 text-center text-slate-500 text-xs">No commissioned trades yet (₹0 demo default)</td></tr>
            )}
          </tbody>
        </table>
      </Section>

      {/* Symbol manager */}
      <Section title="Symbol Management">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-slate-400 border-b border-slate-700">
                <th className="text-left py-2 px-2">Symbol</th>
                <th className="text-center py-2 px-2">Enabled</th>
                <th className="text-right py-2 px-2">Spread (pips)</th>
                <th className="text-right py-2 px-2">Min Lot</th>
                <th className="text-right py-2 px-2">Max Lot</th>
              </tr>
            </thead>
            <tbody>
              {SYMBOL_LIST.map((id) => {
                const s = cfg.symbols[id] || { enabled: true, spread_pips: 2, min_lot: 0.01, max_lot: 100 };
                return (
                  <tr key={id} className="border-b border-slate-800">
                    <td className="py-2 px-2 font-mono text-slate-200 font-bold">{id}</td>
                    <td className="text-center py-2 px-2">
                      <input type="checkbox" checked={s.enabled} onChange={(e) => updateSym(id, { enabled: e.target.checked })} />
                    </td>
                    <td className="py-1 px-2"><InputCell type="number" step={0.5} value={s.spread_pips}
                      onChange={(v) => updateSym(id, { spread_pips: Number(v) })} /></td>
                    <td className="py-1 px-2"><InputCell type="number" step={0.01} value={s.min_lot}
                      onChange={(v) => updateSym(id, { min_lot: Number(v) })} /></td>
                    <td className="py-1 px-2"><InputCell type="number" step={1} value={s.max_lot}
                      onChange={(v) => updateSym(id, { max_lot: Number(v) })} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Section>

      {/* API settings */}
      <Section title="Market Data API">
        <div className="text-xs text-slate-400">
          Twelve Data REST is used for forex/gold quotes when Live Mode is on. Get a free key at twelvedata.com/register (800 calls/day).
          Binance WebSocket (public, no key) provides BTC/USDT.
        </div>
        <div className="flex items-end gap-3">
          <Field label={`Twelve Data API Key ${cfg.twelve_data_api_key_masked ? `(current: ${cfg.twelve_data_api_key_masked})` : "(not set)"}`}
            type="password" value={tdKey}
            onChange={(v) => setTdKey(String(v))} placeholder="paste new key to update" />
        </div>
        {cfg.diagnostics && (
          <div className="text-xs text-slate-400 font-mono bg-slate-900 p-3 rounded border border-slate-700 mt-2">
            <div>live_mode: {String(cfg.diagnostics.live_mode)}</div>
            <div>td_key_set: {String(cfg.diagnostics.td_key_set)}</div>
            <div>td_credits_left: {cfg.diagnostics.td_credits_left ?? "—"}</div>
            <div>last_td_error: {cfg.diagnostics.last_td_error ?? "—"}</div>
            <div>binance_last_error: {cfg.diagnostics.binance_last_error ?? "—"}</div>
            <div>cache_size: {cfg.diagnostics.cache_size}</div>
          </div>
        )}
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: any }) {
  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 space-y-3">
      <h2 className="font-bold text-slate-100 text-base">{title}</h2>
      {children}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: any }) {
  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-3">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-xl font-bold text-slate-100 mt-1">{value}</div>
    </div>
  );
}

function Toggle({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <label className="flex items-center justify-between py-2 border-b border-slate-700 last:border-0">
      <div>
        <div className="text-slate-200 font-medium">{label}</div>
        {hint && <div className="text-xs text-slate-400 mt-0.5">{hint}</div>}
      </div>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="w-5 h-5" />
    </label>
  );
}

function Field({ label, value, onChange, type = "text", step, placeholder }:
  { label: string; value: any; onChange: (v: string) => void; type?: string; step?: number; placeholder?: string }) {
  return (
    <label className="block">
      <span className="text-xs font-semibold text-slate-400">{label}</span>
      <input type={type} value={value as any} step={step} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full mt-1 px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 text-slate-100" />
    </label>
  );
}

function InputCell({ type, value, onChange, step }: { type?: string; value: any; onChange: (v: string) => void; step?: number }) {
  return (
    <input type={type} value={value as any} step={step}
      onChange={(e) => onChange(e.target.value)}
      className="w-20 px-2 py-1 rounded bg-slate-900 border border-slate-700 text-slate-100 text-right text-sm" />
  );
}

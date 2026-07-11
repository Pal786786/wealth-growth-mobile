/**
 * Admin Gold Console (Sprint 10.5)
 * Tabs: Overview · Transactions · Users · Providers · Settings · Analytics
 *
 * Data-source: /api/admin/gold/* (read-only in this sprint per PRD)
 * The analytics tab computes advanced KPIs client-side from transactions +
 * holdings to avoid backend changes.
 */
import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import {
  Activity,
  ArrowLeftRight,
  Users as UsersIcon,
  Server,
  Settings as SettingsIcon,
  BarChart3,
  Coins,
  RefreshCw,
  Download,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  CheckCircle2,
  Play,
  Pause,
} from "lucide-react";

type Tab = "overview" | "transactions" | "users" | "providers" | "settings" | "analytics";
const TABS: { id: Tab; label: string; icon: any }[] = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "transactions", label: "Transactions", icon: ArrowLeftRight },
  { id: "users", label: "Users", icon: UsersIcon },
  { id: "providers", label: "Providers", icon: Server },
  { id: "settings", label: "Settings", icon: SettingsIcon },
  { id: "analytics", label: "Analytics", icon: BarChart3 },
];

const inr = (n: number | undefined | null) =>
  n == null ? "—" : "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const grams = (g: number | undefined | null) => (g == null ? "—" : `${Number(g).toFixed(4)} g`);

export default function AdminGoldConsole() {
  const [tab, setTab] = useState<Tab>("overview");
  return (
    <div className="p-6">
      <div className="flex items-center gap-3 mb-4">
        <Coins className="w-6 h-6 text-amber-600" />
        <h1 className="text-2xl font-black text-brand-navy">Gold Console</h1>
        <span className="text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded bg-amber-600 text-white">Sprint 10 · 999.9 Digital Gold</span>
      </div>

      <div className="flex flex-wrap gap-2 mb-4 border-b border-slate-200 pb-2">
        {TABS.map((t) => {
          const I = t.icon;
          return (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-bold transition ${
                tab === t.id ? "bg-brand-navy text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
              }`}
            >
              <I className="w-4 h-4" /> {t.label}
            </button>
          );
        })}
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "transactions" && <TransactionsTab />}
      {tab === "users" && <UsersTab />}
      {tab === "providers" && <ProvidersTab />}
      {tab === "settings" && <SettingsTab />}
      {tab === "analytics" && <AnalyticsTab />}
    </div>
  );
}

// ============================================================================
// OVERVIEW
// ============================================================================
function OverviewTab() {
  const { data, refetch, isLoading } = useQuery({
    queryKey: ["adm_gold_dashboard"],
    queryFn: async () => (await api.get("/admin/gold/dashboard")).data,
    refetchInterval: 15000,
  });
  if (isLoading || !data) return <div className="p-8 text-center text-slate-400">Loading…</div>;
  const q = data.quote || {};
  const t = data.totals || {};
  const p = data.provider_status || {};
  const cfg = data.config || {};

  return (
    <div className="space-y-4">
      {/* Live price + mode banner */}
      <div className={`p-4 rounded-xl border-2 ${cfg.maintenance_mode ? "border-amber-300 bg-amber-50" : "border-emerald-200 bg-emerald-50"}`}>
        <div className="flex items-center gap-4">
          <div className="text-3xl">{cfg.maintenance_mode ? "⚠️" : q.trading_open ? "🟢" : "🟠"}</div>
          <div className="flex-1">
            <div className="text-[10px] font-bold uppercase tracking-widest opacity-70">Trading Status</div>
            <div className="text-xl font-black">
              {cfg.maintenance_mode ? "MAINTENANCE MODE" : q.trading_open ? "LIVE" : "OUT OF WINDOW"}
            </div>
            <div className="text-xs opacity-80 mt-1">
              Provider: <b>{q.provider}</b> · Source: {q.source || "—"} · Spread {(q.spread_bps / 100).toFixed(2)}%
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Live Price / g</div>
            <div className="text-3xl font-black text-amber-700">{inr(q.mid_price)}</div>
            <div className="text-xs text-slate-500">Buy {inr(q.buy_price)} · Sell {inr(q.sell_price)}</div>
          </div>
          <button onClick={() => refetch()} className="ml-2 p-2 hover:bg-white/40 rounded-lg" title="Refresh">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* KPI grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Buy Volume" value={inr(t.total_buy_inr)} sub={`${t.buy_tx_count || 0} buys · ${grams(t.total_buy_grams)}`} tint="emerald" />
        <StatCard label="Sell Volume" value={inr(t.total_sell_inr)} sub={`${t.sell_tx_count || 0} sells · ${grams(t.total_sell_grams)}`} tint="red" />
        <StatCard label="Platform Revenue" value={inr(t.platform_revenue_inr)} sub={`Spread ${(cfg.spread_bps / 100).toFixed(2)}%`} tint="amber" />
        <StatCard label="Active Investors" value={t.active_investors || 0} sub={`Users with 1+ trade`} tint="blue" />
      </div>

      {/* Provider status */}
      <div className="p-4 bg-white border border-slate-200 rounded-xl">
        <div className="text-xs font-bold text-slate-700 mb-2">ACTIVE PROVIDER</div>
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${p.configured ? "bg-emerald-500" : "bg-amber-500"}`} />
          <div className="flex-1">
            <div className="font-bold text-slate-800">{p.active}</div>
            <div className="text-xs text-slate-500">
              {p.real ? "Real provider" : "Simulated feed"} · {p.configured ? "Configured" : "NOT configured (using mock/fallback)"}
            </div>
          </div>
          <div className="text-xs text-slate-500">Registry: {p.registry?.join(" · ")}</div>
        </div>
      </div>

      {/* Realized P/L to users */}
      <div className="p-4 bg-white border border-slate-200 rounded-xl">
        <div className="text-xs font-bold text-slate-700 mb-2">USER-REALIZED P/L</div>
        <div className="flex items-center gap-2">
          {t.realized_pnl_users_inr >= 0 ? <TrendingUp className="w-5 h-5 text-emerald-600" /> : <TrendingDown className="w-5 h-5 text-red-600" />}
          <span className={`text-2xl font-black ${t.realized_pnl_users_inr >= 0 ? "text-emerald-700" : "text-red-700"}`}>
            {t.realized_pnl_users_inr >= 0 ? "+" : ""}{inr(t.realized_pnl_users_inr)}
          </span>
          <span className="text-xs text-slate-500 ml-2">across {t.sell_tx_count || 0} realized sells</span>
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// TRANSACTIONS
// ============================================================================
function TransactionsTab() {
  const [side, setSide] = useState<string>("");
  const [userIdFilter, setUserIdFilter] = useState<string>("");
  const { data, isLoading } = useQuery({
    queryKey: ["adm_gold_tx", side, userIdFilter],
    queryFn: async () =>
      (await api.get("/admin/gold/transactions", {
        params: { side: side || undefined, user_id: userIdFilter || undefined, limit: 300 },
      })).data,
    refetchInterval: 15000,
  });

  const rows = (data?.items || []) as any[];

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        {["", "buy", "sell"].map((s) => (
          <button
            key={s || "all"}
            onClick={() => setSide(s)}
            className={`px-3 py-1.5 rounded-full text-xs font-bold ${side === s ? "bg-brand-navy text-white" : "bg-slate-100 text-slate-700"}`}
          >
            {s ? s.toUpperCase() : "ALL"}
          </button>
        ))}
        <input
          value={userIdFilter}
          onChange={(e) => setUserIdFilter(e.target.value)}
          placeholder="Filter by user id…"
          className="border border-slate-300 rounded px-3 py-1.5 text-xs flex-1 max-w-xs"
        />
        <button onClick={() => exportCsv(rows, "gold-transactions")} className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 rounded bg-emerald-600 text-white text-xs font-bold">
          <Download className="w-3.5 h-3.5" /> CSV
        </button>
      </div>

      {isLoading ? (
        <div className="p-8 text-center text-slate-400">Loading…</div>
      ) : (
        <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">TX</th>
                <th className="text-left px-3 py-2">User</th>
                <th className="text-left px-3 py-2">Side</th>
                <th className="text-right px-3 py-2">Amount ₹</th>
                <th className="text-right px-3 py-2">Grams</th>
                <th className="text-right px-3 py-2">Price/g</th>
                <th className="text-right px-3 py-2">P/L</th>
                <th className="text-left px-3 py-2">Provider</th>
                <th className="text-left px-3 py-2">When</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((t) => (
                <tr key={t.tx_id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono text-[10px]">{t.tx_id?.slice(-12)}</td>
                  <td className="px-3 py-2 font-mono text-[10px]">{t.user_id?.slice(-10)}</td>
                  <td className="px-3 py-2">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${t.side === "buy" ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
                      {t.side}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-bold">{inr(t.amount_inr)}</td>
                  <td className="px-3 py-2 text-right">{grams(t.grams)}</td>
                  <td className="px-3 py-2 text-right">{inr(t.price_per_gram)}</td>
                  <td className={`px-3 py-2 text-right font-bold ${t.realized_pnl_inr == null ? "text-slate-400" : t.realized_pnl_inr >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                    {t.realized_pnl_inr == null ? "—" : (t.realized_pnl_inr >= 0 ? "+" : "") + inr(t.realized_pnl_inr)}
                  </td>
                  <td className="px-3 py-2 text-slate-500 uppercase text-[10px]">{t.provider}</td>
                  <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{fmtDate(t.created_at)}</td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr>
                  <td colSpan={9} className="text-center py-8 text-slate-400">
                    No transactions.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// USERS
// ============================================================================
function UsersTab() {
  const { data, isLoading } = useQuery({
    queryKey: ["adm_gold_users"],
    queryFn: async () => (await api.get("/admin/gold/users", { params: { limit: 200 } })).data,
    refetchInterval: 20000,
  });
  const { data: quote } = useQuery({
    queryKey: ["adm_gold_quote_users"],
    queryFn: async () => (await api.get("/admin/gold/dashboard")).data.quote,
    refetchInterval: 15000,
  });
  const mid = Number(quote?.mid_price || 0);

  const rows = (data?.items || []) as any[];
  const enriched = rows.map((r) => {
    const currentValue = (Number(r.grams) || 0) * mid;
    const pnl = currentValue - (Number(r.total_invested) || 0);
    const pnlPct = r.total_invested ? (pnl / r.total_invested) * 100 : 0;
    return { ...r, currentValue, pnl, pnlPct };
  });

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <div className="text-xs text-slate-500">
          Top {enriched.length} investors by invested amount. Current value marked at live mid ₹{mid.toLocaleString("en-IN")}.
        </div>
        <button onClick={() => exportCsv(enriched, "gold-users")} className="inline-flex items-center gap-1 px-3 py-1.5 rounded bg-emerald-600 text-white text-xs font-bold">
          <Download className="w-3.5 h-3.5" /> CSV
        </button>
      </div>

      {isLoading ? (
        <div className="p-8 text-center text-slate-400">Loading…</div>
      ) : (
        <div className="bg-white border border-slate-200 rounded-lg overflow-x-auto">
          <table className="min-w-full text-xs">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="text-left px-3 py-2">#</th>
                <th className="text-left px-3 py-2">User</th>
                <th className="text-right px-3 py-2">Grams</th>
                <th className="text-right px-3 py-2">Invested</th>
                <th className="text-right px-3 py-2">Avg Buy</th>
                <th className="text-right px-3 py-2">Current Value</th>
                <th className="text-right px-3 py-2">P/L</th>
                <th className="text-right px-3 py-2">ROI</th>
                <th className="text-left px-3 py-2">Last Update</th>
              </tr>
            </thead>
            <tbody>
              {enriched.map((r, i) => (
                <tr key={r.user_id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 text-slate-400">{i + 1}</td>
                  <td className="px-3 py-2 font-mono text-[10px]">{r.user_id?.slice(-10)}</td>
                  <td className="px-3 py-2 text-right">{grams(r.grams)}</td>
                  <td className="px-3 py-2 text-right font-bold">{inr(r.total_invested)}</td>
                  <td className="px-3 py-2 text-right">{inr(r.avg_buy_price)}</td>
                  <td className="px-3 py-2 text-right">{inr(r.currentValue)}</td>
                  <td className={`px-3 py-2 text-right font-bold ${r.pnl >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                    {r.pnl >= 0 ? "+" : ""}{inr(r.pnl)}
                  </td>
                  <td className={`px-3 py-2 text-right font-bold ${r.pnlPct >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                    {r.pnlPct >= 0 ? "+" : ""}
                    {r.pnlPct.toFixed(2)}%
                  </td>
                  <td className="px-3 py-2 text-slate-500 whitespace-nowrap">{fmtDate(r.updated_at)}</td>
                </tr>
              ))}
              {enriched.length === 0 && (
                <tr>
                  <td colSpan={9} className="text-center py-8 text-slate-400">
                    No investors yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ============================================================================
// PROVIDERS
// ============================================================================
function ProvidersTab() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["adm_gold_providers"],
    queryFn: async () => (await api.get("/admin/gold/providers")).data,
  });
  const { data: cfg } = useQuery({
    queryKey: ["adm_gold_config"],
    queryFn: async () => (await api.get("/admin/gold/config")).data,
  });
  const setProvider = useMutation({
    mutationFn: async (provider: string) => (await api.put("/admin/gold/config", { provider })).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adm_gold_providers"] });
      qc.invalidateQueries({ queryKey: ["adm_gold_config"] });
      qc.invalidateQueries({ queryKey: ["adm_gold_dashboard"] });
    },
  });

  if (isLoading || !data) return <div className="p-8 text-center text-slate-400">Loading…</div>;

  return (
    <div className="space-y-3">
      <div className="text-xs text-slate-500">
        Active provider: <b className="text-slate-800">{data.active}</b>. Switching provider takes effect immediately.
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {(data.providers || []).map((p: any) => {
          const active = p.name === data.active;
          return (
            <div key={p.name} className={`p-4 rounded-xl border-2 ${active ? "border-amber-400 bg-amber-50" : "border-slate-200 bg-white"}`}>
              <div className="flex items-start gap-3">
                <div className={`w-10 h-10 rounded-full grid place-items-center ${p.configured ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                  {p.configured ? <CheckCircle2 className="w-5 h-5" /> : <AlertTriangle className="w-5 h-5" />}
                </div>
                <div className="flex-1">
                  <div className="font-black text-slate-800 uppercase">{p.name}</div>
                  <div className="text-xs text-slate-500 mt-0.5">
                    {p.real ? "Real market feed" : "Simulated feed"} · {p.configured ? "Configured" : "Not configured"}
                  </div>
                </div>
                {active ? (
                  <span className="text-[10px] font-black uppercase text-amber-700 bg-amber-100 border border-amber-300 rounded px-2 py-0.5">ACTIVE</span>
                ) : (
                  <button
                    onClick={() => setProvider.mutate(p.name)}
                    disabled={setProvider.isPending}
                    className="text-xs font-bold text-brand-navy hover:underline disabled:opacity-50"
                  >
                    Set active →
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {cfg?.manual_price_inr_per_gram ? (
        <div className="p-4 rounded-xl border-2 border-red-300 bg-red-50 flex items-center gap-3">
          <AlertTriangle className="w-5 h-5 text-red-600" />
          <div className="flex-1">
            <div className="font-black text-red-800">Manual price override is ACTIVE</div>
            <div className="text-xs text-red-700 mt-0.5">
              All quotes are pinned at ₹{cfg.manual_price_inr_per_gram} / g. Provider is bypassed.
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

// ============================================================================
// SETTINGS
// ============================================================================
function SettingsTab() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["adm_gold_config"],
    queryFn: async () => (await api.get("/admin/gold/config")).data,
  });
  const [form, setForm] = useState<any>({});
  const patch = useMutation({
    mutationFn: async (body: any) => (await api.put("/admin/gold/config", body)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adm_gold_config"] });
      qc.invalidateQueries({ queryKey: ["adm_gold_dashboard"] });
      setForm({});
    },
  });

  if (!data) return <div className="p-8 text-center text-slate-400">Loading…</div>;

  const val = (k: string) => (form[k] !== undefined ? form[k] : data[k]);
  return (
    <div className="space-y-4">
      <div className="p-4 rounded-xl border border-slate-200 bg-white">
        <div className="text-xs font-bold text-slate-700 mb-3">CURRENT SETTINGS</div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
          <KV label="Provider" value={data.provider} />
          <KV label="Spread" value={`${(data.spread_bps / 100).toFixed(2)}%`} />
          <KV label="Min Buy" value={inr(data.min_buy_inr)} />
          <KV label="Max Buy" value={inr(data.max_buy_inr)} />
          <KV label="Maintenance" value={data.maintenance_mode ? "ON" : "off"} />
          <KV label="Trading Hours (UTC)" value={`${data.trading_hours.open_utc} – ${data.trading_hours.close_utc}`} />
          <KV label="Manual Price" value={data.manual_price_inr_per_gram ? inr(data.manual_price_inr_per_gram) : "—"} />
          <KV label="GST" value={`${(data.gst_bps / 100).toFixed(2)}%`} />
          <KV label="Maker Fee" value={`${(data.maker_fee_bps / 100).toFixed(2)}%`} />
          <KV label="Redemption KYC" value={data.redemption_kyc_required ? "Required" : "Not required"} />
        </div>
      </div>

      <div className="p-4 rounded-xl border-2 border-brand-navy/20 bg-brand-navy/5">
        <div className="text-xs font-bold text-brand-navy mb-3">UPDATE SETTINGS</div>
        <div className="grid grid-cols-2 gap-3 text-xs">
          <label>
            Spread (bps)
            <input type="number" value={val("spread_bps") ?? ""} onChange={(e) => setForm({ ...form, spread_bps: Number(e.target.value) })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1" />
          </label>
          <label>
            Min buy (₹)
            <input type="number" value={val("min_buy_inr") ?? ""} onChange={(e) => setForm({ ...form, min_buy_inr: Number(e.target.value) })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1" />
          </label>
          <label>
            Max buy (₹)
            <input type="number" value={val("max_buy_inr") ?? ""} onChange={(e) => setForm({ ...form, max_buy_inr: Number(e.target.value) })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1" />
          </label>
          <label>
            GST (bps)
            <input type="number" value={val("gst_bps") ?? ""} onChange={(e) => setForm({ ...form, gst_bps: Number(e.target.value) })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1" />
          </label>
          <label>
            Maker fee (bps)
            <input type="number" value={val("maker_fee_bps") ?? ""} onChange={(e) => setForm({ ...form, maker_fee_bps: Number(e.target.value) })} className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1" />
          </label>
          <label>
            Manual price / g (blank = disabled)
            <input
              type="number"
              placeholder={data.manual_price_inr_per_gram || "auto"}
              onChange={(e) => setForm({ ...form, manual_price_inr_per_gram: e.target.value === "" ? null : Number(e.target.value) })}
              className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1"
            />
          </label>
          <label>
            Trading open (UTC HH:MM)
            <input
              type="text"
              value={form.trading_hours?.open_utc ?? data.trading_hours.open_utc}
              onChange={(e) => setForm({ ...form, trading_hours: { ...(form.trading_hours || data.trading_hours), open_utc: e.target.value } })}
              className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1 font-mono"
            />
          </label>
          <label>
            Trading close (UTC HH:MM)
            <input
              type="text"
              value={form.trading_hours?.close_utc ?? data.trading_hours.close_utc}
              onChange={(e) => setForm({ ...form, trading_hours: { ...(form.trading_hours || data.trading_hours), close_utc: e.target.value } })}
              className="w-full border border-slate-300 rounded px-2 py-1.5 mt-1 font-mono"
            />
          </label>
          <label className="flex items-center gap-2 mt-6">
            <input type="checkbox" checked={val("maintenance_mode")} onChange={(e) => setForm({ ...form, maintenance_mode: e.target.checked })} />
            <span>Maintenance mode (blocks all trades)</span>
          </label>
          <label className="flex items-center gap-2 mt-6">
            <input type="checkbox" checked={val("redemption_kyc_required")} onChange={(e) => setForm({ ...form, redemption_kyc_required: e.target.checked })} />
            <span>Require KYC for physical redemption</span>
          </label>
        </div>

        <div className="mt-4 flex gap-2 items-center">
          <button onClick={() => patch.mutate(form)} disabled={Object.keys(form).length === 0 || patch.isPending} className="px-4 py-2 rounded-lg bg-brand-navy text-white text-sm font-bold disabled:opacity-50">
            {patch.isPending ? "Saving…" : "Save Settings"}
          </button>
          <button onClick={() => setForm({})} className="px-3 py-2 rounded text-sm text-slate-600 hover:bg-slate-100">
            Reset form
          </button>
          {/* Quick maintenance toggle */}
          <button
            onClick={() => patch.mutate({ maintenance_mode: !data.maintenance_mode })}
            className={`ml-auto inline-flex items-center gap-1 px-3 py-2 rounded-lg text-sm font-bold ${data.maintenance_mode ? "bg-emerald-600 text-white" : "bg-red-600 text-white"}`}
          >
            {data.maintenance_mode ? <><Play className="w-3.5 h-3.5" /> Resume Trading</> : <><Pause className="w-3.5 h-3.5" /> Pause Trading</>}
          </button>
          {patch.error && <span className="text-xs text-red-600 ml-2">{(patch.error as any)?.response?.data?.detail}</span>}
          {patch.isSuccess && <span className="text-xs text-emerald-600 ml-2">✓ Saved</span>}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// ANALYTICS — client-computed advanced KPIs
// ============================================================================
function AnalyticsTab() {
  const [range, setRange] = useState<"today" | "week" | "month" | "year" | "all">("month");
  const { data: allTx } = useQuery({
    queryKey: ["adm_gold_tx_all"],
    queryFn: async () => (await api.get("/admin/gold/transactions", { params: { limit: 500 } })).data,
    refetchInterval: 30000,
  });
  const { data: users } = useQuery({
    queryKey: ["adm_gold_users_all"],
    queryFn: async () => (await api.get("/admin/gold/users", { params: { limit: 500 } })).data,
    refetchInterval: 30000,
  });
  const { data: dash } = useQuery({
    queryKey: ["adm_gold_dashboard_analytics"],
    queryFn: async () => (await api.get("/admin/gold/dashboard")).data,
    refetchInterval: 30000,
  });

  const kpis = useMemo(() => {
    if (!allTx || !users || !dash) return null;
    const now = Date.now();
    const cutoff =
      range === "today" ? now - 24 * 3600 * 1000 :
      range === "week" ? now - 7 * 24 * 3600 * 1000 :
      range === "month" ? now - 30 * 24 * 3600 * 1000 :
      range === "year" ? now - 365 * 24 * 3600 * 1000 : 0;
    const tx = ((allTx.items || []) as any[]).filter((t) => (cutoff ? new Date(t.created_at).getTime() >= cutoff : true));

    let buyVol = 0, sellVol = 0, buyCnt = 0, sellCnt = 0, buyGrams = 0, sellGrams = 0, realized = 0, avgSizeSum = 0;
    const userIds = new Set<string>();
    const userBuyCount: Record<string, number> = {};
    tx.forEach((t) => {
      userIds.add(t.user_id);
      if (t.side === "buy") { buyVol += t.amount_inr; buyCnt++; buyGrams += t.grams; userBuyCount[t.user_id] = (userBuyCount[t.user_id] || 0) + 1; }
      else { sellVol += t.amount_inr; sellCnt++; sellGrams += t.grams; realized += t.realized_pnl_inr || 0; }
      avgSizeSum += t.amount_inr;
    });
    const avgInvSize = tx.length ? avgSizeSum / tx.length : 0;
    const repeat = Object.values(userBuyCount).filter((c) => c > 1).length;
    const repeatPct = userIds.size ? (repeat / userIds.size) * 100 : 0;

    // AUM = total grams * live mid across all users
    const mid = Number(dash?.quote?.mid_price || 0);
    const totalGrams = (users.items || []).reduce((a: number, u: any) => a + (Number(u.grams) || 0), 0);
    const totalInvested = (users.items || []).reduce((a: number, u: any) => a + (Number(u.total_invested) || 0), 0);
    const aum = totalGrams * mid;
    const unrealized = aum - totalInvested;
    const totalInvestors = (users.items || []).filter((u: any) => Number(u.grams) > 0).length;

    // Revenue (spread earned) — total both sides, using config spread
    const spreadFrac = ((dash?.config?.spread_bps || 200) / 2) / 10000;
    const revenue = (buyVol + sellVol) * spreadFrac;

    // Daily buy vs sell over last 14 days
    const days: { d: string; buy: number; sell: number }[] = [];
    for (let i = 13; i >= 0; i--) {
      const day = new Date(now - i * 24 * 3600 * 1000);
      const key = day.toISOString().slice(0, 10);
      days.push({ d: key, buy: 0, sell: 0 });
    }
    (allTx.items || []).forEach((t: any) => {
      const key = new Date(t.created_at).toISOString().slice(0, 10);
      const row = days.find((r) => r.d === key);
      if (!row) return;
      if (t.side === "buy") row.buy += t.amount_inr;
      else row.sell += t.amount_inr;
    });

    // Distribution buckets (grams held)
    const buckets = [
      { label: "< 0.5g", min: 0, max: 0.5, count: 0 },
      { label: "0.5-2g", min: 0.5, max: 2, count: 0 },
      { label: "2-5g", min: 2, max: 5, count: 0 },
      { label: "5-10g", min: 5, max: 10, count: 0 },
      { label: "10g+", min: 10, max: Infinity, count: 0 },
    ];
    (users.items || []).forEach((u: any) => {
      const g = Number(u.grams) || 0;
      const b = buckets.find((x) => g >= x.min && g < x.max);
      if (b) b.count++;
    });

    // Top ROI users
    const topRoi = (users.items || [])
      .map((u: any) => {
        const cur = (Number(u.grams) || 0) * mid;
        const inv = Number(u.total_invested) || 0;
        return { user_id: u.user_id, roi: inv ? ((cur - inv) / inv) * 100 : 0, pnl: cur - inv };
      })
      .filter((r: any) => r.pnl !== 0)
      .sort((a: any, b: any) => b.roi - a.roi)
      .slice(0, 10);

    return {
      buyVol, sellVol, buyCnt, sellCnt, buyGrams, sellGrams, realized,
      unrealized, avgInvSize, aum, totalGrams, totalInvested, totalInvestors,
      activeInRange: userIds.size, revenue, repeatPct, days, buckets, topRoi,
      mid,
    };
  }, [allTx, users, dash, range]);

  const exportEnabled = kpis && (allTx?.items || []).length > 0;

  return (
    <div className="space-y-4">
      {/* Range switcher */}
      <div className="flex flex-wrap gap-2 items-center">
        {(["today", "week", "month", "year", "all"] as const).map((r) => (
          <button
            key={r}
            onClick={() => setRange(r)}
            className={`px-3 py-1.5 rounded-full text-xs font-bold uppercase ${range === r ? "bg-brand-navy text-white" : "bg-slate-100 text-slate-700"}`}
          >
            {r}
          </button>
        ))}
        <button
          onClick={() => exportCsv(allTx?.items || [], "gold-tx-full")}
          disabled={!exportEnabled}
          className="ml-auto inline-flex items-center gap-1 px-3 py-1.5 rounded bg-emerald-600 text-white text-xs font-bold disabled:opacity-40"
        >
          <Download className="w-3.5 h-3.5" /> Full TX CSV
        </button>
      </div>

      {!kpis ? (
        <div className="p-8 text-center text-slate-400">Computing analytics…</div>
      ) : (
        <>
          {/* KPI grid */}
          <div>
            <SectionHeader>BUSINESS KPIs</SectionHeader>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard label="Total Investors" value={kpis.totalInvestors} sub="With active holdings" tint="blue" />
              <StatCard label="Active Investors" value={kpis.activeInRange} sub={`Traded in ${range}`} tint="emerald" />
              <StatCard label="Avg Investment Size" value={inr(kpis.avgInvSize)} sub="Per transaction" tint="amber" />
              <StatCard label="Repeat Buy Rate" value={`${kpis.repeatPct.toFixed(1)}%`} sub="Users w/ 2+ buys" tint="violet" />
            </div>
          </div>

          <div>
            <SectionHeader>FINANCIAL KPIs</SectionHeader>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard label="Buy Volume" value={inr(kpis.buyVol)} sub={`${kpis.buyCnt} buys · ${kpis.buyGrams.toFixed(2)}g`} tint="emerald" />
              <StatCard label="Sell Volume" value={inr(kpis.sellVol)} sub={`${kpis.sellCnt} sells · ${kpis.sellGrams.toFixed(2)}g`} tint="red" />
              <StatCard label="AUM (Live)" value={inr(kpis.aum)} sub={`${kpis.totalGrams.toFixed(2)} g @ ₹${kpis.mid.toLocaleString("en-IN")}`} tint="amber" />
              <StatCard label="Platform Revenue" value={inr(kpis.revenue)} sub="Spread earned" tint="blue" />
              <StatCard label="Total Invested" value={inr(kpis.totalInvested)} sub="Aggregate cost basis" tint="slate" />
              <StatCard
                label="Unrealized P/L"
                value={inr(kpis.unrealized)}
                sub="Users' open positions"
                tint={kpis.unrealized >= 0 ? "emerald" : "red"}
              />
              <StatCard
                label="Realized P/L"
                value={inr(kpis.realized)}
                sub="Closed sell trades"
                tint={kpis.realized >= 0 ? "emerald" : "red"}
              />
              <StatCard label="Net Gold Holdings" value={grams(kpis.totalGrams)} sub={`${(kpis.buyGrams - kpis.sellGrams).toFixed(4)}g net this period`} tint="amber" />
            </div>
          </div>

          <div>
            <SectionHeader>DAILY BUY VS SELL · LAST 14 DAYS</SectionHeader>
            <BuySellChart days={kpis.days} />
          </div>

          <div>
            <SectionHeader>HOLDINGS DISTRIBUTION</SectionHeader>
            <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-2">
              {kpis.buckets.map((b) => {
                const maxCnt = Math.max(1, ...kpis.buckets.map((x) => x.count));
                return (
                  <div key={b.label} className="flex items-center gap-3 text-xs">
                    <span className="w-16 font-bold text-slate-600">{b.label}</span>
                    <div className="flex-1 h-4 bg-slate-100 rounded overflow-hidden">
                      <div className="h-4 bg-amber-500 rounded" style={{ width: `${(b.count / maxCnt) * 100}%` }} />
                    </div>
                    <span className="w-10 text-right font-bold">{b.count}</span>
                  </div>
                );
              })}
            </div>
          </div>

          <div>
            <SectionHeader>TOP ROI INVESTORS</SectionHeader>
            <div className="bg-white border border-slate-200 rounded-xl overflow-x-auto">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    <th className="text-left px-3 py-2">#</th>
                    <th className="text-left px-3 py-2">User</th>
                    <th className="text-right px-3 py-2">P/L</th>
                    <th className="text-right px-3 py-2">ROI %</th>
                  </tr>
                </thead>
                <tbody>
                  {kpis.topRoi.map((r: { user_id: string; pnl: number; roi: number }, i: number) => (
                    <tr key={r.user_id} className="border-t border-slate-100">
                      <td className="px-3 py-2 text-slate-400">{i + 1}</td>
                      <td className="px-3 py-2 font-mono text-[10px]">{r.user_id?.slice(-10)}</td>
                      <td className={`px-3 py-2 text-right font-bold ${r.pnl >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                        {r.pnl >= 0 ? "+" : ""}{inr(r.pnl)}
                      </td>
                      <td className={`px-3 py-2 text-right font-bold ${r.roi >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                        {r.roi >= 0 ? "+" : ""}
                        {r.roi.toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                  {kpis.topRoi.length === 0 && (
                    <tr>
                      <td colSpan={4} className="text-center py-6 text-slate-400">
                        Not enough data yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function BuySellChart({ days }: { days: { d: string; buy: number; sell: number }[] }) {
  const maxV = Math.max(1, ...days.flatMap((d) => [d.buy, d.sell]));
  return (
    <div className="p-4 bg-white border border-slate-200 rounded-xl">
      <div className="flex items-end gap-1 h-40">
        {days.map((d) => (
          <div key={d.d} className="flex-1 flex flex-col items-center gap-1">
            <div className="flex-1 w-full flex flex-col justify-end gap-0.5">
              <div className="w-full bg-emerald-500 rounded-t" style={{ height: `${(d.buy / maxV) * 100}%`, minHeight: d.buy > 0 ? 2 : 0 }} title={`Buy ${inr(d.buy)}`} />
              <div className="w-full bg-red-500 rounded-t" style={{ height: `${(d.sell / maxV) * 100}%`, minHeight: d.sell > 0 ? 2 : 0 }} title={`Sell ${inr(d.sell)}`} />
            </div>
            <div className="text-[9px] text-slate-500 whitespace-nowrap">{d.d.slice(5)}</div>
          </div>
        ))}
      </div>
      <div className="flex gap-3 mt-3 text-xs justify-center">
        <span className="inline-flex items-center gap-1"><span className="w-3 h-3 bg-emerald-500 rounded" /> Buy</span>
        <span className="inline-flex items-center gap-1"><span className="w-3 h-3 bg-red-500 rounded" /> Sell</span>
      </div>
    </div>
  );
}

// ============================================================================
// Helpers
// ============================================================================
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
function KV({ label, value }: any) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] font-bold text-slate-500 uppercase">{label}</span>
      <span className="text-slate-800 font-bold">{value}</span>
    </div>
  );
}
function SectionHeader({ children }: any) {
  return <div className="text-xs font-black text-slate-700 tracking-widest mb-2">{children}</div>;
}

function exportCsv(rows: any[], filename: string) {
  if (!rows || rows.length === 0) return;
  const cols = Array.from(new Set(rows.flatMap((r) => Object.keys(r))));
  const esc = (v: any) => {
    if (v == null) return "";
    const s = typeof v === "string" ? v : JSON.stringify(v);
    if (s.includes(",") || s.includes("\"") || s.includes("\n")) return `"${s.replace(/"/g, '""')}"`;
    return s;
  };
  const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename}-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

/**
 * Admin — Market Data (Sprint 7 Slice 1)
 * ---------------------------------------
 * Configure the active market data provider + transport, manage API keys.
 * Live status view (catalog size, provider health, transport running state).
 */
import { useEffect, useState } from "react";
import { api } from "../lib/api";

type Category = { id: string; label: string; count: number };
type Settings = {
  provider: string;
  transport: string;
  interval_seconds: number;
  api_keys: Record<string, string>;
  enabled_categories: string[];
};
type Status = {
  settings: Settings;
  provider_health: any;
  transport_status: any;
  catalog_size: number;
  categories: Category[];
};

const PROVIDERS = [
  { id: "mock",           label: "Mock (development)" },
  { id: "twelvedata",     label: "TwelveData (needs API key)" },
];
const TRANSPORTS = [
  { id: "polling",   label: "HTTP Polling" },
  { id: "websocket", label: "WebSocket (auto-fallback to polling)" },
];

export default function AdminMarketData() {
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ type: "ok" | "err"; text: string } | null>(null);
  const [provider, setProvider] = useState("mock");
  const [transport, setTransport] = useState("polling");
  const [interval, setIntv] = useState(3);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});

  const load = async () => {
    try {
      const { data } = await api.get<Status>("/admin/market_data/status");
      setStatus(data);
      setProvider(data.settings.provider);
      setTransport(data.settings.transport);
      setIntv(data.settings.interval_seconds);
      setApiKeys(data.settings.api_keys || {});
    } catch (e: any) {
      setMsg({ type: "err", text: e?.response?.data?.detail || e?.message || "Failed to load" });
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const save = async () => {
    setSaving(true); setMsg(null);
    try {
      const { data } = await api.put("/admin/market_data/settings", {
        provider, transport,
        interval_seconds: Number(interval),
        api_keys: apiKeys,
      });
      setStatus((s) => (s ? { ...s, settings: data.settings } : s));
      setMsg({ type: "ok", text: "Settings saved — pipeline reloaded." });
      setTimeout(load, 500);
    } catch (e: any) {
      setMsg({ type: "err", text: e?.response?.data?.detail || e?.message || "Save failed" });
    } finally { setSaving(false); }
  };

  const test = async () => {
    try {
      const { data } = await api.post("/admin/market_data/test-provider");
      setMsg({ type: "ok", text: `Provider health: ${JSON.stringify(data.health)}` });
    } catch (e: any) {
      setMsg({ type: "err", text: e?.response?.data?.detail || e?.message || "Test failed" });
    }
  };

  if (loading) return <div className="p-6 text-slate-500">Loading market data settings…</div>;

  return (
    <div className="p-6 max-w-4xl">
      <h1 className="text-2xl font-bold mb-1">Market Data</h1>
      <p className="text-sm text-slate-500 mb-6">
        Provider &amp; transport for the multi-asset browser. Switching provider requires only an API key —
        frontend stays unchanged. Sprint 7 Slice 1.
      </p>

      {msg && (
        <div className={`mb-4 p-3 rounded text-sm ${msg.type === "ok" ? "bg-emerald-50 text-emerald-800" : "bg-rose-50 text-rose-800"}`}>
          {msg.text}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <StatusCard label="Catalog Size" value={String(status?.catalog_size ?? 0)} />
        <StatusCard label="Active Provider" value={status?.settings.provider ?? "-"} tint={status?.provider_health?.ok ? "green" : "amber"} />
        <StatusCard label="Transport" value={`${status?.transport_status?.name ?? "-"} · ${status?.transport_status?.running ? "running" : "idle"}`} />
      </div>

      <section className="bg-white rounded-lg border border-slate-200 shadow-sm p-5 mb-6">
        <h2 className="font-semibold mb-4">Provider</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-xs uppercase tracking-wide text-slate-500 font-semibold">Provider</span>
            <select
              className="mt-1 block w-full rounded-md border-slate-300 shadow-sm text-sm p-2 border"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            >
              {PROVIDERS.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-wide text-slate-500 font-semibold">Transport</span>
            <select
              className="mt-1 block w-full rounded-md border-slate-300 shadow-sm text-sm p-2 border"
              value={transport}
              onChange={(e) => setTransport(e.target.value)}
            >
              {TRANSPORTS.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs uppercase tracking-wide text-slate-500 font-semibold">Poll interval (s)</span>
            <input
              type="number" min={1} max={60} step={1}
              className="mt-1 block w-full rounded-md border-slate-300 shadow-sm text-sm p-2 border"
              value={interval} onChange={(e) => setIntv(Number(e.target.value))}
            />
          </label>
        </div>
      </section>

      <section className="bg-white rounded-lg border border-slate-200 shadow-sm p-5 mb-6">
        <h2 className="font-semibold mb-1">API Keys</h2>
        <p className="text-xs text-slate-500 mb-4">Keys are stored server-side and never exposed to the frontend.</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {["twelvedata", "alpha_vantage", "finnhub", "polygon"].map((k) => (
            <label key={k} className="block">
              <span className="text-xs uppercase tracking-wide text-slate-500 font-semibold">{k.replace("_", " ")}</span>
              <input
                type="password" placeholder="(not set)"
                className="mt-1 block w-full rounded-md border-slate-300 shadow-sm text-sm p-2 border"
                value={apiKeys[k] || ""}
                onChange={(e) => setApiKeys((prev) => ({ ...prev, [k]: e.target.value }))}
              />
            </label>
          ))}
        </div>
      </section>

      <section className="bg-white rounded-lg border border-slate-200 shadow-sm p-5 mb-6">
        <h2 className="font-semibold mb-4">Diagnostics</h2>
        <div className="text-xs font-mono bg-slate-50 rounded p-3 border max-h-64 overflow-auto">
          <pre>{JSON.stringify({ provider_health: status?.provider_health, transport_status: status?.transport_status }, null, 2)}</pre>
        </div>
      </section>

      <section className="bg-white rounded-lg border border-slate-200 shadow-sm p-5">
        <h2 className="font-semibold mb-4">Catalog Categories</h2>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {(status?.categories || []).map((c) => (
            <div key={c.id} className="text-center bg-slate-50 rounded p-2 border border-slate-200">
              <div className="text-xs text-slate-500 font-semibold">{c.label}</div>
              <div className="text-lg font-bold">{c.count}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="mt-6 flex gap-3">
        <button
          onClick={save}
          disabled={saving}
          className="px-6 py-2.5 rounded bg-sky-600 text-white font-semibold hover:bg-sky-700 disabled:opacity-60"
        >
          {saving ? "Saving…" : "Save Settings"}
        </button>
        <button
          onClick={test}
          className="px-6 py-2.5 rounded bg-slate-100 text-slate-700 font-semibold hover:bg-slate-200"
        >
          Test Provider
        </button>
      </div>
    </div>
  );
}

function StatusCard({ label, value, tint = "slate" }: { label: string; value: string; tint?: "slate" | "green" | "amber" }) {
  const bg = tint === "green" ? "bg-emerald-50 text-emerald-900 border-emerald-200"
    : tint === "amber" ? "bg-amber-50 text-amber-900 border-amber-200"
    : "bg-slate-50 text-slate-900 border-slate-200";
  return (
    <div className={`p-4 rounded border ${bg}`}>
      <div className="text-xs uppercase tracking-wide font-semibold opacity-70">{label}</div>
      <div className="text-xl font-bold mt-1">{value}</div>
    </div>
  );
}

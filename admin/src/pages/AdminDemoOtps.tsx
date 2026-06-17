import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, fmtDate } from "../lib/api";
import {
  Smartphone, RefreshCw, Clock, CheckCircle2, AlertTriangle, Search,
  Copy, KeyRound, XCircle, Shield,
} from "lucide-react";

type Otp = {
  mobile: string;
  purpose: string;
  otp_plain_demo: string;
  created_at: string;
  expires_at: string;
  attempts: number;
  consumed?: boolean;
  delivery?: { provider?: string; demo?: boolean };
};

type ApiResponse = {
  items: Otp[];
  count: number;
  live_mode?: boolean;
  warning?: string;
};

function timeLeft(expiresAt: string): { text: string; expired: boolean } {
  const exp = new Date(expiresAt).getTime();
  const now = Date.now();
  const diff = exp - now;
  if (diff <= 0) return { text: "Expired", expired: true };
  const m = Math.floor(diff / 60000);
  const s = Math.floor((diff % 60000) / 1000);
  return { text: `${m}m ${s}s`, expired: false };
}

type StatusFilter = "all" | "active" | "consumed" | "expired";

export default function AdminDemoOtps() {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [, setTick] = useState(0);

  // Auto-tick every second to refresh the countdown timer text
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const { data, isFetching, refetch } = useQuery<ApiResponse>({
    queryKey: ["demo-otps"],
    queryFn: async () => (await api.get("/admin/demo-otps")).data,
    refetchInterval: 5000,
  });

  const items = data?.items || [];
  const activeCount = items.filter((o) => !o.consumed && !timeLeft(o.expires_at).expired).length;
  const consumedCount = items.filter((o) => o.consumed).length;
  const expiredCount = items.filter((o) => !o.consumed && timeLeft(o.expires_at).expired).length;

  const filtered = useMemo(() => {
    let rows = items;
    if (status !== "all") {
      rows = rows.filter((o) => {
        const tl = timeLeft(o.expires_at);
        if (status === "active") return !o.consumed && !tl.expired;
        if (status === "consumed") return !!o.consumed;
        if (status === "expired") return !o.consumed && tl.expired;
        return true;
      });
    }
    if (search.trim()) {
      const q = search.trim();
      rows = rows.filter((o) => o.mobile.includes(q) || o.otp_plain_demo.includes(q));
    }
    return rows;
  }, [items, search, status]);

  const copy = (value: string) => {
    navigator.clipboard.writeText(value).catch(() => {});
  };

  // Live mode — page is intentionally empty for security
  if (data?.live_mode) {
    return (
      <div className="space-y-5">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2">
            <KeyRound className="w-6 h-6" /> Demo OTP Logs
          </h2>
          <p className="text-sm text-slate-500 mt-1">Testing / Demo Mode Only</p>
        </div>
        <div className="card bg-emerald-50 border-emerald-200 border">
          <div className="flex items-start gap-3">
            <Shield className="w-6 h-6 text-emerald-600 mt-0.5" />
            <div>
              <p className="font-extrabold text-emerald-900 text-lg">SMS Provider is LIVE 🎉</p>
              <p className="text-sm text-emerald-800 mt-1">
                Real OTPs are now being delivered via SMS to users. For security, OTP values are
                <b> never exposed</b> on this page in live mode.
              </p>
              <p className="text-xs text-emerald-700 mt-2">
                To switch back to demo mode (for testing), go to
                <b> API Management → SMS Provider</b> and enable <i>Force demo</i>.
              </p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-brand-navy flex items-center gap-2">
            <KeyRound className="w-6 h-6" /> Demo OTP Logs
          </h2>
          <p className="text-sm text-slate-500 mt-1">
            <span className="badge bg-amber-100 text-amber-800 border border-amber-300 mr-2">
              Testing / Demo Mode Only
            </span>
            Auto-refreshes every 5s · Window: last 10 minutes
          </p>
        </div>
        <button onClick={() => refetch()} className="btn-ghost gap-2 text-sm">
          <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} /> Refresh
        </button>
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-2xl px-4 py-3 flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-600 mt-0.5" />
        <div className="text-sm text-amber-900">
          <p className="font-extrabold">Demo Mode Only — Security Notice</p>
          <p>
            OTP values are visible here only while the <b>SMS Provider</b> is in demo mode.
            Once you add a real MSG91 / Twilio key in <b>API Management → SMS Provider</b>,
            this page will automatically hide all OTP values. Every access to this page is
            recorded in <b>Audit Logs</b>.
          </p>
        </div>
      </div>

      <div className="grid sm:grid-cols-4 gap-3">
        <Stat label="Active" value={activeCount} cls="from-emerald-500 to-emerald-600" Icon={CheckCircle2} />
        <Stat label="Consumed" value={consumedCount} cls="from-sky-500 to-blue-600" Icon={Shield} />
        <Stat label="Expired" value={expiredCount} cls="from-rose-500 to-red-600" Icon={XCircle} />
        <Stat label="Auto-refresh" value="every 5s" cls="from-violet-500 to-fuchsia-600" Icon={Clock} />
      </div>

      <div className="card flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-[220px]">
          <Search className="w-4 h-4 text-slate-400" />
          <input
            className="input"
            placeholder="Search by mobile number or OTP…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {(["all", "active", "consumed", "expired"] as StatusFilter[]).map((s) => (
            <button
              key={s}
              onClick={() => setStatus(s)}
              className={`px-3 py-1.5 rounded-full text-xs font-bold capitalize border transition ${
                status === s
                  ? "bg-brand-navy text-white border-brand-navy"
                  : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="card overflow-hidden">
        {filtered.length === 0 ? (
          <div className="text-slate-400 py-12 text-center">
            <Smartphone className="w-10 h-10 mx-auto opacity-40 mb-2" />
            <p className="font-bold">No matching demo OTPs</p>
            <p className="text-xs mt-1">
              Ask a user to request OTP from the mobile app, or test from <code>POST /api/auth/otp/request</code>
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-slate-500 uppercase font-bold border-b border-slate-200">
                  <th className="py-2 px-2">Mobile</th>
                  <th className="py-2 px-2">OTP Code</th>
                  <th className="py-2 px-2">Purpose</th>
                  <th className="py-2 px-2">Created</th>
                  <th className="py-2 px-2">Expires</th>
                  <th className="py-2 px-2">Expires In</th>
                  <th className="py-2 px-2">Attempts</th>
                  <th className="py-2 px-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((o, i) => {
                  const tl = timeLeft(o.expires_at);
                  return (
                    <tr key={`${o.mobile}-${o.created_at}-${i}`} className="border-b border-slate-100 hover:bg-slate-50">
                      <td className="py-2 px-2 font-mono whitespace-nowrap">+91 {o.mobile}</td>
                      <td className="py-2 px-2">
                        <button
                          onClick={() => copy(o.otp_plain_demo)}
                          className="font-mono text-lg font-extrabold text-brand-navy bg-amber-50 px-3 py-1 rounded border border-amber-200 hover:bg-amber-100 flex items-center gap-2"
                          title="Click to copy"
                        >
                          {o.otp_plain_demo}
                          <Copy className="w-3.5 h-3.5 opacity-60" />
                        </button>
                      </td>
                      <td className="py-2 px-2">
                        <span className="badge bg-slate-100 text-slate-700 capitalize">{o.purpose}</span>
                      </td>
                      <td className="py-2 px-2 text-xs text-slate-500 whitespace-nowrap">{fmtDate(o.created_at)}</td>
                      <td className="py-2 px-2 text-xs text-slate-500 whitespace-nowrap">{fmtDate(o.expires_at)}</td>
                      <td className="py-2 px-2 whitespace-nowrap">
                        <span
                          className={`font-bold text-xs ${
                            tl.expired ? "text-red-600" : "text-emerald-600"
                          }`}
                        >
                          {tl.text}
                        </span>
                      </td>
                      <td className="py-2 px-2">
                        <span className={`font-bold ${o.attempts >= 3 ? "text-red-600" : "text-slate-700"}`}>
                          {o.attempts} / 5
                        </span>
                      </td>
                      <td className="py-2 px-2 whitespace-nowrap">
                        {o.consumed ? (
                          <span className="badge bg-sky-50 text-sky-700 border border-sky-200">
                            <Shield className="w-3 h-3 inline mr-1" /> Consumed
                          </span>
                        ) : tl.expired ? (
                          <span className="badge bg-red-50 text-red-700 border border-red-200">
                            <XCircle className="w-3 h-3 inline mr-1" /> Expired
                          </span>
                        ) : (
                          <span className="badge bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <CheckCircle2 className="w-3 h-3 inline mr-1" /> Active
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card bg-slate-50 border-dashed text-sm text-slate-600">
        <p className="font-bold text-slate-700 mb-1">How to test</p>
        <ol className="list-decimal list-inside space-y-1 text-xs">
          <li>Open the mobile app → Login with Mobile → enter any 10-digit number → tap Send OTP</li>
          <li>This page auto-refreshes every 5s — the new OTP will appear at the top with status <b>Active</b></li>
          <li>Click the OTP code to copy it, then paste it in the mobile app</li>
          <li>After successful verification, status changes to <b>Consumed</b></li>
          <li>OTPs are valid for 5 minutes. Resend cooldown: 30s. Rate-limit: 5/hour per mobile</li>
        </ol>
      </div>
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

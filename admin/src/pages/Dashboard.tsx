import { useQuery } from "@tanstack/react-query";
import { api, inr } from "../lib/api";
import { Users as UsersIcon, Wallet, TrendingUp, Plane, ArrowUp, ArrowDown, FileCheck2 } from "lucide-react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, Legend } from "recharts";

type Stats = {
  users: { total: number; active: number; new_today: number; pending_kyc: number };
  wallet: { total_balance: number; total_deposits: number; total_withdrawals: number; cashback_paid: number };
  investments: { mutual_fund: number; stock: number; gold: number; fd: number; govt: number };
  bookings: { total: number; revenue: number };
  charts: { user_growth: { date: string; count: number }[]; tx_daily: { date: string; credits: number; debits: number }[] };
};

function Stat({ icon: Icon, label, value, sub, color = "sky" }: any) {
  const palette: Record<string, string> = {
    sky: "from-sky-400 to-sky-600 text-sky-600 bg-sky-50",
    green: "from-emerald-400 to-emerald-600 text-emerald-600 bg-emerald-50",
    amber: "from-amber-400 to-amber-600 text-amber-600 bg-amber-50",
    violet: "from-violet-400 to-violet-600 text-violet-600 bg-violet-50",
  };
  const [, , textCls, bgCls] = palette[color].split(" ");
  return (
    <div className="card flex items-start gap-3">
      <div className={`p-3 rounded-xl ${bgCls}`}><Icon className={`w-5 h-5 ${textCls}`} /></div>
      <div className="flex-1">
        <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{label}</p>
        <p className="text-2xl font-extrabold text-slate-900 mt-1">{value}</p>
        {sub ? <p className="text-xs text-slate-500 mt-1">{sub}</p> : null}
      </div>
    </div>
  );
}

export default function Dashboard() {
  const { data, isLoading } = useQuery<Stats>({
    queryKey: ["admin-stats"],
    queryFn: async () => (await api.get("/admin/dashboard/stats")).data,
  });

  if (isLoading || !data) return <div className="text-slate-500">Loading stats…</div>;

  const invSum = Object.values(data.investments).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-extrabold text-brand-navy">Platform Overview</h2>
        <p className="text-sm text-slate-500">Real-time pulse of My Funding Bank.</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <Stat icon={UsersIcon} label="Total Users" value={data.users.total.toLocaleString()} sub={`${data.users.new_today} new today`} color="sky" />
        <Stat icon={Wallet} label="Wallet Balance" value={inr(data.wallet.total_balance)} sub={`${data.users.active} active users`} color="green" />
        <Stat icon={TrendingUp} label="Total Invested" value={inr(invSum)} sub="MF · Stocks · Gold · FD · Govt" color="violet" />
        <Stat icon={Plane} label="Travel Revenue" value={inr(data.bookings.revenue)} sub={`${data.bookings.total} bookings`} color="amber" />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <Stat icon={ArrowDown} label="Total Deposits" value={inr(data.wallet.total_deposits)} color="green" />
        <Stat icon={ArrowUp} label="Total Sent" value={inr(data.wallet.total_withdrawals)} color="amber" />
        <Stat icon={Wallet} label="Cashback Paid" value={inr(data.wallet.cashback_paid)} color="violet" />
        <Stat icon={FileCheck2} label="KYC Pending" value={data.users.pending_kyc} sub="Tap KYC tab to review" color="amber" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-extrabold text-slate-900">User Growth · 30 days</h3>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={data.charts.user_growth}>
              <defs>
                <linearGradient id="userArea" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#38BDF8" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#38BDF8" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Area type="monotone" dataKey="count" stroke="#0EA5E9" strokeWidth={2.4} fill="url(#userArea)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-extrabold text-slate-900">Transactions · 30 days</h3>
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={data.charts.tx_daily}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Bar dataKey="credits" fill="#10B981" name="Credits" />
              <Bar dataKey="debits" fill="#EF4444" name="Debits" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="card">
        <h3 className="font-extrabold text-slate-900 mb-3">Investment Allocation</h3>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {[
            ["Mutual Funds", data.investments.mutual_fund, "bg-sky-50 text-sky-700 border-sky-200"],
            ["Stocks", data.investments.stock, "bg-violet-50 text-violet-700 border-violet-200"],
            ["Gold", data.investments.gold, "bg-amber-50 text-amber-700 border-amber-200"],
            ["FDs", data.investments.fd, "bg-emerald-50 text-emerald-700 border-emerald-200"],
            ["Govt", data.investments.govt, "bg-indigo-50 text-indigo-700 border-indigo-200"],
          ].map(([label, val, cls]: any) => (
            <div key={label} className={`p-3 rounded-xl border ${cls}`}>
              <p className="text-xs font-bold uppercase tracking-wide">{label}</p>
              <p className="text-lg font-extrabold mt-1">{inr(val)}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

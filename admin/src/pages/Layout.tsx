import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, Users as UsersIcon, FileCheck2, Wallet, ArrowLeftRight, LogOut, Menu, X, Bell, TrendingUp, Image, FileText, Settings as SettingsIcon, ShieldCheck, KeyRound, AlertTriangle, Plane, Shield, Trophy, ScrollText, Lock, Activity, Smartphone, FileSearch, Crown, Calculator, LineChart, ArrowUpFromLine, Bot, Copy, CreditCard, Coins } from "lucide-react";
import { Logo } from "../components/Logo";
import { useAdminAuth } from "../lib/auth";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

const ROLE_NAV: Record<string, string[]> = {
  super_admin: ["/", "/users", "/user-security", "/demo-otps", "/kyc", "/transactions", "/wallet", "/wallet-analytics", "/withdrawals", "/ai-advisor", "/ai-console", "/market-settings", "/market-data", "/live-market", "/copy-trading", "/payments", "/gold", "/notifications", "/push-logs", "/investments", "/calculator-config", "/forex-settings", "/travel", "/insurance", "/insurance/claims", "/rewards", "/tier-upgrades", "/cashback-editor", "/content", "/reports", "/audit", "/api-management", "/settings", "/admins"],
  admin: ["/", "/users", "/user-security", "/demo-otps", "/kyc", "/transactions", "/wallet", "/wallet-analytics", "/withdrawals", "/ai-advisor", "/ai-console", "/market-settings", "/market-data", "/live-market", "/copy-trading", "/payments", "/gold", "/notifications", "/push-logs", "/investments", "/calculator-config", "/forex-settings", "/travel", "/insurance", "/insurance/claims", "/rewards", "/tier-upgrades", "/cashback-editor", "/content", "/reports", "/audit", "/api-management", "/settings"],
  finance_manager: ["/", "/users", "/transactions", "/wallet", "/wallet-analytics", "/withdrawals", "/insurance/claims", "/rewards", "/tier-upgrades", "/reports", "/audit", "/gold"],
  support_manager: ["/", "/users", "/kyc", "/transactions", "/notifications", "/push-logs", "/travel", "/insurance", "/insurance/claims", "/tier-upgrades"],
  investment_manager: ["/", "/users", "/investments", "/calculator-config", "/content", "/gold"],
};

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/users", label: "Users", icon: UsersIcon },
  { to: "/user-security", label: "User Security", icon: Lock },
  { to: "/demo-otps", label: "Demo OTPs", icon: Smartphone },
  { to: "/kyc", label: "KYC Review", icon: FileCheck2 },
  { to: "/transactions", label: "Transactions", icon: ArrowLeftRight },
  { to: "/wallet", label: "Wallet Adjust", icon: Wallet },
  { to: "/wallet-analytics", label: "Wallet Analytics", icon: Activity },
  { to: "/withdrawals", label: "Withdrawals", icon: ArrowUpFromLine },
  { to: "/ai-advisor", label: "AI Advisor", icon: Bot },
  { to: "/ai-console", label: "AI Console (S7C.2)", icon: Bot },
  { to: "/market-settings", label: "Market Settings", icon: LineChart },
  { to: "/market-data", label: "Market Data (S7)", icon: LineChart },
  { to: "/live-market", label: "Live Market (S7.5)", icon: Activity },
  { to: "/copy-trading", label: "Copy Trading", icon: Copy },
  { to: "/payments", label: "Payments (S8)", icon: CreditCard },
  { to: "/gold", label: "Gold Console (S10)", icon: Coins },
  { to: "/notifications", label: "Notifications", icon: Bell },
  { to: "/push-logs", label: "Push Logs", icon: Activity },
  { to: "/investments", label: "Investments", icon: TrendingUp },
  { to: "/calculator-config", label: "Calculator Settings", icon: Calculator },
  { to: "/forex-settings", label: "Forex Trading", icon: LineChart },
  { to: "/travel", label: "Travel", icon: Plane },
  { to: "/insurance", label: "Insurance", icon: Shield },
  { to: "/insurance/claims", label: "Insurance Claims", icon: FileSearch },
  { to: "/rewards", label: "Rewards", icon: Trophy },
  { to: "/tier-upgrades", label: "Tier Upgrades", icon: Crown },
  { to: "/cashback-editor", label: "Cashback Editor", icon: Trophy },
  { to: "/content", label: "Content", icon: Image },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/audit", label: "Audit Logs", icon: ScrollText },
  { to: "/api-management", label: "API Management", icon: KeyRound },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
  { to: "/admins", label: "Admin Users", icon: ShieldCheck },
];

export default function Layout() {
  const { admin, logout } = useAdminAuth();
  const [open, setOpen] = useState(false);
  const allowed = new Set(ROLE_NAV[admin?.role || "support_manager"] || []);
  const navItems = NAV.filter((n) => allowed.has(n.to));
  const { data: apiStatus } = useQuery({
    queryKey: ["api-status-banner"],
    queryFn: async () => (await api.get("/app/api-status")).data as { any_demo: boolean; demo_count: number; live_count: number },
    refetchInterval: 30000,
  });
  return (
    <div className="min-h-screen bg-slate-50 flex">
      {/* Sidebar */}
      <aside className={`fixed lg:static inset-y-0 left-0 z-30 w-64 bg-gradient-to-b from-brand-navy to-slate-900 text-white p-4 transform transition-transform ${open ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}>
        <div className="flex items-center justify-between lg:justify-start gap-3 mb-8">
          <div className="flex items-center gap-3">
            <Logo size={40} />
            <div>
              <p className="font-extrabold leading-tight">My Funding</p>
              <p className="text-[10px] text-sky-300 font-bold tracking-widest">BANK · ADMIN</p>
            </div>
          </div>
          <button onClick={() => setOpen(false)} className="lg:hidden p-1"><X className="w-5 h-5" /></button>
        </div>
        <nav className="space-y-1">
          {navItems.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition ${
                  isActive ? "bg-gradient-to-r from-brand-primary to-brand-secondary text-white shadow-glow" : "text-slate-300 hover:bg-white/5"
                }`
              }
            >
              <n.icon className="w-5 h-5" /> {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="absolute bottom-4 left-4 right-4 border-t border-white/10 pt-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-9 h-9 rounded-full bg-brand-primary/30 border border-brand-primary/60 flex items-center justify-center font-extrabold">
              {admin?.name?.split(" ").map((p) => p[0]).slice(0, 2).join("")}
            </div>
            <div className="text-xs leading-tight">
              <p className="font-bold">{admin?.name}</p>
              <p className="text-slate-400">{admin?.role.replace("_", " ")}</p>
            </div>
          </div>
          <button onClick={logout} className="w-full flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-semibold text-red-300 hover:bg-red-500/10">
            <LogOut className="w-4 h-4" /> Sign out
          </button>
        </div>
      </aside>

      {open ? <div onClick={() => setOpen(false)} className="fixed inset-0 z-20 bg-black/40 lg:hidden" /> : null}

      <main className="flex-1 lg:ml-0">
        <header className="sticky top-0 z-10 bg-white/80 backdrop-blur border-b border-slate-200 px-4 lg:px-8 py-4 flex items-center justify-between">
          <button onClick={() => setOpen(true)} className="lg:hidden p-2"><Menu className="w-5 h-5" /></button>
          <div className="hidden lg:block">
            <h1 className="text-lg font-extrabold text-brand-navy">Admin Console</h1>
            <p className="text-xs text-slate-500">Manage everything across My Funding Bank from here.</p>
          </div>
          <div className="flex items-center gap-3">
            {apiStatus?.any_demo ? (
              <NavLink to="/api-management" className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100">
                <AlertTriangle className="w-3.5 h-3.5" /> Demo Mode · {apiStatus.demo_count}
              </NavLink>
            ) : null}
            <div className="text-right text-xs text-slate-500">
              Logged in as <span className="font-bold text-slate-800">{admin?.email}</span>
            </div>
          </div>
        </header>
        {apiStatus?.any_demo ? (
          <div className="bg-amber-50 border-b border-amber-200 px-4 lg:px-8 py-2 flex items-start gap-2 text-sm text-amber-800">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <span><b>Live API keys are not configured yet.</b> Demo data is being used for {apiStatus.demo_count} integration{apiStatus.demo_count > 1 ? "s" : ""}. <NavLink to="/api-management" className="underline font-bold">Configure now →</NavLink></span>
          </div>
        ) : null}
        <div className="px-4 lg:px-8 py-6"><Outlet /></div>
      </main>
    </div>
  );
}

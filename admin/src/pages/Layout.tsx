import { Outlet, NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, Users as UsersIcon, FileCheck2, Wallet, ArrowLeftRight, LogOut, Menu, X, Bell, TrendingUp, Image, FileText, Settings as SettingsIcon, ShieldCheck } from "lucide-react";
import { Logo } from "../components/Logo";
import { useAdminAuth } from "../lib/auth";
import { useState } from "react";

const ROLE_NAV: Record<string, string[]> = {
  super_admin: ["/", "/users", "/kyc", "/transactions", "/wallet", "/notifications", "/investments", "/content", "/reports", "/settings", "/admins"],
  admin: ["/", "/users", "/kyc", "/transactions", "/wallet", "/notifications", "/investments", "/content", "/reports", "/settings"],
  finance_manager: ["/", "/users", "/transactions", "/wallet", "/reports"],
  support_manager: ["/", "/users", "/kyc", "/transactions", "/notifications"],
  investment_manager: ["/", "/users", "/investments", "/content"],
};

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/users", label: "Users", icon: UsersIcon },
  { to: "/kyc", label: "KYC Review", icon: FileCheck2 },
  { to: "/transactions", label: "Transactions", icon: ArrowLeftRight },
  { to: "/wallet", label: "Wallet Adjust", icon: Wallet },
  { to: "/notifications", label: "Notifications", icon: Bell },
  { to: "/investments", label: "Investments", icon: TrendingUp },
  { to: "/content", label: "Content", icon: Image },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
  { to: "/admins", label: "Admin Users", icon: ShieldCheck },
];

export default function Layout() {
  const { admin, logout } = useAdminAuth();
  const [open, setOpen] = useState(false);
  const allowed = new Set(ROLE_NAV[admin?.role || "support_manager"] || []);
  const navItems = NAV.filter((n) => allowed.has(n.to));
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
          <div className="text-right text-xs text-slate-500">
            Logged in as <span className="font-bold text-slate-800">{admin?.email}</span>
          </div>
        </header>
        <div className="px-4 lg:px-8 py-6"><Outlet /></div>
      </main>
    </div>
  );
}

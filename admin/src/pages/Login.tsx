import { useState } from "react";
import { useAdminAuth } from "../lib/auth";
import { Logo } from "../components/Logo";
import { ShieldCheck, Mail, Lock, AlertCircle } from "lucide-react";
import { Navigate } from "react-router-dom";

export default function Login() {
  const { admin, login } = useAdminAuth();
  const [email, setEmail] = useState("admin@mfb.in");
  const [password, setPassword] = useState("Admin@MFB2026");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (admin) return <Navigate to="/" replace />;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await login(email, password);
    } catch (e: any) {
      setError(e?.response?.data?.detail || "Login failed");
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-50 to-sky-50 p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="flex justify-center mb-4"><Logo size={64} /></div>
          <h1 className="text-2xl font-extrabold text-brand-navy">My Funding Bank</h1>
          <p className="text-xs font-bold text-brand-secondary tracking-widest mt-1">ADMIN CONSOLE</p>
        </div>
        <form onSubmit={submit} className="card space-y-4">
          <div className="flex items-center gap-2 text-emerald-700 bg-emerald-50 border border-emerald-200 px-3 py-2 rounded-lg text-xs">
            <ShieldCheck className="w-4 h-4" />
            Secure access. All actions are audit-logged.
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Email</label>
            <div className="mt-1 relative">
              <Mail className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input type="email" className="input pl-10" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </div>
          </div>
          <div>
            <label className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Password</label>
            <div className="mt-1 relative">
              <Lock className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input type="password" className="input pl-10" value={password} onChange={(e) => setPassword(e.target.value)} required />
            </div>
          </div>
          {error ? (
            <div className="flex items-center gap-2 text-red-700 bg-red-50 border border-red-200 px-3 py-2 rounded-lg text-sm">
              <AlertCircle className="w-4 h-4" />{error}
            </div>
          ) : null}
          <button type="submit" disabled={loading} className="btn-primary w-full">
            {loading ? "Signing in…" : "Sign in"}
          </button>
          <p className="text-xs text-slate-500 text-center">
            Default: <span className="font-mono">admin@mfb.in</span> / <span className="font-mono">Admin@MFB2026</span>
          </p>
        </form>
      </div>
    </div>
  );
}

import { createContext, useContext, useEffect, useState, ReactNode, useCallback } from "react";
import { api } from "./api";

export type Admin = { admin_id: string; name: string; email: string; role: string };

type Ctx = {
  admin: Admin | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AdminCtx = createContext<Ctx | null>(null);

export function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [admin, setAdmin] = useState<Admin | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const t = localStorage.getItem("mfb_admin_token");
    if (!t) { setLoading(false); return; }
    try {
      const { data } = await api.get<Admin>("/admin/me");
      setAdmin(data);
    } catch {
      localStorage.removeItem("mfb_admin_token");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const login = useCallback(async (email: string, password: string) => {
    const { data } = await api.post("/admin/login", { email, password });
    localStorage.setItem("mfb_admin_token", data.token);
    setAdmin(data.admin);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("mfb_admin_token");
    setAdmin(null);
    window.location.hash = "#/login";
  }, []);

  return <AdminCtx.Provider value={{ admin, loading, login, logout }}>{children}</AdminCtx.Provider>;
}

export function useAdminAuth() {
  const ctx = useContext(AdminCtx);
  if (!ctx) throw new Error("useAdminAuth must be inside AdminAuthProvider");
  return ctx;
}

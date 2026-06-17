import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api, setAuthToken, getAuthToken } from "@/src/api/client";

export type User = {
  user_id: string;
  full_name: string;
  email: string;
  mobile: string;
  referral_code: string;
  kyc_status: string;
  created_at: string;
};

type Ctx = {
  user: User | null;
  loading: boolean;
  signIn: (token: string, user: User) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthCtx = createContext<Ctx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const token = await getAuthToken();
    if (!token) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const { data } = await api.get<User>("/auth/me");
      setUser(data);
    } catch {
      await setAuthToken(null);
      setUser(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const signIn = useCallback(async (token: string, u: User) => {
    await setAuthToken(token);
    setUser(u);
    // Fire and forget — register for push notifications (no-op on web / FCM not configured)
    try {
      const { registerForPush } = await import("@/src/notifications/registerPush");
      registerForPush(u.user_id).catch(() => {});
    } catch {}
  }, []);

  const signOut = useCallback(async () => {
    await setAuthToken(null);
    setUser(null);
  }, []);

  return (
    <AuthCtx.Provider value={{ user, loading, signIn, signOut, refresh }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

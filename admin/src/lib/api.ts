import axios from "axios";

export const api = axios.create({ baseURL: "/api", timeout: 20000 });

api.interceptors.request.use((config) => {
  const t = localStorage.getItem("mfb_admin_token");
  if (t) config.headers.Authorization = `Bearer ${t}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (e) => {
    if (e?.response?.status === 401) {
      localStorage.removeItem("mfb_admin_token");
      if (!window.location.hash.includes("/login")) window.location.hash = "#/login";
    }
    return Promise.reject(e);
  },
);

export function inr(n: number | undefined | null): string {
  if (n == null || isNaN(n as number)) return "₹0";
  return `₹${Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export function fmtDate(s?: string) {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return s;
  }
}

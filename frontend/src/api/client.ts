import axios, { AxiosError, AxiosInstance } from "axios";
import { storage } from "@/src/utils/storage";

const RAW_BASE_URL = process.env.EXPO_PUBLIC_BACKEND_URL || "";

/**
 * Exposed for diagnostics screen / debug toasts.
 */
export const BACKEND_URL: string = RAW_BASE_URL;
export const API_BASE_URL: string = RAW_BASE_URL ? `${RAW_BASE_URL.replace(/\/+$/, "")}/api` : "";
export const isBackendConfigured = (): boolean => Boolean(RAW_BASE_URL && RAW_BASE_URL.length > 0);

if (!isBackendConfigured()) {
  // eslint-disable-next-line no-console
  console.error(
    "[api/client] EXPO_PUBLIC_BACKEND_URL is missing — every API call will fail. " +
    "Check /app/frontend/.env at build time and ensure the env is inlined in the JS bundle.",
  );
}

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL || "https://invalid.localhost/api",
  timeout: 20000,
});

api.interceptors.request.use(async (config) => {
  const token = await storage.secureGet<string>("mfb_token", "");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  if (!isBackendConfigured()) {
    throw new Error("EXPO_PUBLIC_BACKEND_URL is missing (build-time env not inlined).");
  }
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error: AxiosError) => {
    // Log a structured error for diagnostics — easy to scan in `adb logcat`
    // eslint-disable-next-line no-console
    console.warn(
      "[api/client] request failed:",
      JSON.stringify({
        url: `${error?.config?.baseURL ?? ""}${error?.config?.url ?? ""}`,
        method: error?.config?.method,
        code: (error as any)?.code,
        status: error?.response?.status,
        data: error?.response?.data,
        message: error?.message,
      }, null, 2),
    );
    return Promise.reject(error);
  },
);

export async function setAuthToken(token: string | null) {
  if (token) await storage.secureSet("mfb_token", token);
  else await storage.secureRemove("mfb_token");
}

export async function getAuthToken(): Promise<string | null> {
  const t = await storage.secureGet<string>("mfb_token", "");
  return t || null;
}

/**
 * Lightweight, dependency-free axios formatter for human-readable toasts.
 */
export function describeAxiosError(e: any): string {
  if (!e) return "Unknown error";
  if (axios.isCancel?.(e)) return e.message || "Request cancelled";
  if (e?.response) {
    return `HTTP ${e.response.status} ${e.response.statusText || ""}: ${
      typeof e.response.data === "string"
        ? e.response.data
        : (e.response.data?.detail || JSON.stringify(e.response.data))
    }`;
  }
  if (e?.request) {
    return `Network unreachable (${e?.code || "no-code"}): ${e?.message || "no further info"}`;
  }
  return e?.message || String(e);
}

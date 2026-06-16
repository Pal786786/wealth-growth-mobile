import axios, { AxiosInstance } from "axios";
import { storage } from "@/src/utils/storage";

const BASE_URL = process.env.EXPO_PUBLIC_BACKEND_URL;

export const api: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/api`,
  timeout: 20000,
});

api.interceptors.request.use(async (config) => {
  const token = await storage.secureGet<string>("mfb_token", "");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export async function setAuthToken(token: string | null) {
  if (token) await storage.secureSet("mfb_token", token);
  else await storage.secureRemove("mfb_token");
}

export async function getAuthToken(): Promise<string | null> {
  const t = await storage.secureGet<string>("mfb_token", "");
  return t || null;
}

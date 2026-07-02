import { api } from "./client";

export type NotifItem = {
  notif_id: string; title: string; body: string; category: string; priority: string;
  deeplink?: string; image?: string; action_label?: string;
  read: boolean; delivered: boolean; opened_at?: string; created_at: string;
  campaign_id?: string; source?: string;
};
export type NotifList = {
  items: NotifItem[]; total: number; unread: number;
  per_category: Record<string, { total: number; unread: number }>;
  categories: { key: string; label: string }[];
};
export type NotifPrefs = {
  wallet_alerts: boolean; investment_alerts: boolean; ai_alerts: boolean;
  marketing: boolean; security_alerts: boolean; system_notifications: boolean;
  push_enabled: boolean; email_enabled: boolean; sms_enabled: boolean;
};

export const notifApi = {
  list: (opts: { limit?: number; category?: string; unread_only?: boolean; q?: string } = {}) =>
    api.get<NotifList>("/notifications", { params: opts }).then((r) => r.data),
  unreadCount: () => api.get<{ unread: number }>("/notifications/unread-count").then((r) => r.data.unread),
  markOne: (nid: string) => api.post(`/notifications/${nid}/read`).then((r) => r.data),
  markAll: (ids?: string[]) => api.post("/notifications/mark-read", { ids }).then((r) => r.data),
  delete: (nid: string) => api.delete(`/notifications/${nid}`).then((r) => r.data),
  clear: () => api.delete("/notifications").then((r) => r.data),
  getPrefs: () => api.get<{ preferences: NotifPrefs; categories: Record<string, string> }>("/notifications/preferences").then((r) => r.data),
  putPrefs: (patch: Partial<NotifPrefs>) => api.put<{ preferences: NotifPrefs }>("/notifications/preferences", patch).then((r) => r.data),
};

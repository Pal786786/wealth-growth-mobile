import { api } from "./client";

export type BankAccount = {
  bank_id: string; holder_name: string; bank_name: string; ifsc: string;
  account_masked: string; verified?: boolean;
  is_primary?: boolean; verified_at?: string; name_at_bank?: string;
};
export type Withdrawal = {
  withdrawal_id: string; reference_no: string; amount: number; charge: number;
  net_amount: number; status: string; created_at: string; updated_at: string;
  bank_snapshot: { holder_name: string; bank_name: string; ifsc: string; account_masked: string };
  reason?: string; reason_admin?: string;
  verified_at?: string; approved_at?: string; processing_at?: string;
  completed_at?: string; rejected_at?: string; failed_at?: string;
  auto_approved?: boolean;
  utr?: string;
  provider?: string;
  provider_reference?: string;
  settlement_status?: string;
  admin_override?: boolean;
};
export type WithdrawalSettings = {
  min_amount: number; max_amount: number;
  daily_max_amount: number; daily_max_count: number;
  monthly_max_amount?: number;
  charge_type: "flat" | "percentage"; charge_flat: number; charge_percent: number;
  free_threshold: number; promo_waiver: boolean; processing_time_hours: number;
  otp_expiry_seconds: number; otp_resend_cooldown: number;
  // Sprint 12.2
  require_verified_bank?: boolean;
  single_pending_only?: boolean;
  hard_reject_amount?: number;
  auto_approve_enabled?: boolean;
  auto_approve_threshold?: number;
  compliance_hold?: boolean;
};

export const withdrawalApi = {
  settings: () => api.get<WithdrawalSettings>("/wallet/withdrawals/settings").then((r) => r.data),
  listBanks: () => api.get<{ items: BankAccount[] }>("/wallet/withdrawals/bank-accounts").then((r) => r.data.items),
  addBank: (body: { holder_name: string; bank_name: string; ifsc: string; account_number: string }) =>
    api.post("/wallet/withdrawals/bank-accounts", body).then((r) => r.data),
  delBank: (bank_id: string) => api.delete(`/wallet/withdrawals/bank-accounts/${bank_id}`).then((r) => r.data),
  quote: (amount: number, bank_account_id: string) =>
    api.post<{ amount: number; charge: number; net_amount: number; processing_time_hours: number }>(
      "/wallet/withdrawals/quote", { amount, bank_account_id }).then((r) => r.data),
  create: (amount: number, bank_account_id: string, reason?: string) =>
    api.post<{ ok: boolean; withdrawal_id: string; reference_no: string; charge: number; net_amount: number; otp_expires_in: number; otp_demo?: string }>(
      "/wallet/withdrawals/request", { amount, bank_account_id, reason }).then((r) => r.data),
  verifyOtp: (withdrawal_id: string, otp: string) =>
    api.post<{ ok: boolean; status: string; auto_approved?: boolean; utr?: string; provider_reference?: string; settlement_status?: string }>(
      "/wallet/withdrawals/verify-otp", { withdrawal_id, otp }).then((r) => r.data),
  resendOtp: (withdrawal_id: string) =>
    api.post<{ ok: boolean; otp_expires_in: number; otp_demo?: string }>(
      "/wallet/withdrawals/resend-otp", { withdrawal_id }).then((r) => r.data),
  cancel: (wid: string) => api.post(`/wallet/withdrawals/${wid}/cancel`).then((r) => r.data),
  history: (limit = 50, status?: string) =>
    api.get<{ items: Withdrawal[]; total: number }>("/wallet/withdrawals", {
      params: { limit, status },
    }).then((r) => r.data),
  detail: (wid: string) =>
    api.get<{ withdrawal: Withdrawal; timeline: { event: string; actor: string; at: string; meta?: any }[] }>(
      `/wallet/withdrawals/${wid}`).then((r) => r.data),
};

export type IfscInfo = {
  BANK: string; BRANCH: string; CITY: string; STATE: string;
  ADDRESS?: string; DISTRICT?: string; MICR?: string; CENTRE?: string;
  IFSC: string;
};

/** Razorpay IFSC lookup — free, no key required. Falls back gracefully. */
export async function lookupIfsc(ifsc: string): Promise<IfscInfo | null> {
  const clean = ifsc.trim().toUpperCase();
  if (!/^[A-Z]{4}0[A-Z0-9]{6}$/.test(clean)) return null;
  try {
    const r = await fetch(`https://ifsc.razorpay.com/${clean}`, {
      method: "GET",
    });
    if (!r.ok) return null;
    const data = await r.json();
    if (!data || !data.BANK) return null;
    return data as IfscInfo;
  } catch {
    return null;
  }
}

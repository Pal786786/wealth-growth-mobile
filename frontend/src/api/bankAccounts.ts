import { api } from "./client";

export type BankAccount = {
  bank_id: string;
  holder_name: string;
  bank_name: string;
  ifsc: string;
  account_number?: string;   // stripped by API for security
  account_masked?: string;   // "XXXX<last4>" from API
  verified: boolean;
  verification_method?: string | null;
  last_verification_status?: "verified" | "pending" | "failed" | "error" | null;
  last_verified_provider?: string;
  last_verified_at?: string;
  name_at_bank?: string;
  name_match_score?: number;
  is_primary?: boolean;
};

export type BVConfig = {
  provider: string;
  configured: boolean;
  min_name_match_score: number;
  env?: string;
};

export type BVHistoryItem = {
  verification_id: string;
  bank_id: string;
  provider: string;
  status: "verified" | "pending" | "failed" | "error";
  matched_name?: string | null;
  name_match_score?: number;
  reason?: string | null;
  reference_id?: string;
  created_at: string;
};

export const bankApi = {
  list: async () =>
    (await api.get<{ items: BankAccount[]; count?: number }>("/wallet/withdrawals/bank-accounts")).data,
  add: async (body: {
    holder_name: string; bank_name: string; ifsc: string; account_number: string;
  }) => (await api.post<{ ok: boolean; bank_id: string; duplicate?: boolean }>(
    "/wallet/withdrawals/bank-accounts", body,
  )).data,
  remove: async (bank_id: string) =>
    (await api.delete(`/wallet/withdrawals/bank-accounts/${bank_id}`)).data,
  // Bank Verification (Sprint 12.1)
  bvConfig: async () => (await api.get<BVConfig>("/bank-verification/config")).data,
  verify: async (bank_id: string, force = false) =>
    (await api.post<{
      ok: boolean; bank_id: string; status: string; provider: string;
      matched_name?: string | null; name_match_score?: number;
      reference_id?: string; reason?: string | null;
      already_verified?: boolean; duplicate?: boolean;
    }>(`/bank-verification/verify/${bank_id}?force=${force}`)).data,
  setPrimary: async (bank_id: string) =>
    (await api.post(`/bank-verification/primary/${bank_id}`)).data,
  history: async (bank_id?: string) =>
    (await api.get<{ items: BVHistoryItem[]; count: number }>(
      "/bank-verification/history", { params: { bank_id } })).data,
};

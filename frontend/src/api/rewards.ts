import { api } from "./client";

export interface RewardWallet {
  balance: number;
  lifetime_earned: number;
  lifetime_spent: number;
  pending_rewards: number;
  locked_rewards: number;
  referral_count: number;
  referral_code: string;
  level: number;
  xp: number;
  next_level: number;
  next_level_xp: number;
  progress_pct: number;
  tier: { name: string; emoji: string; min_level: number };
  streak_current: number;
  streak_best: number;
}

export interface RewardTx {
  tx_id: string;
  internal_token_id: string;
  future_blockchain_id: string | null;
  migration_status: string;
  amount: number;
  balance_after: number;
  type: string;
  source: string;
  reference_id: string | null;
  reason: string;
  status: string;
  created_at: string;
  meta?: Record<string, any>;
}

export interface Badge {
  code: string;
  title: string;
  emoji: string;
  tier: number;
  unlocked: boolean;
  unlocked_at: string | null;
  reward: number;
}

export interface Campaign {
  campaign_id: string;
  name: string;
  description: string;
  reward: number;
  status: string;
  start_date: string;
  end_date: string;
}

export interface LeaderboardEntry {
  user_id: string;
  value: number;
  rank: number;
}

export const rewardsApi = {
  wallet: () => api.get<RewardWallet>("/mfb-rewards/wallet").then(r => r.data),

  history: (limit = 50, skip = 0, source?: string) =>
    api.get<{ items: RewardTx[]; count: number }>("/mfb-rewards/history", {
      params: { limit, skip, source },
    }).then(r => r.data),

  rules: () =>
    api.get<{ settings: any[]; tiers: any[] }>("/mfb-rewards/rules").then(r => r.data),

  claimDailyLogin: () => api.post("/mfb-rewards/daily-login").then(r => r.data),

  referrals: () =>
    api.get<{
      code: string; link: string; deep_link: string; qr_png_base64: string;
      items: any[]; totals: { total: number; installed: number; registered: number;
                              kyc_completed: number; first_deposit: number };
    }>("/mfb-rewards/referrals").then(r => r.data),

  achievements: () => api.get<{ items: Badge[] }>("/mfb-rewards/achievements").then(r => r.data.items),

  activeCampaigns: () =>
    api.get<{ items: Campaign[] }>("/mfb-rewards/campaigns/active").then(r => r.data.items),

  claimCampaign: (campaign_id: string) =>
    api.post("/mfb-rewards/campaigns/claim", { campaign_id }).then(r => r.data),

  leaderboard: (period: "weekly" | "monthly" | "all_time",
                 category: "earners" | "referrers" | "investors" | "traders") =>
    api.get<{ period: string; category: string; entries: LeaderboardEntry[] }>(
      "/mfb-rewards/leaderboard", { params: { period, category } },
    ).then(r => r.data),
};

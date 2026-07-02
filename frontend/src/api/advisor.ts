import { api } from "./client";
import * as SecureStore from "expo-secure-store";

export type Conversation = {
  conversation_id: string; title: string; message_count: number; tokens_est: number;
  created_at: string; updated_at: string; last_message_at?: string;
};
export type ChatMessage = {
  message_id: string; role: "user" | "assistant"; content: string; created_at: string;
  tokens_est?: number; rating?: number;
};
export type Goal = {
  goal_id: string; goal_type: string; title: string; target_amount: number;
  horizon_years: number; current_savings: number; risk_appetite: string;
  expected_return_pct: number; recommended_monthly_sip: number; probability_pct: number;
  ai_notes?: {
    strategy?: string; monthly_sip?: number; expected_return_pct?: number; probability?: number;
    asset_mix?: { asset: string; pct: number; why: string }[]; tips?: string[]; disclaimer?: string;
  };
  created_at: string; updated_at: string;
};
export type PortfolioAnalysis = {
  profile: any;
  insights: {
    headline: string;
    highlights: string[];
    recommendations: { action: string; why: string; risk: string; return_range: string; horizon: string }[];
    risks: string[];
    disclaimer?: string;
  };
  generated_at: string;
  demo?: boolean;
};

export const advisorApi = {
  suggestions: () => api.get<{ items: string[] }>("/ai/suggestions").then((r) => r.data.items),
  profile: () => api.get<{ profile: any }>("/ai/profile").then((r) => r.data.profile),
  listConversations: () => api.get<{ items: Conversation[] }>("/ai/conversations").then((r) => r.data.items),
  createConversation: (title?: string) =>
    api.post<{ conversation: Conversation }>("/ai/conversations", { title }).then((r) => r.data.conversation),
  getConversation: (cid: string) =>
    api.get<{ conversation: Conversation; messages: ChatMessage[] }>(`/ai/conversations/${cid}`).then((r) => r.data),
  deleteConversation: (cid: string) => api.delete(`/ai/conversations/${cid}`).then((r) => r.data),
  portfolioAnalyze: () => api.get<PortfolioAnalysis>("/ai/portfolio/analyze").then((r) => r.data),
  listGoals: () => api.get<{ items: Goal[] }>("/ai/goals").then((r) => r.data.items),
  createGoal: (b: { goal_type: string; title: string; target_amount: number; horizon_years: number; current_savings?: number; risk_appetite?: string }) =>
    api.post<{ goal: Goal }>("/ai/goals", b).then((r) => r.data.goal),
  getGoal: (gid: string) => api.get<{ goal: Goal }>(`/ai/goals/${gid}`).then((r) => r.data.goal),
  deleteGoal: (gid: string) => api.delete(`/ai/goals/${gid}`).then((r) => r.data),
  feedback: (message_id: string, rating: number, note?: string) =>
    api.post("/ai/feedback", { message_id, rating, note }).then((r) => r.data),
};

/**
 * Streaming chat over SSE, consumed with XMLHttpRequest.onprogress.
 * Fetch streams aren't reliable on React Native; XHR responseText incremental read works on iOS+Android+Web.
 */
export type StreamEvent =
  | { type: "hello"; conversation_id: string }
  | { type: "start"; user_message_id: string; assistant_message_id: string; profile_snapshot?: any }
  | { type: "delta"; text: string }
  | { type: "done"; assistant_message_id: string; tokens_est?: number; elapsed_ms?: number; demo?: boolean }
  | { type: "error"; error: string };

export function streamChat(
  opts: { conversation_id?: string; message: string },
  onEvent: (ev: StreamEvent) => void,
): { abort: () => void } {
  const backend = (process.env.EXPO_PUBLIC_BACKEND_URL || "").replace(/\/$/, "");
  const url = `${backend}/api/ai/chat/stream`;
  let xhr: XMLHttpRequest | null = null;
  let aborted = false;

  try {
    xhr = new XMLHttpRequest();
    xhr.open("POST", url, true);
    xhr.setRequestHeader("content-type", "application/json");
  } catch (e: any) {
    // If XHR itself can't be constructed (shouldn't happen), fail gracefully
    // so the calling component doesn't crash the whole screen.
    setTimeout(() => onEvent({ type: "error", error: e?.message || "XHR init failed" }), 0);
    return { abort: () => { aborted = true; } };
  }

  SecureStore.getItemAsync("mfb_token").then((raw) => {
    if (aborted || !xhr) return;
    let tok: string | null = null;
    if (raw) { try { tok = JSON.parse(raw); } catch { tok = raw; } }
    try { if (tok) xhr.setRequestHeader("Authorization", `Bearer ${tok}`); } catch { /* header errors shouldn't kill the screen */ }
    let idx = 0;
    xhr.onprogress = () => {
      try {
        if (!xhr) return;
        const raw = xhr.responseText;
        const chunk = raw.slice(idx);
        idx = raw.length;
        // parse SSE events (event: ...\ndata: ...\n\n)
        const blocks = (chunk || "").split("\n\n");
        for (const b of blocks) {
          if (!b.trim()) continue;
          let event = "";
          let data = "";
          for (const line of b.split("\n")) {
            if (line.startsWith("event: ")) event = line.slice(7).trim();
            else if (line.startsWith("data: ")) data += line.slice(6);
          }
          if (!event || !data) continue;
          try {
            const parsed = JSON.parse(data);
            onEvent({ type: event as any, ...(parsed || {}) });
          } catch { /* skip incomplete block */ }
        }
      } catch (e) {
        // Never let SSE parse errors crash the whole app.
        // eslint-disable-next-line no-console
        console.warn("[streamChat] onprogress parse error", e);
      }
    };
    xhr.onerror = () => onEvent({ type: "error", error: "Network error" });
    xhr.onreadystatechange = () => { if (xhr && xhr.readyState === 4 && xhr.status >= 400) onEvent({ type: "error", error: `HTTP ${xhr.status}` }); };
    try {
      xhr.send(JSON.stringify(opts));
    } catch (e: any) {
      onEvent({ type: "error", error: e?.message || "Send failed" });
    }
  }).catch((e) => {
    // SecureStore rejected — surface as a proper stream error rather than
    // an unhandled promise rejection at module scope.
    onEvent({ type: "error", error: `Auth read failed: ${String(e).slice(0, 100)}` });
  });

  return {
    abort: () => {
      aborted = true;
      try { xhr?.abort(); } catch { /* ignore */ }
    },
  };
}

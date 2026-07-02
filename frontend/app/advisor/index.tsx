import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, ScrollView, ActivityIndicator, KeyboardAvoidingView, Platform } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter, useFocusEffect } from "expo-router";
import { ChevronLeft, Send, Bot, User as UserIcon, Sparkles, ThumbsUp, ThumbsDown, TrendingUp, Target, RotateCcw, PieChart } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { advisorApi, streamChat, type ChatMessage } from "@/src/api/advisor";

type UiMessage = ChatMessage & { streaming?: boolean };

export default function AdvisorChat() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [convId, setConvId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [analytics, setAnalytics] = useState<{ health_score: number; risk_bucket: string; confidence_pct: number } | null>(null);
  const scrollRef = useRef<ScrollView>(null);
  const streamCtrl = useRef<{ abort: () => void } | null>(null);

  const load = useCallback(async () => {
    try {
      const [sugs, prof] = await Promise.all([advisorApi.suggestions(), advisorApi.profile().catch(() => null)]);
      setSuggestions(sugs);
      if (prof?.analytics) setAnalytics(prof.analytics);
    } catch { /* ignore */ }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  useEffect(() => () => { streamCtrl.current?.abort(); }, []);

  const scrollToEnd = () => setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 60);

  const send = useCallback((text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || streaming) return;
    setInput("");
    setStreaming(true);
    const now = new Date().toISOString();
    const tempUser: UiMessage = { message_id: `u_local_${Date.now()}`, role: "user", content: msg, created_at: now };
    const tempAsst: UiMessage = { message_id: `a_local_${Date.now() + 1}`, role: "assistant", content: "", created_at: now, streaming: true };
    setMessages((m) => [...m, tempUser, tempAsst]);
    scrollToEnd();

    streamCtrl.current = streamChat({ conversation_id: convId || undefined, message: msg }, (ev) => {
      if (ev.type === "hello") {
        if (ev.conversation_id && !convId) setConvId(ev.conversation_id);
      } else if (ev.type === "start") {
        setMessages((m) => m.map((x) => x.message_id === tempUser.message_id ? { ...x, message_id: ev.user_message_id }
          : x.message_id === tempAsst.message_id ? { ...x, message_id: ev.assistant_message_id } : x));
        if (ev.profile_snapshot) setAnalytics(ev.profile_snapshot);
      } else if (ev.type === "delta") {
        setMessages((m) => m.map((x) => x.message_id === ev && (x as any).streaming ? x : x));
        setMessages((m) => {
          const copy = [...m];
          const idx = copy.findIndex((x) => x.streaming);
          if (idx >= 0) copy[idx] = { ...copy[idx], content: (copy[idx].content || "") + ev.text };
          return copy;
        });
        scrollToEnd();
      } else if (ev.type === "done") {
        setMessages((m) => m.map((x) => x.streaming ? { ...x, streaming: false, message_id: ev.assistant_message_id || x.message_id, tokens_est: ev.tokens_est } : x));
        setStreaming(false);
        scrollToEnd();
      } else if (ev.type === "error") {
        show("error", ev.error || "Something went wrong");
        setMessages((m) => m.map((x) => x.streaming ? { ...x, streaming: false, content: x.content || "⚠️ Couldn't reach the AI. Please try again." } : x));
        setStreaming(false);
      }
    });
  }, [input, streaming, convId, show]);

  const rate = async (message_id: string, rating: number) => {
    try {
      await advisorApi.feedback(message_id, rating);
      setMessages((m) => m.map((x) => x.message_id === message_id ? { ...x, rating } : x));
      show("success", rating === 1 ? "Thanks for the feedback!" : "Noted. We'll do better.");
    } catch { /* ignore */ }
  };

  const resetConv = () => { setConvId(null); setMessages([]); };

  const hasContent = messages.length > 0;

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <View style={{ flex: 1 }}>
          <Text style={[s.title, { color: palette.textPrimary }]}>AI Wealth Advisor</Text>
          <Text style={{ color: palette.textMuted, fontSize: 10 }}>Powered by Claude Sonnet 4.5</Text>
        </View>
        {hasContent && (
          <Pressable onPress={resetConv} hitSlop={12} style={[s.chipBtn, { borderColor: palette.border }]}>
            <RotateCcw color={palette.primary} size={14} />
            <Text style={[s.chipTxt, { color: palette.primary }]}>New</Text>
          </Pressable>
        )}
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView ref={scrollRef} contentContainerStyle={{ padding: 16, paddingBottom: 24 }} keyboardShouldPersistTaps="handled">
          {!hasContent && (
            <>
              <LinearGradient colors={["#1E1B4B", "#0EA5E9"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.hero}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
                  <View style={s.avatar}><Bot color="#fff" size={28} /></View>
                  <View style={{ flex: 1 }}>
                    <Text style={s.heroTitle}>Hi 👋 I&apos;m your Wealth Advisor</Text>
                    <Text style={s.heroSub}>Ask me about your investments, SIPs, goals or portfolio.</Text>
                  </View>
                </View>
                {analytics && (
                  <View style={s.scoreRow}>
                    <ScoreChip label="Health" value={`${analytics.health_score}/100`} />
                    <ScoreChip label="Risk" value={analytics.risk_bucket} />
                    <ScoreChip label="Confidence" value={`${analytics.confidence_pct}%`} />
                  </View>
                )}
              </LinearGradient>

              <View style={s.quickRow}>
                <QuickCard label="Portfolio" icon={PieChart} tint={palette.primary} onPress={() => router.push("/advisor/portfolio")} />
                <QuickCard label="Goals" icon={Target} tint={palette.warning} onPress={() => router.push("/advisor/goals")} />
                <QuickCard label="Insights" icon={TrendingUp} tint={palette.success} onPress={() => send("Give me 3 key insights about my portfolio")} />
              </View>

              <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Suggested Questions</Text>
              <View style={{ gap: 8 }}>
                {suggestions.map((q) => (
                  <Pressable key={q} onPress={() => send(q)} style={[s.suggBtn, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                    <Sparkles color={palette.primary} size={16} />
                    <Text style={[s.suggTxt, { color: palette.textPrimary }]}>{q}</Text>
                  </Pressable>
                ))}
              </View>
            </>
          )}

          {messages.map((m) => (
            <View key={m.message_id} style={[s.bubbleRow, { justifyContent: m.role === "user" ? "flex-end" : "flex-start" }]}>
              {m.role === "assistant" && (
                <View style={[s.msgAvatar, { backgroundColor: palette.primary + "22" }]}>
                  <Bot color={palette.primary} size={16} />
                </View>
              )}
              <View style={[s.bubble, m.role === "user" ? { backgroundColor: palette.primary } : { backgroundColor: palette.surface, borderColor: palette.border, borderWidth: 1 }]}>
                <Text style={[s.bubbleTxt, { color: m.role === "user" ? "#fff" : palette.textPrimary }]}>
                  {m.content || (m.streaming ? "…" : "")}
                  {m.streaming && <Text style={{ color: palette.textMuted, fontSize: 12 }}> ▌</Text>}
                </Text>
                {m.role === "assistant" && !m.streaming && m.content && (
                  <View style={s.rateRow}>
                    <Pressable onPress={() => rate(m.message_id, 1)} hitSlop={8} style={s.rateBtn}>
                      <ThumbsUp color={m.rating === 1 ? "#10B981" : palette.textMuted} size={12} />
                    </Pressable>
                    <Pressable onPress={() => rate(m.message_id, -1)} hitSlop={8} style={s.rateBtn}>
                      <ThumbsDown color={m.rating === -1 ? "#EF4444" : palette.textMuted} size={12} />
                    </Pressable>
                    {m.tokens_est ? <Text style={{ color: palette.textMuted, fontSize: 9 }}>{m.tokens_est} tok</Text> : null}
                  </View>
                )}
              </View>
              {m.role === "user" && (
                <View style={[s.msgAvatar, { backgroundColor: palette.chipBg }]}>
                  <UserIcon color={palette.textSecondary} size={16} />
                </View>
              )}
            </View>
          ))}

          {streaming && (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginTop: 6 }}>
              <TypingDot delay={0} palette={palette} />
              <TypingDot delay={150} palette={palette} />
              <TypingDot delay={300} palette={palette} />
              <Text style={{ color: palette.textMuted, fontSize: 11 }}>AI is thinking…</Text>
            </View>
          )}
        </ScrollView>

        <View style={[s.composer, { backgroundColor: palette.surface, borderTopColor: palette.border }]}>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder="Ask anything about your finances…"
            placeholderTextColor={palette.textMuted}
            style={[s.input, { color: palette.textPrimary, backgroundColor: palette.chipBg }]}
            multiline
            maxLength={4000}
            editable={!streaming}
            onSubmitEditing={() => send()}
            testID="advisor-input"
          />
          <Pressable
            onPress={() => send()}
            disabled={!input.trim() || streaming}
            style={({ pressed }) => [s.sendBtn, { backgroundColor: input.trim() && !streaming ? palette.primary : palette.textMuted, opacity: pressed ? 0.85 : 1 }]}
            testID="advisor-send"
          >
            {streaming ? <ActivityIndicator color="#fff" size="small" /> : <Send color="#fff" size={18} />}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

function ScoreChip({ label, value }: { label: string; value: string }) {
  return (
    <View style={s.scoreChip}>
      <Text style={s.scoreLabel}>{label}</Text>
      <Text style={s.scoreValue}>{value}</Text>
    </View>
  );
}

function QuickCard({ label, icon: Icon, tint, onPress }: { label: string; icon: any; tint: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.quickCard, { borderColor: tint + "55", backgroundColor: tint + "12", opacity: pressed ? 0.85 : 1 }]}>
      <Icon color={tint} size={20} />
      <Text style={[s.quickTxt, { color: tint }]}>{label}</Text>
    </Pressable>
  );
}

function TypingDot({ delay, palette }: { delay: number; palette: any }) {
  const [scale, setScale] = useState(0.7);
  useEffect(() => {
    let mounted = true;
    const t = setInterval(() => { if (mounted) setScale((v) => v === 0.7 ? 1.1 : 0.7); }, 500);
    setTimeout(() => setScale(1.1), delay);
    return () => { mounted = false; clearInterval(t); };
  }, [delay]);
  return <View style={{ width: 6, height: 6, borderRadius: 6, backgroundColor: palette.primary, transform: [{ scale }] }} />;
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { fontSize: 18, fontWeight: "800", letterSpacing: -0.3 },
  chipBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  chipTxt: { fontSize: 12, fontWeight: "800" },

  hero: { padding: 18, borderRadius: 22, gap: 14 },
  avatar: { width: 52, height: 52, borderRadius: 26, backgroundColor: "rgba(255,255,255,0.16)", alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "rgba(255,255,255,0.3)" },
  heroTitle: { color: "#fff", fontSize: 18, fontWeight: "800" },
  heroSub: { color: "rgba(255,255,255,0.85)", fontSize: 12, marginTop: 2 },
  scoreRow: { flexDirection: "row", gap: 8 },
  scoreChip: { flex: 1, backgroundColor: "rgba(255,255,255,0.15)", borderRadius: 12, padding: 8, borderWidth: 1, borderColor: "rgba(255,255,255,0.25)" },
  scoreLabel: { color: "rgba(255,255,255,0.7)", fontSize: 9, fontWeight: "800", letterSpacing: 0.6 },
  scoreValue: { color: "#fff", fontSize: 15, fontWeight: "900", marginTop: 2 },

  quickRow: { flexDirection: "row", gap: 8, marginTop: 16 },
  quickCard: { flex: 1, padding: 12, borderRadius: 14, borderWidth: 1, alignItems: "center", gap: 4 },
  quickTxt: { fontSize: 12, fontWeight: "800" },

  sectionTitle: { fontSize: 14, fontWeight: "800", marginTop: 20, marginBottom: 8 },
  suggBtn: { flexDirection: "row", alignItems: "center", gap: 8, padding: 12, borderRadius: 14, borderWidth: 1 },
  suggTxt: { fontSize: 13, fontWeight: "600", flex: 1 },

  bubbleRow: { flexDirection: "row", gap: 6, alignItems: "flex-end", marginBottom: 8 },
  msgAvatar: { width: 28, height: 28, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  bubble: { maxWidth: "78%", padding: 12, borderRadius: 16 },
  bubbleTxt: { fontSize: 14, lineHeight: 20 },
  rateRow: { flexDirection: "row", alignItems: "center", gap: 12, marginTop: 6 },
  rateBtn: { padding: 2 },

  composer: { flexDirection: "row", gap: 8, padding: 10, borderTopWidth: 1, alignItems: "flex-end" },
  input: { flex: 1, borderRadius: 20, paddingHorizontal: 14, paddingVertical: 10, minHeight: 44, maxHeight: 120, fontSize: 14 },
  sendBtn: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
});

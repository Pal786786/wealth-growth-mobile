import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, Share } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Gift, Share2, Copy, Trophy } from "lucide-react-native";
import * as Clipboard from "expo-clipboard";
import { LinearGradient } from "expo-linear-gradient";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { useAuth } from "@/src/auth/AuthProvider";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";

export default function Referral() {
  const { palette } = useTheme();
  const router = useRouter();
  const { user } = useAuth();
  const { show } = useToast();
  const [board, setBoard] = useState<any[]>([]);

  useEffect(() => { api.get("/referral/leaderboard").then(({ data }) => setBoard(data)).catch(() => {}); }, []);

  const code = user?.referral_code || "MFB000000";
  const copy = async () => { await Clipboard.setStringAsync(code); show("success", "Code copied"); };
  const share = async () => {
    try {
      await Share.share({
        message: `Join My Funding Bank with my code ${code} and we both earn ₹50! Download: https://myfundingbank.in`,
      });
    } catch {}
  };

  return (
    <Screen>
      <Pressable onPress={() => router.back()} style={s.back} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
      <ScrollView contentContainerStyle={s.scroll}>
        <LinearGradient colors={[palette.primary, palette.secondary]} style={s.hero}>
          <Gift color="#fff" size={32} />
          <Text style={s.heroLabel}>Refer & Earn</Text>
          <Text style={s.heroValue}>₹50 per friend</Text>
          <Text style={s.heroSub}>You and your friend both get rewarded</Text>
        </LinearGradient>

        <Card style={s.codeCard}>
          <Text style={[s.label, { color: palette.textSecondary }]}>YOUR REFERRAL CODE</Text>
          <Text style={[s.code, { color: palette.textPrimary }]} testID="referral-code">{code}</Text>
          <View style={s.codeActions}>
            <Pressable onPress={copy} style={[s.codeBtn, { borderColor: palette.border, backgroundColor: palette.surface }]} testID="copy-code-btn">
              <Copy color={palette.primary} size={16} />
              <Text style={{ color: palette.textPrimary, fontWeight: "700" }}>Copy</Text>
            </Pressable>
            <Pressable onPress={share} style={[s.codeBtn, { backgroundColor: palette.primary, borderColor: palette.primary }]} testID="share-code-btn">
              <Share2 color="#fff" size={16} />
              <Text style={{ color: "#fff", fontWeight: "700" }}>Share</Text>
            </Pressable>
          </View>
        </Card>

        <Text style={[s.section, { color: palette.textPrimary }]}>Leaderboard</Text>
        {board.length === 0 ? (
          <Card><Text style={{ color: palette.textSecondary, textAlign: "center" }}>No referrals yet — be the first!</Text></Card>
        ) : board.map((row, idx) => (
          <Card key={row.referral_code} style={s.leaderRow}>
            <View style={[s.rank, { backgroundColor: idx === 0 ? palette.warning + "30" : palette.surfaceAlt }]}>
              <Text style={{ fontWeight: "800", color: idx === 0 ? palette.warning : palette.textSecondary }}>#{idx + 1}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.leaderName, { color: palette.textPrimary }]}>{row.name}</Text>
              <Text style={[s.leaderCode, { color: palette.textMuted }]}>{row.referral_code}</Text>
            </View>
            <View style={{ flexDirection: "row", gap: 4, alignItems: "center" }}>
              <Trophy color={palette.warning} size={14} />
              <Text style={[s.leaderCount, { color: palette.textPrimary }]}>{row.count}</Text>
            </View>
          </Card>
        ))}
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
  scroll: { gap: 14, paddingBottom: 40 },
  hero: { borderRadius: 24, padding: 24, alignItems: "center", gap: 6, marginTop: 8 },
  heroLabel: { color: "rgba(255,255,255,0.9)", fontSize: 13, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase", marginTop: 8 },
  heroValue: { color: "#fff", fontSize: 32, fontWeight: "800" },
  heroSub: { color: "rgba(255,255,255,0.9)", fontSize: 13, fontWeight: "600" },
  codeCard: { alignItems: "center", gap: 8, padding: 20 },
  label: { fontSize: 11, fontWeight: "700", letterSpacing: 1.5 },
  code: { fontSize: 32, fontWeight: "800", letterSpacing: 4, marginVertical: 4 },
  codeActions: { flexDirection: "row", gap: 10, marginTop: 4, alignSelf: "stretch" },
  codeBtn: { flex: 1, flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 8, paddingVertical: 12, borderRadius: 12, borderWidth: 1 },
  section: { fontSize: 16, fontWeight: "800", marginTop: 4, letterSpacing: -0.3 },
  leaderRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  rank: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  leaderName: { fontSize: 14, fontWeight: "700" },
  leaderCode: { fontSize: 11, fontWeight: "600", marginTop: 2 },
  leaderCount: { fontSize: 14, fontWeight: "800" },
});

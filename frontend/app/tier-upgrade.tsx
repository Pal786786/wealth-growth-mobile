import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator } from "react-native";
import { useRouter, useLocalSearchParams } from "expo-router";
import { ChevronLeft, Crown, ArrowUp, Sparkles, CheckCircle2 } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { api } from "@/src/api/client";

const TIER_GRADIENT: Record<string, string[]> = {
  bronze:   ["#FBA74D", "#CD7F32"],
  silver:   ["#CBD5E1", "#94A3B8"],
  gold:     ["#FCD34D", "#F59E0B"],
  platinum: ["#7DD3FC", "#0EA5E9"],
  diamond:  ["#C4B5FD", "#A78BFA"],
};

type Tier = {
  id: string;
  name: string;
  min: number;
  emoji?: string;
  tagline?: string;
  cashback_rate_pct?: number;
  points_multiplier?: number;
  perks?: string[];
};

type Upgrade = {
  upgrade_id: string;
  user_id: string;
  old_tier_id: string;
  new_tier_id: string;
  points_at_upgrade: number;
  old_tier?: Tier;
  new_tier?: Tier;
  at: string;
};

export default function TierUpgradeScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const [data, setData] = useState<Upgrade | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        if (id) {
          const { data: d } = await api.get(`/rewards/tier/upgrade/${id}`);
          setData(d);
        } else {
          // Fallback: load latest
          const { data: h } = await api.get("/rewards/tier/history?limit=1");
          if (h.items?.length) {
            const { data: d } = await api.get(`/rewards/tier/upgrade/${h.items[0].upgrade_id}`);
            setData(d);
          }
        }
      } catch {}
      finally { setLoading(false); }
    })();
  }, [id]);

  if (loading) {
    return (
      <Screen>
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={palette.primary} />
        </View>
      </Screen>
    );
  }

  if (!data) {
    return (
      <Screen>
        <Pressable onPress={() => router.back()} style={{ paddingVertical: 8 }}>
          <ChevronLeft color={palette.textPrimary} size={26} />
        </Pressable>
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 24 }}>
          <Crown color={palette.textMuted} size={48} />
          <Text style={{ color: palette.textPrimary, fontSize: 18, fontWeight: "800", marginTop: 12 }}>No tier upgrades yet</Text>
          <Text style={{ color: palette.textSecondary, fontSize: 13, textAlign: "center", marginTop: 6 }}>
            Spend more, refer friends, or invest to unlock your next tier!
          </Text>
        </View>
      </Screen>
    );
  }

  const newT = data.new_tier!;
  const oldT = data.old_tier!;
  const grad = TIER_GRADIENT[newT.id] || TIER_GRADIENT.bronze;

  return (
    <Screen>
      <Pressable onPress={() => router.back()} style={{ paddingVertical: 8 }} testID="back-btn">
        <ChevronLeft color={palette.textPrimary} size={26} />
      </Pressable>
      <ScrollView contentContainerStyle={{ paddingBottom: 40, gap: 14 }}>
        {/* Hero gradient celebration card */}
        <View
          style={{
            borderRadius: 24,
            paddingVertical: 32,
            paddingHorizontal: 20,
            backgroundColor: grad[1],
            alignItems: "center",
            gap: 8,
            shadowColor: grad[1],
            shadowOpacity: 0.3,
            shadowRadius: 18,
            shadowOffset: { width: 0, height: 8 },
            elevation: 8,
            overflow: "hidden",
          }}
        >
          <Sparkles color="#fff" size={28} />
          <Text style={{ color: "rgba(255,255,255,0.85)", fontSize: 13, fontWeight: "700", letterSpacing: 1 }}>
            CONGRATULATIONS!
          </Text>
          <Text style={{ color: "#fff", fontSize: 64 }}>{newT.emoji}</Text>
          <Text style={{ color: "#fff", fontSize: 28, fontWeight: "800" }}>You're now {newT.name}</Text>
          <Text style={{ color: "rgba(255,255,255,0.92)", fontSize: 14, textAlign: "center", marginTop: 4 }}>
            {newT.tagline}
          </Text>
        </View>

        {/* From → To */}
        <Card style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <View style={{ flex: 1, alignItems: "center" }}>
            <Text style={{ fontSize: 30 }}>{oldT.emoji}</Text>
            <Text style={{ color: palette.textSecondary, fontWeight: "700", fontSize: 11, marginTop: 4 }}>PREVIOUS</Text>
            <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 15 }}>{oldT.name}</Text>
            <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 2 }}>{oldT.cashback_rate_pct}% cashback</Text>
          </View>
          <View style={{ paddingHorizontal: 8 }}>
            <View style={{ width: 36, height: 36, borderRadius: 18, backgroundColor: palette.primary + "1A", alignItems: "center", justifyContent: "center" }}>
              <ArrowUp color={palette.primary} size={20} />
            </View>
          </View>
          <View style={{ flex: 1, alignItems: "center" }}>
            <Text style={{ fontSize: 30 }}>{newT.emoji}</Text>
            <Text style={{ color: palette.primary, fontWeight: "700", fontSize: 11, marginTop: 4 }}>NEW</Text>
            <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 15 }}>{newT.name}</Text>
            <Text style={{ color: palette.success, fontSize: 10, marginTop: 2, fontWeight: "700" }}>{newT.cashback_rate_pct}% cashback</Text>
          </View>
        </Card>

        {/* Unlocked stats */}
        <View style={{ flexDirection: "row", gap: 10 }}>
          <Card style={{ flex: 1, alignItems: "center", gap: 4 }}>
            <Text style={{ fontSize: 11, color: palette.textSecondary, fontWeight: "700" }}>CASHBACK</Text>
            <Text style={{ color: palette.primary, fontSize: 22, fontWeight: "800" }}>{newT.cashback_rate_pct}%</Text>
            <Text style={{ fontSize: 10, color: palette.textMuted }}>on every spend</Text>
          </Card>
          <Card style={{ flex: 1, alignItems: "center", gap: 4 }}>
            <Text style={{ fontSize: 11, color: palette.textSecondary, fontWeight: "700" }}>POINTS</Text>
            <Text style={{ color: palette.primary, fontSize: 22, fontWeight: "800" }}>{newT.points_multiplier}×</Text>
            <Text style={{ fontSize: 10, color: palette.textMuted }}>on travel & insurance</Text>
          </Card>
        </View>

        {/* Perks */}
        <Card>
          <Text style={{ fontSize: 14, fontWeight: "800", color: palette.textPrimary, marginBottom: 12 }}>
            🎁 Benefits unlocked
          </Text>
          {(newT.perks || []).map((p, i) => (
            <View key={i} style={{ flexDirection: "row", alignItems: "flex-start", gap: 8, marginBottom: 8 }}>
              <CheckCircle2 color={palette.success} size={18} />
              <Text style={{ flex: 1, fontSize: 13, color: palette.textPrimary, lineHeight: 18 }}>{p}</Text>
            </View>
          ))}
        </Card>

        {/* Continue */}
        <Pressable
          onPress={() => router.replace("/rewards")}
          style={{ backgroundColor: palette.primary, paddingVertical: 14, borderRadius: 14, alignItems: "center", marginTop: 4 }}
          testID="continue-btn"
        >
          <Text style={{ color: "#fff", fontWeight: "800", fontSize: 15 }}>Continue to Rewards →</Text>
        </Pressable>
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({});

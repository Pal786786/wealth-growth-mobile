import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator, RefreshControl, Alert } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { ChevronLeft, Plus, Target, Trash2, TrendingUp, ChevronRight, Home, Car, Baby, Umbrella, Rocket } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { advisorApi, type Goal } from "@/src/api/advisor";
import { formatINR } from "@/src/utils/format";

const ICONS: Record<string, any> = {
  house: Home, car: Car, education: Baby, retirement: Rocket, emergency: Umbrella, custom: Target,
};

export default function GoalsScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [items, setItems] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { setItems(await advisorApi.listGoals()); } finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const del = (goal_id: string) => {
    Alert.alert("Delete goal?", "You can always create it again later.", [
      { text: "Cancel", style: "cancel" },
      { text: "Delete", style: "destructive", onPress: async () => {
        try { await advisorApi.deleteGoal(goal_id); setItems((xs) => xs.filter((x) => x.goal_id !== goal_id)); show("success", "Goal removed"); }
        catch { show("error", "Could not delete"); }
      } },
    ]);
  };

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>My Goals</Text>
      </View>

      <FlatList
        data={items}
        keyExtractor={(x) => x.goal_id}
        contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
        renderItem={({ item }) => {
          const Icon = ICONS[item.goal_type] || Target;
          return (
            <Pressable onPress={() => router.push({ pathname: "/advisor/goals/[id]", params: { id: item.goal_id } })}>
              <Card style={s.row}>
                <View style={[s.icon, { backgroundColor: palette.primary + "22" }]}>
                  <Icon color={palette.primary} size={22} />
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" }}>
                    <Text style={[s.gTitle, { color: palette.textPrimary }]} numberOfLines={1}>{item.title}</Text>
                    <Text style={[s.gAmt, { color: palette.textPrimary }]}>{formatINR(item.target_amount)}</Text>
                  </View>
                  <Text style={{ color: palette.textSecondary, fontSize: 11, marginTop: 2 }}>SIP: {formatINR(item.recommended_monthly_sip)}/mo · {item.horizon_years} years · {item.probability_pct}% likely</Text>
                  <View style={{ height: 6, backgroundColor: palette.chipBg, borderRadius: 3, marginTop: 6, overflow: "hidden" }}>
                    <View style={{ height: 6, width: `${Math.min(100, (item.current_savings / item.target_amount) * 100)}%`, backgroundColor: palette.primary }} />
                  </View>
                </View>
                <Pressable onPress={() => del(item.goal_id)} hitSlop={8} style={{ padding: 6 }}><Trash2 color={palette.danger} size={16} /></Pressable>
                <ChevronRight color={palette.textMuted} size={16} />
              </Card>
            </Pressable>
          );
        }}
        ListEmptyComponent={
          loading ? <ActivityIndicator color={palette.primary} style={{ marginTop: 30 }} />
            : <Card><View style={{ alignItems: "center", padding: 20, gap: 6 }}>
                <Target color={palette.textMuted} size={36} />
                <Text style={{ color: palette.textPrimary, fontWeight: "700" }}>No goals yet</Text>
                <Text style={{ color: palette.textSecondary, fontSize: 13, textAlign: "center" }}>Set a goal and get an AI-crafted SIP plan.</Text>
              </View></Card>
        }
      />

      <Pressable onPress={() => router.push("/advisor/goals/new")} style={({ pressed }) => [s.fab, { backgroundColor: palette.primary, opacity: pressed ? 0.85 : 1 }]}>
        <Plus color="#fff" size={20} />
        <Text style={s.fabTxt}>Create Goal</Text>
      </Pressable>
    </Screen>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { fontSize: 18, fontWeight: "800", letterSpacing: -0.3 },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  icon: { padding: 10, borderRadius: 12 },
  gTitle: { fontSize: 14, fontWeight: "800", flex: 1 },
  gAmt: { fontSize: 14, fontWeight: "800" },
  fab: { position: "absolute", bottom: 24, left: 16, right: 16, borderRadius: 16, paddingVertical: 14, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, shadowOpacity: 0.25, shadowRadius: 10, shadowOffset: { width: 0, height: 6 }, elevation: 6 },
  fabTxt: { color: "#fff", fontSize: 15, fontWeight: "800" },
});

import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, RefreshControl, ActivityIndicator } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter, useFocusEffect } from "expo-router";
import { ChevronLeft, Plus, Landmark, Clock, CheckCircle2, XCircle, ArrowUpFromLine, ChevronRight, ShieldCheck } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { api } from "@/src/api/client";
import { withdrawalApi, type Withdrawal, type WithdrawalSettings } from "@/src/api/withdrawal";
import { formatINR, shortDate } from "@/src/utils/format";

const STATUS_META: Record<string, { label: string; color: string; icon: any }> = {
  pending: { label: "Awaiting OTP", color: "#94A3B8", icon: Clock },
  under_review: { label: "Under Review", color: "#F59E0B", icon: Clock },
  approved: { label: "Approved", color: "#38BDF8", icon: ShieldCheck },
  processing: { label: "Processing", color: "#6366F1", icon: Clock },
  completed: { label: "Completed", color: "#10B981", icon: CheckCircle2 },
  rejected: { label: "Rejected", color: "#EF4444", icon: XCircle },
  failed: { label: "Failed", color: "#DC2626", icon: XCircle },
  cancelled: { label: "Cancelled", color: "#64748B", icon: XCircle },
};

export default function WithdrawalsIndex() {
  const { palette } = useTheme();
  const router = useRouter();
  const [items, setItems] = useState<Withdrawal[]>([]);
  const [settings, setSettings] = useState<WithdrawalSettings | null>(null);
  const [balance, setBalance] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [{ items: h }, s, w] = await Promise.all([
        withdrawalApi.history(20),
        withdrawalApi.settings(),
        api.get("/wallet").then((r) => r.data),
      ]);
      setItems(h); setSettings(s); setBalance(w?.balance || 0);
    } catch { /* swallow */ } finally {
      setLoading(false); setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={s.iconBtn}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>Withdrawals</Text>
        <Pressable onPress={() => router.push("/withdrawals/banks")} hitSlop={12} style={[s.chipBtn, { borderColor: palette.border }]}>
          <Landmark color={palette.primary} size={16} />
          <Text style={[s.chipTxt, { color: palette.primary }]}>Banks</Text>
        </Pressable>
      </View>

      <FlatList
        data={items}
        keyExtractor={(x) => x.withdrawal_id}
        contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
        ListHeaderComponent={
          <View style={{ gap: 16, marginBottom: 6 }}>
            <LinearGradient colors={["#0F172A", "#0EA5E9"]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.hero}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                <View>
                  <Text style={s.heroLabel}>WITHDRAWABLE BALANCE</Text>
                  <Text style={s.heroAmount}>{formatINR(balance)}</Text>
                  {settings && (
                    <Text style={s.heroSub}>
                      • Min {formatINR(settings.min_amount)}  • Max {formatINR(settings.max_amount)} / txn
                    </Text>
                  )}
                  {settings?.promo_waiver && (
                    <View style={s.chip}><Text style={s.chipText}>🎉  Zero charges — Limited-time promo</Text></View>
                  )}
                </View>
                <ArrowUpFromLine color="rgba(255,255,255,0.35)" size={40} />
              </View>
              <Pressable
                onPress={() => router.push("/withdrawals/new")}
                style={({ pressed }) => [s.newBtn, { opacity: pressed ? 0.85 : 1 }]}
                testID="btn-new-withdrawal"
              >
                <Plus color="#0F172A" size={20} />
                <Text style={s.newBtnTxt}>New Withdrawal</Text>
              </Pressable>
            </LinearGradient>

            <View style={s.sectionHeader}>
              <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Recent</Text>
              {settings && <Text style={[s.sectionSub, { color: palette.textSecondary }]}>Processes in ~{settings.processing_time_hours}h</Text>}
            </View>
          </View>
        }
        renderItem={({ item }) => {
          const meta = STATUS_META[item.status] || STATUS_META.pending;
          const Icon = meta.icon;
          return (
            <Pressable onPress={() => router.push({ pathname: "/withdrawals/[id]", params: { id: item.withdrawal_id } })}>
              <Card style={s.row}>
                <View style={[s.rowIcon, { backgroundColor: meta.color + "22" }]}>
                  <Icon color={meta.color} size={20} />
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                    <Text style={[s.rowRef, { color: palette.textPrimary }]}>{item.reference_no}</Text>
                    <Text style={[s.rowAmount, { color: palette.textPrimary }]}>{formatINR(item.amount)}</Text>
                  </View>
                  <Text style={[s.rowMeta, { color: palette.textSecondary }]} numberOfLines={1}>
                    {item.bank_snapshot.bank_name} · {item.bank_snapshot.account_masked}
                  </Text>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 6, alignItems: "center" }}>
                    <View style={[s.badge, { backgroundColor: meta.color + "22", borderColor: meta.color + "55" }]}>
                      <Text style={[s.badgeTxt, { color: meta.color }]}>{meta.label}</Text>
                    </View>
                    <Text style={[s.rowDate, { color: palette.textMuted }]}>{shortDate(item.created_at)}</Text>
                  </View>
                </View>
                <ChevronRight color={palette.textMuted} size={18} />
              </Card>
            </Pressable>
          );
        }}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
        ListEmptyComponent={
          loading ? (
            <ActivityIndicator color={palette.primary} style={{ marginVertical: 30 }} />
          ) : (
            <Card>
              <View style={{ alignItems: "center", padding: 20, gap: 6 }}>
                <ArrowUpFromLine color={palette.textMuted} size={36} />
                <Text style={{ color: palette.textPrimary, fontWeight: "700", marginTop: 6 }}>No withdrawals yet</Text>
                <Text style={{ color: palette.textSecondary, fontSize: 13, textAlign: "center" }}>Move money from your wallet straight to your bank account.</Text>
              </View>
            </Card>
          )
        }
      />
    </Screen>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  iconBtn: { padding: 4 },
  title: { flex: 1, fontSize: 20, fontWeight: "800", letterSpacing: -0.4 },
  chipBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  chipTxt: { fontSize: 12, fontWeight: "700" },
  hero: { borderRadius: 24, padding: 20, gap: 14, overflow: "hidden" },
  heroLabel: { color: "rgba(255,255,255,0.75)", fontSize: 11, fontWeight: "800", letterSpacing: 1.4 },
  heroAmount: { color: "#fff", fontSize: 32, fontWeight: "900", letterSpacing: -1, marginTop: 4 },
  heroSub: { color: "rgba(255,255,255,0.85)", fontSize: 11, fontWeight: "600", marginTop: 6 },
  chip: { marginTop: 8, alignSelf: "flex-start", paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: "rgba(245,158,11,0.24)", borderWidth: 1, borderColor: "rgba(245,158,11,0.5)" },
  chipText: { color: "#FDE68A", fontSize: 11, fontWeight: "800" },
  newBtn: { flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center", paddingVertical: 14, backgroundColor: "#F8FAFC", borderRadius: 14 },
  newBtnTxt: { color: "#0F172A", fontWeight: "800", fontSize: 15 },
  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 6 },
  sectionTitle: { fontSize: 17, fontWeight: "800", letterSpacing: -0.3 },
  sectionSub: { fontSize: 11, fontWeight: "600" },
  row: { flexDirection: "row", gap: 12, alignItems: "center" },
  rowIcon: { padding: 10, borderRadius: 12 },
  rowRef: { fontSize: 13, fontWeight: "800" },
  rowAmount: { fontSize: 14, fontWeight: "800" },
  rowMeta: { fontSize: 11, marginTop: 2 },
  rowDate: { fontSize: 10 },
  badge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, borderWidth: 1 },
  badgeTxt: { fontSize: 10, fontWeight: "800" },
});

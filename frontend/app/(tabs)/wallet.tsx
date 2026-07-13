import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, RefreshControl, ActivityIndicator, FlatList } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter, useFocusEffect } from "expo-router";
import { Send, Plus, QrCode, ArrowDownLeft, ArrowUpRight, History, Wallet as WalletIcon, ArrowUpFromLine } from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "@/src/theme/ThemeProvider";
import { api } from "@/src/api/client";
import { Card } from "@/src/components/Card";
import { BullLogo } from "@/src/components/BullLogo";
import { AnimatedCounter } from "@/src/components/AnimatedCounter";
import { formatINR, shortDate } from "@/src/utils/format";

export default function WalletTab() {
  const { palette } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [balance, setBalance] = useState<number | null>(null);
  const [txs, setTxs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [{ data: w }, { data: t }] = await Promise.all([
        api.get("/wallet"),
        api.get("/wallet/transactions"),
      ]);
      setBalance(w.balance);
      setTxs(t);
    } catch {}
    finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { load(); }, [load]));
  const onRefresh = () => { setRefreshing(true); load(); };

  const actions = [
    { icon: Plus, label: "Add Money", route: "/wallet/topup" as const, color: palette.success },
    { icon: Send, label: "Send", route: "/wallet/send" as const, color: palette.primary },
    { icon: ArrowUpFromLine, label: "Withdraw", route: "/withdrawals" as const, color: palette.warning },
    { icon: QrCode, label: "Receive", route: "/wallet/qr" as const, color: palette.secondary },
  ];

  return (
    <View style={[s.root, { backgroundColor: palette.background }]}>
      <View style={[s.hdr, { paddingTop: insets.top + 8, backgroundColor: palette.background }]}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <BullLogo size={32} />
          <Text style={[s.title, { color: palette.textPrimary }]}>Wallet</Text>
        </View>
      </View>
      <FlatList
        data={txs}
        keyExtractor={(t) => t.tx_id}
        contentContainerStyle={[s.scroll, { paddingBottom: 110 }]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={palette.primary} />}
        ListHeaderComponent={
          <View style={{ gap: 16 }}>
            <LinearGradient
              colors={["#0F172A", "#0EA5E9", "#38BDF8"]}
              start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
              locations={[0, 0.65, 1]}
              style={s.balanceCard}
            >
              <View style={s.heroBullWrap} pointerEvents="none">
                <BullLogo size={130} variant="flat" />
              </View>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
                <Text style={s.balanceLabel}>AVAILABLE BALANCE</Text>
                <WalletIcon color="rgba(255,255,255,0.85)" size={22} />
              </View>
              {loading ? (
                <Text style={s.balanceValue} testID="wallet-balance-text">—</Text>
              ) : (
                <AnimatedCounter
                  value={balance ?? 0}
                  style={s.balanceValue}
                  testID="wallet-balance-text"
                />
              )}
              <Text style={s.balanceSub}>INR · My Funding Bank Wallet</Text>
            </LinearGradient>

            <View style={s.actionsRow}>
              {actions.map((a) => (
                <Pressable
                  key={a.label}
                  style={[s.actionBtn, { backgroundColor: palette.surface, borderColor: palette.border }]}
                  onPress={() => router.push(a.route)}
                  testID={`wallet-action-${a.label.toLowerCase().replace(" ", "-")}`}
                >
                  <View style={[s.actionIcon, { backgroundColor: a.color + "1A" }]}>
                    <a.icon color={a.color} size={20} />
                  </View>
                  <Text style={[s.actionLabel, { color: palette.textPrimary }]}>{a.label}</Text>
                </Pressable>
              ))}
            </View>

            <View style={s.sectionHeader}>
              <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Transactions</Text>
              <Pressable onPress={() => router.push("/wallet/passbook")} style={{ flexDirection: "row", alignItems: "center", gap: 4 }} testID="open-passbook">
                <Text style={{ color: palette.primary, fontWeight: "800", fontSize: 12 }}>Passbook</Text>
                <History color={palette.primary} size={16} />
              </Pressable>
            </View>
          </View>
        }
        renderItem={({ item: t }) => (
          <Card style={s.txRow}>
            <View style={[s.txIcon, { backgroundColor: (t.type === "credit" ? palette.success : palette.danger) + "1A" }]}>
              {t.type === "credit"
                ? <ArrowDownLeft color={palette.success} size={20} />
                : <ArrowUpRight color={palette.danger} size={20} />}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.txDesc, { color: palette.textPrimary }]} numberOfLines={1}>{t.description}</Text>
              <Text style={[s.txMeta, { color: palette.textSecondary }]}>{shortDate(t.created_at)} • {t.category}</Text>
            </View>
            <Text style={[s.txAmount, { color: t.type === "credit" ? palette.success : palette.textPrimary }]}>
              {t.type === "credit" ? "+" : "−"}{formatINR(t.amount)}
            </Text>
          </Card>
        )}
        ItemSeparatorComponent={() => <View style={{ height: 10 }} />}
        ListEmptyComponent={
          loading ? (
            <ActivityIndicator color={palette.primary} style={{ marginVertical: 20 }} />
          ) : (
            <Card><Text style={{ color: palette.textSecondary, textAlign: "center" }}>No transactions yet</Text></Card>
          )
        }
      />
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1 },
  hdr: { paddingHorizontal: 16, paddingBottom: 12 },
  title: { fontSize: 24, fontWeight: "800", letterSpacing: -0.5 },
  scroll: { paddingHorizontal: 16, gap: 10 },
  balanceCard: { borderRadius: 28, padding: 22, gap: 6, overflow: "hidden", position: "relative" },
  heroBullWrap: { position: "absolute", right: -28, top: -18, opacity: 0.16, transform: [{ rotate: "12deg" }] },
  balanceLabel: { color: "rgba(255,255,255,0.85)", fontSize: 11, fontWeight: "800", letterSpacing: 1.4 },
  balanceValue: { color: "#fff", fontSize: 38, fontWeight: "800", letterSpacing: -1, marginTop: 4 },
  balanceSub: { color: "rgba(255,255,255,0.8)", fontSize: 12, fontWeight: "600", marginTop: 6 },
  actionsRow: { flexDirection: "row", gap: 10 },
  actionBtn: { flex: 1, padding: 14, borderRadius: 16, borderWidth: 1, alignItems: "center", gap: 8 },
  actionIcon: { padding: 10, borderRadius: 12 },
  actionLabel: { fontSize: 12, fontWeight: "700" },
  sectionHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 4 },
  sectionTitle: { fontSize: 17, fontWeight: "800", letterSpacing: -0.3 },
  txRow: { flexDirection: "row", alignItems: "center", gap: 12 },
  txIcon: { padding: 10, borderRadius: 12 },
  txDesc: { fontSize: 14, fontWeight: "700" },
  txMeta: { fontSize: 11, marginTop: 2 },
  txAmount: { fontSize: 14, fontWeight: "800" },
});

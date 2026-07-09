/**
 * My Copies Dashboard — Sprint 7B.2
 *
 * Portfolio-style management page for all active/paused/halted copies.
 * Shows aggregate summary + per-copy P&L and controls.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl, ActivityIndicator, Image, Alert } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { ArrowLeft, Play, Pause, Square, TrendingUp, TrendingDown, Users, Activity, ShieldAlert, Plus, ChevronRight } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { copyApi, CopyRelationship, CopySummary, countryFlag } from "@/src/api/copyTrading";
import { errText } from "@/src/utils/errors";

export default function MyCopiesScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [summary, setSummary] = useState<CopySummary | null>(null);
  const [copies, setCopies] = useState<CopyRelationship[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [bulkBusy, setBulkBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [sum, cop] = await Promise.all([copyApi.mySummary(), copyApi.myCopies()]);
      setSummary(sum);
      setCopies(cop.copies || []);
    } catch (e) {
      show("error", errText(e, "Couldn't load your copies"));
    } finally {
      setLoading(false); setRefreshing(false);
    }
  }, [show]);

  useEffect(() => { load(); }, [load]);
  // Refresh whenever screen regains focus, and poll every 20s while visible
  useFocusEffect(useCallback(() => {
    load();
    const t = setInterval(load, 20000);
    return () => clearInterval(t);
  }, [load]));

  const activeCopies = copies.filter((c) => c.status !== "stopped");

  const bulkAction = async (action: "pause" | "resume" | "close") => {
    if (bulkBusy) return;
    if (action === "close") {
      Alert.alert(
        "Close all copies?",
        "This will stop copying every trader and flat-close all open mirrored positions.",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Close All", style: "destructive", onPress: () => doBulk(action) },
        ],
      );
      return;
    }
    doBulk(action);
  };

  const doBulk = async (action: "pause" | "resume" | "close") => {
    setBulkBusy(true);
    try {
      if (action === "pause") await copyApi.pauseAll();
      else if (action === "resume") await copyApi.resumeAll();
      else await copyApi.closeAll();
      show("success", `Bulk ${action} complete`);
      await load();
    } catch (e) { show("error", errText(e, "Bulk action failed")); }
    finally { setBulkBusy(false); }
  };

  if (loading) {
    return (
      <Screen>
        <View style={{ paddingTop: 80, alignItems: "center" }}>
          <ActivityIndicator color={palette.primary} />
        </View>
      </Screen>
    );
  }

  const totalPnl = summary?.total_pnl_usd ?? 0;
  const todayPnl = summary?.today_pnl_usd ?? 0;
  const isUp = totalPnl >= 0;

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>My Copies</Text>
        <Pressable
          onPress={() => router.push("/traders" as any)}
          hitSlop={8}
          style={{ flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: palette.primary }}
        >
          <Plus size={13} color="#fff" />
          <Text style={{ color: "#fff", fontSize: 11, fontWeight: "800" }}>New Copy</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
      >
        {/* Summary card */}
        <View style={[s.summaryCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
            <View>
              <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700" }}>TOTAL COPY P&amp;L</Text>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 4 }}>
                {isUp ? <TrendingUp size={20} color={palette.success} /> : <TrendingDown size={20} color={palette.danger} />}
                <Text style={{ color: isUp ? palette.success : palette.danger, fontSize: 28, fontWeight: "900", fontVariant: ["tabular-nums"] }}>
                  {isUp ? "+" : ""}${totalPnl.toFixed(2)}
                </Text>
              </View>
              <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 4 }}>
                Today: <Text style={{ color: todayPnl >= 0 ? palette.success : palette.danger, fontWeight: "800" }}>
                  {todayPnl >= 0 ? "+" : ""}${todayPnl.toFixed(2)}
                </Text>{" · "}{summary?.today_trades ?? 0} trades
              </Text>
            </View>
            <View style={{ alignItems: "flex-end", gap: 4 }}>
              <MiniPill icon={Activity} label={`${summary?.open_positions ?? 0} open`} palette={palette} tint={palette.primary} />
              <MiniPill icon={Users} label={`${summary?.active_copies ?? 0} active`} palette={palette} tint={palette.success} />
              {(summary?.halted_copies ?? 0) > 0 && (
                <MiniPill icon={ShieldAlert} label={`${summary?.halted_copies} halted`} palette={palette} tint={palette.danger} />
              )}
            </View>
          </View>

          <View style={s.summaryStats}>
            <MiniStat label="Win Rate" value={`${(summary?.win_rate_pct ?? 0).toFixed(1)}%`} palette={palette} />
            <MiniStat label="Total Trades" value={String(summary?.total_trades ?? 0)} palette={palette} />
            <MiniStat label="Paused" value={String(summary?.paused_copies ?? 0)} palette={palette} />
          </View>

          {activeCopies.length > 0 && (
            <View style={{ flexDirection: "row", gap: 6, marginTop: 12 }}>
              <BulkBtn icon={Pause} label="Pause All" onPress={() => bulkAction("pause")} disabled={bulkBusy} palette={palette} color={palette.warning} />
              <BulkBtn icon={Play} label="Resume All" onPress={() => bulkAction("resume")} disabled={bulkBusy} palette={palette} color={palette.success} />
              <BulkBtn icon={Square} label="Close All" onPress={() => bulkAction("close")} disabled={bulkBusy} palette={palette} color={palette.danger} />
            </View>
          )}
        </View>

        {/* List of copies */}
        {copies.length === 0 ? (
          <EmptyState palette={palette} onExplore={() => router.push("/traders" as any)} />
        ) : (
          <View style={{ paddingHorizontal: 12, marginTop: 4 }}>
            <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>YOUR TRADERS</Text>
            {copies.map((rel) => <CopyRow key={rel.trader_id} rel={rel} palette={palette} onPress={() => router.push(`/copies/${rel.trader_id}` as any)} />)}
          </View>
        )}
      </ScrollView>
    </Screen>
  );
}

function CopyRow({ rel, palette, onPress }: { rel: CopyRelationship; palette: any; onPress: () => void }) {
  const t = rel.trader;
  const pnl = rel.live?.lifetime_pnl_usd ?? 0;
  const today = rel.live?.today_pnl_usd ?? 0;
  const isUp = pnl >= 0;
  const statusColor = rel.status === "active" ? palette.success : rel.status === "paused" ? palette.warning : rel.status === "halted" ? palette.danger : palette.textMuted;
  const statusLabel = rel.status.toUpperCase();

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [s.row, { backgroundColor: pressed ? palette.surface : palette.background, borderColor: palette.border }]}
    >
      {t?.avatar_url ? <Image source={{ uri: t.avatar_url }} style={s.avatar} /> : <View style={[s.avatar, { backgroundColor: palette.surface }]} />}
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 5 }}>
          <Text style={[s.name, { color: palette.textPrimary }]} numberOfLines={1}>{t?.name || rel.trader_id}</Text>
          {t?.country_code && <Text style={{ fontSize: 12 }}>{countryFlag(t.country_code)}</Text>}
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 3 }}>
          <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: statusColor + "22" }}>
            <Text style={{ color: statusColor, fontSize: 9, fontWeight: "900" }}>{statusLabel}</Text>
          </View>
          <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "700" }}>
            {rel.live?.open_positions ?? 0} open · Today {today >= 0 ? "+" : ""}${today.toFixed(2)}
          </Text>
        </View>
        {rel.halt_reason && (
          <Text style={{ color: palette.danger, fontSize: 10, marginTop: 3, fontWeight: "700" }} numberOfLines={1}>
            Halted: {rel.halt_reason}
          </Text>
        )}
      </View>
      <View style={{ alignItems: "flex-end" }}>
        <Text style={{ color: isUp ? palette.success : palette.danger, fontSize: 15, fontWeight: "900", fontVariant: ["tabular-nums"] }}>
          {isUp ? "+" : ""}${pnl.toFixed(2)}
        </Text>
        <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "700" }}>LIFETIME</Text>
      </View>
      <ChevronRight size={16} color={palette.textMuted} />
    </Pressable>
  );
}

function EmptyState({ palette, onExplore }: any) {
  return (
    <View style={{ padding: 40, alignItems: "center" }}>
      <Users size={44} color={palette.textMuted} />
      <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "800", marginTop: 10 }}>No copies yet</Text>
      <Text style={{ color: palette.textMuted, fontSize: 12, textAlign: "center", marginTop: 6, lineHeight: 18 }}>
        Explore top traders and start copying with your own risk settings.
      </Text>
      <Pressable onPress={onExplore} style={{ marginTop: 16, backgroundColor: palette.primary, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 999 }}>
        <Text style={{ color: "#fff", fontWeight: "900", fontSize: 13 }}>Browse traders</Text>
      </Pressable>
    </View>
  );
}

function MiniPill({ icon: Ic, label, palette, tint }: any) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: (tint || palette.textMuted) + "22" }}>
      <Ic size={10} color={tint || palette.textMuted} />
      <Text style={{ color: tint || palette.textMuted, fontSize: 10, fontWeight: "800" }}>{label}</Text>
    </View>
  );
}
function MiniStat({ label, value, palette }: any) {
  return (
    <View style={{ flex: 1 }}>
      <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "800" }}>{label.toUpperCase()}</Text>
      <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "900", marginTop: 2 }}>{value}</Text>
    </View>
  );
}
function BulkBtn({ icon: Ic, label, onPress, disabled, palette, color }: any) {
  return (
    <Pressable onPress={onPress} disabled={disabled} style={{ flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 5, paddingVertical: 10, borderRadius: 8, backgroundColor: color, opacity: disabled ? 0.55 : 1 }}>
      <Ic size={12} color="#fff" fill="#fff" />
      <Text style={{ color: "#fff", fontWeight: "900", fontSize: 11 }}>{label}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { flex: 1, fontSize: 20, fontWeight: "800" },
  summaryCard: { margin: 12, padding: 16, borderRadius: 14, borderWidth: 1 },
  summaryStats: { flexDirection: "row", gap: 10, marginTop: 14, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: "#00000015" },
  sectionTitle: { fontSize: 10, fontWeight: "900", marginTop: 8, marginBottom: 6, letterSpacing: 0.5 },
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 12, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  avatar: { width: 42, height: 42, borderRadius: 21, backgroundColor: "#E2E8F0" },
  name: { fontSize: 14, fontWeight: "800" },
});

/**
 * Individual Copy Detail — Sprint 7B.2
 *
 * Detailed view of a user's copy of one trader:
 *  - Live P&L header (lifetime + today)
 *  - Status controls (pause/resume/stop/edit)
 *  - Live open positions
 *  - Mirrored trade history (closed)
 *  - Risk protection status
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, Image, ActivityIndicator, Alert, RefreshControl } from "react-native";
import { useLocalSearchParams, useRouter, useFocusEffect } from "expo-router";
import { ArrowLeft, Play, Pause, Square, Settings, ShieldCheck, ShieldAlert, TrendingUp, TrendingDown, Clock } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { copyApi, CopyRelationship, FollowerTrade, countryFlag } from "@/src/api/copyTrading";
import { errText, safeStr } from "@/src/utils/errors";

type Tab = "positions" | "history" | "risk";

export default function CopyDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [rel, setRel] = useState<CopyRelationship | null>(null);
  const [open, setOpen] = useState<FollowerTrade[]>([]);
  const [history, setHistory] = useState<FollowerTrade[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("positions");
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [copies, openR, closedR] = await Promise.all([
        copyApi.myCopies(),
        copyApi.myTrades({ trader_id: String(id), status: "open", limit: 100 }),
        copyApi.myTrades({ trader_id: String(id), status: "closed", limit: 100 }),
      ]);
      const found = copies.copies.find((c) => c.trader_id === String(id)) || null;
      if (found) {
        // Fallback fetch trader details if missing
        if (!found.trader) {
          try { found.trader = await copyApi.trader(String(id)); } catch {}
        }
      }
      setRel(found);
      setOpen(openR.trades || []);
      setHistory(closedR.trades || []);
    } catch (e) { show("error", errText(e, "Couldn't load copy")); }
    finally { setLoading(false); setRefreshing(false); }
  }, [id, show]);

  useEffect(() => { load(); }, [load]);
  useFocusEffect(useCallback(() => {
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, [load]));

  const doAction = async (action: "pause" | "resume" | "stop") => {
    try {
      if (action === "stop") {
        Alert.alert(
          "Stop copying?",
          "This closes all open positions and stops mirroring further trades.",
          [
            { text: "Cancel", style: "cancel" },
            {
              text: "Stop", style: "destructive",
              onPress: async () => {
                await copyApi.stopCopy(String(id));
                show("success", "Copy stopped");
                await load();
              },
            },
          ],
        );
        return;
      }
      if (action === "pause") await copyApi.pauseCopy(String(id));
      if (action === "resume") await copyApi.resumeCopy(String(id));
      show("success", `Copy ${action}d`);
      await load();
    } catch (e) { show("error", errText(e, "Action failed")); }
  };

  if (loading) return (
    <Screen><View style={{ paddingTop: 80, alignItems: "center" }}><ActivityIndicator color={palette.primary} /></View></Screen>
  );

  if (!rel) return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>Not found</Text>
      </View>
      <View style={{ padding: 30, alignItems: "center" }}>
        <Text style={{ color: palette.textMuted, fontSize: 13 }}>You are not copying this trader.</Text>
        <Pressable onPress={() => router.push(`/traders/${String(id)}` as any)} style={{ marginTop: 14, backgroundColor: palette.primary, paddingHorizontal: 18, paddingVertical: 10, borderRadius: 999 }}>
          <Text style={{ color: "#fff", fontWeight: "900", fontSize: 13 }}>View trader profile</Text>
        </Pressable>
      </View>
    </Screen>
  );

  const t = rel.trader;
  const status = rel.status;
  const pnl = rel.live?.lifetime_pnl_usd ?? 0;
  const today = rel.live?.today_pnl_usd ?? 0;
  const isUp = pnl >= 0;
  const statusColor = status === "active" ? palette.success : status === "paused" ? palette.warning : status === "halted" ? palette.danger : palette.textMuted;

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]} numberOfLines={1}>{t?.name || String(id)}</Text>
        <Pressable onPress={() => router.push(`/traders/${String(id)}` as any)} hitSlop={8}>
          <Settings size={20} color={palette.textPrimary} />
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
      >
        {/* Hero */}
        <View style={[s.hero, { backgroundColor: palette.surface, borderBottomColor: palette.border }]}>
          <View style={{ flexDirection: "row", gap: 12, alignItems: "center" }}>
            {t?.avatar_url && <Image source={{ uri: t.avatar_url }} style={s.avatar} />}
            <View style={{ flex: 1, minWidth: 0 }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                <Text style={{ color: palette.textPrimary, fontSize: 16, fontWeight: "900" }} numberOfLines={1}>
                  {t?.name || String(id)}
                </Text>
                {t?.country_code && <Text style={{ fontSize: 14 }}>{countryFlag(t.country_code)}</Text>}
                {t?.verified && <ShieldCheck size={14} color="#3B82F6" fill="#3B82F6" />}
              </View>
              <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 2 }}>
                {t?.style} · Risk {t?.risk?.risk_score}/10 · {rel.settings.mode.toUpperCase()}
              </Text>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 5, marginTop: 6 }}>
                <View style={{ paddingHorizontal: 7, paddingVertical: 2, borderRadius: 4, backgroundColor: statusColor + "22" }}>
                  <Text style={{ color: statusColor, fontSize: 10, fontWeight: "900" }}>{status.toUpperCase()}</Text>
                </View>
                {rel.halt_reason && (
                  <Text style={{ color: palette.danger, fontSize: 10, fontWeight: "700" }} numberOfLines={1}>
                    {rel.halt_reason}
                  </Text>
                )}
              </View>
            </View>
          </View>

          {/* Live P&L block */}
          <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 16, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: palette.border }}>
            <View>
              <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800" }}>LIFETIME P&amp;L</Text>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 5, marginTop: 3 }}>
                {isUp ? <TrendingUp size={16} color={palette.success} /> : <TrendingDown size={16} color={palette.danger} />}
                <Text style={{ color: isUp ? palette.success : palette.danger, fontSize: 20, fontWeight: "900", fontVariant: ["tabular-nums"] }}>
                  {isUp ? "+" : ""}${pnl.toFixed(2)}
                </Text>
              </View>
            </View>
            <View style={{ alignItems: "flex-end" }}>
              <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800" }}>TODAY</Text>
              <Text style={{ color: today >= 0 ? palette.success : palette.danger, fontSize: 20, fontWeight: "900", marginTop: 3, fontVariant: ["tabular-nums"] }}>
                {today >= 0 ? "+" : ""}${today.toFixed(2)}
              </Text>
            </View>
            <View style={{ alignItems: "flex-end" }}>
              <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800" }}>OPEN</Text>
              <Text style={{ color: palette.textPrimary, fontSize: 20, fontWeight: "900", marginTop: 3 }}>
                {rel.live?.open_positions ?? 0}
              </Text>
            </View>
          </View>
        </View>

        {/* Action buttons */}
        <View style={{ flexDirection: "row", gap: 6, paddingHorizontal: 12, paddingVertical: 12 }}>
          {status === "active" && (
            <ActionBtn icon={Pause} label="Pause" color={palette.warning} onPress={() => doAction("pause")} />
          )}
          {(status === "paused" || status === "halted") && (
            <ActionBtn icon={Play} label="Resume" color={palette.success} onPress={() => doAction("resume")} />
          )}
          {status !== "stopped" && (
            <ActionBtn icon={Square} label="Stop" color={palette.danger} onPress={() => doAction("stop")} />
          )}
          <ActionBtn icon={Settings} label="Edit" color={palette.primary}
                     onPress={() => router.push(`/traders/${String(id)}` as any)} />
        </View>

        {/* Tabs */}
        <View style={[s.tabs, { borderBottomColor: palette.border }]}>
          {(["positions", "history", "risk"] as Tab[]).map((tk) => (
            <Pressable key={tk} onPress={() => setTab(tk)} style={[s.tabBtn, tab === tk && { borderBottomColor: palette.primary }]}>
              <Text style={{ color: tab === tk ? palette.primary : palette.textMuted, fontWeight: "800", fontSize: 12 }}>
                {tk === "positions" ? `Open (${open.length})` : tk === "history" ? `History (${history.length})` : "Risk"}
              </Text>
            </Pressable>
          ))}
        </View>

        {tab === "positions" && (
          open.length ? open.map((tr) => <TradeRow key={tr.follower_trade_id} t={tr} palette={palette} live />) :
          <EmptyText palette={palette}>No open mirrored positions</EmptyText>
        )}
        {tab === "history" && (
          history.length ? history.map((tr) => <TradeRow key={tr.follower_trade_id} t={tr} palette={palette} />) :
          <EmptyText palette={palette}>No closed trades yet</EmptyText>
        )}
        {tab === "risk" && <RiskPanel rel={rel} palette={palette} />}
      </ScrollView>
    </Screen>
  );
}

function ActionBtn({ icon: Ic, label, color, onPress }: any) {
  return (
    <Pressable onPress={onPress} style={{ flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 11, borderRadius: 10, backgroundColor: color }}>
      <Ic size={14} color="#fff" fill="#fff" />
      <Text style={{ color: "#fff", fontWeight: "900", fontSize: 12 }}>{label}</Text>
    </Pressable>
  );
}
function TradeRow({ t, palette, live }: { t: FollowerTrade; palette: any; live?: boolean }) {
  const pnl = t.pnl_usd ?? 0;
  const pos = pnl >= 0;
  const openedDt = t.opened_at ? new Date(t.opened_at) : null;
  return (
    <View style={{ flexDirection: "row", paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: palette.border }}>
      <View style={{ flex: 1 }}>
        <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 13 }}>
          {safeStr(t.symbol)} · <Text style={{ color: t.side === "buy" ? palette.success : palette.danger }}>{t.side.toUpperCase()}</Text> · {t.lot_size} lot
        </Text>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 5, marginTop: 3 }}>
          <Text style={{ color: palette.textMuted, fontSize: 10 }}>
            {t.entry_price?.toFixed(5)} {t.exit_price ? `→ ${t.exit_price.toFixed(5)}` : ""}
          </Text>
          {openedDt && (
            <>
              <Clock size={9} color={palette.textMuted} />
              <Text style={{ color: palette.textMuted, fontSize: 10 }}>{openedDt.toLocaleTimeString()}</Text>
            </>
          )}
        </View>
      </View>
      <View style={{ alignItems: "flex-end" }}>
        {live ? (
          <Text style={{ color: palette.primary, fontWeight: "900", fontSize: 12, fontVariant: ["tabular-nums"] }}>OPEN</Text>
        ) : (
          <>
            <Text style={{ color: pos ? palette.success : palette.danger, fontWeight: "900", fontSize: 13, fontVariant: ["tabular-nums"] }}>
              {pos ? "+" : ""}${pnl.toFixed(2)}
            </Text>
            <Text style={{ color: palette.textMuted, fontSize: 10 }}>{(t.pnl_pct ?? 0).toFixed(2)}%</Text>
          </>
        )}
      </View>
    </View>
  );
}
function EmptyText({ palette, children }: any) {
  return <View style={{ padding: 30, alignItems: "center" }}><Text style={{ color: palette.textMuted, fontSize: 12 }}>{children}</Text></View>;
}
function RiskPanel({ rel, palette }: { rel: CopyRelationship; palette: any }) {
  const st = rel.settings;
  const isHalted = rel.status === "halted";
  return (
    <View style={{ padding: 14 }}>
      <View style={[s.riskCard, { backgroundColor: isHalted ? palette.danger + "15" : palette.surface, borderColor: isHalted ? palette.danger : palette.border }]}>
        <View style={{ flexDirection: "row", gap: 8, alignItems: "center", marginBottom: 8 }}>
          {isHalted ? <ShieldAlert size={16} color={palette.danger} /> : <ShieldCheck size={16} color={palette.success} />}
          <Text style={{ color: palette.textPrimary, fontSize: 13, fontWeight: "900" }}>
            {isHalted ? "Copy Halted" : "Risk Protection Active"}
          </Text>
        </View>
        {rel.halt_reason && (
          <Text style={{ color: palette.danger, fontSize: 11, fontWeight: "700", marginBottom: 8 }}>
            Reason: {rel.halt_reason}
          </Text>
        )}
        <RiskRow label="Copy Mode" value={st.mode.replace("_", " ").toUpperCase()} palette={palette} />
        {st.mode === "multiplier" && <RiskRow label="Multiplier" value={`${st.multiplier}x`} palette={palette} />}
        {st.mode === "fixed_lot" && <RiskRow label="Fixed Lot" value={String(st.fixed_lot)} palette={palette} />}
        {st.mode === "equity_percent" && <RiskRow label="Equity %" value={`${st.equity_percent}%`} palette={palette} />}
        <RiskRow label="Max Daily Loss" value={`${st.max_daily_loss_pct}%`} palette={palette} />
        <RiskRow label="Max Drawdown" value={`${st.max_drawdown_pct}%`} palette={palette} />
        <RiskRow label="Max Open Trades" value={String(st.max_open_trades)} palette={palette} />
        <RiskRow label="Equity Protection" value={`${st.equity_protection_pct}%`} palette={palette} />
        <RiskRow label="Auto-close Equity" value={st.auto_close_on_equity_protection ? "Yes" : "No"} palette={palette} />
        <RiskRow label="Pause on Daily Loss" value={st.auto_pause_on_daily_loss ? "Yes" : "No"} palette={palette} />
        <RiskRow label="Max Lot Size" value={String(st.max_lot_size ?? "-")} palette={palette} />
        <RiskRow label="Slippage" value={`${st.slippage_pips ?? 0} pips`} palette={palette} />
      </View>
    </View>
  );
}
function RiskRow({ label, value, palette }: any) {
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: palette.border + "50" }}>
      <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700" }}>{label}</Text>
      <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "900" }}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { flex: 1, fontSize: 18, fontWeight: "800" },
  hero: { padding: 16, borderBottomWidth: StyleSheet.hairlineWidth },
  avatar: { width: 60, height: 60, borderRadius: 30, backgroundColor: "#E2E8F0" },
  tabs: { flexDirection: "row", borderBottomWidth: StyleSheet.hairlineWidth },
  tabBtn: { paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 2, borderBottomColor: "transparent" },
  riskCard: { padding: 14, borderRadius: 12, borderWidth: 1 },
});

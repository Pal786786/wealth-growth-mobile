/**
 * Trader Profile — Sprint 7B.1
 * Header, avatar, stats grid, equity curve, monthly bars, tabs (overview/open/closed),
 * risk meter, Copy button + settings sheet.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, Image, ActivityIndicator, TextInput, Platform, Modal } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import Svg, { Path, Defs, LinearGradient as SvgGrad, Stop, Line, Rect } from "react-native-svg";
import { ArrowLeft, ShieldCheck, TrendingUp, TrendingDown, Play, Pause, Square, X, Users, Award, Gauge } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { copyApi, Trader, Trade, CopyRelationship, CopySettings, countryFlag } from "@/src/api/copyTrading";
import { errText, safeStr } from "@/src/utils/errors";

type Tab = "overview" | "open" | "closed";

export default function TraderProfile() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [trader, setTrader] = useState<Trader | null>(null);
  const [opens, setOpens] = useState<Trade[]>([]);
  const [closes, setCloses] = useState<Trade[]>([]);
  const [copy, setCopy] = useState<CopyRelationship | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [loading, setLoading] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [chartWidth, setChartWidth] = useState(0);

  const load = useCallback(async () => {
    try {
      const [t, o, c] = await Promise.all([
        copyApi.trader(String(id)),
        copyApi.openTrades(String(id)).catch(() => ({ trades: [] })),
        copyApi.closedTrades(String(id), 40).catch(() => ({ trades: [] })),
      ]);
      setTrader(t); setOpens(o.trades); setCloses(c.trades);
      try {
        const rel = await copyApi.getCopy(String(id));
        setCopy(rel);
      } catch { /* unauthenticated is fine */ }
    } catch (e) { show("error", errText(e, "Couldn't load trader")); }
    finally { setLoading(false); }
  }, [id, show]);
  useEffect(() => { load(); }, [load]);

  if (loading || !trader) return (
    <Screen><View style={{ paddingTop: 60, alignItems: "center" }}><ActivityIndicator color={palette.primary} /></View></Screen>
  );

  const isActive = copy?.status === "active";
  const isPaused = copy?.status === "paused";
  const doAction = async (action: "start" | "pause" | "resume" | "stop") => {
    try {
      const fn = action === "start" ? copyApi.startCopy(trader.id) : action === "pause" ? copyApi.pauseCopy(trader.id) : action === "resume" ? copyApi.resumeCopy(trader.id) : copyApi.stopCopy(trader.id);
      const rel = await fn;
      setCopy(rel);
      show("success", `${action[0].toUpperCase()}${action.slice(1)} copy — ${rel.status}`);
    } catch (e) { show("error", errText(e, "Action failed")); }
  };

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <Text style={[s.hdrTitle, { color: palette.textPrimary }]} numberOfLines={1}>{safeStr(trader.name)}</Text>
      </View>
      <ScrollView contentContainerStyle={{ paddingBottom: 100 }}>
        {/* Hero */}
        <View style={[s.hero, { backgroundColor: palette.surface, borderBottomColor: palette.border }]}>
          <Image source={{ uri: trader.avatar_url }} style={s.avatar} />
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 8 }}>
            <Text style={[s.name, { color: palette.textPrimary }]}>{safeStr(trader.name)}</Text>
            {trader.verified && <ShieldCheck size={16} color="#3B82F6" fill="#3B82F6" />}
            <Text style={{ fontSize: 18 }}>{countryFlag(trader.country_code)}</Text>
          </View>
          <Text style={[s.meta, { color: palette.textMuted }]}>{trader.style} · {trader.experience_years}yr experience · {trader.country_name}</Text>
          <Text style={[s.bio, { color: palette.textSecondary }]}>{safeStr(trader.bio)}</Text>
          <View style={{ flexDirection: "row", gap: 8, marginTop: 12 }}>
            <PillStat icon={Users} label="Followers" value={trader.stats.followers.toLocaleString()} palette={palette} />
            <PillStat icon={Award} label="AUM" value={`$${(trader.stats.aum_usd / 1000).toFixed(0)}k`} palette={palette} />
            <PillStat icon={Gauge} label={`Risk ${trader.risk.risk_score}/10`} value={trader.risk.risk_tier} palette={palette}
                      tint={trader.risk.risk_score <= 4 ? palette.success : trader.risk.risk_score <= 7 ? palette.warning : palette.danger} />
          </View>
        </View>

        {/* Stats grid */}
        <View style={s.grid}>
          <StatCard label="Total ROI"    value={`${trader.stats.total_roi_pct >= 0 ? "+" : ""}${trader.stats.total_roi_pct.toFixed(1)}%`} tint={trader.stats.total_roi_pct >= 0 ? palette.success : palette.danger} palette={palette} />
          <StatCard label="Monthly ROI"  value={`${trader.stats.monthly_roi_pct.toFixed(1)}%`} palette={palette} />
          <StatCard label="Weekly ROI"   value={`${trader.stats.weekly_roi_pct.toFixed(1)}%`} palette={palette} />
          <StatCard label="Win Rate"     value={`${trader.stats.win_rate_pct.toFixed(1)}%`} palette={palette} />
          <StatCard label="Profit Factor" value={trader.stats.profit_factor.toFixed(2)} palette={palette} />
          <StatCard label="Sharpe"       value={trader.stats.sharpe_ratio.toFixed(2)} palette={palette} />
          <StatCard label="Recovery"     value={trader.stats.recovery_factor.toFixed(2)} palette={palette} />
          <StatCard label="Max DD"       value={`${trader.stats.max_drawdown_pct.toFixed(1)}%`} tint={palette.danger} palette={palette} />
          <StatCard label="Avg Hold"     value={`${trader.stats.avg_holding_hours < 1 ? Math.round(trader.stats.avg_holding_hours * 60) + "m" : trader.stats.avg_holding_hours.toFixed(1) + "h"}`} palette={palette} />
          <StatCard label="Avg Lot"      value={trader.stats.avg_lot_size.toFixed(2)} palette={palette} />
          <StatCard label="Trades"       value={String(trader.stats.total_trades)} palette={palette} />
          <StatCard label="Expectancy"   value={`$${trader.stats.expectancy_usd.toFixed(0)}`} palette={palette} />
        </View>

        {/* Equity curve */}
        <View style={{ paddingHorizontal: 14 }}>
          <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Equity Curve (12M)</Text>
        </View>
        <View onLayout={(e) => setChartWidth(e.nativeEvent.layout.width)} style={{ paddingHorizontal: 14, height: 160 }}>
          <EquityChart curve={trader.equity_curve || []} width={chartWidth - 28} height={150} palette={palette} />
        </View>

        {/* Monthly bars */}
        <View style={{ paddingHorizontal: 14, marginTop: 20 }}>
          <Text style={[s.sectionTitle, { color: palette.textPrimary }]}>Monthly ROI</Text>
          <MonthlyBars months={trader.monthly_returns_pct} palette={palette} />
        </View>

        {/* Tabs */}
        <View style={[s.tabs, { borderBottomColor: palette.border }]}>
          {(["overview", "open", "closed"] as Tab[]).map((t) => (
            <Pressable key={t} onPress={() => setTab(t)} style={[s.tabBtn, tab === t && { borderBottomColor: palette.primary }]}>
              <Text style={{ color: tab === t ? palette.primary : palette.textMuted, fontWeight: "800", fontSize: 12 }}>
                {t === "overview" ? "Overview" : t === "open" ? `Open (${opens.length})` : `History (${closes.length})`}
              </Text>
            </Pressable>
          ))}
        </View>

        {tab === "overview" && (
          <View style={{ paddingHorizontal: 14, paddingVertical: 8 }}>
            <Text style={{ color: palette.textMuted, fontSize: 12, lineHeight: 18 }}>
              {trader.name} uses a {trader.style.toLowerCase()} approach with an average holding period of{" "}
              {trader.stats.avg_holding_hours < 1 ? Math.round(trader.stats.avg_holding_hours * 60) + " minutes" : trader.stats.avg_holding_hours.toFixed(1) + " hours"}.
              Their risk score is {trader.risk.risk_score}/10 ({trader.risk.risk_tier.toLowerCase()}) with a max drawdown of {trader.stats.max_drawdown_pct.toFixed(1)}%.
            </Text>
          </View>
        )}
        {tab === "open" && (opens.length ? opens.map((tr) => <TradeRow key={tr.id} t={tr} palette={palette} />) : <EmptyText palette={palette}>No open trades</EmptyText>)}
        {tab === "closed" && (closes.length ? closes.map((tr) => <TradeRow key={tr.id} t={tr} palette={palette} />) : <EmptyText palette={palette}>No closed trades</EmptyText>)}
      </ScrollView>

      {/* Bottom copy CTA */}
      <View style={[s.cta, { backgroundColor: palette.background, borderTopColor: palette.border }]}>
        {!copy || copy.status === "stopped" ? (
          <Pressable onPress={() => setSettingsOpen(true)} style={[s.ctaBtn, { backgroundColor: palette.primary }]}>
            <Play size={16} color="#fff" fill="#fff" />
            <Text style={s.ctaTxt}>Copy this trader</Text>
          </Pressable>
        ) : (
          <View style={{ flexDirection: "row", gap: 8, flex: 1 }}>
            {isActive ? (
              <Pressable onPress={() => doAction("pause")} style={[s.ctaBtn, { backgroundColor: palette.warning, flex: 1 }]}>
                <Pause size={14} color="#fff" fill="#fff" /><Text style={s.ctaTxt}>Pause</Text>
              </Pressable>
            ) : (
              <Pressable onPress={() => doAction("resume")} style={[s.ctaBtn, { backgroundColor: palette.success, flex: 1 }]}>
                <Play size={14} color="#fff" fill="#fff" /><Text style={s.ctaTxt}>Resume</Text>
              </Pressable>
            )}
            <Pressable onPress={() => doAction("stop")} style={[s.ctaBtn, { backgroundColor: palette.danger, flex: 1 }]}>
              <Square size={14} color="#fff" fill="#fff" /><Text style={s.ctaTxt}>Stop</Text>
            </Pressable>
            <Pressable onPress={() => setSettingsOpen(true)} style={[s.ctaBtn, { backgroundColor: palette.surface, borderColor: palette.border, borderWidth: 1 }]}>
              <Text style={[s.ctaTxt, { color: palette.textPrimary }]}>⚙︎</Text>
            </Pressable>
          </View>
        )}
      </View>

      <CopySettingsSheet
        visible={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        trader={trader}
        initial={copy?.settings ? { ...copy.settings, __isActive: (copy.status === "active" || copy.status === "paused") } as any : undefined}
        onSave={async (settings) => {
          try {
            const rel = copy && copy.status !== "stopped"
              ? await copyApi.updateSettings(trader.id, settings)
              : await copyApi.startCopy(trader.id, settings);
            setCopy(rel);
            setSettingsOpen(false);
            show("success", copy?.status !== "stopped" ? "Settings updated" : `Now copying ${trader.name}`);
          } catch (e) { show("error", errText(e, "Save failed")); }
        }}
      />
    </Screen>
  );
}

function PillStat({ icon: Ic, label, value, palette, tint }: any) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, borderWidth: 1, borderColor: palette.border, backgroundColor: palette.background }}>
      <Ic size={11} color={tint || palette.textMuted} />
      <View>
        <Text style={{ color: palette.textMuted, fontSize: 8, fontWeight: "700" }}>{label}</Text>
        <Text style={{ color: tint || palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{value}</Text>
      </View>
    </View>
  );
}
function StatCard({ label, value, tint, palette }: any) {
  return (
    <View style={{ width: "31%", padding: 10, borderRadius: 10, backgroundColor: palette.surface, borderColor: palette.border, borderWidth: 1 }}>
      <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "700" }}>{label.toUpperCase()}</Text>
      <Text style={{ color: tint || palette.textPrimary, fontSize: 14, fontWeight: "900", marginTop: 2, fontVariant: ["tabular-nums"] }}>{value}</Text>
    </View>
  );
}
function EmptyText({ palette, children }: any) {
  return <View style={{ padding: 30, alignItems: "center" }}><Text style={{ color: palette.textMuted, fontSize: 12 }}>{children}</Text></View>;
}
function TradeRow({ t, palette }: { t: Trade; palette: any }) {
  const pos = (t.pnl_usd ?? t.pnl_pct ?? 0) >= 0;
  return (
    <View style={{ flexDirection: "row", paddingHorizontal: 14, paddingVertical: 10, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: palette.border }}>
      <View style={{ flex: 1 }}>
        <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 13 }}>{t.symbol} · <Text style={{ color: t.side === "buy" ? palette.success : palette.danger }}>{t.side.toUpperCase()}</Text> · {t.lot_size} lot</Text>
        <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 2 }}>Entry {t.entry_price} → {t.exit_price ?? t.current_price ?? "-"}</Text>
      </View>
      <View style={{ alignItems: "flex-end" }}>
        <Text style={{ color: pos ? palette.success : palette.danger, fontWeight: "900", fontSize: 13, fontVariant: ["tabular-nums"] }}>
          {t.pnl_usd !== undefined ? `${pos ? "+" : ""}$${t.pnl_usd.toFixed(2)}` : `${pos ? "+" : ""}${t.pnl_pct.toFixed(2)}%`}
        </Text>
        <Text style={{ color: palette.textMuted, fontSize: 10 }}>{t.pnl_pct.toFixed(2)}%</Text>
      </View>
    </View>
  );
}
function EquityChart({ curve, width, height, palette }: { curve: { balance: number; equity: number }[]; width: number; height: number; palette: any }) {
  if (!curve.length || width <= 0) return <View style={{ height }}><ActivityIndicator color={palette.textMuted} /></View>;
  const bals = curve.map((p) => p.balance);
  const min = Math.min(...bals), max = Math.max(...bals), range = Math.max(1, max - min);
  const path = curve.map((p, i) => {
    const x = (i / (curve.length - 1)) * width;
    const y = height - ((p.balance - min) / range) * (height - 8) - 4;
    return `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
  }).join(" ");
  const areaPath = `${path} L ${width} ${height} L 0 ${height} Z`;
  const isUp = bals[bals.length - 1] >= bals[0];
  const color = isUp ? "#10B981" : "#EF4444";
  return (
    <Svg width={width} height={height}>
      <Defs>
        <SvgGrad id="grad" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={color} stopOpacity="0.28" />
          <Stop offset="1" stopColor={color} stopOpacity="0" />
        </SvgGrad>
      </Defs>
      <Path d={areaPath} fill="url(#grad)" />
      <Path d={path} stroke={color} strokeWidth={2} fill="none" strokeLinejoin="round" />
    </Svg>
  );
}
function MonthlyBars({ months, palette }: { months: number[]; palette: any }) {
  if (!months.length) return null;
  const max = Math.max(...months.map(Math.abs)) || 1;
  return (
    <View style={{ flexDirection: "row", alignItems: "flex-end", height: 80, marginTop: 8, gap: 4 }}>
      {months.map((m, i) => {
        const h = Math.max(4, (Math.abs(m) / max) * 70);
        return (
          <View key={i} style={{ flex: 1, alignItems: "center" }}>
            <View style={{ width: "80%", height: h, backgroundColor: m >= 0 ? palette.success : palette.danger, borderRadius: 3, opacity: 0.85 }} />
            <Text style={{ fontSize: 8, color: palette.textMuted, marginTop: 2 }}>M{i + 1}</Text>
          </View>
        );
      })}
    </View>
  );
}

// -------- Settings sheet ---------
function CopySettingsSheet({ visible, onClose, trader, initial, onSave }: { visible: boolean; onClose: () => void; trader: Trader; initial?: CopySettings; onSave: (patch: Partial<CopySettings>) => void }) {
  const { palette } = useTheme();
  const [mode, setMode] = useState<"fixed_lot" | "multiplier" | "equity_percent">(initial?.mode || "multiplier");
  const [multiplier, setMultiplier] = useState(String(initial?.multiplier ?? 1.0));
  const [fixedLot, setFixedLot] = useState(String(initial?.fixed_lot ?? 0.1));
  const [equityPct, setEquityPct] = useState(String(initial?.equity_percent ?? 2.0));
  const [maxDailyLoss, setMDL] = useState(String(initial?.max_daily_loss_pct ?? 5));
  const [maxDD, setMDD] = useState(String(initial?.max_drawdown_pct ?? 15));
  const [maxOpen, setMO] = useState(String(initial?.max_open_trades ?? 5));
  const [equityProt, setEP] = useState(String(initial?.equity_protection_pct ?? 30));
  useEffect(() => {
    if (visible && initial) {
      setMode(initial.mode); setMultiplier(String(initial.multiplier)); setFixedLot(String(initial.fixed_lot));
      setEquityPct(String(initial.equity_percent)); setMDL(String(initial.max_daily_loss_pct));
      setMDD(String(initial.max_drawdown_pct)); setMO(String(initial.max_open_trades));
      setEP(String(initial.equity_protection_pct));
    }
  }, [visible, initial]);

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" }}>
        <View style={{ backgroundColor: palette.background, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20, maxHeight: "85%" }}>
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <Text style={{ color: palette.textPrimary, fontSize: 18, fontWeight: "800" }}>Copy Settings — {trader.name}</Text>
            <Pressable onPress={onClose} hitSlop={10}><X size={22} color={palette.textPrimary} /></Pressable>
          </View>
          <ScrollView style={{ flexGrow: 0 }}>
            <Text style={ss.label(palette)}>Mode</Text>
            <View style={{ flexDirection: "row", gap: 6, marginBottom: 12 }}>
              {(["multiplier", "fixed_lot", "equity_percent"] as const).map((m) => (
                <Pressable key={m} onPress={() => setMode(m)} style={{ flex: 1, paddingVertical: 10, borderRadius: 8, backgroundColor: mode === m ? palette.primary : palette.surface, borderWidth: 1, borderColor: mode === m ? palette.primary : palette.border, alignItems: "center" }}>
                  <Text style={{ color: mode === m ? "#fff" : palette.textPrimary, fontWeight: "800", fontSize: 11 }}>{m === "fixed_lot" ? "Fixed Lot" : m === "multiplier" ? "Multiplier" : "Equity %"}</Text>
                </Pressable>
              ))}
            </View>
            {mode === "multiplier" && <Field label="Multiplier (0.1 – 5.0)" value={multiplier} setValue={setMultiplier} palette={palette} />}
            {mode === "fixed_lot" && <Field label="Fixed lot per trade" value={fixedLot} setValue={setFixedLot} palette={palette} />}
            {mode === "equity_percent" && <Field label="Equity % per source lot" value={equityPct} setValue={setEquityPct} palette={palette} />}
            <Field label="Max daily loss %" value={maxDailyLoss} setValue={setMDL} palette={palette} />
            <Field label="Max drawdown %" value={maxDD} setValue={setMDD} palette={palette} />
            <Field label="Max open trades" value={maxOpen} setValue={setMO} palette={palette} />
            <Field label="Equity protection %" value={equityProt} setValue={setEP} palette={palette} />
          </ScrollView>
          <Pressable
            onPress={() => onSave({
              mode,
              multiplier: parseFloat(multiplier) || 1,
              fixed_lot: parseFloat(fixedLot) || 0.1,
              equity_percent: parseFloat(equityPct) || 2,
              max_daily_loss_pct: parseFloat(maxDailyLoss) || 5,
              max_drawdown_pct: parseFloat(maxDD) || 15,
              max_open_trades: parseInt(maxOpen, 10) || 5,
              equity_protection_pct: parseFloat(equityProt) || 30,
            })}
            style={{ marginTop: 14, backgroundColor: palette.primary, borderRadius: 10, paddingVertical: 14, alignItems: "center" }}
          >
            <Text style={{ color: "#fff", fontWeight: "900", fontSize: 14 }}>
              {initial && (initial as any).__isActive ? "Update Settings" : "Start Copying"}
            </Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}
function Field({ label, value, setValue, palette }: any) {
  return (
    <View style={{ marginBottom: 12 }}>
      <Text style={ss.label(palette)}>{label}</Text>
      <TextInput value={value} onChangeText={setValue} keyboardType="decimal-pad" style={{ backgroundColor: palette.surface, borderColor: palette.border, borderWidth: 1, borderRadius: 8, paddingHorizontal: 12, paddingVertical: Platform.OS === "ios" ? 10 : 8, color: palette.textPrimary, fontSize: 14, fontWeight: "700" }} />
    </View>
  );
}
const ss = { label: (palette: any) => ({ color: palette.textMuted, fontSize: 11, fontWeight: "800", marginBottom: 4 }) };

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  hdrTitle: { flex: 1, fontSize: 18, fontWeight: "800" },
  hero: { padding: 18, alignItems: "center", borderBottomWidth: StyleSheet.hairlineWidth },
  avatar: { width: 84, height: 84, borderRadius: 42, backgroundColor: "#E2E8F0" },
  name: { fontSize: 20, fontWeight: "900" },
  meta: { fontSize: 12, fontWeight: "600", marginTop: 4 },
  bio: { fontSize: 12, textAlign: "center", marginTop: 8, paddingHorizontal: 20, lineHeight: 17 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 6, padding: 12 },
  sectionTitle: { fontSize: 13, fontWeight: "800", marginTop: 12, marginBottom: 6 },
  tabs: { flexDirection: "row", marginTop: 20, borderBottomWidth: StyleSheet.hairlineWidth },
  tabBtn: { paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 2, borderBottomColor: "transparent" },
  cta: { position: "absolute", left: 0, right: 0, bottom: 0, padding: 12, borderTopWidth: StyleSheet.hairlineWidth, flexDirection: "row", gap: 6 },
  ctaBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingVertical: 12, borderRadius: 10 },
  ctaTxt: { color: "#fff", fontWeight: "900", fontSize: 13 },
});

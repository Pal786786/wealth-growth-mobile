import React, { useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, ActivityIndicator, Alert, Modal } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Calculator, TrendingUp, RefreshCw, ArrowRight, AlertTriangle, BookmarkPlus, Share2, FileDown, FolderOpen, X as XIcon } from "lucide-react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import Svg, { Path, Circle, Line as SvgLine, Text as SvgText } from "react-native-svg";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { api } from "@/src/api/client";
import { formatINR } from "@/src/utils/format";
import { calcPlanHTML, shareCalcText, type CalcSnapshot } from "@/src/utils/calcExport";

type TabId = "onetime" | "sip" | "daily" | "compound";
type TypeCfg = { enabled: boolean; return_min: number; return_max: number; return_default: number; label: string };
type Config = { enabled: boolean; min_amount: number; max_amount: number; types: Record<TabId, TypeCfg> };

const TABS: { id: TabId; label: string; durationLabel: string; returnLabel: string }[] = [
  { id: "onetime",  label: "One Time", durationLabel: "Duration (months)", returnLabel: "Return %" },
  { id: "sip",      label: "SIP",      durationLabel: "Duration (months)", returnLabel: "Annual Return %" },
  { id: "daily",    label: "Daily",    durationLabel: "Number of days",    returnLabel: "Daily Return %" },
  { id: "compound", label: "Compound", durationLabel: "Duration (years)",  returnLabel: "Annual Return %" },
];

function compute(tab: TabId, amount: number, duration: number, ratePct: number, reinvest: boolean) {
  const series: { x: number; v: number }[] = [];
  let invested = 0, maturity = 0;
  if (tab === "onetime") {
    invested = amount;
    if (reinvest) {
      // Treat 'return' as annual; compound monthly
      const months = Math.max(1, duration);
      const r = (ratePct / 100) / 12;
      for (let i = 0; i <= months; i++) {
        const v = amount * Math.pow(1 + r, i);
        series.push({ x: i, v });
      }
      maturity = amount * Math.pow(1 + r, months);
    } else {
      const months = Math.max(1, duration);
      const totalProfit = amount * (ratePct / 100);
      for (let i = 0; i <= months; i++) {
        series.push({ x: i, v: amount + (totalProfit * i / months) });
      }
      maturity = amount + totalProfit;
    }
  } else if (tab === "sip") {
    const months = Math.max(1, duration);
    const r = (ratePct / 100) / 12;
    invested = amount * months;
    for (let i = 0; i <= months; i++) {
      const fv = r === 0 ? amount * i : amount * ((Math.pow(1 + r, i) - 1) / r) * (1 + r);
      series.push({ x: i, v: fv });
    }
    maturity = series[series.length - 1].v;
  } else if (tab === "daily") {
    const days = Math.max(1, duration);
    invested = amount;
    if (reinvest) {
      const r = ratePct / 100;
      for (let i = 0; i <= days; i++) {
        series.push({ x: i, v: amount * Math.pow(1 + r, i) });
      }
      maturity = amount * Math.pow(1 + ratePct / 100, days);
    } else {
      const dailyProfit = amount * (ratePct / 100);
      for (let i = 0; i <= days; i++) {
        series.push({ x: i, v: amount + dailyProfit * i });
      }
      maturity = amount + dailyProfit * days;
    }
  } else {
    // compound
    const years = Math.max(1, duration);
    const r = ratePct / 100;
    invested = amount;
    const steps = Math.max(years * 12, 12);
    for (let i = 0; i <= steps; i++) {
      const t = i / 12;
      series.push({ x: i, v: amount * Math.pow(1 + r, t) });
    }
    maturity = amount * Math.pow(1 + r, years);
  }
  const profit = maturity - invested;
  const growth = invested > 0 ? (profit / invested) * 100 : 0;
  return { invested, profit, maturity, growth, series };
}

function useAnimatedNum(target: number, duration = 600) {
  const [val, setVal] = useState(target);
  useEffect(() => {
    const start = val;
    const t0 = Date.now();
    let raf: any;
    const tick = () => {
      const elapsed = Date.now() - t0;
      const p = Math.min(1, elapsed / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setVal(start + (target - start) * eased);
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target]);
  return val;
}

export default function CalculatorScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const [cfg, setCfg] = useState<Config | null>(null);
  const [tab, setTab] = useState<TabId>("onetime");
  const [amount, setAmount] = useState("10000");
  const [duration, setDuration] = useState("12");
  const [ratePct, setRatePct] = useState("12");
  const [reinvest, setReinvest] = useState(false);
  const [saveModalOpen, setSaveModalOpen] = useState(false);
  const [planName, setPlanName] = useState("");
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    (async () => {
      try { const { data } = await api.get("/calculator/config"); setCfg(data); } catch {}
    })();
  }, []);

  useEffect(() => {
    if (cfg) {
      const t = cfg.types[tab];
      setRatePct(String(t.return_default));
      if (tab === "daily") setDuration("30");
      else if (tab === "compound") setDuration("5");
      else setDuration("12");
    }
  }, [tab, cfg?.enabled]);

  const tabCfg = cfg?.types[tab];
  const minAmt = cfg?.min_amount ?? 100;
  const maxAmt = cfg?.max_amount ?? 1000000;
  const a = Number(amount) || 0;
  const d = Number(duration) || 0;
  const r = Number(ratePct) || 0;
  const amountErr = a < minAmt ? `Min ₹${minAmt}` : a > maxAmt ? `Max ₹${maxAmt}` : "";
  const rateErr = tabCfg && (r < tabCfg.return_min || r > tabCfg.return_max) ? `Allowed ${tabCfg.return_min}–${tabCfg.return_max}%` : "";
  const inputsValid = !amountErr && !rateErr && a > 0 && d > 0;
  const result = useMemo(() => inputsValid ? compute(tab, a, d, r, reinvest) : null, [tab, a, d, r, reinvest, inputsValid]);

  const snapshot: CalcSnapshot | null = result ? {
    calc_type: tab, amount: a, duration: d, rate_pct: r, reinvest,
    invested: result.invested, profit: result.profit, maturity: result.maturity, growth: result.growth,
  } : null;

  const onShare = async () => {
    if (!snapshot) return;
    try { await shareCalcText(snapshot); } catch (e: any) { Alert.alert("Share failed", String(e?.message || e)); }
  };

  const onExportPDF = async () => {
    if (!snapshot) return;
    setExporting(true);
    try {
      const html = calcPlanHTML({ ...snapshot, name: planName || `${TABS.find(t => t.id === tab)?.label} Plan` });
      const { uri } = await Print.printToFileAsync({ html, base64: false });
      const canShare = await Sharing.isAvailableAsync();
      if (canShare) {
        await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle: "Investment Plan PDF" });
      } else {
        Alert.alert("Saved", `PDF generated:\n${uri}`);
      }
    } catch (e: any) {
      Alert.alert("Export failed", String(e?.message || e));
    } finally {
      setExporting(false);
    }
  };

  const onSavePlan = async () => {
    if (!snapshot) return;
    const name = planName.trim();
    if (!name) { Alert.alert("Name required", "Please enter a name for your plan."); return; }
    setSaving(true);
    try {
      await api.post("/calculator/plans", { ...snapshot, name });
      setSaving(false);
      setSaveModalOpen(false);
      setPlanName("");
      if (Platform.OS === "web") {
        // eslint-disable-next-line no-alert
        if (typeof window !== "undefined" && window.confirm(`"${name}" was saved.\n\nView your saved plans now?`)) {
          router.push("/invest/plans");
        }
      } else {
        Alert.alert(
          "Plan saved",
          `"${name}" was added to your saved plans.`,
          [
            { text: "OK", style: "default" },
            { text: "View Plans", onPress: () => router.push("/invest/plans") },
          ],
        );
      }
    } catch (e: any) {
      setSaving(false);
      Alert.alert("Save failed", String(e?.response?.data?.detail || e?.message || e));
    }
  };

  const animInvested = useAnimatedNum(result?.invested || 0);
  const animProfit = useAnimatedNum(result?.profit || 0);
  const animMaturity = useAnimatedNum(result?.maturity || 0);
  const animGrowth = useAnimatedNum(result?.growth || 0);

  if (!cfg) {
    return (
      <Screen>
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={palette.primary} />
        </View>
      </Screen>
    );
  }
  if (!cfg.enabled) {
    return (
      <Screen>
        <Pressable onPress={() => router.back()} style={s.back}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center", padding: 32 }}>
          <Calculator color={palette.textMuted} size={48} />
          <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 18, marginTop: 12 }}>Calculator is disabled</Text>
          <Text style={{ color: palette.textSecondary, fontSize: 13, textAlign: "center", marginTop: 6 }}>Please contact support.</Text>
        </View>
      </Screen>
    );
  }

  const enabledTabs = TABS.filter(t => cfg.types[t.id]?.enabled);

  return (
    <Screen>
      <View style={{ flexDirection: "row", alignItems: "center" }}>
        <Pressable onPress={() => router.back()} style={s.back} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <View style={{ flex: 1 }} />
        <Pressable onPress={() => router.push("/invest/plans")} testID="saved-plans-btn"
          style={{ flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 20, backgroundColor: palette.primary + "1A", borderWidth: 1, borderColor: palette.primary + "40" }}>
          <FolderOpen color={palette.primary} size={14} />
          <Text style={{ color: palette.primary, fontWeight: "800", fontSize: 12 }}>Saved Plans</Text>
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ paddingBottom: 40, gap: 14 }} keyboardShouldPersistTaps="handled">
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginTop: 4 }}>
          <Calculator color={palette.primary} size={26} />
          <Text style={{ fontSize: 24, fontWeight: "800", color: palette.textPrimary, letterSpacing: -0.5 }}>Investment Calculator</Text>
        </View>
        <Text style={{ color: palette.textSecondary, fontSize: 13 }}>Plan your future returns instantly. Calculations happen on your device.</Text>

        {/* Tabs */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingRight: 16 }}>
          {enabledTabs.map(t => (
            <Pressable key={t.id} onPress={() => setTab(t.id)} testID={`tab-${t.id}`}
              style={{ paddingHorizontal: 18, paddingVertical: 10, borderRadius: 22, borderWidth: 1,
                backgroundColor: tab === t.id ? palette.primary : palette.surface,
                borderColor: tab === t.id ? palette.primary : palette.border,
                shadowColor: tab === t.id ? palette.primary : "transparent",
                shadowOpacity: tab === t.id ? 0.3 : 0, shadowRadius: 8, shadowOffset: { width: 0, height: 4 } }}>
              <Text style={{ color: tab === t.id ? "#fff" : palette.textPrimary, fontWeight: "800", fontSize: 13 }}>{t.label}</Text>
            </Pressable>
          ))}
        </ScrollView>

        {/* Inputs */}
        <Card style={{ gap: 12 }}>
          <Field label={tab === "sip" ? "Monthly SIP (₹)" : "Investment Amount (₹)"} value={amount} onChange={setAmount} keyboardType="number-pad" error={amountErr} palette={palette} testID="calc-amount" />
          <Field label={TABS.find(t=>t.id===tab)!.durationLabel} value={duration} onChange={setDuration} keyboardType="number-pad" palette={palette} testID="calc-duration" />
          <Field label={TABS.find(t=>t.id===tab)!.returnLabel} value={ratePct} onChange={setRatePct} keyboardType="decimal-pad" error={rateErr} palette={palette} testID="calc-rate" />

          {(tab === "onetime" || tab === "daily") ? (
            <Pressable onPress={() => setReinvest(v => !v)} style={{ flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 6 }} testID="reinvest-toggle">
              <View style={{ width: 44, height: 26, borderRadius: 13, backgroundColor: reinvest ? palette.primary : palette.border, padding: 3, justifyContent: "center" }}>
                <View style={{ width: 20, height: 20, borderRadius: 10, backgroundColor: "#fff", marginLeft: reinvest ? 18 : 0 }} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: palette.textPrimary, fontWeight: "700", fontSize: 13 }}>Reinvest Profit</Text>
                <Text style={{ color: palette.textSecondary, fontSize: 11 }}>Auto-compound earnings every period</Text>
              </View>
              <RefreshCw color={reinvest ? palette.primary : palette.textMuted} size={16} />
            </Pressable>
          ) : null}
        </Card>

        {tab === "daily" ? (
          <View style={{ flexDirection: "row", gap: 8, backgroundColor: palette.warning + "1A", padding: 10, borderRadius: 12 }}>
            <AlertTriangle color={palette.warning} size={16} />
            <Text style={{ flex: 1, fontSize: 11, color: palette.textPrimary, lineHeight: 16 }}>
              Estimated returns are projections only and may vary based on market conditions.
            </Text>
          </View>
        ) : null}

        {/* Results */}
        {result ? (
          <View style={{ borderRadius: 20, padding: 18, backgroundColor: palette.primary, gap: 14, shadowColor: palette.primary, shadowOpacity: 0.3, shadowRadius: 14, shadowOffset: { width: 0, height: 8 }, elevation: 6 }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: "rgba(255,255,255,0.7)", fontSize: 11, fontWeight: "700" }}>TOTAL INVESTMENT</Text>
                <Text style={{ color: "#fff", fontSize: 18, fontWeight: "800", marginTop: 2 }}>{formatINR(animInvested)}</Text>
              </View>
              <View style={{ flex: 1, alignItems: "flex-end" }}>
                <Text style={{ color: "rgba(255,255,255,0.7)", fontSize: 11, fontWeight: "700" }}>GROWTH</Text>
                <Text style={{ color: "#A7F3D0", fontSize: 18, fontWeight: "800", marginTop: 2 }}>{animGrowth.toFixed(2)}%</Text>
              </View>
            </View>
            <View style={{ height: 1, backgroundColor: "rgba(255,255,255,0.2)" }} />
            <View>
              <Text style={{ color: "rgba(255,255,255,0.7)", fontSize: 11, fontWeight: "700" }}>ESTIMATED PROFIT</Text>
              <Text style={{ color: "#A7F3D0", fontSize: 32, fontWeight: "800", marginTop: 2, textShadowColor: "#10B981", textShadowRadius: 12, letterSpacing: -0.5 }}>{formatINR(animProfit)}</Text>
            </View>
            <View>
              <Text style={{ color: "rgba(255,255,255,0.7)", fontSize: 11, fontWeight: "700" }}>MATURITY VALUE</Text>
              <Text style={{ color: "#fff", fontSize: 26, fontWeight: "800", marginTop: 2, letterSpacing: -0.5 }}>{formatINR(animMaturity)}</Text>
            </View>
          </View>
        ) : null}

        {/* Chart */}
        {result && result.series.length > 1 ? (
          <Card style={{ gap: 8 }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
              <TrendingUp color={palette.primary} size={16} />
              <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 13 }}>Growth Projection</Text>
            </View>
            <GrowthChart series={result.series} invested={result.invested} maturity={result.maturity} palette={palette} />
          </Card>
        ) : null}

        {/* CTA */}
        {result ? (
          <>
            <View style={{ flexDirection: "row", gap: 8 }}>
              <Pressable onPress={() => setSaveModalOpen(true)} testID="save-plan-btn"
                style={{ flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 12, borderRadius: 12, borderWidth: 1.5, borderColor: palette.primary, backgroundColor: palette.primary + "12" }}>
                <BookmarkPlus color={palette.primary} size={16} />
                <Text style={{ color: palette.primary, fontWeight: "800", fontSize: 13 }}>Save Plan</Text>
              </Pressable>
              <Pressable onPress={onShare} testID="share-btn"
                style={{ flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 12, borderRadius: 12, borderWidth: 1.5, borderColor: palette.border, backgroundColor: palette.surface }}>
                <Share2 color={palette.textPrimary} size={16} />
                <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 13 }}>Share</Text>
              </Pressable>
              <Pressable onPress={onExportPDF} disabled={exporting} testID="export-pdf-btn"
                style={{ flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 12, borderRadius: 12, borderWidth: 1.5, borderColor: palette.border, backgroundColor: palette.surface, opacity: exporting ? 0.5 : 1 }}>
                {exporting ? <ActivityIndicator color={palette.textPrimary} size="small" /> : <FileDown color={palette.textPrimary} size={16} />}
                <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 13 }}>PDF</Text>
              </Pressable>
            </View>
            <Pressable onPress={() => router.push("/(tabs)/invest")} testID="start-invest-btn"
              style={{ backgroundColor: palette.success, paddingVertical: 16, borderRadius: 14, alignItems: "center", flexDirection: "row", justifyContent: "center", gap: 8 }}>
              <Text style={{ color: "#fff", fontWeight: "800", fontSize: 15 }}>🚀 Start Investment Now</Text>
              <ArrowRight color="#fff" size={18} />
            </Pressable>
          </>
        ) : null}

        <Text style={{ color: palette.textMuted, fontSize: 10, textAlign: "center", marginTop: 8, fontStyle: "italic" }}>
          Calculations are estimates only. Actual returns may vary.
        </Text>
      </ScrollView>

      {/* Save Plan modal */}
      <Modal visible={saveModalOpen} transparent animationType="fade" onRequestClose={() => setSaveModalOpen(false)}>
        <Pressable onPress={() => setSaveModalOpen(false)} style={{ flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "center", padding: 20 }}>
          <Pressable onPress={(e) => e.stopPropagation()} style={{ backgroundColor: palette.background, borderRadius: 20, padding: 20, gap: 14, borderWidth: 1, borderColor: palette.border }}>
            <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <BookmarkPlus color={palette.primary} size={20} />
                <Text style={{ color: palette.textPrimary, fontSize: 18, fontWeight: "800" }}>Save Plan</Text>
              </View>
              <Pressable onPress={() => setSaveModalOpen(false)} hitSlop={10}><XIcon color={palette.textMuted} size={20} /></Pressable>
            </View>
            <Text style={{ color: palette.textSecondary, fontSize: 12 }}>Save this calculation to revisit, share, or compare later.</Text>
            <View>
              <Text style={{ fontSize: 11, fontWeight: "700", color: palette.textSecondary, marginBottom: 4 }}>PLAN NAME</Text>
              <TextInput value={planName} onChangeText={setPlanName} placeholder={`${TABS.find(t => t.id === tab)?.label} Plan`} placeholderTextColor={palette.textMuted} autoFocus testID="save-plan-name"
                style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 12, padding: 12, color: palette.textPrimary, backgroundColor: palette.surface, fontSize: 15, fontWeight: "700" }} />
            </View>
            {snapshot ? (
              <View style={{ backgroundColor: palette.surface, padding: 12, borderRadius: 12, gap: 6 }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                  <Text style={{ color: palette.textSecondary, fontSize: 11 }}>Invested</Text>
                  <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }}>{formatINR(snapshot.invested)}</Text>
                </View>
                <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                  <Text style={{ color: palette.textSecondary, fontSize: 11 }}>Maturity</Text>
                  <Text style={{ color: palette.success, fontSize: 12, fontWeight: "800" }}>{formatINR(snapshot.maturity)}</Text>
                </View>
              </View>
            ) : null}
            <Pressable onPress={onSavePlan} disabled={saving || !planName.trim()} testID="confirm-save-btn"
              style={{ backgroundColor: palette.primary, paddingVertical: 14, borderRadius: 12, alignItems: "center", opacity: saving || !planName.trim() ? 0.6 : 1 }}>
              {saving ? <ActivityIndicator color="#fff" /> : <Text style={{ color: "#fff", fontWeight: "800", fontSize: 14 }}>Save Plan</Text>}
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </Screen>
  );
}

function Field({ label, value, onChange, keyboardType, error, palette, testID }: any) {
  return (
    <View>
      <Text style={{ fontSize: 11, fontWeight: "700", color: palette.textSecondary, marginBottom: 4 }}>{label.toUpperCase()}</Text>
      <TextInput value={value} onChangeText={onChange} keyboardType={keyboardType} testID={testID}
        style={{ borderWidth: 1, borderColor: error ? palette.danger : palette.border, borderRadius: 12, padding: 12, color: palette.textPrimary, backgroundColor: palette.surface, fontSize: 16, fontWeight: "700" }} />
      {error ? <Text style={{ color: palette.danger, fontSize: 10, marginTop: 4 }}>{error}</Text> : null}
    </View>
  );
}

function GrowthChart({ series, invested, maturity, palette }: { series: { x: number; v: number }[]; invested: number; maturity: number; palette: any }) {
  const W = 320, H = 160, PAD_L = 36, PAD_R = 12, PAD_T = 14, PAD_B = 22;
  const minV = Math.min(invested, ...series.map(p => p.v));
  const maxV = Math.max(invested, maturity, ...series.map(p => p.v));
  const maxX = series[series.length - 1].x;
  const sx = (x: number) => PAD_L + (x / maxX) * (W - PAD_L - PAD_R);
  const sy = (v: number) => H - PAD_B - ((v - minV) / Math.max(1, maxV - minV)) * (H - PAD_T - PAD_B);
  const path = series.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(1)},${sy(p.v).toFixed(1)}`).join(" ");
  const area = `${path} L${sx(maxX).toFixed(1)},${(H - PAD_B).toFixed(1)} L${sx(0).toFixed(1)},${(H - PAD_B).toFixed(1)} Z`;
  const last = series[series.length - 1];
  return (
    <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}>
      {/* baseline (invested) */}
      <SvgLine x1={PAD_L} y1={sy(invested)} x2={W - PAD_R} y2={sy(invested)} stroke={palette.border} strokeWidth="1" strokeDasharray="4 4" />
      <SvgText x={4} y={sy(invested) + 3} fontSize="8" fill={palette.textMuted}>Invested</SvgText>
      {/* area */}
      <Path d={area} fill={palette.primary} fillOpacity={0.15} />
      {/* line */}
      <Path d={path} stroke={palette.primary} strokeWidth="2.5" fill="none" />
      {/* target marker */}
      <Circle cx={sx(last.x)} cy={sy(last.v)} r="5" fill={palette.success} />
      <Circle cx={sx(last.x)} cy={sy(last.v)} r="9" fill={palette.success} fillOpacity={0.2} />
      <SvgText x={sx(last.x) - 30} y={sy(last.v) - 10} fontSize="9" fontWeight="bold" fill={palette.success}>Target</SvgText>
      {/* axis labels */}
      <SvgText x={PAD_L} y={H - 6} fontSize="8" fill={palette.textMuted}>0</SvgText>
      <SvgText x={W - PAD_R - 12} y={H - 6} fontSize="8" fill={palette.textMuted}>{maxX}</SvgText>
    </Svg>
  );
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
});

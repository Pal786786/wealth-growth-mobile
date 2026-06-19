import React, { useCallback, useState } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, RefreshControl, Alert } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { ChevronLeft, FolderOpen, Share2, FileDown, Trash2, Calculator } from "lucide-react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { api } from "@/src/api/client";
import { formatINR, shortDate } from "@/src/utils/format";
import { calcPlanHTML, shareCalcText, type CalcSnapshot } from "@/src/utils/calcExport";

type Plan = CalcSnapshot & {
  plan_id: string;
  name: string;
  created_at: string;
  updated_at?: string;
};

const TYPE_LABEL: Record<string, string> = {
  onetime: "One Time",
  sip: "SIP",
  daily: "Daily",
  compound: "Compound",
};

export default function PlansScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/calculator/plans");
      setPlans(data);
    } catch (e: any) {
      Alert.alert("Failed to load", String(e?.response?.data?.detail || e?.message || e));
      setPlans([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { setLoading(true); load(); }, [load]));

  const onShare = async (p: Plan) => {
    try { await shareCalcText(p); } catch (e: any) { Alert.alert("Share failed", String(e?.message || e)); }
  };

  const onExportPDF = async (p: Plan) => {
    setBusyId(p.plan_id);
    try {
      const html = calcPlanHTML(p);
      const { uri } = await Print.printToFileAsync({ html, base64: false });
      const canShare = await Sharing.isAvailableAsync();
      if (canShare) {
        await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle: p.name });
      } else {
        Alert.alert("Saved", `PDF generated:\n${uri}`);
      }
    } catch (e: any) {
      Alert.alert("Export failed", String(e?.message || e));
    } finally {
      setBusyId(null);
    }
  };

  const onDelete = (p: Plan) => {
    Alert.alert("Delete plan?", `"${p.name}" will be removed permanently.`, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete", style: "destructive", onPress: async () => {
          setBusyId(p.plan_id);
          try {
            await api.delete(`/calculator/plans/${p.plan_id}`);
            setPlans((prev) => (prev || []).filter((x) => x.plan_id !== p.plan_id));
          } catch (e: any) {
            Alert.alert("Delete failed", String(e?.response?.data?.detail || e?.message || e));
          } finally {
            setBusyId(null);
          }
        },
      },
    ]);
  };

  return (
    <Screen>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginTop: 4 }}>
        <Pressable onPress={() => router.back()} testID="back-btn" hitSlop={10} style={{ padding: 4 }}>
          <ChevronLeft color={palette.textPrimary} size={26} />
        </Pressable>
        <FolderOpen color={palette.primary} size={22} />
        <Text style={{ fontSize: 22, fontWeight: "800", color: palette.textPrimary, letterSpacing: -0.5, flex: 1 }}>Saved Plans</Text>
        <Pressable onPress={() => router.push("/invest/calculator")} testID="new-plan-btn"
          style={{ flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: palette.primary }}>
          <Calculator color="#fff" size={14} />
          <Text style={{ color: "#fff", fontWeight: "800", fontSize: 12 }}>New</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 40, gap: 10, paddingTop: 12 }}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={palette.primary} onRefresh={() => { setRefreshing(true); load(); }} />}>
        {loading ? (
          <View style={{ paddingTop: 60, alignItems: "center" }}>
            <ActivityIndicator color={palette.primary} />
          </View>
        ) : plans && plans.length === 0 ? (
          <View style={{ paddingTop: 60, alignItems: "center", gap: 10 }}>
            <FolderOpen color={palette.textMuted} size={48} />
            <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 16 }}>No saved plans yet</Text>
            <Text style={{ color: palette.textSecondary, textAlign: "center", paddingHorizontal: 30, fontSize: 13 }}>
              Use the Investment Calculator to compute returns, then tap “Save Plan” to keep it here.
            </Text>
            <Pressable onPress={() => router.push("/invest/calculator")} testID="empty-cta"
              style={{ flexDirection: "row", alignItems: "center", gap: 6, marginTop: 14, paddingHorizontal: 20, paddingVertical: 12, borderRadius: 12, backgroundColor: palette.primary }}>
              <Calculator color="#fff" size={16} />
              <Text style={{ color: "#fff", fontWeight: "800", fontSize: 14 }}>Open Calculator</Text>
            </Pressable>
          </View>
        ) : (
          plans?.map((p) => (
            <Card key={p.plan_id} style={{ gap: 10 }} testID={`plan-${p.plan_id}`}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 15 }} numberOfLines={1}>{p.name}</Text>
                  <Text style={{ color: palette.textSecondary, fontSize: 11, marginTop: 2 }}>
                    {TYPE_LABEL[p.calc_type] || p.calc_type} • Saved {shortDate(p.created_at)}
                  </Text>
                </View>
                <View style={{ paddingHorizontal: 8, paddingVertical: 3, borderRadius: 999, backgroundColor: palette.primary + "1A" }}>
                  <Text style={{ color: palette.primary, fontWeight: "800", fontSize: 11 }}>{TYPE_LABEL[p.calc_type]}</Text>
                </View>
              </View>

              <View style={{ flexDirection: "row", justifyContent: "space-between", backgroundColor: palette.surface, borderRadius: 12, padding: 10 }}>
                <View>
                  <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "700" }}>INVESTED</Text>
                  <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 13, marginTop: 2 }}>{formatINR(p.invested)}</Text>
                </View>
                <View>
                  <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "700" }}>PROFIT</Text>
                  <Text style={{ color: palette.success, fontWeight: "800", fontSize: 13, marginTop: 2 }}>{formatINR(p.profit)}</Text>
                </View>
                <View>
                  <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "700" }}>MATURITY</Text>
                  <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 13, marginTop: 2 }}>{formatINR(p.maturity)}</Text>
                </View>
                <View>
                  <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "700" }}>GROWTH</Text>
                  <Text style={{ color: palette.success, fontWeight: "800", fontSize: 13, marginTop: 2 }}>+{p.growth.toFixed(2)}%</Text>
                </View>
              </View>

              <View style={{ flexDirection: "row", gap: 8 }}>
                <Pressable onPress={() => onShare(p)} testID={`share-${p.plan_id}`}
                  style={{ flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingVertical: 9, borderRadius: 10, borderWidth: 1, borderColor: palette.border }}>
                  <Share2 color={palette.textPrimary} size={14} />
                  <Text style={{ color: palette.textPrimary, fontWeight: "700", fontSize: 12 }}>Share</Text>
                </Pressable>
                <Pressable onPress={() => onExportPDF(p)} disabled={busyId === p.plan_id} testID={`pdf-${p.plan_id}`}
                  style={{ flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingVertical: 9, borderRadius: 10, borderWidth: 1, borderColor: palette.border, opacity: busyId === p.plan_id ? 0.5 : 1 }}>
                  {busyId === p.plan_id ? <ActivityIndicator color={palette.textPrimary} size="small" /> : <FileDown color={palette.textPrimary} size={14} />}
                  <Text style={{ color: palette.textPrimary, fontWeight: "700", fontSize: 12 }}>PDF</Text>
                </Pressable>
                <Pressable onPress={() => onDelete(p)} disabled={busyId === p.plan_id} testID={`delete-${p.plan_id}`}
                  style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10, borderWidth: 1, borderColor: palette.danger + "40", backgroundColor: palette.danger + "10" }}>
                  <Trash2 color={palette.danger} size={14} />
                </Pressable>
              </View>
            </Card>
          ))
        )}
      </ScrollView>
    </Screen>
  );
}

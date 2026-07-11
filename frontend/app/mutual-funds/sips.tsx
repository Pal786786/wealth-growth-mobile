/**
 * My SIPs — list with pause / resume / cancel actions and modify.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl, Alert } from "react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { mfApi, MFSip, fmtINR } from "@/src/api/mutualFunds";
import { Card } from "@/src/components/Card";
import { Pause, Play, XCircle, AlertTriangle, ClipboardList } from "lucide-react-native";

const STATUSES: MFSip["status"][] = ["active", "paused", "cancelled", "failed", "completed"];

export default function SipsScreen() {
  const { palette } = useTheme();
  const [filter, setFilter] = useState<"all" | MFSip["status"]>("all");
  const [items, setItems] = useState<MFSip[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await mfApi.sipList(filter === "all" ? undefined : filter);
      setItems(r.items);
    } catch {} finally { setLoading(false); setRefreshing(false); }
  }, [filter]);

  useEffect(() => { setLoading(true); load(); }, [filter]);

  const setStatus = async (sip: MFSip, status: MFSip["status"]) => {
    try { await mfApi.sipStatus(sip.sip_id, status); await load(); }
    catch (e: any) { Alert.alert("Error", e?.response?.data?.detail || e?.message || "Failed"); }
  };

  const confirmCancel = (sip: MFSip) => {
    Alert.alert("Cancel SIP?", `Are you sure you want to cancel this SIP in ${sip.fund_name}?`, [
      { text: "Keep SIP", style: "cancel" },
      { text: "Cancel SIP", style: "destructive", onPress: () => setStatus(sip, "cancelled") },
    ]);
  };

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      <ScrollView
        contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
      >
        <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
          {(["all", ...STATUSES] as const).map((f) => {
            const active = filter === f;
            return (
              <Pressable key={f} onPress={() => setFilter(f)} style={[st.pill, { backgroundColor: active ? palette.primary : palette.surface, borderColor: active ? palette.primary : palette.border }]}>
                <Text style={{ color: active ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800", letterSpacing: 0.5 }}>{String(f).toUpperCase()}</Text>
              </Pressable>
            );
          })}
        </View>

        {loading ? (
          <ActivityIndicator color={palette.primary} size="large" style={{ marginTop: 40 }} />
        ) : items.length === 0 ? (
          <View style={{ padding: 40, alignItems: "center", gap: 8 }}>
            <ClipboardList color={palette.textMuted} size={40} />
            <Text style={{ color: palette.textSecondary, fontWeight: "800" }}>No SIPs yet</Text>
            <Text style={{ color: palette.textMuted, fontSize: 12, textAlign: "center" }}>Start a SIP from any fund&apos;s details page.</Text>
          </View>
        ) : items.map((sip) => (
          <Card key={sip.sip_id} style={{ padding: 14, gap: 8 }}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
              <View style={{ flex: 1, gap: 3 }}>
                <Text style={{ color: palette.textPrimary, fontSize: 13, fontWeight: "800" }} numberOfLines={2}>{sip.fund_name}</Text>
                <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700" }}>{sip.frequency.toUpperCase()} · Day {sip.day_of_month}</Text>
              </View>
              <View style={{ alignItems: "flex-end" }}>
                <Text style={{ color: palette.textPrimary, fontSize: 16, fontWeight: "800" }}>{fmtINR(sip.amount)}</Text>
                <StatusBadge status={sip.status} palette={palette} />
              </View>
            </View>
            <View style={{ flexDirection: "row", gap: 12 }}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800" }}>NEXT RUN</Text>
                <Text style={{ color: palette.textPrimary, fontSize: 11, fontWeight: "700" }}>{new Date(sip.next_run_at).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800" }}>SUCCESS</Text>
                <Text style={{ color: palette.success, fontSize: 11, fontWeight: "800" }}>{sip.success_count} runs</Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800" }}>FAILED</Text>
                <Text style={{ color: sip.failure_count > 0 ? palette.danger : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{sip.failure_count} runs</Text>
              </View>
            </View>
            <View style={{ flexDirection: "row", gap: 6 }}>
              {sip.status === "active" ? (
                <ActionBtn icon={Pause} label="Pause"  onPress={() => setStatus(sip, "paused")} tint={palette.warning} palette={palette} testID={`sip-pause-${sip.sip_id}`} />
              ) : sip.status === "paused" ? (
                <ActionBtn icon={Play}  label="Resume" onPress={() => setStatus(sip, "active")} tint={palette.success} palette={palette} testID={`sip-resume-${sip.sip_id}`} />
              ) : null}
              {sip.status !== "cancelled" && sip.status !== "completed" ? (
                <ActionBtn icon={XCircle} label="Cancel" onPress={() => confirmCancel(sip)} tint={palette.danger} palette={palette} testID={`sip-cancel-${sip.sip_id}`} />
              ) : null}
            </View>
            {sip.status === "failed" ? (
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: palette.danger + "15", padding: 8, borderRadius: 8 }}>
                <AlertTriangle color={palette.danger} size={12} />
                <Text style={{ color: palette.danger, fontSize: 11, fontWeight: "700", flex: 1 }}>SIP moved to failed after retries. Top up wallet and reactivate.</Text>
              </View>
            ) : null}
          </Card>
        ))}
      </ScrollView>
    </View>
  );
}

function StatusBadge({ status, palette }: any) {
  const map: Record<string, string> = { active: palette.success, paused: palette.warning, cancelled: palette.textMuted, failed: palette.danger, completed: palette.primary };
  const c = map[status] || palette.textMuted;
  return (
    <View style={{ backgroundColor: c + "22", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, marginTop: 3 }}>
      <Text style={{ color: c, fontSize: 9, fontWeight: "800", letterSpacing: 0.6 }}>{status.toUpperCase()}</Text>
    </View>
  );
}
function ActionBtn({ icon: Icon, label, onPress, tint, palette, testID }: any) {
  return (
    <Pressable onPress={onPress} style={{ flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingVertical: 8, borderRadius: 10, backgroundColor: tint + "1A" }} testID={testID}>
      <Icon color={tint} size={14} />
      <Text style={{ color: tint, fontWeight: "800", fontSize: 11 }}>{label}</Text>
    </Pressable>
  );
}

const st = StyleSheet.create({
  pill: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
});

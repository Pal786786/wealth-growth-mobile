import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Alert } from "react-native";
import { useRouter, useLocalSearchParams, useFocusEffect } from "expo-router";
import { ChevronLeft, Landmark, Clock, CheckCircle2, XCircle, ShieldCheck, Share2, RotateCcw } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { Button } from "@/src/components/Button";
import { useToast } from "@/src/components/Toast";
import { withdrawalApi, type Withdrawal } from "@/src/api/withdrawal";
import { formatINR, shortDate } from "@/src/utils/format";
import { generateAndShareReceipt } from "@/src/utils/withdrawalReceipt";

type TL = { event: string; actor: string; at: string; meta?: any };

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

const EVENT_LABELS: Record<string, string> = {
  created: "Requested",
  otp_verified: "OTP Verified",
  under_review: "Under Review",
  approved: "Approved",
  auto_approved: "Auto-approved ⚡",
  processing: "Processing",
  completed: "Completed",
  rejected: "Rejected",
  failed: "Failed",
  cancelled: "Cancelled",
  refunded: "Refunded",
  payout_completed: "Payout Completed",
  payout_processing: "Payout Sent to Bank",
  payout_failed: "Payout Failed",
  refunded_on_payout_failure: "Refunded (Payout Failed)",
  utr_stamped: "UTR Recorded",
  admin_override_created: "Admin-Initiated",
};

export default function WithdrawalDetailScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [w, setW] = useState<Withdrawal | null>(null);
  const [timeline, setTimeline] = useState<TL[]>([]);
  const [loading, setLoading] = useState(true);
  const [sharing, setSharing] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await withdrawalApi.detail(String(id));
      setW(d.withdrawal); setTimeline(d.timeline || []);
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Failed to load withdrawal");
    } finally { setLoading(false); }
  }, [id, show]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const cancel = () => {
    if (!w) return;
    Alert.alert("Cancel withdrawal?", `Any held funds will be returned to your wallet.`, [
      { text: "Keep", style: "cancel" },
      { text: "Cancel Withdrawal", style: "destructive", onPress: async () => {
        try {
          await withdrawalApi.cancel(w.withdrawal_id);
          show("success", "Withdrawal cancelled");
          load();
        } catch (e: any) {
          show("error", e?.response?.data?.detail || "Couldn't cancel");
        }
      } },
    ]);
  };

  const share = async () => {
    if (!w) return;
    setSharing(true);
    try {
      await generateAndShareReceipt(w);
    } catch {
      show("error", "Couldn't generate PDF");
    } finally { setSharing(false); }
  };

  if (loading || !w) return (
    <Screen>
      <ActivityIndicator color={palette.primary} style={{ marginTop: 40 }} />
    </Screen>
  );

  const meta = STATUS_META[w.status] || STATUS_META.pending;
  const StatusIcon = meta.icon;
  const canCancel = w.status === "pending" || w.status === "under_review";

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.replace("/withdrawals")} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>Withdrawal</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 14, paddingBottom: 80 }}>
        {/* Hero */}
        <View style={[s.hero, { backgroundColor: meta.color + "15", borderColor: meta.color + "55" }]}>
          <View style={[s.heroIcon, { backgroundColor: meta.color }]}>
            <StatusIcon color="#fff" size={26} />
          </View>
          <Text style={[s.heroLabel, { color: meta.color }]}>{meta.label.toUpperCase()}</Text>
          <Text style={[s.heroAmt, { color: palette.textPrimary }]}>{formatINR(w.amount)}</Text>
          <Text style={[s.heroRef, { color: palette.textSecondary }]}>Ref · {w.reference_no}</Text>
          {w.reason_admin && (w.status === "rejected" || w.status === "failed") && (
            <View style={s.rejectBox}>
              <Text style={s.rejectTxt}>⚠️  {w.reason_admin}</Text>
            </View>
          )}
        </View>

        {/* Bank details */}
        <Card>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
            <View style={[s.bankIcon, { backgroundColor: palette.primary + "22" }]}>
              <Landmark color={palette.primary} size={20} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.bankName, { color: palette.textPrimary }]}>{w.bank_snapshot.bank_name}</Text>
              <Text style={[s.bankMeta, { color: palette.textSecondary }]}>{w.bank_snapshot.account_masked} · {w.bank_snapshot.ifsc}</Text>
              <Text style={[s.bankMeta, { color: palette.textMuted }]}>{w.bank_snapshot.holder_name}</Text>
            </View>
          </View>
        </Card>

        {/* Amount breakdown */}
        <Card>
          <Text style={[s.small, { color: palette.textSecondary, marginBottom: 8 }]}>BREAKDOWN</Text>
          <Row label="Withdrawal amount" value={formatINR(w.amount)} palette={palette} />
          <Row label="Charge" value={w.charge > 0 ? `– ${formatINR(w.charge)}` : "FREE"} palette={palette} valueColor={w.charge > 0 ? palette.danger : palette.success} />
          <View style={[s.divider, { backgroundColor: palette.border }]} />
          <Row label="Net credit to bank" value={formatINR(w.net_amount)} palette={palette} bold />
          {w.reason && <Row label="Reason" value={w.reason} palette={palette} />}
        </Card>

        {/* Sprint 12.2 — Settlement / UTR */}
        {(w.utr || w.provider_reference || w.provider || w.auto_approved) && (
          <Card>
            <Text style={[s.small, { color: palette.textSecondary, marginBottom: 8 }]}>SETTLEMENT</Text>
            {w.auto_approved && (
              <Row label="Approval" value="Auto-approved ⚡" palette={palette} valueColor={palette.success} />
            )}
            {w.provider && <Row label="Provider" value={w.provider.toUpperCase()} palette={palette} />}
            {w.utr && (
              <Row label="UTR" value={w.utr} palette={palette} bold valueColor={palette.success} />
            )}
            {w.provider_reference && (
              <Row label="Provider Ref" value={w.provider_reference} palette={palette} />
            )}
            {w.settlement_status && (
              <Row label="Settlement" value={w.settlement_status.toUpperCase()} palette={palette} />
            )}
          </Card>
        )}

        {/* Timeline */}
        <Card>
          <Text style={[s.small, { color: palette.textSecondary, marginBottom: 10 }]}>STATUS TIMELINE</Text>
          <View style={{ gap: 8 }}>
            {timeline.length === 0 ? (
              <Text style={{ color: palette.textMuted, fontSize: 12 }}>—</Text>
            ) : timeline.map((t, i) => (
              <View key={i} style={{ flexDirection: "row", gap: 10 }}>
                <View style={[s.tlDot, { backgroundColor: palette.primary, marginTop: 6 }]} />
                <View style={{ flex: 1, borderLeftWidth: 2, borderLeftColor: palette.border, paddingLeft: 10, paddingBottom: 8 }}>
                  <Text style={{ color: palette.textPrimary, fontSize: 13, fontWeight: "800" }}>{EVENT_LABELS[t.event] || t.event}</Text>
                  <Text style={{ color: palette.textMuted, fontSize: 10 }}>{shortDate(t.at)} · {t.actor}</Text>
                  {t.meta?.reason && <Text style={{ color: palette.textSecondary, fontSize: 11, marginTop: 2 }}>Reason: {t.meta.reason}</Text>}
                </View>
              </View>
            ))}
          </View>
        </Card>

        {/* Actions */}
        {canCancel && (
          <Button label="Cancel Withdrawal" variant="danger" onPress={cancel} icon={<RotateCcw color="#fff" size={18} />} />
        )}

        <Button
          label={sharing ? "Preparing PDF..." : "Share PDF Receipt"}
          variant="secondary"
          onPress={share}
          disabled={sharing}
          icon={sharing ? <ActivityIndicator color={palette.primary} /> : <Share2 color={palette.primary} size={18} />}
          testID="btn-share-receipt"
        />
      </ScrollView>
    </Screen>
  );
}

function Row({ label, value, bold, valueColor, palette }: { label: string; value: string; bold?: boolean; valueColor?: string; palette: any }) {
  return (
    <View style={s.row}>
      <Text style={{ color: palette.textSecondary, fontSize: 12, fontWeight: bold ? "800" : "600", flex: 1 }} numberOfLines={2}>{label}</Text>
      <Text style={{ color: valueColor || palette.textPrimary, fontSize: bold ? 15 : 13, fontWeight: bold ? "900" : "800" }}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { fontSize: 20, fontWeight: "800", letterSpacing: -0.4 },
  hero: { padding: 18, borderRadius: 20, borderWidth: 1, alignItems: "center", gap: 6 },
  heroIcon: { width: 60, height: 60, borderRadius: 60, alignItems: "center", justifyContent: "center" },
  heroLabel: { fontSize: 11, fontWeight: "900", letterSpacing: 1.4, marginTop: 6 },
  heroAmt: { fontSize: 32, fontWeight: "900", letterSpacing: -1 },
  heroRef: { fontSize: 12, fontWeight: "600" },
  rejectBox: { marginTop: 8, padding: 10, backgroundColor: "rgba(239,68,68,0.12)", borderRadius: 12, borderWidth: 1, borderColor: "rgba(239,68,68,0.35)", alignSelf: "stretch" },
  rejectTxt: { fontSize: 12, color: "#DC2626", fontWeight: "700", textAlign: "center" },
  bankIcon: { padding: 10, borderRadius: 12 },
  bankName: { fontSize: 14, fontWeight: "800" },
  bankMeta: { fontSize: 11, fontWeight: "600" },
  small: { fontSize: 11, fontWeight: "800", letterSpacing: 0.5 },
  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6, gap: 8, alignItems: "center" },
  divider: { height: 1, marginVertical: 4 },
  tlDot: { width: 8, height: 8, borderRadius: 4 },
});

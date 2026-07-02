import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter, useFocusEffect } from "expo-router";
import { LinearGradient } from "expo-linear-gradient";
import { Shield, ArrowRight, CheckCircle2, Clock, XCircle, AlertTriangle, RefreshCw, ChevronRight, FileWarning } from "lucide-react-native";
import { kycApi, type KycProfile, type KycStatus } from "@/src/api/kyc";

const STEP_LABELS = ["Personal", "Address", "PAN", "Aadhaar", "Selfie", "Bank", "Nominee"];

const STATUS_MAP: Record<KycStatus, { label: string; color: string; bg: string; Icon: any; desc: string }> = {
  not_started: { label: "Not Started", color: "#94A3B8", bg: "rgba(148,163,184,0.15)", Icon: Shield, desc: "Complete your KYC to unlock all features" },
  in_progress: { label: "In Progress", color: "#38BDF8", bg: "rgba(56,189,248,0.15)", Icon: Clock, desc: "Continue where you left off" },
  submitted: { label: "Submitted", color: "#F0CC5C", bg: "rgba(240,204,92,0.15)", Icon: Clock, desc: "We've received your submission" },
  under_review: { label: "Under Review", color: "#F0CC5C", bg: "rgba(240,204,92,0.15)", Icon: Clock, desc: "Approval typically within 24 hours" },
  approved: { label: "Approved", color: "#10B981", bg: "rgba(16,185,129,0.15)", Icon: CheckCircle2, desc: "You're fully verified — all features unlocked" },
  rejected: { label: "Rejected", color: "#EF4444", bg: "rgba(239,68,68,0.15)", Icon: XCircle, desc: "See reason below and re-submit" },
  reupload_required: { label: "Re-upload Required", color: "#F59E0B", bg: "rgba(245,158,11,0.15)", Icon: FileWarning, desc: "Please re-upload the requested documents" },
};

export default function KycStatusScreen() {
  const router = useRouter();
  const [profile, setProfile] = useState<KycProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setErr(null);
      const p = await kycApi.status();
      setProfile(p);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || "Unable to load KYC status");
    } finally {
      setLoading(false); setRefreshing(false);
    }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (loading) {
    return <SafeAreaView style={styles.container}><ActivityIndicator size="large" color="#D4AF37" style={{ marginTop: 80 }} /></SafeAreaView>;
  }
  const s = profile?.status || "not_started";
  const info = STATUS_MAP[s];
  const canEdit = !profile?.locked && !(["approved", "under_review", "submitted"] as KycStatus[]).includes(s);
  const done = s === "approved";

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <LinearGradient colors={["#0F172A", "#1E293B", "#0F172A"]} style={styles.headerBg}>
        <View style={styles.headerRow}>
          <Text style={styles.headerTitle}>KYC Verification</Text>
          <Pressable onPress={() => { setRefreshing(true); load(); }} style={styles.refreshBtn}><RefreshCw color="#94A3B8" size={18} /></Pressable>
        </View>

        <View style={styles.badgeCenter}>
          <View style={[styles.iconOrb, { backgroundColor: info.bg, borderColor: info.color }]}>
            <info.Icon color={info.color} size={40} strokeWidth={2.2} />
          </View>
          <View style={[styles.pill, { backgroundColor: info.bg, borderColor: info.color }]}>
            <Text style={[styles.pillText, { color: info.color }]}>{info.label}</Text>
          </View>
          <Text style={styles.desc}>{info.desc}</Text>
        </View>
      </LinearGradient>

      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 16, paddingBottom: 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor="#D4AF37" />}>

        {err && <View style={styles.errCard}><Text style={styles.errText}>{err}</Text></View>}

        {/* Progress bar */}
        <View style={styles.progCard}>
          <View style={styles.progHead}>
            <Text style={styles.progLabel}>Completion</Text>
            <Text style={styles.progVal}>{profile?.completion || 0}%</Text>
          </View>
          <View style={styles.progTrack}>
            <LinearGradient colors={["#F0CC5C", "#D4AF37"]} start={{x:0,y:0}} end={{x:1,y:0}}
              style={[styles.progFill, { width: `${profile?.completion || 0}%` }]} />
          </View>
          <View style={styles.stepDots}>
            {STEP_LABELS.map((label, i) => {
              const filled = !!profile?.steps?.[String(i + 1)];
              return (
                <View key={label} style={styles.stepDotWrap}>
                  <View style={[styles.stepDot, filled && styles.stepDotDone]}>
                    {filled && <CheckCircle2 color="#0F172A" size={12} strokeWidth={3} />}
                  </View>
                  <Text style={[styles.stepDotLabel, filled && { color: "#D4AF37" }]}>{label}</Text>
                </View>
              );
            })}
          </View>
        </View>

        {profile?.reject_reason && (
          <View style={styles.warnCard}>
            <XCircle color="#EF4444" size={18} />
            <View style={{ flex: 1 }}>
              <Text style={styles.warnTitle}>Rejection Reason</Text>
              <Text style={styles.warnText}>{profile.reject_reason}</Text>
            </View>
          </View>
        )}

        {(profile?.reupload_fields?.length ?? 0) > 0 && (
          <View style={styles.warnCard}>
            <AlertTriangle color="#F59E0B" size={18} />
            <View style={{ flex: 1 }}>
              <Text style={styles.warnTitle}>Please Re-upload</Text>
              <Text style={styles.warnText}>{profile!.reupload_fields!.join(", ")}</Text>
            </View>
          </View>
        )}

        {done && profile?.expires_at && (
          <View style={styles.infoCard}>
            <CheckCircle2 color="#10B981" size={16} />
            <Text style={styles.infoText}>Valid until {new Date(profile.expires_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</Text>
          </View>
        )}

        {/* CTA */}
        {canEdit && (
          <Pressable onPress={() => router.push("/kyc/wizard")}
            style={({ pressed }) => [styles.cta, pressed && { opacity: 0.9 }]}>
            <LinearGradient colors={["#F0CC5C", "#D4AF37", "#B8941F"]} start={{x:0,y:0}} end={{x:1,y:0}} style={styles.ctaGrad}>
              <Text style={styles.ctaText}>{profile?.completion ? "Continue KYC" : "Start KYC Verification"}</Text>
              <ArrowRight color="#0F172A" size={18} strokeWidth={2.5} />
            </LinearGradient>
          </Pressable>
        )}

        {/* Feature unlock list */}
        <Text style={styles.sectionTitle}>What KYC Unlocks</Text>
        {[
          { label: "Add money to wallet", icon: "💳" },
          { label: "Send money & bill payments", icon: "💸" },
          { label: "Invest in mutual funds, gold & stocks", icon: "📈" },
          { label: "Forex trading (demo & live)", icon: "🌐" },
          { label: "Withdraw funds", icon: "🏦" },
        ].map(f => (
          <View key={f.label} style={[styles.featureRow, done && styles.featureRowDone]}>
            <Text style={{ fontSize: 20 }}>{f.icon}</Text>
            <Text style={styles.featureText}>{f.label}</Text>
            {done ? <CheckCircle2 color="#10B981" size={18} /> : <Text style={styles.featureLock}>🔒</Text>}
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F8FAFC" },
  headerBg: { padding: 20, paddingTop: 12, paddingBottom: 32, borderBottomLeftRadius: 32, borderBottomRightRadius: 32 },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 20 },
  headerTitle: { color: "#F8FAFC", fontSize: 22, fontWeight: "800" },
  refreshBtn: { padding: 8, borderRadius: 999, backgroundColor: "rgba(255,255,255,0.05)" },
  badgeCenter: { alignItems: "center" },
  iconOrb: { width: 88, height: 88, borderRadius: 28, borderWidth: 2, alignItems: "center", justifyContent: "center", marginBottom: 14 },
  pill: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  pillText: { fontSize: 12, fontWeight: "800", letterSpacing: 1, textTransform: "uppercase" },
  desc: { color: "#94A3B8", fontSize: 13, marginTop: 10, textAlign: "center", maxWidth: 260 },

  progCard: { backgroundColor: "#FFF", padding: 20, borderRadius: 20, marginBottom: 14, shadowColor: "#0F172A", shadowOpacity: 0.06, shadowRadius: 12, elevation: 3 },
  progHead: { flexDirection: "row", justifyContent: "space-between", marginBottom: 10 },
  progLabel: { color: "#64748B", fontSize: 13, fontWeight: "600" },
  progVal: { color: "#0F172A", fontSize: 20, fontWeight: "800" },
  progTrack: { height: 6, backgroundColor: "#E2E8F0", borderRadius: 3, overflow: "hidden" },
  progFill: { height: 6, borderRadius: 3 },
  stepDots: { flexDirection: "row", justifyContent: "space-between", marginTop: 16 },
  stepDotWrap: { alignItems: "center", flex: 1 },
  stepDot: { width: 24, height: 24, borderRadius: 12, backgroundColor: "#F1F5F9", borderWidth: 1, borderColor: "#E2E8F0", alignItems: "center", justifyContent: "center" },
  stepDotDone: { backgroundColor: "#D4AF37", borderColor: "#B8941F" },
  stepDotLabel: { fontSize: 9, color: "#94A3B8", marginTop: 4, fontWeight: "600" },

  warnCard: { flexDirection: "row", gap: 10, backgroundColor: "#FEF3C7", padding: 14, borderRadius: 14, marginBottom: 12, borderWidth: 1, borderColor: "#FDE68A" },
  warnTitle: { color: "#92400E", fontSize: 12, fontWeight: "800", marginBottom: 2 },
  warnText: { color: "#78350F", fontSize: 13 },

  infoCard: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: "#D1FAE5", padding: 12, borderRadius: 12, marginBottom: 12 },
  infoText: { color: "#065F46", fontSize: 13, fontWeight: "600" },

  errCard: { backgroundColor: "#FEE2E2", padding: 12, borderRadius: 12, marginBottom: 12 },
  errText: { color: "#991B1B", fontSize: 13 },

  cta: { borderRadius: 16, overflow: "hidden", marginTop: 6, marginBottom: 20, shadowColor: "#D4AF37", shadowOpacity: 0.4, shadowRadius: 12, elevation: 6 },
  ctaGrad: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingVertical: 16 },
  ctaText: { color: "#0F172A", fontSize: 16, fontWeight: "800" },

  sectionTitle: { color: "#0F172A", fontSize: 15, fontWeight: "800", marginTop: 8, marginBottom: 10 },
  featureRow: { flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: "#FFF", padding: 14, borderRadius: 12, marginBottom: 8, borderWidth: 1, borderColor: "#E2E8F0" },
  featureRowDone: { backgroundColor: "#F0FDF4", borderColor: "#BBF7D0" },
  featureText: { flex: 1, color: "#334155", fontSize: 14, fontWeight: "600" },
  featureLock: { fontSize: 14 },
});

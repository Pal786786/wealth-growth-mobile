import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, TextInput, Modal } from "react-native";
import { useRouter } from "expo-router";
import {
  ChevronLeft, Shield, Heart, Car, Plane, Calculator, FileText, X,
  CheckCircle2, XCircle, Clock, AlertCircle,
} from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";
import { formatINR } from "@/src/utils/format";

const ICONS: Record<string, any> = { health: Heart, life: Shield, motor: Car, travel: Plane };

const STATUS_META: Record<string, { label: string; color: string; Icon: any }> = {
  submitted:      { label: "Submitted",      color: "#64748B", Icon: FileText },
  under_review:   { label: "Under Review",   color: "#0EA5E9", Icon: Clock },
  info_requested: { label: "Info Requested", color: "#F59E0B", Icon: AlertCircle },
  approved:       { label: "Approved",       color: "#10B981", Icon: CheckCircle2 },
  rejected:       { label: "Rejected",       color: "#EF4444", Icon: XCircle },
};

const CLAIM_TYPE_LABELS: Record<string, string> = {
  hospitalization: "Hospitalization", outpatient: "OPD / Outpatient",
  accident: "Accident", theft: "Theft", damage: "Damage / Repair",
  death: "Death Benefit", trip_cancel: "Trip Cancellation",
  trip_delay: "Trip Delay", other: "Other",
};

const TYPE_TO_CLAIMS: Record<string, string[]> = {
  health: ["hospitalization", "outpatient", "other"],
  life: ["death", "other"],
  motor: ["accident", "theft", "damage", "other"],
  travel: ["trip_cancel", "trip_delay", "other"],
};

type Claim = {
  claim_id: string;
  policy_id: string;
  plan_name: string;
  plan_type: string;
  claim_type: string;
  claim_amount: number;
  approved_amount: number;
  status: keyof typeof STATUS_META;
  description?: string;
  admin_note?: string;
  created_at: string;
  updated_at: string;
};

export default function Insurance() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [plans, setPlans] = useState<any[]>([]);
  const [policies, setPolicies] = useState<any[]>([]);
  const [claims, setClaims] = useState<Claim[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [claimFor, setClaimFor] = useState<any | null>(null);
  const [viewingClaim, setViewingClaim] = useState<Claim | null>(null);

  const load = async () => {
    try {
      const [{ data: p }, { data: my }, { data: c }] = await Promise.all([
        api.get("/insurance/plans"),
        api.get("/insurance/policies"),
        api.get("/insurance/claims"),
      ]);
      setPlans(p); setPolicies(my); setClaims(c.items || []);
    } catch {}
  };

  useEffect(() => { load(); }, []);

  const buy = async (plan: any) => {
    try {
      await api.post(`/insurance/buy?plan_id=${plan.id}`);
      show("success", `Policy active: ${plan.name}`);
      load();
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Could not buy policy");
    }
  };

  const filtered = filter === "all" ? plans : plans.filter((p) => p.type === filter);

  const [calcType, setCalcType] = useState<string>("health");
  const [calcAge, setCalcAge] = useState("35");
  const [calcCover, setCalcCover] = useState("500000");
  const [calcResult, setCalcResult] = useState<any>(null);
  const [calcLoading, setCalcLoading] = useState(false);
  const runCalculator = async () => {
    setCalcLoading(true);
    try {
      const body: any = { plan_type: calcType, age: Number(calcAge) || 30, cover: Number(calcCover) || 500000 };
      if (calcType === "motor") body.vehicle_age = 3;
      if (calcType === "travel") body.trip_days = 7;
      const { data } = await api.post("/insurance/quote", body);
      setCalcResult(data);
    } catch { show("error", "Could not calculate premium"); }
    finally { setCalcLoading(false); }
  };

  return (
    <Screen>
      <Pressable onPress={() => router.back()} style={s.back} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
      <ScrollView contentContainerStyle={s.scroll}>
        <Text style={[s.title, { color: palette.textPrimary }]}>Insurance</Text>
        <Text style={[s.sub, { color: palette.textSecondary }]}>Protect what matters most</Text>

        {/* Premium Calculator */}
        <Card style={{ gap: 10 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Calculator color={palette.primary} size={18} />
            <Text style={{ fontSize: 14, fontWeight: "800", color: palette.textPrimary }}>Premium Calculator</Text>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {["health", "life", "motor", "travel"].map((t) => (
              <Pressable key={t} onPress={() => { setCalcType(t); setCalcResult(null); }}
                style={{ paddingHorizontal: 14, paddingVertical: 6, borderRadius: 14, borderWidth: 1,
                  backgroundColor: calcType === t ? palette.primary : palette.surfaceAlt,
                  borderColor: calcType === t ? palette.primary : palette.border }}>
                <Text style={{ color: calcType === t ? "#fff" : palette.textPrimary, fontWeight: "700", textTransform: "capitalize", fontSize: 12 }}>{t}</Text>
              </Pressable>
            ))}
          </ScrollView>
          <View style={{ flexDirection: "row", gap: 10 }}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 11, color: palette.textSecondary, fontWeight: "600" }}>Age</Text>
              <TextInput
                value={calcAge} onChangeText={setCalcAge} keyboardType="number-pad"
                style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 10, color: palette.textPrimary, marginTop: 4 }}
                testID="calc-age"
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 11, color: palette.textSecondary, fontWeight: "600" }}>Cover ₹</Text>
              <TextInput
                value={calcCover} onChangeText={setCalcCover} keyboardType="number-pad"
                style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 10, padding: 10, color: palette.textPrimary, marginTop: 4 }}
                testID="calc-cover"
              />
            </View>
          </View>
          <Pressable
            onPress={runCalculator}
            disabled={calcLoading}
            style={{ backgroundColor: palette.primary, paddingVertical: 12, borderRadius: 12, alignItems: "center" }}
            testID="calc-quote-btn"
          >
            <Text style={{ color: "#fff", fontWeight: "800" }}>
              {calcLoading ? "Calculating…" : "Calculate Premium"}
            </Text>
          </Pressable>
          {calcResult ? (
            <View style={{ backgroundColor: palette.surfaceAlt, padding: 12, borderRadius: 12, gap: 4 }}>
              <Text style={{ color: palette.textSecondary, fontSize: 11, fontWeight: "700" }}>ESTIMATED ANNUAL PREMIUM</Text>
              <Text style={{ color: palette.primary, fontSize: 22, fontWeight: "800" }}>
                {formatINR(calcResult.total_annual_premium)}
              </Text>
              <Text style={{ color: palette.textSecondary, fontSize: 12 }}>
                ≈ {formatINR(calcResult.monthly_emi)}/month · incl. GST {formatINR(calcResult.gst)}
              </Text>
              <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 4, fontStyle: "italic" }}>{calcResult.disclaimer}</Text>
            </View>
          ) : null}
        </Card>

        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipsRow}>
          {["all", "health", "life", "motor", "travel"].map((f) => (
            <Pressable
              key={f}
              onPress={() => setFilter(f)}
              style={[s.chip, {
                backgroundColor: filter === f ? palette.primary : palette.surface,
                borderColor: filter === f ? palette.primary : palette.border,
              }]}
              testID={`ins-filter-${f}`}
            >
              <Text style={{ color: filter === f ? "#fff" : palette.textPrimary, fontWeight: "700", textTransform: "capitalize" }}>{f}</Text>
            </Pressable>
          ))}
        </ScrollView>

        {filtered.map((p) => {
          const Icon = ICONS[p.type] || Shield;
          return (
            <Card key={p.id} style={{ gap: 10 }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
                <View style={[s.iconWrap, { backgroundColor: palette.primary + "1A" }]}>
                  <Icon color={palette.primary} size={22} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[s.planName, { color: palette.textPrimary }]}>{p.name}</Text>
                  <Text style={[s.planMeta, { color: palette.textSecondary }]}>Cover {formatINR(p.cover, { compact: true })}</Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={[s.premium, { color: palette.primary }]}>{formatINR(p.premium)}</Text>
                  <Text style={[s.planMeta, { color: palette.textMuted }]}>per year</Text>
                </View>
              </View>
              <Pressable
                onPress={() => buy(p)}
                style={[s.buyBtn, { backgroundColor: palette.primary }]}
                testID={`buy-policy-${p.id}`}
              >
                <Text style={{ color: "#fff", fontWeight: "800" }}>Buy Policy</Text>
              </Pressable>
            </Card>
          );
        })}

        {policies.length > 0 ? (
          <>
            <Text style={[s.section, { color: palette.textPrimary }]}>Your Active Policies</Text>
            {policies.map((p) => (
              <Card key={p.policy_id} style={{ gap: 8 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
                  <View style={[s.iconWrap, { backgroundColor: palette.success + "1A" }]}>
                    <Shield color={palette.success} size={20} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[s.planName, { color: palette.textPrimary }]}>{p.plan_name}</Text>
                    <Text style={[s.planMeta, { color: palette.textSecondary }]}>Active • Cover {formatINR(p.cover, { compact: true })}</Text>
                  </View>
                  <Text style={{ color: palette.success, fontWeight: "800" }}>{formatINR(p.premium)}</Text>
                </View>
                <Pressable
                  onPress={() => setClaimFor(p)}
                  style={[s.claimBtn, { backgroundColor: palette.primary + "15", borderColor: palette.primary + "40" }]}
                  testID={`file-claim-${p.policy_id}`}
                >
                  <FileText color={palette.primary} size={14} />
                  <Text style={{ color: palette.primary, fontWeight: "800", fontSize: 13 }}>File a Claim</Text>
                </Pressable>
              </Card>
            ))}
          </>
        ) : null}

        {claims.length > 0 ? (
          <>
            <Text style={[s.section, { color: palette.textPrimary }]}>Your Claims</Text>
            {claims.map((c) => {
              const m = STATUS_META[c.status] || STATUS_META.submitted;
              return (
                <Pressable key={c.claim_id} onPress={() => setViewingClaim(c)}>
                  <Card style={{ gap: 6 }}>
                    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                      <Text style={{ fontSize: 13, fontWeight: "800", color: palette.textPrimary, flex: 1 }} numberOfLines={1}>
                        {c.plan_name}
                      </Text>
                      <View style={{ flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: m.color + "1A", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 }}>
                        <m.Icon color={m.color} size={11} />
                        <Text style={{ color: m.color, fontWeight: "800", fontSize: 10 }}>{m.label}</Text>
                      </View>
                    </View>
                    <Text style={{ fontSize: 11, color: palette.textSecondary }}>
                      {CLAIM_TYPE_LABELS[c.claim_type] || c.claim_type} · Claimed {formatINR(c.claim_amount)}
                    </Text>
                    {c.status === "approved" && c.approved_amount > 0 ? (
                      <Text style={{ fontSize: 11, color: palette.success, fontWeight: "700" }}>
                        ✓ Approved {formatINR(c.approved_amount)} — credited to wallet
                      </Text>
                    ) : null}
                  </Card>
                </Pressable>
              );
            })}
          </>
        ) : null}
      </ScrollView>

      {claimFor ? (
        <FileClaimModal
          policy={claimFor}
          onClose={() => setClaimFor(null)}
          onSubmitted={() => { setClaimFor(null); load(); }}
        />
      ) : null}

      {viewingClaim ? (
        <ClaimDetailModal claim={viewingClaim} onClose={() => setViewingClaim(null)} />
      ) : null}
    </Screen>
  );
}

function FileClaimModal({ policy, onClose, onSubmitted }: { policy: any; onClose: () => void; onSubmitted: () => void }) {
  const { palette } = useTheme();
  const { show } = useToast();
  const [claimType, setClaimType] = useState(TYPE_TO_CLAIMS[policy.type]?.[0] || "other");
  const [amount, setAmount] = useState("");
  const [incidentDate, setIncidentDate] = useState("");
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    const amt = Number(amount);
    if (!amt || amt <= 0) return show("error", "Enter a valid claim amount");
    if (amt > (policy.cover || 0)) return show("error", `Amount exceeds policy cover (${formatINR(policy.cover)})`);
    if (description.trim().length < 10) return show("error", "Description must be at least 10 characters");
    setSubmitting(true);
    try {
      await api.post("/insurance/claims", {
        policy_id: policy.policy_id,
        claim_type: claimType,
        claim_amount: amt,
        incident_date: incidentDate || undefined,
        description: description.trim(),
      });
      show("success", "Claim submitted! You'll be notified once it's reviewed.");
      onSubmitted();
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Could not submit claim");
    } finally { setSubmitting(false); }
  };

  const allowedTypes = TYPE_TO_CLAIMS[policy.type] || ["other"];

  return (
    <Modal visible animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: palette.background }}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 16, borderBottomWidth: 1, borderBottomColor: palette.border }}>
          <Text style={{ fontSize: 18, fontWeight: "800", color: palette.textPrimary }}>File a Claim</Text>
          <Pressable onPress={onClose} style={{ padding: 4 }}><X color={palette.textPrimary} size={22} /></Pressable>
        </View>
        <ScrollView contentContainerStyle={{ padding: 16, gap: 14 }}>
          <Card>
            <Text style={{ fontSize: 12, color: palette.textSecondary, fontWeight: "700" }}>POLICY</Text>
            <Text style={{ fontSize: 15, fontWeight: "800", color: palette.textPrimary, marginTop: 2 }}>{policy.plan_name}</Text>
            <Text style={{ fontSize: 12, color: palette.textSecondary, marginTop: 2 }}>Cover: {formatINR(policy.cover, { compact: true })}</Text>
          </Card>

          <View>
            <Text style={{ fontSize: 12, fontWeight: "700", color: palette.textSecondary, marginBottom: 6 }}>CLAIM TYPE</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
              {allowedTypes.map((t) => (
                <Pressable key={t} onPress={() => setClaimType(t)}
                  style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 18, borderWidth: 1,
                    backgroundColor: claimType === t ? palette.primary : palette.surface,
                    borderColor: claimType === t ? palette.primary : palette.border }}>
                  <Text style={{ color: claimType === t ? "#fff" : palette.textPrimary, fontWeight: "700", fontSize: 12 }}>
                    {CLAIM_TYPE_LABELS[t] || t}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
          </View>

          <View>
            <Text style={{ fontSize: 12, fontWeight: "700", color: palette.textSecondary, marginBottom: 6 }}>CLAIM AMOUNT (₹)</Text>
            <TextInput
              value={amount} onChangeText={setAmount} keyboardType="number-pad"
              placeholder="e.g. 25000"
              placeholderTextColor={palette.textMuted}
              style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 12, padding: 12, color: palette.textPrimary, backgroundColor: palette.surface, fontSize: 16, fontWeight: "700" }}
              testID="claim-amount"
            />
            <Text style={{ fontSize: 10, color: palette.textMuted, marginTop: 4 }}>Max claimable: {formatINR(policy.cover)}</Text>
          </View>

          <View>
            <Text style={{ fontSize: 12, fontWeight: "700", color: palette.textSecondary, marginBottom: 6 }}>INCIDENT DATE (OPTIONAL)</Text>
            <TextInput
              value={incidentDate} onChangeText={setIncidentDate}
              placeholder="YYYY-MM-DD"
              placeholderTextColor={palette.textMuted}
              style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 12, padding: 12, color: palette.textPrimary, backgroundColor: palette.surface }}
            />
          </View>

          <View>
            <Text style={{ fontSize: 12, fontWeight: "700", color: palette.textSecondary, marginBottom: 6 }}>
              DESCRIPTION <Text style={{ color: palette.danger }}>*</Text>
            </Text>
            <TextInput
              value={description} onChangeText={setDescription}
              multiline numberOfLines={5}
              placeholder="Describe what happened, hospital/garage name, treatment details, etc. (min 10 chars)"
              placeholderTextColor={palette.textMuted}
              style={{ borderWidth: 1, borderColor: palette.border, borderRadius: 12, padding: 12, color: palette.textPrimary, backgroundColor: palette.surface, minHeight: 110, textAlignVertical: "top" }}
              testID="claim-description"
            />
          </View>

          <View style={{ backgroundColor: palette.warning + "1A", padding: 12, borderRadius: 12, flexDirection: "row", gap: 8 }}>
            <AlertCircle color={palette.warning} size={18} />
            <Text style={{ flex: 1, fontSize: 11, color: palette.textPrimary, lineHeight: 16 }}>
              Filing a fraudulent claim is a punishable offence. Our team will review within 2–5 business days. You'll receive a push notification once decided.
            </Text>
          </View>

          <Pressable
            onPress={submit} disabled={submitting}
            style={{ backgroundColor: palette.primary, paddingVertical: 14, borderRadius: 12, alignItems: "center", opacity: submitting ? 0.6 : 1 }}
            testID="submit-claim-btn"
          >
            <Text style={{ color: "#fff", fontWeight: "800", fontSize: 15 }}>
              {submitting ? "Submitting…" : "Submit Claim"}
            </Text>
          </Pressable>
        </ScrollView>
      </View>
    </Modal>
  );
}

function ClaimDetailModal({ claim, onClose }: { claim: Claim; onClose: () => void }) {
  const { palette } = useTheme();
  const [detail, setDetail] = useState<any>(null);
  useEffect(() => {
    (async () => {
      try { const { data } = await api.get(`/insurance/claims/${claim.claim_id}`); setDetail(data); }
      catch { setDetail(claim); }
    })();
  }, [claim.claim_id]);
  const m = STATUS_META[claim.status] || STATUS_META.submitted;

  return (
    <Modal visible animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: palette.background }}>
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", padding: 16, borderBottomWidth: 1, borderBottomColor: palette.border }}>
          <View>
            <Text style={{ fontSize: 18, fontWeight: "800", color: palette.textPrimary }}>Claim Details</Text>
            <Text style={{ fontSize: 10, fontFamily: "monospace", color: palette.textMuted }}>{claim.claim_id}</Text>
          </View>
          <Pressable onPress={onClose} style={{ padding: 4 }}><X color={palette.textPrimary} size={22} /></Pressable>
        </View>
        <ScrollView contentContainerStyle={{ padding: 16, gap: 14 }}>
          <View style={{ backgroundColor: m.color + "1A", padding: 14, borderRadius: 14, flexDirection: "row", alignItems: "center", gap: 10 }}>
            <m.Icon color={m.color} size={22} />
            <View style={{ flex: 1 }}>
              <Text style={{ color: m.color, fontWeight: "800", fontSize: 14 }}>{m.label}</Text>
              {claim.status === "approved" && claim.approved_amount > 0 ? (
                <Text style={{ color: palette.success, fontWeight: "700", fontSize: 13, marginTop: 2 }}>
                  Payout {formatINR(claim.approved_amount)} credited
                </Text>
              ) : null}
            </View>
          </View>

          <Card style={{ gap: 4 }}>
            <Text style={{ fontSize: 11, color: palette.textSecondary, fontWeight: "700" }}>POLICY</Text>
            <Text style={{ fontSize: 14, fontWeight: "800", color: palette.textPrimary }}>{claim.plan_name}</Text>
            <Text style={{ fontSize: 12, color: palette.textSecondary, marginTop: 2 }}>
              {CLAIM_TYPE_LABELS[claim.claim_type] || claim.claim_type} · {formatINR(claim.claim_amount)}
            </Text>
          </Card>

          {claim.description ? (
            <Card>
              <Text style={{ fontSize: 11, color: palette.textSecondary, fontWeight: "700" }}>YOUR DESCRIPTION</Text>
              <Text style={{ fontSize: 13, color: palette.textPrimary, marginTop: 4, lineHeight: 18 }}>{claim.description}</Text>
            </Card>
          ) : null}

          {claim.admin_note ? (
            <Card style={{ backgroundColor: m.color + "0F" }}>
              <Text style={{ fontSize: 11, color: m.color, fontWeight: "700" }}>ADMIN NOTE</Text>
              <Text style={{ fontSize: 13, color: palette.textPrimary, marginTop: 4, lineHeight: 18 }}>{claim.admin_note}</Text>
            </Card>
          ) : null}

          {detail?.history?.length ? (
            <Card>
              <Text style={{ fontSize: 11, color: palette.textSecondary, fontWeight: "700", marginBottom: 8 }}>HISTORY</Text>
              {detail.history.map((h: any, i: number) => {
                const hm = STATUS_META[h.event] || { label: h.event, color: palette.textSecondary, Icon: FileText };
                return (
                  <View key={i} style={{ flexDirection: "row", gap: 10, marginBottom: 10 }}>
                    <View style={{ width: 28, height: 28, borderRadius: 14, backgroundColor: hm.color + "1A", alignItems: "center", justifyContent: "center" }}>
                      <hm.Icon color={hm.color} size={14} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 12, fontWeight: "800", color: palette.textPrimary }}>{hm.label}</Text>
                      <Text style={{ fontSize: 10, color: palette.textMuted }}>{new Date(h.at).toLocaleString()}</Text>
                      {h.note ? <Text style={{ fontSize: 11, color: palette.textSecondary, fontStyle: "italic", marginTop: 2 }}>"{h.note}"</Text> : null}
                    </View>
                  </View>
                );
              })}
            </Card>
          ) : null}
        </ScrollView>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  back: { paddingVertical: 8 },
  scroll: { gap: 12, paddingBottom: 40 },
  title: { fontSize: 24, fontWeight: "800", letterSpacing: -0.5, marginTop: 4 },
  sub: { fontSize: 13 },
  chipsRow: { gap: 8, paddingRight: 16, paddingBottom: 4 },
  chip: { paddingHorizontal: 14, height: 36, borderRadius: 18, borderWidth: 1, justifyContent: "center", flexShrink: 0 },
  iconWrap: { padding: 10, borderRadius: 12 },
  planName: { fontSize: 14, fontWeight: "700" },
  planMeta: { fontSize: 11, marginTop: 2 },
  premium: { fontSize: 16, fontWeight: "800" },
  buyBtn: { paddingVertical: 12, borderRadius: 12, alignItems: "center", marginTop: 4 },
  claimBtn: { paddingVertical: 10, borderRadius: 10, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 6, borderWidth: 1 },
  section: { fontSize: 16, fontWeight: "800", marginTop: 8, letterSpacing: -0.3 },
});

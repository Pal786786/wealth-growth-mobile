import React, { useMemo, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, TextInput } from "react-native";
import { useRouter } from "expo-router";
import { ChevronLeft, Home, Car, Baby, Umbrella, Rocket, Target } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Button } from "@/src/components/Button";
import { useToast } from "@/src/components/Toast";
import { advisorApi } from "@/src/api/advisor";
import { formatINR } from "@/src/utils/format";

const PRESETS = [
  { key: "house", label: "Buy a House", icon: Home, defaultAmount: 5000000, defaultYears: 10 },
  { key: "car", label: "Buy a Car", icon: Car, defaultAmount: 800000, defaultYears: 3 },
  { key: "retirement", label: "Retirement", icon: Rocket, defaultAmount: 20000000, defaultYears: 25 },
  { key: "education", label: "Child Education", icon: Baby, defaultAmount: 3000000, defaultYears: 15 },
  { key: "emergency", label: "Emergency Fund", icon: Umbrella, defaultAmount: 500000, defaultYears: 2 },
  { key: "custom", label: "Custom", icon: Target, defaultAmount: 100000, defaultYears: 5 },
];

export default function NewGoalScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [preset, setPreset] = useState<typeof PRESETS[0]>(PRESETS[0]);
  const [title, setTitle] = useState(PRESETS[0].label);
  const [target, setTarget] = useState(String(PRESETS[0].defaultAmount));
  const [years, setYears] = useState(String(PRESETS[0].defaultYears));
  const [saved, setSaved] = useState("0");
  const [risk, setRisk] = useState<"low" | "moderate" | "high">("moderate");
  const [saving, setSaving] = useState(false);

  const targetNum = parseFloat(target) || 0;
  const yearsNum = parseFloat(years) || 0;
  const savedNum = parseFloat(saved) || 0;

  const valid = title.trim().length >= 2 && targetNum > 0 && yearsNum > 0 && yearsNum <= 60;

  const selectPreset = (p: typeof PRESETS[0]) => {
    setPreset(p);
    setTitle(p.label);
    setTarget(String(p.defaultAmount));
    setYears(String(p.defaultYears));
  };

  const submit = async () => {
    if (!valid) return;
    setSaving(true);
    try {
      const g = await advisorApi.createGoal({
        goal_type: preset.key, title: title.trim(), target_amount: targetNum, horizon_years: yearsNum,
        current_savings: savedNum, risk_appetite: risk,
      });
      show("success", `Goal created. SIP: ${formatINR(g.recommended_monthly_sip)}/mo`);
      router.replace({ pathname: "/advisor/goals/[id]", params: { id: g.goal_id } });
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Could not create goal");
    } finally { setSaving(false); }
  };

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>New Goal</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, gap: 16, paddingBottom: 60 }} keyboardShouldPersistTaps="handled">
        <View>
          <Text style={[s.section, { color: palette.textSecondary }]}>PICK A GOAL TYPE</Text>
          <View style={s.presetRow}>
            {PRESETS.map((p) => {
              const Icon = p.icon;
              const active = preset.key === p.key;
              return (
                <Pressable key={p.key} onPress={() => selectPreset(p)} style={[s.preset, { borderColor: active ? palette.primary : palette.border, backgroundColor: active ? palette.primary + "18" : palette.surface }]}>
                  <Icon color={active ? palette.primary : palette.textSecondary} size={20} />
                  <Text style={[s.presetTxt, { color: active ? palette.primary : palette.textSecondary }]}>{p.label}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <Field label="Title" palette={palette}>
          <TextInput value={title} onChangeText={setTitle} style={[s.input, { color: palette.textPrimary, backgroundColor: palette.surface, borderColor: palette.border }]} />
        </Field>

        <Field label={`Target Amount (₹) - ${formatINR(targetNum)}`} palette={palette}>
          <TextInput value={target} onChangeText={(v) => setTarget(v.replace(/[^0-9]/g, ""))} keyboardType="number-pad"
            style={[s.input, { color: palette.textPrimary, backgroundColor: palette.surface, borderColor: palette.border }]} />
        </Field>

        <Field label={`Horizon: ${yearsNum} years`} palette={palette}>
          <TextInput value={years} onChangeText={(v) => setYears(v.replace(/[^0-9.]/g, ""))} keyboardType="decimal-pad"
            style={[s.input, { color: palette.textPrimary, backgroundColor: palette.surface, borderColor: palette.border }]} />
        </Field>

        <Field label={`Already Saved (₹) - ${formatINR(savedNum)}`} palette={palette}>
          <TextInput value={saved} onChangeText={(v) => setSaved(v.replace(/[^0-9]/g, ""))} keyboardType="number-pad"
            style={[s.input, { color: palette.textPrimary, backgroundColor: palette.surface, borderColor: palette.border }]} />
        </Field>

        <Field label="Risk Appetite" palette={palette}>
          <View style={{ flexDirection: "row", gap: 8 }}>
            {["low", "moderate", "high"].map((r) => (
              <Pressable key={r} onPress={() => setRisk(r as any)} style={[s.riskBtn, { borderColor: risk === r ? palette.primary : palette.border, backgroundColor: risk === r ? palette.primary + "18" : palette.surface }]}>
                <Text style={{ color: risk === r ? palette.primary : palette.textSecondary, fontWeight: "800", fontSize: 12, textTransform: "capitalize" }}>{r}</Text>
              </Pressable>
            ))}
          </View>
        </Field>

        <Button label={saving ? "Creating plan..." : "Create Goal & Get AI Plan"} onPress={submit} disabled={!valid || saving} loading={saving} />

        <Text style={{ color: palette.textMuted, fontSize: 11, textAlign: "center" }}>
          We&apos;ll calculate a monthly SIP using compound-interest math and Claude Sonnet 4.5 will craft a personalized asset mix.
        </Text>
      </ScrollView>
    </Screen>
  );
}

function Field({ label, palette, children }: { label: string; palette: any; children: React.ReactNode }) {
  return (
    <View>
      <Text style={{ color: palette.textSecondary, fontSize: 11, fontWeight: "800", letterSpacing: 0.6, marginBottom: 6 }}>{label.toUpperCase()}</Text>
      {children}
    </View>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { fontSize: 18, fontWeight: "800", letterSpacing: -0.3 },
  section: { fontSize: 11, fontWeight: "800", letterSpacing: 0.6, marginBottom: 8 },
  presetRow: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  preset: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 10, borderRadius: 14, borderWidth: 1 },
  presetTxt: { fontSize: 12, fontWeight: "800" },
  input: { borderWidth: 1, borderRadius: 12, padding: 14, fontSize: 16, fontWeight: "700" },
  riskBtn: { flex: 1, paddingVertical: 12, borderRadius: 12, borderWidth: 1, alignItems: "center" },
});

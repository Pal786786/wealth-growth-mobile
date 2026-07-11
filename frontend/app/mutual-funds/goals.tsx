/**
 * Goals — create with kind (retirement/house/etc.), amount, date, expected return.
 * Shows progress %, current, remaining, required monthly SIP, months left, AI suggestion.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, Modal, TextInput, Alert } from "react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { mfApi, MFGoal, GOAL_KINDS, fmtINR } from "@/src/api/mutualFunds";
import { Card } from "@/src/components/Card";
import { Plus, Target, Trash2, Sparkles, X } from "lucide-react-native";

export default function GoalsScreen() {
  const { palette } = useTheme();
  const [items, setItems] = useState<MFGoal[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    try { setItems((await mfApi.goalsList()).items); } catch {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const del = (g: MFGoal) => Alert.alert("Delete goal?", g.name, [
    { text: "Keep", style: "cancel" },
    { text: "Delete", style: "destructive", onPress: async () => { await mfApi.goalDelete(g.goal_id); load(); } },
  ]);

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      <ScrollView contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 40 }}>
        <Pressable onPress={() => setOpen(true)} style={[st.addBtn, { backgroundColor: palette.primary }]} testID="goal-add">
          <Plus color="#fff" size={16} />
          <Text style={{ color: "#fff", fontWeight: "800", fontSize: 13 }}>Add Goal</Text>
        </Pressable>

        {loading ? (
          <ActivityIndicator color={palette.primary} size="large" style={{ marginTop: 40 }} />
        ) : items.length === 0 ? (
          <View style={{ padding: 30, alignItems: "center", gap: 6 }}>
            <Target color={palette.textMuted} size={40} />
            <Text style={{ color: palette.textSecondary, fontWeight: "800" }}>No goals yet</Text>
            <Text style={{ color: palette.textMuted, fontSize: 12, textAlign: "center" }}>Set financial goals and let AI recommend the perfect SIP.</Text>
          </View>
        ) : items.map((g) => {
          const kind = GOAL_KINDS.find((k) => k.key === g.kind);
          return (
            <Card key={g.goal_id} style={{ padding: 14, gap: 8 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
                <View style={{ flex: 1, gap: 3 }}>
                  <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "800" }}>
                    {kind?.emoji || "🎯"} {g.name}
                  </Text>
                  <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700" }}>
                    Target {fmtINR(g.target_amount)} by {new Date(g.target_date).toLocaleDateString("en-IN", { month: "short", year: "numeric" })}
                  </Text>
                </View>
                <Pressable onPress={() => del(g)} style={{ padding: 6 }}>
                  <Trash2 color={palette.textMuted} size={16} />
                </Pressable>
              </View>
              {/* Progress */}
              <View style={{ gap: 4 }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                  <Text style={{ color: palette.textSecondary, fontSize: 12 }}>{fmtINR(g.current_amount)} of {fmtINR(g.target_amount)}</Text>
                  <Text style={{ color: palette.primary, fontSize: 12, fontWeight: "800" }}>{g.progress_pct.toFixed(1)}%</Text>
                </View>
                <View style={{ height: 8, backgroundColor: palette.chipBg, borderRadius: 5, overflow: "hidden" }}>
                  <View style={{ height: 8, width: `${Math.min(100, g.progress_pct)}%`, backgroundColor: palette.primary }} />
                </View>
              </View>
              <View style={{ flexDirection: "row", gap: 10 }}>
                <KV lbl="Remaining"        val={fmtINR(g.remaining_amount)}    palette={palette} />
                <KV lbl="Months left"      val={String(g.months_left)}           palette={palette} />
                <KV lbl="Suggested SIP"    val={fmtINR(g.required_monthly_sip)}  palette={palette} tint={palette.success} />
              </View>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: palette.primary + "12", padding: 8, borderRadius: 8 }}>
                <Sparkles color={palette.primary} size={12} />
                <Text style={{ color: palette.textSecondary, fontSize: 11, flex: 1 }}>
                  Assuming {g.expected_return_pct}% CAGR, a SIP of {fmtINR(g.required_monthly_sip)}/month will hit this goal by {new Date(g.estimated_completion).toLocaleDateString("en-IN", { month: "short", year: "numeric" })}.
                </Text>
              </View>
            </Card>
          );
        })}
      </ScrollView>
      <CreateGoalModal visible={open} onClose={() => setOpen(false)} onCreated={() => { setOpen(false); load(); }} />
    </View>
  );
}

function KV({ lbl, val, palette, tint }: any) {
  return (
    <View style={{ flex: 1, gap: 2 }}>
      <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "800" }}>{lbl.toUpperCase()}</Text>
      <Text style={{ color: tint || palette.textPrimary, fontSize: 12, fontWeight: "800" }}>{val}</Text>
    </View>
  );
}

function CreateGoalModal({ visible, onClose, onCreated }: any) {
  const { palette } = useTheme();
  const [name, setName] = useState("");
  const [kind, setKind] = useState("retirement");
  const [amount, setAmount] = useState("");
  const [years, setYears] = useState("10");
  const [expected, setExpected] = useState("12");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    const amt = Number(amount);
    const yrs = Number(years);
    if (!name || !amt || amt <= 0 || !yrs) { Alert.alert("Missing fields"); return; }
    setSaving(true);
    try {
      const targetDate = new Date();
      targetDate.setFullYear(targetDate.getFullYear() + yrs);
      await mfApi.goalCreate({
        name, kind, target_amount: amt, target_date: targetDate.toISOString(),
        priority: "medium", expected_return_pct: Number(expected) || 12, linked_funds: [],
      });
      setName(""); setAmount(""); setYears("10");
      onCreated?.();
    } catch (e: any) { Alert.alert("Error", e?.response?.data?.detail || e?.message || "Failed"); }
    finally { setSaving(false); }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={{ flex: 1, backgroundColor: palette.overlay }} onPress={onClose} />
      <View style={[gm.sheet, { backgroundColor: palette.surfaceElevated }]}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
          <Text style={{ color: palette.textPrimary, fontSize: 18, fontWeight: "800" }}>New Goal</Text>
          <Pressable onPress={onClose}><X color={palette.textPrimary} size={20} /></Pressable>
        </View>
        <Text style={gm.lbl(palette)}>KIND</Text>
        <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
          {GOAL_KINDS.map((k) => {
            const active = kind === k.key;
            return (
              <Pressable key={k.key} onPress={() => setKind(k.key)} style={[gm.chip, { backgroundColor: active ? palette.primary : palette.surface, borderColor: active ? palette.primary : palette.border }]}>
                <Text style={{ color: active ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{k.emoji} {k.label}</Text>
              </Pressable>
            );
          })}
        </View>
        <Text style={gm.lbl(palette)}>GOAL NAME</Text>
        <TextInput value={name} onChangeText={setName} placeholder="e.g. Dream Home" placeholderTextColor={palette.textMuted} style={gm.input(palette)} testID="goal-name" />
        <Text style={gm.lbl(palette)}>TARGET AMOUNT (₹)</Text>
        <TextInput value={amount} onChangeText={setAmount} keyboardType="decimal-pad" placeholder="10,00,000" placeholderTextColor={palette.textMuted} style={gm.input(palette)} testID="goal-amount" />
        <View style={{ flexDirection: "row", gap: 8 }}>
          <View style={{ flex: 1 }}>
            <Text style={gm.lbl(palette)}>YEARS</Text>
            <TextInput value={years} onChangeText={setYears} keyboardType="number-pad" style={gm.input(palette)} testID="goal-years" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={gm.lbl(palette)}>EXPECTED RETURN %</Text>
            <TextInput value={expected} onChangeText={setExpected} keyboardType="decimal-pad" style={gm.input(palette)} testID="goal-return" />
          </View>
        </View>
        <Pressable onPress={save} disabled={saving} style={[gm.save, { backgroundColor: palette.primary, opacity: saving ? 0.7 : 1 }]} testID="goal-save">
          {saving ? <ActivityIndicator color="#fff" /> : <Text style={{ color: "#fff", fontSize: 15, fontWeight: "800" }}>Save Goal</Text>}
        </Pressable>
      </View>
    </Modal>
  );
}

const st = StyleSheet.create({
  addBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 12, borderRadius: 14 },
});
const gm = {
  sheet: { padding: 16, borderTopLeftRadius: 22, borderTopRightRadius: 22, gap: 8, maxHeight: "90%" } as any,
  chip: { paddingHorizontal: 10, paddingVertical: 7, borderRadius: 999, borderWidth: 1 } as any,
  input: (p: any) => ({ backgroundColor: p.chipBg, borderColor: p.border, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, color: p.textPrimary, fontSize: 15, fontWeight: "800" }) as any,
  lbl: (p: any) => ({ color: p.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1 } as any),
  save: { paddingVertical: 14, borderRadius: 14, alignItems: "center", marginTop: 6 } as any,
};

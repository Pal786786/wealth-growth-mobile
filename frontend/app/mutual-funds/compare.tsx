/**
 * Fund Compare — pick 2–4 funds side-by-side.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, TextInput } from "react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { mfApi, MFFund, fmtINR, RISK_META } from "@/src/api/mutualFunds";
import { Search, X, Plus } from "lucide-react-native";

export default function CompareScreen() {
  const { palette } = useTheme();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<MFFund[]>([]);
  const [picked, setPicked] = useState<MFFund[]>([]);
  const [loading, setLoading] = useState(false);

  const search = useCallback(async (query: string) => {
    if (!query || query.length < 2) { setResults([]); return; }
    setLoading(true);
    try {
      const r = await mfApi.funds({ q: query, limit: 10 });
      setResults(r.items);
    } catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { const t = setTimeout(() => search(q), 250); return () => clearTimeout(t); }, [q, search]);

  const add = (f: MFFund) => {
    if (picked.length >= 4) return;
    if (picked.some((x) => x.fund_id === f.fund_id)) return;
    setPicked([...picked, f]); setQ(""); setResults([]);
  };
  const remove = (id: string) => setPicked(picked.filter((x) => x.fund_id !== id));

  const attributes: { lbl: string; get: (f: MFFund) => string; tint?: (f: MFFund) => string }[] = [
    { lbl: "NAV", get: (f) => fmtINR(f.current_nav) },
    { lbl: "1Y Return", get: (f) => `${(f.returns?.y1 ?? 0).toFixed(2)}%`, tint: (f) => (f.returns?.y1 ?? 0) >= 0 ? palette.success : palette.danger },
    { lbl: "3Y Return", get: (f) => `${(f.returns?.y3 ?? 0).toFixed(2)}%`, tint: (f) => (f.returns?.y3 ?? 0) >= 0 ? palette.success : palette.danger },
    { lbl: "5Y Return", get: (f) => `${(f.returns?.y5 ?? 0).toFixed(2)}%`, tint: (f) => (f.returns?.y5 ?? 0) >= 0 ? palette.success : palette.danger },
    { lbl: "Expense", get: (f) => `${f.expense_ratio}%` },
    { lbl: "AUM (Cr)", get: (f) => `₹${f.aum_cr.toLocaleString("en-IN")}` },
    { lbl: "Risk", get: (f) => RISK_META[f.risk]?.label || f.risk },
    { lbl: "Rating", get: (f) => `${f.star_rating}★` },
    { lbl: "Exit Load", get: (f) => f.exit_load || "Nil" },
    { lbl: "Min SIP", get: (f) => fmtINR(f.min_sip) },
  ];

  return (
    <ScrollView style={{ flex: 1, backgroundColor: palette.background }} contentContainerStyle={{ padding: 16, gap: 12, paddingBottom: 40 }}>
      <Text style={{ color: palette.textPrimary, fontSize: 16, fontWeight: "800" }}>Compare Funds ({picked.length}/4)</Text>

      <View style={[st.searchBox, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <Search color={palette.textMuted} size={16} />
        <TextInput value={q} onChangeText={setQ} placeholder="Add a fund to compare…" placeholderTextColor={palette.textMuted} style={{ flex: 1, color: palette.textPrimary, paddingVertical: 8 }} testID="compare-search" />
        {q ? <Pressable onPress={() => setQ("")}><X color={palette.textMuted} size={16} /></Pressable> : null}
      </View>

      {loading ? <ActivityIndicator color={palette.primary} /> : results.length ? (
        <View style={{ gap: 6 }}>
          {results.map((f) => (
            <Pressable key={f.fund_id} onPress={() => add(f)} style={[st.res, { backgroundColor: palette.surface, borderColor: palette.border }]} testID={`add-cmp-${f.fund_id}`}>
              <View style={{ flex: 1 }}>
                <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }} numberOfLines={2}>{f.name}</Text>
                <Text style={{ color: palette.textMuted, fontSize: 10 }}>{f.amc} · {f.category}</Text>
              </View>
              <View style={[st.plusBtn, { backgroundColor: palette.primary }]}><Plus color="#fff" size={16} /></View>
            </Pressable>
          ))}
        </View>
      ) : null}

      {picked.length === 0 ? (
        <Text style={{ color: palette.textMuted, textAlign: "center", paddingVertical: 30, fontSize: 12 }}>Search and add at least 2 funds to compare.</Text>
      ) : (
        <ScrollView horizontal contentContainerStyle={{ gap: 10 }} showsHorizontalScrollIndicator={false}>
          {picked.map((f) => (
            <View key={f.fund_id} style={[st.col, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 6 }}>
                <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800", flex: 1 }} numberOfLines={3}>{f.name}</Text>
                <Pressable onPress={() => remove(f.fund_id)} style={{ padding: 4 }}>
                  <X color={palette.textMuted} size={14} />
                </Pressable>
              </View>
              <Text style={{ color: palette.textMuted, fontSize: 10 }}>{f.amc}</Text>
              <View style={{ height: 1, backgroundColor: palette.border, marginVertical: 6 }} />
              {attributes.map((a) => (
                <View key={a.lbl} style={{ paddingVertical: 4 }}>
                  <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "800" }}>{a.lbl.toUpperCase()}</Text>
                  <Text style={{ color: a.tint ? a.tint(f) : palette.textPrimary, fontSize: 12, fontWeight: "800" }}>{a.get(f)}</Text>
                </View>
              ))}
            </View>
          ))}
        </ScrollView>
      )}
    </ScrollView>
  );
}

const st = StyleSheet.create({
  searchBox: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, borderRadius: 14, borderWidth: 1 },
  res: { flexDirection: "row", alignItems: "center", gap: 8, padding: 10, borderRadius: 12, borderWidth: 1 },
  plusBtn: { padding: 6, borderRadius: 8 },
  col: { width: 200, padding: 12, borderRadius: 14, borderWidth: 1 },
});

import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { rewardsApi, LeaderboardEntry } from "@/src/api/rewards";

type Period   = "weekly" | "monthly" | "all_time";
type Category = "earners" | "referrers" | "investors" | "traders";

export default function Leaderboard() {
  const router = useRouter();
  const [period, setPeriod]     = useState<Period>("weekly");
  const [category, setCategory] = useState<Category>("earners");
  const [entries, setEntries]   = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading]   = useState(true);

  useEffect(() => {
    setLoading(true);
    rewardsApi.leaderboard(period, category)
      .then((r) => setEntries(r.entries))
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, [period, category]);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}><Ionicons name="chevron-back" size={24} color="#EAEAF0" /></TouchableOpacity>
        <Text style={styles.title}>Leaderboard</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
        {("weekly monthly all_time".split(" ") as Period[]).map((p) => (
          <Chip key={p} label={p.replace("_", " ").toUpperCase()} active={period === p} onPress={() => setPeriod(p)} />
        ))}
      </ScrollView>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
        {("earners referrers investors traders".split(" ") as Category[]).map((c) => (
          <Chip key={c} label={c.toUpperCase()} active={category === c} onPress={() => setCategory(c)} />
        ))}
      </ScrollView>

      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color="#FFB100" />
      ) : (
        <ScrollView contentContainerStyle={{ padding: 16 }}>
          {entries.length === 0 ? (
            <Text style={styles.empty}>No entries yet — be the first!</Text>
          ) : entries.map((e) => (
            <View key={e.user_id} style={styles.row}>
              <Text style={styles.rank}>#{e.rank}</Text>
              <Text style={styles.uid}>{e.user_id.slice(0, 12)}…</Text>
              <Text style={styles.val}>{e.value.toLocaleString()}</Text>
            </View>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const Chip = ({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) => (
  <TouchableOpacity onPress={onPress} style={[styles.chip, active && styles.chipActive]}>
    <Text style={[styles.chipTxt, active && styles.chipTxtActive]}>{label}</Text>
  </TouchableOpacity>
);

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0E0F14" },
  header: { flexDirection: "row", padding: 16, alignItems: "center", justifyContent: "space-between" },
  title: { color: "#EAEAF0", fontSize: 16, fontWeight: "700" },
  chipRow: { paddingHorizontal: 12, paddingBottom: 8, gap: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, backgroundColor: "#171922", borderWidth: 1, borderColor: "#2A2D3A" },
  chipActive: { backgroundColor: "#FFB100", borderColor: "#FFB100" },
  chipTxt: { color: "#8B8F9E", fontSize: 11, fontWeight: "700" },
  chipTxtActive: { color: "#0E0F14" },
  row: { flexDirection: "row", padding: 14, backgroundColor: "#171922", borderRadius: 10, marginBottom: 8,
         borderWidth: 1, borderColor: "#2A2D3A", alignItems: "center", gap: 12 },
  rank: { color: "#FFB100", fontSize: 15, fontWeight: "800", width: 40 },
  uid:  { color: "#EAEAF0", fontSize: 13, flex: 1 },
  val:  { color: "#3CD48F", fontSize: 15, fontWeight: "800" },
  empty: { color: "#8B8F9E", textAlign: "center", marginTop: 40 },
});

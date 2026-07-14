import React, { useEffect, useState } from "react";
import { View, Text, StyleSheet, FlatList, ActivityIndicator, TouchableOpacity } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { rewardsApi, RewardTx } from "@/src/api/rewards";

export default function RewardsHistory() {
  const router = useRouter();
  const [items, setItems] = useState<RewardTx[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    rewardsApi.history(100).then(r => setItems(r.items)).catch(() => {}).finally(() => setLoading(false));
  }, []);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()}><Ionicons name="chevron-back" size={24} color="#EAEAF0" /></TouchableOpacity>
        <Text style={styles.title}>MFB Reward History</Text>
        <View style={{ width: 24 }} />
      </View>
      {loading ? <ActivityIndicator style={{ marginTop: 40 }} color="#FFB100" /> :
        <FlatList
          data={items}
          keyExtractor={(t) => t.tx_id}
          contentContainerStyle={{ padding: 16 }}
          ListEmptyComponent={<Text style={styles.empty}>No reward transactions yet</Text>}
          renderItem={({ item }) => (
            <View style={styles.row}>
              <View style={{ flex: 1 }}>
                <Text style={styles.reason}>{item.reason}</Text>
                <Text style={styles.meta}>{item.source} • {new Date(item.created_at).toLocaleString()}</Text>
              </View>
              <Text style={[styles.amt, item.amount >= 0 ? styles.amtPos : styles.amtNeg]}>
                {item.amount >= 0 ? "+" : ""}{item.amount}
              </Text>
            </View>
          )}
        />
      }
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#0E0F14" },
  header: { flexDirection: "row", padding: 16, alignItems: "center", justifyContent: "space-between" },
  title: { color: "#EAEAF0", fontSize: 16, fontWeight: "700" },
  row: { flexDirection: "row", backgroundColor: "#171922", padding: 14, borderRadius: 10, marginBottom: 8,
         borderWidth: 1, borderColor: "#2A2D3A", alignItems: "center" },
  reason: { color: "#EAEAF0", fontSize: 13, fontWeight: "600" },
  meta: { color: "#8B8F9E", fontSize: 11, marginTop: 2 },
  amt: { fontSize: 16, fontWeight: "800" },
  amtPos: { color: "#3CD48F" },
  amtNeg: { color: "#FF6A6A" },
  empty: { color: "#8B8F9E", textAlign: "center", marginTop: 40 },
});

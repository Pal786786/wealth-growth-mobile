import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, Alert, ActivityIndicator, RefreshControl } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { ChevronLeft, Plus, Landmark, Trash2, ShieldCheck } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { withdrawalApi, type BankAccount } from "@/src/api/withdrawal";

export default function BanksScreen() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [items, setItems] = useState<BankAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const list = await withdrawalApi.listBanks();
      setItems(list);
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Failed to load banks");
    } finally {
      setLoading(false); setRefreshing(false);
    }
  }, [show]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const del = (bank_id: string) => {
    Alert.alert("Remove bank account?", "You'll have to re-add it if you want to withdraw here again.", [
      { text: "Cancel", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: async () => {
        try {
          await withdrawalApi.delBank(bank_id);
          show("success", "Bank account removed");
          setItems((xs) => xs.filter((x) => x.bank_id !== bank_id));
        } catch (e: any) {
          show("error", e?.response?.data?.detail || "Failed to remove");
        }
      } },
    ]);
  };

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>Bank Accounts</Text>
      </View>

      <FlatList
        data={items}
        keyExtractor={(x) => x.bank_id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
        contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 100 }}
        renderItem={({ item }) => (
          <Card style={s.row}>
            <View style={[s.iconWrap, { backgroundColor: palette.primary + "22" }]}>
              <Landmark color={palette.primary} size={20} />
            </View>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={[s.name, { color: palette.textPrimary }]} numberOfLines={1}>{item.bank_name}</Text>
              <Text style={[s.meta, { color: palette.textSecondary }]}>{item.account_masked} · {item.ifsc}</Text>
              <Text style={[s.meta, { color: palette.textMuted }]} numberOfLines={1}>{item.holder_name}</Text>
              {item.verified && (
                <View style={s.verifiedBadge}>
                  <ShieldCheck color="#10B981" size={12} />
                  <Text style={{ color: "#10B981", fontSize: 10, fontWeight: "800" }}>Verified</Text>
                </View>
              )}
            </View>
            <Pressable onPress={() => del(item.bank_id)} hitSlop={8} style={s.delBtn}>
              <Trash2 color={palette.danger} size={18} />
            </Pressable>
          </Card>
        )}
        ListEmptyComponent={
          loading ? <ActivityIndicator color={palette.primary} style={{ marginVertical: 30 }} />
            : (
              <Card>
                <View style={{ alignItems: "center", padding: 20, gap: 6 }}>
                  <Landmark color={palette.textMuted} size={36} />
                  <Text style={{ color: palette.textPrimary, fontWeight: "700", marginTop: 4 }}>No bank accounts</Text>
                  <Text style={{ color: palette.textSecondary, fontSize: 13, textAlign: "center" }}>Add your first bank to start withdrawing.</Text>
                </View>
              </Card>
            )
        }
      />

      <Pressable
        onPress={() => router.push("/withdrawals/add-bank")}
        style={({ pressed }) => [s.fab, { backgroundColor: palette.primary, opacity: pressed ? 0.85 : 1 }]}
        testID="btn-add-bank"
      >
        <Plus color="#fff" size={20} />
        <Text style={s.fabTxt}>Add Bank Account</Text>
      </Pressable>
    </Screen>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { fontSize: 20, fontWeight: "800", letterSpacing: -0.4 },
  row: { flexDirection: "row", gap: 12, alignItems: "center" },
  iconWrap: { padding: 10, borderRadius: 12 },
  name: { fontSize: 14, fontWeight: "800" },
  meta: { fontSize: 11, fontWeight: "600" },
  verifiedBadge: { marginTop: 4, flexDirection: "row", gap: 4, alignItems: "center" },
  delBtn: { padding: 8, borderRadius: 8 },
  fab: { position: "absolute", bottom: 24, left: 16, right: 16, borderRadius: 16, paddingVertical: 15, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, shadowOpacity: 0.25, shadowRadius: 10, shadowOffset: { width: 0, height: 6 }, elevation: 6 },
  fabTxt: { color: "#fff", fontSize: 15, fontWeight: "800" },
});

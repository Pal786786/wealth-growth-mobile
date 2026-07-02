import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, RefreshControl, ActivityIndicator, TextInput, Alert } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter, useFocusEffect } from "expo-router";
import {
  ChevronLeft, Bell, Wallet, ArrowUpFromLine, ShieldCheck, Bot, TrendingUp, Coins,
  Gift, AlertTriangle, Info, Megaphone, Search, Settings2, Check, Trash2, Filter,
} from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { notifApi, type NotifItem } from "@/src/api/notifications";
import { shortDate } from "@/src/utils/format";

const ICONS: Record<string, any> = {
  wallet: Wallet, withdrawals: ArrowUpFromLine, kyc: ShieldCheck, ai: Bot,
  investments: TrendingUp, gold: Coins, sip: TrendingUp, promotions: Gift,
  security: AlertTriangle, announcements: Megaphone, system: Info,
};
const TINTS: Record<string, string> = {
  wallet: "#0EA5E9", withdrawals: "#F59E0B", kyc: "#10B981", ai: "#8B5CF6",
  investments: "#6366F1", gold: "#F59E0B", sip: "#6366F1", promotions: "#EC4899",
  security: "#EF4444", announcements: "#0EA5E9", system: "#64748B",
};

export default function NotificationsIndex() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [items, setItems] = useState<NotifItem[]>([]);
  const [total, setTotal] = useState(0);
  const [unread, setUnread] = useState(0);
  const [perCat, setPerCat] = useState<Record<string, { total: number; unread: number }>>({});
  const [cats, setCats] = useState<{ key: string; label: string }[]>([]);
  const [category, setCategory] = useState<string>("all");
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await notifApi.list({ limit: 100, category: category === "all" ? undefined : category, unread_only: unreadOnly, q: q || undefined });
      setItems(d.items); setTotal(d.total); setUnread(d.unread); setPerCat(d.per_category); setCats(d.categories);
    } catch (e: any) { show("error", e?.response?.data?.detail || "Failed to load"); }
    finally { setLoading(false); setRefreshing(false); }
  }, [category, unreadOnly, q, show]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  const openNotif = async (n: NotifItem) => {
    if (!n.read) {
      try { await notifApi.markOne(n.notif_id); setUnread((u) => Math.max(0, u - 1)); }
      catch { /* ignore */ }
      setItems((xs) => xs.map((x) => x.notif_id === n.notif_id ? { ...x, read: true } : x));
    }
    if (n.deeplink && n.deeplink !== "/") { try { router.push(n.deeplink as any); } catch { /* invalid route */ } }
  };

  const del = (nid: string) => Alert.alert("Delete notification?", undefined, [
    { text: "Cancel", style: "cancel" },
    { text: "Delete", style: "destructive", onPress: async () => {
      try { await notifApi.delete(nid); setItems((xs) => xs.filter((x) => x.notif_id !== nid)); }
      catch { show("error", "Failed to delete"); }
    } },
  ]);

  const markAll = async () => {
    if (unread === 0) return;
    try { await notifApi.markAll(); show("success", "All marked as read"); load(); }
    catch { show("error", "Failed"); }
  };

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <View style={{ flex: 1 }}>
          <Text style={[s.title, { color: palette.textPrimary }]}>Notifications</Text>
          <Text style={{ color: palette.textMuted, fontSize: 11 }}>{unread} unread · {total} total</Text>
        </View>
        <Pressable onPress={() => router.push("/notifications/preferences")} hitSlop={12} style={[s.iconBtn, { backgroundColor: palette.chipBg }]}>
          <Settings2 color={palette.primary} size={18} />
        </Pressable>
      </View>

      <View style={{ paddingHorizontal: 16, paddingVertical: 10, gap: 10 }}>
        <View style={[s.searchWrap, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Search color={palette.textMuted} size={16} />
          <TextInput
            value={q} onChangeText={setQ}
            placeholder="Search notifications…"
            placeholderTextColor={palette.textMuted}
            style={[s.searchInput, { color: palette.textPrimary }]}
            returnKeyType="search"
            onSubmitEditing={load}
          />
        </View>
        <View style={{ flexDirection: "row", gap: 8 }}>
          <Pressable onPress={() => setUnreadOnly(!unreadOnly)}
            style={[s.filterBtn, { borderColor: unreadOnly ? palette.primary : palette.border, backgroundColor: unreadOnly ? palette.primary + "18" : palette.surface }]}>
            <Filter color={unreadOnly ? palette.primary : palette.textSecondary} size={14} />
            <Text style={{ color: unreadOnly ? palette.primary : palette.textSecondary, fontSize: 12, fontWeight: "800" }}>Unread only</Text>
          </Pressable>
          <Pressable onPress={markAll} disabled={unread === 0}
            style={[s.filterBtn, { borderColor: palette.border, backgroundColor: palette.surface, opacity: unread === 0 ? 0.5 : 1 }]}>
            <Check color={palette.success} size={14} />
            <Text style={{ color: palette.success, fontSize: 12, fontWeight: "800" }}>Mark all read</Text>
          </Pressable>
        </View>

        <FlatList
          data={[{ key: "all", label: "All" }, ...cats]}
          horizontal
          showsHorizontalScrollIndicator={false}
          keyExtractor={(x) => x.key}
          contentContainerStyle={{ gap: 6, paddingVertical: 4 }}
          renderItem={({ item }) => {
            const active = category === item.key;
            const cnt = item.key === "all" ? total : (perCat[item.key]?.total || 0);
            const un = item.key === "all" ? unread : (perCat[item.key]?.unread || 0);
            return (
              <Pressable onPress={() => setCategory(item.key)} style={[s.chip, { borderColor: active ? palette.primary : palette.border, backgroundColor: active ? palette.primary + "18" : palette.surface }]}>
                <Text style={{ color: active ? palette.primary : palette.textSecondary, fontSize: 12, fontWeight: "800" }}>{item.label}</Text>
                {cnt > 0 && (
                  <View style={[s.badge, { backgroundColor: un > 0 ? palette.primary : palette.textMuted }]}>
                    <Text style={s.badgeTxt}>{un > 0 ? un : cnt}</Text>
                  </View>
                )}
              </Pressable>
            );
          }}
        />
      </View>

      <FlatList
        data={items}
        keyExtractor={(x) => x.notif_id}
        contentContainerStyle={{ padding: 16, gap: 8, paddingBottom: 100 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
        renderItem={({ item }) => {
          const Icon = ICONS[item.category] || Bell;
          const tint = TINTS[item.category] || palette.primary;
          return (
            <Pressable onLongPress={() => del(item.notif_id)} onPress={() => openNotif(item)}>
              <View style={[s.card, { backgroundColor: item.read ? palette.surface : palette.primary + "08", borderColor: item.read ? palette.border : palette.primary + "55", borderWidth: 1 }]}>
                <View style={[s.cardIcon, { backgroundColor: tint + "22" }]}>
                  <Icon color={tint} size={18} />
                </View>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" }}>
                    <Text style={[s.cardTitle, { color: palette.textPrimary, fontWeight: item.read ? "600" : "900" }]} numberOfLines={1}>{item.title}</Text>
                    {!item.read && <View style={[s.dot, { backgroundColor: palette.primary }]} />}
                  </View>
                  <Text style={[s.cardBody, { color: palette.textSecondary }]} numberOfLines={2}>{item.body}</Text>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: 4 }}>
                    <Text style={[s.cardMeta, { color: tint }]}>{item.category.toUpperCase()}</Text>
                    <Text style={[s.cardMeta, { color: palette.textMuted }]}>{shortDate(item.created_at)}</Text>
                  </View>
                  {item.priority === "critical" && (
                    <View style={[s.critical, { backgroundColor: palette.danger + "22", borderColor: palette.danger + "55" }]}>
                      <AlertTriangle color={palette.danger} size={11} />
                      <Text style={{ color: palette.danger, fontSize: 10, fontWeight: "800" }}>CRITICAL</Text>
                    </View>
                  )}
                </View>
              </View>
            </Pressable>
          );
        }}
        ListEmptyComponent={
          loading ? <ActivityIndicator color={palette.primary} style={{ marginTop: 30 }} /> :
            <View style={{ alignItems: "center", padding: 40, gap: 6 }}>
              <Bell color={palette.textMuted} size={40} />
              <Text style={{ color: palette.textPrimary, fontWeight: "800", marginTop: 4 }}>Nothing here yet</Text>
              <Text style={{ color: palette.textSecondary, fontSize: 12, textAlign: "center" }}>You're all caught up. New alerts appear here.</Text>
            </View>
        }
      />
    </Screen>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { fontSize: 20, fontWeight: "800", letterSpacing: -0.4 },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  searchWrap: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, borderRadius: 12, borderWidth: 1, height: 40 },
  searchInput: { flex: 1, fontSize: 14 },
  filterBtn: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  chip: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  badge: { minWidth: 18, paddingHorizontal: 5, height: 16, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  badgeTxt: { color: "#fff", fontSize: 9, fontWeight: "900" },
  card: { flexDirection: "row", gap: 10, padding: 12, borderRadius: 14 },
  cardIcon: { padding: 8, borderRadius: 10 },
  cardTitle: { fontSize: 14 },
  cardBody: { fontSize: 12, marginTop: 2, lineHeight: 16 },
  cardMeta: { fontSize: 10, fontWeight: "800" },
  dot: { width: 8, height: 8, borderRadius: 4 },
  critical: { marginTop: 6, alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, borderWidth: 1 },
});

import React, { useCallback, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, RefreshControl } from "react-native";
import { useRouter, useFocusEffect } from "expo-router";
import { ChevronLeft, Bell, BellOff, CheckCheck } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { api } from "@/src/api/client";
import { shortDate } from "@/src/utils/format";

export default function Notifications() {
  const { palette } = useTheme();
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [unread, setUnread] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/notifications");
      setItems(data.items); setUnread(data.unread);
    } catch {} finally { setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const markRead = async () => {
    await api.post("/notifications/mark-read");
    load();
  };

  return (
    <Screen>
      <View style={s.hdr}>
        <Pressable onPress={() => router.back()} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <View style={{ flex: 1 }}>
          <Text style={[s.title, { color: palette.textPrimary }]}>Notifications</Text>
          <Text style={[s.sub, { color: palette.textSecondary }]}>{unread} unread · {items.length} total</Text>
        </View>
        {unread > 0 ? (
          <Pressable onPress={markRead} style={[s.markBtn, { backgroundColor: palette.primary + "1A" }]} testID="mark-read-btn">
            <CheckCheck color={palette.primary} size={16} />
            <Text style={{ color: palette.primary, fontWeight: "700", fontSize: 12 }}>Mark all read</Text>
          </Pressable>
        ) : null}
      </View>
      <ScrollView
        contentContainerStyle={{ gap: 10, paddingBottom: 32 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
      >
        {items.length === 0 ? (
          <Card style={{ alignItems: "center", paddingVertical: 30, gap: 8 }}>
            <BellOff color={palette.textMuted} size={36} />
            <Text style={{ color: palette.textSecondary, fontWeight: "700" }}>No notifications yet</Text>
            <Text style={{ color: palette.textMuted, fontSize: 12, textAlign: "center" }}>You're all caught up. We'll let you know when there's something new.</Text>
          </Card>
        ) : items.map((n) => (
          <Card key={n.notif_id} style={[s.row, !n.read && { borderColor: palette.primary + "60", backgroundColor: palette.primary + "08" }]} testID={`notif-${n.notif_id}`}>
            <View style={[s.icon, { backgroundColor: palette.primary + "1A" }]}>
              <Bell color={palette.primary} size={20} />
              {!n.read ? <View style={[s.unreadDot, { backgroundColor: palette.danger }]} /> : null}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.heading, { color: palette.textPrimary }]}>{n.title}</Text>
              <Text style={[s.body, { color: palette.textSecondary }]}>{n.body}</Text>
              <Text style={[s.time, { color: palette.textMuted }]}>{shortDate(n.created_at)}</Text>
            </View>
          </Card>
        ))}
      </ScrollView>
    </Screen>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 8 },
  title: { fontSize: 22, fontWeight: "800", letterSpacing: -0.5 },
  sub: { fontSize: 12, fontWeight: "600", marginTop: 2 },
  markBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 12 },
  row: { flexDirection: "row", alignItems: "flex-start", gap: 12 },
  icon: { padding: 10, borderRadius: 12, position: "relative" },
  unreadDot: { position: "absolute", top: 6, right: 6, width: 8, height: 8, borderRadius: 4, borderWidth: 1.5, borderColor: "#fff" },
  heading: { fontSize: 14, fontWeight: "700" },
  body: { fontSize: 12, marginTop: 2 },
  time: { fontSize: 11, marginTop: 4 },
});

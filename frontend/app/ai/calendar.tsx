/**
 * Economic Calendar — Sprint 7C.2
 * High-impact macro events with live countdown & impact filters.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { ArrowLeft, CalendarClock, Flag, Zap } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { aiNewsApi, EconomicEvent, Impact, formatCountdown, impactColor } from "@/src/api/aiNews";
import { errText } from "@/src/utils/errors";

const IMPACTS: Array<{ id: Impact | "all"; label: string }> = [
  { id: "all", label: "All" },
  { id: "high", label: "High" },
  { id: "medium", label: "Medium" },
  { id: "low", label: "Low" },
];

const COUNTRIES = ["ALL", "US", "EU", "UK", "JP", "IN", "CA", "AU", "CN"];

function groupByDay(events: EconomicEvent[]) {
  const groups: Record<string, EconomicEvent[]> = {};
  for (const e of events) {
    const d = new Date(e.event_time);
    const key = d.toDateString();
    (groups[key] = groups[key] || []).push(e);
  }
  return Object.entries(groups);
}

export default function EconomicCalendar() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [impact, setImpact] = useState<Impact | "all">("all");
  const [country, setCountry] = useState<string>("ALL");
  const [events, setEvents] = useState<EconomicEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [tick, setTick] = useState(0);

  const load = useCallback(async () => {
    try {
      const r = await aiNewsApi.calendar({
        impact: impact === "all" ? undefined : impact,
        country: country === "ALL" ? undefined : country,
        days_ahead: 60, limit: 150,
      });
      setEvents(r.events);
    } catch (e) { show("error", errText(e, "Failed to load calendar")); }
    finally { setLoading(false); setRefreshing(false); }
  }, [impact, country, show]);

  useEffect(() => { load(); }, [load]);
  // Refresh countdown labels each 30s (data unchanged, just re-render)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30000);
    return () => clearInterval(id);
  }, []);

  const grouped = useMemo(() => groupByDay(events), [events, tick]);

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <CalendarClock size={18} color={palette.primary} />
            <Text style={[s.title, { color: palette.textPrimary }]}>Economic Calendar</Text>
          </View>
          <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 2 }}>
            Fed · ECB · RBI · CPI · NFP — next 60 days
          </Text>
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ maxHeight: 44 }} contentContainerStyle={{ paddingHorizontal: 12, paddingVertical: 8, gap: 6 }}>
        {IMPACTS.map((c) => (
          <Pressable key={c.id} onPress={() => setImpact(c.id)} style={[s.pill, { backgroundColor: impact === c.id ? (c.id === "high" ? palette.danger : palette.primary) : palette.surface, borderColor: impact === c.id ? (c.id === "high" ? palette.danger : palette.primary) : palette.border }]}>
            {c.id === "high" && <Zap size={12} color={impact === c.id ? "#fff" : palette.danger} />}
            <Text style={{ color: impact === c.id ? "#fff" : palette.textPrimary, fontSize: 12, fontWeight: "700", marginLeft: c.id === "high" ? 3 : 0 }}>{c.label}</Text>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ maxHeight: 40 }} contentContainerStyle={{ paddingHorizontal: 12, paddingBottom: 8, gap: 6 }}>
        {COUNTRIES.map((c) => (
          <Pressable key={c} onPress={() => setCountry(c)} style={[s.pillSm, { backgroundColor: country === c ? palette.textPrimary : palette.surface, borderColor: country === c ? palette.textPrimary : palette.border }]}>
            <Text style={{ color: country === c ? palette.background : palette.textPrimary, fontSize: 11, fontWeight: "700" }}>{c}</Text>
          </Pressable>
        ))}
      </ScrollView>

      {loading ? (
        <View style={{ padding: 40, alignItems: "center" }}><ActivityIndicator color={palette.primary} /></View>
      ) : (
        <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />} contentContainerStyle={{ padding: 12, paddingBottom: 40 }}>
          {events.length === 0 && (
            <View style={{ padding: 40, alignItems: "center" }}><Text style={{ color: palette.textMuted }}>No events match your filter.</Text></View>
          )}
          {grouped.map(([day, dayEvents]) => (
            <View key={day} style={{ marginBottom: 14 }}>
              <Text style={{ color: palette.textMuted, fontSize: 11, fontWeight: "700", marginBottom: 6, letterSpacing: 0.5, textTransform: "uppercase" }}>{day}</Text>
              {dayEvents.map((e) => (
                <View key={e.event_id} style={[s.card, { backgroundColor: palette.surface, borderColor: palette.border, borderLeftColor: impactColor(e.impact, palette), borderLeftWidth: 3 }]}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <Flag size={12} color={palette.textMuted} />
                    <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800" }}>{e.country}</Text>
                    <Text style={{ color: palette.textMuted, fontSize: 10 }}>· {e.currency}</Text>
                    <View style={{ flex: 1 }} />
                    <Text style={[s.chip, { color: impactColor(e.impact, palette), backgroundColor: impactColor(e.impact, palette) + "18" }]}>{e.impact.toUpperCase()}</Text>
                  </View>
                  <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "800" }}>{e.title}</Text>
                  {e.description ? (
                    <Text numberOfLines={2} style={{ color: palette.textMuted, fontSize: 11, marginTop: 4, lineHeight: 15 }}>{e.description}</Text>
                  ) : null}
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 10, marginTop: 8 }}>
                    <Text style={{ color: palette.textPrimary, fontSize: 12, fontWeight: "800" }}>
                      {new Date(e.event_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </Text>
                    <Text style={{ color: (e.countdown_sec ?? 0) < 3600 && (e.countdown_sec ?? 0) > 0 ? palette.danger : palette.textMuted, fontSize: 11, fontWeight: "700" }}>
                      ⏱ {formatCountdown(e.countdown_sec)}
                    </Text>
                    {(e.actual || e.forecast || e.previous) ? (
                      <View style={{ flexDirection: "row", gap: 8 }}>
                        {e.actual && <Text style={{ color: palette.success, fontSize: 10 }}>Actual: {e.actual}</Text>}
                        {e.forecast && <Text style={{ color: palette.textMuted, fontSize: 10 }}>Fcst: {e.forecast}</Text>}
                        {e.previous && <Text style={{ color: palette.textMuted, fontSize: 10 }}>Prev: {e.previous}</Text>}
                      </View>
                    ) : null}
                  </View>
                </View>
              ))}
            </View>
          ))}
        </ScrollView>
      )}
    </Screen>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { fontSize: 20, fontWeight: "800" },
  pill: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, height: 30, borderRadius: 15, borderWidth: 1 },
  pillSm: { paddingHorizontal: 10, height: 26, borderRadius: 13, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  card: { padding: 12, borderRadius: 10, borderWidth: 1, marginBottom: 8 },
  chip: { fontSize: 9, fontWeight: "900", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 5, letterSpacing: 0.3 },
});

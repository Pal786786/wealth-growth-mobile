import React, { useCallback, useMemo, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ScrollView, ActivityIndicator, RefreshControl, TextInput } from "react-native";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter, useFocusEffect } from "expo-router";
import { ChevronLeft, TrendingUp, TrendingDown, Search, Star, Plus, Newspaper, CalendarClock, ArrowUpRight, X } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { marketApi, type Quote } from "@/src/api/market";

export default function MarketIndex() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [tab, setTab] = useState<"dash" | "watch" | "news" | "cal">("dash");
  const [items, setItems] = useState<Quote[]>([]);
  const [watch, setWatch] = useState<Quote[]>([]);
  const [news, setNews] = useState<any[]>([]);
  const [newsCat, setNewsCat] = useState("all");
  const [cal, setCal] = useState<any[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [searchQ, setSearchQ] = useState("");
  const [searchRes, setSearchRes] = useState<any[]>([]);

  const load = useCallback(async () => {
    try {
      const [d, w, n, c] = await Promise.all([
        marketApi.dashboard(), marketApi.watchlist().catch(() => ({ items: [], pinned: [] })),
        marketApi.news(newsCat), marketApi.calendar()
      ]);
      setItems(d.items); setWatch(w.items); setNews(n.items); setCal(c);
    } catch (e: any) { show("error", e?.response?.data?.detail || "Market feed unavailable"); }
    finally { setLoading(false); setRefreshing(false); }
  }, [newsCat, show]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const doSearch = async (q: string) => {
    setSearchQ(q);
    if (q.trim().length < 1) { setSearchRes([]); return; }
    try { setSearchRes(await marketApi.search(q)); } catch { setSearchRes([]); }
  };

  const addToWatch = async (sym: string) => {
    try { await marketApi.addWatch(sym); show("success", `${sym} added to watchlist`); setSearchQ(""); setSearchRes([]); load(); }
    catch (e: any) { show("error", e?.response?.data?.detail || "Failed"); }
  };
  const removeWatch = async (sym: string) => { await marketApi.removeWatch(sym); load(); };
  const pinWatch = async (sym: string, pinned: boolean) => { await marketApi.pinWatch(sym, pinned); load(); };

  const cats = ["all", "markets", "economy", "gold", "forex", "crypto"];

  return (
    <Screen padded={false}>
      <View style={[s.hdr, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>Markets</Text>
      </View>

      <View style={{ flexDirection: "row", paddingHorizontal: 16, paddingVertical: 10, gap: 6 }}>
        {[
          { k: "dash", label: "Dashboard", icon: TrendingUp },
          { k: "watch", label: "Watchlist", icon: Star },
          { k: "news", label: "News", icon: Newspaper },
          { k: "cal", label: "Calendar", icon: CalendarClock },
        ].map((t) => {
          const active = tab === t.k;
          return (
            <Pressable key={t.k} onPress={() => setTab(t.k as any)} style={[s.tabBtn, { borderColor: active ? palette.primary : palette.border, backgroundColor: active ? palette.primary + "18" : palette.surface }]}>
              <t.icon color={active ? palette.primary : palette.textSecondary} size={14} />
              <Text style={{ color: active ? palette.primary : palette.textSecondary, fontSize: 11, fontWeight: "800" }}>{t.label}</Text>
            </Pressable>
          );
        })}
      </View>

      {loading ? <ActivityIndicator color={palette.primary} style={{ marginTop: 40 }} /> : (
        <ScrollView contentContainerStyle={{ padding: 16, gap: 10, paddingBottom: 80 }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}>

          {tab === "dash" && items.map((q) => <QuoteCard key={q.symbol} q={q} palette={palette} onPress={() => router.push({ pathname: "/market/[symbol]", params: { symbol: q.symbol } })} />)}

          {tab === "watch" && (
            <>
              <View style={[s.searchWrap, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                <Search color={palette.textMuted} size={16} />
                <TextInput value={searchQ} onChangeText={doSearch} placeholder="Search instruments (e.g. GOLD, BTC)" placeholderTextColor={palette.textMuted} style={[s.searchInput, { color: palette.textPrimary }]} autoCapitalize="characters" />
                {searchQ.length > 0 && <Pressable onPress={() => { setSearchQ(""); setSearchRes([]); }} hitSlop={8}><X color={palette.textMuted} size={16} /></Pressable>}
              </View>
              {searchRes.length > 0 ? searchRes.map((r) => (
                <Pressable key={r.symbol} onPress={() => addToWatch(r.symbol)}>
                  <Card style={s.row}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 14 }}>{r.symbol}</Text>
                      <Text style={{ color: palette.textSecondary, fontSize: 11 }}>{r.name} · {r.category}</Text>
                    </View>
                    <View style={[s.addBtn, { backgroundColor: palette.primary + "22" }]}>
                      <Plus color={palette.primary} size={16} />
                    </View>
                  </Card>
                </Pressable>
              )) : watch.length === 0 ? (
                <Card><View style={{ alignItems: "center", padding: 20, gap: 6 }}><Star color={palette.textMuted} size={36} /><Text style={{ color: palette.textPrimary, fontWeight: "700" }}>No symbols watched</Text><Text style={{ color: palette.textSecondary, fontSize: 12, textAlign: "center" }}>Search above to add instruments.</Text></View></Card>
              ) : watch.map((q) => (
                <QuoteCard key={q.symbol} q={q} palette={palette}
                  onPress={() => router.push({ pathname: "/market/[symbol]", params: { symbol: q.symbol } })}
                  right={<View style={{ flexDirection: "row", gap: 4 }}>
                    <Pressable onPress={() => pinWatch(q.symbol, !q.pinned)} hitSlop={8} style={s.smallBtn}><Star color={q.pinned ? "#F59E0B" : palette.textMuted} size={16} fill={q.pinned ? "#F59E0B" : "none"} /></Pressable>
                    <Pressable onPress={() => removeWatch(q.symbol)} hitSlop={8} style={s.smallBtn}><X color={palette.danger} size={16} /></Pressable>
                  </View>} />
              ))}
            </>
          )}

          {tab === "news" && (
            <>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingBottom: 8 }}>
                {cats.map((c) => (
                  <Pressable key={c} onPress={() => setNewsCat(c)} style={[s.newsChip, { borderColor: newsCat === c ? palette.primary : palette.border, backgroundColor: newsCat === c ? palette.primary + "18" : palette.surface }]}>
                    <Text style={{ color: newsCat === c ? palette.primary : palette.textSecondary, fontSize: 11, fontWeight: "800", textTransform: "capitalize" }}>{c}</Text>
                  </Pressable>
                ))}
              </ScrollView>
              {news.map((n) => (
                <Card key={n.id} style={{ marginBottom: 8 }}>
                  <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 4 }}>
                    <Text style={{ color: palette.primary, fontSize: 10, fontWeight: "800", letterSpacing: 0.5 }}>{n.category.toUpperCase()}</Text>
                    <Text style={{ color: palette.textMuted, fontSize: 10 }}>{new Date(n.published_at).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</Text>
                  </View>
                  <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "800", lineHeight: 20 }}>{n.headline}</Text>
                  <Text style={{ color: palette.textSecondary, fontSize: 12, marginTop: 4, lineHeight: 18 }}>{n.summary}</Text>
                  <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 4 }}>Source · {n.source}</Text>
                </Card>
              ))}
            </>
          )}

          {tab === "cal" && cal.map((e) => (
            <Card key={e.id} style={{ marginBottom: 8 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <View style={{ flex: 1 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <View style={[s.flag, { backgroundColor: e.country === "IN" ? "#F59E0B" : e.country === "US" ? "#0EA5E9" : "#8B5CF6" }]}><Text style={{ color: "#fff", fontSize: 9, fontWeight: "900" }}>{e.country}</Text></View>
                    <Text style={{ color: palette.textPrimary, fontSize: 13, fontWeight: "800", flex: 1 }}>{e.event}</Text>
                  </View>
                  <Text style={{ color: palette.textSecondary, fontSize: 11, marginTop: 4 }}>Forecast: {e.forecast} · Prior: {e.prior}</Text>
                  <Text style={{ color: palette.textMuted, fontSize: 10, marginTop: 2 }}>{new Date(e.when).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</Text>
                </View>
                <View style={[s.impact, { backgroundColor: e.impact === "high" ? "#FEE2E2" : e.impact === "medium" ? "#FEF3C7" : "#DBEAFE" }]}>
                  <Text style={{ color: e.impact === "high" ? "#DC2626" : e.impact === "medium" ? "#D97706" : "#2563EB", fontSize: 9, fontWeight: "900" }}>{e.impact.toUpperCase()}</Text>
                </View>
              </View>
            </Card>
          ))}
        </ScrollView>
      )}
    </Screen>
  );
}

function QuoteCard({ q, palette, onPress, right }: { q: Quote; palette: any; onPress?: () => void; right?: React.ReactNode }) {
  const isUp = q.change_pct >= 0;
  const tint = isUp ? "#10B981" : "#EF4444";
  return (
    <Pressable onPress={onPress}>
      <Card style={{ marginBottom: 8 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
          <View style={[s.qIcon, { backgroundColor: tint + "22" }]}>{isUp ? <TrendingUp color={tint} size={20} /> : <TrendingDown color={tint} size={20} />}</View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 14 }}>{q.name}</Text>
            <Text style={{ color: palette.textMuted, fontSize: 10 }}>{q.symbol} · {q.category} · {q.currency}</Text>
          </View>
          <View style={{ alignItems: "flex-end" }}>
            <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "900" }}>{q.currency === "INR" ? "₹" : "$"}{q.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
            <Text style={{ color: tint, fontSize: 11, fontWeight: "800" }}>{q.change > 0 ? "+" : ""}{q.change} ({q.change_pct > 0 ? "+" : ""}{q.change_pct}%)</Text>
          </View>
          {right}
        </View>
      </Card>
    </Pressable>
  );
}

const s = StyleSheet.create({
  hdr: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 16, paddingVertical: 10, borderBottomWidth: 1 },
  title: { fontSize: 20, fontWeight: "800", letterSpacing: -0.4 },
  tabBtn: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingVertical: 8, borderRadius: 10, borderWidth: 1 },
  qIcon: { padding: 10, borderRadius: 12 },
  searchWrap: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, borderRadius: 12, borderWidth: 1, height: 44, marginBottom: 8 },
  searchInput: { flex: 1, fontSize: 14, fontWeight: "700" },
  row: { flexDirection: "row", alignItems: "center", gap: 12 },
  addBtn: { padding: 8, borderRadius: 10 },
  smallBtn: { padding: 6 },
  newsChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
  flag: { paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4 },
  impact: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
});

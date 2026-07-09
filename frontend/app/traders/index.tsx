/**
 * Copy Trading — Leaderboard (Sprint 7B.1)
 * Filters: sort dropdown pill row + verified toggle + search input.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, TextInput, FlatList, ActivityIndicator, RefreshControl, Image } from "react-native";
import { useRouter } from "expo-router";
import { ArrowLeft, Search, ShieldCheck, TrendingUp, Users, Percent, Sparkles, Award, Filter, Wallet } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { copyApi, Trader, countryFlag } from "@/src/api/copyTrading";
import { errText, safeStr } from "@/src/utils/errors";

const SORTS = [
  { id: "total_roi",   label: "Top ROI",       icon: TrendingUp },
  { id: "monthly_roi", label: "Best Monthly",  icon: Sparkles },
  { id: "win_rate",    label: "Win Rate",      icon: Percent },
  { id: "risk",        label: "Lowest Risk",   icon: ShieldCheck },
  { id: "followers",   label: "Most Followers",icon: Users },
  { id: "new",         label: "New",           icon: Award },
];

export default function TradersLeaderboard() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [sort, setSort] = useState("total_roi");
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [items, setItems] = useState<Trader[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => { const t = setTimeout(() => setDebounced(search.trim()), 250); return () => clearTimeout(t); }, [search]);

  const load = useCallback(async () => {
    try {
      const r = await copyApi.leaderboard({ sort, search: debounced || undefined, verified_only: verifiedOnly, limit: 50 });
      setItems(r.items);
    } catch (e) { show("error", errText(e, "Couldn't load traders")); }
    finally { setLoading(false); setRefreshing(false); }
  }, [sort, debounced, verifiedOnly, show]);
  useEffect(() => { setLoading(true); load(); }, [load]);

  const renderRow = ({ item, index }: { item: Trader; index: number }) => (
    <Pressable
      onPress={() => router.push(`/traders/${item.id}` as any)}
      style={({ pressed }) => [s.row, { backgroundColor: pressed ? palette.surface : palette.background, borderColor: palette.border }]}
    >
      <Text style={[s.rank, { color: palette.textMuted }]}>{index + 1}</Text>
      <Image source={{ uri: item.avatar_url }} style={s.avatar} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          <Text style={[s.name, { color: palette.textPrimary }]} numberOfLines={1}>{safeStr(item.name)}</Text>
          {item.verified && <ShieldCheck size={13} color="#3B82F6" fill="#3B82F6" />}
          <Text style={{ fontSize: 13 }}>{countryFlag(item.country_code)}</Text>
        </View>
        <Text style={[s.sub, { color: palette.textMuted }]} numberOfLines={1}>
          {item.style} · {item.stats.followers.toLocaleString()} followers · Risk {item.risk.risk_score}/10
        </Text>
      </View>
      <View style={{ alignItems: "flex-end" }}>
        <Text style={{ color: item.stats.total_roi_pct >= 0 ? palette.success : palette.danger, fontSize: 15, fontWeight: "900", fontVariant: ["tabular-nums"] }}>
          {item.stats.total_roi_pct >= 0 ? "+" : ""}{item.stats.total_roi_pct.toFixed(1)}%
        </Text>
        <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "700" }}>Total ROI</Text>
      </View>
    </Pressable>
  );

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>Top Traders</Text>
        <Pressable
          onPress={() => router.push("/copies" as any)}
          hitSlop={8}
          style={{ flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: palette.surface, borderWidth: 1, borderColor: palette.border }}
        >
          <Wallet size={13} color={palette.textPrimary} />
          <Text style={{ color: palette.textPrimary, fontSize: 11, fontWeight: "800" }}>My Copies</Text>
        </Pressable>
        <Pressable
          onPress={() => setVerifiedOnly((v) => !v)}
          hitSlop={8}
          style={{ flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: verifiedOnly ? "#3B82F6" : palette.surface, borderWidth: 1, borderColor: verifiedOnly ? "#3B82F6" : palette.border }}
        >
          <ShieldCheck size={13} color={verifiedOnly ? "#fff" : palette.textPrimary} />
          <Text style={{ color: verifiedOnly ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>Verified</Text>
        </Pressable>
      </View>

      <View style={[s.searchWrap, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <Search size={16} color={palette.textMuted} />
        <TextInput
          value={search} onChangeText={setSearch}
          placeholder="Search by name, country or style" placeholderTextColor={palette.textMuted}
          style={[s.searchInput, { color: palette.textPrimary }]}
          autoCorrect={false}
        />
      </View>

      <FlatList
        horizontal data={SORTS} keyExtractor={(x) => x.id}
        contentContainerStyle={{ paddingHorizontal: 12, gap: 6, paddingVertical: 10 }}
        showsHorizontalScrollIndicator={false}
        renderItem={({ item: opt }) => {
          const active = sort === opt.id;
          const Ic = opt.icon;
          return (
            <Pressable
              onPress={() => setSort(opt.id)}
              style={[s.chip, { backgroundColor: active ? palette.primary : palette.surface, borderColor: active ? palette.primary : palette.border }]}
            >
              <Ic size={12} color={active ? "#fff" : palette.textPrimary} />
              <Text style={{ color: active ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{opt.label}</Text>
            </Pressable>
          );
        }}
      />

      <FlatList
        data={items} renderItem={renderRow} keyExtractor={(t) => t.id}
        ItemSeparatorComponent={() => <View style={{ height: 1, backgroundColor: palette.border, opacity: 0.4, marginLeft: 68 }} />}
        contentContainerStyle={{ paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
        ListEmptyComponent={loading ? <View style={{ padding: 40 }}><ActivityIndicator color={palette.primary} /></View> : <View style={{ padding: 40, alignItems: "center" }}><Text style={{ color: palette.textMuted, fontSize: 13 }}>No traders match your filters</Text></View>}
        initialNumToRender={12} windowSize={10}
      />
    </Screen>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { flex: 1, fontSize: 20, fontWeight: "800" },
  searchWrap: { flexDirection: "row", alignItems: "center", gap: 8, marginHorizontal: 12, marginTop: 10, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 12, borderWidth: 1 },
  searchInput: { flex: 1, fontSize: 14, fontWeight: "600" },
  chip: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 7, borderRadius: 999, borderWidth: 1 },
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 12, paddingVertical: 12 },
  rank: { fontSize: 12, fontWeight: "800", width: 24, textAlign: "center" },
  avatar: { width: 44, height: 44, borderRadius: 22, backgroundColor: "#E2E8F0" },
  name: { fontSize: 14, fontWeight: "800" },
  sub: { fontSize: 11, marginTop: 2, fontWeight: "600" },
});

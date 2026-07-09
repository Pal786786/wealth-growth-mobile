/**
 * Market Symbols Browser — Sprint 7 Slice 1
 * -----------------------------------------
 * Full instrument browser:
 *   • Category tabs (auto-generated from /categories — new categories appear
 *     without code changes)
 *   • Search bar (server-side across id/display/name)
 *   • Virtualised list (FlatList windowSize=10)
 *   • Live prices via useMarketStream (WebSocket with polling fallback)
 *   • Favorite star toggle per row
 *   • Pagination — infinite scroll (load more when reaching end)
 *   • Tabs: All / Forex Majors / Minors / Metals / Crypto / etc.
 *   • Tabs bar has a first pinned tab "★ Favorites" and "🕐 Recent"
 *
 * Reachable from /market/symbols. The Sprint 6 dashboard (/market) remains
 * unchanged and links here via a "Browse all markets" CTA.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, TextInput, Pressable, FlatList, ActivityIndicator,
  Platform, RefreshControl,
} from "react-native";
import { useRouter } from "expo-router";
import {
  ArrowLeft, Search, Star, StarOff, TrendingUp, TrendingDown, Wifi, WifiOff,
} from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { marketDataApi, Category, Instrument } from "@/src/api/marketData";
import { useMarketStream } from "@/src/hooks/useMarketStream";
import { errText, safeStr } from "@/src/utils/errors";

const PAGE_LIMIT = 40;

type TabId = "favorites" | "recent" | "all" | string; // category id

export default function MarketSymbolsBrowser() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();

  const [categories, setCategories] = useState<Category[]>([]);
  const [activeTab, setActiveTab] = useState<TabId>("all");
  const [search, setSearch] = useState("");
  const [items, setItems] = useState<Instrument[]>([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [favorites, setFavorites] = useState<Set<string>>(new Set());
  const [debouncedSearch, setDebouncedSearch] = useState("");

  // Debounce the search field so we don't hammer the API
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  // Load categories + favorites on mount. Favorites requires auth — swallow
  // 401 silently rather than surfacing an error toast to unauthenticated
  // visitors who just want to browse the catalog.
  useEffect(() => {
    (async () => {
      try {
        const c = await marketDataApi.categories();
        setCategories(c.categories.filter((x) => x.count > 0));
      } catch (e) { show("error", errText(e, "Couldn't load categories")); }
      try {
        const f = await marketDataApi.favorites();
        setFavorites(new Set(f.symbols));
      } catch (e: any) {
        // 401 = not logged in — expected, don't warn. Any other error is silent too:
        // the star toggle re-attempts and surfaces the real error to the user then.
        if (e?.response?.status && e.response.status !== 401 && e.response.status !== 403) {
          console.warn("[market/symbols] favorites load failed:", errText(e));
        }
      }
    })();
  }, [show]);

  // Reload catalog whenever tab or debounced search changes
  const loadPage = useCallback(async (opts: { reset: boolean }) => {
    const nextPage = opts.reset ? 1 : page + 1;
    if (opts.reset) setLoading(true);
    try {
      let its: Instrument[] = [];
      let more = false;
      if (activeTab === "favorites") {
        const f = await marketDataApi.favorites();
        its = f.items || [];
        more = false;
      } else if (activeTab === "recent") {
        const r = await marketDataApi.recentlyViewed();
        its = r.items || [];
        more = false;
      } else {
        const category = activeTab === "all" ? undefined : activeTab;
        const r = await marketDataApi.catalog({
          category, search: debouncedSearch || undefined,
          page: nextPage, limit: PAGE_LIMIT,
        });
        its = r.items || [];
        more = r.has_more;
      }
      setItems((prev) => opts.reset ? its : [...prev, ...its]);
      setPage(nextPage);
      setHasMore(more);
    } catch (e) {
      show("error", errText(e, "Couldn't load symbols"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [activeTab, debouncedSearch, page, show]);

  useEffect(() => { loadPage({ reset: true }); }, [activeTab, debouncedSearch, loadPage]);

  // Subscribe to live prices for the currently visible list
  const visibleIds = useMemo(() => items.slice(0, 60).map((i) => i.symbol_id), [items]);
  const { quotes, status } = useMarketStream(visibleIds);

  const toggleFavorite = async (symbolId: string) => {
    const isFav = favorites.has(symbolId);
    // Optimistic UI
    setFavorites((prev) => {
      const next = new Set(prev);
      if (isFav) next.delete(symbolId); else next.add(symbolId);
      return next;
    });
    try {
      if (isFav) await marketDataApi.removeFavorite(symbolId);
      else await marketDataApi.addFavorite(symbolId);
    } catch (e) {
      // rollback
      setFavorites((prev) => {
        const next = new Set(prev);
        if (isFav) next.add(symbolId); else next.delete(symbolId);
        return next;
      });
      show("error", errText(e, "Couldn't update favorite"));
    }
  };

  const openSymbol = (inst: Instrument) => {
    // Log recently-viewed silently — non-blocking
    marketDataApi.logView(inst.symbol_id).catch(() => {});
    // For forex-tradable symbols, open the trading detail. Otherwise open a
    // read-only detail screen (added in future slices).
    if (["forex_majors", "forex_minors", "forex_exotics", "metals", "crypto"].includes(inst.category)
        && ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"].includes(inst.symbol_id)) {
      router.push(`/forex/symbol/${inst.symbol_id}`);
    } else {
      // Fallback: still route to forex/symbol which will show a "not tradeable
      // yet" state OR to the market/[symbol] dashboard tile.
      router.push(`/market/${inst.symbol_id}`);
    }
  };

  const renderRow = ({ item }: { item: Instrument }) => {
    const q = quotes[item.symbol_id];
    const change = q?.change_pct ?? 0;
    const isFav = favorites.has(item.symbol_id);
    const priceText = q ? q.mid.toFixed(item.price_dp) : "—";
    return (
      <Pressable
        onPress={() => openSymbol(item)}
        style={({ pressed }) => [s.row, {
          backgroundColor: pressed ? palette.surface : palette.background,
          borderBottomColor: palette.border,
        }]}
      >
        <View style={s.rowLeft}>
          <View style={[s.badge, { backgroundColor: catColor(item.category) + "22" }]}>
            <Text style={[s.badgeText, { color: catColor(item.category) }]}>{item.symbol_id.slice(0, 3)}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text numberOfLines={1} style={[s.rowDisplay, { color: palette.textPrimary }]}>{safeStr(item.display)}</Text>
            <Text numberOfLines={1} style={[s.rowName, { color: palette.textMuted }]}>{safeStr(item.name)}</Text>
          </View>
        </View>
        <View style={s.rowRight}>
          <Text style={[s.rowPrice, { color: palette.textPrimary, fontVariant: ["tabular-nums"] }]}>{priceText}</Text>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 4, marginTop: 2 }}>
            {change !== 0 && (change > 0
              ? <TrendingUp size={11} color={palette.success} />
              : <TrendingDown size={11} color={palette.danger} />)}
            <Text style={{ color: change >= 0 ? palette.success : palette.danger, fontSize: 11, fontWeight: "700" }}>
              {change === 0 ? "—" : `${change > 0 ? "+" : ""}${change.toFixed(2)}%`}
            </Text>
          </View>
        </View>
        <Pressable
          onPress={() => toggleFavorite(item.symbol_id)}
          hitSlop={10}
          style={{ marginLeft: 8, padding: 6 }}
        >
          {isFav
            ? <Star size={20} color={palette.warning} fill={palette.warning} />
            : <StarOff size={20} color={palette.textMuted} />}
        </Pressable>
      </Pressable>
    );
  };

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border, backgroundColor: palette.background }]}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={{ padding: 4 }}>
          <ArrowLeft size={22} color={palette.textPrimary} />
        </Pressable>
        <Text style={[s.title, { color: palette.textPrimary }]}>Markets</Text>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          {status === "ws" ? <Wifi size={13} color={palette.success} />
            : status === "polling" ? <Wifi size={13} color={palette.warning} />
            : status === "connecting" ? <ActivityIndicator size="small" color={palette.textMuted} />
            : <WifiOff size={13} color={palette.textMuted} />}
          <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "700" }}>
            {status === "ws" ? "LIVE" : status === "polling" ? "POLL" : status.toUpperCase()}
          </Text>
        </View>
      </View>

      {/* Search bar */}
      <View style={[s.searchWrap, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <Search size={16} color={palette.textMuted} />
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Search symbols (e.g. EUR, XAU, BTC)"
          placeholderTextColor={palette.textMuted}
          style={[s.searchInput, { color: palette.textPrimary }]}
          autoCorrect={false}
          autoCapitalize="characters"
        />
      </View>

      {/* Tabs */}
      <View style={{ borderBottomColor: palette.border, borderBottomWidth: StyleSheet.hairlineWidth }}>
        <FlatList
          horizontal
          data={[
            { id: "favorites", label: "★ Favorites", count: favorites.size },
            { id: "recent",    label: "Recent",     count: 0 },
            { id: "all",       label: "All",        count: 0 },
            ...categories.map((c) => ({ id: c.id, label: c.label, count: c.count })),
          ]}
          keyExtractor={(t) => t.id}
          contentContainerStyle={{ paddingHorizontal: 10, paddingVertical: 8, gap: 6 }}
          showsHorizontalScrollIndicator={false}
          renderItem={({ item: tab }) => {
            const active = activeTab === tab.id;
            return (
              <Pressable
                onPress={() => setActiveTab(tab.id as TabId)}
                style={[s.tab, {
                  backgroundColor: active ? palette.primary : palette.surface,
                  borderColor: active ? palette.primary : palette.border,
                }]}
              >
                <Text style={{ color: active ? "#fff" : palette.textPrimary, fontWeight: "700", fontSize: 12 }}>
                  {tab.label}{tab.count ? `  ${tab.count}` : ""}
                </Text>
              </Pressable>
            );
          }}
        />
      </View>

      {/* List */}
      <FlatList
        data={items}
        keyExtractor={(x) => x.symbol_id}
        renderItem={renderRow}
        contentContainerStyle={{ paddingBottom: 40 }}
        ListEmptyComponent={
          loading
            ? <View style={{ padding: 40 }}><ActivityIndicator color={palette.primary} /></View>
            : <View style={{ padding: 40, alignItems: "center" }}>
                <Text style={{ color: palette.textMuted, fontSize: 13, fontWeight: "600" }}>
                  {activeTab === "favorites" ? "No favorites yet — tap ★ to add" :
                   activeTab === "recent" ? "Nothing viewed yet" :
                   debouncedSearch ? `No matches for "${debouncedSearch}"` :
                   "No symbols"}
                </Text>
              </View>
        }
        ListFooterComponent={hasMore ? (
          <View style={{ padding: 18 }}>
            <ActivityIndicator color={palette.textMuted} />
          </View>
        ) : null}
        onEndReached={() => { if (hasMore && !loading) loadPage({ reset: false }); }}
        onEndReachedThreshold={0.4}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={palette.primary} onRefresh={() => { setRefreshing(true); loadPage({ reset: true }); }} />}
        removeClippedSubviews={Platform.OS !== "web"}
        windowSize={10}
        initialNumToRender={12}
      />
    </Screen>
  );
}

function catColor(cat: string): string {
  switch (cat) {
    case "forex_majors":
    case "forex_minors":
    case "forex_exotics": return "#0EA5E9";
    case "metals":        return "#F59E0B";
    case "energies":      return "#EF4444";
    case "indices":       return "#8B5CF6";
    case "crypto":        return "#F97316";
    case "commodities":   return "#10B981";
    default:              return "#6366F1";
  }
}

const s = StyleSheet.create({
  header: {
    flexDirection: "row", alignItems: "center", gap: 12,
    paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  title: { flex: 1, fontSize: 20, fontWeight: "800", letterSpacing: 0.2 },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: 8,
    marginHorizontal: 12, marginTop: 10,
    paddingHorizontal: 12, paddingVertical: Platform.OS === "ios" ? 10 : 6,
    borderRadius: 12, borderWidth: 1,
  },
  searchInput: { flex: 1, fontSize: 14, fontWeight: "600" },
  tab: {
    paddingHorizontal: 12, paddingVertical: 8,
    borderRadius: 999, borderWidth: 1,
  },
  row: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: 14, paddingVertical: 12, gap: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  rowLeft: { flex: 1, flexDirection: "row", alignItems: "center", gap: 12, minWidth: 0 },
  badge: {
    width: 36, height: 36, borderRadius: 10,
    alignItems: "center", justifyContent: "center",
  },
  badgeText: { fontSize: 10, fontWeight: "900", letterSpacing: 0.4 },
  rowDisplay: { fontSize: 14, fontWeight: "800" },
  rowName: { fontSize: 11, fontWeight: "500", marginTop: 1 },
  rowRight: { alignItems: "flex-end", minWidth: 80 },
  rowPrice: { fontSize: 14, fontWeight: "800" },
});

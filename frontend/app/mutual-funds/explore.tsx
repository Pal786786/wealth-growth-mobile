/**
 * Fund Explorer — search, filters (AMC / category / risk / rating), sort, infinite list.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, TextInput, FlatList, Pressable, ActivityIndicator, Modal,
} from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Search, X, SlidersHorizontal, Star } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { mfApi, MFFund, CATEGORIES, RISK_META } from "@/src/api/mutualFunds";

type SortKey = "aum_desc" | "return_1y_desc" | "return_3y_desc" | "return_5y_desc" | "expense_asc" | "rating_desc" | "name_asc";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "aum_desc", label: "AUM" },
  { key: "return_1y_desc", label: "1Y Return" },
  { key: "return_3y_desc", label: "3Y Return" },
  { key: "return_5y_desc", label: "5Y Return" },
  { key: "expense_asc", label: "Low Expense" },
  { key: "rating_desc", label: "Rating" },
  { key: "name_asc", label: "A-Z" },
];

export default function Explore() {
  const { palette } = useTheme();
  const router = useRouter();
  const params = useLocalSearchParams<{ category?: string; sort?: string }>();
  const [q, setQ] = useState("");
  const [items, setItems] = useState<MFFund[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const [category, setCategory] = useState<string | undefined>(params.category);
  const [risk, setRisk] = useState<string | undefined>();
  const [minRating, setMinRating] = useState<number | undefined>();
  const [sort, setSort] = useState<SortKey>((params.sort as SortKey) || "aum_desc");
  const [amc, setAmc] = useState<string | undefined>();
  const [amcs, setAmcs] = useState<string[]>([]);

  const PAGE = 25;

  const load = useCallback(async (reset = false) => {
    const skip = reset ? 0 : items.length;
    try {
      const r = await mfApi.funds({
        q: q || undefined, category, risk, min_rating: minRating,
        amc, sort, limit: PAGE, skip,
      });
      setTotal(r.total);
      setItems((prev) => (reset ? r.items : [...prev, ...r.items]));
    } catch {}
    finally { setLoading(false); setLoadingMore(false); }
  }, [q, category, risk, minRating, amc, sort, items.length]);

  useEffect(() => { setLoading(true); load(true); }, [q, category, risk, minRating, amc, sort]);

  useEffect(() => {
    mfApi.amcs().then((r) => setAmcs(r.items)).catch(() => {});
  }, []);

  const activeFilters = useMemo(() => {
    const chips: string[] = [];
    if (category) chips.push(CATEGORIES.find((c) => c.key === category)?.label ?? category);
    if (risk) chips.push(RISK_META[risk]?.label ?? risk);
    if (minRating) chips.push(`≥${minRating}★`);
    if (amc) chips.push(amc);
    return chips;
  }, [category, risk, minRating, amc]);

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      <View style={{ padding: 16, paddingBottom: 8, gap: 10 }}>
        <View style={[s.searchWrap, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Search color={palette.textMuted} size={16} />
          <TextInput
            value={q}
            onChangeText={setQ}
            placeholder="Search fund or AMC…"
            placeholderTextColor={palette.textMuted}
            style={{ flex: 1, color: palette.textPrimary, paddingVertical: 8 }}
            returnKeyType="search"
            testID="mf-search-input"
          />
          {q ? (
            <Pressable onPress={() => setQ("")} testID="mf-clear-search">
              <X color={palette.textMuted} size={16} />
            </Pressable>
          ) : null}
          <Pressable onPress={() => setShowFilters(true)} style={[s.filterBtn, { backgroundColor: palette.primary + "1A" }]} testID="mf-filter-btn">
            <SlidersHorizontal color={palette.primary} size={16} />
          </Pressable>
        </View>

        {/* Active filter chips */}
        {activeFilters.length ? (
          <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>
            {activeFilters.map((label, i) => (
              <View key={i} style={[s.activeChip, { backgroundColor: palette.primary + "1A", borderColor: palette.primary }]}>
                <Text style={{ color: palette.primary, fontSize: 10, fontWeight: "800" }}>{label}</Text>
              </View>
            ))}
            <Pressable
              onPress={() => { setCategory(undefined); setRisk(undefined); setMinRating(undefined); setAmc(undefined); }}
              style={[s.activeChip, { backgroundColor: palette.chipBg, borderColor: palette.border }]}
              testID="mf-clear-filters"
            >
              <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "800" }}>Clear ×</Text>
            </Pressable>
          </View>
        ) : null}

        <Text style={{ color: palette.textMuted, fontSize: 11 }}>{total} funds found · sorted by {SORTS.find((s) => s.key === sort)?.label}</Text>
      </View>

      {loading ? (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={palette.primary} size="large" />
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(f) => f.fund_id}
          contentContainerStyle={{ paddingHorizontal: 16, paddingBottom: 40, gap: 8 }}
          onEndReachedThreshold={0.4}
          onEndReached={() => { if (items.length < total && !loadingMore) { setLoadingMore(true); load(); } }}
          renderItem={({ item: f }) => (
            <Pressable
              onPress={() => router.push({ pathname: "/mutual-funds/fund/[id]", params: { id: f.fund_id } })}
              style={[s.row, { backgroundColor: palette.surface, borderColor: palette.border }]}
              testID={`mf-explore-${f.fund_id}`}
            >
              <View style={{ flex: 1, gap: 3 }}>
                <Text style={{ color: palette.textPrimary, fontSize: 13, fontWeight: "800" }} numberOfLines={2}>{f.name}</Text>
                <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "700" }}>{f.amc} · Exp {f.expense_ratio}% · AUM ₹{(f.aum_cr / 1000).toFixed(1)}k Cr</Text>
                <View style={{ flexDirection: "row", gap: 6, marginTop: 2 }}>
                  <View style={[s.riskChip, { backgroundColor: (RISK_META[f.risk]?.color || palette.textMuted) + "22" }]}>
                    <Text style={{ color: RISK_META[f.risk]?.color, fontSize: 9, fontWeight: "800", letterSpacing: 0.4 }}>{(RISK_META[f.risk]?.label || f.risk).toUpperCase()}</Text>
                  </View>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 1 }}>
                    {Array.from({ length: Math.round(f.star_rating) }).map((_, i) => (
                      <Star key={i} color="#F59E0B" fill="#F59E0B" size={9} />
                    ))}
                  </View>
                </View>
              </View>
              <View style={{ alignItems: "flex-end", gap: 2 }}>
                <Text style={{ color: (f.returns?.y1 ?? 0) >= 0 ? palette.success : palette.danger, fontSize: 14, fontWeight: "800" }}>
                  {(f.returns?.y1 ?? 0) >= 0 ? "+" : ""}{(f.returns?.y1 ?? 0).toFixed(2)}%
                </Text>
                <Text style={{ color: palette.textMuted, fontSize: 9, fontWeight: "700" }}>1Y</Text>
                <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "700" }}>NAV ₹{f.current_nav}</Text>
              </View>
            </Pressable>
          )}
          ListEmptyComponent={
            <View style={{ padding: 40, alignItems: "center", gap: 8 }}>
              <Search color={palette.textMuted} size={44} />
              <Text style={{ color: palette.textSecondary, fontWeight: "800" }}>No funds found</Text>
            </View>
          }
          ListFooterComponent={loadingMore ? <ActivityIndicator color={palette.primary} style={{ marginVertical: 20 }} /> : null}
        />
      )}

      <FilterModal
        visible={showFilters}
        onClose={() => setShowFilters(false)}
        category={category} setCategory={setCategory}
        risk={risk} setRisk={setRisk}
        minRating={minRating} setMinRating={setMinRating}
        sort={sort} setSort={setSort}
        amc={amc} setAmc={setAmc} amcs={amcs}
      />
    </View>
  );
}

function FilterModal({ visible, onClose, category, setCategory, risk, setRisk, minRating, setMinRating, sort, setSort, amc, setAmc, amcs }: any) {
  const { palette } = useTheme();
  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <Pressable style={{ flex: 1, backgroundColor: palette.overlay }} onPress={onClose} />
      <View style={[fm.sheet, { backgroundColor: palette.surfaceElevated }]}>
        <View style={{ alignItems: "center", paddingVertical: 8 }}>
          <View style={{ width: 44, height: 4, borderRadius: 2, backgroundColor: palette.borderStrong }} />
        </View>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <Text style={{ color: palette.textPrimary, fontSize: 18, fontWeight: "800" }}>Filters & Sort</Text>
          <Pressable onPress={onClose} testID="filter-close"><X color={palette.textPrimary} size={20} /></Pressable>
        </View>
        <FilterGroup label="Category" palette={palette}>
          {CATEGORIES.map((c) => (
            <FilterPill key={c.key} label={`${c.emoji} ${c.label}`} active={category === c.key}
                          onPress={() => setCategory(category === c.key ? undefined : c.key)} palette={palette} />
          ))}
        </FilterGroup>
        <FilterGroup label="Risk" palette={palette}>
          {Object.entries(RISK_META).map(([k, m]: any) => (
            <FilterPill key={k} label={m.label} active={risk === k}
                          onPress={() => setRisk(risk === k ? undefined : k)} palette={palette} />
          ))}
        </FilterGroup>
        <FilterGroup label="Min Star Rating" palette={palette}>
          {[3, 4, 5].map((r) => (
            <FilterPill key={r} label={`${r}★+`} active={minRating === r}
                          onPress={() => setMinRating(minRating === r ? undefined : r)} palette={palette} />
          ))}
        </FilterGroup>
        <FilterGroup label="AMC" palette={palette}>
          {amcs.slice(0, 12).map((a: string) => (
            <FilterPill key={a} label={a.replace(" Mutual Fund", "")} active={amc === a}
                          onPress={() => setAmc(amc === a ? undefined : a)} palette={palette} />
          ))}
        </FilterGroup>
        <FilterGroup label="Sort" palette={palette}>
          {SORTS.map((so) => (
            <FilterPill key={so.key} label={so.label} active={sort === so.key}
                          onPress={() => setSort(so.key)} palette={palette} />
          ))}
        </FilterGroup>
        <Pressable onPress={onClose} style={[fm.apply, { backgroundColor: palette.primary }]} testID="filter-apply">
          <Text style={{ color: "#fff", fontSize: 15, fontWeight: "800" }}>Show Results</Text>
        </Pressable>
      </View>
    </Modal>
  );
}
function FilterGroup({ label, children, palette }: any) {
  return (
    <View style={{ gap: 6, marginBottom: 8 }}>
      <Text style={{ color: palette.textMuted, fontSize: 10, fontWeight: "800", letterSpacing: 1 }}>{label.toUpperCase()}</Text>
      <View style={{ flexDirection: "row", gap: 6, flexWrap: "wrap" }}>{children}</View>
    </View>
  );
}
function FilterPill({ label, active, onPress, palette }: any) {
  return (
    <Pressable
      onPress={onPress}
      style={{
        paddingHorizontal: 12, paddingVertical: 8, borderRadius: 999, borderWidth: 1,
        backgroundColor: active ? palette.primary : "transparent",
        borderColor: active ? palette.primary : palette.border,
      }}
    >
      <Text style={{ color: active ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{label}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  searchWrap: { flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 12, borderRadius: 14, borderWidth: 1 },
  filterBtn: { padding: 6, borderRadius: 10 },
  activeChip: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, borderWidth: 1 },
  row: { flexDirection: "row", gap: 10, padding: 14, borderRadius: 14, borderWidth: 1, alignItems: "center" },
  riskChip: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
});

const fm = StyleSheet.create({
  sheet: { padding: 16, borderTopLeftRadius: 22, borderTopRightRadius: 22, gap: 4, maxHeight: "80%" },
  apply: { paddingVertical: 14, borderRadius: 14, alignItems: "center", marginTop: 12 },
});

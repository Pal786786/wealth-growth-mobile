/**
 * Sprint 12.3 · Phase A — User Passbook
 *
 * Projected view of the immutable double-entry finance journal, per user:
 *   Date · Opening · Credit · Debit · Closing · Reference · Type · Narration · UTR · Status
 *
 * Sourced from `GET /api/wallet/passbook`.
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  View, Text, StyleSheet, Pressable, ScrollView, RefreshControl,
  ActivityIndicator, Platform, Modal,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  ChevronLeft, ArrowDownRight, ArrowUpRight, TrendingUp, Filter,
  BookOpen, Calendar, X, Copy,
} from "lucide-react-native";
import * as Clipboard from "expo-clipboard";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";

type Row = {
  journal_id: string;
  entry_date: string;
  txn_type: string;
  reference_id?: string;
  reference_type?: string;
  narration?: string;
  utr?: string;
  status?: string;
  opening_balance: number;
  credit: number;
  debit: number;
  closing_balance: number;
  is_reversed?: boolean;
};

type Passbook = {
  opening_balance: number;
  closing_balance: number;
  total_credit: number;
  total_debit: number;
  total_rows: number;
  rows: Row[];
};

const TYPE_LABEL: Record<string, string> = {
  wallet_credit: "Credit",
  wallet_debit: "Debit",
  razorpay_deposit: "Top-up",
  cashfree_withdrawal: "Withdrawal",
  gold_buy: "Gold Buy",
  gold_sell: "Gold Sell",
  mutual_fund_buy: "MF Buy",
  mutual_fund_redeem: "MF Redeem",
  forex_pnl: "Forex P&L",
  referral_bonus: "Referral",
  cashback: "Cashback",
  admin_adjustment: "Adjustment",
  reversal: "Reversal",
  fee: "Fee",
  tax: "Tax",
  provider_charge: "Charge",
};

const RANGE_PRESETS: { label: string; days: number | null }[] = [
  { label: "7D", days: 7 },
  { label: "30D", days: 30 },
  { label: "90D", days: 90 },
  { label: "1Y", days: 365 },
  { label: "All", days: null },
];

function inr(n: number) {
  return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" }) +
    " · " + d.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
}

export default function Passbook() {
  const { palette } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { show } = useToast();

  const [range, setRange] = useState<{ label: string; days: number | null }>(RANGE_PRESETS[1]);
  const [data, setData] = useState<Passbook | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [detail, setDetail] = useState<Row | null>(null);

  const load = useCallback(async () => {
    try {
      const params: any = { limit: 200 };
      if (range.days) {
        const from = new Date(); from.setDate(from.getDate() - range.days);
        params.date_from = from.toISOString();
      }
      const r = await api.get<Passbook>("/wallet/passbook", { params });
      setData(r.data);
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Failed to load passbook");
    } finally {
      setLoading(false); setRefreshing(false);
    }
  }, [range.days, show]);

  useEffect(() => { setLoading(true); load(); }, [load]);

  const grouped = useMemo(() => {
    if (!data) return [] as { day: string; rows: Row[] }[];
    const bucket: Record<string, Row[]> = {};
    for (const r of data.rows) {
      const d = new Date(r.entry_date);
      const key = d.toLocaleDateString("en-IN", { day: "2-digit", month: "long", year: "numeric" });
      (bucket[key] ||= []).push(r);
    }
    return Object.entries(bucket).map(([day, rows]) => ({ day, rows }));
  }, [data]);

  if (loading) {
    return (
      <View style={[styles.center, { backgroundColor: palette.background }]}>
        <ActivityIndicator size="large" color={palette.primary} />
      </View>
    );
  }

  return (
    <View style={{ flex: 1, backgroundColor: palette.background }}>
      {/* Header */}
      <View style={[styles.header, { paddingTop: insets.top + 8, backgroundColor: palette.surface, borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} hitSlop={12}>
          <ChevronLeft color={palette.textPrimary} size={22} />
        </Pressable>
        <View style={{ flex: 1, alignItems: "center" }}>
          <Text style={[styles.headerTitle, { color: palette.textPrimary }]}>Passbook</Text>
          <Text style={[styles.headerSub, { color: palette.textSecondary }]}>Immutable finance journal</Text>
        </View>
        <View style={{ width: 36 }} />
      </View>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
      >
        {/* Summary */}
        <View style={styles.section}>
          <View style={[styles.summaryCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={styles.balanceRow}>
              <View>
                <Text style={[styles.small, { color: palette.textSecondary }]}>CLOSING BALANCE</Text>
                <Text style={[styles.balance, { color: palette.textPrimary }]}>{inr(data?.closing_balance || 0)}</Text>
              </View>
              <View style={[styles.badge, { backgroundColor: palette.primary + "18" }]}>
                <BookOpen color={palette.primary} size={16} />
                <Text style={[styles.badgeText, { color: palette.primary }]}>{data?.total_rows || 0} entries</Text>
              </View>
            </View>
            <View style={[styles.dividerH, { backgroundColor: palette.border }]} />
            <View style={styles.summaryRow}>
              <SummaryStat icon={<ArrowDownRight color={palette.success} size={18} />}
                            label="CREDITS" value={inr(data?.total_credit || 0)} color={palette.success} palette={palette} />
              <View style={[styles.dividerV, { backgroundColor: palette.border }]} />
              <SummaryStat icon={<ArrowUpRight color={palette.danger} size={18} />}
                            label="DEBITS" value={inr(data?.total_debit || 0)} color={palette.danger} palette={palette} />
              <View style={[styles.dividerV, { backgroundColor: palette.border }]} />
              <SummaryStat icon={<TrendingUp color={palette.primary} size={18} />}
                            label="OPENING" value={inr(data?.opening_balance || 0)} color={palette.textPrimary} palette={palette} />
            </View>
          </View>
        </View>

        {/* Range filter */}
        <View style={styles.rangeRow}>
          {RANGE_PRESETS.map((r) => (
            <Pressable key={r.label} onPress={() => setRange(r)}
                       style={[styles.rangeChip, {
                         backgroundColor: range.label === r.label ? palette.primary : palette.surface,
                         borderColor: range.label === r.label ? palette.primary : palette.border,
                       }]}>
              <Text style={{ color: range.label === r.label ? "#fff" : palette.textPrimary, fontWeight: "800", fontSize: 12 }}>{r.label}</Text>
            </Pressable>
          ))}
        </View>

        {/* Rows */}
        {(!data || data.total_rows === 0) ? (
          <View style={styles.empty}>
            <BookOpen color={palette.textMuted} size={64} />
            <Text style={[styles.emptyTitle, { color: palette.textPrimary }]}>No transactions yet</Text>
            <Text style={[styles.emptyBody, { color: palette.textSecondary }]}>
              When money moves in or out of your wallet — top-ups, withdrawals, gold, mutual funds, forex — you&apos;ll see them here.
            </Text>
          </View>
        ) : (
          grouped.map(({ day, rows }) => (
            <View key={day} style={styles.section}>
              <Text style={[styles.dayHeader, { color: palette.textSecondary }]}>{day.toUpperCase()}</Text>
              {rows.map((r, idx) => (
                <Pressable key={r.journal_id} onPress={() => setDetail(r)}
                           style={[styles.row, { backgroundColor: palette.surface, borderColor: palette.border },
                                    idx === 0 && { borderTopLeftRadius: 14, borderTopRightRadius: 14 },
                                    idx === rows.length - 1 && { borderBottomLeftRadius: 14, borderBottomRightRadius: 14, marginBottom: 12 }]}>
                  <View style={[styles.rowIcon, { backgroundColor: (r.credit > 0 ? palette.success : palette.danger) + "18" }]}>
                    {r.credit > 0
                      ? <ArrowDownRight color={palette.success} size={20} />
                      : <ArrowUpRight color={palette.danger} size={20} />}
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      <Text style={[styles.rowTitle, { color: palette.textPrimary }]} numberOfLines={1}>
                        {TYPE_LABEL[r.txn_type] || r.txn_type}
                      </Text>
                      {r.is_reversed && (
                        <View style={{ paddingHorizontal: 5, paddingVertical: 1, borderRadius: 4, backgroundColor: palette.warning + "22" }}>
                          <Text style={{ fontSize: 8, fontWeight: "900", color: palette.warning, letterSpacing: 0.3 }}>REVERSED</Text>
                        </View>
                      )}
                    </View>
                    <Text style={[styles.rowNarration, { color: palette.textSecondary }]} numberOfLines={1}>
                      {r.narration || (r.reference_id ? `Ref: ${r.reference_id.slice(0, 22)}` : "")}
                    </Text>
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={{ fontWeight: "900", fontSize: 14,
                                    color: r.credit > 0 ? palette.success : palette.danger }}>
                      {r.credit > 0 ? "+" : "-"}{inr(r.credit || r.debit)}
                    </Text>
                    <Text style={{ fontSize: 10, color: palette.textMuted, marginTop: 2 }}>
                      Bal · {inr(r.closing_balance)}
                    </Text>
                  </View>
                </Pressable>
              ))}
            </View>
          ))
        )}
      </ScrollView>

      {/* Detail modal */}
      <Modal visible={!!detail} animationType="slide" transparent onRequestClose={() => setDetail(null)}>
        <Pressable style={styles.modalOverlay} onPress={() => setDetail(null)}>
          <Pressable style={[styles.modalCard, { backgroundColor: palette.surface, borderColor: palette.border, paddingBottom: insets.bottom + 20 }]} onPress={(e) => e.stopPropagation?.()}>
            {detail && (
              <>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                  <Text style={[styles.modalTitle, { color: palette.textPrimary }]}>{TYPE_LABEL[detail.txn_type] || detail.txn_type}</Text>
                  <Pressable onPress={() => setDetail(null)} hitSlop={12}>
                    <X color={palette.textPrimary} size={22} />
                  </Pressable>
                </View>
                <Text style={{ fontSize: 32, fontWeight: "900", color: detail.credit > 0 ? palette.success : palette.danger, marginBottom: 4 }}>
                  {detail.credit > 0 ? "+" : "-"}{inr(detail.credit || detail.debit)}
                </Text>
                <Text style={{ fontSize: 12, color: palette.textSecondary, marginBottom: 20 }}>
                  {fmtDate(detail.entry_date)}
                </Text>
                <DetailRow label="Opening Balance" value={inr(detail.opening_balance)} palette={palette} />
                <DetailRow label="Closing Balance" value={inr(detail.closing_balance)} palette={palette} bold />
                {detail.narration && <DetailRow label="Narration" value={detail.narration} palette={palette} multiline />}
                {detail.reference_id && (
                  <DetailRow label="Reference" value={detail.reference_id} palette={palette} mono copyable show={show} />
                )}
                {detail.utr && (
                  <DetailRow label="UTR" value={detail.utr} palette={palette} mono copyable show={show} />
                )}
                {detail.status && <DetailRow label="Status" value={detail.status.toUpperCase()} palette={palette} />}
                <DetailRow label="Journal ID" value={detail.journal_id} palette={palette} mono copyable show={show} />
                {detail.is_reversed && (
                  <View style={{ backgroundColor: palette.warning + "18", padding: 10, borderRadius: 10, marginTop: 12 }}>
                    <Text style={{ color: palette.warning, fontWeight: "900", fontSize: 12 }}>⚠ This entry has been reversed</Text>
                  </View>
                )}
              </>
            )}
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

function SummaryStat({ icon, label, value, color, palette }: { icon: React.ReactNode; label: string; value: string; color: string; palette: any }) {
  return (
    <View style={{ flex: 1, alignItems: "center", gap: 4 }}>
      {icon}
      <Text style={{ fontSize: 10, fontWeight: "800", letterSpacing: 0.3, color: palette.textSecondary }}>{label}</Text>
      <Text style={{ fontSize: 14, fontWeight: "900", color }} numberOfLines={1}>{value}</Text>
    </View>
  );
}

function DetailRow({ label, value, palette, bold, mono, multiline, copyable, show }: {
  label: string; value: string; palette: any; bold?: boolean; mono?: boolean;
  multiline?: boolean; copyable?: boolean; show?: (t: string, m: string) => void;
}) {
  const onCopy = async () => {
    try { await Clipboard.setStringAsync(value); show?.("success", `${label} copied`); } catch {}
  };
  return (
    <View style={{ flexDirection: multiline ? "column" : "row", justifyContent: "space-between",
                    paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: palette.border, gap: multiline ? 4 : 8 }}>
      <Text style={{ fontSize: 12, color: palette.textSecondary, fontWeight: "700" }}>{label}</Text>
      <Pressable disabled={!copyable} onPress={onCopy} style={{ flexDirection: "row", alignItems: "center", gap: 6, flexShrink: 1 }}>
        <Text style={[{ fontSize: 13, color: palette.textPrimary, textAlign: multiline ? "left" : "right", flexShrink: 1 },
                       bold && { fontWeight: "900", fontSize: 15 },
                       mono && { fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace", fontSize: 12 }]} numberOfLines={multiline ? 4 : 1}>
          {value}
        </Text>
        {copyable && <Copy color={palette.textMuted} size={12} />}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingBottom: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "900" },
  headerSub: { fontSize: 10, fontWeight: "700", marginTop: 1 },
  section: { paddingHorizontal: 16, marginTop: 16 },
  summaryCard: { borderWidth: 1, borderRadius: 16, padding: 16, gap: 12 },
  balanceRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  small: { fontSize: 10, fontWeight: "800", letterSpacing: 0.5, marginBottom: 2 },
  balance: { fontSize: 32, fontWeight: "900" },
  badge: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999 },
  badgeText: { fontSize: 11, fontWeight: "900" },
  summaryRow: { flexDirection: "row", alignItems: "center" },
  dividerH: { height: 1 },
  dividerV: { width: 1, alignSelf: "stretch", marginVertical: 4 },
  rangeRow: { flexDirection: "row", gap: 8, paddingHorizontal: 16, marginTop: 16 },
  rangeChip: { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 999, borderWidth: 1.5 },
  dayHeader: { fontSize: 10, fontWeight: "900", letterSpacing: 0.6, marginBottom: 6, marginTop: 8 },
  row: { flexDirection: "row", alignItems: "center", gap: 12, padding: 12,
          borderTopWidth: StyleSheet.hairlineWidth, borderLeftWidth: 1, borderRightWidth: 1 },
  rowIcon: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  rowTitle: { fontSize: 14, fontWeight: "800" },
  rowNarration: { fontSize: 12, fontWeight: "600", marginTop: 2 },
  empty: { alignItems: "center", padding: 40, gap: 12 },
  emptyTitle: { fontSize: 18, fontWeight: "900" },
  emptyBody: { fontSize: 13, textAlign: "center", lineHeight: 20, paddingHorizontal: 20 },
  modalOverlay: { flex: 1, backgroundColor: "rgba(0,0,0,0.5)", justifyContent: "flex-end" },
  modalCard: { borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, borderTopWidth: 1, maxHeight: "85%" },
  modalTitle: { fontSize: 18, fontWeight: "900" },
});

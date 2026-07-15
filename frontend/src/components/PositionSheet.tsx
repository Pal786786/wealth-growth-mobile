/** Sprint 16.1 — MT5-style position management sheet.
 * Modify TP/SL · Partial Close (25/50/75/custom) · Close · Reverse · Double. */
import React, { useEffect, useState } from "react";
import { View, Text, Modal, Pressable, TextInput, ActivityIndicator, StyleSheet, Platform, Alert } from "react-native";
import { forexApi, Position } from "@/src/api/forex";
import { useTheme } from "@/src/theme/ThemeProvider";
import { formatINR } from "@/src/utils/format";

type Props = {
  position: Position | null;
  priceDecimals: number;
  onClose: () => void;
  onChanged: () => void | Promise<void>;
};

function confirmDialog(title: string, msg: string, onYes: () => void) {
  if (Platform.OS === "web") {
    if (window.confirm(`${title}\n\n${msg}`)) onYes();
  } else {
    Alert.alert(title, msg, [{ text: "Cancel", style: "cancel" }, { text: "Confirm", onPress: onYes }]);
  }
}

export function PositionSheet({ position, priceDecimals, onClose, onChanged }: Props) {
  const { palette } = useTheme();
  const [tp, setTp] = useState("");
  const [sl, setSl] = useState("");
  const [customPct, setCustomPct] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    if (position) {
      setTp(position.tp ? String(position.tp) : "");
      setSl(position.sl ? String(position.sl) : "");
      setCustomPct("");
      setErr("");
    }
  }, [position?.position_id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!position) return null;
  const p = position;

  const run = async (fn: () => Promise<any>, closeAfter = true) => {
    setBusy(true); setErr("");
    try {
      await fn();
      await onChanged();
      if (closeAfter) onClose();
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const partial = (frac: number) => {
    if (!(frac > 0 && frac < 1)) { setErr("Enter a % between 1 and 99"); return; }
    confirmDialog("Partial close", `Close ${(frac * 100).toFixed(0)}% of ${p.side.toUpperCase()} ${p.lot_size}?`,
      () => run(() => forexApi.partialClose(p.position_id, frac)));
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.bg} onPress={onClose}>
        <Pressable style={[s.sheet, { backgroundColor: palette.card, borderColor: palette.border }]} onPress={() => {}}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={{ color: p.side === "buy" ? palette.success : palette.danger, fontWeight: "800", fontSize: 15 }}>
              {p.side.toUpperCase()} {p.lot_size} {p.symbol_id}
            </Text>
            <Text style={{ color: p.pnl_inr >= 0 ? palette.success : palette.danger, fontWeight: "800", fontVariant: ["tabular-nums"] }}>
              {p.pnl_inr >= 0 ? "+" : ""}{formatINR(p.pnl_inr)}
            </Text>
          </View>
          <Text style={{ color: palette.textMuted, fontSize: 11 }}>
            Entry {p.entry_price?.toFixed?.(priceDecimals) ?? p.entry_price} · Margin {formatINR(p.margin_inr)}
            {(p as any).est_commission ? ` · Est. commission ${formatINR((p as any).est_commission)} · Est. net ${formatINR((p as any).est_net_pnl)}` : ""}
          </Text>

          {/* Modify TP/SL */}
          <View style={{ flexDirection: "row", gap: 8 }}>
            <View style={{ flex: 1 }}>
              <Text style={[s.label, { color: palette.textSecondary }]}>TAKE PROFIT</Text>
              <TextInput value={tp} onChangeText={setTp} keyboardType="decimal-pad" testID="sheet-tp"
                placeholder="—" placeholderTextColor={palette.textMuted}
                style={[s.input, { color: palette.textPrimary, borderColor: palette.border, backgroundColor: palette.surface }]} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[s.label, { color: palette.textSecondary }]}>STOP LOSS</Text>
              <TextInput value={sl} onChangeText={setSl} keyboardType="decimal-pad" testID="sheet-sl"
                placeholder="—" placeholderTextColor={palette.textMuted}
                style={[s.input, { color: palette.textPrimary, borderColor: palette.border, backgroundColor: palette.surface }]} />
            </View>
            <Pressable testID="sheet-save-tpsl" disabled={busy}
              onPress={() => run(() => forexApi.updateTPSL(p.position_id, tp ? parseFloat(tp) : undefined, sl ? parseFloat(sl) : undefined), false)}
              style={[s.saveBtn, { backgroundColor: palette.primary }]}>
              <Text style={{ color: "#fff", fontWeight: "800", fontSize: 12 }}>Save</Text>
            </Pressable>
          </View>

          {/* Partial close */}
          <Text style={[s.label, { color: palette.textSecondary }]}>PARTIAL CLOSE</Text>
          <View style={{ flexDirection: "row", gap: 6 }}>
            {[0.25, 0.5, 0.75].map((f) => (
              <Pressable key={f} testID={`partial-${f * 100}`} disabled={busy} onPress={() => partial(f)}
                style={[s.pctBtn, { borderColor: palette.border, backgroundColor: palette.surface }]}>
                <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 12 }}>{f * 100}%</Text>
              </Pressable>
            ))}
            <TextInput value={customPct} onChangeText={setCustomPct} keyboardType="number-pad" testID="partial-custom"
              placeholder="%" placeholderTextColor={palette.textMuted}
              style={[s.pctBtn, { color: palette.textPrimary, borderColor: palette.border, backgroundColor: palette.surface, textAlign: "center" }]} />
            <Pressable testID="partial-custom-go" disabled={busy}
              onPress={() => partial((parseFloat(customPct) || 0) / 100)}
              style={[s.pctBtn, { borderColor: palette.primary, backgroundColor: palette.primary + "15" }]}>
              <Text style={{ color: palette.primary, fontWeight: "800", fontSize: 12 }}>Go</Text>
            </Pressable>
          </View>

          {/* Actions */}
          <View style={{ flexDirection: "row", gap: 8 }}>
            <Pressable testID="sheet-reverse" disabled={busy}
              onPress={() => confirmDialog("Reverse position", `Close and open ${p.side === "buy" ? "SELL" : "BUY"} ${p.lot_size}?`,
                () => run(() => forexApi.reversePosition(p.position_id)))}
              style={[s.actBtn, { borderColor: "#f0b90b" }]}>
              <Text style={{ color: "#f0b90b", fontWeight: "800", fontSize: 12 }}>Reverse</Text>
            </Pressable>
            <Pressable testID="sheet-double" disabled={busy}
              onPress={() => confirmDialog("Double position", `Open another ${p.side.toUpperCase()} ${p.lot_size}?`,
                () => run(() => forexApi.doublePosition(p.position_id)))}
              style={[s.actBtn, { borderColor: "#29b6f6" }]}>
              <Text style={{ color: "#29b6f6", fontWeight: "800", fontSize: 12 }}>Double</Text>
            </Pressable>
            <Pressable testID="sheet-close" disabled={busy}
              onPress={() => confirmDialog("Close position", `Close ${p.side.toUpperCase()} ${p.lot_size} at market?`,
                () => run(() => forexApi.closePosition(p.position_id)))}
              style={[s.actBtn, { borderColor: palette.danger, backgroundColor: palette.danger + "15" }]}>
              <Text style={{ color: palette.danger, fontWeight: "800", fontSize: 12 }}>Close</Text>
            </Pressable>
          </View>

          {busy ? <ActivityIndicator color={palette.primary} /> : null}
          {err ? <Text style={{ color: palette.danger, fontSize: 11 }}>{err}</Text> : null}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const s = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "#000a", justifyContent: "flex-end" },
  sheet: { borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 18, gap: 12, borderWidth: 1 },
  label: { fontSize: 10, fontWeight: "700", letterSpacing: 1, marginBottom: 4 },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 9, fontSize: 13, fontWeight: "600" },
  saveBtn: { alignSelf: "flex-end", paddingHorizontal: 14, paddingVertical: 11, borderRadius: 10 },
  pctBtn: { flex: 1, paddingVertical: 9, borderRadius: 9, borderWidth: 1, alignItems: "center", minHeight: 38, justifyContent: "center" },
  actBtn: { flex: 1, paddingVertical: 11, borderRadius: 10, borderWidth: 1.5, alignItems: "center" },
});

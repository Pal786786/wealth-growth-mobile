/**
 * Price Alerts — Sprint 7C.1
 * List + create/toggle/delete. 5 alert types.
 */
import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, Pressable, ActivityIndicator, TextInput, Modal, RefreshControl } from "react-native";
import { useRouter } from "expo-router";
import { ArrowLeft, Bell, Trash2, Plus, X, Play, Pause } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { useToast } from "@/src/components/Toast";
import { aiApi, Alert as AlertT, AlertType } from "@/src/api/aiIntel";
import { errText } from "@/src/utils/errors";

const TYPES: { id: AlertType; label: string; hint: string }[] = [
  { id: "price_above", label: "Price above", hint: "Trigger when price crosses ABOVE target" },
  { id: "price_below", label: "Price below", hint: "Trigger when price crosses BELOW target" },
  { id: "percent_move", label: "% Move", hint: "Trigger when price moves ± X% from anchor" },
  { id: "indicator_cross", label: "EMA Cross", hint: "Golden/Death cross on chosen EMAs" },
  { id: "rsi_alert", label: "RSI Alert", hint: "Trigger when RSI crosses a threshold" },
];

export default function AIAlerts() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [alerts, setAlerts] = useState<AlertT[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await aiApi.alerts();
      setAlerts(r.alerts || []);
    } catch (e) { show("error", errText(e, "Failed to load alerts")); }
    finally { setLoading(false); setRefreshing(false); }
  }, [show]);
  useEffect(() => { load(); }, [load]);

  const toggle = async (a: AlertT) => {
    try {
      if (a.status === "active") await aiApi.pauseAlert(a.alert_id);
      else await aiApi.resumeAlert(a.alert_id);
      await load();
    } catch (e) { show("error", errText(e, "Toggle failed")); }
  };
  const remove = async (a: AlertT) => {
    try { await aiApi.deleteAlert(a.alert_id); setAlerts((prev) => prev.filter((x) => x.alert_id !== a.alert_id)); }
    catch (e) { show("error", errText(e, "Delete failed")); }
  };

  return (
    <Screen padded={false}>
      <View style={[s.header, { borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} hitSlop={12}><ArrowLeft size={22} color={palette.textPrimary} /></Pressable>
        <View style={{ flex: 1 }}>
          <Text style={[s.title, { color: palette.textPrimary }]}>Price Alerts</Text>
          <Text style={{ color: palette.textMuted, fontSize: 10 }}>{alerts.length} total · Evaluates every 30s</Text>
        </View>
        <Pressable onPress={() => setCreating(true)} hitSlop={8}
          style={{ flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: palette.primary }}>
          <Plus size={13} color="#fff" />
          <Text style={{ color: "#fff", fontSize: 11, fontWeight: "800" }}>New</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={palette.primary} />}
      >
        {loading && <View style={{ padding: 40, alignItems: "center" }}><ActivityIndicator color={palette.primary} /></View>}
        {!loading && alerts.length === 0 && (
          <View style={{ padding: 40, alignItems: "center" }}>
            <Bell size={44} color={palette.textMuted} />
            <Text style={{ color: palette.textPrimary, fontSize: 15, fontWeight: "800", marginTop: 10 }}>No alerts set</Text>
            <Text style={{ color: palette.textMuted, fontSize: 12, textAlign: "center", marginTop: 6, lineHeight: 18 }}>
              Create alerts to get notified on price movement, EMA crosses or RSI extremes.
            </Text>
            <Pressable onPress={() => setCreating(true)} style={{ marginTop: 16, backgroundColor: palette.primary, paddingHorizontal: 20, paddingVertical: 10, borderRadius: 999 }}>
              <Text style={{ color: "#fff", fontWeight: "900", fontSize: 13 }}>Create your first alert</Text>
            </Pressable>
          </View>
        )}
        {alerts.map((a) => <AlertRow key={a.alert_id} a={a} palette={palette}
          onToggle={() => toggle(a)} onRemove={() => remove(a)} onOpen={() => router.push(`/ai/signal/${a.symbol}` as any)} />)}
      </ScrollView>

      {creating && <CreateAlertSheet palette={palette} onClose={() => setCreating(false)} onCreated={() => { setCreating(false); load(); }} />}
    </Screen>
  );
}

function AlertRow({ a, palette, onToggle, onRemove, onOpen }: any) {
  const isTriggered = a.status === "triggered";
  const isActive = a.status === "active";
  const statusColor = isActive ? palette.success : isTriggered ? "#3B82F6" : palette.warning;
  return (
    <Pressable onPress={onOpen} style={({ pressed }) => [s.row, { backgroundColor: pressed ? palette.surface : palette.background, borderBottomColor: palette.border }]}>
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Text style={{ color: palette.textPrimary, fontSize: 14, fontWeight: "900" }}>{a.symbol}</Text>
          <View style={{ paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4, backgroundColor: statusColor + "22" }}>
            <Text style={{ color: statusColor, fontSize: 9, fontWeight: "900" }}>{a.status.toUpperCase()}</Text>
          </View>
          <Text style={{ color: palette.textMuted, fontSize: 10 }}>{typeLabel(a.type)}</Text>
        </View>
        <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 3 }}>{describe(a)}</Text>
        {isTriggered && a.trigger_note && (
          <Text style={{ color: "#3B82F6", fontSize: 10, marginTop: 3, fontWeight: "700" }}>Triggered: {a.trigger_note}</Text>
        )}
      </View>
      {!isTriggered && (
        <Pressable onPress={onToggle} hitSlop={6} style={{ padding: 6 }}>
          {isActive ? <Pause size={14} color={palette.warning} /> : <Play size={14} color={palette.success} />}
        </Pressable>
      )}
      <Pressable onPress={onRemove} hitSlop={6} style={{ padding: 6 }}>
        <Trash2 size={14} color={palette.textMuted} />
      </Pressable>
    </Pressable>
  );
}

function typeLabel(t: AlertType) {
  return TYPES.find((x) => x.id === t)?.label || t;
}
function describe(a: AlertT) {
  if (a.type === "price_above") return `Price crosses above ${a.target_price}`;
  if (a.type === "price_below") return `Price crosses below ${a.target_price}`;
  if (a.type === "percent_move") return `Moves ${a.direction === "both" ? "±" : a.direction === "up" ? "+" : "-"}${a.target_percent}% from ${a.anchor_price}`;
  if (a.type === "indicator_cross") return `EMA ${a.fast_ema}/${a.slow_ema} cross on ${a.timeframe}`;
  if (a.type === "rsi_alert") return `RSI ${a.direction === "cross_above" ? "crosses above" : "crosses below"} ${a.threshold} on ${a.timeframe}`;
  return "";
}

function CreateAlertSheet({ palette, onClose, onCreated }: any) {
  const { show } = useToast();
  const [type, setType] = useState<AlertType>("price_above");
  const [symbol, setSymbol] = useState("XAUUSD");
  const [target_price, setTargetPrice] = useState("");
  const [target_percent, setTargetPercent] = useState("");
  const [anchor_price, setAnchorPrice] = useState("");
  const [threshold, setThreshold] = useState("70");
  const [direction, setDirection] = useState<string>("cross_above");
  const [fast_ema, setFastEma] = useState("20");
  const [slow_ema, setSlowEma] = useState("50");
  const [timeframe, setTimeframe] = useState("H1");
  const [busy, setBusy] = useState(false);

  const create = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const payload: any = { type, symbol: symbol.toUpperCase() };
      if (type === "price_above" || type === "price_below") {
        if (!target_price) throw new Error("Target price required");
        payload.target_price = Number(target_price);
      } else if (type === "percent_move") {
        if (!target_percent) throw new Error("Target percent required");
        payload.target_percent = Number(target_percent);
        if (anchor_price) payload.anchor_price = Number(anchor_price);
        payload.direction = direction === "cross_above" || direction === "cross_below" ? "both" : direction;
      } else if (type === "indicator_cross") {
        payload.fast_ema = Number(fast_ema); payload.slow_ema = Number(slow_ema);
        payload.timeframe = timeframe;
      } else if (type === "rsi_alert") {
        payload.threshold = Number(threshold); payload.direction = direction;
        payload.timeframe = timeframe;
      }
      await aiApi.createAlert(payload);
      show("success", "Alert created");
      onCreated();
    } catch (e: any) {
      show("error", errText(e, "Create failed"));
    } finally { setBusy(false); }
  };

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: "#0006", justifyContent: "flex-end" }}>
        <View style={[s.sheet, { backgroundColor: palette.background, maxHeight: "88%" }]}>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <Text style={{ color: palette.textPrimary, fontSize: 16, fontWeight: "900" }}>New Price Alert</Text>
            <Pressable onPress={onClose} hitSlop={8}><X size={20} color={palette.textPrimary} /></Pressable>
          </View>

          <ScrollView showsVerticalScrollIndicator={false}>
            <Text style={s.lbl}>Symbol</Text>
            <TextInput value={symbol} onChangeText={setSymbol} autoCapitalize="characters" autoCorrect={false}
              style={[s.input, { borderColor: palette.border, color: palette.textPrimary, backgroundColor: palette.surface }]} />

            <Text style={s.lbl}>Alert Type</Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
              {TYPES.map((t) => (
                <Pressable key={t.id} onPress={() => setType(t.id)}
                  style={[s.chip, { backgroundColor: type === t.id ? palette.primary : palette.surface, borderColor: palette.border }]}>
                  <Text style={{ color: type === t.id ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{t.label}</Text>
                </Pressable>
              ))}
            </View>
            <Text style={{ color: palette.textMuted, fontSize: 11, marginTop: 6 }}>{TYPES.find((t) => t.id === type)?.hint}</Text>

            {(type === "price_above" || type === "price_below") && (
              <>
                <Text style={s.lbl}>Target price</Text>
                <TextInput value={target_price} onChangeText={setTargetPrice} keyboardType="decimal-pad"
                  placeholder="e.g. 4100" placeholderTextColor={palette.textMuted}
                  style={[s.input, { borderColor: palette.border, color: palette.textPrimary, backgroundColor: palette.surface }]} />
              </>
            )}
            {type === "percent_move" && (
              <>
                <Text style={s.lbl}>% Move (absolute)</Text>
                <TextInput value={target_percent} onChangeText={setTargetPercent} keyboardType="decimal-pad"
                  placeholder="e.g. 2 → ±2%" placeholderTextColor={palette.textMuted}
                  style={[s.input, { borderColor: palette.border, color: palette.textPrimary, backgroundColor: palette.surface }]} />
                <Text style={s.lbl}>Anchor price (leave blank for current)</Text>
                <TextInput value={anchor_price} onChangeText={setAnchorPrice} keyboardType="decimal-pad" placeholder="Optional"
                  placeholderTextColor={palette.textMuted}
                  style={[s.input, { borderColor: palette.border, color: palette.textPrimary, backgroundColor: palette.surface }]} />
                <Text style={s.lbl}>Direction</Text>
                <View style={{ flexDirection: "row", gap: 6 }}>
                  {["up", "down", "both"].map((d) => (
                    <Pressable key={d} onPress={() => setDirection(d)}
                      style={[s.chip, { backgroundColor: direction === d ? palette.primary : palette.surface, borderColor: palette.border }]}>
                      <Text style={{ color: direction === d ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{d}</Text>
                    </Pressable>
                  ))}
                </View>
              </>
            )}
            {type === "indicator_cross" && (
              <>
                <View style={{ flexDirection: "row", gap: 8 }}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.lbl}>Fast EMA</Text>
                    <TextInput value={fast_ema} onChangeText={setFastEma} keyboardType="numeric"
                      style={[s.input, { borderColor: palette.border, color: palette.textPrimary, backgroundColor: palette.surface }]} />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={s.lbl}>Slow EMA</Text>
                    <TextInput value={slow_ema} onChangeText={setSlowEma} keyboardType="numeric"
                      style={[s.input, { borderColor: palette.border, color: palette.textPrimary, backgroundColor: palette.surface }]} />
                  </View>
                </View>
                <Text style={s.lbl}>Timeframe</Text>
                <View style={{ flexDirection: "row", gap: 6 }}>
                  {["M15", "H1", "H4", "D1"].map((t) => (
                    <Pressable key={t} onPress={() => setTimeframe(t)}
                      style={[s.chip, { backgroundColor: timeframe === t ? palette.primary : palette.surface, borderColor: palette.border }]}>
                      <Text style={{ color: timeframe === t ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{t}</Text>
                    </Pressable>
                  ))}
                </View>
              </>
            )}
            {type === "rsi_alert" && (
              <>
                <Text style={s.lbl}>RSI threshold</Text>
                <TextInput value={threshold} onChangeText={setThreshold} keyboardType="numeric"
                  style={[s.input, { borderColor: palette.border, color: palette.textPrimary, backgroundColor: palette.surface }]} />
                <Text style={s.lbl}>Direction</Text>
                <View style={{ flexDirection: "row", gap: 6 }}>
                  {["cross_above", "cross_below"].map((d) => (
                    <Pressable key={d} onPress={() => setDirection(d)}
                      style={[s.chip, { backgroundColor: direction === d ? palette.primary : palette.surface, borderColor: palette.border }]}>
                      <Text style={{ color: direction === d ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{d.replace("_", " ")}</Text>
                    </Pressable>
                  ))}
                </View>
                <Text style={s.lbl}>Timeframe</Text>
                <View style={{ flexDirection: "row", gap: 6 }}>
                  {["M15", "H1", "H4", "D1"].map((t) => (
                    <Pressable key={t} onPress={() => setTimeframe(t)}
                      style={[s.chip, { backgroundColor: timeframe === t ? palette.primary : palette.surface, borderColor: palette.border }]}>
                      <Text style={{ color: timeframe === t ? "#fff" : palette.textPrimary, fontSize: 11, fontWeight: "800" }}>{t}</Text>
                    </Pressable>
                  ))}
                </View>
              </>
            )}

            <Pressable disabled={busy} onPress={create}
              style={{ marginTop: 20, backgroundColor: palette.primary, padding: 14, borderRadius: 12, alignItems: "center", opacity: busy ? 0.6 : 1 }}>
              <Text style={{ color: "#fff", fontWeight: "900", fontSize: 14 }}>{busy ? "Creating…" : "Create Alert"}</Text>
            </Pressable>
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 14, paddingTop: 8, paddingBottom: 10, borderBottomWidth: StyleSheet.hairlineWidth },
  title: { fontSize: 18, fontWeight: "800" },
  row: { flexDirection: "row", alignItems: "center", gap: 10, paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  sheet: { padding: 18, borderTopLeftRadius: 20, borderTopRightRadius: 20, paddingBottom: 34 },
  lbl: { color: "#94A3B8", fontSize: 10, fontWeight: "900", letterSpacing: 0.5, marginTop: 12, marginBottom: 4 },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, borderWidth: 1 },
});

/**
 * Sprint 12.2.1 — Wallet Top-up via UPI QR (MFB-owned QR only)
 *
 * Flow:
 *   1. Request Camera permission (graceful denial handling)
 *   2. Scan QR → parse UPI URI via backend `/wallet/qr/parse`
 *   3. Backend validates payee VPA is MFB-owned → returns is_mfb + parsed amount
 *   4. If unsupported → show "This QR is not supported for Wallet Top-up."
 *   5. If supported → confirmation sheet (amount if present, or user input)
 *   6. Initiate via `/wallet/qr/initiate` (creates Razorpay order + intent URI)
 *   7. Open UPI intent → any UPI app (GPay/PhonePe/Paytm/BHIM)
 *   8. Poll `/wallet/qr/status/{order_id}` for `captured`
 *   9. Wallet credit is authoritative via existing Razorpay webhook — never client-driven
 */
import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  View, Text, StyleSheet, Pressable, Linking, Platform,
  ActivityIndicator, Alert, TextInput, KeyboardAvoidingView, ScrollView,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as WebBrowser from "expo-web-browser";
import {
  ChevronLeft, ShieldCheck, QrCode, ScanLine, AlertTriangle,
  CheckCircle2, Copy, ExternalLink, RotateCcw, Wallet,
} from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { useToast } from "@/src/components/Toast";
import { api } from "@/src/api/client";

type ParseResp = {
  is_mfb: boolean;
  reason?: string | null;
  match_type?: "vpa" | "domain" | null;
  payee_vpa: string;
  payee_name: string;
  amount: number | null;
  currency: string;
  note: string;
  merchant_code: string;
  supported_message?: string | null;
};

type InitiateResp = {
  ok: boolean;
  order: { order_id: string; provider_order_id: string; amount_paise: number; status: string; is_demo?: boolean; receipt?: string };
  intent_uri: string;
  checkout: { key_id: string; provider_order_id: string; amount_paise: number; currency: string; receipt: string; demo: boolean; mode: string };
  merchant: { name: string; vpa: string };
};

type QRCfg = {
  enabled: boolean;
  merchant_name: string;
  allowed_vpas: string[];
  allowed_vpa_domains: string[];
  min_amount: number;
  max_amount: number;
};

function formatINR(n: number) {
  return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}
function genIdempotencyKey() {
  return `mfb_qr_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

export default function TopUpScanQR() {
  const { palette } = useTheme();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { show } = useToast();

  const [perm, requestPerm] = useCameraPermissions();
  const [cfg, setCfg] = useState<QRCfg | null>(null);
  const [scanning, setScanning] = useState(true);
  const [parsing, setParsing] = useState(false);
  const [parsed, setParsed] = useState<ParseResp | null>(null);
  const [amount, setAmount] = useState<string>("");
  const [confirming, setConfirming] = useState(false);
  const [order, setOrder] = useState<InitiateResp | null>(null);
  const [polling, setPolling] = useState(false);
  const [completed, setCompleted] = useState<null | "captured" | "failed" | "cancelled" | "pending">(null);
  const [captureAmount, setCaptureAmount] = useState<number>(0);
  const lastScanRef = useRef<{ data: string; at: number } | null>(null);
  const pollRef = useRef<any>(null);

  // ---------- initial load ----------
  useEffect(() => {
    (async () => {
      try {
        const r = await api.get("/wallet/qr/config");
        setCfg(r.data);
      } catch {
        setCfg(null);
      }
    })();
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ---------- permission ----------
  const askPerm = useCallback(async () => {
    const p = await requestPerm();
    if (!p.granted && !p.canAskAgain) {
      Alert.alert(
        "Camera permission needed",
        "Please enable camera access in Settings to scan UPI QR codes.",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Open Settings", onPress: () => Linking.openSettings() },
        ]
      );
    }
  }, [requestPerm]);

  // ---------- scan handler ----------
  const onScanned = useCallback(async (payload: { data: string; type: string }) => {
    if (!payload?.data || parsing || parsed || order) return;
    // De-dupe rapid re-fires
    const now = Date.now();
    if (lastScanRef.current && lastScanRef.current.data === payload.data && now - lastScanRef.current.at < 2000) return;
    lastScanRef.current = { data: payload.data, at: now };

    setParsing(true);
    setScanning(false);
    try {
      const r = await api.post<ParseResp>("/wallet/qr/parse", { upi_uri: payload.data });
      setParsed(r.data);
      if (r.data.amount) setAmount(String(r.data.amount));
    } catch (e: any) {
      const detail = e?.response?.data?.detail || "Invalid QR code";
      show("error", detail);
      // Allow rescan after brief pause
      setTimeout(() => { setScanning(true); }, 1500);
    } finally {
      setParsing(false);
    }
  }, [parsing, parsed, order, show]);

  // ---------- initiate ----------
  const initiate = useCallback(async () => {
    if (!parsed || !parsed.is_mfb) return;
    const amt = parseFloat(amount);
    if (!amt || amt <= 0) { show("error", "Enter a valid amount"); return; }
    if (cfg && amt < cfg.min_amount) { show("error", `Minimum ${formatINR(cfg.min_amount)}`); return; }
    if (cfg && amt > cfg.max_amount) { show("error", `Maximum ${formatINR(cfg.max_amount)}`); return; }
    setConfirming(true);
    try {
      const r = await api.post<InitiateResp>(
        "/wallet/qr/initiate",
        { upi_uri: reconstructUri(parsed, amt), amount: amt },
        { headers: { "Idempotency-Key": genIdempotencyKey() } },
      );
      setOrder(r.data);
      // Auto-launch UPI intent
      openUpiIntent(r.data.intent_uri, r.data.order.order_id, r.data.order.is_demo);
    } catch (e: any) {
      show("error", e?.response?.data?.detail || "Could not create top-up order");
    } finally {
      setConfirming(false);
    }
  }, [parsed, amount, cfg, show]);

  // ---------- launch UPI + poll ----------
  const openUpiIntent = useCallback(async (intentUri: string, orderId: string, demo?: boolean) => {
    if (demo) {
      // Demo mode: no real UPI app dance — hit the demo capture endpoint directly
      try {
        await api.post(`/payments/demo/capture?order_id=${orderId}&method=upi`);
      } catch (e: any) {
        show("info", "Demo capture failed; polling will still detect final state.");
      }
    } else {
      try {
        const canOpen = await Linking.canOpenURL(intentUri);
        if (!canOpen && Platform.OS === "ios") {
          // iOS may refuse `upi://` without registered LSApplicationQueriesSchemes.
          // Fall back to a web hand-off using the intent URI (some UPI apps accept `?upi_url=`).
          await WebBrowser.openBrowserAsync(intentUri);
        } else {
          await Linking.openURL(intentUri);
        }
      } catch {
        Alert.alert(
          "No UPI app found",
          "Please install Google Pay, PhonePe, Paytm or BHIM to complete this payment.",
        );
      }
    }
    // Begin polling for capture
    setPolling(true);
    let ticks = 0;
    pollRef.current && clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      ticks += 1;
      try {
        const s = await api.get(`/wallet/qr/status/${orderId}`);
        const st = s.data?.status as string | undefined;
        if (st === "captured") {
          clearInterval(pollRef.current);
          setPolling(false);
          setCompleted("captured");
          setCaptureAmount((s.data?.amount_paise || 0) / 100);
          show("success", "Wallet topped up successfully");
        } else if (st === "failed") {
          clearInterval(pollRef.current);
          setPolling(false);
          setCompleted("failed");
          show("error", "Payment failed");
        }
      } catch { /* ignore transient */ }
      if (ticks > 60) { // ~2min
        clearInterval(pollRef.current);
        setPolling(false);
        setCompleted((cur) => cur || "pending");
      }
    }, 2000);
  }, [show]);

  const rescan = useCallback(() => {
    setParsed(null); setOrder(null); setAmount(""); setCompleted(null);
    setPolling(false);
    if (pollRef.current) clearInterval(pollRef.current);
    setScanning(true);
  }, []);

  // ---------- render states ----------
  // 1) Permission gate
  if (!perm) {
    return (
      <View style={[styles.center, { backgroundColor: palette.background }]}>
        <ActivityIndicator size="large" color={palette.primary} />
      </View>
    );
  }
  if (!perm.granted) {
    return (
      <View style={[styles.center, { backgroundColor: palette.background, paddingTop: insets.top + 24 }]}>
        <Pressable style={[styles.back, { top: insets.top + 12 }]} onPress={() => router.back()}>
          <ChevronLeft color={palette.textPrimary} size={22} />
        </Pressable>
        <View style={[styles.permIcon, { backgroundColor: palette.primary + "18" }]}>
          <QrCode color={palette.primary} size={40} />
        </View>
        <Text style={[styles.title, { color: palette.textPrimary }]}>Camera permission needed</Text>
        <Text style={[styles.subtitle, { color: palette.textSecondary }]}>
          MFB uses your camera to scan UPI QR codes for wallet top-up.
          We never store images or scan anything else.
        </Text>
        <Pressable
          style={[styles.primaryBtn, { backgroundColor: palette.primary }]}
          onPress={askPerm}
        >
          <Text style={styles.primaryBtnText}>Enable Camera</Text>
        </Pressable>
        {!perm.canAskAgain && (
          <Pressable
            style={[styles.secondaryBtn, { borderColor: palette.border }]}
            onPress={() => Linking.openSettings()}
          >
            <ExternalLink color={palette.textPrimary} size={16} />
            <Text style={[styles.secondaryBtnText, { color: palette.textPrimary }]}>Open Settings</Text>
          </Pressable>
        )}
      </View>
    );
  }

  // 2) Completed / status screen
  if (completed) {
    const isOk = completed === "captured";
    return (
      <View style={[styles.center, { backgroundColor: palette.background, paddingTop: insets.top + 24 }]}>
        <View style={[styles.permIcon, { backgroundColor: isOk ? palette.success + "22" : palette.warning + "22" }]}>
          {isOk ? <CheckCircle2 color={palette.success} size={48} /> : <AlertTriangle color={palette.warning} size={48} />}
        </View>
        <Text style={[styles.title, { color: palette.textPrimary }]}>
          {isOk ? "Top-up successful" : completed === "failed" ? "Payment failed" : completed === "cancelled" ? "Payment cancelled" : "Still processing"}
        </Text>
        {isOk && <Text style={[styles.amountBig, { color: palette.success }]}>{formatINR(captureAmount)}</Text>}
        <Text style={[styles.subtitle, { color: palette.textSecondary }]}>
          {isOk
            ? "Your wallet has been credited. Reference: " + (order?.order.receipt || "").slice(0, 20)
            : completed === "pending"
              ? "We haven't received a confirmation yet. It usually settles within a minute — you'll get a notification."
              : "No amount was debited from your bank."}
        </Text>
        <Pressable
          style={[styles.primaryBtn, { backgroundColor: palette.primary }]}
          onPress={() => router.replace("/(tabs)/wallet")}
        >
          <Text style={styles.primaryBtnText}>Back to Wallet</Text>
        </Pressable>
        {!isOk && (
          <Pressable style={[styles.secondaryBtn, { borderColor: palette.border }]} onPress={rescan}>
            <RotateCcw color={palette.textPrimary} size={16} />
            <Text style={[styles.secondaryBtnText, { color: palette.textPrimary }]}>Try again</Text>
          </Pressable>
        )}
      </View>
    );
  }

  // 3) Waiting for UPI app to return (order created, polling)
  if (order) {
    return (
      <View style={[styles.center, { backgroundColor: palette.background, paddingTop: insets.top + 24 }]}>
        <View style={[styles.permIcon, { backgroundColor: palette.primary + "18" }]}>
          <Wallet color={palette.primary} size={40} />
        </View>
        <Text style={[styles.title, { color: palette.textPrimary }]}>Complete in your UPI app</Text>
        <Text style={[styles.subtitle, { color: palette.textSecondary }]}>
          Return to MFB after paying. We&apos;ll credit your wallet automatically once we receive confirmation.
        </Text>
        {polling && (
          <View style={{ flexDirection: "row", gap: 10, alignItems: "center", marginBottom: 24 }}>
            <ActivityIndicator size="small" color={palette.primary} />
            <Text style={{ color: palette.textSecondary, fontWeight: "700" }}>Waiting for confirmation…</Text>
          </View>
        )}
        <View style={[styles.orderCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Row label="To" value={order.merchant.name} palette={palette} />
          <Row label="UPI ID" value={order.merchant.vpa} palette={palette} mono />
          <Row label="Amount" value={formatINR(order.order.amount_paise / 100)} palette={palette} bold />
          <Row label="Reference" value={(order.order.receipt || order.order.order_id).slice(0, 22)} palette={palette} mono />
        </View>
        <Pressable
          style={[styles.primaryBtn, { backgroundColor: palette.primary }]}
          onPress={() => openUpiIntent(order.intent_uri, order.order.order_id, order.order.is_demo)}
        >
          <Text style={styles.primaryBtnText}>Reopen UPI App</Text>
        </Pressable>
        <Pressable
          style={[styles.secondaryBtn, { borderColor: palette.border }]}
          onPress={() => {
            setCompleted("cancelled");
          }}
        >
          <Text style={[styles.secondaryBtnText, { color: palette.textPrimary }]}>Cancel</Text>
        </Pressable>
      </View>
    );
  }

  // 4) Parsed → confirmation
  if (parsed) {
    const notSupported = !parsed.is_mfb;
    return (
      <ScrollView style={{ backgroundColor: palette.background, flex: 1 }} contentContainerStyle={{ paddingTop: insets.top + 24, paddingBottom: 24, paddingHorizontal: 20 }}>
        <Pressable style={[styles.back, { top: insets.top + 12 }]} onPress={rescan}>
          <ChevronLeft color={palette.textPrimary} size={22} />
        </Pressable>
        <Text style={[styles.headerTitle, { color: palette.textPrimary, marginBottom: 16, marginTop: 8 }]}>Confirm QR</Text>

        {notSupported ? (
          <View style={[styles.notSupportedCard, { backgroundColor: palette.warning + "18", borderColor: palette.warning + "55" }]}>
            <AlertTriangle color={palette.warning} size={40} />
            <Text style={[styles.notSupportedTitle, { color: palette.textPrimary }]}>This QR is not supported for Wallet Top-up</Text>
            <Text style={[styles.notSupportedBody, { color: palette.textSecondary }]}>
              For your safety, we only accept MFB-owned UPI QR codes on this screen. Scanned QR was to:
            </Text>
            <View style={[styles.notSupportedVpaBox, { backgroundColor: palette.background, borderColor: palette.border }]}>
              <Text style={[styles.mono, { color: palette.textPrimary }]}>{parsed.payee_vpa || "—"}</Text>
              {!!parsed.payee_name && <Text style={[styles.notSupportedName, { color: palette.textSecondary }]}>{parsed.payee_name}</Text>}
            </View>
          </View>
        ) : (
          <>
            <View style={[styles.merchantCard, { backgroundColor: palette.primary + "10", borderColor: palette.primary + "44" }]}>
              <View style={[styles.badge, { backgroundColor: palette.success + "22" }]}>
                <ShieldCheck color={palette.success} size={14} />
                <Text style={[styles.badgeText, { color: palette.success }]}>Verified MFB QR</Text>
              </View>
              <Text style={[styles.merchantName, { color: palette.textPrimary }]}>{parsed.payee_name || "My Funding Bank"}</Text>
              <Text style={[styles.mono, { color: palette.textSecondary, marginTop: 4 }]}>{parsed.payee_vpa}</Text>
            </View>

            <Text style={[styles.label, { color: palette.textSecondary }]}>AMOUNT (₹)</Text>
            <TextInput
              value={amount}
              onChangeText={(t) => setAmount(t.replace(/[^0-9.]/g, ""))}
              editable={!parsed.amount}      // If QR has fixed amount, don't let user edit
              keyboardType="decimal-pad"
              style={[
                styles.amountInput,
                {
                  color: palette.textPrimary,
                  borderColor: palette.border,
                  backgroundColor: parsed.amount ? palette.surface : palette.background,
                },
              ]}
              placeholder="0.00"
              placeholderTextColor={palette.textMuted}
            />
            {parsed.amount ? (
              <Text style={[styles.hint, { color: palette.textMuted }]}>
                Amount is fixed in this QR ({formatINR(parsed.amount)})
              </Text>
            ) : (
              <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                {[100, 500, 1000, 2000, 5000].map((v) => (
                  <Pressable key={v} onPress={() => setAmount(String(v))}
                             style={[styles.chip, { borderColor: palette.border, backgroundColor: palette.surface }]}>
                    <Text style={[styles.chipText, { color: palette.textPrimary }]}>₹{v}</Text>
                  </Pressable>
                ))}
              </View>
            )}

            {!!parsed.note && (
              <View style={{ marginTop: 16 }}>
                <Text style={[styles.label, { color: palette.textSecondary }]}>NOTE</Text>
                <Text style={{ color: palette.textPrimary, fontWeight: "700" }}>{parsed.note}</Text>
              </View>
            )}

            <Pressable
              disabled={confirming || !amount || parseFloat(amount) <= 0}
              onPress={initiate}
              style={[styles.primaryBtn, {
                backgroundColor: palette.primary,
                opacity: (confirming || !amount || parseFloat(amount) <= 0) ? 0.5 : 1,
                marginTop: 24,
              }]}
            >
              {confirming
                ? <ActivityIndicator color="#fff" />
                : <Text style={styles.primaryBtnText}>Confirm & Pay {amount ? formatINR(parseFloat(amount) || 0) : ""}</Text>}
            </Pressable>
          </>
        )}

        <Pressable onPress={rescan} style={[styles.secondaryBtn, { borderColor: palette.border, marginTop: 12 }]}>
          <RotateCcw color={palette.textPrimary} size={16} />
          <Text style={[styles.secondaryBtnText, { color: palette.textPrimary }]}>Scan another QR</Text>
        </Pressable>
      </ScrollView>
    );
  }

  // 5) Live camera scanner
  return (
    <View style={{ flex: 1, backgroundColor: "#000" }}>
      <CameraView
        style={StyleSheet.absoluteFillObject}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
        onBarcodeScanned={scanning && !parsing ? onScanned : undefined}
      />
      {/* Overlay */}
      <View pointerEvents="box-none" style={StyleSheet.absoluteFillObject}>
        <View style={[styles.topBar, { paddingTop: insets.top + 6 }]}>
          <Pressable onPress={() => router.back()} style={styles.iconBtn} hitSlop={12}>
            <ChevronLeft color="#fff" size={22} />
          </Pressable>
          <Text style={styles.topBarTitle}>Scan MFB QR</Text>
          <View style={{ width: 36 }} />
        </View>

        <View style={styles.reticleWrap}>
          <View style={styles.reticle}>
            <View style={[styles.corner, styles.tl]} />
            <View style={[styles.corner, styles.tr]} />
            <View style={[styles.corner, styles.bl]} />
            <View style={[styles.corner, styles.br]} />
            {parsing && (
              <View style={styles.parsing}>
                <ActivityIndicator color="#fff" size="large" />
                <Text style={styles.parsingText}>Verifying QR…</Text>
              </View>
            )}
          </View>
          <View style={styles.hintBox}>
            <ScanLine color="#fff" size={16} />
            <Text style={styles.hintText}>
              Align an MFB UPI QR inside the frame
            </Text>
          </View>
        </View>

        <View style={[styles.bottomInfo, { paddingBottom: insets.bottom + 20 }]}>
          <View style={styles.safetyRow}>
            <ShieldCheck color="#4ade80" size={16} />
            <Text style={styles.safetyText}>
              Only MFB QRs are accepted. Third-party QRs are blocked.
            </Text>
          </View>
        </View>
      </View>
    </View>
  );
}

/** Reconstruct a UPI URI from parsed fields + explicit amount for backend init.
 *  We reuse the original URI's payee VPA but override the amount, so a static
 *  QR (no amount) still validates. */
function reconstructUri(p: ParseResp, amount: number): string {
  const parts: Array<[string, string]> = [
    ["pa", p.payee_vpa],
    ["pn", p.payee_name || "MFB"],
    ["am", amount.toFixed(2)],
    ["cu", p.currency || "INR"],
  ];
  if (p.note) parts.push(["tn", p.note]);
  if (p.merchant_code) parts.push(["mc", p.merchant_code]);
  return "upi://pay?" + parts.map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
}

function Row({ label, value, palette, bold, mono }: { label: string; value: string; palette: any; bold?: boolean; mono?: boolean }) {
  return (
    <View style={styles.row}>
      <Text style={[styles.rowLabel, { color: palette.textSecondary }]}>{label}</Text>
      <Text
        style={[
          styles.rowValue,
          { color: palette.textPrimary },
          bold && { fontWeight: "900", fontSize: 15 },
          mono && { fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace" },
        ]}
        numberOfLines={1}
      >
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: 24, gap: 12 },
  back: { position: "absolute", left: 12, width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  permIcon: { width: 96, height: 96, borderRadius: 48, alignItems: "center", justifyContent: "center", marginBottom: 8 },
  title: { fontSize: 22, fontWeight: "900", textAlign: "center", marginTop: 8 },
  subtitle: { fontSize: 14, textAlign: "center", lineHeight: 20, marginBottom: 16, paddingHorizontal: 8 },
  amountBig: { fontSize: 40, fontWeight: "900", marginBottom: 12 },
  primaryBtn: { paddingVertical: 14, paddingHorizontal: 28, borderRadius: 12, alignItems: "center", justifyContent: "center", minWidth: 240 },
  primaryBtnText: { color: "#fff", fontWeight: "900", fontSize: 15 },
  secondaryBtn: { paddingVertical: 12, paddingHorizontal: 24, borderRadius: 12, borderWidth: 1.5, marginTop: 12, flexDirection: "row", alignItems: "center", gap: 8, justifyContent: "center", minWidth: 200 },
  secondaryBtnText: { fontWeight: "800", fontSize: 14 },

  headerTitle: { fontSize: 24, fontWeight: "900", marginTop: 20 },
  label: { fontSize: 11, fontWeight: "800", letterSpacing: 0.5, marginBottom: 6, marginTop: 20 },
  hint: { fontSize: 11, marginTop: 6, fontStyle: "italic" },
  merchantCard: { padding: 16, borderRadius: 16, borderWidth: 1.5, gap: 4, marginTop: 8 },
  merchantName: { fontSize: 18, fontWeight: "900", marginTop: 8 },
  badge: { flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  badgeText: { fontSize: 10, fontWeight: "900", letterSpacing: 0.4 },
  amountInput: { borderWidth: 1.5, borderRadius: 12, paddingHorizontal: 16, paddingVertical: 14, fontSize: 24, fontWeight: "900" },
  chip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1.5 },
  chipText: { fontWeight: "800", fontSize: 13 },
  mono: { fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace", fontSize: 13 },

  notSupportedCard: { padding: 20, borderRadius: 16, borderWidth: 1.5, alignItems: "center", gap: 10 },
  notSupportedTitle: { fontSize: 18, fontWeight: "900", textAlign: "center", marginTop: 6 },
  notSupportedBody: { fontSize: 13, textAlign: "center", lineHeight: 18, marginTop: 2 },
  notSupportedVpaBox: { padding: 12, borderRadius: 10, borderWidth: 1, alignItems: "center", marginTop: 6, minWidth: 220 },
  notSupportedName: { fontSize: 12, marginTop: 4 },

  orderCard: { width: "100%", borderRadius: 16, borderWidth: 1, padding: 16, marginBottom: 20, gap: 8 },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 4 },
  rowLabel: { fontSize: 12, fontWeight: "700", letterSpacing: 0.3 },
  rowValue: { fontSize: 13, fontWeight: "700", maxWidth: 200 },

  topBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: 12, paddingVertical: 8, backgroundColor: "rgba(0,0,0,0.35)" },
  iconBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: "rgba(255,255,255,0.15)", alignItems: "center", justifyContent: "center" },
  topBarTitle: { color: "#fff", fontSize: 15, fontWeight: "900" },
  reticleWrap: { flex: 1, alignItems: "center", justifyContent: "center", gap: 20 },
  reticle: { width: 260, height: 260, borderRadius: 24, position: "relative" },
  corner: { position: "absolute", width: 32, height: 32, borderColor: "#4ade80" },
  tl: { top: 0, left: 0, borderTopWidth: 3, borderLeftWidth: 3, borderTopLeftRadius: 10 },
  tr: { top: 0, right: 0, borderTopWidth: 3, borderRightWidth: 3, borderTopRightRadius: 10 },
  bl: { bottom: 0, left: 0, borderBottomWidth: 3, borderLeftWidth: 3, borderBottomLeftRadius: 10 },
  br: { bottom: 0, right: 0, borderBottomWidth: 3, borderRightWidth: 3, borderBottomRightRadius: 10 },
  parsing: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", gap: 10, backgroundColor: "rgba(0,0,0,0.5)", borderRadius: 24 },
  parsingText: { color: "#fff", fontWeight: "800", fontSize: 13 },
  hintBox: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "rgba(0,0,0,0.5)", paddingHorizontal: 12, paddingVertical: 8, borderRadius: 20 },
  hintText: { color: "#fff", fontSize: 12, fontWeight: "700" },
  bottomInfo: { paddingHorizontal: 20, paddingTop: 12, backgroundColor: "rgba(0,0,0,0.35)" },
  safetyRow: { flexDirection: "row", alignItems: "center", gap: 8, justifyContent: "center" },
  safetyText: { color: "#fff", fontSize: 12, fontWeight: "700" },
});

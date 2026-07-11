/**
 * TradeBottomSheet — reusable modal used by Gold Buy/Sell, Forex Trade, Wallet Top-up,
 * Withdraw Request, SIP / Mutual Fund Investment.
 *
 * Features:
 *   • Snap points via `snap` prop: 40% / 70% / 95% (drag handle to switch)
 *   • Smooth spring animation on open/close
 *   • Drag-to-close + tap-outside-to-dismiss
 *   • KeyboardAvoidingView
 *   • Slot API — parent renders whatever body it needs (amount input, grams preview,
 *     live price, wallet balance, charges, P/L)
 *   • Long-press confirm button (prevents accidental trades)
 *   • Loading + success + failure states are handled by parent via `state`
 */
import React, { useEffect, useRef } from "react";
import {
  View,
  Text,
  StyleSheet,
  Modal,
  Pressable,
  Animated,
  Dimensions,
  KeyboardAvoidingView,
  Platform,
  PanResponder,
  ActivityIndicator,
} from "react-native";
import { CheckCircle2, XCircle, ChevronDown } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import * as Haptics from "expo-haptics";

const { height: SCREEN_H } = Dimensions.get("window");

export type SheetState = "idle" | "submitting" | "success" | "error";
export type SnapPoint = "small" | "medium" | "large";

const SNAP_PCT: Record<SnapPoint, number> = { small: 0.4, medium: 0.7, large: 0.95 };

export function TradeBottomSheet({
  visible,
  onClose,
  title,
  subtitle,
  children,
  snap = "medium",
  onConfirm,
  confirmLabel = "Confirm",
  confirmDisabled = false,
  state = "idle",
  successMessage = "Order placed successfully",
  errorMessage,
  onRetry,
  onSuccessClose,
  accent,
}: {
  visible: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  snap?: SnapPoint;
  onConfirm?: () => void | Promise<void>;
  confirmLabel?: string;
  confirmDisabled?: boolean;
  state?: SheetState;
  successMessage?: string;
  errorMessage?: string;
  onRetry?: () => void;
  onSuccessClose?: () => void;
  accent?: string;
}) {
  const { palette } = useTheme();
  const brand = accent ?? palette.primary;
  const initialTargetH = SCREEN_H * SNAP_PCT[snap];
  const translateY = useRef(new Animated.Value(SCREEN_H)).current;
  const overlayOpacity = useRef(new Animated.Value(0)).current;
  const currentSnap = useRef<SnapPoint>(snap);
  const currentH = useRef<number>(initialTargetH);

  const animateToSnap = (target: SnapPoint) => {
    currentSnap.current = target;
    const targetY = SCREEN_H - SCREEN_H * SNAP_PCT[target];
    currentH.current = SCREEN_H * SNAP_PCT[target];
    Animated.spring(translateY, { toValue: targetY, useNativeDriver: true, damping: 22, mass: 0.9, stiffness: 220 }).start();
  };

  useEffect(() => {
    if (visible) {
      currentSnap.current = snap;
      currentH.current = SCREEN_H * SNAP_PCT[snap];
      translateY.setValue(SCREEN_H);
      overlayOpacity.setValue(0);
      Animated.parallel([
        Animated.spring(translateY, { toValue: SCREEN_H - currentH.current, useNativeDriver: true, damping: 22, mass: 0.9, stiffness: 220 }),
        Animated.timing(overlayOpacity, { toValue: 1, duration: 220, useNativeDriver: true }),
      ]).start();
    }
  }, [visible, snap]);

  const dismiss = () => {
    Animated.parallel([
      Animated.timing(translateY, { toValue: SCREEN_H, duration: 220, useNativeDriver: true }),
      Animated.timing(overlayOpacity, { toValue: 0, duration: 180, useNativeDriver: true }),
    ]).start(() => onClose());
  };

  // Drag handle
  const dragStartY = useRef<number>(0);
  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dy) > 3,
      onPanResponderGrant: () => {
        dragStartY.current = SCREEN_H - currentH.current;
      },
      onPanResponderMove: (_, g) => {
        const next = Math.max(SCREEN_H * 0.05, dragStartY.current + g.dy);
        translateY.setValue(next);
      },
      onPanResponderRelease: (_, g) => {
        const velY = g.vy;
        // Choose nearest snap based on final position
        const finalY = dragStartY.current + g.dy;
        const finalPct = 1 - finalY / SCREEN_H;
        if (velY > 1.5 || finalPct < SNAP_PCT.small - 0.08) {
          dismiss();
          return;
        }
        // pick closest snap
        const targets: SnapPoint[] = ["small", "medium", "large"];
        let best: SnapPoint = "medium";
        let bestDelta = Infinity;
        targets.forEach((t) => {
          const d = Math.abs(finalPct - SNAP_PCT[t]);
          if (d < bestDelta) { bestDelta = d; best = t; }
        });
        animateToSnap(best);
      },
    }),
  ).current;

  return (
    <Modal visible={visible} transparent animationType="none" onRequestClose={dismiss} statusBarTranslucent>
      <View style={StyleSheet.absoluteFill}>
        {/* Overlay */}
        <Animated.View
          style={[StyleSheet.absoluteFill, { backgroundColor: palette.overlay, opacity: overlayOpacity }]}
          pointerEvents={state === "submitting" ? "none" : "auto"}
        >
          <Pressable style={StyleSheet.absoluteFill} onPress={state === "submitting" ? undefined : dismiss} />
        </Animated.View>

        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={StyleSheet.absoluteFill} pointerEvents="box-none">
          <Animated.View
            style={[
              s.sheet,
              {
                backgroundColor: palette.surfaceElevated,
                transform: [{ translateY }],
                height: SCREEN_H * 0.95,
              },
            ]}
          >
            <View {...panResponder.panHandlers} style={s.handleZone}>
              <View style={[s.handle, { backgroundColor: palette.borderStrong }]} />
            </View>

            <View style={s.headerRow}>
              <View style={{ flex: 1 }}>
                <Text style={[s.title, { color: palette.textPrimary }]}>{title}</Text>
                {subtitle ? <Text style={[s.subtitle, { color: palette.textSecondary }]}>{subtitle}</Text> : null}
              </View>
              <Pressable
                onPress={state === "submitting" ? undefined : dismiss}
                style={[s.closeBtn, { backgroundColor: palette.chipBg }]}
                hitSlop={10}
                testID="sheet-close-btn"
              >
                <ChevronDown color={palette.textPrimary} size={18} />
              </Pressable>
            </View>

            {state === "success" ? (
              <View style={s.stateContainer}>
                <View style={[s.stateIcon, { backgroundColor: palette.success + "22" }]}>
                  <CheckCircle2 color={palette.success} size={52} />
                </View>
                <Text style={[s.stateTitle, { color: palette.textPrimary }]}>Success</Text>
                <Text style={[s.stateBody, { color: palette.textSecondary }]}>{successMessage}</Text>
                <Pressable
                  onPress={onSuccessClose ?? dismiss}
                  style={[s.confirmBtn, { backgroundColor: palette.success }]}
                  testID="sheet-success-close"
                >
                  <Text style={s.confirmText}>Done</Text>
                </Pressable>
              </View>
            ) : state === "error" ? (
              <View style={s.stateContainer}>
                <View style={[s.stateIcon, { backgroundColor: palette.danger + "22" }]}>
                  <XCircle color={palette.danger} size={52} />
                </View>
                <Text style={[s.stateTitle, { color: palette.textPrimary }]}>Something went wrong</Text>
                <Text style={[s.stateBody, { color: palette.textSecondary }]}>{errorMessage || "Please try again."}</Text>
                <View style={{ flexDirection: "row", gap: 10, marginTop: 12 }}>
                  <Pressable
                    onPress={dismiss}
                    style={[s.confirmBtn, { backgroundColor: palette.chipBg, flex: 1 }]}
                    testID="sheet-error-cancel"
                  >
                    <Text style={[s.confirmText, { color: palette.textPrimary }]}>Cancel</Text>
                  </Pressable>
                  {onRetry ? (
                    <Pressable
                      onPress={onRetry}
                      style={[s.confirmBtn, { backgroundColor: brand, flex: 1 }]}
                      testID="sheet-error-retry"
                    >
                      <Text style={s.confirmText}>Retry</Text>
                    </Pressable>
                  ) : null}
                </View>
              </View>
            ) : (
              <>
                <View style={{ flex: 1 }}>{children}</View>
                {onConfirm ? (
                  <Pressable
                    onLongPress={async () => {
                      try { await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); } catch {}
                      onConfirm();
                    }}
                    onPress={async () => {
                      // Provide subtle haptic hint that a long-press is required
                      try { await Haptics.selectionAsync(); } catch {}
                    }}
                    delayLongPress={450}
                    disabled={confirmDisabled || state === "submitting"}
                    style={[
                      s.confirmBtn,
                      {
                        backgroundColor: brand,
                        opacity: confirmDisabled || state === "submitting" ? 0.6 : 1,
                      },
                    ]}
                    testID="sheet-confirm-btn"
                  >
                    {state === "submitting" ? (
                      <ActivityIndicator color="#fff" />
                    ) : (
                      <Text style={s.confirmText}>{confirmLabel}</Text>
                    )}
                  </Pressable>
                ) : null}
              </>
            )}
          </Animated.View>
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  sheet: {
    position: "absolute",
    left: 0,
    right: 0,
    top: 0,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingHorizontal: 20,
    paddingBottom: 30,
    gap: 14,
  },
  handleZone: { alignItems: "center", paddingVertical: 10, marginBottom: -4 },
  handle: { width: 44, height: 4, borderRadius: 2 },
  headerRow: { flexDirection: "row", alignItems: "flex-start", gap: 10 },
  title: { fontSize: 20, fontWeight: "800", letterSpacing: -0.4 },
  subtitle: { fontSize: 12, marginTop: 3 },
  closeBtn: { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  confirmBtn: { paddingVertical: 16, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  confirmText: { color: "#fff", fontSize: 15, fontWeight: "800", letterSpacing: 0.3 },
  stateContainer: { flex: 1, alignItems: "center", justifyContent: "center", gap: 10 },
  stateIcon: { width: 96, height: 96, borderRadius: 48, alignItems: "center", justifyContent: "center" },
  stateTitle: { fontSize: 18, fontWeight: "800" },
  stateBody: { fontSize: 13, textAlign: "center", paddingHorizontal: 20 },
});

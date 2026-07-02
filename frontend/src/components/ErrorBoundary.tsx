/**
 * Global ErrorBoundary — catches ANY render/lifecycle error anywhere in the
 * component tree and shows a recoverable fallback instead of an unrecoverable
 * white screen.
 *
 * Placement: wrap the top-level Stack in app/_layout.tsx so it catches errors
 * from every route. Individual screens can optionally add their own inner
 * boundaries around risky sections (native modules, WebViews, streaming).
 *
 * Also intercepts unhandled promise rejections in dev/native so silent async
 * failures at least surface a log line.
 */
import React from "react";
import { View, Text, Pressable, ScrollView, StyleSheet, Platform } from "react-native";

type Props = {
  children: React.ReactNode;
  /** Human-friendly label to help distinguish nested boundaries in logs */
  scope?: string;
  /** Optional custom fallback renderer */
  fallback?: (err: Error, reset: () => void) => React.ReactNode;
};
type State = { err: Error | null };

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { err: null };

  static getDerivedStateFromError(err: Error): State {
    return { err };
  }

  componentDidCatch(err: Error, info: React.ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error(`[ErrorBoundary${this.props.scope ? ":" + this.props.scope : ""}]`, err, info?.componentStack);
  }

  reset = () => this.setState({ err: null });

  render() {
    if (!this.state.err) return this.props.children;
    if (this.props.fallback) return this.props.fallback(this.state.err, this.reset);
    return <DefaultFallback err={this.state.err} onRetry={this.reset} scope={this.props.scope} />;
  }
}

function DefaultFallback({ err, onRetry, scope }: { err: Error; onRetry: () => void; scope?: string }) {
  return (
    <View style={s.container}>
      <View style={s.emoji}><Text style={{ fontSize: 44 }}>🛠️</Text></View>
      <Text style={s.title}>Something went wrong</Text>
      <Text style={s.subtitle}>
        We hit an unexpected error{scope ? ` in ${scope}` : ""}. This has been logged. You can retry
        this screen or restart the app.
      </Text>
      <ScrollView style={s.scroller} contentContainerStyle={{ padding: 12 }}>
        <Text style={s.code} selectable>{err.name}: {err.message}</Text>
        {err.stack ? <Text style={s.stack} selectable>{String(err.stack).split("\n").slice(0, 12).join("\n")}</Text> : null}
      </ScrollView>
      <View style={{ flexDirection: "row", gap: 8, marginTop: 16 }}>
        <Pressable onPress={onRetry} style={[s.btn, s.btnPrimary]}>
          <Text style={s.btnPrimaryTxt}>Try again</Text>
        </Pressable>
      </View>
      <Text style={s.hint}>Platform: {Platform.OS}</Text>
    </View>
  );
}

/**
 * Optional global unhandled-rejection handler. Call once from RootLayout.
 * Prevents silent async failures from becoming untracked crashes on native.
 */
export function attachGlobalErrorHandlers() {
  if (typeof globalThis === "undefined") return;
  const g: any = globalThis;
  if (g.__mfb_error_handlers_attached) return;
  g.__mfb_error_handlers_attached = true;
  try {
    // React Native (Hermes) exposes ErrorUtils. If a JS error bubbles up here
    // the app would normally red-box/crash; log it so QA sees the source.
    const EU = (g as any).ErrorUtils;
    if (EU?.setGlobalHandler) {
      const prev = EU.getGlobalHandler?.();
      EU.setGlobalHandler((error: Error, isFatal: boolean) => {
        // eslint-disable-next-line no-console
        console.error("[global-error]", isFatal ? "FATAL" : "warn", error?.message, error?.stack);
        try { prev?.(error, isFatal); } catch { /* ignore */ }
      });
    }
  } catch { /* ignore */ }
  try {
    // Some RN environments expose promise rejection tracking via HermesInternal
    if (g.HermesInternal?.enablePromiseRejectionTracker) {
      g.HermesInternal.enablePromiseRejectionTracker({
        allRejections: true,
        onUnhandled: (id: number, err: any) => {
          // eslint-disable-next-line no-console
          console.warn("[unhandled-rejection]", id, err?.message || err);
        },
      });
    }
  } catch { /* ignore */ }
}

const s = StyleSheet.create({
  container: {
    flex: 1,
    padding: 20,
    paddingTop: 80,
    backgroundColor: "#0F172A",
    alignItems: "center",
  },
  emoji: { width: 84, height: 84, borderRadius: 42, backgroundColor: "rgba(56,189,248,0.12)", alignItems: "center", justifyContent: "center", marginBottom: 14 },
  title: { color: "#F8FAFC", fontSize: 20, fontWeight: "800" },
  subtitle: { color: "#94A3B8", fontSize: 13, textAlign: "center", marginTop: 6, maxWidth: 320, lineHeight: 19 },
  scroller: { marginTop: 20, maxHeight: 280, width: "100%", backgroundColor: "rgba(148,163,184,0.08)", borderRadius: 12, borderWidth: 1, borderColor: "rgba(148,163,184,0.2)" },
  code: { color: "#F87171", fontSize: 12, fontWeight: "700", fontFamily: Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" }) },
  stack: { color: "#94A3B8", fontSize: 10, marginTop: 8, fontFamily: Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" }) },
  btn: { paddingHorizontal: 24, paddingVertical: 12, borderRadius: 10 },
  btnPrimary: { backgroundColor: "#38BDF8" },
  btnPrimaryTxt: { color: "#0F172A", fontWeight: "800", fontSize: 14 },
  hint: { marginTop: 20, color: "#475569", fontSize: 10 },
});

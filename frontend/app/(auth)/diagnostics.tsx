import React, { useEffect, useState, useCallback } from "react";
import { View, Text, ScrollView, Pressable, ActivityIndicator, Platform } from "react-native";
import { useRouter } from "expo-router";
import * as Clipboard from "expo-clipboard";
import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Application from "expo-application";
import { ChevronLeft, Copy, RefreshCw, CheckCircle2, XCircle, AlertTriangle, Smartphone, Server, Flame, Settings, Cpu, ScrollText } from "lucide-react-native";
import { useTheme } from "@/src/theme/ThemeProvider";
import { Screen } from "@/src/components/Screen";
import { Card } from "@/src/components/Card";
import { useToast } from "@/src/components/Toast";
import { api, BACKEND_URL, API_BASE_URL, isBackendConfigured, describeAxiosError } from "@/src/api/client";
import { isFirebaseAvailable } from "@/src/auth/firebase";

type CheckState = "pending" | "ok" | "fail" | "warn";

type Diag = {
  bundledBackendUrl: string;
  apiBaseUrl: string;
  backendConfigured: boolean;
  pingApiStatus: { state: CheckState; detail: string };
  firebaseStatus: { state: CheckState; detail: string };
  firebaseNativeAvailable: boolean;
  otpReachTest: { state: CheckState; detail: string };
  buildMode: string;
  appOwnership: string;
  platform: string;
  platformVersion: string;
  deviceModel: string;
  deviceBrand: string;
  appVersion: string;
  buildVersion: string;
  applicationId: string;
  bundleId: string;
  timestamp: string;
};

const initial: Diag = {
  bundledBackendUrl: BACKEND_URL,
  apiBaseUrl: API_BASE_URL,
  backendConfigured: isBackendConfigured(),
  pingApiStatus: { state: "pending", detail: "Running…" },
  firebaseStatus: { state: "pending", detail: "Running…" },
  firebaseNativeAvailable: false,
  otpReachTest: { state: "pending", detail: "Tap 'Test OTP reach'" },
  buildMode: __DEV__ ? "development" : "production",
  appOwnership: Constants.appOwnership || "standalone",
  platform: Platform.OS,
  platformVersion: String(Platform.Version),
  deviceModel: Device.modelName || "unknown",
  deviceBrand: Device.brand || "unknown",
  appVersion: Application.nativeApplicationVersion || Constants.expoConfig?.version || "n/a",
  buildVersion: Application.nativeBuildVersion || "n/a",
  applicationId: Application.applicationId || "n/a",
  bundleId: Constants.expoConfig?.android?.package || Constants.expoConfig?.ios?.bundleIdentifier || "n/a",
  timestamp: new Date().toISOString(),
};

export default function Diagnostics() {
  const { palette } = useTheme();
  const router = useRouter();
  const { show } = useToast();
  const [d, setD] = useState<Diag>(initial);
  const [running, setRunning] = useState(false);
  const [otpProbing, setOtpProbing] = useState(false);

  const runAll = useCallback(async () => {
    setRunning(true);
    setD((prev) => ({
      ...prev,
      pingApiStatus: { state: "pending", detail: "Running…" },
      firebaseStatus: { state: "pending", detail: "Running…" },
      firebaseNativeAvailable: false,
      timestamp: new Date().toISOString(),
    }));

    // 1) Ping /api/app/api-status
    let pingResult: { state: CheckState; detail: string };
    if (!isBackendConfigured()) {
      pingResult = { state: "fail", detail: "EXPO_PUBLIC_BACKEND_URL not set — env var was not inlined at build time." };
    } else {
      try {
        const t0 = Date.now();
        const { data, status } = await api.get("/app/api-status", { timeout: 8000 });
        const dt = Date.now() - t0;
        pingResult = {
          state: "ok",
          detail: `HTTP ${status} in ${dt}ms · payload: ${JSON.stringify(data).slice(0, 220)}`,
        };
      } catch (e: any) {
        pingResult = { state: "fail", detail: describeAxiosError(e) };
      }
    }

    // 2) Firebase backend status
    let fbResult: { state: CheckState; detail: string };
    if (!isBackendConfigured()) {
      fbResult = { state: "fail", detail: "Cannot query — backend URL missing." };
    } else {
      try {
        const { data, status } = await api.get("/auth/firebase/status", { timeout: 8000 });
        fbResult = {
          state: data?.enabled ? "ok" : "warn",
          detail: `HTTP ${status} · enabled=${data?.enabled} · provider=${data?.provider || "none"} · ${JSON.stringify(data).slice(0, 200)}`,
        };
      } catch (e: any) {
        fbResult = { state: "fail", detail: describeAxiosError(e) };
      }
    }

    const fbNative = isFirebaseAvailable();

    setD((prev) => ({
      ...prev,
      pingApiStatus: pingResult,
      firebaseStatus: fbResult,
      firebaseNativeAvailable: fbNative,
    }));
    setRunning(false);
  }, []);

  useEffect(() => { runAll(); }, [runAll]);

  const testOtpReach = useCallback(async () => {
    if (!isBackendConfigured()) {
      setD((p) => ({ ...p, otpReachTest: { state: "fail", detail: "Backend URL missing — cannot reach OTP endpoint." } }));
      return;
    }
    setOtpProbing(true);
    setD((p) => ({ ...p, otpReachTest: { state: "pending", detail: "Sending probe…" } }));
    try {
      const t0 = Date.now();
      // Send a probe OTP request with a fake but valid 10-digit number (admin will see it as a demo OTP entry)
      const probeNumber = "9000000099";
      const { data, status } = await api.post("/auth/otp/request", { mobile: probeNumber }, { timeout: 10000 });
      const dt = Date.now() - t0;
      setD((p) => ({
        ...p,
        otpReachTest: {
          state: "ok",
          detail: `✅ HTTP ${status} in ${dt}ms · probe=${probeNumber} · response=${JSON.stringify(data).slice(0, 220)}\n\nNow check Admin → Demo OTPs page — an entry for ${probeNumber} should appear within seconds.`,
        },
      }));
      show("success", `OTP probe sent! Check admin logs for ${probeNumber}`);
    } catch (e: any) {
      setD((p) => ({ ...p, otpReachTest: { state: "fail", detail: describeAxiosError(e) } }));
      show("error", `OTP probe failed: ${describeAxiosError(e)}`);
    } finally {
      setOtpProbing(false);
    }
  }, [show]);

  const copyAll = useCallback(async () => {
    const text = formatDiagnostics(d);
    try {
      await Clipboard.setStringAsync(text);
      show("success", "Diagnostics copied to clipboard");
    } catch (e: any) {
      show("error", `Copy failed: ${e?.message || e}`);
    }
  }, [d, show]);

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ paddingBottom: 60, gap: 12 }}>
        <View style={{ flexDirection: "row", alignItems: "center", marginTop: 4 }}>
          <Pressable onPress={() => router.back()} hitSlop={10} testID="back-btn"><ChevronLeft color={palette.textPrimary} size={26} /></Pressable>
          <Text style={{ fontSize: 22, fontWeight: "800", color: palette.textPrimary, flex: 1, marginLeft: 4 }}>Diagnostics</Text>
          <Pressable onPress={runAll} disabled={running} testID="rerun-btn"
            style={{ flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: palette.primary + "1A", borderWidth: 1, borderColor: palette.primary + "40" }}>
            {running ? <ActivityIndicator size="small" color={palette.primary} /> : <RefreshCw color={palette.primary} size={14} />}
            <Text style={{ color: palette.primary, fontSize: 12, fontWeight: "800" }}>{running ? "Running…" : "Re-run"}</Text>
          </Pressable>
        </View>

        <Text style={{ color: palette.textSecondary, fontSize: 12, marginBottom: 4 }}>
          Use this to verify the APK can reach the backend and Firebase. Tap "Copy diagnostics" and share with the dev team if anything fails.
        </Text>

        {/* Backend URL card */}
        <Card style={{ gap: 10 }}>
          <SectionTitle icon={<Server color={palette.primary} size={16} />} title="Backend URL (bundled at build time)" />
          <RowBig label="EXPO_PUBLIC_BACKEND_URL" value={d.bundledBackendUrl || "(empty / undefined)"} />
          <RowBig label="Computed API base" value={d.apiBaseUrl || "(invalid)"} />
          <Status state={d.backendConfigured ? "ok" : "fail"}
            label={d.backendConfigured ? "BACKEND_URL is configured ✓" : "BACKEND_URL is MISSING — every API call will fail!"} />
        </Card>

        {/* Connectivity ping */}
        <Card style={{ gap: 10 }}>
          <SectionTitle icon={<Smartphone color={palette.primary} size={16} />} title="Backend connectivity (GET /api/app/api-status)" />
          <Status state={d.pingApiStatus.state} label={d.pingApiStatus.detail} />
        </Card>

        {/* Firebase status */}
        <Card style={{ gap: 10 }}>
          <SectionTitle icon={<Flame color="#F97316" size={16} />} title="Firebase status" />
          <Status state={d.firebaseStatus.state} label={d.firebaseStatus.detail} />
          <Row label="Firebase native module available" value={d.firebaseNativeAvailable ? "yes ✓" : "no — running in Expo Go or modules not linked"} />
        </Card>

        {/* OTP reach test */}
        <Card style={{ gap: 10 }}>
          <SectionTitle icon={<ScrollText color={palette.primary} size={16} />} title="OTP reach probe → /api/auth/otp/request" />
          <Status state={d.otpReachTest.state} label={d.otpReachTest.detail} />
          <Pressable onPress={testOtpReach} disabled={otpProbing} testID="test-otp-btn"
            style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 12, borderRadius: 10, backgroundColor: palette.primary, opacity: otpProbing ? 0.6 : 1 }}>
            {otpProbing ? <ActivityIndicator color="#fff" size="small" /> : <Smartphone color="#fff" size={14} />}
            <Text style={{ color: "#fff", fontWeight: "800", fontSize: 13 }}>{otpProbing ? "Probing…" : "Test OTP reach (probe 9000000099)"}</Text>
          </Pressable>
        </Card>

        {/* App + Device + Build */}
        <Card style={{ gap: 8 }}>
          <SectionTitle icon={<Cpu color={palette.primary} size={16} />} title="Build & Device" />
          <Row label="Build mode" value={d.buildMode} />
          <Row label="App ownership" value={d.appOwnership} />
          <Row label="Platform" value={`${d.platform} ${d.platformVersion}`} />
          <Row label="Device" value={`${d.deviceBrand} ${d.deviceModel}`} />
          <Row label="App version" value={d.appVersion} />
          <Row label="Build number" value={d.buildVersion} />
          <Row label="Application ID" value={d.applicationId} />
          <Row label="Configured bundle ID" value={d.bundleId} />
          <Row label="Generated at" value={d.timestamp} />
        </Card>

        {/* Tip card */}
        <Card style={{ gap: 6, backgroundColor: palette.surface }}>
          <SectionTitle icon={<Settings color={palette.textSecondary} size={16} />} title="What to do next" />
          <Tip text='1) If "Backend connectivity" fails → the APK&apos;s BASE_URL is unreachable from your device. Try opening it in your phone&apos;s browser.' />
          <Tip text='2) If "Test OTP reach" shows ✅ but Admin → Demo OTPs has no entry → check that the probe phone matches what admin filters by.' />
          <Tip text="3) If Firebase native module = no → your APK was built without google-services.json or in Expo Go. Re-publish with the file present." />
          <Tip text="4) If Firebase backend returns enabled=true but Phone Auth fails → SHA-1/SHA-256 fingerprint isn't whitelisted yet." />
        </Card>

        <Pressable onPress={copyAll} testID="copy-btn"
          style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingVertical: 14, borderRadius: 12, backgroundColor: palette.success }}>
          <Copy color="#fff" size={16} />
          <Text style={{ color: "#fff", fontWeight: "800", fontSize: 14 }}>Copy diagnostics</Text>
        </Pressable>
      </ScrollView>
    </Screen>
  );
}

function SectionTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  const { palette } = useTheme();
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
      {icon}
      <Text style={{ color: palette.textPrimary, fontWeight: "800", fontSize: 13 }}>{title}</Text>
    </View>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  const { palette } = useTheme();
  return (
    <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 12 }}>
      <Text style={{ color: palette.textSecondary, fontSize: 11, flex: 1 }}>{label}</Text>
      <Text style={{ color: palette.textPrimary, fontSize: 11, fontWeight: "700", flexShrink: 0, maxWidth: "60%" }} numberOfLines={2}>{value}</Text>
    </View>
  );
}

function RowBig({ label, value }: { label: string; value: string }) {
  const { palette } = useTheme();
  return (
    <View>
      <Text style={{ color: palette.textSecondary, fontSize: 10, fontWeight: "700", letterSpacing: 0.8 }}>{label.toUpperCase()}</Text>
      <Text selectable style={{ color: palette.textPrimary, fontSize: 12, fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace", marginTop: 2 }}>{value}</Text>
    </View>
  );
}

function Status({ state, label }: { state: CheckState; label: string }) {
  const { palette } = useTheme();
  const icon = state === "ok"
    ? <CheckCircle2 color={palette.success} size={16} />
    : state === "fail"
      ? <XCircle color={palette.danger} size={16} />
      : state === "warn"
        ? <AlertTriangle color="#F59E0B" size={16} />
        : <ActivityIndicator color={palette.primary} size="small" />;
  const color = state === "ok" ? palette.success : state === "fail" ? palette.danger : state === "warn" ? "#F59E0B" : palette.textSecondary;
  return (
    <View style={{ flexDirection: "row", alignItems: "flex-start", gap: 8 }}>
      <View style={{ marginTop: 2 }}>{icon}</View>
      <Text selectable style={{ color, fontSize: 12, flex: 1, lineHeight: 18 }}>{label}</Text>
    </View>
  );
}

function Tip({ text }: { text: string }) {
  const { palette } = useTheme();
  return <Text style={{ color: palette.textSecondary, fontSize: 11, lineHeight: 17 }}>{text}</Text>;
}

function formatDiagnostics(d: Diag): string {
  return [
    "=== My Funding Bank — Mobile Diagnostics ===",
    `generated_at: ${d.timestamp}`,
    "",
    `BACKEND_URL: ${d.bundledBackendUrl || "(empty)"}`,
    `API_BASE_URL: ${d.apiBaseUrl || "(invalid)"}`,
    `backendConfigured: ${d.backendConfigured}`,
    "",
    `ping_api_status: ${d.pingApiStatus.state} — ${d.pingApiStatus.detail}`,
    `firebase_backend_status: ${d.firebaseStatus.state} — ${d.firebaseStatus.detail}`,
    `firebase_native_available: ${d.firebaseNativeAvailable}`,
    `otp_reach_test: ${d.otpReachTest.state} — ${d.otpReachTest.detail}`,
    "",
    `build_mode: ${d.buildMode}`,
    `app_ownership: ${d.appOwnership}`,
    `platform: ${d.platform} ${d.platformVersion}`,
    `device: ${d.deviceBrand} ${d.deviceModel}`,
    `app_version: ${d.appVersion}`,
    `build_number: ${d.buildVersion}`,
    `application_id: ${d.applicationId}`,
    `configured_bundle_id: ${d.bundleId}`,
    "",
    "=== end ===",
  ].join("\n");
}

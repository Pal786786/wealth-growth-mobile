import { Stack, useRouter } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect, useRef } from "react";
import { Platform } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import * as Linking from "expo-linking";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { ThemeProvider } from "@/src/theme/ThemeProvider";
import KycRequiredModal from "@/src/components/KycRequiredModal";
import { AuthProvider } from "@/src/auth/AuthProvider";
import { ToastProvider } from "@/src/components/Toast";
import { ErrorBoundary, attachGlobalErrorHandlers } from "@/src/components/ErrorBoundary";

// Splash: guard against unhandled rejection on Android release.
SplashScreen.preventAutoHideAsync().catch(() => {});

// Attach global JS error / promise handlers exactly once. Must run before
// any UI renders so that even boot-time errors are captured.
attachGlobalErrorHandlers();

/**
 * Configure expo-notifications AFTER the app has mounted (never at module
 * scope). Module-scope Promise rejections on Android release with Hermes have
 * previously caused the app to whitescreen on boot.
 */
function useNotificationsBootstrap(): void {
  const router = useRouter();
  const configuredRef = useRef(false);

  useEffect(() => {
    if (Platform.OS === "web" || configuredRef.current) return;
    configuredRef.current = true;

    let Notifications: any = null;
    try {
      // eslint-disable-next-line @typescript-eslint/no-require-imports
      Notifications = require("expo-notifications");
    } catch (e) {
      // native module not present (Expo Go without dev-client) — non-fatal
      console.log("[push] expo-notifications not available:", String(e));
      return;
    }

    // Handler must be a synchronous set; wrap in try so a shape change doesn't
    // crash the boot sequence.
    try {
      Notifications.setNotificationHandler({
        handleNotification: async () => ({
          // shouldShowAlert is DEPRECATED in expo-notifications >=0.32 — using
          // the new banner/list flags. Keeping only the modern fields to avoid
          // "unknown option" warnings and native TypeError on some builds.
          shouldPlaySound: true,
          shouldSetBadge: false,
          shouldShowBanner: true,
          shouldShowList: true,
        }),
      });
    } catch (e) {
      console.warn("[push] setNotificationHandler failed:", String(e));
    }

    if (Platform.OS === "android") {
      // ALWAYS attach .catch() to module-level Promises. On Android release
      // an unhandled rejection here previously blank-screened the app on boot.
      try {
        const p = Notifications.setNotificationChannelAsync?.("default", {
          name: "Default",
          importance: Notifications.AndroidImportance?.MAX ?? 5,
          sound: "default",
        });
        if (p && typeof p.catch === "function") {
          p.catch((e: any) => console.warn("[push] setNotificationChannelAsync failed:", String(e)));
        }
      } catch (e) {
        console.warn("[push] channel setup skipped:", String(e));
      }
    }

    // Foreground tap listener
    let sub: { remove: () => void } | undefined;
    try {
      sub = Notifications.addNotificationResponseReceivedListener?.((response: any) => {
        try {
          const data = response?.notification?.request?.content?.data || {};
          const url = data.deeplink || data.action_url;
          if (!url) return;
          if (typeof url === "string" && url.startsWith("http")) Linking.openURL(url).catch(() => {});
          else router.push(url);
        } catch (e) {
          console.warn("[push] response handler failed:", String(e));
        }
      });
    } catch (e) {
      console.warn("[push] addNotificationResponseReceivedListener failed:", String(e));
    }

    // Cold-start tap
    try {
      const p = Notifications.getLastNotificationResponseAsync?.();
      if (p && typeof p.then === "function") {
        p.then((response: any) => {
          if (!response) return;
          const data = response.notification?.request?.content?.data || {};
          const url = data.deeplink || data.action_url;
          if (!url) return;
          if (typeof url === "string" && url.startsWith("http")) Linking.openURL(url).catch(() => {});
          else router.push(url);
        }).catch((e: any) => console.warn("[push] getLastNotificationResponseAsync failed:", String(e)));
      }
    } catch (e) {
      console.warn("[push] cold-start check skipped:", String(e));
    }

    return () => {
      try { sub?.remove(); } catch { /* ignore */ }
    };
  }, [router]);
}

export default function RootLayout() {
  const [loaded, error] = useIconFonts();
  useNotificationsBootstrap();

  useEffect(() => {
    if (loaded || error) {
      SplashScreen.hideAsync().catch(() => {});
    }
  }, [loaded, error]);

  // Guard: if fonts genuinely fail (network offline), show the app anyway
  // after 4s so the user never sees a permanent splash.
  useEffect(() => {
    const t = setTimeout(() => { SplashScreen.hideAsync().catch(() => {}); }, 4000);
    return () => clearTimeout(t);
  }, []);

  if (!loaded && !error) return null;

  return (
    <ErrorBoundary scope="Root">
      <GestureHandlerRootView style={{ flex: 1 }}>
        <SafeAreaProvider>
          <ErrorBoundary scope="Providers">
            <ThemeProvider>
              <AuthProvider>
                <ToastProvider>
                  <ErrorBoundary scope="Navigator">
                    <Stack
                      screenOptions={{
                        headerShown: false,
                        animation: "slide_from_right",
                        contentStyle: { backgroundColor: "transparent" },
                      }}
                    />
                  </ErrorBoundary>
                  <KycRequiredModal />
                </ToastProvider>
              </AuthProvider>
            </ThemeProvider>
          </ErrorBoundary>
        </SafeAreaProvider>
      </GestureHandlerRootView>
    </ErrorBoundary>
  );
}

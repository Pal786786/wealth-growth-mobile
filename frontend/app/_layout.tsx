import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { Platform } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { useRouter } from "expo-router";
import * as Linking from "expo-linking";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { ThemeProvider } from "@/src/theme/ThemeProvider";
import KycRequiredModal from "@/src/components/KycRequiredModal";
import { AuthProvider } from "@/src/auth/AuthProvider";
import { ToastProvider } from "@/src/components/Toast";

SplashScreen.preventAutoHideAsync();

// --- Push notifications: module-scope setup (per Emergent Push playbook) ---
// Guarded so web preview doesn't crash and so missing google-services.json
// doesn't throw during Expo Go / dev-client boot.
if (Platform.OS !== "web") {
  // Lazy require so web bundle stays slim
  try {
    const Notifications = require("expo-notifications");
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldPlaySound: true,
        shouldSetBadge: false,
        // expo-notifications >=0.32 uses banner/list flags too
        shouldShowBanner: true,
        shouldShowList: true,
      }),
    });
    if (Platform.OS === "android") {
      Notifications.setNotificationChannelAsync("default", {
        name: "Default",
        importance: Notifications.AndroidImportance.MAX,
        sound: "default",
      });
    }
  } catch (e) {
    // Silently ignore — push not available (e.g. Expo Go without dev-client)
    // eslint-disable-next-line no-console
    console.log("[push] expo-notifications setup skipped:", String(e));
  }
}

export default function RootLayout() {
  const [loaded, error] = useIconFonts();
  const router = useRouter();

  useEffect(() => {
    if (loaded || error) SplashScreen.hideAsync();
  }, [loaded, error]);

  useEffect(() => {
    if (Platform.OS === "web") return;
    let cleanup: (() => void) | undefined;
    try {
      const Notifications = require("expo-notifications");
      // Warm tap — user taps notification while app is open
      const sub = Notifications.addNotificationResponseReceivedListener((response: any) => {
        const data = response?.notification?.request?.content?.data || {};
        const url = data.deeplink || data.action_url;
        if (!url) return;
        url.startsWith("http") ? Linking.openURL(url) : router.push(url);
      });
      // Cold-start tap — user tapped notification while app was killed
      Notifications.getLastNotificationResponseAsync().then((response: any) => {
        if (!response) return;
        const data = response.notification?.request?.content?.data || {};
        const url = data.deeplink || data.action_url;
        if (url) (url.startsWith("http") ? Linking.openURL(url) : router.push(url));
      });
      cleanup = () => sub.remove();
    } catch (e) {
      // Push not available — non-fatal
    }
    return cleanup;
  }, [router]);

  if (!loaded && !error) return null;

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <ThemeProvider>
          <AuthProvider>
            <ToastProvider>
              <Stack
                screenOptions={{
                  headerShown: false,
                  animation: "slide_from_right",
                  contentStyle: { backgroundColor: "transparent" },
                }}
              />
              <KycRequiredModal />
            </ToastProvider>
          </AuthProvider>
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

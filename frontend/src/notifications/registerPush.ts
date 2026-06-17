/**
 * Push registration helper — call after successful login.
 *
 * Demo-safe: silently no-ops on web and when expo-notifications/native modules
 * are unavailable. Backend stores the token even if Emergent push relay isn't
 * configured, so when google-services.json is uploaded and the app is rebuilt,
 * tokens flow upstream automatically.
 */
import { Platform } from "react-native";
import { api } from "@/src/api/client";

export async function registerForPush(userId: string): Promise<{ status: string; reason?: string }> {
  if (Platform.OS === "web") return { status: "skipped", reason: "web" };
  try {
    const Notifications = require("expo-notifications");
    const { status: existing } = await Notifications.getPermissionsAsync();
    let granted = existing === "granted";
    if (!granted) {
      const { status } = await Notifications.requestPermissionsAsync();
      granted = status === "granted";
    }
    if (!granted) return { status: "denied" };
    const tokenResp = await Notifications.getDevicePushTokenAsync();
    if (!tokenResp?.data) return { status: "no_token" };
    await api.post("/register-push", {
      user_id: userId,
      platform: Platform.OS,
      device_token: tokenResp.data,
    });
    return { status: "registered" };
  } catch (e) {
    return { status: "error", reason: String(e).slice(0, 120) };
  }
}

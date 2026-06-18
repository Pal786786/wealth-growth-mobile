/**
 * Firebase Phone Auth helper — uses lazy require so the bundle still works in
 * Expo Go (where @react-native-firebase native modules are NOT available).
 *
 * In Expo Go: `isFirebaseAvailable()` returns false → callers fall back to
 *             the demo / MSG91 OTP flow.
 * In dev / production build (after google-services.json is uploaded via
 *             Emergent Publish): native modules link properly → full Phone Auth works.
 */

import Constants from "expo-constants";

const isExpoGo = Constants.appOwnership === "expo";

let _authMod: any = null;
let _appMod: any = null;
let _initTried = false;

function loadModules(): { app: any; auth: any } | null {
  if (isExpoGo) return null;
  if (!_initTried) {
    _initTried = true;
    try {
      _appMod = require("@react-native-firebase/app").default;
      _authMod = require("@react-native-firebase/auth").default;
    } catch (e) {
      console.warn("[firebase] native modules unavailable:", e);
      return null;
    }
  }
  if (!_authMod) return null;
  return { app: _appMod, auth: _authMod };
}

export function isFirebaseAvailable(): boolean {
  return loadModules() !== null;
}

export async function sendFirebaseOtp(phoneE164: string): Promise<any> {
  const mod = loadModules();
  if (!mod) throw new Error("Firebase Phone Auth requires a dev/production build (not Expo Go).");
  // signInWithPhoneNumber returns a confirmation object whose confirm(code) returns UserCredential
  return await mod.auth().signInWithPhoneNumber(phoneE164);
}

export async function confirmFirebaseOtp(confirmation: any, code: string): Promise<string> {
  if (!confirmation || typeof confirmation.confirm !== "function") {
    throw new Error("No active confirmation. Request OTP first.");
  }
  const credential = await confirmation.confirm(code);
  if (!credential?.user) throw new Error("OTP verification failed");
  // getIdToken(true) forces a fresh token
  const idToken: string = await credential.user.getIdToken(true);
  return idToken;
}

export async function getFirebaseIdToken(forceRefresh = false): Promise<string | null> {
  const mod = loadModules();
  if (!mod) return null;
  const u = mod.auth().currentUser;
  if (!u) return null;
  return await u.getIdToken(forceRefresh);
}

export async function signOutFirebase(): Promise<void> {
  const mod = loadModules();
  if (!mod) return;
  try { await mod.auth().signOut(); } catch {}
}

/**
 * Best-effort FCM token retrieval. Returns null in Expo Go.
 */
export async function getFcmToken(): Promise<string | null> {
  if (isExpoGo) return null;
  try {
    const msg = require("@react-native-firebase/messaging").default;
    const authStatus = await msg().requestPermission();
    const enabled = authStatus === 1 || authStatus === 2; // AUTHORIZED | PROVISIONAL
    if (!enabled) return null;
    const token = await msg().getToken();
    return token || null;
  } catch (e) {
    console.warn("[firebase] FCM unavailable:", e);
    return null;
  }
}

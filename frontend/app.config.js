// Dynamic Expo config — only enables Firebase plugins when google-services.json
// exists AND its `client[].client_info.android_client_info.package_name` matches the
// configured Android package. The Emergent build pipeline overrides the Android
// package name (e.g. to `app.emergent.wealthgrowthmobile76f1c650`), so a hand-uploaded
// `google-services.json` for `com.myfundingbank.app` would fail the Gradle
// `processReleaseGoogleServices` step with:
//   "No matching client found for package name 'app.emergent.<slug>...'"
// Strip the Firebase plugins automatically in that case so the build succeeds —
// the app gracefully falls back to backend/demo OTP (already wired).
const fs = require("fs");
const path = require("path");
const base = require("./app.json");

const root = __dirname;
const androidServicesPath = path.join(root, "google-services.json");
const iosServicesPath = path.join(root, "GoogleService-Info.plist");

const hasAndroidGoogleServices = fs.existsSync(androidServicesPath);
const hasIosGoogleServices = fs.existsSync(iosServicesPath);

const expo = { ...base.expo };

// Determine the *effective* Android package at build time. EAS / Emergent may
// override `expo.android.package` via `EAS_BUILD_RUNNER_PACKAGE_NAME` or
// `expo.android.package` directly in app.json. We compare against the JSON file.
const effectiveAndroidPackage =
  process.env.EAS_BUILD_RUNNER_PACKAGE_NAME ||
  process.env.ANDROID_PACKAGE ||
  (expo.android && expo.android.package) ||
  "";

let androidGoogleServicesUsable = hasAndroidGoogleServices;
if (hasAndroidGoogleServices && effectiveAndroidPackage) {
  try {
    const j = JSON.parse(fs.readFileSync(androidServicesPath, "utf8"));
    const clients = (j && j.client) || [];
    const match = clients.some(
      (c) => c && c.client_info && c.client_info.android_client_info &&
              c.client_info.android_client_info.package_name === effectiveAndroidPackage,
    );
    if (!match) {
      // eslint-disable-next-line no-console
      console.warn(
        `[app.config] google-services.json has no client for package '${effectiveAndroidPackage}'. ` +
        `Stripping Firebase plugins to keep the build green. App will use backend/demo OTP fallback.`,
      );
      androidGoogleServicesUsable = false;
    }
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn("[app.config] google-services.json unreadable:", e.message);
    androidGoogleServicesUsable = false;
  }
}

const firebaseEnabled = androidGoogleServicesUsable || hasIosGoogleServices;

// Strip googleServicesFile references when the file is missing OR unusable for this build
if (!androidGoogleServicesUsable && expo.android) {
  // eslint-disable-next-line no-unused-vars
  const { googleServicesFile, ...androidRest } = expo.android;
  expo.android = androidRest;
}
if (!hasIosGoogleServices && expo.ios) {
  // eslint-disable-next-line no-unused-vars
  const { googleServicesFile, ...iosRest } = expo.ios;
  expo.ios = iosRest;
}

// Strip Firebase plugins entirely if no usable credentials at all
if (!firebaseEnabled && Array.isArray(expo.plugins)) {
  expo.plugins = expo.plugins.filter((p) => {
    const name = typeof p === "string" ? p : p && p[0];
    return !(typeof name === "string" && name.startsWith("@react-native-firebase/"));
  });
}

module.exports = { expo };

// Dynamic Expo config — only enables Firebase plugins when google-services.json exists.
// This prevents EAS prebuild from failing when the credentials file hasn't been uploaded yet.
const fs = require("fs");
const path = require("path");
const base = require("./app.json");

const root = __dirname;
const hasAndroidGoogleServices = fs.existsSync(path.join(root, "google-services.json"));
const hasIosGoogleServices = fs.existsSync(path.join(root, "GoogleService-Info.plist"));
const firebaseEnabled = hasAndroidGoogleServices || hasIosGoogleServices;

const expo = { ...base.expo };

// Strip googleServicesFile references if the actual file is missing — prevents prebuild crash
if (!hasAndroidGoogleServices && expo.android) {
  const { googleServicesFile, ...androidRest } = expo.android;
  expo.android = androidRest;
}
if (!hasIosGoogleServices && expo.ios) {
  const { googleServicesFile, ...iosRest } = expo.ios;
  expo.ios = iosRest;
}

// Strip Firebase plugins (they require google-services.json at prebuild time)
if (!firebaseEnabled && Array.isArray(expo.plugins)) {
  expo.plugins = expo.plugins.filter((p) => {
    const name = typeof p === "string" ? p : p?.[0];
    return !(typeof name === "string" && name.startsWith("@react-native-firebase/"));
  });
}

module.exports = { expo };

# Firebase Release SHA Fingerprint — Whitelisting Guide

After you generate a signed Android APK via Emergent **Publish → Android → Generate APK**, Firebase Phone Auth (real OTP SMS) will only work on devices once the release certificate's SHA-1 / SHA-256 fingerprints are added to the Firebase Console.

Until then, your APK will silently fall back to **Demo OTP mode** (the same one served via the in-app Admin Demo OTPs page).

---

## Step 1 — Extract SHA fingerprints from the new APK

Run this on the downloaded APK (replace path):

```bash
keytool -printcert -jarfile MyFundingBank-release.apk
```

Look for two lines in the output:

```
SHA1: AA:BB:CC:DD:...   (40 hex pairs)
SHA256: AA:BB:CC:DD:... (64 hex pairs)
```

> **Alternative** (if Emergent provides the keystore): you can also run  
> `keytool -list -v -keystore <your-keystore.jks> -alias <alias>`  
> to get the same values.

---

## Step 2 — Add fingerprints to Firebase Console

1. Go to **https://console.firebase.google.com/** → select project **My Funding Bank**.
2. Click the **gear icon** → **Project settings**.
3. Scroll to **Your apps** → select the Android app (package name `com.myfundingbank.app`, or whatever is in `app.json` → `expo.android.package`).
4. Under **SHA certificate fingerprints**, click **Add fingerprint**.
5. Paste the **SHA-1** value (no spaces, colons OK) → click **Save**.
6. Click **Add fingerprint** again → paste the **SHA-256** value → click **Save**.

You should now see both entries listed.

---

## Step 3 — Regenerate `google-services.json` (REQUIRED)

The SHA fingerprints are baked into the `google-services.json` config file.

1. In the same Android app card, click **Download google-services.json**.
2. Replace the file at `/app/frontend/google-services.json` with the newly downloaded copy.
3. Commit & redeploy — the next APK build will include the new fingerprints.

> **Do not skip this step** — if you only add fingerprints in the console but reuse the old `google-services.json`, the device will still fall back to Demo mode.

---

## Step 4 — Verify on a real device

1. Install the new APK on an Android phone (sideload via `adb install MyFundingBank-release.apk` or share the file directly).
2. On the login screen, enter a real 10-digit phone number.
3. You should receive an SMS OTP via Firebase Phone Auth (within ~10 seconds).
4. Confirm successful login.

**Troubleshooting**

| Symptom | Likely cause |
|---|---|
| OTP shows up on `/api/admin/demo-otps` instead of SMS | Fingerprints missing OR old `google-services.json` bundled |
| `Token mismatch` error on verify | Forgot to redeploy after replacing `google-services.json` |
| "Quota exceeded for Phone Auth" | Firebase free tier limit (10 SMS/day). Upgrade to Blaze plan in Firebase. |
| App crashes on launch | `applicationId` in `app.json` does not match Firebase Android app's package name |

---

## Quick reference

| Field | Where |
|---|---|
| Android package | `/app/frontend/app.json` → `expo.android.package` |
| `google-services.json` | `/app/frontend/google-services.json` (tracked in git) |
| Demo OTP fallback page | Admin → **Demo OTPs** (`/api/admin-ui/demo-otps`) |
| Phone Auth backend status | `GET /api/auth/firebase/status` |

---

## Debug vs. Release fingerprints

Expo's **development build** uses a debug keystore with a well-known SHA. The **release APK** is signed with a fresh keystore created by Emergent's build service. Each keystore produces a unique SHA pair, so you must add the release fingerprints separately. (The debug ones — if previously added — can stay; just don't remove them.)

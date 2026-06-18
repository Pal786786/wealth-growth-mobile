# Firebase Phone Auth + FCM Integration — My Funding Bank

## ✅ What's been implemented

### Backend (`/app/backend/firebase_auth.py`)
- **`GET /api/auth/firebase/status`** — mobile pre-flight check (returns `{enabled, provider, project_id, force_demo}`)
- **`POST /api/auth/firebase/verify`** — accepts a Firebase ID token, verifies signature via Google's public JWK certs (NO service-account JSON needed), looks up / creates user, issues MFB JWT
- ID-token verification:
  - Validates RS256 signature against Google's rotating public certs (cached in-memory with TTL from `Cache-Control` header)
  - Checks `iss == https://securetoken.google.com/<project_id>`
  - Checks `aud == <project_id>`
  - Validates `exp`, `iat`, `auth_time`
  - Requires non-empty `phone_number` claim
- Stores `firebase_uid` and `auth_provider="firebase"` on user record (so re-login via OTP/email still works)

### Mobile (`/app/frontend/src/auth/firebase.ts`)
- `isFirebaseAvailable()` — detects if native modules are linked (false in Expo Go)
- `sendFirebaseOtp(phoneE164)` — calls `signInWithPhoneNumber`
- `confirmFirebaseOtp(confirmation, code)` — confirms OTP and returns ID token
- `getFcmToken()` — fetches FCM device token (after permission)
- `signOutFirebase()` — clears Firebase session
- All native imports are **lazy** so Expo Go bundle doesn't crash

### Mobile (`/app/frontend/app/(auth)/otp.tsx`)
- On mount → calls `/auth/firebase/status` → picks provider automatically
- Provider precedence: `firebase` (if enabled AND native modules available) → `msg91` / `twilio` / `demo`
- Firebase path: `sendFirebaseOtp(+91…)` → user enters OTP → `confirmFirebaseOtp()` → POSTs ID token to backend → backend issues MFB JWT
- Graceful fallback: if Firebase fails (e.g. Expo Go) → automatically degrades to demo OTP

### Config (`/app/frontend/app.json`)
- `android.googleServicesFile: "./google-services.json"` ← uploaded via Publish flow
- `ios.googleServicesFile: "./GoogleService-Info.plist"` ← uploaded via Publish flow
- Plugins: `@react-native-firebase/app`, `@react-native-firebase/auth`, `@react-native-firebase/messaging`
- Package name: `com.myfundingbank.app`

### `.gitignore`
- `google-services.json` and `GoogleService-Info.plist` are excluded (these contain Firebase API keys; uploaded only via Publish)

---

## 🔧 Provider Switching (3 modes, no redeploy needed)

| Provider | How to enable | Use case |
|---|---|---|
| **demo** | Admin → API Management → SMS Provider → check **Force demo** | Local testing, no DLT |
| **msg91** | Provider field = `msg91` + Auth Key + DLT Sender ID + Template ID | India production (post-DLT) |
| **twilio** | Provider field = `twilio` + Auth Token + Account SID + From number | International prod |
| **firebase** | Provider field = `firebase` + Firebase Project ID (only field needed) | Cross-platform mobile |

`force_demo=true` always overrides — Demo OTPs always work as a safety net.

---

## 📱 How to publish the Android APK with Firebase

### Step 1 — Confirm Firebase project setup
- Firebase Console → Authentication → Sign-in method → **Phone** = enabled
- Firebase Console → Project Settings → **Your apps** → Android app with package `com.myfundingbank.app`
- **SHA-1 + SHA-256** registered (extract via the keytool instructions in earlier session)

### Step 2 — Configure backend
1. Open Admin → **API Management** → **SMS Provider** card
2. Set: `provider = firebase`, `firebase_project_id = <your-firebase-project-id>` (found in `google-services.json` → `project_info.project_id`)
3. **Uncheck** "Force demo"
4. Save

### Step 3 — Click Emergent Publish button (top-right)
1. Choose **Android**
2. When prompted, **upload `google-services.json`**
3. (Optional) Upload `GoogleService-Info.plist` for iOS
4. Click **Generate Build**
5. Wait ~5–10 min for signed APK/AAB
6. Download and install on a real device (NOT Expo Go)

### Step 4 — Test on device
1. Open app → Login → "Sign in with mobile"
2. Enter your registered test phone number from Firebase Console (or real number with DLT-approved template)
3. Native reCAPTCHA / Play Integrity check may flash briefly
4. SMS arrives via Firebase
5. Enter the 6-digit OTP → app calls `/api/auth/firebase/verify` → receives MFB JWT → lands on Home

### Step 5 — If something fails
- **"Token signed by unknown key"**: Backend caches certs for 1h. If your Firebase project just rotated keys, restart backend or wait.
- **"Token audience mismatch"**: `firebase_project_id` in API Management doesn't match the Firebase project the mobile app is configured for. Check `google-services.json` → `project_info.project_id`.
- **"Token has no phone_number"**: User signed in via Google/Facebook etc. instead of Phone Auth. Use the right Firebase SDK call.
- **"INVALID_APP_CREDENTIAL"** on mobile: SHA-1/SHA-256 fingerprint missing in Firebase Console → re-add the production fingerprints.

---

## ⚠️ Reality check: DLT for production India

Firebase Phone Auth uses Google's carrier-routed SMS. For **production India**, you still need DLT registration because:
- TRAI fines apply to Google's local carrier delivery
- Above 10k SMS/month free tier, Firebase routes through your DLT-approved sender ID
- Solution: Either complete DLT (7-15 days) OR use Firebase only for testing + switch to MSG91/Twilio for production

For testing right now with a small set of test numbers (registered in Firebase Console → Authentication → Phone → **Phone numbers for testing**), Firebase is free and DLT-exempt.

---

## 🛡️ Demo OTP fallback (always available)
- When **Force demo** is checked in admin → all OTP requests use demo mode regardless of provider config
- OTPs appear on **Admin → Demo OTPs** page (auto-refreshing every 5s)
- This is the safety net for QA / staging / when external providers fail

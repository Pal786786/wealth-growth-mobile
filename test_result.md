#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  Add centralized API Management + Demo Mode to the My Funding Bank admin dashboard
  (and surface a demo banner on the mobile app). Admin must be able to add/edit API
  keys for Stripe, Razorpay, SMS, Email, Stock Market, Mutual Fund, Gold, Flight,
  Hotel, Push & KYC; enable/disable each; force-demo; and test connection. When a
  key is missing, the integration auto-falls-back to demo data — no errors shown.

backend:
  - task: "API Settings registry + CRUD endpoints (api_settings.py)"
    implemented: true
    working: true
    file: "/app/backend/api_settings.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "New module with catalog of 11 supported integrations. Endpoints: GET /api/admin/api-settings (list), PUT /api/admin/api-settings/{name} (upsert key/enable/force-demo), POST /api/admin/api-settings/{name}/test (test connection — never raises), GET /api/app/api-status (public status feed for mobile banner). Manual curl tests passed for list/update/disable/clear."
  - task: "Refactor Stripe & Alpha Vantage to use centralized api_settings"
    implemented: true
    working: true
    file: "/app/backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "Stripe top-up now reads key dynamically from api_settings (fallback to env, then to demo). Stripe errors now degrade to demo top-up instead of HTTP 502. Alpha Vantage stocks read key dynamically and add mode flag. /invest/gold-price respects api_settings + manual override."

frontend:
  - task: "Admin: API Management page + nav + global demo banner"
    implemented: true
    working: true
    file: "/app/admin/src/pages/ApiManagement.tsx, /app/admin/src/pages/Layout.tsx, /app/admin/src/main.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "New Settings → API Management page with stats cards (Live/Demo/Disabled), grouped table by category, expandable rows with masked key, extra fields, force-demo toggle, Test Connection, Enable/Disable, Save. Global amber banner + header badge shown when any_demo>0. Built with `yarn build`, served at /api/admin-ui/."
  - task: "Mobile: Demo Mode banner on Home"
    implemented: true
    working: true
    file: "/app/frontend/app/(tabs)/index.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "Home tab now calls /api/app/api-status alongside dashboard + banners. When any_demo=true, shows yellow Demo Mode card with count badge above the hero. Verified visually in preview."

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 2
  run_ui: true

test_plan:
  current_focus:
    - "API Settings registry + CRUD endpoints (api_settings.py)"
    - "Refactor Stripe & Alpha Vantage to use centralized api_settings"
    - "Admin: API Management page + nav + global demo banner"
    - "Mobile: Demo Mode banner on Home"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
    -agent: "main"
    -message: |
      Implemented full API Management + Demo Mode system.
      Backend additions:
        • /app/backend/api_settings.py (new module)
        • Wired into /app/backend/server.py (router + startup seed)
        • Stripe & Alpha Vantage now read key dynamically — graceful demo fallback
        • Public endpoint /api/app/api-status for mobile banner
      Admin UI:
        • New /api-management route with full CRUD + Test Connection
        • Global Demo Mode banner & header badge in Layout
        • Sidebar nav entry "API Management"
        • Built: /app/admin/dist updated
      Mobile UI:
        • Home tab shows Demo Mode banner with count when any integration is in demo
      Test credentials in /app/memory/test_credentials.md (admin@mfb.in / Admin@MFB2026; demo@mfb.in / demo1234).
      Please verify:
        1) Admin login → /api-management → list, expand Stripe row, save fake key (sk_test_abcdefghijk1234567), test connection (will fail), then clear key. Verify status badge updates without page reload.
        2) Toggle force_demo on Razorpay → verify status="demo" even with key set.
        3) Disable a row → verify status="disabled" and mobile /api/app/api-status reflects it.
        4) Mobile (web preview): login as demo@mfb.in/demo1234 → home should show Demo Mode banner.
        5) Existing flows still work: wallet top-up (should auto-fallback to demo), stocks list (should still load with live cache), notifications, banners, KYC.

backend_v2:
  - task: "AI Investment Suggestions endpoint (ai_invest.py)"
    implemented: true
    working: true
    file: "/app/backend/ai_invest.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "Uses Emergent LLM key + Claude Sonnet 4.6 to return personalised JSON with overall_summary, risk_score, risk_label, recommendations (buy/hold/sell + confidence + reason), suggested_sip, next_steps, disclaimer. Falls back to rule-based suggestion when LLM fails or key absent. Per-user cache (30 min) stored in MongoDB ai_suggestions collection. Manual curl tests passed: live mode returns rich Claude output in ~17s; cached call returns in 14ms with cached=true."

frontend_v2:
  - task: "Mobile: AI Investment Coach screen + teaser card"
    implemented: true
    working: true
    file: "/app/frontend/app/invest/ai-coach.tsx, /app/frontend/app/(tabs)/invest.tsx"
    stuck_count: 0
    priority: "high"
    needs_retesting: true
    status_history:
        -working: true
        -agent: "main"
        -comment: "New /invest/ai-coach screen with purple-pink hero, Today's snapshot card, risk profile bar, recommendation cards (BUY/HOLD/SELL badges with confidence dots), suggested SIP card, next steps list, disclaimer, refresh button. Teaser card with gradient added to Invest > Portfolio tab. Verified visually — Claude generates real recommendations (RELIANCE/HDFCBANK/TCS as BUY with reasons)."

agent_communication_v2:
    -agent: "main"
    -message: |
      Built AI Investment Suggestions feature.
      Backend: /app/backend/ai_invest.py uses emergentintegrations LlmChat with claude-sonnet-4-6. Endpoint GET /api/invest/ai-suggestions (auth required), optional ?refresh=true. Per-user 30-min MongoDB cache. Rule-based fallback when LLM unavailable.
      Mobile: New screen /app/frontend/app/invest/ai-coach.tsx with hero, snapshot, recommendations, SIP card. Teaser card on Invest tab Portfolio view.
      Creds: demo@mfb.in / demo1234 (mobile); admin@mfb.in / Admin@MFB2026 (admin).
      Verify: (1) endpoint returns full JSON shape; (2) 2nd call cached=true <200ms; (3) ?refresh=true bypasses cache; (4) mobile teaser → AI Coach screen renders; (5) existing flows unaffected.


## Forex Regression Fix — 2026-07-02

**User-reported issues:**
1. Blank white screen after tapping BUY/SELL on symbol detail
2. Orders not being placed
3. Price inconsistency: Watchlist (2343) vs Order screen (2341) vs TradingView chart (4074)

**Root causes & fixes:**

1. **Symbol detail infinite spinner (blank white screen)**  
   Root cause: `Promise.all([symbols(), balance()])` in `/app/frontend/app/forex/symbol/[id].tsx` — if `balance()` returned 401 (auth expired) or any error, the whole promise rejected and `setSymbol()` was never called → `symbol` stayed `null` → infinite `<ActivityIndicator>` → looked like a blank white screen.  
   Fix: Split `loadSymbol()` (public, must succeed) from `loadBalance()` (silently ignores failure). Added a retry CTA if symbol lookup itself errors.

2. **Price inconsistency (2343 vs 4074)**  
   Root cause: Watchlist + Order used our simulated feed with June-2024 starting anchors (`XAUUSD: 2340.50`, `BTCUSD: 67400`), while the chart embedded a TradingView WebView pointing at OANDA:XAUUSD which shows LIVE 2026 market prices (~$4070). Two different data sources = guaranteed mismatch.  
   Fix:  
   - Updated starting prices in `/app/backend/forex/symbols.py` to realistic June-2026 anchors (XAUUSD=4070, BTCUSD=102000, EURUSD=1.145, GBPUSD=1.345, USDJPY=158.5).  
   - Added an in-memory ring buffer (300 pts, ~10 min at 2s tick) to `PriceFeed` capturing every tick.  
   - New public endpoint `GET /api/forex/candles/{symbol_id}?limit=100` returning `[{ts,mid}]`.  
   - Replaced the TradingView `WebView` with a new `<FeedChart />` (React Native SVG) which pulls history + appends live `quote.mid` on every 2s tick. **Watchlist, order screen and chart now share ONE source of truth.**  
   - Updated the watchlist arrow anchor map in `/app/frontend/app/(tabs)/forex.tsx` to match new starting prices.

3. **Orders not placing (symptom cascade of #1)**  
   Root cause: with `symbol=null` the trade ticket never rendered; and even after login the BUY/SELL button was disabled because `canTrade = q && lot > 0 && balance >= margin` — with balance stuck at 0 the button stayed disabled.  
   Fix: symbol now renders even when balance fails, so button becomes enabled once auth loads.

4. **Log noise:** Binance WS retries every 30s on region-blocked pods. Detected HTTP 451/403 → stop retrying instead of exponential backoff forever.

**Files touched:**
- `/app/backend/forex/symbols.py` — starting prices
- `/app/backend/forex/feed.py` — ring buffer + seeded history + `get_history`
- `/app/backend/forex/routes.py` — `GET /api/forex/candles/{symbol_id}`
- `/app/backend/forex/providers.py` — Binance region-block short-circuit
- `/app/frontend/src/api/forex.ts` — `candles()` client
- `/app/frontend/src/components/FeedChart.tsx` — new SVG chart
- `/app/frontend/app/forex/symbol/[id].tsx` — split loads + FeedChart
- `/app/frontend/app/(tabs)/forex.tsx` — updated arrow anchor map

**Verified via curl on the demo user (KYC-approved):**
- BUY 0.1 XAUUSD → entry 3936.79, margin ₹100 ✅
- Close position → P&L computed −₹1660 ✅
- SELL 0.01 BTCUSD with TP=90000/SL=110000 → entry 101769.05 ✅
- `/api/forex/candles/XAUUSD` returns rolling price history ✅


## Forex Regression Iter16 — Sprint 6 GA Sign-off — 2026-07-02

### Additional cleanup this round
- Removed `_tv_symbol()` helper from `/app/backend/forex/routes.py`
- Removed `tradingview_symbol` field from `/api/forex/symbols` response
- Removed `tradingview_symbol` from `ForexSymbol` TS type
- Removed dead `tradingViewHTML` stub from `symbol/[id].tsx`
- Added new **GET /api/forex/equity** endpoint → `{balance, unrealized_pnl, equity, margin_used, free_margin, open_position_count, currency}`
- Added `forexApi.equity()` client method

### Testing_agent iter16 result — retest_needed: false
- Backend: **41/42 pass** (1 non-deterministic skip for TP auto-close on random walk)
- Frontend: 100% pass on iter16 changes
- All 6 price read points on symbol detail confirmed synchronized (chart, marker, BID, ASK, SELL btn, BUY btn) 
- Equity math reconciles: `equity == balance + unrealized_pnl`; `free_margin == equity - margin_used`
- Zero "tradingview" mentions in any API response
- Zero console errors during full BUY→open→close flow
- No regressions in wallet, kyc, ai advisor, notifications, market dashboard, admin panel

### Signed off checklist (user-requested)
- [x] BUY order executes
- [x] SELL order executes
- [x] No blank/white screen / crash
- [x] Watchlist = Order screen = Chart = P&L = Equity = Trade History (same feed)
- [x] Margin, spread, TP, SL, balance, equity, floating P&L math correct
- [x] Open positions live-update
- [x] Close position works
- [x] Trade history records all completed trades
- [x] Refresh preserves open positions & history (persisted in MongoDB)
- [x] No console/API/React errors

**Sprint 6 (Live Market Intelligence Dashboard) — READY to be marked complete.**

## Project Stabilization Sprint (P0) — 2026-07-02

### User report
Latest APK crashes on real Android device. Modules affected: Push Notification screen, AI Advisor, Forex, "multiple other". Previous APK was more stable. User asked for full-code stabilization sweep (proceed blind — no logcat available).

### Root causes identified
1. **NO GLOBAL ERROR BOUNDARY.** Any component throw in `app/_layout.tsx` tree caused whole-tree unmount → white screen. Root cause of the majority of reported "crashes".
2. **Module-scope unhandled Promise** in `_layout.tsx`: `Notifications.setNotificationChannelAsync()` was called at module scope with no `.catch()`. On Android Hermes release builds this bubbles up as an unhandled rejection during bundle boot and can whitescreen the app.
3. **Deprecated `shouldShowAlert: true`** flag on expo-notifications ≥ 0.32. Some builds throw instead of warn.
4. **`advisor/index.tsx` dead setState** — `x.message_id === ev` compared string ID to event object → no-op that also broke unmount cleanup timing. Also caused an incorrect wasted render on every delta.
5. **`kyc/index.tsx` STATUS_MAP guard missing** — if server returned an unknown status enum, `info` was `undefined` → `info.Icon` / `info.color` crashed the entire KYC screen render.
6. **`notifications/index.tsx` Alert.alert** — passed `undefined` as message. Some Android release builds throw TypeError on undefined args.
7. **`streamChat` fragility** — SecureStore promise had no `.catch()`; XHR constructor errors were unhandled; SSE parse errors could bubble.

### Fixes applied
- Added `/app/frontend/src/components/ErrorBoundary.tsx` with three-tier nesting (Root, Providers, Navigator) + `attachGlobalErrorHandlers()` that installs an ErrorUtils global handler and Hermes unhandled-rejection tracker.
- Rewrote `/app/frontend/app/_layout.tsx`:
  - Notifications setup now runs post-mount inside `useNotificationsBootstrap()` (never at module scope).
  - `setNotificationChannelAsync` Promise has `.catch()`.
  - Deprecated `shouldShowAlert` removed — only modern `shouldShowBanner`+`shouldShowList` remain.
  - Every native call defensively wrapped so a Promise chain never surfaces to the boot path.
  - 4-second splash-screen safety timeout so users never see a stuck splash.
- Fixed `/app/frontend/app/advisor/index.tsx` delta handling.
- Guarded `/app/frontend/app/kyc/index.tsx` STATUS_MAP against unknown enums.
- Fixed `/app/frontend/app/notifications/index.tsx` Alert.alert to pass `""` not `undefined`.
- Hardened `/app/frontend/src/api/advisor.ts` streamChat with try/catch around XHR init, SecureStore `.catch()`, SSE parse guards, and cancellation-safe abort.

### Files modified
- `app/frontend/src/components/ErrorBoundary.tsx` (new)
- `app/frontend/app/_layout.tsx` (rewrite)
- `app/frontend/app/advisor/index.tsx`
- `app/frontend/app/kyc/index.tsx`
- `app/frontend/app/notifications/index.tsx`
- `app/frontend/src/api/advisor.ts`

### Post-fix boot check
- Web preview boots cleanly to Onboarding screen — no white screen, no ErrorBoundary triggered.
- Lint clean on all touched files.

### Testing_agent regression run — pending (about to invoke)

### Iter18 verification — PASSED, sprint closed
- Preferences fix verified: unauth returns "Preferences unavailable" + Retry (was infinite spinner). Auth path: all toggles work.
- Smoke of 6 stabilization landings: onboarding, /forex/symbol/XAUUSD, /advisor (graceful SSE fail), /kyc (STATUS_MAP guard), /notifications empty-state, /market — all pass.
- Backend: login/prefs/GET/PUT all 200.
- testing_agent: retest_needed=false, `/app/test_reports/iteration_18.json`.

### Files modified in stabilization sprint
- `app/frontend/src/components/ErrorBoundary.tsx` (new — 3-tier global boundary + attachGlobalErrorHandlers)
- `app/frontend/app/_layout.tsx` (rewrite — module-scope side-effects moved to useEffect, catch on Promises, 4s splash safety)
- `app/frontend/app/advisor/index.tsx` (dead setState fix)
- `app/frontend/app/kyc/index.tsx` (STATUS_MAP undefined guard)
- `app/frontend/app/notifications/index.tsx` (Alert.alert undefined→"")
- `app/frontend/app/notifications/preferences.tsx` (catch + Retry fallback UI)
- `app/frontend/src/api/advisor.ts` (streamChat hardening — XHR try/catch, SecureStore .catch, cancellation-safe abort)

### Next step for the user
Publish a fresh APK via Emergent → install → reproduce the previous crash scenarios. The likelihood of white-screen crashes should be dramatically reduced. If a crash still occurs, the new ErrorBoundary will display the stack trace on-screen (paste that back to us).

## Objects-as-React-child crash — 2026-07-02

### Root cause (surfaced by iter17 ErrorBoundary)
Backend returned KYC_REQUIRED payload as an OBJECT under `response.data.detail`:
```
{ code, message, current_status, action_url, completion_required }
```
Every screen used the pattern `show("error", e?.response?.data?.detail || "...")` — passing the object to the Toast, which then rendered `<Text>{toast.message}</Text>` and crashed React with **"Objects are not valid as a React child"**.

### Fix — 4-layer defense
1. **utils/errors.ts** (new) — exports `safeStr()` and `errText()` for safe stringification of any value. Understands FastAPI validation arrays, KYC_REQUIRED objects, plain axios errors and unknown shapes.
2. **kycGate interceptor** — after emitting KYC_REQUIRED event, REWRITES `response.data.detail` from object → string (`message` field extracted, or JSON-stringified fallback). Original object preserved under `response.data.detailRaw`. This means every downstream `catch` handler receives a **string** in `detail`, so no other file needs to change.
3. **Toast.show** — coerces any incoming `message` via `safeStr()` before storing in state. Belt-and-braces so even if some future call site bypasses the interceptor, we still won't crash.
4. **Stateful `<Text>{err}</Text>` renderers** — wrapped in `safeStr(err)` at the call sites in `kyc/index.tsx` and `(auth)/forgot-password.tsx`. Their `setErr` calls updated to use `errText(e)`.

### Files modified
- `app/frontend/src/utils/errors.ts` (new)
- `app/frontend/src/api/kycGate.ts` (interceptor normalization)
- `app/frontend/src/components/Toast.tsx` (defensive coerce)
- `app/frontend/app/kyc/index.tsx` (safeStr + errText)
- `app/frontend/app/(auth)/forgot-password.tsx` (safeStr + errText)

### Testing plan
- testing_agent to reproduce the KYC_REQUIRED path: attempt a gated action (e.g. `POST /api/forex/positions` as a non-KYC user) and verify the response now surfaces the KycRequiredModal AND the toast shows `payload.message` (string) — no React crash.

### Iter19 verification — PASSED
- **Layer 1**: `safeStr` + `errText` never throw across all input shapes.
- **Layer 2**: `Toast.show(any)` coerces via `safeStr`.
- **Layer 3**: `kycGate` interceptor rewrites `detail` object → string, preserves original at `detailRaw`.
- **Layer 4**: `kyc/index.tsx` + `forgot-password.tsx` `<Text>` sites wrap in `safeStr`.
- **E2E**: 0 occurrences of "Objects are not valid as a React child", 0 ErrorBoundary triggers, 0 white screens.
- pytest: `/app/backend/tests/test_kyc_gate_iter19.py` 3/3 pass. Full report `/app/test_reports/iteration_19.json`.

Stabilization sprint fully closed. Ready for a fresh APK build.

## Hotfix 2026-07-02 — Notification crash + Remove KYC from non-withdrawal

### Bug 1: Notification screen crash
`TypeError: Cannot read property 'toUpperCase' of undefined` at renderItem when a notification record lacked `category` (or other) field.

**Fix in `app/frontend/app/notifications/index.tsx` renderItem:**
- Every field defensively defaulted at the top of the render (`category`, `title`, `body`, `read`, `priority`, `notif_id`, `created_at`).
- `keyExtractor` falls back to index and `_id` when `notif_id` is missing.
- `openNotif` gracefully returns on null.
- `shortDate` in `src/utils/format.ts` now accepts `null | undefined`, checks `isNaN`, and never throws.

### Bug 2: KYC gating too aggressive
Business flow correction — KYC should ONLY be enforced at Withdrawal.

**Backend endpoints — removed `require_kyc_approved`:**
- `POST /api/wallet/send` (`server.py:413`)
- `POST /api/wallet/recharge` (`server.py:433`)
- `POST /api/wallet/billpay` (`server.py:456`)
- `POST /api/wallet/topup/create-session` (Stripe deposit) (`server.py:485`)
- `POST /api/wallet/payments/create` (Razorpay deposit) (`wallet_module.py:365-370`)
- `POST /api/forex/positions` (BUY/SELL) (`forex/routes.py:187-193`)

**KYC still enforced on:**
- Withdrawal flow — `wallet_module.attach(kyc_gate=...)` passes into `withdrawal_module`, which calls `kyc_gate(u)` on `/wallet/withdrawals/bank-accounts`, `/wallet/withdrawals/request`, `/wallet/withdrawals/verify-otp`.

**Curl verification (fresh non-KYC user):**
- `POST /api/forex/positions XAUUSD buy 0.01` → 200 ✅ (entry_price=4003.15, margin=₹10)
- `POST /api/wallet/send ₹50` → 200 ✅
- `POST /api/wallet/withdrawals/request` → 403 KYC_REQUIRED ✅ (correctly blocked)

### Iter20 verification — BOTH HOTFIXES PASS
- Backend pytest: 14/14 (`test_iter20_kyc_removal.py`)
- (A) Notifications: seeded 4 malformed docs → all render, 0 crashes, 0 `toUpperCase` errors.
- (B) KYC removal: fresh non-KYC user → 200 on forex BUY/SELL/close, wallet/send, wallet/recharge, wallet/billpay, wallet/topup/create-session, wallet/payments/create. UI renders trade ticket with no KYC modal.
- (C) Withdrawal KYC gate holds: 403 KYC_REQUIRED on /wallet/withdrawals/request + /bank-accounts; passes after DB approval.
- Full report: `/app/test_reports/iteration_20.json`

Ready for APK build.

## Iter21 — Broader stabilization audit (P0 re-report)

User re-reported the same 2 P0 issues (Notifications toUpperCase crash + Forex KYC block). Most likely their installed APK was built BEFORE iter20 fixes landed. Nevertheless expanded the fix to guard EVERY `.toUpperCase()` and audit all remaining KYC gates.

### Additional unsafe field accesses guarded (potential future crashes)
- `/app/frontend/app/market/[symbol].tsx:48` — `q.category.toUpperCase()` → `String(q.category ?? "market").toUpperCase()`
- `/app/frontend/app/market/index.tsx:128` — `n.category.toUpperCase()` → `String(n?.category ?? "news").toUpperCase()`
- `/app/frontend/app/market/index.tsx:151` — `e.impact.toUpperCase()` → `String(e?.impact ?? "low").toUpperCase()`
- `/app/frontend/app/(tabs)/travel.tsx:56` — `type[0].toUpperCase()` → guarded with `(type || "trip").charAt(0)`
- `/app/frontend/app/(tabs)/travel.tsx:245` — `bk.booking_type.toUpperCase()` → guarded with `String(bk?.booking_type ?? "trip")`

### KYC state — final audit
Only ONE gate remains, on the exact endpoint per user requirement:
- `/wallet/withdrawals/request` (line 230) — KYC gate PRESENT ✅ (user submits withdrawal)

Removed additionally in iter21:
- `/wallet/withdrawals/bank-accounts` (add-bank) — kyc_gate removed. User can save bank accounts anytime; KYC only prompts at actual withdrawal.

### Curl end-to-end (fresh non-KYC user)
| Action | HTTP | Notes |
|---|---|---|
| Signup | 200 | new token issued |
| Forex BUY XAUUSD 0.01 | **200** ✅ | position opened |
| Invest buy ₹100 | **200** ✅ | holding created |
| Wallet topup /create-session ₹500 | **200** ✅ | demo Stripe session |
| Add bank account | **200** ✅ | bank_id returned |
| Withdrawal request | **403** ✅ | KYC_REQUIRED (correctly blocked) |

Every other module already had NO KYC gate — /invest/buy, /forex/positions, /wallet/send, /wallet/recharge, /wallet/billpay, /wallet/payments/create, /wallet/topup/create-session.

### Iter21 verification — PASS (retest_needed: false)
- Backend pytest 11/11 (`test_iter21_kyc_bank_accounts.py`)
- All iter20 renderItem guards intact + 5 new iter21 toUpperCase guards land.
- Fresh non-KYC user gets 200 on 9 non-withdrawal endpoints incl. bank-accounts add. 403 only on withdrawals/request.
- Playwright E2E: signup → notifications (3 malformed docs) → market → advisor → kyc → forex/symbol — zero crashes, zero KYC modal on non-withdrawal flows.
- Full report: `/app/test_reports/iteration_21.json`.

## Sprint 7 Slice 1 — Live Market Data Foundation

### What ships
- **Scalable catalog** (`/app/backend/market_data/catalog.py`) — 96 instruments across 8 categories today (Forex Majors 7, Minors 21, Exotics 15, Metals 4, Energies 3, Indices 10, Crypto 30, Commodities 6). Schema is open-ended; adding new categories/instruments requires only a list append.
- **Provider abstraction** (`providers.py`) — `BaseProvider` + `MockProvider` + `TwelveDataProvider` (real HTTPS adapter, activates only when API key set). Registry factory `build_provider(name, settings)`. Extensible for Alpha Vantage / Finnhub / Polygon / Kite Connect / Upstox.
- **Transport abstraction** (`transports.py`) — `PollingTransport` (default) and `WebSocketTransport` (falls back to polling until provider WS is wired). Admin switches by name.
- **Routes** (`routes.py`) under `/api/market_data/*`:
  - GET `/categories`, `/catalog?category=&search=&page=&limit=`, `/symbols/{id}`, `/quote/{id}`, `/quotes?symbols=`, `/history/{id}`
  - GET/POST/DEL `/favorites`, `/favorites/{id}` (persisted per user)
  - POST/GET `/recently-viewed`
  - **WebSocket `/ws/stream`** — subscribe/unsubscribe protocol, transport-agnostic
  - Admin: `/api/admin/market_data/status` + `PUT /settings` + `POST /test-provider`
- **Mobile UI** — new `/market/symbols` browser: category tabs auto-generated from `/categories`, debounced search, virtualized FlatList, favorite star toggle, infinite scroll pagination, live prices via WebSocket with polling fallback, LIVE/POLL/idle status indicator. "Browse all" CTA added to `/market` dashboard.
- **Admin panel** — new `AdminMarketData.tsx` at `/#/market-data` with provider dropdown, transport dropdown, poll interval, API keys (masked), diagnostics viewer, catalog stats. Vite build produced and copied to `backend/static/admin-ui`.

### No regression
- `backend/forex/*` untouched. Existing BUY/SELL, watchlist, positions, KYC-only-on-withdrawal all unchanged.
- Existing `market_module.py` (Sprint 6 dashboard, news, calendar, watchlist) untouched.

### Backend curl verification
- `/api/market_data/categories` → 8 categories with counts, HTTP 200.
- `/api/market_data/catalog?category=forex_majors` → 7 items page 1.
- `/api/market_data/catalog?search=bit` → BTC/USD, BCH/USD, ARB/USD (relevance-ordered).
- `/api/market_data/quote/XAUUSD` → mid=4069.93, source=mock, HTTP 200.
- `/api/market_data/quotes?symbols=XAUUSD,BTCUSD,EURUSD,SOLUSD` → 4 quotes.
- Favorites add/list roundtrip for demo user → persisted in `market_favorites` collection.
- Recently viewed roundtrip → persisted in `market_recent` collection.
- WebSocket `/ws/stream` — Playwright shows LIVE status on `/market/symbols`, prices tick every 3s.

### Files added / modified
- **New**: `backend/market_data/{__init__,catalog,providers,transports,routes}.py`, `frontend/src/api/marketData.ts`, `frontend/src/hooks/useMarketStream.ts`, `frontend/app/market/symbols.tsx`, `admin/src/pages/AdminMarketData.tsx`
- **Modified**: `backend/server.py` (attach), `frontend/app/market/index.tsx` (Browse-all CTA), `admin/src/main.tsx` (route), `admin/src/pages/Layout.tsx` (nav)

### Iter22 + Iter23 verification — Sprint 7 Slice 1 COMPLETE
- **Iter22**: 25/27 backend pytest + 100% frontend Playwright pass. Two follow-ups:
  - P1 (blocking): PUT /api/admin/market_data/settings 500 due to nested Pydantic model
  - P2 (cosmetic): 4× 401 console warnings on unauth /market/symbols load
- **Iter23 retest** (after main-agent fix): 
  - **Backend 27/27 pytest pass** (`test_market_data.py`) + **5/5** on the new admin-put fix (`test_iter23_admin_put.py`)
  - Frontend: 0 favorites-load warnings on unauth load, LIVE badge + prices streaming.
  - Regression: forex/notifications/kyc/advisor all clean; non-KYC forex 200, non-KYC withdrawal 403.
  - Report: `/app/test_reports/iteration_23.json` — `retest_needed: false`

## Sprint 7B.1 — Copy Trading Foundation (Discover & Follow)

### Ships
- **28 deterministic trader personas** with realistic profiles (name/country/style/bio/experience/verified). Same numbers across restarts — driven by `random.Random(persona.seed)` throughout `traders.py`.
- **Statistics generator** (deterministic) — Total/Monthly/Weekly/Annual ROI, Win Rate, Profit Factor, Sharpe, Recovery Factor, Max DD, Avg Holding, Avg Lot, Followers, AUM, Expectancy, Avg Win/Loss.
- **Risk Engine** — 1–10 score + tier (Conservative/Moderate/Aggressive), derived from drawdown, win rate, volatility, position size, holding time.
- **Equity + Balance curves** (12 months, daily). **Monthly ROI** array (12 months).
- **Open + Closed trade history** (deterministic per persona).
- **Copy Engine** — Mongo-persisted `copy_relationships` per (user, trader): status (active/paused/stopped), settings (mode, fixed_lot, multiplier, equity_percent, max_daily_loss_pct, max_drawdown_pct, max_open_trades, equity_protection_pct, auto_close_on_stop).
- **Broker Adapter abstraction** — `BrokerAdapter` base + `PaperBroker` default + placeholder classes for MetaTrader 5, DXtrade, cTrader, MatchTrader, Custom.
- **Server-side sorting** — sort=total_roi/monthly_roi/win_rate/followers/risk/new + search + verified filter + risk range.
- **HTTP endpoints** under `/api/copy_trading/*`:
  - GET `/traders` (leaderboard, paginated), `/traders/{id}` (profile), `/open-trades`, `/closed-trades`
  - GET `/my/copies`, `/traders/{id}/copy`
  - POST `/copy/start`, `/copy/pause`, `/copy/resume`, `/copy/stop`
  - PUT `/copy/settings`
  - GET `/meta`
- **Mobile UI** — `/traders` leaderboard (sort chips, search, verified toggle, ranked list with avatars + flags + stats) + `/traders/[id]` profile (hero, 12-stat grid, gradient equity curve, monthly bars, Overview/Open/History tabs, bottom Copy CTA + settings modal).
- **Home tab** — new "Copy Traders" quick-action tile.

### No regression
- backend/{forex, wallet, notifications, kyc, market_module, market_data}.py — untouched.
- KYC still enforced only on `/wallet/withdrawals/request`.

### Curl verification
- 28 traders, sort works, determinism (identical stats on repeat call).
- Copy lifecycle: start → pause → stop reflected in DB.
- Screenshots verified — leaderboard and profile pages render, avatars/flags/curves visible.

### Iter24 verification — Sprint 7B.1 PASSED
- Backend pytest: **27/27** (`test_copy_trading_iter24.py`) incl. determinism-across-restart P0 check.
- Frontend Playwright: leaderboard + profile + copy lifecycle all verified.
- Regression: forex, wallet, kyc, notifications, market, market_data — all 200.
- Minor cosmetic (settings sheet button label when relationship is `stopped`) — fixed.
- Report: `/app/test_reports/iteration_24.json` — retest_needed: false.

---

## Iteration 25 — Sprint 7B.2 (Copy Execution Engine) — 2026-06

### Scope
Event-driven Copy Execution Engine on top of the 7B.1 foundation.
- Master Simulator (28 traders auto-trading) → EventBus → CopyEngine fan-out → PaperBroker
- 3 execution modes: Fixed Lot, Multiplier, Equity %
- Full risk protection: Max Daily Loss, Max Drawdown, Equity Protection, Max Open Trades
- Admin control: pause/resume simulation, speed (slow/normal/fast), force-open, force-close
- My Copies dashboard + individual copy detail with mirrored trade history

### Backend changes
- `/app/backend/copy_trading/events.py` — EventBus + TradeEvent (in-process asyncio pub/sub)
- `/app/backend/copy_trading/config.py` — CopyConfig singleton (mongo-backed, admin-editable)
- `/app/backend/copy_trading/broker.py` — BrokerAdapter interface + PaperBroker (persists follower trades) + MT5/DXtrade/cTrader/MatchTrader/Custom placeholders
- `/app/backend/copy_trading/simulator.py` — MasterSimulator (per-trader background tasks driven by style intervals + hold durations, admin pause/resume/speed/force-open)
- `/app/backend/copy_trading/engine.py` — CopyEngine (subscribes to bus, fans out to followers; risk halts; my_summary; follower_trades; my_copies_enriched)
- `/app/backend/copy_trading/routes.py` — extended with `/my/summary`, `/my/trades`, `/my/copies/pause-all|resume-all|close-all`, `/traders/{id}/master-trades`, `/admin/simulation/*`, `/admin/config/*`
- `/app/backend/copy_trading/__init__.py` — wire everything + startup/shutdown handlers
- `/app/backend/server.py` — pass `get_current_admin` to copy_trading.attach

### Frontend changes
- `/app/frontend/app/copies/index.tsx` — My Copies portfolio dashboard (summary card with total P&L, today P&L, win rate; per-trader rows; bulk pause/resume/close-all)
- `/app/frontend/app/copies/[id].tsx` — Individual copy detail (live P&L, status controls, open positions, mirrored trade history, risk panel)
- `/app/frontend/app/copies/_layout.tsx` — Stack layout
- `/app/frontend/app/(tabs)/index.tsx` — "My Copies" quick-action tile
- `/app/frontend/app/(tabs)/profile.tsx` — "My Copies" account menu entry
- `/app/frontend/app/traders/index.tsx` — "My Copies" button top-right of leaderboard header
- `/app/frontend/src/api/copyTrading.ts` — extended types + methods (CopySummary, FollowerTrade, MasterTrade, mySummary, myTrades, masterTrades, pauseAll, resumeAll, closeAll)

### Mongo collections added/used
- `copy_config` — global defaults + simulation state (singleton _id="active")
- `copy_master_trades` — simulated master trades (event log)
- `copy_follower_trades` — mirrored follower trades (managed by PaperBroker)
- `copy_daily_stats` — per (user, trader, day) P&L for risk halt tracking
- `copy_relationships` — pre-existing, now also stores `starting_equity_usd`, `halt_reason`, `copy_id`

### No regression
- Wallet, Forex, KYC, Notifications, AI Advisor, Market Data — untouched
- KYC still enforced only on withdrawal requests
- Auto-copy off by default for existing open trades (per user spec)

### Curl verification
- `GET /api/copy_trading/meta` → simulator enabled, defaults reflect user-provided values (max_daily_loss 10%, max_drawdown 20%, max_open_trades 10, equity_protection 30%, etc.)
- Master simulator producing trades within seconds of startup (Hana Tanaka scalper opened/closed EURUSD/GBPUSD within 30s)
- Backend clean startup: `MasterSimulator started with 28 traders`

---

## Iteration 26 — Sprint 7B.3 (Admin Copy Trading Console) — 2026-06

### Scope
Full admin console for Copy Trading — Trader Management, Live Simulation Panel,
Master Trade Explorer, Follower Monitor, Analytics, System Health, Configuration.

### Design decisions confirmed by user
- Hybrid trader model: 28 seeded traders (deterministic) + admin overlays + custom traders in mongo.
- Master Trade Explorer polls every 2s (design allows swapping to WebSocket later).
- Trader Categories: system / verified / custom / disabled.
- Approval Levels: verified / professional / elite / master.
- All configuration stored in MongoDB (nothing hardcoded).

### Backend additions
- `/app/backend/copy_trading/admin_traders.py` — Overlay system for system traders (`copy_trader_overlays` collection) + full CRUD for custom traders (`copy_custom_traders` collection).
- Extended `/app/backend/copy_trading/simulator.py` — includes custom traders in the loop; respects disabled flag; adds `sync_traders()` and `remove_trader()`.
- Extended `/app/backend/copy_trading/engine.py` — health metrics (fanout_ms, exec_ms, failed_mirrors, retry_queue) + `health_snapshot()`.
- Extended `/app/backend/copy_trading/routes.py` with:
  - Trader CRUD: `GET /admin/traders`, `GET /admin/traders/{id}`, `POST /admin/traders`, `PUT /admin/traders/{id}`, `DELETE /admin/traders/{id}`, `POST /admin/traders/{id}/verify|unverify|disable|enable|reset-overlay`
  - Master Trade Explorer: `GET /admin/master-trades` (with `followers_copied` per row)
  - Follower Monitor: `GET /admin/followers/summary`, `GET /admin/traders/{id}/followers`
  - Analytics: `GET /admin/analytics` (daily/weekly/monthly ROI, win rate, most copied, highest ROI, highest win rate, highest AUM, mirrored trades, open positions, unique followers)
  - System Health: `GET /admin/system-health` (event queue, active simulators, followers, sessions, broker, avg fan-out/exec ms, failed mirrors, retry queue, DB ping, uptime)
- Public leaderboard now merges seeded (with overlay) + custom + honours `visible`/`disabled` flags.

### Admin panel additions
- `/app/admin/src/pages/AdminCopyTrading.tsx` — new page with 7 tabs (Traders / Simulation / Master Trades / Followers / Analytics / System Health / Configuration).
- Trader table with category filter (ALL/SYSTEM/VERIFIED/CUSTOM/DISABLED), search, verify/unverify/enable/disable/edit/delete inline actions, reset-overlay for system traders.
- Custom Trader creator + system trader Editor with avatar upload (base64), country, style, approval level, risk tier, verified/visible/disabled toggles.
- Simulation panel with Start/Pause, Speed selector (Slow/Normal/Fast), Force-open master trade.
- Master Trades table auto-refreshing every 2s with followers_copied count + force-close button.
- Follower Monitor: top-10 traders by follower count with click-through to detailed follower list.
- Analytics dashboard: 16 stat cards + 3 leader cards + most-copied banner.
- System Health: 12 stat cards (queue, simulators, followers, sessions, broker, timings, retries, server, DB).
- Configuration editor with 10 numeric fields + 4 boolean toggles.
- Registered nav entry "Copy Trading" (Copy icon) and route `/copy-trading`.

### MongoDB collections added
- `copy_trader_overlays` — admin edits to system traders (avatar, bio, verified, risk_tier, style, country, visible, disabled, approval_level)
- `copy_custom_traders` — full custom trader documents (persona + admin metadata)

### Regression protection
Wallet, Forex, KYC, Notifications, AI Advisor, Market Data — untouched.
KYC still enforced only on withdrawal requests.

### Curl verification
- `POST /api/admin/login` → admin token OK
- `GET /copy_trading/admin/traders` → 28 system traders returned
- `POST /copy_trading/admin/traders` → custom trader created with generated stats & risk score
- `GET /copy_trading/admin/analytics` → daily/weekly/monthly ROI, leaders (highest ROI, win rate, AUM), most copied all populated
- `GET /copy_trading/admin/system-health` → active_simulators=28, broker=paper OK, database OK, uptime tracked
- `DELETE /copy_trading/admin/traders/{custom_id}` → custom trader removed and simulator task cancelled

---

## Iteration 27 — Sprint 7C.1 (AI Trading Intelligence) — 2026-06

### Scope
Independent AI Intelligence subsystem — Signal Engine, TA Engine, AI Reasoning (Claude), Enhanced Watchlist, Price Alerts (5 types with 30s configurable evaluation loop).

### Architecture (all modules independent)
Signal Engine → TA Engine → AI Engine (Claude) → Alerts (Notifications) → Frontend

### Backend files created
- `/app/backend/ai_intelligence/feed.py` — Deterministic SHA-256-seeded OHLCV synthesizer with mean-reversion to anchor prices (from market_data catalog). Provider-based so TwelveData/Alpha Vantage/Finnhub can replace it later.
- `/app/backend/ai_intelligence/ta_engine.py` — All 10 indicators: EMA 20/50/200, RSI, MACD, ATR, Bollinger Bands, ADX, SuperTrend, VWAP + volatility.
- `/app/backend/ai_intelligence/signal_engine.py` — Combines TA into signals with all 13 required fields (side, entry, SL, TP1/2/3, RR, confidence %, trend, strength, timeframe, expiry, reason hits, indicator summary).
- `/app/backend/ai_intelligence/ai_engine.py` — Claude Sonnet 4.5 narrative reasoning cached in `ai_signal_explanations` collection (falls back to deterministic template if LLM unavailable).
- `/app/backend/ai_intelligence/watchlist_engine.py` — Enriched watchlist with trend/signal/confidence/volatility/daily+weekly change.
- `/app/backend/ai_intelligence/alerts_engine.py` — 5 alert types (price_above/below, percent_move, indicator_cross, rsi_alert), background asyncio loop @ 30s (admin-configurable), integrates with existing Notifications module.
- `/app/backend/ai_intelligence/routes.py` — 14 endpoints under `/api/ai/*` + admin config endpoints.
- `/app/backend/ai_intelligence/__init__.py` — Startup wires alerts loop from `ai_config` collection.

### Endpoints (all under /api/ai/)
- Meta: GET /meta
- Signals: GET /signals[?timeframe&asset_class&min_confidence&side&limit], GET /signals/{symbol}[?timeframe&with_ai], GET /indicators/{symbol}, GET /candles/{symbol}
- Watchlist: GET /watchlist, POST /watchlist, DELETE /watchlist/{symbol}
- Alerts: GET/POST/DELETE /alerts[/…], POST /alerts/{id}/pause, POST /alerts/{id}/resume
- Admin: GET /admin/alerts/config, PUT /admin/alerts/config

### Mongo collections used
- `ai_watchlist` — user symbol watchlist
- `ai_price_alerts` — user alerts (5 types)
- `ai_config` — global config (alerts_eval_interval_sec)
- `ai_signal_explanations` — Claude cache keyed by (symbol|timeframe|bar_index)

### Frontend screens created
- `/app/frontend/app/ai/_layout.tsx` — Stack
- `/app/frontend/app/ai/index.tsx` — AI Intelligence Hub with 3 module cards
- `/app/frontend/app/ai/signals.tsx` — Filterable signals list (timeframe / asset class / side / min confidence)
- `/app/frontend/app/ai/signal/[symbol].tsx` — Detailed signal view: SL/TP1/TP2/TP3, AI explanation, 10 indicators, quick alert/watchlist actions
- `/app/frontend/app/ai/watchlist.tsx` — Symbol watchlist with add-modal (quick picks + custom entry)
- `/app/frontend/app/ai/alerts.tsx` — Alert list + creator sheet supporting all 5 types
- `/app/frontend/src/api/aiIntel.ts` — Typed API client

### Home screen integration
- Added "AI Signals" quick-action tile (Brain icon, #8B5CF6)

### Not modified (regression protection)
- Wallet, Forex, Copy Trading, KYC, Notifications (Alerts ADD notifications, don't modify code), AI Advisor, Market Data — untouched
- Existing Copy Trading tests still pass

### Curl verification
- `GET /api/ai/meta` → timeframes (M5..D1), asset_classes, alert_types, universe (15), eval_interval_sec=30
- `GET /api/ai/signals?limit=6` → returns signals with anchors matching catalog (BTCUSD @ ~99k, GER40 @ ~21k, XAUUSD @ ~4098)
- `GET /api/ai/signals/BTCUSD` → full detail with Claude AI explanation (fallback narrative since sandbox has no live key), 10 indicators, indicator_summary rows, 6 reason hits
- Alerts loop confirmed active at startup ("AlertsEngine started interval=30s")

---

## Iteration 28 — Sprint 7.5 (Live Market Integration) — 2026-06

### Scope
Provider-based live market layer with TwelveData → Alpha Vantage → Mock automatic fallback. Zero frontend changes. All 5 consumers (Forex/AI Signals/Watchlist/Copy Trading/Price Alerts) read from a shared MongoDB TTL cache.

### Architecture
```
ProviderManager (10s refresh, circuit breaker)
   ├── TwelveDataProvider     (priority 100, needs API key)
   ├── AlphaVantageProvider   (priority 200, needs API key)
   └── MockProvider           (priority 300, always available)
          ↓
     QuoteCache (MongoDB, 30s TTL)  +  in-process _MEMO
          ↓
     Consumers: Forex / AI Signals / Watchlist / Copy Trading / Alerts
```

### Backend files created
- `/app/backend/market_providers/base.py` — Provider abstract + Quote + ProviderStats
- `/app/backend/market_providers/mock.py` — Mock provider (always ok)
- `/app/backend/market_providers/twelvedata.py` — REST client + symbol map (24 symbols)
- `/app/backend/market_providers/alphavantage.py` — REST client (FX + Crypto + equities)
- `/app/backend/market_providers/cache.py` — MongoDB TTL cache (`market_price_cache` collection)
- `/app/backend/market_providers/manager.py` — Circuit breaker + auto-fallback + background refresh loop + history logging
- `/app/backend/market_providers/routes.py` — 11 admin endpoints under /api/market_providers
- `/app/backend/market_providers/__init__.py` — Bootstrap + `get_manager()` singleton
- Modified `ai_intelligence/feed.py` — Added `skip_live` param + `publish_price()` + `_MEMO` for sync live reads; `get_candles` splices live price into last bar

### Endpoints (all admin)
GET /api/market_providers/status  — full status snapshot
GET /api/market_providers/quotes  — all cached quotes
GET /api/market_providers/quote/{symbol}  — one quote
POST /api/market_providers/refresh  — manual refresh
GET /api/market_providers/health[?provider=…]  — health check
GET /api/market_providers/history — recent refresh history
PUT /api/market_providers/manual-provider  — force provider or clear override
PUT /api/market_providers/auto-fallback  — enable/disable
PUT /api/market_providers/refresh-interval  — set interval seconds
PUT /api/market_providers/universe  — set symbol universe
PUT /api/market_providers/api-key  — set provider API key
DELETE /api/market_providers/cache  — clear cache

### MongoDB collections
- `market_price_cache` — live quotes with age tracking
- `market_provider_config` — persisted config (auto_fallback, manual_provider, api keys, universe, refresh interval)
- `market_provider_history` — refresh events (last ~500)

### Admin Panel
- New page `/app/admin/src/pages/AdminLiveMarket.tsx` with 4 tabs:
  - **Overview** — Active provider, auto-fallback, refresh interval, symbols, cache stats, manual override, actions
  - **Providers** — Per-provider stats + circuit state + API key input + Test Connection
  - **Cache** — Live 20-symbol table with bid/ask/provider/age (auto-refresh 3s)
  - **History** — Refresh events with timestamps + latency + errors
- Nav entry added: "Live Market (S7.5)" using `Activity` icon

### No frontend changes (mobile)
Zero mobile screens modified. All 5 consumers continue calling the same functions; underneath they now read from the shared cache instead of ad-hoc synthesized values.

### Regression protection
Wallet, Forex, Copy Trading, Notifications, AI Advisor, KYC, Market Data, AI Signals — all untouched. Existing endpoints continue to work.

### Curl verification
- GET /api/market_providers/status → active=mock, auto_fallback=true, cache 20/20 fresh, 3 providers listed
- GET /api/market_providers/quotes → 20 quotes (BTCUSD ≈97878, EURUSD ≈1.151, GER40 ≈20874, XAUUSD present)
- GET /api/market_providers/health → mock ok, twelvedata + alphavantage report "ProviderNotConfigured" (correct — no keys)
- Background refresh loop running every 10s (verified via history)

## Iteration 29 — Sprint 7.5 P0 Fix (TwelveData Batch + Backoff) — 2026-06

### Problem
Free-tier TwelveData quota was being exhausted (20 individual HTTP requests × every 10s = ~120 credits/min vs 8/min limit).

### Fix (files touched)
- `/app/backend/market_providers/twelvedata.py` — full rewrite
  * Kept batch `/quote?symbol=A,B,C` (1 HTTP request per cycle)
  * Added exponential backoff: **30s → 60s → 120s → 240s → 600s** on 429 (HTTP status OR JSON `code:429`)
  * Backoff resets on first successful response
  * Parses `api-credits-left` / `api-daily-credits-left` headers
  * Provider REJECTS calls while backed-off (never hammers the API)
- `/app/backend/market_providers/manager.py` — full rewrite
  * `refresh_interval_sec` default: 10 → **60**
  * Cache TTL default: 30 → **60**
  * 429s DO NOT trip the circuit breaker (only network/5xx do)
  * `_choose_provider` skips backed-off providers
  * New `_market_status()` computes LIVE / STALE / FALLBACK
  * `live_max_sec = max(30, refresh_interval + 5s grace)` — no green→amber oscillation
  * On startup, migrates stored `refresh_interval_sec` <60 → 60 (P0 safety)
- `/app/backend/market_providers/base.py` — added default `is_backed_off()` / `backoff_state()` on Provider
- `/app/backend/market_providers/cache.py` — TTL 60, FRESH_MAX_SEC=30, STALE_MAX_SEC=300, `newest_age_sec` / `oldest_age_sec` / `expired`
- `/app/admin/src/pages/AdminLiveMarket.tsx` — 🟢 LIVE / 🟠 STALE / 🔵 FALLBACK banner + backoff panel with countdown, schedule, total 429 events
- `/app/backend/tests/test_iter28_market_providers.py` — assertions updated (60/60/300, market_status, backoff)

### Testing (iteration_29.json)
- 57/57 backend tests pass (34 iter28 + 23 new sprint75 P0 tests)
- Validated: batch call path, 429 backoff triggers, 429 does NOT trip breaker, credits parsing, mock fallback, market_status shape, admin controls, all downstream endpoints (Wallet/Forex/AI/CopyTrading) still 200.

### Curl verification (post-fix)
- `GET /api/market_providers/status` → refresh_interval_sec=60, cache.ttl_sec=60, market_status={state:FALLBACK, tint:blue, live_max_sec:65}
- Setting a bad TD key → circuit_failures++ but backoff.active=False (correct separation)
- Admin UI screenshot confirmed: FALLBACK banner + all backoff/credits fields visible


## Iteration 30 — Sprint 7C.2 AI Market News & Analytics — 2026-06

### New module
`/app/backend/ai_news/` (attached in `server.py` after `ai_intelligence`)
  * `news_engine.py`      — AI-generated categorized market news (Forex/Crypto/Indices/Commodities/Indian Market/Global) via Claude Sonnet 4.5 + deterministic template fallback + high-impact broadcaster (2-min interval, notifications collection)
  * `calendar_engine.py`  — Economic calendar with 32-event curated seed (Fed/NFP/CPI/ECB/RBI/BoE/BoJ/RBA/etc.), impact filters + live countdown_sec, admin CRUD
  * `summary_engine.py`   — Daily/weekly/intraday market summaries powered by Claude Sonnet 4.5 aggregating top movers from `market_price_cache`
  * `analytics_engine.py` — Signal outcome tracker (5-min tick loop): resolves against SL/TP levels, computes ROI, aggregates win rate / tp1/2/3 hit rates / confidence edge
  * `routes.py`           — Public + admin endpoints (see below)

### New endpoints
Public:
  `GET /api/ai/news[?category&sentiment&high_impact_only&limit]`
  `GET /api/ai/news/{id}`
  `GET /api/ai/calendar[?impact&country&currency&days_ahead&include_past&limit]`
  `GET /api/ai/calendar/meta`
  `GET /api/ai/summary?type=intraday|daily|weekly`
  `GET /api/ai/summary/history[?type&limit]`
  `GET /api/ai/analytics/overview[?window_days]`
  `GET /api/ai/analytics/by-symbol[?window_days&limit]`
  `GET /api/ai/analytics/by-timeframe[?window_days]`
  `GET /api/ai/analytics/history[?limit&outcome]`
Admin console:
  `POST/PUT/DELETE /api/ai/admin/news`, `POST/PUT/DELETE /api/ai/admin/calendar`,
  `POST /api/ai/admin/summary/generate`, `DELETE /api/ai/admin/summary/{id}`,
  `POST /api/ai/admin/analytics/tick`, `GET /api/ai/admin/console`, `GET /api/ai/admin/news`

### New Mongo collections
  * `ai_news_items`         — categorized AI news
  * `ai_economic_events`    — 32 seeded macro events + admin additions
  * `ai_market_summaries`   — intraday/daily/weekly narratives
  * `ai_signal_history`     — tracked signals with SL/TP outcomes + ROI

### Mobile screens
  * `/app/frontend/app/ai/news.tsx` + `/news/[id].tsx` — feed with category pills + high-impact filter, detail with sentiment icon + snapshot
  * `/app/frontend/app/ai/calendar.tsx` — impact + country filters, live countdown grouped by day, side border indicates impact
  * `/app/frontend/app/ai/summary.tsx` — Intraday/Daily/Weekly tabs, key-movers card
  * `/app/frontend/app/ai/analytics.tsx` — 4 KPI cards (win rate / TP hit rate / sum ROI / confidence edge), outcome breakdown, by-symbol, by-timeframe, recent signals
  * `/app/frontend/app/ai/index.tsx` — hub updated to expose 7 modules (Signals/News/Calendar/Summary/Analytics/Watchlist/Alerts)

### Admin console page
  * `/app/admin/src/pages/AdminAIConsole.tsx` — 5 tabs (Overview, News, Economic Calendar, Market Summary, Signal Analytics). CRUD news (Mark HI, Publish, Delete), CRUD calendar (Add Event, Delete), regenerate summaries, view analytics per window (7/30/90/all-time), force analytics tick.
  * Routed at `/ai-console`, added to sidebar as "AI Console (S7C.2)".

### Testing
- `/app/backend/tests/test_iter30_ai_news_analytics.py`: 50/50 PASS
  (news + filters, calendar CRUD, summary all types + history, analytics aggregations + tick, admin console, broadcaster, datetime ISO)
- Regression: 70/71 iter27+iter28 tests pass. 1 pre-existing failure (alerts_engine cross-detection) documented in iteration_27, NOT introduced by 7C.2.
- Untouched (verified regression-free): Wallet, Notifications, Auth/me, Forex, Market Dashboard, Live Market (7.5), Copy Trading, AI Intelligence (7C.1), KYC.

### Frontend build & deploy
- Admin panel rebuilt: `cd /app/admin && yarn build` → copied to `/app/backend/static/admin-ui/`.
- Expo restarted via supervisorctl. AI hub now shows 7 modules.

### Report
`/app/test_reports/iteration_30.json`


## Iteration 31 — Stabilization Sprint (Alert Notification Test) — 2026-06

### Bug Fixed
`TestAlertsTrigger.test_eval_loop_triggers` in `test_iter27_ai_intelligence.py` was failing since Sprint 7C.1 with "no price_alert notification with EURUSD in title found".

### RCA
The test looked up the wrong JSON key. Endpoint `/api/notifications` returns
`{items, total, unread, per_category, categories}` (per Sprint 7A refactor to a
richer notifications module), but the test was reading `r.json().get("notifications", [])`.
So even though the alerts_engine created the notification correctly (verified in
Mongo: `db.notifications.count({category:'price_alert'}) > 0`), the test always
saw `notif_list=[]` and asserted False.

### Fix
- `/app/backend/tests/test_iter27_ai_intelligence.py` — tolerant assertion that
  accepts a raw list OR `items` key OR legacy `notifications` key. No production
  code change was needed (alerts_engine, notifications_module untouched).

### Regression run (post-fix)
- iter27 (AI Intelligence) — 37/37 ✅
- iter28 (Market Providers / Sprint 7.5) — 34/34 ✅
- iter30 (AI News & Analytics / Sprint 7C.2) — 50/50 ✅
- **Total: 121/121 PASS** — all three sprints green.

### Untouched (regression-free)
Wallet · Forex · Copy Trading · Live Market · AI News · AI Console · KYC · Notifications module · alerts_engine production code.


## Iteration 32 — Sprint 8 Production Payments (Razorpay) — 2026-06

### New module `/app/backend/payments/`
  * `providers/razorpay.py`  — SDK wrapper + DemoRazorpayProvider fallback
  * `engine.py`              — order lifecycle, wallet credit ONLY after webhook signature verification, refunds (full + partial)
  * `webhooks.py`            — HMAC-SHA256 signature verification + payload_hash & X-Razorpay-Event-Id replay protection
  * `reconciliation.py`      — background job (30-min cadence) + on-demand admin endpoint; skips gracefully in demo mode
  * `logging_setup.py`       — structured JSON logging; redacts key_secret, webhook_secret, signature, cvv, etc.
  * `security.py`            — HMAC helpers (webhook + client-side payment signature)
  * `models.py`              — Pydantic models + OrderStatus/RefundStatus enums
  * `routes.py`              — 21 endpoints (user + webhook + admin)

### Design guarantees VERIFIED
  1. Wallet is NEVER credited before webhook signature verification (client `/verify` only ACKs signature; credit happens exclusively inside `engine.capture_payment` triggered by webhook).
  2. Idempotency-Key on order creation — same key + same user returns existing order with `created_new:false`.
  3. HMAC-SHA256(webhook_secret, body) enforced; bad signature → 401.
  4. Replay-protected via `payload_hash` + `X-Razorpay-Event-Id`; duplicate delivery → `{ok:true, idempotent:true}` and no double-credit.
  5. Refund lifecycle: full + partial, wallet debit only when refund status is `processed`, audit trail on every transition.
  6. JSON logs never emit secrets — sanitizer runs on every extra field.
  7. Demo mode when keys are placeholder OR admin toggle. Auto-forces demo_mode=true if creds go missing.
  8. Reconciliation heals missed webhooks on schedule; in demo mode returns `skipped=demo_mode_or_unconfigured`.

### DB collections
  * `payments_orders`, `payments_transactions`, `payments_refunds`
  * `payments_webhooks`, `payments_audit_log`
  * `payments_config` (singleton), `payments_reconciliation_runs`

### Frontend
  * Mobile `/app/frontend/app/wallet/topup.tsx` rewritten to hit `/api/payments/*`; supports UPI/Card/Net Banking hint pills; Razorpay checkout via `expo-web-browser` in live mode; local demo/capture flow in demo mode; polls order until captured.
  * Admin `/app/admin/src/pages/AdminPayments.tsx` — 7-tab console (Overview, Orders, Transactions, Refunds, Reconciliation, Audit Log, Config); order detail modal with inline refund; live secrets never revealed (only booleans + key_id_public).

### Notification categories registry updated
`notifications_module.py` — added `market_news`, `payment`, `price_alert` to the categories registry so admin dashboards see the same list as `per_category` counts.

### Testing
- New suite `tests/test_payments_iter32.py`: **26/26 PASS**
- Full regression across ALL suites (iter27 + iter28 + iter30 + iter32 + forex + notifications):
  **192 PASS · 1 SKIP · 0 FAIL** in 91s.
  Also fixed two pre-existing test drifts:
    * `test_forex_regression`: widened BTC 2026 band to 95k–120k
    * `test_notifications`: made category-count assertion tolerant of new modules

### Report
`/app/test_reports/iteration_32.json`

### Sprint 8 remaining work (before production go-live)
- User must provide RAZORPAY_KEY_ID + RAZORPAY_KEY_SECRET + RAZORPAY_WEBHOOK_SECRET via Admin Panel → Payments → Config
- Configure the webhook endpoint on Razorpay dashboard: `https://<host>/api/payments/webhooks/razorpay`
- Enable events: payment.captured, payment.failed, refund.processed, refund.failed
- Flip demo_mode → false via Config tab (auto-forced to false once real keys are saved and mode=live)


## Iteration 33 — Sprint 9 Real KYC Platform (kyc_v2) — 2026-06

### New module `/app/backend/kyc_v2/` (additive — legacy `kyc_module.py` untouched)
  * `providers/base.py`         — Protocol definitions
  * `providers/pan.py`          — DemoPanProvider + NSDLPanProvider stub (delegates to demo when key missing)
  * `providers/digilocker.py`   — DemoDigiLockerProvider + DigiLockerProviderReal (OAuth stub)
  * `providers/aux.py`          — DemoOCRProvider + DemoFaceMatchProvider (deterministic outputs for reliable tests)
  * `storage.py`                — Fernet-encrypted document storage (falls back to unencrypted b64 when KYC_ENCRYPTION_KEY is placeholder)
  * `gating.py`                 — 4 gated actions: `withdrawal`, `become_signal_provider`, `become_copy_trader`, `compliance_limits`; audit trail via `kyc_gating_events`
  * `routes.py`                 — 13 endpoints under `/api/kyc/v2/*` (user) + `/api/admin/kyc/v2/*` (admin)

### DB collections (additive)
  * `kyc_verifications` — one row per check (PAN, Aadhaar-soft, DigiLocker, OCR, FaceMatch)
  * `kyc_v2_documents` — encrypted document blobs with sha256 hash
  * `kyc_gating_events` — audit trail for gate decisions
  * `kyc_digilocker_states` — OAuth state binding (short-lived)

### Business rules honoured
  * Sign Up / Login / Deposit / Forex / Copy Trade / AI / Gold / SIP / Mutual Funds → **NO KYC required**
  * Withdrawal / Signal Provider / Copy Trader / crossing compliance limits → KYC gate returns 403 with `{kyc_required:true, action, reason, kyc_status, unblock_hint}`
  * Compliance thresholds: ₹5L lifetime deposit, ₹1L single transaction

### Provider abstraction
  * PAN, DigiLocker, OCR, FaceMatch each expose `provider`, `is_configured()`, and their verify methods.
  * `get_pan_provider()` auto-picks the real backend when `NSDL_PAN_API_KEY` is set, else demo.
  * `get_digilocker_provider()` same pattern using `DIGILOCKER_CLIENT_ID` + `DIGILOCKER_CLIENT_SECRET`.
  * When keys land later, NO code changes needed.

### Encrypted document storage
  * Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
  * Key accepted as raw urlsafe base64 OR any passphrase (SHA-256-derived).
  * With placeholder key, docs are stored as plain base64 but flagged `encrypted:false` so ops can catch it via `/api/admin/kyc/v2/dashboard` → `encryption`.

### Testing (iteration_33)
- **kyc_v2 new tests**: **22/22 PASS** (`test_kyc_v2_iter33.py`)
  All 17 scenarios covered incl. PAN happy/invalid/BAD-prefix, Aadhaar soft-verify, DigiLocker full flow, DigiLocker security (wrong-state 400 + foreign-state 403), OCR PAN+Aadhaar, face-match identical+different, doc upload+sha256, doc >8MB → 413, summary, gate withdrawal + gate forex_trade, compliance, admin dashboard, admin verifications 401 gate, admin providers.
- **Regression**: iter27 (37) + iter28 (34) + iter30 (49+1 skip) + iter32 (26) + forex (16) + notifications (30) → all green.
- **Grand total: 214 PASS · 1 SKIP · 0 FAIL** across 215 tests.

### Report
`/app/test_reports/iteration_33.json`, `iter33_kyc_v2.xml`, `iter33_regression_*.xml`

### Production go-live prerequisites (user actions when ready)
1. `KYC_ENCRYPTION_KEY` — set a strong 32-byte urlsafe base64 key OR any passphrase (auto-derived) in `/app/backend/.env`
2. `NSDL_PAN_API_KEY` — plug real NSDL PAN check credentials
3. `DIGILOCKER_CLIENT_ID` + `DIGILOCKER_CLIENT_SECRET` — Meri Pehchaan / DigiLocker Sandbox / Prod credentials
4. Register callback URL in DigiLocker console: `https://<host>/api/kyc/v2/digilocker/callback` (or app deeplink)


## Iteration 34 — Sprint 10 Gold Investment Platform — 2026-06

### New module `/app/backend/gold/` (4 files, additive)
  * `providers.py` — GoldProvider abstraction with 5 backends:
      - `MockGoldProvider` (deterministic ±15 INR/g band around ₹6500/g, seeded per-minute)
      - `LiveMarketGoldProvider` (derives ₹/g from XAUUSD × USDINR / 31.1035 from `market_price_cache`)
      - `AugmontProvider`, `MmtcPampProvider`, `SafeGoldProvider` — real backend stubs; automatically fall through to LiveMarketGoldProvider when API keys are placeholder
  * `engine.py` — GoldEngine:
      - Manual price override → chosen provider → live_market → mock fallback chain
      - Buy/sell against wallet (weighted-average cost, realized P/L on sell)
      - Spread engine (default 2% total split as buy/sell around mid)
      - Trading hours + maintenance-mode guardrails
      - Weighted-avg cost basis + P/L (unrealized + realized)
      - Price history collection + auto-seeded 400-point 1Y chart curve
      - Structured audit log for every action
  * `routes.py` — 7 user + 7 admin endpoints
  * `__init__.py` — startup hook

### DB collections (additive)
  * `gold_config` (singleton), `gold_transactions`, `gold_holdings`, `gold_audit_log`, `gold_price_history`

### Business rules verified
  * NO KYC required to buy/sell gold. KYC gate stays reserved for gold **redemption** (config flag `redemption_kyc_required=true`, to be enforced when redemption module lands)
  * Purchases use wallet balance only; every tx generates a notification + audit entry
  * Minimum purchase ₹10, maximum ₹2,00,000 (both admin-configurable)
  * Idempotency-Key header protects against double-buys on retry

### Testing
- **Sprint 10 new suite**: `test_gold_iter34.py` (21 tests) — 21/21 PASS
- **Full regression**: **214 pass + 21 gold = 235 PASS · 1 SKIP · 0 FAIL**
- Wallet integrity: no double-debit, balance delta matches tx amount to ₹0.01 on all buy/sell paths

### Report
`/app/test_reports/iteration_34.json`, `iter34_gold.xml`, `iter34_full.xml`

### Follow-ups (all non-blocking, admin config)
  * Provide `AUGMONT_API_KEY` / `MMTC_PAMP_API_KEY` / `SAFEGOLD_API_KEY` when ready → real backends auto-activate
  * Admin can switch provider live via `PUT /api/admin/gold/config {"provider": "augmont"}`
  * Manual price override via `PUT /api/admin/gold/config {"manual_price_inr_per_gram": 7000}`

### Mobile UI (still to build in follow-up)
Backend is production-ready. Mobile screens for the gold hub, buy/sell sheet, chart, and holdings will be built as an incremental UI-only iteration.


---
## Sprint 10.5 — Gold Investment Mobile UI + Admin Console (June 2026)

### Scope
Frontend-only sprint. Backend endpoints from Sprint 10 (unchanged) are wired into:
- Mobile app (Expo React Native) — new `/gold` route family
- Admin panel (Vite React) — new `/gold` route

Backend WAS NOT modified. Regression sanity: `test_gold_iter34.py` → 21/21 PASS.

### New reusable components
- `/app/frontend/src/components/FinancialChart.tsx` — powered by `react-native-gifted-charts`, area-gradient, timeframe pills (1D/1W/1M/3M/1Y/ALL), long-press tooltip + strip, live price badge, dark/light theme. Reused across Gold, will plug into Forex/AI Signals/Watchlist/MF NAV.
- `/app/frontend/src/components/TradeBottomSheet.tsx` — snap points 40/70/95%, spring animation, drag-to-close, tap-outside-dismiss, keyboard-aware, long-press confirm, submitting/success/error state slots. Reused for Gold buy/sell; drop-in for Forex/Wallet/Withdraw/SIP/MF.
- `/app/frontend/src/api/gold.ts` — typed API wrapper for `/api/gold/*` (quote, chart, holdings, transactions, buy, sell, config).

### Mobile Gold screens
- `app/gold/index.tsx` — Dashboard: gold gradient hero (live price, bid/ask, 24h delta), holdings summary, live mini-chart, quick tiles, wallet strip, Buy + Sell sheets
- `app/gold/chart.tsx` — Full-screen live chart with timeframe switcher and range stats
- `app/gold/history.tsx` — Transactions with all/buy/sell filter, infinite pagination
- `app/gold/analytics.tsx` — Personal analytics (P/L total = realized + unrealized, cost vs market, activity blocks, portfolio position)
- Home dashboard now has a "Gold" quick-action tile that opens `/gold`

### Admin Gold Console
`/app/admin/src/pages/AdminGoldConsole.tsx` — 6 tabs:
1. Overview — Live price banner, trading status, KPI cards, provider state, user-realized P/L
2. Transactions — Side/user filters, CSV export
3. Users — Top investors, live-marked current value, ROI %, CSV export
4. Providers — Provider registry cards, active toggle, manual-override warning
5. Settings — Full config editor (spread, min/max, GST, fees, trading hours, manual price, maintenance toggle, KYC gate)
6. Analytics — Range switcher (today/week/month/year/all), full KPI grid (Business/Financial), daily buy-vs-sell 14-day bar chart, holdings distribution, top ROI investors, CSV export

Wired into `Layout.tsx` sidebar (`/gold`) and `main.tsx` router; roles: super_admin, admin, finance_manager, investment_manager.

### Testing done in-session
- Backend regression: `test_gold_iter34.py` 21/21 PASS
- Admin build: `yarn build` → 0 errors
- Frontend lint: no errors on new files (only unused-var warnings)
- Mobile screenshot smoke test: /gold renders premium UI without crashes (auth-gated data placeholders visible when unauthenticated)

### Files added / modified
- ADD: `/app/frontend/src/api/gold.ts`
- ADD: `/app/frontend/src/components/FinancialChart.tsx`
- ADD: `/app/frontend/src/components/TradeBottomSheet.tsx`
- ADD: `/app/frontend/app/gold/{_layout,index,chart,history,analytics}.tsx`
- ADD: `/app/admin/src/pages/AdminGoldConsole.tsx`
- EDIT: `/app/frontend/app/(tabs)/index.tsx` (Gold quick action)
- EDIT: `/app/admin/src/main.tsx` (route)
- EDIT: `/app/admin/src/pages/Layout.tsx` (sidebar + role matrix)

### Package additions
- `react-native-gifted-charts@1.4.77` (installed via `yarn expo install`)

---
## Sprint 11 — Mutual Funds & SIP Platform (June 2026)

### Scope
Full-stack module for Indian mutual funds & SIPs. Backend + Mobile UI + Admin Console + AI Advisor.

### Backend (`/app/backend/mutual_funds/`)
- `providers.py` — Mock (default seed) + AMFI (free NAV feed) + CAMS/KFintech/MF Central stubs
- `seed.py` — 40 realistic funds across 11 categories, 400 days of NAV history each
- `engine.py` — Fund catalog, NAV history, order lifecycle (created→pending_payment→processing→allocated→completed / failed / redeemed), SIP state machine (active/paused/cancelled/failed/completed) with retry policy, portfolio (XIRR/CAGR/absolute + Daily/Weekly/Monthly P/L + 4-way allocations + top/worst performer), goals with SIP-required + ETA + progress, watchlist, redemption with KYC gate, admin dashboard + KPIs
- `ai.py` — Claude Sonnet 4.5 advisor (6 kinds: analyze_portfolio / suggest_funds / sip_increase / tax_saving / risk_analysis / diversification + top_funds / best_sip / goal_plan)
- `routes.py` — 20 user endpoints + 10 admin endpoints under `/api/mf/*` and `/api/admin/mf/*`
- Wired into `server.py` — startup seeds if empty

### Mobile UI (`/app/frontend/app/mutual-funds/`)
- `index.tsx` — Hub with portfolio hero, quick tiles (Portfolio/SIPs/Goals/Compare/Watchlist/AI), category shortcuts, top-rated funds
- `explore.tsx` — Full explorer with search, filters (AMC/Category/Risk/Rating), 7 sort modes, infinite list
- `fund/[id].tsx` — Fund detail with NAV chart (FinancialChart, 7 windows 1M/3M/6M/1Y/3Y/5Y/MAX), historical returns grid, key details, top holdings, sector allocation, YOUR HOLDING pane, Invest sheet with Lumpsum/SIP tabs, Redeem sheet
- `portfolio.tsx` — XIRR/CAGR/Absolute, Daily/Weekly/Monthly P/L cards, 4-way allocation stack (asset/AMC/category/risk), top+worst performer, holdings list
- `sips.tsx` — Pause/Resume/Cancel actions, status filter, retry warnings
- `goals.tsx` — Create sheet (kind/amount/years/return), progress bar, required SIP, ETA
- `compare.tsx` — Add-to-compare search, 2–4 side-by-side attribute cards
- `watchlist.tsx` — Add/remove funds, deep-link to detail
- `advisor.tsx` — 6 AI prompt tiles, streamed answers
- `orders.tsx` — Full order lifecycle history with status pipeline
- Home dashboard: added "SIP & MF" quick action tile

### Reusable components (all reused, NO duplication):
- FinancialChart (Gold + MF NAV)
- TradeBottomSheet (Gold + MF Lumpsum/SIP + MF Redeem)
- Notifications collection (SIP success, SIP failed, investment success, redemption completed)
- Wallet + wallet_transactions collection
- Admin analytics framework (Stat/StatCard, CSV export)

### Admin Console (`AdminMutualFundsConsole.tsx`)
8 tabs: Overview · Funds · Investors · Transactions · SIPs · Providers · Analytics · Settings
- SIP Success/Failure rate KPIs, Avg SIP, Avg lumpsum, Avg holding days
- Highest-AUM AMC, Fastest-growing category
- Category + AMC distribution bars
- Daily lumpsum-vs-redemption 14-day chart
- Execute-due-SIPs button (dry-run + real)
- Full config editor (min amounts, retry policy, KYC gate, maintenance mode, NAV sync)
- Wired into Layout sidebar & main.tsx router; role matrix updated (super_admin, admin, finance_manager, investment_manager)

### Business rules honored
- No KYC required to browse / SIP / lumpsum. KYC gate ONLY on redemption (per config).
- Long-press confirm on all TradeBottomSheet interactions (from Sprint 10.5 review).

### Testing
- New pytest suite `test_mutual_funds_iter36.py` — 21 tests PASS
- Full regression: **668 pass / 2 skip / 10 pre-existing failures (unrelated to Sprint 11)**
    - The 10 failures are in `test_notifications`, `test_push_notifications`, `test_mfb_backend` (OTP/Stripe), `test_kyc_gate_iter19`, `test_iter20_kyc_removal`, `test_withdrawals` — all touching untouched modules.
- Admin `yarn build` — 0 errors
- Mobile lint — 0 errors (16 warnings only)
- Mobile smoke test — /mutual-funds renders premium UI

### Files added / modified
- ADD: `/app/backend/mutual_funds/{__init__,providers,seed,engine,ai,routes}.py`
- ADD: `/app/backend/tests/test_mutual_funds_iter36.py`
- ADD: `/app/frontend/src/api/mutualFunds.ts`
- ADD: `/app/frontend/app/mutual-funds/{_layout,index,explore,portfolio,sips,goals,compare,watchlist,advisor,orders}.tsx`
- ADD: `/app/frontend/app/mutual-funds/fund/[id].tsx`
- ADD: `/app/admin/src/pages/AdminMutualFundsConsole.tsx`
- EDIT: `/app/backend/server.py` (attach mutual_funds)
- EDIT: `/app/frontend/app/(tabs)/index.tsx` (Home MF tile)
- EDIT: `/app/admin/src/main.tsx` + `Layout.tsx` (route + sidebar + roles)

---
## Stabilization Sprint (June 2026, post Sprint 11)

Freeze on new features. Full stabilization pass.

### Regression: 697/697 PASS · 2 skipped · 0 failed 🎯
Fixed 11 previously failing tests (10 pre-existing + 1 new S11 supplemental).
Details in `/app/PRODUCTION_READINESS_REPORT.md`.

### Critical bug fix
Admin Audit page was crashing (React: "Objects are not valid as a React child")
because 49 legacy rows had `target` stored as a dict. Root cause: `forex/routes.py`
was passing the meta payload as `target` kwarg. Fix:
- Backend: `admin.py::_log_action` defensively coerces `target` to `str|None`
- Backend: `forex/routes.py` corrected to pass `meta=` kwarg
- Data: 49 legacy rows migrated in place
- Frontend: `AdminAuditLogs.tsx` defensive render
- Frontend: new admin-wide `ErrorBoundary` around `<Outlet />` so any future page-level crash cannot brick the SPA

### Perf & indexes
Added production-grade indexes (MF: 12 indexes, shared: 12 more). Hot-path
p50 ~10 ms.

### Deliverable
`/app/PRODUCTION_READINESS_REPORT.md` — sign-off document with caveats.

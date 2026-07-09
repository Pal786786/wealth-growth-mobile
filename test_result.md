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

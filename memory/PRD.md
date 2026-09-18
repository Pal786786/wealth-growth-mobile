## Investment Calculator Module (Phase 1 + Phase 2 — DONE)
- Mobile: `/invest/calculator` with 4 tabs, animated counters, SVG growth chart, reinvest toggle, plus Save Plan / Share / PDF action row + "Saved Plans" header chip → `/invest/plans`.
- Mobile: `/invest/plans` saved-plans list with cards (per-card Share/PDF/Delete), empty-state CTA, pull-to-refresh. Web fallback uses `window.confirm` for delete and save-success prompts.
- Backend: `calculator_config` singleton + `saved_plans` collection. Endpoints: public `GET /api/calculator/config`, admin `GET/PUT /api/admin/calculator/config`, user `GET/POST/GET-one/PUT/DELETE /api/calculator/plans[/{id}]`. Per-user 50-plan cap.
- Admin Web: `/calculator-config` page in sidebar.
- PDF: `expo-print` → `expo-sharing` produces branded gradient-header PDF via `src/utils/calcExport.ts`.
- Share: React Native `Share` API with plain-text snapshot.


# My Funding Bank — PRD

## Product
A premium Expo React Native (iOS + Android) fintech super-app combining digital wallet,
recharge/bill payments, investments (MF/Stocks/Gold/FD/Govt schemes), travel booking,
insurance, and a rewards/referral program — built with FastAPI + MongoDB backend.

## Brand
- Name: **My Funding Bank**
- Primary `#38BDF8`, Secondary `#0EA5E9`, Accent `#7DD3FC`, Background `#FFFFFF`, Text `#0F172A`
- Logo: stylized bull head + rising chart inside a sky-blue gradient tile

## Tech Stack
- Frontend: Expo SDK 54, Expo Router, TypeScript, react-native-safe-area-context,
  lucide-react-native, expo-linear-gradient, react-native-qrcode-svg, expo-clipboard,
  expo-web-browser
- Backend: FastAPI + Motor (MongoDB)
- Auth: JWT (email/password) + mocked mobile OTP (`123456`)
- Payments: Stripe Checkout (test key) — wallet top-up flow

## Implemented Features
- Authentication: signup, email/mobile login, mobile OTP, JWT session, /auth/me
- Home dashboard: total balance, portfolio/gold value, quick actions grid (8 actions),
  trending stocks (LIVE prices) horizontal, trending mutual funds, recent transactions, rewards CTA
- Wallet: balance, transaction history, add money via Stripe checkout,
  send money (UPI/mobile), receive money via QR code (UPI deep link)
- Recharge: mobile prepaid recharge with 2% cashback (auto-credited)
- Bills: 8 bill categories (electricity, water, gas, dth, broadband, fastag, insurance, mobile postpaid)
- Investments: Mutual Funds, **Live Stocks via Alpha Vantage (BSE)** — RELIANCE/TCS/HDFCBANK/INFY/ICICIBANK/BHARTIARTL/ITC/LT,
  Digital Gold (with SIP), Fixed Deposits, Government Schemes, Portfolio view with asset allocation
- Travel: Flight & Hotel booking (search & deals, instant book deducts wallet)
- Insurance: Health/Life/Motor/Travel plans with policy purchase
- Rewards: points, cashback total, badges, leaderboard
- Referral: share/copy code, leaderboard, ₹50 per referral
- Profile: avatar, KYC (PAN+Aadhaar verify), theme toggle (light/dark), sign out
- Notifications screen
- Light + Dark mode (system + manual toggle)

## Real Integrations
- **Stripe Checkout** for wallet top-up (demo fallback when `STRIPE_API_KEY=sk_test_emergent` placeholder)
- **Alpha Vantage** for live BSE stock quotes — 12 h MongoDB cache to respect 25 req/day free limit;
  budget of 4 AV calls per `/api/invest/stocks` request; falls back to cache or seed data on rate limit

## Critical Endpoints
- `POST /api/auth/signup`, `POST /api/auth/login`
- `POST /api/auth/otp/request`, `POST /api/auth/otp/verify`
- `GET /api/auth/me`, `GET /api/dashboard/summary`
- `GET /api/wallet`, `GET /api/wallet/transactions`
- `POST /api/wallet/send`, `POST /api/wallet/recharge`, `POST /api/wallet/billpay`
- `POST /api/wallet/topup/create-session`, `GET /api/wallet/topup/status/{session_id}`
- `GET /api/invest/{mutual-funds,stocks,gold-price,fixed-deposits,govt-schemes}`
- `POST /api/invest/buy`, `GET /api/invest/portfolio`
- `GET /api/travel/{flights,hotels}`, `POST /api/travel/book`, `GET /api/travel/bookings`
- `GET /api/insurance/plans`, `POST /api/insurance/buy?plan_id=...`, `GET /api/insurance/policies`
- `GET /api/rewards`, `GET /api/referral/leaderboard`
- `POST /api/profile/kyc`, `PUT /api/profile`
- `GET /api/calculator/config` (public), `GET/PUT /api/admin/calculator/config` (admin)

## Mocked / Not-real
- **Mobile OTP** is mocked (always `123456`)
- **Travel & Insurance bookings** debit the wallet but no real provider — simulated confirmations
- **Mutual Fund NAVs** are static (no real MF feed) — only stocks are live
- **KYC verification** auto-marks "verified" — no real PAN/Aadhaar API
- **Recharge & Bills** debit wallet but no real telecom/utility provider
- **AI investment suggestions** were skipped per user choice

---
## Sprint 12.2 — Withdrawal Module (June 2026)
Full production withdrawal flow with **Cashfree Payouts** integration + hybrid
auto-approval engine. Reuses verified bank accounts from Sprint 12.1.

### Business rules (all configurable via Admin Console)
- Min ₹100, Max per-txn ₹2,00,000, Daily ₹5,00,000, Monthly ₹20,00,000
- Max 5 requests/day; only 1 in-flight (pending/under_review/approved/processing)
- Hybrid approval: ≤ ₹25,000 → auto-approve; > ₹25K → manual admin approval;
  > ₹2L → hard-reject (admin override endpoint available)
- Compliance-hold kill-switch for platform-wide pause
- OTP required (6-digit / 5-min / 3 attempts / 30s resend)
- Only Sprint 12.1 verified bank accounts (Penny-Drop verified) eligible
- KYC-verified required (existing gate)

### Payout provider
- **Cashfree Payouts** (`payout-api.cashfree.com` v2 / 2024-01-01) — configured
  via Admin Console with client_id / client_secret / sandbox|production env.
- **Demo provider** auto-fallback when creds missing (dev / testing).
- Provider abstraction (`/app/backend/withdrawals_payout/`) supports adding
  more providers in future.

### New endpoints (backend)
- User: (existing user endpoints unchanged; `/wallet/withdrawals/settings` now
  exposes Sprint 12.2 fields)
- Admin (Sprint 12.2 additions):
  - `POST /api/admin/withdrawals/{wid}/dispatch-payout` — manually (re)dispatch
    a Cashfree payout for an approved withdrawal
  - `POST /api/admin/withdrawals/{wid}/mark-utr` — manually stamp UTR + complete
  - `POST /api/admin/withdrawals/create-override` — admin-authored withdrawal
    (bypasses OTP + hard-reject cap with `override_hard_reject=true`)
  - `GET  /api/admin/withdrawals/payout/providers` — provider registry + config status
  - `POST /api/admin/withdrawals/payout/test` — connectivity check

### Mocked / demo
- Demo payout provider always succeeds & stamps a `MFB<12-digit>` UTR.
- To simulate failure in demo: use an account number containing the string `FAIL`.
- Real Cashfree creds required for production payouts.

---
## Sprint 12.2.1 — Wallet UPI QR Top-up (MFB-owned QR only, June 2026)

**Goal**: Add a scan-QR path to Wallet Top-up while preserving all existing
payment methods (UPI ID / Card / Net Banking) — Razorpay production flow
unchanged.

### Rules
- Only **MFB-owned** UPI QR codes accepted (whitelisted VPAs + optional domain
  match). Third-party QRs are rejected client- and server-side with a friendly
  "This QR is not supported for Wallet Top-up." message.
- Wallet is **never credited** without a successful Razorpay webhook — the
  existing HMAC-verified webhook is the sole source of truth.
- QR intent URI is **server-crafted** (never assembled by client) to prevent
  tampering.
- Idempotency-Key honoured through the existing payments engine — duplicate
  requests return the same order.
- Kill-switch: admin can flip `enabled=false` to disable QR path platform-wide
  without touching any other payment method.

### Admin console (new)
- `GET/PUT /api/admin/wallet/qr/config` — merchant name, merchant category
  code, allowed VPAs list, allowed VPA domains list, min/max amount, note
  template, enable/disable flag.
- `GET /api/admin/wallet/qr/scans` — audit list of scanned QRs (user id,
  order id, payee VPA, amount, timestamp, match type).

### Configuration required to go live
Admin must populate `allowed_vpas` (and optionally `allowed_vpa_domains`)
under Admin Console once Razorpay generates the merchant's UPI collect
handle(s). Until then the QR flow returns "not supported" for every scan
by design.

### Mobile permission
Camera permission (`NSCameraUsageDescription` + `expo-camera` plugin block)
handled with graceful denial + "Open Settings" fallback.

---
## Sprint 12.3 · Phase A — Finance Ledger Foundation (June 2026)

Double-entry, immutable finance journal + Chart of Accounts + enhanced audit
trail + user passbook + idempotent backfill.

**Chart of Accounts** — `assets:*`, `liab:*`, `rev:*`, `exp:*`, `eq:*`, `susp:*`.
Every journal entry is BALANCED (sum(DR) == sum(CR)) and IMMUTABLE — reversals
are new negated entries linked to the original.

**Collections created**
- `finance_journal` — the immutable ledger (unique-index dedupe_key)
- `finance_ledger_balances` — denormalized per-account balance
- `finance_audit_trail` — enhanced audit (IP / device / actor / before / after)
- `finance_migrations` — backfill run reports (audit)

**Backfill** — one-time, admin-triggered, idempotent, supports dry-run.
Migrated 199 historical rows across wallet_ledger / payments / withdrawals /
gold / mutual_funds / forex / referrals on activation.

**Endpoints**
- User: `GET /api/wallet/passbook`, `GET /api/wallet/passbook/{id}`
- Admin: journal search / balances / balance-by-account / reverse /
  audit query / backfill (dry_run|apply) / backfill status

**Mobile**
- New `/app/wallet/passbook.tsx` screen — running-balance passbook with
  date-range filter, grouped-by-day rows, per-row detail modal
  (opening/closing/UTR/reference/journal_id with copy).

**Phase B** (Reconciliation, Settlement Dashboard, PDF/Excel/CSV Reports,
Provider Settlement) queued next — will start after Phase A validation.

**Phase C** (Recharts finance dashboards, Finance Alerts) queued after Phase B.

---
## Sprint 12.3 · Phase B — Reconciliation + Reports + Settlements (June 2026)

Read-only reconciliation engine, mismatch queue, admin Settlement Dashboard
KPIs, per-provider settlement views, on-demand PDF/Excel/CSV finance report
exports. Zero journal mutations.

**Reconciliation** — 6 modules (payments, withdrawals, wallet, gold,
mutual_funds, forex) → matched | pending | mismatch | manual_review.
Idempotent per `pair_key`. Admin can retry / resolve / ignore / add notes,
all audited.

**Settlement Dashboard KPIs** — total deposits/withdrawals, wallet balance,
platform liability, provider balance (per provider), fees, GST, refunds,
failed payments, pending withdrawals/settlements, net revenue. Filterable
by today / week / month / quarter / year / custom.

**Provider Settlements** — Razorpay + Cashfree, with settlement id / amount /
date / status / fees / GST / UTR / delay hours.

**Reports** — PDF (ReportLab, branded, KPI cards + tables + footer w/ page
numbers), Excel (openpyxl, multi-sheet w/ frozen headers + currency
formatting), CSV. On-demand only, no persistence. Types: daily / weekly /
monthly / quarterly / yearly / deposit / withdrawal / gold / mf / forex /
fees / tax. Filters: date range, provider, module, user, status.

**Admin UI** — new `/finance` page with 4 tabs: Dashboard (Recharts
ComposedChart + Pie), Reconciliation queue, Settlements viewer, Reports
Export Center.

**Deps**: `reportlab==4.2.5`, `openpyxl==3.1.5`.

**Phase C** (queued): Recharts finance dashboards polish, Finance Alerts
(settlement fail / large withdrawal / ledger mismatch / negative balance /
provider offline / high failure rate) with in-app + email notification.

---
## Sprint 12.3 · Phase C — Finance Alerts + Provider Health (June 2026)

Background finance alert engine + provider health probes + in-process
scheduler. Read-only, non-invasive.

**13 alert rules** evaluated every 15 min via scheduler:
settlement_failed / provider_offline / high_payment_failure_rate /
ledger_mismatch / negative_balance / large_withdrawal / large_refund /
large_wallet_adjustment / high_mismatch_rate / low_provider_balance /
cashfree_unavailable / razorpay_unavailable / pending_settlement_exceeded.

**Severities**: info / warning / critical  →  **Statuses**: active / acknowledged / resolved.

**Provider Health** — derives online/degraded/offline from 24h success/failure
counters (Razorpay + Cashfree + Live Market + MF + Gold). Exposes circuit
breaker + backoff status.

**Admin UI** — new "Alerts" and "Health" tabs in Finance Console with full
workflow (ack/resolve/note + audit trail).

**Deps**: none new. All admin actions audited.

**Final PRR**: `/app/PRODUCTION_READINESS_REPORT_v2.md` — feature completion
matrix, security checklist, performance summary, Go-Live + Beta→GA
deployment checklist.

---

## Sprint 15.1 — Demo Account Reset & Virtual Wallet Recharge (COMPLETE)

**Scope**: Production-quality demo account reset. Demo trading wallet stays INR
(default ₹10,00,000, configurable via Admin → Forex Settings → Default Demo Balance).
Real wallets (`wallets`/`transactions`/`wallet_ledger`) are NEVER touched.

**Backend** (`/app/backend/demo_reset.py`):
- `POST /api/demo/reset` (user) · `GET /api/demo/reset/history` (user)
- `POST /api/admin/demo/reset/{user_id}` (admin, audited) · `GET /api/admin/demo/reset/history`
- Reset: closes open forex positions (close_reason=demo_reset), cancels pending
  orders, ARCHIVES (never deletes) positions/orders/history under `reset_id`,
  closes+archives copied demo trades (copy_relationships/follows preserved),
  resets `forex_balances` to configured default, writes `demo_reset_history`
  record {reset_id, initiated_by(kind/id/label), previous_balance, new_balance,
  positions_closed, orders_cancelled, copy_trades_closed, ts} + a `demo_reset`
  marker event in the new session's forex_history.
- Legacy `POST /api/forex/balance/reset` delegates to the full reset.
- `forex/engine.py` list_positions/list_history and copy_trading user queries
  exclude `archived: true` docs (fresh session view, data retained).

**Mobile**: Profile → "DEMO WALLET" card (balance testID `demo-wallet-balance`,
button testID `reset-demo-btn`) with confirmation (window.confirm on web,
Alert.alert on native) + success summary.

**Admin SPA**: Users page → amber "Reset Demo" button per row with confirm +
result alert. SPA rebuilt & deployed to `/app/backend/static/admin-ui/`
(bundle `index-DSqoye2Y.js`). Admin-UI HTML now served with
`Cache-Control: no-cache` (NoCacheHTMLStaticFiles in server.py) so stale
bundles can never be cached after redeploys.

**Tests**: `tests/test_sprint_151_demo_reset.py` 9/9 PASS; regressions
(Finnhub 22, forex 56) all green. E2E verified via testing_agent + browser.

**PENDING USER ACTION**: `https://wealth-growth-mobile.emergent.host` (published
domain) still serves the pre-Sprint-15.0 snapshot (`index-DKB8rA1W.js`,
last-modified 13 Jul). User must click **Publish** to ship Sprint 15.0 + 15.1
to production, then agent should verify the emergent.host URL in a browser.
Finnhub production API key also still needs to be entered by user in
Admin → Live Market → Providers.

---

## Sprint 16.0 — Professional Trading Chart (COMPLETE)

**Chart**: TradingView Lightweight Charts (bundled, served same-origin at
/api/chart/index.html — no CDN) inside WebView (native) / iframe (web).
Features live: OHLC candlesticks + line toggle, 7 timeframes (1m/5m/15m/30m/1H/4H/D1),
volume histogram (green/red per direction, hidden if unavailable), crosshair OHLC+V
legend, bid/ask price lines, position entry line with floating PnL, TP/SL dashed
lines, buy/sell execution markers, pinch/zoom/pan, infinite scroll → automatic
historical backfill, indicator registry (window.Indicators) ready for EMA/SMA/RSI/
MACD/Bollinger next sprint.

**Backend** (`market_candles.py`):
- Live forming 1m candle built from unified ProviderManager tick stream (ingest
  hook inside refresh_once — ONE scheduler, no second price engine). Tick-count
  volume until official Finnhub bar replaces it at next sync.
- Historical OHLC ONLY from Finnhub REST, cached in `market_price_history`
  (meta: `market_history_meta`), incremental append, never re-fetch cached
  ranges, 60s per-series throttle. Preloads: 1m→2d, 5m→7d, 15m/30m→30d,
  1h→1y (covers 4H), 1d→5y. 4h aggregated from cached 1h Finnhub bars.
- `GET /api/market/candles/{symbol}?tf=&limit=&before=` (before → older-chunk backfill).

**Key gotcha**: chart HTML pins `localization.locale: "en-US"` — environments
reporting "en-US@posix" crash Intl inside lightweight-charts → blank canvas.

**Tests**: tests/test_sprint_160_candles.py 19/19 PASS; testing_agent E2E 100%
green (iteration_46). Regressions all green.

**Still pending user actions**: (1) Publish to emergent.host (still serving
pre-15.0 snapshot), (2) enter Finnhub API key in Admin → Live Market → Providers
to activate LIVE prices + historical candle backfill (currently MOCK ticks).

**Next sprint (planned)**: indicators — EMA, SMA, RSI, MACD, Bollinger Bands via
the existing window.Indicators registry + message protocol (addIndicator/removeIndicator).

---

## Sprint 16.1 — Professional Trading Panel MT5-style (COMPLETE) + 16.2/16.3 core

**Delivered**: unified commission engine (forex/costs.py — fixed_per_lot/per_side/
round_turn, INR/USD, per-trade immutable snapshot, net PnL settlement, applies to
demo + copy trading), pending limit/stop orders (placement validation, trigger in
existing mark loop, fill at live quote, drag on chart), position ops (partial
close 25/50/75/custom, reverse, double, modify TP/SL via sheet or chart drag),
order-cost estimates (margin/commission/spread/swap/total + R:R), chart drawing
tools (trend/hline/vline/rect/fib/text/erase, persisted per user+symbol+chartKey
in `chart_objects`), indicators EMA/SMA/BB/VWAP overlays + RSI/MACD/ATR synced
oscillator sub-pane (toggle modal, persisted in `chart_prefs`), Multi-Chart
workspace /forex/multi-chart (single/dual-v/dual-h/quad, independent
symbol/TF/indicators/drawings per pane, workspace persisted), Admin Trading Costs
card + Commission Collected report (day/week/month/symbol/user).

**Tests**: tests/test_sprint_161_trading_panel.py 19/19 + sprint160 19/19 PASS.
testing_agent iteration_47: all green after 2 HIGH fixes (pending-price-input JSX,
index.html default dispatch for extraHandlers) — both re-verified in browser.

**KNOWN GOTCHA**: chart HTML message dispatch — handleMsg switch MUST keep the
`default:` case calling window.__chart.extraHandlers[m.type] or setIndicator/
setTool/setObjects/setDraggable silently stop working.

**Deferred to next sprints (user-approved backlog)**:
- 16.2: Stochastic/CCI/ADX/Williams %R, SuperTrend/Ichimoku, pane reorder/
  collapse/height, per-indicator source/color/style settings UI, indicator
  templates (Scalping/Intraday/Swing/Gold/Crypto), max-3-pane management.
- 16.3: fullscreen double-tap, long-press context menu, symbol linking,
  cross-pane crosshair sync, timeframe sync option, tablet 6-chart, ray/arrow
  drawing tools.

**Still pending USER actions**: Publish to emergent.host (serves pre-15.0
snapshot) · enter Finnhub API key for LIVE prices + history backfill.

---
## Sprint 16.2a–16.2g + 16.3 (2026-07-15) — Candle 500 investigation & fix

**Investigation (evidence-only sprints 16.2a-e)**: production (emergent.host)
returned HTTP 500 (~11s) on /api/market/candles for ALL 9 OANDA symbols while
BTC/crypto/indices returned 200 with live-tick candles. Bisected via public
API (before=future isolates read path → healthy, 179-818 finnhub bars already
stored). Deployment drift eliminated in 16.2f/g: build-identity stamp added to
/api/market/debug/config (build_info.json + LIVE sha256 of market_candles.py,
forex/feed.py, server.py) — after republish, production == repo byte-identical,
yet forex 500s persisted on HEAD. Production runtime logs are NOT accessible
(deployment_agent = static scan only; support confirms no log viewer).

**Sprint 16.3 FIX (market_candles.py only)**:
1. ensure_history: naive last_sync_at (motor tz_aware=False) minus tz-aware
   _now_dt() → TypeError → 500 once meta existed. Now normalized to UTC-aware.
   (Full traceback was captured in preview repro at line 300.)
2. _store_bars: de-dupes bars by t (one op per (symbol,tf,t) per bulk) and
   catches BulkWriteError → salvages partial success, logs writeErrors verbatim.
3. Route: ensure_history/backfill_older wrapped — sync failure NEVER 500s the
   read path; sync.reason carries "sync_error:<Class>: <msg>" for diagnosis.

**Tests**: /app/backend/tests/test_sprint_163_candle_fix.py (19) +
test_sprint_163_e2e_public.py (23, by testing_agent) — 42/42 pass
(iteration_48.json). Charts render for XAUUSD/BTCUSD in preview browser.

**KNOWN GOTCHA**: local market_price_history contains ~800k legacy Sprint-7.x
tick rows {symbol, ts, price, provider} → unique index sym_tf_t can NEVER
build (E11000 dup (sym,null,null) at startup, warning in logs). Writes still
work. Cleanup/migration NOT authorized yet.

**PENDING USER ACTION**: republish to emergent.host so the 16.3 fix reaches
production; then verify stamp_id cbbce4b5b1d34594a12625edb63b5113 in
/api/market/debug/config and re-probe XAUUSD/GBPUSD/EURUSD (expect 200; the
first sync will also finally persist meta, enabling the 60s throttle and
REDUCING Finnhub usage).

---
## Sprint 16.3a/16.3b (2026-07-15) — Production verified + pipeline stabilized

**16.3a verification**: after user published (deployment 314dc0a), production ran
byte-identical 16.3 code. All 6 symbols returned HTTP 200 (500s GONE). The real
production exception finally surfaced via sync.reason: **NetworkTimeout** from
Atlas during _store_bars bulk write (~10s socket limit). Charts rendered for all
5 symbols in real browser vs published chart engine + data; dup live rows in
prod DB (upsert races) caused lightweight-charts "Value is null" asserts.

**16.3b fixes (market_candles.py only)**:
1. _store_bars → bounded batches (STORE_CHUNK_OPS=400/bulk), returns
   {stored, last_ok_t, complete}; ensure_history persists meta up to last
   successful batch (resume, not refetch); backfill_older extends oldest_t
   only when complete (no gaps).
2. get_candles → unique ascending timestamps guaranteed (finnhub bar preferred
   over live duplicate). API shape unchanged.

**Tests**: 52/52 (test_sprint_163b_stabilize.py 10 + 163_candle_fix 19 +
163_e2e_public 23). Build stamp 59e0b0cab3264e929ef69d1c26a046c8,
market_candles.py sha 0cf03595b16beecc….

**PENDING USER ACTION**: republish → verify prod: first call per symbol syncs
(seconds), subsequent <1s (throttled via persisted meta), no dup timestamps,
no chart asserts.

---
## Sprint 16.3c (2026-07-15) — Self-diagnosing candle sync + cooldown

Production (still on 16.3b stamp 59e0b0ca — the 82b2bd89 fallback-index build
NEVER deployed; publish pipeline stalled) began returning provider_unavailable
for XAUUSD too (fetch worked earlier same day). Backoff inactive, credits OK →
failure branch invisible without prod logs.

**Changes (market_candles.py only)**:
1. _fetch_finnhub_bars records exact exit branch per (symbol,res) in
   _fetch_diag: no_provider_or_key / backed_off / unmapped_symbol /
   http_429_rate_limited / http_<code>:<body> / no_data / exception:<cls>.
   Surfaced as sync.detail in the API response (additive field).
2. 60s failure cooldown (_fetch_fail_until) — failing fetches aren't
   re-attempted on every request (protects credits, flat response times).
3. Build also carries the 16.3b-r2 fallback index (sym_tf_t_nu non-unique)
   which never reached production.

Tests 52/52. Stamp for publish verification is in build_info.json (16.3c).

---
## Sprint 17 Phase 1 (2026) — Real MT5 Account Opening Module

**Backend**: /app/backend/real_accounts.py (isolated module, attach pattern).
- MT5AccountService (single MT5 seam): create_real_account / get_account /
  disable_account / reset_password / sync_account. Env: MT5_MANAGER_API_URL,
  MT5_MANAGER_LOGIN, MT5_MANAGER_PASSWORD, MT5_SERVER. NOT configured →
  honest {success:false, error_code:MT5_UNAVAILABLE}; NO fake account numbers.
- Collections: real_trading_accounts (unique user_id+account_type),
  real_account_audit (append-only), real_account_config (_id=defaults,
  admin-editable: mt5_server/account_type/currency/leverage/group/trade_mode/
  initial_balance). kyc_status field seeded NOT_REQUIRED for future sprint.
- States: NOT_CREATED→PENDING→ACTIVE|FAILED(→retry)|SUSPENDED(admin).
- User APIs: POST /api/real-account/apply, GET /api/real-account,
  GET /api/real-account/status, POST /api/real-account/retry.
- Admin APIs: GET /api/admin/real-accounts(?status=), GET+/{id} (with history),
  POST /{id}/retry|suspend|activate, GET/PUT /api/admin/real-accounts-config.
- Mounted in server.py after demo_reset; ensure_indexes on startup.

**Frontend**: /app/frontend/app/profile/real-account.tsx (full state machine
UI, email pre-filled+validated); profile tab row "Real Trading Account".

**Tests**: 16/16 tests/test_real_accounts.py + 7/7 test_sprint17_regression.py
(testing agent) — iteration_49.json FULL PASS incl. demo isolation + secret
leak scans + cross-user isolation.

**PENDING for production activation**: broker MT5 Manager/Web API credentials
(env vars above) + adapter endpoint paths may need matching to the actual
broker API (currently generic REST shape in MT5AccountService._call /
create_real_account). Also still pending: publish of Sprint 16.3c build
(stamp 88cdce88…) — candle sync self-diagnosis + fallback index NOT yet in
production.

## Sprint 18 — MSG91 Real SMS OTP (backend-proxied Widget flow)

**Backend**: /app/backend/security_extras.py
- Env vars (backend-only, never in frontend/bundle/DB/logs): MSG91_AUTHKEY,
  MSG91_WIDGET_ID, MSG91_TOKEN, OTP_DEMO_MODE.
- Gating: OTP_DEMO_MODE=true → demo; keys present + not demo → LIVE MSG91
  Widget server-to-server flow (https://control.msg91.com/api/v5/widget):
  sendOtpMobile → reqId (stored in otp_codes.req_id, provider=msg91_widget,
  no plaintext/hash) → verifyOtp(reqId,otp) → accessToken → verifyAccessToken.
- Resend: sendOtpMobile again; on rejection falls back to retryOtp with the
  previous reqId. Send failure → 502 (never fake success).
- Kept intact: 30s cooldown, 5/hour rate limit, 5 verify attempts, 5-min TTL,
  consumed/replay protection, sms_logs audit.
- Forgot-password via mobile in live mode uses the widget session
  (password_resets.via=msg91_widget) — verify through verify_otp(purpose=reset).
- Admin Demo-OTPs page hides OTPs when MSG91 env keys are live.
- Identifier normalization: 10-digit Indian numbers → 91-prefixed, no '+'.

**Tests**: tests/test_msg91_otp.py — 8/8 pass (mocked provider: gating,
normalization, send/verify/replay, retry fallback, 502, attempt cap). Demo
regression verified via curl. 103/103 core suites still pass.

**PENDING**: user adding MSG91 env vars via platform UI, then live SMS test
to +918556939970. MSG91 auth key must have IP Security DISABLED (egress IPs
are dynamic on this cluster).

### Sprint 18.1 — Admin Panel MSG91 Widget configuration (Mongo-backed)
- Config resolution priority in security_extras._msg91_live_cfg():
  1) env vars MSG91_AUTHKEY+MSG91_WIDGET_ID (platform Secrets)
  2) Mongo api_settings.sms_provider: api_key=Authkey, extra.provider=msg91_widget,
     extra.widget_id (+extra.server_token stored, extra.test_mobile for testing).
  OTP_DEMO_MODE=true (env) forces demo globally; force_demo/is_enabled in admin
  doc gate the DB path.
- api_settings.py: sms_provider catalog fields now include widget_id,
  server_token, test_mobile. _public_doc masks sensitive extra keys
  (server_token/key_secret/client_secret/token); PUT preserves masked
  round-trips (values containing '•' keep stored secret) for api_key + extra.
  PUT validates msg91_widget config (400 if Authkey/Widget ID missing).
- Test Connection (POST /admin/api-settings/sms_provider/test): for
  msg91_widget sends a REAL OTP SMS to extra.test_mobile via sendOtpMobile
  (validates Authkey+WidgetID); without test_mobile falls back to balance.php
  authkey check.
- Admin UI (/app/admin/src/pages/ApiManagement.tsx): provider dropdown
  (msg91_widget recommended / msg91 / twilio / firebase), MSG91 setup hint box,
  password-type inputs for sensitive fields, save error detail shown.
  Rebuilt → /app/admin/dist + /app/backend/static/admin-ui (index-D0TAKYjr.js).
- Verified E2E via API: save validation, masking, masked round-trip preserve,
  live routing (fake key → 502, no demo bypass), demo-otps hides in live mode,
  Test Connection surfaces real MSG91 AuthenticationFailure.
- Tests: tests/test_msg91_otp.py now 10/10 (added DB-config + env-priority).
  test_api_management 24/24 (fixed fork-state empty stock_market key from env).
- STILL PENDING: real MSG91 credentials → live SMS send+verify to
  +918556939970 before claiming production readiness.

### Sprint 18.2 — MSG91 HTTP 302 redirect fix (production Test Connection)
- Root symptom: production POST to control.msg91.com/api/v5/widget/sendOtpMobile
  returns HTTP 302 (dev pod gets 200 with same request shape → egress/WAF
  behavior, possibly MSG91 IP-security or CDN challenge on datacenter IPs).
- Fix in security_extras._msg91_widget_call: browser User-Agent header; manual
  3xx handling — logs Location (redacted-safe), re-POSTs (method+body
  preserved) ONLY to https *.msg91.com targets (authkey never sent elsewhere),
  max 3 hops → 508 on loop; non-2xx provider body snippet logged.
- Test Connection message now includes the redirect Location when a 3xx is
  not followable → actionable diagnosis in the admin UI.
- Tests: test_msg91_otp.py 14/14 (added 4 redirect tests w/ httpx MockTransport).
- Production check performed remotely via prod admin API: prod HAS Sprint 18.1
  code (fields+config saved: provider=msg91_widget, key+widget_id set,
  test_mobile +918556939970) but NOT this 18.2 fix → user must Publish again,
  then re-run Test Connection. If still 302, the shown Location reveals cause
  (verify IP Security OFF on MSG91 authkey).
- Live SMS still NOT confirmed.

### Sprint 18.3 — MSG91 "HTTP 200: None" diagnostics + KYC/balance guidance
- Prod redeploy fixed the 302 (browser UA); MSG91 now answers HTTP 200 but with
  a body lacking type/message (likely empty) → root cause per user's MSG91
  dashboard: account KYC PENDING + wallet ₹0 → MSG91 blocks sends at account
  level (their OTP Logs show no requests).
- security_extras: _msg91_widget_call now attaches _raw (400-char body snippet
  with all request secret values scrubbed) + _content_type to every response
  and warn-logs them; new _msg91_err() builds human errors (message → raw →
  EMPTY-body note → redirect location) used by sms_logs and Test Connection.
- api_settings Test Connection: HTTP 200 is NEVER treated as success (requires
  type=="success"); failure hints now detect kyc/verification/balance keywords
  and empty-body case → tells admin to complete KYC + add wallet balance.
- Tests: 38/38 (msg91 14 + api_management 24). Demo fallback still intact.
- ACTION FOR USER: complete MSG91 KYC + add balance; Publish to get the
  diagnostic build; re-run Test Connection. Live SMS still NOT confirmed.

### Sprint 18.4 — OTP Health View + 503 fix
- New admin endpoint GET /api/admin/sms-logs (super_admin/admin): recent 150
  sms_logs entries + 24h stats {total,sent,failed} + mode
  (live_msg91_widget/demo/live_<provider>). No secrets/OTPs in payload.
- Test Connection attempts now also logged to sms_logs (purpose=test_connection).
- issue_otp live send failure now raises 503 (was 502 — Cloudflare replaces
  origin 502/504 bodies with its HTML error page, hiding our JSON detail).
- New admin page /otp-health (AdminOtpHealth.tsx): mode badge, 24h stat cards,
  most-recent-failure banner w/ KYC-balance guidance, filterable table (time,
  mobile, purpose, provider, result, error), 10s auto-refresh. Nav added for
  super_admin+admin. Admin rebuilt → index-D341p9RK.js (copied to
  backend/static/admin-ui). Verified via screenshot with live data.
- Verified prod behavior: /auth/otp/request returns 502 (old build) with NO
  demo fallback. Prod still on pre-18.3 build — user must Publish again.
- MSG91 account facts (user): KYC pending + ₹0 wallet → MSG91 blocks sends.
  Guidance: complete KYC (e-KYC via Aadhaar or manual docs), add balance
  (min ~₹1000), AND register entity on DLT platform (TRAI requirement for
  India SMS). Tests 14/14 pass.

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

## Mocked / Not-real
- **Mobile OTP** is mocked (always `123456`)
- **Travel & Insurance bookings** debit the wallet but no real provider — simulated confirmations
- **Mutual Fund NAVs** are static (no real MF feed) — only stocks are live
- **KYC verification** auto-marks "verified" — no real PAN/Aadhaar API
- **Recharge & Bills** debit wallet but no real telecom/utility provider
- **AI investment suggestions** were skipped per user choice

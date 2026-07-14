"""My Funding Bank — Fintech Super App Backend."""
import os
import uuid
import logging
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional, Any, Dict

import bcrypt
import httpx
import jwt
import stripe
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr

import admin as admin_module
import admin_extra
import api_settings as api_settings_module
import ai_invest
import super_app
import push as push_module
import security_extras
import wallet_module
import wallet_pdf
import kyc_module
import withdrawal_module
import ai_advisor_module
import notifications_module
import market_module

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
STRIPE_API_KEY = os.environ.get("STRIPE_API_KEY", "")
ALPHA_VANTAGE_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "")

stripe.api_key = STRIPE_API_KEY

client = AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]

app = FastAPI(title="My Funding Bank")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("mfb")


# ---------- Helpers ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False


def create_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "iat": now_utc(),
        "exp": now_utc() + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def gen_id(prefix: str = "id") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------- Models ----------
class SignupReq(BaseModel):
    full_name: str
    email: EmailStr
    mobile: str
    password: str
    referral_code: Optional[str] = None


class LoginReq(BaseModel):
    identifier: str  # email or mobile
    password: str


class OtpRequestReq(BaseModel):
    mobile: str


class OtpVerifyReq(BaseModel):
    mobile: str
    otp: str
    full_name: Optional[str] = None  # for signup via OTP


class UserOut(BaseModel):
    user_id: str
    full_name: str
    email: str
    mobile: str
    referral_code: str
    kyc_status: str = "pending"
    created_at: datetime


class TokenOut(BaseModel):
    token: str
    user: UserOut


class WalletOut(BaseModel):
    balance: float
    currency: str = "INR"


class TxOut(BaseModel):
    tx_id: str
    type: str  # credit/debit
    category: str  # topup, send, recharge, bill, etc.
    amount: float
    description: str
    status: str  # success, pending, failed
    counterparty: Optional[str] = None
    created_at: datetime


class SendMoneyReq(BaseModel):
    recipient: str  # mobile or upi id
    amount: float
    note: Optional[str] = ""


class RechargeReq(BaseModel):
    operator: str
    mobile: str
    amount: float
    plan_name: Optional[str] = "Custom"


class BillPayReq(BaseModel):
    biller_type: str  # electricity, water, gas, dth, broadband, fastag, insurance
    biller_name: str
    consumer_number: str
    amount: float


class InvestReq(BaseModel):
    asset_id: str
    asset_type: str  # mutual_fund, stock, gold, fd, govt
    asset_name: str
    amount: float
    units: Optional[float] = None
    sip: bool = False


class BookingReq(BaseModel):
    booking_type: str  # flight, hotel, bus, train
    from_loc: Optional[str] = None
    to_loc: Optional[str] = None
    travel_date: str
    passengers: int = 1
    amount: float
    title: str  # e.g. "IndiGo 6E-203 DEL→BLR"
    meta: Optional[Dict[str, Any]] = None


class StripeCheckoutReq(BaseModel):
    amount: float  # INR
    platform: str = "native"  # native or web


# ---------- Seed Data ----------
MUTUAL_FUNDS = [
    {"id": "mf_axis_bluechip", "name": "Axis Bluechip Fund", "category": "Large Cap", "nav": 58.42, "returns_1y": 18.4, "risk": "Moderate"},
    {"id": "mf_parag_flexi", "name": "Parag Parikh Flexi Cap", "category": "Flexi Cap", "nav": 75.18, "returns_1y": 22.1, "risk": "Moderate"},
    {"id": "mf_quant_small", "name": "Quant Small Cap Fund", "category": "Small Cap", "nav": 232.10, "returns_1y": 38.6, "risk": "High"},
    {"id": "mf_sbi_bluechip", "name": "SBI Bluechip Fund", "category": "Large Cap", "nav": 82.30, "returns_1y": 16.2, "risk": "Moderate"},
    {"id": "mf_icici_pru", "name": "ICICI Pru Technology Fund", "category": "Sectoral", "nav": 198.55, "returns_1y": 24.9, "risk": "High"},
    {"id": "mf_hdfc_balanced", "name": "HDFC Balanced Advantage", "category": "Hybrid", "nav": 412.85, "returns_1y": 14.7, "risk": "Low"},
]
STOCKS = [
    {"id": "stk_reliance", "symbol": "RELIANCE", "av_symbol": "RELIANCE.BSE", "name": "Reliance Industries", "price": 2845.20, "change": 1.42},
    {"id": "stk_tcs", "symbol": "TCS", "av_symbol": "TCS.BSE", "name": "Tata Consultancy Services", "price": 4128.55, "change": -0.86},
    {"id": "stk_hdfcbank", "symbol": "HDFCBANK", "av_symbol": "HDFCBANK.BSE", "name": "HDFC Bank", "price": 1672.30, "change": 0.74},
    {"id": "stk_infy", "symbol": "INFY", "av_symbol": "INFY.BSE", "name": "Infosys", "price": 1854.10, "change": 2.18},
    {"id": "stk_icicibank", "symbol": "ICICIBANK", "av_symbol": "ICICIBANK.BSE", "name": "ICICI Bank", "price": 1284.45, "change": 1.05},
    {"id": "stk_bharti", "symbol": "BHARTIARTL", "av_symbol": "BHARTIARTL.BSE", "name": "Bharti Airtel", "price": 1602.80, "change": 0.62},
    {"id": "stk_itc", "symbol": "ITC", "av_symbol": "ITC.BSE", "name": "ITC Ltd", "price": 462.15, "change": -0.34},
    {"id": "stk_lt", "symbol": "LT", "av_symbol": "LT.BSE", "name": "Larsen & Toubro", "price": 3712.60, "change": 1.86},
]
GOLD_PRICE_PER_GRAM = 7820.50  # INR/g

FDS = [
    {"id": "fd_hdfc", "name": "HDFC Bank FD", "tenure_months": 12, "interest_rate": 7.1},
    {"id": "fd_sbi", "name": "SBI FD", "tenure_months": 24, "interest_rate": 7.0},
    {"id": "fd_icici", "name": "ICICI Bank FD", "tenure_months": 36, "interest_rate": 7.25},
    {"id": "fd_axis", "name": "Axis Bank FD", "tenure_months": 60, "interest_rate": 7.5},
]
GOVT_SCHEMES = [
    {"id": "gov_ppf", "name": "Public Provident Fund (PPF)", "rate": 7.1, "tenure": "15 years"},
    {"id": "gov_nps", "name": "National Pension Scheme (NPS)", "rate": 9.5, "tenure": "Till retirement"},
    {"id": "gov_bond", "name": "RBI Floating Rate Bond", "rate": 8.05, "tenure": "7 years"},
    {"id": "gov_ssy", "name": "Sukanya Samriddhi Yojana", "rate": 8.2, "tenure": "21 years"},
]

OPERATORS = ["Jio", "Airtel", "Vi", "BSNL"]
BILLER_TYPES = [
    {"id": "electricity", "name": "Electricity", "icon": "Zap"},
    {"id": "water", "name": "Water", "icon": "Droplets"},
    {"id": "gas", "name": "Gas", "icon": "Flame"},
    {"id": "dth", "name": "DTH", "icon": "Tv"},
    {"id": "broadband", "name": "Broadband", "icon": "Wifi"},
    {"id": "fastag", "name": "FASTag", "icon": "Car"},
    {"id": "insurance", "name": "Insurance", "icon": "Shield"},
    {"id": "mobile", "name": "Mobile Postpaid", "icon": "Smartphone"},
]

INSURANCE_PLANS = [
    {"id": "ins_health_basic", "type": "health", "name": "Health Shield Basic", "cover": 500000, "premium": 4999},
    {"id": "ins_health_plus", "type": "health", "name": "Health Shield Plus", "cover": 1000000, "premium": 8999},
    {"id": "ins_life_term", "type": "life", "name": "Term Life 1 Cr", "cover": 10000000, "premium": 12000},
    {"id": "ins_motor", "type": "motor", "name": "Comprehensive Motor", "cover": 500000, "premium": 6500},
    {"id": "ins_travel", "type": "travel", "name": "International Travel", "cover": 1000000, "premium": 2500},
]

FLIGHT_DEALS = [
    {"airline": "IndiGo", "code": "6E-203", "from": "DEL", "to": "BLR", "depart": "06:15", "arrive": "09:00", "duration": "2h 45m", "price": 4250},
    {"airline": "Air India", "code": "AI-505", "from": "DEL", "to": "BLR", "depart": "08:30", "arrive": "11:20", "duration": "2h 50m", "price": 5180},
    {"airline": "Vistara", "code": "UK-815", "from": "BOM", "to": "DEL", "depart": "07:00", "arrive": "09:10", "duration": "2h 10m", "price": 4890},
    {"airline": "SpiceJet", "code": "SG-101", "from": "BLR", "to": "BOM", "depart": "10:15", "arrive": "11:55", "duration": "1h 40m", "price": 3850},
    {"airline": "IndiGo", "code": "6E-742", "from": "DEL", "to": "GOI", "depart": "12:00", "arrive": "14:30", "duration": "2h 30m", "price": 4990},
]
HOTEL_DEALS = [
    {"name": "Taj Lake Palace", "city": "Udaipur", "rating": 4.9, "price_per_night": 28500, "image": "hotel_taj"},
    {"name": "The Oberoi", "city": "Mumbai", "rating": 4.8, "price_per_night": 18900, "image": "hotel_oberoi"},
    {"name": "ITC Grand Chola", "city": "Chennai", "rating": 4.7, "price_per_night": 12400, "image": "hotel_itc"},
    {"name": "Leela Palace", "city": "Bangalore", "rating": 4.8, "price_per_night": 15600, "image": "hotel_leela"},
    {"name": "Radisson Blu", "city": "Goa", "rating": 4.5, "price_per_night": 8200, "image": "hotel_radisson"},
]


# ---------- Auth Routes ----------
@api.get("/")
async def root():
    return {"app": "My Funding Bank", "status": "ok"}


async def _ensure_wallet(user_id: str):
    existing = await db.wallets.find_one({"user_id": user_id}, {"_id": 0})
    if not existing:
        await db.wallets.insert_one({
            "user_id": user_id,
            "balance": 5000.0,  # welcome bonus
            "currency": "INR",
            "created_at": now_utc(),
        })
        # log welcome tx
        await _add_tx(user_id, "credit", "bonus", 5000.0, "Welcome bonus", "success")


async def _add_tx(user_id: str, ttype: str, category: str, amount: float, description: str, status: str, counterparty: Optional[str] = None) -> Dict[str, Any]:
    tx = {
        "tx_id": gen_id("tx"),
        "user_id": user_id,
        "type": ttype,
        "category": category,
        "amount": float(amount),
        "description": description,
        "status": status,
        "counterparty": counterparty,
        "created_at": now_utc(),
    }
    await db.transactions.insert_one(tx)
    tx.pop("_id", None)
    return tx


def _user_public(u: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "user_id": u["user_id"],
        "full_name": u["full_name"],
        "email": u["email"],
        "mobile": u["mobile"],
        "referral_code": u["referral_code"],
        "kyc_status": u.get("kyc_status", "pending"),
        "created_at": u["created_at"],
    }


@api.post("/auth/signup", response_model=TokenOut)
async def signup(req: SignupReq):
    existing = await db.users.find_one({"$or": [{"email": req.email}, {"mobile": req.mobile}]})
    if existing:
        raise HTTPException(status_code=400, detail="User with this email or mobile already exists")
    user_id = gen_id("usr")
    referral_code = f"MFB{user_id[-6:].upper()}"
    user = {
        "user_id": user_id,
        "full_name": req.full_name,
        "email": req.email,
        "mobile": req.mobile,
        "password": hash_password(req.password),
        "referral_code": referral_code,
        "referred_by": req.referral_code,
        "kyc_status": "pending",
        "created_at": now_utc(),
        "reward_points": 100,  # signup bonus
    }
    await db.users.insert_one(user)
    await _ensure_wallet(user_id)
    # ---- Sprint 14: reward hooks (guarded, non-blocking) ----
    try:
        from mfb_rewards import engine as _rw
        await _rw.notify_event("signup", user_id, reference_id=user_id)
        if req.referral_code:
            from mfb_rewards import referrals as _rr
            referrer = await _rr.resolve_referrer(db, req.referral_code)
            if referrer and referrer.get("user_id") != user_id:
                await _rr.track_event(db, referrer["user_id"], user_id, req.referral_code, "registered")
                await _rr.award_referral_rewards(db, referrer["user_id"], user_id, "install")
    except Exception:
        pass
    token = create_token(user_id)
    return {"token": token, "user": _user_public(user)}


@api.post("/auth/login", response_model=TokenOut)
async def login(req: LoginReq):
    user = await db.users.find_one({"$or": [{"email": req.identifier}, {"mobile": req.identifier}]})
    if not user or not verify_password(req.password, user.get("password", "")):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token(user["user_id"])
    return {"token": token, "user": _user_public(user)}


# Mobile OTP — delegated to security_extras (no hardcoded 123456)
@api.post("/auth/otp/request")
async def request_otp(req: OtpRequestReq):
    return await security_extras.issue_otp(req.mobile, "login")


@api.post("/auth/otp/verify", response_model=TokenOut)
async def verify_otp(req: OtpVerifyReq):
    ok = await security_extras.verify_otp(req.mobile, req.otp, "login")
    if not ok:
        raise HTTPException(status_code=401, detail="Invalid or expired OTP")
    # Find or create user
    user = await db.users.find_one({"mobile": req.mobile})
    if not user:
        if not req.full_name:
            raise HTTPException(status_code=400, detail="Full name required for new user")
        user_id = gen_id("usr")
        user = {
            "user_id": user_id,
            "full_name": req.full_name,
            "email": f"{req.mobile}@mfb.in",
            "mobile": req.mobile,
            "password": hash_password(uuid.uuid4().hex),
            "referral_code": f"MFB{user_id[-6:].upper()}",
            "kyc_status": "pending",
            "created_at": now_utc(),
            "reward_points": 100,
            "login_method": "mobile",
        }
        await db.users.insert_one(user)
        await _ensure_wallet(user_id)
        # ---- Sprint 14: reward signup bonus (guarded) ----
        try:
            from mfb_rewards import engine as _rw
            await _rw.notify_event("signup", user_id, reference_id=user_id)
        except Exception:
            pass
    await db.users.update_one({"user_id": user["user_id"]}, {"$set": {"last_login_at": now_utc(), "failed_logins": 0}})
    # ---- Sprint 14: daily-login streak (guarded, idempotent per UTC day) ----
    try:
        from mfb_rewards import engine as _rw
        await _rw.record_daily_login(user["user_id"])
    except Exception:
        pass
    token = create_token(user["user_id"])
    return {"token": token, "user": _user_public(user)}


@api.get("/auth/me")
async def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    return _user_public(user)


# ---------- Wallet ----------
@api.get("/wallet", response_model=WalletOut)
async def get_wallet(user: Dict[str, Any] = Depends(get_current_user)):
    w = await db.wallets.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not w:
        await _ensure_wallet(user["user_id"])
        w = await db.wallets.find_one({"user_id": user["user_id"]}, {"_id": 0})
    return {"balance": w["balance"], "currency": w.get("currency", "INR")}


@api.get("/wallet/transactions")
async def get_transactions(user: Dict[str, Any] = Depends(get_current_user), limit: int = 50):
    items = await db.transactions.find({"user_id": user["user_id"]}, {"_id": 0, "user_id": 0}).sort("created_at", -1).to_list(limit)
    return items


@api.post("/wallet/send")
async def send_money(req: SendMoneyReq, user: Dict[str, Any] = Depends(get_current_user)):
    # KYC gate removed — only WITHDRAWALS require KYC per business flow.
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    w = await db.wallets.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not w or w["balance"] < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await db.wallets.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": -req.amount}})
    tx = await _add_tx(user["user_id"], "debit", "send", req.amount, req.note or f"Sent to {req.recipient}", "success", req.recipient)
    # award reward points (1 per 100)
    await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"reward_points": int(req.amount / 100)}})
    try:
        import tier_upgrades
        await tier_upgrades.check_and_upgrade(user["user_id"], trigger="send_money", trigger_detail=f"₹{req.amount}")
    except Exception:
        pass
    return {"success": True, "tx": tx}


@api.post("/wallet/recharge")
async def recharge(req: RechargeReq, user: Dict[str, Any] = Depends(get_current_user)):
    # KYC gate removed — only WITHDRAWALS require KYC per business flow.
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    w = await db.wallets.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not w or w["balance"] < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await db.wallets.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": -req.amount}})
    tx = await _add_tx(user["user_id"], "debit", "recharge", req.amount, f"{req.operator} recharge for {req.mobile} ({req.plan_name})", "success", req.mobile)
    cashback = round(req.amount * 0.02, 2)  # 2% cashback
    if cashback > 0:
        await db.wallets.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": cashback}})
        await _add_tx(user["user_id"], "credit", "cashback", cashback, "2% cashback on recharge", "success")
    await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"reward_points": 10}})
    try:
        import tier_upgrades
        await tier_upgrades.check_and_upgrade(user["user_id"], trigger="recharge", trigger_detail=f"₹{req.amount}")
    except Exception:
        pass
    return {"success": True, "tx": tx, "cashback": cashback}


@api.post("/wallet/billpay")
async def bill_pay(req: BillPayReq, user: Dict[str, Any] = Depends(get_current_user)):
    # KYC gate removed — only WITHDRAWALS require KYC per business flow.
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    w = await db.wallets.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not w or w["balance"] < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await db.wallets.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": -req.amount}})
    tx = await _add_tx(user["user_id"], "debit", "bill", req.amount, f"{req.biller_name} ({req.biller_type}) - {req.consumer_number}", "success", req.biller_name)
    await db.users.update_one({"user_id": user["user_id"]}, {"$inc": {"reward_points": 5}})
    try:
        import tier_upgrades
        await tier_upgrades.check_and_upgrade(user["user_id"], trigger="bill_payment", trigger_detail=f"₹{req.amount}")
    except Exception:
        pass
    return {"success": True, "tx": tx}


# ---------- Stripe Wallet Top-up ----------
async def _stripe_cfg() -> Dict[str, Any]:
    """Returns live Stripe config from api_settings, falling back to env."""
    cfg = await api_settings_module.get_config("payment_gateway_stripe")
    if cfg["is_demo"] and STRIPE_API_KEY.startswith(("sk_test_", "sk_live_")) and len(STRIPE_API_KEY) > 20:
        # Legacy env fallback (only when admin hasn't configured anything)
        return {"api_key": STRIPE_API_KEY, "is_demo": False, "mode": "live"}
    return cfg


@api.post("/wallet/topup/create-session")
async def create_topup_session(req: StripeCheckoutReq, user: Dict[str, Any] = Depends(get_current_user)):
    # KYC gate removed — DEPOSITS (top-ups) must work without KYC per business
    # flow. KYC is only required at Withdrawal.
    if req.amount < 10 or req.amount > 100000:
        raise HTTPException(status_code=400, detail="Amount must be between ₹10 and ₹1,00,000")

    cfg = await _stripe_cfg()

    # Demo mode: Stripe not configured — credit instantly
    if cfg["is_demo"]:
        session_id = gen_id("demo")
        await db.topups.insert_one({
            "session_id": session_id,
            "user_id": user["user_id"],
            "amount": req.amount,
            "status": "pending",
            "demo": True,
            "created_at": now_utc(),
        })
        return {"checkout_url": f"mfb://demo-pay?session_id={session_id}", "session_id": session_id, "demo": True, "mode": "demo"}

    stripe.api_key = cfg["api_key"]
    amount_paise = int(round(req.amount * 100))
    app_url = os.environ.get("APP_URL", "http://localhost:3000").rstrip("/")
    success_url = f"{app_url}/wallet/topup-success?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{app_url}/wallet/topup-cancel"
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            mode="payment",
            line_items=[{
                "price_data": {
                    "currency": "inr",
                    "product_data": {"name": "My Funding Bank wallet top-up"},
                    "unit_amount": amount_paise,
                },
                "quantity": 1,
            }],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "user_id": user["user_id"],
                "wallet_action": "topup",
                "amount_inr": str(req.amount),
            },
        )
    except stripe.error.StripeError as e:
        logger.exception("Stripe error — falling back to demo")
        # Never block the user: fallback to demo top-up
        session_id = gen_id("demo")
        await db.topups.insert_one({
            "session_id": session_id,
            "user_id": user["user_id"],
            "amount": req.amount,
            "status": "pending",
            "demo": True,
            "created_at": now_utc(),
            "fallback_reason": str(e),
        })
        return {"checkout_url": f"mfb://demo-pay?session_id={session_id}", "session_id": session_id, "demo": True, "mode": "demo"}
    # Track pending topup
    await db.topups.insert_one({
        "session_id": session.id,
        "user_id": user["user_id"],
        "amount": req.amount,
        "status": "pending",
        "created_at": now_utc(),
    })
    return {"checkout_url": session.url, "session_id": session.id, "demo": False, "mode": "live"}


@api.get("/wallet/topup/status/{session_id}")
async def topup_status(session_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    """Polled by client after returning from Stripe. Verifies & credits wallet."""
    pending = await db.topups.find_one({"session_id": session_id, "user_id": user["user_id"]}, {"_id": 0})
    if not pending:
        raise HTTPException(status_code=404, detail="Session not found")
    if pending["status"] == "completed":
        return {"status": "completed", "amount": pending["amount"]}

    # Demo mode: instant success
    if pending.get("demo"):
        await db.topups.update_one({"session_id": session_id}, {"$set": {"status": "completed", "completed_at": now_utc()}})
        amount = pending["amount"]
        await db.wallets.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": amount}})
        await _add_tx(user["user_id"], "credit", "topup", amount, "Wallet top-up (demo)", "success")
        return {"status": "completed", "amount": amount, "demo": True}

    cfg = await _stripe_cfg()
    if cfg["is_demo"]:
        # Should not reach here since demo branch above handles it, but be safe
        raise HTTPException(status_code=500, detail="Stripe not configured")
    stripe.api_key = cfg["api_key"]
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError:
        raise HTTPException(status_code=502, detail="Stripe lookup failed")
    if session.get("payment_status") == "paid":
        # Idempotent credit
        await db.topups.update_one({"session_id": session_id}, {"$set": {"status": "completed", "completed_at": now_utc()}})
        amount = pending["amount"]
        await db.wallets.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": amount}})
        await _add_tx(user["user_id"], "credit", "topup", amount, "Wallet top-up via card", "success")
        return {"status": "completed", "amount": amount}
    return {"status": session.get("payment_status", "pending"), "amount": pending["amount"]}


# ---------- Investments ----------
@api.get("/invest/mutual-funds")
async def list_mutual_funds():
    return MUTUAL_FUNDS


@api.get("/invest/stocks")
async def list_stocks(force: bool = False):
    """Returns stocks list. Live prices from Alpha Vantage cached in MongoDB (12h TTL).
    Free tier is 25 req/day so we cache aggressively. Falls back to seed prices on rate limit.
    """
    results = []
    cache_ttl_seconds = 12 * 3600  # 12 hours
    av_budget_per_call = 4  # max number of AV calls per stocks request

    # Resolve Alpha Vantage key dynamically from api_settings (falls back to env)
    av_cfg = await api_settings_module.get_config("stock_market")
    av_key = av_cfg["api_key"] or (ALPHA_VANTAGE_KEY if av_cfg["is_demo"] else "")
    is_demo_stocks = not av_key

    av_calls_made = 0
    for s in STOCKS:
        cached = await db.stock_cache.find_one({"symbol": s["symbol"]}, {"_id": 0})
        is_fresh = False
        if cached and cached.get("fetched_at"):
            fetched = cached["fetched_at"]
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=timezone.utc)
            age = (now_utc() - fetched).total_seconds()
            is_fresh = age < cache_ttl_seconds

        if is_fresh and not force and cached.get("price"):
            results.append({
                "id": s["id"], "symbol": s["symbol"], "name": s["name"],
                "price": cached["price"], "change": cached["change_pct"],
                "live": True, "as_of": cached["fetched_at"],
            })
            continue

        # Try fetching live (with budget)
        if av_key and av_calls_made < av_budget_per_call:
            av_calls_made += 1
            try:
                async with httpx.AsyncClient(timeout=8) as http:
                    r = await http.get(
                        "https://www.alphavantage.co/query",
                        params={
                            "function": "GLOBAL_QUOTE",
                            "symbol": s["av_symbol"],
                            "apikey": av_key,
                        },
                    )
                    data = r.json() or {}
                q = data.get("Global Quote") or data.get("GlobalQuote") or {}
                price_raw = q.get("05. price")
                change_raw = q.get("10. change percent")
                if price_raw and change_raw:
                    price = float(price_raw)
                    change_pct = float(change_raw.rstrip("%"))
                    await db.stock_cache.update_one(
                        {"symbol": s["symbol"]},
                        {"$set": {
                            "symbol": s["symbol"], "price": price,
                            "change_pct": change_pct, "fetched_at": now_utc(),
                        }},
                        upsert=True,
                    )
                    results.append({
                        "id": s["id"], "symbol": s["symbol"], "name": s["name"],
                        "price": price, "change": change_pct,
                        "live": True, "as_of": now_utc(),
                    })
                    continue
                # Rate limit / empty response
                if data.get("Note") or data.get("Information"):
                    logger.warning(f"Alpha Vantage rate limit: {data.get('Note') or data.get('Information')}")
            except Exception as e:
                logger.warning(f"Alpha Vantage fetch failed for {s['symbol']}: {e}")

        # Fallback: cached (even if stale) or seed
        if cached and cached.get("price"):
            results.append({
                "id": s["id"], "symbol": s["symbol"], "name": s["name"],
                "price": cached["price"], "change": cached["change_pct"],
                "live": True, "as_of": cached.get("fetched_at"),
                "mode": "live" if not is_demo_stocks else "demo",
            })
        else:
            # Seed jitter as last resort
            jittered = round(s["price"] * (1 + random.uniform(-0.002, 0.002)), 2)
            results.append({
                "id": s["id"], "symbol": s["symbol"], "name": s["name"],
                "price": jittered, "change": s["change"], "live": False,
                "mode": "demo",
            })
    return results


@api.get("/invest/gold-price")
async def gold_price():
    # Try admin-managed override first (set via Investment Manager)
    override = await db.app_settings.find_one({"_key": "gold_rate"}, {"_id": 0})
    cfg = await api_settings_module.get_config("gold_price")
    price = (override or {}).get("price_per_gram", GOLD_PRICE_PER_GRAM)
    return {
        "price_per_gram": price,
        "currency": "INR",
        "unit": "gram",
        "mode": "live" if (not cfg["is_demo"]) else "demo",
    }


@api.get("/invest/fixed-deposits")
async def list_fds():
    return FDS


@api.get("/invest/govt-schemes")
async def list_govt():
    return GOVT_SCHEMES


@api.post("/invest/buy")
async def invest_buy(req: InvestReq, user: Dict[str, Any] = Depends(get_current_user)):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    w = await db.wallets.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not w or w["balance"] < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await db.wallets.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": -req.amount}})
    holding = {
        "holding_id": gen_id("hld"),
        "user_id": user["user_id"],
        "asset_id": req.asset_id,
        "asset_type": req.asset_type,
        "asset_name": req.asset_name,
        "amount": float(req.amount),
        "units": req.units,
        "sip": req.sip,
        "created_at": now_utc(),
    }
    await db.holdings.insert_one(holding)
    holding.pop("_id", None)
    tx = await _add_tx(user["user_id"], "debit", "investment", req.amount, f"Bought {req.asset_name}", "success", req.asset_name)
    return {"success": True, "holding": holding, "tx": tx}


@api.get("/invest/portfolio")
async def portfolio(user: Dict[str, Any] = Depends(get_current_user)):
    holdings = await db.holdings.find({"user_id": user["user_id"]}, {"_id": 0, "user_id": 0}).to_list(500)
    # Simulate current value as 1.04x - 1.18x of invested
    by_type: Dict[str, Dict[str, float]] = {}
    total_invested = 0.0
    total_current = 0.0
    for h in holdings:
        mult = {"mutual_fund": 1.12, "stock": 1.08, "gold": 1.06, "fd": 1.04, "govt": 1.05}.get(h["asset_type"], 1.05)
        current_val = round(h["amount"] * mult, 2)
        h["current_value"] = current_val
        h["returns_pct"] = round((mult - 1) * 100, 2)
        by_type.setdefault(h["asset_type"], {"invested": 0, "current": 0})
        by_type[h["asset_type"]]["invested"] += h["amount"]
        by_type[h["asset_type"]]["current"] += current_val
        total_invested += h["amount"]
        total_current += current_val
    return {
        "holdings": holdings,
        "total_invested": round(total_invested, 2),
        "total_current": round(total_current, 2),
        "returns_pct": round(((total_current - total_invested) / total_invested * 100) if total_invested > 0 else 0, 2),
        "by_type": by_type,
    }


# ---------- Travel ----------
@api.get("/travel/flights")
async def list_flights(from_loc: Optional[str] = None, to_loc: Optional[str] = None):
    flights = FLIGHT_DEALS
    if from_loc:
        flights = [f for f in flights if f["from"].lower() == from_loc.lower()]
    if to_loc:
        flights = [f for f in flights if f["to"].lower() == to_loc.lower()]
    return flights if flights else FLIGHT_DEALS


@api.get("/travel/hotels")
async def list_hotels(city: Optional[str] = None):
    hotels = HOTEL_DEALS
    if city:
        hotels = [h for h in hotels if city.lower() in h["city"].lower()]
    return hotels if hotels else HOTEL_DEALS


@api.post("/travel/book")
async def travel_book(req: BookingReq, user: Dict[str, Any] = Depends(get_current_user)):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Invalid amount")
    w = await db.wallets.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not w or w["balance"] < req.amount:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await db.wallets.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": -req.amount}})
    booking = {
        "booking_id": gen_id("bkg"),
        "user_id": user["user_id"],
        "booking_type": req.booking_type,
        "title": req.title,
        "from_loc": req.from_loc,
        "to_loc": req.to_loc,
        "travel_date": req.travel_date,
        "passengers": req.passengers,
        "amount": req.amount,
        "status": "confirmed",
        "meta": req.meta,
        "created_at": now_utc(),
    }
    await db.bookings.insert_one(booking)
    booking.pop("_id", None)
    tx = await _add_tx(user["user_id"], "debit", "travel", req.amount, f"{req.booking_type.title()} booking: {req.title}", "success", req.title)
    cashback = await super_app.award_cashback(user["user_id"], req.amount, "travel")
    return {"success": True, "booking": booking, "tx": tx, "cashback": cashback}


@api.get("/travel/bookings")
async def my_bookings(user: Dict[str, Any] = Depends(get_current_user)):
    items = await db.bookings.find({"user_id": user["user_id"]}, {"_id": 0, "user_id": 0}).sort("created_at", -1).to_list(100)
    return items


# ---------- Insurance ----------
@api.get("/insurance/plans")
async def insurance_plans(ptype: Optional[str] = None):
    if ptype:
        return [p for p in INSURANCE_PLANS if p["type"] == ptype]
    return INSURANCE_PLANS


@api.post("/insurance/buy")
async def insurance_buy(plan_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    plan = next((p for p in INSURANCE_PLANS if p["id"] == plan_id), None)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    w = await db.wallets.find_one({"user_id": user["user_id"]}, {"_id": 0})
    if not w or w["balance"] < plan["premium"]:
        raise HTTPException(status_code=400, detail="Insufficient balance")
    await db.wallets.update_one({"user_id": user["user_id"]}, {"$inc": {"balance": -plan["premium"]}})
    policy = {
        "policy_id": gen_id("pol"),
        "user_id": user["user_id"],
        "plan_id": plan_id,
        "plan_name": plan["name"],
        "type": plan["type"],
        "cover": plan["cover"],
        "premium": plan["premium"],
        "status": "active",
        "created_at": now_utc(),
    }
    await db.policies.insert_one(policy)
    policy.pop("_id", None)
    await _add_tx(user["user_id"], "debit", "insurance", plan["premium"], f"{plan['name']} premium", "success", plan["name"])
    cashback = await super_app.award_cashback(user["user_id"], plan["premium"], "insurance")
    return {"success": True, "policy": policy, "cashback": cashback}


@api.get("/insurance/policies")
async def my_policies(user: Dict[str, Any] = Depends(get_current_user)):
    items = await db.policies.find({"user_id": user["user_id"]}, {"_id": 0, "user_id": 0}).to_list(100)
    return items


# ---------- Rewards & Referral ----------
@api.get("/rewards")
async def rewards(user: Dict[str, Any] = Depends(get_current_user)):
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0})
    points = u.get("reward_points", 0)
    cashback_total = await db.transactions.aggregate([
        {"$match": {"user_id": user["user_id"], "category": "cashback"}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    cashback = cashback_total[0]["total"] if cashback_total else 0
    referred = await db.users.count_documents({"referred_by": u["referral_code"]})
    badges = []
    if points >= 100:
        badges.append({"id": "starter", "name": "Starter", "icon": "Award"})
    if points >= 500:
        badges.append({"id": "pro", "name": "Pro Saver", "icon": "Trophy"})
    if referred >= 1:
        badges.append({"id": "influencer", "name": "Influencer", "icon": "Users"})
    if cashback >= 100:
        badges.append({"id": "cashback_hero", "name": "Cashback Hero", "icon": "Gift"})
    return {
        "reward_points": points,
        "cashback_earned": round(cashback, 2),
        "referral_code": u["referral_code"],
        "referrals_count": referred,
        "referral_earnings": referred * 50,
        "badges": badges,
    }


@api.get("/referral/leaderboard")
async def leaderboard():
    pipeline = [
        {"$group": {"_id": "$referred_by", "count": {"$sum": 1}}},
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    rows = await db.users.aggregate(pipeline).to_list(10)
    # join with referrer names
    out = []
    for r in rows:
        ref = await db.users.find_one({"referral_code": r["_id"]}, {"_id": 0, "full_name": 1, "referral_code": 1})
        if ref:
            out.append({"name": ref["full_name"], "referral_code": ref["referral_code"], "count": r["count"]})
    return out


# ---------- Bill payment helpers ----------
@api.get("/bills/types")
async def bill_types():
    return BILLER_TYPES


@api.get("/bills/operators")
async def operators():
    return OPERATORS


# ---------- Profile / KYC ----------
class KycReq(BaseModel):
    pan: str
    aadhaar: str


@api.post("/profile/kyc")
async def submit_kyc(req: KycReq, user: Dict[str, Any] = Depends(get_current_user)):
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"kyc_status": "verified", "pan": req.pan, "aadhaar_last4": req.aadhaar[-4:]}},
    )
    return {"success": True, "kyc_status": "verified"}


class ProfileUpdateReq(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None


@api.put("/profile")
async def update_profile(req: ProfileUpdateReq, user: Dict[str, Any] = Depends(get_current_user)):
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if updates:
        await db.users.update_one({"user_id": user["user_id"]}, {"$set": updates})
    u = await db.users.find_one({"user_id": user["user_id"]}, {"_id": 0, "password": 0})
    return _user_public(u)


# ---------- Home Dashboard Summary ----------
@api.get("/dashboard/summary")
async def dashboard_summary(user: Dict[str, Any] = Depends(get_current_user)):
    w = await db.wallets.find_one({"user_id": user["user_id"]}, {"_id": 0}) or {"balance": 0}
    holdings = await db.holdings.find({"user_id": user["user_id"]}, {"_id": 0}).to_list(500)
    invested = sum(h["amount"] for h in holdings)
    portfolio_value = 0.0
    gold_value = 0.0
    for h in holdings:
        mult = {"mutual_fund": 1.12, "stock": 1.08, "gold": 1.06, "fd": 1.04, "govt": 1.05}.get(h["asset_type"], 1.05)
        cv = h["amount"] * mult
        portfolio_value += cv
        if h["asset_type"] == "gold":
            gold_value += cv
    recent_tx = await db.transactions.find({"user_id": user["user_id"]}, {"_id": 0, "user_id": 0}).sort("created_at", -1).to_list(5)
    # Use cached live stocks for trending (no extra AV calls beyond cache)
    trending_stocks = await list_stocks()
    return {
        "wallet_balance": w["balance"],
        "portfolio_value": round(portfolio_value, 2),
        "portfolio_invested": round(invested, 2),
        "gold_value": round(gold_value, 2),
        "recent_transactions": recent_tx,
        "trending_stocks": trending_stocks[:4],
        "trending_funds": MUTUAL_FUNDS[:3],
    }


@api.get("/notifications-legacy", include_in_schema=False)
async def list_my_notifications(user: Dict[str, Any] = Depends(get_current_user), limit: int = 50):
    rows = await db.notifications.find({"user_id": user["user_id"]}, {"_id": 0, "user_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    unread = await db.notifications.count_documents({"user_id": user["user_id"], "read": False})
    return {"items": rows, "unread": unread}


@api.post("/notifications-legacy/mark-read", include_in_schema=False)
async def mark_read(user: Dict[str, Any] = Depends(get_current_user)):
    await db.notifications.update_many({"user_id": user["user_id"], "read": False}, {"$set": {"read": True}})
    return {"success": True}


# Mount
admin_module.attach(api, db, logger)
admin_extra.attach(api, db)
api_settings_module.attach(api, db)
ai_invest.attach(api, db, get_current_user, lambda: list_stocks(force=False), logger=logger)
super_app.attach(api, db, get_current_user, _add_tx, admin_module.get_current_admin, INSURANCE_PLANS, logger=logger)
push_module.attach(api, db, get_current_user)
security_extras.attach(api, db, get_current_user, admin_module.get_current_admin, push_module.send_push, logger_=logger)
import insurance_claims  # type: ignore
insurance_claims.attach(api, db, get_current_user, admin_module.get_current_admin, _add_tx, admin_module._log_action)
import tier_upgrades  # type: ignore
tier_upgrades.attach(api, db, get_current_user, admin_module.get_current_admin, super_app.TIERS)
import travel_admin  # type: ignore
travel_admin.attach(api, db, get_current_user, admin_module.get_current_admin, _add_tx, admin_module._log_action)
import tier_config  # type: ignore
tier_config.attach(api, db, admin_module.get_current_admin, admin_module._log_action)
import calculator_config  # type: ignore
calculator_config.attach(api, db, admin_module.get_current_admin, admin_module._log_action)
import calculator_plans  # type: ignore
calculator_plans.attach(api, db, get_current_user)
# Forex paper trading
from forex.feed import PriceFeed as _ForexFeed  # type: ignore  # noqa: E402
from forex.engine import TradingEngine as _ForexEngine  # type: ignore  # noqa: E402
from forex.routes import attach as _forex_attach, seed_settings as _forex_seed  # type: ignore  # noqa: E402
forex_feed = _ForexFeed()
forex_engine = _ForexEngine(db, forex_feed)
_forex_attach(api, db, forex_feed, forex_engine, get_current_user,
              admin_module.get_current_admin, admin_module._log_action)
import firebase_auth  # type: ignore
firebase_auth.attach(api, db, lambda payload: create_token(payload["user_id"]), now_fn=now_utc)
# Wallet v2 — double-entry ledger, payments, analytics, admin
wallet_module.attach(api, db, get_current_user,
                     admin_module.get_current_admin, admin_module._log_action)
# KYC & Compliance — extends users w/o touching auth. Provides require_kyc_approved gate.
kyc_module.attach(api, db, get_current_user,
                  admin_module.get_current_admin, admin_module._log_action,
                  send_push=security_extras.send_push_logged)
kyc_module.attach_bypass_routes(api, db, admin_module.get_current_admin,
                                admin_module._log_action)

# Sprint 2A — Withdrawal Management (backend + admin)
async def _notify_user(uid: str, title: str, message: str, deeplink: str = "/wallet"):
    try:
        await db.notifications.insert_one({
            "notif_id": f"nf_{__import__('secrets').token_hex(6)}",
            "user_id": uid, "title": title, "body": message,
            "read": False, "created_at": now_utc(),
            "deeplink": deeplink, "category": "wallet",
        })
        await security_extras.send_push_logged(
            recipients=[uid], data={"title": title, "message": message, "action_url": deeplink},
            batch_id=f"wd-{uid[-8:]}-{int(now_utc().timestamp())}")
    except Exception:
        pass

withdrawal_module.attach(
    api, db, get_current_user, admin_module.get_current_admin,
    admin_module._log_action,
    credit_wallet=wallet_module._credit_wallet,
    debit_wallet=wallet_module._debit_wallet,
    kyc_gate=kyc_module.require_kyc_approved,
    send_push=security_extras.send_push_logged,
    notify_user=_notify_user,
    build_receipt_pdf=wallet_pdf.build_receipt_pdf,
)

ai_advisor_module.attach(
    api,
    db=db,
    get_current_user=get_current_user,
    get_current_admin=admin_module.get_current_admin,
    log_action=admin_module._log_action,
    logger=logger,
)

notifications_module.attach(
    api, db=db, get_current_user=get_current_user,
    get_current_admin=admin_module.get_current_admin,
    send_push=security_extras.send_push_logged,
    log_action=admin_module._log_action, logger=logger,
)

market_module.attach(
    api, db=db, get_current_user=get_current_user,
    get_current_admin=admin_module.get_current_admin, logger=logger,
)

# ------ Sprint 13: Production health checks + Prometheus metrics ------
try:
    import health_monitoring as _health_mon
    _health_mon.attach(app, api, db=db, logger=logger)
except Exception as _e:
    logger.warning("health_monitoring not attached: %s", _e)

# ------ Sprint 14: MFB Rewards & Ecosystem (Internal Token Platform) ------
try:
    import mfb_rewards as _mfb_rewards
    _mfb_rewards.attach(api, app, db=db,
                          get_current_user=get_current_user,
                          get_current_admin=admin_module.get_current_admin,
                          logger=logger)
except Exception as _e:
    logger.warning("mfb_rewards not attached: %s", _e)

app.include_router(api)

# ------ Sprint 7 Slice 1: Market Data (multi-asset browser + provider layer) ------
try:
    import market_data as _mkt_data
    _mkt_data.attach(
        app,
        db=db,
        get_current_user=get_current_user,
        get_current_admin=admin_module.get_current_admin,
        logger=logger,
    )
    logger.info("market_data subsystem attached")
except Exception as _e:
    logger.warning(f"market_data attach failed: {_e}")

# ------ Sprint 7B.1 + 7B.2: Copy Trading (traders + leaderboard + copy engine + fan-out) ------
try:
    import copy_trading as _copy_trading
    _copy_trading.attach(
        app, db=db, get_current_user=get_current_user,
        get_current_admin=admin_module.get_current_admin,
    )
    logger.info("copy_trading subsystem attached (Sprint 7B.2)")
except Exception as _e:
    logger.warning(f"copy_trading attach failed: {_e}")

# ------ Sprint 7.5: Live Market Providers (TwelveData → Alpha Vantage → Mock with auto-fallback) ------
try:
    import market_providers as _market_providers
    _market_providers.attach(
        app, db=db,
        get_current_admin=admin_module.get_current_admin,
        log_action=admin_module._log_action,
    )
    # Sprint 14.1.1 — bridge the shared price manager into the forex feed so
    # order execution + UI + mark-to-market + chart + watchlist all read the
    # SAME live quote object.
    try:
        from forex.feed import attach_shared_manager as _forex_bridge
        _forex_bridge(_market_providers.get_manager())
    except Exception as _b:
        logger.warning(f"forex ↔ market_providers bridge failed: {_b}")
    logger.info("market_providers subsystem attached (Sprint 7.5)")
except Exception as _e:
    logger.warning(f"market_providers attach failed: {_e}")

# ------ Sprint 7C.1: AI Intelligence (signals + TA + watchlist + alerts) ------
try:
    import ai_intelligence as _ai_intelligence
    _ai_intelligence.attach(
        app, db=db, get_current_user=get_current_user,
        get_current_admin=admin_module.get_current_admin,
    )
    logger.info("ai_intelligence subsystem attached (Sprint 7C.1)")
except Exception as _e:
    logger.warning(f"ai_intelligence attach failed: {_e}")

# ------ Sprint 7C.2: AI Market News & Analytics (news + calendar + summary + analytics) ------
try:
    import ai_news as _ai_news
    _ai_news.attach(
        app, db=db, get_current_user=get_current_user,
        get_current_admin=admin_module.get_current_admin,
    )
    logger.info("ai_news subsystem attached (Sprint 7C.2)")
except Exception as _e:
    logger.warning(f"ai_news attach failed: {_e}")

# ------ Sprint 8: Production Payments (Razorpay) ------
_payments_ctx: Optional[Dict[str, Any]] = None
try:
    import payments as _payments
    _payments_ctx = _payments.attach(
        app, db=db, get_current_user=get_current_user,
        get_current_admin=admin_module.get_current_admin,
    )
    logger.info("payments subsystem attached (Sprint 8)")
except Exception as _e:
    logger.warning(f"payments attach failed: {_e}")

# ------ Sprint 9: Real KYC Platform (v2) ------
try:
    import kyc_v2 as _kyc_v2
    _kyc_v2.attach(
        app, db=db, get_current_user=get_current_user,
        get_current_admin=admin_module.get_current_admin,
    )
    logger.info("kyc_v2 subsystem attached (Sprint 9)")
except Exception as _e:
    logger.warning(f"kyc_v2 attach failed: {_e}")

# ------ Sprint 10: Gold Investment Platform ------
try:
    import gold as _gold
    _gold.attach(
        app, db=db, get_current_user=get_current_user,
        get_current_admin=admin_module.get_current_admin,
    )
    logger.info("gold subsystem attached (Sprint 10)")
except Exception as _e:
    logger.warning(f"gold attach failed: {_e}")

# ------ Sprint 11: Mutual Funds & SIP Platform ------
try:
    import mutual_funds as _mf
    _mf.attach(
        app, db=db, get_current_user=get_current_user,
        get_current_admin=admin_module.get_current_admin,
    )
    logger.info("mutual_funds subsystem attached (Sprint 11)")
except Exception as _e:
    logger.warning(f"mutual_funds attach failed: {_e}")

# ------ Sprint 12.1: Bank Account Verification (Cashfree Penny Drop) ------
try:
    import bank_verification as _bv
    _bv.attach(
        app, db=db, get_current_user=get_current_user,
        get_current_admin=admin_module.get_current_admin,
    )
    logger.info("bank_verification subsystem attached (Sprint 12.1)")
except Exception as _e:
    logger.warning(f"bank_verification attach failed: {_e}")

# ------ Sprint 12.2.1: Wallet QR Top-up (MFB-owned UPI QR only) ------
try:
    if _payments_ctx and _payments_ctx.get("engine"):
        import wallet_qr as _wqr
        _wqr.attach(
            app, db=db, get_current_user=get_current_user,
            get_current_admin=admin_module.get_current_admin,
            payments_engine=_payments_ctx["engine"],
            log_action=getattr(admin_module, "_log_action", None),
        )
        logger.info("wallet_qr subsystem attached (Sprint 12.2.1)")
    else:
        logger.warning("wallet_qr skipped — payments engine not initialised")
except Exception as _e:
    logger.warning(f"wallet_qr attach failed: {_e}")

# ------ Sprint 12.3 Phase A: Finance Ledger (double-entry journal) ------
try:
    import finance_ledger as _fl
    from finance_ledger.engine import Journal as _Journal, set_default_journal
    from finance_ledger.audit import AuditTrail as _AuditTrail, set_default_trail
    from finance_ledger.hooks import install_wallet_hooks
    _fl_journal = _Journal(db)
    _fl_trail = _AuditTrail(db)
    set_default_journal(_fl_journal)
    set_default_trail(_fl_trail)
    _fl.attach(
        app, db=db, get_current_user=get_current_user,
        get_current_admin=admin_module.get_current_admin,
        notifier=globals().get("notify_user"),
    )
    import wallet_module as _wallet_module
    install_wallet_hooks(_wallet_module)
    @app.on_event("startup")
    async def _fl_startup():
        try:
            await _fl_journal.ensure_indexes()
            await _fl_trail.ensure_indexes()
            logger.info("finance_ledger indexes ensured")
        except Exception as _e2:
            logger.warning(f"finance_ledger index init failed: {_e2}")
    logger.info("finance_ledger subsystem attached (Sprint 12.3 Phase A)")
except Exception as _e:
    logger.warning(f"finance_ledger attach failed: {_e}")

# Serve built admin SPA at /api/admin-ui/
# Production deploy only ships /app/backend, so the SPA build is bundled inside
# backend/static/admin-ui (committed). Preview also has /app/admin/dist as
# fallback for legacy local-dev workflows.
ADMIN_DIST_CANDIDATES = [
    Path(__file__).parent / "static" / "admin-ui",   # /app/backend/static/admin-ui (PROD)
    Path("/app/admin/dist"),                         # legacy local-dev location
]
ADMIN_DIST = next((p for p in ADMIN_DIST_CANDIDATES if p.exists() and (p / "index.html").exists()), None)
if ADMIN_DIST is not None:
    app.mount("/api/admin-ui", StaticFiles(directory=str(ADMIN_DIST), html=True), name="admin-ui")
    logger.info(f"Admin SPA mounted at /api/admin-ui/ from {ADMIN_DIST}")
else:
    logger.warning("Admin SPA dist not found — /api/admin-ui/ will 404. Run `cd /app/admin && yarn build` and copy dist/* to /app/backend/static/admin-ui/")

# Serve corporate marketing website (Next.js static export) at /api/site/
WEBSITE_DIST = Path(__file__).parent / "static" / "website"
if WEBSITE_DIST.exists() and (WEBSITE_DIST / "index.html").exists():
    app.mount("/api/site", StaticFiles(directory=str(WEBSITE_DIST), html=True), name="marketing-site")
    logger.info(f"Marketing site mounted at /api/site/ from {WEBSITE_DIST}")
else:
    logger.warning("Marketing site dist not found — /api/site/ will 404. Run `cd /app/website && SITE_BASE_PATH=/api/site yarn build` and copy out/* to /app/backend/static/website/")

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("mobile", unique=True)
    await db.users.create_index("user_id", unique=True)
    await db.users.create_index("referral_code")
    await db.wallets.create_index("user_id", unique=True)
    await db.transactions.create_index([("user_id", 1), ("created_at", -1)])
    await db.topups.create_index("session_id", unique=True)
    await db.admins.create_index("email", unique=True)
    await db.admins.create_index("admin_id", unique=True)
    await db.insurance_claims.create_index("claim_id", unique=True)
    await db.insurance_claims.create_index([("user_id", 1), ("created_at", -1)])
    await db.insurance_claims.create_index([("status", 1), ("created_at", -1)])
    await db.tier_upgrades.create_index("upgrade_id", unique=True)
    await db.tier_upgrades.create_index([("user_id", 1), ("at", -1)])
    await db.tier_upgrades.create_index([("new_tier_id", 1), ("at", -1)])
    await db.bookings.create_index("booking_id", unique=True)
    await db.bookings.create_index([("status", 1), ("created_at", -1)])
    await db.bookings.create_index([("refund_status", 1), ("updated_at", -1)])
    await db.saved_plans.create_index("plan_id", unique=True)
    await db.saved_plans.create_index([("user_id", 1), ("created_at", -1)])
    await db.forex_balances.create_index("user_id", unique=True)
    await db.forex_positions.create_index("position_id", unique=True)
    await db.forex_positions.create_index([("user_id", 1), ("status", 1), ("opened_at", -1)])
    await db.forex_positions.create_index([("status", 1), ("symbol_id", 1)])
    await db.forex_orders.create_index([("user_id", 1), ("ts", -1)])
    await db.forex_history.create_index([("user_id", 1), ("ts", -1)])
    # ---- Stabilization sprint: production-critical indexes ----
    try:
        await db.notifications.create_index([("user_id", 1), ("created_at", -1)])
        await db.notifications.create_index([("user_id", 1), ("read", 1), ("created_at", -1)])
        await db.notifications.create_index([("user_id", 1), ("category", 1)])
        await db.notifications.create_index("notif_id", unique=True, sparse=True)
        await db.wallet_transactions.create_index([("user_id", 1), ("created_at", -1)])
        await db.wallet_transactions.create_index("tx_id", unique=True, sparse=True)
        await db.otp_codes.create_index([("mobile", 1), ("created_at", -1)])
        await db.otp_codes.create_index("expires_at", expireAfterSeconds=0)
        await db.kyc_profiles.create_index("user_id", unique=True)
        await db.bank_accounts.create_index([("user_id", 1), ("deleted", 1)])
        await db.bank_accounts.create_index("bank_id", unique=True, sparse=True)
        # Gold indexes (Sprint 10)
        await db.gold_transactions.create_index("tx_id", unique=True, sparse=True)
        await db.gold_transactions.create_index([("user_id", 1), ("created_at", -1)])
        await db.gold_holdings.create_index("user_id", unique=True, sparse=True)
        logger.info("stabilization: hot-path indexes ensured")
    except Exception as _e:
        logger.warning(f"index bootstrap warning: {_e}")
    # Seed tier config singleton if missing
    try:
        import tier_config as _tc  # type: ignore
        _tc._db = db
        await _tc.seed_config()
    except Exception as _e:
        logger.warning(f"tier_config seed failed: {_e}")
    # Seed calculator config singleton if missing
    try:
        import calculator_config as _cc  # type: ignore
        _cc._db = db
        await _cc.seed_config()
    except Exception as _e:
        logger.warning(f"calculator_config seed failed: {_e}")
    # Forex: seed settings + start price feed + engine
    try:
        await _forex_seed(db)
        # Apply admin's saved live_mode/api_key
        _fx_cfg = await db.forex_settings.find_one({"_id": "active"}) or {}
        forex_feed.set_live_mode(bool(_fx_cfg.get("live_mode", False)),
                                 td_api_key=_fx_cfg.get("twelve_data_api_key") or None)
        await forex_feed.start()
        await forex_engine.start()
        logger.info("forex feed + engine started")
    except Exception as _e:
        logger.warning(f"forex startup failed: {_e}")
    await admin_module.seed_admin(db, logger)
    await api_settings_module.seed_catalog()
    await super_app.seed_demo_catalogs()
    await super_app.seed_insurance_catalog(INSURANCE_PLANS)
    logger.info("MFB backend ready")


@app.on_event("shutdown")
async def shutdown():
    client.close()

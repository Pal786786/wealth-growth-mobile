"""Payment status enums + Pydantic request models."""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, validator


class OrderStatus(str, Enum):
    CREATED = "created"        # Order created, awaiting payment
    ATTEMPTED = "attempted"    # Client initiated checkout
    CAPTURED = "captured"      # Webhook-verified, wallet credited
    FAILED = "failed"          # Payment failed at gateway
    EXPIRED = "expired"        # Order timed out (usually 15 min)
    REFUNDED = "refunded"      # Fully refunded
    PARTIALLY_REFUNDED = "partially_refunded"


class PaymentMethod(str, Enum):
    UPI = "upi"
    CARD = "card"
    NETBANKING = "netbanking"
    WALLET = "wallet"
    OTHER = "other"


class RefundStatus(str, Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"


MIN_TOPUP_PAISE = 1_00       # ₹1

MAX_TOPUP_PAISE = 1_00_00000 # ₹1,00,000


class CreateOrderIn(BaseModel):
    amount_paise: int = Field(..., description="Amount in paise (min 100 = ₹1)")
    currency: str = "INR"
    method_hint: Optional[str] = None       # upi/card/netbanking (UI hint only)
    notes: Optional[dict] = None

    @validator("amount_paise")
    def _validate_amount(cls, v):
        if v < MIN_TOPUP_PAISE:
            raise ValueError(f"amount must be >= {MIN_TOPUP_PAISE} paise")
        if v > MAX_TOPUP_PAISE:
            raise ValueError(f"amount must be <= {MAX_TOPUP_PAISE} paise")
        return v

    @validator("currency")
    def _validate_currency(cls, v):
        if v.upper() != "INR":
            raise ValueError("only INR is supported")
        return v.upper()


class VerifyPaymentIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class RefundIn(BaseModel):
    payment_id: str = Field(..., description="Local payment_id")
    amount_paise: Optional[int] = Field(None, description="None = full refund")
    reason: str = Field("admin_initiated", max_length=200)
    notes: Optional[dict] = None


class ConfigPatch(BaseModel):
    demo_mode: Optional[bool] = None
    mode: Optional[str] = None          # "test" | "live"
    min_topup_paise: Optional[int] = None
    max_topup_paise: Optional[int] = None
    # Sensitive keys: only set here to update via admin panel; NEVER return
    key_id: Optional[str] = None
    key_secret: Optional[str] = None
    webhook_secret: Optional[str] = None

    @validator("mode")
    def _mode_ok(cls, v):
        if v is not None and v not in ("test", "live"):
            raise ValueError("mode must be 'test' or 'live'")
        return v


class RetryOrderIn(BaseModel):
    reason: Optional[str] = None

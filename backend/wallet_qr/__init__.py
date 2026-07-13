"""Sprint 12.2.1 — Wallet QR Top-up (MFB-owned UPI QR only).

Adds a QR-scan path for wallet top-up. Reuses the existing Razorpay engine
for order creation + verification + webhook credit — this module only:
  1. Validates that a scanned UPI URI's payee (`pa`) matches MFB's registered
     merchant VPAs.
  2. Creates a Razorpay order for the parsed / user-entered amount.
  3. Returns a signed UPI intent URI that the mobile app can open in any
     UPI app (GPay / PhonePe / Paytm / BHIM / etc.).

Wallet credit **never** happens here — always via the existing webhook path.
"""
from .routes import attach

__all__ = ["attach"]

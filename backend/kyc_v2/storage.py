"""Encrypted document storage helper (Fernet symmetric encryption).

When `KYC_ENCRYPTION_KEY` is set to a valid 32-byte urlsafe base64 key we
encrypt every payload before storing. If it's placeholder we still store the
documents (base64) but flag them as unencrypted so ops can catch it.
"""
from __future__ import annotations
import base64
import hashlib
import logging
import os
from typing import Dict, Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("kyc_v2.storage")

_KEY_ENV = (os.environ.get("KYC_ENCRYPTION_KEY") or "").strip()


def _fernet() -> Optional[Fernet]:
    if not _KEY_ENV or _KEY_ENV == "placeholder":
        return None
    try:
        # Accept both raw 32-byte urlsafe base64 keys AND arbitrary passphrases
        # (we derive a valid Fernet key via SHA-256 in that case).
        key = _KEY_ENV
        if len(key) != 44 or not key.endswith("="):
            derived = hashlib.sha256(key.encode()).digest()
            key = base64.urlsafe_b64encode(derived).decode()
        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        logger.warning("Fernet init failed: %s", e)
        return None


_F = _fernet()


def encrypt_blob(data: bytes) -> Tuple[str, bool]:
    """Return (base64-encoded ciphertext, encrypted_bool)."""
    if _F is None:
        return base64.b64encode(data).decode(), False
    ct = _F.encrypt(data)
    return base64.b64encode(ct).decode(), True


def decrypt_blob(b64_ct: str, encrypted: bool) -> Optional[bytes]:
    try:
        raw = base64.b64decode(b64_ct)
    except Exception:
        return None
    if not encrypted or _F is None:
        return raw
    try:
        return _F.decrypt(raw)
    except InvalidToken:
        logger.warning("KYC blob decrypt failed — invalid token")
        return None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encryption_status() -> Dict[str, object]:
    return {
        "encryption_enabled": _F is not None,
        "algorithm": "Fernet (AES-128-CBC + HMAC-SHA256)" if _F else "NONE (stored plain-base64)",
        "key_configured": bool(_KEY_ENV and _KEY_ENV != "placeholder"),
    }

"""OCR & Face-match provider stubs.

Both use deterministic outputs in demo mode so tests are stable. Real
implementations plug in Tesseract / AWS Rekognition / fal.ai / etc.
"""
from __future__ import annotations
import hashlib
import logging
import random
from typing import Any, Dict, Optional

logger = logging.getLogger("kyc_v2.providers.aux")


class DemoOCRProvider:
    provider = "demo"
    def is_configured(self) -> bool: return True

    async def parse(self, doc_type: str, data: bytes) -> Dict[str, Any]:
        """Extract deterministic fields keyed off the document hash so admins can
        cross-check consistency across uploads."""
        h = hashlib.sha256(data or b"empty").hexdigest()
        seeded = random.Random(h)
        first_names = ["Aarav", "Vivaan", "Reyansh", "Ishaan", "Kabir", "Riya", "Isha"]
        last_names = ["Sharma", "Verma", "Nair", "Iyer", "Reddy", "Menon"]
        name = f"{seeded.choice(first_names)} {seeded.choice(last_names)}"
        dob = f"{seeded.randint(1975, 2003)}-{seeded.randint(1,12):02d}-{seeded.randint(1,28):02d}"
        if doc_type == "pan":
            pan = (
                "".join(seeded.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(5))
                + "".join(str(seeded.randint(0, 9)) for _ in range(4))
                + seeded.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")
            )
            return {"ok": True, "provider": self.provider, "doc_type": "pan",
                    "fields": {"pan": pan, "name": name, "dob": dob,
                                "father_name": f"{seeded.choice(first_names)} {seeded.choice(last_names)}"},
                    "confidence": round(seeded.uniform(0.85, 0.98), 2),
                    "doc_hash": h}
        if doc_type == "aadhaar":
            aadhaar = "".join(str(seeded.randint(0, 9)) for _ in range(12))
            return {"ok": True, "provider": self.provider, "doc_type": "aadhaar",
                    "fields": {"aadhaar": aadhaar, "aadhaar_last4": aadhaar[-4:],
                                "name": name, "dob": dob,
                                "gender": seeded.choice(["M", "F"])},
                    "confidence": round(seeded.uniform(0.82, 0.97), 2),
                    "doc_hash": h}
        return {"ok": True, "provider": self.provider, "doc_type": doc_type,
                "fields": {"raw_length": len(data or b"")}, "confidence": 0.5,
                "doc_hash": h}


class DemoFaceMatchProvider:
    provider = "demo"
    def is_configured(self) -> bool: return True

    async def match(self, id_photo: bytes, selfie: bytes) -> Dict[str, Any]:
        """Deterministic similarity: high when hash prefixes overlap; low
        otherwise. Ensures tests are stable but exercise both branches."""
        if not id_photo or not selfie:
            return {"ok": False, "match": False, "score": 0.0,
                    "provider": self.provider, "message": "missing image"}
        h1 = hashlib.sha256(id_photo).hexdigest()
        h2 = hashlib.sha256(selfie).hexdigest()
        # Overlap in the first 12 hex chars → similarity score (0.60 baseline
        # if bytes are identical or similar prefix; scaled to 0.95 when equal)
        prefix_matches = sum(1 for a, b in zip(h1[:12], h2[:12]) if a == b)
        base = 0.60 if id_photo == selfie else 0.35
        boost = prefix_matches * 0.04
        # If images are exactly identical treat as high-confidence match
        if id_photo == selfie:
            score = 0.98
        else:
            score = min(0.95, base + boost)
        threshold = 0.65
        return {
            "ok": True, "match": bool(score >= threshold),
            "score": round(score, 3),
            "threshold": threshold,
            "provider": self.provider,
            "id_photo_hash": h1[:16], "selfie_hash": h2[:16],
        }


def get_ocr_provider() -> Any:
    return DemoOCRProvider()


def get_face_match_provider() -> Any:
    return DemoFaceMatchProvider()

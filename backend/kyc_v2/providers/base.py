"""Provider abstraction for KYC checks.

Each provider handles one type of check and can be swapped for a real API
without touching business logic. In demo mode we return deterministic OK
responses so the flow works end-to-end without external dependencies.
"""
from __future__ import annotations
from typing import Any, Dict, Optional, Protocol


class PanProvider(Protocol):
    provider: str
    def is_configured(self) -> bool: ...
    async def verify(self, pan: str, name: Optional[str] = None,
                      dob: Optional[str] = None) -> Dict[str, Any]: ...


class DigiLockerProvider(Protocol):
    provider: str
    def is_configured(self) -> bool: ...
    async def issue_authorization(self, redirect_uri: str,
                                    state: str, user_id: str) -> Dict[str, Any]: ...
    async def exchange_code(self, code: str, state: str) -> Dict[str, Any]: ...
    async def fetch_aadhaar(self, access_token: str) -> Dict[str, Any]: ...


class OCRProvider(Protocol):
    provider: str
    def is_configured(self) -> bool: ...
    async def parse(self, doc_type: str, data: bytes) -> Dict[str, Any]: ...


class FaceMatchProvider(Protocol):
    provider: str
    def is_configured(self) -> bool: ...
    async def match(self, id_photo: bytes, selfie: bytes) -> Dict[str, Any]: ...

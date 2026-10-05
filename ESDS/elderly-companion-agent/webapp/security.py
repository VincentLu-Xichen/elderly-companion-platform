from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from webapp.config import settings


password_hasher = PasswordHasher()


def hash_secret(value: str) -> str:
    return password_hasher.hash(value)


def verify_secret(hashed: str, value: str) -> bool:
    try:
        return password_hasher.verify(hashed, value)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _encryption_key() -> bytes:
    if settings.data_encryption_key:
        try:
            key = base64.urlsafe_b64decode(settings.data_encryption_key + "==")
        except ValueError as exc:
            raise RuntimeError("DATA_ENCRYPTION_KEY must be URL-safe base64") from exc
        if len(key) != 32:
            raise RuntimeError("DATA_ENCRYPTION_KEY must decode to exactly 32 bytes")
        return key
    return hashlib.sha256((settings.app_secret + ":data").encode("utf-8")).digest()


def encrypt_text(value: str) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_encryption_key()).encrypt(nonce, value.encode("utf-8"), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_text(value: Optional[str]) -> str:
    if not value:
        return ""
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    return AESGCM(_encryption_key()).decrypt(raw[:12], raw[12:], None).decode("utf-8")


def encrypt_json(value: Dict[str, Any]) -> str:
    return encrypt_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def decrypt_json(value: Optional[str]) -> Dict[str, Any]:
    if not value:
        return {}
    result = json.loads(decrypt_text(value))
    return result if isinstance(result, dict) else {}


def sign_session(kind: str, subject: str) -> str:
    payload = {
        "kind": kind,
        "sub": subject,
        "exp": int(time.time()) + settings.session_hours * 3600,
    }
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(settings.app_secret.encode(), encoded, hashlib.sha256).digest()
    return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def verify_session(token: Optional[str], kind: str) -> Optional[str]:
    if not token or "." not in token:
        return None
    encoded_text, signature_text = token.split(".", 1)
    encoded = encoded_text.encode()
    try:
        signature = base64.urlsafe_b64decode(signature_text + "==")
        expected = hmac.new(settings.app_secret.encode(), encoded, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(encoded_text + "=="))
    except (ValueError, json.JSONDecodeError):
        return None
    if payload.get("kind") != kind or int(payload.get("exp", 0)) < int(time.time()):
        return None
    subject = payload.get("sub")
    return str(subject) if subject else None


def new_csrf_token() -> str:
    return base64.urlsafe_b64encode(os.urandom(24)).rstrip(b"=").decode("ascii")


def csrf_matches(cookie_value: Optional[str], header_value: Optional[str]) -> bool:
    return bool(cookie_value and header_value and hmac.compare_digest(cookie_value, header_value))

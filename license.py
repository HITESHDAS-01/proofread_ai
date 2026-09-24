"""Offline license keys: HMAC-SHA256, no server required.

Format: APRO-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
  - 8 bytes random nonce (hex)
  - 8 bytes HMAC-SHA256(secret, nonce)[:8] (hex)
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# App secret — rotate to invalidate all previously issued keys.
_SECRET = bytes(
    b"\x41\x49\x50\x52\x30\x4f\x4f\x52\x5f\x4c\x49\x43\x5f\x4b\x45\x59"
    b"\x5f\x53\x45\x43\x52\x45\x54\x5f\x32\x30\x32\x36\x5f\x56\x31\x21"
)

_PREFIX = "APRO"
_NONCE_LEN = 8
_MAC_LEN = 8

# Single key for all customers — share this one key everywhere.
UNIVERSAL_KEY = "APRO-1FB1-7A0C-9C50-52C7-056B-5976-6070-2B89"


def _mac(nonce: bytes) -> bytes:
    return hmac.new(_SECRET, nonce, hashlib.sha256).digest()[:_MAC_LEN]


def generate_license_key() -> str:
    nonce = secrets.token_bytes(_NONCE_LEN)
    body = (nonce + _mac(nonce)).hex().upper()
    groups = [body[i : i + 4] for i in range(0, len(body), 4)]
    return "-".join([_PREFIX, *groups])


def _parse(key: str) -> bytes | None:
    raw = (key or "").strip().upper().replace(" ", "")
    if raw.startswith(_PREFIX + "-"):
        raw = raw[len(_PREFIX) + 1 :]
    raw = raw.replace("-", "")
    if len(raw) != (_NONCE_LEN + _MAC_LEN) * 2:
        return None
    try:
        return bytes.fromhex(raw)
    except ValueError:
        return None


def _normalize_display(key: str) -> str:
    return (key or "").strip().upper().replace(" ", "")


def is_valid_license_key(key: str) -> bool:
    try:
        if _normalize_display(key) == _normalize_display(UNIVERSAL_KEY):
            return True
        parsed = _parse(key)
        if parsed is None:
            return False
        nonce = parsed[:_NONCE_LEN]
        mac = parsed[_NONCE_LEN:]
        return hmac.compare_digest(mac, _mac(nonce))
    except Exception:
        return False


def license_suffix(key: str) -> str:
    parsed = _parse(key)
    if not parsed:
        return ""
    body = (parsed[:_NONCE_LEN] + parsed[_NONCE_LEN:]).hex().upper()
    return "…" + body[-6:]

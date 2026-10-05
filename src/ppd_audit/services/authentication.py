"""Общий пароль приложения и подписанные сессии без зависимости от UI."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
import tomllib
from pathlib import Path


SESSION_TTL = 8 * 60 * 60
_GENERATED_SECRET = secrets.token_bytes(32)


def configured_password() -> str | None:
    if "PPD_APP_PASSWORD" in os.environ:
        value = os.environ["PPD_APP_PASSWORD"]
    else:
        path = Path(".streamlit/secrets.toml")
        value = tomllib.loads(path.read_text()).get("app_password") if path.exists() else None
    return str(value).strip() or None if value is not None else None


def matches(entered: str, expected: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(entered.encode("utf-8")).digest(),
        hashlib.sha256(expected.encode("utf-8")).digest(),
    )


def _secret() -> bytes:
    configured = os.environ.get("PPD_SESSION_SECRET")
    if configured is None:
        return _GENERATED_SECRET
    if len(configured.encode()) < 32:
        raise ValueError("PPD_SESSION_SECRET должен содержать не менее 32 байт")
    return configured.encode()


def _signature(payload: str, password: str) -> str:
    version = hmac.digest(_secret(), password.encode(), "sha256")
    return hmac.new(version, payload.encode(), "sha256").hexdigest()


def issue_session(password: str) -> str:
    payload = f"{int(time.time()) + SESSION_TTL}.{secrets.token_hex(16)}"
    return f"{payload}.{_signature(payload, password)}"


def valid_session(token: str | None, password: str) -> bool:
    if not token:
        return False
    try:
        expiry, nonce, signature = token.split(".")
        if int(expiry) <= time.time() or int(expiry) > time.time() + SESSION_TTL:
            return False
        return hmac.compare_digest(signature, _signature(f"{expiry}.{nonce}", password))
    except ValueError:
        return False

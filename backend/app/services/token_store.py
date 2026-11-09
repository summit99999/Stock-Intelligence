"""
Secure token storage using the OS credential manager (keyring).

On Windows this uses Windows Credential Manager.
If keyring is unavailable the module falls back to a fail-safe mode
that refuses to store tokens rather than silently saving them in plaintext.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

SERVICE_NAME = "StockIntelligence_DhanHQ"
SERVICE_NAME_UPSTOX = "StockIntelligence_Upstox"
USERNAME_TOKEN = "access_token"

_MEMORY_TOKEN_CACHE: dict[str, StoredToken] = {}


@dataclass
class StoredToken:
    """Container for a securely stored access token."""

    access_token: str
    dhan_client_id: str = ""
    dhan_client_name: str = ""
    user_id: str = ""
    user_name: str = ""
    expires_at: str = ""         # ISO-8601
    stored_at: str = ""          # ISO-8601

    @property
    def is_expired(self) -> bool:
        """
        Check if token is expired using standardized timezone-aware UTC comparison.

        If expires_at is empty, treats token as valid for 24h from stored_at (or valid if stored_at missing).
        Returns False if expiry is valid and in the future.
        """
        if not self.expires_at:
            if self.stored_at:
                st = parse_expiry_datetime(self.stored_at)
                if st:
                    from datetime import timedelta
                    return datetime.now(timezone.utc) >= (st + timedelta(hours=24))
            return False
        dt = parse_expiry_datetime(self.expires_at)
        if dt is None:
            return True
        return datetime.now(timezone.utc) >= dt

    @property
    def expires_at_local(self) -> str:
        """
        Return expiry timestamp formatted in the system's local timezone.
        """
        dt = parse_expiry_datetime(self.expires_at)
        if dt is None:
            return ""
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def parse_expiry_datetime(expiry: Optional[str]) -> Optional[datetime]:
    """
    Parse an expiry timestamp into a timezone-aware UTC datetime.

    Standardizes internal expiry calculations using timezone-aware UTC datetimes.
    - If a timezone offset or 'Z' is present, converts it to UTC.
    - If no timezone is specified in the timestamp string (naive ISO format like
      '2026-11-02T02:01:25'), it is treated as UTC without making arbitrary timezone guesses.
    - Robustly handles space or 'T' separator, sub-seconds, and common fallback date formats.
    - Returns None if input is empty, None, or unparseable.
    """
    if not expiry or not isinstance(expiry, str):
        return None

    s = expiry.strip()
    if not s:
        return None

    # Replace 'Z' with explicit UTC offset
    s_clean = s.replace("Z", "+00:00")

    try:
        dt = datetime.fromisoformat(s_clean)
        if dt.tzinfo is None:
            # Naive timestamp — no timezone was specified. Attach UTC.
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        pass

    # Fallback to strptime for alternative date formats
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d",
        "%d-%m-%Y",
    ):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    return None


def _keyring_available() -> bool:
    """Return True if keyring can talk to a real credential backend."""
    try:
        import keyring                         # noqa: F811
        from keyring.backends.fail import Keyring as FailKeyring

        backend = keyring.get_keyring()
        if isinstance(backend, FailKeyring):
            return False
        return True
    except Exception:
        return False


def store_token(
    access_token: str,
    dhan_client_id: str = "",
    dhan_client_name: str = "",
    expires_at: str = "",
) -> bool:
    """
    Store the Dhan access token securely.

    Returns True on success, False if keyring is unavailable.
    NEVER falls back to plaintext storage.
    """
    if not _keyring_available():
        logger.error(
            "Keyring backend unavailable — cannot store token securely.  "
            "Token will NOT be persisted."
        )
        return False

    import keyring  # noqa: F811

    payload = json.dumps(
        {
            "access_token": access_token,
            "dhan_client_id": dhan_client_id,
            "dhan_client_name": dhan_client_name,
            "expires_at": expires_at,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    try:
        keyring.set_password(SERVICE_NAME, USERNAME_TOKEN, payload)
        logger.info("Dhan access token stored securely via keyring.")
        return True
    except Exception:
        logger.exception("Failed to store token in keyring.")
        return False


def get_token() -> Optional[StoredToken]:
    """
    Retrieve the stored Dhan access token.

    Returns None if no token is stored or keyring is unavailable.
    """
    if not _keyring_available():
        return None

    import keyring  # noqa: F811

    try:
        raw = keyring.get_password(SERVICE_NAME, USERNAME_TOKEN)
        if not raw:
            return None
        data = json.loads(raw)
        return StoredToken(**data)
    except Exception:
        logger.exception("Failed to read token from keyring.")
        return None


def delete_token() -> bool:
    """Remove the stored token.  Returns True on success."""
    if not _keyring_available():
        return False

    import keyring  # noqa: F811

    try:
        keyring.delete_password(SERVICE_NAME, USERNAME_TOKEN)
        logger.info("Dhan access token removed from keyring.")
        return True
    except keyring.errors.PasswordDeleteError:
        # Nothing stored — that's fine.
        return True
    except Exception:
        logger.exception("Failed to delete token from keyring.")
        return False


def get_backend_info() -> dict:
    """Return non-sensitive info about the keyring backend in use."""
    try:
        import keyring  # noqa: F811

        backend = keyring.get_keyring()
        return {
            "backend": type(backend).__name__,
            "available": _keyring_available(),
        }
    except Exception:
        return {"backend": "unavailable", "available": False}


def store_upstox_token(
    access_token: str,
    user_id: str = "",
    user_name: str = "",
    expires_at: str = "",
) -> bool:
    """Store the Upstox access token securely via Keyring or memory cache."""
    now_dt = datetime.now(timezone.utc)
    if not expires_at:
        from datetime import timedelta
        expires_at = (now_dt + timedelta(hours=24)).isoformat()

    stored_token = StoredToken(
        access_token=access_token,
        user_id=user_id,
        user_name=user_name,
        expires_at=expires_at,
        stored_at=now_dt.isoformat(),
    )
    _MEMORY_TOKEN_CACHE["upstox"] = stored_token

    if not _keyring_available():
        logger.info("Keyring unavailable; stored Upstox token in secure memory cache.")
        return True

    try:
        import keyring  # noqa: F811
        payload = json.dumps({
            "access_token": access_token,
            "user_id": user_id,
            "user_name": user_name,
            "expires_at": expires_at,
            "stored_at": stored_token.stored_at,
        })
        keyring.set_password(SERVICE_NAME_UPSTOX, USERNAME_TOKEN, payload)
        logger.info("Upstox access token stored securely via keyring.")
        return True
    except Exception:
        logger.warning("Could not persist Upstox token to keyring; retaining in secure memory.")
        return True


def get_upstox_token() -> Optional[StoredToken]:
    """Retrieve the stored Upstox access token."""
    # 1. First check in-memory cache
    if "upstox" in _MEMORY_TOKEN_CACHE and not _MEMORY_TOKEN_CACHE["upstox"].is_expired:
        return _MEMORY_TOKEN_CACHE["upstox"]

    # 2. Check keyring
    if _keyring_available():
        try:
            import keyring  # noqa: F811
            raw = keyring.get_password(SERVICE_NAME_UPSTOX, USERNAME_TOKEN)
            if raw:
                data = json.loads(raw)
                token = StoredToken(**data)
                if not token.is_expired:
                    _MEMORY_TOKEN_CACHE["upstox"] = token
                    return token
        except Exception:
            pass

    # 3. Check environment / config fallback
    from app.config import get_upstox_config
    cfg = get_upstox_config()
    if cfg.access_token:
        # Default expiry: 24h from now if not specified
        token = StoredToken(
            access_token=cfg.access_token,
            user_id="UPSTOX_USER",
            user_name="Upstox Trader",
            expires_at="",
            stored_at=datetime.now(timezone.utc).isoformat(),
        )
        _MEMORY_TOKEN_CACHE["upstox"] = token
        return token

    return None


def delete_upstox_token() -> bool:
    """Remove the stored Upstox token."""
    _MEMORY_TOKEN_CACHE.pop("upstox", None)
    if not _keyring_available():
        return True

    try:
        import keyring  # noqa: F811
        keyring.delete_password(SERVICE_NAME_UPSTOX, USERNAME_TOKEN)
        logger.info("Upstox access token removed from keyring.")
        return True
    except Exception:
        return True


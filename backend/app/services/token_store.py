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
USERNAME_TOKEN = "access_token"


@dataclass
class StoredToken:
    """Container for a securely stored access token."""

    access_token: str
    dhan_client_id: str = ""
    dhan_client_name: str = ""
    expires_at: str = ""         # ISO-8601
    stored_at: str = ""          # ISO-8601

    @property
    def is_expired(self) -> bool:
        """
        Check if token is expired using standardized timezone-aware UTC comparison.

        Returns True if expires_at is empty, invalid, or current UTC time >= expiry.
        Returns False if expiry is valid and in the future.
        """
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

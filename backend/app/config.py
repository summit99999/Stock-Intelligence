"""
Application configuration — loaded from environment variables / .env file.

Security: Settings are loaded at startup but NEVER exposed in API responses,
logs, or error messages.  Only boolean 'is_configured' checks are returned.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import dotenv_values, load_dotenv

# Derive absolute path to backend/.env reliably regardless of current working directory
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_PATH = _BACKEND_DIR / ".env"

if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=True)


@dataclass(frozen=True)
class DhanConfig:
    """Dhan API credentials — read-only, never serialised to responses."""

    client_id: str = ""
    api_key: str = ""
    api_secret: str = ""
    api_base_url: str = "https://api.dhan.co"
    auth_base_url: str = "https://auth.dhan.co"
    redirect_url: str = "http://127.0.0.1:8000/api/dhan/oauth/callback"
    live_data_enabled: bool = False

    @property
    def is_configured(self) -> bool:
        """True when the minimum required credentials are present."""
        return bool(self.client_id and self.api_key and self.api_secret)


@dataclass(frozen=True)
class UpstoxConfig:
    """Upstox API credentials — read-only, never serialised to responses."""

    api_key: str = ""           # Upstox App / Client Key
    api_secret: str = ""        # Upstox App Secret
    redirect_uri: str = "http://127.0.0.1:8000/api/upstox/oauth/callback"
    access_token: str = ""      # Direct bearer token or OAuth exchanged token
    api_base_url: str = "https://api.upstox.com/v2"
    live_data_enabled: bool = False
    sandbox_mode: bool = False

    @property
    def is_configured(self) -> bool:
        """True when either an access token or required OAuth credentials are present."""
        return bool(self.access_token or (self.api_key and self.api_secret))


def get_dhan_config() -> DhanConfig:
    """
    Build DhanConfig from environment variables and backend/.env.
    Includes robust fallbacks for file-level reading.
    Never logs or exposes values.
    """
    client_id = os.getenv("DHAN_CLIENT_ID", "").strip()
    api_key = os.getenv("DHAN_API_KEY", "").strip()
    api_secret = os.getenv("DHAN_API_SECRET", "").strip()
    api_base_url = os.getenv("DHAN_API_BASE_URL", "https://api.dhan.co").strip()
    auth_base_url = os.getenv("DHAN_AUTH_BASE_URL", "https://auth.dhan.co").strip()
    redirect_url = os.getenv(
        "DHAN_REDIRECT_URL", "http://127.0.0.1:8000/api/dhan/oauth/callback"
    ).strip()

    raw_live_enabled = os.getenv("DHAN_LIVE_DATA_ENABLED")
    if raw_live_enabled is None and _ENV_PATH.exists():
        try:
            file_values = dotenv_values(_ENV_PATH)
            raw_live_enabled = file_values.get("DHAN_LIVE_DATA_ENABLED")
        except Exception:
            pass

    live_data_enabled = False
    if raw_live_enabled is not None:
        live_data_enabled = str(raw_live_enabled).strip().lower() in ("1", "true", "yes", "on", "t")

    # Fallback: if credentials are empty in environment, directly inspect .env
    if (not client_id or not api_key or not api_secret) and _ENV_PATH.exists():
        try:
            file_values = dotenv_values(_ENV_PATH)
            client_id = client_id or str(file_values.get("DHAN_CLIENT_ID") or "").strip()
            api_key = api_key or str(file_values.get("DHAN_API_KEY") or "").strip()
            api_secret = api_secret or str(file_values.get("DHAN_API_SECRET") or "").strip()
            api_base_url = api_base_url or str(file_values.get("DHAN_API_BASE_URL") or "https://api.dhan.co").strip()
            auth_base_url = auth_base_url or str(file_values.get("DHAN_AUTH_BASE_URL") or "https://auth.dhan.co").strip()
            redirect_url = redirect_url or str(
                file_values.get("DHAN_REDIRECT_URL") or "http://127.0.0.1:8000/api/dhan/oauth/callback"
            ).strip()

            # Secondary fallback: check for positional raw lines if lines lacked '='
            if not client_id or not api_key or not api_secret:
                raw_lines = [
                    l.strip()
                    for l in _ENV_PATH.read_text(encoding="utf-8").splitlines()
                    if l.strip() and not l.strip().startswith("#") and "=" not in l
                ]
                if len(raw_lines) >= 3:
                    client_id = client_id or raw_lines[0]
                    api_key = api_key or raw_lines[1]
                    api_secret = api_secret or raw_lines[2]
        except Exception:
            pass

    return DhanConfig(
        client_id=client_id,
        api_key=api_key,
        api_secret=api_secret,
        api_base_url=api_base_url,
        auth_base_url=auth_base_url,
        redirect_url=redirect_url,
        live_data_enabled=live_data_enabled,
    )


def get_dhan_credential_diagnostics() -> dict[str, bool]:
    """
    Safe credential-presence diagnostic.
    Returns only True/False for each required credential key.
    Never exposes values.
    """
    cfg = get_dhan_config()
    return {
        "DHAN_CLIENT_ID": bool(cfg.client_id),
        "DHAN_API_KEY": bool(cfg.api_key),
        "DHAN_API_SECRET": bool(cfg.api_secret),
    }


def get_upstox_config() -> UpstoxConfig:
    """Build UpstoxConfig from environment variables and backend/.env. Never logs values."""
    api_key = os.getenv("UPSTOX_API_KEY", "").strip()
    api_secret = os.getenv("UPSTOX_API_SECRET", "").strip()
    redirect_uri = os.getenv(
        "UPSTOX_REDIRECT_URI", "http://127.0.0.1:8000/api/upstox/oauth/callback"
    ).strip()
    access_token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    api_base_url = os.getenv("UPSTOX_API_BASE_URL", "https://api.upstox.com/v2").strip()

    raw_live_enabled = os.getenv("UPSTOX_LIVE_DATA_ENABLED")
    if raw_live_enabled is None and _ENV_PATH.exists():
        try:
            file_values = dotenv_values(_ENV_PATH)
            raw_live_enabled = file_values.get("UPSTOX_LIVE_DATA_ENABLED")
        except Exception:
            pass

    live_data_enabled = False
    if raw_live_enabled is not None:
        live_data_enabled = str(raw_live_enabled).strip().lower() in ("1", "true", "yes", "on", "t")

    raw_sandbox = os.getenv("UPSTOX_SANDBOX_MODE")
    sandbox_mode = False
    if raw_sandbox is not None:
        sandbox_mode = str(raw_sandbox).strip().lower() in ("1", "true", "yes", "on", "t")

    if (not access_token or not api_key) and _ENV_PATH.exists():
        try:
            file_values = dotenv_values(_ENV_PATH)
            api_key = api_key or str(file_values.get("UPSTOX_API_KEY") or "").strip()
            api_secret = api_secret or str(file_values.get("UPSTOX_API_SECRET") or "").strip()
            redirect_uri = redirect_uri or str(file_values.get("UPSTOX_REDIRECT_URI") or "").strip()
            access_token = access_token or str(file_values.get("UPSTOX_ACCESS_TOKEN") or "").strip()
            api_base_url = api_base_url or str(file_values.get("UPSTOX_API_BASE_URL") or "https://api.upstox.com/v2").strip()
        except Exception:
            pass

    return UpstoxConfig(
        api_key=api_key,
        api_secret=api_secret,
        redirect_uri=redirect_uri,
        access_token=access_token,
        api_base_url=api_base_url,
        live_data_enabled=live_data_enabled,
        sandbox_mode=sandbox_mode,
    )


def get_upstox_credential_diagnostics() -> dict[str, bool]:
    """Safe credential-presence diagnostic for Upstox."""
    cfg = get_upstox_config()
    return {
        "UPSTOX_API_KEY": bool(cfg.api_key),
        "UPSTOX_API_SECRET": bool(cfg.api_secret),
        "UPSTOX_ACCESS_TOKEN": bool(cfg.access_token),
        "UPSTOX_LIVE_DATA_ENABLED": bool(cfg.live_data_enabled),
    }

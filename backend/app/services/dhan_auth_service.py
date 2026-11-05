"""
Dhan OAuth authentication service.

Implements the 3-step Dhan OAuth flow:
  1. Generate Consent  — POST /app/generate-consent?client_id={client_id}
  2. Browser Login     — user authenticates on Dhan's site
  3. Consume Consent   — POST /app/consumeApp-consent  (exchange tokenId for accessToken)

Security:
  - Credentials are read from DhanConfig (never logged).
  - Access tokens are stored via keyring (Windows Credential Manager).
  - This module never returns raw tokens to callers; it returns metadata only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import httpx

from app.config import DhanConfig

logger = logging.getLogger(__name__)

# Timeout for calls to Dhan's auth server (seconds).
_TIMEOUT = 30.0


@dataclass
class ConsentResult:
    success: bool
    consent_app_id: str = ""
    login_url: str = ""
    error: str = ""


@dataclass
class TokenExchangeResult:
    success: bool
    access_token: str = ""     # only held transiently, stored via keyring
    dhan_client_id: str = ""
    dhan_client_name: str = ""
    expires_at: str = ""
    error: str = ""


@dataclass
class ProfileResult:
    """Safe profile fields returned by Dhan's GET /v2/profile."""
    success: bool
    dhan_client_id: str = ""
    active_segment: str = ""
    data_plan: str = ""
    data_validity: str = ""
    error: str = ""


async def generate_consent(cfg: DhanConfig) -> ConsentResult:
    """
    Step 1 — call Dhan's generate-consent endpoint.

    Follows the individual Dhan API Key OAuth flow:
      POST https://auth.dhan.co/app/generate-consent?client_id={DHAN_CLIENT_ID}
      Headers:
        app_id: {DHAN_API_KEY}
        app_secret: {DHAN_API_SECRET}

    Returns a ConsentResult with the login URL the user must open in a browser.
    """
    if not cfg.is_configured:
        return ConsentResult(
            success=False,
            error="Dhan API credentials are not configured. Set DHAN_CLIENT_ID, DHAN_API_KEY, and DHAN_API_SECRET in backend/.env",
        )

    base = cfg.auth_base_url.rstrip("/")
    url = f"{base}/app/generate-consent"
    headers = {
        "app_id": cfg.api_key,
        "app_secret": cfg.api_secret,
        "Accept": "application/json",
    }
    params = {"client_id": cfg.client_id}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, params=params)

        if resp.status_code != 200:
            err_msg = f"Dhan returned HTTP {resp.status_code}"
            try:
                err_data = resp.json()
                custom_err = err_data.get("message") or err_data.get("remarks") or err_data.get("error")
                if custom_err:
                    err_msg = f"{err_msg}: {custom_err}"
            except Exception:
                pass
            return ConsentResult(success=False, error=err_msg)

        data = resp.json()
        consent_app_id = (
            data.get("consentAppId")
            or data.get("consent_app_id")
            or data.get("consentAppID")
            or ""
        )

        if not consent_app_id:
            err_msg = (
                data.get("message")
                or data.get("remarks")
                or data.get("error")
                or "Dhan returned 200 OK but no consentAppId received"
            )
            return ConsentResult(success=False, error=err_msg)

        safe_consent_id = quote(str(consent_app_id).strip())
        login_url = f"{base}/login/consentApp-login?consentAppId={safe_consent_id}"

        return ConsentResult(
            success=True,
            consent_app_id=str(consent_app_id),
            login_url=login_url,
        )

    except httpx.TimeoutException:
        return ConsentResult(success=False, error="Dhan auth server timed out")
    except httpx.HTTPError as exc:
        logger.error("HTTP error during consent generation: %s", type(exc).__name__)
        return ConsentResult(success=False, error="Network error contacting Dhan")
    except Exception:
        logger.exception("Unexpected error during consent generation")
        return ConsentResult(success=False, error="Unexpected error during consent generation")


async def exchange_token(cfg: DhanConfig, token_id: str) -> TokenExchangeResult:
    """
    Step 3 — call Dhan's consumeApp-consent endpoint.

    Exchanges the tokenId (from browser redirect) for a permanent access token.
    The access token is NOT returned to the frontend; it is stored via keyring.
    """
    if not cfg.is_configured:
        return TokenExchangeResult(
            success=False,
            error="Dhan API credentials are not configured. Set DHAN_CLIENT_ID, DHAN_API_KEY, and DHAN_API_SECRET in backend/.env",
        )

    if not token_id:
        return TokenExchangeResult(success=False, error="tokenId is required")

    base = cfg.auth_base_url.rstrip("/")
    url = f"{base}/app/consumeApp-consent"
    headers = {
        "app_id": cfg.api_key,
        "app_secret": cfg.api_secret,
        "Accept": "application/json",
    }
    params = {"tokenId": token_id}

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, params=params)

        if resp.status_code != 200:
            err_msg = f"Dhan returned HTTP {resp.status_code}"
            try:
                err_data = resp.json()
                custom_err = err_data.get("message") or err_data.get("remarks") or err_data.get("error")
                if custom_err:
                    err_msg = f"{err_msg}: {custom_err}"
            except Exception:
                pass
            return TokenExchangeResult(success=False, error=err_msg)

        data = resp.json()
        access_token = data.get("accessToken") or data.get("access_token") or ""

        if not access_token:
            err_msg = (
                data.get("message")
                or data.get("remarks")
                or data.get("error")
                or "Token exchange failed — no accessToken returned"
            )
            return TokenExchangeResult(success=False, error=err_msg)

        return TokenExchangeResult(
            success=True,
            access_token=access_token,
            dhan_client_id=str(data.get("dhanClientId") or ""),
            dhan_client_name=str(data.get("dhanClientName") or ""),
            expires_at=str(data.get("expiryTime") or ""),
        )

    except httpx.TimeoutException:
        return TokenExchangeResult(success=False, error="Dhan auth server timed out")
    except httpx.HTTPError as exc:
        logger.error("HTTP error during token exchange: %s", type(exc).__name__)
        return TokenExchangeResult(success=False, error="Network error contacting Dhan")
    except Exception:
        logger.exception("Unexpected error during token exchange")
        return TokenExchangeResult(success=False, error="Unexpected error during token exchange")


async def fetch_profile(cfg: DhanConfig, access_token: str) -> ProfileResult:
    """
    Call Dhan profile API: GET https://api.dhan.co/v2/profile.
    Uses access-token header. Returns safe profile fields.
    Never logs or returns access_token.
    """
    if not access_token:
        return ProfileResult(success=False, error="No access token provided")

    base = cfg.api_base_url.rstrip("/")
    url = f"{base}/profile" if base.endswith("/v2") else f"{base}/v2/profile"
    headers = {
        "access-token": access_token,
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code == 200:
            data = resp.json()
            return ProfileResult(
                success=True,
                dhan_client_id=str(data.get("dhanClientId") or data.get("clientId") or ""),
                active_segment=str(data.get("activeSegment") or ""),
                data_plan=str(data.get("dataPlan") or ""),
                data_validity=str(data.get("dataValidity") or ""),
            )
        elif resp.status_code == 401:
            return ProfileResult(success=False, error="Access token is invalid or expired with Dhan")
        else:
            return ProfileResult(success=False, error=f"Dhan profile returned HTTP {resp.status_code}")

    except httpx.TimeoutException:
        return ProfileResult(success=False, error="Dhan profile server timed out")
    except httpx.HTTPError as exc:
        logger.error("HTTP error during profile verification: %s", type(exc).__name__)
        return ProfileResult(success=False, error="Network error contacting Dhan profile API")
    except Exception:
        logger.exception("Unexpected error during profile verification")
        return ProfileResult(success=False, error="Unexpected error during profile verification")

"""Upstox OAuth 2.0 and Token Authentication Service.

Handles:
1. Generation of Upstox authorization dialog URL
2. Exchanging authorization code for an access token (POST /v2/login/authorization/token)
3. Validating and saving direct manual access tokens (GET /v2/user/profile)
4. Non-sensitive status reporting and secure token lifecycle management
"""

from __future__ import annotations

import base64
import datetime
import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import quote
import httpx

from app.config import get_upstox_config
from app.schemas.upstox import UpstoxAuthResponse, UpstoxStatusResponse
from app.services.token_store import (
    delete_upstox_token,
    get_upstox_token,
    store_upstox_token,
)

logger = logging.getLogger(__name__)

UPSTOX_AUTH_DIALOG_URL = "https://api.upstox.com/v2/login/authorization/dialog"
UPSTOX_TOKEN_URL = "https://api.upstox.com/v2/login/authorization/token"
UPSTOX_PROFILE_URL = "https://api.upstox.com/v2/user/profile"
UPSTOX_VALIDATION_URL = "https://api.upstox.com/v2/market-quote/ltp?instrument_key=NSE_INDEX|Nifty 50"
_TIMEOUT = 20.0


def decode_upstox_jwt(token: str) -> dict[str, Any]:
    """Extract non-sensitive claims (user_id, exp) from an Upstox JWT without signature verification."""
    try:
        parts = token.strip().split(".")
        if len(parts) >= 2:
            payload = parts[1]
            rem = len(payload) % 4
            if rem > 0:
                payload += "=" * (4 - rem)
            return json.loads(base64.urlsafe_b64decode(payload.encode("utf-8")).decode("utf-8"))
    except Exception:
        pass
    return {}


class UpstoxAuthService:
    """Service to manage Upstox API credentials, tokens, and OAuth flow."""

    def __init__(self):
        self.cfg = get_upstox_config()

    def get_login_url(self) -> str:
        """Generate the browser login authorization dialog URL."""
        cfg = get_upstox_config()
        if not cfg.api_key:
            return ""
        encoded_redirect = quote(cfg.redirect_uri, safe="")
        return f"{UPSTOX_AUTH_DIALOG_URL}?response_type=code&client_id={cfg.api_key}&redirect_uri={encoded_redirect}"

    async def exchange_code_for_token(self, code: str) -> UpstoxAuthResponse:
        """Exchange the OAuth authorization code for an Upstox access token."""
        cfg = get_upstox_config()
        if not cfg.api_key or not cfg.api_secret:
            return UpstoxAuthResponse(
                success=False,
                message="UPSTOX_API_KEY or UPSTOX_API_SECRET is not configured.",
            )

        payload = {
            "code": code,
            "client_id": cfg.api_key,
            "client_secret": cfg.api_secret,
            "redirect_uri": cfg.redirect_uri,
            "grant_type": "authorization_code",
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                res = await client.post(UPSTOX_TOKEN_URL, data=payload, headers=headers)
                if res.status_code != 200:
                    logger.error("Upstox token exchange failed: HTTP %s - %s", res.status_code, res.text)
                    return UpstoxAuthResponse(
                        success=False,
                        message=f"Upstox token exchange failed: HTTP {res.status_code} ({res.text[:120]})",
                    )

                data = res.json()
                access_token = data.get("access_token", "")
                user_id = data.get("user_id", "")
                user_name = data.get("user_name", "")
                email = data.get("email", "")

                if not access_token:
                    return UpstoxAuthResponse(
                        success=False,
                        message="Response did not contain an access_token.",
                    )

                saved = store_upstox_token(
                    access_token=access_token,
                    user_id=user_id,
                    user_name=user_name,
                )

                return UpstoxAuthResponse(
                    success=True,
                    user_id=user_id,
                    user_name=user_name,
                    email=email,
                    message="Upstox connected successfully.",
                    token_stored_securely=saved,
                )
        except Exception as e:
            logger.exception("Error during Upstox token exchange: %s", e)
            return UpstoxAuthResponse(
                success=False,
                message=f"Network or connection error during Upstox token exchange: {str(e)}",
            )

    async def validate_and_save_direct_token(self, access_token: str, force: bool = False) -> UpstoxAuthResponse:
        """Validate a user-supplied Upstox access token or authorization code and persist it."""
        token = access_token.strip()
        if not token:
            return UpstoxAuthResponse(
                success=False,
                message="Access token cannot be empty.",
            )

        # 1. Check if the user pasted an Authorization Code (?code=...) instead of a JWT Access Token
        is_jwt = ("." in token and len(token.split(".")) == 3)
        cfg = get_upstox_config()

        if not is_jwt:
            # If API key and secret are configured, attempt code exchange
            if cfg.api_key and cfg.api_secret:
                logger.info("Non-JWT token detected; attempting OAuth authorization code exchange...")
                exchange_res = await self.exchange_code_for_token(token)
                if exchange_res.success:
                    return exchange_res
            return UpstoxAuthResponse(
                success=False,
                message=(
                    "The provided string is not a valid Upstox Access Token. Upstox Access Tokens are JSON Web Tokens (JWT) "
                    "with 3 dot-separated parts starting with 'eyJ...'. If you copied an authorization code from the login "
                    "dialog URL (?code=...), configure UPSTOX_API_KEY & UPSTOX_API_SECRET on the server to auto-exchange it."
                ),
            )

        # 2. Extract unverified claims from the JWT (user_id, exp)
        claims = decode_upstox_jwt(token)
        user_id = str(claims.get("user_id") or claims.get("sub") or claims.get("client_id") or "UPSTOX_USER")
        user_name = str(claims.get("user_name") or claims.get("name") or "Upstox Trader")
        exp = claims.get("exp")
        expires_at = ""

        if exp and isinstance(exp, (int, float)):
            exp_dt = datetime.datetime.fromtimestamp(exp, tz=datetime.timezone.utc)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if now_utc >= exp_dt:
                local_exp = exp_dt.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
                return UpstoxAuthResponse(
                    success=False,
                    message=f"This token expired on {local_exp}. Upstox tokens expire daily at 3:30 AM IST. Please generate a fresh token from the Upstox Developer Console.",
                )
            expires_at = exp_dt.isoformat()

        # 3. If force=True, bypass upstream live validation
        if force:
            saved = store_upstox_token(
                access_token=token,
                user_id=user_id,
                user_name=user_name,
                expires_at=expires_at,
            )
            return UpstoxAuthResponse(
                success=True,
                user_id=user_id,
                user_name=user_name,
                expires_at=expires_at,
                message="Upstox token saved successfully (forced mode).",
                token_stored_securely=saved,
            )

        # 4. Live validation against Upstox Market Quote API
        # Note: We validate against Market Quote LTP, NOT User Profile, because User Profile
        # requires a static IP whitelist in Upstox Developer Console, whereas Market Quotes
        # can be queried from any server or client IP.
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                res = await client.get(UPSTOX_VALIDATION_URL, headers=headers)
                if res.status_code == 200:
                    email = ""
                    # Optional: try fetching user profile for full display name (non-blocking if IP whitelist is absent)
                    try:
                        prof_res = await client.get(UPSTOX_PROFILE_URL, headers=headers)
                        if prof_res.status_code == 200:
                            pdata = prof_res.json().get("data", {})
                            user_id = pdata.get("user_id", user_id)
                            user_name = pdata.get("user_name", user_name)
                            email = pdata.get("email", "")
                    except Exception:
                        pass

                    saved = store_upstox_token(
                        access_token=token,
                        user_id=user_id,
                        user_name=user_name,
                        expires_at=expires_at,
                    )
                    return UpstoxAuthResponse(
                        success=True,
                        user_id=user_id,
                        user_name=user_name,
                        email=email,
                        expires_at=expires_at,
                        message="Upstox access token validated and connected successfully!",
                        token_stored_securely=saved,
                    )
                else:
                    err_msg = ""
                    try:
                        err_json = res.json()
                        errors = err_json.get("errors", [])
                        if errors and isinstance(errors, list):
                            err_msg = errors[0].get("message", "")
                        elif "message" in err_json:
                            err_msg = err_json["message"]
                    except Exception:
                        err_msg = res.text[:120]

                    logger.warning("Upstox token validation failed: HTTP %s (%s)", res.status_code, err_msg)
                    return UpstoxAuthResponse(
                        success=False,
                        message=f"Upstox API rejected token (HTTP {res.status_code}): {err_msg or 'Invalid token'}. Please copy a fresh Access Token from the Upstox Developer Console.",
                    )
        except Exception as e:
            logger.exception("Error validating Upstox direct token: %s", e)
            # In offline or sandboxed mode, store the token so the user is ready
            saved = store_upstox_token(
                access_token=token,
                user_id=user_id,
                user_name=user_name,
                expires_at=expires_at,
            )
            return UpstoxAuthResponse(
                success=True,
                user_id=user_id,
                user_name=user_name,
                expires_at=expires_at,
                message="Upstox token saved (offline/deferred verification mode).",
                token_stored_securely=saved,
            )

    def get_status(self) -> UpstoxStatusResponse:
        """Return non-sensitive status of Upstox integration."""
        cfg = get_upstox_config()
        stored = get_upstox_token()

        has_token = bool(stored and stored.access_token)
        is_expired = stored.is_expired if stored else True

        return UpstoxStatusResponse(
            configured=cfg.is_configured or has_token,
            token_available=has_token,
            token_expired=is_expired,
            user_name=stored.user_name if stored else "",
            user_id=stored.user_id if stored else "",
            expires_at=stored.expires_at if stored else "",
            expires_at_local=stored.expires_at_local if stored else "",
            live_data_enabled=cfg.live_data_enabled,
            sandbox_mode=cfg.sandbox_mode,
        )

    def logout(self) -> bool:
        """Disconnect and delete the active Upstox access token."""
        return delete_upstox_token()


_service_instance: Optional[UpstoxAuthService] = None


def get_upstox_auth_service() -> UpstoxAuthService:
    global _service_instance
    if _service_instance is None:
        _service_instance = UpstoxAuthService()
    return _service_instance

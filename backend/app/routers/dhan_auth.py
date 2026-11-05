"""
Dhan OAuth authentication router.

Endpoints
---------
GET   /api/dhan/status          — config & token status (no secrets)
POST  /api/dhan/oauth/consent   — start OAuth: generate consent -> return login URL
GET   /api/dhan/oauth/callback  — browser redirect from Dhan with ?tokenId=...
POST  /api/dhan/oauth/callback  — programmatic callback (JSON body)
POST  /api/dhan/oauth/revoke    — clear the stored token
POST  /api/dhan/verify          — verify token by calling Dhan profile API

Security:
  - No endpoint ever returns credentials, API keys, or access tokens.
  - Tokens are stored/retrieved exclusively via keyring (Windows Credential Manager).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.config import get_dhan_config, get_dhan_credential_diagnostics
from app.schemas.dhan import (
    CallbackRequest,
    CallbackResponse,
    ConsentResponse,
    DhanStatusResponse,
    ProfileResponse,
    RevokeResponse,
)
from app.services import token_store
from app.services.dhan_auth_service import exchange_token, fetch_profile, generate_consent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dhan", tags=["dhan-auth"])


# ---------------------------------------------------------------------------
# GET /api/dhan/status
# ---------------------------------------------------------------------------

@router.get("/status", response_model=DhanStatusResponse)
def dhan_status():
    """
    Report whether Dhan integration is configured and whether a valid
    token is available.  Never returns credentials or the token itself.
    """
    cfg = get_dhan_config()
    stored = token_store.get_token()
    backend_info = token_store.get_backend_info()

    return DhanStatusResponse(
        configured=cfg.is_configured,
        token_available=stored is not None,
        token_expired=stored.is_expired if stored else True,
        dhan_client_name=stored.dhan_client_name if stored else "",
        expires_at=stored.expires_at if stored else "",
        expires_at_local=stored.expires_at_local if stored else "",
        keyring_backend=backend_info.get("backend", ""),
        keyring_available=backend_info.get("available", False),
    )


# ---------------------------------------------------------------------------
# GET /api/dhan/diagnostics
# ---------------------------------------------------------------------------

@router.get("/diagnostics")
def dhan_diagnostics() -> dict[str, bool]:
    """
    Safe credential-presence diagnostic.
    Returns only True/False for each required credential key.
    Never exposes values.
    """
    return get_dhan_credential_diagnostics()


# ---------------------------------------------------------------------------
# POST /api/dhan/oauth/consent
# ---------------------------------------------------------------------------

@router.post("/oauth/consent", response_model=ConsentResponse)
async def oauth_consent():
    """
    Step 1 of Dhan OAuth.

    Calls Dhan's generate-consent endpoint and returns the login URL
    that the user must open in their browser to authenticate.
    """
    cfg = get_dhan_config()

    if not cfg.is_configured:
        return ConsentResponse(
            success=False,
            message="Dhan API credentials are not configured.  "
                    "Set DHAN_CLIENT_ID, DHAN_API_KEY, and DHAN_API_SECRET in backend/.env",
        )

    result = await generate_consent(cfg)

    if not result.success:
        return ConsentResponse(success=False, message=result.error)

    return ConsentResponse(
        success=True,
        login_url=result.login_url,
        consent_app_id=result.consent_app_id,
        message="Open the login_url in your browser to authenticate with Dhan.",
    )


# ---------------------------------------------------------------------------
# GET /api/dhan/oauth/callback  — browser redirect from Dhan
# ---------------------------------------------------------------------------

@router.get("/oauth/callback", response_model=CallbackResponse)
async def oauth_callback_get(tokenId: str = Query(..., description="Token ID from Dhan redirect")):
    """
    Browser-redirect callback.

    After the user authenticates on Dhan's login page, the browser is
    redirected to this URL with ``?tokenId=...`` as a query parameter.
    This endpoint exchanges the tokenId for an access token and stores
    it securely via keyring.

    The access token is NEVER returned to the browser.
    """
    return await _handle_callback(tokenId)


# ---------------------------------------------------------------------------
# POST /api/dhan/oauth/callback — programmatic / frontend JSON body
# ---------------------------------------------------------------------------

@router.post("/oauth/callback", response_model=CallbackResponse)
async def oauth_callback_post(body: CallbackRequest):
    """
    Programmatic callback.

    Used when the frontend captures the tokenId from the redirect URL
    and sends it to the backend as a JSON body.
    """
    return await _handle_callback(body.token_id)


async def _handle_callback(token_id: str) -> CallbackResponse:
    """Shared logic for both GET and POST callback routes."""
    cfg = get_dhan_config()

    if not cfg.is_configured:
        return CallbackResponse(
            success=False,
            message="Dhan API credentials are not configured.",
        )

    result = await exchange_token(cfg, token_id)

    if not result.success:
        return CallbackResponse(success=False, message=result.error)

    # Store the token securely — never in plaintext
    stored = token_store.store_token(
        access_token=result.access_token,
        dhan_client_id=result.dhan_client_id,
        dhan_client_name=result.dhan_client_name,
        expires_at=result.expires_at,
    )

    if not stored:
        return CallbackResponse(
            success=False,
            message="Token received from Dhan but could not be stored securely.  "
                    "Windows Credential Manager (keyring) may be unavailable.",
            token_stored_securely=False,
        )

    return CallbackResponse(
        success=True,
        dhan_client_name=result.dhan_client_name,
        expires_at=result.expires_at,
        message="Dhan authentication successful.  Token stored securely.",
        token_stored_securely=True,
    )


# ---------------------------------------------------------------------------
# POST / GET /api/dhan/verify
# ---------------------------------------------------------------------------

@router.get("/verify", response_model=ProfileResponse)
@router.post("/verify", response_model=ProfileResponse)
async def verify_profile():
    """
    Verify the stored Dhan access token by calling Dhan's profile API.

    Returns safe profile fields only — never the access token or secrets.
    Handles expired, invalid, or missing tokens gracefully.
    """
    cfg = get_dhan_config()
    stored = token_store.get_token()

    if stored is None:
        return ProfileResponse(
            success=False,
            message="No Dhan access token is stored.",
        )

    if stored.is_expired:
        return ProfileResponse(
            success=False,
            token_valid=False,
            dhan_client_id=stored.dhan_client_id,
            message="Stored access token has expired.  Please re-authenticate.",
        )

    result = await fetch_profile(cfg, stored.access_token)

    if not result.success:
        return ProfileResponse(
            success=False,
            token_valid=False,
            message=result.error,
        )

    return ProfileResponse(
        success=True,
        token_valid=True,
        dhan_client_id=result.dhan_client_id,
        active_segment=result.active_segment,
        data_plan=result.data_plan,
        data_validity=result.data_validity,
        message="Dhan profile verified successfully.",
    )


# ---------------------------------------------------------------------------
# POST /api/dhan/oauth/revoke
# ---------------------------------------------------------------------------

@router.post("/oauth/revoke", response_model=RevokeResponse)
def oauth_revoke():
    """Clear the stored Dhan access token from keyring."""
    deleted = token_store.delete_token()

    if deleted:
        return RevokeResponse(success=True, message="Dhan token removed.")

    return RevokeResponse(
        success=False,
        message="Could not remove token — keyring may be unavailable.",
    )

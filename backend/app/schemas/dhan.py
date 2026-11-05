"""Pydantic schemas for Dhan authentication endpoints."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# GET /api/dhan/status
# ---------------------------------------------------------------------------

class DhanStatusResponse(BaseModel):
    """Non-sensitive status of Dhan integration."""

    configured: bool              # True if .env has required credentials
    token_available: bool         # True if a token is stored in keyring
    token_expired: bool           # True if stored token has passed expiry
    dhan_client_name: str = ""    # Stored display name (not a secret)
    expires_at: str = ""          # ISO-8601 expiry timestamp
    expires_at_local: Optional[str] = ""  # Local system timezone display
    keyring_backend: str = ""     # e.g. "WinVaultKeyring"
    keyring_available: bool = False


# ---------------------------------------------------------------------------
# POST /api/dhan/oauth/consent
# ---------------------------------------------------------------------------

class ConsentResponse(BaseModel):
    """Response after generating a Dhan consent request."""

    success: bool
    login_url: str = ""           # URL user must open in browser
    consent_app_id: str = ""
    message: str = ""


# ---------------------------------------------------------------------------
# POST /api/dhan/oauth/callback
# ---------------------------------------------------------------------------

class CallbackRequest(BaseModel):
    """Payload sent by the frontend after Dhan redirects with tokenId."""

    token_id: str


class CallbackResponse(BaseModel):
    """Result of exchanging the tokenId for an access token."""

    success: bool
    dhan_client_name: str = ""
    expires_at: str = ""
    message: str = ""
    token_stored_securely: bool = False


# ---------------------------------------------------------------------------
# POST /api/dhan/oauth/revoke
# ---------------------------------------------------------------------------

class RevokeResponse(BaseModel):
    """Result of clearing the stored token."""

    success: bool
    message: str = ""


# ---------------------------------------------------------------------------
# POST /api/dhan/verify
# ---------------------------------------------------------------------------

class ProfileResponse(BaseModel):
    """Safe subset of fields from Dhan's /v2/profile endpoint."""

    success: bool
    dhan_client_id: str = ""
    token_valid: bool = False
    active_segment: str = ""
    data_plan: str = ""
    data_validity: str = ""
    message: str = ""

"""Pydantic schemas for Upstox authentication and profile endpoints."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class UpstoxStatusResponse(BaseModel):
    """Non-sensitive status of Upstox integration."""

    configured: bool
    token_available: bool
    token_expired: bool
    user_name: str = ""
    user_id: str = ""
    email: str = ""
    broker: str = "UPSTOX"
    expires_at: str = ""
    expires_at_local: Optional[str] = ""
    live_data_enabled: bool = False
    sandbox_mode: bool = False


class UpstoxLoginUrlResponse(BaseModel):
    """Response containing Upstox OAuth login dialog URL."""

    success: bool
    login_url: str = ""
    message: str = ""


class UpstoxCallbackRequest(BaseModel):
    """Payload sent with OAuth authorization code from Upstox redirect."""

    code: str


class UpstoxDirectTokenRequest(BaseModel):
    """Direct manual entry of an Upstox daily access token."""

    access_token: str
    force: bool = False


class UpstoxAuthResponse(BaseModel):
    """Result of setting or exchanging an Upstox access token."""

    success: bool
    user_id: str = ""
    user_name: str = ""
    email: str = ""
    expires_at: str = ""
    message: str = ""
    token_stored_securely: bool = False

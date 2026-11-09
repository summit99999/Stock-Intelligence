"""Upstox API authentication router.

Provides endpoints for:
- Checking Upstox connection and token validity status
- Generating OAuth login dialog URL
- Exchanging authorization code for an access token
- Validating and securely saving direct access tokens
- Disconnecting / removing tokens
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, HTTPException

from app.schemas.upstox import (
    UpstoxAuthResponse,
    UpstoxCallbackRequest,
    UpstoxDirectTokenRequest,
    UpstoxLoginUrlResponse,
    UpstoxStatusResponse,
)
from app.services.upstox_auth_service import get_upstox_auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upstox", tags=["upstox-auth"])


@router.get("/status", response_model=UpstoxStatusResponse)
def get_upstox_status():
    """Return non-sensitive status of Upstox integration."""
    service = get_upstox_auth_service()
    return service.get_status()


@router.get("/oauth/login-url", response_model=UpstoxLoginUrlResponse)
def get_login_url():
    """Generate the browser login authorization dialog URL."""
    service = get_upstox_auth_service()
    url = service.get_login_url()
    if not url:
        return UpstoxLoginUrlResponse(
            success=False,
            message="UPSTOX_API_KEY is not configured.",
        )
    return UpstoxLoginUrlResponse(
        success=True,
        login_url=url,
        message="Open this URL in browser to authenticate with Upstox.",
    )


@router.post("/oauth/callback", response_model=UpstoxAuthResponse)
async def oauth_callback(req: UpstoxCallbackRequest):
    """Exchange authorization code for an access token."""
    service = get_upstox_auth_service()
    res = await service.exchange_code_for_token(req.code)
    if not res.success:
        raise HTTPException(status_code=400, detail=res.message)
    return res


@router.post("/token", response_model=UpstoxAuthResponse)
async def set_direct_token(req: UpstoxDirectTokenRequest):
    """Validate and securely store a manually provided Upstox access token."""
    service = get_upstox_auth_service()
    res = await service.validate_and_save_direct_token(req.access_token, force=req.force)
    if not res.success:
        raise HTTPException(status_code=400, detail=res.message)
    return res


@router.delete("/token")
def delete_token():
    """Disconnect and delete the active Upstox access token."""
    service = get_upstox_auth_service()
    service.logout()
    return {"success": True, "message": "Upstox disconnected successfully."}

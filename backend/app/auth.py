"""
Authentication and Authorization module for Stock Intelligence Pro.
Supports:
1. Asymmetric key verification via Supabase JWKS (RS256 / ES256)
2. Symmetric key verification via SUPABASE_JWT_SECRET (HS256)
3. Strict fail-closed security in production (ENVIRONMENT=production)
4. Offline mock local-operator fallback strictly in development / testing
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

import jwt
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

# Supabase Auth Configuration module-level variables
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "").strip()
SUPABASE_JWKS_URL: str = os.getenv("SUPABASE_JWKS_URL", "").strip()

# Allowed signing algorithms
ALLOWED_ASYMMETRIC_ALGORITHMS: List[str] = ["RS256", "ES256"]
ALLOWED_SYMMETRIC_ALGORITHMS: List[str] = ["HS256"]
ALL_ALLOWED_ALGORITHMS: List[str] = ALLOWED_ASYMMETRIC_ALGORITHMS + ALLOWED_SYMMETRIC_ALGORITHMS

# Local Operator Mock Identity (STRICTLY for development / testing)
LOCAL_MOCK_USER: Dict[str, Any] = {
    "id": "00000000-0000-0000-0000-000000000000",
    "email": "local-operator@stockintelligence.pro",
    "role": "authenticated",
    "is_local": True,
}

_jwks_client: Optional[jwt.PyJWKClient] = None


def get_environment() -> str:
    """Return the normalized environment name."""
    return os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).strip().lower()


def is_production() -> bool:
    """Return True if running in a production or staging cloud environment."""
    return get_environment() in ("production", "prod", "staging")


def get_supabase_url() -> str:
    """Return normalized Supabase project base URL."""
    val = globals().get("SUPABASE_URL", "")
    if val:
        return val.strip().rstrip("/")
    return os.getenv("SUPABASE_URL", "").strip().rstrip("/")


def get_supabase_jwt_secret() -> str:
    """Return configured symmetric JWT secret (if any)."""
    val = globals().get("SUPABASE_JWT_SECRET", "")
    if val:
        return val.strip()
    return os.getenv("SUPABASE_JWT_SECRET", "").strip()


def get_jwks_url() -> str:
    """Return configured or derived JWKS endpoint URL."""
    custom_url = globals().get("SUPABASE_JWKS_URL", "") or os.getenv("SUPABASE_JWKS_URL", "").strip()
    if custom_url:
        return custom_url
    base = get_supabase_url()
    if base:
        return f"{base}/auth/v1/.well-known/jwks.json"
    return ""


def is_auth_configured() -> bool:
    """Check whether any live authentication key/URL source is configured."""
    return bool(get_supabase_jwt_secret() or get_supabase_url() or get_jwks_url())


def is_auth_enabled() -> bool:
    """
    In production: ALWAYS True (fails closed if misconfigured).
    In development: True if Supabase keys/URL are provided.
    """
    if is_production():
        return True
    return is_auth_configured()


def get_auth_mode() -> str:
    """Return active authentication mode name for diagnostics."""
    if not is_auth_enabled():
        return "local_mock"
    if get_supabase_jwt_secret():
        return "supabase_jwt_symmetric"
    if get_jwks_url():
        return "supabase_jwks_asymmetric"
    return "production_unconfigured"


def mask_token(token: str) -> str:
    """Safely mask JWT string for audit logs without leaking token signatures."""
    if not token or len(token) < 12:
        return "***"
    return f"{token[:6]}...{token[-4:]}"


def get_jwks_client() -> Optional[jwt.PyJWKClient]:
    """Retrieve or initialize the cached PyJWKClient instance."""
    global _jwks_client
    jwks_url = get_jwks_url()
    if not jwks_url:
        return None
    if _jwks_client is None:
        try:
            _jwks_client = jwt.PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300)
        except Exception as e:
            logger.warning("Could not initialize JWKS client for %s: %s", jwks_url, str(e))
            return None
    return _jwks_client


def verify_supabase_jwt(token: str) -> Dict[str, Any]:
    """
    Verify and decode a Supabase JWT token.
    Supports asymmetric JWKS (RS256/ES256) and legacy symmetric secrets (HS256).
    Enforces algorithm allowlisting, expiration (exp), audience (aud), and subject (sub).
    Never logs sensitive token bytes or secrets.
    """
    masked = mask_token(token)

    # 1. Parse unverified header to inspect algorithm and key ID
    try:
        header = jwt.get_unverified_header(token)
    except Exception as e:
        logger.warning("Malformed JWT header received for %s: %s", masked, str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed JWT header or token structure",
            headers={"WWW-Authenticate": "Bearer"},
        )

    alg = header.get("alg")
    if not alg or alg.lower() == "none":
        logger.warning("Rejected token with disallowed algorithm 'none' (%s)", masked)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unsecured tokens (alg='none') are strictly forbidden",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if alg not in ALL_ALLOWED_ALGORITHMS:
        logger.warning("Rejected token with non-allowlisted algorithm '%s' (%s)", alg, masked)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token algorithm '{alg}' is not in the server allowlist",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Resolve verification key based on algorithm family
    key: Any = None
    algorithms: List[str] = []

    if alg in ALLOWED_ASYMMETRIC_ALGORITHMS:
        client = get_jwks_client()
        if not client:
            logger.error("Token requires asymmetric verification (%s) but JWKS endpoint is not configured", alg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR if is_production() else status.HTTP_401_UNAUTHORIZED,
                detail="Asymmetric key verification is unconfigured on server",
            )
        try:
            signing_key = client.get_signing_key_from_jwt(token)
            key = signing_key.key
            algorithms = [alg]
        except Exception as e:
            logger.warning("Could not match signing key from JWKS for token %s: %s", masked, str(e))
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to find matching public key for token key ID",
                headers={"WWW-Authenticate": "Bearer"},
            )

    elif alg in ALLOWED_SYMMETRIC_ALGORITHMS:
        secret = get_supabase_jwt_secret()
        if not secret:
            logger.error("Token requires symmetric verification (%s) but SUPABASE_JWT_SECRET is not configured", alg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR if is_production() else status.HTTP_401_UNAUTHORIZED,
                detail="Symmetric signing secret is unconfigured on server",
            )
        key = secret
        algorithms = [alg]

    # 3. Decode and validate claims
    expected_issuer = f"{get_supabase_url()}/auth/v1" if get_supabase_url() else None
    options: Dict[str, Any] = {
        "verify_exp": True,
        "verify_aud": True,
    }
    decode_kwargs: Dict[str, Any] = {
        "algorithms": algorithms,
        "audience": "authenticated",
        "options": options,
    }

    try:
        unverified_claims = jwt.decode(token, options={"verify_signature": False})
    except Exception:
        unverified_claims = {}

    has_iss = "iss" in unverified_claims
    if expected_issuer and (has_iss or is_production()):
        options["verify_iss"] = True
        decode_kwargs["issuer"] = expected_issuer
    else:
        options["verify_iss"] = False

    try:
        payload = jwt.decode(token, key, **decode_kwargs)
        user_id = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role", "authenticated")

        if not user_id or not str(user_id).strip():
            logger.warning("Token %s verified successfully but subject (sub) is missing or empty", masked)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload is missing subject user ID (sub)",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return {
            "id": str(user_id).strip(),
            "email": email,
            "role": role,
            "is_local": False,
        }

    except jwt.ExpiredSignatureError:
        logger.info("Session token %s has expired", masked)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidIssuerError:
        logger.warning("Token %s rejected due to invalid issuer", masked)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token issuer does not match configured Supabase project",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidAudienceError:
        logger.warning("Token %s rejected due to invalid audience", masked)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token audience must be 'authenticated'",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        logger.warning("Token %s rejected due to signature or claim mismatch: %s", masked, str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    FastAPI dependency to retrieve the verified authenticated user.
    - Production: ALWAYS fails closed. Requires valid Bearer JWT. Never returns LOCAL_MOCK_USER.
      If auth is unconfigured in production, raises 500.
    - Development / Configured mode: When auth is configured, requires valid Bearer JWT (raises 401 if missing).
    - Development offline mode: When auth is unconfigured, returns LOCAL_MOCK_USER.
    """
    if is_production():
        # Production must fail closed
        if not is_auth_configured():
            logger.critical("SECURITY ALERT: Production environment active but authentication is unconfigured!")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Production authentication configuration missing or invalid. Refusing anonymous access.",
            )

        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization header with Bearer token is required in production",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = authorization.split(" ", 1)[1].strip()
        return verify_supabase_jwt(token)

    # Development / Test mode
    if not is_auth_configured():
        return LOCAL_MOCK_USER

    # When auth IS configured in development/test, require Bearer token
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header with Bearer token is required when authentication is enabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization.split(" ", 1)[1].strip()
    return verify_supabase_jwt(token)


def get_optional_user(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency for endpoints that can be public or user-personalized.
    In production: Never returns LOCAL_MOCK_USER. Returns verified user or None.
    In development with auth configured: Returns verified user or None.
    In development offline (unconfigured): Returns LOCAL_MOCK_USER.
    """
    if is_production():
        if not authorization or not authorization.startswith("Bearer "):
            return None
        try:
            token = authorization.split(" ", 1)[1].strip()
            return verify_supabase_jwt(token)
        except HTTPException:
            return None

    if not is_auth_configured():
        return LOCAL_MOCK_USER

    if not authorization or not authorization.startswith("Bearer "):
        return None

    try:
        token = authorization.split(" ", 1)[1].strip()
        return verify_supabase_jwt(token)
    except HTTPException:
        return None

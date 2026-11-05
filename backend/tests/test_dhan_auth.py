"""
Tests for Phase 4A — Dhan OAuth authentication.

Tests are designed to run WITHOUT network access and WITHOUT real Dhan
credentials.  They verify:
  - Config loading
  - Token store operations (keyring)
  - Status endpoint shape
  - Consent endpoint with missing config
  - Callback endpoint with missing config
  - Revoke endpoint
  - Auth service logic (mocked HTTP)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx


# ---------------------------------------------------------------------------
# 1. Config tests
# ---------------------------------------------------------------------------

class TestDhanConfig:

    def test_config_loads_from_env(self):
        """Config should read from environment variables."""
        from app.config import DhanConfig

        cfg = DhanConfig(
            client_id="test_id",
            api_key="test_key",
            api_secret="test_secret",
        )
        assert cfg.is_configured is True

    def test_config_not_configured_when_empty(self):
        from app.config import DhanConfig

        cfg = DhanConfig()
        assert cfg.is_configured is False

    def test_config_not_configured_partial(self):
        from app.config import DhanConfig

        cfg = DhanConfig(client_id="id_only")
        assert cfg.is_configured is False

    def test_config_defaults(self):
        from app.config import DhanConfig

        cfg = DhanConfig()
        assert cfg.auth_base_url == "https://auth.dhan.co"
        assert cfg.api_base_url == "https://api.dhan.co"


# ---------------------------------------------------------------------------
# 2. Token store tests
# ---------------------------------------------------------------------------

class TestTokenStore:

    def test_stored_token_expiry_check_expired(self):
        from app.services.token_store import StoredToken

        token = StoredToken(
            access_token="fake",
            expires_at="2020-01-01T00:00:00Z",
        )
        assert token.is_expired is True

    def test_stored_token_expiry_check_future(self):
        from app.services.token_store import StoredToken

        token = StoredToken(
            access_token="fake",
            expires_at="2099-12-31T23:59:59Z",
        )
        assert token.is_expired is False

    def test_stored_token_expiry_naive_future(self):
        """Dhan returns ISO strings without timezone (e.g. 2026-11-02T02:01:25). Must NOT be marked expired."""
        from datetime import datetime, timezone, timedelta
        from app.services.token_store import StoredToken

        # Dynamic future naive timestamp
        future_naive = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
        token = StoredToken(
            access_token="fake",
            expires_at=future_naive,
        )
        assert token.is_expired is False

        # Specific documented format
        token_doc = StoredToken(
            access_token="fake",
            expires_at="2099-11-02T02:01:25",
        )
        assert token_doc.is_expired is False

    def test_stored_token_expiry_naive_past(self):
        """Naive timestamp in the past must be marked expired."""
        from app.services.token_store import StoredToken

        token = StoredToken(
            access_token="fake",
            expires_at="2020-01-01T12:00:00",
        )
        assert token.is_expired is True

    def test_stored_token_expiry_exact_current_time(self):
        """A token expiring at exactly the current time must be treated as expired."""
        from datetime import datetime, timezone
        from app.services.token_store import StoredToken

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        token = StoredToken(
            access_token="fake",
            expires_at=now_str,
        )
        assert token.is_expired is True

    def test_stored_token_utc_timestamps(self):
        """Supports explicit UTC offsets (+00:00 and Z)."""
        from app.services.token_store import StoredToken

        future_z = StoredToken(access_token="fake", expires_at="2099-01-01T00:00:00Z")
        future_offset = StoredToken(access_token="fake", expires_at="2099-01-01T00:00:00+00:00")
        assert future_z.is_expired is False
        assert future_offset.is_expired is False

        past_z = StoredToken(access_token="fake", expires_at="2020-01-01T00:00:00Z")
        past_offset = StoredToken(access_token="fake", expires_at="2020-01-01T00:00:00+00:00")
        assert past_z.is_expired is True
        assert past_offset.is_expired is True

    def test_stored_token_local_timezone_display(self):
        """Test local timezone formatting property."""
        from app.services.token_store import StoredToken

        token = StoredToken(
            access_token="fake",
            expires_at="2099-11-02T02:01:25",
        )
        local_display = token.expires_at_local
        assert isinstance(local_display, str)
        assert len(local_display) > 0
        assert "2099" in local_display

        empty_token = StoredToken(access_token="fake", expires_at="")
        assert empty_token.expires_at_local == ""

    def test_stored_token_no_expiry(self):
        from app.services.token_store import StoredToken

        token = StoredToken(access_token="fake")
        assert token.is_expired is True

    def test_stored_token_invalid_expiry(self):
        from app.services.token_store import StoredToken

        token = StoredToken(access_token="fake", expires_at="not-a-date")
        assert token.is_expired is True

    def test_stored_token_missing_and_whitespace_expiry(self):
        from app.services.token_store import StoredToken

        assert StoredToken(access_token="fake", expires_at="").is_expired is True
        assert StoredToken(access_token="fake", expires_at="   ").is_expired is True

    @patch("app.services.token_store._keyring_available", return_value=True)
    def test_store_and_retrieve_token(self, mock_avail):
        """Mock keyring to test the store/get/delete cycle."""
        from app.services.token_store import (
            delete_token,
            get_token,
            store_token,
        )

        storage: dict[str, str] = {}

        def mock_set(service, user, pw):
            storage[f"{service}:{user}"] = pw

        def mock_get(service, user):
            return storage.get(f"{service}:{user}")

        def mock_del(service, user):
            storage.pop(f"{service}:{user}", None)

        # keyring is imported locally inside each function, so we must
        # patch the top-level 'keyring' module that those local imports resolve.
        mock_kr = MagicMock()
        mock_kr.set_password = mock_set
        mock_kr.get_password = mock_get
        mock_kr.delete_password = mock_del

        with patch.dict("sys.modules", {"keyring": mock_kr}):
            # Store
            ok = store_token(
                access_token="test_token_abc",
                dhan_client_id="C123",
                dhan_client_name="Test User",
                expires_at="2099-12-31T23:59:59Z",
            )
            assert ok is True

            # Retrieve
            stored = get_token()
            assert stored is not None
            assert stored.access_token == "test_token_abc"
            assert stored.dhan_client_id == "C123"
            assert stored.dhan_client_name == "Test User"
            assert stored.is_expired is False

            # Delete
            deleted = delete_token()
            assert deleted is True
            assert get_token() is None

    @patch("app.services.token_store._keyring_available", return_value=False)
    def test_store_fails_without_keyring(self, mock_avail):
        from app.services.token_store import store_token

        ok = store_token(access_token="should_fail")
        assert ok is False

    def test_get_backend_info_returns_dict(self):
        from app.services.token_store import get_backend_info

        info = get_backend_info()
        assert isinstance(info, dict)
        assert "backend" in info
        assert "available" in info


# ---------------------------------------------------------------------------
# 3. Schema tests
# ---------------------------------------------------------------------------

class TestDhanSchemas:

    def test_status_response_shape(self):
        from app.schemas.dhan import DhanStatusResponse

        resp = DhanStatusResponse(
            configured=True,
            token_available=False,
            token_expired=True,
        )
        data = resp.model_dump()
        assert "configured" in data
        assert "token_available" in data
        assert "keyring_backend" in data

    def test_consent_response(self):
        from app.schemas.dhan import ConsentResponse

        resp = ConsentResponse(
            success=True,
            login_url="https://auth.dhan.co/login/consentApp-login?consentAppId=abc",
            consent_app_id="abc",
        )
        assert resp.success is True
        assert "abc" in resp.login_url

    def test_callback_request(self):
        from app.schemas.dhan import CallbackRequest

        req = CallbackRequest(token_id="tok123")
        assert req.token_id == "tok123"


# ---------------------------------------------------------------------------
# 4. Auth service tests (mocked HTTP)
# ---------------------------------------------------------------------------

class TestDhanAuthService:

    @pytest.mark.asyncio
    async def test_generate_consent_success(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import generate_consent

        cfg = DhanConfig(
            client_id="test_id",
            api_key="test_key",
            api_secret="test_secret",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "consentAppId": "consent-123",
            "consentAppStatus": "GENERATED",
            "status": "success",
        }

        with patch("app.services.dhan_auth_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await generate_consent(cfg)

        assert result.success is True
        assert result.consent_app_id == "consent-123"
        assert "consent-123" in result.login_url

    @pytest.mark.asyncio
    async def test_generate_consent_not_configured(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import generate_consent

        cfg = DhanConfig()  # empty = not configured
        result = await generate_consent(cfg)
        assert result.success is False
        assert "not configured" in result.error.lower()

    @pytest.mark.asyncio
    async def test_exchange_token_success(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import exchange_token

        cfg = DhanConfig(
            client_id="test_id",
            api_key="test_key",
            api_secret="test_secret",
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "dhanClientId": "C123",
            "dhanClientName": "Test User",
            "accessToken": "jwt_token_here",
            "expiryTime": "2099-12-31T10:00:00Z",
        }

        with patch("app.services.dhan_auth_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await exchange_token(cfg, "tokenId-abc")

        assert result.success is True
        assert result.access_token == "jwt_token_here"
        assert result.dhan_client_name == "Test User"

    @pytest.mark.asyncio
    async def test_exchange_token_empty_token_id(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import exchange_token

        cfg = DhanConfig(
            client_id="test_id",
            api_key="test_key",
            api_secret="test_secret",
        )
        result = await exchange_token(cfg, "")
        assert result.success is False
        assert "required" in result.error.lower()

    @pytest.mark.asyncio
    async def test_exchange_token_http_error(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import exchange_token

        cfg = DhanConfig(
            client_id="test_id",
            api_key="test_key",
            api_secret="test_secret",
        )

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("app.services.dhan_auth_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await exchange_token(cfg, "bad-token")

        assert result.success is False
        assert "401" in result.error


# ---------------------------------------------------------------------------
# 4b. Profile service tests (mocked HTTP)
# ---------------------------------------------------------------------------

class TestDhanProfileService:

    @pytest.mark.asyncio
    async def test_fetch_profile_success(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import fetch_profile

        cfg = DhanConfig(api_base_url="https://api.dhan.co")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "dhanClientId": "C999",
            "activeSegment": "EQUITY",
            "dataPlan": "STARTER",
            "dataValidity": "2027-01-01",
        }

        with patch("app.services.dhan_auth_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await fetch_profile(cfg, "valid_token")

        assert result.success is True
        assert result.dhan_client_id == "C999"
        assert result.active_segment == "EQUITY"

    @pytest.mark.asyncio
    async def test_fetch_profile_invalid_token_401(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import fetch_profile

        cfg = DhanConfig(api_base_url="https://api.dhan.co")

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("app.services.dhan_auth_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await fetch_profile(cfg, "bad_token")

        assert result.success is False
        assert "invalid or expired" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fetch_profile_no_token(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import fetch_profile

        cfg = DhanConfig(api_base_url="https://api.dhan.co")
        result = await fetch_profile(cfg, "")
        assert result.success is False
        assert "no access token" in result.error.lower()

    @pytest.mark.asyncio
    async def test_fetch_profile_server_error(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import fetch_profile

        cfg = DhanConfig(api_base_url="https://api.dhan.co")

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch("app.services.dhan_auth_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await fetch_profile(cfg, "some_token")

        assert result.success is False
        assert "500" in result.error

    @pytest.mark.asyncio
    async def test_fetch_profile_timeout(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import fetch_profile

        cfg = DhanConfig(api_base_url="https://api.dhan.co")

        with patch("app.services.dhan_auth_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.side_effect = httpx.TimeoutException("timed out")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await fetch_profile(cfg, "some_token")

        assert result.success is False
        assert "timed out" in result.error.lower()


# ---------------------------------------------------------------------------
# 5. Router / FastAPI integration tests (TestClient)
# ---------------------------------------------------------------------------

class TestDhanAuthRouter:
    """Test the FastAPI endpoints via TestClient (no real HTTP to Dhan)."""

    @pytest.fixture(autouse=True)
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app

        self._client = TestClient(app)
        yield

    def test_status_endpoint_returns_200(self):
        resp = self._client.get("/api/dhan/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "configured" in data
        assert "token_available" in data
        assert "token_expired" in data
        assert "keyring_backend" in data
        assert "keyring_available" in data

    @patch("app.routers.dhan_auth.token_store.get_token")
    def test_status_endpoint_with_future_naive_token(self, mock_get_token):
        """Regression test for bug: naive future ISO timestamp (e.g. 2026-11-02T02:01:25) must report token_expired=False."""
        from app.services.token_store import StoredToken

        mock_get_token.return_value = StoredToken(
            access_token="secure_mock_token",
            dhan_client_id="C999",
            dhan_client_name="Sumit  Barik",
            expires_at="2099-11-02T02:01:25",
        )

        resp = self._client.get("/api/dhan/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["token_available"] is True
        assert data["token_expired"] is False
        assert data["expires_at"] == "2099-11-02T02:01:25"
        assert data["dhan_client_name"] == "Sumit  Barik"
        assert "2099" in data["expires_at_local"]

    @patch("app.routers.dhan_auth.token_store.get_token")
    def test_status_endpoint_with_expired_token(self, mock_get_token):
        """Expired token must report token_expired=True."""
        from app.services.token_store import StoredToken

        mock_get_token.return_value = StoredToken(
            access_token="secure_mock_token",
            dhan_client_id="C999",
            dhan_client_name="Sumit  Barik",
            expires_at="2020-01-01T00:00:00",
        )

        resp = self._client.get("/api/dhan/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["token_available"] is True
        assert data["token_expired"] is True

    def test_status_never_contains_secrets(self):
        """Ensure no credential-like fields leak."""
        resp = self._client.get("/api/dhan/status")
        data = resp.json()
        text = json.dumps(data).lower()
        for secret_key in ("api_key", "api_secret", "access_token", "app_secret"):
            assert secret_key not in text

    @patch("app.routers.dhan_auth.get_dhan_config")
    def test_consent_fails_without_config(self, mock_cfg):
        from app.config import DhanConfig

        mock_cfg.return_value = DhanConfig()  # empty
        resp = self._client.post("/api/dhan/oauth/consent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not configured" in data["message"].lower()

    @patch("app.routers.dhan_auth.get_dhan_config")
    def test_callback_fails_without_config(self, mock_cfg):
        from app.config import DhanConfig

        mock_cfg.return_value = DhanConfig()  # empty
        resp = self._client.post(
            "/api/dhan/oauth/callback",
            json={"token_id": "test"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False

    def test_revoke_endpoint(self):
        resp = self._client.post("/api/dhan/oauth/revoke")
        assert resp.status_code == 200
        data = resp.json()
        assert "success" in data
        assert "message" in data

    def test_health_still_works(self):
        """Verify existing endpoint is not broken."""
        resp = self._client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_root_version_updated(self):
        resp = self._client.get("/")
        assert resp.status_code == 200
        assert resp.json()["version"] == "0.3.0"

    # --- GET callback tests ---

    @patch("app.routers.dhan_auth.get_dhan_config")
    def test_get_callback_fails_without_config(self, mock_cfg):
        from app.config import DhanConfig

        mock_cfg.return_value = DhanConfig()  # empty
        resp = self._client.get("/api/dhan/oauth/callback?tokenId=test123")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "not configured" in data["message"].lower()

    def test_get_callback_missing_tokenId_returns_422(self):
        """GET callback without tokenId query param should return 422."""
        resp = self._client.get("/api/dhan/oauth/callback")
        assert resp.status_code == 422

    @patch("app.routers.dhan_auth.token_store")
    @patch("app.routers.dhan_auth.exchange_token")
    @patch("app.routers.dhan_auth.get_dhan_config")
    def test_get_callback_stores_token(self, mock_cfg, mock_exchange, mock_ts):
        """GET callback with valid tokenId should exchange and store token."""
        from app.config import DhanConfig
        from app.services.dhan_auth_service import TokenExchangeResult

        mock_cfg.return_value = DhanConfig(
            client_id="id", api_key="key", api_secret="secret",
        )
        mock_exchange.return_value = TokenExchangeResult(
            success=True,
            access_token="jwt_abc",
            dhan_client_id="C100",
            dhan_client_name="Test",
            expires_at="2099-12-31T00:00:00Z",
        )
        mock_ts.store_token.return_value = True

        resp = self._client.get("/api/dhan/oauth/callback?tokenId=tok-browser")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["token_stored_securely"] is True
        # Verify exchange was called with the correct tokenId
        mock_exchange.assert_called_once()
        # Verify token was stored
        mock_ts.store_token.assert_called_once()
        # Verify response does NOT contain the actual token
        text = json.dumps(data).lower()
        assert "jwt_abc" not in text

    # --- Verify / profile tests ---

    def test_verify_no_token_stored(self):
        """Verify should fail gracefully when no token is stored."""
        with patch("app.routers.dhan_auth.token_store") as mock_ts:
            mock_ts.get_token.return_value = None
            resp = self._client.post("/api/dhan/verify")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "no" in data["message"].lower() and "token" in data["message"].lower()

    def test_verify_expired_token(self):
        """Verify should report expired token without calling Dhan API."""
        from app.services.token_store import StoredToken

        expired = StoredToken(
            access_token="old_jwt",
            dhan_client_id="C200",
            expires_at="2020-01-01T00:00:00Z",
        )
        with patch("app.routers.dhan_auth.token_store") as mock_ts:
            mock_ts.get_token.return_value = expired
            resp = self._client.post("/api/dhan/verify")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert data["token_valid"] is False
        assert "expired" in data["message"].lower()

    @patch("app.routers.dhan_auth.fetch_profile")
    def test_verify_valid_token_success(self, mock_fetch):
        from app.services.token_store import StoredToken
        from app.services.dhan_auth_service import ProfileResult

        valid_token = StoredToken(
            access_token="good_jwt",
            dhan_client_id="C300",
            expires_at="2099-12-31T23:59:59Z",
        )
        mock_fetch.return_value = ProfileResult(
            success=True,
            dhan_client_id="C300",
            active_segment="EQUITY",
            data_plan="PREMIUM",
            data_validity="2027-06-01",
        )
        with patch("app.routers.dhan_auth.token_store") as mock_ts:
            mock_ts.get_token.return_value = valid_token
            resp = self._client.post("/api/dhan/verify")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["token_valid"] is True
        assert data["dhan_client_id"] == "C300"
        assert data["active_segment"] == "EQUITY"
        assert data["data_plan"] == "PREMIUM"
        # Verify response does NOT contain the access token
        text = json.dumps(data).lower()
        assert "good_jwt" not in text

    @patch("app.routers.dhan_auth.fetch_profile")
    def test_verify_dhan_api_returns_401(self, mock_fetch):
        """Verify should handle Dhan returning 401 for a non-expired token."""
        from app.services.token_store import StoredToken
        from app.services.dhan_auth_service import ProfileResult

        token = StoredToken(
            access_token="revoked_jwt",
            expires_at="2099-12-31T23:59:59Z",
        )
        mock_fetch.return_value = ProfileResult(
            success=False,
            error="Access token is invalid or expired",
        )
        with patch("app.routers.dhan_auth.token_store") as mock_ts:
            mock_ts.get_token.return_value = token
            resp = self._client.post("/api/dhan/verify")

        data = resp.json()
        assert data["success"] is False
        assert data["token_valid"] is False

    # --- Security: verify response never leaks secrets ---

    def test_verify_response_never_contains_secrets(self):
        """No matter what, the verify endpoint must not leak tokens."""
        with patch("app.routers.dhan_auth.token_store") as mock_ts:
            mock_ts.get_token.return_value = None
            resp = self._client.post("/api/dhan/verify")

        text = json.dumps(resp.json()).lower()
        for secret_key in ("access_token", "api_key", "api_secret", "app_secret"):
            assert secret_key not in text

    def test_profile_response_schema(self):
        from app.schemas.dhan import ProfileResponse

        resp = ProfileResponse(
            success=True,
            token_valid=True,
            dhan_client_id="C100",
            active_segment="EQUITY",
            data_plan="STARTER",
            data_validity="2027-01-01",
        )
        data = resp.model_dump()
        assert "token_valid" in data
        assert "active_segment" in data
        assert "data_plan" in data

    def test_diagnostics_endpoint_returns_presence(self):
        resp = self._client.get("/api/dhan/diagnostics")
        assert resp.status_code == 200
        data = resp.json()
        assert "DHAN_CLIENT_ID" in data
        assert "DHAN_API_KEY" in data
        assert "DHAN_API_SECRET" in data
        assert isinstance(data["DHAN_CLIENT_ID"], bool)
        assert isinstance(data["DHAN_API_KEY"], bool)
        assert isinstance(data["DHAN_API_SECRET"], bool)


# ---------------------------------------------------------------------------
# 6. OAuth Fix & Edge Case Tests
# ---------------------------------------------------------------------------

class TestDhanOAuthFixes:

    def test_env_path_derivation_is_absolute(self):
        from app.config import _ENV_PATH
        assert _ENV_PATH.is_absolute()
        assert _ENV_PATH.name == ".env"

    def test_credential_diagnostics_structure(self):
        from app.config import get_dhan_credential_diagnostics
        diag = get_dhan_credential_diagnostics()
        assert set(diag.keys()) == {"DHAN_CLIENT_ID", "DHAN_API_KEY", "DHAN_API_SECRET"}
        for v in diag.values():
            assert isinstance(v, bool)

    @pytest.mark.asyncio
    async def test_generate_consent_dhan_401_handled(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import generate_consent

        cfg = DhanConfig(client_id="12345", api_key="key", api_secret="sec")
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"message": "Invalid API Key or Secret"}

        with patch("app.services.dhan_auth_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await generate_consent(cfg)

        assert result.success is False
        assert "401" in result.error
        assert "Invalid API Key" in result.error

    @pytest.mark.asyncio
    async def test_generate_consent_dhan_429_handled(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import generate_consent

        cfg = DhanConfig(client_id="12345", api_key="key", api_secret="sec")
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {"message": "Too Many Requests"}

        with patch("app.services.dhan_auth_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await generate_consent(cfg)

        assert result.success is False
        assert "429" in result.error

    @pytest.mark.asyncio
    async def test_generate_consent_invalid_payload_handled(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import generate_consent

        cfg = DhanConfig(client_id="12345", api_key="key", api_secret="sec")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "failure", "message": "Consent error"}

        with patch("app.services.dhan_auth_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await generate_consent(cfg)

        assert result.success is False
        assert "Consent error" in result.error

    @pytest.mark.asyncio
    async def test_generate_consent_success_generates_url_encoded_login(self):
        from app.config import DhanConfig
        from app.services.dhan_auth_service import generate_consent

        cfg = DhanConfig(client_id="12345", api_key="key", api_secret="sec")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "consentAppId": "app-id 123/xyz"}

        with patch("app.services.dhan_auth_service.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await generate_consent(cfg)

        assert result.success is True
        assert result.consent_app_id == "app-id 123/xyz"
        assert "consentAppId=app-id%20123/xyz" in result.login_url or "app-id%20123%2Fxyz" in result.login_url


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

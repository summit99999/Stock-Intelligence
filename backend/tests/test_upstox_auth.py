"""
Unit and integration tests for Upstox OAuth 2.0 and Token Authentication.

Designed to execute completely offline without network access:
- Config loading and diagnostics
- Token store operations (memory cache & secure keyring fallback)
- UpstoxAuthService OAuth URL generation, status reporting, and logout
- Router endpoints verification
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import UpstoxConfig, get_upstox_credential_diagnostics
from app.schemas.upstox import (
    UpstoxCallbackRequest,
    UpstoxDirectTokenRequest,
)
from app.services.token_store import (
    delete_upstox_token,
    get_upstox_token,
    store_upstox_token,
)
from app.services.upstox_auth_service import UpstoxAuthService
from app.routers.upstox_auth import (
    delete_token,
    get_login_url,
    get_upstox_status,
)


def run_coro(coro):
    """Synchronously advance a coroutine without starting a socket-based event loop."""
    try:
        coro.send(None)
    except StopIteration as e:
        return e.value
    raise RuntimeError("Coroutine did not complete synchronously")


class TestUpstoxConfig:
    """Verifies configuration loading, defaults, and diagnostics."""

    def test_config_defaults(self):
        cfg = UpstoxConfig()
        assert cfg.api_base_url == "https://api.upstox.com/v2"
        assert cfg.redirect_uri == "http://127.0.0.1:8000/api/upstox/oauth/callback"
        assert cfg.live_data_enabled is False
        assert cfg.sandbox_mode is False
        assert cfg.is_configured is False

    def test_config_configured(self):
        cfg = UpstoxConfig(
            api_key="mock_api_key",
            api_secret="mock_api_secret",
        )
        assert cfg.is_configured is True

    def test_credential_diagnostics(self):
        with patch.dict("os.environ", {"UPSTOX_API_KEY": "key1", "UPSTOX_API_SECRET": "sec1"}):
            diag = get_upstox_credential_diagnostics()
            assert diag["UPSTOX_API_KEY"] is True
            assert diag["UPSTOX_API_SECRET"] is True


class TestUpstoxTokenStore:
    """Verifies token storage, retrieval, and deletion lifecycle."""

    def setup_method(self):
        with patch("app.services.token_store._keyring_available", return_value=False):
            delete_upstox_token()

    def teardown_method(self):
        with patch("app.services.token_store._keyring_available", return_value=False):
            delete_upstox_token()

    def test_store_and_retrieve_token(self):
        with patch("app.services.token_store._keyring_available", return_value=False):
            saved = store_upstox_token(
                access_token="test_jwt_access_token_12345",
                user_id="U1001",
                user_name="John Doe",
            )
            assert saved is True

            token_obj = get_upstox_token()
            assert token_obj is not None
            assert token_obj.access_token == "test_jwt_access_token_12345"
            assert token_obj.user_id == "U1001"
            assert token_obj.user_name == "John Doe"
            assert token_obj.is_expired is False

    def test_delete_token(self):
        with patch("app.services.token_store._keyring_available", return_value=False):
            store_upstox_token("token_to_delete")
            assert get_upstox_token() is not None

            deleted = delete_upstox_token()
            assert deleted is True
            assert get_upstox_token() is None


class TestUpstoxAuthService:
    """Verifies Upstox OAuth URL generation, token validation, and status."""

    def setup_method(self):
        with patch("app.services.token_store._keyring_available", return_value=False):
            delete_upstox_token()

    def teardown_method(self):
        with patch("app.services.token_store._keyring_available", return_value=False):
            delete_upstox_token()

    def test_get_login_url(self):
        service = UpstoxAuthService()
        with patch("app.services.upstox_auth_service.get_upstox_config") as mock_cfg:
            mock_cfg.return_value = UpstoxConfig(
                api_key="my_client_id",
                api_secret="my_secret",
                redirect_uri="https://myapp.com/callback",
            )
            url = service.get_login_url()
            assert "client_id=my_client_id" in url
            assert "redirect_uri=https%3A%2F%2Fmyapp.com%2Fcallback" in url
            assert "response_type=code" in url

    def test_validate_and_save_direct_token_empty(self):
        service = UpstoxAuthService()
        res = run_coro(service.validate_and_save_direct_token(""))
        assert res.success is False
        assert "cannot be empty" in res.message.lower()

    def test_validate_and_save_direct_token_non_jwt(self):
        service = UpstoxAuthService()
        res = run_coro(service.validate_and_save_direct_token("some_short_code_12345"))
        assert res.success is False
        assert "not a valid" in res.message.lower()

    def test_validate_and_save_direct_token_forced_jwt(self):
        import base64, json
        h = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
        p = base64.urlsafe_b64encode(json.dumps({"user_id": "U444", "user_name": "Pro Trader"}).encode()).decode().rstrip("=")
        mock_jwt = f"{h}.{p}.signature"

        service = UpstoxAuthService()
        with patch("app.services.token_store._keyring_available", return_value=False):
            res = run_coro(service.validate_and_save_direct_token(mock_jwt, force=True))
            assert res.success is True
            assert res.user_id == "U444"
            assert res.user_name == "Pro Trader"

            stored = get_upstox_token()
            assert stored is not None
            assert stored.access_token == mock_jwt

    def test_status_reporting(self):
        service = UpstoxAuthService()
        with patch("app.services.token_store._keyring_available", return_value=False):
            status = service.get_status()
            assert status.token_available is False

            store_upstox_token("tok_abc", user_id="U88", user_name="Trader")
            status_after = service.get_status()
            assert status_after.token_available is True
            assert status_after.user_id == "U88"


class TestUpstoxAuthRouter:
    """Verifies router endpoints direct responses."""

    def setup_method(self):
        with patch("app.services.token_store._keyring_available", return_value=False):
            delete_upstox_token()

    def teardown_method(self):
        with patch("app.services.token_store._keyring_available", return_value=False):
            delete_upstox_token()

    def test_status_endpoint(self):
        with patch("app.services.token_store._keyring_available", return_value=False):
            status = get_upstox_status()
            assert status.token_available is False
            assert status.token_expired is True

            store_upstox_token("token_123", user_id="U99", user_name="Trader")
            status_after = get_upstox_status()
            assert status_after.token_available is True
            assert status_after.user_id == "U99"

    def test_login_url_endpoint(self):
        with patch("app.services.upstox_auth_service.get_upstox_config") as mock_cfg:
            mock_cfg.return_value = UpstoxConfig(api_key="client_xyz")
            res = get_login_url()
            assert res.success is True
            assert "client_id=client_xyz" in res.login_url

    def test_delete_token_endpoint(self):
        with patch("app.services.token_store._keyring_available", return_value=False):
            store_upstox_token("token_to_del")
            res = delete_token()
            assert res["success"] is True
            assert get_upstox_token() is None

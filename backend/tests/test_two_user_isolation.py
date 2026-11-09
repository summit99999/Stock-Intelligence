"""
Two-User Isolation and IDOR Prevention Test Suite (Phase 13.1 Security Audit).

Verifies strict multi-tenant isolation across all user-owned entities:
1. Research Trade Plans
2. Qualitative Research Notes
3. Custom Watchlists & Watchlist Items
4. Market Alerts & Alert History
5. Custom Scanner Definitions
6. Screener Presets
7. Rejection of unauthenticated access to user-scoped routes in cloud mode.
"""

from __future__ import annotations

import time
from typing import Generator
import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app

SUPABASE_URL = "https://security-audit.supabase.co"
AUTH_SECRET = "super-secret-test-key-32-chars-long-minimum!"


def create_token(user_id: str, email: str) -> str:
    """Generate a signed Supabase JWT for testing."""
    payload = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "aud": "authenticated",
        "iss": f"{SUPABASE_URL}/auth/v1",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    return jwt.encode(payload, AUTH_SECRET, algorithm="HS256")


USER_A_ID = "00000000-0000-0000-0000-aaaaaaaaaaaa"
USER_B_ID = "11111111-1111-1111-1111-bbbbbbbbbbbb"

HEADERS_A: dict[str, str] = {}
HEADERS_B: dict[str, str] = {}


@pytest.fixture(autouse=True)
def configure_test_auth(monkeypatch):
    """Enable cloud authentication mode for all tests in this module."""
    global HEADERS_A, HEADERS_B

    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setenv("SUPABASE_JWT_SECRET", AUTH_SECRET)
    monkeypatch.setattr("app.auth.SUPABASE_URL", SUPABASE_URL)
    monkeypatch.setattr("app.auth.SUPABASE_JWT_SECRET", AUTH_SECRET)
    HEADERS_A = {
        "Authorization": f"Bearer {create_token(USER_A_ID, 'alice@example.com')}"
    }
    HEADERS_B = {
        "Authorization": f"Bearer {create_token(USER_B_ID, 'bob@example.com')}"
    }


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. Research Trade Plans Isolation
# ---------------------------------------------------------------------------

def test_trade_plans_two_user_isolation(client: TestClient):
    """Verify User B cannot view, modify, or delete User A's trade plan."""
    # Alice creates a trade plan
    plan_payload = {
        "symbol": "INFY",
        "exchange": "NSE",
        "setup_type": "ORDER_BLOCK_RETEST",
        "direction": "LONG",
        "timeframe": "1D",
        "ideal_entry": 1850.0,
        "entry_min": 1840.0,
        "entry_max": 1855.0,
        "stop_loss": 1810.0,
        "target_1": 1920.0,
        "target_2": 1980.0,
        "risk_reward_ratio": 2.33,
        "position_size": 50,
        "risk_amount": 2000.0,
        "capital_allocated": 92500.0,
        "invalidation_condition": "Close below 1810",
        "notes": "Alice's proprietary trade plan",
    }
    res_a = client.post("/api/research/trade-plans/save", json=plan_payload, headers=HEADERS_A)
    assert res_a.status_code == 200
    plan_id = res_a.json()["id"]

    # Alice can read it
    res_get_a = client.get(f"/api/research/trade-plans/{plan_id}", headers=HEADERS_A)
    assert res_get_a.status_code == 200
    assert res_get_a.json()["symbol"] == "INFY"

    # Bob tries to read it -> 404 Not Found
    res_get_b = client.get(f"/api/research/trade-plans/{plan_id}", headers=HEADERS_B)
    assert res_get_b.status_code == 404

    # Bob tries to update it -> 404 Not Found
    res_put_b = client.put(
        f"/api/research/trade-plans/{plan_id}",
        json={"notes": "Bob was here"},
        headers=HEADERS_B,
    )
    assert res_put_b.status_code == 404

    # Verify Alice's notes were NOT altered
    res_check = client.get(f"/api/research/trade-plans/{plan_id}", headers=HEADERS_A)
    assert res_check.json()["notes"] == "Alice's proprietary trade plan"

    # Bob tries to delete it -> 404 Not Found
    res_del_b = client.delete(f"/api/research/trade-plans/{plan_id}", headers=HEADERS_B)
    assert res_del_b.status_code == 404

    # Alice's plan still exists
    res_still_there = client.get(f"/api/research/trade-plans/{plan_id}", headers=HEADERS_A)
    assert res_still_there.status_code == 200

    # Alice deletes her own plan -> 200
    res_del_a = client.delete(f"/api/research/trade-plans/{plan_id}", headers=HEADERS_A)
    assert res_del_a.status_code == 200


# ---------------------------------------------------------------------------
# 2. Qualitative Research Notes Isolation
# ---------------------------------------------------------------------------

def test_research_notes_two_user_isolation(client: TestClient):
    """Verify User B cannot see or delete User A's qualitative research notes."""
    note_payload = {
        "symbol": "TCS",
        "title": "Alice Private Analysis",
        "note": "Expect strong margin expansion next quarter.",
        "tags": "fundamental,margins",
    }
    res_a = client.post("/api/research/notes", json=note_payload, headers=HEADERS_A)
    assert res_a.status_code == 200
    note_id = res_a.json()["id"]

    # Bob lists notes for TCS -> should NOT contain Alice's note
    res_list_b = client.get("/api/research/notes/TCS", headers=HEADERS_B)
    assert res_list_b.status_code == 200
    bob_notes = res_list_b.json()
    assert all(n["id"] != note_id for n in bob_notes)

    # Alice lists notes for TCS -> finds her note
    res_list_a = client.get("/api/research/notes/TCS", headers=HEADERS_A)
    assert res_list_a.status_code == 200
    alice_notes = res_list_a.json()
    assert any(n["id"] == note_id for n in alice_notes)

    # Bob tries to delete Alice's note -> 404
    res_del_b = client.delete(f"/api/research/notes/{note_id}", headers=HEADERS_B)
    assert res_del_b.status_code == 404

    # Alice can delete her own note -> 200
    res_del_a = client.delete(f"/api/research/notes/{note_id}", headers=HEADERS_A)
    assert res_del_a.status_code == 200


# ---------------------------------------------------------------------------
# 3. Custom Watchlists Isolation
# ---------------------------------------------------------------------------

def test_custom_watchlists_two_user_isolation(client: TestClient):
    """Verify User B cannot view, modify, or delete User A's custom watchlists."""
    wl_payload = {
        "name": "Alice Secret Breakouts",
        "description": "High probability setups",
        "symbols": ["RELIANCE", "HDFCBANK"],
    }
    res_a = client.post("/api/watchlists", json=wl_payload, headers=HEADERS_A)
    assert res_a.status_code == 200
    wl_id = res_a.json()["id"]

    # Alice lists watchlists -> sees it
    res_list_a = client.get("/api/watchlists", headers=HEADERS_A)
    assert any(w["id"] == wl_id for w in res_list_a.json())

    # Bob lists watchlists -> does NOT see it
    res_list_b = client.get("/api/watchlists", headers=HEADERS_B)
    assert all(w["id"] != wl_id for w in res_list_b.json())

    # Bob tries to read detail -> 404
    res_get_b = client.get(f"/api/watchlists/{wl_id}", headers=HEADERS_B)
    assert res_get_b.status_code == 404

    # Bob tries to add a symbol -> 404
    res_add_b = client.post(f"/api/watchlists/{wl_id}/symbols", json={"symbol": "WIPRO"}, headers=HEADERS_B)
    assert res_add_b.status_code == 404

    # Bob tries to update it -> 404
    res_put_b = client.put(f"/api/watchlists/{wl_id}", json={"name": "Hacked", "symbols": []}, headers=HEADERS_B)
    assert res_put_b.status_code == 404

    # Bob tries to delete it -> 404
    res_del_b = client.delete(f"/api/watchlists/{wl_id}", headers=HEADERS_B)
    assert res_del_b.status_code == 404

    # Alice adds a symbol successfully -> 200
    res_add_a = client.post(f"/api/watchlists/{wl_id}/symbols", json={"symbol": "INFY"}, headers=HEADERS_A)
    assert res_add_a.status_code == 200

    # Alice deletes her watchlist -> 200
    res_del_a = client.delete(f"/api/watchlists/{wl_id}", headers=HEADERS_A)
    assert res_del_a.status_code == 200


# ---------------------------------------------------------------------------
# 4. Market Alerts Isolation
# ---------------------------------------------------------------------------

def test_market_alerts_two_user_isolation(client: TestClient):
    """Verify User B cannot view, modify, or delete User A's alerts."""
    alert_payload = {
        "symbol": "SBIN",
        "alert_type": "PRICE_ABOVE",
        "target_value": 850.0,
        "timeframe": "1D",
        "note": "Alice's breakout alert",
    }
    res_a = client.post("/api/alerts", json=alert_payload, headers=HEADERS_A)
    assert res_a.status_code == 200
    alert_id = res_a.json()["id"]

    # Bob lists alerts -> does NOT contain Alice's alert
    res_list_b = client.get("/api/alerts", headers=HEADERS_B)
    assert all(a["id"] != alert_id for a in res_list_b.json())

    # Bob tries to update -> 404
    res_put_b = client.put(
        f"/api/alerts/{alert_id}",
        json={"target_value": 999.0, "status": "MUTED"},
        headers=HEADERS_B,
    )
    assert res_put_b.status_code == 404

    # Bob tries to delete -> 404
    res_del_b = client.delete(f"/api/alerts/{alert_id}", headers=HEADERS_B)
    assert res_del_b.status_code == 404

    # Alice deletes her alert -> 200
    res_del_a = client.delete(f"/api/alerts/{alert_id}", headers=HEADERS_A)
    assert res_del_a.status_code == 200


# ---------------------------------------------------------------------------
# 5. Saved Custom Scanners & Screener Presets Isolation
# ---------------------------------------------------------------------------

def test_custom_scanners_and_presets_isolation(client: TestClient):
    """Verify User B cannot view or delete User A's custom scanners or presets."""
    # Alice creates a custom scanner
    scanner_payload = {
        "name": "Alice Scanner",
        "description": "Custom RSI Scan",
        "universe": "nifty_50",
        "timeframe": "1D",
        "logic_mode": "AND",
        "conditions": {"rsi": 30},
    }
    res_sc_a = client.post("/api/scanner/custom/save", json=scanner_payload, headers=HEADERS_A)
    assert res_sc_a.status_code == 200
    scanner_id = res_sc_a.json()["id"]

    # Bob lists custom scanners -> does NOT see Alice's scanner
    res_sc_list_b = client.get("/api/scanner/custom/saved", headers=HEADERS_B)
    assert all(s["id"] != scanner_id for s in res_sc_list_b.json())

    # Bob tries to delete Alice's scanner -> 404
    res_del_sc_b = client.delete(f"/api/scanner/custom/{scanner_id}", headers=HEADERS_B)
    assert res_del_sc_b.status_code == 404

    # Alice deletes it -> 200
    res_del_sc_a = client.delete(f"/api/scanner/custom/{scanner_id}", headers=HEADERS_A)
    assert res_del_sc_a.status_code == 200

    # Alice creates a screener preset
    preset_payload = {
        "name": "Alice Screener Preset",
        "description": "Low PE scan",
        "config": {
            "filters": [{"field": "pe", "operator": "LESS_THAN", "value": 15}],
            "universe": "NIFTY500",
        },
    }
    res_pre_a = client.post("/api/screener/presets", json=preset_payload, headers=HEADERS_A)
    assert res_pre_a.status_code == 200
    preset_id = res_pre_a.json()["id"]

    # Bob tries to read preset -> 404
    res_get_pre_b = client.get(f"/api/screener/presets/{preset_id}", headers=HEADERS_B)
    assert res_get_pre_b.status_code == 404

    # Bob tries to delete preset -> 404
    res_del_pre_b = client.delete(f"/api/screener/presets/{preset_id}", headers=HEADERS_B)
    assert res_del_pre_b.status_code == 404

    # Alice deletes preset -> 200
    res_del_pre_a = client.delete(f"/api/screener/presets/{preset_id}", headers=HEADERS_A)
    assert res_del_pre_a.status_code == 200


# ---------------------------------------------------------------------------
# 6. Unauthenticated Access Rejection in Cloud Mode
# ---------------------------------------------------------------------------

def test_unauthenticated_requests_fail_in_cloud_mode(client: TestClient):
    """Verify user-scoped endpoints reject unauthenticated requests with 401 when auth is configured."""
    # Test across multiple protected user endpoints without Authorization header
    endpoints = [
        ("GET", "/api/watchlists"),
        ("POST", "/api/watchlists"),
        ("GET", "/api/alerts"),
        ("POST", "/api/alerts"),
        ("GET", "/api/scanner/custom/saved"),
        ("POST", "/api/scanner/custom/save"),
        ("GET", "/api/screener/presets"),
        ("POST", "/api/screener/presets"),
        ("GET", "/api/research/trade-plans"),
        ("POST", "/api/research/trade-plans/save"),
        ("POST", "/api/research/notes"),
        ("GET", "/api/dhan/diagnostics"),
        ("POST", "/api/dhan/oauth/consent"),
        ("POST", "/api/dhan/oauth/revoke"),
    ]

    for method, endpoint in endpoints:
        if method == "GET":
            res = client.get(endpoint)
        elif method == "POST":
            res = client.post(endpoint, json={})
        assert res.status_code == 401, f"Expected 401 for unauthenticated {method} {endpoint}, got {res.status_code}"

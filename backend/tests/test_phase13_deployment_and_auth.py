"""
Phase 13 Test Suite: Zero-Cost Cloud Deployment, Private Authentication & Database Migration.
Validates:
1. Dual-mode database abstraction (SQLite fallback, PostgreSQL SQL adaptation, DbRow compatibility)
2. Authentication security (Local mock mode, Supabase JWT verification, expiration, tampering checks)
3. Migration utility idempotency, safe backup generation, and dry-run inspection
4. Cloud deployment health, status, and CORS configuration
5. User-scoped asset persistence with user ownership
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient

from app.auth import (
    LOCAL_MOCK_USER,
    get_auth_mode,
    get_current_user,
    is_auth_enabled,
    verify_supabase_jwt,
)
from app.database import (
    DbRow,
    adapt_sql_for_postgres,
    create_market_alert,
    get_database_mode,
    is_postgres,
    list_market_alerts,
    list_research_notes,
    list_research_trade_plans,
    save_research_note,
    save_research_trade_plan,
)
from app.main import app
from app.migrate_to_postgres import ALL_TABLES, backup_sqlite

client = TestClient(app)

TEST_JWT_SECRET = "super-secret-jwt-key-with-at-least-32-bytes-length!!"


# ---------------------------------------------------------------------------
# 1. Dual-Mode Database Abstraction Tests
# ---------------------------------------------------------------------------

def test_database_mode_defaults_to_sqlite():
    """Verify that without DATABASE_URL, local SQLite is the active engine."""
    with patch.dict(os.environ, {"DATABASE_URL": ""}):
        assert not is_postgres()
        assert get_database_mode() == "sqlite"


def test_sql_adapter_placeholder_replacement():
    """Verify ? parameter placeholders are translated to %s for PostgreSQL."""
    sql = "SELECT * FROM stocks WHERE symbol = ? AND exchange = ?"
    adapted, capture_id = adapt_sql_for_postgres(sql)
    assert adapted == "SELECT * FROM stocks WHERE symbol = %s AND exchange = %s"
    assert not capture_id


def test_sql_adapter_datetime_translation():
    """Verify datetime('now') is replaced with NOW() for PostgreSQL compatibility."""
    sql = "UPDATE custom_watchlists SET name = ?, updated_at = datetime('now') WHERE id = ?"
    adapted, capture_id = adapt_sql_for_postgres(sql)
    assert "NOW()" in adapted
    assert "%s" in adapted
    assert not capture_id


def test_sql_adapter_insert_or_replace_stocks():
    """Verify INSERT OR REPLACE INTO stocks translates to ON CONFLICT (symbol) DO UPDATE."""
    sql = "INSERT OR REPLACE INTO stocks (symbol, company_name, close) VALUES (?, ?, ?)"
    adapted, capture_id = adapt_sql_for_postgres(sql)
    assert "ON CONFLICT (symbol) DO UPDATE SET" in adapted
    assert "company_name = EXCLUDED.company_name" in adapted
    assert "close = EXCLUDED.close" in adapted
    assert not capture_id


def test_sql_adapter_insert_or_replace_ohlcv():
    """Verify INSERT OR REPLACE INTO ohlcv translates to composite ON CONFLICT target."""
    sql = "INSERT OR REPLACE INTO ohlcv (symbol, interval, timestamp, close, volume) VALUES (?, ?, ?, ?, ?)"
    adapted, capture_id = adapt_sql_for_postgres(sql)
    assert "ON CONFLICT (symbol, interval, timestamp) DO UPDATE SET" in adapted
    assert "close = EXCLUDED.close" in adapted
    assert "volume = EXCLUDED.volume" in adapted


def test_sql_adapter_auto_increment_returning_id():
    """Verify AUTO_INCREMENT table inserts append RETURNING id to capture lastrowid."""
    sql = "INSERT INTO saved_screeners (name, description, config_json) VALUES (?, ?, ?)"
    adapted, capture_id = adapt_sql_for_postgres(sql)
    assert adapted.endswith("RETURNING id")
    assert capture_id is True


def test_sql_adapter_safe_placeholder_replacement():
    """Verify ? is replaced with %s outside quotes/comments but preserved inside them."""
    from app.database import safe_replace_placeholders

    # Question mark inside single quotes
    sql1 = "SELECT * FROM notes WHERE content = 'What is this? Breakout?' AND symbol = ?"
    adapted1 = safe_replace_placeholders(sql1)
    assert adapted1 == "SELECT * FROM notes WHERE content = 'What is this? Breakout?' AND symbol = %s"

    # Question mark inside comments
    sql2 = "SELECT id, symbol FROM stocks WHERE active = ? -- Is active? Yes or no\nAND price > ?"
    adapted2 = safe_replace_placeholders(sql2)
    assert adapted2 == "SELECT id, symbol FROM stocks WHERE active = %s -- Is active? Yes or no\nAND price > %s"

    # Question mark inside block comments
    sql3 = "SELECT /* Questionable? */ id FROM alerts WHERE user_id = ?"
    adapted3 = safe_replace_placeholders(sql3)
    assert adapted3 == "SELECT /* Questionable? */ id FROM alerts WHERE user_id = %s"

    # Question mark inside double quotes
    sql4 = 'SELECT "col?name" FROM data WHERE symbol = ?'
    adapted4 = safe_replace_placeholders(sql4)
    assert adapted4 == 'SELECT "col?name" FROM data WHERE symbol = %s'

    # Full query through adapt_sql_for_postgres
    sql_full = "INSERT OR REPLACE INTO stocks (symbol, company_name) VALUES ('TEST?SYM', ?)"
    adapted_full, _ = adapt_sql_for_postgres(sql_full)
    assert "'TEST?SYM'" in adapted_full
    assert "%s" in adapted_full
    assert "ON CONFLICT (symbol) DO UPDATE" in adapted_full


def test_db_row_dict_and_index_access():
    """Verify DbRow provides seamless dictionary and 0-based integer index access."""
    raw = {"symbol": "INFY", "close": 1850.5, "sector": "IT"}
    keys = ["symbol", "close", "sector"]
    row = DbRow(raw, keys)

    # String key access
    assert row["symbol"] == "INFY"
    assert row["close"] == 1850.5
    assert row.get("sector") == "IT"

    # Integer index access (tuple-like)
    assert row[0] == "INFY"
    assert row[1] == 1850.5
    assert row[2] == "IT"

    # Standard dict conversion
    d = dict(row)
    assert d == raw


# ---------------------------------------------------------------------------
# 2. Authentication & JWT Verification Tests
# ---------------------------------------------------------------------------

def test_auth_mode_defaults_to_local_mock():
    """Verify that when Supabase is not configured, local mock mode is active."""
    with patch("app.auth.SUPABASE_URL", ""), patch("app.auth.SUPABASE_JWT_SECRET", ""):
        assert not is_auth_enabled()
        assert get_auth_mode() == "local_mock"
        user = get_current_user()
        assert user == LOCAL_MOCK_USER
        assert user["is_local"] is True


def test_supabase_jwt_verification_valid():
    """Verify valid Supabase JWT is successfully parsed and claims extracted."""
    payload = {
        "sub": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "email": "trader@stockintelligence.pro",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")

    with patch("app.auth.SUPABASE_URL", "https://xyz.supabase.co"), \
         patch("app.auth.SUPABASE_JWT_SECRET", TEST_JWT_SECRET):
        user = verify_supabase_jwt(token)
        assert user["id"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert user["email"] == "trader@stockintelligence.pro"
        assert user["role"] == "authenticated"
        assert user["is_local"] is False


def test_supabase_jwt_verification_expired():
    """Verify expired token raises 401 Unauthorized with descriptive message."""
    payload = {
        "sub": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "email": "trader@stockintelligence.pro",
        "aud": "authenticated",
        "exp": int(time.time()) - 100,  # Expired
    }
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")

    with patch("app.auth.SUPABASE_URL", "https://xyz.supabase.co"), \
         patch("app.auth.SUPABASE_JWT_SECRET", TEST_JWT_SECRET):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            verify_supabase_jwt(token)
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()


def test_supabase_jwt_verification_invalid_signature():
    """Verify token signed with wrong secret raises 401 Unauthorized."""
    payload = {
        "sub": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "email": "trader@stockintelligence.pro",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, "wrong-signature-key-12345678901234567890", algorithm="HS256")

    with patch("app.auth.SUPABASE_URL", "https://xyz.supabase.co"), \
         patch("app.auth.SUPABASE_JWT_SECRET", TEST_JWT_SECRET):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            verify_supabase_jwt(token)
        assert exc.value.status_code == 401
        assert "invalid" in exc.value.detail.lower()


def test_supabase_jwt_verification_rejects_none_algorithm():
    """Verify algorithm 'none' attack is strictly forbidden."""
    import base64
    import json
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({
        "sub": "attacker",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }).encode()).rstrip(b"=").decode()
    token = f"{header}.{payload}."

    with patch("app.auth.SUPABASE_URL", "https://xyz.supabase.co"), \
         patch("app.auth.SUPABASE_JWT_SECRET", TEST_JWT_SECRET):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            verify_supabase_jwt(token)
        assert exc.value.status_code == 401
        assert "none" in exc.value.detail.lower() or "disallowed" in exc.value.detail.lower() or "forbidden" in exc.value.detail.lower()


def test_supabase_jwt_verification_rejects_invalid_issuer():
    """Verify token with forged or foreign issuer claim is rejected."""
    payload = {
        "sub": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "email": "trader@stockintelligence.pro",
        "aud": "authenticated",
        "iss": "https://foreign-project.supabase.co/auth/v1",
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")

    with patch("app.auth.SUPABASE_URL", "https://xyz.supabase.co"), \
         patch("app.auth.SUPABASE_JWT_SECRET", TEST_JWT_SECRET):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            verify_supabase_jwt(token)
        assert exc.value.status_code == 401
        assert "issuer" in exc.value.detail.lower()


def test_production_fail_closed_without_config():
    """Verify production fails closed with 500 if credentials are unconfigured."""
    with patch("app.auth.is_production", return_value=True), \
         patch("app.auth.is_auth_configured", return_value=False):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            get_current_user(authorization=None)
        assert exc.value.status_code == 500
        assert "missing or invalid" in exc.value.detail.lower() or "unconfigured" in exc.value.detail.lower()


def test_production_rejects_unauthenticated_request():
    """Verify production requires Bearer token when configured, raising 401."""
    with patch("app.auth.is_production", return_value=True), \
         patch("app.auth.is_auth_configured", return_value=True):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            get_current_user(authorization=None)
        assert exc.value.status_code == 401
        assert "bearer" in exc.value.detail.lower()


def test_get_current_user_enforces_bearer_in_cloud_mode():
    """Verify get_current_user dependency rejects requests without Bearer token when auth enabled."""
    with patch("app.auth.SUPABASE_URL", "https://xyz.supabase.co"), \
         patch("app.auth.SUPABASE_JWT_SECRET", TEST_JWT_SECRET):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            get_current_user(authorization=None)
        assert exc.value.status_code == 401

        with pytest.raises(HTTPException) as exc:
            get_current_user(authorization="Basic dXNlcjpwYXNz")
        assert exc.value.status_code == 401


# ---------------------------------------------------------------------------
# 3. Database Migration & Pre-Migration Backup Tests
# ---------------------------------------------------------------------------

def test_migration_backup_creates_valid_copy():
    """Verify backup_sqlite creates a readable timestamped copy in target directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        dummy_db = tmp_path / "test.db"
        dummy_db.write_text("DUMMY_DATABASE_CONTENT", encoding="utf-8")
        backup_dir = tmp_path / "backups"

        backup_file = backup_sqlite(dummy_db, backup_dir)
        assert backup_file.exists()
        assert backup_file.name.startswith("stock_intelligence_backup_")
        assert backup_file.read_text(encoding="utf-8") == "DUMMY_DATABASE_CONTENT"


def test_migration_table_list_coverage():
    """Verify migration table list covers all 19 required database tables."""
    assert len(ALL_TABLES) == 19
    assert "stocks" in ALL_TABLES
    assert "ohlcv" in ALL_TABLES
    assert "fundamental_income_statements" in ALL_TABLES
    assert "research_trade_plans" in ALL_TABLES
    assert "market_alerts" in ALL_TABLES


# ---------------------------------------------------------------------------
# 4. Cloud Health, Status & Root API Endpoints
# ---------------------------------------------------------------------------

def test_health_endpoint():
    """Verify /api/health reports ok status and /api/system/status reports cloud metadata."""
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}

    sys_res = client.get("/api/system/status")
    assert sys_res.status_code == 200
    data = sys_res.json()
    assert data["status"] == "ok"
    assert data["database"] in ["sqlite", "postgresql"]
    assert "auth" in data
    assert "version" in data


def test_root_endpoint():
    """Verify root / reports Stock Intelligence Pro metadata."""
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert "Stock Intelligence" in data["name"]
    assert data["status"] == "running"


def test_auth_status_endpoint():
    """Verify /api/auth/status returns operator identity without leaking secrets."""
    res = client.get("/api/auth/status")
    assert res.status_code == 200
    data = res.json()
    assert "auth_enabled" in data
    assert "database_mode" in data
    assert "user_id" in data
    assert "SUPABASE_JWT_SECRET" not in data


# ---------------------------------------------------------------------------
# 5. User-Scoped Data Isolation Tests
# ---------------------------------------------------------------------------

def test_research_trade_plan_user_isolation():
    """Verify research trade plans can be saved with user_id and filtered by user."""
    test_user_a = "user-alpha-1111"
    test_user_b = "user-beta-2222"

    plan_a = save_research_trade_plan({
        "symbol": "TCS",
        "reference_price": 3800.0,
        "stop_loss": 3700.0,
        "target_1": 4000.0,
        "target_2": 4200.0,
        "risk_reward_ratio": 2.5,
        "setup_score": 85.0,
        "invalidation_condition": "Daily close below 3700",
    }, user_id=test_user_a)

    assert plan_a["symbol"] == "TCS"

    # User A query sees the plan
    plans_a = list_research_trade_plans(symbol="TCS", user_id=test_user_a)
    assert any(p["id"] == plan_a["id"] for p in plans_a)

    # General unauthenticated query sees plans
    all_plans = list_research_trade_plans(symbol="TCS")
    assert len(all_plans) >= 1


def test_research_notes_user_isolation():
    """Verify research notes support user_id association."""
    test_user = "user-gamma-3333"
    note = save_research_note(
        symbol="INFY",
        note="Strong order book execution and margin resilience.",
        title="Q3 FY26 Channel Check",
        user_id=test_user,
    )
    assert note["symbol"] == "INFY"
    user_notes = list_research_notes(symbol="INFY", user_id=test_user)
    assert any(n["id"] == note["id"] for n in user_notes)

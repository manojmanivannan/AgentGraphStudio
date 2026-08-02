"""Tests for the auth foundation: register, login, logout, /auth/me, sessions,
CSRF, and the authed cookie-jar fixture. See issue #35."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

ORIGIN = {"Origin": "http://test"}
EVIL_ORIGIN = {"Origin": "http://evil.com"}
COOKIE_NAME = "agentbuilder_session"


def _aware(dt):
    """sqlite drops tzinfo on read; normalize for tz-aware comparisons."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _email() -> str:
    return f"user_{uuid.uuid4().hex[:12]}@example.com"


def _set_cookie_header(resp) -> str | None:
    headers = resp.headers.get_list("set-cookie")
    return headers[0] if headers else None


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------


class TestRegister:
    async def test_register_success(self, test_client, fresh_db):
        creds = {"email": "Alice@Example.com", "password": "super-secret-123"}
        resp = await test_client.post("/api/auth/register", json=creds, headers=ORIGIN)
        assert resp.status_code == 201, resp.text
        data = resp.json()["user"]
        assert data["id"] is not None
        # Email is normalized to lowercase.
        assert data["email"] == "alice@example.com"
        assert data["created_at"] is not None
        # Register does NOT log the user in (no session cookie).
        assert _set_cookie_header(resp) is None

    async def test_register_duplicate_email_rejected(self, test_client, fresh_db):
        creds = {"email": "dup@example.com", "password": "super-secret-123"}
        resp = await test_client.post("/api/auth/register", json=creds, headers=ORIGIN)
        assert resp.status_code == 201
        resp = await test_client.post("/api/auth/register", json=creds, headers=ORIGIN)
        assert resp.status_code == 409

    async def test_register_normalizes_email_for_dup_check(self, test_client, fresh_db):
        # Uppercase variant of an already-registered email is the same user.
        await test_client.post(
            "/api/auth/register",
            json={"email": "mixed@Example.com", "password": "super-secret-123"},
            headers=ORIGIN,
        )
        resp = await test_client.post(
            "/api/auth/register",
            json={"email": "MIXED@example.com", "password": "super-secret-123"},
            headers=ORIGIN,
        )
        assert resp.status_code == 409

    async def test_register_short_password_rejected(self, test_client, fresh_db):
        resp = await test_client.post(
            "/api/auth/register",
            json={"email": _email(), "password": "short"},
            headers=ORIGIN,
        )
        assert resp.status_code == 400

    async def test_register_long_password_rejected(self, test_client, fresh_db):
        resp = await test_client.post(
            "/api/auth/register",
            json={"email": _email(), "password": "x" * 1025},
            headers=ORIGIN,
        )
        assert resp.status_code == 400

    async def test_register_invalid_email_rejected(self, test_client, fresh_db):
        resp = await test_client.post(
            "/api/auth/register",
            json={"email": "not-an-email", "password": "super-secret-123"},
            headers=ORIGIN,
        )
        assert resp.status_code == 400

    async def test_register_requires_origin(self, test_client, fresh_db):
        resp = await test_client.post(
            "/api/auth/register",
            json={"email": _email(), "password": "super-secret-123"},
        )
        assert resp.status_code == 403

    async def test_register_blocks_cross_origin(self, test_client, fresh_db):
        resp = await test_client.post(
            "/api/auth/register",
            json={"email": _email(), "password": "super-secret-123"},
            headers=EVIL_ORIGIN,
        )
        assert resp.status_code == 403


# --------------------------------------------------------------------------
# Login
# --------------------------------------------------------------------------


class TestLogin:
    async def test_login_success_sets_cookie(self, test_client, fresh_db):
        creds = {"email": "alice@example.com", "password": "super-secret-123"}
        await test_client.post("/api/auth/register", json=creds, headers=ORIGIN)
        resp = await test_client.post("/api/auth/login", json=creds, headers=ORIGIN)
        assert resp.status_code == 200, resp.text
        assert resp.json()["user"]["email"] == "alice@example.com"

        cookie = _set_cookie_header(resp)
        assert cookie is not None
        assert COOKIE_NAME in cookie
        assert "Path=/" in cookie
        assert "HttpOnly" in cookie
        assert "samesite=lax" in cookie.lower()
        # Over plain http the Secure flag must NOT be set.
        assert "secure" not in cookie.lower()

    async def test_login_wrong_password(self, test_client, fresh_db):
        creds = {"email": "alice@example.com", "password": "super-secret-123"}
        await test_client.post("/api/auth/register", json=creds, headers=ORIGIN)
        resp = await test_client.post(
            "/api/auth/login",
            json={"email": "alice@example.com", "password": "wrong-password"},
            headers=ORIGIN,
        )
        assert resp.status_code == 401
        assert _set_cookie_header(resp) is None

    async def test_login_unknown_email(self, test_client, fresh_db):
        resp = await test_client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "whatever-12345"},
            headers=ORIGIN,
        )
        assert resp.status_code == 401

    async def test_login_normalizes_email(self, test_client, fresh_db):
        await test_client.post(
            "/api/auth/register",
            json={"email": "Alice@Example.com", "password": "super-secret-123"},
            headers=ORIGIN,
        )
        # Login with different case resolves the same user.
        resp = await test_client.post(
            "/api/auth/login",
            json={"email": "ALICE@example.com", "password": "super-secret-123"},
            headers=ORIGIN,
        )
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == "alice@example.com"

    async def test_login_requires_origin(self, test_client, fresh_db):
        creds = {"email": "alice@example.com", "password": "super-secret-123"}
        await test_client.post("/api/auth/register", json=creds, headers=ORIGIN)
        resp = await test_client.post("/api/auth/login", json=creds)
        assert resp.status_code == 403

    async def test_login_blocks_cross_origin(self, test_client, fresh_db):
        creds = {"email": "alice@example.com", "password": "super-secret-123"}
        await test_client.post("/api/auth/register", json=creds, headers=ORIGIN)
        resp = await test_client.post("/api/auth/login", json=creds, headers=EVIL_ORIGIN)
        assert resp.status_code == 403


# --------------------------------------------------------------------------
# /auth/me
# --------------------------------------------------------------------------


class TestMe:
    async def test_me_unauthenticated(self, test_client, fresh_db):
        resp = await test_client.get("/api/auth/me")
        assert resp.status_code == 401

    async def test_me_authenticated(self, authed_client):
        resp = await authed_client.get("/api/auth/me")
        assert resp.status_code == 200, resp.text
        assert resp.json()["email"] == authed_client.auth_email


# --------------------------------------------------------------------------
# Logout
# --------------------------------------------------------------------------


class TestLogout:
    async def test_logout_destroys_session_and_clears_cookie(self, authed_client):
        # Authenticated before logout.
        assert (await authed_client.get("/api/auth/me")).status_code == 200

        resp = await authed_client.post("/api/auth/logout", headers=ORIGIN)
        assert resp.status_code == 200
        cookie = _set_cookie_header(resp)
        assert cookie is not None  # Set-Cookie clears the cookie
        assert COOKIE_NAME in cookie
        # The client jar drops the cookie after a clearing Set-Cookie.
        assert authed_client.cookies.get(COOKIE_NAME) in (None, "")

        # After logout, /me is unauthenticated.
        assert (await authed_client.get("/api/auth/me")).status_code == 401

    async def test_logout_requires_origin(self, authed_client):
        resp = await authed_client.post("/api/auth/logout")
        assert resp.status_code == 403

    async def test_logout_without_cookie_is_noop(self, test_client, fresh_db):
        resp = await test_client.post("/api/auth/logout", headers=ORIGIN)
        assert resp.status_code == 200


# --------------------------------------------------------------------------
# Session expiry & sliding window
# --------------------------------------------------------------------------


async def _load_session(db_session, sid):
    from canvas_server.models.auth import Session

    return await db_session.get(Session, sid)


class TestSessionExpiry:
    async def test_idle_expiry_rejects_and_deletes_session(
        self, authed_client, test_session
    ):
        sid = authed_client.cookies.get(COOKIE_NAME)
        assert sid is not None

        sess = await _load_session(test_session, sid)
        sess.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await test_session.commit()

        resp = await authed_client.get("/api/auth/me")
        assert resp.status_code == 401

        # Expired session row is destroyed.
        test_session.expunge_all()
        assert await _load_session(test_session, sid) is None

    async def test_absolute_expiry_rejects_session(
        self, authed_client, test_session
    ):
        sid = authed_client.cookies.get(COOKIE_NAME)
        sess = await _load_session(test_session, sid)
        # Idle still valid, but absolute cap exceeded.
        sess.absolute_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await test_session.commit()

        resp = await authed_client.get("/api/auth/me")
        assert resp.status_code == 401

    async def test_sliding_window_extends_idle_deadline(
        self, authed_client, test_session
    ):
        sid = authed_client.cookies.get(COOKIE_NAME)
        sess = await _load_session(test_session, sid)
        original_expires = sess.expires_at
        # Shrink the idle deadline to "about to expire" — still valid right now.
        sess.expires_at = datetime.now(UTC) + timedelta(seconds=3)
        await test_session.commit()

        resp = await authed_client.get("/api/auth/me")
        assert resp.status_code == 200

        # Sliding extension should have pushed expires_at far into the future
        # (the 30-min idle window), well past the 3-second deadline we set and
        # past the original login-time deadline.
        test_session.expunge_all()
        sess = await _load_session(test_session, sid)
        assert _aware(sess.expires_at) > datetime.now(UTC) + timedelta(minutes=1)
        assert _aware(sess.expires_at) > _aware(original_expires)


# --------------------------------------------------------------------------
# Authed fixture
# --------------------------------------------------------------------------


class TestAuthedFixture:
    async def test_fixture_can_hit_protected_route(self, authed_client):
        resp = await authed_client.get("/api/auth/me")
        assert resp.status_code == 200
        assert resp.json()["email"] == authed_client.auth_email

    async def test_canvas_route_requires_auth(self, test_client, fresh_db):
        # Canvas routes now require auth (issue #36); unauthed -> 401.
        resp = await test_client.post("/api/canvases", json={"name": "C1"})
        assert resp.status_code == 401


# --------------------------------------------------------------------------
# CSRF allowlist is separate from CORS
# --------------------------------------------------------------------------


class TestCSRFAllowlist:
    async def test_cors_origin_does_not_grant_csrf_trust(
        self, test_client, fresh_db, monkeypatch
    ):
        # Add a third-party origin to the CORS list (a common staging/preview
        # setup). It must NOT be trusted for CSRF — state-changing routes still
        # block it.
        from canvas_server.config import settings

        monkeypatch.setattr(
            settings, "cors_origins", ["http://evil.com", "http://localhost:5173"]
        )
        resp = await test_client.post(
            "/api/auth/register",
            json={"email": _email(), "password": "super-secret-123"},
            headers=EVIL_ORIGIN,
        )
        assert resp.status_code == 403

    async def test_csrf_trusted_origin_allows_non_server_host(
        self, test_client, fresh_db, monkeypatch
    ):
        # The trusted list covers the same-origin-proxy case: an Origin that is
        # not the host the server sees, but is a trusted frontend origin.
        from canvas_server.config import settings

        monkeypatch.setattr(
            settings, "csrf_trusted_origins", ["http://frontend.local"]
        )
        resp = await test_client.post(
            "/api/auth/register",
            json={"email": _email(), "password": "super-secret-123"},
            headers={"Origin": "http://frontend.local"},
        )
        assert resp.status_code == 201


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for the account-management surface (#39): change password and
logout-other-sessions. Both routes share one ``revoke_other_sessions`` helper
that destroys every session for the user except the calling one.

Written before implementation (TDD). Mirrors the patterns in ``test_auth.py``:
real cookie-jar clients through the ASGI app, same-origin Origin header for the
CSRF check, and a shared ``get_session`` override pointed at the test sqlite DB.
"""

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

ORIGIN = {"Origin": "http://test"}
COOKIE_NAME = "agentbuilder_session"


def _email() -> str:
    return f"user_{uuid.uuid4().hex[:12]}@example.com"


def _set_cookie_header(resp) -> str | None:
    headers = resp.headers.get_list("set-cookie")
    return headers[0] if headers else None


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------


@pytest_asyncio.fixture
async def account_setup(fresh_db):
    """Activate the test-DB ``get_session`` override for the account tests.

    The account tests need multiple independent cookie jars (two browsers logged
    in as the SAME user) and don't use the single-session ``authed_client``
    fixture, so they manage their own override here.
    """
    from canvas_server.database import get_session, get_session_factory
    from canvas_server.main import app

    factory = get_session_factory(
        __import__("os").environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///test.db")
    )

    async def override_get_session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    yield
    app.dependency_overrides.clear()


async def _register_and_login(creds: dict, *, login_only: bool = False) -> AsyncClient:
    """A fresh AsyncClient logged in via the real cookie flow.

    ``login_only=False`` registers the user first; ``login_only=True`` assumes
    the user already exists and just opens a second session for them (a second
    "device" with its own cookie jar).
    """
    from canvas_server.main import app

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    if not login_only:
        r = await client.post("/api/auth/register", json=creds, headers=ORIGIN)
        assert r.status_code == 201, r.text
    r = await client.post("/api/auth/login", json=creds, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert client.cookies.get(COOKIE_NAME) is not None
    return client


def _creds() -> dict:
    return {"email": _email(), "password": "super-secret-123"}


# --------------------------------------------------------------------------
# Change password
# --------------------------------------------------------------------------


class TestChangePassword:
    async def test_requires_auth(self, account_setup, fresh_db):
        # No session cookie -> 401 (the route is authed).
        from canvas_server.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/api/auth/change-password",
                json={"current_password": "x", "new_password": "y"},
                headers=ORIGIN,
            )
        assert resp.status_code == 401

    async def test_requires_origin(self, account_setup, fresh_db):
        alice = await _register_and_login(_creds())
        resp = await alice.post(
            "/api/auth/change-password",
            json={"current_password": "super-secret-123", "new_password": "new-secret-456"},
        )
        assert resp.status_code == 403
        await alice.aclose()

    async def test_wrong_current_password_rejected_without_revoking(
        self, account_setup, fresh_db, test_session
    ):
        creds = _creds()
        alice = await _register_and_login(creds)
        bob = await _register_and_login(creds, login_only=True)  # second device

        resp = await alice.post(
            "/api/auth/change-password",
            json={"current_password": "totally-wrong", "new_password": "new-secret-456"},
            headers=ORIGIN,
        )
        assert resp.status_code == 422, resp.text

        # The password hash is unchanged — bob can still log in? No, bob is
        # already logged in; assert his session is still alive (nothing revoked).
        assert (await bob.get("/api/auth/me")).status_code == 200
        # And the original password still works for a fresh login.
        from canvas_server.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post("/api/auth/login", json=creds, headers=ORIGIN)
            assert r.status_code == 200  # original password still valid
        await alice.aclose()
        await bob.aclose()

    async def test_short_new_password_rejected(self, account_setup, fresh_db):
        alice = await _register_and_login(_creds())
        resp = await alice.post(
            "/api/auth/change-password",
            json={"current_password": "super-secret-123", "new_password": "short"},
            headers=ORIGIN,
        )
        assert resp.status_code == 400, resp.text
        await alice.aclose()

    async def test_correct_change_updates_hash_and_revokes_others(
        self, account_setup, fresh_db
    ):
        creds = _creds()
        alice = await _register_and_login(creds)
        bob = await _register_and_login(creds, login_only=True)  # second device

        # Sanity: both sessions are alive before the change.
        assert (await alice.get("/api/auth/me")).status_code == 200
        assert (await bob.get("/api/auth/me")).status_code == 200

        resp = await alice.post(
            "/api/auth/change-password",
            json={
                "current_password": "super-secret-123",
                "new_password": "new-secret-456",
            },
            headers=ORIGIN,
        )
        assert resp.status_code == 200, resp.text

        # The current (alice) session stays alive — no cookie rotation needed.
        assert (await alice.get("/api/auth/me")).status_code == 200
        # The other (bob) session was revoked — his next protected call 401s.
        assert (await bob.get("/api/auth/me")).status_code == 401

        # The hash actually changed: the old password no longer logs in...
        from canvas_server.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.post(
                "/api/auth/login",
                json={"email": creds["email"], "password": "super-secret-123"},
                headers=ORIGIN,
            )
            assert r.status_code == 401
            # ...and the new password does.
            r = await c.post(
                "/api/auth/login",
                json={"email": creds["email"], "password": "new-secret-456"},
                headers=ORIGIN,
            )
            assert r.status_code == 200
        await alice.aclose()
        await bob.aclose()


# --------------------------------------------------------------------------
# Logout other sessions
# --------------------------------------------------------------------------


class TestLogoutOtherSessions:
    async def test_requires_auth(self, account_setup, fresh_db):
        from canvas_server.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/auth/logout-other-sessions", headers=ORIGIN)
        assert resp.status_code == 401

    async def test_requires_origin(self, account_setup, fresh_db):
        alice = await _register_and_login(_creds())
        resp = await alice.post("/api/auth/logout-other-sessions")
        assert resp.status_code == 403
        await alice.aclose()

    async def test_revokes_others_keeps_current(self, account_setup, fresh_db):
        creds = _creds()
        alice = await _register_and_login(creds)
        bob = await _register_and_login(creds, login_only=True)
        carol = await _register_and_login(creds, login_only=True)

        # Three sessions alive before.
        assert (await alice.get("/api/auth/me")).status_code == 200
        assert (await bob.get("/api/auth/me")).status_code == 200
        assert (await carol.get("/api/auth/me")).status_code == 200

        resp = await alice.post("/api/auth/logout-other-sessions", headers=ORIGIN)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["revoked"] == 2  # bob + carol

        # The calling session survives.
        assert (await alice.get("/api/auth/me")).status_code == 200
        # The other two are gone.
        assert (await bob.get("/api/auth/me")).status_code == 401
        assert (await carol.get("/api/auth/me")).status_code == 401
        await alice.aclose()
        await bob.aclose()
        await carol.aclose()

    async def test_revoked_count_zero_when_only_current(self, account_setup, fresh_db):
        alice = await _register_and_login(_creds())
        resp = await alice.post("/api/auth/logout-other-sessions", headers=ORIGIN)
        assert resp.status_code == 200
        assert resp.json()["revoked"] == 0
        assert (await alice.get("/api/auth/me")).status_code == 200
        await alice.aclose()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

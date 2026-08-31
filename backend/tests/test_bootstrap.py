"""Tests for the .env-seeded default user (DEFAULT_USER_EMAIL / DEFAULT_PASSWORD).

The default user lets a fresh deployment log in immediately: if
``default_user_email`` and ``default_password`` (base64 of the plaintext) are
configured, startup seeds that user account — idempotently, never resetting an
existing user's password.
"""

import base64

from canvas_server.bootstrap import seed_default_user


def _b64(plaintext: str) -> str:
    return base64.b64encode(plaintext.encode()).decode()


def _configure_default_user(monkeypatch, email="demo@example.com", password="demo-pass-123"):
    from canvas_server.config import settings

    monkeypatch.setattr(settings, "default_user_email", email)
    monkeypatch.setattr(settings, "default_password", _b64(password) if password is not None else "")


class TestSeedDefaultUser:
    async def test_creates_user_with_verified_password(self, test_session, monkeypatch):
        _configure_default_user(monkeypatch, email="Demo@Example.com", password="s3cret-pass")
        from canvas_server.security import verify_password

        user = await seed_default_user(test_session)

        assert user is not None
        # The login handle is normalized like every other auth path.
        assert user.email == "demo@example.com"
        assert verify_password("s3cret-pass", user.password_hash)

    async def test_seeded_user_can_login_via_api(self, test_client, test_session, monkeypatch):
        password = "bootstrap-pw-1"
        _configure_default_user(monkeypatch, email="boot@example.com", password=password)

        from canvas_server.database import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            await seed_default_user(session)
            await session.commit()

        r = await test_client.post(
            "/api/auth/login",
            json={"email": "boot@example.com", "password": password},
            headers={"Origin": "http://test"},
        )
        assert r.status_code == 200, r.text

    async def test_idempotent_does_not_reset_existing_password(self, test_session, monkeypatch):
        _configure_default_user(monkeypatch, password="a-fresh-password")
        from canvas_server.repos.auth_repo import AuthRepo
        from canvas_server.security import hash_password, verify_password

        existing = await AuthRepo(test_session).create_user(
            "demo@example.com", hash_password("the-original-password")
        )
        original_hash = existing.password_hash

        user = await seed_default_user(test_session)

        assert user is not None
        assert user.id == existing.id
        assert user.password_hash == original_hash
        assert verify_password("the-original-password", user.password_hash)
        assert not verify_password("a-fresh-password", user.password_hash)

    async def test_skips_when_env_unset(self, test_session, monkeypatch):
        from canvas_server.config import settings

        monkeypatch.setattr(settings, "default_user_email", "")
        monkeypatch.setattr(settings, "default_password", "")

        assert await seed_default_user(test_session) is None

        from canvas_server.repos.auth_repo import AuthRepo

        assert await AuthRepo(test_session).get_user_by_email("demo@example.com") is None

    async def test_skips_when_password_env_unset_even_if_email_set(self, test_session, monkeypatch):
        from canvas_server.config import settings

        monkeypatch.setattr(settings, "default_user_email", "demo@example.com")
        monkeypatch.setattr(settings, "default_password", "")

        assert await seed_default_user(test_session) is None

    async def test_invalid_base64_is_skipped_not_fatal(self, test_session, monkeypatch):
        from canvas_server.config import settings

        monkeypatch.setattr(settings, "default_user_email", "demo@example.com")
        monkeypatch.setattr(settings, "default_password", "!!!not-base64!!!")

        assert await seed_default_user(test_session) is None

    async def test_invalid_email_shape_is_skipped(self, test_session, monkeypatch):
        _configure_default_user(monkeypatch, email="not-an-email")

        assert await seed_default_user(test_session) is None

    async def test_password_below_min_length_is_skipped(self, test_session, monkeypatch):
        # password_min_length defaults to 8 (per #32).
        _configure_default_user(monkeypatch, password="short")

        assert await seed_default_user(test_session) is None


class TestDefaultUserSettings:
    def test_defaults_are_empty(self):
        from canvas_server.config import Settings

        s = Settings()
        assert s.default_user_email == ""
        assert s.default_password == ""

    def test_env_override(self, monkeypatch):
        from canvas_server.config import Settings

        monkeypatch.setenv("DEFAULT_USER_EMAIL", "demo@demo.com")
        monkeypatch.setenv("DEFAULT_PASSWORD", _b64("hunter2-secret"))
        s = Settings()
        assert s.default_user_email == "demo@demo.com"
        import base64 as b64mod

        assert b64mod.b64decode(s.default_password).decode() == "hunter2-secret"

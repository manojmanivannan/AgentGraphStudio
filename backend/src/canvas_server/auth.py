"""Authentication dependencies: session resolution, sliding/absolute timeout
enforcement, and the Origin/Referer CSRF check for state-changing routes."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import HTTPConnection

from canvas_server.config import settings
from canvas_server.database import get_session
from canvas_server.models.auth import User
from canvas_server.repos.auth_repo import AuthRepo

COOKIE_NAME = settings.session_cookie_name


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(dt: datetime) -> datetime:
    """Ensure a datetime is tz-aware.

    sqlite+aiosqlite drops tzinfo on DateTime(timezone=True) columns when
    reading rows back; postgres returns aware values. Normalize before
    comparing so both backends behave identically.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def set_session_cookie(response, session_id: str, *, secure: bool) -> None:
    """Set the auth session cookie with the documented attributes.

    path=/, httpOnly, SameSite=Lax; Secure only when the request is https.
    """
    response.set_cookie(
        COOKIE_NAME,
        session_id,
        path="/",
        httponly=True,
        samesite="lax",
        secure=secure,
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def verify_origin(request: Request) -> None:
    """CSRF guard for state-changing routes.

    Requires an Origin (or Referer) header and that its scheme+host[:port]
    matches either the host the server sees (same-origin direct access) or an
    explicitly trusted origin in ``csrf_trusted_origins`` (same-origin via the
    dev / compose proxy, where the browser's Origin is the frontend host).
    Anything else — cross-origin or missing — is rejected.
    """
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        raise HTTPException(status_code=403, detail="Missing Origin/Referer header")

    parsed = urlparse(source)
    origin_netloc = parsed.netloc
    origin_scheme = parsed.scheme
    if not origin_netloc:
        raise HTTPException(status_code=403, detail="Invalid Origin/Referer header")

    # Same-origin as the server sees it.
    if origin_netloc == request.url.netloc:
        return

    # Trusted same-origin origins — covers the same-origin proxy case, where the
    # browser's Origin is the frontend host but the backend sees its own Host.
    # This is a dedicated list, NOT cors_origins, so adding a third-party origin
    # for CORS does not open a CSRF hole.
    for allowed in settings.csrf_trusted_origins:
        a = urlparse(allowed)
        if a.scheme == origin_scheme and a.netloc == origin_netloc:
            return

    raise HTTPException(status_code=403, detail="Cross-origin request blocked")


async def get_current_user(
    request: HTTPConnection,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the current user from the session cookie.

    Enforces the 30-min sliding idle timeout (extends ``expires_at`` and
    ``last_seen_at`` on every protected-route hit) and the 7-day absolute cap
    (fixed from login). Expired / missing sessions are rejected with 401.

    The connection is typed ``HTTPConnection`` (the shared base of
    ``Request`` and ``WebSocket``) so this one dependency authenticates both
    HTTP routes and the WebSocket run route. FastAPI only injects a
    ``Request``-typed param for HTTP scopes (the websocket branch is skipped),
    so a plain ``request: Request`` here would never receive a value on the WS
    path — leaving the WS route unauthenticated. ``HTTPConnection`` is injected
    unconditionally and exposes ``.cookies`` on both connection types. See
    ADR 0007.
    """
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    repo = AuthRepo(session)
    sess = await repo.get_session(token)
    if sess is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Constant-time compare of the presented token against the stored id.
    if not secrets.compare_digest(token, sess.id):
        raise HTTPException(status_code=401, detail="Not authenticated")

    now = _utcnow()
    if now > _aware(sess.expires_at) or now > _aware(sess.absolute_expires_at):
        # Expired — destroy it so it can't be reused.
        await repo.delete_session(sess.id)
        await session.commit()
        raise HTTPException(status_code=401, detail="Session expired")

    # Sliding idle window: extend the idle deadline on activity.
    sess.last_seen_at = now
    sess.expires_at = now + timedelta(seconds=settings.session_idle_timeout_seconds)
    await session.commit()
    return sess.user

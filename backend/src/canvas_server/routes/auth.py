"""Authentication routes: register, login, logout, /auth/me.

Stateful server-side sessions back all of these (see ``models/auth.py`` and
``auth.py``). This slice does NOT yet require auth on canvas routes — that
lands in a later ticket.
"""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.auth import (
    clear_session_cookie,
    get_current_session,
    get_current_user,
    set_session_cookie,
    verify_origin,
)
from canvas_server.config import settings
from canvas_server.database import get_session
from canvas_server.models.api import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    SessionsRevokedResponse,
    UserResponse,
)
from canvas_server.models.auth import Session, User
from canvas_server.repos.auth_repo import AuthRepo
from canvas_server.security import hash_password, is_valid_email, normalize_email, verify_password

logger = logging.getLogger("canvas_server.routes.auth")
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _validate_password(password: str) -> None:
    if (
        len(password) < settings.password_min_length
        or len(password) > settings.password_max_length
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Password must be between {settings.password_min_length} and "
                f"{settings.password_max_length} characters."
            ),
        )


@auth_router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    body: RegisterRequest,
    session: AsyncSession = Depends(get_session),
    _origin: None = Depends(verify_origin),
) -> AuthResponse:
    _validate_password(body.password)
    if not is_valid_email(body.email):
        raise HTTPException(status_code=400, detail="Invalid email address.")

    email = normalize_email(body.email)
    repo = AuthRepo(session)
    if await repo.get_user_by_email(email) is not None:
        raise HTTPException(status_code=409, detail="Email already registered.")

    user = await repo.create_user(email, hash_password(body.password))
    await session.commit()
    logger.info("Registered new user: %s", email)
    return AuthResponse(user=UserResponse.model_validate(user))


@auth_router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _origin: None = Depends(verify_origin),
) -> AuthResponse:
    email = normalize_email(body.email)
    repo = AuthRepo(session)
    user = await repo.get_user_by_email(email)
    # Identical failure for unknown email vs wrong password — no user enumeration.
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    now = _utcnow()
    expires_at = now + timedelta(seconds=settings.session_idle_timeout_seconds)
    absolute_expires_at = now + timedelta(seconds=settings.session_absolute_timeout_seconds)
    sess = await repo.create_session(user.id, expires_at, absolute_expires_at)
    await session.commit()

    set_session_cookie(response, sess.id, secure=request.url.scheme == "https")
    logger.info("User %s logged in (session %s)", email, sess.id[:8])
    return AuthResponse(user=UserResponse.model_validate(user))


@auth_router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
    _origin: None = Depends(verify_origin),
) -> dict[str, bool]:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        repo = AuthRepo(session)
        await repo.delete_session(token)
        await session.commit()
    clear_session_cookie(response)
    return {"ok": True}


@auth_router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@auth_router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    sess: Session = Depends(get_current_session),
    _origin: None = Depends(verify_origin),
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool]:
    """Verify the current password, then set a new one.

    On success every other session for the user is revoked (via the shared
    ``revoke_other_sessions`` helper) while the calling session stays alive —
    so this device keeps working but every other device's cookie is dead.

    A wrong current password is rejected with 422 (NOT 401) so the frontend's
    global 401 → /login redirect does not fire on a typo while the user is
    logged in. Nothing is revoked on failure.
    """
    # Validate the new password's length before touching the current one, so
    # a bad new password never triggers a revoke.
    _validate_password(body.new_password)

    repo = AuthRepo(session)
    if not verify_password(body.current_password, sess.user.password_hash):
        raise HTTPException(
            status_code=422,
            detail="Current password is incorrect.",
        )

    await repo.update_password(sess.user.id, hash_password(body.new_password))
    await repo.revoke_other_sessions(sess.user.id, keep_session_id=sess.id)
    await session.commit()
    logger.info("User %s changed password (session %s kept)", sess.user.email, sess.id[:8])
    return {"ok": True}


@auth_router.post("/logout-other-sessions", response_model=SessionsRevokedResponse)
async def logout_other_sessions(
    sess: Session = Depends(get_current_session),
    _origin: None = Depends(verify_origin),
    session: AsyncSession = Depends(get_session),
) -> SessionsRevokedResponse:
    """Destroy every session for the current user except the calling one.

    Thin user-facing endpoint that reuses the same ``revoke_other_sessions``
    helper as change-password.
    """
    repo = AuthRepo(session)
    revoked = await repo.revoke_other_sessions(sess.user.id, keep_session_id=sess.id)
    await session.commit()
    logger.info(
        "User %s logged out %s other session(s) (session %s kept)",
        sess.user.email,
        revoked,
        sess.id[:8],
    )
    return SessionsRevokedResponse(revoked=revoked)

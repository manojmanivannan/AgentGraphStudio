"""Startup seeding: create the default user account from .env configuration.

Set ``DEFAULT_USER_EMAIL`` and ``DEFAULT_PASSWORD`` (base64 of the plaintext)
and a fresh deployment can log in immediately — no interactive registration
step. Seeding is idempotent: an account that already exists is left untouched
(the env password is never used to reset a real user's password).
"""

from __future__ import annotations

import base64
import binascii
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.config import settings
from canvas_server.repos.auth_repo import AuthRepo
from canvas_server.security import hash_password, is_valid_email, normalize_email

logger = logging.getLogger("canvas_server")


async def seed_default_user(session: AsyncSession):
    """Create the configured default user if it does not exist yet.

    Returns the seeded user, the pre-existing user when one is already present
    (unchanged), or ``None`` when seeding is disabled, misconfigured, or the
    decoded password violates the min-length policy. Never raises: a bad
    configuration logs a warning and skips so it cannot block startup.
    """
    email = settings.default_user_email.strip()
    encoded_password = settings.default_password.strip()
    if not email or not encoded_password:
        return None

    if not is_valid_email(email):
        logger.warning(
            "DEFAULT_USER_EMAIL=%r is not a valid email — default user not seeded",
            email,
        )
        return None

    try:
        password = base64.b64decode(encoded_password, validate=True).decode()
    except (binascii.Error, UnicodeDecodeError):
        logger.warning(
            "DEFAULT_PASSWORD is not valid base64 of UTF-8 text — default user not seeded"
        )
        return None

    if len(password) < settings.password_min_length:
        logger.warning(
            "DEFAULT_PASSWORD decodes to fewer than %d characters — default user not seeded",
            settings.password_min_length,
        )
        return None

    repo = AuthRepo(session)
    handle = normalize_email(email)
    existing = await repo.get_user_by_email(handle)
    if existing is not None:
        # Never reset a real account's password from env.
        logger.info("Default user %s already exists — leaving it untouched", handle)
        return existing

    user = await repo.create_user(handle, hash_password(password))
    # Repos only flush; this is a self-contained startup task and the lifespan
    # caller passes a fire-and-forget session, so commit here or the insert is
    # rolled back when the session closes.
    await session.commit()
    logger.info("Seeded default user %s from DEFAULT_USER_EMAIL", handle)
    return user

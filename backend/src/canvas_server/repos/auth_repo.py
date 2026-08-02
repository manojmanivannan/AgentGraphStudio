"""CRUD for users and server-side sessions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from canvas_server.models.auth import Session, User, new_session_id


class AuthRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- users ---

    async def get_user_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def create_user(self, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash)
        self._session.add(user)
        await self._session.flush()
        return user

    # --- sessions ---

    async def create_session(
        self,
        user_id: uuid.UUID,
        expires_at: datetime,
        absolute_expires_at: datetime,
    ) -> Session:
        sess = Session(
            id=new_session_id(),
            user_id=user_id,
            expires_at=expires_at,
            absolute_expires_at=absolute_expires_at,
        )
        self._session.add(sess)
        await self._session.flush()
        return sess

    async def get_session(self, session_id: str) -> Session | None:
        """Load a session and its owning user in one query."""
        stmt = (
            select(Session)
            .where(Session.id == session_id)
            .options(selectinload(Session.user))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete_session(self, session_id: str) -> None:
        stmt = delete(Session).where(Session.id == session_id)
        await self._session.execute(stmt)

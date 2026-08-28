"""Read/write access to the singleton provider settings row."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.models.provider import SINGLETON_ID, ProviderSettings


class ProviderSettingsRepo:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> ProviderSettings | None:
        return await self._session.get(ProviderSettings, SINGLETON_ID)

    async def upsert(self, **fields: Any) -> ProviderSettings:
        """Create or partially update the row; unset fields keep their value."""
        row = await self.get()
        if row is None:
            row = ProviderSettings(id=SINGLETON_ID)
            self._session.add(row)

        for key, value in fields.items():
            if value is None:
                continue
            if not hasattr(row, key):
                raise AttributeError(f"Unknown provider settings field: {key}")
            setattr(row, key, value)

        await self._session.flush()
        return row

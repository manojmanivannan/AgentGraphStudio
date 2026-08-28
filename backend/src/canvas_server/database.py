from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from canvas_server.config import settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: Callable[..., async_sessionmaker[AsyncSession]] | None = None
_configured_url: str | None = None


def get_engine(database_url: str | None = None):
    global _engine, _configured_url
    url = database_url or settings.database_url
    if _engine is None or url != _configured_url:
        # Ensure ORM table mappings are imported before metadata is used.
        import canvas_server.models.auth  # noqa: F401
        import canvas_server.models.canvas  # noqa: F401
        import canvas_server.models.provider  # noqa: F401

        _engine = create_async_engine(url, echo=False)
        _configured_url = url
    return _engine


def get_session_factory(database_url: str | None = None):
    global _session_factory
    engine = get_engine(database_url)
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


def reset_session_factory():
    global _engine, _session_factory, _configured_url
    _engine = None
    _session_factory = None
    _configured_url = None


async def async_reset_session_factory():
    global _engine, _session_factory, _configured_url
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
    _configured_url = None


async def get_session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session

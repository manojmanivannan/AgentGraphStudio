"""Active LLM provider configuration.

The app-managed ``provider_settings`` row is the source of truth; the ``.env``
values in :mod:`canvas_server.config` are only a seed/fallback used until a row
exists. Reads are synchronous (callers sit deep inside DSPy construction), so
the resolved config lives in a process-local cache refreshed explicitly via
:func:`refresh_provider_config`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.config import settings

logger = logging.getLogger("canvas_server.provider_config")


@dataclass(frozen=True)
class ProviderConfig:
    profile: str
    llm_provider_type: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    mem0_llm_model: str
    mem0_embedder_model: str
    mem0_embedder_dimensions: int
    source: str = "env"


def provider_config_from_env() -> ProviderConfig:
    return ProviderConfig(
        profile="custom",
        llm_provider_type=settings.llm_provider_type,
        llm_base_url=settings.llm_base_url,
        llm_api_key=settings.llm_api_key,
        llm_model=settings.llm_model,
        mem0_llm_model=settings.mem0_llm_model,
        mem0_embedder_model=settings.mem0_embedder_model,
        mem0_embedder_dimensions=settings.mem0_embedder_dimensions,
        source="env",
    )


def provider_config_from_row(row) -> ProviderConfig:
    return ProviderConfig(
        profile=row.profile,
        llm_provider_type=row.llm_provider_type,
        llm_base_url=row.llm_base_url,
        llm_api_key=row.llm_api_key,
        llm_model=row.llm_model,
        mem0_llm_model=row.mem0_llm_model,
        mem0_embedder_model=row.mem0_embedder_model,
        mem0_embedder_dimensions=row.mem0_embedder_dimensions,
        source="database",
    )


_cached: ProviderConfig | None = None


def get_provider_config() -> ProviderConfig:
    return _cached if _cached is not None else provider_config_from_env()


def set_provider_config(config: ProviderConfig) -> None:
    global _cached
    changed = _cached != config
    _cached = config
    if changed:
        invalidate_derived_caches()


def reset_provider_config() -> None:
    global _cached
    _cached = None


async def refresh_provider_config(session: AsyncSession) -> ProviderConfig:
    """Reload the cache from the database (falling back to env when unset)."""
    from canvas_server.repos.provider_settings_repo import ProviderSettingsRepo

    row = await ProviderSettingsRepo(session).get()
    config = provider_config_from_row(row) if row is not None else provider_config_from_env()
    set_provider_config(config)
    return config


def invalidate_derived_caches() -> None:
    """Drop objects built from the previous provider config (mem0 singleton)."""
    try:
        from canvas_server.runner.memory import MemoryManager

        MemoryManager._shared_memory = None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not reset shared mem0 instance: %s", exc)

"""App-managed provider configuration routes (Settings page)."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from canvas_server.auth import get_current_user, verify_origin
from canvas_server.config import settings
from canvas_server.database import get_session
from canvas_server.models.api import (
    ProviderCheckResult,
    ProviderSettingsResponse,
    ProviderSettingsUpdate,
    ProviderTestRequest,
    ProviderTestResponse,
)
from canvas_server.models.auth import User
from canvas_server.models.canvas import AgentDocumentChunk
from canvas_server.provider_config import (
    ProviderConfig,
    get_provider_config,
    refresh_provider_config,
)
from canvas_server.provider_probe import probe_provider
from canvas_server.repos.provider_settings_repo import ProviderSettingsRepo

logger = logging.getLogger("canvas_server.routes.settings")
settings_router = APIRouter(prefix="/api/settings", tags=["settings"])


def _to_response(config: ProviderConfig) -> ProviderSettingsResponse:
    return ProviderSettingsResponse(
        profile=config.profile,
        llm_provider_type=config.llm_provider_type,
        llm_base_url=config.llm_base_url,
        llm_model=config.llm_model,
        mem0_embedder_model=config.mem0_embedder_model,
        mem0_embedder_dimensions=config.mem0_embedder_dimensions,
        api_key_set=bool(config.llm_api_key),
        source=config.source,
    )


@settings_router.get("/provider", response_model=ProviderSettingsResponse)
async def get_provider_settings(
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> ProviderSettingsResponse:
    return _to_response(await refresh_provider_config(session))


@settings_router.put("/provider", response_model=ProviderSettingsResponse)
async def update_provider_settings(
    body: ProviderSettingsUpdate,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
    _origin: None = Depends(verify_origin),
) -> ProviderSettingsResponse:
    current = await refresh_provider_config(session)
    dims_changed = body.mem0_embedder_dimensions != current.mem0_embedder_dimensions

    if dims_changed and not body.confirm_reindex:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Changing the embedding dimension from {current.mem0_embedder_dimensions} "
                f"to {body.mem0_embedder_dimensions} invalidates every stored RAG chunk and "
                "memory. Confirm to clear them and re-index."
            ),
        )

    repo = ProviderSettingsRepo(session)
    await repo.upsert(
        profile=body.profile,
        llm_provider_type=body.llm_provider_type,
        llm_base_url=body.llm_base_url,
        llm_model=body.llm_model,
        mem0_embedder_model=body.mem0_embedder_model,
        mem0_embedder_dimensions=body.mem0_embedder_dimensions,
        # None keeps the stored key; "" clears it (upsert skips None).
        llm_api_key=body.api_key,
    )

    if dims_changed:
        await session.execute(delete(AgentDocumentChunk))
        _purge_vector_store()

    await session.commit()
    return _to_response(await refresh_provider_config(session))


@settings_router.post("/provider/test", response_model=ProviderTestResponse)
async def test_provider_settings(
    body: ProviderTestRequest,
    session: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
    _origin: None = Depends(verify_origin),
) -> ProviderTestResponse:
    api_key = body.api_key
    if api_key is None:
        stored = await ProviderSettingsRepo(session).get()
        api_key = stored.llm_api_key if stored else get_provider_config().llm_api_key

    candidate = ProviderConfig(
        profile=body.profile,
        llm_provider_type=body.llm_provider_type,
        llm_base_url=body.llm_base_url,
        llm_api_key=api_key,
        llm_model=body.llm_model,
        mem0_embedder_model=body.mem0_embedder_model,
        mem0_embedder_dimensions=body.mem0_embedder_dimensions,
        source="candidate",
    )

    results = await probe_provider(candidate)
    checks = [ProviderCheckResult(**vars(result)) for result in results]
    return ProviderTestResponse(ok=all(check.ok for check in checks), checks=checks)


def _purge_vector_store() -> None:
    """Drop the local Qdrant store so mem0 rebuilds it at the new dimension."""
    path = Path(settings.mem0_qdrant_path)
    if not path.is_dir():
        return
    try:
        shutil.rmtree(path)
    except OSError as exc:
        logger.warning("Could not purge vector store at %s: %s", path, exc)

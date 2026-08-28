"""Provider configuration seam: env fallback, DB precedence, cache refresh."""

import pytest

from canvas_server.config import settings
from canvas_server.provider_config import (
    ProviderConfig,
    derive_mem0_llm_model,
    get_provider_config,
    provider_config_from_env,
    refresh_provider_config,
    reset_provider_config,
    set_provider_config,
)
from canvas_server.repos.provider_settings_repo import ProviderSettingsRepo


@pytest.fixture(autouse=True)
def _clean_provider_cache():
    reset_provider_config()
    yield
    reset_provider_config()


def test_falls_back_to_env_when_cache_empty():
    cfg = get_provider_config()
    assert cfg.llm_model == settings.llm_model
    assert cfg.llm_base_url == settings.llm_base_url
    assert cfg.mem0_embedder_dimensions == settings.mem0_embedder_dimensions
    assert cfg.source == "env"


@pytest.mark.parametrize(
    ("llm_model", "expected"),
    [
        ("ollama_chat/gemma3:27b", "gemma3:27b"),
        ("openrouter/google/gemma-3-27b-it:free", "google/gemma-3-27b-it:free"),
        ("gpt-4o-mini", "gpt-4o-mini"),
        ("myorg/custom-model", "myorg/custom-model"),
    ],
)
def test_mem0_model_is_derived_from_chat_model(llm_model, expected):
    assert derive_mem0_llm_model(llm_model) == expected


def test_set_provider_config_takes_precedence():
    env_cfg = provider_config_from_env()
    set_provider_config(
        ProviderConfig(
            profile="openai",
            llm_provider_type="openai",
            llm_base_url="https://api.openai.com/v1",
            llm_api_key="sk-test",
            llm_model="gpt-4o-mini",
            mem0_embedder_model="text-embedding-3-small",
            mem0_embedder_dimensions=1536,
            source="database",
        )
    )
    cfg = get_provider_config()
    assert cfg.llm_model == "gpt-4o-mini"
    assert cfg.llm_model != env_cfg.llm_model or env_cfg.llm_model == "gpt-4o-mini"

    reset_provider_config()
    assert get_provider_config().llm_model == settings.llm_model


@pytest.mark.asyncio
async def test_refresh_uses_env_when_no_row(test_session):
    cfg = await refresh_provider_config(test_session)
    assert cfg.source == "env"
    assert cfg.llm_model == settings.llm_model


@pytest.mark.asyncio
async def test_refresh_loads_persisted_row(test_session):
    repo = ProviderSettingsRepo(test_session)
    await repo.upsert(
        profile="openrouter",
        llm_provider_type="openai",
        llm_base_url="https://openrouter.ai/api/v1",
        llm_api_key="or-key",
        llm_model="openrouter/some/model",
        mem0_embedder_model="some/embed",
        mem0_embedder_dimensions=2048,
    )
    await test_session.commit()

    cfg = await refresh_provider_config(test_session)
    assert cfg.source == "database"
    assert cfg.profile == "openrouter"
    assert cfg.llm_api_key == "or-key"
    assert cfg.mem0_embedder_dimensions == 2048
    assert get_provider_config().llm_model == "openrouter/some/model"


@pytest.mark.asyncio
async def test_refresh_resets_shared_mem0_singleton(test_session):
    from canvas_server.runner.memory import MemoryManager

    MemoryManager._shared_memory = object()
    repo = ProviderSettingsRepo(test_session)
    await repo.upsert(
        profile="openai",
        llm_provider_type="openai",
        llm_base_url="https://api.openai.com/v1",
        llm_api_key="sk",
        llm_model="gpt-4o-mini",
        mem0_embedder_model="text-embedding-3-small",
        mem0_embedder_dimensions=1536,
    )
    await test_session.commit()

    await refresh_provider_config(test_session)
    assert MemoryManager._shared_memory is None


@pytest.mark.asyncio
async def test_upsert_is_singleton(test_session):
    repo = ProviderSettingsRepo(test_session)
    await repo.upsert(llm_model="a", mem0_embedder_dimensions=768)
    await repo.upsert(llm_model="b")
    await test_session.commit()

    row = await repo.get()
    assert row is not None
    assert row.llm_model == "b"
    # Partial upsert must not clobber untouched fields.
    assert row.mem0_embedder_dimensions == 768

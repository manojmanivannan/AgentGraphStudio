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


@pytest.mark.parametrize(
    ("provider_type", "llm_model", "expected"),
    [
        ("openai", "openrouter/google/gemma-4-31b-it:free", "openrouter/google/gemma-4-31b-it:free"),
        ("openai", "openrouter/google/gemma-4-26b-a4b-it:free", "openrouter/google/gemma-4-26b-a4b-it:free"),
        ("openai", "google/gemma-4-26b-a4b-it:free", "openai/google/gemma-4-26b-a4b-it:free"),
        ("openai", "gpt-4o-mini", "openai/gpt-4o-mini"),
        ("openai", "openai/gpt-4o-mini", "openai/gpt-4o-mini"),
        ("ollama", "ollama_chat/llama3.1", "ollama_chat/llama3.1"),
        ("ollama", "ollama/llama3.1", "ollama/llama3.1"),
        ("ollama", "llama3.1", "ollama/llama3.1"),
        ("", "some-model", "some-model"),
    ],
)
def test_dspy_llm_model_routing(provider_type, llm_model, expected):
    cfg = ProviderConfig(
        profile="custom",
        llm_provider_type=provider_type,
        llm_base_url="https://example.com",
        llm_api_key="key",
        llm_model=llm_model,
        mem0_embedder_model="embed",
        mem0_embedder_dimensions=1536,
    )
    assert cfg.dspy_llm_model == expected


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

    class FakeClient:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    class FakeStore:
        def __init__(self):
            self.client = FakeClient()

    class FakeMemory:
        def __init__(self):
            self.vector_store = FakeStore()
            self._telemetry_vector_store = FakeStore()
            self._entity_store = None

    memory = FakeMemory()
    MemoryManager._shared_memory = memory
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
    # Local Qdrant stores must be closed or the rebuild hits a directory lock.
    assert memory.vector_store.client.closed is True
    assert memory._telemetry_vector_store.client.closed is True


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


def _probe_cfg(llm_api_key: str) -> ProviderConfig:
    return ProviderConfig(
        profile="custom",
        llm_provider_type="ollama",
        llm_base_url="http://127.0.0.1:1",
        llm_api_key=llm_api_key,
        llm_model="ollama_chat/glm-5.3-flash:cloud",
        mem0_embedder_model="nomic-embed-text",
        mem0_embedder_dimensions=768,
    )


def test_dspy_client_kwargs_omits_empty_api_key():
    # dspy>=3.4 registers an api_keys entry whenever the kwarg is present, even
    # empty, and then refuses with "empty credential under '<provider>'".
    # Keyless endpoints (local ollama) must omit the kwarg entirely.
    from canvas_server.provider_config import dspy_client_kwargs

    kwargs = dspy_client_kwargs(_probe_cfg(llm_api_key=""))
    assert "api_key" not in kwargs
    assert kwargs["api_base"] == "http://127.0.0.1:1"


def test_dspy_client_kwargs_keeps_set_api_key():
    from canvas_server.provider_config import dspy_client_kwargs

    kwargs = dspy_client_kwargs(_probe_cfg(llm_api_key="sk-test"))
    assert kwargs["api_key"] == "sk-test"


def test_dspy_client_kwargs_passes_extra_kwargs_through():
    from canvas_server.provider_config import dspy_client_kwargs

    kwargs = dspy_client_kwargs(_probe_cfg(llm_api_key="sk-test"), num_retries=0, timeout=5)
    assert kwargs["num_retries"] == 0
    assert kwargs["timeout"] == 5


def test_dspy_client_kwargs_pins_litellm_engine():
    # dspy>=3.4 defaults to engine="auto" and its native lm15 backend, which
    # POSTs to {base_url}/chat/completions. Ollama base URLs are the server
    # root (the OpenAI-compatible surface lives at /v1/...), so lm15 404s.
    # Pinning the litellm compatibility engine keeps the wire behavior the
    # runtime, probe and mem0 were built against.
    from canvas_server.provider_config import dspy_client_kwargs

    assert dspy_client_kwargs(_probe_cfg(llm_api_key=""))["engine"] == "litellm"

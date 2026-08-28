"""Build mem0 config from the active provider configuration."""

from canvas_server.config import settings
from canvas_server.provider_config import get_provider_config


def build_mem0_config() -> dict:
    active = get_provider_config()
    provider = active.llm_provider_type
    llm_config = {
        "model": active.mem0_llm_model,
        "api_key": active.llm_api_key,
        "temperature": 0.1,
    }
    if provider == "ollama":
        llm_config["ollama_base_url"] = active.llm_base_url
    elif provider == "openai":
        llm_config["openai_base_url"] = active.llm_base_url

    embedder_config = {
        "model": active.mem0_embedder_model,
        "api_key": active.llm_api_key,
    }
    if provider == "ollama":
        embedder_config["ollama_base_url"] = active.llm_base_url
    elif provider == "openai":
        embedder_config["openai_base_url"] = active.llm_base_url

    return {
        "llm": {
            "provider": provider,
            "config": llm_config,
        },
        "embedder": {
            "provider": provider,
            "config": embedder_config,
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "embedding_model_dims": active.mem0_embedder_dimensions,
                "path": settings.mem0_qdrant_path,
                "on_disk": settings.mem0_qdrant_on_disk,
            },
        },
        "version": "v1.1",
    }

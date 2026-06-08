"""Build mem0 config from application settings."""

from canvas_server.config import settings


def build_mem0_config() -> dict:
    llm_provider = settings.mem0_llm_provider
    llm_config = {
        "model": settings.mem0_llm_model,
        "api_key": settings.llm_api_key,
        "temperature": 0.1,
    }
    if llm_provider == "ollama":
        llm_config["ollama_base_url"] = settings.llm_base_url
    elif llm_provider == "openai":
        llm_config["openai_base_url"] = settings.llm_base_url

    embedder_provider = settings.mem0_embedder_provider
    embedder_config = {
        "model": settings.mem0_embedder_model,
        "api_key": settings.llm_api_key,
    }
    if embedder_provider == "ollama":
        embedder_config["ollama_base_url"] = settings.llm_base_url
    elif embedder_provider == "openai":
        embedder_config["openai_base_url"] = settings.llm_base_url

    return {
        "llm": {
            "provider": llm_provider,
            "config": llm_config,
        },
        "embedder": {
            "provider": embedder_provider,
            "config": embedder_config,
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "embedding_model_dims": settings.mem0_embedder_dimensions,
                "path": settings.mem0_qdrant_path,
                "on_disk": settings.mem0_qdrant_on_disk,
            },
        },
        "version": "v1.1",
    }


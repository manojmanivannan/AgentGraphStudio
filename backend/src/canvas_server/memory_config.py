"""Build mem0 config from application settings."""

from canvas_server.config import settings


def build_mem0_config() -> dict:
    return {
        "llm": {
            "provider": settings.mem0_llm_provider,
            "config": {
                "model": settings.mem0_llm_model,
                "ollama_base_url": settings.llm_base_url,
                "temperature": 0.1,
            },
        },
        "embedder": {
            "provider": settings.mem0_embedder_provider,
            "config": {
                "model": settings.mem0_embedder_model,
                "ollama_base_url": settings.llm_base_url,
            },
        },
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "embedding_model_dims": 768,
            },
        },
        "version": "v1.1",
    }

from canvas_server.config import Settings


class TestSettings:
    def test_default_database_url(self):
        settings = Settings()
        assert "sqlite+aiosqlite" in settings.database_url

    def test_default_cors_origins(self):
        settings = Settings()
        assert "http://localhost:5173" in settings.cors_origins

    def test_default_llm_model(self):
        settings = Settings()
        assert settings.llm_model != ""

    def test_llm_base_url_has_default(self):
        settings = Settings()
        assert settings.llm_base_url != ""

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host/db")
        monkeypatch.setenv("LLM_BASE_URL", "http://ollama:1234/v1")
        settings = Settings()
        assert settings.database_url == "postgresql+asyncpg://user:pass@host/db"
        assert settings.llm_base_url == "http://ollama:1234/v1"


class TestMemoryConfig:
    def test_build_mem0_config_ollama(self, monkeypatch):
        from canvas_server.config import settings
        from canvas_server.memory_config import build_mem0_config

        monkeypatch.setattr(settings, "llm_provider_type", "ollama")
        monkeypatch.setattr(settings, "llm_base_url", "http://ollama-host:11434")
        monkeypatch.setattr(settings, "llm_api_key", "test-key")
        monkeypatch.setattr(settings, "mem0_llm_model", "test-llm-model")
        monkeypatch.setattr(settings, "mem0_embedder_model", "test-embed-model")
        monkeypatch.setattr(settings, "mem0_embedder_dimensions", 2048)

        config = build_mem0_config()
        assert config["llm"]["provider"] == "ollama"
        assert config["llm"]["config"]["model"] == "test-llm-model"
        assert config["llm"]["config"]["ollama_base_url"] == "http://ollama-host:11434"
        assert "embedding_model_dims" not in config["llm"]["config"]
        assert "openai_base_url" not in config["llm"]["config"]

        assert config["embedder"]["provider"] == "ollama"
        assert config["embedder"]["config"]["model"] == "test-embed-model"
        assert (
            config["embedder"]["config"]["ollama_base_url"]
            == "http://ollama-host:11434"
        )
        assert "openai_base_url" not in config["embedder"]["config"]

    def test_build_mem0_config_openai(self, monkeypatch):
        from canvas_server.config import settings
        from canvas_server.memory_config import build_mem0_config

        monkeypatch.setattr(settings, "llm_provider_type", "openai")
        monkeypatch.setattr(settings, "llm_base_url", "https://openrouter.ai/api/v1")
        monkeypatch.setattr(settings, "llm_api_key", "sk-test-key")
        monkeypatch.setattr(settings, "mem0_llm_model", "test-openai-model")
        monkeypatch.setattr(settings, "mem0_embedder_model", "test-embed-model")
        monkeypatch.setattr(settings, "mem0_qdrant_path", "/data/qdrant")
        monkeypatch.setattr(settings, "mem0_qdrant_on_disk", True)

        config = build_mem0_config()
        assert config["llm"]["provider"] == "openai"
        assert config["llm"]["config"]["model"] == "test-openai-model"
        assert (
            config["llm"]["config"]["openai_base_url"] == "https://openrouter.ai/api/v1"
        )
        assert "ollama_base_url" not in config["llm"]["config"]

        assert config["embedder"]["provider"] == "openai"
        assert config["embedder"]["config"]["model"] == "test-embed-model"
        assert (
            config["embedder"]["config"]["openai_base_url"]
            == "https://openrouter.ai/api/v1"
        )
        assert "ollama_base_url" not in config["embedder"]["config"]
        assert config["vector_store"]["config"]["path"] == "/data/qdrant"
        assert config["vector_store"]["config"]["on_disk"] is True

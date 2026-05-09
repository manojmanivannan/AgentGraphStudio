import os
from canvas_server.config import Settings


class TestSettings:
    def test_default_database_url(self):
        db = "canvas_db"
        settings = Settings()
        assert "sqlite+aiosqlite" in settings.database_url

    def test_default_cors_origins(self):
        settings = Settings()
        assert "http://localhost:5173" in settings.cors_origins

    def test_default_llm(self):
        settings = Settings()
        assert settings.default_llm == "ollama:ollama/granite4.1:3b"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host/db")
        monkeypatch.setenv("LLM_BASE_URL", "http://ollama:1234/v1")
        settings = Settings()
        assert settings.database_url == "postgresql+asyncpg://user:pass@host/db"
        assert settings.llm_base_url == "http://ollama:1234/v1"

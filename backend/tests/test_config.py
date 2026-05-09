import os
from canvas_server.config import Settings


class TestSettings:
    def test_default_database_url(self):
        db = "canvas_db"
        settings = Settings()
        assert "postgresql+asyncpg" in settings.database_url
        assert "canvas" in settings.database_url

    def test_default_ollama_host(self):
        settings = Settings()
        assert "localhost" in settings.ollama_host
        assert "11434" in settings.ollama_host

    def test_default_cors_origins(self):
        settings = Settings()
        assert "http://localhost:5173" in settings.cors_origins

    def test_default_llm(self):
        settings = Settings()
        assert settings.default_llm == "ollama:llama3.1"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host/db")
        monkeypatch.setenv("OLLAMA_HOST", "http://ollama:1234/v1")
        settings = Settings()
        assert settings.database_url == "postgresql+asyncpg://user:pass@host/db"
        assert settings.ollama_host == "http://ollama:1234/v1"

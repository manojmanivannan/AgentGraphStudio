from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://canvas:canvas@localhost:5432/canvas_db"
    default_llm: str = "ollama:llama3.1"
    cors_origins: list[str] = ["http://localhost:5173"]
    ollama_host: str = "http://localhost:11434"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

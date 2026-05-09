from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://canvas:canvas@localhost:5432/canvas_db"
    default_llm: str = "ollama:llama3.1"
    cors_origins: list[str] = ["http://localhost:5173"]
    ollama_host: str = "http://localhost:11434"
    llm_base_url: str = "http://localhost:11434"
    llm_model_router: str = ""
    llm_model_agent: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

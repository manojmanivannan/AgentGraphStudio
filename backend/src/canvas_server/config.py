from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://canvas:canvas@localhost:5432/canvas_db"
    default_llm: str = "ollama:ollama/granite4.1:3b"
    cors_origins: list[str] = ["http://localhost:5173"]
    llm_base_url: str = "http://192.168.1.120:11434"
    llm_model_router: str = "ollama:glm-5.1:cloud"
    llm_model_agent: str = "ollama:glm-5.1:cloud"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

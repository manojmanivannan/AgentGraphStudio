from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://canvas:canvas@localhost:5432/canvas_db"
    cors_origins: list[str] = ["http://localhost:5173"]
    llm_base_url: str = "http://192.168.1.120:11434"
    llm_api_key: str = ""
    llm_model: str = "ollama_chat/gemma4:31b"

    # Memory (mem0) settings
    mem0_provider: str = "ollama"
    mem0_llm_model: str = "gemma4:31b"
    mem0_embedder_model: str = "nomic-embed-text"
    mem0_embedder_dimensions: int = 768
    mem0_qdrant_path: str = "/tmp/qdrant"
    mem0_qdrant_on_disk: bool = True

    # MLflow tracing — set MLFLOW_ENABLED=false to skip initialization (e.g. in CI)
    mlflow_enabled: bool = True
    mlflow_tracking_uri: str = "http://mlflow:5000"
    mlflow_experiment_name: str = "canvas-agents"
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

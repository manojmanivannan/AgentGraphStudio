from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://canvas:canvas@localhost:5432/canvas_db"
    cors_origins: list[str] = ["http://localhost:5173"]
    llm_base_url: str = "http://192.168.1.120:11434"
    llm_api_key: str = ""
    llm_model: str = "ollama_chat/gemma4:31b"
    llm_title_timeout_seconds: float = 8.0
    llm_validation_timeout_seconds: float = 12.0
    execution_mode: str = "all"

    # Memory (mem0) settings
    llm_provider_type: str = "ollama"
    mem0_llm_model: str = "gemma4:31b"
    mem0_embedder_model: str = "nomic-embed-text"
    mem0_embedder_dimensions: int = 768
    mem0_qdrant_path: str = "/tmp/qdrant"
    mem0_qdrant_on_disk: bool = True

    # MLflow tracing — set MLFLOW_ENABLED=false to skip initialization (e.g. in CI)
    mlflow_enabled: bool = True
    mlflow_tracking_uri: str = "http://mlflow:5000"
    mlflow_experiment_name: str = "canvas-agents"

    # --- Auth & sessions ---
    # Password rules (per #32): min 8, no mandatory complexity, max 1024.
    password_min_length: int = 8
    password_max_length: int = 1024
    # Sliding idle timeout and fixed-from-login absolute cap.
    session_idle_timeout_seconds: int = 1800  # 30 min
    session_absolute_timeout_seconds: int = 604800  # 7 days
    # Cookie attributes (per #32).
    session_cookie_name: str = "agentbuilder_session"
    # Origins trusted for the CSRF same-origin check on state-changing routes.
    # Deliberately separate from cors_origins: CORS is for intentionally
    # third-party API access, while CSRF trust must be same-origin only.
    # Defaults to the local Vite dev origin (served same-origin via the proxy).
    csrf_trusted_origins: list[str] = ["http://localhost:5173"]

    # --- Sandbox (llm-sandbox) container resource limits ---
    # Applied to warm pool containers at creation time via docker runtime_configs.
    # sandbox_mem_limit is a docker mem_limit string (e.g. "512m", "1g"); empty
    # disables the memory cap. sandbox_cpus is CPU cores (fractional allowed),
    # converted to nano_cpus for docker-py; 0.0 disables the CPU cap.
    sandbox_mem_limit: str = "512m"
    sandbox_cpus: float = 1.0

    # --- Sandbox networked pool (#55) ---
    # ``network_mode`` for the *lazy networked* pool (the pool that agents with
    # ``enable_network`` run in). This is a **config seam**: it defaults to
    # Docker's ``"bridge"`` (internet egress) so a future custom egress network
    # + proxy can be swapped with no code change. The *locked* default pool is
    # always ``network_mode="none"`` — a hardcoded invariant (CLAUDE.md §8), NOT
    # this knob.
    sandbox_network_mode: str = "bridge"

    # --- pip_install hardening (#56) ---
    # Wall-clock timeout for a single ``pip_install`` call (and the hardened
    # author-tool pip installs). A pip install that overruns this is aborted
    # and surfaced as an observation string (agent path) / error (author path)
    # — never allowed to stall the turn indefinitely.
    sandbox_pip_install_timeout: int = 120

    model_config = {
        "env_file": (".env", "../.env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()

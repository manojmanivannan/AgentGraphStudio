import logging
import os
import time
from contextlib import asynccontextmanager

import mlflow
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import canvas_server
from canvas_server.background_run_worker import shutdown_background_run_worker
from canvas_server.config import settings
from canvas_server.provider_config import get_provider_config, refresh_provider_config
from canvas_server.routes.auth import auth_router
from canvas_server.routes.canvas import canvas_router
from canvas_server.routes.execute import execute_router
from canvas_server.routes.settings import settings_router
from canvas_server.routes.tools import tools_router

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s",
)
logger = logging.getLogger("canvas_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Canvas server starting up")

    # Ensure plots storage directory exists
    backend_root = os.path.dirname(os.path.dirname(os.path.dirname(canvas_server.__file__)))
    plots_dir = os.path.join(backend_root, "storage", "plots")
    os.makedirs(plots_dir, exist_ok=True)
    logger.info(f"Ensured plots storage directory exists: {plots_dir}")

    url_part = (
        settings.database_url.split("@")[1] if "@" in settings.database_url else "..."
    )
    logger.debug("Config: database_url=%s", url_part)

    # App-managed provider settings win over .env once a row exists.
    try:
        from canvas_server.database import get_session_factory

        factory = get_session_factory()
        async with factory() as session:
            await refresh_provider_config(session)
    except Exception as exc:
        logger.warning("Could not load provider settings from database: %s", exc)

    # Seed the optional default user (DEFAULT_USER_EMAIL / DEFAULT_PASSWORD).
    # Never fatal: misconfiguration logs a warning and startup continues.
    try:
        from canvas_server.bootstrap import seed_default_user

        factory = get_session_factory()
        async with factory() as session:
            await seed_default_user(session)
    except Exception as exc:
        logger.warning("Could not seed default user: %s", exc)

    logger.debug("Config: llm_model=%s", get_provider_config().llm_model)
    logger.debug(f"Config: cors_origins={settings.cors_origins}")

    # Pre-warm the llm-sandbox pool for tool execution
    try:
        from canvas_server.sandbox import get_sandbox

        manager = await get_sandbox()
        await manager.initialize_pool()
        logger.info("llm-sandbox pool initialized")
    except Exception as exc:
        logger.warning("Sandbox initialization failed (tools will not work): %s", exc)

    # Initialize MLflow tracing for DSPy — skip gracefully when unavailable
    if settings.mlflow_enabled:
        try:
            mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
            mlflow.set_experiment(settings.mlflow_experiment_name)
            mlflow.dspy.autolog()
            logger.info(
                "MLflow tracing enabled: tracking_uri=%s experiment=%s",
                settings.mlflow_tracking_uri,
                settings.mlflow_tracking_uri,
            )
        except Exception as exc:
            logger.warning(
                "MLflow tracing disabled — could not connect to %s: %s",
                settings.mlflow_tracking_uri,
                exc,
            )
    else:
        logger.info("MLflow tracing disabled via configuration")

    yield
    logger.info("Canvas server shutting down")

    # Shut down the sandbox manager
    try:
        from canvas_server.sandbox import get_sandbox

        manager = await get_sandbox()
        await manager.shutdown()
        logger.info("SandboxManager shut down")
    except Exception as exc:
        logger.warning("Sandbox shutdown failed: %s", exc)

    try:
        await shutdown_background_run_worker()
    except Exception as exc:
        logger.warning("Background worker shutdown failed: %s", exc)


app = FastAPI(title="Canvas Server", version="0.1.0", lifespan=lifespan)

# Mount static files route for plots
backend_root = os.path.dirname(os.path.dirname(os.path.dirname(canvas_server.__file__)))
plots_dir = os.path.join(backend_root, "storage", "plots")
os.makedirs(plots_dir, exist_ok=True)
app.mount("/api/static/plots", StaticFiles(directory=plots_dir), name="plots")

app.add_middleware(
    CORSMiddleware,

    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    logger.debug(
        f"--> {request.method} {request.url.path} from {request.client.host if request.client else '?'}"
    )
    response = await call_next(request)
    elapsed = time.time() - start
    logger.debug(
        f"<-- {request.method} {request.url.path} [{response.status_code}] {elapsed:.3f}s"
    )
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"Unhandled exception on {request.method} {request.url.path}: {exc}",
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


app.include_router(auth_router)
app.include_router(canvas_router)
app.include_router(execute_router)
app.include_router(settings_router)
app.include_router(tools_router)


@app.get("/health")
async def health():
    logger.debug("Health check requested")
    return {"status": "ok"}

import asyncio
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from canvas_server.config import settings
from canvas_server.routes.canvas import canvas_router
from canvas_server.routes.execute import execute_router

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("canvas_server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Canvas server starting up")
    logger.debug(f"Config: database_url={settings.database_url.split('@')[1] if '@' in settings.database_url else '...'}")
    logger.debug(f"Config: default_llm={settings.default_llm}")
    logger.debug(f"Config: cors_origins={settings.cors_origins}")
    yield
    logger.info("Canvas server shutting down")


app = FastAPI(title="Canvas Server", version="0.1.0", lifespan=lifespan)

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
    logger.debug(f"--> {request.method} {request.url.path} from {request.client.host if request.client else '?'}")
    response = await call_next(request)
    elapsed = time.time() - start
    logger.debug(f"<-- {request.method} {request.url.path} [{response.status_code}] {elapsed:.3f}s")
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


app.include_router(canvas_router)
app.include_router(execute_router)


@app.get("/health")
async def health():
    logger.debug("Health check requested")
    return {"status": "ok"}

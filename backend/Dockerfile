FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev

COPY alembic.ini .
COPY alembic/ alembic/
COPY src/ src/

ENV PYTHONPATH=/app/src

EXPOSE 8000

CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn canvas_server.main:app --host 0.0.0.0 --port 8000 --reload"]

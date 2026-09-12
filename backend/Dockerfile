FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --frozen --no-install-project --no-dev

FROM python:3.14-slim-bookworm

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app/src

COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini .
COPY alembic/ alembic/
COPY src/ src/

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn canvas_server.main:app --host 0.0.0.0 --port 8000"]

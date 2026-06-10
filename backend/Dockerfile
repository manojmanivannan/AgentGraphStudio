FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# install docker for the llm-sandbox to access the host docker as backend
RUN apt-get update && \
    apt-get install -y curl unzip ca-certificates gnupg && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | \
    gpg --dearmor -o /etc/apt/keyrings/docker.gpg && \
    echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/debian bookworm stable" \
    > /etc/apt/sources.list.d/docker.list && \
    apt-get update && \
    apt-get install -y docker-ce-cli && \
    rm -rf /var/lib/apt/lists/*

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

CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn canvas_server.main:app --host 0.0.0.0 --port 8000"]

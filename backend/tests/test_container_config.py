from pathlib import Path

import tomllib


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"


def test_production_dependencies_exclude_test_packages() -> None:
    with (BACKEND_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        dependencies = tomllib.load(pyproject_file)["project"]["dependencies"]

    package_names = {dependency.split("[")[0].split("<")[0].split(">=")[0] for dependency in dependencies}

    assert "mlflow-skinny" in package_names
    assert package_names.isdisjoint({"pytest", "pytest-asyncio", "aiosqlite", "fastembed", "mlflow"})


def test_backend_image_uses_only_python_runtime_tools() -> None:
    dockerfile = (BACKEND_ROOT / "Dockerfile").read_text()

    assert " AS builder" in dockerfile
    assert "FROM python:3.12-slim-bookworm" in dockerfile
    assert "COPY --from=builder /app/.venv /app/.venv" in dockerfile
    assert "apt-get" not in dockerfile
    assert "docker-ce-cli" not in dockerfile
    assert "UV_COMPILE_BYTECODE=1" in dockerfile
    assert "uv run" not in dockerfile


def test_backend_healthcheck_does_not_require_curl() -> None:
    compose = (REPO_ROOT / "docker-compose.yml").read_text()

    assert '["CMD", "curl"' not in compose
    assert "urllib.request.urlopen('http://localhost:8000/health')" in compose

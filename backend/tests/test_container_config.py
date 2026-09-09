import tomllib
from pathlib import Path

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


def test_sandbox_image_uses_a_slim_runtime_base() -> None:
    dockerfile = (REPO_ROOT / "sandbox" / "Dockerfile").read_text()

    assert "FROM python:3.11-slim-trixie" in dockerfile
    assert "ghcr.io/vndee/sandbox-python-311-bullseye" not in dockerfile
    assert "pip install --no-cache-dir matplotlib plotly numpy" in dockerfile
    # --no-compile must NOT be used here either: it defers all bytecode
    # compilation to the first execution inside every pooled container.
    assert "--no-compile" not in dockerfile


def test_mlflow_image_avoids_pip_cache_and_runs_unprivileged() -> None:
    dockerfile = (REPO_ROOT / "mlflow" / "Dockerfile").read_text()

    assert "FROM python:3.12-slim" in dockerfile
    assert "pip install --no-cache-dir --only-binary=:all: mlflow" in dockerfile
    # --no-compile must NOT be used: site-packages stays root-owned while the
    # server runs as the unprivileged mlflow user, so bytecode can never be
    # written lazily at runtime — every worker would recompile the whole
    # package (~40s import) and blow past the compose healthcheck window.
    assert "--no-compile" not in dockerfile
    assert "USER mlflow" in dockerfile


def test_dependabot_covers_all_dependency_ecosystems() -> None:
    dependabot = (REPO_ROOT / ".github" / "dependabot.yml").read_text()

    assert 'package-ecosystem: "github-actions"' in dependabot
    assert 'package-ecosystem: "uv"\n    directory: "/backend"' in dependabot
    assert 'package-ecosystem: "npm"\n    directory: "/frontend"' in dependabot
    for directory in ("/backend", "/frontend", "/mlflow", "/sandbox"):
        assert f'package-ecosystem: "docker"\n    directory: "{directory}"' in dependabot

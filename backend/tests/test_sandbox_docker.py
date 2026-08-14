from unittest.mock import MagicMock, patch

import pytest

from canvas_server.sandbox import SandboxError, SandboxManager


class MockDockerPoolManager(MagicMock):
    pass

@pytest.mark.asyncio
async def test_sandbox_session_lifecycle():
    """Test that a SandboxSession can run code and be closed."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create_pool:
        mock_pool = MockDockerPoolManager()
        mock_pool.image = "mock-image"
        mock_container = MagicMock()
        mock_container.container_id = "mock-container-id"
        mock_pool.acquire.return_value = mock_container
        mock_create_pool.return_value = mock_pool

        manager = SandboxManager()
        await manager.initialize_pool()

        session = manager.get_session("test_conv", enable_plotting=False)

        # Mock the session.run return value
        # llm-sandbox returns a result object with .stdout
        mock_result = MagicMock()
        mock_result.stdout = '{"result": 42}'

        from llm_sandbox.pool.session import PooledSandboxSession
        mock_backend = MagicMock()
        mock_backend.run.return_value = mock_result
        mock_backend.language_handler.run_with_artifacts.return_value = (mock_result, [])

        with patch.object(PooledSandboxSession, "_create_backend_session", return_value=mock_backend):
            with session:
                result = session.run("result = 10 + 32")
            assert result.stdout == '{"result": 42}'

        manager.release_session("test_conv")
        # Verify session was closed
        mock_backend.close.assert_called_once()

@pytest.mark.asyncio
async def test_sandbox_session_install():
    """Test that a SandboxSession can install packages via libraries arg."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create_pool:
        mock_pool = MockDockerPoolManager()
        mock_pool.image = "mock-image"
        mock_container = MagicMock()
        mock_container.container_id = "mock-container-id"
        mock_pool.acquire.return_value = mock_container
        mock_create_pool.return_value = mock_pool

        manager = SandboxManager()
        await manager.initialize_pool()
        session = manager.get_session("test_conv", enable_plotting=False)

        mock_result = MagicMock()
        mock_result.stdout = "Success"

        from llm_sandbox.pool.session import PooledSandboxSession
        mock_backend = MagicMock()
        mock_backend.run.return_value = mock_result

        def mock_run_with_artifacts(container, code, libraries=None, **kwargs):
            return mock_backend.run(code, libraries=libraries, **kwargs), []
        mock_backend.language_handler.run_with_artifacts.side_effect = mock_run_with_artifacts

        with patch.object(PooledSandboxSession, "_create_backend_session", return_value=mock_backend):
            with session:
                session.run("import numpy", libraries=["numpy"])
            args, kwargs = mock_backend.run.call_args
            assert args == ("import numpy",)
            assert kwargs.get("libraries") == ["numpy"]

        manager.release_session("test_conv")

@pytest.mark.asyncio
async def test_sandbox_manager_pooling():
    """Test that SandboxManager manages sessions and pool lifecycle."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create_pool:
        mock_pool = MockDockerPoolManager()
        mock_create_pool.return_value = mock_pool

        manager = SandboxManager()
        await manager.initialize_pool()

        # Get session twice for same conv_id -> should be same object
        session1 = manager.get_session("conv_1")
        session2 = manager.get_session("conv_1")
        assert session1 is session2

        # Get different session for different conv_id
        session3 = manager.get_session("conv_2")
        assert session1 is not session3

        await manager.shutdown()
        mock_pool.close.assert_called_once()

@pytest.mark.asyncio
async def test_sandbox_manager_error():
    """Test that SandboxManager raises error if not initialized."""
    manager = SandboxManager()
    with pytest.raises(SandboxError, match="SandboxManager not initialized"):
        manager.get_session("any_conv")


@pytest.mark.asyncio
async def test_sandbox_pool_receives_default_resource_limits(monkeypatch):
    """Default sandbox limits are translated to docker runtime_configs and passed
    to the pool manager so warm containers are capped at creation time."""
    from canvas_server import sandbox
    from canvas_server.config import settings

    monkeypatch.setattr(settings, "sandbox_mem_limit", "512m")
    monkeypatch.setattr(settings, "sandbox_cpus", 1.0)

    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create_pool:
        mock_create_pool.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

    _, kwargs = mock_create_pool.call_args
    runtime_configs = kwargs["runtime_configs"]
    assert runtime_configs["mem_limit"] == "512m"
    assert runtime_configs["nano_cpus"] == 1_000_000_000


@pytest.mark.asyncio
async def test_sandbox_pool_resource_limits_env_override(monkeypatch):
    """Sandbox limits can be overridden via settings, flowing through to
    runtime_configs with the CPU value converted to nano_cpus."""
    from canvas_server.config import settings

    monkeypatch.setattr(settings, "sandbox_mem_limit", "1g")
    monkeypatch.setattr(settings, "sandbox_cpus", 2.5)

    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create_pool:
        mock_create_pool.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

    _, kwargs = mock_create_pool.call_args
    runtime_configs = kwargs["runtime_configs"]
    assert runtime_configs["mem_limit"] == "1g"
    assert runtime_configs["nano_cpus"] == 2_500_000_000


@pytest.mark.asyncio
async def test_sandbox_pool_resource_limits_disabled(monkeypatch):
    """When both limit settings are unset, no resource keys are emitted so the
    pool falls back to the library default (uncapped) behavior."""
    from canvas_server.config import settings

    monkeypatch.setattr(settings, "sandbox_mem_limit", "")
    monkeypatch.setattr(settings, "sandbox_cpus", 0.0)

    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create_pool:
        mock_create_pool.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

    _, kwargs = mock_create_pool.call_args
    assert kwargs["runtime_configs"] == {}

from unittest.mock import MagicMock, patch

import pytest

from canvas_server.sandbox import SandboxError, SandboxManager


class MockDockerPoolManager(MagicMock):
    pass

@pytest.mark.asyncio
async def test_sandbox_session_lifecycle():
    """Test that a SandboxSession can run code and be closed."""
    with patch("canvas_server.sandbox.create_pool_manager") as mock_create_pool:
        mock_pool = MockDockerPoolManager()
        mock_pool.image = "mock-image"
        mock_container = MagicMock()
        mock_container.container_id = "mock-container-id"
        mock_pool.acquire.return_value = mock_container
        mock_create_pool.return_value = mock_pool

        manager = SandboxManager()
        await manager.initialize_pool()

        session = manager.get_session("test_conv")

        # Mock the session.run return value
        # llm-sandbox returns a result object with .stdout
        mock_result = MagicMock()
        mock_result.stdout = '{"result": 42}'

        from llm_sandbox.pool.session import PooledSandboxSession
        mock_backend = MagicMock()
        mock_backend.run.return_value = mock_result

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
    with patch("canvas_server.sandbox.create_pool_manager") as mock_create_pool:
        mock_pool = MockDockerPoolManager()
        mock_pool.image = "mock-image"
        mock_container = MagicMock()
        mock_container.container_id = "mock-container-id"
        mock_pool.acquire.return_value = mock_container
        mock_create_pool.return_value = mock_pool

        manager = SandboxManager()
        await manager.initialize_pool()
        session = manager.get_session("test_conv")

        mock_result = MagicMock()
        mock_result.stdout = "Success"

        from llm_sandbox.pool.session import PooledSandboxSession
        mock_backend = MagicMock()
        mock_backend.run.return_value = mock_result

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
    with patch("canvas_server.sandbox.create_pool_manager") as mock_create_pool:
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

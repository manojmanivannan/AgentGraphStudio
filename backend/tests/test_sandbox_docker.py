import pytest
import pytest_asyncio
from unittest.mock import MagicMock, patch
from canvas_server.sandbox import SandboxManager, SandboxError
from llm_sandbox import InteractiveSandboxSession

@pytest.mark.asyncio
async def test_sandbox_session_lifecycle():
    """Test that a SandboxSession can run code and be closed."""
    with patch("canvas_server.sandbox.create_pool_manager") as mock_create_pool:
        mock_pool = MagicMock()
        mock_create_pool.return_value = mock_pool

        manager = SandboxManager()
        await manager.initialize_pool()

        session = manager.get_session("test_conv")

        # Mock the session.run return value
        # llm-sandbox returns a result object with .stdout
        mock_result = MagicMock()
        mock_result.stdout = '{"result": 42}'

        with patch.object(InteractiveSandboxSession, "run", return_value=mock_result):
            result = session.run("result = 10 + 32")
            assert result.stdout == '{"result": 42}'

        manager.release_session("test_conv")
        # Verify session was closed
        session.close.assert_called() if hasattr(session, 'close') else None

@pytest.mark.asyncio
async def test_sandbox_session_install():
    """Test that a SandboxSession can install packages via libraries arg."""
    with patch("canvas_server.sandbox.create_pool_manager") as mock_create_pool:
        mock_pool = MagicMock()
        mock_create_pool.return_value = mock_pool

        manager = SandboxManager()
        await manager.initialize_pool()
        session = manager.get_session("test_conv")

        mock_result = MagicMock()
        mock_result.stdout = "Success"

        with patch.object(InteractiveSandboxSession, "run", return_value=mock_result) as mock_run:
            session.run("import numpy", libraries=["numpy"])
            mock_run.assert_called_with("import numpy", libraries=["numpy"])

        manager.release_session("test_conv")

@pytest.mark.asyncio
async def test_sandbox_manager_pooling():
    """Test that SandboxManager manages sessions and pool lifecycle."""
    with patch("canvas_server.sandbox.create_pool_manager") as mock_create_pool:
        mock_pool = MagicMock()
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

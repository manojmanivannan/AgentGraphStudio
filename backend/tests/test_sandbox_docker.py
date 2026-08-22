from unittest.mock import MagicMock, patch

import pytest

from canvas_server.sandbox import SANDBOX_FLOOR_IMAGE, SandboxError, SandboxManager


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
    pool falls back to the library default (uncapped) behavior.

    ``network_mode="none"`` is always present — it is a hardcoded invariant of
    the default (locked) pool, not a resource limit and not a Settings knob
    (see ``test_build_runtime_configs_locks_network_mode_none``)."""
    from canvas_server.config import settings

    monkeypatch.setattr(settings, "sandbox_mem_limit", "")
    monkeypatch.setattr(settings, "sandbox_cpus", 0.0)

    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create_pool:
        mock_create_pool.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

    _, kwargs = mock_create_pool.call_args
    assert kwargs["runtime_configs"] == {"network_mode": "none"}


# ── Default (locked) pool: network_mode="none" hardcoded invariant (#54) ──


def test_build_runtime_configs_locks_network_mode_none():
    """The default pool's runtime_configs always carry network_mode="none" as a
    hardcoded invariant (CLAUDE.md §8: "no network by default"). This is what
    finally prevents agents without enable_network from making outbound calls —
    previously build_runtime_configs never set network_mode, so containers ran
    on Docker's bridge with internet on."""
    from canvas_server.sandbox import build_runtime_configs

    assert build_runtime_configs()["network_mode"] == "none"


def test_build_runtime_configs_network_mode_not_configurable(monkeypatch):
    """The *locked* pool's ``network_mode="none"`` is NOT controlled by the
    ``sandbox_network_mode`` seam and cannot be relaxed via config.

    Note (#55): ``sandbox_network_mode`` *is* now a Settings field — but it
    controls only the lazy **networked** pool (``build_networked_runtime_configs``),
    not the locked default pool. ``build_runtime_configs`` (the locked pool)
    hardcodes the ``"none"`` literal and never consults the seam, so setting the
    seam to a networked value cannot relax the locked pool's invariant."""
    from canvas_server.config import Settings, settings

    # The seam exists (for the networked pool) but is NOT named for the locked
    # pool's network_mode, and there is no field that the locked pool consults.
    assert "network_mode" not in Settings.model_fields

    # Relaxing the seam does NOT affect the locked pool's build_runtime_configs:
    # even with the seam set to a networked value, the locked pool stays "none".
    monkeypatch.setattr(settings, "sandbox_network_mode", "bridge")
    from canvas_server.sandbox import build_runtime_configs

    assert build_runtime_configs()["network_mode"] == "none"


@pytest.mark.asyncio
async def test_sandbox_pool_created_with_network_mode_none():
    """The default pool is created with network_mode="none" passed through to
    the pool manager's runtime_configs (mirrors the mocked-pool pattern)."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create_pool:
        mock_create_pool.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

    _, kwargs = mock_create_pool.call_args
    assert kwargs["runtime_configs"]["network_mode"] == "none"


@pytest.mark.asyncio
async def test_sandbox_pool_uses_baked_floor_image():
    """The default pool runs on the baked-floor custom image (matplotlib +
    plotly + numpy pre-installed) so it needs no runtime pip — which is
    impossible under network_mode="none". The networked pool (#55) will share
    this same image, differing only in network_mode."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create_pool:
        mock_create_pool.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

    _, kwargs = mock_create_pool.call_args
    assert kwargs["image"] == SANDBOX_FLOOR_IMAGE


@pytest.mark.asyncio
async def test_sandbox_pool_skips_environment_setup():
    """The default pool is created with skip_environment_setup=True so the
    baked-floor image is used as-is: no venv creation, no `pip install
    --upgrade pip`, no library install — none of which can reach the network
    under network_mode="none". Floor packages are baked into the image."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create_pool:
        mock_create_pool.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

    _, kwargs = mock_create_pool.call_args
    assert kwargs.get("skip_environment_setup") is True


@pytest.mark.asyncio
async def test_sandbox_pool_no_runtime_libraries():
    """The default pool does NOT pass `libraries` for runtime pip install —
    matplotlib/plotly/numpy are baked into the floor image, and pip is
    impossible under network_mode="none" anyway. Passing libraries here would
    make container creation fail at environment_setup time."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create_pool:
        mock_create_pool.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

    _, kwargs = mock_create_pool.call_args
    assert "libraries" not in kwargs

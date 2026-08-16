"""Mocked-pool tests for the two-pool sandbox architecture + per-turn session
release (#55).

Mirrors ``test_sandbox_docker.py`` (mocked pool manager — no real Docker). Verifies:
- The networked pool is lazy (``min=0``/``max=2``), with ``network_mode`` as a
  config seam defaulting to ``"bridge"``.
- Both pools share the baked-floor image (differ only in ``network_mode``).
- The session cache is keyed by ``(conversation_id, network_pool)`` — the same
  conversation across the two pools returns *distinct* sessions; a non-networked
  worker never reuses a networked worker's session.
- ``get_session`` gains a defaulted ``network_pool`` so the coding ticket's
  ``get_session(conversation_id, enable_plotting=False)`` call stays compatible.
- On acquire the session's workdir + plot dir are cleaned (no cross-conversation
  file/plot leakage).
- Release-strategy asymmetry: networked-pool release *destroys* the container;
  locked-pool release *reuses* it.
- Pool exhaustion → bounded wait → observation string, never raises (shared
  helper, mirrors ``run_code``).
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from llm_sandbox.pool import PoolConfig, PoolExhaustedError

from canvas_server.sandbox import (
    NETWORK_POOL_DEFAULT,
    NETWORK_POOL_NETWORKED,
    NETWORKED_POOL_MAX,
    NETWORKED_POOL_MIN,
    SANDBOX_BUSY_OBSERVATION,
    SANDBOX_FLOOR_IMAGE,
    SandboxManager,
    bounded_acquire,
    build_networked_runtime_configs,
    create_named_pool_manager,
)


class MockDockerPoolManager(MagicMock):
    pass


# ── Config seam: network_mode for the networked pool defaults to "bridge" ──


def test_networked_pool_network_mode_seam_defaults_to_bridge():
    """A new ``Settings`` field ``sandbox_network_mode`` defaults to ``"bridge"``
    (Docker's bridge — internet egress). This is a config seam so a future custom
    egress network + proxy can be swapped with no code change. The locked default
    pool's ``network_mode="none"`` is a *hardcoded invariant*, not this knob."""
    from canvas_server.config import Settings

    assert Settings().sandbox_network_mode == "bridge"
    assert "sandbox_network_mode" in Settings.model_fields


def test_networked_pool_network_mode_seam_env_override(monkeypatch):
    """The seam is configurable via the environment (e.g. a custom egress network
    name), unlike the locked pool's hardcoded ``"none"``."""
    from canvas_server.config import Settings

    monkeypatch.setenv("SANDBOX_NETWORK_MODE", "custom-egress-net")
    assert Settings().sandbox_network_mode == "custom-egress-net"


def test_build_networked_runtime_configs_uses_seam(monkeypatch):
    """``build_networked_runtime_configs`` reads the seam for ``network_mode`` —
    not the locked pool's hardcoded ``"none"``."""
    from canvas_server.config import settings

    monkeypatch.setattr(settings, "sandbox_network_mode", "custom-egress-net")
    monkeypatch.setattr(settings, "sandbox_mem_limit", "")
    monkeypatch.setattr(settings, "sandbox_cpus", 0.0)
    assert build_networked_runtime_configs()["network_mode"] == "custom-egress-net"


# ── Lazy networked pool: no idle cost; grows on demand ──


@pytest.mark.asyncio
async def test_networked_pool_is_lazy_until_first_networked_session():
    """``initialize_pool`` only warms the *locked* pool. The networked pool is
    created lazily on the first ``network_pool="networked"`` request — no idle
    cost (``min_pool_size=0``)."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create:
        mock_create.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

        # Only the locked pool exists after initialize_pool.
        assert mock_create.call_count == 1
        assert manager._networked_pool is None

        # First networked request lazily creates the networked pool.
        manager.get_session("conv-1", network_pool=NETWORK_POOL_NETWORKED)
        assert mock_create.call_count == 2
        assert manager._networked_pool is not None

        # A second networked request reuses the same networked pool (no third).
        manager.get_session("conv-2", network_pool=NETWORK_POOL_NETWORKED)
        assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_networked_pool_config_invariants():
    """When the networked pool is lazily created it uses ``min=0`` / ``max=2``
    (no idle cost), the baked-floor image (shared with the locked pool),
    ``skip_environment_setup=True``, ``network_mode`` from the seam, and
    ``destroy_on_release=True``."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create:
        mock_create.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

        manager.get_session("conv-1", network_pool=NETWORK_POOL_NETWORKED)

        # First call = locked pool, second = networked pool.
        networked_call = mock_create.call_args_list[1]
        config: PoolConfig = networked_call.kwargs["config"]
        assert config.min_pool_size == NETWORKED_POOL_MIN == 0
        assert config.max_pool_size == NETWORKED_POOL_MAX == 2
        assert networked_call.kwargs["image"] == SANDBOX_FLOOR_IMAGE
        assert networked_call.kwargs.get("skip_environment_setup") is True
        assert networked_call.kwargs.get("destroy_on_release") is True
        assert (
            networked_call.kwargs["runtime_configs"]["network_mode"]
            == "bridge"
        )


@pytest.mark.asyncio
async def test_locked_pool_does_not_destroy_on_release():
    """The locked (default) pool is created with ``destroy_on_release=False`` so
    its warm baked-floor containers are reused (not destroyed) on release."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create:
        mock_create.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

        locked_call = mock_create.call_args
        assert locked_call.kwargs.get("destroy_on_release") is False


# ── Session cache keyed by (conversation_id, network_pool) ──


@pytest.mark.asyncio
async def test_get_session_distinct_across_pools_for_same_conversation():
    """The same conversation served by the two pools returns *distinct* sessions
    — a non-networked worker never reuses a networked worker's session (and
    vice versa)."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create:
        mock_create.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

        s_default = manager.get_session("conv-1", network_pool=NETWORK_POOL_DEFAULT)
        s_networked = manager.get_session(
            "conv-1", network_pool=NETWORK_POOL_NETWORKED
        )
        assert s_default is not s_networked


@pytest.mark.asyncio
async def test_get_session_same_pool_reused_for_same_conversation():
    """Within one pool, the same conversation reuses its session (cache hit)."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create:
        mock_create.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

        a = manager.get_session("conv-1", network_pool=NETWORK_POOL_DEFAULT)
        b = manager.get_session("conv-1", network_pool=NETWORK_POOL_DEFAULT)
        assert a is b


@pytest.mark.asyncio
async def test_get_session_default_pool_compatible_without_network_pool():
    """``network_pool`` is a *defaulted* parameter: the coding ticket's existing
    ``get_session(conversation_id, enable_plotting=False)`` call stays
    compatible and routes to the locked (default) pool."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create:
        mock_create.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

        # No network_pool argument — routes to the default (locked) pool.
        session = manager.get_session("conv-1", enable_plotting=False)
        assert session is manager.get_session(
            "conv-1", network_pool=NETWORK_POOL_DEFAULT, enable_plotting=False
        )


# ── Clean-on-acquire: workdir + plot dir cleaned so no cross-conversation leak ──


@pytest.mark.asyncio
async def test_clean_on_acquire_clears_workdir_and_plot_dir():
    """On acquire (``__enter__``) the session cleans its workdir (``/sandbox``)
    and plot dir (``/tmp/sandbox_plots``) so a stale file/plot from a prior
    conversation cannot leak into a new one."""
    from llm_sandbox.pool.session import PooledSandboxSession

    mock_pool = MockDockerPoolManager()
    mock_container = MagicMock()
    mock_container.container_id = "c-id"
    mock_pool.acquire.return_value = mock_container

    manager = SandboxManager()
    manager._locked_pool = mock_pool
    manager._initialized = True

    session = manager.get_session("conv-1", enable_plotting=False)

    mock_backend = MagicMock()
    with patch.object(
        PooledSandboxSession, "_create_backend_session", return_value=mock_backend
    ), session:
        pass

    # The clean command ran on enter and touched both the workdir and plot dir.
    clean_calls = [
        c for c in mock_backend.execute_command.call_args_list
        if "rm -rf" in (c.args[0] if c.args else "")
    ]
    assert clean_calls, "expected a clean-on-acquire command"
    cmd = clean_calls[0].args[0]
    assert "/sandbox" in cmd
    assert "/tmp/sandbox_plots" in cmd


@pytest.mark.asyncio
async def test_container_held_for_turn_acquired_and_cleaned_once():
    """Per-turn container pinning (#55 central criterion): the container is
    acquired and the workdir cleaned **once** per turn, then held across every
    ``run_code``/``generate_plot`` call in that turn — so intra-turn file
    handoffs survive (a file written by run_code is not wiped before
    generate_plot reads it) and no other conversation can grab the container
    between calls. Released once at turn end by ``close()``."""
    from llm_sandbox.pool.session import PooledSandboxSession

    mock_pool = MockDockerPoolManager()
    mock_container = MagicMock()
    mock_container.container_id = "c-id"
    mock_pool.acquire.return_value = mock_container

    manager = SandboxManager()
    manager._locked_pool = mock_pool
    manager._initialized = True

    session = manager.get_session("conv-1", enable_plotting=False)

    mock_backend = MagicMock()
    mock_result = MagicMock()
    mock_result.stdout = "ok"
    mock_backend.run.return_value = mock_result
    mock_backend.language_handler.run_with_artifacts.return_value = (mock_result, [])

    with patch.object(
        PooledSandboxSession, "_create_backend_session", return_value=mock_backend
    ):
        # Simulate a turn: two sequential tool calls (e.g. run_code then
        # generate_plot), each using `with session:`.
        for _ in range(2):
            with session:
                session.run("print('hi')")

        # The container was acquired from the pool exactly once (held for the
        # turn — the second `with session:` reused it, did not re-acquire).
        mock_pool.acquire.assert_called_once()

        # The clean command ran exactly once (on the first acquire). A second
        # clean would wipe files written by the first call and break intra-turn
        # handoff.
        clean_calls = [
            c for c in mock_backend.execute_command.call_args_list
            if "rm -rf" in (c.args[0] if c.args else "")
        ]
        assert len(clean_calls) == 1

        # The per-call __exit__ did NOT release the container (held for the
        # turn). It is released only by close() — the per-turn release hook.
        mock_backend.close.assert_not_called()

        # Turn end: the per-turn release hook closes the session, releasing the
        # held container exactly once.
        session.close()
        mock_backend.close.assert_called_once()


# ── Release-strategy asymmetry: destroy (networked) vs reuse (locked) ──


def _make_pool_manager(*, destroy_on_release: bool) -> object:
    """Construct a NamedDockerPoolManager with a mock docker client (no real
    Docker) so its ``release`` semantics can be unit-tested in isolation."""
    return create_named_pool_manager(
        config=PoolConfig(max_pool_size=NETWORKED_POOL_MAX, min_pool_size=0),
        lang="python",
        client=MagicMock(),
        image=SANDBOX_FLOOR_IMAGE,
        skip_environment_setup=True,
        runtime_configs={"network_mode": "bridge"},
        destroy_on_release=destroy_on_release,
    )


def test_networked_pool_release_destroys_container():
    """Releasing a container to the networked pool *destroys* it — no
    cross-conversation package bleed (a networked worker's pip installs do not
    leak to the next conversation)."""
    manager = _make_pool_manager(destroy_on_release=True)
    manager._destroy_container_impl = MagicMock()
    container = MagicMock()

    manager.release(container)

    manager._destroy_container_impl.assert_called_once()
    manager.close()


def test_locked_pool_release_reuses_container():
    """Releasing a container to the locked pool returns it to the pool (warm
    baked-floor reuse) — it is NOT destroyed."""
    manager = _make_pool_manager(destroy_on_release=False)
    manager._destroy_container_impl = MagicMock()
    container = MagicMock()
    container.is_expired.return_value = False

    manager.release(container)

    manager._destroy_container_impl.assert_not_called()
    container.mark_idle.assert_called_once()
    manager.close()


# ── Per-turn release hook fires at turn end ──


@pytest.mark.asyncio
async def test_per_turn_release_fires_at_turn_end():
    """The coordinator's ``run()`` finally block releases the conversation's
    sandbox session(s) at the end of each turn — today ``release_session`` only
    runs at shutdown."""
    import uuid
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from canvas_server.conversation_run_coordinator import (
        ConversationRunCoordinator,
    )

    conversation_id = uuid.uuid4()
    canvas_id = uuid.uuid4()

    class _FakeConvRepo:
        def __init__(self, conversation):
            self.conversation = conversation
            self.update_name = AsyncMock()

        async def get_or_404(self, cid):
            return self.conversation

    class _FakeCanvasRepo:
        async def get_or_404(self, cid):
            return SimpleNamespace(id=canvas_id)

    class _FakeSession:
        def __init__(self):
            self.commit = AsyncMock()

    conversation = SimpleNamespace(
        id=conversation_id,
        canvas_id=canvas_id,
        name="Existing Conversation",
        messages=[object()],
    )
    runner = SimpleNamespace(
        generate_conversation_title=AsyncMock(),
        run=AsyncMock(),
        _conversation=SimpleNamespace(persist_message=AsyncMock()),
    )

    mock_sandbox = MagicMock()
    mock_sandbox.release_session = MagicMock()
    with patch(
        "canvas_server.conversation_run_coordinator.get_sandbox",
        new=AsyncMock(return_value=mock_sandbox),
    ):
        coordinator = ConversationRunCoordinator(
            session=_FakeSession(),
            conversation_repo=_FakeConvRepo(conversation),
            canvas_repo=_FakeCanvasRepo(),
            runner_factory=AsyncMock(return_value=runner),
        )
        await coordinator.run(
            conversation_id=conversation_id,
            user_prompt="hi",
            send_event=AsyncMock(),
        )

    mock_sandbox.release_session.assert_called_once_with(str(conversation_id))


@pytest.mark.asyncio
async def test_release_session_releases_all_pools_for_conversation():
    """``release_session`` releases every session for a conversation across both
    pools (the per-turn hook must not leave a networked session pinned)."""
    with patch("canvas_server.sandbox.create_named_pool_manager") as mock_create:
        mock_create.return_value = MockDockerPoolManager()
        manager = SandboxManager()
        await manager.initialize_pool()

        s_default = manager.get_session("conv-1", network_pool=NETWORK_POOL_DEFAULT)
        s_networked = manager.get_session(
            "conv-1", network_pool=NETWORK_POOL_NETWORKED
        )
        s_default.close = MagicMock()
        s_networked.close = MagicMock()

        manager.release_session("conv-1")

        s_default.close.assert_called_once()
        s_networked.close.assert_called_once()
        assert ("conv-1", NETWORK_POOL_DEFAULT) not in manager._active_sessions
        assert ("conv-1", NETWORK_POOL_NETWORKED) not in manager._active_sessions
        # Other conversations are untouched.
        manager.get_session("conv-2", network_pool=NETWORK_POOL_DEFAULT)
        assert ("conv-2", NETWORK_POOL_DEFAULT) in manager._active_sessions


# ── Bounded wait on pool exhaustion never raises (shared helper) ──


@pytest.mark.asyncio
async def test_bounded_acquire_pool_exhausted_returns_busy_observation():
    """A ``PoolExhaustedError`` on acquire surfaces as the 'busy' observation —
    never raised. Shared with ``run_code`` / future ``pip_install``."""
    session = MagicMock()
    session.__enter__.side_effect = PoolExhaustedError("no containers")

    result = await bounded_acquire(session, timeout=1.0)

    assert result.acquired is False
    assert result.observation == SANDBOX_BUSY_OBSERVATION


@pytest.mark.asyncio
async def test_bounded_acquire_timeout_returns_busy_observation(monkeypatch):
    """An acquire that blocks longer than the bound returns the 'busy'
    observation (never raises), and the orphaned acquire is released so it
    cannot leak a container into the shared pool."""
    session = MagicMock()

    def slow_enter():
        import time

        time.sleep(0.3)

    session.__enter__.side_effect = slow_enter

    result = await asyncio.wait_for(
        bounded_acquire(session, timeout=0.1), timeout=5
    )

    assert result.acquired is False
    assert result.observation == SANDBOX_BUSY_OBSERVATION
    # Let the orphaned acquire + its cleanup finish.
    await asyncio.sleep(0.4)
    session.__exit__.assert_called_once()


@pytest.mark.asyncio
async def test_bounded_acquire_success_returns_acquired():
    """A promptly-acquired session reports acquired=True with no observation."""
    session = MagicMock()

    result = await bounded_acquire(session, timeout=1.0)

    assert result.acquired is True
    assert result.observation is None

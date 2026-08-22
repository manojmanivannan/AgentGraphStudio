"""Docker-based Sandbox — managed session pool for isolated Python execution.

This module uses the `llm-sandbox` library to provide OS-level isolation, native Python performance,
and session-based state persistence.

Architecture:
- SandboxManager: A singleton managing an `llm_sandbox` PoolManager and
  mapping conversations to InteractiveSandboxSessions.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any

from llm_sandbox import ArtifactSandboxSession
from llm_sandbox.pool import PoolConfig
from llm_sandbox.pool.base import ContainerPoolManager
from llm_sandbox.pool.exceptions import PoolExhaustedError

from canvas_server.config import settings

logger = logging.getLogger("canvas_server.sandbox")

# Configuration constants
POOL_SIZE_MAX = 2
POOL_SIZE_MIN = 1
DEFAULT_LANG = "python"

# --- Two-pool architecture (#55) ---
# The locked (default) pool: warm, ``network_mode="none"`` (hardcoded invariant),
# reused on release. The networked pool: lazy (no idle cost), grows on demand,
# ``network_mode`` from the ``sandbox_network_mode`` seam, *destroyed* on release
# so a networked worker's pip installs / files never bleed across conversations.
NETWORKED_POOL_MAX = 2
NETWORKED_POOL_MIN = 0

# ``network_pool`` selector values passed to ``get_session``. The session cache
# is keyed by ``(conversation_id, network_pool)`` so a non-networked worker's
# session is never reused for a networked worker (and vice versa).
NETWORK_POOL_DEFAULT = "default"  # locked, network_mode="none"
NETWORK_POOL_NETWORKED = "networked"  # lazy, network_mode=settings.sandbox_network_mode

# Workdir and plot dir inside every sandbox container. Cleaned on acquire
# (CanvasSandboxSession.__enter__) so a stale file/plot from a prior
# conversation cannot leak into a new one (#55, Story 24).
SANDBOX_WORKDIR = "/sandbox"
SANDBOX_PLOT_DIR = "/tmp/sandbox_plots"

# Bounded wait for a free sandbox container before reporting the sandbox busy.
# Shared by run_code / future pip_install (#56) via ``bounded_acquire`` — a
# per-call bound layered on top of the shared pool's own (longer) acquisition
# timeout, so a saturated pool surfaces as a 'busy' observation quickly instead
# of stalling the agent's turn. Pool exhaustion never raises out of the helper.
SANDBOX_ACQUIRE_TIMEOUT = 10  # seconds
SANDBOX_BUSY_OBSERVATION = (
    "Code sandbox busy — all sandboxes are currently in use. "
    "Try again shortly, or simplify your request."
)

# Baked-floor custom Docker image shared by both sandbox pools (the locked
# default pool here, and the lazy networked pool in #55). matplotlib + plotly +
# numpy are pre-installed (along with a `/sandbox/.sandbox-venv` that inherits
# them via --system-site-packages) so the locked pool needs *no* runtime pip —
# which is impossible under ``network_mode="none"`` anyway. The two pools differ
# only in ``network_mode``. Built from ``sandbox/Dockerfile`` (see
# ``make sandbox-image``).
SANDBOX_FLOOR_IMAGE = "agentbuilder-sandbox-floor:latest"

# Hardcoded invariant of the default (locked) pool: the container is created
# with no network stack, so agents without ``enable_network`` cannot make
# outbound calls (CLAUDE.md §8: "no network by default"). This is deliberately
# NOT a ``Settings`` knob and cannot be relaxed via config — see
# ``build_runtime_configs``.
LOCKED_POOL_NETWORK_MODE = "none"


class SandboxError(Exception):
    """Base exception for sandbox operations."""

    pass


def _resource_configs() -> dict[str, Any]:
    """Shared docker resource limits for both sandbox pools.

    Translates the ``sandbox_mem_limit`` / ``sandbox_cpus`` settings into the
    docker-py keys ``llm-sandbox`` spreads into ``containers.create(...)``:
    ``mem_limit`` (string) and ``nano_cpus`` (int nanocpus). When a setting is
    unset (empty / 0.0) the corresponding key is omitted so the pool falls back
    to the library default (uncapped) behavior. The two pools share these
    limits and the baked-floor image — they differ only in ``network_mode``,
    which each ``build_*_runtime_configs`` appends.
    """
    configs: dict[str, Any] = {}
    if settings.sandbox_mem_limit:
        configs["mem_limit"] = settings.sandbox_mem_limit
    if settings.sandbox_cpus:
        configs["nano_cpus"] = int(settings.sandbox_cpus * 1_000_000_000)
    return configs


def build_runtime_configs() -> dict[str, Any]:
    """Build docker ``runtime_configs`` for the default (locked) sandbox pool.

    ``network_mode`` is set to ``"none"`` as a **hardcoded invariant** — not a
    ``Settings`` knob, not overridable. This finally honours CLAUDE.md §8's "no
    network by default" contract: agents without ``enable_network`` run in this
    pool and cannot make outbound network calls. Previously this never set
    ``network_mode``, so containers ran on Docker's bridge with internet on.
    The networked pool (#55) is a separate pool with its own runtime configs
    (see ``build_networked_runtime_configs``).
    """
    # Hardcoded security invariant — set last so nothing can override it.
    configs = _resource_configs()
    configs["network_mode"] = LOCKED_POOL_NETWORK_MODE
    return configs


def build_networked_runtime_configs() -> dict[str, Any]:
    """Build docker ``runtime_configs`` for the lazy networked sandbox pool (#55).

    Shares the baked-floor image and resource limits with the locked pool
    (differing only in ``network_mode``), but ``network_mode`` comes from the
    ``sandbox_network_mode`` **config seam** (defaulting to ``"bridge"`` —
    internet egress) rather than the locked pool's hardcoded ``"none"``. This is
    the seam a future custom egress network + proxy swaps with no code change.
    """
    # Config seam — NOT a hardcoded invariant (unlike the locked pool).
    configs = _resource_configs()
    configs["network_mode"] = settings.sandbox_network_mode
    return configs


def create_named_pool_manager(
    config: PoolConfig,
    lang: str,
    *,
    destroy_on_release: bool = False,
    **kwargs: Any,
) -> ContainerPoolManager:
    """Create a Docker pool manager that assigns unique names to containers.

    Args:
        config: Pool size / exhaustion configuration.
        lang: Sandbox language.
        destroy_on_release: When True, ``release()`` *destroys* the container
            instead of returning it to the pool — used by the networked pool so
            a networked worker's pip installs / files never bleed across
            conversations (#55, Stories 25/26). When False (the locked pool),
            the warm baked-floor container is reused.
        **kwargs: Forwarded to ``DockerPoolManager`` (``backend``, ``image``,
            ``skip_environment_setup``, ``runtime_configs``, ``client``, ...).
    """
    import uuid

    from llm_sandbox.docker import SandboxDockerSession
    from llm_sandbox.pool.docker_pool import DockerPoolManager

    class NamedDockerPoolManager(DockerPoolManager):
        def __init__(self, *args: Any, **kw: Any) -> None:
            super().__init__(*args, **kw)
            self._destroy_on_release = destroy_on_release

        def _create_session_for_container(self) -> Any:
            configs = dict(self.runtime_configs)
            configs["name"] = f"sandbox-{uuid.uuid4().hex}"
            return SandboxDockerSession(
                client=self.client,
                image=self.image,
                dockerfile=self.dockerfile,
                lang=str(self.lang),
                runtime_configs=configs,
                **self.session_kwargs,
            )

        def release(self, container: Any) -> None:  # type: ignore[override]
            """Release a container back to the pool.

            For the networked pool (``destroy_on_release=True``) the container is
            *destroyed* — no cross-conversation package/file bleed, and because
            ``min_pool_size=0`` the pool simply shrinks (a subsequent acquire
            grows it again on demand). For the locked pool the base behaviour
            (return-to-pool, warm reuse) applies unchanged.

            Note: this reaches into base-class internals (``_condition``,
            ``_closed``, ``_destroy_container``) because ``release`` is the only
            override hook the library offers for release strategy. If
            ``DockerPoolManager``'s release internals change, this must be
            revisited.
            """
            if not self._destroy_on_release:
                return super().release(container)
            with self._condition:
                if self._closed:
                    self._destroy_container(container)
                    return
                self._destroy_container(container)
                # Wake any waiters so they can scale the pool back up on demand.
                self._condition.notify()

    return NamedDockerPoolManager(config=config, lang=lang, **kwargs)


class CanvasSandboxSession(ArtifactSandboxSession):
    """Pooled sandbox session that holds its container for one whole turn.

    This realizes the per-turn container pinning the spec requires (#55): a
    session's container is acquired **once** at the start of the turn (lazily,
    on the first ``__enter__``) and held across every ``run_code`` /
    ``generate_plot`` call in that turn, so intra-turn file handoffs (``run_code``
    writes a file → ``generate_plot`` reads it) work on the *same* container and
    no other conversation can grab it between calls. The container is released
    once, at turn end, by :meth:`close` — which the per-turn release hook
    (``ConversationRunCoordinator.run()``'s ``finally`` block) calls via
    ``SandboxManager.release_session``.

    On the single acquire-per-turn the workdir (``/sandbox``) and plot dir
    (``/tmp/sandbox_plots``) are cleaned, so a stale file/plot from a *prior
    conversation* cannot leak into a new one (Story 24). Cleaning once-per-turn
    (not once-per-call) is what preserves intra-turn handoffs while still
    preventing cross-conversation leakage. The locked pool reuses warm
    containers across conversations, so without this clean a leftover file would
    resurface; the networked pool destroys its container on release, making the
    clean a harmless idempotent no-op on a fresh container.

    ``__enter__`` is idempotent within a turn (a second ``with session:`` block
    reuses the held container and does *not* re-clean). ``__exit__`` is a no-op —
    it deliberately does **not** release the container; only :meth:`close` does.
    The acquire is serialized per-session so the pooled session's single
    container slot cannot be overwritten by a concurrent acquire (which would
    leak a container).
    """

    _CLEAN_CMD = (
        f'rm -rf {SANDBOX_WORKDIR}/* {SANDBOX_PLOT_DIR}/* 2>/dev/null; '
        f'mkdir -p {SANDBOX_PLOT_DIR}; '
        f'echo 0 > {SANDBOX_PLOT_DIR}/.counter 2>/dev/null; true'
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # Whether this session currently holds a container for the turn.
        self._canvas_held = False
        # Serializes the per-turn acquire so only one container is acquired per
        # session per turn (the pooled session has a single container slot).
        self._canvas_lock = threading.Lock()

    def __enter__(self) -> CanvasSandboxSession:  # type: ignore[override]
        with self._canvas_lock:
            if self._canvas_held:
                # Already holding a container for this turn — reuse it, no
                # re-acquire, no re-clean (preserves intra-turn handoff files).
                return self
            # Acquire the container (may block on pool.acquire). Held under the
            # lock so a concurrent enter waits rather than acquiring a second
            # container that would overwrite and leak this session's single slot.
            super().__enter__()
            self._canvas_held = True
        # Clean once per turn, outside the lock (container already acquired).
        try:
            self.execute_command(f'sh -c "{self._CLEAN_CMD}"')
        except Exception as e:  # noqa: BLE001 - clean must never break a run
            logger.warning("Failed to clean sandbox workdir on acquire: %s", e)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:  # type: ignore[override]
        # Deliberately do NOT release the container here. It is held for the
        # duration of the turn so intra-turn run_code -> generate_plot file
        # handoffs work on the same container, and so no other conversation can
        # acquire it between this turn's calls. The container is released once,
        # at turn end, by close() (the per-turn release hook).
        return None

    def close(self) -> None:  # type: ignore[override]
        """Per-turn release: release the held container back to the pool.

        Called by ``SandboxManager.release_session`` at turn end (the per-turn
        release hook) and at shutdown. Idempotent: a session that never acquired
        a container (e.g. was created but never used) releases nothing. Releasing
        a networked-pool container destroys it (no cross-conversation package
        bleed); releasing a locked-pool container returns it to the warm pool.
        """
        with self._canvas_lock:
            if not self._canvas_held:
                return
            self._canvas_held = False
        try:
            super().__exit__(None, None, None)
        except Exception as e:  # noqa: BLE001 - never let cleanup raise out
            logger.warning("Error releasing sandbox session: %s", e)


@dataclass
class AcquireResult:
    """Outcome of a bounded sandbox-container acquire (``bounded_acquire``)."""

    acquired: bool
    observation: str | None


async def bounded_acquire(
    session: Any, *, timeout: float = SANDBOX_ACQUIRE_TIMEOUT
) -> AcquireResult:
    """Bound the wait for a free sandbox container; never raise on exhaustion.

    Wraps the pooled session's blocking ``__enter__`` (``pool.acquire()``) in a
    bounded wait. If a container is free within ``timeout`` seconds, returns
    ``acquired=True``. If the pool is exhausted (``PoolExhaustedError``) or the
    wait exceeds the bound, returns ``acquired=False`` plus the 'busy'
    observation string — never raises. This is the shared helper that
    ``run_code`` and the future ``pip_install`` (#56) use so a saturated pool
    surfaces as an observation the agent can reason over instead of stalling or
    crashing the turn.

    On timeout the underlying acquire keeps running in a worker thread and may
    still grab a container; ``_release_orphaned_acquire`` awaits it and exits
    the session so that container is returned to the shared pool instead of
    leaking.
    """
    enter_task = asyncio.ensure_future(asyncio.to_thread(session.__enter__))
    try:
        await asyncio.wait_for(asyncio.shield(enter_task), timeout=timeout)
    except TimeoutError:
        asyncio.create_task(_release_orphaned_acquire(enter_task, session))
        return AcquireResult(acquired=False, observation=SANDBOX_BUSY_OBSERVATION)
    except PoolExhaustedError:
        return AcquireResult(acquired=False, observation=SANDBOX_BUSY_OBSERVATION)
    return AcquireResult(acquired=True, observation=None)


async def _release_orphaned_acquire(enter_task: asyncio.Future, session: Any) -> None:
    """Clean up after a bounded-acquire timeout.

    When the bounded acquire wait times out, the underlying ``__enter__`` keeps
    running in a worker thread and may still acquire a container. This awaits
    that orphaned acquire. For a hold-for-turn :class:`CanvasSandboxSession`,
    ``__exit__`` is a no-op by design: an orphan that *does* acquire simply
    becomes that turn's held container (used by the agent's next call and
    released at turn end by :meth:`CanvasSandboxSession.close`), so there is no
    leak. If the orphaned acquire raised (e.g. ``PoolExhaustedError``), there is
    nothing to release.
    """
    try:
        await enter_task
        await asyncio.to_thread(session.__exit__, None, None, None)
    except Exception:  # noqa: BLE001 - acquire raised (e.g. PoolExhaustedError): nothing to release
        logger.debug("Orphaned sandbox acquire raised; nothing to release")


class SandboxManager:
    """Singleton that manages the two-pool sandbox architecture (#55).

    Holds two ``llm-sandbox`` pool managers and maps ``(conversation_id,
    network_pool)`` pairs to :class:`CanvasSandboxSession` instances:

    - **Locked (default) pool** — eager/warm, ``network_mode="none"`` (hardcoded
      invariant), reused on release. Serves non-networked workers + plotting +
      author-tool compilation. Initialised by ``initialize_pool`` at startup.
    - **Networked pool** — lazy (``min=0``/``max=2``, no idle cost), grows on
      demand, ``network_mode`` from the ``sandbox_network_mode`` seam, *destroyed*
      on release (no cross-conversation package bleed). Created on the first
      ``network_pool="networked"`` request.

    The session cache is keyed by ``(conversation_id, network_pool)`` so a
    non-networked worker's session is never reused for a networked worker (and
    vice versa). Sessions are released at the end of each turn via the per-turn
    release hook (``release_session`` from
    ``ConversationRunCoordinator.run()``'s ``finally`` block), correcting the old
    behaviour where sessions persisted app-lifetime (file/plot leakage across
    conversations).
    """

    _instance: SandboxManager | None = None

    def __init__(self):
        self._locked_pool: ContainerPoolManager | None = None
        self._networked_pool: ContainerPoolManager | None = None
        self._active_sessions: dict[tuple[str, str], ArtifactSandboxSession] = {}
        self._initialized = False

    @classmethod
    def get(cls) -> SandboxManager:
        """Retrieves the singleton instance of the SandboxManager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize_pool(self) -> None:
        """Pre-warm the *locked* (default) container pool using llm-sandbox.

        The networked pool is **not** warmed here — it is lazy (``min=0``) and
        created on the first ``network_pool="networked"`` request (no idle cost).

        Must be called during application startup (e.g. FastAPI lifespan) so
        the locked pool's containers are ready before the first non-networked
        execution request, minimizing latency.

        Raises:
            SandboxError: If Docker is unavailable or the pool fails to build.
        """
        if self._initialized:
            return

        logger.info(f"Initializing locked sandbox pool (max={POOL_SIZE_MAX}, min={POOL_SIZE_MIN})...")
        try:
            # The locked pool: network_mode="none" (a hardcoded invariant in
            # build_runtime_configs) + the baked-floor image
            # (matplotlib/plotly/numpy pre-installed). skip_environment_setup
            # means no venv/pip runs at container creation — required because
            # pip is impossible under network_mode="none". Floor packages are
            # baked into the image (and its /sandbox/.sandbox-venv) instead.
            # destroy_on_release=False: warm baked-floor containers are reused.
            self._locked_pool = create_named_pool_manager(
                config=PoolConfig(
                    max_pool_size=POOL_SIZE_MAX, min_pool_size=POOL_SIZE_MIN
                ),
                lang=DEFAULT_LANG,
                backend="docker",
                image=SANDBOX_FLOOR_IMAGE,
                skip_environment_setup=True,
                runtime_configs=build_runtime_configs(),
                destroy_on_release=False,
            )
            self._initialized = True
            logger.info("Locked sandbox pool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize sandbox pool: {e}")
            raise SandboxError(f"Sandbox initialization failed: {e}") from e

    def _ensure_networked_pool(self) -> ContainerPoolManager:
        """Lazily create the networked pool on first use (no idle cost).

        ``min_pool_size=0`` means nothing is pre-warmed; the pool only grows on
        demand up to ``max_pool_size=2``. ``destroy_on_release=True`` destroys
        containers on release so a networked worker's pip installs / files never
        bleed across conversations. ``network_mode`` comes from the seam.
        """
        if self._networked_pool is None:
            logger.info(
                "Creating lazy networked sandbox pool "
                f"(max={NETWORKED_POOL_MAX}, min={NETWORKED_POOL_MIN})..."
            )
            self._networked_pool = create_named_pool_manager(
                config=PoolConfig(
                    max_pool_size=NETWORKED_POOL_MAX, min_pool_size=NETWORKED_POOL_MIN
                ),
                lang=DEFAULT_LANG,
                backend="docker",
                image=SANDBOX_FLOOR_IMAGE,
                skip_environment_setup=True,
                runtime_configs=build_networked_runtime_configs(),
                destroy_on_release=True,
            )
        return self._networked_pool

    def _pool_for(self, network_pool: str) -> ContainerPoolManager:
        """Select the pool for a ``network_pool`` selector value.

        The networked pool is created lazily; the locked pool must have been
        initialised (non-networked workers require the warm locked pool).
        """
        if network_pool == NETWORK_POOL_NETWORKED:
            return self._ensure_networked_pool()
        # Default / locked pool.
        if self._locked_pool is None:
            raise SandboxError(
                "SandboxManager not initialized. Call initialize_pool() first."
            )
        return self._locked_pool

    def get_session(
        self,
        conversation_id: str,
        enable_plotting: bool = True,
        network_pool: str = NETWORK_POOL_DEFAULT,
    ) -> ArtifactSandboxSession:
        """Retrieves or creates an interactive session for the given conversation.

        The session cache is keyed by ``(conversation_id, network_pool)``: the
        same conversation served by the two pools returns *distinct* sessions,
        so a non-networked worker never reuses a networked worker's session (and
        vice versa). Within one pool, the same conversation reuses its session
        so intra-turn ``run_code``→``generate_plot`` file handoffs work.

        ``network_pool`` is a **defaulted** parameter (``"default"``) so the
        coding ticket's existing ``get_session(conversation_id,
        enable_plotting=False)`` call sites stay compatible; the coding
        ``CodeProvider`` passes ``network_pool="default"`` explicitly.

        On acquire (``__enter__``) the session's workdir and plot dir are
        cleaned (see :class:`CanvasSandboxSession`) so no cross-conversation
        file/plot leakage occurs.

        Args:
            conversation_id (str): The unique ID of the conversation.
            enable_plotting (bool, optional): Whether to capture plotting artifacts.
            network_pool (str, optional): ``"default"`` (locked, no network) or
                ``"networked"`` (lazy, internet egress). Defaults to ``"default"``.

        Returns:
            ArtifactSandboxSession: The configured sandbox session.

        Raises:
            SandboxError: If the locked pool has not been initialised and a
                default-pool session is requested.
        """
        key = (conversation_id, network_pool)
        if key in self._active_sessions:
            session = self._active_sessions[key]
            session.enable_plotting = enable_plotting
            return session

        pool = self._pool_for(network_pool)

        logger.info(
            "Creating new sandbox session for conversation=%s pool=%s",
            conversation_id,
            network_pool,
        )
        # CanvasSandboxSession cleans the workdir + plot dir on each acquire.
        session = CanvasSandboxSession(
            lang=DEFAULT_LANG,
            pool=pool,
            verbose=True,
            enable_plotting=enable_plotting,
        )

        self._active_sessions[key] = session
        return session

    def release_session(self, conversation_id: str) -> None:
        """Release every session for a conversation across both pools.

        This is the per-turn release hook (called from
        ``ConversationRunCoordinator.run()``'s ``finally`` block at the end of
        each turn) as well as the shutdown path. Releasing a networked session
        destroys its container (no cross-conversation package bleed); releasing
        a locked session returns its warm container to the pool for reuse.

        Args:
            conversation_id (str): The ID of the conversation to release.
        """
        for key in list(self._active_sessions):
            cid, _network_pool = key
            if cid != conversation_id:
                continue
            session = self._active_sessions.pop(key, None)
            if session:
                try:
                    session.close()
                    logger.info(
                        "Session for conversation %s (pool=%s) released",
                        cid,
                        _network_pool,
                    )
                except Exception as e:
                    logger.warning(
                        "Error releasing session %s (pool=%s): %s",
                        cid,
                        _network_pool,
                        e,
                    )

    async def shutdown(self) -> None:
        """Cleanup all active sessions and both pool managers."""
        logger.info("Shutting down SandboxManager...")

        # Close active sessions (across both pools).
        if self._active_sessions:
            logger.info(f"Closing {len(self._active_sessions)} active sessions...")
            for key in list(self._active_sessions.keys()):
                cid, _ = key
                self.release_session(cid)

        for name, pool in (
            ("locked", self._locked_pool),
            ("networked", self._networked_pool),
        ):
            if pool:
                try:
                    logger.info("Closing %s pool manager...", name)
                    pool.close()
                    logger.info("%s pool manager closed successfully", name)
                except Exception as e:
                    logger.error(f"Error closing {name} pool manager: {e}")

        self._initialized = False


async def get_sandbox() -> SandboxManager:
    """Helper to get the SandboxManager singleton."""
    return SandboxManager.get()

"""Docker-based Sandbox — managed session pool for isolated Python execution.

This module uses the `llm-sandbox` library to provide OS-level isolation, native Python performance,
and session-based state persistence.

Architecture:
- SandboxManager: A singleton managing an `llm_sandbox` PoolManager and
  mapping conversations to InteractiveSandboxSessions.
"""

from __future__ import annotations

import logging
from typing import Any

from llm_sandbox import ArtifactSandboxSession
from llm_sandbox.pool import PoolConfig
from llm_sandbox.pool.base import ContainerPoolManager

from canvas_server.config import settings

logger = logging.getLogger("canvas_server.sandbox")

# Configuration constants
POOL_SIZE_MAX = 2
POOL_SIZE_MIN = 1
DEFAULT_LANG = "python"

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


def build_runtime_configs() -> dict[str, Any]:
    """Build docker ``runtime_configs`` for the default (locked) sandbox pool.

    Translates the ``sandbox_mem_limit`` / ``sandbox_cpus`` settings into the
    docker-py keys ``llm-sandbox`` spreads into ``containers.create(...)``:
    ``mem_limit`` (string) and ``nano_cpus`` (int nanocpus). When a setting is
    unset (empty / 0.0) the corresponding key is omitted so the pool falls back
    to the library default (uncapped) behavior.

    ``network_mode`` is set to ``"none"`` as a **hardcoded invariant** — not a
    ``Settings`` knob, not overridable. This finally honours CLAUDE.md §8's "no
    network by default" contract: agents without ``enable_network`` run in this
    pool and cannot make outbound network calls. Previously this never set
    ``network_mode``, so containers ran on Docker's bridge with internet on.
    The networked pool (#55) is a separate pool with its own runtime configs.
    """
    configs: dict[str, Any] = {}
    if settings.sandbox_mem_limit:
        configs["mem_limit"] = settings.sandbox_mem_limit
    if settings.sandbox_cpus:
        configs["nano_cpus"] = int(settings.sandbox_cpus * 1_000_000_000)
    # Hardcoded security invariant — set last so nothing can override it.
    configs["network_mode"] = LOCKED_POOL_NETWORK_MODE
    return configs


def create_named_pool_manager(
    config: PoolConfig,
    lang: str,
    **kwargs: Any,
) -> ContainerPoolManager:
    """Create a Docker pool manager that assigns unique names to containers."""
    import uuid

    from llm_sandbox.docker import SandboxDockerSession
    from llm_sandbox.pool.docker_pool import DockerPoolManager

    class NamedDockerPoolManager(DockerPoolManager):
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

    return NamedDockerPoolManager(config=config, lang=lang, **kwargs)


class SandboxManager:
    """Singleton that manages a pool of warm Docker containers.

    Uses `llm-sandbox` to maintain a pool of `ArtifactSandboxSession` instances.
    Each session is mapped to a conversation ID to ensure that consecutive tool
    executions within the same conversation share the same container and
    filesystem state (e.g., variables, installed packages, generated plots).

    Attributes:
        _pool_manager: The underlying `llm-sandbox` PoolManager.
        _active_sessions (dict): Mapping of conversation_id to active sessions.
    """

    _instance: SandboxManager | None = None

    def __init__(self):
        self._pool_manager = None
        self._active_sessions: dict[str, ArtifactSandboxSession] = {}
        self._initialized = False

    @classmethod
    def get(cls) -> SandboxManager:
        """Retrieves the singleton instance of the SandboxManager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize_pool(self) -> None:
        """Pre-warms the container pool using llm-sandbox.

        Must be called during application startup (e.g. FastAPI lifespan)
        to ensure containers are ready before the first execution request,
        minimizing latency.

        Raises:
            SandboxError: If Docker is unavailable or the pool fails to build.
        """
        if self._initialized:
            return

        logger.info(f"Initializing llm-sandbox pool (max={POOL_SIZE_MAX}, min={POOL_SIZE_MIN})...")
        try:
            # The default pool is the LOCKED pool: network_mode="none" (a
            # hardcoded invariant in build_runtime_configs) + the baked-floor
            # image (matplotlib/plotly/numpy pre-installed). skip_environment_setup
            # means no venv/pip runs at container creation — which is required
            # because pip is impossible under network_mode="none". Floor packages
            # are baked into the image (and its /sandbox/.sandbox-venv) instead.
            self._pool_manager = create_named_pool_manager(
                config=PoolConfig(max_pool_size=POOL_SIZE_MAX, min_pool_size=POOL_SIZE_MIN),
                lang=DEFAULT_LANG,
                backend="docker",
                image=SANDBOX_FLOOR_IMAGE,
                skip_environment_setup=True,
                runtime_configs=build_runtime_configs(),
            )
            self._initialized = True
            logger.info("Sandbox pool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize sandbox pool: {e}")
            raise SandboxError(f"Sandbox initialization failed: {e}") from e

    def get_session(self, conversation_id: str, enable_plotting: bool = True) -> ArtifactSandboxSession:
        """Retrieves or creates an interactive session for the given conversation.

        If a session already exists for this `conversation_id`, it is reused,
        ensuring that in-memory Python variables from previous tool calls
        remain available.

        Args:
            conversation_id (str): The unique ID of the conversation.
            enable_plotting (bool, optional): Whether to capture plotting artifacts.

        Returns:
            ArtifactSandboxSession: The configured sandbox session.

        Raises:
            SandboxError: If the manager has not been initialized.
        """
        if conversation_id in self._active_sessions:
            session = self._active_sessions[conversation_id]
            session.enable_plotting = enable_plotting
            return session

        if not self._pool_manager:
            raise SandboxError("SandboxManager not initialized. Call initialize_pool() first.")

        logger.info(f"Creating new interactive session for conversation: {conversation_id}")
        # InteractiveSandboxSession maintains state across multiple .run() calls
        session = ArtifactSandboxSession(
            lang=DEFAULT_LANG,
            pool=self._pool_manager,
            verbose=True,
            enable_plotting=enable_plotting,
        )

        self._active_sessions[conversation_id] = session
        return session

    def release_session(self, conversation_id: str) -> None:
        """Releases a session and returns the underlying container to the pool.

        Args:
            conversation_id (str): The ID of the conversation to release.
        """
        session = self._active_sessions.pop(conversation_id, None)
        if session:
            try:
                session.close()
                logger.info(f"Session for conversation {conversation_id} released")
            except Exception as e:
                logger.warning(f"Error releasing session {conversation_id}: {e}")

    async def shutdown(self) -> None:
        """Cleanup all active sessions and the pool manager."""
        logger.info("Shutting down SandboxManager...")

        # Close active sessions
        if self._active_sessions:
            logger.info(f"Closing {len(self._active_sessions)} active sessions...")
            for conversation_id in list(self._active_sessions.keys()):
                self.release_session(conversation_id)

        if self._pool_manager:
            try:
                logger.info("Closing pool manager...")
                self._pool_manager.close()
                logger.info("Pool manager closed successfully")
            except Exception as e:
                logger.error(f"Error closing pool manager: {e}")

        self._initialized = False


async def get_sandbox() -> SandboxManager:
    """Helper to get the SandboxManager singleton."""
    return SandboxManager.get()

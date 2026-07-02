"""Docker-based Sandbox — managed session pool for isolated Python execution.

This module uses the `llm-sandbox` library to provide OS-level isolation, native Python performance,
and session-based state persistence.

Architecture:
- SandboxManager: A singleton managing an `llm_sandbox` PoolManager and
  mapping conversations to InteractiveSandboxSessions.
"""

from __future__ import annotations

import logging

from llm_sandbox import ArtifactSandboxSession
from llm_sandbox.pool import PoolConfig, create_pool_manager

logger = logging.getLogger("canvas_server.sandbox")

# Configuration constants
POOL_SIZE_MAX = 2
POOL_SIZE_MIN = 1
DEFAULT_LANG = "python"


class SandboxError(Exception):
    """Base exception for sandbox operations."""

    pass


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

        logger.info(
            f"Initializing llm-sandbox pool (max={POOL_SIZE_MAX}, min={POOL_SIZE_MIN})..."
        )
        try:
            # We pre-install matplotlib and plotly so that plotting tools
            # work instantly without requiring inline pip installs.
            self._pool_manager = create_pool_manager(
                backend="docker",
                config=PoolConfig(
                    max_pool_size=POOL_SIZE_MAX, min_pool_size=POOL_SIZE_MIN
                ),
                lang=DEFAULT_LANG,
                libraries=["matplotlib", "plotly"]
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
            raise SandboxError(
                "SandboxManager not initialized. Call initialize_pool() first."
            )

        logger.info(
            f"Creating new interactive session for conversation: {conversation_id}"
        )
        # ArtifactSandboxSession maintains state across multiple .run() calls
        # because the underlying Docker container is kept alive.
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

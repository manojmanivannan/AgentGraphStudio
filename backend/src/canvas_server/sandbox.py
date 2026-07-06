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

logger = logging.getLogger("canvas_server.sandbox")

# Configuration constants
POOL_SIZE_MAX = 2
POOL_SIZE_MIN = 1
DEFAULT_LANG = "python"


class SandboxError(Exception):
    """Base exception for sandbox operations."""

    pass


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
    """
    Singleton that manages a pool of warm Docker containers
    and maps conversations to specific interactive sessions.
    """

    _instance: SandboxManager | None = None

    def __init__(self):
        self._pool_manager = None
        self._active_sessions: dict[str, ArtifactSandboxSession] = {}
        self._initialized = False

    @classmethod
    def get(cls) -> SandboxManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize_pool(self) -> None:
        """Pre-warm the container pool using llm-sandbox."""
        if self._initialized:
            return

        logger.info(f"Initializing llm-sandbox pool (max={POOL_SIZE_MAX}, min={POOL_SIZE_MIN})...")
        try:
            self._pool_manager = create_named_pool_manager(
                config=PoolConfig(max_pool_size=POOL_SIZE_MAX, min_pool_size=POOL_SIZE_MIN),
                lang=DEFAULT_LANG,
                libraries=["matplotlib", "plotly"],
            )
            self._initialized = True
            logger.info("Sandbox pool initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize sandbox pool: {e}")
            raise SandboxError(f"Sandbox initialization failed: {e}") from e

    def get_session(self, conversation_id: str, enable_plotting: bool = True) -> ArtifactSandboxSession:
        """
        Get an existing interactive session for the conversation,
        or create a new one from the pool.
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

        # try:
        #     session.open()
        # except Exception as e:
        #     logger.error(f"Failed to open sandbox session for {conversation_id}: {e}")
        #     raise SandboxError(f"Could not open sandbox session: {e}")

        self._active_sessions[conversation_id] = session
        return session

    def release_session(self, conversation_id: str) -> None:
        """
        Release a session and return the container to the pool.
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

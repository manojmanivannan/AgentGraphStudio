"""MemoryManager — shared mem0 lifecycle and per-agent MemoryProvider creation."""

from __future__ import annotations

import logging
import uuid

from canvas_server.memory_config import build_mem0_config
from canvas_server.memory_provider import MemoryProvider

logger = logging.getLogger("canvas_server.runner.memory")


class MemoryManager:
    """Manages the shared ``mem0.Memory`` instance and per-agent providers.

    A single shared memory instance avoids local-qdrant file-locking issues.
    Isolation is achieved via ``user_id = f"agent_{agent_node.id}"``.

    State owned by this service:
      ``_memory_providers`` — ``{agent_id: MemoryProvider}`` for agents with memory enabled
      ``_shared_memory`` — the single ``mem0.Memory`` singleton shared across all MemoryManager instances
    """

    _shared_memory = None

    def __init__(self):
        self._memory_providers: dict[uuid.UUID, MemoryProvider] = {}
        self.initialization_error: Exception | None = None

    @staticmethod
    def needs_memory(agent_node) -> bool:
        return getattr(agent_node, "enable_memory", False)

    def _init_shared_memory(self):
        """Create (once) the shared mem0 Memory instance."""
        if self.__class__._shared_memory is None:
            from mem0 import Memory

            config = build_mem0_config()
            shared = Memory.from_config(config)
            # Dry-run search to verify embedder & vector-db connection (skipped for tests using fake/mock Memory objects)
            if hasattr(shared, "search"):
                shared.search("test_connection", filters={"user_id": "test_init_connection"}, limit=1)
            self.__class__._shared_memory = shared
        return self.__class__._shared_memory

    def build_provider(self, agent_node) -> MemoryProvider | None:
        """Return a ``MemoryProvider`` for *agent_node*, or ``None`` if memory
        is disabled. If initialization fails, returns a MemoryProvider that raises the error when called."""
        if not self.needs_memory(agent_node):
            return None
        if agent_node.id in self._memory_providers:
            return self._memory_providers[agent_node.id]
        if self.initialization_error is not None:
            user_id = f"agent_{agent_node.id}"
            provider = MemoryProvider(user_id=user_id, memory=None, initialization_error=self.initialization_error)
            self._memory_providers[agent_node.id] = provider
            return provider
        try:
            memory = self._init_shared_memory()
            user_id = f"agent_{agent_node.id}"
            provider = MemoryProvider(user_id=user_id, memory=memory)
            self._memory_providers[agent_node.id] = provider
            return provider
        except ImportError as e:
            logger.warning(
                "mem0 not installed; memory disabled for agent %s", agent_node.name
            )
            self.initialization_error = e
            provider = MemoryProvider(user_id=f"agent_{agent_node.id}", memory=None, initialization_error=e)
            self._memory_providers[agent_node.id] = provider
            return provider
        except Exception as e:
            err_msg = str(e)
            if "<html" in err_msg.lower() or "<!doctype" in err_msg.lower():
                err_msg = "Database/API returned an HTML error page. Please check that your server URL, credentials, and settings are correct."
            elif len(err_msg) > 300:
                err_msg = err_msg[:300] + "..."
            
            logger.warning(
                "Failed to initialize mem0 for agent %s: %s", agent_node.name, err_msg
            )
            exc = RuntimeError(err_msg)
            self.initialization_error = exc
            provider = MemoryProvider(user_id=f"agent_{agent_node.id}", memory=None, initialization_error=exc)
            self._memory_providers[agent_node.id] = provider
            return provider

    def get_provider(self, agent_id: uuid.UUID) -> MemoryProvider | None:
        return self._memory_providers.get(agent_id)

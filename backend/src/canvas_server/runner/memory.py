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

    @staticmethod
    def needs_memory(agent_node) -> bool:
        return getattr(agent_node, "enable_memory", False)

    def _init_shared_memory(self):
        """Create (once) the shared mem0 Memory instance."""
        if self.__class__._shared_memory is None:
            from mem0 import Memory

            config = build_mem0_config()
            self.__class__._shared_memory = Memory.from_config(config)
        return self.__class__._shared_memory

    def build_provider(self, agent_node) -> MemoryProvider | None:
        """Return a ``MemoryProvider`` for *agent_node*, or ``None`` if memory
        is disabled or initialisation fails."""
        if not self.needs_memory(agent_node):
            return None
        try:
            memory = self._init_shared_memory()
            user_id = f"agent_{agent_node.id}"
            provider = MemoryProvider(user_id=user_id, memory=memory)
            self._memory_providers[agent_node.id] = provider
            return provider
        except ImportError:
            logger.warning(
                "mem0 not installed; memory disabled for agent %s", agent_node.name
            )
            return None
        except Exception as e:
            logger.warning(
                "Failed to initialize mem0 for agent %s: %s", agent_node.name, e
            )
            return None

    def get_provider(self, agent_id: uuid.UUID) -> MemoryProvider | None:
        return self._memory_providers.get(agent_id)

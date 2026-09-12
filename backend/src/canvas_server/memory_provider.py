"""Per-agent memory provider wrapping mem0 as DSPy-compatible tool functions."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mem0 import Memory

logger = logging.getLogger(__name__)


class MemoryProvider:
    """Wraps mem0.Memory and exposes add/search/get_all as callable tool functions.

    Each agent gets its own MemoryProvider instance and user_id so memories
    are scoped per agent. All providers share a single mem0 Memory (and thus a
    single QdrantClient) to avoid local-qdrant file-locking issues.

    Invariant: ``memory`` is ``None`` only when ``initialization_error`` is set
    (see ``MemoryManager.build_provider``); the tool methods raise that stored
    error before ever touching ``memory``.
    """

    def __init__(
        self,
        user_id: str,
        memory: Memory | None,
        initialization_error: Exception | None = None,
    ) -> None:
        self.user_id: str = user_id
        self.memory: Memory | None = memory
        self.initialization_error: Exception | None = initialization_error

    async def store_memory(self, content: str) -> str:
        """
        Persist a fact, preference, or detail from the current conversation into long-term memory
        so it can be recalled later. Call this whenever you learn something about the user
        or the task without the user explicitly requesting.
        """
        if self.initialization_error is not None:
            raise self.initialization_error
        try:
            assert self.memory is not None
            self.memory.add(content, user_id=self.user_id, infer=False)
            return f"Stored memory: {content}"
        except Exception as e:
            logger.exception("store_memory failed")
            return f"Error storing memory: {e}"

    async def search_memories(self, query: str) -> str:
        """Search stored memories semantically by meaning. Returns up to 5 matching memories.
        Use this when you need to recall past information the user shared."""
        if self.initialization_error is not None:
            raise self.initialization_error
        try:
            assert self.memory is not None
            results = self.memory.search(
                query, filters={"user_id": self.user_id}, top_k=5
            )
            if not results.get("results"):
                return "No relevant memories found."
            lines = []
            for i, r in enumerate(results["results"], 1):
                lines.append(f"{i}. {r.get('memory', '')}")
            return "\n".join(lines)
        except Exception as e:
            logger.exception("search_memories failed")
            return f"Error searching memories: {e}"

    async def get_all_memories(self) -> str:
        """Retrieve every stored memory for this agent. Use this to see everything you remember."""
        if self.initialization_error is not None:
            raise self.initialization_error
        try:
            assert self.memory is not None
            results = self.memory.get_all(filters={"user_id": self.user_id})
            if not results.get("results"):
                return "No memories stored."
            lines = []
            for i, r in enumerate(results["results"], 1):
                lines.append(f"{i}. {r.get('memory', '')}")
            return "\n".join(lines)
        except Exception as e:
            logger.exception("get_all_memories failed")
            return f"Error retrieving memories: {e}"

"""Per-agent memory provider wrapping mem0 as DSPy-compatible tool functions."""

import logging

logger = logging.getLogger(__name__)


class MemoryProvider:
    """Wraps mem0.Memory and exposes add/search/get_all as callable tool functions.

    Each agent gets its own MemoryProvider instance and user_id so memories
    are scoped per agent. All providers share a single mem0 Memory (and thus a
    single QdrantClient) to avoid local-qdrant file-locking issues.
    """

    def __init__(self, user_id: str, memory):
        self.user_id = user_id
        self.memory = memory

    async def store_memory(self, content: str) -> str:
        """Persist a fact, preference, or detail from the current conversation into long-term memory so it can be recalled later. Call this after you learn something about the user or the task."""
        try:
            self.memory.add(content, user_id=self.user_id, infer=False)
            return f"Stored memory: {content}"
        except Exception as e:
            logger.exception("store_memory failed")
            return f"Error storing memory: {e}"

    async def search_memories(self, query: str) -> str:
        """Search stored memories semantically by meaning. Returns up to 5 matching memories. Use this when you need to recall past information the user shared."""
        try:
            results = self.memory.search(query, filters={"user_id": self.user_id}, limit=5)
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
        try:
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

import sys
import types
import uuid

from canvas_server.memory_provider import MemoryProvider
from canvas_server.runner.memory import MemoryManager


class DummyAgent:
    def __init__(self, id_: uuid.UUID):
        self.id = id_
        self.name = "Dummy"
        self.enable_memory = True


class FakeMemory:
    instances = 0

    @classmethod
    def from_config(cls, config):
        cls.instances += 1
        return f"fake-memory-{cls.instances}"


def test_memory_manager_reuses_shared_mem0(monkeypatch):
    fake_mem0 = types.SimpleNamespace(Memory=FakeMemory)
    monkeypatch.setitem(sys.modules, "mem0", fake_mem0)

    manager1 = MemoryManager()
    manager2 = MemoryManager()

    mem1 = manager1._init_shared_memory()
    mem2 = manager2._init_shared_memory()

    assert mem1 == mem2
    assert FakeMemory.instances == 1


class RecordingMemory:
    """Records search kwargs so tests can assert which parameters reach mem0."""

    def __init__(self):
        self.search_calls: list[tuple[str, dict]] = []

    def search(self, query, **kwargs):
        self.search_calls.append((query, kwargs))
        return {"results": []}


async def test_search_memories_limits_results_to_five():
    # mem0.Memory.search takes ``top_k`` (default 20); ``limit`` is silently
    # swallowed by **kwargs, so the documented "up to 5 memories" cap must be
    # passed as top_k.
    mem = RecordingMemory()
    provider = MemoryProvider(user_id="agent-1", memory=mem)

    await provider.search_memories("hello")

    assert mem.search_calls[0][1].get("top_k") == 5

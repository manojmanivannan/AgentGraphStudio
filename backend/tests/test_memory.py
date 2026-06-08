import sys
import types
import uuid

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

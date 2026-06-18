import uuid
from unittest.mock import AsyncMock, patch

from canvas_server.runner.tool_registry import ToolRegistry


class FakeToolNode:
    def __init__(self, name: str, code: str, dependencies: list[str] | None = None):
        self.id = uuid.uuid4()
        self.name = name
        self.code = code
        self.dependencies = dependencies or []


async def test_compile_all_forwards_runtime_session_id():
    registry = ToolRegistry()
    node = FakeToolNode("my_tool", "def my_tool():\n    return 'ok'", ["requests"])

    compiled_fn = AsyncMock()

    with patch(
        "canvas_server.runner.tool_registry.compile_tool_from_code",
        new=AsyncMock(return_value=compiled_fn),
    ) as compile_mock:
        await registry.compile_all([node], runtime_session_id="conversation-42")

    compile_mock.assert_awaited_once_with(
        "my_tool",
        "def my_tool():\n    return 'ok'",
        dependencies=["requests"],
        runtime_session_id="conversation-42",
    )

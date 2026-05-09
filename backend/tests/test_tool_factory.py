import pytest
from beeai_framework.tools.tool import StringToolOutput
from canvas_server.tool_factory import compile_tool_from_code
from canvas_server.exceptions import ToolCompilationError


class TestCompileToolFromCode:
    async def test_simple_function(self):
        code = "def greet(name: str) -> str:\n    return f'Hello {name}'"
        tool = await compile_tool_from_code("greeter", code)
        assert tool.name == "greeter"
        assert tool.description != ""

    async def test_function_with_docstring(self):
        code = 'def add(a: int, b: int) -> int:\n    """Adds two numbers."""\n    return a + b'
        tool = await compile_tool_from_code("adder", code)
        assert tool.name == "adder"
        assert "Adds two numbers" in tool.description

    async def test_empty_code_raises(self):
        with pytest.raises(ToolCompilationError):
            await compile_tool_from_code("empty", "")

    async def test_no_function_raises(self):
        with pytest.raises(ToolCompilationError):
            await compile_tool_from_code("noval", "x = 42")

    async def test_syntax_error_raises(self):
        with pytest.raises(ToolCompilationError):
            await compile_tool_from_code("broken", "def broken(:")

    async def test_picks_first_callable(self):
        code = "def first():\n    return 1\ndef second():\n    return 2"
        tool = await compile_tool_from_code("picker", code)
        assert tool.name == "picker"

    async def test_skips_builtins(self):
        code = "import math\ndef calc(x): return math.sqrt(x)"
        tool = await compile_tool_from_code("calc", code)
        assert tool.name == "calc"

    async def test_tool_execution(self):
        code = "def multiply(a: int, b: int) -> int:\n    return a * b"
        tool = await compile_tool_from_code("mult", code)
        result = await tool.run({"a": 3, "b": 4})
        assert isinstance(result, StringToolOutput)
        assert "12" in result.get_text_content()

    async def test_logs_on_call(self, caplog):
        import logging
        caplog.set_level(logging.DEBUG)
        code = "def echo(msg: str) -> str:\n    return msg"
        tool = await compile_tool_from_code("echoer", code)
        result = await tool.run({"msg": "hi"})
        assert isinstance(result, StringToolOutput)
        assert "hi" in result.get_text_content()
        assert any("echoer" in r.message for r in caplog.records)

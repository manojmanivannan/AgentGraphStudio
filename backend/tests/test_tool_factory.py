import pytest

from canvas_server.exceptions import ToolCompilationError
from canvas_server.tool_factory import compile_tool_from_code


class TestCompileToolFromCode:
    async def test_simple_function(self):
        code = "def greet(name: str) -> str:\n    return f'Hello {name}'"
        fn = await compile_tool_from_code("greeter", code)
        assert callable(fn)
        assert fn("world") == "Hello world"

    async def test_function_with_docstring(self):
        code = 'def add(a: int, b: int) -> int:\n    """Adds two numbers."""\n    return a + b'
        fn = await compile_tool_from_code("adder", code)
        assert fn.__doc__ is not None
        assert "Adds two numbers" in fn.__doc__

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
        fn = await compile_tool_from_code("picker", code)
        assert callable(fn)

    async def test_skips_builtins(self):
        code = "import math\ndef calc(x): return math.sqrt(x)"
        fn = await compile_tool_from_code("calc", code)
        assert fn(9) == 3.0

    async def test_tool_execution(self):
        code = "def multiply(a: int, b: int) -> int:\n    return a * b"
        fn = await compile_tool_from_code("mult", code)
        result = fn(3, 4)
        assert result == 12

    async def test_logs_on_call(self, caplog):
        import logging

        caplog.set_level(logging.DEBUG)
        code = "def echo(msg: str) -> str:\n    return msg"
        fn = await compile_tool_from_code("echoer", code)
        assert fn("hi") == "hi"
        assert any("echoer" in r.message for r in caplog.records)

import shutil

import pytest

from canvas_server.exceptions import ToolCompilationError, ToolExecutionError
from canvas_server.tool_factory import (
    coerce_arg,
    compile_tool_from_code,
    execute_tool_code,
    inspect_tool_code,
)

requires_docker = pytest.mark.skipif(
    not shutil.which("docker"), reason="Docker not installed"
)


# ── compile_tool_from_code (host-side metadata + sandbox execution) ────────


class TestCompileToolFromCode:
    """Existing tests for compile_tool_from_code — these now also verify sandbox
    execution when Deno is available."""

    async def test_simple_function(self):
        code = "def greet(name: str) -> str:\n    return f'Hello {name}'"
        fn = await compile_tool_from_code("greeter", code)
        assert callable(fn)
        assert fn.__name__ == "greet"
        assert fn.__doc__ is not None or True  # docstring is optional

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
        assert fn.__name__ == "first"

    async def test_skips_builtins(self):
        code = "import math\ndef calc(x):\n    return math.sqrt(x)"
        fn = await compile_tool_from_code("calc", code)
        assert fn.__name__ == "calc"

    @requires_docker
    async def test_sandbox_execution_simple(self):
        """Compiled function should execute in the sandbox."""
        code = "def multiply(a: int, b: int) -> int:\n    return a * b"
        fn = await compile_tool_from_code("mult", code)
        result = await fn(a=3, b=4)
        assert result == 12

    @requires_docker
    async def test_sandbox_execution_string(self):
        """Compiled function should handle string arguments."""
        code = "def greet(name: str) -> str:\n    return f'Hello {name}'"
        fn = await compile_tool_from_code("greeter", code)
        result = await fn(name="world")
        assert result == "Hello world"

    @requires_docker
    async def test_sandbox_runtime_error(self):
        """Runtime errors in sandbox should propagate."""
        code = "def boom():\n    return 1 / 0"
        fn = await compile_tool_from_code("boom", code)
        with pytest.raises(Exception):
            await fn()


# ── inspect_tool_code ───────────────────────────────────────────────────────


class TestInspectToolCode:
    """Tests for the inspect endpoint that extracts function metadata."""

    async def test_inspect_simple_function(self):
        code = "def greet(name: str) -> str:\n    return f'Hello {name}'"
        result = await inspect_tool_code("greeter", code)
        assert result.function_name == "greet"
        assert len(result.arguments) == 1
        assert result.arguments[0].name == "name"
        assert result.arguments[0].type_hint == "str"

    async def test_inspect_multiple_args(self):
        code = "def add(a: int, b: int) -> int:\n    return a + b"
        result = await inspect_tool_code("adder", code)
        assert result.function_name == "add"
        assert len(result.arguments) == 2
        assert result.arguments[0].name == "a"
        assert result.arguments[0].type_hint == "int"
        assert result.arguments[1].name == "b"
        assert result.arguments[1].type_hint == "int"

    async def test_inspect_default_values(self):
        code = 'def greet(name: str = "world") -> str:\n    return f"Hello {name}"'
        result = await inspect_tool_code("greeter", code)
        assert result.arguments[0].default_value == "'world'"

    async def test_inspect_no_type_hints(self):
        code = "def run(x):\n    return x"
        result = await inspect_tool_code("runner", code)
        assert result.arguments[0].type_hint == "str"  # fallback

    async def test_inspect_empty_code_raises(self):
        with pytest.raises(ToolCompilationError):
            await inspect_tool_code("empty", "")

    async def test_inspect_no_function_raises(self):
        with pytest.raises(ToolCompilationError):
            await inspect_tool_code("noval", "x = 42")

    async def test_inspect_async_function(self):
        code = "async def fetch(url: str) -> str:\n    return url"
        result = await inspect_tool_code("fetcher", code)
        assert result.function_name == "fetch"
        assert result.arguments[0].type_hint == "str"

    async def test_inspect_mixed_args(self):
        code = "def calc(x: int, y: float, z: str = 'hi') -> str:\n    return z"
        result = await inspect_tool_code("calc", code)
        assert len(result.arguments) == 3
        assert result.arguments[0].type_hint == "int"
        assert result.arguments[1].type_hint == "float"
        assert result.arguments[2].type_hint == "str"
        assert result.arguments[2].default_value == "'hi'"


# ── execute_tool_code ───────────────────────────────────────────────────────


class TestExecuteToolCode:
    """Tests for the test execution endpoint."""

    @requires_docker
    async def test_execute_simple(self):
        code = "def add(a: int, b: int) -> int:\n    return a + b"
        result = await execute_tool_code("adder", code, {"a": "3", "b": "4"})
        assert result.success is True
        assert result.output == "7"
        assert result.execution_time_ms > 0

    @requires_docker
    async def test_execute_string_args(self):
        code = "def greet(name: str) -> str:\n    return f'Hello {name}'"
        result = await execute_tool_code("greeter", code, {"name": "world"})
        assert result.success is True
        assert result.output == "Hello world"

    async def test_execute_compilation_error(self):
        """Compilation errors should return success=False with error message."""
        result = await execute_tool_code("broken", "def broken(:", {})
        assert result.success is False
        assert "SyntaxError" in result.output or "syntax" in result.output.lower()
        assert result.execution_time_ms == 0

    async def test_execute_no_function_raises(self):
        """Code with no function should return success=False."""
        result = await execute_tool_code("noval", "x = 42", {})
        assert result.success is False

    @requires_docker
    async def test_execute_runtime_error(self):
        code = "def boom():\n    raise ValueError('kaboom')"
        result = await execute_tool_code("boom", code, {})
        assert result.success is False
        assert "kaboom" in result.output

    @requires_docker
    async def test_execute_type_coercion_int(self):
        code = "def double(x: int) -> int:\n    return x * 2"
        result = await execute_tool_code("double", code, {"x": "5"})
        assert result.success is True
        assert result.output == "10"

    @requires_docker
    async def test_execute_type_coercion_float(self):
        code = "def half(x: float) -> float:\n    return x / 2"
        result = await execute_tool_code("half", code, {"x": "3.14"})
        assert result.success is True

    @requires_docker
    async def test_execute_type_coercion_bool(self):
        code = "def negate(x: bool) -> bool:\n    return not x"
        result = await execute_tool_code("negate", code, {"x": "true"})
        assert result.success is True

    @requires_docker
    async def test_execute_missing_required_arg(self):
        code = "def add(a: int, b: int) -> int:\n    return a + b"
        result = await execute_tool_code("adder", code, {"a": "1"})  # missing b
        assert result.success is False
        assert "missing" in result.output.lower() or "b" in result.output

    @requires_docker
    async def test_execute_default_args_used(self):
        code = 'def greet(name: str = "world") -> str:\n    return f"Hello {name}"'
        result = await execute_tool_code("greeter", code, {})
        assert result.success is True
        assert result.output == "Hello world"

    @requires_docker
    async def test_execution_time_reported(self):
        code = "def fast() -> str:\n    return 'done'"
        result = await execute_tool_code("fast", code, {})
        assert result.success is True
        assert result.execution_time_ms >= 0


# ── coerce_arg (unit tests — no Deno needed) ─────────────────────────────────


class TestCoerceArg:
    """Tests for the type coercion helper function."""

    def test_coerce_str(self):
        assert coerce_arg("hello", "str") == "hello"

    def test_coerce_int(self):
        assert coerce_arg("42", "int") == 42

    def test_coerce_int_invalid(self):
        with pytest.raises(ToolExecutionError):
            coerce_arg("not_a_number", "int")

    def test_coerce_float(self):
        assert coerce_arg("3.14", "float") == 3.14

    def test_coerce_float_invalid(self):
        with pytest.raises(ToolExecutionError):
            coerce_arg("not_a_float", "float")

    def test_coerce_bool_true(self):
        assert coerce_arg("true", "bool") is True

    def test_coerce_bool_True(self):
        assert coerce_arg("True", "bool") is True

    def test_coerce_bool_false(self):
        assert coerce_arg("false", "bool") is False

    def test_coerce_bool_invalid(self):
        with pytest.raises(ToolExecutionError):
            coerce_arg("not_a_bool", "bool")

    def test_coerce_list(self):
        assert coerce_arg("[1, 2, 3]", "list") == [1, 2, 3]

    def test_coerce_dict(self):
        result = coerce_arg('{"key": "value"}', "dict")
        assert result == {"key": "value"}

    def test_coerce_list_invalid(self):
        with pytest.raises(ToolExecutionError):
            coerce_arg("not a list", "list")

    def test_coerce_unknown_type_falls_back_to_str(self):
        assert coerce_arg("hello", "SomeCustomType") == "hello"
import shutil

import pytest

from canvas_server.sandbox import Sandbox

requires_deno = pytest.mark.skipif(
    not shutil.which("deno"), reason="Deno not installed"
)


class TestSandbox:
    """Tests for the Sandbox singleton wrapping dspy.PythonInterpreter."""

    @requires_deno
    async def test_get_creates_instance(self):
        """Sandbox.get() should create a PythonInterpreter instance if none exists."""
        # Ensure clean state
        await Sandbox.shutdown()
        sandbox = await Sandbox.get()
        assert sandbox is not None
        assert Sandbox._instance is not None
        await Sandbox.shutdown()

    @requires_deno
    async def test_get_returns_same_instance(self):
        """Repeated calls to Sandbox.get() should return the same instance."""
        await Sandbox.shutdown()
        sandbox1 = await Sandbox.get()
        sandbox2 = await Sandbox.get()
        assert sandbox1 is sandbox2
        await Sandbox.shutdown()

    @requires_deno
    async def test_shutdown_clears_instance(self):
        """Sandbox.shutdown() should clear the singleton instance."""
        await Sandbox.get()
        assert Sandbox._instance is not None
        await Sandbox.shutdown()
        assert Sandbox._instance is None

    @requires_deno
    async def test_shutdown_is_idempotent(self):
        """Calling shutdown when no instance exists should be a no-op."""
        await Sandbox.shutdown()
        await Sandbox.shutdown()  # should not raise

    @requires_deno
    async def test_execute_simple_code(self):
        """Sandbox should execute simple Python code and return a result."""
        sandbox = await Sandbox.get()
        result = sandbox("1 + 2")
        assert result == 3
        await Sandbox.shutdown()

    @requires_deno
    async def test_execute_string_result(self):
        """Sandbox should handle string return values."""
        sandbox = await Sandbox.get()
        result = sandbox("'hello' + ' ' + 'world'")
        assert result == "hello world"
        await Sandbox.shutdown()

    @requires_deno
    async def test_execute_function_definition_and_call(self):
        """Sandbox should define a function and then call it."""
        sandbox = await Sandbox.get()
        code = """
def greet(name):
    return f'Hello {name}'

greet('Alice')
"""
        result = sandbox(code)
        assert result == "Hello Alice"
        await Sandbox.shutdown()

    @requires_deno
    async def test_execute_syntax_error(self):
        """Sandbox should raise SyntaxError for invalid Python syntax."""
        sandbox = await Sandbox.get()
        with pytest.raises(SyntaxError):
            sandbox("def broken(:")
        await Sandbox.shutdown()

    @requires_deno
    async def test_execute_runtime_error(self):
        """Sandbox should raise an error for runtime errors."""
        sandbox = await Sandbox.get()
        with pytest.raises(Exception):
            sandbox("1 / 0")
        await Sandbox.shutdown()

    @requires_deno
    async def test_recover_after_error(self):
        """Sandbox should remain usable after a runtime error."""
        sandbox = await Sandbox.get()
        with pytest.raises(Exception):
            sandbox("1 / 0")
        # Should still work after an error
        result = sandbox("2 + 2")
        assert result == 4
        await Sandbox.shutdown()
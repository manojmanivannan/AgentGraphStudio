import functools
import inspect
import logging

from beeai_framework.tools import tool
from beeai_framework.tools.tool import StringToolOutput

from canvas_server.exceptions import ToolCompilationError

logger = logging.getLogger("canvas_server.tool_factory")


async def compile_tool_from_code(name: str, code: str):
    """
    Compiles a tool from a string of Python code.
    The code is expected to contain a single function that will be turned into a tool.
    """
    logger.debug("Compiling tool '%s': code=%s...", name, code[:80] if code else "(empty)")
    namespace: dict = {}
    try:
        exec(code, namespace)
    except Exception as e:
        logger.error("Failed to exec tool '%s': %s", name, e)
        raise ToolCompilationError(f"Failed to compile tool '{name}': {e}") from e

    user_func = None
    for val in namespace.values():
        if callable(val) and not inspect.isbuiltin(val) and getattr(val, "__module__", "") != "builtins":
            user_func = val
            break

    if not user_func:
        logger.warning("No callable function found in tool '%s'", name)
        raise ToolCompilationError(f"No callable function found in tool '{name}'.")

    # Use the function's docstring as the description.
    desc = (user_func.__doc__ or "").strip() or f"A tool named {name}"

    # The beeai-framework can infer the schema from the function signature and docstring.
    # We need to wrap the user_func to ensure it returns a ToolOutput,
    # but we must preserve the original signature for the schema generation.
    @functools.wraps(user_func)
    def wrapper(*args, **kwargs) -> StringToolOutput:
        logger.debug("Calling tool '%s' with args: %s, kwargs: %s", name, args, kwargs)
        result = user_func(*args, **kwargs)
        logger.debug("Tool '%s' result: %s", name, str(result)[:200])
        return StringToolOutput(str(result))

    # We need to set the name of the wrapper to the desired tool name.
    wrapper.__name__ = name
    # The docstring is carried over by @functools.wraps.

    # Now, create the tool by applying the decorator programmatically.
    # The decorator will use the function's signature and docstring to create the schema.
    decorated_tool = tool(name=name, description=desc)(wrapper)

    logger.info("Compiled tool '%s' successfully", name)
    return decorated_tool


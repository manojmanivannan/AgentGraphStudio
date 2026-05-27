import inspect
import logging

from canvas_server.exceptions import ToolCompilationError

logger = logging.getLogger("canvas_server.tool_factory")


async def compile_tool_from_code(name: str, code: str):
    """
    Compiles a tool from a string of Python code.
    The code is expected to contain a single function with type hints that will be
    used as a DSPy tool.
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

    logger.info("Compiled tool '%s' successfully", name)
    return user_func

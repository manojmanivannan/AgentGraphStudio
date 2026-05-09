import inspect
import logging

from beeai_framework.tools import tool
from beeai_framework.tools.tool import StringToolOutput

from canvas_server.exceptions import ToolCompilationError

logger = logging.getLogger("canvas_server.tool_factory")


async def compile_tool_from_code(name: str, code: str):
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

    desc = (user_func.__doc__ or "").strip() or f"Tool: {name}"
    tool_kwargs = {"name": name, "description": desc}

    @tool(**tool_kwargs)
    def dynamic_tool(**kwargs) -> StringToolOutput:
        logger.debug("Calling tool '%s' with args: %s", name, kwargs)
        result = user_func(**kwargs)
        logger.debug("Tool '%s' result: %s", name, str(result)[:200])
        return StringToolOutput(str(result))

    logger.info("Compiled tool '%s' successfully", name)

    return dynamic_tool

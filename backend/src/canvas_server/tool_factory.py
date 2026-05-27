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

    # Create a wrapper with the same signature as the original function
    sig = inspect.signature(user_func)
    params = sig.parameters
    
    wrapper_code = f"""
@functools.wraps(user_func)
def wrapper({', '.join(params)}):
    logger.debug("Calling tool '{name}' with args: %s, kwargs: %s", {tuple(params)}, {{}})
    result = user_func({', '.join(f'{p}={p}' for p in params)})
    logger.debug("Tool '%s' result: %s", name, str(result)[:200])
    return StringToolOutput(str(result))
"""
    
    local_vars = {
        'user_func': user_func,
        'logger': logger,
        'StringToolOutput': StringToolOutput,
        'name': name,
        'functools': functools,
        'params': params,
    }
    exec(wrapper_code, local_vars)
    wrapper = local_vars['wrapper']


    # Now, create the tool by applying the decorator programmatically.
    # The decorator will use the function's signature and docstring to create the schema.
    decorated_tool = tool(name=name, description=desc)(wrapper)

    logger.info("Compiled tool '%s' successfully", name)
    return decorated_tool


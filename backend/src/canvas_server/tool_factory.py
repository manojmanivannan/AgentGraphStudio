"""Tool factory -- compiles user Python tool code and executes it in a sandbox.

The compilation flow is:
1. Validate syntax by sending code to the Deno/Pyodide sandbox (catches SyntaxErrors)
2. Extract function metadata (name, docstring, annotations) via host-side exec
   -- this is safe because we only use it for inspect, not execution
3. Return an async wrapper callable that executes the function in the sandbox

For testing, ``inspect_tool_code`` extracts parameter metadata and
``execute_tool_code`` runs a function with user-provided string arguments,
coercing them to the correct Python types via type hints.
"""

from __future__ import annotations

import ast
import inspect
import json
import logging
import time
from typing import Any

from canvas_server.exceptions import ToolCompilationError, ToolExecutionError
from canvas_server.models.api import ToolArgumentInfo, ToolInspectResponse, ToolTestResponse
from canvas_server.package_manager import PackageManager

logger = logging.getLogger("canvas_server.tool_factory")


# -- Type coercion ---------------------------------------------------------------


def coerce_arg(value: str, type_hint: str) -> Any:
    """Coerce a string value to the Python type indicated by *type_hint*.

    Supported types: str, int, float, bool, list, dict.
    Unknown types fall back to returning the raw string.
    """
    if type_hint == "str":
        return value
    if type_hint == "int":
        try:
            return int(value)
        except (ValueError, TypeError) as exc:
            raise ToolExecutionError(f"Cannot coerce '{value}' to int: {exc}") from exc
    if type_hint == "float":
        try:
            return float(value)
        except (ValueError, TypeError) as exc:
            raise ToolExecutionError(f"Cannot coerce '{value}' to float: {exc}") from exc
    if type_hint == "bool":
        if value.lower() in ("true", "1", "yes"):
            return True
        if value.lower() in ("false", "0", "no"):
            return False
        raise ToolExecutionError(f"Cannot coerce '{value}' to bool")
    if type_hint in ("list", "list[str]", "list[int]"):
        try:
            parsed = json.loads(value)
            if not isinstance(parsed, list):
                raise ToolExecutionError(
                    f"Expected a JSON list, got {type(parsed).__name__}"
                )
            return parsed
        except json.JSONDecodeError as exc:
            raise ToolExecutionError(
                f"Cannot coerce '{value}' to list: {exc}"
            ) from exc
    if type_hint in ("dict", "dict[str, Any]", "dict[str, str]"):
        try:
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ToolExecutionError(
                    f"Expected a JSON dict, got {type(parsed).__name__}"
                )
            return parsed
        except json.JSONDecodeError as exc:
            raise ToolExecutionError(
                f"Cannot coerce '{value}' to dict: {exc}"
            ) from exc
    # Unknown type -- fall back to raw string
    return value


# -- Host-side metadata extraction -----------------------------------------------


def _extract_function(code: str, name: str):
    """Extract the first user-defined callable from *code* using host-side exec.

    This is used ONLY for metadata extraction (name, docstring, annotations)
    that DSPy needs to build tool descriptors.  The actual execution happens in
    the sandbox.
    """
    namespace: dict = {}
    try:
        exec(code, namespace)  # noqa: S102 -- safe: used for metadata only
    except SyntaxError as e:
        raise ToolCompilationError(f"Syntax error in tool '{name}': {e}") from e
    except Exception as e:
        raise ToolCompilationError(f"Failed to compile tool '{name}': {e}") from e

    user_func = None
    for val in namespace.values():
        if callable(val) and not inspect.isbuiltin(val) and getattr(val, "__module__", "") != "builtins":
            user_func = val
            break

    if not user_func:
        raise ToolCompilationError(f"No callable function found in tool '{name}'.")
    return user_func


def _resolve_type_hint(annotation: Any) -> str:
    """Convert a type annotation object to a simple string hint."""
    if annotation is inspect.Parameter.empty:
        return "str"  # default fallback
    if isinstance(annotation, type):
        return annotation.__name__
    # Handle string annotations like 'str', 'int', etc.
    hint_str = str(annotation)
    # Clean up common forms: <class 'int'> -> int, typing.List[str] -> list
    if hint_str.startswith("<class '"):
        return hint_str[8:-2]
    # Strip typing module prefixes
    for prefix in ("typing.", "builtins."):
        if hint_str.startswith(prefix):
            return hint_str[len(prefix):]
    # Simplify complex types: list[str] -> list, dict[str, Any] -> dict
    if hint_str.startswith("list"):
        return "list"
    if hint_str.startswith("dict"):
        return "dict"
    return hint_str


# -- AST-based function extraction (no host-side exec of imports) ----------------


def _extract_function_ast(code: str, name: str):
    """Extract the first user-defined function from *code* using AST parsing.

    Parses the code into a syntax tree (safe — no execution), finds the first
    ``FunctionDef``, then builds a minimal function *stub* (``def …: pass``)
    with the same name, parameters, type annotations, and default values.

    Because the stub body is simply ``pass``, import statements in the original
    code are irrelevant — this never triggers ``ImportError`` on the host side.
    The returned function object is compatible with ``inspect.signature()``.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ToolCompilationError(f"Syntax error in tool '{name}': {e}") from e

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        func_name = node.name
        docstring = ast.get_docstring(node) or ""

        # ---- Build annotations dict from AST -----------------------------------
        annotations: dict[str, str] = {}
        for arg in node.args.args:
            if arg.annotation:
                annotations[arg.arg] = _ast_node_to_type_str(arg.annotation)
        for arg in node.args.kwonlyargs:
            if arg.annotation:
                annotations[arg.arg] = _ast_node_to_type_str(arg.annotation)
        if node.returns:
            annotations["return"] = _ast_node_to_type_str(node.returns)

        # ---- Build default values map -------------------------------------------
        default_values: dict[str, object] = {}
        num_pos = len(node.args.args)
        num_plain_defaults = len(node.args.defaults)
        for i, d in enumerate(node.args.defaults):
            try:
                val = ast.literal_eval(d)
            except (ValueError, TypeError):
                val = None
            default_values[node.args.args[num_pos - num_plain_defaults + i].arg] = val
        for i, d in enumerate(node.args.kw_defaults):
            if d is not None:
                try:
                    val = ast.literal_eval(d)
                except (ValueError, TypeError):
                    val = None
                default_values[node.args.kwonlyargs[i].arg] = val

        # ---- Build minimal stub function string ---------------------------------
        parts: list[str] = []
        for arg_node in node.args.args:
            s = arg_node.arg
            if arg_node.annotation:
                s += f": {_ast_node_to_type_str(arg_node.annotation)}"
            if arg_node.arg in default_values:
                s += f"={repr(default_values[arg_node.arg])}"
            parts.append(s)

        if node.args.vararg:
            parts.append(f"*{node.args.vararg.arg}")
        elif node.args.kwonlyargs:
            parts.append("*")

        for arg_node in node.args.kwonlyargs:
            s = arg_node.arg
            if arg_node.annotation:
                s += f": {_ast_node_to_type_str(arg_node.annotation)}"
            if arg_node.arg in default_values:
                s += f"={repr(default_values[arg_node.arg])}"
            parts.append(s)

        if node.args.kwarg:
            parts.append(f"**{node.args.kwarg.arg}")

        ret_ann = ""
        if node.returns:
            ret_ann = f" -> {_ast_node_to_type_str(node.returns)}"

        async_prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        stub = f"{async_prefix}def {func_name}({', '.join(parts)}){ret_ann}: pass"

        namespace: dict = {}
        try:
            exec(stub, namespace)  # noqa: S102 — safe: minimal function stub
        except Exception as e:
            raise ToolCompilationError(
                f"Failed to build metadata stub for tool '{name}': {e}"
            ) from e

        user_func = namespace[func_name]
        user_func.__doc__ = docstring
        return user_func

    raise ToolCompilationError(f"No callable function found in tool '{name}'.")


def _ast_node_to_type_str(node: ast.expr) -> str:
    """Convert an AST annotation node to a simple type string.

    Handles: ``ast.Name`` → ``"int"``, ``ast.Constant`` → ``"str"`` (a forward
    reference), and ``ast.Subscript`` → ``"list"`` / ``"dict"`` (strips generic
    parameters to keep things simple for coerce_arg).
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return node.value
        return str(node.value)
    if isinstance(node, ast.Subscript):
        # list[...] -> "list", dict[...] -> "dict"
        if isinstance(node.value, ast.Name):
            return node.value.id
        return "str"
    if isinstance(node, ast.Attribute):
        return node.attr
    return "str"


# -- Public API ------------------------------------------------------------------


async def compile_tool_from_code(name: str, code: str):
    """Compile user tool code and return an async callable that executes in the sandbox.

    The returned function has __name__, __doc__, and __annotations__
    set from the original code so that DSPy can build tool descriptors from it.
    When called, it sends the function definition + call through the Deno/Pyodide
    sandbox.
    """
    # Validate syntax via sandbox
    from canvas_server.sandbox import Sandbox

    sandbox = await Sandbox.get()
    try:
        sandbox(f"compile({repr(code)}, '<tool>', 'exec')")
    except SyntaxError as e:
        raise ToolCompilationError(f"Syntax error in tool '{name}': {e}") from e
    except Exception as e:
        # Non-syntax errors in compile() are unexpected but we handle them
        raise ToolCompilationError(f"Failed to compile tool '{name}': {e}") from e

    # Extract function metadata using AST (safe -- no exec of imports on host)
    user_func = _extract_function_ast(code, name)
    fn_name = user_func.__name__

    # Capture code in a closure variable to avoid late-binding issues
    tool_code = code

    async def sandbox_tool_fn(**kwargs):
        """Executes the user's function in the Deno/Pyodide sandbox."""
        sandbox = await Sandbox.get()
        args_repr = ", ".join(f"{k}={repr(v)}" for k, v in kwargs.items())
        call_code = f"{tool_code}\n_result = {fn_name}({args_repr})\n_result"
        return sandbox(call_code)

    # Copy DSPy-needed metadata from the original function
    sandbox_tool_fn.__name__ = user_func.__name__
    sandbox_tool_fn.__doc__ = user_func.__doc__
    sandbox_tool_fn.__annotations__ = getattr(user_func, "__annotations__", {})

    logger.info("Compiled tool '%s' (sandbox mode)", name)
    return sandbox_tool_fn


async def inspect_tool_code(
    name: str, code: str, dependencies: list[str] | None = None
) -> ToolInspectResponse:
    """Extract function signature metadata from tool code.

    Uses AST parsing so that import statements for packages not installed on
    the host do not cause errors.  If *dependencies* are provided they are
    pre-installed in the sandbox so that the code can be compiled there
    (for subsequent execution), but inspection itself does not require them.

    Returns the function name and a list of argument descriptors with name,
    type hint, and default value (if any).
    """
    if dependencies:
        pm = PackageManager()
        try:
            await pm.install_packages(dependencies)
            logger.info("Pre-installed dependencies for inspect: %s", dependencies)
        except Exception as e:
            logger.warning("Failed to pre-install deps during inspect: %s", e)

    user_func = _extract_function_ast(code, name)
    sig = inspect.signature(user_func)
    annotations = getattr(user_func, "__annotations__", {})

    arguments: list[ToolArgumentInfo] = []
    for param_name, param in sig.parameters.items():
        type_hint = _resolve_type_hint(annotations.get(param_name, param.annotation))
        default_value = None
        if param.default is not inspect.Parameter.empty:
            default_value = repr(param.default)
        arguments.append(
            ToolArgumentInfo(
                name=param_name,
                type_hint=type_hint,
                default_value=default_value,
            )
        )

    logger.info(
        "Inspected tool '%s': function=%s, args=%d",
        name,
        user_func.__name__,
        len(arguments),
    )
    return ToolInspectResponse(
        function_name=user_func.__name__,
        arguments=arguments,
    )


async def execute_tool_code(
    name: str, code: str, args: dict[str, str], dependencies: list[str] | None = None
) -> ToolTestResponse:
    """Execute a tool function in the sandbox with user-provided string arguments.

    Coerces string arguments to the correct Python types using type hints,
    then runs the function in the Deno/Pyodide sandbox and returns the result.

    If *dependencies* are provided they are pre-installed in the sandbox via
    ``micropip`` before compilation and execution.
    """
    start = time.perf_counter()

    # 0. Install dependencies in the sandbox before anything else
    if dependencies:
        pm = PackageManager()
        try:
            await pm.install_packages(dependencies)
            logger.info("Pre-installed dependencies for test: %s", dependencies)
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return ToolTestResponse(
                success=False,
                output=f"Failed to install dependencies: {e}",
                execution_time_ms=round(elapsed_ms, 2),
            )

    # 1. Validate and compile the code
    try:
        fn = await compile_tool_from_code(name, code)
    except ToolCompilationError as e:
        return ToolTestResponse(success=False, output=str(e), execution_time_ms=0)

    # 2. Coerce string args using the ORIGINAL function's annotations and signature.
    #    We cannot use inspect.signature(fn) because fn is the async sandbox wrapper
    #    which has **kwargs. Instead, extract the original function for metadata.
    try:
        original_func = _extract_function_ast(code, name)
    except ToolCompilationError as e:
        return ToolTestResponse(success=False, output=str(e), execution_time_ms=0)

    annotations = dict(getattr(original_func, "__annotations__", {}))
    annotations.pop("return", None)

    sig = inspect.signature(original_func)
    coerced_args: dict[str, Any] = {}

    for param_name, param in sig.parameters.items():
        type_hint = _resolve_type_hint(annotations.get(param_name, param.annotation))

        if param_name in args:
            # User provided a value -- coerce it
            try:
                coerced_args[param_name] = coerce_arg(args[param_name], type_hint)
            except ToolExecutionError as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                return ToolTestResponse(
                    success=False, output=str(e), execution_time_ms=elapsed_ms
                )
        elif param.default is not inspect.Parameter.empty:
            # Parameter has a default -- let it be used
            coerced_args[param_name] = param.default
        else:
            # Required argument missing
            elapsed_ms = (time.perf_counter() - start) * 1000
            return ToolTestResponse(
                success=False,
                output=f"Missing required argument: '{param_name}' (expected type: {type_hint})",
                execution_time_ms=elapsed_ms,
            )

    # 3. Execute in the sandbox
    try:
        result = await fn(**coerced_args)
        elapsed_ms = (time.perf_counter() - start) * 1000
        return ToolTestResponse(
            success=True,
            output=str(result),
            execution_time_ms=round(elapsed_ms, 2),
        )
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        error_msg = f"{type(e).__name__}: {e}"
        return ToolTestResponse(
            success=False,
            output=error_msg,
            execution_time_ms=round(elapsed_ms, 2),
        )
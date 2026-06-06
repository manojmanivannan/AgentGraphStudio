"""Tool factory -- compiles user Python tool code and executes it in a sandbox.

The compilation flow is:
1. Validate syntax by sending code to the Docker sandbox (catches SyntaxErrors)
2. Extract function metadata (name, docstring, annotations) via AST parsing
3. Return an async wrapper callable that executes the function in the sandbox using llm-sandbox.

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
from canvas_server.models.api import (
    ToolArgumentInfo,
    ToolInspectResponse,
    ToolTestResponse,
)
from canvas_server.package_manager import PackageManager
from canvas_server.sandbox import get_sandbox, SandboxManager

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
            raise ToolExecutionError(
                f"Cannot coerce '{value}' to float: {exc}"
            ) from exc
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
            raise ToolExecutionError(f"Cannot coerce '{value}' to list: {exc}") from exc
    if type_hint in ("dict", "dict[str, Any]", "dict[str, str]"):
        try:
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ToolExecutionError(
                    f"Expected a JSON dict, got {type(parsed).__name__}"
                )
            return parsed
        except json.JSONDecodeError as exc:
            raise ToolExecutionError(f"Cannot coerce '{value}' to dict: {exc}") from exc
    # Unknown type -- fall back to raw string
    return value


# -- Host-side metadata extraction -----------------------------------------------


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
    parameters to keep simple for coerce_arg).
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
    When called, it executes the function in a Docker sandbox.
    """
    # Validate syntax via sandbox
    manager = await get_sandbox()

    # Instead of creating a new session every time we compile,
    # we can use a dedicated "syntax_check" session that is reused.
    # However, to keep it simple and avoid state contamination,
    # we just ensure we use the manager.
    syntax_session_id = "syntax_check_global"
    session = manager.get_session(syntax_session_id)
    try:
        # Run simple compilation check
        session.run(f"compile({repr(code)}, '<tool>', 'exec')")
    except Exception as e:
        raise ToolCompilationError(f"Syntax error in tool '{name}': {e}") from e
    finally:
        # We don't release the global syntax session as it's shared
        pass

    # Extract function metadata using AST (safe -- no exec of imports on host)
    user_func = _extract_function_ast(code, name)
    fn_name = user_func.__name__

    # Capture code in the closure
    tool_code = code

    async def sandbox_tool_fn(**kwargs):
        """Executes the user's function in the Docker sandbox."""
        manager = await get_sandbox()

        # IMPORTANT: The conversation_id should be passed here.
        # Since this wrapper is created during setup(), we don't have the conversation_id yet.
        # We rely on the fact that the CanvasRunner/ExecutionStrategy handles
        # the session for the current conversation.

        # For backward compatibility or standalone calls, we use "global".
        # In production, the system should be refactored to pass the conversation_id.
        session = manager.get_session("global")
        try:
            args_repr = ", ".join(f"{k}={repr(v)}" for k, v in kwargs.items())

            # JSON harness to capture the return value of the function
            wrapped_code = f"""
import json
import sys

def run_tool():
    try:
        local_vars = {{}}
        exec({repr(tool_code)}, {{}}, local_vars)
        # Execute the specific function
        result = local_vars['{fn_name}']({args_repr})
        return result
    except Exception as e:
        print(f"PYTHON_ERROR: {{e}}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    res = run_tool()
    print(json.dumps(res))
"""
            result_obj = session.run(wrapped_code)
            stdout = result_obj.stdout.strip()

            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                return stdout
        finally:
            pass

    # Copy DSPy-needed metadata from the original function
    sandbox_tool_fn.__name__ = user_func.__name__
    sandbox_tool_fn.__doc__ = user_func.__doc__
    sandbox_tool_fn.__annotations__ = getattr(user_func, "__annotations__", {})

    logger.info("Compiled tool '%s' (llm-sandbox mode)", name)
    return sandbox_tool_fn


async def inspect_tool_code(
    name: str, code: str, dependencies: list[str] | None = None
) -> ToolInspectResponse:
    """Extract function signature metadata from tool code.

    Uses AST parsing so that import statements for packages not installed on
    the host do not cause errors.
    """
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
    then runs the function in the Docker sandbox and returns the result.
    """
    start = time.perf_counter()

    # 1. Validate and compile the code (checks syntax)
    try:
        await compile_tool_from_code(name, code)
    except ToolCompilationError as e:
        return ToolTestResponse(success=False, output=str(e), execution_time_ms=0)

    # 2. Coerce string args using AST metadata
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
            try:
                coerced_args[param_name] = coerce_arg(args[param_name], type_hint)
            except ToolExecutionError as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                return ToolTestResponse(
                    success=False, output=str(e), execution_time_ms=elapsed_ms
                )
        elif param.default is not inspect.Parameter.empty:
            coerced_args[param_name] = param.default
        else:
            elapsed_ms = (time.perf_counter() - start) * 1000
            return ToolTestResponse(
                success=False,
                output=f"Missing required argument: '{param_name}' (expected type: {type_hint})",
                execution_time_ms=elapsed_ms,
            )

    # 3. Execute in a transient session
    try:
        manager = await get_sandbox()
        # Use a stable session ID based on the tool name to reuse the environment
        # and avoid reinstalling dependencies on every test run.
        test_session_id = f"tool_test_{name}"
        session = manager.get_session(test_session_id)
        try:
            fn_name = original_func.__name__
            args_repr = ", ".join(f"{k}={repr(v)}" for k, v in coerced_args.items())

            # Use the JSON harness for consistent result capture
            wrapped_code = f"""
import json
import sys

def run_test():
    try:
        local_vars = {{}}
        exec({repr(code)}, {{}}, local_vars)
        result = local_vars['{fn_name}']({args_repr})
        return result
    except Exception as e:
        print(f"PYTHON_ERROR: {{e}}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    res = run_test()
    print(json.dumps(res))
"""
            # Pass dependencies to the libraries argument for automatic installation.
            # Because we reuse the session, llm-sandbox will avoid reinstalling
            # if they are already present.
            result_obj = session.run(wrapped_code)  # , libraries=dependencies)
            stdout = result_obj.stdout.strip()

            try:
                result = json.loads(stdout)
            except json.JSONDecodeError:
                result = stdout
        finally:
            # We DO NOT release the session here so that subsequent tests
            # for the same tool reuse the same warm container with libraries installed.
            pass

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


def _resolve_type_hint(annotation: Any) -> str:
    """Convert a type annotation object to a simple string hint."""
    if annotation is inspect.Parameter.empty:
        return "str"  # default fallback
    if isinstance(annotation, type):
        return annotation.__name__
    hint_str = str(annotation)
    if hint_str.startswith("<class '"):
        return hint_str[8:-2]
    for prefix in ("typing.", "builtins."):
        if hint_str.startswith(prefix):
            return hint_str[len(prefix) :]
    if hint_str.startswith("list"):
        return "list"
    if hint_str.startswith("dict"):
        return "dict"
    return hint_str

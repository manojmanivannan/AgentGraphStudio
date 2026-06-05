"""Sandbox — managed singleton for dspy.PythonInterpreter (Deno/Pyodide).

Wraps the Deno-based PythonInterpreter into a process-wide singleton that is
started once at app startup and kept warm across requests.  This avoids the
~2s cold-start cost of launching a Deno subprocess on every call.

The sandbox provides secure Python execution: no filesystem, network, or
environment access by default (Deno permission model).

**Stdout noise resilience:** Pyodide's ``loadPackagesFromImports`` emits
progress messages ("Loading numpy", "Package ... loaded from CDN") through
Emscripten's WASM ``fd_write``, which is NOT interceptable from JavaScript.
These messages land on Deno stdout intermixed with our JSON responses, so we
handle this at the Python level by reading multiple lines from the subprocess
and skipping content that doesn't parse as valid response JSON.
"""

from __future__ import annotations

import json as json_mod
import logging
import os
from typing import Any, ClassVar

from dspy import PythonInterpreter
from dspy.primitives.python_interpreter import InterpreterError

logger = logging.getLogger("canvas_server.sandbox")

# Path to our custom runner which suppresses console.log during
# loadPackagesFromImports so that package-loading messages do not
# leak into the JSON response stream on Deno stdout.
_RUNNER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runner.js")


class Sandbox:
    """Manages a long-lived Deno/Pyodide sandbox process for executing Python code.

    Usage::

        sandbox = await Sandbox.get()      # get or create the singleton
        result = sandbox("1 + 2")           # execute Python code
        await Sandbox.shutdown()            # graceful shutdown

    The sandbox is pre-warmed during FastAPI app startup (see main.py lifespan).
    """

    _instance: ClassVar[PythonInterpreter | None] = None
    _has_patch: ClassVar[bool] = False

    @classmethod
    async def get(cls) -> PythonInterpreter:
        """Get or create the singleton sandbox instance.

        Returns the PythonInterpreter, starting the Deno subprocess on first call.
        Network access is granted to ``cdn.jsdelivr.net`` so that Pyodide can
        auto-download packages (``loadPackagesFromImports``, ``micropip``).
        """
        if cls._instance is None:
            logger.info("Starting Deno/Pyodide sandbox (with CDN network access)...")
            cls._instance = PythonInterpreter(
                enable_network_access=["cdn.jsdelivr.net"],
            )
            # Replace the DSPy-built-in runner.js with our custom version
            # that suppresses console.log during loadPackagesFromImports.
            for i, arg in enumerate(cls._instance.deno_command):
                if arg.endswith("runner.js"):
                    cls._instance.deno_command[i] = _RUNNER_PATH
                    break
            cls._instance.__enter__()
            # Force the subprocess to start
            cls._instance._ensure_deno_process()
            logger.info("Sandbox started successfully")

        # Apply our noise-resilient execute wrapper once
        if not cls._has_patch and cls._instance.deno_process is not None:
            cls._patch_execute()
            cls._has_patch = True

        return cls._instance

    @classmethod
    def _patch_execute(cls) -> None:
        """Replace the instance's ``execute`` with a noise-resilient version.

        The standard DSPy ``PythonInterpreter.execute`` reads exactly one line
        from Deno stdout and tries to parse it as JSON.  Pyodide's package
        loader emits progress messages (via WASM ``fd_write``) onto Deno stdout
        that cannot be suppressed from JavaScript, so the first line read may
        be ``"Loading numpy"`` instead of the actual JSON response.

        Our patched version reads lines from the subprocess until it encounters
        one that parses as a valid response JSON object (containing ``"output"``
        or ``"error"`` keys), discarding noise lines.
        """
        interp = cls._instance
        original_execute = interp.execute

        def noise_resilient_execute(
            code: str,
            variables: dict[str, Any] | None = None,
        ) -> Any:
            variables = variables or {}
            code = interp._inject_variables(code, variables)

            if interp.deno_process is None or interp.deno_process.poll() is not None:
                interp._ensure_deno_process()
            interp._mount_files()

            input_data = json_mod.dumps({"code": code})
            try:
                interp.deno_process.stdin.write(input_data + "\n")
                interp.deno_process.stdin.flush()
            except BrokenPipeError:
                interp._ensure_deno_process()
                interp.deno_process.stdin.write(input_data + "\n")
                interp.deno_process.stdin.flush()

            # Read lines until we find a valid JSON response with our shape
            result: dict | None = None
            while True:
                output_line = interp.deno_process.stdout.readline()
                if not output_line:
                    err_output = interp.deno_process.stderr.read()
                    raise InterpreterError(
                        f"No output from Deno subprocess. Stderr: {err_output}"
                    )
                output_line = output_line.strip()
                if not output_line:
                    continue
                try:
                    candidate = json_mod.loads(output_line)
                except json_mod.JSONDecodeError:
                    # Skip noise lines like "Loading numpy"
                    continue
                # Accept any JSON that has our expected response keys
                if "output" in candidate or "error" in candidate:
                    result = candidate
                    break

            # Handle errors and special responses (same logic as original)
            if "error" in result:
                error_msg = result["error"]
                error_type = result.get("errorType", "Sandbox Error")
                if error_type == "FinalAnswer":
                    result["output"] = result.get("errorArgs", None)
                elif error_type == "SyntaxError":
                    raise SyntaxError(f"Invalid Python syntax. message: {error_msg}")
                else:
                    raise InterpreterError(
                        f"{error_type}: {result.get('errorArgs') or error_msg}"
                    )

            interp._sync_files()
            return result.get("output", None)

        # Bind as an instance method
        interp.execute = noise_resilient_execute

    @classmethod
    async def shutdown(cls) -> None:
        """Gracefully shut down the sandbox process.

        Idempotent — safe to call multiple times or when no instance exists.
        """
        if cls._instance is not None:
            logger.info("Shutting down Deno/Pyodide sandbox...")
            cls._instance.shutdown()
            cls._instance = None
            cls._has_patch = False
            logger.info("Sandbox shut down")
# Deno/Pyodide Sandbox for Tool Execution

## Status

Accepted

## Context

Tool nodes contain user-written Python code that gets executed when agents call tools during workflow runs. Previously, `tool_factory.py` used raw `exec()` to compile user code into callable functions. This meant tool code ran in the same Python process as the backend with full access to the host filesystem, network, and environment.

We also needed a "Test Tool" feature: users should be able to test their Python tool code directly in the UI by providing argument values and seeing the output, without wiring it to an agent first.

Both use cases — agent execution and interactive testing — require running arbitrary user Python code, which presents security and isolation concerns.

## Considered Options

### 1. Raw `exec()` (status quo)

Keep using `exec(code, namespace)` in the host Python process.

- **Pros:** Simple, fast, full CPython stdlib access.
- **Cons:** No isolation — tool code can read/write host filesystem, make network requests, access environment variables, or crash the server with infinite loops. Acceptable for local dev but dangerous for any shared or production deployment.

### 2. Deno + Pyodide sandbox (via DSPy PythonInterpreter)

Use DSPy's built-in `dspy.PythonInterpreter`, which launches a Deno subprocess running Pyodide (WebAssembly-based Python runtime). Communication via JSON-RPC over stdin/stdout pipes. Deno's permission system enforces strict boundaries: no filesystem, network, or env access by default.

- **Pros:** Strong sandboxing via Deno permission model; same trust model as DSPy's own tool execution; process isolation (tool crash doesn't kill the server); already bundled with DSPy.
- **Cons:** Pyodide (WASM Python) has limitations — no C extensions, limited stdlib (~95% coverage); cold start ~2s (mitigated by keeping process warm); additional Deno dependency in the container.

### 3. Docker-based sandbox

Run each tool call in a short-lived Docker container.

- **Pros:** Maximum isolation.
- **Cons:** Very high per-call latency (container startup); complex orchestration; overkill for a development tool.

### 4. Restricted `exec()` namespace

Use `exec()` with a restricted `__builtins__` dict and blocked imports.

- **Pros:** No external dependencies.
- **Cons:** Python sandboxing via restricted namespaces is notoriously bypassable; constant arms race; false sense of security.

## Decision

**Option 2: Deno + Pyodide sandbox.**

Both tool execution (during agent runs) and tool testing (interactive UI) use the same sandbox. `compile_tool_from_code()` validates syntax in the sandbox, extracts function metadata on the host side (safe — metadata only, no execution), then returns an async wrapper that executes the function in the sandbox.

The Deno process is started once at app startup (singleton via `Sandbox` class) and kept warm across requests. The ~2s cold start is paid once.

Host-side `exec()` is retained **only** for extracting function metadata (`__name__`, `__doc__`, `__annotations__`) that DSPy needs to build tool descriptors. This is safe because we never execute the function through the host-side reference.

## Consequences

- **Deno must be installed** in the backend container (added to Dockerfile).
- **Sandbox singleton** managed via `canvas_server.sandbox.Sandbox` — started in FastAPI lifespan, shut down on teardown.
- **Pyodide limitations:** Tool code cannot use C extensions (e.g., numpy, pandas). Pure Python and most stdlib modules work. `os.listdir()` works but against a virtual filesystem, not the host.
- **Test marker:** Sandbox integration tests use `@requires_deno` (skip if `deno` not in PATH), so CI without Deno still passes unit tests.
- **New API endpoints:** `POST /api/tools/inspect` (arg metadata) and `POST /api/tools/test` (execute with args) — both stateless, no DB required.
- **New frontend feature:** ToolEditor "Test Tool" panel with argument inputs and result display.
- **Type coercion:** Frontend sends string args; backend coerces to correct Python types (int, float, bool, list, dict) using function type hints.
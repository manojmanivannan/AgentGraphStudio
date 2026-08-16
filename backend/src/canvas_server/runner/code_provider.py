"""CodeProvider — exposes a ``run_code`` tool that lets worker agents write and
execute their own Python in the per-conversation Docker sandbox and reason over
the returned stdout.

This is the text-output mirror of :mod:`canvas_server.runner.plot_provider`:
it runs on the same shared per-conversation sandbox session (so a worker can
``run_code`` to compute a file and then hand it off to ``generate_plot`` in the
same turn), but with plot detection disabled — ``result.plots`` is always
``[]`` and stdout is returned to the agent as a plain-text observation that the
agent reasons over (never raw-dumped to the user).
"""

from __future__ import annotations

import asyncio
import logging

from llm_sandbox.exceptions import SandboxTimeoutError

from canvas_server.sandbox import (
    SANDBOX_ACQUIRE_TIMEOUT,
    bounded_acquire,
    get_sandbox,
)

logger = logging.getLogger(__name__)

# Max chars of stdout/stderr kept before the rest is dropped.
MAX_OUTPUT_CHARS = 8000
# Hard wall on a single code execution (passed to session.run).
EXECUTION_TIMEOUT = 60  # seconds
# Bounded wait for a free sandbox container before reporting the sandbox busy.
# Re-exported from the shared ``bounded_acquire`` helper (sandbox.py) so the
# per-call bound stays a single source of truth shared with future pip_install
# (#56). A saturated pool surfaces as a 'busy' observation quickly instead of
# stalling the agent's turn.
ACQUIRE_TIMEOUT = SANDBOX_ACQUIRE_TIMEOUT
TRUNCATION_MARKER = (
    "…[truncated at 8000 chars — narrow your print, or save to a file and read a slice]"
)

# Observation returned when no sandbox container is free within the bounded wait.
# Kept in sync with ``canvas_server.sandbox.SANDBOX_BUSY_OBSERVATION`` (the shared
# helper's canonical string).
BUSY_OBSERVATION = (
    "Code sandbox busy — all sandboxes are currently in use. "
    "Try again shortly, or simplify your request."
)


def _truncate(text: str) -> str:
    """Drop output beyond ``MAX_OUTPUT_CHARS``, marking the truncation."""
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + TRUNCATION_MARKER
    return text


class CodeProvider:
    """Wraps :class:`SandboxManager` to expose a ``run_code`` tool to agents."""

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id

    async def run_code(self, python_code: str) -> str:
        """Execute Python code in an isolated sandbox and return stdout as text.

        Use ``print()`` to emit the output you want to read back; only captured
        stdout is returned as a text observation. If the output is very large,
        narrow your print or save the data to a file and read a slice in a
        follow-up call. Files you write persist across ``run_code`` calls within
        the same conversation (each call runs in a fresh process on the shared
        container, so in-memory variables do not carry over — save to a file
        instead), so you can compute a file and hand it off to ``generate_plot``
        in the same turn.

        Args:
            python_code (str): The complete Python code script to execute.

        Returns:
            str: The captured stdout (text), or a descriptive error
                 observation. This method never raises — every failure mode
                 becomes a string the agent can reason over.
        """
        try:
            sandbox = await get_sandbox()
            # enable_plotting=False: no plot detection, result.plots is always [].
            # network_pool="default": run_code runs in the locked (no-network)
            # pool — a worker that needs network uses a separate tool (#56).
            session = sandbox.get_session(
                self.conversation_id,
                enable_plotting=False,
                network_pool="default",
            )

            logger.info("Executing code in sandbox...")
            # Bound the pool-acquire wait so a saturated pool reports 'busy'
            # instead of stalling the turn. The shared helper never raises on
            # exhaustion; on timeout it releases any container the orphaned
            # acquire eventually grabs so it cannot leak into the shared pool.
            acquired = await bounded_acquire(session, timeout=ACQUIRE_TIMEOUT)
            if not acquired.acquired:
                return acquired.observation or BUSY_OBSERVATION

            try:
                result = await asyncio.to_thread(
                    session.run, python_code, timeout=EXECUTION_TIMEOUT
                )
            except SandboxTimeoutError:
                return (
                    f"Error: code execution timed out after {EXECUTION_TIMEOUT}s. "
                    "Simplify or optimize your code, or save intermediate results to a file."
                )
            finally:
                try:
                    await asyncio.to_thread(session.__exit__, None, None, None)
                except Exception:  # noqa: BLE001 - never let cleanup raise out
                    logger.warning("Failed to exit sandbox session cleanly")

            return self._format_result(result)
        except Exception as e:  # noqa: BLE001 - run_code must never raise
            logger.exception("run_code failed")
            return f"Error: {e}"

    @staticmethod
    def _format_result(result) -> str:
        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if result.exit_code != 0:
            # Keep partial stdout, then append the error block.
            body = (
                f"{stdout}\n\nError executing code (exit code {result.exit_code}):\n{stderr}"
                if stdout
                else f"Error executing code (exit code {result.exit_code}):\n{stderr}"
            )
        else:
            body = stdout
        # One 8000-char cap on the whole observation, with a single marker
        # (spec: "output beyond 8,000 chars dropped with a … marker").
        return _truncate(body)

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

from canvas_server.config import settings
from canvas_server.pip_hardening import build_pip_install_command
from canvas_server.sandbox import (
    NETWORK_POOL_DEFAULT,
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
    """Wraps :class:`SandboxManager` to expose a ``run_code`` tool to agents.

    ``network_pool`` selects which sandbox pool the worker's session runs in:
    the locked (no-network) default pool, or the lazy networked pool (internet
    egress) for workers with ``enable_network`` (#56). A networked worker's
    ``run_code`` and ``pip_install`` share the *same* per-conversation session
    (keyed by ``(conversation_id, network_pool)``), so packages installed by
    ``pip_install`` are importable from subsequent ``run_code`` calls in the
    same turn.
    """

    def __init__(
        self, conversation_id: str, network_pool: str = NETWORK_POOL_DEFAULT
    ):
        self.conversation_id = conversation_id
        self.network_pool = network_pool

    async def _with_session(self, work):
        """Acquire the per-conversation sandbox session, run ``work(session)``,
        and always release the session afterwards.

        Shared scaffold for :meth:`run_code` and :meth:`pip_install`: bounds the
        pool-acquire wait (a saturated pool surfaces as the 'busy' observation
        instead of stalling the turn — never raises) and guarantees the session
        is exited in a ``finally``. ``work`` is an awaitable taking the acquired
        session and returning the observation string; its own timeout handling
        lives in the caller. Any exception from ``work`` propagates to the
        caller's outer never-raise guard.
        """
        sandbox = await get_sandbox()
        session = sandbox.get_session(
            self.conversation_id,
            enable_plotting=False,
            network_pool=self.network_pool,
        )
        acquired = await bounded_acquire(session, timeout=ACQUIRE_TIMEOUT)
        if not acquired.acquired:
            return acquired.observation or BUSY_OBSERVATION
        try:
            return await work(session)
        finally:
            try:
                await asyncio.to_thread(session.__exit__, None, None, None)
            except Exception:  # noqa: BLE001 - never let cleanup raise out
                logger.warning("Failed to exit sandbox session cleanly")

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
            logger.info("Executing code in sandbox...")

            async def _work(session):
                try:
                    result = await asyncio.to_thread(
                        session.run, python_code, timeout=EXECUTION_TIMEOUT
                    )
                except SandboxTimeoutError:
                    return (
                        f"Error: code execution timed out after {EXECUTION_TIMEOUT}s. "
                        "Simplify or optimize your code, or save intermediate results to a file."
                    )
                return self._format_result(result)

            return await self._with_session(_work)
        except Exception as e:  # noqa: BLE001 - run_code must never raise
            logger.exception("run_code failed")
            return f"Error: {e}"

    async def pip_install(self, packages: list[str]) -> str:
        """Install pip packages into the worker's networked sandbox session.

        Hardened against supply-chain mistakes (#56): each token is PEP 508
        validated, flag-like tokens (``--index-url`` / ``--trusted-host`` /
        ``--no-deps``) are rejected, tokens are ``shlex.quote``'d, and at most
        20 packages are accepted per call. Default PyPI only. Typosquat risk
        is accepted (no allowlist).

        Runs in the **networked** pool session — the same shared per-conversation
        session the worker's other tools execute in — so installed packages are
        importable from subsequent code execution in the same turn. The install
        is bounded by ``sandbox_pip_install_timeout`` (default 120s).

        This method **never raises** — every failure mode (bad token, over the
        package cap, nonzero exit, timeout, pool exhaustion, internal error)
        becomes an observation string the agent can reason over.

        Args:
            packages (list[str]): Pip package requirement strings (PEP 508).

        Returns:
            str: pip's stdout on success, or a descriptive error observation.
        """
        # Build the hardened command up front — a bad token / over-limit
        # batch rejects the whole install *before* touching the sandbox.
        try:
            cmd = build_pip_install_command(packages)
        except ValueError as exc:
            return f"pip_install rejected: {exc}"

        if cmd == "pip install":
            return "pip_install: no valid packages to install."

        timeout = settings.sandbox_pip_install_timeout

        async def _work(session):
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(session.execute_command, cmd),
                    timeout=timeout,
                )
            except TimeoutError:
                return (
                    f"pip_install timed out after {timeout}s. "
                    "Try fewer/smaller packages, or retry."
                )
            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            if result.exit_code != 0:
                body = (
                    f"{stdout}\n\npip_install failed (exit code {result.exit_code}):\n{stderr}"
                    if stdout
                    else f"pip_install failed (exit code {result.exit_code}):\n{stderr}"
                )
                return _truncate(body)
            return _truncate(stdout) if stdout else "Packages installed."

        try:
            return await self._with_session(_work)
        except Exception as e:  # noqa: BLE001 - pip_install must never raise
            logger.exception("pip_install failed")
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

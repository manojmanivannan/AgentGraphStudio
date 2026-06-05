"""Sandbox — managed singleton for dspy.PythonInterpreter (Deno/Pyodide).

Wraps the Deno-based PythonInterpreter into a process-wide singleton that is
started once at app startup and kept warm across requests.  This avoids the
~2s cold-start cost of launching a Deno subprocess on every call.

The sandbox provides secure Python execution: no filesystem, network, or
environment access by default (Deno permission model).
"""

from __future__ import annotations

import logging
from typing import ClassVar

from dspy import PythonInterpreter

logger = logging.getLogger("canvas_server.sandbox")


class Sandbox:
    """Manages a long-lived Deno/Pyodide sandbox process for executing Python code.

    Usage::

        sandbox = await Sandbox.get()      # get or create the singleton
        result = sandbox("1 + 2")           # execute Python code
        await Sandbox.shutdown()            # graceful shutdown

    The sandbox is pre-warmed during FastAPI app startup (see main.py lifespan).
    """

    _instance: ClassVar[PythonInterpreter | None] = None

    @classmethod
    async def get(cls) -> PythonInterpreter:
        """Get or create the singleton sandbox instance.

        Returns the PythonInterpreter, starting the Deno subprocess on first call.
        """
        if cls._instance is None:
            logger.info("Starting Deno/Pyodide sandbox...")
            cls._instance = PythonInterpreter()
            cls._instance.__enter__()
            logger.info("Sandbox started successfully")
        return cls._instance

    @classmethod
    async def shutdown(cls) -> None:
        """Gracefully shut down the sandbox process.

        Idempotent — safe to call multiple times or when no instance exists.
        """
        if cls._instance is not None:
            logger.info("Shutting down Deno/Pyodide sandbox...")
            cls._instance.shutdown()
            cls._instance = None
            logger.info("Sandbox shut down")
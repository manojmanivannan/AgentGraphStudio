"""Per-run MCP session registry (ticket #137, spec §3.2/§4.3).

Runner-local — **not** a singleton. Each run opens one Streamable HTTP
session per referenced MCP server (workers' tool grants only, decided by
``CanvasRunner.setup``), reuses it across every MCP tool call in the run,
and terminates it at run end (``ConversationRunCoordinator.run``'s
``finally``, next to ``sandbox.release_session``).

Lifecycle mirrors the sandbox session registry but is deliberately simpler:
no warm pool, no idle-session management, no per-call reconnection (spec #120
fallbacks are documented, not mechanisms). One mid-run re-handshake on a
stale ``Mcp-Session-Id`` is the degradation ticket's scope (#139).

Sessions are opened **concurrently** (spec #127 scale rule) so one slow or
distant server does not serially delay the rest.

Interface for the descriptor ticket (#138):
  * ``get_session(server_id)`` — the initialized ``mcp.ClientSession``, or
    ``None`` when the server was never opened / failed to connect.
  * ``list_tools(server_id)`` — the session's ``tools/list`` result.
  * ``error_for(server_id)`` — the connect-time exception, if any (call-time
    error callables + degradation surfacing build on it).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Iterable

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from canvas_server import mcp_config
from canvas_server.config import settings

logger = logging.getLogger("canvas_server.runner.mcp_sessions")

# Grace period for lifetime tasks to exit their transport context managers
# after the close event is set; stragglers are cancelled.
_CLOSE_GRACE_SECONDS = 5.0


class McpSessionRegistry:
    """Holds the open MCP ``ClientSession`` for each referenced server for a
    single run. Created per run inside ``CanvasRunner.setup()``; closed in
    ``ConversationRunCoordinator.run``'s ``finally``.

    Server configs are resolved through the process-local ``mcp_config``
    cache (the #129 read seam). A constructor override keeps the unit seams
    open for tests; production callers use the default (cache lookup).
    """

    def __init__(self, servers=None) -> None:
        self._servers = servers if servers is not None else mcp_config.get_mcp_servers()
        self._configs: dict[uuid.UUID, mcp_config.McpServerConfig] = {}
        self._sessions: dict[uuid.UUID, ClientSession] = {}
        self._tasks: dict[uuid.UUID, asyncio.Task] = {}
        self._close_events: dict[uuid.UUID, asyncio.Event] = {}
        self._ready_events: dict[uuid.UUID, asyncio.Event] = {}
        self._errors: dict[uuid.UUID, BaseException] = {}
        self._closed = False

    # ------------------------------------------------------------------
    # Open / ready
    # ------------------------------------------------------------------

    async def open(self, server_ids: Iterable[uuid.UUID]) -> None:
        """Open sessions for *server_ids* known to the server cache,
        concurrently (spec §3.2 scale rule). Never raises: a server that
        fails to connect is recorded via :meth:`error_for` and its session
        stays ``None`` so the run can still proceed with the rest (#138
        builds a call-time error callable for it; retry/degrade is #139).
        Unknown server ids are skipped with a warning.
        """
        wanted = [sid for sid in dict.fromkeys(server_ids) if sid is not None]
        for sid, cfg in self._resolve_configs(wanted):
            self._close_events[sid] = asyncio.Event()
            self._ready_events[sid] = asyncio.Event()
            self._tasks[sid] = asyncio.create_task(
                self._session_lifetime(sid, cfg), name=f"mcp-session-{sid}"
            )

        if not self._tasks:
            return

        # All configured servers were opened above; wait until each reached
        # "initialized" or "failed". Concurrent opens complete together.
        await asyncio.gather(
            *(self._ready_events[sid].wait() for sid in self._tasks),
        )
        for sid, exc in self._errors.items():
            logger.warning(
                "MCP session open failed for server %s: %r",
                sid,
                exc,
            )

    def _resolve_configs(
        self, server_ids: list[uuid.UUID]
    ) -> list[tuple[uuid.UUID, mcp_config.McpServerConfig]]:
        configs = {cfg.id: cfg for cfg in self._servers}
        resolved = []
        for sid in server_ids:
            cfg = configs.get(sid)
            if cfg is None:
                logger.warning(
                    "Tool node references MCP server %s which is not "
                    "registered — no session will be opened (call-time "
                    "error stub is #138's scope).",
                    sid,
                )
                continue
            resolved.append((sid, cfg))
        self._configs.update(dict(resolved))
        return resolved

    async def _session_lifetime(self, server_id: uuid.UUID, cfg) -> None:
        """Hold one server's transport+session open until ``close()``.

        Initialized on first connect and re-raised nothing: failures land in
        ``_errors`` (never raise out of the task — they would cancel the
        gather above).
        """
        ready = self._ready_events[server_id]
        close_event = self._close_events[server_id]
        headers = (
            {cfg.credential_header: cfg.credential_value}
            if cfg.credential_header and cfg.credential_value
            else None
        )
        timeout = settings.llm_validation_timeout_seconds
        try:
            async with streamablehttp_client(
                cfg.url, headers=headers, timeout=timeout, sse_read_timeout=timeout
            ) as (read_stream, write_stream, _get_session_id):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    self._sessions[server_id] = session
                    ready.set()
                    # Held open — every MCP tool call in the run reuses this
                    # session (spec §3.2: one handshake per run and server).
                    await close_event.wait()
        except BaseException as exc:  # noqa: BLE001 — recorded, never escapes the task
            self._errors[server_id] = exc
        finally:
            if not ready.is_set():
                ready.set()
            self._sessions.pop(server_id, None)
            self._tasks.pop(server_id, None)

    # ------------------------------------------------------------------
    # Session access (the #138 surface)
    # ------------------------------------------------------------------

    def get_session(self, server_id: uuid.UUID) -> ClientSession | None:
        """The initialized session for *server_id*, or ``None``.

        Sessions are stored only after ``initialize()`` completes, so a
        non-``None`` result is fully initialized.
        """
        return self._sessions.get(server_id)

    @property
    def server_ids(self) -> set[uuid.UUID]:
        """Ids of servers with a live (initialized) session."""
        return set(self._sessions)

    def error_for(self, server_id: uuid.UUID) -> BaseException | None:
        """The connect-time exception for a failed server, or ``None``."""
        return self._errors.get(server_id)

    async def list_tools(self, server_id: uuid.UUID) -> list:
        """``tools/list`` for *server_id* through the run's session."""
        session = self.get_session(server_id)
        if session is None:
            raise LookupError(
                f"No open MCP session for server {server_id}"
            )
        result = await session.list_tools()
        return result.tools

    # ------------------------------------------------------------------
    # Close (run end — ConversationRunCoordinator's finally)
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Terminate every open session. Idempotent; never raises on
        already-exited transports (run-end cleanup must not block the turn)."""
        if self._closed:
            return
        self._closed = True
        for event in self._close_events.values():
            event.set()

        tasks = list(self._tasks.values())
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=_CLOSE_GRACE_SECONDS)
            for task in pending:
                task.cancel()
            results = await asyncio.gather(
                *(list(done) + list(pending)), return_exceptions=True
            )
            # Transport-exit errors after a clean handshake are noise; a
            # terminated server should just drop the session (DELETE above).
            for result in results:
                if isinstance(result, BaseException) and not isinstance(
                    result, (asyncio.CancelledError, GeneratorExit)
                ):
                    logger.debug("MCP session close-time error: %r", result)
        self._tasks.clear()
        self._sessions.clear()
        self._close_events.clear()
        self._ready_events.clear()
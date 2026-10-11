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

# Server-side session invalidation markers (spec §4.6 retry-then-degrade).
# The official SDK turns a 404 on a POSTed JSON-RPC request into
# McpError("Session terminated"); other implementations say "not found".
_STALE_SESSION_MARKERS = ("session terminated", "session not found")


def is_stale_session_error(exc: BaseException) -> bool:
    """True when *exc*'s tree reports a dead server-side session.

    Walks exception groups / causes — transport errors usually arrive
    wrapped in an anyio ``ExceptionGroup`` whose ``str`` hides the leaf.
    Deliberately narrow: tool errors, auth failures and plain transport
    drops must NOT trigger the one-shot re-handshake.
    """
    stack: list[BaseException] = [exc]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if not isinstance(current, BaseException):
            continue  # pydantic payloads etc. — no message/cause graph
        text = str(current).lower()
        if any(marker in text for marker in _STALE_SESSION_MARKERS):
            return True
        stack.extend(getattr(current, "exceptions", ()) or ())
        for linked in (current.__cause__, current.__context__):
            if isinstance(linked, BaseException):
                stack.append(linked)
    return False


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
        # Servers whose single per-run re-handshake budget is spent (#139):
        # degraded for the rest of the run — no further handshake attempts,
        # whether the one attempt succeeded or failed (spec §4.6).
        self._rehandshake_used: dict[uuid.UUID, bool] = {}
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
            ) as (read_stream, write_stream, _get_session_id), ClientSession(read_stream, write_stream) as session:
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

    def server_name(self, server_id: uuid.UUID) -> str | None:
        """The registered display name for *server_id*, or ``None`` when the
        id is unknown (flag messages fall back to the id itself)."""
        cfg = self._configs.get(server_id)
        return cfg.name if cfg is not None else None

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
    # One-shot re-handshake on a stale mid-run session (#139, spec §4.6)
    # ------------------------------------------------------------------

    async def rehandshake(self, server_id: uuid.UUID) -> ClientSession | None:
        """Tear down the stale session for *server_id* and open exactly one
        fresh one. Each server gets **one** re-handshake per run (spec §4.6):
        the budget is spent by the first invocation for that server — whether
        it succeeds or fails — so a second stale-session event degrades the
        server for the rest of the run (**no retry loop**). Returns the new
        session, or ``None`` when the budget is spent, there was nothing
        registered, the run is closing, or the fresh handshake failed
        (callers then degrade — spec §4.6).
        Genuine connect/TLS/auth failures never reach this path: it is only
        invoked for detected stale-session errors, and a server that failed
        to connect never produced a session to go stale."""
        if self._closed:
            logger.warning(
                "MCP re-handshake for server %s skipped — the run is closing",
                server_id,
            )
            return None
        cfg = self._configs.get(server_id)
        if cfg is None:
            logger.warning(
                "MCP re-handshake for server %s skipped — never registered "
                "with this run's registry",
                server_id,
            )
            return None
        if self._rehandshake_used.get(server_id):
            # The run's single re-handshake for this server was already spent
            # (success or failure): it stays degraded (spec §4.6
            # retry-then-degrade, no retry loop).
            logger.warning(
                "MCP re-handshake for server %s skipped — the run's single "
                "re-handshake is already spent; the server stays degraded",
                server_id,
            )
            return None

        stale_event = self._close_events.get(server_id)
        stale_task = self._tasks.get(server_id)
        if stale_event is not None:
            stale_event.set()
        if stale_task is not None:
            _done, pending = await asyncio.wait(
                {stale_task}, timeout=_CLOSE_GRACE_SECONDS
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

        self._errors.pop(server_id, None)
        self._sessions.pop(server_id, None)
        self._close_events[server_id] = asyncio.Event()
        self._ready_events[server_id] = asyncio.Event()
        self._tasks[server_id] = asyncio.create_task(
            self._session_lifetime(server_id, cfg), name=f"mcp-session-{server_id}"
        )
        await self._ready_events[server_id].wait()

        # The budget is spent by the attempt itself — a successful fresh
        # session serves the run until its next staleness degrades it.
        self._rehandshake_used[server_id] = True
        fresh = self.get_session(server_id)
        if fresh is None:
            logger.warning(
                "MCP re-handshake failed for server %s: %r — its tools "
                "degrade for the rest of the run",
                server_id,
                self._errors.get(server_id),
            )
        return fresh

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

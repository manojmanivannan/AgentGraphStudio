"""Shared types for the execution-event seam.

The runner emits execution events as ``dict[str, Any]`` payloads matching the
wire protocol documented in ``docs/ARCHITECTURE.md`` / ``CLAUDE.md``
(``{"type": "new_type", ...}``). Everything that consumes or produces those
payloads across process boundaries (CanvasRunner, StreamingReAct, the
background worker, the WebSocket route) shares the aliases below so the
callback shape is declared once.
"""

from collections.abc import Awaitable, Callable
from typing import Any

EventPayload = dict[str, Any]

EventCallback = Callable[[EventPayload], Awaitable[None]]

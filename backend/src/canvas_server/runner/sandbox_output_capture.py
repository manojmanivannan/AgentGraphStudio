"""Sandbox output auto-capture helpers (#89).

Generalizes the plot-only sandbox artifact capture flow so a coding-enabled
agent can point an ``output_attachments`` entry at a file it already wrote in
its sandbox session by emitting ``sandbox://<path>``. The framework resolves
that path, copies the bytes out of the same per-conversation sandbox session,
and stores them as an ``AttachmentInstance``.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import tempfile
import uuid
from typing import Any

from canvas_server.sandbox import (
    SANDBOX_ACQUIRE_TIMEOUT,
    SANDBOX_WORKDIR,
    bounded_session_work,
    get_sandbox,
)

logger = logging.getLogger("canvas_server.runner.sandbox_output_capture")


def resolve_sandbox_path(path: str) -> str:
    """Resolve a sandbox file reference to an absolute container path (#89)."""
    if path.startswith("/"):
        return path
    return f"{SANDBOX_WORKDIR}/{path}"


def _read_local_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


async def read_sandbox_file(
    conversation_id: str | uuid.UUID, network_pool: str, path: str
) -> bytes | None:
    """Read bytes out of a conversation's sandbox session; never raises (#89)."""
    container_path = resolve_sandbox_path(path)

    try:
        sandbox = await get_sandbox()
        session = sandbox.get_session(
            conversation_id,
            enable_plotting=False,
            network_pool=network_pool,
        )

        async def work(active_session: Any) -> bytes | None:
            fd, local_path = tempfile.mkstemp(prefix="sandbox-output-")
            os.close(fd)
            try:
                await asyncio.to_thread(
                    active_session.copy_from_runtime,
                    container_path,
                    local_path,
                )
                return await asyncio.to_thread(_read_local_bytes, local_path)
            except Exception as exc:  # noqa: BLE001 - sandbox output capture never raises
                logger.warning(
                    "Sandbox output %r could not be read from sandbox path %r: %s",
                    path,
                    container_path,
                    exc,
                )
                return None
            finally:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(local_path)

        acquired, result = await bounded_session_work(
            session, work, timeout=SANDBOX_ACQUIRE_TIMEOUT
        )
    except Exception as exc:  # noqa: BLE001 - sandbox output capture never raises
        logger.warning(
            "Sandbox output %r could not be read from sandbox path %r: %s",
            path,
            container_path,
            exc,
        )
        return None

    if not acquired:
        logger.warning(
            "Sandbox busy — could not read sandbox output file from path %r",
            container_path,
        )
        return None
    return result

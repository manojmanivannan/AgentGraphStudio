"""Input-attachment delivery orchestrator (#88): resolves and materializes
chat-uploaded input attachments for a consuming agent right before its ReAct
loop starts.

Ties together the pure resolution matrix in ``attachment_delivery.py`` with
I/O: looking up unconsumed ``AttachmentInstance`` rows for the agent's
declared input Attachment node(s), materializing bytes into the
conversation's default-pool Docker sandbox session when the resolved method
calls for a file path, building the prompt text to inject via
``AgentFactory.build_worker_prompt``, and marking each delivered instance
consumed so a later turn in the same conversation never re-delivers it.

Never raises: a busy sandbox pool degrades to the same no-sandbox fallback
ladder ``resolve_delivery_method`` already defines, rather than failing the
turn.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import dspy

from canvas_server.attachment_delivery import (
    DeclaredInputNode,
    declared_input_nodes,
    input_attachment_field_names,
    resolve_delivery_method,
)
from canvas_server.output_extraction import file_type_to_format
from canvas_server.runner.attachment_events import announce_attachment_consumed
from canvas_server.sandbox import (
    NETWORK_POOL_DEFAULT,
    NETWORK_POOL_NETWORKED,
    SANDBOX_ACQUIRE_TIMEOUT,
    SANDBOX_WORKDIR,
    bounded_session_work,
    get_sandbox,
)

if TYPE_CHECKING:
    from canvas_server.models.canvas import AgentNode, AttachmentInstance, Canvas

logger = logging.getLogger("canvas_server.runner.input_attachment_delivery")

# Maps an ``AttachmentInstance.format`` (a short extension string, e.g.
# "png") to its image MIME type for building a data URI. Deliberately
# independent of Pillow: dspy.Image() accepts a "data:" URI string directly
# without ever touching PIL, whereas passing raw bytes requires it — see
# ``dspy.adapters.types.image.encode_image``. Falls back to "image/png" for
# an unknown/missing format.
_IMAGE_FORMAT_TO_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "webp": "image/webp",
    "svg": "image/svg+xml",
}


# Where materialized attachments live inside the sandbox container, kept
# separate from an agent's own run_code-created files.
SANDBOX_ATTACHMENT_DIR = f"{SANDBOX_WORKDIR}/attachments"


@dataclass(frozen=True)
class DeliveredAttachment:
    """One attachment instance actually delivered to the agent this turn."""

    attachment_id: uuid.UUID
    name: str
    file_type: str
    source: str
    delivery_method: str  # resolved: inline | file_path | dual | manifest_only
    sandbox_path: str | None = None
    # The filename the user actually uploaded it under (e.g. "city_name.json"),
    # distinct from `name` (the declared Attachment node's own canvas label,
    # e.g. "CityName") — #90. `None` for agent-produced attachments, which
    # were never uploaded.
    original_filename: str | None = None


@dataclass
class InputAttachmentDeliveryResult:
    delivered: list[DeliveredAttachment] = field(default_factory=list)
    input_values: dict[str, str] = field(default_factory=dict)
    # At most one image is threaded through as the ``attachment_image``
    # signature field — a reasonable single-image simplification; additional
    # declared image inputs still get their prompt text (name + path, when
    # materialized) but only the first resolved image is passed multimodally.
    # A base64 "data:" URI (see ``_image_data_uri``) — never raw bytes — so
    # ``dspy.Image(...)`` never needs Pillow to construct it.
    image_data_uri: str | None = None

    @property
    def has_any(self) -> bool:
        return bool(self.delivered)


def _image_data_uri(content: bytes, format_hint: str) -> str:
    mime = _IMAGE_FORMAT_TO_MIME.get((format_hint or "").lower(), "image/png")
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("utf-8", errors="replace")


def _manifest_block(name: str, file_type: str, size_bytes: int) -> str:
    return (
        f"[Attachment '{name}' ({file_type}, {size_bytes} bytes) — not inlinable as "
        "text and no sandbox is available to materialize it as a file.]"
    )


def _inline_text_block(name: str, file_type: str, content: bytes) -> str:
    text = _decode_text(content)
    return f"--- Attachment: {name} ({file_type}) ---\n{text}\n--- end attachment: {name} ---"


def _file_path_block(name: str, file_type: str, path: str) -> str:
    return f"Attachment '{name}' ({file_type}) is available as a file at: {path}"


def build_forwarded_attachment_text(consumed: list[DeliveredAttachment]) -> str:
    """Builds prompt text re-announcing attachments already materialized as
    sandbox file paths earlier in this run.

    A router agent commonly declares the ``consumes`` edge for a chat
    upload/output attachment itself (rather than the worker(s) it later
    delegates to), and may have no sandbox tools of its own to ever open the
    file. ``HandoffToolBuilder.transfer`` forwards this text to every
    handoff target's prompt so a downstream worker that DOES have sandbox
    access can still open the file, without requiring its own separate
    ``consumes`` edge to the same Attachment node.

    Args:
        consumed: Attachments delivered so far this run (see
            ``CanvasRunState.consumed_file_attachments``).

    Returns:
        str: Newline-joined file-path blocks, or ``""`` when nothing in
        ``consumed`` carries a ``sandbox_path`` (``inline``/``manifest_only``
        deliveries are skipped — there's nothing to forward).
    """
    blocks = [
        _file_path_block(d.name, d.file_type, d.sandbox_path)
        for d in consumed
        if d.sandbox_path is not None
    ]
    return "\n".join(blocks)


async def _materialize_in_sandbox(
    conversation_id: str | uuid.UUID, name: str, content: bytes, network_pool: str
) -> str | None:
    """Writes ``content`` into the conversation's sandbox session at
    ``SANDBOX_ATTACHMENT_DIR/<name>``, returning the container path, or
    ``None`` if the sandbox pool is saturated (never raises).

    ``name`` should be the attachment's original uploaded filename when one
    exists (see ``_attachment_filename``) so the materialized file reads
    naturally to the agent/user, rather than always being the declared
    Attachment node's own (unrelated) canvas label.

    ``network_pool`` must match the pool the consuming agent's own code
    session runs in (``NETWORK_POOL_NETWORKED`` when it has
    ``enable_network`` — mirroring ``AgentFactory``'s ``CodeProvider`` pool
    selection — else ``NETWORK_POOL_DEFAULT``), since sessions are cached
    per ``(conversation_id, network_pool)``: materializing into the wrong
    pool would put the file out of reach of the agent's own ``run_code``.
    """
    sandbox = await get_sandbox()
    session = sandbox.get_session(
        conversation_id, enable_plotting=False, network_pool=network_pool
    )
    dest_path = f"{SANDBOX_ATTACHMENT_DIR}/{name}"

    async def work(active_session: Any) -> str:
        fd, tmp_path = tempfile.mkstemp()
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
            await asyncio.to_thread(
                active_session.execute_command, f"mkdir -p {SANDBOX_ATTACHMENT_DIR}"
            )
            await asyncio.to_thread(active_session.copy_to_runtime, tmp_path, dest_path)
        finally:
            os.unlink(tmp_path)
        return dest_path

    acquired, result = await bounded_session_work(
        session, work, timeout=SANDBOX_ACQUIRE_TIMEOUT
    )
    if not acquired:
        logger.warning(
            "Sandbox busy — could not materialize attachment %r as a file", name
        )
        return None
    return result


def _attachment_filename(node: DeclaredInputNode, instance: AttachmentInstance) -> str:
    """Resolves the filename to materialize an attachment under (#90).

    Prefers the filename the user actually uploaded (``instance.original_filename``,
    e.g. "city_name.json") over the declared Attachment node's own ``name`` —
    a stable canvas label (e.g. "CityName") that is a distinct concept from
    the file's content/identity and, unlike an upload, carries no extension.
    Agent-produced (``agent_output``) instances have no upload filename, so
    fall back to ``<node.name>.<file_type-derived extension>`` (e.g.
    "CityName.json") rather than an extension-less name a tool can't infer
    the format of.
    """
    original_filename = getattr(instance, "original_filename", None)
    if original_filename:
        return original_filename
    ext = file_type_to_format(node.file_type)
    if node.name.lower().endswith(f".{ext}"):
        return node.name
    return f"{node.name}.{ext}"


async def deliver_input_attachments(
    *,
    agent_node: AgentNode,
    agent_id: uuid.UUID,
    canvas: Canvas,
    conversation_repo: Any,
    conversation_id: str | uuid.UUID,
) -> InputAttachmentDeliveryResult:
    """Resolves and materializes this agent's declared input attachments.

    Args:
        agent_node: The consuming agent node (duck-typed: ``.id``,
            ``.enable_coding``, ``.enable_network``).
        agent_id: The consuming agent's node id.
        canvas: The current canvas (duck-typed: ``.edges``,
            ``.attachment_nodes``, ``.tool_nodes``).
        conversation_repo: Repo exposing
            ``get_unconsumed_input_attachments(conversation_id, node_ids)``
            and ``mark_attachment_consumed(attachment_id)``.
        conversation_id: The current conversation id.

    Returns:
        InputAttachmentDeliveryResult: Empty (``has_any is False``) when the
        agent has no declared input nodes, or nothing unconsumed is waiting —
        callers should skip ``agent_start``/``attachment_consumed`` entirely
        in that case.
    """
    edges = getattr(canvas, "edges", None) or []
    attachment_nodes = getattr(canvas, "attachment_nodes", None) or []

    declared = declared_input_nodes(edges, attachment_nodes, agent_id)
    if not declared:
        return InputAttachmentDeliveryResult()

    node_ids = [node.id for node in declared]
    instances: list[AttachmentInstance] = await conversation_repo.get_unconsumed_input_attachments(
        conversation_id, node_ids
    )
    if not instances:
        return InputAttachmentDeliveryResult()

    declared_by_id = {node.id: node for node in declared}
    # `file_path` is honored regardless of THIS agent's own sandbox tools
    # (`enable_coding`/`enable_network`/`tool_access`): a router with none of
    # those may still be the declared consumer, and forwards the resulting
    # path to whichever downstream worker it hands off to (see
    # `build_forwarded_attachment_text` / `HandoffToolBuilder.transfer`).
    # `_materialize_in_sandbox` already degrades gracefully below when the
    # sandbox pool itself is unavailable/busy.
    has_sandbox = True
    # Mirrors AgentFactory's own CodeProvider pool selection so a materialized
    # file lands in the same session the agent's `run_code`/`pip_install`
    # tools use.
    network_pool = (
        NETWORK_POOL_NETWORKED
        if getattr(agent_node, "enable_network", False)
        else NETWORK_POOL_DEFAULT
    )

    result = InputAttachmentDeliveryResult()
    input_field_names = input_attachment_field_names(declared)

    for instance in instances:
        attachment_node_id = instance.attachment_node_id
        if attachment_node_id is None:
            continue
        node = declared_by_id.get(attachment_node_id)
        if node is None:
            continue

        method = resolve_delivery_method(
            file_type=node.file_type,
            delivery_method=node.delivery_method,
            has_sandbox=has_sandbox,
        )

        sandbox_path: str | None = None
        if method in ("file_path", "dual"):
            sandbox_path = await _materialize_in_sandbox(
                conversation_id, _attachment_filename(node, instance), instance.content, network_pool
            )
            if sandbox_path is None:
                # Sandbox saturated: degrade exactly like the no-sandbox case.
                method = resolve_delivery_method(
                    file_type=node.file_type,
                    delivery_method=node.delivery_method,
                    has_sandbox=False,
                )

        if method == "manifest_only":
            result.input_values[input_field_names[node.id]] = _manifest_block(
                node.name, node.file_type, len(instance.content)
            )
        elif method == "inline":
            if node.file_type == "image":
                if result.image_data_uri is None:
                    result.image_data_uri = _image_data_uri(
                        instance.content, getattr(instance, "format", "png")
                    )
            else:
                result.input_values[input_field_names[node.id]] = _decode_text(instance.content)
        elif method == "file_path":
            result.input_values[input_field_names[node.id]] = sandbox_path or ""
        elif method == "dual" and result.image_data_uri is None:
            result.image_data_uri = _image_data_uri(
                instance.content, getattr(instance, "format", "png")
            )

        result.delivered.append(
            DeliveredAttachment(
                attachment_id=instance.id,
                name=node.name,
                file_type=node.file_type,
                source=instance.source,
                delivery_method=method,
                sandbox_path=sandbox_path,
                original_filename=getattr(instance, "original_filename", None),
            )
        )
        await conversation_repo.mark_attachment_consumed(instance.id)

    return result


async def deliver_and_announce_input_attachments(
    *,
    agent_node: AgentNode,
    agent_id: uuid.UUID,
    canvas: Any,
    conversation_repo: Any,
    conversation_id: str | uuid.UUID,
    conversation_service: Any,
    send_event: Any,
    run_id: uuid.UUID | None,
    user_prompt: str,
    emit_agent_start: bool,
) -> tuple[str, dict[str, Any], list[DeliveredAttachment]]:
    """Shared entry point for delivering input attachments right before an
    agent's ReAct loop starts (#88): resolves/materializes via
    ``deliver_input_attachments``, optionally emits ``agent_start``, then
    announces ``attachment_consumed`` for each delivered instance.

    Both "entry-point" call sites that never otherwise emit ``agent_start``
    themselves (``ExecutionStrategy._run_worker``/``RouterExecution.execute``
    in ``execution.py``) and the handoff-delegation call site
    (``HandoffToolBuilder.transfer`` in ``handoff.py``, which already emits
    ``agent_start`` unconditionally) share this one function — only
    ``emit_agent_start`` differs between them — instead of each
    reimplementing the resolve → emit → announce → augment-prompt shape.

    A no-op (returns ``user_prompt`` unchanged, no extra kwargs, empty
    delivered list) when the agent has no declared input Attachment node(s),
    or nothing unconsumed is waiting.

    Returns:
        tuple[str, dict[str, Any], list[DeliveredAttachment]]: The (possibly
        attachment-augmented) prompt, extra ``aforward`` kwargs for declared
        attachment input fields (plus ``attachment_image`` when resolved),
        and the attachments delivered this call — callers should fold
        ``sandbox_path``-bearing entries into
        ``CanvasRunState.consumed_file_attachments`` so a later handoff can
        forward them via ``build_forwarded_attachment_text``.
    """
    result = await deliver_input_attachments(
        agent_node=agent_node,
        agent_id=agent_id,
        canvas=canvas,
        conversation_repo=conversation_repo,
        conversation_id=conversation_id,
    )
    if not result.has_any:
        return user_prompt, {}, []

    if emit_agent_start:
        await send_event(
            {
                "type": "agent_start",
                "agent": agent_node.name,
                "agentType": getattr(agent_node, "agent_type", None),
                "node_id": str(agent_id),
            }
        )

    for delivered in result.delivered:
        await announce_attachment_consumed(
            send_event=send_event,
            conversation_service=conversation_service,
            agent_name=agent_node.name,
            agent_id=agent_id,
            attachment_id=delivered.attachment_id,
            name=delivered.name,
            file_type=delivered.file_type,
            source=delivered.source,
            delivery_method=delivered.delivery_method,
            conversation_id=conversation_id,
            run_id=run_id,
            original_filename=delivered.original_filename,
        )

    extra_kwargs: dict[str, Any] = dict(result.input_values)
    if result.image_data_uri is not None:
        extra_kwargs["attachment_image"] = dspy.Image(result.image_data_uri)

    return user_prompt, extra_kwargs, result.delivered

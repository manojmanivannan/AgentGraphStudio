"""Output-extraction mechanism (#78/#86): validates and shapes an agent's
``output_attachments`` structured output field against its declared *output*
Attachment node(s) — the canvas nodes wired to the agent via a ``produces``
edge (#84) — before anything is stored as an ``AttachmentInstance``.

This module is pure (no I/O, no DB access) so it can be unit-tested in
isolation; ``runner/execution.py`` wires it into the actual storage/event
pipeline. Extraction happens once, post-loop, at ``extract()`` time — never
per ReAct iteration — so nothing here ever raises: a mismatch is recorded as
a tool-output-style error string (mirroring the
``f"Execution error in {tool}: {err}"`` convention already used for failed
tool calls in ``streaming_react.py``) and the offending item is simply
skipped, never crashing the run.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

_FILE_TYPE_TO_FORMAT = {
    "text": "txt",
    "csv": "csv",
    "json": "json",
    "python": "py",
    "yaml": "yaml",
    "pdf": "pdf",
    "image": "png",
    "binary": "bin",
}


@dataclass(frozen=True)
class DeclaredOutputNode:
    """A declared *output* Attachment node slot wired to an agent (#76/#84)."""

    id: uuid.UUID
    name: str
    file_type: str


@dataclass(frozen=True)
class ExtractedAttachment:
    """A validated attachment draft, ready to be persisted as an ``AttachmentInstance``."""

    node_id: uuid.UUID
    name: str
    file_type: str
    content: str


@dataclass
class ExtractionOutcome:
    attachments: list[ExtractedAttachment] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def declared_output_nodes(
    edges: list[Any], attachment_nodes: list[Any], agent_id: uuid.UUID
) -> list[DeclaredOutputNode]:
    """Resolves an agent's declared output Attachment node(s).

    An Attachment node is a declared *output* slot for ``agent_id`` when a
    ``produces`` edge connects the agent (source) to the attachment node
    (target) — see the Attachment node model (#84). Accepts duck-typed
    edge/node objects (ORM models or plain ``SimpleNamespace``s in tests) —
    only ``.source_node_id``/``.target_node_id``/``.edge_type`` and
    ``.id``/``.name``/``.file_type`` are read.

    Args:
        edges: The canvas's edges.
        attachment_nodes: The canvas's Attachment nodes.
        agent_id: The producing agent's node id.

    Returns:
        list[DeclaredOutputNode]: One entry per wired output slot, in edge order.
    """
    attachment_nodes_by_id = {node.id: node for node in attachment_nodes}
    declared: list[DeclaredOutputNode] = []
    for edge in edges:
        if edge.edge_type != "produces" or edge.source_node_id != agent_id:
            continue
        node = attachment_nodes_by_id.get(edge.target_node_id)
        if node is None:
            continue
        declared.append(
            DeclaredOutputNode(id=node.id, name=node.name, file_type=node.file_type)
        )
    return declared


def _content_sanity_check(file_type: str, content: str) -> str | None:
    """A soft content sanity check. Returns an error detail, or ``None`` when OK."""
    if not content or not content.strip():
        return "content is empty"
    if file_type == "json":
        try:
            json.loads(content)
        except (ValueError, TypeError):
            return "declared json but content is not valid JSON"
    return None


def extract_output_attachments(
    raw_items: list[Any] | None,
    declared_nodes: list[DeclaredOutputNode],
) -> ExtractionOutcome:
    """Validates raw ``output_attachments`` entries against declared slots.

    Each raw entry is expected to be a dict with ``name``, ``file_type``, and
    ``content`` keys — the shape the LM is instructed to fill in via the
    ``output_attachments`` DSPy OutputField (see ``AgentFactory.build_signature``).
    An entry is accepted only when its name matches a declared slot, its
    file_type matches that slot's configured type, and it passes a soft
    content sanity check (non-empty; valid JSON when ``file_type == "json"``).

    Never raises. Invalid entries are dropped and recorded in ``.errors`` as
    tool-output-style messages; valid entries land in ``.attachments``. One
    bad entry never short-circuits the rest of the batch.

    Args:
        raw_items: The raw list from ``result.output_attachments``, or ``None``.
        declared_nodes: The agent's declared output Attachment node slots.

    Returns:
        ExtractionOutcome: Validated attachments plus any error messages.
    """
    declared_by_name = {node.name: node for node in declared_nodes}
    attachments: list[ExtractedAttachment] = []
    errors: list[str] = []

    for item in raw_items or []:
        if not isinstance(item, dict):
            errors.append(
                f"Execution error in output_attachments: malformed entry {item!r} (expected an object)."
            )
            continue

        name = str(item.get("name") or "").strip()
        file_type = str(item.get("file_type") or "").strip()
        raw_content = item.get("content")
        content = raw_content if isinstance(raw_content, str) else ("" if raw_content is None else str(raw_content))

        if not name or not file_type:
            errors.append(
                "Execution error in output_attachments: malformed entry "
                f"(missing name/file_type): {item!r}."
            )
            continue

        node = declared_by_name.get(name)
        if node is None:
            errors.append(
                f"Execution error in output_attachments: {name!r} does not match any "
                "declared output Attachment node on this agent."
            )
            continue

        if node.file_type != file_type:
            errors.append(
                f"Execution error in output_attachments: {name!r} is wired as "
                f"{node.file_type!r} on the canvas but the agent emitted {file_type!r}."
            )
            continue

        sanity_error = _content_sanity_check(file_type, content)
        if sanity_error is not None:
            errors.append(
                f"Execution error in output_attachments: {name!r} {sanity_error}."
            )
            continue

        attachments.append(
            ExtractedAttachment(node_id=node.id, name=name, file_type=file_type, content=content)
        )

    return ExtractionOutcome(attachments=attachments, errors=errors)


def file_type_to_format(file_type: str) -> str:
    """Maps a declared ``file_type`` to a storage extension/format string.

    Mirrors the reverse mapping in ``attachment_matching.guess_file_type``.
    Unknown/freeform file types fall back to ``"bin"``.
    """
    return _FILE_TYPE_TO_FORMAT.get(file_type, "bin")

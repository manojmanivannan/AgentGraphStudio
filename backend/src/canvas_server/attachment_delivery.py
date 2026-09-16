"""Attachment delivery resolution (#88): decides how a chat-uploaded input
attachment is represented to a consuming agent at runtime — inline text/
image, a materialized sandbox file path, both ("dual", images only), or an
opaque manifest note when nothing else is feasible.

This module is pure (no I/O, no DB, no sandbox access) so the resolution
matrix can be unit-tested in isolation; ``runner/`` wires it into the actual
sandbox-materialization + event-emission pipeline. It mirrors the shape of
``output_extraction.py`` (declared-node lookup + a pure decision function)
and reuses the ``READABLE_TYPES``/``UNREADABLE_TYPES`` taxonomy locked in by
the ``prototype/runtime-representation`` design spike for issue #81.

Design (see ``backend/scripts/prototype_runtime_representation/logic.py``
for the full reaction-session writeup this is derived from):

- ``image`` file_type is always delivered as ``"dual"`` (multimodal image
  block *and* a materialized sandbox path) when the consuming agent has
  sandbox access — path alone would lose vision reasoning, inline alone
  would lose tool access. Without a sandbox it degrades to ``"inline"``
  (image block only).
- Any other type "wants" a file path when the node's ``delivery_method``
  preference is ``"file_path"``, OR when the type can never truly be
  inlined as text (``binary``/``pdf``) regardless of preference.
  - If the agent has sandbox access, that preference is honored:
    ``"file_path"``.
  - Without a sandbox, a path is meaningless: readable types fall back to
    plain ``"inline"`` text; unreadable types fall back to ``"manifest_only"``
    (no dedicated tool needed — the agent just gets a short note it can
    surface to the user).
- Otherwise (inline preference, readable type) it is always ``"inline"``,
  with no sandbox involvement at all.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

READABLE_TYPES = {"csv", "json", "text", "yaml", "python"}
UNREADABLE_TYPES = {"binary", "pdf"}


@dataclass(frozen=True)
class DeclaredInputNode:
    """A declared *input* Attachment node slot wired to an agent (#84/#88)."""

    id: uuid.UUID
    name: str
    file_type: str
    delivery_method: str


def declared_input_nodes(
    edges: list[Any], attachment_nodes: list[Any], agent_id: uuid.UUID
) -> list[DeclaredInputNode]:
    """Resolves an agent's declared input Attachment node(s).

    An Attachment node is a declared *input* slot for ``agent_id`` when a
    ``consumes`` edge connects the attachment node (source) to the agent
    (target) — see the Attachment node model (#84). Accepts duck-typed
    edge/node objects (ORM models or plain ``SimpleNamespace``s in tests) —
    only ``.source_node_id``/``.target_node_id``/``.edge_type`` and
    ``.id``/``.name``/``.file_type``/``.delivery_method`` are read.

    Args:
        edges: The canvas's edges.
        attachment_nodes: The canvas's Attachment nodes.
        agent_id: The consuming agent's node id.

    Returns:
        list[DeclaredInputNode]: One entry per wired input slot, in edge order.
    """
    attachment_nodes_by_id = {node.id: node for node in attachment_nodes}
    declared: list[DeclaredInputNode] = []
    for edge in edges:
        if edge.edge_type != "consumes" or edge.target_node_id != agent_id:
            continue
        node = attachment_nodes_by_id.get(edge.source_node_id)
        if node is None:
            continue
        declared.append(
            DeclaredInputNode(
                id=node.id,
                name=node.name,
                file_type=node.file_type,
                delivery_method=node.delivery_method,
            )
        )
    return declared


def input_attachment_field_names(
    nodes: list[DeclaredInputNode],
) -> dict[uuid.UUID, str]:
    """Return stable, DSPy-safe input-field names for declared attachments."""
    reserved_names = {
        "user_request",
        "history",
        "attachment_image",
        "process_result",
        "output_attachments",
    }
    used_names = set(reserved_names)
    names: dict[uuid.UUID, str] = {}

    for node in nodes:
        snake_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", node.name)
        base_name = re.sub(r"[^a-zA-Z0-9]+", "_", snake_case).strip("_").lower()
        if not base_name or base_name[0].isdigit():
            base_name = f"attachment_{base_name}".rstrip("_")

        candidate = base_name
        suffix = 2
        while candidate in used_names:
            candidate = f"{base_name}_{suffix}"
            suffix += 1

        used_names.add(candidate)
        names[node.id] = candidate

    return names


def agent_has_sandbox_access(agent: Any, edges: list[Any], tool_nodes: list[Any]) -> bool:
    """Whether ``agent`` has any way to reach the Docker sandbox at runtime.

    True when the agent has coding or network tools enabled (both use
    ``CodeProvider``, which runs in a sandbox session), or when it's wired
    via a ``tool_access`` edge to at least one custom Tool node — those
    always execute in the conversation's default-pool sandbox session
    regardless of the owning agent's own flags (see ``tool_factory.py``).

    Args:
        agent: The consuming agent node (duck-typed: ``.id``,
            ``.enable_coding``, ``.enable_network``).
        edges: The canvas's edges.
        tool_nodes: The canvas's custom Tool nodes.

    Returns:
        bool: Whether the agent has sandbox access.
    """
    if getattr(agent, "enable_coding", False) or getattr(agent, "enable_network", False):
        return True
    tool_node_ids = {node.id for node in tool_nodes}
    return any(
        edge.edge_type == "tool_access"
        and edge.source_node_id == agent.id
        and edge.target_node_id in tool_node_ids
        for edge in edges
    )


def resolve_delivery_method(*, file_type: str, delivery_method: str, has_sandbox: bool) -> str:
    """Resolves the actual delivery method for one input attachment.

    Args:
        file_type: The attachment's declared type (e.g. ``"csv"``, ``"image"``).
        delivery_method: The Attachment node's configured preference
            (``"inline"`` or ``"file_path"``).
        has_sandbox: Whether the consuming agent has sandbox access
            (see ``agent_has_sandbox_access``).

    Returns:
        str: One of ``"inline"``, ``"file_path"``, ``"dual"`` (image only),
        or ``"manifest_only"``.
    """
    if file_type == "image":
        return "dual" if has_sandbox else "inline"

    wants_file_path = delivery_method == "file_path" or file_type in UNREADABLE_TYPES
    if wants_file_path:
        if has_sandbox:
            return "file_path"
        return "manifest_only" if file_type in UNREADABLE_TYPES else "inline"

    return "inline"

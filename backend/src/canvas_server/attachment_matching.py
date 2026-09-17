from __future__ import annotations

import uuid
from dataclasses import dataclass

_EXTENSION_TO_TYPE = {
    "csv": "csv",
    "json": "json",
    "txt": "text",
    "md": "text",
    "py": "python",
    "yaml": "yaml",
    "yml": "yaml",
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "bmp": "image",
    "webp": "image",
    "svg": "image",
    "pdf": "pdf",
}


@dataclass(frozen=True)
class DeclaredInputNode:
    id: uuid.UUID
    file_type: str


@dataclass(frozen=True)
class MatchOutcome:
    filename: str
    file_type: str
    node_id: uuid.UUID | None
    error: str | None


def guess_file_type(filename: str) -> str:
    parts = filename.rsplit(".", 1)
    extension = parts[1].lower() if len(parts) == 2 and parts[1] else ""
    return _EXTENSION_TO_TYPE.get(extension, "binary")


def match_uploads_to_nodes(
    filenames: list[str], declared_nodes: list[DeclaredInputNode]
) -> list[MatchOutcome]:
    used: set[uuid.UUID] = set()
    outcomes: list[MatchOutcome] = []

    for filename in filenames:
        detected_type = guess_file_type(filename)
        candidates = [
            node
            for node in declared_nodes
            if node.file_type == detected_type and node.id not in used
        ]

        if not candidates:
            outcomes.append(
                MatchOutcome(
                    filename=filename,
                    file_type=detected_type,
                    node_id=None,
                    error=(
                        "No input attachment node on this agent accepts "
                        f"file type '{detected_type}'"
                    ),
                )
            )
            continue

        if len(candidates) > 1:
            outcomes.append(
                MatchOutcome(
                    filename=filename,
                    file_type=detected_type,
                    node_id=None,
                    error=(
                        "Ambiguous: multiple input attachment nodes accept "
                        f"file type '{detected_type}'"
                    ),
                )
            )
            continue

        matched = candidates[0]
        used.add(matched.id)
        outcomes.append(
            MatchOutcome(
                filename=filename,
                file_type=detected_type,
                node_id=matched.id,
                error=None,
            )
        )

    return outcomes

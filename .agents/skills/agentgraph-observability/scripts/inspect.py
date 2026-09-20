#!/usr/bin/env python3
"""Run read-only AgentGraphStudio observability queries through Docker Compose."""

from __future__ import annotations

import argparse
import subprocess
import sys
import uuid


QUERIES = {
    "canvas": """
SELECT id, name, owner_id, created_at, updated_at
FROM canvases WHERE name = :'name' ORDER BY updated_at DESC;
""",
    "layout": """
SELECT 'agent' AS kind, id, name, agent_type AS detail, position_x, position_y
FROM agent_nodes WHERE canvas_id = :'id'
UNION ALL
SELECT 'tool', id, name, CASE WHEN requires_approval THEN 'approval' ELSE '' END,
       position_x, position_y
FROM tool_nodes WHERE canvas_id = :'id'
UNION ALL
SELECT 'attachment', id, name, file_type || '/' || delivery_method,
       position_x, position_y
FROM attachment_nodes WHERE canvas_id = :'id'
ORDER BY kind, name, id;

SELECT id, source_node_id, target_node_id, edge_type
FROM edges WHERE canvas_id = :'id' ORDER BY edge_type, id;
""",
    "conversation": """
SELECT c.id, c.name, c.status, c.canvas_id, cv.name AS canvas_name,
       c.created_at, c.updated_at,
       (SELECT count(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count,
       (SELECT count(*) FROM durable_runs r WHERE r.conversation_id = c.id) AS run_count
FROM conversations c JOIN canvases cv ON cv.id = c.canvas_id
WHERE c.id = :'id';
""",
    "messages": """
SELECT id, role, content, agent_name, node_id, event_type, tool, args, created_at
FROM messages WHERE conversation_id = :'id' ORDER BY created_at, id;
""",
    "runs": """
SELECT id, status, target_agent_id, attempt_count, replay_cursor,
       started_at, completed_at, failed_at, final_error, created_at, updated_at
FROM durable_runs WHERE conversation_id = :'id' ORDER BY created_at, id;
""",
    "events": """
SELECT sequence, event_type, payload, created_at
FROM durable_run_events WHERE run_id = :'id' ORDER BY sequence;
""",
}


def valid_uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"invalid UUID: {value}") from error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    canvas = subparsers.add_parser("canvas", help="find an exact canvas name")
    canvas.add_argument("--name", required=True)

    for command in ("layout", "conversation", "messages", "runs", "events"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--id", required=True, type=valid_uuid)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    variable = "name" if args.command == "canvas" else "id"
    value = getattr(args, variable)
    command = [
        "docker", "compose", "exec", "-T", "postgres", "psql",
        "-X", "-v", "ON_ERROR_STOP=1", "-U", "canvas", "-d", "canvas_db",
        "-P", "pager=off", "-v", f"{variable}={value}",
    ]
    result = subprocess.run(command, input=QUERIES[args.command], text=True)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
---
name: agentgraph-observability
description: 'Inspect AgentGraphStudio PostgreSQL records and MLflow traces for canvas designs, conversation histories, durable runs, events, and attachments. Use when asked to fetch a canvas by name, inspect its node layout or edges, retrieve a conversation by UUID, read its messages, diagnose an agent run, or correlate execution with MLflow.'
argument-hint: 'canvas name or conversation UUID'
---

# AgentGraphStudio Observability

Use read-only queries against the running Docker Compose services. Never update or delete records.

## Quick Start

1. Work from the repository root.
2. Check services with `docker compose ps postgres mlflow backend`.
3. Run `python3 .github/skills/agentgraph-observability/scripts/inspect.py --help`.

## Canvas By Name

Find exact matches first. Do not silently choose one when names are duplicated.

```bash
python3 .github/skills/agentgraph-observability/scripts/inspect.py canvas --name "Canvas Name"
```

After resolving the canvas UUID, inspect its design:

```bash
python3 .github/skills/agentgraph-observability/scripts/inspect.py layout --id <canvas-uuid>
```

Report node coordinates and edge direction so the canvas layout can be reconstructed. Fetch agent instructions or tool code only when relevant to the request because they may be lengthy or sensitive.

## Conversation By ID

Fetch the conversation and parent canvas:

```bash
python3 .github/skills/agentgraph-observability/scripts/inspect.py conversation --id <conversation-uuid>
```

Return a metadata summary first. Retrieve message bodies only when the user asks for the history or message content:

```bash
python3 .github/skills/agentgraph-observability/scripts/inspect.py messages --id <conversation-uuid>
```

For execution diagnosis, list runs and then events for the selected run:

```bash
python3 .github/skills/agentgraph-observability/scripts/inspect.py runs --id <conversation-uuid>
python3 .github/skills/agentgraph-observability/scripts/inspect.py events --id <run-uuid>
```

Do not print `durable_runs.prompt`, `final_result`, attachment binary content, message `content`, or tool `args` unless requested. Summarize errors and event types before exposing full payloads.

## MLflow Correlation

Use the backend's installed client:

```python
import mlflow

mlflow.set_tracking_uri("http://mlflow:5000")
experiment = mlflow.get_experiment_by_name("canvas-agents")
traces = mlflow.search_traces(locations=[experiment.experiment_id])
```

Inspect root `canvas_run` spans for `canvas_id`, `canvas_name`, `num_agents`, and `entry_agent`; agent spans may include `agent_node_id`, `agent_type`, and `canvas_name`. Narrow candidates using the durable run's `started_at`/`completed_at` window.

Current instrumentation does not attach `conversation_id` or durable `run_id` to MLflow spans. Treat canvas-and-time matching as correlation, not an exact join, and say so in the result.

## Output

Identify the queried canvas/conversation and whether it was found. Present concise metadata and counts first, then requested details in chronological or graph order. Mention ambiguous canvas names, missing records, unhealthy services, and inexact MLflow matches explicitly.
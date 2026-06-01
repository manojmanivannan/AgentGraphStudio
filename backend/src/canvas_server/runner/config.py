"""Per-run context data — the ephemeral state that changes with each run() invocation."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import dspy


@dataclass
class RunContext:
    """Holds everything that varies per call to CanvasRunner.run().

    Extracted as a single dataclass to keep execution strategy signatures simple
    — strategies take ``(agent_id, ctx)`` instead of half a dozen keyword args.
    """

    user_prompt: str
    send_event: Callable[..., Awaitable[None]]
    target_agent_id: uuid.UUID | None = None

    # Conversation history — both the plain-text summary and the structured
    # DSPy history object.  Either or both may be None when history is off.
    history_text: str = ""
    dspy_history: dspy.History | None = None

    # Set of agent node IDs that have conversation history enabled; used to
    # filter intermediate sub-agent responses from the formatted history.
    history_enabled_node_ids: set[uuid.UUID] = field(default_factory=set)

    # Primary agent ID — the "entry point" for memory auto-store after run().
    primary_agent_id: uuid.UUID | None = None
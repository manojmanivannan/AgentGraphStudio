"""EdgeGraph — navigates the canvas edge graph."""

from __future__ import annotations

import logging
import uuid

logger = logging.getLogger("canvas_server.runner.edge_graph")


class EdgeGraph:
    """Pure navigation over a canvas's edges.

    Stateless after construction — the edge list is frozen at setup time.
    Answers questions like "what agents does this agent hand off to?" and
    "what tools can this agent access?"
    """

    def __init__(self, edges: list):
        self._edges = edges

    def get_handoff_targets(self, agent_id: uuid.UUID) -> list[uuid.UUID]:
        """Return the node IDs that *agent_id* can hand off to, in edge order."""
        return [
            edge.target_node_id
            for edge in self._edges
            if edge.source_node_id == agent_id and edge.edge_type == "handoff"
        ]

    def get_first_handoff_target(self, agent_id: uuid.UUID) -> uuid.UUID | None:
        """Return the first handoff target for *agent_id*, or ``None``."""
        targets = self.get_handoff_targets(agent_id)
        return targets[0] if targets else None

    def build_handoff_map(
        self, agent_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[uuid.UUID]]:
        """Return ``{agent_id: [handoff_target_ids]}`` for every agent in *agent_ids*."""
        return {aid: self.get_handoff_targets(aid) for aid in agent_ids}

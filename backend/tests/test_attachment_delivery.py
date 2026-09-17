import uuid
from types import SimpleNamespace

import pytest

from canvas_server.attachment_delivery import (
    DeclaredInputNode,
    agent_has_sandbox_access,
    declared_input_nodes,
    resolve_delivery_method,
)


def _edge(edge_type: str, source_node_id, target_node_id):
    return SimpleNamespace(
        edge_type=edge_type, source_node_id=source_node_id, target_node_id=target_node_id
    )


def _attachment_node(node_id, name="Data", file_type="csv", delivery_method="inline"):
    return SimpleNamespace(id=node_id, name=name, file_type=file_type, delivery_method=delivery_method)


class TestDeclaredInputNodes:
    def test_finds_nodes_wired_via_consumes_edge_with_agent_as_target(self):
        agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        node = _attachment_node(node_id, name="Report", file_type="csv", delivery_method="file_path")
        edges = [_edge("consumes", node_id, agent_id)]

        result = declared_input_nodes(edges, [node], agent_id)

        assert result == [
            DeclaredInputNode(
                id=node_id, name="Report", file_type="csv", delivery_method="file_path"
            )
        ]

    def test_ignores_produces_edges_and_edges_for_other_agents(self):
        agent_id = uuid.uuid4()
        other_agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        node = _attachment_node(node_id)
        edges = [
            _edge("produces", agent_id, node_id),
            _edge("consumes", node_id, other_agent_id),
        ]

        assert declared_input_nodes(edges, [node], agent_id) == []

    def test_ignores_consumes_edge_pointing_at_unknown_node(self):
        agent_id = uuid.uuid4()
        edges = [_edge("consumes", uuid.uuid4(), agent_id)]

        assert declared_input_nodes(edges, [], agent_id) == []

    def test_returns_multiple_declared_nodes_in_edge_order(self):
        agent_id = uuid.uuid4()
        node_a = _attachment_node(uuid.uuid4(), name="A")
        node_b = _attachment_node(uuid.uuid4(), name="B")
        edges = [
            _edge("consumes", node_a.id, agent_id),
            _edge("consumes", node_b.id, agent_id),
        ]

        result = declared_input_nodes(edges, [node_a, node_b], agent_id)

        assert [n.name for n in result] == ["A", "B"]


class TestAgentHasSandboxAccess:
    def test_true_when_coding_enabled(self):
        agent = SimpleNamespace(id=uuid.uuid4(), enable_coding=True, enable_network=False)
        assert agent_has_sandbox_access(agent, edges=[], tool_nodes=[]) is True

    def test_true_when_network_enabled(self):
        agent = SimpleNamespace(id=uuid.uuid4(), enable_coding=False, enable_network=True)
        assert agent_has_sandbox_access(agent, edges=[], tool_nodes=[]) is True

    def test_true_when_wired_to_a_custom_tool_node(self):
        agent = SimpleNamespace(id=uuid.uuid4(), enable_coding=False, enable_network=False)
        tool_id = uuid.uuid4()
        edges = [_edge("tool_access", agent.id, tool_id)]
        tool_nodes = [SimpleNamespace(id=tool_id)]

        assert agent_has_sandbox_access(agent, edges=edges, tool_nodes=tool_nodes) is True

    def test_false_when_no_coding_no_network_no_tool_access(self):
        agent = SimpleNamespace(id=uuid.uuid4(), enable_coding=False, enable_network=False)
        assert agent_has_sandbox_access(agent, edges=[], tool_nodes=[]) is False

    def test_false_when_tool_access_edge_points_at_non_tool_node(self):
        agent = SimpleNamespace(id=uuid.uuid4(), enable_coding=False, enable_network=False)
        other_id = uuid.uuid4()
        edges = [_edge("tool_access", agent.id, other_id)]

        assert agent_has_sandbox_access(agent, edges=edges, tool_nodes=[]) is False


class TestResolveDeliveryMethod:
    @pytest.mark.parametrize(
        "file_type,delivery_method,has_sandbox,expected",
        [
            # Image is always "dual" with a sandbox, "inline" (image block only) without.
            ("image", "inline", True, "dual"),
            ("image", "file_path", True, "dual"),
            ("image", "inline", False, "inline"),
            ("image", "file_path", False, "inline"),
            # Readable types: inline preference always stays inline.
            ("csv", "inline", True, "inline"),
            ("csv", "inline", False, "inline"),
            ("json", "inline", True, "inline"),
            ("text", "inline", False, "inline"),
            ("yaml", "inline", True, "inline"),
            ("python", "inline", True, "inline"),
            # Readable types: file_path preference honored only with a sandbox;
            # falls back to inline text without one.
            ("csv", "file_path", True, "file_path"),
            ("csv", "file_path", False, "inline"),
            # Unreadable types (binary/pdf) always want file_path regardless of
            # node preference; fall back to manifest_only without a sandbox.
            ("binary", "inline", True, "file_path"),
            ("binary", "file_path", True, "file_path"),
            ("binary", "inline", False, "manifest_only"),
            ("pdf", "inline", True, "file_path"),
            ("pdf", "inline", False, "manifest_only"),
        ],
    )
    def test_resolution_matrix(self, file_type, delivery_method, has_sandbox, expected):
        assert (
            resolve_delivery_method(
                file_type=file_type, delivery_method=delivery_method, has_sandbox=has_sandbox
            )
            == expected
        )

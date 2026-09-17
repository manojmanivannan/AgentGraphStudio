import uuid

import pytest

from canvas_server.exceptions import CanvasNotFoundError
from canvas_server.models.api import (
    AgentNodeInput,
    AttachmentNodeInput,
    EdgeInput,
    ToolNodeInput,
)
from canvas_server.models.auth import User
from canvas_server.repos.canvas_repo import CanvasRepo


class TestCanvasRepoCreate:
    async def test_create_empty(self, test_session, test_user):
        repo = CanvasRepo(test_session)
        canvas = await repo.create("Empty", owner_id=test_user.id)
        assert canvas.name == "Empty"
        assert canvas.id is not None
        assert canvas.owner_id == test_user.id
        assert canvas.agent_nodes == []
        assert canvas.tool_nodes == []
        assert canvas.edges == []

    async def test_create_default_name(self, test_session, test_user):
        repo = CanvasRepo(test_session)
        canvas = await repo.create(owner_id=test_user.id)
        assert canvas.name == "Untitled Canvas"


class TestCanvasRepoGet:
    async def test_get_existing(self, blank_canvas, test_session):
        repo = CanvasRepo(test_session)
        canvas = await repo.get(blank_canvas.id)
        assert canvas is not None
        assert canvas.id == blank_canvas.id
        assert canvas.name == blank_canvas.name

    async def test_get_missing(self, test_session):
        repo = CanvasRepo(test_session)
        canvas = await repo.get(uuid.uuid4())
        assert canvas is None

    async def test_get_or_404_existing(self, blank_canvas, test_session):
        repo = CanvasRepo(test_session)
        canvas = await repo.get_or_404(blank_canvas.id)
        assert canvas.id == blank_canvas.id

    async def test_get_or_404_missing(self, test_session):
        repo = CanvasRepo(test_session)
        with pytest.raises(CanvasNotFoundError):
            await repo.get_or_404(uuid.uuid4())


class TestCanvasRepoList:
    async def test_list_empty(self, test_session):
        repo = CanvasRepo(test_session)
        canvases = await repo.list_all()
        assert canvases == []

    async def test_list_with_canvases(self, blank_canvas, test_session):
        repo = CanvasRepo(test_session)
        canvases = await repo.list_all()
        assert len(canvases) == 1
        assert canvases[0].id == blank_canvas.id

    async def test_list_ordered_by_updated(self, test_session, test_user):
        repo = CanvasRepo(test_session)
        c1 = await repo.create("First", owner_id=test_user.id)
        await repo.create("Second", owner_id=test_user.id)
        await repo.save_nodes_and_edges(c1.id, "First Updated", [], [], [])
        canvases = await repo.list_all()
        assert canvases[0].id == c1.id

    async def test_list_for_owner_scopes_to_user(self, test_session, test_user):
        repo = CanvasRepo(test_session)
        await repo.create("Mine", owner_id=test_user.id)
        other = User(email=f"other_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        test_session.add(other)
        await test_session.flush()
        await repo.create("Theirs", owner_id=other.id)
        await test_session.commit()

        mine = await repo.list_for_owner(test_user.id)
        assert [c.name for c in mine] == ["Mine"]

    async def test_get_for_owner_returns_owned_canvas(self, blank_canvas, test_session):
        repo = CanvasRepo(test_session)
        canvas = await repo.get_for_owner(blank_canvas.id, blank_canvas.owner_id)
        assert canvas is not None
        assert canvas.id == blank_canvas.id

    async def test_get_for_owner_returns_none_for_foreign_canvas(
        self, blank_canvas, test_session
    ):
        repo = CanvasRepo(test_session)
        foreign = await repo.get_for_owner(blank_canvas.id, uuid.uuid4())
        assert foreign is None

    async def test_get_for_owner_returns_none_for_missing_canvas(self, test_session, test_user):
        repo = CanvasRepo(test_session)
        assert await repo.get_for_owner(uuid.uuid4(), test_user.id) is None


class TestCanvasRepoDelete:
    async def test_delete_existing(self, blank_canvas, test_session):
        repo = CanvasRepo(test_session)
        result = await repo.delete(blank_canvas.id)
        assert result is True
        assert await repo.get(blank_canvas.id) is None

    async def test_delete_missing(self, test_session):
        repo = CanvasRepo(test_session)
        result = await repo.delete(uuid.uuid4())
        assert result is False


class TestCanvasRepoSaveNodesAndEdges:
    async def test_save_creates_nodes(self, blank_canvas, test_session):
        repo = CanvasRepo(test_session)
        aid = uuid.uuid4()
        tid = uuid.uuid4()
        eid = uuid.uuid4()

        agents = [AgentNodeInput(id=aid, name="Agent1")]
        tools = [ToolNodeInput(id=tid, name="Tool1", code="def f(): pass")]
        edges = [EdgeInput(id=eid, source_node_id=aid, target_node_id=tid)]

        canvas = await repo.save_nodes_and_edges(
            blank_canvas.id, "Updated", agents, tools, edges
        )
        assert canvas.name == "Updated"
        assert len(canvas.agent_nodes) == 1
        assert len(canvas.tool_nodes) == 1
        assert len(canvas.edges) == 1
        assert canvas.agent_nodes[0].id == aid
        assert canvas.tool_nodes[0].id == tid
        assert canvas.edges[0].id == eid

    async def test_save_replaces_existing(self, blank_canvas, test_session):
        repo = CanvasRepo(test_session)
        aid = uuid.uuid4()
        await repo.save_nodes_and_edges(
            blank_canvas.id, "V1",
            [AgentNodeInput(id=aid)],
            [],
            [],
        )
        canvas = await repo.get_or_404(blank_canvas.id)
        assert len(canvas.agent_nodes) == 1

        new_id = uuid.uuid4()
        await repo.save_nodes_and_edges(
            blank_canvas.id, "V2",
            [AgentNodeInput(id=new_id, name="NewAgent")],
            [],
            [],
        )
        canvas = await repo.get_or_404(blank_canvas.id)
        assert len(canvas.agent_nodes) == 1
        assert canvas.agent_nodes[0].id == new_id
        assert canvas.agent_nodes[0].name == "NewAgent"

    async def test_save_missing_canvas(self, test_session):
        repo = CanvasRepo(test_session)
        with pytest.raises(CanvasNotFoundError):
            await repo.save_nodes_and_edges(uuid.uuid4(), "N", [], [], [])

    async def test_save_persists_enable_coding(self, blank_canvas, test_session):
        """enable_coding round-trips through both the new-node and upsert branches."""
        repo = CanvasRepo(test_session)
        aid = uuid.uuid4()

        # New-node branch (constructor call in save_nodes_and_edges)
        await repo.save_nodes_and_edges(
            blank_canvas.id, "Coding",
            [AgentNodeInput(id=aid, name="Coder", agent_type="worker", enable_coding=True)],
            [],
            [],
        )
        canvas = await repo.get_or_404(blank_canvas.id)
        assert canvas.agent_nodes[0].enable_coding is True

        # Upsert branch (existing node assignment in save_nodes_and_edges)
        await repo.save_nodes_and_edges(
            blank_canvas.id, "Coding",
            [AgentNodeInput(id=aid, name="Coder", agent_type="worker", enable_coding=True)],
            [],
            [],
        )
        canvas = await repo.get_or_404(blank_canvas.id)
        assert canvas.agent_nodes[0].enable_coding is True

        # Toggle off via upsert
        await repo.save_nodes_and_edges(
            blank_canvas.id, "Coding",
            [AgentNodeInput(id=aid, name="Coder", agent_type="worker", enable_coding=False)],
            [],
            [],
        )
        canvas = await repo.get_or_404(blank_canvas.id)
        assert canvas.agent_nodes[0].enable_coding is False

    async def test_save_persists_enable_network(self, blank_canvas, test_session):
        """enable_network round-trips through both the new-node and upsert branches."""
        repo = CanvasRepo(test_session)
        aid = uuid.uuid4()

        # New-node branch (constructor call in save_nodes_and_edges)
        await repo.save_nodes_and_edges(
            blank_canvas.id, "Networked",
            [AgentNodeInput(id=aid, name="NetWorker", agent_type="worker", enable_network=True)],
            [],
            [],
        )
        canvas = await repo.get_or_404(blank_canvas.id)
        assert canvas.agent_nodes[0].enable_network is True

        # Upsert branch (existing node assignment in save_nodes_and_edges)
        await repo.save_nodes_and_edges(
            blank_canvas.id, "Networked",
            [AgentNodeInput(id=aid, name="NetWorker", agent_type="worker", enable_network=True)],
            [],
            [],
        )
        canvas = await repo.get_or_404(blank_canvas.id)
        assert canvas.agent_nodes[0].enable_network is True

        # Toggle off via upsert
        await repo.save_nodes_and_edges(
            blank_canvas.id, "Networked",
            [AgentNodeInput(id=aid, name="NetWorker", agent_type="worker", enable_network=False)],
            [],
            [],
        )
        canvas = await repo.get_or_404(blank_canvas.id)
        assert canvas.agent_nodes[0].enable_network is False


class TestCanvasRepoCreateFull:
    async def test_create_full(self, test_session, test_user):
        repo = CanvasRepo(test_session)
        master_id = uuid.uuid4()
        worker_id = uuid.uuid4()
        tool_id = uuid.uuid4()
        e1_id = uuid.uuid4()
        e2_id = uuid.uuid4()

        agents = [
            AgentNodeInput(id=master_id, name="Master", agent_type="router"),
            AgentNodeInput(id=worker_id, name="Worker", agent_type="worker"),
        ]
        tools = [ToolNodeInput(id=tool_id, name="Tool1")]
        edges = [
            EdgeInput(id=e1_id, source_node_id=master_id, target_node_id=worker_id, edge_type="handoff"),
            EdgeInput(id=e2_id, source_node_id=worker_id, target_node_id=tool_id, edge_type="tool_access"),
        ]

        canvas = await repo.create_full("Full Canvas", agents, tools, edges, owner_id=test_user.id)
        assert canvas.name == "Full Canvas"
        assert canvas.owner_id == test_user.id
        assert len(canvas.agent_nodes) == 2
        assert len(canvas.tool_nodes) == 1
        assert len(canvas.edges) == 2

        names = {n.name for n in canvas.agent_nodes}
        assert names == {"Master", "Worker"}

    async def test_create_full_persists_enable_coding(self, test_session, test_user):
        repo = CanvasRepo(test_session)
        worker_id = uuid.uuid4()
        agents = [
            AgentNodeInput(id=worker_id, name="Coder", agent_type="worker", enable_coding=True),
        ]
        canvas = await repo.create_full("Coding Canvas", agents, [], [], owner_id=test_user.id)
        assert canvas.agent_nodes[0].enable_coding is True

    async def test_create_full_persists_enable_network(self, test_session, test_user):
        repo = CanvasRepo(test_session)
        worker_id = uuid.uuid4()
        agents = [
            AgentNodeInput(id=worker_id, name="NetWorker", agent_type="worker", enable_network=True),
        ]
        canvas = await repo.create_full("Networked Canvas", agents, [], [], owner_id=test_user.id)
        assert canvas.agent_nodes[0].enable_network is True


class TestCanvasRepoAttachments:
    async def test_save_creates_attachment_node(self, blank_canvas, test_session):
        repo = CanvasRepo(test_session)
        att_id = uuid.uuid4()

        canvas = await repo.save_nodes_and_edges(
            blank_canvas.id,
            "Attachments",
            [],
            [],
            [],
            attachments=[
                AttachmentNodeInput(id=att_id, name="Data", file_type="csv", description="Sales")
            ],
        )
        assert len(canvas.attachment_nodes) == 1
        assert canvas.attachment_nodes[0].id == att_id
        assert canvas.attachment_nodes[0].file_type == "csv"
        assert canvas.attachment_nodes[0].description == "Sales"

    async def test_save_with_no_attachments_arg_defaults_empty(self, blank_canvas, test_session):
        repo = CanvasRepo(test_session)
        # attachments is optional/keyword — existing 5-positional-arg call sites
        # must keep working unchanged.
        canvas = await repo.save_nodes_and_edges(blank_canvas.id, "NoAttachments", [], [], [])
        assert canvas.attachment_nodes == []

    async def test_save_replaces_attachments(self, blank_canvas, test_session):
        repo = CanvasRepo(test_session)
        first_id = uuid.uuid4()
        await repo.save_nodes_and_edges(
            blank_canvas.id, "V1", [], [], [],
            attachments=[AttachmentNodeInput(id=first_id, name="First")],
        )
        canvas = await repo.get_or_404(blank_canvas.id)
        assert len(canvas.attachment_nodes) == 1

        second_id = uuid.uuid4()
        await repo.save_nodes_and_edges(
            blank_canvas.id, "V2", [], [], [],
            attachments=[AttachmentNodeInput(id=second_id, name="Second")],
        )
        canvas = await repo.get_or_404(blank_canvas.id)
        assert len(canvas.attachment_nodes) == 1
        assert canvas.attachment_nodes[0].id == second_id
        assert canvas.attachment_nodes[0].name == "Second"

    async def test_save_with_produces_and_consumes_edges(self, blank_canvas, test_session):
        repo = CanvasRepo(test_session)
        agent_id = uuid.uuid4()
        other_agent_id = uuid.uuid4()
        att_id = uuid.uuid4()

        canvas = await repo.save_nodes_and_edges(
            blank_canvas.id,
            "Wired",
            [AgentNodeInput(id=agent_id), AgentNodeInput(id=other_agent_id)],
            [],
            [
                EdgeInput(
                    id=uuid.uuid4(),
                    source_node_id=agent_id,
                    target_node_id=att_id,
                    edge_type="produces",
                ),
                EdgeInput(
                    id=uuid.uuid4(),
                    source_node_id=att_id,
                    target_node_id=other_agent_id,
                    edge_type="consumes",
                ),
            ],
            attachments=[AttachmentNodeInput(id=att_id, name="Shared")],
        )
        assert len(canvas.edges) == 2
        edge_types = {e.edge_type for e in canvas.edges}
        assert edge_types == {"produces", "consumes"}

    async def test_create_full_with_attachments(self, test_session, test_user):
        repo = CanvasRepo(test_session)
        att_id = uuid.uuid4()
        canvas = await repo.create_full(
            "Full With Attachments",
            [],
            [],
            [],
            attachments=[
                AttachmentNodeInput(id=att_id, name="Data", file_type="json")
            ],
            owner_id=test_user.id,
        )
        assert len(canvas.attachment_nodes) == 1
        assert canvas.attachment_nodes[0].name == "Data"
        assert canvas.attachment_nodes[0].file_type == "json"
        # imported attachment gets a fresh server-generated id, like agents/tools
        assert canvas.attachment_nodes[0].id != att_id

    async def test_create_full_remaps_attachment_edge_ids(self, test_session, test_user):
        repo = CanvasRepo(test_session)
        agent_id = uuid.uuid4()
        att_id = uuid.uuid4()
        edge_id = uuid.uuid4()

        canvas = await repo.create_full(
            "Remap Canvas",
            [AgentNodeInput(id=agent_id, name="Agent1")],
            [],
            [
                EdgeInput(
                    id=edge_id,
                    source_node_id=agent_id,
                    target_node_id=att_id,
                    edge_type="produces",
                )
            ],
            attachments=[AttachmentNodeInput(id=att_id, name="Data")],
            owner_id=test_user.id,
        )
        assert len(canvas.edges) == 1
        new_agent_id = canvas.agent_nodes[0].id
        new_attachment_id = canvas.attachment_nodes[0].id
        assert canvas.edges[0].source_node_id == new_agent_id
        assert canvas.edges[0].target_node_id == new_attachment_id

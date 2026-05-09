import uuid

import pytest

from canvas_server.exceptions import CanvasNotFoundError
from canvas_server.models.api import AgentNodeInput, EdgeInput, ToolNodeInput
from canvas_server.repos.canvas_repo import CanvasRepo


class TestCanvasRepoCreate:
    async def test_create_empty(self, test_session):
        repo = CanvasRepo(test_session)
        canvas = await repo.create("Empty")
        assert canvas.name == "Empty"
        assert canvas.id is not None
        assert canvas.agent_nodes == []
        assert canvas.tool_nodes == []
        assert canvas.edges == []

    async def test_create_default_name(self, test_session):
        repo = CanvasRepo(test_session)
        canvas = await repo.create()
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

    async def test_list_ordered_by_updated(self, test_session):
        repo = CanvasRepo(test_session)
        c1 = await repo.create("First")
        await repo.create("Second")
        await repo.save_nodes_and_edges(c1.id, "First Updated", [], [], [])
        canvases = await repo.list_all()
        assert canvases[0].id == c1.id


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


class TestCanvasRepoCreateFull:
    async def test_create_full(self, test_session):
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

        canvas = await repo.create_full("Full Canvas", agents, tools, edges)
        assert canvas.name == "Full Canvas"
        assert len(canvas.agent_nodes) == 2
        assert len(canvas.tool_nodes) == 1
        assert len(canvas.edges) == 2

        names = {n.name for n in canvas.agent_nodes}
        assert names == {"Master", "Worker"}

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from beeai_framework.agents.react import ReActAgent
from beeai_framework.backend.chat import ChatModel

from canvas_server.repos.conversation_repo import ConversationRepo
from canvas_server.runner import CanvasRunner, RouterDecision


class FakeCanvas:
    def __init__(self, id=None, agent_nodes=None, tool_nodes=None, edges=None):
        self.id = id or uuid.uuid4()
        self.agent_nodes = agent_nodes or []
        self.tool_nodes = tool_nodes or []
        self.edges = edges or []


class FakeAgentNode:
    def __init__(
        self,
        id=None,
        name="",
        role="",
        instructions="",
        model_name="ollama:llama3.1",
        agent_type="worker",
    ):
        self.id = id or uuid.uuid4()
        self.name = name
        self.role = role
        self.instructions = instructions
        self.model_name = model_name
        self.agent_type = agent_type
        self.position_x = 0
        self.position_y = 0


class FakeEdge:
    def __init__(self, source, target, edge_type):
        self.id = uuid.uuid4()
        self.canvas_id = uuid.uuid4()
        self.source_node_id = source
        self.target_node_id = target
        self.edge_type = edge_type


def _mock_worker_result(text: str):
    result = MagicMock()
    result.iterations = []
    result.result = MagicMock()
    result.result.text = text
    result.get_text_content = MagicMock(return_value=text)
    return result


class TestConversationAPI:
    async def test_create_conversation(self, test_client, fresh_db, blank_canvas):
        resp = await test_client.post(
            f"/api/canvases/{blank_canvas.id}/conversations",
            json={"name": "My Chat"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "My Chat"
        assert data["status"] == "active"
        assert data["canvas_id"] == str(blank_canvas.id)
        assert data["messages"] == []

    async def test_create_conversation_default_name(
        self, test_client, fresh_db, blank_canvas
    ):
        resp = await test_client.post(
            f"/api/canvases/{blank_canvas.id}/conversations", json={}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Conversation"

    async def test_create_conversation_missing_canvas(self, test_client, fresh_db):
        resp = await test_client.post(
            f"/api/canvases/{uuid.uuid4()}/conversations", json={"name": "X"}
        )
        assert resp.status_code == 404

    async def test_list_conversations(self, test_client, fresh_db, blank_canvas):
        await test_client.post(
            f"/api/canvases/{blank_canvas.id}/conversations", json={"name": "C1"}
        )
        await test_client.post(
            f"/api/canvases/{blank_canvas.id}/conversations", json={"name": "C2"}
        )

        resp = await test_client.get(
            f"/api/canvases/{blank_canvas.id}/conversations"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {c["name"] for c in data}
        assert names == {"C1", "C2"}

    async def test_list_conversations_empty(
        self, test_client, fresh_db, blank_canvas
    ):
        resp = await test_client.get(
            f"/api/canvases/{blank_canvas.id}/conversations"
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_conversation(self, test_client, fresh_db, blank_canvas):
        create_resp = await test_client.post(
            f"/api/canvases/{blank_canvas.id}/conversations",
            json={"name": "My Chat"},
        )
        conv_id = create_resp.json()["id"]

        resp = await test_client.get(
            f"/api/canvases/{blank_canvas.id}/conversations/{conv_id}"
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == conv_id
        assert resp.json()["name"] == "My Chat"

    async def test_get_conversation_wrong_canvas(
        self, test_client, fresh_db, blank_canvas
    ):
        create_resp = await test_client.post(
            f"/api/canvases/{blank_canvas.id}/conversations", json={"name": "C"}
        )
        conv_id = create_resp.json()["id"]

        other = await test_client.post("/api/canvases", json={"name": "Other"})
        other_id = other.json()["id"]

        resp = await test_client.get(
            f"/api/canvases/{other_id}/conversations/{conv_id}"
        )
        assert resp.status_code == 404

    async def test_delete_conversation(self, test_client, fresh_db, blank_canvas):
        create_resp = await test_client.post(
            f"/api/canvases/{blank_canvas.id}/conversations",
            json={"name": "ToDelete"},
        )
        conv_id = create_resp.json()["id"]

        del_resp = await test_client.delete(
            f"/api/canvases/{blank_canvas.id}/conversations/{conv_id}"
        )
        assert del_resp.status_code == 204

        get_resp = await test_client.get(
            f"/api/canvases/{blank_canvas.id}/conversations/{conv_id}"
        )
        assert get_resp.status_code == 404

    async def test_delete_conversation_wrong_canvas(
        self, test_client, fresh_db, blank_canvas
    ):
        create_resp = await test_client.post(
            f"/api/canvases/{blank_canvas.id}/conversations", json={"name": "C"}
        )
        conv_id = create_resp.json()["id"]

        other = await test_client.post("/api/canvases", json={"name": "Other"})
        other_id = other.json()["id"]

        resp = await test_client.delete(
            f"/api/canvases/{other_id}/conversations/{conv_id}"
        )
        assert resp.status_code == 404


class TestConversationRepo:
    async def test_complete_conversation_sets_status(
        self, test_session, blank_canvas
    ):
        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="Test Conv")
        conv_id = conv.id
        assert conv.status == "active"

        await repo.complete_conversation(conv_id)
        await test_session.commit()

        fetched = await repo.get(conv_id)
        assert fetched.status == "completed"

    async def test_get_conversation_includes_messages(
        self, test_session, blank_canvas
    ):
        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="Test Conv")
        conv_id = conv.id

        await repo.add_message(
            conversation_id=conv_id,
            role="user",
            content="Hello",
        )
        await repo.add_message(
            conversation_id=conv_id,
            role="assistant",
            content="Hi there!",
            agent_name="MathAgent",
            node_id=uuid.uuid4(),
            event_type="final_answer",
        )
        await test_session.commit()

        test_session.expire_all()

        fetched = await repo.get(conv_id)
        assert fetched is not None
        assert len(fetched.messages) == 2
        assert fetched.messages[0].role == "user"
        assert fetched.messages[0].content == "Hello"
        assert fetched.messages[1].role == "assistant"
        assert fetched.messages[1].agent_name == "MathAgent"

    async def test_delete_conversation_cascades_messages(
        self, test_session, blank_canvas
    ):
        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="Test Conv")
        conv_id = conv.id

        await repo.add_message(conversation_id=conv_id, role="user", content="test")
        await test_session.commit()

        assert await repo.delete(conv_id) is True
        await test_session.commit()

        assert await repo.get(conv_id) is None

    async def test_list_for_canvas_returns_correct_scope(
        self, test_session, blank_canvas
    ):
        canvas_id = blank_canvas.id
        repo = ConversationRepo(test_session)
        await repo.create(canvas_id=canvas_id, name="A")
        await repo.create(canvas_id=canvas_id, name="B")

        from canvas_server.repos.canvas_repo import CanvasRepo

        canvas_repo = CanvasRepo(test_session)
        other = await canvas_repo.create(name="Other Canvas")
        await repo.create(canvas_id=other.id, name="Other Conv")
        await test_session.commit()

        result = await repo.list_for_canvas(canvas_id)
        names = {c.name for c in result}
        assert names == {"A", "B"}


class TestRunnerWithConversation:
    async def test_runner_persists_user_message(
        self, test_session, blank_canvas
    ):
        worker = FakeAgentNode(
            id=uuid.uuid4(), name="Worker", agent_type="worker"
        )
        canvas = FakeCanvas(agent_nodes=[worker])

        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="Test")
        conv_id = conv.id

        async def collect(event):
            pass

        with patch.object(ChatModel, "from_name") as m_from_name:
            m_from_name.return_value = MagicMock(spec=ChatModel)
            m_agent_run = AsyncMock(return_value=_mock_worker_result("Done!"))

            with patch.object(ReActAgent, "run", m_agent_run):
                runner = CanvasRunner(
                    canvas, conversation_repo=repo, conversation_id=conv_id
                )
                await runner.run("Hello world", collect)

        await test_session.commit()
        test_session.expire_all()

        fetched = await repo.get(conv_id)
        user_msgs = [m for m in fetched.messages if m.role == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0].content == "Hello world"

    async def test_runner_completes_conversation(
        self, test_session, blank_canvas
    ):
        worker = FakeAgentNode(
            id=uuid.uuid4(), name="Worker", agent_type="worker"
        )
        canvas = FakeCanvas(agent_nodes=[worker])

        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="Test")
        conv_id = conv.id

        async def collect(event):
            pass

        with patch.object(ChatModel, "from_name") as m_from_name:
            m_from_name.return_value = MagicMock(spec=ChatModel)
            m_agent_run = AsyncMock(return_value=_mock_worker_result("Done!"))

            with patch.object(ReActAgent, "run", m_agent_run):
                runner = CanvasRunner(
                    canvas, conversation_repo=repo, conversation_id=conv_id
                )
                await runner.run("test", collect)

        await test_session.commit()
        test_session.expire_all()

        fetched = await repo.get(conv_id)
        assert fetched.status == "completed"

    async def test_runner_injects_history_into_router(
        self, test_session, blank_canvas
    ):
        master = FakeAgentNode(
            id=uuid.uuid4(), name="Master", role="Router", agent_type="router"
        )
        worker = FakeAgentNode(
            id=uuid.uuid4(), name="MathAgent", role="Math expert", agent_type="worker"
        )
        canvas = FakeCanvas(
            agent_nodes=[master, worker],
            edges=[FakeEdge(master.id, worker.id, "handoff")],
        )

        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="Test")
        conv_id = conv.id
        await repo.add_message(
            conversation_id=conv_id,
            role="user",
            content="Previous question: what is 2+2?",
        )
        await repo.add_message(
            conversation_id=conv_id,
            role="assistant",
            content="4",
            agent_name="MathAgent",
            event_type="final_answer",
        )
        await test_session.commit()

        async def collect(event):
            pass

        with patch.object(ChatModel, "from_name") as m_from_name:
            mock_llm = MagicMock(spec=ChatModel)
            mock_llm.run = AsyncMock()
            m_from_name.return_value = mock_llm

            route_decision = RouterDecision(
                thought="Math question, routing to MathAgent",
                action="transfer_to_MathAgent",
                action_input="what is 3*7?",
            )
            final_decision = RouterDecision(
                thought="MathAgent answered: 3 * 7 = 21",
                final_answer="21",
            )

            mock_llm.run.side_effect = [
                MagicMock(
                    output_structured=route_decision,
                    get_text_content=lambda: "",
                ),
                MagicMock(
                    output_structured=final_decision,
                    get_text_content=lambda: "",
                ),
            ]

            m_agent_run = AsyncMock(return_value=_mock_worker_result("21"))

            with patch.object(ReActAgent, "run", m_agent_run):
                runner = CanvasRunner(
                    canvas, conversation_repo=repo, conversation_id=conv_id
                )
                await runner.run("what is 3*7?", collect)

        await test_session.commit()
        test_session.expire_all()

        fetched = await repo.get(conv_id)
        assistant_msgs = [
            m for m in fetched.messages if m.role == "assistant"
        ]
        assert len(assistant_msgs) >= 1

    async def test_runner_worker_persists_final_answer(
        self, test_session, blank_canvas
    ):
        worker = FakeAgentNode(
            id=uuid.uuid4(), name="Worker", agent_type="worker"
        )
        canvas = FakeCanvas(agent_nodes=[worker])

        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="Test")
        conv_id = conv.id

        async def collect(event):
            pass

        with patch.object(ChatModel, "from_name") as m_from_name:
            m_from_name.return_value = MagicMock(spec=ChatModel)
            m_agent_run = AsyncMock(return_value=_mock_worker_result("Done!"))

            with patch.object(ReActAgent, "run", m_agent_run):
                runner = CanvasRunner(
                    canvas, conversation_repo=repo, conversation_id=conv_id
                )
                await runner.run("do work", collect)

        await test_session.commit()
        test_session.expire_all()

        fetched = await repo.get(conv_id)
        assistant_msgs = [
            m for m in fetched.messages if m.role == "assistant"
        ]
        assert len(assistant_msgs) >= 1
        assert assistant_msgs[0].content == "Done!"
        assert assistant_msgs[0].agent_name == "Worker"

    async def test_runner_with_target_agent_id_uses_specific_agent(self):
        master = FakeAgentNode(
            id=uuid.uuid4(), name="Master", role="Router", agent_type="router"
        )
        worker = FakeAgentNode(
            id=uuid.uuid4(), name="MathAgent", role="Math expert", agent_type="worker"
        )
        canvas = FakeCanvas(
            agent_nodes=[master, worker],
            edges=[FakeEdge(master.id, worker.id, "handoff")],
        )

        events = []

        async def collect(event):
            events.append(event)

        with patch.object(ChatModel, "from_name") as m_from_name:
            m_from_name.return_value = MagicMock(spec=ChatModel)
            m_agent_run = AsyncMock(return_value=_mock_worker_result("42"))

            with patch.object(ReActAgent, "run", m_agent_run):
                runner = CanvasRunner(canvas)
                await runner.run("do work", collect, target_agent_id=worker.id)

        agent_starts = [e for e in events if e["type"] == "agent_start"]
        assert len(agent_starts) == 1
        assert agent_starts[0]["agent"] == "MathAgent"

        handoffs = [e for e in events if e["type"] == "handoff"]
        assert len(handoffs) == 0

    async def test_runner_events_include_node_ids(self):
        master = FakeAgentNode(
            id=uuid.uuid4(), name="Master", role="Router", agent_type="router"
        )
        worker = FakeAgentNode(
            id=uuid.uuid4(), name="MathAgent", role="Math expert", agent_type="worker"
        )
        canvas = FakeCanvas(
            agent_nodes=[master, worker],
            edges=[FakeEdge(master.id, worker.id, "handoff")],
        )

        events = []

        async def collect(event):
            events.append(event)

        with patch.object(ChatModel, "from_name") as m_from_name:
            mock_llm = MagicMock(spec=ChatModel)
            mock_llm.run = AsyncMock()
            m_from_name.return_value = mock_llm

            route_decision = RouterDecision(
                thought="Routing math question",
                action="transfer_to_MathAgent",
                action_input="what is 2+2?",
            )
            final_decision = RouterDecision(
                thought="Got answer from MathAgent",
                final_answer="4",
            )

            mock_llm.run.side_effect = [
                MagicMock(
                    output_structured=route_decision,
                    get_text_content=lambda: "",
                ),
                MagicMock(
                    output_structured=final_decision,
                    get_text_content=lambda: "",
                ),
            ]

            m_agent_run = AsyncMock(return_value=_mock_worker_result("4"))

            with patch.object(ReActAgent, "run", m_agent_run):
                runner = CanvasRunner(canvas)
                await runner.run("what is 2+2?", collect)

        for event in events:
            if event["type"] in (
                "agent_start",
                "handoff",
                "final_answer",
                "tool_result",
            ):
                assert "node_id" in event, (
                    f"Event {event['type']} missing node_id"
                )

    async def test_conversation_delete_cascades_from_canvas_delete(
        self, test_client, fresh_db, blank_canvas
    ):
        create_resp = await test_client.post(
            f"/api/canvases/{blank_canvas.id}/conversations",
            json={"name": "C1"},
        )
        conv_id = create_resp.json()["id"]

        del_resp = await test_client.delete(
            f"/api/canvases/{blank_canvas.id}"
        )
        assert del_resp.status_code == 204

        get_resp = await test_client.get(
            f"/api/canvases/{blank_canvas.id}/conversations/{conv_id}"
        )
        assert get_resp.status_code == 404

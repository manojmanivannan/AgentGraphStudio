import uuid
from unittest.mock import AsyncMock, patch

import dspy

from canvas_server.repos.conversation_repo import ConversationRepo
from canvas_server.runner import CanvasRunner


def _make_prediction(process_result="", trajectory=None):
    trajectory = trajectory or {"thought_0": "", "tool_name_0": "finish", "tool_args_0": {}}
    return dspy.Prediction(process_result=process_result, trajectory=trajectory)


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
        enable_conversation_history=False,
        enable_memory=False,
    ):
        self.id = id or uuid.uuid4()
        self.name = name
        self.role = role
        self.instructions = instructions
        self.model_name = model_name
        self.agent_type = agent_type
        self.enable_conversation_history = enable_conversation_history
        self.enable_memory = enable_memory
        self.position_x = 0
        self.position_y = 0


class FakeEdge:
    def __init__(self, source, target, edge_type):
        self.id = uuid.uuid4()
        self.canvas_id = uuid.uuid4()
        self.source_node_id = source
        self.target_node_id = target
        self.edge_type = edge_type


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
    def _make_agent_mock(self, text="Done!"):
        pred = _make_prediction(process_result=text)
        agent = AsyncMock(return_value=pred)
        agent.aforward = AsyncMock(return_value=pred)
        return agent

    def _make_router_mock(self, result_text, trajectory=None):
        pred = _make_prediction(process_result=result_text, trajectory=trajectory or {})
        router = AsyncMock(return_value=pred)
        router.aforward = AsyncMock(return_value=pred)
        return router

    async def _setup_worker_runner(self, worker, canvas, text="Done!"):
        """Helper: set up runner internals for a worker-only canvas."""
        runner = CanvasRunner(canvas)
        runner.setup = AsyncMock()
        runner.node_map = {worker.id: worker}
        runner.agents[worker.id] = self._make_agent_mock(text)
        return runner

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

        runner = await self._setup_worker_runner(worker, canvas)
        runner.conversation_repo = repo
        runner.conversation_id = conv_id

        await runner.run("Hello world", collect)

        await test_session.commit()
        test_session.expire_all()

        fetched = await repo.get(conv_id)
        user_msgs = [m for m in fetched.messages if m.role == "user"]
        assert len(user_msgs) == 1
        assert user_msgs[0].content == "Hello world"

    async def test_runner_keeps_conversation_active(
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

        runner = await self._setup_worker_runner(worker, canvas)
        runner.conversation_repo = repo
        runner.conversation_id = conv_id

        await runner.run("test", collect)

        await test_session.commit()
        test_session.expire_all()

        fetched = await repo.get(conv_id)
        # Conversations should stay "active" so that multi-turn
        # conversation history works correctly across messages.
        assert fetched.status == "active"

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

        runner = CanvasRunner(
            canvas, conversation_repo=repo, conversation_id=conv_id
        )
        runner.setup = AsyncMock()
        runner.node_map = {master.id: master, worker.id: worker}

        worker_mock = self._make_agent_mock("21")
        runner.agents[worker.id] = worker_mock

        with patch.object(runner, "_build_router_agent") as mock_builder:
            router_mock = self._make_router_mock(
                "21",
                trajectory={
                    "thought_0": "Math question, routing to MathAgent",
                    "tool_name_0": "transfer_to_MathAgent",
                    "tool_args_0": {"task": "what is 3*7?"},
                    "observation_0": "21",
                    "thought_1": "Got answer from MathAgent",
                    "tool_name_1": "finish",
                    "tool_args_1": {},
                },
            )
            mock_builder.return_value = router_mock

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

        runner = await self._setup_worker_runner(worker, canvas, text="Done!")
        runner.conversation_repo = repo
        runner.conversation_id = conv_id

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

    async def test_router_persists_final_answer(
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

        async def collect(event):
            pass

        runner = CanvasRunner(
            canvas, conversation_repo=repo, conversation_id=conv_id
        )
        runner.setup = AsyncMock()
        runner.node_map = {master.id: master, worker.id: worker}

        worker_mock = self._make_agent_mock("42")
        runner.agents[worker.id] = worker_mock

        with patch.object(runner, "_build_router_agent") as mock_builder:
            router_mock = self._make_router_mock(
                "The answer is 42",
                trajectory={
                    "thought_0": "Math question, routing to MathAgent",
                    "tool_name_0": "transfer_to_MathAgent",
                    "tool_args_0": {"task": "what is 6*7?"},
                    "observation_0": "42",
                    "thought_1": "Got answer from MathAgent",
                    "tool_name_1": "finish",
                    "tool_args_1": {},
                },
            )
            mock_builder.return_value = router_mock

            await runner.run("what is 6*7?", collect)

        await test_session.commit()
        test_session.expire_all()

        fetched = await repo.get(conv_id)
        # The router's final answer should be persisted as an assistant message
        assistant_msgs = [
            m for m in fetched.messages if m.role == "assistant"
        ]
        router_msgs = [
            m for m in assistant_msgs if m.agent_name == "Master"
        ]
        assert len(router_msgs) >= 1
        assert "42" in router_msgs[0].content

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

        runner = CanvasRunner(canvas)
        runner.setup = AsyncMock()
        runner.node_map = {master.id: master, worker.id: worker}

        worker_mock = self._make_agent_mock("42")
        runner.agents[worker.id] = worker_mock

        await runner.run("do work", collect, target_agent_id=worker.id)

        agent_starts = [e for e in events if e["type"] == "agent_start"]
        assert len(agent_starts) == 0  # attached events don't fire agent_start for workers
        assert "run_complete" in [e["type"] for e in events]

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

        runner = CanvasRunner(canvas)
        runner.setup = AsyncMock()
        runner.node_map = {master.id: master, worker.id: worker}

        worker_mock = self._make_agent_mock("4")
        runner.agents[worker.id] = worker_mock

        with patch.object(runner, "_build_router_agent") as mock_builder:
            router_mock = self._make_router_mock(
                "4",
                trajectory={
                    "thought_0": "Routing math question",
                    "tool_name_0": "transfer_to_MathAgent",
                    "tool_args_0": {"task": "what is 2+2?"},
                    "observation_0": "4",
                    "thought_1": "Got answer from MathAgent",
                    "tool_name_1": "finish",
                    "tool_args_1": {},
                },
            )
            mock_builder.return_value = router_mock

            await runner.run("what is 2+2?", collect)

        for event in events:
            if event["type"] in (
                "run_start",
                "run_complete",
            ):
                continue
            assert "node_id" in event, (
                f"Event {event['type']} missing node_id"
            )

    async def test_history_excludes_system_prompts_and_intermediate_agents(
        self, test_session, blank_canvas
    ):
        """Conversation history should only include user messages and final
        answers from history-enabled agents.  System prompts and intermediate
        sub-agent responses must be excluded."""
        master_id = uuid.uuid4()
        math_team_id = uuid.uuid4()
        factorial_id = uuid.uuid4()

        master = FakeAgentNode(
            id=master_id,
            name="MasterAgent",
            role="Routing Expert",
            instructions="You route questions.",
            agent_type="router",
            enable_conversation_history=True,
        )
        math_team = FakeAgentNode(
            id=math_team_id,
            name="MathTeam",
            role="Math expert team",
            agent_type="router",
            enable_conversation_history=False,
        )
        factorial = FakeAgentNode(
            id=factorial_id,
            name="FactorialAgent",
            role="FactorialExpert",
            agent_type="worker",
            enable_conversation_history=False,
        )
        canvas = FakeCanvas(
            agent_nodes=[master, math_team, factorial],
            edges=[
                FakeEdge(master_id, math_team_id, "handoff"),
                FakeEdge(math_team_id, factorial_id, "handoff"),
            ],
        )

        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="Test")
        conv_id = conv.id

        # Pre-populate messages mimicking a real multi-agent run:
        # - A system prompt (should be excluded from history)
        # - A user message
        # - FactorialAgent intermediate answer (excluded — no history)
        # - MathTeam intermediate answer (excluded — no history)
        # - MasterAgent final answer (included — has history)
        await repo.add_message(
            conversation_id=conv_id,
            role="system",
            content="Routing Expert\n\nYou route questions.",
            agent_name="MasterAgent",
            node_id=master_id,
            event_type="system_prompt",
        )
        await repo.add_message(
            conversation_id=conv_id,
            role="user",
            content="what is the factorial of 8",
            event_type="run_start",
        )
        await repo.add_message(
            conversation_id=conv_id,
            role="assistant",
            content="40320",
            agent_name="FactorialAgent",
            node_id=factorial_id,
            event_type="final_answer",
        )
        await repo.add_message(
            conversation_id=conv_id,
            role="assistant",
            content="The factorial of 8 (8!) is 40,320.",
            agent_name="MathTeam",
            node_id=math_team_id,
            event_type="final_answer",
        )
        await repo.add_message(
            conversation_id=conv_id,
            role="assistant",
            content="The factorial of 8 is 40,320.",
            agent_name="MasterAgent",
            node_id=master_id,
            event_type="final_answer",
        )
        await test_session.commit()
        test_session.expire_all()

        runner = CanvasRunner(
            canvas, conversation_repo=repo, conversation_id=conv_id
        )
        runner.setup = AsyncMock()
        runner.node_map = {master_id: master, math_team_id: math_team, factorial_id: factorial}

        # Load history and format it
        history_messages = await runner._load_conversation_history()
        history_enabled_ids = {
            n.id for n in canvas.agent_nodes if n.enable_conversation_history
        }
        history_text = runner._format_history(
            history_messages, history_enabled_node_ids=history_enabled_ids
        )

        # History should contain user + MasterAgent answer only
        assert "User: what is the factorial of 8" in history_text
        assert "Assistant [MasterAgent]" in history_text
        assert "The factorial of 8 is 40,320" in history_text

        # History should NOT contain system prompt or intermediate agents
        assert "Routing Expert" not in history_text
        assert "FactorialAgent" not in history_text
        assert "40320" not in history_text
        assert "MathTeam" not in history_text
        assert "8!) is" not in history_text

    async def test_dspy_history_excludes_intermediate_agents(
        self, test_session, blank_canvas
    ):
        """dspy.History should only contain user/assistant pairs from
        history-enabled agents — not system messages or sub-agent responses."""
        import dspy

        master_id = uuid.uuid4()
        math_team_id = uuid.uuid4()

        master = FakeAgentNode(
            id=master_id,
            name="MasterAgent",
            role="Router",
            agent_type="router",
            enable_conversation_history=True,
        )
        math_team = FakeAgentNode(
            id=math_team_id,
            name="MathTeam",
            role="Math expert",
            agent_type="worker",
            enable_conversation_history=False,
        )
        canvas = FakeCanvas(
            agent_nodes=[master, math_team],
            edges=[FakeEdge(master_id, math_team_id, "handoff")],
        )

        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="Test")
        conv_id = conv.id

        # Pre-populate: user asks, sub-agent answers, master summarizes
        await repo.add_message(
            conversation_id=conv_id,
            role="system",
            content="Router\n\nYou are a router.",
            agent_name="MasterAgent",
            node_id=master_id,
            event_type="system_prompt",
        )
        await repo.add_message(
            conversation_id=conv_id,
            role="user",
            content="what is 2+2?",
            event_type="run_start",
        )
        await repo.add_message(
            conversation_id=conv_id,
            role="assistant",
            content="4",
            agent_name="MathTeam",
            node_id=math_team_id,
            event_type="final_answer",
        )
        await repo.add_message(
            conversation_id=conv_id,
            role="assistant",
            content="The answer is 4.",
            agent_name="MasterAgent",
            node_id=master_id,
            event_type="final_answer",
        )
        await test_session.commit()
        test_session.expire_all()

        runner = CanvasRunner(
            canvas, conversation_repo=repo, conversation_id=conv_id
        )
        runner.setup = AsyncMock()
        runner.node_map = {master_id: master, math_team_id: math_team}

        history_messages = await runner._load_conversation_history()
        history_enabled_ids = {
            n.id for n in canvas.agent_nodes if n.enable_conversation_history
        }

        # Build dspy.History the same way run() does
        dspy_messages = []
        for msg in history_messages:
            if msg.role == "system":
                continue
            elif msg.role == "user":
                dspy_messages.append({"user_request": msg.content})
            elif msg.role == "assistant":
                if msg.node_id in history_enabled_ids:
                    dspy_messages.append({"process_result": msg.content})
        dspy_history = dspy.History(messages=dspy_messages)

        # dspy.History should have exactly 2 entries: user request + master answer
        assert len(dspy_history.messages) == 2
        assert dspy_history.messages[0]["user_request"] == "what is 2+2?"
        assert dspy_history.messages[1]["process_result"] == "The answer is 4."

    async def test_no_system_prompt_persisted_when_history_enabled(
        self, test_session, blank_canvas
    ):
        """System prompts should NOT be persisted as messages when
        enable_conversation_history is true — they're already in the
        DSPy signature instructions."""
        master = FakeAgentNode(
            id=uuid.uuid4(),
            name="MasterAgent",
            role="Routing Expert",
            instructions="You route the questions to the sub agent.",
            agent_type="router",
            enable_conversation_history=True,
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

        async def collect(event):
            pass

        runner = CanvasRunner(
            canvas, conversation_repo=repo, conversation_id=conv_id
        )
        runner.setup = AsyncMock()
        runner.node_map = {master.id: master, worker.id: worker}

        worker_mock = self._make_agent_mock("720")
        runner.agents[worker.id] = worker_mock

        with patch.object(runner, "_build_router_agent") as mock_builder:
            router_mock = self._make_router_mock(
                "The factorial of 6 is 720",
                trajectory={
                    "thought_0": "Math question",
                    "tool_name_0": "finish",
                    "tool_args_0": {},
                },
            )
            mock_builder.return_value = router_mock

            await runner.run("what is the factorial of 6?", collect)

        await test_session.commit()
        test_session.expire_all()

        fetched = await repo.get(conv_id)
        system_msgs = [m for m in fetched.messages if m.role == "system"]
        # No system prompt messages should be persisted
        assert len(system_msgs) == 0

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

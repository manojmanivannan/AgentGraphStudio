import uuid
from unittest.mock import AsyncMock, patch

import dspy
import pytest

from canvas_server.repos.conversation_repo import ConversationRepo
from canvas_server.runner import CanvasRunner


def _make_prediction(process_result="", trajectory=None):
    trajectory = trajectory or {
        "thought_0": "",
        "tool_name_0": "finish",
        "tool_args_0": {},
    }
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
    async def test_create_conversation(self, authed_client, owned_canvas):
        resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations",
            json={"name": "My Chat"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "My Chat"
        assert data["status"] == "active"
        assert data["canvas_id"] == str(owned_canvas.id)
        assert data["messages"] == []

    async def test_create_conversation_default_name(
        self, authed_client, owned_canvas
    ):
        resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations", json={}
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Conversation"

    async def test_create_conversation_missing_canvas(self, authed_client):
        resp = await authed_client.post(
            f"/api/canvases/{uuid.uuid4()}/conversations", json={"name": "X"}
        )
        assert resp.status_code == 404

    async def test_list_conversations(self, authed_client, owned_canvas):
        await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations", json={"name": "C1"}
        )
        await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations", json={"name": "C2"}
        )

        resp = await authed_client.get(f"/api/canvases/{owned_canvas.id}/conversations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {c["name"] for c in data}
        assert names == {"C1", "C2"}

    async def test_list_conversations_empty(self, authed_client, owned_canvas):
        resp = await authed_client.get(f"/api/canvases/{owned_canvas.id}/conversations")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_conversation(self, authed_client, owned_canvas):
        create_resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations",
            json={"name": "My Chat"},
        )
        conv_id = create_resp.json()["id"]

        resp = await authed_client.get(
            f"/api/canvases/{owned_canvas.id}/conversations/{conv_id}"
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == conv_id
        assert resp.json()["name"] == "My Chat"

    async def test_get_conversation_wrong_canvas(
        self, authed_client, owned_canvas
    ):
        create_resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations", json={"name": "C"}
        )
        conv_id = create_resp.json()["id"]

        other = await authed_client.post("/api/canvases", json={"name": "Other"})
        other_id = other.json()["id"]

        resp = await authed_client.get(
            f"/api/canvases/{other_id}/conversations/{conv_id}"
        )
        assert resp.status_code == 404

    async def test_delete_conversation(self, authed_client, owned_canvas):
        create_resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations",
            json={"name": "ToDelete"},
        )
        conv_id = create_resp.json()["id"]

        del_resp = await authed_client.delete(
            f"/api/canvases/{owned_canvas.id}/conversations/{conv_id}"
        )
        assert del_resp.status_code == 204

        get_resp = await authed_client.get(
            f"/api/canvases/{owned_canvas.id}/conversations/{conv_id}"
        )
        assert get_resp.status_code == 404

    async def test_delete_conversation_wrong_canvas(
        self, authed_client, owned_canvas
    ):
        create_resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations", json={"name": "C"}
        )
        conv_id = create_resp.json()["id"]

        other = await authed_client.post("/api/canvases", json={"name": "Other"})
        other_id = other.json()["id"]

        resp = await authed_client.delete(
            f"/api/canvases/{other_id}/conversations/{conv_id}"
        )
        assert resp.status_code == 404

    async def test_get_conversation_by_id(self, authed_client, owned_canvas):
        create_resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations",
            json={"name": "Direct Chat"},
        )
        conv_id = create_resp.json()["id"]

        resp = await authed_client.get(f"/api/canvases/conversations/{conv_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == conv_id
        assert resp.json()["name"] == "Direct Chat"

    async def test_delete_conversation_by_id(self, authed_client, owned_canvas):
        create_resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations",
            json={"name": "DirectToDelete"},
        )
        conv_id = create_resp.json()["id"]

        del_resp = await authed_client.delete(f"/api/canvases/conversations/{conv_id}")
        assert del_resp.status_code == 204

        get_resp = await authed_client.get(f"/api/canvases/conversations/{conv_id}")
        assert get_resp.status_code == 404

    async def test_export_and_import_conversation(
        self, authed_client, owned_canvas, test_session
    ):
        import io
        import json
        import zipfile

        create_resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations",
            json={"name": "ExportImportChat"},
        )
        assert create_resp.status_code == 200
        conv_id = create_resp.json()["id"]

        from canvas_server.repos.conversation_repo import ConversationRepo
        repo = ConversationRepo(test_session)

        attachment = await repo.save_attachment(
            conversation_id=uuid.UUID(conv_id),
            content=b"fake-image-bytes",
            format="png",
        )

        await repo.add_message(
            conversation_id=uuid.UUID(conv_id),
            role="user",
            content="Show me a plot",
        )
        await repo.add_message(
            conversation_id=uuid.UUID(conv_id),
            role="assistant",
            content=f"Here is the plot: ![Plot](/api/attachments/{attachment.id})",
        )
        await test_session.commit()

        export_resp = await authed_client.get(
            f"/api/canvases/{owned_canvas.id}/conversations/{conv_id}/export"
        )
        assert export_resp.status_code == 200
        assert export_resp.headers["content-type"] == "application/zip"

        zip_bytes = export_resp.read()
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
        assert "manifest.json" in archive.namelist()
        assert f"attachments/{attachment.id}.png" in archive.namelist()

        manifest_data = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest_data["name"] == "ExportImportChat"
        assert manifest_data["canvas"]["id"] == str(owned_canvas.id)
        assert manifest_data["canvas"]["name"] == owned_canvas.name
        assert len(manifest_data["messages"]) == 2
        assert len(manifest_data["attachments"]) == 1
        assert manifest_data["attachments"][0]["file_type"] == "image"
        assert manifest_data["attachments"][0]["source"] == "agent_output"

        import_resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations/import",
            files={"file": ("export.zip", zip_bytes, "application/zip")},
        )
        assert import_resp.status_code == 200
        imported_data = import_resp.json()
        assert imported_data["name"] == "ExportImportChat"
        assert imported_data["id"] != conv_id

        get_resp = await authed_client.get(
            f"/api/canvases/{owned_canvas.id}/conversations/{imported_data['id']}"
        )
        assert get_resp.status_code == 200
        imported_conv = get_resp.json()
        assert len(imported_conv["messages"]) == 2

        user_msg = imported_conv["messages"][0]
        assistant_msg = imported_conv["messages"][1]

        assert "Show me a plot" in user_msg["content"]
        assert f"![Plot](/api/attachments/{attachment.id})" not in assistant_msg["content"]
        assert "/api/attachments/" in assistant_msg["content"]

    async def test_import_conversation_rejects_wrong_canvas_with_helpful_error(
        self, authed_client, owned_canvas
    ):
        create_resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations",
            json={"name": "Canvas Bound Conversation"},
        )
        assert create_resp.status_code == 200
        conv_id = create_resp.json()["id"]

        export_resp = await authed_client.get(
            f"/api/canvases/{owned_canvas.id}/conversations/{conv_id}/export"
        )
        assert export_resp.status_code == 200

        other_canvas_resp = await authed_client.post(
            "/api/canvases",
            json={"name": "Other Canvas"},
        )
        other_canvas_id = other_canvas_resp.json()["id"]

        import_resp = await authed_client.post(
            f"/api/canvases/{other_canvas_id}/conversations/import",
            files={"file": ("export.zip", export_resp.read(), "application/zip")},
        )

        assert import_resp.status_code == 409
        detail = import_resp.json()["detail"]
        assert "belongs to canvas" in detail.lower()
        assert owned_canvas.name in detail


class TestAttachmentEndToEnd:
    """#87: a plot generated by an `enable_plotting` agent, mid-loop, flows
    through the *same* unified attachment pipeline as any other output
    attachment (#86) — stored as an ``AttachmentInstance`` via
    ``ConversationRepo.save_attachment``, announced via one
    ``attachment_produced`` event + persisted message, and downloadable via
    the existing ``GET /api/attachments/{id}`` endpoint. No bespoke
    markdown-image-link-in-final_answer path remains."""

    async def test_agent_generated_plot_stored_and_downloadable(
        self, authed_client, owned_canvas, test_session
    ):
        import base64
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock, patch

        from llm_sandbox.data import ExecutionResult, FileType, PlotOutput

        from canvas_server.repos.conversation_repo import ConversationRepo
        from canvas_server.runner import CanvasRunner
        from canvas_server.streaming_react import StreamingReAct

        create_resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations",
            json={"name": "Plot Chat"},
        )
        conv_id = uuid.UUID(create_resp.json()["id"])

        repo = ConversationRepo(test_session)

        worker = FakeAgentNode(name="Plotter", agent_type="worker")
        worker.enable_plotting = True
        canvas = FakeCanvas(agent_nodes=[worker])

        runner = CanvasRunner(canvas, conversation_repo=repo, conversation_id=conv_id)

        plot_bytes = b"raw-png-bytes-from-agent-run"
        mock_plot = PlotOutput(
            format=FileType.PNG,
            content_base64=base64.b64encode(plot_bytes).decode(),
        )
        mock_sandbox_manager = MagicMock()
        mock_sandbox_session = MagicMock()
        mock_sandbox_manager.get_session.return_value = mock_sandbox_session
        mock_sandbox_session.run.return_value = ExecutionResult(
            exit_code=0, stdout="", stderr="", plots=[mock_plot]
        )

        async def fake_aforward(self, **kwargs):
            # Simulates the ReAct loop invoking `generate_plot` mid-reasoning
            # — using the *real* tool wired by `AgentFactory.build_worker`
            # (real PlotProvider, real agent_id/name, real live `run_state`),
            # exactly as a genuine StreamingReAct loop would. Patched at the
            # class level (not the instance) because `run()` always calls
            # `setup()` internally, which rebuilds worker agent instances.
            await self.tools["generate_plot"].acall(
                python_code="import matplotlib.pyplot as plt; plt.show()"
            )
            return SimpleNamespace(process_result="Here is your chart.", trajectory={})

        events = []

        async def collect(event):
            events.append(event)

        with (
            patch(
                "canvas_server.runner.plot_provider.get_sandbox",
                new_callable=AsyncMock,
            ) as mock_get_sandbox,
            patch.object(StreamingReAct, "aforward", fake_aforward),
        ):
            mock_get_sandbox.return_value = mock_sandbox_manager

            final_text = await runner.run("Plot the data", collect)

        # `test_session` and `authed_client`'s session factory both point at
        # the same on-disk sqlite file; make sure our writes are fully
        # committed (no lingering implicit transaction) before issuing HTTP
        # requests on a separate connection, to avoid "database is locked".
        await test_session.commit()

        assert final_text == "Here is your chart."

        # Event: the *same* `attachment_produced` event #86 introduced for
        # post-loop output-extraction, not a plot-specific event type.
        produced_events = [e for e in events if e.get("type") == "attachment_produced"]
        assert len(produced_events) == 1
        payload = produced_events[0]
        assert payload["file_type"] == "image"
        assert payload["source"] == "agent_output"
        assert payload["agent"] == "Plotter"
        attachment_id = payload["attachment_id"]

        # Storage: downloadable via the unified endpoint (#79/#83), same as
        # any other output attachment — no separate plot-only storage path.
        download_resp = await authed_client.get(f"/api/attachments/{attachment_id}")
        assert download_resp.status_code == 200
        assert download_resp.content == plot_bytes
        assert download_resp.headers["content-type"] == "image/png"

        # Rendering: the persisted message stream carries an
        # `attachment_produced` entry — what the frontend (ExecutionStepsViewer
        # + ProducedAttachmentCard) renders as an image thumbnail — instead of
        # the old bespoke markdown-image-link embedded in `final_answer`.
        get_resp = await authed_client.get(
            f"/api/canvases/{owned_canvas.id}/conversations/{conv_id}"
        )
        assert get_resp.status_code == 200
        messages = get_resp.json()["messages"]

        attachment_messages = [m for m in messages if m["event_type"] == "attachment_produced"]
        assert len(attachment_messages) == 1
        assert attachment_messages[0]["args"]["attachment_id"] == attachment_id
        assert attachment_messages[0]["args"]["file_type"] == "image"

        final_answer_messages = [m for m in messages if m["event_type"] == "final_answer"]
        assert len(final_answer_messages) == 1
        assert "![Plot]" not in final_answer_messages[0]["content"]

    async def test_save_attachment_rejects_over_size_cap(
        self, test_session, blank_canvas
    ):
        from canvas_server.config import settings
        from canvas_server.exceptions import AttachmentTooLargeError
        from canvas_server.repos.conversation_repo import ConversationRepo

        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="Big Attachment Conv")

        with patch.object(settings, "max_attachment_size_bytes", 10), pytest.raises(
            AttachmentTooLargeError
        ):
            await repo.save_attachment(
                conversation_id=conv.id,
                content=b"way more than ten bytes of content",
                format="png",
            )

    async def test_import_rejects_attachment_over_size_cap(
        self, authed_client, owned_canvas, test_session
    ):
        """The 25MB cap (#83) must also be enforced on ZIP import, not just on
        the direct save_attachment() write path used by live plot generation."""
        import io
        import json
        import zipfile

        from canvas_server.config import settings

        attachment_id = str(uuid.uuid4())
        manifest = {
            "name": "Oversized Import",
            "canvas": {"id": str(owned_canvas.id), "name": owned_canvas.name},
            "status": "active",
            "messages": [],
            "attachments": [
                {
                    "id": attachment_id,
                    "file_type": "image",
                    "source": "agent_output",
                    "format": "png",
                    "created_at": None,
                }
            ],
        }

        with patch.object(settings, "max_attachment_size_bytes", 10):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, mode="w") as zf:
                zf.writestr("manifest.json", json.dumps(manifest))
                zf.writestr(f"attachments/{attachment_id}.png", b"way more than ten bytes")
            buffer.seek(0)

            import_resp = await authed_client.post(
                f"/api/canvases/{owned_canvas.id}/conversations/import",
                files={"file": ("oversized.zip", buffer.read(), "application/zip")},
            )

        assert import_resp.status_code == 400
        assert "exceeds" in import_resp.json()["detail"]


class TestConversationRepo:
    async def test_complete_conversation_sets_status(self, test_session, blank_canvas):
        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="Test Conv")
        conv_id = conv.id
        assert conv.status == "active"

        await repo.complete_conversation(conv_id)
        await test_session.commit()

        fetched = await repo.get(conv_id)
        assert fetched.status == "completed"

    async def test_get_conversation_includes_messages(self, test_session, blank_canvas):
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

    async def test_get_conversation_messages_are_ordered_by_created_at(
        self, test_session, blank_canvas
    ):
        from datetime import UTC, datetime

        from canvas_server.models.canvas import Message

        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="Test Conv")
        conv_id = conv.id

        first = Message(
            conversation_id=conv_id,
            role="user",
            content="First",
            created_at=datetime(2020, 1, 1, 0, 0, tzinfo=UTC),
        )
        second = Message(
            conversation_id=conv_id,
            role="assistant",
            content="Second",
            created_at=datetime(2020, 1, 1, 0, 1, tzinfo=UTC),
        )
        test_session.add_all([second, first])
        await test_session.commit()

        test_session.expire_all()

        fetched = await repo.get(conv_id)
        assert fetched is not None
        assert [msg.content for msg in fetched.messages] == ["First", "Second"]

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

        from canvas_server.models.auth import User
        from canvas_server.repos.canvas_repo import CanvasRepo

        other_owner = User(email=f"other_{uuid.uuid4().hex[:8]}@example.com", password_hash="x")
        test_session.add(other_owner)
        await test_session.flush()
        canvas_repo = CanvasRepo(test_session)
        other = await canvas_repo.create(name="Other Canvas", owner_id=other_owner.id)
        await repo.create(canvas_id=other.id, name="Other Conv")
        await test_session.commit()

        result = await repo.list_for_canvas(canvas_id)
        names = {c.name for c in result}
        assert names == {"A", "B"}

    async def test_update_conversation_name(self, test_session, blank_canvas):
        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="New Conversation")
        await repo.update_name(conv.id, "Weather question")
        await test_session.commit()

        fetched = await repo.get(conv.id)
        assert fetched is not None
        assert fetched.name == "Weather question"


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

    async def test_runner_persists_user_message(self, test_session, blank_canvas):
        worker = FakeAgentNode(id=uuid.uuid4(), name="Worker", agent_type="worker")
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

    async def test_generate_conversation_title(self, test_session, blank_canvas):
        worker = FakeAgentNode(id=uuid.uuid4(), name="Worker", agent_type="worker")
        canvas = FakeCanvas(agent_nodes=[worker])

        repo = ConversationRepo(test_session)
        conv = await repo.create(canvas_id=blank_canvas.id, name="New Conversation")
        conv_id = conv.id

        runner = await self._setup_worker_runner(worker, canvas)
        runner.conversation_repo = repo
        runner.conversation_id = conv_id
        runner._lm.acall = AsyncMock(return_value=[{"content": "Weather question"}])

        title = await runner.generate_conversation_title(
            "What is the weather like today?"
        )
        assert title == "Weather question"

    async def test_runner_keeps_conversation_active(self, test_session, blank_canvas):
        worker = FakeAgentNode(id=uuid.uuid4(), name="Worker", agent_type="worker")
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

    async def test_runner_injects_history_into_router(self, test_session, blank_canvas):
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

        runner = CanvasRunner(canvas, conversation_repo=repo, conversation_id=conv_id)
        runner.setup = AsyncMock()
        runner.node_map = {master.id: master, worker.id: worker}

        worker_mock = self._make_agent_mock("21")
        runner.agents[worker.id] = worker_mock

        with patch.object(runner._agent_factory, "build_router") as mock_builder:
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
        assistant_msgs = [m for m in fetched.messages if m.role == "assistant"]
        assert len(assistant_msgs) >= 1

    async def test_runner_worker_persists_final_answer(
        self, test_session, blank_canvas
    ):
        worker = FakeAgentNode(id=uuid.uuid4(), name="Worker", agent_type="worker")
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
        assistant_msgs = [m for m in fetched.messages if m.role == "assistant"]
        assert len(assistant_msgs) >= 1
        assert assistant_msgs[0].content == "Done!"
        assert assistant_msgs[0].agent_name == "Worker"

    async def test_router_persists_final_answer(self, test_session, blank_canvas):
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

        runner = CanvasRunner(canvas, conversation_repo=repo, conversation_id=conv_id)
        runner.setup = AsyncMock()
        runner.node_map = {master.id: master, worker.id: worker}

        worker_mock = self._make_agent_mock("42")
        runner.agents[worker.id] = worker_mock

        with patch.object(runner._agent_factory, "build_router") as mock_builder:
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

            await runner.run("what is 6*7?", collect, target_agent_id=master.id)

        await test_session.commit()
        test_session.expire_all()

        fetched = await repo.get(conv_id)
        # The router's final answer should be persisted as an assistant message
        assistant_msgs = [m for m in fetched.messages if m.role == "assistant"]
        router_msgs = [m for m in assistant_msgs if m.agent_name == "Master"]
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
        assert (
            len(agent_starts) == 0
        )  # attached events don't fire agent_start for workers
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

        with patch.object(runner._agent_factory, "build_router") as mock_builder:
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
            assert "node_id" in event, f"Event {event['type']} missing node_id"

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

        runner = CanvasRunner(canvas, conversation_repo=repo, conversation_id=conv_id)
        runner.setup = AsyncMock()
        runner.node_map = {
            master_id: master,
            math_team_id: math_team,
            factorial_id: factorial,
        }

        # Load history and format it
        history_messages = await runner._conversation.load_messages()
        history_enabled_ids = {
            n.id for n in canvas.agent_nodes if n.enable_conversation_history
        }
        history_text = runner._conversation.format_history(
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

        runner = CanvasRunner(canvas, conversation_repo=repo, conversation_id=conv_id)
        runner.setup = AsyncMock()
        runner.node_map = {master_id: master, math_team_id: math_team}

        history_messages = await runner._conversation.load_messages()
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
            elif msg.role == "assistant" and msg.node_id in history_enabled_ids:
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

        runner = CanvasRunner(canvas, conversation_repo=repo, conversation_id=conv_id)
        runner.setup = AsyncMock()
        runner.node_map = {master.id: master, worker.id: worker}

        worker_mock = self._make_agent_mock("720")
        runner.agents[worker.id] = worker_mock

        with patch.object(runner._agent_factory, "build_router") as mock_builder:
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
        self, authed_client, owned_canvas
    ):
        create_resp = await authed_client.post(
            f"/api/canvases/{owned_canvas.id}/conversations",
            json={"name": "C1"},
        )
        conv_id = create_resp.json()["id"]

        del_resp = await authed_client.delete(f"/api/canvases/{owned_canvas.id}")
        assert del_resp.status_code == 204

        get_resp = await authed_client.get(
            f"/api/canvases/{owned_canvas.id}/conversations/{conv_id}"
        )
        assert get_resp.status_code == 404

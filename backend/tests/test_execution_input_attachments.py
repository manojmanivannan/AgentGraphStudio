"""Tests for input-attachment delivery wired into the execution strategies
(#88): a directly-targeted worker/router agent (an "entry point," which
otherwise never emits ``agent_start``) resolves and materializes its
declared *input* Attachment node(s) right before the ReAct loop starts,
emitting ``agent_start`` + ``attachment_consumed`` once, only when there is
something to deliver this turn.
"""

import base64
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import dspy
import pytest

from canvas_server.runner.config import RunContext
from canvas_server.runner.execution import RouterExecution, StrategyServices, WorkerExecution


def _edge(source_node_id, target_node_id, edge_type="consumes"):
    return SimpleNamespace(
        source_node_id=source_node_id, target_node_id=target_node_id, edge_type=edge_type
    )


def _attachment_node(node_id, name, file_type, delivery_method="inline"):
    return SimpleNamespace(
        id=node_id, name=name, file_type=file_type, delivery_method=delivery_method
    )


def _instance(instance_id, node_id, content, file_type):
    return SimpleNamespace(
        id=instance_id,
        attachment_node_id=node_id,
        content=content,
        file_type=file_type,
        source="chat_upload",
    )


class FakeAgent:
    def __init__(self, process_result="hello"):
        self._process_result = process_result
        self.last_kwargs = None

    async def aforward(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(process_result=self._process_result, trajectory=None)


def make_harness(
    *,
    agent_type="worker",
    enable_coding=False,
    attachment_nodes=None,
    edges=None,
    unconsumed_attachments=None,
    conversation_id=None,
):
    agent_id = uuid.uuid4()
    fake_agent = FakeAgent()
    node = SimpleNamespace(
        id=agent_id, name="Analyst", agent_type=agent_type, enable_coding=enable_coding,
        enable_network=False,
    )
    conversation_repo = SimpleNamespace(
        get_unconsumed_input_attachments=AsyncMock(
            return_value=unconsumed_attachments or []
        ),
        get_generated_attachments=AsyncMock(return_value=[]),
        mark_attachment_consumed=AsyncMock(),
    )
    conversation_service = SimpleNamespace(
        persist_message=AsyncMock(),
        conversation_repo=conversation_repo,
        conversation_id=conversation_id or uuid.uuid4(),
    )
    canvas = SimpleNamespace(
        name="Demo canvas",
        attachment_nodes=attachment_nodes or [],
        edges=edges or [],
        tool_nodes=[],
    )
    run_state = SimpleNamespace(
        get_or_build_agent=AsyncMock(return_value=fake_agent),
        get_client_response=None,
        node_map={agent_id: node},
        agents={agent_id: fake_agent},
        agent_factory=SimpleNamespace(
            needs_history=lambda n: False,
            build_worker_prompt=lambda prompt, *extra: prompt,
        ),
        conversation_service=conversation_service,
        handoff_tool_builder=None,
        tool_registry=SimpleNamespace(),
        attach_events=lambda *a, **k: None,
        send_event=AsyncMock(),
        user_prompt="analyze this",
        history_text="",
        dspy_history=None,
        canvas=canvas,
    )
    services = StrategyServices(run_state, edge_graph=None, memory_manager=None)
    return SimpleNamespace(
        agent_id=agent_id,
        fake_agent=fake_agent,
        node=node,
        services=services,
        conversation_repo=conversation_repo,
        conversation_service=conversation_service,
    )


@pytest.mark.asyncio
class TestWorkerExecutionInputAttachmentDelivery:
    async def test_no_declared_input_nodes_never_emits_agent_start(self):
        harness = make_harness()
        send_event = AsyncMock()
        ctx = RunContext(
            user_prompt="analyze this", send_event=send_event, target_agent_id=harness.agent_id
        )

        await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        emitted_types = [call.args[0]["type"] for call in send_event.await_args_list]
        assert "agent_start" not in emitted_types
        harness.conversation_repo.get_unconsumed_input_attachments.assert_not_awaited()

    async def test_prior_generated_files_are_listed_for_entry_agent_without_consumes_edge(self):
        attachment_id = uuid.uuid4()
        generated = SimpleNamespace(
            id=attachment_id,
            attachment_node_id=uuid.uuid4(),
            content=b"png-bytes",
            format="png",
            file_type="image",
            source="agent_output",
            original_filename="plot_a1b2c3d4.png",
        )
        harness = make_harness()
        harness.conversation_repo.get_generated_attachments.return_value = [generated]
        harness.services.run_state.consumed_file_attachments = []
        send_event = AsyncMock()
        ctx = RunContext(
            user_prompt="what is the value at 14:00?",
            send_event=send_event,
            target_agent_id=harness.agent_id,
        )

        with patch(
            "canvas_server.runner.input_attachment_delivery._materialize_in_sandbox",
            new=AsyncMock(return_value="/sandbox/attachments/plot_a1b2c3d4.png"),
        ):
            await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        prompt = harness.fake_agent.last_kwargs["user_request"]
        assert "Previously generated attachment file paths:" in prompt
        assert "/sandbox/attachments/plot_a1b2c3d4.png" in prompt
        assert [item.attachment_id for item in harness.services.run_state.consumed_file_attachments] == [
            attachment_id
        ]
        harness.conversation_repo.get_unconsumed_input_attachments.assert_not_awaited()
        # #96: a re-surfaced generated *image* must give the agent actual
        # vision input, not just a text mention that a file exists at a path.
        assert harness.fake_agent.last_kwargs["attachment_image"] == dspy.Image(
            "data:image/png;base64," + base64.b64encode(b"png-bytes").decode("ascii")
        )

    async def test_prior_generated_image_uses_declared_image_field_name(self):
        attachment_node_id = uuid.uuid4()
        generated = SimpleNamespace(
            id=uuid.uuid4(),
            attachment_node_id=attachment_node_id,
            content=b"png-bytes",
            format="png",
            file_type="image",
            source="agent_output",
            original_filename="plot_a1b2c3d4.png",
        )
        harness = make_harness(
            attachment_nodes=[_attachment_node(attachment_node_id, "PlotImage", "image")]
        )
        harness.services.run_state.canvas.edges = [_edge(attachment_node_id, harness.agent_id)]
        harness.conversation_repo.get_generated_attachments.return_value = [generated]
        harness.services.run_state.consumed_file_attachments = []
        ctx = RunContext(
            user_prompt="what is the value at 14:00?",
            send_event=AsyncMock(),
            target_agent_id=harness.agent_id,
        )

        with patch(
            "canvas_server.runner.input_attachment_delivery._materialize_in_sandbox",
            new=AsyncMock(return_value="/sandbox/attachments/plot_a1b2c3d4.png"),
        ):
            await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        assert harness.fake_agent.last_kwargs["plot_image"] == dspy.Image(
            "data:image/png;base64," + base64.b64encode(b"png-bytes").decode("ascii")
        )
        assert "attachment_image" not in harness.fake_agent.last_kwargs

    async def test_prior_generated_non_image_files_do_not_set_attachment_image(self):
        generated = SimpleNamespace(
            id=uuid.uuid4(),
            attachment_node_id=uuid.uuid4(),
            content=b"42.0",
            format="txt",
            file_type="text",
            source="agent_output",
            original_filename="CurrentTemperature.txt",
        )
        harness = make_harness()
        harness.conversation_repo.get_generated_attachments.return_value = [generated]
        harness.services.run_state.consumed_file_attachments = []
        send_event = AsyncMock()
        ctx = RunContext(
            user_prompt="what was the temperature?",
            send_event=send_event,
            target_agent_id=harness.agent_id,
        )

        with patch(
            "canvas_server.runner.input_attachment_delivery._materialize_in_sandbox",
            new=AsyncMock(return_value="/sandbox/attachments/CurrentTemperature.txt"),
        ):
            await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        assert "attachment_image" not in harness.fake_agent.last_kwargs

    async def test_declared_node_with_nothing_unconsumed_never_emits_agent_start(self):
        node_id = uuid.uuid4()
        harness = make_harness(
            attachment_nodes=[_attachment_node(node_id, "Report", "csv")],
            edges=[_edge(node_id, None)],
        )
        harness.services.run_state.canvas.edges = [_edge(node_id, harness.agent_id)]
        send_event = AsyncMock()
        ctx = RunContext(
            user_prompt="analyze this", send_event=send_event, target_agent_id=harness.agent_id
        )

        await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        emitted_types = [call.args[0]["type"] for call in send_event.await_args_list]
        assert "agent_start" not in emitted_types

    async def test_unconsumed_attachment_emits_agent_start_then_attachment_consumed(self):
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        node = _attachment_node(node_id, "Report", "csv", delivery_method="inline")
        instance = _instance(instance_id, node_id, b"a,b\n1,2", file_type="csv")
        harness = make_harness(
            attachment_nodes=[node], unconsumed_attachments=[instance]
        )
        harness.services.run_state.canvas.edges = [_edge(node_id, harness.agent_id)]
        send_event = AsyncMock()
        ctx = RunContext(
            user_prompt="analyze this", send_event=send_event, target_agent_id=harness.agent_id
        )

        await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        emitted_types = [call.args[0]["type"] for call in send_event.await_args_list]
        assert emitted_types.index("agent_start") < emitted_types.index("attachment_consumed")
        consumed_event = next(
            call.args[0] for call in send_event.await_args_list
            if call.args[0]["type"] == "attachment_consumed"
        )
        assert consumed_event["attachment_id"] == str(instance_id)
        assert consumed_event["name"] == "Report"
        assert consumed_event["delivery_method"] == "inline"
        assert consumed_event["agent"] == "Analyst"

        # Attachment content is a trace-visible DSPy input, not prompt text.
        assert harness.fake_agent.last_kwargs["user_request"] == "analyze this"
        assert harness.fake_agent.last_kwargs["report"] == "a,b\n1,2"
        harness.conversation_repo.mark_attachment_consumed.assert_awaited_once_with(instance_id)

    async def test_image_attachment_passes_declared_image_field_kwarg(self):
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        node = _attachment_node(node_id, "PlotImage", "image", delivery_method="inline")
        instance = _instance(instance_id, node_id, b"\x89PNG", file_type="image")
        harness = make_harness(
            attachment_nodes=[node], unconsumed_attachments=[instance], enable_coding=False
        )
        harness.services.run_state.canvas.edges = [_edge(node_id, harness.agent_id)]
        ctx = RunContext(
            user_prompt="analyze this",
            send_event=AsyncMock(),
            target_agent_id=harness.agent_id,
        )

        # Image attachments always attempt "dual" delivery regardless of this
        # agent's own `enable_coding` (#90 — a router may forward the
        # materialized path downstream), so this reaches the real sandbox
        # singleton unless mocked. `get_sandbox` must be patched here or this
        # "unit" test silently pins a real Docker container from the locked
        # pool (max 2) for the rest of the pytest session, starving every
        # later sandbox-dependent test (mirrors the mocking already done in
        # test_input_attachment_delivery.py).
        mock_sandbox = MagicMock()
        mock_session = MagicMock()
        mock_sandbox.get_session.return_value = mock_session
        gs = AsyncMock(return_value=mock_sandbox)

        with patch("canvas_server.runner.input_attachment_delivery.get_sandbox", new=gs):
            await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        image = harness.fake_agent.last_kwargs.get("plot_image")
        assert image is not None
        assert "attachment_image" not in harness.fake_agent.last_kwargs


@pytest.mark.asyncio
class TestRouterExecutionInputAttachmentDelivery:
    async def test_router_entry_point_also_delivers_and_emits_agent_start(self):
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        node = _attachment_node(node_id, "Report", "csv", delivery_method="inline")
        instance = _instance(instance_id, node_id, b"a,b\n1,2", file_type="csv")
        harness = make_harness(
            agent_type="router", attachment_nodes=[node], unconsumed_attachments=[instance]
        )
        harness.services.run_state.canvas.edges = [_edge(node_id, harness.agent_id)]
        send_event = AsyncMock()
        ctx = RunContext(
            user_prompt="analyze this", send_event=send_event, target_agent_id=harness.agent_id
        )

        await RouterExecution(harness.services).execute(harness.agent_id, ctx)

        emitted_types = [call.args[0]["type"] for call in send_event.await_args_list]
        assert "agent_start" in emitted_types
        assert "attachment_consumed" in emitted_types

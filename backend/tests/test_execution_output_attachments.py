"""Tests for output-attachment extraction + storage wired into the execution
strategies (#86): once a worker/router agent's ReAct loop finishes, any
``output_attachments`` the LM emitted are validated against the agent's
declared output Attachment node(s) and stored as ``AttachmentInstance`` rows,
with a matching ``attachment_produced`` event fired once, alongside
``final_answer``.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from canvas_server.exceptions import AttachmentTooLargeError
from canvas_server.runner.config import RunContext
from canvas_server.runner.execution import RouterExecution, WorkerExecution, StrategyServices


def _edge(source_node_id, target_node_id, edge_type="produces"):
    return SimpleNamespace(
        source_node_id=source_node_id, target_node_id=target_node_id, edge_type=edge_type
    )


def _attachment_node(node_id, name, file_type):
    return SimpleNamespace(id=node_id, name=name, file_type=file_type)


class FakeAgent:
    def __init__(self, process_result="hello", output_attachments=None):
        self._process_result = process_result
        self._output_attachments = output_attachments

    async def aforward(self, **kwargs):
        fields = {"process_result": self._process_result, "trajectory": None}
        if self._output_attachments is not None:
            fields["output_attachments"] = self._output_attachments
        return SimpleNamespace(**fields)


def make_harness(
    *,
    agent_type="worker",
    output_attachments=None,
    attachment_nodes=None,
    edges=None,
    save_attachment=None,
    conversation_id=None,
):
    agent_id = uuid.uuid4()
    fake_agent = FakeAgent(output_attachments=output_attachments)
    node = SimpleNamespace(id=agent_id, name="Reporter", agent_type=agent_type)
    conversation_repo = SimpleNamespace(
        save_attachment=save_attachment
        or AsyncMock(
            side_effect=lambda **kwargs: SimpleNamespace(id=uuid.uuid4(), **kwargs)
        )
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
        user_prompt="",
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
class TestWorkerExecutionStoresOutputAttachments:
    async def test_no_declared_output_nodes_means_no_storage_even_with_field(self):
        harness = make_harness(
            output_attachments=[{"name": "report", "file_type": "text", "content": "hi"}],
        )
        ctx = RunContext(
            user_prompt="go", send_event=AsyncMock(), target_agent_id=harness.agent_id
        )

        await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        harness.conversation_repo.save_attachment.assert_not_awaited()

    async def test_matching_attachment_is_stored_and_event_emitted(self):
        attachment_id = uuid.uuid4()
        edges = [_edge(uuid.UUID(int=0), attachment_id)]
        harness = make_harness(
            output_attachments=[{"name": "report", "file_type": "text", "content": "hello"}],
            attachment_nodes=[_attachment_node(attachment_id, "report", "text")],
        )
        # Wire the produces edge from *this* agent, not a placeholder id.
        harness.services.run_state.canvas.edges = [_edge(harness.agent_id, attachment_id)]
        send_event = AsyncMock()
        ctx = RunContext(
            user_prompt="go",
            send_event=send_event,
            target_agent_id=harness.agent_id,
            run_id=uuid.uuid4(),
        )

        result = await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        assert result == "hello"
        harness.conversation_repo.save_attachment.assert_awaited_once()
        call_kwargs = harness.conversation_repo.save_attachment.await_args.kwargs
        assert call_kwargs["content"] == b"hello"
        assert call_kwargs["file_type"] == "text"
        assert call_kwargs["format"] == "txt"
        assert call_kwargs["source"] == "agent_output"
        assert call_kwargs["attachment_node_id"] == attachment_id
        assert call_kwargs["produced_by_run_id"] == ctx.run_id
        assert call_kwargs["conversation_id"] == harness.conversation_service.conversation_id

        produced_events = [
            e for e in send_event.await_args_list if e.args[0].get("type") == "attachment_produced"
        ]
        assert len(produced_events) == 1
        payload = produced_events[0].args[0]
        assert payload["name"] == "report"
        assert payload["file_type"] == "text"
        assert payload["source"] == "agent_output"
        assert payload["run_id"] == str(ctx.run_id)
        assert payload["agent"] == "Reporter"
        assert payload["node_id"] == str(harness.agent_id)
        assert "attachment_id" in payload

        # A persisted message row survives page reload (mirrors final_answer).
        persisted_calls = [
            c
            for c in harness.conversation_service.persist_message.await_args_list
            if c.kwargs.get("event_type") == "attachment_produced"
        ]
        assert len(persisted_calls) == 1

    async def test_attachment_produced_event_fires_before_final_answer_event(self):
        attachment_id = uuid.uuid4()
        harness = make_harness(
            output_attachments=[{"name": "report", "file_type": "text", "content": "hello"}],
            attachment_nodes=[_attachment_node(attachment_id, "report", "text")],
        )
        harness.services.run_state.canvas.edges = [_edge(harness.agent_id, attachment_id)]
        send_event = AsyncMock()
        ctx = RunContext(user_prompt="go", send_event=send_event, target_agent_id=harness.agent_id)

        await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        event_types = [c.args[0].get("type") for c in send_event.await_args_list]
        assert event_types.index("attachment_produced") < event_types.index("final_answer")

    async def test_mismatched_file_type_is_not_stored(self):
        attachment_id = uuid.uuid4()
        harness = make_harness(
            output_attachments=[{"name": "report", "file_type": "csv", "content": "a,b"}],
            attachment_nodes=[_attachment_node(attachment_id, "report", "text")],
        )
        harness.services.run_state.canvas.edges = [_edge(harness.agent_id, attachment_id)]
        ctx = RunContext(user_prompt="go", send_event=AsyncMock(), target_agent_id=harness.agent_id)

        await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        harness.conversation_repo.save_attachment.assert_not_awaited()

    async def test_no_output_attachments_field_on_result_is_a_noop(self):
        attachment_id = uuid.uuid4()
        harness = make_harness(
            output_attachments=None,
            attachment_nodes=[_attachment_node(attachment_id, "report", "text")],
        )
        harness.services.run_state.canvas.edges = [_edge(harness.agent_id, attachment_id)]
        ctx = RunContext(user_prompt="go", send_event=AsyncMock(), target_agent_id=harness.agent_id)

        result = await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        assert result == "hello"
        harness.conversation_repo.save_attachment.assert_not_awaited()

    async def test_too_large_attachment_is_skipped_without_failing_the_run(self):
        attachment_id = uuid.uuid4()
        save_attachment = AsyncMock(side_effect=AttachmentTooLargeError("too big"))
        harness = make_harness(
            output_attachments=[{"name": "report", "file_type": "text", "content": "hello"}],
            attachment_nodes=[_attachment_node(attachment_id, "report", "text")],
            save_attachment=save_attachment,
        )
        harness.services.run_state.canvas.edges = [_edge(harness.agent_id, attachment_id)]
        send_event = AsyncMock()
        ctx = RunContext(user_prompt="go", send_event=send_event, target_agent_id=harness.agent_id)

        result = await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        assert result == "hello"
        event_types = [c.args[0].get("type") for c in send_event.await_args_list]
        assert "attachment_produced" not in event_types
        assert "final_answer" in event_types

    async def test_mismatch_is_surfaced_as_warning_event_and_persisted_message(self):
        """A validation mismatch must not just be logged server-side — it's
        surfaced as a tool-output-style ``warning`` event, plus a durable
        system message, so the agent/user can see and react to it (#86 AC)."""
        attachment_id = uuid.uuid4()
        harness = make_harness(
            output_attachments=[{"name": "report", "file_type": "csv", "content": "a,b"}],
            attachment_nodes=[_attachment_node(attachment_id, "report", "text")],
        )
        harness.services.run_state.canvas.edges = [_edge(harness.agent_id, attachment_id)]
        send_event = AsyncMock()
        ctx = RunContext(user_prompt="go", send_event=send_event, target_agent_id=harness.agent_id)

        await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        warning_events = [
            c.args[0] for c in send_event.await_args_list if c.args[0].get("type") == "warning"
        ]
        assert len(warning_events) == 1
        assert "report" in warning_events[0]["message"]
        assert warning_events[0]["agent"] == "Reporter"

        warning_messages = [
            c
            for c in harness.conversation_service.persist_message.await_args_list
            if c.kwargs.get("event_type") == "warning"
        ]
        assert len(warning_messages) == 1
        assert warning_messages[0].kwargs["role"] == "system"
        assert "report" in warning_messages[0].kwargs["content"]

    async def test_multiple_valid_attachments_each_get_stored_and_emitted(self):
        first_id, second_id = uuid.uuid4(), uuid.uuid4()
        harness = make_harness(
            output_attachments=[
                {"name": "report", "file_type": "text", "content": "hello"},
                {"name": "table", "file_type": "csv", "content": "a,b"},
            ],
            attachment_nodes=[
                _attachment_node(first_id, "report", "text"),
                _attachment_node(second_id, "table", "csv"),
            ],
        )
        harness.services.run_state.canvas.edges = [
            _edge(harness.agent_id, first_id),
            _edge(harness.agent_id, second_id),
        ]
        ctx = RunContext(user_prompt="go", send_event=AsyncMock(), target_agent_id=harness.agent_id)

        await WorkerExecution(harness.services).execute(harness.agent_id, ctx)

        assert harness.conversation_repo.save_attachment.await_count == 2


@pytest.mark.asyncio
class TestRouterExecutionStoresOutputAttachments:
    async def test_matching_attachment_is_stored_and_event_emitted(self):
        attachment_id = uuid.uuid4()
        harness = make_harness(
            agent_type="router",
            output_attachments=[{"name": "report", "file_type": "text", "content": "hello"}],
            attachment_nodes=[_attachment_node(attachment_id, "report", "text")],
        )
        harness.services.run_state.canvas.edges = [_edge(harness.agent_id, attachment_id)]
        send_event = AsyncMock()
        ctx = RunContext(user_prompt="go", send_event=send_event, target_agent_id=harness.agent_id)

        result = await RouterExecution(harness.services).execute(harness.agent_id, ctx)

        assert result == "hello"
        harness.conversation_repo.save_attachment.assert_awaited_once()
        event_types = [c.args[0].get("type") for c in send_event.await_args_list]
        assert "attachment_produced" in event_types

"""Tests for the input-attachment delivery orchestrator (#88): resolves and
materializes chat-uploaded input attachments for a consuming agent right
before its ReAct loop starts.
"""

import asyncio
import shutil
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from canvas_server.runner.input_attachment_delivery import (
    SANDBOX_ATTACHMENT_DIR,
    deliver_input_attachments,
)

requires_docker = pytest.mark.skipif(
    not shutil.which("docker"), reason="Docker not installed"
)


def _edge(edge_type, source_node_id, target_node_id):
    return SimpleNamespace(
        edge_type=edge_type, source_node_id=source_node_id, target_node_id=target_node_id
    )


def _attachment_node(node_id, name="Data", file_type="csv", delivery_method="inline"):
    return SimpleNamespace(id=node_id, name=name, file_type=file_type, delivery_method=delivery_method)


def _instance(instance_id, node_id, content, file_type="csv"):
    return SimpleNamespace(id=instance_id, attachment_node_id=node_id, content=content, file_type=file_type)


def _agent_node(agent_id, enable_coding=False, enable_network=False):
    return SimpleNamespace(id=agent_id, enable_coding=enable_coding, enable_network=enable_network)


def _patch_sandbox(mock_sandbox):
    gs = AsyncMock()
    gs.return_value = mock_sandbox
    return patch("canvas_server.runner.input_attachment_delivery.get_sandbox", new=gs)


@pytest.mark.asyncio
class TestDeliverInputAttachmentsNoOp:
    async def test_no_declared_input_nodes_returns_empty_result(self):
        agent_id = uuid.uuid4()
        canvas = SimpleNamespace(edges=[], attachment_nodes=[], tool_nodes=[])
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(),
            mark_attachment_consumed=AsyncMock(),
        )

        result = await deliver_input_attachments(
            agent_node=_agent_node(agent_id),
            agent_id=agent_id,
            canvas=canvas,
            conversation_repo=conversation_repo,
            conversation_id=uuid.uuid4(),
        )

        assert result.has_any is False
        conversation_repo.get_unconsumed_input_attachments.assert_not_awaited()

    async def test_declared_node_with_no_unconsumed_attachments_returns_empty_result(self):
        agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        node = _attachment_node(node_id)
        canvas = SimpleNamespace(
            edges=[_edge("consumes", node_id, agent_id)],
            attachment_nodes=[node],
            tool_nodes=[],
        )
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(return_value=[]),
            mark_attachment_consumed=AsyncMock(),
        )

        result = await deliver_input_attachments(
            agent_node=_agent_node(agent_id),
            agent_id=agent_id,
            canvas=canvas,
            conversation_repo=conversation_repo,
            conversation_id=uuid.uuid4(),
        )

        assert result.has_any is False


@pytest.mark.asyncio
class TestDeliverInputAttachmentsInlineText:
    async def test_readable_type_inline_preference_is_inlined_without_sandbox(self):
        agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        node = _attachment_node(node_id, name="Report", file_type="csv", delivery_method="inline")
        instance = _instance(instance_id, node_id, b"a,b\n1,2", file_type="csv")
        canvas = SimpleNamespace(
            edges=[_edge("consumes", node_id, agent_id)],
            attachment_nodes=[node],
            tool_nodes=[],
        )
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(return_value=[instance]),
            mark_attachment_consumed=AsyncMock(),
        )

        result = await deliver_input_attachments(
            agent_node=_agent_node(agent_id, enable_coding=False),
            agent_id=agent_id,
            canvas=canvas,
            conversation_repo=conversation_repo,
            conversation_id=uuid.uuid4(),
        )

        assert result.has_any is True
        assert len(result.delivered) == 1
        delivered = result.delivered[0]
        assert delivered.delivery_method == "inline"
        assert delivered.attachment_id == instance_id
        assert result.input_values == {"report": "a,b\n1,2"}
        conversation_repo.mark_attachment_consumed.assert_awaited_once_with(instance_id)


@pytest.mark.asyncio
class TestDeliverInputAttachmentsFilePath:
    async def test_file_path_preference_materializes_into_sandbox_when_agent_has_sandbox(self):
        agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        node = _attachment_node(node_id, name="Report", file_type="csv", delivery_method="file_path")
        instance = _instance(instance_id, node_id, b"a,b\n1,2", file_type="csv")
        canvas = SimpleNamespace(
            edges=[_edge("consumes", node_id, agent_id)],
            attachment_nodes=[node],
            tool_nodes=[],
        )
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(return_value=[instance]),
            mark_attachment_consumed=AsyncMock(),
        )

        mock_sandbox = MagicMock()
        mock_session = MagicMock()
        mock_sandbox.get_session.return_value = mock_session

        with _patch_sandbox(mock_sandbox):
            result = await deliver_input_attachments(
                agent_node=_agent_node(agent_id, enable_coding=True),
                agent_id=agent_id,
                canvas=canvas,
                conversation_repo=conversation_repo,
                conversation_id="conv-1",
            )

        assert result.has_any is True
        delivered = result.delivered[0]
        assert delivered.delivery_method == "file_path"
        assert delivered.sandbox_path == f"{SANDBOX_ATTACHMENT_DIR}/Report"
        assert result.input_values == {"report": delivered.sandbox_path}
        mock_session.copy_to_runtime.assert_called_once()
        conversation_repo.mark_attachment_consumed.assert_awaited_once_with(instance_id)

    async def test_file_path_preference_falls_back_to_inline_without_sandbox(self):
        agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        node = _attachment_node(node_id, name="Report", file_type="csv", delivery_method="file_path")
        instance = _instance(instance_id, node_id, b"a,b\n1,2", file_type="csv")
        canvas = SimpleNamespace(
            edges=[_edge("consumes", node_id, agent_id)],
            attachment_nodes=[node],
            tool_nodes=[],
        )
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(return_value=[instance]),
            mark_attachment_consumed=AsyncMock(),
        )

        result = await deliver_input_attachments(
            agent_node=_agent_node(agent_id, enable_coding=False),
            agent_id=agent_id,
            canvas=canvas,
            conversation_repo=conversation_repo,
            conversation_id=uuid.uuid4(),
        )

        delivered = result.delivered[0]
        assert delivered.delivery_method == "inline"
        assert delivered.sandbox_path is None
        assert result.input_values == {"report": "a,b\n1,2"}

    async def test_binary_type_manifest_only_without_sandbox(self):
        agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        node = _attachment_node(node_id, name="Blob", file_type="binary", delivery_method="inline")
        instance = _instance(instance_id, node_id, b"\x00\x01\x02", file_type="binary")
        canvas = SimpleNamespace(
            edges=[_edge("consumes", node_id, agent_id)],
            attachment_nodes=[node],
            tool_nodes=[],
        )
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(return_value=[instance]),
            mark_attachment_consumed=AsyncMock(),
        )

        result = await deliver_input_attachments(
            agent_node=_agent_node(agent_id, enable_coding=False),
            agent_id=agent_id,
            canvas=canvas,
            conversation_repo=conversation_repo,
            conversation_id=uuid.uuid4(),
        )

        delivered = result.delivered[0]
        assert delivered.delivery_method == "manifest_only"
        assert "Blob" in result.input_values["blob"]

    async def test_sandbox_busy_falls_back_gracefully_instead_of_raising(self):
        agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        node = _attachment_node(node_id, name="Report", file_type="csv", delivery_method="file_path")
        instance = _instance(instance_id, node_id, b"a,b\n1,2", file_type="csv")
        canvas = SimpleNamespace(
            edges=[_edge("consumes", node_id, agent_id)],
            attachment_nodes=[node],
            tool_nodes=[],
        )
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(return_value=[instance]),
            mark_attachment_consumed=AsyncMock(),
        )

        mock_sandbox = MagicMock()
        mock_session = MagicMock()
        mock_sandbox.get_session.return_value = mock_session

        with _patch_sandbox(mock_sandbox), patch(
            "canvas_server.runner.input_attachment_delivery.bounded_session_work",
            new=AsyncMock(return_value=(False, "Code sandbox busy")),
        ):
            result = await deliver_input_attachments(
                agent_node=_agent_node(agent_id, enable_coding=True),
                agent_id=agent_id,
                canvas=canvas,
                conversation_repo=conversation_repo,
                conversation_id="conv-1",
            )

        delivered = result.delivered[0]
        # Falls back to the no-sandbox ladder for a readable type.
        assert delivered.delivery_method == "inline"
        assert delivered.sandbox_path is None
        conversation_repo.mark_attachment_consumed.assert_awaited_once_with(instance_id)


@pytest.mark.asyncio
class TestDeliverInputAttachmentsImage:
    async def test_image_with_sandbox_is_dual_and_materializes_path(self):
        agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        node = _attachment_node(node_id, name="Chart", file_type="image", delivery_method="inline")
        instance = _instance(instance_id, node_id, b"\x89PNG", file_type="image")
        canvas = SimpleNamespace(
            edges=[_edge("consumes", node_id, agent_id)],
            attachment_nodes=[node],
            tool_nodes=[],
        )
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(return_value=[instance]),
            mark_attachment_consumed=AsyncMock(),
        )

        mock_sandbox = MagicMock()
        mock_session = MagicMock()
        mock_sandbox.get_session.return_value = mock_session

        with _patch_sandbox(mock_sandbox):
            result = await deliver_input_attachments(
                agent_node=_agent_node(agent_id, enable_coding=True),
                agent_id=agent_id,
                canvas=canvas,
                conversation_repo=conversation_repo,
                conversation_id="conv-1",
            )

        delivered = result.delivered[0]
        assert delivered.delivery_method == "dual"
        assert delivered.sandbox_path == f"{SANDBOX_ATTACHMENT_DIR}/Chart"
        assert result.image_data_uri == "data:image/png;base64,iVBORw=="

    async def test_image_without_sandbox_is_inline_image_block_only(self):
        agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        node = _attachment_node(node_id, name="Chart", file_type="image", delivery_method="inline")
        instance = _instance(instance_id, node_id, b"\x89PNG", file_type="image")
        canvas = SimpleNamespace(
            edges=[_edge("consumes", node_id, agent_id)],
            attachment_nodes=[node],
            tool_nodes=[],
        )
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(return_value=[instance]),
            mark_attachment_consumed=AsyncMock(),
        )

        result = await deliver_input_attachments(
            agent_node=_agent_node(agent_id, enable_coding=False),
            agent_id=agent_id,
            canvas=canvas,
            conversation_repo=conversation_repo,
            conversation_id=uuid.uuid4(),
        )

        delivered = result.delivered[0]
        assert delivered.delivery_method == "inline"
        assert delivered.sandbox_path is None
        assert result.image_data_uri == "data:image/png;base64,iVBORw=="


@pytest.mark.asyncio
class TestDeliverInputAttachmentsNetworkPoolRouting:
    """A materialized file must land in the SAME sandbox session the
    consuming agent's own `run_code`/`pip_install` tools use — those tools
    are bound to a `CodeProvider` on `NETWORK_POOL_NETWORKED` when the agent
    has `enable_network`, mirroring `AgentFactory`'s own pool selection
    (`agent_factory.py`'s `network_pool = NETWORK_POOL_NETWORKED if
    enable_network else NETWORK_POOL_DEFAULT`). Materializing into the wrong
    pool would put the file out of reach of that session.
    """

    async def test_network_enabled_agent_materializes_into_networked_pool(self):
        from canvas_server.sandbox import NETWORK_POOL_NETWORKED

        agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        node = _attachment_node(node_id, name="Report", file_type="csv", delivery_method="file_path")
        instance = _instance(instance_id, node_id, b"a,b\n1,2", file_type="csv")
        canvas = SimpleNamespace(
            edges=[_edge("consumes", node_id, agent_id)],
            attachment_nodes=[node],
            tool_nodes=[],
        )
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(return_value=[instance]),
            mark_attachment_consumed=AsyncMock(),
        )

        mock_sandbox = MagicMock()
        mock_session = MagicMock()
        mock_sandbox.get_session.return_value = mock_session

        with _patch_sandbox(mock_sandbox):
            await deliver_input_attachments(
                agent_node=_agent_node(agent_id, enable_coding=True, enable_network=True),
                agent_id=agent_id,
                canvas=canvas,
                conversation_repo=conversation_repo,
                conversation_id="conv-1",
            )

        _, kwargs = mock_sandbox.get_session.call_args
        assert kwargs["network_pool"] == NETWORK_POOL_NETWORKED

    async def test_non_network_agent_materializes_into_default_pool(self):
        from canvas_server.sandbox import NETWORK_POOL_DEFAULT

        agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        node = _attachment_node(node_id, name="Report", file_type="csv", delivery_method="file_path")
        instance = _instance(instance_id, node_id, b"a,b\n1,2", file_type="csv")
        canvas = SimpleNamespace(
            edges=[_edge("consumes", node_id, agent_id)],
            attachment_nodes=[node],
            tool_nodes=[],
        )
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(return_value=[instance]),
            mark_attachment_consumed=AsyncMock(),
        )

        mock_sandbox = MagicMock()
        mock_session = MagicMock()
        mock_sandbox.get_session.return_value = mock_session

        with _patch_sandbox(mock_sandbox):
            await deliver_input_attachments(
                agent_node=_agent_node(agent_id, enable_coding=True, enable_network=False),
                agent_id=agent_id,
                canvas=canvas,
                conversation_repo=conversation_repo,
                conversation_id="conv-1",
            )

        _, kwargs = mock_sandbox.get_session.call_args
        assert kwargs["network_pool"] == NETWORK_POOL_DEFAULT


@pytest.mark.asyncio
class TestDeliverInputAttachmentsMultiple:
    async def test_multiple_attachments_all_marked_consumed_and_concatenated(self):
        agent_id = uuid.uuid4()
        node_a = _attachment_node(uuid.uuid4(), name="A", file_type="csv")
        node_b = _attachment_node(uuid.uuid4(), name="B", file_type="text")
        instance_a = _instance(uuid.uuid4(), node_a.id, b"content-a", file_type="csv")
        instance_b = _instance(uuid.uuid4(), node_b.id, b"content-b", file_type="text")
        canvas = SimpleNamespace(
            edges=[
                _edge("consumes", node_a.id, agent_id),
                _edge("consumes", node_b.id, agent_id),
            ],
            attachment_nodes=[node_a, node_b],
            tool_nodes=[],
        )
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(return_value=[instance_a, instance_b]),
            mark_attachment_consumed=AsyncMock(),
        )

        result = await deliver_input_attachments(
            agent_node=_agent_node(agent_id, enable_coding=False),
            agent_id=agent_id,
            canvas=canvas,
            conversation_repo=conversation_repo,
            conversation_id=uuid.uuid4(),
        )

        assert len(result.delivered) == 2
        assert result.input_values == {"a": "content-a", "b": "content-b"}
        assert conversation_repo.mark_attachment_consumed.await_count == 2


@pytest.mark.asyncio
class TestDeliverInputAttachmentsRealDockerE2E:
    """End-to-end (#88 acceptance criterion): a csv attachment matching a
    coding-enabled entry agent's declared ``file_path`` input node is
    materialized into a *real* Docker sandbox session, and a subsequent
    sandbox tool call in that same conversation session can read the exact
    file back — no mocked sandbox involved. This is the one path the
    mocked-sandbox tests above cannot exercise: real ``copy_to_runtime``
    into a real container, and a real process reading it back from disk.

    ``attachment_consumed`` event emission (right after ``agent_start``,
    with the resolved delivery method and attachment identity) is covered
    end-to-end against the real orchestrator call site in
    ``test_execution_input_attachments.py``, and the chat-side rendering of
    that event is covered by ``ConsumedAttachmentCard.test.tsx`` and
    ``ExecutionStepsViewer.test.tsx`` on the frontend.
    """

    @requires_docker
    async def test_csv_file_path_delivery_is_readable_by_sandbox_tool(self):
        from canvas_server.runner.code_provider import CodeProvider

        conversation_id = f"test-attachment-delivery-e2e-{uuid.uuid4()}"
        agent_id = uuid.uuid4()
        node_id = uuid.uuid4()
        instance_id = uuid.uuid4()
        csv_content = b"name,age\nAda,30\nGrace,85\n"

        node = _attachment_node(
            node_id, name="People", file_type="csv", delivery_method="file_path"
        )
        instance = _instance(instance_id, node_id, csv_content, file_type="csv")
        canvas = SimpleNamespace(
            edges=[_edge("consumes", node_id, agent_id)],
            attachment_nodes=[node],
            tool_nodes=[],
        )
        conversation_repo = SimpleNamespace(
            get_unconsumed_input_attachments=AsyncMock(return_value=[instance]),
            mark_attachment_consumed=AsyncMock(),
        )

        result = await deliver_input_attachments(
            agent_node=_agent_node(agent_id, enable_coding=True),
            agent_id=agent_id,
            canvas=canvas,
            conversation_repo=conversation_repo,
            conversation_id=conversation_id,
        )

        delivered = result.delivered[0]
        assert delivered.delivery_method == "file_path"
        sandbox_path = delivered.sandbox_path
        assert sandbox_path == f"{SANDBOX_ATTACHMENT_DIR}/People"
        assert conversation_repo.mark_attachment_consumed.await_count == 1

        # Same conversation_id -> same (locked-pool) sandbox session, so a
        # tool call here reads back exactly what was materialized above.
        provider = CodeProvider(conversation_id=conversation_id)
        read_back = ""
        for _ in range(8):
            read_back = await provider.run_code(f"print(open('{sandbox_path}').read())")
            if "busy" not in read_back.lower():
                break
            await asyncio.sleep(2)

        assert read_back.strip() == csv_content.decode("utf-8").strip()

        # Release the turn's pinned container so the test does not leak it
        # (locked pool max is only 2 — mirrors test_code_provider.py's real
        # execution tests).
        from canvas_server.sandbox import get_sandbox

        sandbox = await get_sandbox()
        sandbox.release_session(conversation_id)

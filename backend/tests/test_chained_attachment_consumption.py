"""Chained downstream/upstream attachment consumption end-to-end (#89):
agent A produces a csv output attachment, and agent B — a different agent
reached via handoff, wired to the *same* Attachment node as a declared input
with ``file_path`` delivery — consumes it exactly like a chat-uploaded input
would be consumed (#88).

This exercises the real production chain across the pieces #89 wires
together: ``ExecutionStrategy._store_output_attachments`` storing agent A's
output as an ``AttachmentInstance`` (source ``agent_output``, #86), the
widened ``ConversationRepo.get_unconsumed_input_attachments`` surfacing that
same-node instance as unconsumed input for agent B regardless of source
(#89), and ``deliver_and_announce_input_attachments`` — the exact shared
function ``HandoffToolBuilder.transfer`` calls with ``emit_agent_start=True``
— materializing it into a *real* Docker sandbox session for agent B and
emitting ``agent_start``/``attachment_consumed`` in order, whose own
``run_code`` sandbox tool call then reads back the exact bytes agent A
produced, proving the file handoff works end-to-end and not just that an
event fired.
"""

from __future__ import annotations

import asyncio
import shutil
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from canvas_server.repos.conversation_repo import ConversationRepo
from canvas_server.runner.config import RunContext
from canvas_server.runner.execution import StrategyServices, WorkerExecution
from canvas_server.runner.input_attachment_delivery import (
    SANDBOX_ATTACHMENT_DIR,
    deliver_and_announce_input_attachments,
)

requires_docker = pytest.mark.skipif(not shutil.which("docker"), reason="Docker not installed")


def _edge(source_node_id, target_node_id, edge_type):
    return SimpleNamespace(
        source_node_id=source_node_id, target_node_id=target_node_id, edge_type=edge_type
    )


def _attachment_node(node_id, name, file_type, delivery_method="inline"):
    return SimpleNamespace(
        id=node_id, name=name, file_type=file_type, delivery_method=delivery_method
    )


class _ProducingAgent:
    """A minimal stand-in for agent A's named CSV attachment output field."""

    def __init__(self, orders):
        self._orders = orders

    async def aforward(self, **kwargs):
        return SimpleNamespace(
            process_result="Report generated.",
            trajectory=None,
            orders=self._orders,
        )


@pytest.fixture
async def conversation(test_session, blank_canvas):
    repo = ConversationRepo(test_session)
    conv = await repo.create(canvas_id=blank_canvas.id, name="Chained Attachment Chat")
    await test_session.commit()
    return conv


@pytest.mark.asyncio
class TestChainedAgentOutputConsumedByHandoffTarget:
    async def _run_agent_a(self, *, conversation_repo, conversation_id, shared_node_id, csv_content):
        """Runs agent A end-to-end through ``WorkerExecution`` so the stored
        ``AttachmentInstance`` comes from the real #86 output-extraction/
        storage pipeline, not a hand-rolled ``save_attachment`` call."""
        agent_a_id = uuid.uuid4()
        node_a = SimpleNamespace(id=agent_a_id, name="Producer", agent_type="worker")
        canvas_a = SimpleNamespace(
            name="Chained canvas",
            attachment_nodes=[_attachment_node(shared_node_id, "orders", "csv")],
            edges=[_edge(agent_a_id, shared_node_id, "produces")],
        )
        run_state_a = SimpleNamespace(
            get_or_build_agent=AsyncMock(
                return_value=_ProducingAgent(
                    orders=csv_content
                )
            ),
            get_client_response=None,
            node_map={agent_a_id: node_a},
            agent_factory=SimpleNamespace(
                needs_history=lambda n: False,
                build_worker_prompt=lambda prompt, *extra: prompt,
            ),
            conversation_service=SimpleNamespace(
                persist_message=AsyncMock(),
                conversation_repo=conversation_repo,
                conversation_id=conversation_id,
            ),
            canvas=canvas_a,
        )
        services_a = StrategyServices(run_state_a, edge_graph=None, memory_manager=None)
        ctx_a = RunContext(
            user_prompt="produce the orders data",
            send_event=AsyncMock(),
            target_agent_id=agent_a_id,
        )

        result = await WorkerExecution(services_a).execute(agent_a_id, ctx_a)
        assert result == "Report generated."

    @requires_docker
    async def test_agent_b_sandbox_tool_reads_file_agent_a_produced(
        self, test_session, conversation
    ):
        from canvas_server.runner.code_provider import CodeProvider
        from canvas_server.sandbox import get_sandbox

        conversation_repo = ConversationRepo(test_session)
        shared_node_id = uuid.uuid4()
        csv_content = "name,age\nAda,30\nGrace,85"

        # --- Agent A produces the csv output attachment (#86). ---
        await self._run_agent_a(
            conversation_repo=conversation_repo,
            conversation_id=conversation.id,
            shared_node_id=shared_node_id,
            csv_content=csv_content,
        )

        # --- Agent B, reached via handoff, declares the SAME Attachment
        # node as a `file_path` input (#89): the widened repo query now
        # surfaces agent A's `agent_output` instance as unconsumed input
        # for B, exactly as it would a chat upload. We drive this through
        # ``deliver_and_announce_input_attachments`` with
        # ``emit_agent_start=True`` — the exact shared function and flag
        # value ``HandoffToolBuilder.transfer`` uses in ``handoff.py`` — so
        # this proves the ``attachment_consumed`` event fires right after
        # ``agent_start`` for the chained/downstream case too (AC#2), not
        # just that the bytes round-trip through the sandbox.
        agent_b_id = uuid.uuid4()
        canvas_b = SimpleNamespace(
            edges=[_edge(shared_node_id, agent_b_id, "consumes")],
            attachment_nodes=[
                _attachment_node(shared_node_id, "orders", "csv", delivery_method="file_path")
            ],
            tool_nodes=[],
        )
        agent_node_b = SimpleNamespace(
            id=agent_b_id, name="Consumer", agent_type="worker",
            enable_coding=True, enable_network=False,
        )
        send_event_b = AsyncMock()

        await deliver_and_announce_input_attachments(
            agent_node=agent_node_b,
            agent_id=agent_b_id,
            canvas=canvas_b,
            conversation_repo=conversation_repo,
            conversation_id=conversation.id,
            conversation_service=None,
            send_event=send_event_b,
            run_id=None,
            user_prompt="continue the analysis",
            emit_agent_start=True,
        )

        emitted_types = [call.args[0]["type"] for call in send_event_b.await_args_list]
        assert emitted_types.index("agent_start") < emitted_types.index("attachment_consumed")

        sandbox_path = f"{SANDBOX_ATTACHMENT_DIR}/orders"

        # Consumed — a later turn must never redeliver the same instance.
        remaining = await conversation_repo.get_unconsumed_input_attachments(
            conversation.id, [shared_node_id]
        )
        assert remaining == []

        # --- B's own sandbox tool call reads the exact file A produced,
        # from the same conversation's real Docker sandbox session. ---
        provider = CodeProvider(conversation_id=conversation.id)
        read_back = ""
        for _ in range(8):
            read_back = await provider.run_code(f"print(open('{sandbox_path}').read())")
            if "busy" not in read_back.lower():
                break
            await asyncio.sleep(2)

        assert read_back.strip() == csv_content.strip()

        # Release the turn's pinned container so the test does not leak it
        # (locked pool max is only 2 — mirrors
        # test_input_attachment_delivery.py's real-Docker e2e test).
        sandbox = await get_sandbox()
        sandbox.release_session(conversation.id)

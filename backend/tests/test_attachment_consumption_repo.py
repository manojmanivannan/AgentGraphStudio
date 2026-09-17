import uuid

import pytest

from canvas_server.repos.conversation_repo import ConversationRepo


@pytest.fixture
async def conversation(test_session, blank_canvas):
    repo = ConversationRepo(test_session)
    conv = await repo.create(canvas_id=blank_canvas.id, name="Attachment Delivery Chat")
    await test_session.commit()
    return conv


class TestGetUnconsumedInputAttachments:
    async def test_returns_chat_uploads_and_agent_outputs_for_declared_nodes_not_yet_consumed(
        self, test_session, conversation
    ):
        """Both chat-uploaded instances *and* agent-produced instances count
        as unconsumed input for a declared node (#89): the same Attachment
        node can be wired as an output slot for a producing agent (a
        ``produces`` edge) and, simultaneously, an input slot for a
        different, downstream/upstream agent reached via handoff (a
        ``consumes`` edge) — so an agent-output instance must be delivered
        to that consumer exactly like a chat upload is.
        """
        repo = ConversationRepo(test_session)
        node_id = uuid.uuid4()
        other_node_id = uuid.uuid4()

        chat_upload = await repo.save_attachment(
            conversation_id=conversation.id,
            content=b"a,b\n1,2",
            format="csv",
            file_type="csv",
            source="chat_upload",
            attachment_node_id=node_id,
        )
        # Different declared node: excluded.
        await repo.save_attachment(
            conversation_id=conversation.id,
            content=b"other",
            format="txt",
            file_type="text",
            source="chat_upload",
            attachment_node_id=other_node_id,
        )
        # Agent-produced output for the SAME declared node: included (#89) —
        # this is what makes a chained agent-A-produces → agent-B-consumes
        # handoff flow work.
        agent_output = await repo.save_attachment(
            conversation_id=conversation.id,
            content=b"png-bytes",
            format="png",
            file_type="image",
            source="agent_output",
            attachment_node_id=node_id,
        )
        await test_session.commit()

        result = await repo.get_unconsumed_input_attachments(conversation.id, [node_id])

        assert {a.id for a in result} == {chat_upload.id, agent_output.id}
        # Ordered by created_at (chat_upload was saved first).
        assert [a.id for a in result] == [chat_upload.id, agent_output.id]

    async def test_excludes_already_consumed_attachments(self, test_session, conversation):
        repo = ConversationRepo(test_session)
        node_id = uuid.uuid4()

        attachment = await repo.save_attachment(
            conversation_id=conversation.id,
            content=b"a,b\n1,2",
            format="csv",
            file_type="csv",
            source="chat_upload",
            attachment_node_id=node_id,
        )
        await test_session.commit()

        await repo.mark_attachment_consumed(attachment.id)

        result = await repo.get_unconsumed_input_attachments(conversation.id, [node_id])

        assert result == []

    async def test_empty_node_ids_returns_empty_list_without_querying(
        self, test_session, conversation
    ):
        repo = ConversationRepo(test_session)
        assert await repo.get_unconsumed_input_attachments(conversation.id, []) == []


class TestMarkAttachmentConsumed:
    async def test_sets_consumed_at_timestamp(self, test_session, conversation):
        repo = ConversationRepo(test_session)
        node_id = uuid.uuid4()
        attachment = await repo.save_attachment(
            conversation_id=conversation.id,
            content=b"a,b\n1,2",
            format="csv",
            file_type="csv",
            source="chat_upload",
            attachment_node_id=node_id,
        )
        await test_session.commit()
        assert attachment.consumed_at is None

        await repo.mark_attachment_consumed(attachment.id)

        refreshed = await repo.get_attachment(attachment.id)
        assert refreshed is not None
        assert refreshed.consumed_at is not None

    async def test_is_a_no_op_for_unknown_attachment_id(self, test_session, conversation):
        repo = ConversationRepo(test_session)
        # Must not raise.
        await repo.mark_attachment_consumed(uuid.uuid4())

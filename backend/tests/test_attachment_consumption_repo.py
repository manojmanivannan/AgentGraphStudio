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
    async def test_returns_only_chat_uploads_for_declared_nodes_not_yet_consumed(
        self, test_session, conversation
    ):
        repo = ConversationRepo(test_session)
        node_id = uuid.uuid4()
        other_node_id = uuid.uuid4()

        wanted = await repo.save_attachment(
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
        # Agent-produced output, not a chat upload: excluded even if it
        # happens to share a node id.
        await repo.save_attachment(
            conversation_id=conversation.id,
            content=b"png-bytes",
            format="png",
            file_type="image",
            source="agent_output",
            attachment_node_id=node_id,
        )
        await test_session.commit()

        result = await repo.get_unconsumed_input_attachments(conversation.id, [node_id])

        assert [a.id for a in result] == [wanted.id]

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

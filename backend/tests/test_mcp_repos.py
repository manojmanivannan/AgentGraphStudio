"""McpServerRepo basics: CRUD round-trip, name/URL persistence (#129)."""

import uuid

import pytest

from canvas_server.models.mcp import McpServer
from canvas_server.repos.mcp_repo import McpServerRepo


@pytest.fixture
async def one_server(test_session):
    repo = McpServerRepo(test_session)
    return await repo.create(
        name="Context7",
        url="https://mcp.context7.com/mcp",
        credential_header="Authorization",
        credential_value="Bearer ctx7-secret-token",
    )


class TestMcpServerRepoCreate:
    async def test_create_persists_name_and_url(self, test_session, one_server):
        repo = McpServerRepo(test_session)
        row = await repo.get(one_server.id)
        assert row is not None
        assert row.name == "Context7"
        assert row.url == "https://mcp.context7.com/mcp"
        assert row.id == one_server.id

    async def test_create_defaults_header_and_no_credential(self, test_session):
        repo = McpServerRepo(test_session)
        row = await repo.create(name="Local", url="http://localhost:8000/mcp")
        assert row.credential_header == "Authorization"
        assert row.credential_value is None

    async def test_create_generates_uuid_pk(self, test_session, one_server):
        assert isinstance(one_server.id, uuid.UUID)

    async def test_created_row_is_queryable_after_flush(self, test_session):
        repo = McpServerRepo(test_session)
        await repo.create(
            name="DeepWiki",
            url="https://mcp.deepwiki.com/mcp",
            credential_value="Bearer dw-token",
        )
        rows = await repo.list()
        assert [row.name for row in rows] == ["DeepWiki"]
        assert rows[0].credential_value == "Bearer dw-token"


class TestMcpServerRepoList:
    async def test_list_empty(self, test_session):
        assert await McpServerRepo(test_session).list() == []

    async def test_list_is_ordered_by_name(self, test_session):
        repo = McpServerRepo(test_session)
        for name in ["zeta", "alpha", "mike"]:
            await repo.create(name=name, url="https://example.com/mcp")
        assert [row.name for row in await repo.list()] == ["alpha", "mike", "zeta"]


class TestMcpServerRepoGet:
    async def test_get_missing_returns_none(self, test_session):
        assert await McpServerRepo(test_session).get(uuid.uuid4()) is None

    async def test_get_isolated_from_other_rows(self, test_session, one_server):
        other = await McpServerRepo(test_session).create(
            name="Other", url="https://other.example/mcp"
        )
        repo = McpServerRepo(test_session)
        row = await repo.get(other.id)
        assert row.credential_value is None
        row = await repo.get(one_server.id)
        assert row.credential_value == "Bearer ctx7-secret-token"


class TestMcpServerRepoReferencingCanvases:
    """Deletion-guard lookup (#132): which canvases hold a Tool Node granting
    tools from this server."""

    async def _canvas_with_grant(self, test_session, owner_id, server_id, name):
        from canvas_server.models.api import ToolNodeInput
        from canvas_server.repos.canvas_repo import CanvasRepo

        canvas = await CanvasRepo(test_session).create(name, owner_id=owner_id)
        await CanvasRepo(test_session).save_nodes_and_edges(
            canvas.id,
            name,
            [],
            [
                ToolNodeInput(
                    id=uuid.uuid4(),
                    name="MCP Tools",
                    mcp_server_id=server_id,
                    mcp_tools=[{"name": "web_search", "requires_approval": False}],
                )
            ],
            [],
        )
        return canvas

    async def test_lists_canvas_id_and_name_for_referencing_nodes(
        self, test_session, test_user, one_server
    ):
        canvas = await self._canvas_with_grant(
            test_session, test_user.id, one_server.id, "Docs Canvas"
        )
        referencing = await McpServerRepo(test_session).list_referencing_canvases(
            one_server.id
        )
        assert [(c.id, c.name) for c in referencing] == [(canvas.id, "Docs Canvas")]

    async def test_lists_every_referencing_canvas_distinct(self, test_session, test_user):
        server = await McpServerRepo(test_session).create(
            name="Shared", url="https://shared.example/mcp"
        )
        await test_session.commit()
        c1 = await self._canvas_with_grant(test_session, test_user.id, server.id, "C1")
        c2 = await self._canvas_with_grant(test_session, test_user.id, server.id, "C2")
        # A second node in one canvas referencing the same server must not
        # duplicate the canvas in the result.
        from canvas_server.models.api import ToolNodeInput
        from canvas_server.repos.canvas_repo import CanvasRepo

        await CanvasRepo(test_session).save_nodes_and_edges(
            c2.id,
            "C2",
            [],
            [
                ToolNodeInput(
                    id=uuid.uuid4(),
                    name="Other Tools",
                    mcp_server_id=server.id,
                    mcp_tools=[{"name": "docs", "requires_approval": True}],
                )
            ],
            [],
        )
        referencing = await McpServerRepo(test_session).list_referencing_canvases(
            server.id
        )
        assert sorted(c.id for c in referencing) == sorted([c1.id, c2.id])

    async def test_unreferenced_server_has_no_referencing_canvases(
        self, test_session, one_server
    ):
        assert (
            await McpServerRepo(test_session).list_referencing_canvases(one_server.id)
            == []
        )


class TestMcpServerRepoUpdate:
    async def test_update_changes_fields(self, test_session, one_server):
        repo = McpServerRepo(test_session)
        updated = await repo.update(
            one_server,
            name="Context7 Renamed",
            url="https://upstream.context7.dev/mcp",
            credential_header="X-Api-Key",
            credential_value="new-secret",
        )
        assert updated.name == "Context7 Renamed"
        assert updated.url == "https://upstream.context7.dev/mcp"
        assert updated.credential_header == "X-Api-Key"
        assert updated.credential_value == "new-secret"

    async def test_update_none_keeps_stored_credential(self, test_session, one_server):
        repo = McpServerRepo(test_session)
        updated = await repo.update(one_server, name="still-here", credential_value=None)
        assert updated.name == "still-here"
        assert updated.credential_value == "Bearer ctx7-secret-token"

    async def test_update_empty_string_clears_credential(self, test_session, one_server):
        repo = McpServerRepo(test_session)
        updated = await repo.update(one_server, credential_value="")
        assert updated.credential_value is None

    async def test_update_persists_across_sessions(self, test_session, one_server):
        await McpServerRepo(test_session).update(one_server, name="persisted")
        row = await McpServerRepo(test_session).get(one_server.id)
        assert row.name == "persisted"


class TestMcpServerRepoDelete:
    async def test_delete_removes_row(self, test_session, one_server):
        repo = McpServerRepo(test_session)
        await repo.delete(one_server)
        assert await repo.get(one_server.id) is None
        assert await repo.list() == []

    async def test_deleted_model_is_the_orm_class(self, one_server):
        assert isinstance(one_server, McpServer)

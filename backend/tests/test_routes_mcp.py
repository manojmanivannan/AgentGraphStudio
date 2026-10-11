"""MCP server registry routes: CRUD, redaction, URL policy, cache (#129)."""

import pytest

from canvas_server.mcp_config import get_mcp_servers, reset_mcp_servers_cache

ORIGIN = {"Origin": "http://test"}

SECRET = "Bearer sk-live-abcdefghij123456"


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_mcp_servers_cache()
    yield
    reset_mcp_servers_cache()


async def _create(authed_client, **overrides):
    body = {
        "name": "Context7",
        "url": "https://mcp.context7.com/mcp",
        "credential_header": "Authorization",
        "credential_value": SECRET,
    } | overrides
    return await authed_client.post("/api/mcp/servers", json=body, headers=ORIGIN)


class TestAuth:
    async def test_list_requires_auth(self, test_client):
        assert (await test_client.get("/api/mcp/servers")).status_code == 401

    async def test_create_requires_auth(self, test_client):
        res = await test_client.post(
            "/api/mcp/servers",
            json={"name": "x", "url": "https://example.com/mcp"},
            headers=ORIGIN,
        )
        assert res.status_code == 401

    async def test_update_requires_auth(self, test_client):
        res = await test_client.put(
            "/api/mcp/servers/00000000-0000-0000-0000-000000000000",
            json={"name": "x", "url": "https://example.com/mcp"},
            headers=ORIGIN,
        )
        assert res.status_code == 401

    async def test_delete_requires_auth(self, test_client):
        res = await test_client.delete(
            "/api/mcp/servers/00000000-0000-0000-0000-000000000000",
            headers=ORIGIN,
        )
        assert res.status_code == 401

    async def test_create_requires_same_origin(self, authed_client):
        res = await authed_client.post(
            "/api/mcp/servers",
            json={"name": "x", "url": "https://example.com/mcp"},
            headers={"Origin": "http://evil.example"},
        )
        assert res.status_code == 403


class TestCrudRoundTrip:
    async def test_create_then_get_by_id_keeps_name_and_url(self, authed_client):
        res = await _create(authed_client)
        assert res.status_code == 201, res.text
        created = res.json()
        assert created["name"] == "Context7"
        assert created["url"] == "https://mcp.context7.com/mcp"

        listed = (await authed_client.get("/api/mcp/servers")).json()["servers"]
        assert [s["name"] for s in listed] == ["Context7"]
        assert listed[0]["url"] == "https://mcp.context7.com/mcp"
        assert listed[0]["id"] == created["id"]

    async def test_create_defaults_header(self, authed_client):
        res = await _create(authed_client, credential_header=None)
        assert res.json()["credential_header"] == "Authorization"

    async def test_update_changes_fields(self, authed_client):
        created = (await _create(authed_client)).json()
        res = await authed_client.put(
            f"/api/mcp/servers/{created['id']}",
            json={
                "name": "Renamed",
                "url": "https://mcp.upstream.example/v2/mcp",
                "credential_header": "X-Api-Key",
            },
            headers=ORIGIN,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["name"] == "Renamed"
        assert body["url"] == "https://mcp.upstream.example/v2/mcp"
        assert body["credential_header"] == "X-Api-Key"

    async def test_update_missing_server_is_404(self, authed_client):
        res = await authed_client.put(
            "/api/mcp/servers/00000000-0000-0000-0000-000000000000",
            json={"name": "x", "url": "https://example.com/mcp"},
            headers=ORIGIN,
        )
        assert res.status_code == 404

    async def test_delete_removes_the_server(self, authed_client):
        created = (await _create(authed_client)).json()
        res = await authed_client.delete(
            f"/api/mcp/servers/{created['id']}", headers=ORIGIN
        )
        assert res.status_code == 204
        listed = (await authed_client.get("/api/mcp/servers")).json()["servers"]
        assert listed == []

    async def test_list_ordered_by_name(self, authed_client):
        await _create(authed_client, name="zeta")
        await _create(authed_client, name="alpha")
        listed = (await authed_client.get("/api/mcp/servers")).json()["servers"]
        assert [s["name"] for s in listed] == ["alpha", "zeta"]


class TestCredentialRedaction:
    async def test_create_response_never_returns_the_credential(self, authed_client):
        res = await _create(authed_client)
        body = res.json()
        assert body["credential_set"] is True
        assert "credential_value" not in body
        assert SECRET not in res.text

    async def test_list_response_never_returns_the_credential(self, authed_client):
        await _create(authed_client)
        res = await authed_client.get("/api/mcp/servers")
        assert "credential_value" not in res.text
        assert SECRET not in res.text
        servers = res.json()["servers"]
        assert servers[0]["credential_set"] is True

    async def test_masked_preview_exposes_only_a_tail(self, authed_client):
        body = (await _create(authed_client)).json()
        preview = body["credential_preview"]
        assert preview is not None
        # Masked: the bulk of the secret must be hidden, only a short tail shown.
        assert SECRET not in preview
        assert "•" in preview
        assert preview.endswith(SECRET[-4:])

    async def test_short_credentials_are_fully_masked(self, authed_client):
        res = await _create(authed_client, credential_value="tok1")
        body = res.json()
        assert body["credential_preview"] == "••••••••"
        assert "tok1" not in res.text

    async def test_no_credential_means_not_set_and_no_preview(self, authed_client):
        await _create(authed_client, credential_value=None)
        body = (await authed_client.get("/api/mcp/servers")).json()["servers"][0]
        assert body["credential_set"] is False
        assert body["credential_preview"] is None


class TestCredentialUpdateSemantics:
    async def test_null_credential_keeps_stored_value(self, authed_client):
        created = (await _create(authed_client)).json()
        res = await authed_client.put(
            f"/api/mcp/servers/{created['id']}",
            json={"name": "Renamed", "url": created["url"], "credential_value": None},
            headers=ORIGIN,
        )
        body = res.json()
        assert body["credential_set"] is True
        # The update response also never leaks the stored credential.
        assert SECRET not in res.text

    async def test_empty_string_credential_clears_stored_value(self, authed_client):
        created = (await _create(authed_client)).json()
        res = await authed_client.put(
            f"/api/mcp/servers/{created['id']}",
            json={"name": "Renamed", "url": created["url"], "credential_value": ""},
            headers=ORIGIN,
        )
        body = res.json()
        assert body["credential_set"] is False
        assert body["credential_preview"] is None


class TestUrlPolicy:
    async def test_https_url_is_accepted_without_warning(self, authed_client):
        res = await _create(authed_client, url="https://mcp.context7.com/mcp")
        assert res.status_code == 201, res.text
        assert res.json()["url_warning"] is None

    async def test_http_url_is_accepted_with_a_warning(self, authed_client):
        res = await _create(authed_client, url="http://localhost:8123/mcp")
        assert res.status_code == 201, res.text
        body = res.json()
        assert body["url"] == "http://localhost:8123/mcp"
        assert body["url_warning"] is not None
        assert "http" in body["url_warning"].lower()

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com/mcp",
            "file:///etc/passwd",
            "ws://example.com/mcp",
            "example.com/mcp",
        ],
    )
    async def test_other_schemes_are_rejected_on_create(self, authed_client, url):
        res = await _create(authed_client, url=url)
        assert res.status_code == 400
        assert "scheme" in res.json()["detail"].lower()

    async def test_other_schemes_are_rejected_on_update(self, authed_client):
        created = (await _create(authed_client)).json()
        res = await authed_client.put(
            f"/api/mcp/servers/{created['id']}",
            json={"name": "x", "url": "file:///etc/passwd"},
            headers=ORIGIN,
        )
        assert res.status_code == 400

    async def test_warning_flag_follows_the_stored_url(self, authed_client):
        created = (await _create(authed_client, url="http://localhost:8000/mcp")).json()
        res = await authed_client.put(
            f"/api/mcp/servers/{created['id']}",
            json={"name": "x", "url": "https://secure.example/mcp"},
            headers=ORIGIN,
        )
        assert res.json()["url_warning"] is None


class TestCacheInvalidation:
    async def test_create_invalidates_process_cache(self, authed_client):
        assert get_mcp_servers() == ()
        await _create(authed_client)
        cached = get_mcp_servers()
        assert [s.name for s in cached] == ["Context7"]
        assert cached[0].credential_value == SECRET

    async def test_update_invalidates_process_cache(self, authed_client):
        created = (await _create(authed_client)).json()
        await authed_client.put(
            f"/api/mcp/servers/{created['id']}",
            json={"name": "Updated", "url": created["url"], "credential_value": ""},
            headers=ORIGIN,
        )
        cached = get_mcp_servers()
        assert [s.name for s in cached] == ["Updated"]
        assert cached[0].credential_value is None

    async def test_delete_invalidates_process_cache(self, authed_client):
        created = (await _create(authed_client)).json()
        assert get_mcp_servers() != ()
        await authed_client.delete(
            f"/api/mcp/servers/{created['id']}", headers=ORIGIN
        )
        assert get_mcp_servers() == ()

"""Provider settings API: auth, key handling, dimension-change gate, test probe."""

import pytest

from canvas_server.provider_config import reset_provider_config
from canvas_server.provider_probe import ProbeResult

ORIGIN = {"Origin": "http://test"}

BASE_BODY = {
    "profile": "openai",
    "llm_provider_type": "openai",
    "llm_base_url": "https://api.openai.com/v1",
    "llm_model": "gpt-4o-mini",
    "mem0_llm_model": "gpt-4o-mini",
    "mem0_embedder_model": "text-embedding-3-small",
    "mem0_embedder_dimensions": 768,
}


@pytest.fixture(autouse=True)
def _clean_provider_cache(monkeypatch):
    # Pin the env fallback so assertions don't depend on the developer's .env.
    from canvas_server.config import settings

    monkeypatch.setattr(settings, "llm_api_key", "", raising=False)
    monkeypatch.setattr(settings, "llm_model", "env-model", raising=False)
    monkeypatch.setattr(settings, "mem0_embedder_dimensions", 768, raising=False)
    reset_provider_config()
    yield
    reset_provider_config()


class TestAuth:
    async def test_get_requires_auth(self, test_client):
        res = await test_client.get("/api/settings/provider")
        assert res.status_code == 401

    async def test_put_requires_auth(self, test_client):
        res = await test_client.put(
            "/api/settings/provider", json={**BASE_BODY}, headers=ORIGIN
        )
        assert res.status_code == 401

    async def test_put_requires_same_origin(self, authed_client):
        res = await authed_client.put(
            "/api/settings/provider",
            json={**BASE_BODY},
            headers={"Origin": "http://evil.example"},
        )
        assert res.status_code == 403


class TestGetAndUpdate:
    async def test_get_falls_back_to_env(self, authed_client):
        from canvas_server.config import settings

        res = await authed_client.get("/api/settings/provider")
        assert res.status_code == 200
        body = res.json()
        assert body["source"] == "env"
        assert body["llm_model"] == settings.llm_model
        assert "api_key" not in body
        assert "llm_api_key" not in body

    async def test_update_persists_and_never_returns_key(self, authed_client):
        res = await authed_client.put(
            "/api/settings/provider",
            json={**BASE_BODY, "api_key": "sk-secret"},
            headers=ORIGIN,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["source"] == "database"
        assert body["llm_model"] == "gpt-4o-mini"
        assert body["api_key_set"] is True
        assert "sk-secret" not in res.text

    async def test_omitted_key_is_preserved(self, authed_client):
        await authed_client.put(
            "/api/settings/provider",
            json={**BASE_BODY, "api_key": "sk-secret"},
            headers=ORIGIN,
        )
        res = await authed_client.put(
            "/api/settings/provider",
            json={**BASE_BODY, "llm_model": "gpt-4o"},
            headers=ORIGIN,
        )
        assert res.status_code == 200
        assert res.json()["api_key_set"] is True

        from canvas_server.provider_config import get_provider_config

        assert get_provider_config().llm_api_key == "sk-secret"

    async def test_empty_key_clears_it(self, authed_client):
        await authed_client.put(
            "/api/settings/provider",
            json={**BASE_BODY, "api_key": "sk-secret"},
            headers=ORIGIN,
        )
        res = await authed_client.put(
            "/api/settings/provider",
            json={**BASE_BODY, "api_key": ""},
            headers=ORIGIN,
        )
        assert res.json()["api_key_set"] is False


class TestDimensionChange:
    async def test_change_without_confirm_is_rejected(self, authed_client):
        res = await authed_client.put(
            "/api/settings/provider",
            json={**BASE_BODY, "mem0_embedder_dimensions": 1536},
            headers=ORIGIN,
        )
        assert res.status_code == 409
        assert "1536" in res.json()["detail"]

    async def test_confirmed_change_purges_rag_chunks(
        self, authed_client, test_session
    ):
        import uuid

        from sqlalchemy import func, select

        from canvas_server.models.canvas import (
            AgentDocument,
            AgentDocumentChunk,
            AgentNode,
            Canvas,
        )

        canvas = Canvas(id=uuid.uuid4(), name="c", owner_id=authed_client.auth_user_id)
        agent = AgentNode(id=uuid.uuid4(), canvas_id=canvas.id, name="a")
        document = AgentDocument(
            id=uuid.uuid4(),
            canvas_id=canvas.id,
            agent_node_id=agent.id,
            name="d",
            content="hello",
        )
        chunk = AgentDocumentChunk(
            id=uuid.uuid4(),
            canvas_id=canvas.id,
            agent_node_id=agent.id,
            document_id=document.id,
            chunk_index=0,
            content="hello",
            embedding=[0.0] * 768,
        )
        test_session.add_all([canvas, agent, document, chunk])
        await test_session.commit()

        res = await authed_client.put(
            "/api/settings/provider",
            json={
                **BASE_BODY,
                "mem0_embedder_dimensions": 1536,
                "confirm_reindex": True,
            },
            headers=ORIGIN,
        )
        assert res.status_code == 200, res.text
        assert res.json()["mem0_embedder_dimensions"] == 1536

        remaining = await test_session.scalar(
            select(func.count()).select_from(AgentDocumentChunk)
        )
        assert remaining == 0


class TestProbe:
    async def test_reports_failures_as_ok_false(self, authed_client, monkeypatch):
        async def fake_probe(config):
            return [
                ProbeResult(name="chat", ok=True, detail="OK", latency_ms=12),
                ProbeResult(
                    name="embedding", ok=False, detail="404 Not Found", latency_ms=7
                ),
            ]

        monkeypatch.setattr("canvas_server.routes.settings.probe_provider", fake_probe)

        res = await authed_client.post(
            "/api/settings/provider/test", json={**BASE_BODY}, headers=ORIGIN
        )
        assert res.status_code == 200
        body = res.json()
        assert body["ok"] is False
        assert [c["name"] for c in body["checks"]] == ["chat", "embedding"]
        assert body["checks"][1]["detail"] == "404 Not Found"

    async def test_uses_stored_key_when_omitted(self, authed_client, monkeypatch):
        captured = {}

        async def fake_probe(config):
            captured["api_key"] = config.llm_api_key
            return [ProbeResult(name="chat", ok=True, detail="OK", latency_ms=1)]

        monkeypatch.setattr("canvas_server.routes.settings.probe_provider", fake_probe)

        await authed_client.put(
            "/api/settings/provider",
            json={**BASE_BODY, "api_key": "sk-stored"},
            headers=ORIGIN,
        )
        res = await authed_client.post(
            "/api/settings/provider/test", json={**BASE_BODY}, headers=ORIGIN
        )
        assert res.status_code == 200
        assert captured["api_key"] == "sk-stored"

    async def test_does_not_persist(self, authed_client, monkeypatch):
        async def fake_probe(config):
            return [ProbeResult(name="chat", ok=True, detail="OK", latency_ms=1)]

        monkeypatch.setattr("canvas_server.routes.settings.probe_provider", fake_probe)

        await authed_client.post(
            "/api/settings/provider/test",
            json={**BASE_BODY, "llm_model": "throwaway"},
            headers=ORIGIN,
        )
        res = await authed_client.get("/api/settings/provider")
        assert res.json()["llm_model"] != "throwaway"

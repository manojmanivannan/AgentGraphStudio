import io
import json
import uuid
import zipfile


class TestCreateCanvas:
    async def test_create_default(self, authed_client):
        resp = await authed_client.post("/api/canvases", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Untitled Canvas"
        assert data["id"] is not None
        assert data["nodes"]["agents"] == []

    async def test_create_named(self, authed_client):
        resp = await authed_client.post("/api/canvases", json={"name": "My Canvas"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "My Canvas"


class TestListCanvases:
    async def test_list_empty(self, authed_client):
        resp = await authed_client.get("/api/canvases")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_canvas(self, authed_client):
        await authed_client.post("/api/canvases", json={"name": "C1"})
        resp = await authed_client.get("/api/canvases")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "C1"


class TestGetCanvas:
    async def test_get_existing(self, authed_client):
        created = await authed_client.post("/api/canvases", json={"name": "G1"})
        cid = created.json()["id"]

        resp = await authed_client.get(f"/api/canvases/{cid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == cid
        assert resp.json()["name"] == "G1"

    async def test_get_missing(self, authed_client):
        resp = await authed_client.get(f"/api/canvases/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestSaveCanvas:
    async def test_save_with_nodes(self, authed_client):
        created = await authed_client.post("/api/canvases", json={"name": "S1"})
        cid = created.json()["id"]

        aid = str(uuid.uuid4())
        tid = str(uuid.uuid4())
        eid = str(uuid.uuid4())

        payload = {
            "name": "S1 Updated",
            "nodes": {
                "agents": [
                    {
                        "id": aid,
                        "name": "AgentA",
                        "model_name": "ollama:llama3.1",
                        "agent_type": "worker",
                        "enable_rag": True,
                        "rag_chunk_size": 1337,
                        "is_entry_point": True,
                        "position_x": 100,
                        "position_y": 200,
                    },
                ],
                "tools": [
                    {"id": tid, "name": "ToolT", "code": "def run(): return 42"},
                ],
            },
            "edges": [
                {
                    "id": eid,
                    "source_node_id": aid,
                    "target_node_id": tid,
                    "edge_type": "tool_access",
                },
            ],
        }

        resp = await authed_client.put(f"/api/canvases/{cid}", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "S1 Updated"
        assert len(data["nodes"]["agents"]) == 1
        assert len(data["nodes"]["tools"]) == 1
        assert len(data["edges"]) == 1
        assert data["nodes"]["agents"][0]["name"] == "AgentA"
        assert data["nodes"]["agents"][0]["rag_chunk_size"] == 1337
        assert data["nodes"]["agents"][0]["is_entry_point"] is True

        get_resp = await authed_client.get(f"/api/canvases/{cid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["nodes"]["agents"][0]["rag_chunk_size"] == 1337
        assert get_resp.json()["nodes"]["agents"][0]["is_entry_point"] is True

    async def test_save_missing_canvas(self, authed_client):
        resp = await authed_client.put(
            f"/api/canvases/{uuid.uuid4()}",
            json={
                "name": "X",
                "nodes": {"agents": [], "tools": []},
                "edges": [],
            },
        )
        assert resp.status_code == 404


class TestDeleteCanvas:
    async def test_delete_existing(self, authed_client):
        created = await authed_client.post("/api/canvases", json={"name": "D1"})
        cid = created.json()["id"]

        resp = await authed_client.delete(f"/api/canvases/{cid}")
        assert resp.status_code == 204

        get_resp = await authed_client.get(f"/api/canvases/{cid}")
        assert get_resp.status_code == 404

    async def test_delete_missing(self, authed_client):
        resp = await authed_client.delete(f"/api/canvases/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestExportCanvas:
    async def test_export_json(self, authed_client):
        created = await authed_client.post("/api/canvases", json={"name": "ExportCanvas"})
        cid = created.json()["id"]

        resp = await authed_client.get(f"/api/canvases/{cid}/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert "content-disposition" in resp.headers
        assert "ExportCanvas" in resp.headers["content-disposition"]

        data = resp.json()
        assert data["name"] == "ExportCanvas"
        assert data["id"] == cid
        assert "nodes" in data
        assert "edges" in data

    async def test_export_with_nodes(self, authed_client):
        created = await authed_client.post("/api/canvases", json={"name": "FullCanvas"})
        cid = created.json()["id"]

        aid = str(uuid.uuid4())
        tid = str(uuid.uuid4())
        eid = str(uuid.uuid4())

        await authed_client.put(
            f"/api/canvases/{cid}",
            json={
                "name": "FullCanvas",
                "nodes": {
                    "agents": [{"id": aid, "name": "A1"}],
                    "tools": [{"id": tid, "name": "T1"}],
                },
                "edges": [{"id": eid, "source_node_id": aid, "target_node_id": tid}],
            },
        )

        resp = await authed_client.get(f"/api/canvases/{cid}/export")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]["agents"]) == 1
        assert len(data["nodes"]["tools"]) == 1
        assert len(data["edges"]) == 1

    async def test_export_missing(self, authed_client):
        resp = await authed_client.get(f"/api/canvases/{uuid.uuid4()}/export")
        assert resp.status_code == 404


class TestImportCanvas:
    async def test_import_full_canvas(self, authed_client):
        aid = str(uuid.uuid4())
        worker_id = str(uuid.uuid4())
        tid = str(uuid.uuid4())
        e1 = str(uuid.uuid4())
        e2 = str(uuid.uuid4())

        payload = {
            "name": "Imported Canvas",
            "nodes": {
                "agents": [
                    {
                        "id": aid,
                        "name": "Master",
                        "agent_type": "router",
                        "model_name": "ollama:llama3.1",
                        "position_x": 100,
                        "position_y": 50,
                    },
                    {
                        "id": worker_id,
                        "name": "Worker",
                        "agent_type": "worker",
                        "model_name": "ollama:llama3.1",
                        "position_x": 300,
                        "position_y": 200,
                    },
                ],
                "tools": [
                    {
                        "id": tid,
                        "name": "Calc",
                        "code": "def add(a,b): return a+b",
                        "position_x": 500,
                        "position_y": 200,
                    },
                ],
            },
            "edges": [
                {
                    "id": e1,
                    "source_node_id": aid,
                    "target_node_id": worker_id,
                    "edge_type": "handoff",
                },
                {
                    "id": e2,
                    "source_node_id": worker_id,
                    "target_node_id": tid,
                    "edge_type": "tool_access",
                },
            ],
        }

        resp = await authed_client.post("/api/canvases/import", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Imported Canvas"
        cid = data["id"]
        assert cid is not None

        assert len(data["nodes"]["agents"]) == 2
        assert len(data["nodes"]["tools"]) == 1
        assert len(data["edges"]) == 2

        agent_types = {a["agent_type"] for a in data["nodes"]["agents"]}
        assert agent_types == {"router", "worker"}

        edge_types = {e["edge_type"] for e in data["edges"]}
        assert edge_types == {"handoff", "tool_access"}

    async def test_import_empty_canvas(self, authed_client):
        resp = await authed_client.post(
            "/api/canvases/import",
            json={
                "name": "Empty Import",
                "nodes": {"agents": [], "tools": []},
                "edges": [],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Empty Import"
        assert resp.json()["nodes"]["agents"] == []

    async def test_import_default_name(self, authed_client):
        resp = await authed_client.post(
            "/api/canvases/import",
            json={
                "nodes": {"agents": [], "tools": []},
                "edges": [],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Untitled Canvas"

    async def test_import_canvas_with_contentless_documents(self, authed_client):
        aid = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())
        payload = {
            "name": "Canvas with Empty Doc",
            "nodes": {
                "agents": [
                    {
                        "id": aid,
                        "name": "AgentA",
                        "model_name": "ollama:llama3.1",
                        "agent_type": "worker",
                    }
                ],
                "tools": [],
            },
            "edges": [],
            "documents": [
                {
                    "id": doc_id,
                    "agent_node_id": aid,
                    "name": "missing_content.txt",
                    "content": None,
                }
            ],
        }
        resp = await authed_client.post("/api/canvases/import", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Canvas with Empty Doc"
        # The canvas should import fine, and we should be able to fetch it
        cid = data["id"]

        # Verify the agent node was imported
        assert len(data["nodes"]["agents"]) == 1
        imported_agent_id = data["nodes"]["agents"][0]["id"]

        # Fetching documents for the agent should return empty, as the contentless document was skipped
        docs_resp = await authed_client.get(f"/api/canvases/{cid}/agents/{imported_agent_id}/documents")
        assert docs_resp.status_code == 200
        assert docs_resp.json() == []


class TestExportImportRoundTrip:
    async def test_export_then_import(self, authed_client):
        aid = str(uuid.uuid4())
        payload = {
            "name": "RoundTrip Canvas",
            "nodes": {
                "agents": [{"id": aid, "name": "OnlyAgent", "agent_type": "worker", "enable_plotting": True}],
                "tools": [],
            },
            "edges": [],
        }

        import_resp = await authed_client.post("/api/canvases/import", json=payload)
        assert import_resp.status_code == 200
        original_id = import_resp.json()["id"]
        original_data = import_resp.json()

        export_resp = await authed_client.get(f"/api/canvases/{original_id}/export")
        assert export_resp.status_code == 200
        exported = export_resp.json()

        assert exported["name"] == original_data["name"]
        assert exported["id"] == original_data["id"]
        assert len(exported["nodes"]["agents"]) == len(original_data["nodes"]["agents"])
        assert (
            exported["nodes"]["agents"][0]["name"]
            == original_data["nodes"]["agents"][0]["name"]
        )
        assert exported["nodes"]["agents"][0]["enable_plotting"] is True


class TestZipExportImport:
    async def test_export_zip_and_import_zip_with_documents(
        self, authed_client, fresh_db
    ):
        payload = {
            "name": "ZipCanvas",
            "nodes": {
                "agents": [
                    {
                        "id": str(uuid.uuid4()),
                        "name": "DocAgent",
                        "agent_type": "worker",
                        "enable_plotting": True,
                    }
                ],
                "tools": [],
            },
            "edges": [],
        }

        create_resp = await authed_client.post("/api/canvases/import", json=payload)
        assert create_resp.status_code == 200
        canvas_id = create_resp.json()["id"]
        agent_id = create_resp.json()["nodes"]["agents"][0]["id"]

        upload_resp = await authed_client.post(
            f"/api/canvases/{canvas_id}/agents/{agent_id}/documents",
            files={"file": ("note.txt", b"Hello RAG content", "text/plain")},
        )
        assert upload_resp.status_code == 200
        assert upload_resp.json()["name"] == "note.txt"

        export_resp = await authed_client.get(f"/api/canvases/{canvas_id}/export-zip")
        assert export_resp.status_code == 200
        assert "application/zip" in export_resp.headers["content-type"]

        archive = zipfile.ZipFile(io.BytesIO(export_resp.content))
        assert "manifest.json" in archive.namelist()
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        assert manifest["name"] == "ZipCanvas"
        assert len(manifest["documents"]) == 1
        assert manifest["nodes"]["agents"][0]["enable_plotting"] is True
        doc_entry = manifest["documents"][0]
        assert doc_entry["name"] == "note.txt"
        assert doc_entry["path"] in archive.namelist()

        import_resp = await authed_client.post(
            "/api/canvases/import-zip",
            files={"file": ("canvas.zip", export_resp.content, "application/zip")},
        )
        assert import_resp.status_code == 200
        imported = import_resp.json()
        assert imported["name"] == "ZipCanvas"
        assert len(imported["nodes"]["agents"]) == 1
        assert imported["nodes"]["agents"][0]["enable_plotting"] is True

        imported_agent_id = imported["nodes"]["agents"][0]["id"]
        docs_resp = await authed_client.get(
            f"/api/canvases/{imported['id']}/agents/{imported_agent_id}/documents"
        )
        assert docs_resp.status_code == 200
        docs = docs_resp.json()
        assert len(docs) == 1
        assert docs[0]["name"] == "note.txt"


class TestPerUserIsolation:
    """Two registered users see only their own canvases; cross-user access 404s."""

    async def test_list_canvases_scoped_per_user(self, make_authed_client):
        alice = await make_authed_client()
        bob = await make_authed_client()

        await alice.post("/api/canvases", json={"name": "Alice Canvas"})
        await bob.post("/api/canvases", json={"name": "Bob Canvas"})

        alice_list = (await alice.get("/api/canvases")).json()
        bob_list = (await bob.get("/api/canvases")).json()

        assert [c["name"] for c in alice_list] == ["Alice Canvas"]
        assert [c["name"] for c in bob_list] == ["Bob Canvas"]

    async def test_cross_user_get_canvas_returns_404(self, make_authed_client):
        alice = await make_authed_client()
        bob = await make_authed_client()

        created = await alice.post("/api/canvases", json={"name": "Alice Only"})
        cid = created.json()["id"]

        # Bob cannot fetch or mutate Alice's canvas.
        assert (await bob.get(f"/api/canvases/{cid}")).status_code == 404
        assert (
            await bob.put(f"/api/canvases/{cid}", json={"name": "Hijack", "nodes": {"agents": [], "tools": []}, "edges": []})
        ).status_code == 404
        assert (await bob.delete(f"/api/canvases/{cid}")).status_code == 404
        # Alice still owns it (Bob's delete was a no-op).
        assert (await alice.get(f"/api/canvases/{cid}")).status_code == 200

    async def test_cross_user_export_returns_404(self, make_authed_client):
        alice = await make_authed_client()
        bob = await make_authed_client()
        cid = (await alice.post("/api/canvases", json={"name": "ExportMe"})).json()["id"]
        assert (await bob.get(f"/api/canvases/{cid}/export")).status_code == 404

    async def test_cross_user_conversation_returns_404(self, make_authed_client):
        alice = await make_authed_client()
        bob = await make_authed_client()
        cid = (await alice.post("/api/canvases", json={"name": "C"})).json()["id"]
        conv = await alice.post(f"/api/canvases/{cid}/conversations", json={"name": "Conv"})
        conv_id = conv.json()["id"]

        # Bob cannot reach Alice's conversation through either path.
        assert (
            await bob.get(f"/api/canvases/{cid}/conversations/{conv_id}")
        ).status_code == 404
        assert (
            await bob.get(f"/api/canvases/conversations/{conv_id}")
        ).status_code == 404

    async def test_cross_user_agent_document_returns_404(self, make_authed_client):
        alice = await make_authed_client()
        bob = await make_authed_client()
        cid = (await alice.post("/api/canvases", json={"name": "C"})).json()["id"]
        aid = str(uuid.uuid4())
        await alice.put(
            f"/api/canvases/{cid}",
            json={
                "name": "C",
                "nodes": {"agents": [{"id": aid, "name": "A"}], "tools": []},
                "edges": [],
            },
        )
        up = await alice.post(
            f"/api/canvases/{cid}/agents/{aid}/documents",
            files={"file": ("note.txt", b"secret", "text/plain")},
        )
        assert up.status_code == 200
        doc_id = up.json()["id"]

        assert (
            await bob.get(f"/api/canvases/{cid}/agents/{aid}/documents")
        ).status_code == 404
        assert (
            await bob.delete(f"/api/canvases/{cid}/agents/{aid}/documents/{doc_id}")
        ).status_code == 404
        # Alice can still list/delete her own document.
        assert (
            await alice.get(f"/api/canvases/{cid}/agents/{aid}/documents")
        ).status_code == 200

    async def test_unauthed_canvas_routes_return_401(self, test_client, fresh_db):
        # No cookie -> every canvas route is 401 (not 404/200).
        assert (await test_client.get("/api/canvases")).status_code == 401
        assert (await test_client.post("/api/canvases", json={})).status_code == 401
        assert (await test_client.get(f"/api/canvases/{uuid.uuid4()}")).status_code == 401
        assert (
            await test_client.put(
                f"/api/canvases/{uuid.uuid4()}",
                json={"name": "X", "nodes": {"agents": [], "tools": []}, "edges": []},
            )
        ).status_code == 401
        assert (await test_client.delete(f"/api/canvases/{uuid.uuid4()}")).status_code == 401

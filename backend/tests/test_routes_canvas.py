import uuid


class TestCreateCanvas:
    async def test_create_default(self, test_client, fresh_db):
        resp = await test_client.post("/api/canvases", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Untitled Canvas"
        assert data["id"] is not None
        assert data["nodes"]["agents"] == []

    async def test_create_named(self, test_client, fresh_db):
        resp = await test_client.post("/api/canvases", json={"name": "My Canvas"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "My Canvas"


class TestListCanvases:
    async def test_list_empty(self, test_client, fresh_db):
        resp = await test_client.get("/api/canvases")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_with_canvas(self, test_client, fresh_db):
        await test_client.post("/api/canvases", json={"name": "C1"})
        resp = await test_client.get("/api/canvases")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "C1"


class TestGetCanvas:
    async def test_get_existing(self, test_client, fresh_db):
        created = await test_client.post("/api/canvases", json={"name": "G1"})
        cid = created.json()["id"]

        resp = await test_client.get(f"/api/canvases/{cid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == cid
        assert resp.json()["name"] == "G1"

    async def test_get_missing(self, test_client, fresh_db):
        resp = await test_client.get(f"/api/canvases/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestSaveCanvas:
    async def test_save_with_nodes(self, test_client, fresh_db):
        created = await test_client.post("/api/canvases", json={"name": "S1"})
        cid = created.json()["id"]

        aid = str(uuid.uuid4())
        tid = str(uuid.uuid4())
        eid = str(uuid.uuid4())

        payload = {
            "name": "S1 Updated",
            "nodes": {
                "agents": [
                    {"id": aid, "name": "AgentA", "model_name": "ollama:llama3.1", "agent_type": "worker", "position_x": 100, "position_y": 200},
                ],
                "tools": [
                    {"id": tid, "name": "ToolT", "code": "def run(): return 42"},
                ],
            },
            "edges": [
                {"id": eid, "source_node_id": aid, "target_node_id": tid, "edge_type": "tool_access"},
            ],
        }

        resp = await test_client.put(f"/api/canvases/{cid}", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "S1 Updated"
        assert len(data["nodes"]["agents"]) == 1
        assert len(data["nodes"]["tools"]) == 1
        assert len(data["edges"]) == 1
        assert data["nodes"]["agents"][0]["name"] == "AgentA"

    async def test_save_missing_canvas(self, test_client, fresh_db):
        resp = await test_client.put(f"/api/canvases/{uuid.uuid4()}", json={
            "name": "X", "nodes": {"agents": [], "tools": []}, "edges": [],
        })
        assert resp.status_code == 404


class TestDeleteCanvas:
    async def test_delete_existing(self, test_client, fresh_db):
        created = await test_client.post("/api/canvases", json={"name": "D1"})
        cid = created.json()["id"]

        resp = await test_client.delete(f"/api/canvases/{cid}")
        assert resp.status_code == 204

        get_resp = await test_client.get(f"/api/canvases/{cid}")
        assert get_resp.status_code == 404

    async def test_delete_missing(self, test_client, fresh_db):
        resp = await test_client.delete(f"/api/canvases/{uuid.uuid4()}")
        assert resp.status_code == 404


class TestExportCanvas:
    async def test_export_json(self, test_client, fresh_db):
        created = await test_client.post("/api/canvases", json={"name": "ExportCanvas"})
        cid = created.json()["id"]

        resp = await test_client.get(f"/api/canvases/{cid}/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert "content-disposition" in resp.headers
        assert "ExportCanvas" in resp.headers["content-disposition"]

        data = resp.json()
        assert data["name"] == "ExportCanvas"
        assert data["id"] == cid
        assert "nodes" in data
        assert "edges" in data

    async def test_export_with_nodes(self, test_client, fresh_db):
        created = await test_client.post("/api/canvases", json={"name": "FullCanvas"})
        cid = created.json()["id"]

        aid = str(uuid.uuid4())
        tid = str(uuid.uuid4())
        eid = str(uuid.uuid4())

        await test_client.put(f"/api/canvases/{cid}", json={
            "name": "FullCanvas",
            "nodes": {
                "agents": [{"id": aid, "name": "A1"}],
                "tools": [{"id": tid, "name": "T1"}],
            },
            "edges": [{"id": eid, "source_node_id": aid, "target_node_id": tid}],
        })

        resp = await test_client.get(f"/api/canvases/{cid}/export")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["nodes"]["agents"]) == 1
        assert len(data["nodes"]["tools"]) == 1
        assert len(data["edges"]) == 1

    async def test_export_missing(self, test_client, fresh_db):
        resp = await test_client.get(f"/api/canvases/{uuid.uuid4()}/export")
        assert resp.status_code == 404


class TestImportCanvas:
    async def test_import_full_canvas(self, test_client, fresh_db):
        aid = str(uuid.uuid4())
        worker_id = str(uuid.uuid4())
        tid = str(uuid.uuid4())
        e1 = str(uuid.uuid4())
        e2 = str(uuid.uuid4())

        payload = {
            "name": "Imported Canvas",
            "nodes": {
                "agents": [
                    {"id": aid, "name": "Master", "agent_type": "router", "model_name": "ollama:llama3.1", "position_x": 100, "position_y": 50},
                    {"id": worker_id, "name": "Worker", "agent_type": "worker", "model_name": "ollama:llama3.1", "position_x": 300, "position_y": 200},
                ],
                "tools": [
                    {"id": tid, "name": "Calc", "code": "def add(a,b): return a+b", "position_x": 500, "position_y": 200},
                ],
            },
            "edges": [
                {"id": e1, "source_node_id": aid, "target_node_id": worker_id, "edge_type": "handoff"},
                {"id": e2, "source_node_id": worker_id, "target_node_id": tid, "edge_type": "tool_access"},
            ],
        }

        resp = await test_client.post("/api/canvases/import", json=payload)
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

    async def test_import_empty_canvas(self, test_client, fresh_db):
        resp = await test_client.post("/api/canvases/import", json={
            "name": "Empty Import",
            "nodes": {"agents": [], "tools": []},
            "edges": [],
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Empty Import"
        assert resp.json()["nodes"]["agents"] == []

    async def test_import_default_name(self, test_client, fresh_db):
        resp = await test_client.post("/api/canvases/import", json={
            "nodes": {"agents": [], "tools": []},
            "edges": [],
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "Untitled Canvas"


class TestExportImportRoundTrip:
    async def test_export_then_import(self, test_client, fresh_db):
        aid = str(uuid.uuid4())
        payload = {
            "name": "RoundTrip Canvas",
            "nodes": {
                "agents": [{"id": aid, "name": "OnlyAgent", "agent_type": "worker"}],
                "tools": [],
            },
            "edges": [],
        }

        import_resp = await test_client.post("/api/canvases/import", json=payload)
        assert import_resp.status_code == 200
        original_id = import_resp.json()["id"]
        original_data = import_resp.json()

        export_resp = await test_client.get(f"/api/canvases/{original_id}/export")
        assert export_resp.status_code == 200
        exported = export_resp.json()

        assert exported["name"] == original_data["name"]
        assert exported["id"] == original_data["id"]
        assert len(exported["nodes"]["agents"]) == len(original_data["nodes"]["agents"])
        assert exported["nodes"]["agents"][0]["name"] == original_data["nodes"]["agents"][0]["name"]

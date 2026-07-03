import json
import time

from fastapi.testclient import TestClient

import canvs.server as server_module
from canvs.registry import node
from canvs.runner import LocalRunner
from canvs.server import app


def test_health_reports_kaggle_and_supabase_flags(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["supabase"] is False
        assert body["kaggle"] == {"available": False, "reason": "kaggle package not installed"}


def test_config_endpoint_404_when_supabase_not_configured(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    with TestClient(app) as client:
        resp = client.get("/config")
        assert resp.status_code == 404


def test_config_endpoint_returns_anon_credentials_when_configured(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "anon-key-123")

    with TestClient(app) as client:
        resp = client.get("/config")
        assert resp.status_code == 200
        assert resp.json() == {
            "supabase_url": "https://example.supabase.co",
            "supabase_anon_key": "anon-key-123",
        }


def test_local_run_persists_and_lists_in_history(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("CANVS_RUNS_DIR", str(tmp_path))
    # The module-level `runner` singleton binds its runs_dir at import
    # time, before this test's CANVS_RUNS_DIR is set -- swap it out so
    # the run's script/log/events land under tmp_path instead of the
    # real repo's canvs_runs/.
    monkeypatch.setattr(server_module, "runner", LocalRunner(runs_dir=str(tmp_path)))

    # Registered directly rather than relying on examples.toy_nodes via
    # the app's lifespan -- that module is only ever imported once per
    # process, so a later test's registry.clear() would leave it as a
    # no-op reload with nothing actually re-registered.
    @node(category="data", name="Nums")
    def nums(n: int = 2) -> list:
        return list(range(n))

    graph = {
        "graph_id": "g1",
        "name": "history-test-pipeline",
        "nodes": [{"id": "n1", "spec": "data.nums", "config": {"n": 2}}],
        "edges": [],
    }

    with TestClient(app) as client:
        resp = client.post("/runs", json={"graph": graph, "target": "local"})
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        assert (tmp_path / run_id / "run.json").exists()

        list_resp = client.get("/runs")
        assert list_resp.status_code == 200
        runs = list_resp.json()["runs"]
        assert any(r["run_id"] == run_id and r["name"] == "history-test-pipeline" for r in runs)

        deadline = time.time() + 20
        status = None
        while time.time() < deadline:
            status = client.get(f"/runs/{run_id}").json()["status"]
            if status in ("done", "failed"):
                break
            time.sleep(0.2)
        assert status == "done"

    record = json.loads((tmp_path / run_id / "run.json").read_text())
    assert record["status"] == "done"

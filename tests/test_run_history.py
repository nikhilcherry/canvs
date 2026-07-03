import json

import pytest

import canvs.reporter as reporter_module
from canvs import run_history


@pytest.fixture(autouse=True)
def _reset_supabase_client_cache():
    reporter_module._SUPABASE_CLIENT = None
    reporter_module._SUPABASE_CLIENT_ATTEMPTED = False
    yield
    reporter_module._SUPABASE_CLIENT = None
    reporter_module._SUPABASE_CLIENT_ATTEMPTED = False


def test_create_record_writes_local_run_json(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    graph = {"graph_id": "g1", "name": "p", "nodes": [], "edges": []}
    run_history.create_run_record("run1", "p", "local", "pending", graph, runs_dir=str(tmp_path))

    path = tmp_path / "run1" / "run.json"
    assert path.exists()
    record = json.loads(path.read_text())
    assert record["run_id"] == "run1"
    assert record["name"] == "p"
    assert record["target"] == "local"
    assert record["status"] == "pending"
    assert record["graph"] == graph
    assert "created_at" in record


def test_update_status_patches_local_record(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    graph = {"graph_id": "g1", "name": "p", "nodes": [], "edges": []}
    run_history.create_run_record("run2", "p", "local", "pending", graph, runs_dir=str(tmp_path))
    run_history.update_run_status("run2", "done", runs_dir=str(tmp_path))

    path = tmp_path / "run2" / "run.json"
    record = json.loads(path.read_text())
    assert record["status"] == "done"


def test_list_runs_dedupes_and_sorts_newest_first(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    graph = {"graph_id": "g1", "name": "p", "nodes": [], "edges": []}
    run_history.create_run_record("run-a", "a", "local", "done", graph, runs_dir=str(tmp_path))
    run_history.create_run_record("run-b", "b", "local", "done", graph, runs_dir=str(tmp_path))

    # Force a's created_at earlier than b's so ordering is deterministic.
    a_path = tmp_path / "run-a" / "run.json"
    a_record = json.loads(a_path.read_text())
    a_record["created_at"] = "2020-01-01T00:00:00+00:00"
    a_path.write_text(json.dumps(a_record))

    runs = run_history.list_runs(runs_dir=str(tmp_path))
    run_ids = [r["run_id"] for r in runs]
    assert run_ids == ["run-b", "run-a"]


def test_list_runs_caps_at_limit(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)

    graph = {"graph_id": "g1", "name": "p", "nodes": [], "edges": []}
    for i in range(5):
        run_history.create_run_record(f"run-{i}", "p", "local", "done", graph, runs_dir=str(tmp_path))

    runs = run_history.list_runs(runs_dir=str(tmp_path), limit=3)
    assert len(runs) == 3

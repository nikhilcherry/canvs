import json

import pytest

import canvs.reporter as reporter_module
from canvs.reporter import canvs_metric, canvs_report


@pytest.fixture(autouse=True)
def _reset_supabase_client_cache():
    reporter_module._SUPABASE_CLIENT = None
    reporter_module._SUPABASE_CLIENT_ATTEMPTED = False
    yield
    reporter_module._SUPABASE_CLIENT = None
    reporter_module._SUPABASE_CLIENT_ATTEMPTED = False


def test_falls_back_to_jsonl_when_supabase_env_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setenv("CANVS_RUNS_DIR", str(tmp_path))

    canvs_report("run1", event="run_start")
    canvs_metric("run1", "n1", step=0, loss=0.5)

    path = tmp_path / "run1.jsonl"
    assert path.exists()
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert lines[0]["event"] == "run_start"
    assert lines[1]["event"] == "metric"
    assert lines[1]["step"] == 0
    assert lines[1]["values"] == {"loss": 0.5}


def test_never_raises_on_bad_supabase_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://localhost:0")
    monkeypatch.setenv("SUPABASE_KEY", "bogus")
    monkeypatch.setenv("CANVS_RUNS_DIR", str(tmp_path))

    # Should not raise even though the Supabase call will fail; falls back to JSONL.
    canvs_report("run2", event="run_start")

    path = tmp_path / "run2.jsonl"
    assert path.exists()


def test_supabase_client_cached_and_dual_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "http://example.invalid")
    monkeypatch.setenv("SUPABASE_KEY", "key")
    monkeypatch.setenv("CANVS_RUNS_DIR", str(tmp_path))

    calls = {"create_client": 0, "inserts": []}

    class FakeTable:
        def insert(self, payload):
            calls["inserts"].append(payload)
            return self

        def execute(self):
            return None

    class FakeClient:
        def table(self, name):
            return FakeTable()

    def fake_create_client(url, key):
        calls["create_client"] += 1
        return FakeClient()

    monkeypatch.setattr("supabase.create_client", fake_create_client)

    canvs_report("run3", event="run_start")
    canvs_metric("run3", "n1", step=0, loss=0.1)

    # Client constructed exactly once across both calls (module-level cache).
    assert calls["create_client"] == 1
    # Both events pushed to Supabase...
    assert len(calls["inserts"]) == 2
    # ...and both also dual-written to the local JSONL.
    path = tmp_path / "run3.jsonl"
    assert path.exists()
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(lines) == 2
    assert lines[0]["event"] == "run_start"
    assert lines[1]["event"] == "metric"

import json

from canvs.reporter import canvs_metric, canvs_report


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

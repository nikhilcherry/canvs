import json
import time

from canvs.compiler import compile_graph
from canvs.graph import Graph, GraphEdge, GraphNode
from canvs.registry import node, registry
from canvs.runner import LocalRunner


def test_local_run_completes_and_reports_events(tmp_path):
    @node(category="data", name="Nums")
    def nums(n: int = 4) -> list:
        return list(range(n))

    @node(category="proc", name="Total")
    def total(data: list) -> int:
        return sum(data)

    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[
            GraphNode(id="n1", spec="data.nums", config={"n": 4}),
            GraphNode(id="n2", spec="proc.total", config={}),
        ],
        edges=[GraphEdge(source="n1", target="n2", target_port="data")],
    )
    run_id = "testrun1"
    artifact = compile_graph(graph, "local", run_id, registry=registry)

    runner = LocalRunner(runs_dir=str(tmp_path))
    handle = runner.start(artifact)

    deadline = time.time() + 20
    while handle.status() not in ("done", "failed") and time.time() < deadline:
        time.sleep(0.2)

    assert handle.status() == "done"

    jsonl_path = tmp_path / f"{run_id}.jsonl"
    assert jsonl_path.exists()
    events = [json.loads(line) for line in jsonl_path.read_text().splitlines()]
    event_names = [e["event"] for e in events]
    assert "run_start" in event_names
    assert "node_done" in event_names
    assert "run_done" in event_names

    log_lines = handle.tail_log(50)
    assert isinstance(log_lines, list)


def test_kill_terminates_running_process(tmp_path):
    @node(category="proc", name="Slow")
    def slow(n: int = 1) -> int:
        import time as _time

        _time.sleep(5)
        return n

    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[GraphNode(id="n1", spec="proc.slow", config={"n": 1})],
    )
    run_id = "testrun2"
    artifact = compile_graph(graph, "local", run_id, registry=registry)

    runner = LocalRunner(runs_dir=str(tmp_path))
    handle = runner.start(artifact)
    time.sleep(0.5)
    assert handle.process.poll() is None  # still running

    handle.kill()
    time.sleep(1.0)
    assert handle.process.poll() is not None


def test_kill_escalates_to_sigkill_when_process_ignores_sigterm(tmp_path):
    @node(category="proc", name="Stubborn")
    def stubborn(n: int = 1) -> int:
        import signal as _signal
        import time as _time

        _signal.signal(_signal.SIGTERM, _signal.SIG_IGN)
        _time.sleep(30)
        return n

    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[GraphNode(id="n1", spec="proc.stubborn", config={"n": 1})],
    )
    run_id = "testrun3"
    artifact = compile_graph(graph, "local", run_id, registry=registry)

    runner = LocalRunner(runs_dir=str(tmp_path))
    handle = runner.start(artifact)
    time.sleep(0.5)
    assert handle.process.poll() is None  # still running, ignoring SIGTERM

    start = time.time()
    handle.kill()
    elapsed = time.time() - start

    assert handle.process.poll() is not None  # escalation reaped it
    assert elapsed >= 5.0  # waited the full terminate() grace period first

import nbformat

from canvs.compiler import compile_graph
from canvs.graph import Graph, GraphEdge, GraphNode
from canvs.registry import node, registry


def _register_pipeline_nodes():
    @node(category="data", name="Make Numbers")
    def make_numbers(n: int = 5, seed: int = 1) -> list:
        import random

        rng = random.Random(seed)
        return [rng.random() for _ in range(n)]

    @node(category="proc", name="Scale", requires=["numpy"])
    def scale(data: list, factor: float = 2.0) -> list:
        return [x * factor for x in data]

    @node(category="train", name="Report")
    def report(data: list, _run_id: str = "", _node_id: str = "") -> dict:
        report_metric = globals().get("canvs_metric")
        if report_metric is not None:
            report_metric(_run_id, _node_id, step=0, mean=sum(data) / len(data))
        return {"mean": sum(data) / len(data)}


def _build_graph() -> Graph:
    return Graph(
        graph_id="g1",
        name="pipeline",
        nodes=[
            GraphNode(id="n1", spec="data.make_numbers", config={"n": 5}),
            GraphNode(id="n2", spec="proc.scale", config={"factor": 3.0}),
            GraphNode(id="n3", spec="train.report", config={}),
        ],
        edges=[
            GraphEdge(source="n1", target="n2", target_port="data"),
            GraphEdge(source="n2", target="n3", target_port="data"),
        ],
    )


def test_local_script_self_contained_and_valid_python():
    _register_pipeline_nodes()
    artifact = compile_graph(_build_graph(), "local", "run123", registry=registry)

    assert artifact.filename == "pipeline.py"
    assert "import canvs" not in artifact.content
    assert "from canvs" not in artifact.content
    assert "def canvs_report" in artifact.content
    assert "def canvs_metric" in artifact.content
    assert "def make_numbers" in artifact.content
    assert "def scale" in artifact.content
    assert "def report" in artifact.content
    assert "out_n1 = make_numbers(n=5)" in artifact.content
    assert "out_n2 = scale(out_n1, factor=3.0)" in artifact.content
    assert "_run_id=RUN_ID" in artifact.content
    assert "_node_id='n3'" in artifact.content

    compile(artifact.content, "<pipeline>", "exec")


def test_compiled_script_reports_lifecycle_events():
    _register_pipeline_nodes()
    artifact = compile_graph(_build_graph(), "local", "runY", registry=registry)

    assert 'event="run_start"' in artifact.content
    assert 'event="node_start"' in artifact.content
    assert 'event="node_done"' in artifact.content
    assert 'event="node_failed"' in artifact.content
    assert 'event="run_failed"' in artifact.content
    assert 'event="run_done"' in artifact.content


def test_deduplicates_node_source_for_repeated_spec():
    _register_pipeline_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[
            GraphNode(id="n1", spec="data.make_numbers", config={"n": 3}),
            GraphNode(id="n2", spec="data.make_numbers", config={"n": 4}),
        ],
    )
    artifact = compile_graph(graph, "local", "runX", registry=registry)
    assert artifact.content.count("def make_numbers") == 1


def test_kaggle_notebook_self_contained_with_dataset_note_and_deps():
    _register_pipeline_nodes()
    artifact = compile_graph(_build_graph(), "kaggle", "run456", registry=registry)

    assert artifact.filename == "pipeline.ipynb"
    assert "import canvs" not in artifact.content
    assert "from canvs" not in artifact.content

    nb = nbformat.reads(artifact.content, as_version=4)
    assert any(c.cell_type == "markdown" and "/kaggle/input/" in c.source for c in nb.cells)
    assert any(
        c.cell_type == "code" and "pip install" in c.source and "numpy" in c.source
        for c in nb.cells
    )


def test_colab_notebook_has_no_dataset_markdown():
    _register_pipeline_nodes()
    artifact = compile_graph(_build_graph(), "colab", "run789", registry=registry)
    nb = nbformat.reads(artifact.content, as_version=4)
    assert not any(c.cell_type == "markdown" for c in nb.cells)

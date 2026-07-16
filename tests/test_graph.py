from canvs.graph import Graph, GraphEdge, GraphNode
from canvs.registry import node, registry


def _register_common_nodes():
    @node(category="data", name="Source")
    def source() -> list:
        return [1, 2, 3]

    @node(category="proc", name="Step")
    def step(data: list, factor: int) -> list:
        return [x * factor for x in data]

    @node(category="out", name="Sink")
    def sink(data: list) -> dict:
        return {"data": data}


def test_valid_graph_has_no_errors():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="pipeline",
        nodes=[
            GraphNode(id="n1", spec="data.source", config={}),
            GraphNode(id="n2", spec="proc.step", config={"factor": 2}),
            GraphNode(id="n3", spec="out.sink", config={}),
        ],
        edges=[
            GraphEdge(source="n1", target="n2", target_port="data"),
            GraphEdge(source="n2", target="n3", target_port="data"),
        ],
    )
    assert graph.validate_against(registry) == []


def test_duplicate_node_id_error():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[
            GraphNode(id="n1", spec="data.source", config={}),
            GraphNode(id="n1", spec="proc.step", config={"factor": 2}),
        ],
    )
    errors = graph.validate_against(registry)
    assert any(e.field == "id" and "Duplicate node id" in e.message for e in errors)


def test_unknown_spec_error():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[GraphNode(id="n1", spec="data.nonexistent", config={})],
    )
    errors = graph.validate_against(registry)
    assert any(e.field == "spec" for e in errors)


def test_unknown_config_key_error():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[GraphNode(id="n1", spec="data.source", config={"bogus": 1})],
    )
    errors = graph.validate_against(registry)
    assert any(e.field == "config.bogus" for e in errors)


def test_bad_config_type_error():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[
            GraphNode(id="n1", spec="data.source", config={}),
            GraphNode(id="n2", spec="proc.step", config={"factor": "not-an-int"}),
        ],
        edges=[GraphEdge(source="n1", target="n2", target_port="data")],
    )
    errors = graph.validate_against(registry)
    assert any(e.field == "config.factor" and "expects type" in e.message for e in errors)


def test_missing_required_param_error():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[
            GraphNode(id="n1", spec="data.source", config={}),
            GraphNode(id="n2", spec="proc.step", config={}),
        ],
        edges=[GraphEdge(source="n1", target="n2", target_port="data")],
    )
    errors = graph.validate_against(registry)
    assert any(e.field == "config.factor" and "Missing required param" in e.message for e in errors)


def test_dangling_edge_source_error():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[GraphNode(id="n2", spec="proc.step", config={"factor": 2})],
        edges=[GraphEdge(source="missing", target="n2", target_port="data")],
    )
    errors = graph.validate_against(registry)
    assert any("does not exist" in e.message for e in errors)


def test_dangling_edge_target_error():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[GraphNode(id="n1", spec="data.source", config={})],
        edges=[GraphEdge(source="n1", target="missing", target_port="data")],
    )
    errors = graph.validate_against(registry)
    assert any("does not exist" in e.message for e in errors)


def test_unknown_target_port_error():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[
            GraphNode(id="n1", spec="data.source", config={}),
            GraphNode(id="n2", spec="proc.step", config={"factor": 2}),
        ],
        edges=[GraphEdge(source="n1", target="n2", target_port="nonexistent_port")],
    )
    errors = graph.validate_against(registry)
    assert any("Target port" in e.message for e in errors)


def test_unfed_required_input_error():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[GraphNode(id="n2", spec="proc.step", config={"factor": 2})],
        edges=[],
    )
    errors = graph.validate_against(registry)
    assert any(e.field == "inputs.data" and "not fed" in e.message for e in errors)


def test_input_fed_by_multiple_edges_error():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[
            GraphNode(id="n1", spec="data.source", config={}),
            GraphNode(id="n1b", spec="data.source", config={}),
            GraphNode(id="n2", spec="proc.step", config={"factor": 2}),
        ],
        edges=[
            GraphEdge(source="n1", target="n2", target_port="data"),
            GraphEdge(source="n1b", target="n2", target_port="data"),
        ],
    )
    errors = graph.validate_against(registry)
    assert any(e.field == "inputs.data" and "2 edges" in e.message for e in errors)


def test_cycle_error():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[
            GraphNode(id="n1", spec="proc.step", config={"factor": 2}),
            GraphNode(id="n2", spec="proc.step", config={"factor": 2}),
        ],
        edges=[
            GraphEdge(source="n1", target="n2", target_port="data"),
            GraphEdge(source="n2", target="n1", target_port="data"),
        ],
    )
    errors = graph.validate_against(registry)
    assert any(e.field == "graph" and "cycle" in e.message for e in errors)


def test_disconnected_graph_error():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[
            GraphNode(id="n1", spec="data.source", config={}),
            GraphNode(id="n2", spec="data.source", config={}),
        ],
        edges=[],
    )
    errors = graph.validate_against(registry)
    assert any(e.field == "graph" and "connected" in e.message for e in errors)


def test_topo_order_deterministic_and_respects_deps():
    _register_common_nodes()
    graph = Graph(
        graph_id="g1",
        name="p",
        nodes=[
            GraphNode(id="n3", spec="proc.step", config={"factor": 2}),
            GraphNode(id="n1", spec="data.source", config={}),
            GraphNode(id="n2", spec="proc.step", config={"factor": 2}),
        ],
        edges=[
            GraphEdge(source="n1", target="n2", target_port="data"),
            GraphEdge(source="n1", target="n3", target_port="data"),
        ],
    )
    order = graph.topo_order()
    assert order == ["n1", "n2", "n3"]
    # deterministic across repeated calls
    assert graph.topo_order() == order

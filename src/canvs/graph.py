"""Graph model: the JSON contract between frontend and backend.

A Graph is nodes + edges + per-node config. validate_against() checks
the graph against a Registry and returns a list of structured errors
instead of raising, so the frontend can render all of them on the
canvas at once. topo_order() gives a deterministic execution order
that compiled artifacts rely on for reproducibility.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    id: str
    spec: str
    config: dict = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source: str
    target: str
    target_port: str


class GraphError(BaseModel):
    node_id: str | None
    field: str
    message: str


class Graph(BaseModel):
    graph_id: str
    name: str
    nodes: list[GraphNode]
    edges: list[GraphEdge] = Field(default_factory=list)

    def _node_map(self) -> dict[str, GraphNode]:
        return {n.id: n for n in self.nodes}

    def validate_against(self, registry) -> list[GraphError]:
        errors: list[GraphError] = []
        node_map = self._node_map()

        # 0. no duplicate node ids. _node_map() (and topo_order()) key off
        # id, so a duplicate silently drops all but the last node with that
        # id from the graph -- everything downstream would "validate"
        # cleanly against a graph the user never actually built.
        seen_ids: set[str] = set()
        for gn in self.nodes:
            if gn.id in seen_ids:
                errors.append(GraphError(
                    node_id=gn.id, field="id",
                    message=f"Duplicate node id: {gn.id!r}",
                ))
            seen_ids.add(gn.id)

        # 1. every spec exists; config keys/types/required params.
        for gn in self.nodes:
            if gn.spec not in registry:
                errors.append(GraphError(
                    node_id=gn.id, field="spec",
                    message=f"Unknown node spec: {gn.spec!r}",
                ))
                continue

            node_spec = registry.get(gn.spec)

            for key, value in gn.config.items():
                if key not in node_spec.params:
                    errors.append(GraphError(
                        node_id=gn.id, field=f"config.{key}",
                        message=f"Unknown param {key!r} for spec {gn.spec!r}",
                    ))
                    continue
                schema = node_spec.params[key]
                if not _matches_type(value, schema):
                    errors.append(GraphError(
                        node_id=gn.id, field=f"config.{key}",
                        message=(
                            f"Param {key!r} expects type {schema.get('type')!r}"
                            + (f" (one of {schema['enum']})" if "enum" in schema else "")
                            + f", got {value!r}"
                        ),
                    ))

            for pname, schema in node_spec.params.items():
                if schema.get("required") and pname not in gn.config:
                    errors.append(GraphError(
                        node_id=gn.id, field=f"config.{pname}",
                        message=f"Missing required param {pname!r}",
                    ))

        # 2. edge endpoints & ports exist.
        incoming: dict[tuple[str, str], list[GraphEdge]] = {}
        for edge in self.edges:
            if edge.source not in node_map:
                errors.append(GraphError(
                    node_id=edge.target, field="edges",
                    message=f"Edge source {edge.source!r} does not exist",
                ))
                continue
            if edge.target not in node_map:
                errors.append(GraphError(
                    node_id=edge.target, field="edges",
                    message=f"Edge target {edge.target!r} does not exist",
                ))
                continue

            target_spec_id = node_map[edge.target].spec
            if target_spec_id in registry:
                target_spec = registry.get(target_spec_id)
                if edge.target_port not in target_spec.inputs:
                    errors.append(GraphError(
                        node_id=edge.target, field="edges",
                        message=(
                            f"Target port {edge.target_port!r} does not exist "
                            f"on {target_spec_id!r}"
                        ),
                    ))
                    continue

            incoming.setdefault((edge.target, edge.target_port), []).append(edge)

        # 3. every non-defaulted data input fed by exactly one edge.
        for gn in self.nodes:
            if gn.spec not in registry:
                continue
            node_spec = registry.get(gn.spec)
            for input_name in node_spec.inputs:
                feeds = incoming.get((gn.id, input_name), [])
                if len(feeds) == 0 and input_name not in node_spec.input_defaults:
                    errors.append(GraphError(
                        node_id=gn.id, field=f"inputs.{input_name}",
                        message=f"Input {input_name!r} is not fed by any edge",
                    ))
                elif len(feeds) > 1:
                    errors.append(GraphError(
                        node_id=gn.id, field=f"inputs.{input_name}",
                        message=f"Input {input_name!r} is fed by {len(feeds)} edges, expected 1",
                    ))

        # 4. DAG + weak connectivity.
        cycle_nodes = _find_cycle(self.nodes, self.edges)
        if cycle_nodes:
            errors.append(GraphError(
                node_id=None, field="graph",
                message=f"Graph contains a cycle: {' -> '.join(cycle_nodes)}",
            ))
        elif len(self.nodes) > 1 and not _weakly_connected(self.nodes, self.edges):
            errors.append(GraphError(
                node_id=None, field="graph",
                message="Graph is not weakly connected",
            ))

        return errors

    def topo_order(self) -> list[str]:
        ids = sorted(n.id for n in self.nodes)
        deps: dict[str, set[str]] = {i: set() for i in ids}
        for edge in self.edges:
            if edge.target in deps and edge.source in deps:
                deps[edge.target].add(edge.source)

        result: list[str] = []
        remaining = set(ids)
        while remaining:
            ready = sorted(i for i in remaining if not (deps[i] & remaining))
            if not ready:
                raise ValueError("Graph contains a cycle")
            for i in ready:
                result.append(i)
                remaining.discard(i)
        return result


def _matches_type(value, schema: dict) -> bool:
    if "enum" in schema:
        return value in schema["enum"]
    t = schema.get("type")
    if t == "string":
        return isinstance(value, str)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    return True


def _find_cycle(nodes: list[GraphNode], edges: list[GraphEdge]) -> list[str] | None:
    ids = [n.id for n in nodes]
    adj: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges:
        if e.source in adj and e.target in adj:
            adj[e.source].append(e.target)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {i: WHITE for i in ids}
    path: list[str] = []

    def dfs(u: str) -> list[str] | None:
        color[u] = GRAY
        path.append(u)
        for v in adj[u]:
            if color[v] == GRAY:
                idx = path.index(v)
                return path[idx:] + [v]
            if color[v] == WHITE:
                found = dfs(v)
                if found:
                    return found
        path.pop()
        color[u] = BLACK
        return None

    for i in sorted(ids):
        if color[i] == WHITE:
            found = dfs(i)
            if found:
                return found
    return None


def _weakly_connected(nodes: list[GraphNode], edges: list[GraphEdge]) -> bool:
    ids = [n.id for n in nodes]
    if not ids:
        return True
    adj: dict[str, set[str]] = {i: set() for i in ids}
    for e in edges:
        if e.source in adj and e.target in adj:
            adj[e.source].add(e.target)
            adj[e.target].add(e.source)

    seen = set()
    stack = [ids[0]]
    while stack:
        u = stack.pop()
        if u in seen:
            continue
        seen.add(u)
        stack.extend(adj[u] - seen)
    return seen == set(ids)

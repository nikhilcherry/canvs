"""target="local" compiler: produces a single runnable .py script."""
from __future__ import annotations

from . import templates


def compile_script(graph, registry, run_id: str) -> str:
    used_specs = sorted({n.spec for n in graph.nodes})

    parts = [templates.render_future_import() + "\n" + templates.render_header(run_id, "local")]
    for spec_id in used_specs:
        parts.append(templates.render_node_block(registry.get(spec_id)))
    parts.append(templates.render_execution_block(graph, registry))
    parts.append(templates.render_footer())

    return "\n".join(parts)

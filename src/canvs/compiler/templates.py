"""Shared code-generation blocks used by both the script and notebook
compiler targets. Nothing here may import canvs at the *output* level
— only the compiler itself may import canvs to read source text.
"""
from __future__ import annotations

import ast
import inspect
import re

from .. import reporter as _reporter_module


def _strip_module_docstring(source: str) -> str:
    tree = ast.parse(source)
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        doc = tree.body[0]
        lines = source.splitlines()
        return "\n".join(lines[: doc.lineno - 1] + lines[doc.end_lineno:])
    return source


def _reporter_source() -> str:
    source = _strip_module_docstring(inspect.getsource(_reporter_module))
    lines = [ln for ln in source.splitlines() if ln.strip() != "from __future__ import annotations"]
    return "\n".join(lines).strip() + "\n"


def render_future_import() -> str:
    # Must be the first statement in the file/cell: defers evaluation of
    # node function annotations (Literal[...], list[...], custom types)
    # so re-defining node source in the compiled artifact never needs
    # those names to actually resolve at def-time.
    return "from __future__ import annotations\n"


def render_header(run_id: str, target: str) -> str:
    return (
        "# ── compiled pipeline artifact ──\n"
        f"# target: {target} | run_id: {run_id}\n\n"
        f'RUN_ID = {run_id!r}\n'
        f'CANVS_TARGET = {target!r}\n\n'
        + _reporter_source()
    )


def alias_name(spec) -> str:
    """Collision-safe name for a node's inlined function.

    Two specs can share a bare function name across categories (e.g.
    ``data.load`` and ``model.load``), which would silently shadow each
    other once both are inlined into the same compiled artifact. Every
    inlined def and call site uses this alias instead of the bare name.
    """
    func_name = spec.id.split(".")[-1]
    category = re.sub(r"\W", "_", spec.category)
    return f"{func_name}__{category}"


def render_node_block(spec) -> str:
    banner = f"# ── node: {spec.id} ──"
    func_name = spec.id.split(".")[-1]
    alias = alias_name(spec)
    pattern = re.compile(rf"^def {re.escape(func_name)}\(", re.MULTILINE)
    source, n_subs = pattern.subn(f"def {alias}(", spec.source.rstrip(), count=1)
    assert n_subs == 1, f"expected exactly one top-level def {func_name}( in {spec.id} source"
    return f"{banner}\n{source}\n"


def render_execution_block(graph, registry) -> str:
    order = graph.topo_order()
    node_map = {n.id: n for n in graph.nodes}

    incoming: dict[tuple[str, str], str] = {}
    for edge in graph.edges:
        incoming[(edge.target, edge.target_port)] = edge.source

    lines = ['canvs_report(RUN_ID, event="run_start")', "try:"]
    for node_id in order:
        gn = node_map[node_id]
        spec = registry.get(gn.spec)
        func_name = alias_name(spec)

        args = []
        for input_name in spec.inputs:
            source_id = incoming.get((node_id, input_name))
            if source_id is not None:
                args.append(f"out_{source_id}")
        for key in sorted(gn.config.keys()):
            args.append(f"{key}={gn.config[key]!r}")
        if spec.accepts_run_id:
            args.append("_run_id=RUN_ID")
        if spec.accepts_node_id:
            args.append(f"_node_id={node_id!r}")

        call = f"{func_name}({', '.join(args)})"

        lines.append(f'    canvs_report(RUN_ID, event="node_start", node={node_id!r})')
        lines.append("    try:")
        lines.append(f"        out_{node_id} = {call}")
        lines.append(f'        canvs_report(RUN_ID, event="node_done", node={node_id!r})')
        lines.append("    except Exception as e:")
        lines.append(
            f'        canvs_report(RUN_ID, event="node_failed", node={node_id!r}, '
            'payload={"error": str(e)})'
        )
        lines.append("        raise")
    lines.append("except Exception:")
    lines.append('    canvs_report(RUN_ID, event="run_failed")')
    lines.append("    raise")

    return "\n".join(lines) + "\n"


def render_footer() -> str:
    return 'canvs_report(RUN_ID, event="run_done")\n'


def render_env_cell(env_vars: dict[str, str]) -> str:
    # Kaggle kernels pushed via API cannot attach Kaggle account secrets,
    # so Supabase credentials are injected as a plaintext cell instead.
    # Only ever use the anon key here, and keep pushed kernels private.
    lines = ["import os", ""]
    for key, value in env_vars.items():
        lines.append(f"os.environ[{key!r}] = {value!r}")
    return "\n".join(lines) + "\n"

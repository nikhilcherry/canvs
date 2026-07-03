# canvs

canvs is a visual ML pipeline runner. Users wire nodes (data → preprocess →
model → train → eval → export) on a drag-and-drop canvas, then execute the
pipeline locally or on Kaggle/Colab, with live metrics streaming back to
the UI.

This repository currently contains the **backend skeleton and compiler**
only — no frontend, no Kaggle push. The core (`src/canvs/`) contains zero
domain-specific (ML or astronomy) logic: it composes and executes
registered functions, and never imports torch, sklearn, lightkurve, or
any ML library. Domain nodes live in separate examples/consumer packages.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the server

```bash
cp .env.example .env   # fill in SUPABASE_URL / SUPABASE_KEY if you have a project; leave blank to use local JSONL fallback
uvicorn canvs.server:app --reload
```

On startup the server imports the modules listed in `CANVS_NODE_MODULES`
(comma-separated, default `examples.toy_nodes`) so their `@node`-decorated
functions register themselves.

### Endpoints

| Method | Path                  | Behavior                                                             |
|--------|-----------------------|-----------------------------------------------------------------------|
| GET    | `/registry`           | Full node palette: `{"categories": [...], "nodes": [...]}`            |
| POST   | `/graphs/validate`    | Body: graph JSON → `{"valid": bool, "errors": [...]}`                 |
| POST   | `/runs`               | Body: `{"graph": {...}, "target": "local"}` → compiles + starts a run |
| GET    | `/runs/{run_id}`      | Status + last 50 log lines (local runs)                               |
| POST   | `/runs/{run_id}/kill` | Kill a local run                                                       |

## Registering nodes in a consumer project

Decorate any plain Python function with `@node`. Scalar-typed parameters
(`str`, `int`, `float`, `bool`, `Literal[...]`) become config fields
rendered as a form by the frontend; parameters typed as anything else
(e.g. `list`, `dict`, a custom class) become data input ports wired by
graph edges. The return type annotation defines the node's single output
port.

```python
from typing import Literal
from canvs import node

@node(category="preprocess", name="Normalize", description="Scale values to [0, 1]")
def normalize(data: list, method: Literal["minmax", "zscore"] = "minmax", clip: bool = True) -> list:
    ...
```

Keep each node function's own imports **inside its body**, not at module
scope — the compiler embeds only the function's extracted source
(`inspect.getsource`) into compiled artifacts, so a module-level import
would silently disappear from the generated script/notebook.

Point `CANVS_NODE_MODULES` at your package (e.g.
`CANVS_NODE_MODULES=my_pipeline.nodes`) so `registry.load_module()` picks
it up on server startup, or call `registry.load_module("my_pipeline.nodes")`
yourself before compiling.

## The graph JSON contract

```json
{
  "graph_id": "uuid",
  "name": "my_pipeline",
  "nodes": [
    {"id": "n1", "spec": "data.load_csv", "config": {"path": "train.csv"}},
    {"id": "n2", "spec": "preprocess.normalize", "config": {"method": "zscore"}}
  ],
  "edges": [
    {"source": "n1", "target": "n2", "target_port": "data"}
  ]
}
```

- `nodes[].spec` references a registered node id (`{category}.{function_name}`).
- `nodes[].config` supplies values for that node's scalar params.
- `edges[].target_port` names the data-input parameter on the target node
  being fed.
- `POST /graphs/validate` returns every structural problem at once
  (unknown spec, bad config type, missing required param, dangling edge,
  unfed input, cycle, disconnected graph) rather than failing on the
  first error, so the frontend can annotate the whole canvas.

## Compiled artifacts

`compile_graph(graph, target, run_id)` produces a `CompiledArtifact`
(`local` → `.py`, `kaggle`/`colab` → `.ipynb`). Every artifact is fully
self-contained: it inlines `reporter.py` verbatim and never
`import canvs`. Node dependencies declared via `@node(..., requires=[...])`
are unioned into the notebook targets' pip-install cell (local runs
assume the dependency is already present in the environment).

## Supabase setup (manual)

The reporter (`canvs_report` / `canvs_metric`, embedded in every compiled
artifact) phones home to Supabase when `SUPABASE_URL` and `SUPABASE_KEY`
are both set in the run's environment. When either is absent — or the
insert throws for any reason — it falls back to appending JSON lines to
`$CANVS_RUNS_DIR/{run_id}.jsonl`, without ever raising or interrupting
the run.

To wire up Supabase:

1. Create a Supabase project.
2. Run `src/canvs/supabase_schema.sql` against it (SQL editor or
   `supabase db push`) to create the `runs` and `metrics` tables. RLS is
   deliberately left off for this internal tool.
3. Copy the anon key and project URL into `.env` as `SUPABASE_URL` /
   `SUPABASE_KEY`, and make sure the runner subprocess inherits them.

## Tests

```bash
pytest
```

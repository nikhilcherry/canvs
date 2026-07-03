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
| GET    | `/health`             | `{"ok": bool, "supabase": bool, "kaggle": {"available": bool, "reason": str \| null}}` |
| GET    | `/registry`           | Full node palette: `{"categories": [...], "nodes": [...]}`            |
| POST   | `/graphs/validate`    | Body: graph JSON → `{"valid": bool, "errors": [...]}`                 |
| POST   | `/runs`               | Body: `{"graph": {...}, "target": "local"}` → compiles + starts a run |
| GET    | `/runs/{run_id}`      | Status + last 50 log lines (local runs); merges Kaggle kernel status for pushed runs |
| POST   | `/runs/{run_id}/kill` | Kill a local run                                                       |

## Kaggle push

`POST /runs` with `"target": "kaggle"` and a `"kaggle"` block pushes the
compiled notebook straight to your Kaggle account instead of returning
it for download:

```json
{
  "graph": {...},
  "target": "kaggle",
  "kaggle": {"push": true, "title": "my-pipeline", "dataset_slugs": ["me/my-dataset"], "gpu": false}
}
```

This requires the optional `kaggle` dependency group and Kaggle
credentials resolved the standard way (`~/.kaggle/kaggle.json` or
`KAGGLE_USERNAME`/`KAGGLE_KEY` env vars):

```bash
pip install -e ".[kaggle]"
```

If the package isn't installed or credentials aren't usable, `/runs`
falls back to the normal download response and adds
`"push_available": false` plus a `"push_unavailable_reason"` — the
frontend uses this (via `/health`) to gray out the Push button with the
reason as a tooltip. `GET /runs/{run_id}` merges the Kaggle kernel
status for pushed runs (queued/running → `running`, complete → `done`,
error/cancelled → `failed`).

**Secrets caveat (read this before pushing):** Kaggle kernels pushed
via the API cannot attach Kaggle account secrets. To let a pushed
kernel still phone home to Supabase, canvs injects your `SUPABASE_URL`
and **anon** key into a plaintext cell at the top of the pushed
notebook whenever the server has Supabase configured. This is
acceptable for an internal tool as long as you:

- **Never** put the Supabase **service-role** key in `SUPABASE_KEY` —
  only the anon key belongs here.
- Keep pushed kernels private (the default; `private: false` is opt-in
  per push).

### Manual smoke test (credentials required)

The automated tests mock the Kaggle API entirely, so a live push has to
be checked by hand once real credentials are available:

1. `pip install -e ".[kaggle]"` and drop a valid `~/.kaggle/kaggle.json`
   (or set `KAGGLE_USERNAME`/`KAGGLE_KEY`) in the server's environment.
2. Start the backend and confirm `GET /health` reports
   `"kaggle": {"available": true, "reason": null}`.
3. From the canvas, build the toy pipeline, set target to `kaggle`,
   open **Kaggle settings**, leave dataset slugs empty and GPU off, and
   click **Push**.
4. Confirm the response/UI shows a kernel URL and open it — the kernel
   should appear in your Kaggle account, private, with the notebook
   cells intact.
5. Poll `GET /runs/{run_id}` (or watch the UI) until status reaches
   `done`; if Supabase is configured, confirm metric rows appear in the
   `metrics` table for that `run_id`. Without Supabase, just confirm
   the kernel itself completes successfully.

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
2. Open the SQL editor in the Supabase dashboard, paste the entire
   contents of `src/canvs/supabase_schema.sql`, and run it. This creates
   the `runs` and `metrics` tables (RLS is deliberately left off for
   this internal tool).
3. Enable realtime on the `metrics` table so the frontend can receive
   live INSERT events instead of only polling: uncomment and run the
   footer line in that same file,
   `alter publication supabase_realtime add table metrics;` (SQL editor
   again, or `supabase db push` picks it up automatically since it's
   part of the same file).
4. Copy the anon key and project URL into `.env` as `SUPABASE_URL` /
   `SUPABASE_KEY`, and make sure the runner subprocess inherits them.

### Realtime metrics (frontend)

When `GET /health` reports `supabase: true`, the canvas fetches anon
credentials from `GET /config` and opens a Supabase realtime channel
(`src/realtime.ts`) subscribed to `INSERT` events on `metrics` filtered
to the active `run_id`, instead of polling every second. A slow 10s
poll keeps running alongside it as a gap-filler (realtime can drop
events across a reconnect), and if the channel errors or Supabase isn't
configured, the UI falls back to the original 1s poll automatically.
The RunBar shows a small "live" / "polling" indicator next to the run
status so this is visible, but functionally transparent otherwise.

### Manual smoke test (Supabase project required)

The polling fallback is covered by running the app without Supabase
configured (confirms no crash, no stuck spinner). The realtime path
itself needs a live project to check by hand:

1. Apply `supabase_schema.sql` and its `alter publication` footer line
   per the setup steps above, then set `SUPABASE_URL`/`SUPABASE_KEY` in
   the server's `.env`.
2. Start the backend and confirm `GET /health` reports
   `"supabase": true`, and `GET /config` returns the anon URL/key.
3. Run the toy pipeline locally from the canvas. The RunBar should
   switch from "polling" to "live" shortly after the run starts.
4. Open devtools' Network tab and confirm there is no steady 1Hz
   stream of `/metrics` requests while "live" is shown (only the slow
   10s gap-filler poll).
5. Toggle devtools' network offline, wait a few seconds, then toggle it
   back online. The indicator should drop to "polling" while offline
   and metrics should catch up via the poll's `after_id` without
   duplicate or missing points once reconnected.

## Tests

```bash
pytest
```

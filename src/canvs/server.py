"""FastAPI app exposing the registry, compiler, and local runs."""
from __future__ import annotations

import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import kaggle_push, reporter, run_history
from .compiler import compile_graph
from .graph import Graph
from .registry import registry
from .runner import LocalRunner

log = logging.getLogger(__name__)

runner = LocalRunner()

# run_id -> kernel_slug, for runs pushed to Kaggle.
_kaggle_kernels: dict[str, str] = {}

# Demo nodes, importable only from a source checkout — `examples/` is not part
# of the installed package. Missing is normal, so it must not abort startup.
DEFAULT_NODE_MODULES = "examples.toy_nodes"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configured = os.environ.get("CANVS_NODE_MODULES")
    modules = configured if configured is not None else DEFAULT_NODE_MODULES
    for mod in modules.split(","):
        mod = mod.strip()
        if not mod:
            continue
        try:
            registry.load_module(mod)
        except ImportError:
            # Modules the operator asked for are a real misconfiguration; the
            # demo default just isn't there outside a source checkout.
            if configured is not None:
                raise
            log.warning(
                "Optional demo node module %r not found; starting with no demo "
                "nodes registered. Set CANVS_NODE_MODULES to load your own.",
                mod,
            )
    yield


app = FastAPI(title="canvs", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class KaggleRunOptions(BaseModel):
    push: bool = False
    title: str = "canvs-pipeline"
    dataset_slugs: list[str] = []
    gpu: bool = False


class RunRequest(BaseModel):
    graph: Graph
    target: Literal["local", "kaggle", "colab"] = "local"
    kaggle: KaggleRunOptions | None = None


def _supabase_configured() -> bool:
    return bool(os.environ.get("SUPABASE_URL")) and bool(os.environ.get("SUPABASE_KEY"))


@app.get("/health")
def get_health() -> dict:
    kaggle_available, kaggle_reason = kaggle_push.is_available()
    return {
        "ok": True,
        "supabase": _supabase_configured(),
        "kaggle": {"available": kaggle_available, "reason": kaggle_reason},
    }


@app.get("/config")
def get_config() -> dict:
    """Anon Supabase credentials for the frontend's realtime channel.

    Only served when Supabase is configured -- the frontend checks
    /health first and only calls this when health.supabase is true.
    """
    if not _supabase_configured():
        raise HTTPException(status_code=404, detail="Supabase not configured")
    return {
        "supabase_url": os.environ["SUPABASE_URL"],
        "supabase_anon_key": os.environ["SUPABASE_KEY"],
    }


@app.get("/registry")
def get_registry() -> dict:
    return registry.to_json()


@app.post("/graphs/validate")
def validate_graph(graph: Graph) -> dict:
    errors = graph.validate_against(registry)
    return {"valid": len(errors) == 0, "errors": [e.model_dump() for e in errors]}


@app.post("/runs")
def create_run(req: RunRequest) -> dict:
    errors = req.graph.validate_against(registry)
    if errors:
        raise HTTPException(
            status_code=400,
            detail={"valid": False, "errors": [e.model_dump() for e in errors]},
        )

    run_id = uuid.uuid4().hex

    if req.target == "kaggle" and req.kaggle is not None and req.kaggle.push:
        available, reason = kaggle_push.is_available()
        if not available:
            artifact = compile_graph(req.graph, req.target, run_id, registry=registry)
            return {
                "run_id": run_id,
                "status": "compiled",
                "artifact_filename": artifact.filename,
                "artifact_content": artifact.content,
                "push_available": False,
                "push_unavailable_reason": reason,
            }

        env_vars = None
        if _supabase_configured():
            env_vars = {
                "SUPABASE_URL": os.environ["SUPABASE_URL"],
                "SUPABASE_KEY": os.environ["SUPABASE_KEY"],
            }
        artifact = compile_graph(req.graph, req.target, run_id, registry=registry, env_vars=env_vars)
        kernel_ref = kaggle_push.push_kernel(
            artifact,
            title=req.kaggle.title,
            dataset_slugs=req.kaggle.dataset_slugs,
            gpu=req.kaggle.gpu,
        )
        _kaggle_kernels[run_id] = kernel_ref["kernel_slug"]
        run_history.create_run_record(run_id, req.graph.name, "kaggle", "pushed", req.graph.model_dump())

        return {
            "run_id": run_id,
            "status": "pushed",
            "artifact_filename": artifact.filename,
            "kernel_url": kernel_ref["url"],
        }

    artifact = compile_graph(req.graph, req.target, run_id, registry=registry)

    if req.target == "local":
        runner.start(artifact)
        run_history.create_run_record(run_id, req.graph.name, "local", "pending", req.graph.model_dump())
        return {
            "run_id": run_id,
            "status": "pending",
            "artifact_filename": artifact.filename,
        }

    result = {
        "run_id": run_id,
        "status": "compiled",
        "artifact_filename": artifact.filename,
        "artifact_content": artifact.content,
    }
    if req.target == "kaggle":
        available, reason = kaggle_push.is_available()
        result["push_available"] = available
        if not available:
            result["push_unavailable_reason"] = reason
    return result


@app.get("/runs")
def list_runs() -> dict:
    return {"runs": run_history.list_runs()}


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    kernel_slug = _kaggle_kernels.get(run_id)
    if kernel_slug is not None:
        status_info = kaggle_push.kernel_status(kernel_slug)
        run_history.update_run_status(run_id, status_info["status"])
        return {
            "run_id": run_id,
            "status": status_info["status"],
            "log": [],
            "kernel_slug": kernel_slug,
        }

    handle = runner.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    status = handle.status()
    run_history.update_run_status(run_id, status)
    return {
        "run_id": run_id,
        "status": status,
        "log": handle.tail_log(50),
    }


@app.get("/runs/{run_id}/metrics")
def get_run_metrics(run_id: str, after_id: int = 0) -> dict:
    client = reporter._get_supabase_client() if _supabase_configured() else None
    if client is not None:
        resp = (
            client.table("metrics")
            .select("*")
            .eq("run_id", run_id)
            .gt("id", after_id)
            .order("id")
            .limit(500)
            .execute()
        )
        events = [
            {
                "id": row["id"],
                "event": row["event"],
                "node": row["node"],
                "step": row["step"],
                "values": row["values"],
                "payload": row["payload"],
                "created_at": row["created_at"],
            }
            for row in resp.data
        ]
        return {"events": events}

    runs_dir = os.environ.get("CANVS_RUNS_DIR", "./canvs_runs")
    path = os.path.join(runs_dir, f"{run_id}.jsonl")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Unknown run_id")

    events = []
    with open(path) as f:
        for line_no, line in enumerate(f, start=1):
            if line_no <= after_id:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            events.append({
                "id": line_no,
                "event": record.get("event"),
                "node": record.get("node"),
                "step": record.get("step"),
                "values": record.get("values"),
                "payload": record.get("payload"),
                "created_at": record.get("ts"),
            })
            if len(events) >= 500:
                break

    return {"events": events}


@app.post("/runs/{run_id}/kill")
def kill_run(run_id: str) -> dict:
    handle = runner.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    handle.kill()
    return {"run_id": run_id, "status": handle.status()}

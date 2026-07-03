"""FastAPI app exposing the registry, compiler, and local runs."""
from __future__ import annotations

import json
import os
import uuid
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .compiler import compile_graph
from .graph import Graph
from .registry import registry
from .runner import LocalRunner

runner = LocalRunner()


@asynccontextmanager
async def lifespan(app: FastAPI):
    modules = os.environ.get("CANVS_NODE_MODULES", "examples.toy_nodes")
    for mod in modules.split(","):
        mod = mod.strip()
        if mod:
            registry.load_module(mod)
    yield


app = FastAPI(title="canvs", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    graph: Graph
    target: Literal["local", "kaggle", "colab"] = "local"


def _supabase_configured() -> bool:
    return bool(os.environ.get("SUPABASE_URL")) and bool(os.environ.get("SUPABASE_KEY"))


@app.get("/health")
def get_health() -> dict:
    return {"ok": True, "supabase": _supabase_configured()}


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
    artifact = compile_graph(req.graph, req.target, run_id, registry=registry)

    if req.target == "local":
        runner.start(artifact)
        return {
            "run_id": run_id,
            "status": "pending",
            "artifact_filename": artifact.filename,
        }

    return {
        "run_id": run_id,
        "status": "compiled",
        "artifact_filename": artifact.filename,
        "artifact_content": artifact.content,
    }


@app.get("/runs/{run_id}")
def get_run(run_id: str) -> dict:
    handle = runner.get(run_id)
    if handle is None:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    return {
        "run_id": run_id,
        "status": handle.status(),
        "log": handle.tail_log(50),
    }


@app.get("/runs/{run_id}/metrics")
def get_run_metrics(run_id: str, after_id: int = 0) -> dict:
    if _supabase_configured():
        from supabase import create_client

        client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
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

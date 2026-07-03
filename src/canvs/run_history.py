"""Run history persistence: local run.json files + optional Supabase mirror.

Every run gets a local record regardless of Supabase configuration
(mirrors the reporter's dual-write philosophy from Part 0.2) so history
survives a server restart with zero external dependencies. Reuses
reporter's cached Supabase client rather than creating a second one.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from . import reporter


def _runs_dir() -> str:
    return os.environ.get("CANVS_RUNS_DIR", "./canvs_runs")


def _record_path(run_id: str, runs_dir: str | None = None) -> str:
    base = runs_dir or _runs_dir()
    run_dir = os.path.join(base, run_id)
    os.makedirs(run_dir, exist_ok=True)
    return os.path.join(run_dir, "run.json")


def create_run_record(
    run_id: str,
    name: str,
    target: str,
    status: str,
    graph: dict,
    runs_dir: str | None = None,
) -> None:
    record = {
        "run_id": run_id,
        "name": name,
        "target": target,
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "graph": graph,
    }
    with open(_record_path(run_id, runs_dir), "w") as f:
        json.dump(record, f)

    client = reporter._get_supabase_client()
    if client is not None:
        try:
            client.table("runs").insert({
                "run_id": run_id,
                "name": name,
                "target": target,
                "status": status,
                "graph": graph,
            }).execute()
        except Exception:
            pass


def update_run_status(run_id: str, status: str, runs_dir: str | None = None) -> None:
    path = _record_path(run_id, runs_dir)
    try:
        with open(path) as f:
            record = json.load(f)
        record["status"] = status
        with open(path, "w") as f:
            json.dump(record, f)
    except (OSError, json.JSONDecodeError):
        pass

    client = reporter._get_supabase_client()
    if client is not None:
        try:
            client.table("runs").update({"status": status}).eq("run_id", run_id).execute()
        except Exception:
            pass


def _read_local_records(runs_dir: str | None = None) -> list[dict]:
    base = runs_dir or _runs_dir()
    records = []
    if not os.path.isdir(base):
        return records
    for entry in os.listdir(base):
        path = os.path.join(base, entry, "run.json")
        if os.path.isfile(path):
            try:
                with open(path) as f:
                    records.append(json.load(f))
            except (OSError, json.JSONDecodeError):
                continue
    return records


def list_runs(runs_dir: str | None = None, limit: int = 100) -> list[dict]:
    # Local records win over Supabase on a run_id collision -- they're
    # the source of truth per the same dual-write rule as reporter.py.
    by_id: dict[str, dict] = {}
    for record in _read_local_records(runs_dir):
        by_id[record["run_id"]] = record

    client = reporter._get_supabase_client()
    if client is not None:
        try:
            resp = (
                client.table("runs")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            for row in resp.data:
                run_id = row["run_id"]
                if run_id not in by_id:
                    by_id[run_id] = {
                        "run_id": run_id,
                        "name": row.get("name"),
                        "target": row.get("target"),
                        "status": row.get("status"),
                        "created_at": row.get("created_at"),
                        "graph": row.get("graph"),
                    }
        except Exception:
            pass

    records = sorted(by_id.values(), key=lambda r: r.get("created_at") or "", reverse=True)
    return records[:limit]

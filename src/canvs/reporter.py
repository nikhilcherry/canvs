"""canvs metrics reporter — the phone-home client.

This file is inlined verbatim into every compiled artifact (see
compiler/templates.py), so it must stay stdlib + supabase only, with
no imports from canvs itself and no dependency on anything outside
this module. It must never raise: a broken metrics channel should
never take down a training run.
"""
from __future__ import annotations

import json
import os
import time

_WARNED = False


def _warn_once(msg: str) -> None:
    global _WARNED
    if not _WARNED:
        print(f"[reporter] warning: {msg}")
        _WARNED = True


def _fallback_path(run_id: str) -> str:
    base_dir = os.environ.get("CANVS_RUNS_DIR", "./canvs_runs")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, f"{run_id}.jsonl")


def _write_fallback(record: dict) -> None:
    try:
        path = _fallback_path(record["run_id"])
        with open(path, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        _warn_once(f"failed to write fallback metrics file: {e}")


def canvs_report(
    run_id: str,
    event: str,
    node: str | None = None,
    metrics: dict | None = None,
    payload: dict | None = None,
) -> None:
    step = None
    values = metrics
    if metrics is not None and "step" in metrics:
        values = {k: v for k, v in metrics.items() if k != "step"}
        step = metrics["step"]

    record = {
        "run_id": run_id,
        "event": event,
        "node": node,
        "step": step,
        "values": values,
        "payload": payload,
        "ts": time.time(),
    }

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if url and key:
        try:
            from supabase import create_client

            client = create_client(url, key)
            client.table("metrics").insert({
                "run_id": run_id,
                "event": event,
                "node": node,
                "step": step,
                "values": values,
                "payload": payload,
            }).execute()
            return
        except Exception as e:
            _warn_once(f"Supabase insert failed ({e}); falling back to local JSONL logging.")

    _write_fallback(record)


def canvs_metric(run_id: str, node: str, step: int, **values) -> None:
    canvs_report(run_id, event="metric", node=node, metrics={"step": step, **values})

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
_SUPABASE_CLIENT = None
_SUPABASE_CLIENT_ATTEMPTED = False


def _warn_once(msg: str) -> None:
    global _WARNED
    if not _WARNED:
        print(f"[reporter] warning: {msg}")
        _WARNED = True


def _get_supabase_client():
    """Return the process-wide Supabase client, creating it at most once.

    A prior creation failure (missing package, bad URL) is cached too --
    every canvs_report() call would otherwise retry construction.
    """
    global _SUPABASE_CLIENT, _SUPABASE_CLIENT_ATTEMPTED
    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT
    if _SUPABASE_CLIENT_ATTEMPTED:
        return None
    _SUPABASE_CLIENT_ATTEMPTED = True

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None

    try:
        from supabase import create_client

        _SUPABASE_CLIENT = create_client(url, key)
        return _SUPABASE_CLIENT
    except Exception as e:
        _warn_once(f"failed to create Supabase client: {e}")
        return None


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
    """Record a run/node lifecycle or metric event.

    Always appends to the local JSONL fallback file -- that file is the
    source of truth for local runs. When SUPABASE_URL/SUPABASE_KEY are
    set, additionally pushes the same event to Supabase as a remote
    mirror + realtime channel. A Supabase failure is warned once and
    never affects the local write or raises into the caller.
    """
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

    _write_fallback(record)

    client = _get_supabase_client()
    if client is not None:
        try:
            client.table("metrics").insert({
                "run_id": run_id,
                "event": event,
                "node": node,
                "step": step,
                "values": values,
                "payload": payload,
            }).execute()
        except Exception as e:
            _warn_once(f"Supabase insert failed ({e}); continuing with local JSONL only.")


def canvs_metric(run_id: str, node: str, step: int, **values) -> None:
    canvs_report(run_id, event="metric", node=node, metrics={"step": step, **values})

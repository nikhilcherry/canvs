"""LocalRunner: executes a compiled artifact as a subprocess and lets
callers poll its status via the embedded reporter's JSONL fallback
file plus the subprocess's own exit code.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


class RunHandle:
    def __init__(self, run_id: str, run_dir: str, runs_dir: str, process: subprocess.Popen):
        self.run_id = run_id
        self.run_dir = run_dir
        self.runs_dir = runs_dir
        self.process = process

    def _log_path(self) -> str:
        return os.path.join(self.run_dir, "log.txt")

    def _events_path(self) -> str:
        return os.path.join(self.runs_dir, f"{self.run_id}.jsonl")

    def _last_event(self) -> dict | None:
        path = self._events_path()
        if not os.path.exists(path):
            return None
        last = None
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    last = json.loads(line)
                except json.JSONDecodeError:
                    continue
        return last

    def status(self) -> str:
        exit_code = self.process.poll()
        last_event = self._last_event()

        if exit_code is None:
            return "pending" if last_event is None else "running"

        if last_event is not None and last_event.get("event") == "run_failed":
            return "failed"
        return "done" if exit_code == 0 else "failed"

    def tail_log(self, n: int = 50) -> list[str]:
        path = self._log_path()
        if not os.path.exists(path):
            return []
        with open(path) as f:
            lines = f.readlines()
        return [line.rstrip("\n") for line in lines[-n:]]

    def kill(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()


class LocalRunner:
    def __init__(self, runs_dir: str | None = None):
        base = runs_dir or os.environ.get("CANVS_RUNS_DIR", "./canvs_runs")
        self.runs_dir = os.path.abspath(base)
        self._handles: dict[str, RunHandle] = {}

    def start(self, artifact) -> RunHandle:
        run_dir = os.path.join(self.runs_dir, artifact.run_id)
        os.makedirs(run_dir, exist_ok=True)

        script_path = os.path.join(run_dir, "pipeline.py")
        with open(script_path, "w") as f:
            f.write(artifact.content)

        log_path = os.path.join(run_dir, "log.txt")
        log_file = open(log_path, "w")

        env = dict(os.environ)
        env["CANVS_RUNS_DIR"] = self.runs_dir

        process = subprocess.Popen(
            [sys.executable, script_path],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=run_dir,
            env=env,
        )

        handle = RunHandle(artifact.run_id, run_dir, self.runs_dir, process)
        self._handles[artifact.run_id] = handle
        return handle

    def get(self, run_id: str) -> RunHandle | None:
        return self._handles.get(run_id)

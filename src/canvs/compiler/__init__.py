"""compile_graph(graph, target, run_id) -> CompiledArtifact."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from .notebook import compile_notebook
from .script import compile_script

Target = Literal["local", "kaggle", "colab"]


class CompiledArtifact(BaseModel):
    run_id: str
    target: Target
    filename: str
    content: str


def compile_graph(graph, target: Target, run_id: str, registry=None) -> CompiledArtifact:
    if registry is None:
        from ..registry import registry

    if target == "local":
        content = compile_script(graph, registry, run_id)
        filename = "pipeline.py"
    elif target in ("kaggle", "colab"):
        content = compile_notebook(graph, registry, run_id, target)
        filename = "pipeline.ipynb"
    else:
        raise ValueError(f"Unknown target: {target!r}")

    return CompiledArtifact(run_id=run_id, target=target, filename=filename, content=content)

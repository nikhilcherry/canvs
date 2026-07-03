"""Node registry: turns plain Python functions into canvas nodes.

@node introspects the function signature to split parameters into
scalar "config" params (rendered as forms by the frontend) and
non-scalar "data" params (rendered as input ports / edges). The
decorated function is registered in a module-level `registry`
singleton and returned unchanged.
"""
from __future__ import annotations

import importlib
import inspect
import textwrap
import types
import typing
from typing import Any, Callable, Literal, get_args, get_origin

from pydantic import BaseModel

_SCALAR_TYPES: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}

SPECIAL_PARAMS = ("_run_id", "_node_id")


def _snake_to_title(name: str) -> str:
    return " ".join(part.capitalize() for part in name.split("_"))


def _param_schema(annotation: Any) -> dict | None:
    """Return a JSON-schema-ish dict for scalar/Literal annotations, else None."""
    if annotation in _SCALAR_TYPES:
        return {"type": _SCALAR_TYPES[annotation]}
    if get_origin(annotation) is Literal:
        args = get_args(annotation)
        return {"type": "string", "enum": list(args)}
    return None


class NodeSpec(BaseModel):
    id: str
    category: str
    name: str
    description: str = ""
    params: dict[str, Any] = {}
    inputs: list[str] = []
    input_defaults: dict[str, Any] = {}
    outputs: list[str] = []
    source: str = ""
    requires: list[str] = []
    accepts_run_id: bool = False
    accepts_node_id: bool = False


def _strip_decorator(source: str) -> str:
    """Remove the leading @node(...) decorator line(s) from source text."""
    lines = source.splitlines()
    out = []
    in_decorator = False
    depth = 0
    for line in lines:
        stripped = line.strip()
        if not in_decorator and stripped.startswith("@node"):
            in_decorator = True
            depth = line.count("(") - line.count(")")
            if depth <= 0:
                in_decorator = False
            continue
        if in_decorator:
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                in_decorator = False
            continue
        out.append(line)
    return "\n".join(out).lstrip("\n") + "\n"


class Registry:
    def __init__(self) -> None:
        self._nodes: dict[str, NodeSpec] = {}
        self._funcs: dict[str, Callable] = {}

    def register(self, spec: NodeSpec, func: Callable) -> None:
        if spec.id in self._nodes:
            raise ValueError(f"Duplicate node id: {spec.id!r}")
        self._nodes[spec.id] = spec
        self._funcs[spec.id] = func

    def get(self, node_id: str) -> NodeSpec:
        return self._nodes[node_id]

    def get_func(self, node_id: str) -> Callable:
        return self._funcs[node_id]

    def __contains__(self, node_id: str) -> bool:
        return node_id in self._nodes

    def clear(self) -> None:
        self._nodes.clear()
        self._funcs.clear()

    def to_json(self) -> dict:
        categories = sorted({spec.category for spec in self._nodes.values()})
        return {
            "categories": categories,
            "nodes": [spec.model_dump() for spec in self._nodes.values()],
        }

    def load_module(self, path_or_module: str | types.ModuleType) -> types.ModuleType:
        if isinstance(path_or_module, types.ModuleType):
            return path_or_module
        return importlib.import_module(path_or_module)


registry = Registry()


def node(
    category: str,
    name: str | None = None,
    description: str = "",
    requires: list[str] | None = None,
):
    def decorator(func: Callable) -> Callable:
        sig = inspect.signature(func)
        node_name = name or _snake_to_title(func.__name__)
        node_id = f"{category}.{func.__name__}"

        params: dict[str, Any] = {}
        inputs: list[str] = []
        input_defaults: dict[str, Any] = {}
        accepts_run_id = False
        accepts_node_id = False

        for pname, p in sig.parameters.items():
            if pname == "_run_id":
                accepts_run_id = True
                continue
            if pname == "_node_id":
                accepts_node_id = True
                continue

            annotation = p.annotation
            schema = _param_schema(annotation)
            if schema is not None:
                if p.default is not inspect.Parameter.empty:
                    schema["default"] = p.default
                else:
                    schema["required"] = True
                params[pname] = schema
            else:
                inputs.append(pname)
                if p.default is not inspect.Parameter.empty:
                    input_defaults[pname] = p.default

        return_annotation = sig.return_annotation
        outputs = [] if return_annotation is inspect.Signature.empty else ["output"]

        try:
            raw_source = inspect.getsource(func)
        except OSError as exc:
            raise OSError(
                f"Could not read source for node {node_id!r}: nodes must be "
                "defined in importable .py files (not the stdin/REPL)."
            ) from exc
        dedented = textwrap.dedent(raw_source)
        source = _strip_decorator(dedented)

        spec = NodeSpec(
            id=node_id,
            category=category,
            name=node_name,
            description=description,
            params=params,
            inputs=inputs,
            input_defaults=input_defaults,
            outputs=outputs,
            source=source,
            requires=requires or [],
            accepts_run_id=accepts_run_id,
            accepts_node_id=accepts_node_id,
        )
        registry.register(spec, func)
        return func

    return decorator

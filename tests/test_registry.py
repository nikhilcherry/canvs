from typing import Literal

import pytest

from canvs.registry import node, registry


def test_scalar_and_data_param_split():
    @node(category="test", description="desc")
    def sample(
        data: list,
        count: int = 5,
        ratio: float = 0.5,
        flag: bool = True,
        mode: Literal["a", "b"] = "a",
    ) -> dict:
        return {}

    spec = registry.get("test.sample")
    assert spec.inputs == ["data"]
    assert spec.params["count"] == {"type": "integer", "default": 5}
    assert spec.params["ratio"] == {"type": "number", "default": 0.5}
    assert spec.params["flag"] == {"type": "boolean", "default": True}
    assert spec.params["mode"] == {"type": "string", "enum": ["a", "b"], "default": "a"}
    assert spec.outputs == ["output"]


def test_required_param_without_default():
    @node(category="test")
    def sample(x: int) -> int:
        return x

    spec = registry.get("test.sample")
    assert spec.params["x"] == {"type": "integer", "required": True}


def test_data_input_with_default_recorded():
    @node(category="test")
    def sample(model: dict = None) -> dict:
        return model

    spec = registry.get("test.sample")
    assert spec.inputs == ["model"]
    assert spec.input_defaults == {"model": None}


def test_name_derivation_snake_to_title():
    @node(category="test")
    def my_cool_node() -> int:
        return 1

    spec = registry.get("test.my_cool_node")
    assert spec.name == "My Cool Node"


def test_explicit_name_and_id():
    @node(category="test", name="Custom Name")
    def foo() -> int:
        return 1

    spec = registry.get("test.foo")
    assert spec.id == "test.foo"
    assert spec.name == "Custom Name"


def test_duplicate_id_raises():
    @node(category="test")
    def dup() -> int:
        return 1

    with pytest.raises(ValueError):

        @node(category="test")
        def dup() -> int:  # noqa: F811
            return 2


def test_source_strips_decorator_and_dedents():
    @node(category="test", description="x")
    def sourced(x: int = 1) -> int:
        return x + 1

    spec = registry.get("test.sourced")
    assert "@node" not in spec.source
    assert spec.source.startswith("def sourced")


def test_to_json_structure():
    @node(category="alpha")
    def a() -> int:
        return 1

    @node(category="beta")
    def b() -> int:
        return 2

    data = registry.to_json()
    assert set(data["categories"]) == {"alpha", "beta"}
    ids = {n["id"] for n in data["nodes"]}
    assert ids == {"alpha.a", "beta.b"}


def test_special_params_excluded_from_params_and_inputs():
    @node(category="test")
    def special(x: int = 1, _run_id: str = "", _node_id: str = "") -> int:
        return x

    spec = registry.get("test.special")
    assert "_run_id" not in spec.params
    assert "_node_id" not in spec.params
    assert "_run_id" not in spec.inputs
    assert "_node_id" not in spec.inputs
    assert spec.accepts_run_id is True
    assert spec.accepts_node_id is True


def test_requires_captured():
    @node(category="test", requires=["numpy", "pandas"])
    def needs_deps() -> int:
        return 1

    spec = registry.get("test.needs_deps")
    assert spec.requires == ["numpy", "pandas"]


def test_decorated_function_still_plain_callable():
    @node(category="test")
    def add_one(x: int = 1) -> int:
        return x + 1

    assert add_one(4) == 5


def test_getsource_failure_raises_helpful_message(monkeypatch):
    import inspect as inspect_module

    def fake_getsource(func):
        raise OSError("could not find source code")

    monkeypatch.setattr(inspect_module, "getsource", fake_getsource)

    with pytest.raises(OSError, match="importable .py files"):

        @node(category="test")
        def sample() -> int:
            return 1

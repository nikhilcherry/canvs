"""Stdlib-only toy pipeline proving the canvs execution loop end to end.

Each node function keeps its imports local to its own body (rather
than at module scope) because the compiler embeds only the function's
extracted source into compiled artifacts — a module-level import here
would silently vanish from the compiled script.
"""
from typing import Literal

from canvs import node


@node(category="data", name="Make Numbers", description="Generate random floats")
def make_numbers(n: int = 100, seed: int = 42) -> list:
    import random

    rng = random.Random(seed)
    return [rng.uniform(0.0, 100.0) for _ in range(n)]


@node(category="preprocess", name="Normalize", description="Scale values to [0, 1] or z-score")
def normalize(data: list, method: Literal["minmax", "zscore"] = "minmax") -> list:
    if method == "minmax":
        lo, hi = min(data), max(data)
        span = (hi - lo) or 1.0
        return [(x - lo) / span for x in data]
    mean = sum(data) / len(data)
    variance = sum((x - mean) ** 2 for x in data) / len(data)
    std = (variance ** 0.5) or 1.0
    return [(x - mean) / std for x in data]


@node(category="train", name="Fake Train", description="Fake training loop that reports metrics")
def fake_train(
    data: list,
    epochs: int = 5,
    lr: float = 0.1,
    _run_id: str = "",
    _node_id: str = "",
) -> dict:
    import time

    report_metric = globals().get("canvs_metric")

    loss = 1.0
    for epoch in range(epochs):
        loss = loss * (1.0 - lr) + 0.01
        accuracy = max(0.0, 1.0 - loss)
        if report_metric is not None:
            report_metric(_run_id, _node_id, step=epoch, loss=loss, acc=accuracy)
        time.sleep(0.5)

    return {"loss": loss, "accuracy": max(0.0, 1.0 - loss), "epochs": epochs}


@node(category="eval", name="Summarize", description="Summarize final training metrics")
def summarize(model: dict) -> dict:
    return {"final_loss": model["loss"], "final_accuracy": model["accuracy"]}

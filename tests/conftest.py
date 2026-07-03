import pytest

from canvs.registry import registry


@pytest.fixture(autouse=True)
def _clear_registry():
    registry.clear()
    yield
    registry.clear()

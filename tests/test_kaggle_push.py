import json
import os
from types import SimpleNamespace

from canvs import kaggle_push


class FakeApi:
    def __init__(self, username="alice"):
        self.config_values = {"username": username}
        self.last_metadata = None
        self.pushed_folders = []

    def kernels_push_cli(self, folder):
        self.pushed_folders.append(folder)
        with open(os.path.join(folder, "kernel-metadata.json")) as f:
            self.last_metadata = json.load(f)


def test_push_kernel_writes_expected_metadata(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(kaggle_push, "_get_api", lambda: fake)

    artifact = SimpleNamespace(run_id="0123456789ab", filename="pipeline.ipynb", content="{}")
    ref = kaggle_push.push_kernel(
        artifact, title="My Pipeline!", dataset_slugs=["user/ds"], gpu=True, private=True
    )

    assert ref["kernel_slug"] == "alice/my-pipeline-01234567"
    assert ref["url"] == "https://www.kaggle.com/code/alice/my-pipeline-01234567"
    assert fake.last_metadata == {
        "id": "alice/my-pipeline-01234567",
        "title": "My Pipeline!",
        "code_file": "pipeline.ipynb",
        "language": "python",
        "kernel_type": "notebook",
        "is_private": True,
        "enable_gpu": True,
        "enable_internet": True,
        "dataset_sources": ["user/ds"],
        "competition_sources": [],
        "kernel_sources": [],
        "model_sources": [],
    }


def test_push_kernel_slug_unique_per_run_id(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(kaggle_push, "_get_api", lambda: fake)

    artifact1 = SimpleNamespace(run_id="0123456789ab", filename="pipeline.ipynb", content="{}")
    artifact2 = SimpleNamespace(run_id="ffffeeeeddd0", filename="pipeline.ipynb", content="{}")

    ref1 = kaggle_push.push_kernel(artifact1, title="My Pipeline!", dataset_slugs=[], gpu=False)
    ref2 = kaggle_push.push_kernel(artifact2, title="My Pipeline!", dataset_slugs=[], gpu=False)

    assert ref1["kernel_slug"] == "alice/my-pipeline-01234567"
    assert ref2["kernel_slug"] == "alice/my-pipeline-ffffeeee"
    assert ref1["kernel_slug"] != ref2["kernel_slug"]


def test_kernel_status_normalizes_kaggle_values(monkeypatch):
    class FakeResponse:
        def __init__(self, status):
            self.status = status

    class FakeStatusApi:
        def __init__(self, status):
            self._status = status

        def kernels_status_cli(self, kernel_slug):
            return FakeResponse(self._status)

    for raw, expected in [
        ("queued", "running"),
        ("running", "running"),
        ("complete", "done"),
        ("error", "failed"),
        ("cancelled", "failed"),
    ]:
        monkeypatch.setattr(kaggle_push, "_get_api", lambda raw=raw: FakeStatusApi(raw))
        assert kaggle_push.kernel_status("alice/slug") == {"status": expected}


def test_is_available_false_when_kaggle_package_missing():
    # This sandbox has no `kaggle` package installed -- exercises the real
    # ImportError path rather than a mock.
    available, reason = kaggle_push.is_available()
    assert available is False
    assert "kaggle package not installed" in reason

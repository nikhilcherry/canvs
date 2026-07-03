import json
import os
import sys
from types import SimpleNamespace

import pytest

from canvs import kaggle_push


class FakeResult:
    def __init__(self, ref, url, error=None):
        self.ref = ref
        self.url = url
        self.error = error


class FakeApi:
    def __init__(self, username="alice", error=None):
        self.config_values = {"username": username}
        self.last_metadata = None
        self.pushed_folders = []
        self.last_timeout = "unset"
        self.last_acc = "unset"
        self._error = error

    def kernels_push(self, folder, timeout, acc):
        self.pushed_folders.append(folder)
        self.last_timeout = timeout
        self.last_acc = acc
        with open(os.path.join(folder, "kernel-metadata.json")) as f:
            self.last_metadata = json.load(f)
        if self._error:
            return FakeResult(ref=None, url=None, error=self._error)
        # Mirrors the real API: ref/url are derived from the metadata id,
        # which push_kernel constructs so title and id always agree.
        slug = self.last_metadata["id"]
        return FakeResult(ref=f"/code/{slug}", url=f"https://www.kaggle.com/code/{slug}")


def test_push_kernel_writes_expected_metadata(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(kaggle_push, "_get_api", lambda: fake)

    artifact = SimpleNamespace(run_id="0123456789ab", filename="pipeline.ipynb", content="{}")
    ref = kaggle_push.push_kernel(
        artifact, title="My Pipeline!", dataset_slugs=["user/ds"], gpu=True, private=True
    )

    assert ref["kernel_slug"] == "alice/my-pipeline-01234567"
    assert ref["url"] == "https://www.kaggle.com/code/alice/my-pipeline-01234567"
    assert fake.last_timeout is None
    assert fake.last_acc is None
    assert fake.last_metadata == {
        "id": "alice/my-pipeline-01234567",
        "title": "My Pipeline!-01234567",
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


def test_push_kernel_trusts_api_ref_over_local_guess(monkeypatch):
    # Kaggle derives the real slug from title server-side and can diverge
    # from whatever we compute locally (this is what broke the live smoke
    # test: kernel_status polling used a locally-guessed slug that Kaggle
    # never actually created).
    fake = FakeApi()
    monkeypatch.setattr(kaggle_push, "_get_api", lambda: fake)
    monkeypatch.setattr(
        fake,
        "kernels_push",
        lambda folder, timeout, acc: FakeResult(
            ref="/code/alice/some-other-slug", url="https://www.kaggle.com/code/alice/some-other-slug"
        ),
    )

    artifact = SimpleNamespace(run_id="0123456789ab", filename="pipeline.ipynb", content="{}")
    ref = kaggle_push.push_kernel(artifact, title="My Pipeline!", dataset_slugs=[], gpu=False)

    assert ref["kernel_slug"] == "alice/some-other-slug"
    assert ref["url"] == "https://www.kaggle.com/code/alice/some-other-slug"


def test_push_kernel_raises_on_api_error(monkeypatch):
    fake = FakeApi(error="Title must be at least five characters")
    monkeypatch.setattr(kaggle_push, "_get_api", lambda: fake)

    artifact = SimpleNamespace(run_id="0123456789ab", filename="pipeline.ipynb", content="{}")
    with pytest.raises(RuntimeError, match="Title must be at least five characters"):
        kaggle_push.push_kernel(artifact, title="hi", dataset_slugs=[], gpu=False)


def test_kernel_status_normalizes_kaggle_values(monkeypatch):
    # The real kernels_status() response's .status is a KernelWorkerStatus
    # enum member (e.g. KernelWorkerStatus.ERROR), not a plain string --
    # the fake mirrors that shape via a .name attribute so a regression to
    # naive string comparison would fail this test.
    class FakeEnumStatus:
        def __init__(self, name):
            self.name = name

    class FakeResponse:
        def __init__(self, status_name):
            self.status = FakeEnumStatus(status_name)

    class FakeStatusApi:
        def __init__(self, status_name):
            self._status_name = status_name

        def kernels_status(self, kernel_slug):
            return FakeResponse(self._status_name)

    for raw, expected in [
        ("QUEUED", "running"),
        ("RUNNING", "running"),
        ("COMPLETE", "done"),
        ("ERROR", "failed"),
        ("CANCEL_REQUESTED", "failed"),
        ("CANCEL_ACKNOWLEDGED", "failed"),
    ]:
        monkeypatch.setattr(kaggle_push, "_get_api", lambda raw=raw: FakeStatusApi(raw))
        assert kaggle_push.kernel_status("alice/slug") == {"status": expected}


def test_is_available_false_when_kaggle_package_missing(monkeypatch):
    # Force the import to fail regardless of whether `kaggle` happens to be
    # installed in the environment running this test.
    monkeypatch.setitem(sys.modules, "kaggle.api.kaggle_api_extended", None)
    available, reason = kaggle_push.is_available()
    assert available is False
    assert "kaggle package not installed" in reason

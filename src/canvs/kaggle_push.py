"""One-click Kaggle push: compiles + pushes a notebook via the `kaggle`
pip package's KaggleApi.

The `kaggle` package is an optional dependency (`pip install "canvs[kaggle]"`)
and is imported lazily so canvs works without it installed. Note a real
quirk of that package: merely `import kaggle` eagerly authenticates and
raises if credentials are missing/invalid, not just on API calls -- so
`is_available()` treats any exception from the import, not only
ImportError, as "not available" with a reason.
"""
from __future__ import annotations

import json
import os
import re
import tempfile

_STATUS_MAP = {
    "queued": "running",
    "running": "running",
    "complete": "done",
    "error": "failed",
    "cancelled": "failed",
}


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "pipeline"


def is_available() -> tuple[bool, str | None]:
    """Whether a Kaggle push can be attempted right now: (available, reason)."""
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi

        KaggleApi().authenticate()
    except ImportError:
        return False, "kaggle package not installed"
    except Exception as e:
        return False, f"kaggle credentials not usable: {e}"
    return True, None


def _get_api():
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    return api


def _username(api) -> str:
    username = getattr(api, "config_values", {}).get("username")
    if not username:
        raise RuntimeError("Kaggle username not resolved from credentials")
    return username


def push_kernel(
    artifact,
    *,
    title: str,
    dataset_slugs: list[str],
    gpu: bool,
    private: bool = True,
) -> dict:
    """Push a compiled notebook artifact as a Kaggle kernel.

    Returns {"kernel_slug": "user/slug", "url": "..."}. The run_id
    suffix on the slug guarantees uniqueness across repeated pushes of
    the same title.
    """
    api = _get_api()
    username = _username(api)
    kernel_slug = f"{username}/{_slugify(title)}-{artifact.run_id[:8]}"

    with tempfile.TemporaryDirectory() as tmp_dir:
        with open(os.path.join(tmp_dir, artifact.filename), "w") as f:
            f.write(artifact.content)

        metadata = {
            "id": kernel_slug,
            "title": title,
            "code_file": artifact.filename,
            "language": "python",
            "kernel_type": "notebook",
            "is_private": private,
            "enable_gpu": gpu,
            "enable_internet": True,
            "dataset_sources": dataset_slugs,
            "competition_sources": [],
            "kernel_sources": [],
            "model_sources": [],
        }
        with open(os.path.join(tmp_dir, "kernel-metadata.json"), "w") as f:
            json.dump(metadata, f)

        api.kernels_push_cli(tmp_dir)

    return {"kernel_slug": kernel_slug, "url": f"https://www.kaggle.com/code/{kernel_slug}"}


def kernel_status(kernel_slug: str) -> dict:
    """Normalize the Kaggle kernel status API to canvs's running/done/failed."""
    api = _get_api()
    response = api.kernels_status_cli(kernel_slug)
    raw_status = getattr(response, "status", None)
    if raw_status is None and isinstance(response, dict):
        raw_status = response.get("status")
    return {"status": _STATUS_MAP.get(raw_status, "running")}

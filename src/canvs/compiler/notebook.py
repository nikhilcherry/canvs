"""target="kaggle" | "colab" compiler: produces a self-contained .ipynb."""
from __future__ import annotations

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

from . import templates

KAGGLE_DATASET_NOTE = (
    "**Note:** this notebook expects the pipeline's input dataset to be "
    "attached at `/kaggle/input/`."
)


def compile_notebook(graph, registry, run_id: str, target: str, env_vars: dict[str, str] | None = None) -> str:
    used_specs = sorted({n.spec for n in graph.nodes})

    pip_packages = {"supabase"}
    for spec_id in used_specs:
        pip_packages.update(registry.get(spec_id).requires)
    pip_line = "!pip install -q " + " ".join(sorted(pip_packages))

    header_cell_source = (
        templates.render_future_import()
        + "\n"
        + pip_line
        + "\n\n"
        + templates.render_header(run_id, target)
    )

    cells = []
    if target == "kaggle":
        cells.append(new_markdown_cell(KAGGLE_DATASET_NOTE))
    if env_vars:
        cells.append(new_code_cell(templates.render_env_cell(env_vars)))

    cells.append(new_code_cell(header_cell_source))
    for spec_id in used_specs:
        cells.append(new_code_cell(templates.render_node_block(registry.get(spec_id))))
    cells.append(new_code_cell(templates.render_execution_block(graph, registry)))
    cells.append(new_code_cell(templates.render_footer()))

    # Kaggle executes pushed notebooks with papermill, which resolves the
    # kernel to run via nb.metadata.kernelspec.name -- without it papermill
    # raises "No kernel name found in notebook" and the kernel run errors
    # out immediately, before any cell executes.
    metadata = {
        "kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
        "language_info": {"name": "python"},
    }
    nb = new_notebook(cells=cells, metadata=metadata)
    return nbformat.writes(nb)

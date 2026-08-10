"""Verify graph entries with the same import modes used by Agent Server."""

import importlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_registered_graphs_load_as_runtime_entrypoints() -> None:
    config = json.loads((ROOT / "langgraph.json").read_text(encoding="utf-8"))

    for graph_id, entrypoint in config["graphs"].items():
        source, variable = entrypoint.rsplit(":", maxsplit=1)
        if "/" in source:
            path = (ROOT / source).resolve()
            spec = importlib.util.spec_from_file_location(
                f"_langgraph_contract_{graph_id}", path
            )
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        else:
            module = importlib.import_module(source)

        assert getattr(module, variable) is not None

"""File-registered graphs must load without a package context, as Agent Server does."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("graph_id", "version_key"),
    [
        ("ax768_information_extraction", "extraction_version"),
        ("ax768_information_update", "information_version"),
    ],
)
def test_information_graph_file_registration(graph_id, version_key, monkeypatch):
    graphs = json.loads((ROOT / "langgraph.json").read_text())["graphs"]
    path, variable = graphs[graph_id].rsplit(":", 1)
    # LangGraph API gives file entrypoints a synthetic, non-package module name.
    name = path.replace("/", "__").replace(".py", "").replace(" ", "_").lstrip(".")
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    graph = getattr(module, variable)
    schema = graph.get_input_jsonschema()
    assert schema["properties"][version_key]["const"] == (
        "2" if graph_id == "ax768_information_update" else "1"
    )
    assert graph.get_output_jsonschema()["properties"]["status"]


def test_information_input_no_longer_requires_region():
    from workflows.ax768.information_update import graph

    assert "region" not in graph.get_input_jsonschema()["properties"]

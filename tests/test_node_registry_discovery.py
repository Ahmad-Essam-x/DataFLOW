"""Node discovery must not depend on scanning .py files (PyInstaller bundles modules in an archive)."""
import importlib
import os
import pkgutil

from backend.engine.nodes import registry
from backend.engine.nodes.registry import NODE_MODULES, NODE_REGISTRY


def test_node_modules_list_matches_the_package():
    on_disk = {m.name for m in pkgutil.iter_modules(importlib.import_module("backend.engine.nodes").__path__)}
    on_disk -= {"base", "registry"}
    assert on_disk == set(NODE_MODULES), "add the new node module to NODE_MODULES in registry.py"


def test_discovery_works_with_no_py_files_to_scan(monkeypatch):
    """Frozen apps have no nodes/*.py on disk: the explicit list alone must yield the full registry."""
    monkeypatch.setattr(registry.pkgutil, "iter_modules", lambda *_a, **_k: iter(()))
    monkeypatch.setattr(registry, "Path", None, raising=False)
    assert registry._discover_nodes().keys() == NODE_REGISTRY.keys()


def test_core_tools_are_registered():
    for t in ("input_data", "output_data", "select", "filter", "formula", "join", "summarize", "schema_fit",
              "llm_override", "llm_process", "unsupported_tool", "running_total", "dynamic_rename"):
        assert t in NODE_REGISTRY, t


def test_discovery_does_not_use_filesystem_globbing():
    src = open(registry.__file__, encoding="utf-8").read()
    assert ".glob(" not in src and "listdir" not in src and "os.walk" not in src

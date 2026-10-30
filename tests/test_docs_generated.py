"""Generated documentation must match the code. Regenerate with the scripts named in the failure message."""
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _check(script):
    return subprocess.run([sys.executable, os.path.join(REPO, "scripts", script), "--check"],
                          cwd=REPO, capture_output=True, text=True)


def test_tool_reference_is_current():
    r = _check("generate_tool_reference.py")
    assert r.returncode == 0, r.stdout + r.stderr


def test_compatibility_page_is_current():
    r = _check("generate_compatibility.py")
    assert r.returncode == 0, r.stdout + r.stderr


def test_every_palette_tool_has_reference_notes():
    sys.path.insert(0, REPO)
    from backend.engine.nodes.registry import TOOL_METADATA, NODE_REGISTRY
    from scripts.generate_tool_reference import NOTES
    assert not {m["type"] for m in TOOL_METADATA} - set(NOTES)
    assert not set(NODE_REGISTRY) - set(NOTES)


def test_compatibility_page_does_not_claim_verified_results():
    text = open(os.path.join(REPO, "docs", "ALTERYX_COMPATIBILITY.md"), encoding="utf-8").read()
    assert "(verified)" not in text, "only mark cases verified after comparing with a real Alteryx run"
    assert "not** Alteryx" in text.replace("is **not**", "not**") or "It is **not** Alteryx" in text

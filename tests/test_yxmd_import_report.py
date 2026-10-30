"""Alteryx import: every bundled fixture parses, unsupported tools are reported (not hidden), and the user is told."""
import glob
import os

import pytest

from backend.engine.alteryx.yxmd_parser import parse_yxmd_file

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "alteryx")
ALL = sorted(glob.glob(os.path.join(FIXTURES, "*.yxmd")))

# Fixtures that deliberately contain tools DataFlow cannot run, with the exact tools expected as placeholders.
KNOWN_UNSUPPORTED = {
    "challenge_15_atcodedog05_Solution.yxmd": {"CreatePoints": 2, "FindNearest": 1},
}


def test_fixtures_exist():
    assert len(ALL) >= 28


@pytest.mark.parametrize("path", ALL, ids=[os.path.basename(p) for p in ALL])
def test_fixture_parses_and_placeholders_are_exactly_the_known_ones(path):
    res = parse_yxmd_file(path)
    assert isinstance(res.workflow["nodes"], list) and isinstance(res.workflow["connections"], list)
    found = {}
    for t in res.to_dict()["stats"]["substituted_tools"]:
        found[t["tool"]] = found.get(t["tool"], 0) + 1
    assert found == KNOWN_UNSUPPORTED.get(os.path.basename(path), {}), \
        "an unexpected tool became a placeholder (or a known one is now supported: update KNOWN_UNSUPPORTED)"
    assert res.fallback_tools == sum(found.values())


def test_substituted_tools_report_is_in_stats_and_warnings_are_not_info():
    res = parse_yxmd_file(os.path.join(FIXTURES, "challenge_15_atcodedog05_Solution.yxmd"))
    stats = res.to_dict()["stats"]
    assert [t["tool"] for t in stats["substituted_tools"]].count("CreatePoints") == 2
    assert all({"node_id", "tool_id", "tool"} <= set(t) for t in stats["substituted_tools"])
    placeholder_warnings = [w for w in res.warnings if "placeholder" in w.message]
    assert len(placeholder_warnings) == 3
    assert all(w.severity == "warning" for w in placeholder_warnings)
    assert all("results may differ from Alteryx" in w.message for w in placeholder_warnings)


def test_clean_import_has_empty_report():
    res = parse_yxmd_file(os.path.join(FIXTURES, "018 Join.yxmd"))
    assert res.to_dict()["stats"]["substituted_tools"] == []


def test_import_endpoint_returns_the_report():
    from backend.app import app
    xml = open(os.path.join(FIXTURES, "challenge_15_atcodedog05_Solution.yxmd"), encoding="utf-8").read()
    r = app.test_client().post("/api/workflow/import-yxmd", json={"xml": xml, "filename": "challenge15.yxmd"})
    body = r.get_json()
    assert r.status_code == 200 and body["success"] is True
    assert {t["tool"] for t in body["stats"]["substituted_tools"]} == {"CreatePoints", "FindNearest"}


def test_ui_shows_a_persistent_warning_for_placeholders():
    js = open(os.path.join(os.path.dirname(FIXTURES), "..", "..", "static", "js", "workflow_io.js"), encoding="utf-8").read()
    assert "substituted_tools" in js and "showToast('warning'" in js and "Results may differ from Alteryx" in js

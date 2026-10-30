"""Runs every golden case through the real node implementation."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import runner  # noqa: E402

CASES = runner.load_cases()


def test_there_are_golden_cases_for_the_core_tools():
    covered = {c["tool"] for c in CASES}
    core = {"join", "filter", "sort", "unique", "summarize", "select", "union", "formula", "crosstab", "transpose"}
    assert core <= covered, f"missing golden cases for: {sorted(core - covered)}"


def test_every_case_declares_provenance_and_source():
    for c in CASES:
        assert c.get("provenance") in ("derived", "verified"), c["_file"]
        assert c.get("source"), f"{c['_file']}: say why this output is the expected one"


@pytest.mark.parametrize("case", CASES, ids=[c["_file"][:-5] for c in CASES])
def test_golden_case(case):
    outputs = runner.run_case(case)
    problems = runner.compare(case, outputs)
    assert not problems, f"{case['name']}: " + "; ".join(problems)

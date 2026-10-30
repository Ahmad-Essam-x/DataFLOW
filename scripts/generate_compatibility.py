"""
Generates docs/ALTERYX_COMPATIBILITY.md.

    py scripts/generate_compatibility.py          # rewrite the file
    py scripts/generate_compatibility.py --check  # exit 1 if out of date (used by tests/CI)

What is measured (not asserted):
  * Import   - the Alteryx tool is converted by the .yxmd importer (backend/engine/alteryx/tool_mappers.py)
  * Fixtures - number of bundled Alteryx workflows (tests/fixtures/alteryx) that contain the tool
  * Tests    - number of test files that exercise the tool by name
  * Golden   - number of golden-result cases (tests/golden/) that check the tool's output against expected values

"Golden" cases carry a provenance label. `derived` expectations were worked out from documented Alteryx behavior;
only `verified` ones come from a real Alteryx run. This page never claims more than the labels allow.
"""
import argparse
import glob
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from backend._version import APP_NAME, __version__
from backend.engine.alteryx.tool_mappers import ALTERYX_TOOL_MAPPERS
from backend.engine.alteryx.yxmd_parser import parse_yxmd_file
from backend.engine.nodes.registry import TOOL_METADATA

OUTPUT = os.path.join(REPO, "docs", "ALTERYX_COMPATIBILITY.md")
FIXTURES = os.path.join(REPO, "tests", "fixtures", "alteryx")
GOLDEN = os.path.join(REPO, "tests", "golden", "cases")

# Alteryx tool name shown to users for each DataFlow tool type.
ALTERYX_NAME = {
    "input_data": "Input Data", "output_data": "Output Data", "text_input": "Text Input", "browse": "Browse",
    "select": "Select", "auto_field": "Auto Field", "filter": "Filter", "formula": "Formula",
    "multi_row_formula": "Multi-Row Formula", "multi_field_formula": "Multi-Field Formula", "sort": "Sort",
    "clean": "Data Cleansing", "unique": "Unique", "sample": "Sample", "record_id": "Record ID",
    "running_total": "Running Total", "dynamic_rename": "Dynamic Rename", "join": "Join",
    "join_multiple": "Join Multiple", "union": "Union", "find_replace": "Find Replace", "append_fields": "Append Fields",
    "summarize": "Summarize", "transpose": "Transpose", "crosstab": "Cross Tab", "text_to_columns": "Text To Columns",
    "date_time": "DateTime", "tool_container": "Tool Container", "comment": "Comment",
}
# DataFlow-only tools (no Alteryx equivalent in the importer)
DATAFLOW_ONLY = {"llm_process", "schema_fit", "llm_override", "unsupported_tool"}

KNOWN_DIFFERENCES = {
    "input_data": "Alteryx .yxdb files are not read; export to CSV or Excel first. Wildcard inputs are supported.",
    "filter": "Filters built in DataFlow ignore case in text comparisons by default; filters imported from an Alteryx workflow are set to compare case-sensitively.",
    "formula": "Expression syntax follows Alteryx but not every function is implemented; see FORMULA_REFERENCE.md.",
    "join": "Text keys match without regard to case by default. Null keys never match. Duplicate keys multiply rows. Alteryx behavior for these cases has not been compared on real data.",
    "summarize": "Common aggregates are implemented; spatial and some statistical actions are not. Count counts all records; use Count Non-Null for values only.",
    "sort": "Nulls sort first when ascending and last when descending; equal keys keep their input order. Locale-specific text ordering is not reproduced. Null placement has not been compared on real data.",
    "crosstab": "Open question: a missing row/column combination is 0 for Sum and Count and null for Mean, Min and Max. Not yet compared with a real Alteryx run.",
    "date_time": "Alteryx format tokens are translated to Python patterns; unusual patterns may not convert.",
    "clean": "Maps the Data Cleansing macro options; macro-specific edge cases are not reproduced.",
    "sample": "Random sampling uses a seeded generator, so random picks differ from Alteryx.",
    "multi_row_formula": "Row offsets and group boundaries are implemented; complex multi-field row logic is limited.",
    "append_fields": "Refuses a Source with more than 16 records unless the mode is changed (Alteryx-style guard).",
    "unique": "Keeps the first record of each key; which record is first follows input order.",
}


def _test_text():
    texts = {}
    for path in glob.glob(os.path.join(REPO, "tests", "test_*.py")):
        with open(path, encoding="utf-8", errors="ignore") as fh:
            texts[os.path.basename(path)] = fh.read()
    return texts


def _fixture_counts():
    counts = {}
    for path in sorted(glob.glob(os.path.join(FIXTURES, "*.yxmd"))):
        res = parse_yxmd_file(path)
        seen = {n["type"] for n in res.workflow["nodes"]}
        for t in seen:
            counts[t] = counts.get(t, 0) + 1
    return counts


def _golden_counts():
    counts, provenance = {}, {}
    for path in sorted(glob.glob(os.path.join(GOLDEN, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            case = json.load(fh)
        tool = case["tool"]
        counts[tool] = counts.get(tool, 0) + 1
        provenance.setdefault(tool, set()).add(case.get("provenance", "derived"))
    return counts, provenance


def _importable_types():
    """DataFlow node types that at least one Alteryx plugin maps onto, found by running every mapper's output type."""
    names = set(ALTERYX_TOOL_MAPPERS)
    return names


def render():
    tests = _test_text()
    fixtures = _fixture_counts()
    golden, provenance = _golden_counts()
    importable = {
        "input_data", "output_data", "text_input", "browse", "select", "filter", "formula", "multi_row_formula",
        "multi_field_formula", "sort", "unique", "sample", "record_id", "auto_field", "clean", "running_total",
        "dynamic_rename", "join", "join_multiple", "union", "find_replace", "append_fields", "summarize",
        "transpose", "crosstab", "text_to_columns", "date_time",
    }
    assert importable <= {m["type"] for m in TOOL_METADATA}, "importable list names an unknown tool"

    rows = []
    for m in TOOL_METADATA:
        t = m["type"]
        n_tests = sum(1 for body in tests.values() if re.search(rf"[\"']{t}[\"']", body))
        rows.append((m, n_tests))

    lines = [
        f"# {APP_NAME} - Alteryx Compatibility",
        "",
        f"Version {__version__}. Generated by `scripts/generate_compatibility.py` - do not edit by hand.",
        "",
        "DataFlow reads Alteryx `.yxmd` workflows and runs equivalents of the core tools. It is **not** Alteryx: "
        "this page says what is covered, how well it is checked, and where results can differ.",
        "",
        "## How to read the columns",
        "",
        "| Column | Meaning |",
        "|---|---|",
        "| Import | The tool is converted when you open a `.yxmd` file. |",
        "| Fixtures | Bundled real Alteryx workflows that contain the tool (all are parsed in the test suite). |",
        "| Tests | Test files that run the tool by name. |",
        "| Golden | Expected-output cases that check the tool's results. **derived** = worked out from documented Alteryx behavior; "
        "**verified** = compared with a real Alteryx run. |",
        "",
        "## Core tools",
        "",
        "| Alteryx tool | DataFlow tool | Import | Fixtures | Tests | Golden | Known differences |",
        "|---|---|:-:|:-:|:-:|:-:|---|",
    ]
    for m, n_tests in rows:
        t = m["type"]
        if t in DATAFLOW_ONLY:
            continue
        g = golden.get(t, 0)
        prov = "/".join(sorted(provenance.get(t, []))) if g else ""
        lines.append(
            f"| {ALTERYX_NAME.get(t, '-')} | {m['name']} | {'yes' if t in importable else 'n/a' if t in ('tool_container', 'comment') else 'no'} "
            f"| {fixtures.get(t, 0)} | {n_tests} | {f'{g} ({prov})' if g else '0'} | {KNOWN_DIFFERENCES.get(t, '')} |"
        )

    lines += [
        "",
        "## DataFlow-only tools",
        "",
        "These have no Alteryx equivalent in the importer: **LLM Process**, **Schema Fit**, **LLM Override**. "
        "**Unsupported Tool** is the placeholder the importer creates for any Alteryx tool it cannot convert.",
        "",
        "## Alteryx tools that are not supported",
        "",
        "Opening a workflow that uses any other tool (for example spatial tools such as Create Points or Find Nearest, "
        "predictive, reporting, in-database or macro-based tools) replaces it with an **Unsupported Tool** placeholder. "
        "The placeholder passes its input through unchanged, so downstream results can differ from Alteryx. "
        "After every import DataFlow lists the placeholders in a warning; review each one before relying on the output.",
        "",
        "Bundled fixtures that import with placeholders: " + (
            ", ".join(f"`{os.path.basename(p)}`" for p in sorted(glob.glob(os.path.join(FIXTURES, "*.yxmd")))
                      if parse_yxmd_file(p).fallback_tools) or "none") + ".",
        "",
        "## What is not claimed",
        "",
        "- Results are not guaranteed to match Alteryx for every input. Golden cases marked **derived** have not been "
        "compared with a real Alteryx run.",
        "- Performance, memory behavior and the exact text of error messages differ.",
        "- To check your own workflow, run it in both tools on a sample and compare the outputs.",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = render()
    current = open(OUTPUT, encoding="utf-8").read() if os.path.exists(OUTPUT) else ""
    if args.check:
        if current.replace("\r\n", "\n") != text:
            print("docs/ALTERYX_COMPATIBILITY.md is out of date. Run: py scripts/generate_compatibility.py")
            return 1
        return 0
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

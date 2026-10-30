"""Golden-result harness: small inputs, a tool config, and the exact output the tool must produce.

A case is a JSON file in tests/golden/cases/:
{
  "name": "join duplicate keys multiply rows",
  "tool": "join",
  "provenance": "derived" | "verified",     # verified = compared with a real Alteryx run
  "source": "why this is the expected behavior (Alteryx docs section, or the export it came from)",
  "config": {...},
  "inputs": {"L": {"columns": [...], "rows": [[...], ...]}, "R": {...}},
  "expect": {"J": {"columns": [...], "rows": [[...], ...]}, "L": {...}}   # only the listed outputs are checked
  "ordered": true | false                   # compare rows in order (default true)
}
Cell values: numbers, strings, booleans and null. Floats compare with a small tolerance.
"""
import json
import math
import os

import pandas as pd

from backend.engine.nodes.registry import NODE_REGISTRY

CASES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases")


def load_cases():
    cases = []
    for name in sorted(os.listdir(CASES_DIR)):
        if name.endswith(".json"):
            with open(os.path.join(CASES_DIR, name), encoding="utf-8") as fh:
                case = json.load(fh)
            case["_file"] = name
            cases.append(case)
    return cases


def frame(spec):
    return pd.DataFrame(spec["rows"], columns=spec["columns"])


def _norm(v):
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT or (not isinstance(v, (list, str)) and pd.isna(v)):
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def rows_of(df):
    return [[_norm(v) for v in row] for row in df.itertuples(index=False, name=None)]


def run_case(case):
    node = NODE_REGISTRY[case["tool"]](f"golden_{case['_file']}", case.get("config", {}))
    inputs = {port: frame(spec) for port, spec in case.get("inputs", {}).items()}
    outputs = node.execute(inputs, {})
    return outputs


def compare(case, outputs):
    problems = []
    for port, want in case["expect"].items():
        if port not in outputs:
            problems.append(f"missing output port {port!r} (got {sorted(outputs)})")
            continue
        got = outputs[port]
        if want.get("columns") is not None and list(got.columns) != want["columns"]:
            problems.append(f"{port}: columns {list(got.columns)} != {want['columns']}")
            continue
        got_rows = rows_of(got)
        want_rows = [[_norm(v) for v in r] for r in want["rows"]]
        if not case.get("ordered", True):
            key = lambda r: json.dumps(r, sort_keys=True, default=str)
            got_rows, want_rows = sorted(got_rows, key=key), sorted(want_rows, key=key)
        if len(got_rows) != len(want_rows):
            problems.append(f"{port}: {len(got_rows)} rows != {len(want_rows)} expected: got {got_rows}")
            continue
        for i, (g, w) in enumerate(zip(got_rows, want_rows)):
            for j, (a, b) in enumerate(zip(g, w)):
                same = (a is None and b is None) or (
                    isinstance(a, float) and isinstance(b, float) and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
                ) or a == b
                if not same:
                    problems.append(f"{port} row {i} col {j}: got {a!r}, expected {b!r}")
    return problems

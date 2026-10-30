"""Writes tests/golden/cases/*.json from the table below (run: py tests/golden/build_cases.py).

Expected values are worked out by hand from documented Alteryx behavior and marked provenance "derived".
Change a case to "verified" only after comparing it with output from a real Alteryx run, and record where it came from.
"""
import json
import os
import re

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases")
os.makedirs(OUT, exist_ok=True)
N = None  # null


def T(columns, *rows):
    return {"columns": columns, "rows": [list(r) for r in rows]}


CASES = []


def case(tool, name, source, config, inputs, expect, ordered=True, provenance="derived"):
    CASES.append(dict(name=name, tool=tool, provenance=provenance, source=source, config=config, inputs=inputs,
                      expect=expect, ordered=ordered))


# ------------------------------------------------------------------ Join
JK = [{"left_key": "id", "right_key": "id"}]
case("join", "inner join splits matched / left-only / right-only",
     "Alteryx Join tool: J = matched, L = left unmatched, R = right unmatched",
     {"join_keys": JK},
     {"L": T(["id", "a"], [1, "x"], [2, "y"], [3, "z"]), "R": T(["id", "b"], [2, "B2"], [3, "B3"], [4, "B4"])},
     {"J": T(["id", "a", "Right_id", "b"], [2, "y", 2, "B2"], [3, "z", 3, "B3"]),
      "L": T(["id", "a"], [1, "x"]), "R": T(["id", "b"], [4, "B4"])}, ordered=False)
case("join", "duplicate keys on both sides produce every combination",
     "Alteryx Join: many-to-many matches multiply rows",
     {"join_keys": JK},
     {"L": T(["id", "a"], [1, "x1"], [1, "x2"]), "R": T(["id", "b"], [1, "y1"], [1, "y2"])},
     {"J": T(["id", "a", "Right_id", "b"], [1, "x1", 1, "y1"], [1, "x1", 1, "y2"], [1, "x2", 1, "y1"], [1, "x2", 1, "y2"])},
     ordered=False)
case("join", "keys match case-insensitively by default",
     "Alteryx Join compares string keys case-insensitively unless told otherwise",
     {"join_keys": [{"left_key": "k", "right_key": "k"}]},
     {"L": T(["k", "a"], ["ABC", 1]), "R": T(["k", "b"], ["abc", 2])},
     {"J": T(["k", "a", "Right_k", "b"], ["ABC", 1, "abc", 2])})
case("join", "null keys never match each other",
     "Alteryx Join: null does not equal null",
     {"join_keys": JK},
     {"L": T(["id", "a"], [N, "x"], [1, "y"]), "R": T(["id", "b"], [N, "p"], [1, "q"])},
     {"J": T(["id", "a", "Right_id", "b"], [1, "y", 1, "q"]),
      "L": T(["id", "a"], [N, "x"]), "R": T(["id", "b"], [N, "p"])}, ordered=False)

# ------------------------------------------------------------------ Filter
FC = lambda col, op, val: {"mode": "basic", "conditions": [{"column": col, "operator": op, "value": val}]}
case("filter", "true and false outputs partition the input",
     "Alteryx Filter: T = records that match, F = records that do not",
     FC("n", ">", "2"),
     {"I": T(["n", "s"], [1, "a"], [2, "b"], [3, "c"], [4, "d"])},
     {"T": T(["n", "s"], [3, "c"], [4, "d"]), "F": T(["n", "s"], [1, "a"], [2, "b"])})
case("filter", "null is not greater than anything and lands in False",
     "Alteryx Filter: comparisons with null are false, so the record goes to F",
     FC("n", ">", "0"),
     {"I": T(["n"], [1], [N], [5])},
     {"T": T(["n"], [1], [5]), "F": T(["n"], [N])})
case("filter", "native filters ignore case by default (differs from Alteryx; imported filters do not)",
     "DataFlow default: ignore_case is true unless the condition says otherwise",
     FC("s", "==", "b"),
     {"I": T(["s"], ["a"], ["b"], ["B"])},
     {"T": T(["s"], ["b"], ["B"]), "F": T(["s"], ["a"])}, provenance="derived")

case("filter", "ignore_case false makes text equality case-sensitive (as imported Alteryx filters are)",
     "Alteryx Filter: text comparison is case-sensitive; the importer sets ignore_case false",
     {"mode": "basic", "conditions": [{"column": "s", "operator": "==", "value": "b", "ignore_case": False}]},
     {"I": T(["s"], ["a"], ["b"], ["B"])},
     {"T": T(["s"], ["b"]), "F": T(["s"], ["a"], ["B"])})

# ------------------------------------------------------------------ Sort
case("sort", "ascending sort with a second key breaks ties",
     "Alteryx Sort: records ordered by the first field, ties by the next",
     {"sort_by": [{"column": "g", "ascending": True}, {"column": "n", "ascending": False}]},
     {"I": T(["g", "n"], ["b", 1], ["a", 1], ["a", 3], ["b", 2])},
     {"O": T(["g", "n"], ["a", 3], ["a", 1], ["b", 2], ["b", 1])})
case("sort", "equal keys keep their input order (stable)",
     "Alteryx Sort is stable for equal keys",
     {"sort_by": [{"column": "g", "ascending": True}]},
     {"I": T(["g", "id"], ["x", 1], ["y", 2], ["x", 3], ["y", 4])},
     {"O": T(["g", "id"], ["x", 1], ["x", 3], ["y", 2], ["y", 4])})
case("sort", "nulls sort first when ascending",
     "Alteryx Sort places nulls before values in ascending order",
     {"sort_by": [{"column": "n", "ascending": True}]},
     {"I": T(["n"], [2], [N], [1])},
     {"O": T(["n"], [N], [1], [2])})

case("sort", "nulls sort last when descending",
     "Alteryx Sort places nulls after values in descending order",
     {"sort_by": [{"column": "n", "ascending": False}]},
     {"I": T(["n"], [2], [N], [1])},
     {"O": T(["n"], [2], [1], [N])})

# ------------------------------------------------------------------ Unique
case("unique", "first record of each key is Unique, repeats are Duplicate",
     "Alteryx Unique: U = first of each group, D = the rest",
     {"columns": ["k"]},
     {"I": T(["k", "v"], ["a", 1], ["b", 2], ["a", 3], ["a", 4])},
     {"U": T(["k", "v"], ["a", 1], ["b", 2]), "D": T(["k", "v"], ["a", 3], ["a", 4])})

# ------------------------------------------------------------------ Summarize
case("summarize", "group by with sum, count and average",
     "Alteryx Summarize: grouped aggregates",
     {"actions": [{"field": "g", "action": "GroupBy"}, {"field": "n", "action": "Sum"},
                  {"field": "n", "action": "Count"}, {"field": "n", "action": "Avg"}]},
     {"I": T(["g", "n"], ["a", 1], ["a", 3], ["b", 10])},
     {"O": T(None, ["a", 4, 2, 2.0], ["b", 10, 1, 10.0])}, ordered=False)
case("summarize", "sum skips nulls; Count counts every record, CountNonNull only values",
     "Alteryx Summarize: Sum ignores nulls; Count = number of records; Count Non-Null = records with a value",
     {"actions": [{"field": "n", "action": "Sum"}, {"field": "n", "action": "Count"}, {"field": "n", "action": "CountNonNull"}]},
     {"I": T(["n"], [1], [N], [4])},
     {"O": T(None, [5, 3, 2])})
case("summarize", "min and max",
     "Alteryx Summarize: Min and Max",
     {"actions": [{"field": "n", "action": "Min"}, {"field": "n", "action": "Max"}]},
     {"I": T(["n"], [3], [1], [7])},
     {"O": T(None, [1, 7])})

# ------------------------------------------------------------------ Select
case("select", "rename, drop and reorder",
     "Alteryx Select: keep, rename and order columns; unselected columns are dropped",
     {"fields": [{"original": "b", "keep": True, "rename": "B2", "type": "none"},
                 {"original": "a", "keep": True, "rename": "a", "type": "none"},
                 {"original": "c", "keep": False, "rename": "c", "type": "none"}]},
     {"I": T(["a", "b", "c"], [1, 2, 3])},
     {"O": T(["B2", "a"], [2, 1])})
case("select", "*Unknown row keeps columns that are not listed",
     "Alteryx Select: the Unknown row controls fields that appear later",
     {"fields": [{"original": "a", "keep": False, "rename": "a", "type": "none"},
                 {"original": "*Unknown", "keep": True, "rename": "*Unknown", "type": "none"}]},
     {"I": T(["a", "b", "c"], [1, 2, 3])},
     {"O": T(["b", "c"], [2, 3])})

# ------------------------------------------------------------------ Union
case("union", "by name, non-matching columns are filled with null",
     "Alteryx Union: auto-configure by name; missing fields are null",
     {"mode": "by_name", "non_matching": "all"},
     {"I": T(["a", "b"], [1, 2])},  # second input is added by the multi-input test below
     {"O": T(["a", "b"], [1, 2])})

# ------------------------------------------------------------------ Formula
case("formula", "arithmetic with a new field",
     "Alteryx Formula: [a] * [b] into a new field",
     {"formulas": [{"output_field": "p", "expression": "[a] * [b]", "type": "double"}]},
     {"I": T(["a", "b"], [2, 3], [4, 5])},
     {"O": T(["a", "b", "p"], [2, 3, 6.0], [4, 5, 20.0])})
case("formula", "IF/THEN/ELSE",
     "Alteryx Formula: IF [n] > 1 THEN 'big' ELSE 'small' ENDIF",
     {"formulas": [{"output_field": "size", "expression": "IF [n] > 1 THEN 'big' ELSE 'small' ENDIF", "type": "string"}]},
     {"I": T(["n"], [1], [2])},
     {"O": T(["n", "size"], [1, "small"], [2, "big"])})
case("formula", "string functions",
     "Alteryx Formula: Uppercase and Trim",
     {"formulas": [{"output_field": "u", "expression": "Uppercase(Trim([s]))", "type": "string"}]},
     {"I": T(["s"], ["  ab "], ["Cd"])},
     {"O": T(["s", "u"], ["  ab ", "AB"], ["Cd", "CD"])})

# ------------------------------------------------------------------ Cross Tab / Transpose
case("crosstab", "pivot with sum fills a missing combination with 0",
     "OPEN QUESTION: DataFlow fills Sum/Count with 0 and leaves Mean/Min/Max null; confirm against a real Alteryx Cross Tab run",
     {"group_by": ["r"], "header_field": "q", "value_field": "v", "agg_func": "sum"},
     {"I": T(["r", "q", "v"], ["n", "Q1", 1], ["n", "Q2", 2], ["s", "Q1", 5])},
     {"O": T(["r", "Q1", "Q2"], ["n", 1.0, 2.0], ["s", 5.0, 0.0])}, ordered=False)
case("crosstab", "pivot with mean leaves a missing combination null",
     "OPEN QUESTION: see the Sum case; Mean over no records is null",
     {"group_by": ["r"], "header_field": "q", "value_field": "v", "agg_func": "mean"},
     {"I": T(["r", "q", "v"], ["n", "Q1", 1], ["n", "Q2", 3], ["s", "Q1", 5])},
     {"O": T(["r", "Q1", "Q2"], ["n", 1.0, 3.0], ["s", 5.0, N])}, ordered=False)
case("transpose", "unpivot key and data columns",
     "Alteryx Transpose: key columns stay, data columns become Name/Value rows",
     {"key_columns": ["id"], "data_columns": ["q1", "q2"], "name_column": "Name", "value_column": "Value"},
     {"I": T(["id", "q1", "q2"], [1, 10, 20], [2, 30, 40])},
     {"O": T(["id", "Name", "Value"], [1, "q1", 10], [1, "q2", 20], [2, "q1", 30], [2, "q2", 40])}, ordered=False)

# ------------------------------------------------------------------ Record ID / Sample / Running Total
case("record_id", "sequential ids starting at 1",
     "Alteryx Record ID: new field numbering records from the start value",
     {"column_name": "RecordID", "start_value": 1, "position": "first"},
     {"I": T(["x"], ["a"], ["b"], ["c"])},
     {"O": T(["RecordID", "x"], [1, "a"], [2, "b"], [3, "c"])})
case("sample", "first N records",
     "Alteryx Sample: First N",
     {"sample_type": "first_n", "n_records": 2},
     {"I": T(["x"], [1], [2], [3])},
     {"O": T(["x"], [1], [2])})
case("sample", "every Nth record",
     "Alteryx Sample: 1 of every N (starting with the first)",
     {"sample_type": "sample_1_in_n", "n_records": 2},
     {"I": T(["x"], [1], [2], [3], [4], [5])},
     {"O": T(["x"], [1], [3], [5])})
case("running_total", "cumulative sum per group",
     "Alteryx Running Total: cumulative sum within each group, in record order",
     {"running_total_fields": ["n"], "group_by_fields": ["g"]},
     {"I": T(["g", "n"], ["a", 1], ["b", 10], ["a", 2], ["b", 20])},
     {"O": T(["g", "n", "RunTot_n"], ["a", 1, 1.0], ["b", 10, 10.0], ["a", 2, 3.0], ["b", 20, 30.0])})


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


if __name__ == "__main__":
    for old in os.listdir(OUT):
        if old.endswith(".json"):
            os.remove(os.path.join(OUT, old))
    for i, c in enumerate(CASES, 1):
        with open(os.path.join(OUT, f"{c['tool']}__{i:02d}_{slug(c['name'])[:48]}.json"), "w", encoding="utf-8") as fh:
            json.dump(c, fh, indent=2)
            fh.write("\n")
    print(f"wrote {len(CASES)} cases to {OUT}")

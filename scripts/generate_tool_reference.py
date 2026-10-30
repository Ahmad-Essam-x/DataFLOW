"""
Generates docs/TOOL_REFERENCE.md from the node registry plus the curated notes below.

    py scripts/generate_tool_reference.py          # rewrite the file
    py scripts/generate_tool_reference.py --check  # exit 1 if the committed file is out of date (used by tests/CI)

Names, categories, ports and one-line descriptions come from the registry (backend/engine/nodes/registry.py), so
they cannot drift. The per-tool "what it does / settings / notes" text lives in NOTES; the generator and
tests/test_docs_generated.py fail if a registered tool has no notes.
"""
import argparse
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from backend._version import APP_NAME, __version__
from backend.engine.nodes.registry import NODE_REGISTRY, TOOL_METADATA

OUTPUT = os.path.join(REPO, "docs", "TOOL_REFERENCE.md")

CATEGORIES = [
    ("in_out", "In / Out"), ("preparation", "Preparation"), ("join", "Join"), ("transform", "Transform"),
    ("parse", "Parse"), ("ai", "AI"), ("documentation", "Documentation"), ("fallback", "Imported (unsupported)"),
]
PORT_NAMES = {
    "I": "Input", "O": "Output", "L": "Left", "R": "Right", "J": "Joined", "U": "Unique", "D": "Duplicate",
    "T": "True / Target", "F": "False", "S": "Source", "M": "Model", "E": "Errors",
}

# type -> (what it does, [(setting, meaning)], notes). Keep the settings in step with the node's config keys.
NOTES = {
    "input_data": (
        "Reads a CSV, TSV, Excel (.xlsx/.xls) or Parquet file, a wildcard set of files, or a database query.",
        [("File path", "The file to read. Relative names are looked up in your data folder."),
         ("Delimiter / quote / encoding", "How to parse delimited text. Header detection is automatic."),
         ("Sheet", "For Excel: which sheet to read, or all sheets."),
         ("Bad lines", "What to do with malformed rows: stop with an error, or skip them.")],
        "Excel files are read with the pandas engine, so very large workbooks take longer than CSV."),
    "output_data": (
        "Writes the incoming records to a CSV or Excel file in your outputs folder.",
        [("File name / format", "CSV or Excel."), ("Write mode", "Overwrite, or append where supported."),
         ("Delimiter, encoding, quoting, line ending", "CSV formatting options.")],
        "Written files appear under Data > outputs and can be downloaded from the results panel."),
    "text_input": (
        "Creates a small table by typing or pasting values, for lookups and test data.",
        [("Columns", "Field names."), ("Data", "The rows.")], ""),
    "browse": ("Shows the data flowing through a point in the workflow, with profiling and charts.", [],
               "Place it anywhere to inspect data without writing a file."),
    "select": (
        "Keeps, drops, renames, reorders and re-types columns.",
        [("Fields", "One row per column: keep, new name, data type."),
         ("*Unknown", "A row that stands for columns not listed (for example new columns arriving later). Keep it checked to let them through.")],
        "Columns not listed and without an *Unknown row are dropped."),
    "auto_field": ("Chooses the smallest suitable data type for text columns that hold numbers, dates or booleans.", [], ""),
    "filter": (
        "Splits records into those that match a condition (True) and those that do not (False).",
        [("Mode", "Basic (field / operator / value rows) or Custom (a formula expression)."),
         ("Conditions", "Combined with AND or OR.")],
        "Both outputs can be used; unmatched records are never lost."),
    "formula": (
        "Creates or updates columns using expressions (math, text, dates, IF/ELSE).",
        [("Output field", "New or existing column."), ("Expression", "See FORMULA_REFERENCE.md."), ("Type", "Result data type.")],
        "Expressions use square brackets for fields, for example [Price] * [Qty]."),
    "sort": ("Orders records by one or more columns, ascending or descending.", [("Sort fields", "Column and direction, in priority order."),
             ("Case sensitive", "Whether upper and lower case sort separately.")], ""),
    "clean": (
        "Tidies text and missing values: trim spaces, change case, remove characters, replace nulls.",
        [("Columns", "Which columns to clean."), ("Whitespace / characters", "Trim, remove tabs and line breaks, letters, numbers, punctuation or custom text."),
         ("Case", "Upper, lower or title case."), ("Nulls", "Replace missing text or numbers with a value.")], ""),
    "unique": ("Splits records into the first of each key combination (Unique) and the repeats (Duplicate).", [("Columns", "Key columns that define a duplicate.")],
               "Both outputs are available."),
    "sample": (
        "Keeps or skips records: the first or last N, every Nth, a random share, a percentage, or a range.",
        [("Sample type", "First N, Last N, Skip first N, 1 in N, Random 1 in N, First N percent, or Records range (for example 10-15, -5, 20+)."),
         ("N / percent / range", "The number, percentage or range for the chosen type."), ("Group by", "Apply the sample within each group."),
         ("Seed", "Makes the random type repeatable.")], ""),
    "record_id": ("Adds a sequential number column.", [("Column name", "Default RecordID."), ("Start value", "First number."),
                  ("Position", "First or last column."), ("Group by", "Restart numbering for each group.")], ""),
    "multi_row_formula": (
        "Calculates a value that depends on other rows, such as the previous record.",
        [("Output field", "New or existing column."), ("Expression", "Can refer to the row above or below."), ("Group by", "Restart per group.")], ""),
    "multi_field_formula": (
        "Applies one expression to many columns at once.",
        [("Fields", "Which columns to change."), ("Expression", "Use the placeholder for the current field."),
         ("Output", "Update in place or create new columns with a prefix/suffix.")], ""),
    "running_total": (
        "Adds a cumulative-sum column for each selected numeric field, optionally restarting per group.",
        [("Fields to total", "Each gets a new column named RunTot_<field>."), ("Group by", "Restart the total for each group.")],
        "Records keep their original order. Non-numeric values count as 0."),
    "dynamic_rename": (
        "Renames columns in bulk: use the first row as headers, or add a prefix or suffix to every column.",
        [("Mode", "First row as headers, add prefix, or add suffix."), ("Prefix / suffix", "Text to add.")],
        "With first-row mode the first record becomes the header and is removed from the data."),
    "join": (
        "Combines two inputs by matching key columns. Matches go to J; unmatched records to L and R.",
        [("Join keys", "Pair a left and a right column."), ("Ignore case", "Match text without regard to case."),
         ("Select fields", "Choose and rename the columns in the result.")],
        "Duplicate keys on both sides produce every combination (as in Alteryx)."),
    "join_multiple": ("Joins three or more inputs on shared keys.", [("Join keys", "Columns shared by all inputs."), ("Join mode", "Specific fields or all fields.")], ""),
    "union": ("Stacks several inputs into one.", [("Mode", "Match columns by name or by position."),
              ("Non-matching columns", "Keep all columns (filling gaps with null) or only those common to every input.")], ""),
    "find_replace": (
        "Looks up values from a second table and replaces or appends matching data.",
        [("Find field", "Column in the main input (F anchor)."), ("Lookup field and value field", "Columns in the reference input (R anchor)."),
         ("Action", "Replace the matched text, or append fields from the reference record."),
         ("Search mode", "Match the entire field, the beginning of the field, or anywhere in it."), ("Case sensitive / whole word", "Matching options.")], ""),
    "append_fields": (
        "Adds every column of a small second input (Source, S) to every record of the first (Target, T).",
        [("Cartesian mode", "Stop with an error (default), warn, or allow when the Source has more than 16 records."),
         ("Source prefix", "Added to Source columns whose names clash with Target columns.")],
        "By default a Source with more than 16 records is refused, to prevent accidentally huge results."),
    "summarize": (
        "Groups records and calculates totals, averages, counts and similar.",
        [("Actions", "For each column choose Group By or an aggregate: Sum, Average, Min, Max, Median, Std Dev, Variance, Product, Percentile, "
                     "First, Last, Count, Count Distinct, Count Null / Non-Null / Blank / Non-Blank, Longest, Shortest, Concatenate "
                     "(also distinct), and the financial functions NPV, XNPV, IRR, XIRR, MIRR.")], ""),
    "transpose": ("Turns selected columns into rows (unpivot).", [("Key columns", "Columns that stay as they are."), ("Data columns", "Columns to turn into rows."),
                  ("Name / value columns", "Names of the two new columns.")], ""),
    "crosstab": ("Turns row values into columns (pivot).", [("Group by", "Rows of the result."), ("Header field", "Values that become column names."),
                 ("Value field and method", "What to aggregate and how.")], ""),
    "text_to_columns": ("Splits one text column into several columns or rows at a delimiter.", [("Column", "Field to split."), ("Delimiters", "Characters to split on."),
                        ("Split to", "Columns or rows."), ("Number of columns", "How many parts to keep.")], ""),
    "date_time": ("Converts between text and dates.", [("Column", "Field to convert."), ("Conversion", "Text to date, or date to text."), ("Format", "Date pattern, for example yyyy-MM-dd.")], ""),
    "llm_process": (
        "Sends each record to a language model with your prompt and stores the answer.",
        [("Provider and model", "Ollama, LM Studio, OpenAI, Azure OpenAI, Gemini or any OpenAI-compatible endpoint."),
         ("Prompt template", "Use {{column}} to insert values from each record."), ("Output mode", "Single column, JSON fields, or structured output."),
         ("Concurrency and retries", "Throughput and error handling.")],
        "Row values are sent to the configured endpoint. Local endpoints send nothing off your PC; any other host must be approved once. API keys are stored in Windows Credential Manager."),
    "llm_override": ("Defines a model connection once and passes it to AI tools through the M anchor.", [("Provider, model, endpoint, API key", "Connection details.")],
                     "The key is stored securely and is never saved in the workflow file."),
    "schema_fit": (
        "Reshapes a source table to match a target table's columns and types, showing the steps it took.",
        [("Max transformations", "Number of correction attempts when using a model."), ("Only target columns", "Drop columns that are not in the target."),
         ("Custom code", "Provide your own pandas steps instead of a model.")],
        "Generated code runs in an isolated, restricted process with a time and memory limit. Without a model it uses a built-in matcher. Sample values are sent to a remote model only after you approve the host."),
    "unsupported_tool": ("Placeholder for a tool in an imported Alteryx workflow that DataFlow cannot run. Data passes through unchanged.", [],
                         "Review every placeholder after an import: results may differ from Alteryx."),
    "tool_container": ("Groups tools visually.", [], "Containers do not change results."),
    "comment": ("Adds a note to the canvas.", [], ""),
}


def _ports(ports):
    return ", ".join(f"`{p}` ({PORT_NAMES.get(p, p)})" for p in ports) if ports else "none"


def render():
    meta = {m["type"]: m for m in TOOL_METADATA}
    missing = sorted(t for t in set(meta) | set(NODE_REGISTRY) if t not in NOTES)
    if missing:
        raise SystemExit(f"Add notes in scripts/generate_tool_reference.py for: {', '.join(missing)}")

    lines = [
        f"# {APP_NAME} - Tool Reference",
        "",
        f"Version {__version__}. Generated by `scripts/generate_tool_reference.py` - do not edit by hand.",
        "",
        "Tools are grouped as in the palette. For formulas see [FORMULA_REFERENCE.md](FORMULA_REFERENCE.md).",
        "",
    ]
    ordered = []
    for key, title in CATEGORIES:
        tools = [m for m in TOOL_METADATA if m["category"] == key]
        if tools:
            ordered.append((title, tools))
    for _title, tools in ordered:
        lines.append(f"- **{_title}:** " + ", ".join(f"[{t['name']}](#{t['name'].lower().replace(' ', '-')})" for t in tools))
    lines.append("")

    for title, tools in ordered:
        lines += [f"## {title}", ""]
        for m in tools:
            what, settings, notes = NOTES[m["type"]]
            lines += [f"### {m['name']}", "", what, ""]
            lines.append(f"- **Inputs:** {_ports(m['inputs'])}")
            lines.append(f"- **Outputs:** {_ports(m['outputs'])}")
            if settings:
                lines += ["", "| Setting | What it does |", "|---|---|"]
                lines += [f"| {name} | {meaning} |" for name, meaning in settings]
            if notes:
                lines += ["", f"**Notes:** {notes}"]
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = render()
    current = open(OUTPUT, encoding="utf-8").read() if os.path.exists(OUTPUT) else ""
    if args.check:
        if current.replace("\r\n", "\n") != text:
            print("docs/TOOL_REFERENCE.md is out of date. Run: py scripts/generate_tool_reference.py")
            return 1
        return 0
    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

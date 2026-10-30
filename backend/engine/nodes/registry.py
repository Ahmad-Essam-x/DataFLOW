"""
Node Registry — auto-discovers all BaseNode subclasses from the nodes/ package.

TOOL_METADATA (palette UI config) remains explicit; adding a new node type only
requires creating a file in nodes/ that inherits BaseNode with a unique type_name,
and adding an entry to TOOL_METADATA for palette display.
"""
import importlib
import inspect
import pkgutil
from typing import Dict, Type, Any, List

from .base import BaseNode

# Modules that define nodes. pkgutil finds new files automatically in a source checkout; this list is the
# guarantee for frozen (PyInstaller) builds, where modules live in an archive and are also bundled explicitly via
# hidden imports. test_node_modules_are_listed fails if a new node module is missing from it.
NODE_MODULES = (
    'ai', 'fallback', 'io', 'join', 'llm_override', 'parse', 'preparation', 'schema_fit', 'transform',
)


def _node_module_names() -> List[str]:
    names = set(NODE_MODULES)
    package = importlib.import_module(__package__)
    for info in pkgutil.iter_modules(package.__path__):
        names.add(info.name)
    return sorted(names - {'base', 'registry', '__init__'})


def _discover_nodes() -> Dict[str, Type[BaseNode]]:
    """Auto-register every concrete BaseNode subclass defined in the nodes package.

    Imports each node module and registers classes that inherit BaseNode and define a non-default type_name.
    First registration wins on name collision (sorted alphabetically by module name).
    """
    registry: Dict[str, Type[BaseNode]] = {}
    for name in _node_module_names():
        mod = importlib.import_module(f'.{name}', package=__package__)
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if (
                issubclass(cls, BaseNode)
                and cls is not BaseNode
                and getattr(cls, 'type_name', 'base') != 'base'
                and cls.type_name not in registry
            ):
                registry[cls.type_name] = cls
    return registry


NODE_REGISTRY: Dict[str, Type[BaseNode]] = _discover_nodes()

TOOL_METADATA: List[Dict[str, Any]] = [
    {
        "type": "input_data",
        "name": "Input Data",
        "category": "in_out",
        "color": "#22c55e",
        "icon": "upload",
        "inputs": [],
        "outputs": ["O"],
        "description": "Ingest CSV or Excel files"
    },
    {
        "type": "output_data",
        "name": "Output Data",
        "category": "in_out",
        "color": "#16a34a",
        "icon": "download",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Export data to CSV or Excel"
    },
    {
        "type": "text_input",
        "name": "Text Input",
        "category": "in_out",
        "color": "#10b981",
        "icon": "edit",
        "inputs": [],
        "outputs": ["O"],
        "description": "Manually input data via table grid or paste clipboard text"
    },
    {
        "type": "browse",
        "name": "Browse",
        "category": "in_out",
        "color": "#059669",
        "icon": "eye",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "View data and comprehensive data profiling studio"
    },
    {
        "type": "select",
        "name": "Select",
        "category": "preparation",
        "color": "#3b82f6",
        "icon": "check-square",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Select, rename, and change column data types"
    },
    {
        "type": "auto_field",
        "name": "Auto Field",
        "category": "preparation",
        "color": "#3b82f6",
        "icon": "zap",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Automatically optimize and assign best field data types"
    },
    {
        "type": "filter",
        "name": "Filter",
        "category": "preparation",
        "color": "#2563eb",
        "icon": "filter",
        "inputs": ["I"],
        "outputs": ["T", "F"],
        "description": "Split records into True and False outputs"
    },
    {
        "type": "formula",
        "name": "Formula",
        "category": "preparation",
        "color": "#0284c7",
        "icon": "code",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Calculate or modify columns with formulas"
    },
    {
        "type": "multi_row_formula",
        "name": "Multi-Row Formula",
        "category": "preparation",
        "color": "#0284c7",
        "icon": "rows",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Calculate running totals, lag/lead differences, and recursive row logic"
    },
    {
        "type": "multi_field_formula",
        "name": "Multi-Field Formula",
        "category": "preparation",
        "color": "#0369a1",
        "icon": "columns",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Apply formulas, cleaning, and transformations across multiple fields at once"
    },
    {
        "type": "sort",
        "name": "Sort",
        "category": "preparation",
        "color": "#0ea5e9",
        "icon": "arrow-down-up",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Order records ascending or descending"
    },
    {
        "type": "clean",
        "name": "Data Clean",
        "category": "preparation",
        "color": "#06b6d4",
        "icon": "sparkles",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Trim whitespace, handle nulls, and format text"
    },
    {
        "type": "unique",
        "name": "Unique",
        "category": "preparation",
        "color": "#0891b2",
        "icon": "copy",
        "inputs": ["I"],
        "outputs": ["U", "D"],
        "description": "Separate unique and duplicate records"
    },
    {
        "type": "sample",
        "name": "Sample",
        "category": "preparation",
        "color": "#0284c7",
        "icon": "scissors",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Limit records using first/last N, percentage, or 1 of N sample"
    },
    {
        "type": "record_id",
        "name": "Record ID",
        "category": "preparation",
        "color": "#0369a1",
        "icon": "hash",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Assign a unique sequential identifier to each record"
    },
    {
        "type": "running_total",
        "name": "Running Total",
        "category": "preparation",
        "color": "#0369a1",
        "icon": "sigma",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Add a cumulative sum of numeric fields, optionally restarting per group"
    },
    {
        "type": "dynamic_rename",
        "name": "Dynamic Rename",
        "category": "preparation",
        "color": "#0369a1",
        "icon": "edit",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Rename columns from the first data row, or add a prefix/suffix to every column"
    },
    {
        "type": "join",
        "name": "Join",
        "category": "join",
        "color": "#a855f7",
        "icon": "git-merge",
        "inputs": ["L", "R"],
        "outputs": ["J", "L", "R"],
        "description": "Join two tables with Joined, Left, and Right outputs"
    },
    {
        "type": "join_multiple",
        "name": "Join Multiple",
        "category": "join",
        "color": "#8b5cf6",
        "icon": "git-merge",
        "inputs": ["I"],
        "outputs": ["J"],
        "description": "Combine 2 or more datasets based on common field(s) or record position"
    },
    {
        "type": "union",
        "name": "Union",
        "category": "join",
        "color": "#9333ea",
        "icon": "layers",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Stack multiple datasets vertically"
    },
    {
        "type": "find_replace",
        "name": "Find Replace",
        "category": "join",
        "color": "#7e22ce",
        "icon": "search",
        "inputs": ["F", "R"],
        "outputs": ["O"],
        "description": "Find data in one table and replace or append from a reference table"
    },
    {
        "type": "summarize",
        "name": "Summarize",
        "category": "transform",
        "color": "#f97316",
        "icon": "sigma",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Group by and aggregate numerical & text fields"
    },
    {
        "type": "transpose",
        "name": "Transpose",
        "category": "transform",
        "color": "#ea580c",
        "icon": "refresh-cw",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Pivot wide data to tall format (Key Columns + Data Columns)"
    },
    {
        "type": "crosstab",
        "name": "Cross Tab",
        "category": "transform",
        "color": "#c2410c",
        "icon": "table",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Pivot tall data to wide format (Group By, Column Headers, Values)"
    },
    {
        "type": "append_fields",
        "name": "Append Fields",
        "category": "join",
        "color": "#7c3aed",
        "icon": "link",
        "inputs": ["T", "S"],
        "outputs": ["O"],
        "description": "Append fields of a Source stream to every record of a Target stream"
    },
    {
        "type": "text_to_columns",
        "name": "Text To Columns",
        "category": "parse",
        "color": "#00a3e0",
        "icon": "columns",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Split text from one field into multiple columns or rows based on delimiters"
    },
    {
        "type": "date_time",
        "name": "DateTime",
        "category": "parse",
        "color": "#0284c7",
        "icon": "calendar",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Transform date/time data between strings and standardized DateTime formats"
    },
    {
        "type": "llm_process",
        "name": "LLM Process",
        "category": "ai",
        "color": "#8b5cf6",
        "icon": "brain",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Process each record through an LLM with a configurable prompt"
    },
    {
        "type": "schema_fit",
        "name": "Schema Fit",
        "category": "ai",
        "color": "#8b5cf6",
        "icon": "sparkles",
        "inputs": ["M", "T", "S"],
        "outputs": ["T", "D"],
        "description": "Transform Source data to match Target schema using AI-generated Python steps"
    },
    {
        "type": "llm_override",
        "name": "LLM Override",
        "category": "ai",
        "color": "#8b5cf6",
        "icon": "cpu",
        "inputs": [],
        "outputs": ["M"],
        "description": "Configure and pass LLM connection settings to AI tools"
    },
    {
        "type": "tool_container",
        "name": "Tool Container",
        "category": "documentation",
        "color": "#0284c7",
        "icon": "box",
        "inputs": [],
        "outputs": [],
        "description": "Organize, collapse, or disable tool groups"
    },
    {
        "type": "comment",
        "name": "Comment",
        "category": "documentation",
        "color": "#eab308",
        "icon": "file-text",
        "inputs": [],
        "outputs": [],
        "description": "Add documentation notes with Markdown support"
    },
    {
        "type": "unsupported_tool",
        "name": "Unsupported Tool",
        "category": "fallback",
        "color": "#f59e0b",
        "icon": "alert-triangle",
        "inputs": ["I"],
        "outputs": ["O"],
        "description": "Preserved Alteryx tool not yet natively implemented. Operates as a non-destructive passthrough."
    }
]

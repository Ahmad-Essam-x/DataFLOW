from typing import Dict, Type, Any, List
from .base import BaseNode, NodeExecutionError, sanitize_dataframe
from .io import InputDataNode, OutputDataNode, TextInputNode, BrowseNode
from .preparation import (
    SelectNode, AutoFieldNode, FilterNode, FormulaNode, SortNode,
    CleanNode, UniqueNode, SampleNode, RecordIDNode,
    MultiRowFormulaNode, MultiFieldFormulaNode
)
from .join import JoinNode, UnionNode, FindReplaceNode, AppendFieldsNode, JoinMultipleNode
from .transform import SummarizeNode, TransposeNode, CrossTabNode
from .parse import TextToColumnsNode, DateTimeNode
from .ai import LLMProcessNode

NODE_REGISTRY = {
    "input_data": InputDataNode,
    "output_data": OutputDataNode,
    "text_input": TextInputNode,
    "browse": BrowseNode,
    "select": SelectNode,
    "auto_field": AutoFieldNode,
    "filter": FilterNode,
    "formula": FormulaNode,
    "multi_row_formula": MultiRowFormulaNode,
    "multi_field_formula": MultiFieldFormulaNode,
    "sort": SortNode,
    "clean": CleanNode,
    "unique": UniqueNode,
    "sample": SampleNode,
    "record_id": RecordIDNode,
    "join": JoinNode,
    "join_multiple": JoinMultipleNode,
    "union": UnionNode,
    "find_replace": FindReplaceNode,
    "append_fields": AppendFieldsNode,
    "summarize": SummarizeNode,
    "transpose": TransposeNode,
    "crosstab": CrossTabNode,
    "text_to_columns": TextToColumnsNode,
    "date_time": DateTimeNode,
    "llm_process": LLMProcessNode,
}

TOOL_METADATA = [
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
    }
]

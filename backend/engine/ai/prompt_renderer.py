import re
import pandas as pd
from typing import Any, Dict, List, Optional
import os

COLUMN_PATTERN = re.compile(r'\{\{\[([^\]]+)\]\}\}')
_FILE_CACHE = {}

def render_template(template: str, row: pd.Series) -> str:
    """Replace {{[ColumnName]}} with actual row values."""
    if not isinstance(template, str):
        return template

    def repl(match):
        col_name = match.group(1)
        if col_name in row:
            val = row[col_name]
            if pd.isna(val) or val is None:
                return ""
            return str(val)
        return match.group(0)

    return COLUMN_PATTERN.sub(repl, template)

def extract_column_references(template: str) -> list:
    """Extract all column names referenced in a template."""
    if not isinstance(template, str):
        return []
    return COLUMN_PATTERN.findall(template)

def validate_template(template: str, available_columns: list) -> dict:
    """Validate template - check all referenced columns exist. Return {valid: bool, missing_columns: [], referenced_columns: []}."""
    referenced = extract_column_references(template)
    missing = [c for c in referenced if c not in available_columns]
    return {
        "valid": len(missing) == 0,
        "missing_columns": missing,
        "referenced_columns": referenced
    }

def inject_context(prompt: str, row: pd.Series, ctx_config: dict) -> str:
    """Inject RAG context into the prompt based on config.
    ctx_config keys: enabled, source (static|column|file), text, column, file_path, placement (before|after|system)
    """
    if not ctx_config.get("enabled", False):
        return prompt

    source = ctx_config.get("source", "static")
    context_text = ""

    if source == "static":
        context_text = ctx_config.get("text", "")
    elif source == "column":
        col = ctx_config.get("column")
        if col and col in row:
            val = row[col]
            context_text = "" if pd.isna(val) or val is None else str(val)
    elif source == "file":
        file_path = ctx_config.get("file_path")
        if file_path:
            if file_path in _FILE_CACHE:
                context_text = _FILE_CACHE[file_path]
            elif os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        context_text = f.read()
                    _FILE_CACHE[file_path] = context_text
                except Exception:
                    context_text = ""
    
    if not context_text:
        return prompt
        
    placement = ctx_config.get("placement", "before")
    if placement == "before":
        return f"{context_text}\n\n{prompt}"
    elif placement == "after":
        return f"{prompt}\n\n{context_text}"
    
    # if placement == "system" it shouldn't be injected into the user prompt, handled separately by caller
    return prompt

def preview_prompts(template: str, system_prompt: str, df: pd.DataFrame, ctx_config: dict, n: int = 3) -> list:
    """Render prompts for the first N rows for preview. Returns list of {row_index, system_prompt, user_prompt, total_chars}."""
    results = []
    n_rows = min(n, len(df))
    for i in range(n_rows):
        row = df.iloc[i]
        
        # Render basic templates
        user_prompt = render_template(template, row)
        rendered_sys = render_template(system_prompt, row)
        
        # Inject context
        if ctx_config and ctx_config.get("enabled", False):
            placement = ctx_config.get("placement", "before")
            if placement == "system":
                rendered_sys = inject_context(rendered_sys, row, {**ctx_config, "placement": "after"})
            else:
                user_prompt = inject_context(user_prompt, row, ctx_config)
                
        results.append({
            "row_index": i,
            "system_prompt": rendered_sys,
            "user_prompt": user_prompt,
            "total_chars": len(rendered_sys) + len(user_prompt)
        })
    return results

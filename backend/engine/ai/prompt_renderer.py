"""
Prompt renderer for LLMProcessNode.

Template syntax:
  Legacy:  {{[Column Name]}}  — auto-converted to Jinja2 before render
  Jinja2:  {{ column_name }}  — full Jinja2 (conditionals, loops, filters)

Column names with spaces are normalised by replacing spaces with underscores
in both the template and the row dict so Jinja2 can address them as identifiers.
"""
import re
import os
import pandas as pd
from typing import Any, Dict, List, Optional

# Legacy syntax: {{[Column Name]}}
COLUMN_PATTERN = re.compile(r'\{\{\[([^\]]+)\]\}\}')

# File context cache (process-lifetime; keyed by absolute path)
_FILE_CACHE: Dict[str, str] = {}

# ---------------------------------------------------------------------------
# Jinja2 support (Flask already depends on it — should always be available)
# ---------------------------------------------------------------------------
try:
    from jinja2 import Environment, Undefined, TemplateSyntaxError
    _JINJA_ENV = Environment(undefined=Undefined)
    _JINJA2_AVAILABLE = True
except ImportError:  # pragma: no cover
    _JINJA2_AVAILABLE = False


def _to_jinja(template: str) -> str:
    """Convert legacy {{[Column Name]}} tokens to Jinja2 {{ column_name }} syntax."""
    return COLUMN_PATTERN.sub(
        lambda m: '{{ ' + m.group(1).replace(' ', '_') + ' }}', template
    )


def _row_dict(row: pd.Series) -> Dict[str, str]:
    """Convert a DataFrame row to a Jinja2-safe dict (spaces → underscores, NaN → '')."""
    return {
        str(k).replace(' ', '_'): ('' if pd.isna(v) or v is None else str(v))
        for k, v in row.items()
    }


def render_template(template: str, row: pd.Series) -> str:
    """Render a prompt template against a single row.

    Supports both legacy {{[Column Name]}} syntax (converted transparently)
    and full Jinja2 syntax — conditionals, loops, filters, etc.
    Falls back to regex substitution if Jinja2 is unavailable or raises a
    syntax error (e.g. user mixed syntaxes in an unusual way).
    """
    if not isinstance(template, str):
        return template

    available_cols = set(row.index) if hasattr(row, 'index') else set()
    unresolved_map = {}

    def _prep_legacy(m):
        col = m.group(1)
        if col in available_cols:
            return '{{ ' + col.replace(' ', '_') + ' }}'
        token = f"__UNRESOLVED_TOKEN_{len(unresolved_map)}__"
        unresolved_map[token] = m.group(0)
        return token

    converted = COLUMN_PATTERN.sub(_prep_legacy, template)

    rendered = None
    if _JINJA2_AVAILABLE:
        try:
            rendered = _JINJA_ENV.from_string(converted).render(**_row_dict(row))
        except Exception:
            pass  # fall through to regex fallback

    if rendered is None:
        def repl(match):
            col_name = match.group(1)
            if col_name in row:
                val = row[col_name]
                return '' if pd.isna(val) or val is None else str(val)
            return match.group(0)
        return COLUMN_PATTERN.sub(repl, template)

    for token, orig in unresolved_map.items():
        rendered = rendered.replace(token, orig)

    return rendered


def extract_column_references(template: str) -> List[str]:
    """Return all column names referenced via the legacy {{[Name]}} syntax."""
    if not isinstance(template, str):
        return []
    return COLUMN_PATTERN.findall(template)


def validate_template(template: str, available_columns: List[str]) -> dict:
    """Check that all legacy {{[Name]}} references exist in available_columns.

    Returns ``{valid: bool, missing_columns: list, referenced_columns: list}``.
    Jinja2-only templates (no legacy tokens) always pass this check — Jinja2
    syntax errors surface at render time, not here.
    """
    referenced = extract_column_references(template)
    # Also check underscore-normalised form (spaces → underscores)
    normalised = {c.replace(' ', '_') for c in available_columns}
    missing = [
        c for c in referenced
        if c not in available_columns and c.replace(' ', '_') not in normalised
    ]
    return {
        'valid': len(missing) == 0,
        'missing_columns': missing,
        'referenced_columns': referenced,
    }


# ---------------------------------------------------------------------------
# Context / RAG injection
# ---------------------------------------------------------------------------

def _resolve_context_text(ctx_config: dict, row: pd.Series) -> str:
    """Extract the raw context string for a single context block."""
    source = ctx_config.get('source', 'static')

    if source == 'static':
        return ctx_config.get('text', '')

    if source == 'column':
        col = ctx_config.get('column')
        if col and col in row:
            val = row[col]
            return '' if pd.isna(val) or val is None else str(val)
        return ''

    if source == 'file':
        file_path = ctx_config.get('file_path', '')
        if not file_path:
            return ''
        if file_path not in _FILE_CACHE:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as fh:
                        _FILE_CACHE[file_path] = fh.read()
                except Exception:
                    _FILE_CACHE[file_path] = ''
            else:
                _FILE_CACHE[file_path] = ''
        return _FILE_CACHE[file_path]

    return ''


def inject_context(prompt: str, row: pd.Series, ctx_config: dict) -> str:
    """Inject a single RAG context block into ``prompt``.

    ``placement`` values:
    - ``'before'``: context prepended to user prompt
    - ``'after'``: context appended to user prompt
    - ``'system'``: caller is responsible for injecting into the system prompt;
      this function returns ``prompt`` unchanged for system-placement blocks.
    """
    if not ctx_config.get('enabled', False):
        return prompt

    context_text = _resolve_context_text(ctx_config, row)
    if not context_text:
        return prompt

    placement = ctx_config.get('placement', 'before')
    if placement == 'before':
        return f'{context_text}\n\n{prompt}'
    if placement == 'after':
        return f'{prompt}\n\n{context_text}'
    # placement == 'system' — handled by caller
    return prompt


def inject_contexts(prompt: str, row: pd.Series, ctx_configs: List[dict]) -> str:
    """Apply a list of context blocks sequentially to ``prompt``.

    System-placement blocks are skipped here; callers handle them separately.
    """
    for ctx in ctx_configs:
        if ctx.get('enabled', False) and ctx.get('placement', 'before') != 'system':
            prompt = inject_context(prompt, row, ctx)
    return prompt


def collect_system_contexts(
    system_prompt: str,
    row: pd.Series,
    ctx_configs: List[dict],
) -> str:
    """Append all system-placement context blocks to ``system_prompt``."""
    additions = []
    for ctx in ctx_configs:
        if ctx.get('enabled', False) and ctx.get('placement') == 'system':
            text = _resolve_context_text(ctx, row)
            if text:
                additions.append(text)
    if additions:
        return system_prompt + '\n\n' + '\n\n'.join(additions)
    return system_prompt


# ---------------------------------------------------------------------------
# Preview helper (used by /api/ai/preview-prompt)
# ---------------------------------------------------------------------------

def preview_prompts(
    template: str,
    system_prompt: str,
    df: pd.DataFrame,
    ctx_config: dict,
    n: int = 3,
) -> List[dict]:
    """Render prompts for the first ``n`` rows.

    Accepts either a legacy single-context dict (``rag_context``) or a list
    (``rag_contexts``).  Returns a list of
    ``{row_index, system_prompt, user_prompt, total_chars}``.
    """
    # Normalise to list
    if isinstance(ctx_config, list):
        ctx_list = ctx_config
    elif isinstance(ctx_config, dict) and ctx_config.get('enabled'):
        ctx_list = [ctx_config]
    else:
        ctx_list = []

    results = []
    for i in range(min(n, len(df))):
        row = df.iloc[i]

        user_prompt = render_template(template, row)
        rendered_sys = render_template(system_prompt, row)

        # Apply user-placement contexts
        user_prompt = inject_contexts(user_prompt, row, ctx_list)

        # Apply system-placement contexts
        rendered_sys = collect_system_contexts(rendered_sys, row, ctx_list)

        results.append({
            'row_index': i,
            'system_prompt': rendered_sys,
            'user_prompt': user_prompt,
            'total_chars': len(rendered_sys) + len(user_prompt),
        })
    return results

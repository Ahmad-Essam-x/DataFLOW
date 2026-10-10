"""
DuckDB Fast-Path Executor for Antigravity DataFlow.

For workflows that contain only SQL-compilable node types (no AI/LLM nodes),
this executor bypasses the pandas node-by-node engine entirely:

  1. Registers each input_data file as a DuckDB in-memory view.
  2. Compiles the whole workflow to DuckDB CTE SQL via the existing sql_compiler.
  3. Materializes each CTE as a DuckDB TEMP TABLE (topological order, done once).
  4. Reads each node's output from its materialized table into the run cache.
  5. Invokes OutputDataNode only for writing files (unchanged logic).

Falls back gracefully to the pandas AMP engine if any step fails
(Excel input, compilation error, DuckDB execution error, etc.).
"""
import os
import re
import time
from typing import Any, Dict, List, Optional

import pandas as pd

from backend.engine.io_formats import detect_format
from backend.engine.node_registry import (
    sanitize_dataframe,
    infer_alteryx_type,
    map_alteryx_to_category,
)

# Node types the SQL compiler can handle.
# Any workflow containing ONLY these types is eligible for the DuckDB fast path.
_COMPILABLE_TYPES = frozenset({
    "input_data", "output_data", "filter", "sort", "unique",
    "select", "formula", "join", "union", "summarize", "parse",
    "data_clean", "tool_container", "comment", "clean",
    "find_replace", "transpose", "crosstab", "join_multiple",
    "multi_row_formula", "multi_field_formula", "sample",
    "record_id", "text_input", "auto_field", "date_time",
    "text_to_columns",
})


def can_use_duckdb(active_nodes: List[Dict[str, Any]]) -> bool:
    """
    Returns True when:
    - duckdb is installed
    - every active node type has a SQL transpiler
    - at least one input_data node is present
    - no input_data node uses Excel (DuckDB has no native Excel reader)
    """
    try:
        import duckdb  # noqa: F401
    except ImportError:
        return False

    if not any(n["type"] == "input_data" for n in active_nodes):
        return False

    for node in active_nodes:
        if node["type"] not in _COMPILABLE_TYPES:
            return False
        # Reject Excel inputs and database inputs upfront — fall back to pandas AMP engine
        if node["type"] == "input_data":
            cfg = node.get("config", {})
            if cfg.get("source_type") == "database":
                return False
            fp = cfg.get("file_path", "")
            if detect_format(fp) == "excel":
                return False

    return True


def _resolve_input_file(
    config: Dict[str, Any], data_dir: str, base_dir: str
) -> Optional[str]:
    """Mirror of InputDataNode's file resolution order."""
    file_path = config.get("file_path", "").strip()
    if not file_path:
        return None

    if os.path.isabs(file_path) and os.path.exists(file_path):
        return os.path.normpath(file_path)

    candidates = [file_path]
    if data_dir:
        candidates.append(os.path.join(data_dir, file_path))
        if file_path.startswith(("data/", "data\\")):
            candidates.append(os.path.join(data_dir, file_path[5:]))
        candidates.append(os.path.join(data_dir, os.path.basename(file_path)))
    if base_dir:
        candidates.append(os.path.join(base_dir, file_path))

    for c in candidates:
        if os.path.exists(c):
            return os.path.normpath(c)
    return None


def _build_column_meta(df: pd.DataFrame) -> List[Dict[str, Any]]:
    meta = []
    for col in df.columns:
        at = infer_alteryx_type(df[col])
        meta.append({
            "name": str(col),
            "type": map_alteryx_to_category(at),
            "alteryx_type": at,
            "dtype": at,
        })
    return meta


def _load_extra_data_dirs() -> List[str]:
    """Read user-configured trusted directories from user_settings.json."""
    try:
        import json as _json
        import backend.extensions as _ext
        sf = getattr(_ext, "USER_SETTINGS_FILE", None)
        if sf and os.path.isfile(sf):
            with open(sf, "r", encoding="utf-8") as f:
                cfg = _json.load(f)
            dirs = cfg.get("extra_data_dirs", [])
            if isinstance(dirs, list):
                return [d for d in dirs if d and isinstance(d, str)]
    except Exception:
        pass
    return []


def run_duckdb_workflow(
    workflow: Dict[str, Any],
    context: Dict[str, Any],
    result,                         # ExecutionResult (modified in-place)
    current_run_cache,              # SpillableRunDataCache
    active_nodes: List[Dict[str, Any]],
    active_connections: List[Dict[str, Any]],
    observer_cb: Optional[Any] = None,
) -> bool:
    """
    Execute a pure-SQL workflow using DuckDB.

    Modifies result and current_run_cache in place.
    Returns True on success, False to signal the caller to fall back to the
    pandas engine (cache is cleared before returning False).
    """
    import duckdb
    from backend.engine.sql_compiler.compiler import compile_workflow_to_sql
    from backend.engine.nodes.io import OutputDataNode
    from backend.engine.security import is_safe_path

    data_dir = context.get("data_dir", "")
    base_dir = context.get("base_dir", "")
    # Build the same allowed_dirs list as InputDataNode, including user-trusted paths.
    _allowed_dirs = [d for d in [data_dir, base_dir] if d] + _load_extra_data_dirs()

    con = duckdb.connect()  # per-run in-memory connection
    # Prevent hanging on large/slow files (e.g. OneDrive-backed CSVs).
    try:
        con.execute("SET query_timeout = 300000")  # 300 s in ms (DuckDB ≥ 0.9)
    except Exception:
        pass  # Older DuckDB versions may not support this setting
    table_mappings: Dict[str, str] = {}
    start_time = time.time()

    # ------------------------------------------------------------------
    # 1. Register input_data files as DuckDB views
    # ------------------------------------------------------------------
    for node in active_nodes:
        if node["type"] != "input_data":
            continue

        node_id = node["id"]
        file_path = _resolve_input_file(node["config"], data_dir, base_dir)
        if not file_path:
            _warn(result, f"DuckDB fast-path: cannot resolve file for '{node.get('name', node_id)}'. Falling back.")
            return False

        # Enforce the same directory allow-list as InputDataNode.
        if _allowed_dirs and not is_safe_path(file_path, _allowed_dirs):
            _warn(result, f"DuckDB fast-path: '{node.get('name', node_id)}' is outside trusted directories. Falling back.")
            return False

        fmt = detect_format(file_path)
        view_name = f"src_{re.sub(r'[^\\w]', '_', node_id)}"
        safe_path = file_path.replace("\\", "/")

        try:
            if fmt == "parquet":
                con.execute(f"CREATE VIEW {view_name} AS SELECT * FROM read_parquet('{safe_path}')")
            elif fmt == "json":
                con.execute(f"CREATE VIEW {view_name} AS SELECT * FROM read_json_auto('{safe_path}')")
            else:
                # CSV / TSV — DuckDB auto-detects delimiter, header, types
                con.execute(f"CREATE VIEW {view_name} AS SELECT * FROM read_csv_auto('{safe_path}')")
        except Exception as exc:
            _warn(result, f"DuckDB fast-path: could not register '{os.path.basename(file_path)}': {exc}. Falling back.")
            return False

        table_mappings[node_id] = view_name

    # ------------------------------------------------------------------
    # 2. Compile workflow to DuckDB CTE SQL
    # ------------------------------------------------------------------
    try:
        compile_result = compile_workflow_to_sql(
            workflow,
            dialect="duckdb",
            options={"table_mappings": table_mappings, "include_comments": False},
        )
    except Exception as exc:
        _warn(result, f"DuckDB fast-path: SQL compilation failed: {exc}. Falling back.")
        return False

    if not compile_result.get("success") or not compile_result.get("compiled_ctes"):
        return False

    compiled_ctes: List[Dict[str, Any]] = compile_result["compiled_ctes"]
    node_cte_map: Dict[str, Dict[str, str]] = compile_result.get("node_cte_map", {})

    # ------------------------------------------------------------------
    # 3. Materialize each CTE as a DuckDB TEMP TABLE (topological order)
    #    Each CTE body references either source views or previously created tables.
    # ------------------------------------------------------------------
    try:
        for cte in compiled_ctes:
            con.execute(f"CREATE TEMP TABLE {cte['cte_name']} AS {cte['query']}")
    except Exception as exc:
        _warn(result, f"DuckDB fast-path: materialization failed: {exc}. Falling back.")
        current_run_cache.clear()
        return False

    # ------------------------------------------------------------------
    # 4. Read node outputs from materialized tables → populate cache
    # ------------------------------------------------------------------
    try:
        for node in active_nodes:
            node_id = node["id"]
            ntype = node["type"]

            if ntype in ("tool_container", "comment"):
                continue

            node_start = time.time()

            if ntype == "input_data":
                view_name = table_mappings.get(node_id)
                if not view_name:
                    continue
                df = con.execute(f"SELECT * FROM {view_name}").df()
                _record_node_success(result, current_run_cache, node, {"O": df},
                                     (time.time() - node_start) * 1000, observer_cb)

            elif ntype == "output_data":
                # Find the upstream connection into this output node
                in_edges = [
                    c for c in active_connections
                    if (c.get("target") or c.get("to_node")) == node_id
                ]
                if not in_edges:
                    continue

                edge = in_edges[0]
                src_id = edge.get("source") or edge.get("from_node")
                src_port = edge.get("sourceHandle") or edge.get("from_port", "O")

                # Pull upstream DataFrame from cache (already populated above)
                upstream = current_run_cache.get(src_id)
                if isinstance(upstream, dict):
                    df = upstream.get(src_port) or upstream.get("O", pd.DataFrame())
                else:
                    df = pd.DataFrame()

                out_node = OutputDataNode(node_id, node["config"])
                outputs = out_node.execute({"I": df}, context)
                _record_node_success(result, current_run_cache, node, outputs,
                                     (time.time() - node_start) * 1000, observer_cb)

            else:
                # Transform node — read from its materialized temp table(s)
                port_map = node_cte_map.get(node_id, {})
                if not port_map:
                    continue

                port_dfs: Dict[str, pd.DataFrame] = {
                    port: con.execute(f"SELECT * FROM {cte_name}").df()
                    for port, cte_name in port_map.items()
                }
                _record_node_success(result, current_run_cache, node, port_dfs,
                                     (time.time() - node_start) * 1000, observer_cb)

    except Exception as exc:
        _warn(result, f"DuckDB fast-path: execution failed: {exc}. Falling back to pandas engine.")
        current_run_cache.clear()
        return False

    result.total_duration_ms = (time.time() - start_time) * 1000
    result.success = True
    n_tools = len([n for n in active_nodes if n["type"] not in ("tool_container", "comment")])
    result.logs.append({
        "time": time.strftime("%H:%M:%S"),
        "level": "INFO",
        "message": (
            f"Workflow completed via DuckDB fast-path in "
            f"{result.total_duration_ms:.1f}ms ({n_tools} tools)."
        ),
    })
    return True


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _warn(result, message: str) -> None:
    result.logs.append({"time": time.strftime("%H:%M:%S"), "level": "WARN", "message": message})


def _record_node_success(
    result,
    current_run_cache,
    node: Dict[str, Any],
    outputs: Dict[str, pd.DataFrame],
    duration_ms: float,
    observer_cb: Optional[Any],
) -> None:
    node_id = node["id"]
    ntype = node["type"]
    nname = node.get("name") or ntype

    sanitized: Dict[str, pd.DataFrame] = {}
    record_counts: Dict[str, int] = {}
    columns: Dict[str, List] = {}
    column_meta: Dict[str, List] = {}

    for port, df in outputs.items():
        if isinstance(df, pd.DataFrame):
            clean = sanitize_dataframe(df)
            sanitized[port] = clean
            record_counts[port] = len(clean)
            columns[port] = list(clean.columns)
            column_meta[port] = _build_column_meta(clean)
        else:
            sanitized[port] = df
            record_counts[port] = 0
            columns[port] = []
            column_meta[port] = []

    current_run_cache[node_id] = sanitized

    node_res = {
        "id": node_id,
        "type": ntype,
        "name": nname,
        "status": "success",
        "duration_ms": round(duration_ms, 2),
        "record_counts": record_counts,
        "columns": columns,
        "column_meta": column_meta,
        "error": None,
    }
    result.node_results[node_id] = node_res

    if observer_cb:
        try:
            observer_cb({
                "event": "node_completed",
                "run_id": result.run_id,
                "node_id": node_id,
                "node_name": nname,
                "name": nname,
                "node_type": ntype,
                "type": ntype,
                "status": "success",
                "duration_ms": round(duration_ms, 2),
                "record_counts": record_counts,
                "columns": columns,
                "column_meta": column_meta,
            })
        except Exception:
            pass

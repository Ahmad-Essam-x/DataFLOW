"""
Execution & Node Data REST API Blueprint.
Handles workflow graph execution, SSE streaming, node cache locking,
profiling, chart aggregation, SQL transpilation, and column lineage.
"""
import io
import json
import time
import queue
import threading
import pandas as pd
from flask import Blueprint, request, jsonify, send_file, Response, stream_with_context

import backend.extensions as ext
from backend.engine.node_registry import TOOL_METADATA
from backend.engine.sql_compiler import compile_workflow_to_sql, DIALECT_REGISTRY
from backend.engine.security import sanitize_file_basename

bp = Blueprint("execution", __name__)


@bp.route("/api/tools", methods=["GET"])
def get_tools():
    """Returns available tools and their metadata for palette rendering."""
    return jsonify({"tools": TOOL_METADATA})


@bp.route("/api/run", methods=["POST"])
def run_workflow():
    """Executes the workflow graph."""
    data = request.get_json(silent=True)
    if not data or "nodes" not in data:
        return jsonify({"success": False, "error": "Invalid workflow payload."}), 400

    session_id = request.headers.get("X-Session-ID") or data.get("session_id")
    run_id = request.headers.get("X-Run-ID") or data.get("run_id")

    ctx = ext.executor.get_run_context(session_id)
    result = ctx.run(data, run_id=run_id)
    return jsonify(result.to_dict())


@bp.route("/api/run-stream", methods=["POST"])
def run_workflow_stream():
    """Executes the workflow graph and streams real-time execution milestones as Server-Sent Events."""
    data = request.get_json(silent=True)
    if not data or "nodes" not in data:
        return jsonify({"success": False, "error": "Invalid workflow payload."}), 400

    session_id = request.headers.get("X-Session-ID") or data.get("session_id")
    run_id = request.headers.get("X-Run-ID") or data.get("run_id")

    def generate_events():
        q = queue.Queue()

        def observer(event_dict):
            q.put(event_dict)

        def worker():
            try:
                ctx = ext.executor.get_run_context(session_id)
                ctx.run(data, observer_cb=observer, run_id=run_id)
            except Exception as e:
                q.put({
                    "event": "workflow_completed",
                    "run_id": run_id,
                    "session_id": session_id,
                    "success": False,
                    "error": str(e)
                })
            finally:
                q.put(None)  # Signal EOF

        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {json.dumps(item)}\n\n"

    response = Response(stream_with_context(generate_events()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@bp.route("/api/run-node", methods=["POST"])
def run_single_node():
    """Executes a single target node and any uncached upstream dependencies."""
    data = request.get_json(silent=True) or {}
    workflow = data.get("workflow") or data
    node_id = data.get("node_id")

    if not workflow or "nodes" not in workflow or not node_id:
        return jsonify({"success": False, "error": "Invalid payload: workflow and node_id required."}), 400

    session_id = request.headers.get("X-Session-ID") or data.get("session_id")
    run_id = request.headers.get("X-Run-ID") or data.get("run_id")
    force_rerun = data.get("force_rerun", True)

    ctx = ext.executor.get_run_context(session_id)
    result = ctx.run_node(
        workflow=workflow,
        node_id=node_id,
        run_id=run_id,
        force_rerun=force_rerun
    )
    return jsonify(result.to_dict())


@bp.route("/api/node-cache/lock", methods=["POST"])
def lock_node_cache():
    """Locks or unlocks intermediate outputs for a node."""
    data = request.get_json(silent=True) or {}
    node_id = data.get("node_id")
    locked = data.get("locked", True)

    if not node_id:
        return jsonify({"success": False, "error": "node_id is required."}), 400

    if locked:
        outs = ext.executor.data_cache.get(node_id) or ext.executor._local_data_cache.get(node_id)
        if outs:
            ext.executor.frozen_node_cache[node_id] = outs
            ext.executor.persist_locked_node(node_id, outs)
            count = sum(len(df) for df in outs.values() if isinstance(df, pd.DataFrame))
            return jsonify({
                "success": True,
                "locked": True,
                "node_id": node_id,
                "record_count": count,
                "message": f"Tool '{node_id}' output locked ({count:,} records)."
            })
        else:
            return jsonify({
                "success": True,
                "locked": True,
                "node_id": node_id,
                "record_count": 0,
                "message": f"Tool '{node_id}' marked as locked. It will freeze upon next execution."
            })
    else:
        ext.executor.clear_frozen_cache(node_id)
        return jsonify({
            "success": True,
            "locked": False,
            "node_id": node_id,
            "message": f"Tool '{node_id}' output unlocked."
        })


@bp.route("/api/cancel/<run_id>", methods=["POST"])
@bp.route("/api/cancel", methods=["POST"])
def cancel_workflow_execution(run_id=None):
    """Signals cancellation of an in-flight workflow run."""
    if not run_id and request.is_json:
        body = request.get_json(silent=True) or {}
        run_id = body.get("run_id")
    cancelled = ext.executor.cancel_run(run_id)
    return jsonify({
        "success": True,
        "cancelled": cancelled,
        "run_id": run_id,
        "message": "Cancellation signal sent." if cancelled else "No active run found to cancel."
    })


@bp.route("/api/node-cache/clear", methods=["POST"])
def clear_node_cache():
    """Clears frozen cached node outputs."""
    data = request.get_json(silent=True) or {}
    node_id = data.get("node_id")
    cleared = ext.executor.clear_frozen_cache(node_id)
    return jsonify({
        "success": True,
        "cleared": cleared,
        "node_id": node_id
    })


@bp.route("/api/node-cache/status", methods=["GET"])
def get_node_cache_status():
    """Returns list of currently cached/frozen node IDs."""
    return jsonify({
        "cached_node_ids": ext.executor.get_frozen_node_ids()
    })


@bp.route("/api/validate-node", methods=["POST"])
def validate_node():
    """Server-side pre-run configuration validation for a node."""
    data = request.get_json(silent=True) or {}
    node_type = data.get("type", "")
    config = data.get("config", {})
    from backend.engine.validation import validate_node_config
    is_valid, warnings = validate_node_config(node_type, config)
    return jsonify({
        "valid": is_valid,
        "warnings": warnings
    })


@bp.route("/api/node-data/<node_id>", methods=["GET"])
def get_node_data(node_id):
    """Fetches paginated intermediate data for a specific node and output port."""
    port = request.args.get("port", "O")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 100))
    search = request.args.get("search", "")
    sample_mode = request.args.get("sample_mode", "page")
    sort_by = request.args.get("sort_by")
    sort_dir = request.args.get("sort_dir", "asc")
    run_id = request.args.get("run_id") or request.headers.get("X-Run-ID")
    session_id = request.args.get("session_id") or request.headers.get("X-Session-ID")

    try:
        ctx = ext.executor.get_run_context(session_id)
        res = ctx.get_node_data(
            node_id=node_id,
            port=port,
            page=page,
            page_size=page_size,
            search=search,
            run_id=run_id,
            sample_mode=sample_mode,
            sort_by=sort_by,
            sort_dir=sort_dir
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({
            "available": False,
            "error": str(e),
            "message": f"Error retrieving node data: {str(e)}"
        }), 200


@bp.route("/api/node-profile/<node_id>", methods=["GET"])
def get_node_profiling(node_id):
    """Fetches column profiling statistics for a specific node and output port."""
    port = request.args.get("port", "O")
    run_id = request.args.get("run_id") or request.headers.get("X-Run-ID")
    session_id = request.args.get("session_id") or request.headers.get("X-Session-ID")
    try:
        ctx = ext.executor.get_run_context(session_id)
        res = ctx.get_node_profiling(node_id=node_id, port=port, run_id=run_id)
        return jsonify(res)
    except Exception as e:
        return jsonify({
            "available": False,
            "error": str(e),
            "message": f"Error profiling node: {str(e)}"
        }), 200


@bp.route("/api/node-profile/<node_id>/export-report", methods=["GET"])
def export_node_quality_report(node_id):
    """Generates and downloads a self-contained interactive HTML Quality Audit Report."""
    port = request.args.get("port", "O")
    run_id = request.args.get("run_id") or request.headers.get("X-Run-ID")
    session_id = request.args.get("session_id") or request.headers.get("X-Session-ID")
    title = request.args.get("title") or f"Data Quality Audit Report - Node {node_id}"

    try:
        ctx = ext.executor.get_run_context(session_id)
        prof_res = ctx.get_node_profiling(node_id=node_id, port=port, run_id=run_id)
        if not prof_res.get("available"):
            return jsonify({"error": "Profiling data not available for this node/port."}), 404

        from backend.engine.profiler import generate_html_report
        html_content = generate_html_report(prof_res, title=title)

        mem = io.BytesIO(html_content.encode("utf-8"))
        download_name = f"quality_report_{node_id}_{port}.html"
        return send_file(
            mem,
            mimetype="text/html",
            as_attachment=True,
            download_name=download_name
        )
    except Exception as e:
        return jsonify({"error": f"Failed to generate report: {str(e)}"}), 500


@bp.route("/api/node-chart-data/<node_id>", methods=["GET", "POST"])
def get_node_chart_data(node_id):
    """Fetches binned or aggregated data for interactive charts."""
    payload = request.get_json(silent=True) or {}
    port = request.args.get("port") or payload.get("port", "O")
    chart_type = request.args.get("chart_type") or payload.get("chart_type", "bar")
    x_col = request.args.get("x_col") or payload.get("x_col")
    y_col = request.args.get("y_col") or payload.get("y_col")
    agg_func = request.args.get("agg_func") or payload.get("agg_func", "count")
    num_bins = int(request.args.get("num_bins") or payload.get("num_bins", 15))
    run_id = request.args.get("run_id") or payload.get("run_id") or request.headers.get("X-Run-ID")
    session_id = request.args.get("session_id") or payload.get("session_id") or request.headers.get("X-Session-ID")

    try:
        ctx = ext.executor.get_run_context(session_id)
        res = ctx.get_node_chart_data(
            node_id=node_id,
            port=port,
            chart_type=chart_type,
            x_col=x_col,
            y_col=y_col,
            agg_func=agg_func,
            num_bins=num_bins,
            run_id=run_id
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({
            "available": False,
            "error": str(e),
            "message": f"Error preparing chart data: {str(e)}"
        }), 200


@bp.route("/api/cache/stats", methods=["GET"])
def get_cache_stats():
    """Returns runtime cache metrics, temp disk space used, and current memory consumption."""
    total_disk = ext.cache_manager.get_total_disk_bytes()
    runs_count = len(ext.cache_manager)
    mem_mb = 0.0
    try:
        import os
        import psutil
        process = psutil.Process(os.getpid())
        mem_mb = round(process.memory_info().rss / (1024 * 1024), 2)
    except Exception:
        pass

    return jsonify({
        "success": True,
        "runs_count": runs_count,
        "disk_bytes": total_disk,
        "disk_mb": round(total_disk / (1024 * 1024), 2),
        "process_memory_mb": mem_mb,
        "cache_root_dir": ext.cache_manager.cache_root_dir
    })


@bp.route("/api/cache/purge", methods=["POST"])
def purge_engine_cache():
    """Wipes all execution run caches, frozen node caches, and temporary disk files."""
    try:
        ext.cache_manager.purge_all()
        ext.executor.clear_frozen_cache()
        ext.executor.data_cache.clear()
        import gc
        gc.collect()

        mem_mb = 0.0
        try:
            import os
            import psutil
            process = psutil.Process(os.getpid())
            mem_mb = round(process.memory_info().rss / (1024 * 1024), 2)
        except Exception:
            pass

        return jsonify({
            "success": True,
            "message": "Engine cache, temporary disk files, and resident memory successfully purged.",
            "process_memory_mb": mem_mb
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"Error purging cache: {str(e)}"
        }), 500


@bp.route("/api/workflow/sql-dialects", methods=["GET"])
def get_sql_dialects():
    """Returns supported SQL dialects and their metadata."""
    dialects = [
        {"id": d.name, "name": d.display_name, "supports_try_cast": d.supports_try_cast, "supports_read_csv": d.supports_read_csv}
        for d in DIALECT_REGISTRY.values()
    ]
    return jsonify({"success": True, "dialects": dialects})


@bp.route("/api/workflow/to-sql", methods=["POST"])
def convert_workflow_to_sql():
    """Compiles a workflow DAG into an executable SQL script with CTEs."""
    data = request.get_json(silent=True) or {}
    workflow = data.get("workflow") or data
    dialect = data.get("dialect", "ansi")
    options = data.get("options", {})

    try:
        result = compile_workflow_to_sql(workflow, dialect=dialect, options=options)
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/workflow/to-sql/download", methods=["POST"])
def download_workflow_sql():
    """Exports and streams the transpiled workflow SQL script as an attachment."""
    data = request.get_json(silent=True) or {}
    sql = data.get("sql")
    filename = data.get("filename") or "workflow.sql"
    if not filename.endswith(".sql"):
        filename += ".sql"

    if not sql:
        workflow = data.get("workflow") or data
        dialect = data.get("dialect", "ansi")
        options = data.get("options", {})
        res = compile_workflow_to_sql(workflow, dialect=dialect, options=options)
        sql = res.get("sql", "")

    mem = io.BytesIO(sql.encode("utf-8"))
    return send_file(
        mem,
        mimetype="application/sql",
        as_attachment=True,
        download_name=sanitize_file_basename(filename)
    )


@bp.route("/api/workflow/lineage", methods=["POST"])
def compute_workflow_lineage():
    """Computes column-level lineage and downstream impact across the workflow DAG."""
    data = request.get_json(silent=True) or {}
    workflow = data.get("workflow") or data
    node_id = data.get("node_id")
    direction = data.get("direction", "upstream").lower().strip()
    column = data.get("column")

    try:
        from backend.engine.lineage import compute_lineage, compute_rich_lineage, compute_downstream_impact

        all_lineage = compute_lineage(workflow)

        if direction == "downstream" and node_id:
            impact_res = compute_downstream_impact(workflow, node_id, column_name=column)
            return jsonify({
                "success": True,
                "direction": "downstream",
                "node_id": node_id,
                "impacted_node_ids": impact_res.get("impacted_node_ids", []),
                "columns": impact_res.get("columns", {}),
                "lineage": {node_id: all_lineage.get(node_id, {})}
            })

        rich_res = compute_rich_lineage(workflow, target_node_id=node_id)
        return jsonify({
            "success": True,
            "direction": "upstream",
            "node_id": node_id,
            "lineage": {node_id: all_lineage.get(node_id, {})} if node_id else all_lineage,
            "rich_lineage": rich_res.get(node_id, {}) if node_id else rich_res
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

"""
Flask Application Entrypoint & REST API.
Serves the drag-and-drop web application and handles workflow execution,
file ingestion, data profiling, and exports.
"""
import os
import io
import json
import uuid
import re
import time
import werkzeug
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory, Response, stream_with_context
import pandas as pd

import sys
import shutil

from backend.engine.node_registry import TOOL_METADATA
from backend.engine.executor import WorkflowExecutor
from backend.engine.cache_manager import SessionRunCacheManager
from backend.engine.workflow_manager import WorkflowManager
from backend.engine.security import validate_safe_path, is_safe_path, sanitize_file_basename, validate_upload_file, SecurityError
from backend.samples.generator import ensure_sample_data
from backend.engine.sql_compiler import compile_workflow_to_sql, DIALECT_REGISTRY
from backend.engine.excel_reader import get_excel_sheet_names, get_excel_row_count, fast_read_excel


# Resolve base, bundle, and writable data directories for frozen bundle vs source
IS_FROZEN = getattr(sys, "frozen", False)
if IS_FROZEN:
    BUNDLE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    EXE_DIR = os.path.dirname(sys.executable)
    # Check if executable directory is writable for portable mode
    test_write = os.path.join(EXE_DIR, ".write_test")
    try:
        with open(test_write, "w") as f:
            f.write("1")
        os.remove(test_write)
        USER_DATA_ROOT = EXE_DIR
    except Exception:
        USER_DATA_ROOT = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AntigravityDataFlow")
        os.makedirs(USER_DATA_ROOT, exist_ok=True)

    BASE_DIR = USER_DATA_ROOT
    DATA_DIR = os.path.join(USER_DATA_ROOT, "data")
    OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
    WORKFLOWS_DIR = os.path.join(USER_DATA_ROOT, "workflows")
    STATIC_DIR = os.path.join(BUNDLE_DIR, "static")
    TEMPLATES_DIR = os.path.join(BUNDLE_DIR, "templates")

    BUNDLED_DATA_DIR = os.path.join(BUNDLE_DIR, "data")
    BUNDLED_WORKFLOWS_DIR = os.path.join(BUNDLE_DIR, "workflows")
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, "data")
    OUTPUT_DIR = os.path.join(DATA_DIR, "outputs")
    WORKFLOWS_DIR = os.path.join(BASE_DIR, "workflows")
    STATIC_DIR = os.path.join(BASE_DIR, "static")
    TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
    BUNDLED_DATA_DIR = DATA_DIR
    BUNDLED_WORKFLOWS_DIR = WORKFLOWS_DIR

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(WORKFLOWS_DIR, exist_ok=True)
WORKFLOW_TEMPLATES_DIR = os.path.join(WORKFLOWS_DIR, "templates")
WORKFLOW_TEMPLATES_USER_DIR = os.path.join(WORKFLOW_TEMPLATES_DIR, "user")
os.makedirs(WORKFLOW_TEMPLATES_DIR, exist_ok=True)
os.makedirs(WORKFLOW_TEMPLATES_USER_DIR, exist_ok=True)

# Copy pre-bundled sample datasets and workflows if running in frozen mode
if BUNDLED_DATA_DIR != DATA_DIR and os.path.exists(BUNDLED_DATA_DIR):
    for fn in os.listdir(BUNDLED_DATA_DIR):
        src = os.path.join(BUNDLED_DATA_DIR, fn)
        dst = os.path.join(DATA_DIR, fn)
        if os.path.isfile(src) and not os.path.exists(dst):
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass

if BUNDLED_WORKFLOWS_DIR != WORKFLOWS_DIR and os.path.exists(BUNDLED_WORKFLOWS_DIR):
    for fn in os.listdir(BUNDLED_WORKFLOWS_DIR):
        src = os.path.join(BUNDLED_WORKFLOWS_DIR, fn)
        dst = os.path.join(WORKFLOWS_DIR, fn)
        if os.path.isfile(src) and not os.path.exists(dst):
            try:
                shutil.copy2(src, dst)
            except Exception:
                pass

app = Flask(__name__, static_folder=STATIC_DIR, template_folder=TEMPLATES_DIR)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB max upload

# Initialize sample data and directories
ensure_sample_data(DATA_DIR, WORKFLOWS_DIR)

# Shared executor instance with execution context and isolated run cache manager
cache_manager = SessionRunCacheManager(max_runs=2, ttl_seconds=3600)
executor = WorkflowExecutor(context={
    "data_dir": DATA_DIR,
    "output_dir": OUTPUT_DIR,
    "base_dir": BASE_DIR
}, cache_manager=cache_manager)

# Workflow lifecycle, packaging, backup, and dependency manager
workflow_manager = WorkflowManager(
    workflows_dir=WORKFLOWS_DIR,
    data_dir=DATA_DIR,
    base_dir=BASE_DIR
)


# Global initial workflow to open on startup (set via CLI --open)
INITIAL_WORKFLOW_FILE = None

def set_initial_workflow(filepath_or_name):
    global INITIAL_WORKFLOW_FILE
    INITIAL_WORKFLOW_FILE = filepath_or_name


# ----------------------------------------------------------------------
# Web Views
# ----------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/data/outputs/<path:filename>")
def download_output_file(filename):
    """Direct download for files saved in data/outputs."""
    target_path = os.path.join(OUTPUT_DIR, filename)
    if not is_safe_path(target_path, [OUTPUT_DIR]):
        return jsonify({"error": "Forbidden: Path traversal is forbidden."}), 403
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


# ----------------------------------------------------------------------
# REST API Endpoints
# ----------------------------------------------------------------------
@app.route("/api/app-info", methods=["GET"])
def get_app_info():
    """Returns application runtime metadata and directory paths."""
    return jsonify({
        "app_name": "Antigravity DataFlow",
        "version": "2.1.0",
        "frozen": getattr(sys, "frozen", False),
        "data_dir": DATA_DIR,
        "workflows_dir": WORKFLOWS_DIR,
        "base_dir": BASE_DIR
    })


@app.route("/api/initial-workflow", methods=["GET"])
def get_initial_workflow():
    """Returns initial workflow specified via CLI --open or query parameter ?open=filename."""
    global INITIAL_WORKFLOW_FILE
    target = request.args.get("open") or INITIAL_WORKFLOW_FILE
    if not target:
        return jsonify({"workflow": None})

    candidate_paths = [
        target,
        os.path.join(WORKFLOWS_DIR, target),
        os.path.join(WORKFLOWS_DIR, target + (".json" if not target.endswith(".json") else ""))
    ]
    if hasattr(sys, "_MEIPASS"):
        candidate_paths.append(os.path.join(sys._MEIPASS, "workflows", target))
        candidate_paths.append(os.path.join(sys._MEIPASS, "workflows", target + (".json" if not target.endswith(".json") else "")))

    for p in candidate_paths:
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return jsonify({
                    "workflow": data,
                    "path": p,
                    "name": data.get("name", os.path.splitext(os.path.basename(p))[0])
                })
            except Exception as e:
                return jsonify({"workflow": None, "error": f"Failed to load workflow: {str(e)}"}), 400

    # Fallback: scan workflows directory for matching workflow name or clean slug
    clean_target = target.lower().replace(".json", "").replace("_", " ").strip()
    search_dirs = [WORKFLOWS_DIR]
    if hasattr(sys, "_MEIPASS"):
        search_dirs.append(os.path.join(sys._MEIPASS, "workflows"))

    for s_dir in search_dirs:
        if os.path.isdir(s_dir):
            for fn in os.listdir(s_dir):
                if fn.lower().endswith(".json"):
                    fp = os.path.join(s_dir, fn)
                    try:
                        with open(fp, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        wf_name = str(data.get("name", "")).lower().strip()
                        if wf_name == clean_target or clean_target in wf_name or wf_name in clean_target:
                            return jsonify({
                                "workflow": data,
                                "path": fp,
                                "name": data.get("name", os.path.splitext(fn)[0])
                            })
                    except Exception:
                        pass

    return jsonify({"workflow": None, "warning": f"Workflow '{target}' not found."})


@app.route("/api/tools", methods=["GET"])
def get_tools():
    """Returns available tools and their metadata for palette rendering."""
    return jsonify({"tools": TOOL_METADATA})


@app.route("/api/run", methods=["POST"])
def run_workflow():
    """Executes the workflow graph."""
    data = request.get_json(silent=True)
    if not data or "nodes" not in data:
        return jsonify({"success": False, "error": "Invalid workflow payload."}), 400

    session_id = request.headers.get("X-Session-ID") or data.get("session_id")
    run_id = request.headers.get("X-Run-ID") or data.get("run_id")

    result = executor.run(data, session_id=session_id, run_id=run_id)
    return jsonify(result.to_dict())


@app.route("/api/run-stream", methods=["POST"])
def run_workflow_stream():
    """Executes the workflow graph and streams real-time execution milestones as Server-Sent Events."""
    data = request.get_json(silent=True)
    if not data or "nodes" not in data:
        return jsonify({"success": False, "error": "Invalid workflow payload."}), 400

    session_id = request.headers.get("X-Session-ID") or data.get("session_id")
    run_id = request.headers.get("X-Run-ID") or data.get("run_id")

    def generate_events():
        import queue
        import threading
        q = queue.Queue()

        def observer(event_dict):
            q.put(event_dict)

        def worker():
            try:
                executor.run(data, observer_cb=observer, session_id=session_id, run_id=run_id)
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


@app.route("/api/cancel/<run_id>", methods=["POST"])
@app.route("/api/cancel", methods=["POST"])
def cancel_workflow_execution(run_id=None):
    """Signals cancellation of an in-flight workflow run."""
    if not run_id and request.is_json:
        body = request.get_json(silent=True) or {}
        run_id = body.get("run_id")
    cancelled = executor.cancel_run(run_id)
    return jsonify({
        "success": True,
        "cancelled": cancelled,
        "run_id": run_id,
        "message": "Cancellation signal sent." if cancelled else "No active run found to cancel."
    })


@app.route("/api/node-cache/clear", methods=["POST"])
def clear_node_cache():
    """Clears frozen cached node outputs."""
    data = request.get_json(silent=True) or {}
    node_id = data.get("node_id")
    cleared = executor.clear_frozen_cache(node_id)
    return jsonify({
        "success": True,
        "cleared": cleared,
        "node_id": node_id
    })


@app.route("/api/node-cache/status", methods=["GET"])
def get_node_cache_status():
    """Returns list of currently cached/frozen node IDs."""
    return jsonify({
        "cached_node_ids": executor.get_frozen_node_ids()
    })


@app.route("/api/validate-node", methods=["POST"])
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


@app.route("/api/node-data/<node_id>", methods=["GET"])
def get_node_data(node_id):
    """Fetches paginated intermediate data for a specific node and output port."""
    port = request.args.get("port", "O")
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 100))
    search = request.args.get("search", "")
    sample_mode = request.args.get("sample_mode", "page")
    run_id = request.args.get("run_id") or request.headers.get("X-Run-ID")
    session_id = request.args.get("session_id") or request.headers.get("X-Session-ID")

    try:
        res = executor.get_node_data(
            node_id=node_id,
            port=port,
            page=page,
            page_size=page_size,
            search=search,
            run_id=run_id,
            session_id=session_id,
            sample_mode=sample_mode
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({
            "available": False,
            "error": str(e),
            "message": f"Error retrieving node data: {str(e)}"
        }), 200


@app.route("/api/node-profile/<node_id>", methods=["GET"])
def get_node_profiling(node_id):
    """Fetches column profiling statistics for a specific node and output port."""
    port = request.args.get("port", "O")
    run_id = request.args.get("run_id") or request.headers.get("X-Run-ID")
    session_id = request.args.get("session_id") or request.headers.get("X-Session-ID")
    try:
        res = executor.get_node_profiling(node_id=node_id, port=port, run_id=run_id, session_id=session_id)
        return jsonify(res)
    except Exception as e:
        return jsonify({
            "available": False,
            "error": str(e),
            "message": f"Error profiling node: {str(e)}"
        }), 200


@app.route("/api/node-profile/<node_id>/export-report", methods=["GET"])
def export_node_quality_report(node_id):
    """Generates and downloads a self-contained interactive HTML Quality Audit Report."""
    port = request.args.get("port", "O")
    run_id = request.args.get("run_id") or request.headers.get("X-Run-ID")
    session_id = request.args.get("session_id") or request.headers.get("X-Session-ID")
    title = request.args.get("title") or f"Data Quality Audit Report - Node {node_id}"

    try:
        prof_res = executor.get_node_profiling(node_id=node_id, port=port, run_id=run_id, session_id=session_id)
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


@app.route("/api/node-chart-data/<node_id>", methods=["GET", "POST"])
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
        res = executor.get_node_chart_data(
            node_id=node_id,
            port=port,
            chart_type=chart_type,
            x_col=x_col,
            y_col=y_col,
            agg_func=agg_func,
            num_bins=num_bins,
            run_id=run_id,
            session_id=session_id
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({
            "available": False,
            "error": str(e),
            "message": f"Error preparing chart data: {str(e)}"
        }), 200


@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "available": False, "error": "Not Found", "message": str(e)}), 404
    return "Not Found", 404


@app.errorhandler(500)
def handle_500(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "available": False, "error": "Internal Server Error", "message": str(e)}), 500
    return "Internal Server Error", 500


@app.errorhandler(Exception)
def handle_global_exception(e):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "available": False, "error": type(e).__name__, "message": str(e)}), 500
    raise e


@app.route("/api/upload", methods=["POST"])
def upload_file():
    """Uploads a CSV or Excel file and inspects its schema & sheet list."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded."}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Empty filename."}), 400

    is_valid, err_msg = validate_upload_file(file.filename, request.content_length)
    if not is_valid:
        return jsonify({"success": False, "error": err_msg}), 400

    filename = sanitize_file_basename(file.filename, fallback="uploaded_data.csv")
    unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    save_path = os.path.join(DATA_DIR, unique_name)
    try:
        validate_safe_path(save_path, [DATA_DIR])
    except SecurityError as se:
        return jsonify({"success": False, "error": str(se)}), 403

    file.save(save_path)

    ext = os.path.splitext(filename)[1].lower()
    file_type = "excel" if ext in [".xlsx", ".xls", ".xlsm", ".xlsb"] else "csv"

    sheets = []
    columns = []
    row_count = 0
    preview_records = []
    detected_delimiter = ","

    try:
        if file_type == "excel":
            sheets = get_excel_sheet_names(save_path)
            first_sheet = sheets[0] if sheets else 0
            df_preview = fast_read_excel(save_path, sheet_name=first_sheet, nrows=10)
            if isinstance(df_preview, dict):
                df_preview = next(iter(df_preview.values())) if df_preview else pd.DataFrame()
            try:
                row_count = get_excel_row_count(save_path, sheet_name=first_sheet)
            except Exception:
                row_count = len(df_preview)
        else:
            if ext in [".tsv", ".tab"]:
                detected_delimiter = "\t"
            else:
                try:
                    with open(save_path, "r", encoding="utf-8", errors="replace") as f_sample:
                        first_line = f_sample.readline()
                        if "\t" in first_line and first_line.count("\t") > first_line.count(","):
                            detected_delimiter = "\t"
                        elif ";" in first_line and first_line.count(";") > first_line.count(","):
                            detected_delimiter = ";"
                        elif "|" in first_line and first_line.count("|") > first_line.count(","):
                            detected_delimiter = "|"
                except Exception:
                    pass

            try:
                df_preview = pd.read_csv(save_path, sep=detected_delimiter, nrows=10)
                with open(save_path, "r", encoding="utf-8") as f_in:
                    row_count = sum(1 for _ in f_in) - 1
            except UnicodeDecodeError:
                df_preview = pd.read_csv(save_path, sep=detected_delimiter, encoding="latin1", nrows=10)
                with open(save_path, "r", encoding="latin1") as f_in:
                    row_count = sum(1 for _ in f_in) - 1

        columns = [str(c) for c in df_preview.columns]
        preview_records = df_preview.fillna("").to_dict(orient="records")

    except Exception as e:
        return jsonify({"success": False, "error": f"Uploaded file could not be parsed: {str(e)}"}), 400

    return jsonify({
        "success": True,
        "file_name": unique_name,
        "original_name": filename,
        "file_type": file_type,
        "delimiter": detected_delimiter if file_type == "csv" else None,
        "sheets": sheets,
        "columns": columns,
        "row_count": max(0, row_count),
        "preview": preview_records
    })


@app.route("/api/export/<node_id>", methods=["GET"])
def export_node_data(node_id):
    """Downloads intermediate or final node output as CSV, Excel, TSV, or JSON."""
    port = request.args.get("port", "O")
    fmt = request.args.get("format", "csv").lower()
    custom_name = request.args.get("filename", "").strip()
    run_id = request.args.get("run_id") or request.headers.get("X-Run-ID")
    session_id = request.args.get("session_id") or request.headers.get("X-Session-ID")

    run_entry = executor.cache_manager.get_run(run_id=run_id, session_id=session_id)
    effective_cache = run_entry.data_cache if run_entry else executor.data_cache

    node_cache = effective_cache.get(node_id)
    if not node_cache or port not in node_cache:
        return jsonify({"error": "No cached data found for this node and port."}), 404

    df = node_cache[port]
    if not isinstance(df, pd.DataFrame):
        return jsonify({"error": "Data is not tabular."}), 400

    base_name = custom_name if custom_name else f"export_{node_id}_{port}"
    base_name = re.sub(r'[^\w\-_\.]', '_', base_name).strip()
    for ext_strip in [".csv", ".xlsx", ".xls", ".tsv", ".json"]:
        if base_name.lower().endswith(ext_strip):
            base_name = base_name[:-len(ext_strip)]
            break
    if not base_name:
        base_name = f"export_{node_id}_{port}"

    if fmt in ["excel", "xlsx"]:
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Export")
        output.seek(0)
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"{base_name}.xlsx"
        )
    elif fmt in ["tsv", "tab"]:
        output = io.StringIO()
        df.to_csv(output, index=False, sep="\t", encoding="utf-8")
        mem = io.BytesIO(output.getvalue().encode("utf-8"))
        mem.seek(0)
        return send_file(
            mem,
            mimetype="text/tab-separated-values",
            as_attachment=True,
            download_name=f"{base_name}.tsv"
        )
    elif fmt == "json":
        json_str = df.to_json(orient="records", indent=2)
        mem = io.BytesIO(json_str.encode("utf-8"))
        mem.seek(0)
        return send_file(
            mem,
            mimetype="application/json",
            as_attachment=True,
            download_name=f"{base_name}.json"
        )
    else:
        delim = request.args.get("delimiter", ",")
        if delim in ["\\t", "tab"]:
            delim = "\t"
        elif delim in ["pipe", "\\|"]:
            delim = "|"
        elif delim == "semicolon":
            delim = ";"
        output = io.StringIO()
        df.to_csv(output, index=False, sep=delim, encoding="utf-8")
        mem = io.BytesIO(output.getvalue().encode("utf-8"))
        mem.seek(0)
        return send_file(
            mem,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"{base_name}.csv"
        )


@app.route("/api/cache/stats", methods=["GET"])
def get_cache_stats():
    """Returns runtime cache metrics, temp disk space used, and current memory consumption."""
    total_disk = cache_manager.get_total_disk_bytes()
    runs_count = len(cache_manager)
    mem_mb = 0.0
    try:
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
        "cache_root_dir": cache_manager.cache_root_dir
    })


@app.route("/api/cache/purge", methods=["POST"])
def purge_engine_cache():
    """Wipes all execution run caches, frozen node caches, and temporary disk files."""
    try:
        cache_manager.purge_all()
        executor.clear_frozen_cache()
        executor.data_cache.clear()
        import gc
        gc.collect()

        mem_mb = 0.0
        try:
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


USER_SETTINGS_FILE = os.path.join(BASE_DIR, "user_settings.json")


@app.route("/api/user-settings", methods=["GET"])
def get_user_settings():
    """Returns the persisted user settings JSON, or {} if none exist yet."""
    if not os.path.exists(USER_SETTINGS_FILE):
        return jsonify({})
    try:
        with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": f"Failed to read settings: {str(e)}"}), 500


@app.route("/api/user-settings", methods=["POST"])
def save_user_settings():
    """Persists the user settings JSON to user_settings.json in the workspace root."""
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid or missing JSON body."}), 400
    if not isinstance(data, dict):
        return jsonify({"error": "Settings must be a JSON object."}), 400
    try:
        with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": f"Failed to save settings: {str(e)}"}), 500


@app.route("/api/browse", methods=["GET"])
def browse_directory():
    """Returns directory contents (folders and files) for the File Explorer dialog."""
    req_path = request.args.get("path", "").strip()

    root_dir = BASE_DIR

    if not req_path:
        target_dir = root_dir
    elif os.path.isabs(req_path):
        target_dir = req_path
    else:
        target_dir = os.path.normpath(os.path.join(root_dir, req_path))

    if not os.path.exists(target_dir) or not os.path.isdir(target_dir):
        target_dir = root_dir

    try:
        entries = sorted(os.listdir(target_dir))
    except Exception as e:
        return jsonify({"error": f"Unable to read directory: {str(e)}"}), 400

    folders = []
    files = []

    for item in entries:
        if item.startswith("."):
            continue
        full_p = os.path.join(target_dir, item)
        if os.path.isdir(full_p):
            folders.append({
                "name": item,
                "path": full_p.replace("\\", "/"),
                "is_dir": True
            })
        elif os.path.isfile(full_p):
            ext = os.path.splitext(item)[1].lower()
            try:
                size_bytes = os.path.getsize(full_p)
            except Exception:
                size_bytes = 0
            files.append({
                "name": item,
                "path": full_p.replace("\\", "/"),
                "is_dir": False,
                "size_kb": round(size_bytes / 1024, 1),
                "extension": ext
            })

    parent_dir = os.path.dirname(target_dir)
    has_parent = os.path.exists(parent_dir) and parent_dir != target_dir

    return jsonify({
        "success": True,
        "current_path": target_dir.replace("\\", "/"),
        "parent_path": parent_dir.replace("\\", "/") if has_parent else None,
        "workspace_root": root_dir.replace("\\", "/"),
        "data_dir": DATA_DIR.replace("\\", "/"),
        "output_dir": OUTPUT_DIR.replace("\\", "/"),
        "folders": folders,
        "files": files
    })


@app.route("/api/excel-sheets", methods=["GET"])
def get_excel_sheets():
    """Returns sheet names for a given Excel file path using openpyxl without loading data."""
    raw_file = request.args.get("file", "").strip()
    if not raw_file:
        return jsonify({"success": False, "error": "Query parameter 'file' is required."}), 400

    # Path resolution: check absolute or relative to DATA_DIR or BASE_DIR
    resolved_path = None
    if os.path.isabs(raw_file) and os.path.exists(raw_file):
        resolved_path = raw_file
    elif os.path.exists(os.path.join(DATA_DIR, raw_file)):
        resolved_path = os.path.join(DATA_DIR, raw_file)
    elif raw_file.startswith(("data/", "data\\")) and os.path.exists(os.path.join(DATA_DIR, raw_file[5:])):
        resolved_path = os.path.join(DATA_DIR, raw_file[5:])
    elif os.path.exists(os.path.join(BASE_DIR, raw_file)):
        resolved_path = os.path.join(BASE_DIR, raw_file)
    elif os.path.exists(raw_file):
        resolved_path = raw_file

    if not resolved_path:
        return jsonify({"success": False, "error": f"File '{raw_file}' not found."}), 404

    # Security check: must reside inside allowed workspace directories
    allowed_dirs = [d for d in [DATA_DIR, BASE_DIR, OUTPUT_DIR] if d]
    if not is_safe_path(resolved_path, allowed_dirs):
        return jsonify({"success": False, "error": "Access forbidden: path outside workspace."}), 403

    ext = os.path.splitext(resolved_path)[1].lower()
    if ext not in [".xlsx", ".xls", ".xlsm", ".xlsb"]:
        return jsonify({"success": False, "error": f"File is not an Excel workbook ({ext})."}), 400

    try:
        sheet_names = get_excel_sheet_names(resolved_path)
        return jsonify({
            "success": True,
            "file": raw_file,
            "resolved_path": resolved_path.replace("\\", "/"),
            "sheets": sheet_names
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to inspect Excel sheets: {str(e)}"}), 500


@app.route("/api/wildcard-preview", methods=["GET"])
def preview_wildcard_files():
    """Returns matching files and count for a wildcard pattern within workspace directories."""
    pattern = request.args.get("pattern", "").strip()
    if not pattern:
        return jsonify({"success": True, "count": 0, "files": []})

    import glob
    candidate_globs = []
    if os.path.isabs(pattern):
        candidate_globs.append(pattern)
    else:
        candidate_globs.append(pattern)
        if DATA_DIR:
            candidate_globs.append(os.path.join(DATA_DIR, pattern))
            if pattern.startswith(("data/", "data\\")):
                candidate_globs.append(os.path.join(DATA_DIR, pattern[5:]))
            candidate_globs.append(os.path.join(DATA_DIR, os.path.basename(pattern)))
        if BASE_DIR:
            candidate_globs.append(os.path.join(BASE_DIR, pattern))

    matched_files = []
    for g in candidate_globs:
        matches = glob.glob(g)
        if matches:
            matched_files.extend(matches)

    matched_files = sorted(list(dict.fromkeys(matched_files)))
    allowed_dirs = [d for d in [DATA_DIR, BASE_DIR, OUTPUT_DIR] if d]
    safe_matches = [f for f in matched_files if is_safe_path(f, allowed_dirs)]

    return jsonify({
        "success": True,
        "pattern": pattern,
        "count": len(safe_matches),
        "files": [os.path.basename(f) for f in safe_matches[:10]],
        "has_more": len(safe_matches) > 10
    })


@app.route("/api/samples", methods=["GET"])
def list_samples():
    """Lists available pre-loaded sample datasets and sample workflows."""
    curated_dataset_names = [
        "sales_orders.csv",
        "warehouse_inventory.xlsx",
        "quarterly_campaign_responses.csv",
        "customers.csv",
        "orders.xlsx"
    ]
    datasets = []
    for f in curated_dataset_names:
        path = os.path.join(DATA_DIR, f)
        if os.path.isfile(path):
            ext = os.path.splitext(f)[1].lower()
            size_kb = round(os.path.getsize(path) / 1024, 1)
            datasets.append({
                "name": f,
                "type": "excel" if ext in [".xlsx", ".xls"] else "csv",
                "size_kb": size_kb
            })

    curated_workflow_files = [
        "sales_customer_enrichment.json",
        "inventory_supplier_reconciliation.json",
        "marketing_campaign_attribution.json"
    ]
    all_wf_files = list(curated_workflow_files)
    if os.path.exists(WORKFLOWS_DIR):
        for f in sorted(os.listdir(WORKFLOWS_DIR)):
            if f.endswith(".json") and f not in all_wf_files:
                all_wf_files.append(f)

    workflows = []
    for f in all_wf_files:
        path = os.path.join(WORKFLOWS_DIR, f)
        if os.path.isfile(path):
            try:
                mtime = os.path.getmtime(path)
                with open(path, "r", encoding="utf-8") as wf_file:
                    wf_data = json.load(wf_file)
                    workflows.append({
                        "file": f,
                        "name": wf_data.get("name", f),
                        "description": wf_data.get("description", ""),
                        "node_count": len(wf_data.get("nodes", [])),
                        "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
                    })
            except Exception:
                pass

    return jsonify({"datasets": datasets, "workflows": workflows})


@app.route("/api/workflow/<filename>", methods=["GET"])
@app.route("/api/sample-workflow/<filename>", methods=["GET"])
def get_sample_workflow(filename):
    """Fetches a sample or saved workflow JSON."""
    safe_name = sanitize_file_basename(filename, fallback="workflow.json")
    path = os.path.join(WORKFLOWS_DIR, safe_name)
    if not is_safe_path(path, [WORKFLOWS_DIR]):
        return jsonify({"error": "Path traversal prohibited."}), 403
    if not os.path.exists(path):
        return jsonify({"error": "Workflow not found."}), 404

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return jsonify(data)


# ─── Template Library API ────────────────────────────────────────────────────

def _load_template_meta(filepath, is_user=False):
    """Helper: load template JSON and return its metadata dict."""
    try:
        with open(filepath, "r", encoding="utf-8-sig") as f:
            wf = json.load(f)
        fname = os.path.basename(filepath)
        node_names = [n.get("name", n.get("type", "")) for n in wf.get("nodes", [])]
        return {
            "id": os.path.splitext(fname)[0],
            "file": fname,
            "name": wf.get("name", fname),
            "description": wf.get("description", ""),
            "category": wf.get("category", "general"),
            "tags": wf.get("tags", []),
            "difficulty": wf.get("difficulty", "beginner"),
            "node_count": len(wf.get("nodes", [])),
            "nodes_preview": node_names[:6],
            "is_user": is_user,
            "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(filepath)))
        }
    except Exception:
        return None


@app.route("/api/templates", methods=["GET"])
def list_templates():
    """Returns all curated and user-saved workflow templates with metadata."""
    templates = []

    # Curated templates (from workflows/templates/, excluding user/ subdir)
    if os.path.isdir(WORKFLOW_TEMPLATES_DIR):
        for fname in sorted(os.listdir(WORKFLOW_TEMPLATES_DIR)):
            if not fname.endswith(".json"):
                continue
            meta = _load_template_meta(
                os.path.join(WORKFLOW_TEMPLATES_DIR, fname), is_user=False
            )
            if meta:
                templates.append(meta)

    # User-saved templates (from workflows/templates/user/)
    if os.path.isdir(WORKFLOW_TEMPLATES_USER_DIR):
        for fname in sorted(os.listdir(WORKFLOW_TEMPLATES_USER_DIR)):
            if not fname.endswith(".json"):
                continue
            meta = _load_template_meta(
                os.path.join(WORKFLOW_TEMPLATES_USER_DIR, fname), is_user=True
            )
            if meta:
                templates.append(meta)

    return jsonify({"templates": templates})


@app.route("/api/templates/save", methods=["POST"])
def save_template():
    """Saves current workflow as a user template."""
    body = request.get_json(force=True, silent=True) or {}
    name = str(body.get("name", "My Template")).strip()[:100]
    description = str(body.get("description", "")).strip()[:500]
    category = str(body.get("category", "general")).strip()
    tags = body.get("tags", [])
    workflow = body.get("workflow", {})

    if not name:
        return jsonify({"error": "Template name is required."}), 400
    if not isinstance(workflow, dict) or not workflow.get("nodes"):
        return jsonify({"error": "Workflow data with at least one node is required."}), 400

    workflow["name"] = name
    workflow["description"] = description
    workflow["category"] = category
    workflow["tags"] = tags if isinstance(tags, list) else []

    safe_stem = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")[:60]
    if not safe_stem:
        safe_stem = "user_template"
    fname = f"{safe_stem}.json"
    dest = os.path.join(WORKFLOW_TEMPLATES_USER_DIR, fname)

    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(WORKFLOW_TEMPLATES_USER_DIR, f"{safe_stem}_{counter}.json")
        counter += 1
    fname = os.path.basename(dest)

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)

    return jsonify({"success": True, "file": fname, "name": name})


@app.route("/api/templates/<filename>", methods=["GET"])
def get_template(filename):
    """Returns the full workflow JSON for a template by filename."""
    safe_name = sanitize_file_basename(filename, fallback="template.json")

    for search_dir in [WORKFLOW_TEMPLATES_DIR, WORKFLOW_TEMPLATES_USER_DIR]:
        path = os.path.join(search_dir, safe_name)
        if is_safe_path(path, [WORKFLOW_TEMPLATES_DIR]) and os.path.isfile(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            return jsonify(data)

    return jsonify({"error": "Template not found."}), 404


@app.route("/api/templates/<filename>", methods=["DELETE"])
def delete_template(filename):
    """Deletes a user-saved template (curated templates cannot be deleted)."""
    safe_name = sanitize_file_basename(filename, fallback="template.json")
    path = os.path.join(WORKFLOW_TEMPLATES_USER_DIR, safe_name)
    if not is_safe_path(path, [WORKFLOW_TEMPLATES_USER_DIR]):
        return jsonify({"error": "Path traversal prohibited."}), 403
    if not os.path.isfile(path):
        return jsonify({"error": "User template not found."}), 404
    os.remove(path)
    return jsonify({"success": True})


def show_native_save_dialog(default_name="workflow.json", initial_dir=None):
    """Opens native Windows Explorer Save As dialog via Tkinter in a safe thread."""
    import queue
    import threading
    q = queue.Queue()

    def _worker():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            root.focus_force()
            selected = filedialog.asksaveasfilename(
                parent=root,
                initialfile=default_name,
                initialdir=initial_dir or os.path.join(BASE_DIR, "workflows"),
                defaultextension=".json",
                filetypes=[
                    ("Workflow Files (*.json)", "*.json"),
                    ("Alteryx Workflow (*.yxmd)", "*.yxmd"),
                    ("All Files (*.*)", "*.*")
                ]
            )
            root.destroy()
            q.put(selected)
        except Exception as err:
            q.put(err)

    t = threading.Thread(target=_worker)
    t.daemon = True
    t.start()
    t.join(timeout=120.0)
    if t.is_alive():
        return None
    res = q.get() if not q.empty() else None
    if isinstance(res, Exception):
        raise res
    return res


def show_native_open_dialog(initial_dir=None):
    """Opens native Windows Explorer Open dialog via Tkinter in a safe thread."""
    import queue
    import threading
    q = queue.Queue()

    def _worker():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            root.focus_force()
            selected = filedialog.askopenfilename(
                parent=root,
                initialdir=initial_dir or os.path.join(BASE_DIR, "workflows"),
                filetypes=[
                    ("All Supported Workflow Formats", "*.json;*.yxmd;*.zip;*.yxzp"),
                    ("Workflow Files (*.json)", "*.json"),
                    ("Alteryx Workflow (*.yxmd)", "*.yxmd"),
                    ("Workflow Packages (*.zip, *.yxzp)", "*.zip;*.yxzp"),
                    ("All Files (*.*)", "*.*")
                ]
            )
            root.destroy()
            q.put(selected)
        except Exception as err:
            q.put(err)

    t = threading.Thread(target=_worker)
    t.daemon = True
    t.start()
    t.join(timeout=120.0)
    if t.is_alive():
        return None
    res = q.get() if not q.empty() else None
    if isinstance(res, Exception):
        raise res
    return res


@app.route("/api/save-workflow", methods=["POST"])
def save_workflow():
    """Saves workflow JSON locally with schema validation and automatic revision backup."""
    data = request.get_json(silent=True)
    if not data or "name" not in data:
        return jsonify({"success": False, "error": "Invalid workflow data."}), 400

    try:
        custom_file = request.args.get("file")
        target_path = data.get("target_filepath") or request.args.get("target_filepath")
        result = workflow_manager.save_workflow(data, custom_filename=custom_file, target_filepath=target_path)
        return jsonify(result)
    except SecurityError as se:
        return jsonify({"success": False, "error": str(se)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save workflow: {str(e)}"}), 500


@app.route("/api/dialog/save-file", methods=["POST"])
def handle_native_save_dialog():
    """Opens Windows Explorer Save As dialog on host system and saves workflow to chosen location."""
    data = request.get_json(silent=True) or {}
    wf_data = data.get("workflow") or data
    if not isinstance(wf_data, dict) or not wf_data:
        return jsonify({"success": False, "error": "Invalid workflow data."}), 400

    wf_name = wf_data.get("name", "workflow").strip()
    clean_stem = sanitize_file_basename(wf_name.replace(" ", "_").lower(), fallback="workflow")
    default_name = f"{clean_stem}.json"

    custom_handler = app.config.get("NATIVE_SAVE_DIALOG_HANDLER", show_native_save_dialog)
    try:
        chosen_path = custom_handler(default_name=default_name)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to launch Windows Explorer Save dialog: {str(e)}"}), 500

    if not chosen_path:
        return jsonify({"success": False, "cancelled": True})

    try:
        save_res = workflow_manager.save_workflow(wf_data, target_filepath=chosen_path)
        return jsonify(save_res)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save to '{chosen_path}': {str(e)}"}), 500


@app.route("/api/dialog/open-file", methods=["POST", "GET"])
def handle_native_open_dialog():
    """Opens Windows Explorer Open dialog on host system and loads selected workflow or package."""
    custom_handler = app.config.get("NATIVE_OPEN_DIALOG_HANDLER", show_native_open_dialog)
    try:
        chosen_path = custom_handler()
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to launch Windows Explorer Open dialog: {str(e)}"}), 500

    if not chosen_path:
        return jsonify({"success": False, "cancelled": True})

    ext = os.path.splitext(chosen_path)[1].lower()
    try:
        if ext in [".zip", ".yxzp"]:
            with open(chosen_path, "rb") as f:
                res = workflow_manager.import_package(f)
            return jsonify({
                "success": True,
                "is_package": True,
                "path": chosen_path.replace("\\", "/"),
                "filename": os.path.basename(chosen_path),
                **res
            })
        else:
            res = workflow_manager.load_from_path(chosen_path)
            return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to open workflow from '{chosen_path}': {str(e)}"}), 500


def show_native_output_save_dialog(default_name="output.csv", initial_dir=None, fmt="csv"):
    """Opens native Windows Explorer Save As dialog to pick an output path and format."""
    import queue
    import threading
    q = queue.Queue()

    fmt_lower = (fmt or "csv").lower()
    ext_map = {
        "csv": (".csv", [("CSV (Comma Delimited) (*.csv)", "*.csv"), ("All Files (*.*)", "*.*")]),
        "excel": (".xlsx", [("Excel Workbook (*.xlsx)", "*.xlsx"), ("All Files (*.*)", "*.*")]),
        "xlsx": (".xlsx", [("Excel Workbook (*.xlsx)", "*.xlsx"), ("All Files (*.*)", "*.*")]),
        "tsv": (".tsv", [("Tab-Delimited (*.tsv)", "*.tsv"), ("Text Files (*.txt)", "*.txt"), ("All Files (*.*)", "*.*")]),
        "json": (".json", [("JSON Files (*.json)", "*.json"), ("All Files (*.*)", "*.*")]),
        "parquet": (".parquet", [("Apache Parquet (*.parquet)", "*.parquet"), ("All Files (*.*)", "*.*")]),
    }
    def_ext, file_types = ext_map.get(fmt_lower, (".csv", [("CSV Files (*.csv)", "*.csv"), ("All Files (*.*)", "*.*")]))

    if not os.path.splitext(default_name)[1]:
        default_name = f"{default_name}{def_ext}"

    def _worker():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            root.focus_force()
            selected = filedialog.asksaveasfilename(
                parent=root,
                initialfile=default_name,
                initialdir=initial_dir or OUTPUT_DIR,
                defaultextension=def_ext,
                filetypes=file_types
            )
            root.destroy()
            q.put(selected)
        except Exception as err:
            q.put(err)

    t = threading.Thread(target=_worker)
    t.daemon = True
    t.start()
    t.join(timeout=120.0)
    if t.is_alive():
        return None
    res = q.get() if not q.empty() else None
    if isinstance(res, Exception):
        raise res
    return res


def show_native_folder_dialog(initial_dir=None):
    """Opens native Windows Explorer Folder selection dialog via Tkinter."""
    import queue
    import threading
    q = queue.Queue()

    def _worker():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            root.focus_force()
            selected = filedialog.askdirectory(
                parent=root,
                initialdir=initial_dir or OUTPUT_DIR,
                mustexist=False
            )
            root.destroy()
            q.put(selected)
        except Exception as err:
            q.put(err)

    t = threading.Thread(target=_worker)
    t.daemon = True
    t.start()
    t.join(timeout=120.0)
    if t.is_alive():
        return None
    res = q.get() if not q.empty() else None
    if isinstance(res, Exception):
        raise res
    return res


@app.route("/api/dialog/pick-output-path", methods=["POST"])
def handle_native_pick_output_path():
    """Opens Windows Explorer Save As dialog for picking target output file and destination path."""
    data = request.get_json(silent=True) or {}
    fmt = data.get("format", "csv")
    default_name = data.get("default_name") or data.get("filename") or "export_result"
    initial_dir = data.get("initial_dir") or data.get("output_dir") or OUTPUT_DIR

    custom_handler = app.config.get("NATIVE_OUTPUT_SAVE_HANDLER", show_native_output_save_dialog)
    try:
        chosen_path = custom_handler(default_name=default_name, initial_dir=initial_dir, fmt=fmt)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to launch Windows Explorer Save dialog: {str(e)}"}), 500

    if not chosen_path:
        return jsonify({"success": False, "cancelled": True})

    chosen_path = os.path.normpath(chosen_path)
    output_dir = os.path.dirname(chosen_path)
    base_file = os.path.basename(chosen_path)
    stem, ext = os.path.splitext(base_file)

    ext_clean = ext.lower().lstrip(".")
    detected_fmt = None
    if ext_clean in ["csv", "xlsx", "xls", "tsv", "json", "parquet"]:
        detected_fmt = "excel" if ext_clean in ["xlsx", "xls"] else ext_clean

    return jsonify({
        "success": True,
        "path": chosen_path.replace("\\", "/"),
        "raw_path": chosen_path,
        "directory": output_dir.replace("\\", "/"),
        "filename": stem or base_file,
        "full_filename": base_file,
        "extension": ext,
        "detected_format": detected_fmt
    })


@app.route("/api/dialog/pick-folder", methods=["POST"])
def handle_native_pick_folder():
    """Opens Windows Explorer Directory picker dialog on host system."""
    data = request.get_json(silent=True) or {}
    initial_dir = data.get("initial_dir") or data.get("output_dir") or OUTPUT_DIR

    custom_handler = app.config.get("NATIVE_FOLDER_DIALOG_HANDLER", show_native_folder_dialog)
    try:
        chosen_path = custom_handler(initial_dir=initial_dir)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to launch Windows Explorer Folder dialog: {str(e)}"}), 500

    if not chosen_path:
        return jsonify({"success": False, "cancelled": True})

    chosen_path = os.path.normpath(chosen_path)
    return jsonify({
        "success": True,
        "path": chosen_path.replace("\\", "/"),
        "raw_path": chosen_path
    })


@app.route("/api/open-in-explorer", methods=["POST"])
def handle_open_in_explorer():
    """Opens Windows Explorer highlighting the target file or directory on host OS."""
    data = request.get_json(silent=True) or {}
    target_path = data.get("path")
    if not target_path:
        return jsonify({"success": False, "error": "Missing 'path' parameter."}), 400

    # Clean / resolve path
    if not os.path.isabs(target_path):
        candidates = [
            os.path.join(OUTPUT_DIR, target_path),
            os.path.join(DATA_DIR, target_path),
            os.path.join(BASE_DIR, target_path),
        ]
        resolved = None
        for c in candidates:
            if os.path.exists(c):
                resolved = c
                break
        if not resolved:
            resolved = os.path.join(OUTPUT_DIR, target_path)
    else:
        resolved = target_path

    resolved = os.path.normpath(resolved)
    custom_launcher = app.config.get("NATIVE_EXPLORER_LAUNCHER")
    if custom_launcher:
        try:
            custom_launcher(resolved)
            return jsonify({"success": True, "path": resolved.replace("\\", "/")})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    try:
        import platform
        import subprocess

        system = platform.system()
        if system == "Windows":
            if os.path.isfile(resolved):
                subprocess.Popen(f'explorer /select,"{resolved}"')
            elif os.path.isdir(resolved):
                os.startfile(resolved)
            else:
                parent = os.path.dirname(resolved)
                if os.path.exists(parent):
                    os.startfile(parent)
                else:
                    return jsonify({"success": False, "error": f"Path '{resolved}' does not exist on disk."}), 404
        elif system == "Darwin":
            if os.path.isfile(resolved):
                subprocess.Popen(["open", "-R", resolved])
            else:
                subprocess.Popen(["open", resolved if os.path.isdir(resolved) else os.path.dirname(resolved)])
        else:
            folder = resolved if os.path.isdir(resolved) else os.path.dirname(resolved)
            subprocess.Popen(["xdg-open", folder])

        return jsonify({"success": True, "path": resolved.replace("\\", "/")})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to launch file explorer: {str(e)}"}), 500



@app.route("/api/workflow/export-package", methods=["POST"])
def export_workflow_package():
    """Packages workflow definition and referenced data files into a downloadable .zip archive."""
    data = request.get_json(silent=True)
    if not data or "name" not in data:
        return jsonify({"success": False, "error": "Invalid workflow payload."}), 400

    raw_name = data.get("name", "workflow_package").strip()
    clean_stem = sanitize_file_basename(raw_name.replace(" ", "_").lower(), fallback="workflow")
    zip_download_name = f"{clean_stem}_package.zip"

    try:
        zip_buf = workflow_manager.export_package(data)
        return send_file(
            zip_buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name=zip_download_name
        )
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to generate workflow package: {str(e)}"}), 500


@app.route("/api/workflow/import-package", methods=["POST"])
def import_workflow_package():
    """Uploads and unpacks a workflow package (.zip / .yxzp) into data and workflows directories."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No package file uploaded."}), 400

    uploaded = request.files["file"]
    if not uploaded or not uploaded.filename:
        return jsonify({"success": False, "error": "Empty filename."}), 400

    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in [".zip", ".yxzp"]:
        return jsonify({"success": False, "error": f"Unsupported package extension ({ext}). Use .zip or .yxzp."}), 400

    try:
        result = workflow_manager.import_package(uploaded.stream)
        return jsonify(result)
    except SecurityError as se:
        return jsonify({"success": False, "error": str(se)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to import package: {str(e)}"}), 400


@app.route("/api/workflow/dependencies", methods=["POST"])
def inspect_workflow_dependencies():
    """Inspects external data assets referenced in a workflow payload."""
    data = request.get_json(silent=True) or {}
    try:
        result = workflow_manager.inspect_dependencies(data)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/workflow/<filename>/revisions", methods=["GET"])
def get_workflow_revisions(filename):
    """Lists historical timestamped backups for a workflow file."""
    try:
        revisions = workflow_manager.get_revisions(filename)
        return jsonify({"success": True, "filename": filename, "revisions": revisions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/workflow/<filename>/revert", methods=["POST"])
def revert_workflow_revision(filename):
    """Reverts a workflow to a chosen timestamped revision snapshot."""
    data = request.get_json(silent=True) or {}
    backup_file = data.get("backup_file") or request.args.get("backup_file")
    if not backup_file:
        return jsonify({"success": False, "error": "Missing 'backup_file' parameter."}), 400

    try:
        result = workflow_manager.revert_revision(filename, backup_file)
        return jsonify(result)
    except SecurityError as se:
        return jsonify({"success": False, "error": str(se)}), 403
    except FileNotFoundError as fe:
        return jsonify({"success": False, "error": str(fe)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to revert revision: {str(e)}"}), 500


@app.route("/api/workflow/autosave", methods=["GET", "POST", "DELETE"])
def handle_workflow_autosave():
    """Manages active session autosaves for crash recovery."""
    session_id = request.headers.get("X-Session-ID") or request.args.get("session_id") or "default_session"

    if request.method == "POST":
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"success": False, "error": "Invalid autosave payload."}), 400
        res = workflow_manager.save_autosave(session_id, data)
        return jsonify(res)

    elif request.method == "GET":
        saved = workflow_manager.get_autosave(session_id)
        if saved:
            return jsonify({"success": True, "available": True, "workflow": saved})
        return jsonify({"success": True, "available": False, "workflow": None})

    elif request.method == "DELETE":
        cleared = workflow_manager.clear_autosave(session_id)
        return jsonify({"success": True, "cleared": cleared})


# ----------------------------------------------------------------------
# Workflow-to-SQL Transpilation & Pushdown Endpoints
# ----------------------------------------------------------------------
@app.route("/api/workflow/sql-dialects", methods=["GET"])
def get_sql_dialects():
    """Returns supported SQL dialects and their metadata."""
    dialects = [
        {"id": d.name, "name": d.display_name, "supports_try_cast": d.supports_try_cast, "supports_read_csv": d.supports_read_csv}
        for d in DIALECT_REGISTRY.values()
    ]
    return jsonify({"success": True, "dialects": dialects})


@app.route("/api/workflow/to-sql", methods=["POST"])
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


@app.route("/api/workflow/to-sql/download", methods=["POST"])
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


# ----------------------------------------------------------------------
# AI / LLM Tool Endpoints
# ----------------------------------------------------------------------
@app.route("/api/ai/providers", methods=["GET"])
def api_ai_providers():
    """Returns available LLM provider definitions."""
    try:
        from backend.engine.ai.provider_registry import list_providers
        return jsonify({"success": True, "providers": list_providers()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/ai/test-connection", methods=["POST"])
def api_ai_test_connection():
    """Tests connection to an LLM provider (Ollama, OpenAI, Gemini, etc.)."""
    try:
        from backend.engine.ai.provider_registry import get_provider
        data = request.get_json(silent=True) or {}
        provider_type = data.get("provider_type", "ollama")
        connection = data.get("connection", {})
        provider = get_provider(provider_type, connection)
        result = provider.test_connection()
        return jsonify({
            "success": result.success,
            "message": result.message,
            "models_available": result.models_available,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Connection test failed: {str(e)}",
            "models_available": 0,
        }), 200


@app.route("/api/ai/models", methods=["GET", "POST"])
def api_ai_models():
    """Lists available models from the target provider."""
    try:
        from backend.engine.ai.provider_registry import get_provider
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            provider_type = data.get("provider_type", "ollama")
            connection = data.get("connection", {})
        else:
            provider_type = request.args.get("provider", "ollama")
            connection = {
                "base_url": request.args.get("base_url", ""),
                "api_key": request.args.get("api_key", ""),
            }
        provider = get_provider(provider_type, connection)
        models = provider.list_models()
        return jsonify({
            "success": True,
            "models": [
                {
                    "name": m.name,
                    "size": m.size,
                    "family": m.family,
                    "context_length": m.context_length,
                }
                for m in models
            ],
        })
    except Exception as e:
        return jsonify({"success": False, "models": [], "error": str(e)}), 200


@app.route("/api/ai/preview-prompt", methods=["POST"])
def api_ai_preview_prompt():
    """Renders user & system prompt templates against sample rows for preview."""
    try:
        from backend.engine.ai.prompt_renderer import preview_prompts
        data = request.get_json(silent=True) or {}
        template = data.get("user_prompt_template", "")
        system_prompt = data.get("system_prompt", "")
        rag_context = data.get("rag_context", {})
        sample_rows = data.get("sample_data", [])

        if sample_rows:
            sample_df = pd.DataFrame(sample_rows)
        else:
            node_id = data.get("node_id")
            sample_df = pd.DataFrame()
            if node_id:
                df = executor.cache_manager.get_dataframe(node_id)
                if df is not None and not df.empty:
                    sample_df = df.head(5)

        if sample_df.empty:
            return jsonify({
                "success": False,
                "previews": [],
                "message": "No sample data available to preview. Run upstream node first or provide sample data.",
            })

        previews = preview_prompts(template, system_prompt, sample_df, rag_context, n=3)
        return jsonify({"success": True, "previews": previews})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500




# ----------------------------------------------------------------------
# Local Server Runner Helper
# ----------------------------------------------------------------------
def find_available_port(start_port=5000, max_tries=20):
    import socket
    for p in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    return start_port


def start_server(port=5000, open_browser=True, server="waitress", threads=8):
    import webbrowser
    import threading

    # Automatically find free port if initial port is occupied
    actual_port = find_available_port(port)

    def open_web():
        import time
        time.sleep(1.2)
        webbrowser.open(f"http://127.0.0.1:{actual_port}")

    if open_browser:
        threading.Thread(target=open_web, daemon=True).start()

    server_type = server.lower() if server else "waitress"
    print(f"==================================================")
    print(f"  Antigravity DataFlow (Alteryx-like Local App)   ")
    print(f"  Running locally at: http://127.0.0.1:{actual_port}      ")
    print(f"  WSGI Server: {server_type.capitalize()} (Threads: {threads})")
    print(f"  Press Ctrl+C in this console to stop the server ")
    print(f"==================================================")

    if server_type == "waitress":
        try:
            from waitress import serve
            serve(
                app,
                host="127.0.0.1",
                port=actual_port,
                threads=threads,
                connection_limit=200,
                channel_timeout=120
            )
            return
        except ImportError:
            print("Waitress not installed, falling back to Flask development server.")

    app.run(host="127.0.0.1", port=actual_port, debug=False)


if __name__ == "__main__":
    start_server(port=5000, open_browser=True)

"""
Files, Uploads & Dataset Previews REST API Blueprint.
Handles CSV/Excel file uploads, schema inspections, sheet listings,
directory browsing, sample datasets, and data exports.
"""
import os
import io
import re
import uuid
import time
import pandas as pd
from flask import Blueprint, request, jsonify, send_file, send_from_directory

import backend.extensions as ext
from backend.engine.node_registry import infer_alteryx_type, map_alteryx_to_category
from backend.engine.security import (
    validate_safe_path,
    is_safe_path,
    sanitize_file_basename,
    validate_upload_file,
    SecurityError
)
from backend.engine.excel_reader import get_excel_sheet_names, get_excel_row_count, fast_read_excel
from backend.engine.io_formats import (
    detect_format,
    read_tabular_file,
    filter_dataframe_by_search,
    export_dataframe_to_stream,
    get_format_extension,
    SUPPORTED_FORMATS
)

bp = Blueprint("files", __name__)


@bp.route("/data/outputs/<path:filename>")
def download_output_file(filename):
    """Direct download for files saved in data/outputs."""
    target_path = os.path.join(ext.OUTPUT_DIR, filename)
    if not is_safe_path(target_path, [ext.OUTPUT_DIR]):
        return jsonify({"error": "Forbidden: Path traversal is forbidden."}), 403
    return send_from_directory(ext.OUTPUT_DIR, filename, as_attachment=True)


@bp.route("/api/upload", methods=["POST"])
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
    save_path = os.path.join(ext.DATA_DIR, unique_name)
    try:
        validate_safe_path(save_path, [ext.DATA_DIR])
    except SecurityError as se:
        return jsonify({"success": False, "error": str(se)}), 403

    file.save(save_path)

    extension = os.path.splitext(filename)[1].lower()
    file_type = detect_format(filename)

    sheets = []
    columns = []
    row_count = 0
    preview_records = []
    detected_delimiter = "\t" if file_type == "tsv" else ","

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
        elif file_type == "parquet":
            df_preview = read_tabular_file(save_path, format_hint="parquet", max_rows=10)
            try:
                import pyarrow.parquet as pq
                row_count = pq.read_metadata(save_path).num_rows
            except Exception:
                try:
                    row_count = len(pd.read_parquet(save_path))
                except Exception:
                    row_count = len(df_preview)
        elif file_type == "json":
            df_preview = read_tabular_file(save_path, format_hint="json", max_rows=10)
            try:
                full_json_df = read_tabular_file(save_path, format_hint="json")
                row_count = len(full_json_df)
            except Exception:
                row_count = len(df_preview)
        else:
            if extension in [".tsv", ".tab"]:
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

            df_preview = read_tabular_file(
                save_path,
                format_hint="csv",
                delimiter=detected_delimiter,
                max_rows=10
            )
            try:
                with open(save_path, "r", encoding="utf-8", errors="replace") as f_in:
                    row_count = max(0, sum(1 for _ in f_in) - 1)
            except Exception:
                row_count = len(df_preview)

        columns = [str(c) for c in df_preview.columns]
        meta_list = []
        for col in df_preview.columns:
            s = df_preview[col]
            alt_t = infer_alteryx_type(s)
            cat = map_alteryx_to_category(alt_t)
            meta_list.append({
                "name": str(col),
                "type": cat,
                "alteryx_type": alt_t,
                "dtype": alt_t
            })
        preview_records = df_preview.fillna("").to_dict(orient="records")

    except Exception as e:
        return jsonify({"success": False, "error": f"Uploaded file could not be parsed: {str(e)}"}), 400

    return jsonify({
        "success": True,
        "file_name": unique_name,
        "original_name": filename,
        "file_type": "csv" if file_type == "tsv" else file_type,
        "delimiter": detected_delimiter if file_type in ["csv", "tsv"] else None,
        "sheets": sheets,
        "columns": columns,
        "column_meta": meta_list,
        "row_count": max(0, row_count),
        "preview": preview_records
    })



@bp.route("/api/export/<node_id>", methods=["GET"])
def export_node_data(node_id):
    """Downloads intermediate or final node output as CSV, Excel, TSV, JSON, or Parquet."""
    port = request.args.get("port", "O")
    fmt = request.args.get("format", "csv").lower()
    custom_name = request.args.get("filename", "").strip()
    sort_by = request.args.get("sort_by")
    sort_dir = request.args.get("sort_dir", "asc")
    search = request.args.get("search", "").strip()
    delim = request.args.get("delimiter", ",")
    run_id = request.args.get("run_id") or request.headers.get("X-Run-ID")
    session_id = request.args.get("session_id") or request.headers.get("X-Session-ID")

    run_entry = ext.executor.cache_manager.get_run(run_id=run_id, session_id=session_id)
    effective_cache = run_entry.data_cache if run_entry else ext.executor.data_cache

    node_cache = effective_cache.get(node_id)
    if not node_cache or port not in node_cache:
        return jsonify({"error": "No cached data found for this node and port. Please run workflow first."}), 404

    df = node_cache[port]
    if not isinstance(df, pd.DataFrame):
        return jsonify({"error": "Data is not tabular."}), 400

    if search:
        df = filter_dataframe_by_search(df, search)

    if sort_by and sort_by in df.columns:
        ascending = (str(sort_dir).lower() != "desc")
        try:
            df = df.sort_values(by=sort_by, ascending=ascending, na_position="last")
        except Exception:
            pass

    base_name = custom_name if custom_name else f"export_{node_id}_{port}"
    base_name = re.sub(r'[^\w\-_\.]', '_', base_name).strip()
    for ext_strip in [".csv", ".xlsx", ".xls", ".tsv", ".tab", ".json", ".jsonl", ".parquet", ".pq"]:
        if base_name.lower().endswith(ext_strip):
            base_name = base_name[:-len(ext_strip)]
            break
    if not base_name:
        base_name = f"export_{node_id}_{port}"

    try:
        mem_stream, mimetype, def_ext = export_dataframe_to_stream(
            df=df,
            fmt=fmt,
            delimiter=delim,
            include_index=False,
            sheet_name="Export"
        )
        download_filename = f"{base_name}{def_ext}"
        return send_file(
            mem_stream,
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_filename
        )
    except Exception as e:
        return jsonify({"error": f"Export failed: {str(e)}"}), 500



@bp.route("/api/browse", methods=["GET"])
def browse_directory():
    """Returns directory contents (folders and files) for the File Explorer dialog."""
    req_path = request.args.get("path", "").strip()
    root_dir = ext.BASE_DIR

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
            ext_name = os.path.splitext(item)[1].lower()
            try:
                size_bytes = os.path.getsize(full_p)
            except Exception:
                size_bytes = 0
            files.append({
                "name": item,
                "path": full_p.replace("\\", "/"),
                "is_dir": False,
                "size_kb": round(size_bytes / 1024, 1),
                "extension": ext_name
            })

    parent_dir = os.path.dirname(target_dir)
    has_parent = os.path.exists(parent_dir) and parent_dir != target_dir

    return jsonify({
        "success": True,
        "current_path": target_dir.replace("\\", "/"),
        "parent_path": parent_dir.replace("\\", "/") if has_parent else None,
        "workspace_root": root_dir.replace("\\", "/"),
        "data_dir": ext.DATA_DIR.replace("\\", "/"),
        "output_dir": ext.OUTPUT_DIR.replace("\\", "/"),
        "folders": folders,
        "files": files
    })


@bp.route("/api/file-schema", methods=["GET"])
def get_file_schema():
    """Extracts column names and inferred types for a dataset file without running workflow."""
    raw_file = request.args.get("file", "").strip()
    if not raw_file:
        return jsonify({"success": False, "error": "Query parameter 'file' is required."}), 400

    resolved_path = None
    if os.path.isabs(raw_file) and os.path.exists(raw_file):
        resolved_path = raw_file
    elif os.path.exists(os.path.join(ext.DATA_DIR, raw_file)):
        resolved_path = os.path.join(ext.DATA_DIR, raw_file)
    elif raw_file.startswith(("data/", "data\\")) and os.path.exists(os.path.join(ext.DATA_DIR, raw_file[5:])):
        resolved_path = os.path.join(ext.DATA_DIR, raw_file[5:])
    elif os.path.exists(os.path.join(ext.BASE_DIR, raw_file)):
        resolved_path = os.path.join(ext.BASE_DIR, raw_file)
    elif os.path.exists(raw_file):
        resolved_path = raw_file

    if not resolved_path:
        return jsonify({"success": False, "error": f"File '{raw_file}' not found."}), 404

    allowed_dirs = [d for d in [ext.DATA_DIR, ext.BASE_DIR, ext.OUTPUT_DIR] if d]
    if not is_safe_path(resolved_path, allowed_dirs):
        return jsonify({"success": False, "error": "Access forbidden: path outside workspace."}), 403

    extension = os.path.splitext(resolved_path)[1].lower()
    sheet_param = request.args.get("sheet", "0").strip()
    delimiter = request.args.get("delimiter", ",").strip()

    try:
        sheet_arg = int(sheet_param) if sheet_param.isdigit() else sheet_param
        df_preview = read_tabular_file(
            resolved_path,
            sheet_name=sheet_arg,
            delimiter=delimiter,
            max_rows=5,
            trim_headers=True
        )

        columns = [str(c) for c in df_preview.columns]
        meta_list = []
        for col in df_preview.columns:
            s = df_preview[col]
            alt_t = infer_alteryx_type(s)
            cat = map_alteryx_to_category(alt_t)
            meta_list.append({
                "name": str(col),
                "type": cat,
                "alteryx_type": alt_t,
                "dtype": alt_t
            })

        return jsonify({
            "success": True,
            "file": raw_file,
            "columns": columns,
            "column_meta": meta_list
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to inspect file schema: {str(e)}"}), 500


@bp.route("/api/excel-sheets", methods=["GET"])
def get_excel_sheets():
    """Returns sheet names for a given Excel file path using openpyxl without loading data."""
    raw_file = request.args.get("file", "").strip()
    if not raw_file:
        return jsonify({"success": False, "error": "Query parameter 'file' is required."}), 400

    resolved_path = None
    if os.path.isabs(raw_file) and os.path.exists(raw_file):
        resolved_path = raw_file
    elif os.path.exists(os.path.join(ext.DATA_DIR, raw_file)):
        resolved_path = os.path.join(ext.DATA_DIR, raw_file)
    elif raw_file.startswith(("data/", "data\\")) and os.path.exists(os.path.join(ext.DATA_DIR, raw_file[5:])):
        resolved_path = os.path.join(ext.DATA_DIR, raw_file[5:])
    elif os.path.exists(os.path.join(ext.BASE_DIR, raw_file)):
        resolved_path = os.path.join(ext.BASE_DIR, raw_file)
    elif os.path.exists(raw_file):
        resolved_path = raw_file

    if not resolved_path:
        return jsonify({"success": False, "error": f"File '{raw_file}' not found."}), 404

    allowed_dirs = [d for d in [ext.DATA_DIR, ext.BASE_DIR, ext.OUTPUT_DIR] if d]
    if not is_safe_path(resolved_path, allowed_dirs):
        return jsonify({"success": False, "error": "Access forbidden: path outside workspace."}), 403

    extension = os.path.splitext(resolved_path)[1].lower()
    if extension not in [".xlsx", ".xls", ".xlsm", ".xlsb"]:
        return jsonify({"success": False, "error": f"File is not an Excel workbook ({extension})."}), 400

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


@bp.route("/api/wildcard-preview", methods=["GET"])
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
        if ext.DATA_DIR:
            candidate_globs.append(os.path.join(ext.DATA_DIR, pattern))
            if pattern.startswith(("data/", "data\\")):
                candidate_globs.append(os.path.join(ext.DATA_DIR, pattern[5:]))
            candidate_globs.append(os.path.join(ext.DATA_DIR, os.path.basename(pattern)))
        if ext.BASE_DIR:
            candidate_globs.append(os.path.join(ext.BASE_DIR, pattern))

    matched_files = []
    for g in candidate_globs:
        matches = glob.glob(g)
        if matches:
            matched_files.extend(matches)

    matched_files = sorted(list(dict.fromkeys(matched_files)))
    allowed_dirs = [d for d in [ext.DATA_DIR, ext.BASE_DIR, ext.OUTPUT_DIR] if d]
    safe_matches = [f for f in matched_files if is_safe_path(f, allowed_dirs)]

    return jsonify({
        "success": True,
        "pattern": pattern,
        "count": len(safe_matches),
        "files": [os.path.basename(f) for f in safe_matches[:10]],
        "has_more": len(safe_matches) > 10
    })


@bp.route("/api/samples", methods=["GET"])
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
        path = os.path.join(ext.DATA_DIR, f)
        if os.path.isfile(path):
            extension = os.path.splitext(f)[1].lower()
            size_kb = round(os.path.getsize(path) / 1024, 1)
            datasets.append({
                "name": f,
                "type": "excel" if extension in [".xlsx", ".xls"] else "csv",
                "size_kb": size_kb
            })

    curated_workflow_files = [
        "sales_customer_enrichment.json",
        "inventory_supplier_reconciliation.json",
        "marketing_campaign_attribution.json"
    ]
    all_wf_files = list(curated_workflow_files)
    if os.path.exists(ext.WORKFLOWS_DIR):
        for f in sorted(os.listdir(ext.WORKFLOWS_DIR)):
            if f.endswith(".json") and f not in all_wf_files:
                all_wf_files.append(f)

    workflows = []
    for f in all_wf_files:
        path = os.path.join(ext.WORKFLOWS_DIR, f)
        if os.path.isfile(path):
            try:
                import json
                mtime = os.path.getmtime(path)
                with open(path, "r", encoding="utf-8") as wf_file:
                    wf_data = json.load(wf_file)
                    file_stem = os.path.splitext(f)[0]
                    generic_names = {"new workflow", "untitled_workflow", "untitled", "workflow"}
                    current_name = wf_data.get("name")
                    if not current_name or str(current_name).strip().lower() in generic_names:
                        display_name = file_stem.replace("_", " ").title()
                    else:
                        display_name = current_name
                    workflows.append({
                        "file": f,
                        "path": path.replace("\\", "/"),
                        "name": display_name,
                        "description": wf_data.get("description", ""),
                        "node_count": len(wf_data.get("nodes", [])),
                        "modified": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
                    })
            except Exception:
                pass

    return jsonify({"datasets": datasets, "workflows": workflows})

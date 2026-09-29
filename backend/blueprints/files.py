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
    file_type = "excel" if extension in [".xlsx", ".xls", ".xlsm", ".xlsb"] else "csv"

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

            try:
                df_preview = pd.read_csv(save_path, sep=detected_delimiter, nrows=10)
                with open(save_path, "r", encoding="utf-8") as f_in:
                    row_count = sum(1 for _ in f_in) - 1
            except UnicodeDecodeError:
                df_preview = pd.read_csv(save_path, sep=detected_delimiter, encoding="latin1", nrows=10)
                with open(save_path, "r", encoding="latin1") as f_in:
                    row_count = sum(1 for _ in f_in) - 1

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
        "file_type": file_type,
        "delimiter": detected_delimiter if file_type == "csv" else None,
        "sheets": sheets,
        "columns": columns,
        "column_meta": meta_list,
        "row_count": max(0, row_count),
        "preview": preview_records
    })


@bp.route("/api/export/<node_id>", methods=["GET"])
def export_node_data(node_id):
    """Downloads intermediate or final node output as CSV, Excel, TSV, or JSON."""
    port = request.args.get("port", "O")
    fmt = request.args.get("format", "csv").lower()
    custom_name = request.args.get("filename", "").strip()
    sort_by = request.args.get("sort_by")
    sort_dir = request.args.get("sort_dir", "asc")
    run_id = request.args.get("run_id") or request.headers.get("X-Run-ID")
    session_id = request.args.get("session_id") or request.headers.get("X-Session-ID")

    run_entry = ext.executor.cache_manager.get_run(run_id=run_id, session_id=session_id)
    effective_cache = run_entry.data_cache if run_entry else ext.executor.data_cache

    node_cache = effective_cache.get(node_id)
    if not node_cache or port not in node_cache:
        return jsonify({"error": "No cached data found for this node and port."}), 404

    df = node_cache[port]
    if not isinstance(df, pd.DataFrame):
        return jsonify({"error": "Data is not tabular."}), 400

    if sort_by and sort_by in df.columns:
        ascending = (str(sort_dir).lower() != "desc")
        try:
            df = df.sort_values(by=sort_by, ascending=ascending, na_position="last")
        except Exception:
            pass

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
        if extension in [".xlsx", ".xls", ".xlsm", ".xlsb"]:
            sheet_name = int(sheet_param) if sheet_param.isdigit() else sheet_param
            df_preview = fast_read_excel(resolved_path, sheet_name=sheet_name, nrows=5)
            if isinstance(df_preview, dict):
                df_preview = next(iter(df_preview.values())) if df_preview else pd.DataFrame()
        elif extension in [".parquet", ".pq"]:
            df_preview = pd.read_parquet(resolved_path)
            if len(df_preview) > 5:
                df_preview = df_preview.iloc[:5]
        elif extension == ".json":
            df_preview = pd.read_json(resolved_path)
            if len(df_preview) > 5:
                df_preview = df_preview.iloc[:5]
        else:
            sep = "\t" if extension in [".tsv", ".tab"] else (delimiter or ",")
            try:
                df_preview = pd.read_csv(resolved_path, sep=sep, nrows=5)
            except Exception:
                df_preview = pd.read_csv(resolved_path, sep=None, engine="python", nrows=5)

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

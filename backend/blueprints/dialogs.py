"""
Native OS File & Directory Dialogs REST API Blueprint.
Uses non-blocking dedicated worker threads with timeout guards to prevent
stalling WSGI worker threads.
"""
import os
import queue
import threading
import concurrent.futures
from flask import Blueprint, request, jsonify, current_app

import backend.extensions as ext
from backend.engine.security import sanitize_file_basename

bp = Blueprint("dialogs", __name__)

_DIALOG_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="dataflow-dialog"
)


def _run_dialog_safe(fn, timeout=30.0, **kwargs):
    """
    Executes a native dialog function in a dedicated thread pool
    with a strict timeout, preventing WSGI thread pool starvation.
    """
    future = _DIALOG_POOL.submit(fn, **kwargs)
    try:
        return future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return None
    except Exception as e:
        raise e


def show_native_save_dialog(default_name="workflow.json", initial_dir=None):
    """Opens native Windows Explorer Save As dialog via Tkinter."""
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
                initialdir=initial_dir or os.path.join(ext.BASE_DIR, "workflows"),
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
    t.join(timeout=30.0)
    if t.is_alive():
        return None
    res = q.get() if not q.empty() else None
    if isinstance(res, Exception):
        raise res
    return res


def show_native_open_dialog(initial_dir=None):
    """Opens native Windows Explorer Open dialog via Tkinter."""
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
                initialdir=initial_dir or os.path.join(ext.BASE_DIR, "workflows"),
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
    t.join(timeout=30.0)
    if t.is_alive():
        return None
    res = q.get() if not q.empty() else None
    if isinstance(res, Exception):
        raise res
    return res


def show_native_input_file_dialog(initial_dir=None):
    """Opens native Windows Explorer Open File dialog for tabular data files via Tkinter."""
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
                initialdir=initial_dir or ext.DATA_DIR or ext.BASE_DIR,
                filetypes=[
                    ("All Supported Data Files", "*.csv;*.tsv;*.tab;*.xlsx;*.xls;*.xlsm;*.xlsb;*.parquet;*.pq;*.json;*.jsonl;*.txt"),
                    ("Delimited / CSV Files (*.csv, *.tsv, *.txt)", "*.csv;*.tsv;*.tab;*.txt"),
                    ("Excel Workbooks (*.xlsx, *.xls, *.xlsm)", "*.xlsx;*.xls;*.xlsm;*.xlsb"),
                    ("Parquet Files (*.parquet, *.pq)", "*.parquet;*.pq"),
                    ("JSON Files (*.json, *.jsonl)", "*.json;*.jsonl;*.ndjson"),
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
    t.join(timeout=30.0)
    if t.is_alive():
        return None
    res = q.get() if not q.empty() else None
    if isinstance(res, Exception):
        raise res
    return res


def show_native_output_save_dialog(default_name="output.csv", initial_dir=None, fmt="csv"):
    """Opens native Windows Explorer Save As dialog to pick an output path and format."""
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
                initialdir=initial_dir or ext.OUTPUT_DIR,
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
    t.join(timeout=30.0)
    if t.is_alive():
        return None
    res = q.get() if not q.empty() else None
    if isinstance(res, Exception):
        raise res
    return res


def show_native_folder_dialog(initial_dir=None):
    """Opens native Windows Explorer Folder selection dialog via Tkinter."""
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
                initialdir=initial_dir or ext.OUTPUT_DIR,
                mustexist=False
            )
            root.destroy()
            q.put(selected)
        except Exception as err:
            q.put(err)

    t = threading.Thread(target=_worker)
    t.daemon = True
    t.start()
    t.join(timeout=30.0)
    if t.is_alive():
        return None
    res = q.get() if not q.empty() else None
    if isinstance(res, Exception):
        raise res
    return res


@bp.route("/api/dialog/save-file", methods=["POST"])
def handle_native_save_dialog():
    """Opens Windows Explorer Save As dialog on host system and saves workflow to chosen location."""
    data = request.get_json(silent=True) or {}
    wf_data = data.get("workflow") or data
    if not isinstance(wf_data, dict) or not wf_data:
        return jsonify({"success": False, "error": "Invalid workflow data."}), 400

    wf_name = wf_data.get("name", "workflow").strip()
    clean_stem = sanitize_file_basename(wf_name.replace(" ", "_").lower(), fallback="workflow")
    default_name = f"{clean_stem}.json"

    custom_handler = current_app.config.get("NATIVE_SAVE_DIALOG_HANDLER", show_native_save_dialog)
    try:
        chosen_path = _run_dialog_safe(custom_handler, timeout=30.0, default_name=default_name)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to launch Windows Explorer Save dialog: {str(e)}"}), 500

    if not chosen_path:
        return jsonify({"success": False, "cancelled": True, "message": "Dialog cancelled or unavailable."})

    try:
        chosen_filename = os.path.basename(chosen_path)
        file_stem = os.path.splitext(chosen_filename)[0]
        generic_names = {"new workflow", "untitled_workflow", "untitled", "workflow"}
        if not wf_data.get("name") or str(wf_data.get("name")).strip().lower() in generic_names:
            wf_data["name"] = file_stem.replace("_", " ").title()
        save_res = ext.workflow_manager.save_workflow(wf_data, target_filepath=chosen_path)
        return jsonify(save_res)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save to '{chosen_path}': {str(e)}"}), 500


@bp.route("/api/dialog/open-file", methods=["POST", "GET"])
def handle_native_open_dialog():
    """Opens Windows Explorer Open dialog on host system and loads selected workflow or package."""
    custom_handler = current_app.config.get("NATIVE_OPEN_DIALOG_HANDLER", show_native_open_dialog)
    try:
        chosen_path = _run_dialog_safe(custom_handler, timeout=30.0)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to launch Windows Explorer Open dialog: {str(e)}"}), 500

    if not chosen_path:
        return jsonify({"success": False, "cancelled": True, "message": "Dialog cancelled or unavailable."})

    extension = os.path.splitext(chosen_path)[1].lower()
    try:
        if extension in [".zip", ".yxzp"]:
            with open(chosen_path, "rb") as f:
                res = ext.workflow_manager.import_package(f)
            return jsonify({
                "success": True,
                "is_package": True,
                "path": chosen_path.replace("\\", "/"),
                "filename": os.path.basename(chosen_path),
                **res
            })
        else:
            res = ext.workflow_manager.load_from_path(chosen_path)
            return jsonify(res)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to open workflow from '{chosen_path}': {str(e)}"}), 500


@bp.route("/api/dialog/pick-output-path", methods=["POST"])
def handle_native_pick_output_path():
    """Opens Windows Explorer Save As dialog for picking target output file and destination path."""
    data = request.get_json(silent=True) or {}
    fmt = data.get("format", "csv")
    default_name = data.get("default_name") or data.get("filename") or "export_result"
    initial_dir = data.get("initial_dir") or data.get("output_dir") or ext.OUTPUT_DIR

    custom_handler = current_app.config.get("NATIVE_OUTPUT_SAVE_HANDLER", show_native_output_save_dialog)
    try:
        chosen_path = _run_dialog_safe(custom_handler, timeout=30.0, default_name=default_name, initial_dir=initial_dir, fmt=fmt)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to launch Windows Explorer Save dialog: {str(e)}"}), 500

    if not chosen_path:
        return jsonify({"success": False, "cancelled": True, "message": "Dialog cancelled or unavailable."})

    chosen_path = os.path.normpath(chosen_path)
    output_dir = os.path.dirname(chosen_path)
    base_file = os.path.basename(chosen_path)
    stem, extension = os.path.splitext(base_file)

    ext_clean = extension.lower().lstrip(".")
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
        "extension": extension,
        "detected_format": detected_fmt
    })


@bp.route("/api/dialog/pick-input-file", methods=["POST", "GET"])
def handle_native_pick_input_file():
    """Opens Windows Explorer Open File dialog on host system and returns selected data file info."""
    data = request.get_json(silent=True) or {}
    initial_dir = data.get("initial_dir") or ext.DATA_DIR or ext.BASE_DIR

    custom_handler = current_app.config.get("NATIVE_INPUT_FILE_HANDLER", show_native_input_file_dialog)
    try:
        chosen_path = _run_dialog_safe(custom_handler, timeout=30.0, initial_dir=initial_dir)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to launch Windows Explorer Open dialog: {str(e)}"}), 500

    if not chosen_path:
        return jsonify({"success": False, "cancelled": True, "message": "Dialog cancelled or unavailable."})

    chosen_path = os.path.normpath(chosen_path)
    extension = os.path.splitext(chosen_path)[1].lower()
    from backend.engine.io_formats import detect_format
    detected_fmt = detect_format(chosen_path)

    return jsonify({
        "success": True,
        "path": chosen_path.replace("\\", "/"),
        "raw_path": chosen_path,
        "filename": os.path.basename(chosen_path),
        "extension": extension,
        "detected_format": detected_fmt
    })


@bp.route("/api/dialog/pick-folder", methods=["POST"])
def handle_native_pick_folder():
    """Opens Windows Explorer Directory picker dialog on host system."""
    data = request.get_json(silent=True) or {}
    initial_dir = data.get("initial_dir") or data.get("output_dir") or ext.OUTPUT_DIR

    custom_handler = current_app.config.get("NATIVE_FOLDER_DIALOG_HANDLER", show_native_folder_dialog)
    try:
        chosen_path = _run_dialog_safe(custom_handler, timeout=30.0, initial_dir=initial_dir)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to launch Windows Explorer Folder dialog: {str(e)}"}), 500

    if not chosen_path:
        return jsonify({"success": False, "cancelled": True, "message": "Dialog cancelled or unavailable."})

    chosen_path = os.path.normpath(chosen_path)
    return jsonify({
        "success": True,
        "path": chosen_path.replace("\\", "/"),
        "raw_path": chosen_path
    })


@bp.route("/api/open-in-explorer", methods=["POST"])
def handle_open_in_explorer():
    """Opens Windows Explorer highlighting the target file or directory on host OS."""
    data = request.get_json(silent=True) or {}
    target_path = data.get("path")
    if not target_path:
        return jsonify({"success": False, "error": "Missing 'path' parameter."}), 400

    if not os.path.isabs(target_path):
        candidates = [
            os.path.join(ext.OUTPUT_DIR, target_path),
            os.path.join(ext.DATA_DIR, target_path),
            os.path.join(ext.BASE_DIR, target_path),
        ]
        resolved = None
        for c in candidates:
            if os.path.exists(c):
                resolved = c
                break
        if not resolved:
            resolved = os.path.join(ext.OUTPUT_DIR, target_path)
    else:
        resolved = target_path

    resolved = os.path.normpath(resolved)
    custom_launcher = current_app.config.get("NATIVE_EXPLORER_LAUNCHER")
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

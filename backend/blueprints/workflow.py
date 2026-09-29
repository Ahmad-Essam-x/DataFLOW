"""
Workflow Lifecycle, Templates & Version Control REST API Blueprint.
Handles saving workflows, revision backups, checkpoints, diffing,
crash recovery autosaves, template libraries, and packaging (.zip/.yxzp).
"""
import os
import sys
import json
import re
import time
from flask import Blueprint, request, jsonify, send_file

import backend.extensions as ext
from backend.engine.security import (
    sanitize_file_basename,
    is_safe_path,
    SecurityError
)

bp = Blueprint("workflow", __name__)


@bp.route("/api/app-info", methods=["GET"])
def get_app_info():
    """Returns application runtime metadata and directory paths."""
    return jsonify({
        "app_name": "Antigravity DataFlow",
        "version": "2.1.0",
        "frozen": getattr(sys, "frozen", False),
        "data_dir": ext.DATA_DIR,
        "workflows_dir": ext.WORKFLOWS_DIR,
        "base_dir": ext.BASE_DIR
    })


@bp.route("/api/initial-workflow", methods=["GET"])
def get_initial_workflow():
    """Returns initial workflow specified via CLI --open or query parameter ?open=filename."""
    target = request.args.get("open") or ext.INITIAL_WORKFLOW_FILE
    if not target:
        return jsonify({"workflow": None})

    candidate_paths = [
        target,
        os.path.join(ext.WORKFLOWS_DIR, target),
        os.path.join(ext.WORKFLOWS_DIR, target + (".json" if not target.endswith(".json") else ""))
    ]
    if hasattr(sys, "_MEIPASS"):
        candidate_paths.append(os.path.join(sys._MEIPASS, "workflows", target))
        candidate_paths.append(os.path.join(sys._MEIPASS, "workflows", target + (".json" if not target.endswith(".json") else "")))

    for p in candidate_paths:
        if p and os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                file_stem = os.path.splitext(os.path.basename(p))[0]
                generic_names = {"new workflow", "untitled_workflow", "untitled", "workflow"}
                current_name = data.get("name")
                if not current_name or str(current_name).strip().lower() in generic_names:
                    data["name"] = file_stem.replace("_", " ").title()
                return jsonify({
                    "workflow": data,
                    "path": p.replace("\\", "/"),
                    "name": data["name"]
                })
            except Exception as e:
                return jsonify({"workflow": None, "error": f"Failed to load workflow: {str(e)}"}), 400

    clean_target = target.lower().replace(".json", "").replace("_", " ").strip()
    search_dirs = [ext.WORKFLOWS_DIR]
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
                            file_stem = os.path.splitext(fn)[0]
                            generic_names = {"new workflow", "untitled_workflow", "untitled", "workflow"}
                            current_name = data.get("name")
                            if not current_name or str(current_name).strip().lower() in generic_names:
                                data["name"] = file_stem.replace("_", " ").title()
                            return jsonify({
                                "workflow": data,
                                "path": fp.replace("\\", "/"),
                                "name": data["name"]
                            })
                    except Exception:
                        pass

    return jsonify({"workflow": None, "warning": f"Workflow '{target}' not found."})


@bp.route("/api/workflow/<filename>", methods=["GET"])
@bp.route("/api/sample-workflow/<filename>", methods=["GET"])
def get_sample_workflow(filename):
    """Fetches a sample or saved workflow JSON with resilient fallback matching."""
    safe_name = sanitize_file_basename(filename, fallback="workflow.json")
    path = os.path.join(ext.WORKFLOWS_DIR, safe_name)
    if not is_safe_path(path, [ext.WORKFLOWS_DIR]):
        return jsonify({"error": "Path traversal prohibited."}), 403

    if not os.path.isfile(path):
        candidates = [
            safe_name + ".json",
            safe_name.replace(" ", "_"),
            safe_name.replace("_", " "),
            safe_name.replace(" ", "_") + ".json",
            safe_name.replace("_", " ") + ".json"
        ]
        found = False
        for cand in candidates:
            cand_p = os.path.join(ext.WORKFLOWS_DIR, cand)
            if is_safe_path(cand_p, [ext.WORKFLOWS_DIR]) and os.path.isfile(cand_p):
                path = cand_p
                safe_name = cand
                found = True
                break
        if not found and os.path.isdir(ext.WORKFLOWS_DIR):
            lower_name = safe_name.lower()
            if not lower_name.endswith(".json"):
                lower_name += ".json"
            for fn in os.listdir(ext.WORKFLOWS_DIR):
                if fn.lower() == lower_name or fn.lower().replace("_", " ") == lower_name.replace("_", " "):
                    cand_p = os.path.join(ext.WORKFLOWS_DIR, fn)
                    if is_safe_path(cand_p, [ext.WORKFLOWS_DIR]) and os.path.isfile(cand_p):
                        path = cand_p
                        safe_name = fn
                        found = True
                        break
        if not found:
            return jsonify({"error": "Workflow not found."}), 404

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    file_stem = os.path.splitext(safe_name)[0]
    generic_names = {"new workflow", "untitled_workflow", "untitled", "workflow"}
    current_name = data.get("name")
    if not current_name or str(current_name).strip().lower() in generic_names:
        data["name"] = file_stem.replace("_", " ").title()

    data["_path"] = path.replace("\\", "/")
    data["_filename"] = safe_name
    return jsonify(data)


@bp.route("/api/workflow/open", methods=["GET", "POST"])
def open_workflow_endpoint():
    """
    Loads workflow JSON from an arbitrary path, filename, or name.
    Supports absolute paths, workspace paths, and fuzzy filename resolution.
    """
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
    else:
        data = request.args

    raw_path = data.get("path") or data.get("filepath")
    raw_filename = data.get("filename") or data.get("file")
    raw_name = data.get("name")

    resolved_path = None

    # 1. Try absolute or direct path
    if raw_path:
        norm_p = str(raw_path).strip()
        candidates = [norm_p]
        if not (norm_p.lower().endswith(".json") or norm_p.lower().endswith(".yxmd")):
            candidates.append(norm_p + ".json")

        for cp in candidates:
            if os.path.isabs(cp) and os.path.isfile(cp):
                resolved_path = os.path.abspath(cp)
                break
            # Try relative to BASE_DIR and WORKFLOWS_DIR
            if ext.BASE_DIR:
                base_cand = os.path.join(ext.BASE_DIR, cp)
                if os.path.isfile(base_cand):
                    resolved_path = os.path.abspath(base_cand)
                    break
            if ext.WORKFLOWS_DIR:
                wf_cand = os.path.join(ext.WORKFLOWS_DIR, cp)
                if os.path.isfile(wf_cand):
                    resolved_path = os.path.abspath(wf_cand)
                    break
                base_name = os.path.basename(cp.replace("\\", "/"))
                wf_base_cand = os.path.join(ext.WORKFLOWS_DIR, base_name)
                if os.path.isfile(wf_base_cand):
                    resolved_path = os.path.abspath(wf_base_cand)
                    break

    # 2. Try raw_filename in WORKFLOWS_DIR
    if not resolved_path and raw_filename:
        fname = str(raw_filename).strip()
        candidates = [
            fname,
            fname + (".json" if not fname.endswith(".json") else ""),
            fname.replace(" ", "_"),
            fname.replace("_", " "),
            fname.replace(" ", "_") + ".json",
            fname.replace("_", " ") + ".json"
        ]
        for cand in candidates:
            cand_p = os.path.join(ext.WORKFLOWS_DIR, cand)
            if os.path.isfile(cand_p):
                resolved_path = os.path.abspath(cand_p)
                break

    # 3. Case-insensitive or workflow name lookup
    target_ident = raw_name or raw_filename or raw_path
    if not resolved_path and target_ident:
        clean_target = str(target_ident).lower().replace(".json", "").replace("_", " ").strip()
        if os.path.isdir(ext.WORKFLOWS_DIR):
            for fn in os.listdir(ext.WORKFLOWS_DIR):
                if fn.lower().endswith((".json", ".yxmd")):
                    fn_stem = os.path.splitext(fn)[0].lower().replace("_", " ").strip()
                    if fn_stem == clean_target:
                        resolved_path = os.path.join(ext.WORKFLOWS_DIR, fn)
                        break

    if not resolved_path or not os.path.isfile(resolved_path):
        return jsonify({
            "success": False,
            "error": f"Workflow file not found on disk: {raw_path or raw_filename or raw_name or 'unknown'}"
        }), 404

    # Security check on extension
    allowed_exts = {".json", ".yxmd", ".zip", ".yxzp"}
    _, ext_part = os.path.splitext(resolved_path)
    if ext_part.lower() not in allowed_exts:
        return jsonify({"success": False, "error": f"File type '{ext_part}' is not an allowed workflow format."}), 403

    try:
        if ext_part.lower() in [".zip", ".yxzp"]:
            with open(resolved_path, "rb") as f:
                res = ext.workflow_manager.import_package(f)
            return jsonify({
                "success": True,
                "is_package": True,
                "path": resolved_path.replace("\\", "/"),
                "filename": os.path.basename(resolved_path),
                **res
            })
        else:
            result = ext.workflow_manager.load_from_path(resolved_path)
            return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to load workflow: {str(e)}"}), 500


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


@bp.route("/api/templates", methods=["GET"])
def list_templates():
    """Returns all curated and user-saved workflow templates with metadata."""
    templates = []

    if os.path.isdir(ext.WORKFLOW_TEMPLATES_DIR):
        for fname in sorted(os.listdir(ext.WORKFLOW_TEMPLATES_DIR)):
            if not fname.endswith(".json"):
                continue
            meta = _load_template_meta(
                os.path.join(ext.WORKFLOW_TEMPLATES_DIR, fname), is_user=False
            )
            if meta:
                templates.append(meta)

    if os.path.isdir(ext.WORKFLOW_TEMPLATES_USER_DIR):
        for fname in sorted(os.listdir(ext.WORKFLOW_TEMPLATES_USER_DIR)):
            if not fname.endswith(".json"):
                continue
            meta = _load_template_meta(
                os.path.join(ext.WORKFLOW_TEMPLATES_USER_DIR, fname), is_user=True
            )
            if meta:
                templates.append(meta)

    return jsonify({"templates": templates})


@bp.route("/api/templates/save", methods=["POST"])
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
    dest = os.path.join(ext.WORKFLOW_TEMPLATES_USER_DIR, fname)

    counter = 1
    while os.path.exists(dest):
        dest = os.path.join(ext.WORKFLOW_TEMPLATES_USER_DIR, f"{safe_stem}_{counter}.json")
        counter += 1
    fname = os.path.basename(dest)

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(workflow, f, ensure_ascii=False, indent=2)

    return jsonify({"success": True, "file": fname, "name": name})


@bp.route("/api/templates/<filename>", methods=["GET"])
def get_template(filename):
    """Returns the full workflow JSON for a template by filename."""
    safe_name = sanitize_file_basename(filename, fallback="template.json")

    for search_dir in [ext.WORKFLOW_TEMPLATES_DIR, ext.WORKFLOW_TEMPLATES_USER_DIR]:
        path = os.path.join(search_dir, safe_name)
        if is_safe_path(path, [ext.WORKFLOW_TEMPLATES_DIR]) and os.path.isfile(path):
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            return jsonify(data)

    return jsonify({"error": "Template not found."}), 404


@bp.route("/api/templates/<filename>", methods=["DELETE"])
def delete_template(filename):
    """Deletes a user-saved template (curated templates cannot be deleted)."""
    safe_name = sanitize_file_basename(filename, fallback="template.json")
    path = os.path.join(ext.WORKFLOW_TEMPLATES_USER_DIR, safe_name)
    if not is_safe_path(path, [ext.WORKFLOW_TEMPLATES_USER_DIR]):
        return jsonify({"error": "Path traversal prohibited."}), 403
    if not os.path.isfile(path):
        return jsonify({"error": "User template not found."}), 404
    os.remove(path)
    return jsonify({"success": True})


@bp.route("/api/save-workflow", methods=["POST"])
def save_workflow():
    """Saves workflow JSON locally with schema validation and automatic revision backup."""
    data = request.get_json(silent=True)
    if not data or "name" not in data:
        return jsonify({"success": False, "error": "Invalid workflow data."}), 400

    try:
        custom_file = request.args.get("file")
        target_path = data.get("target_filepath") or request.args.get("target_filepath")
        result = ext.workflow_manager.save_workflow(data, custom_filename=custom_file, target_filepath=target_path)
        return jsonify(result)
    except SecurityError as se:
        return jsonify({"success": False, "error": str(se)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to save workflow: {str(e)}"}), 500


@bp.route("/api/workflow/export-package", methods=["POST"])
def export_workflow_package():
    """Packages workflow definition and referenced data files into a downloadable .zip archive."""
    data = request.get_json(silent=True)
    if not data or "name" not in data:
        return jsonify({"success": False, "error": "Invalid workflow payload."}), 400

    raw_name = data.get("name", "workflow_package").strip()
    clean_stem = sanitize_file_basename(raw_name.replace(" ", "_").lower(), fallback="workflow")
    zip_download_name = f"{clean_stem}_package.zip"

    try:
        zip_buf = ext.workflow_manager.export_package(data)
        return send_file(
            zip_buf,
            mimetype="application/zip",
            as_attachment=True,
            download_name=zip_download_name
        )
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to generate workflow package: {str(e)}"}), 500


@bp.route("/api/workflow/import-package", methods=["POST"])
def import_workflow_package():
    """Uploads and unpacks a workflow package (.zip / .yxzp) into data and workflows directories."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No package file uploaded."}), 400

    uploaded = request.files["file"]
    if not uploaded or not uploaded.filename:
        return jsonify({"success": False, "error": "Empty filename."}), 400

    extension = os.path.splitext(uploaded.filename)[1].lower()
    if extension not in [".zip", ".yxzp"]:
        return jsonify({"success": False, "error": f"Unsupported package extension ({extension}). Use .zip or .yxzp."}), 400

    try:
        result = ext.workflow_manager.import_package(uploaded.stream)
        return jsonify(result)
    except SecurityError as se:
        return jsonify({"success": False, "error": str(se)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to import package: {str(e)}"}), 400


@bp.route("/api/workflow/dependencies", methods=["POST"])
def inspect_workflow_dependencies():
    """Inspects external data assets referenced in a workflow payload."""
    data = request.get_json(silent=True) or {}
    try:
        result = ext.workflow_manager.inspect_dependencies(data)
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/workflow/<filename>/revisions", methods=["GET"])
def get_workflow_revisions(filename):
    """Lists historical timestamped backups for a workflow file."""
    try:
        revisions = ext.workflow_manager.get_revisions(filename)
        return jsonify({"success": True, "filename": filename, "revisions": revisions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/workflow/<filename>/revert", methods=["POST"])
def revert_workflow_revision(filename):
    """Reverts a workflow to a chosen timestamped revision snapshot."""
    data = request.get_json(silent=True) or {}
    backup_file = data.get("backup_file") or request.args.get("backup_file")
    if not backup_file:
        return jsonify({"success": False, "error": "Missing 'backup_file' parameter."}), 400

    try:
        result = ext.workflow_manager.revert_revision(filename, backup_file)
        return jsonify(result)
    except SecurityError as se:
        return jsonify({"success": False, "error": str(se)}), 403
    except FileNotFoundError as fe:
        return jsonify({"success": False, "error": str(fe)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to revert revision: {str(e)}"}), 500


@bp.route("/api/workflow/autosave", methods=["GET", "POST", "DELETE"])
def handle_workflow_autosave():
    """Manages active session autosaves for crash recovery."""
    session_id = request.headers.get("X-Session-ID") or request.args.get("session_id") or "default_session"

    if request.method == "POST":
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"success": False, "error": "Invalid autosave payload."}), 400
        res = ext.workflow_manager.save_autosave(session_id, data)
        return jsonify(res)

    elif request.method == "GET":
        saved = ext.workflow_manager.get_autosave(session_id)
        if saved:
            return jsonify({"success": True, "available": True, "workflow": saved})
        return jsonify({"success": True, "available": False, "workflow": None})

    elif request.method == "DELETE":
        cleared = ext.workflow_manager.clear_autosave(session_id)
        return jsonify({"success": True, "cleared": cleared})


@bp.route("/api/workflow/recovery/available", methods=["GET"])
def get_available_workflow_recoveries():
    """Returns all discoverable autosave recovery drafts for crash restoration."""
    try:
        recoveries = ext.workflow_manager.get_available_recoveries()
        return jsonify({"success": True, "recoveries": recoveries, "count": len(recoveries)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/workflow/recovery/clear-all", methods=["POST"])
def clear_all_workflow_recoveries():
    """Clears all autosave recovery snapshots on clean exit or explicit user discard."""
    try:
        cleared_count = ext.workflow_manager.clear_all_autosaves()
        return jsonify({"success": True, "cleared_count": cleared_count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/workflow/<filename>/commit", methods=["POST"])
def commit_workflow_checkpoint(filename):
    """Creates a named version checkpoint with commit message and author metadata."""
    data = request.get_json(silent=True) or {}
    workflow_data = data.get("workflow") or data
    message = data.get("message") or "Manual Checkpoint"
    author = data.get("author") or "User"
    tag = data.get("tag")

    try:
        result = ext.workflow_manager.commit_checkpoint(
            filename=filename,
            wf_data=workflow_data,
            message=message,
            author=author,
            tag=tag
        )
        return jsonify(result)
    except SecurityError as se:
        return jsonify({"success": False, "error": str(se)}), 403
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to commit checkpoint: {str(e)}"}), 500


@bp.route("/api/workflow/revision/<backup_filename>", methods=["GET"])
def get_workflow_revision_content(backup_filename):
    """Retrieves full workflow JSON of a specific backup revision for diffing or branching."""
    try:
        result = ext.workflow_manager.get_revision_content(backup_filename)
        return jsonify(result)
    except SecurityError as se:
        return jsonify({"success": False, "error": str(se)}), 403
    except FileNotFoundError as fe:
        return jsonify({"success": False, "error": str(fe)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.route("/api/workflow/diff", methods=["POST"])
def compute_workflow_diff():
    """Compares current workflow against a target revision or another workflow."""
    data = request.get_json(silent=True) or {}
    base_wf = data.get("base_workflow") or {}
    target_wf = data.get("target_workflow") or {}
    backup_file = data.get("backup_file")

    try:
        if backup_file and not target_wf:
            rev_res = ext.workflow_manager.get_revision_content(backup_file)
            target_wf = rev_res.get("workflow", {})

        diff = ext.workflow_manager.compute_diff(base_wf, target_wf)
        return jsonify({"success": True, "diff": diff})
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to compute diff: {str(e)}"}), 500

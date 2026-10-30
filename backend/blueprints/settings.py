"""
Application Settings & App Lifecycle REST API Blueprint.
Handles user settings JSON persistence, recent workflows list,
frontend dirty state tracking, and graceful application exit.
"""
import os
import json
import time
import threading
from flask import Blueprint, request, jsonify

import backend.extensions as ext
from backend.fileio import atomic_write_json

bp = Blueprint("settings", __name__)


def _get_settings_file():
    import backend.app as app_mod
    return getattr(app_mod, "USER_SETTINGS_FILE", ext.USER_SETTINGS_FILE)


@bp.route("/api/user-settings", methods=["GET"])
def get_user_settings():
    """Returns the persisted user settings JSON, or {} if none exist yet."""
    settings_file = _get_settings_file()
    if not settings_file or not os.path.exists(settings_file):
        return jsonify({})
    try:
        with open(settings_file, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": f"Failed to read settings: {str(e)}"}), 500


@bp.route("/api/user-settings", methods=["POST"])
def save_user_settings():
    """Persists the user settings JSON to user_settings.json in the workspace root."""
    settings_file = _get_settings_file()
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Invalid or missing JSON body."}), 400
    if not isinstance(data, dict):
        return jsonify({"error": "Settings must be a JSON object."}), 400
    try:
        atomic_write_json(settings_file, data)
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": f"Failed to save settings: {str(e)}"}), 500


@bp.route("/api/workflow/recent", methods=["GET", "POST", "DELETE"])
def manage_recent_workflows():
    """Manages the server-persisted list of recently accessed workflows."""
    settings_file = _get_settings_file()
    settings = {}
    if settings_file and os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except Exception:
            settings = {}

    if request.method == "DELETE":
        settings["recent_workflows"] = []
        try:
            atomic_write_json(settings_file, settings)
            return jsonify({"success": True, "cleared": True})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        if isinstance(data, list):
            bulk_entries = data
        elif "recent_workflows" in data and isinstance(data["recent_workflows"], list):
            bulk_entries = data["recent_workflows"]
        else:
            bulk_entries = None

        if bulk_entries is not None:
            # Bulk synchronize entries from client
            recent_list = []
            for b in bulk_entries:
                if isinstance(b, dict) and b.get("name"):
                    clean_name = str(b["name"]).strip()
                    if not any(r.get("name", "").lower() == clean_name.lower() for r in recent_list):
                        recent_list.append({
                            "name": clean_name,
                            "path": b.get("path"),
                            "timestamp": b.get("timestamp") or int(time.time() * 1000),
                            "node_count": b.get("node_count", 0)
                        })
            settings["recent_workflows"] = recent_list[:12]
        else:
            entry = data.get("recent") or data
            if not entry or not isinstance(entry, dict) or not entry.get("name"):
                return jsonify({"error": "Invalid recent workflow payload"}), 400

            recent_list = settings.get("recent_workflows", [])
            clean_name = str(entry["name"]).strip()
            recent_list = [r for r in recent_list if r.get("name", "").lower() != clean_name.lower()]
            recent_list.insert(0, {
                "name": clean_name,
                "path": entry.get("path"),
                "timestamp": entry.get("timestamp") or int(time.time() * 1000),
                "node_count": entry.get("node_count", 0)
            })
            settings["recent_workflows"] = recent_list[:12]

        try:
            atomic_write_json(settings_file, settings)
            return jsonify({"success": True, "recent_workflows": settings["recent_workflows"]})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # GET: return list enriched with disk existence check and resolved disk path
    recent_list = settings.get("recent_workflows", [])
    enriched = []
    for r in recent_list:
        p = r.get("path")
        exists = False
        resolved_p = None
        if p:
            norm_p = str(p).strip()
            cands = []
            if os.path.isabs(norm_p):
                cands.append(norm_p)
                cands.append(norm_p + ".json")
            if ext.BASE_DIR:
                cands.append(os.path.join(ext.BASE_DIR, norm_p))
                cands.append(os.path.join(ext.BASE_DIR, norm_p + ".json"))
            if ext.WORKFLOWS_DIR:
                cands.append(os.path.join(ext.WORKFLOWS_DIR, norm_p))
                cands.append(os.path.join(ext.WORKFLOWS_DIR, norm_p + ".json"))
                base_fn = os.path.basename(norm_p.replace("\\", "/"))
                cands.append(os.path.join(ext.WORKFLOWS_DIR, base_fn))
                cands.append(os.path.join(ext.WORKFLOWS_DIR, base_fn + ".json"))
                cands.append(os.path.join(ext.WORKFLOWS_DIR, base_fn.replace(" ", "_")))
                cands.append(os.path.join(ext.WORKFLOWS_DIR, base_fn.replace("_", " ")))
                cands.append(os.path.join(ext.WORKFLOWS_DIR, base_fn.replace(" ", "_") + ".json"))
                cands.append(os.path.join(ext.WORKFLOWS_DIR, base_fn.replace("_", " ") + ".json"))

            for c in cands:
                if c and os.path.isfile(c):
                    exists = True
                    resolved_p = os.path.abspath(c).replace("\\", "/")
                    break

        # Fallback search by workflow name in WORKFLOWS_DIR
        if not exists and r.get("name") and ext.WORKFLOWS_DIR and os.path.isdir(ext.WORKFLOWS_DIR):
            target_n = str(r["name"]).lower().replace("_", " ").strip()
            for fn in os.listdir(ext.WORKFLOWS_DIR):
                if fn.lower().endswith((".json", ".yxmd")):
                    stem = os.path.splitext(fn)[0].lower().replace("_", " ").strip()
                    if stem == target_n:
                        exists = True
                        resolved_p = os.path.join(ext.WORKFLOWS_DIR, fn).replace("\\", "/")
                        break

        enriched.append({**r, "exists": exists, "resolved_path": resolved_p or p})
    return jsonify({"success": True, "recent_workflows": enriched})


@bp.route("/api/app/exit", methods=["POST"])
def exit_application():
    """Signals application shutdown from desktop or web UI with optional autosave cleanup."""
    data = request.get_json(silent=True) or {}
    clear_autosave = data.get("clear_autosave", False)
    if clear_autosave:
        try:
            ext.workflow_manager.clear_all_autosaves()
        except Exception:
            pass

    def _shutdown():
        time.sleep(0.4)
        os._exit(0)

    threading.Thread(target=_shutdown, daemon=True).start()
    return jsonify({"success": True, "message": "Antigravity DataFlow is shutting down."})


@bp.route("/api/app/dirty-state", methods=["GET", "POST"])
def app_dirty_state():
    """Tracks dirty state of workflows across frontend tabs for non-blocking exit interception."""
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        ext._app_dirty_state["is_dirty"] = bool(data.get("is_dirty", False))
        ext._app_dirty_state["dirty_tabs_count"] = int(data.get("dirty_tabs_count", 0))
        return jsonify({"success": True, "dirty_state": ext._app_dirty_state})
    return jsonify({"success": True, "dirty_state": ext._app_dirty_state})

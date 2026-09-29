"""
Flask Application Entrypoint & Factory for Antigravity DataFlow.
Organized using Flask Blueprints for modularity, maintainability, and concurrency isolation.
"""
import os
import sys
import shutil
from flask import Flask, render_template, request, jsonify

import backend.extensions as ext
from backend.engine.executor import WorkflowExecutor
from backend.engine.cache_manager import SessionRunCacheManager
from backend.engine.workflow_manager import WorkflowManager
from backend.samples.generator import ensure_sample_data

# ----------------------------------------------------------------------
# 1. Path Resolution (Source vs PyInstaller Frozen Bundle)
# ----------------------------------------------------------------------
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

USER_SETTINGS_FILE = os.path.join(BASE_DIR, "user_settings.json")

# Populate extensions module paths
ext.BASE_DIR = BASE_DIR
ext.DATA_DIR = DATA_DIR
ext.OUTPUT_DIR = OUTPUT_DIR
ext.WORKFLOWS_DIR = WORKFLOWS_DIR
ext.WORKFLOW_TEMPLATES_DIR = WORKFLOW_TEMPLATES_DIR
ext.WORKFLOW_TEMPLATES_USER_DIR = WORKFLOW_TEMPLATES_USER_DIR
ext.USER_SETTINGS_FILE = USER_SETTINGS_FILE

# Initialize sample data and directories
ensure_sample_data(DATA_DIR, WORKFLOWS_DIR)

# Shared singletons (re-exported for backward compatibility)
cache_manager = SessionRunCacheManager(max_runs=2, ttl_seconds=3600)
executor = WorkflowExecutor(context={
    "data_dir": DATA_DIR,
    "output_dir": OUTPUT_DIR,
    "base_dir": BASE_DIR
}, cache_manager=cache_manager)

workflow_manager = WorkflowManager(
    workflows_dir=WORKFLOWS_DIR,
    data_dir=DATA_DIR,
    base_dir=BASE_DIR
)

ext.cache_manager = cache_manager
ext.executor = executor
ext.workflow_manager = workflow_manager

INITIAL_WORKFLOW_FILE = None
_app_dirty_state = ext._app_dirty_state


def set_initial_workflow(filepath_or_name):
    global INITIAL_WORKFLOW_FILE
    INITIAL_WORKFLOW_FILE = filepath_or_name
    ext.INITIAL_WORKFLOW_FILE = filepath_or_name


# ----------------------------------------------------------------------
# 2. Flask Application Factory
# ----------------------------------------------------------------------
def create_app():
    """Creates and configures the Flask application with all registered blueprints."""
    app_instance = Flask(__name__, static_folder=STATIC_DIR, template_folder=TEMPLATES_DIR)
    app_instance.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB max upload

    # Register blueprints
    from backend.blueprints.execution import bp as execution_bp
    from backend.blueprints.files import bp as files_bp
    from backend.blueprints.workflow import bp as workflow_bp
    from backend.blueprints.settings import bp as settings_bp
    from backend.blueprints.dialogs import bp as dialogs_bp
    from backend.blueprints.ai import bp as ai_bp

    app_instance.register_blueprint(execution_bp)
    app_instance.register_blueprint(files_bp)
    app_instance.register_blueprint(workflow_bp)
    app_instance.register_blueprint(settings_bp)
    app_instance.register_blueprint(dialogs_bp)
    app_instance.register_blueprint(ai_bp)

    @app_instance.route("/")
    def index():
        return render_template("index.html")

    @app_instance.errorhandler(404)
    def handle_404(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "available": False, "error": "Not Found", "message": str(e)}), 404
        return "Not Found", 404

    @app_instance.errorhandler(500)
    def handle_500(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "available": False, "error": "Internal Server Error", "message": str(e)}), 500
        return "Internal Server Error", 500

    @app_instance.errorhandler(Exception)
    def handle_global_exception(e):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "available": False, "error": type(e).__name__, "message": str(e)}), 500
        raise e

    return app_instance


# Module-level app instance (preserves `from backend.app import app` across desktop_app.py and tests)
app = create_app()


# ----------------------------------------------------------------------
# 3. Server Launcher & Port Resolution
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

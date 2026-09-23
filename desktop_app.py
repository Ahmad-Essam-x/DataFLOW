"""
Antigravity DataFlow - Native Desktop Application Shell.
Launches the production WSGI server (Waitress) on an ephemeral port in the background
and renders the UI inside a chromeless native Windows desktop window using PyWebView (WebView2).
Includes pre-flight diagnostics, persistent logging, and multi-tier visual fallbacks.
"""
import os
import sys
import time
import socket
import logging
import argparse
import threading
import urllib.request
import urllib.error

# Ensure base directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import app, set_initial_workflow, find_available_port
from desktop.diagnostics import (
    setup_persistent_logger,
    run_system_diagnostics,
    format_diagnostic_report,
    show_native_error_dialog,
    get_launch_log_path,
    logger
)


def wait_for_server(port: int, timeout: float = 10.0) -> bool:
    """Waits until the backend server responds to HTTP requests."""
    start = time.time()
    url = f"http://127.0.0.1:{port}/api/tools"
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                if response.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.08)
    return False


def get_icon_path() -> str:
    """Resolves the icon path across dev source and frozen PyInstaller bundles."""
    candidates = [
        os.path.join(BASE_DIR, "assets", "icon.ico"),
        os.path.join(os.path.dirname(sys.executable), "assets", "icon.ico"),
        os.path.join(os.path.dirname(sys.executable), "icon.ico"),
    ]
    if hasattr(sys, '_MEIPASS'):
        candidates.insert(0, os.path.join(sys._MEIPASS, "assets", "icon.ico"))

    for c in candidates:
        if c and os.path.exists(c):
            return c
    return None


def launch_edge_app_mode(url: str):
    """
    Tier 2 Fallback: Launches Microsoft Edge in standalone chromeless application mode.
    Returns subprocess.Popen instance if launched, or None if Edge is not available.
    """
    import subprocess
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        "msedge"
    ]
    for edge in edge_paths:
        try:
            proc = subprocess.Popen([
                edge,
                f"--app={url}",
                "--window-size=1440,900"
            ])
            return proc
        except (FileNotFoundError, OSError):
            continue
    return None


def attach_to_parent_console():
    """Attaches a windowed GUI executable to the parent console if launched from terminal/cmd."""
    if sys.platform == "win32":
        try:
            import ctypes
            # ATTACH_PARENT_PROCESS = -1
            if ctypes.windll.kernel32.AttachConsole(-1):
                sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Antigravity DataFlow Desktop")
    parser.add_argument("workflow_pos", nargs="?", default=None, help="Optional positional workflow JSON to open")
    parser.add_argument("--open", "-o", dest="open_workflow", default=None, help="Workflow JSON file to open on launch")
    parser.add_argument("--port", "-p", dest="port", type=int, default=0, help="Port for local backend (0 = auto-assign)")
    parser.add_argument("--threads", "-t", dest="threads", type=int, default=8, help="Worker threads for Waitress (default: 8)")
    parser.add_argument("--headless", action="store_true", help="Run background server only without desktop window")
    parser.add_argument("--browser", action="store_true", help="Open in default browser instead of native PyWebView window")
    parser.add_argument("--create-shortcut", action="store_true", help="Create Windows Desktop and Start Menu shortcuts")
    parser.add_argument("--diagnose", action="store_true", help="Run pre-flight dependency diagnostics and print report")
    parser.add_argument("--check-deps", action="store_true", help="Check dependencies silently; exit 0 if ready, 1 if critical error")
    parser.add_argument("--log-file", default=None, help="Custom path for launch log file")

    args = parser.parse_args()

    # 1. Initialize persistent launch logger
    log_file = setup_persistent_logger(args.log_file)
    logger.info("=" * 60)
    logger.info("Antigravity DataFlow Desktop Shell starting...")
    logger.info(f"Executable: {sys.executable} (Frozen: {getattr(sys, 'frozen', False)})")
    logger.info(f"Base Directory: {BASE_DIR}")
    logger.info(f"Python Version: {sys.version.split()[0]} on {sys.platform}")

    # 2. Handle --diagnose or --check-deps
    if args.diagnose or args.check_deps:
        attach_to_parent_console()
        report = run_system_diagnostics()
        formatted = format_diagnostic_report(report)
        logger.info("\n" + formatted)
        if args.diagnose:
            print(formatted)
        return 0 if report["overall_status"] in ("PASS", "WARN") else 1

    # 3. Handle shortcut creation if requested
    if args.create_shortcut:
        attach_to_parent_console()
        from desktop.shortcuts import install_desktop_shortcuts
        res = install_desktop_shortcuts()
        desktop_ok = res.get("desktop", (False,))[0]
        start_ok = res.get("start_menu", (False,))[0]
        logger.info(f"Desktop shortcut: {'OK' if desktop_ok else 'Failed'}")
        logger.info(f"Start Menu shortcut: {'OK' if start_ok else 'Failed'}")
        print(f"Desktop shortcut: {'OK' if desktop_ok else 'Failed'}")
        print(f"Start Menu shortcut: {'OK' if start_ok else 'Failed'}")
        return 0 if (desktop_ok and start_ok) else 1

    # 4. Configure initial workflow to open
    target_wf = args.open_workflow or args.workflow_pos
    if target_wf:
        logger.info(f"Opening initial workflow: {target_wf}")
        set_initial_workflow(target_wf)

    # 5. Find available port
    target_port = args.port if args.port > 0 else find_available_port(start_port=5000)
    logger.info(f"Assigned local port: {target_port}")

    # 6. Start Waitress production WSGI server in background daemon thread
    server = None
    try:
        from waitress.server import create_server
        server = create_server(app, host="127.0.0.1", port=target_port, threads=args.threads, connection_limit=200)
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        logger.info(f"Waitress WSGI server started on 127.0.0.1:{target_port} with {args.threads} worker threads.")
    except Exception as e:
        logger.warning(f"Failed to start Waitress server ({e}). Falling back to standard Flask runner...")
        try:
            server_thread = threading.Thread(
                target=lambda: app.run(host="127.0.0.1", port=target_port, debug=False, use_reloader=False),
                daemon=True
            )
            server_thread.start()
        except Exception as flask_err:
            fatal_err = f"Fatal: Both Waitress and Flask failed to start on port {target_port}.\nError: {flask_err}"
            logger.critical(fatal_err)
            show_native_error_dialog("Antigravity DataFlow Startup Failure", fatal_err, log_file)
            return 1

    # 7. Wait until backend server is responsive
    if not wait_for_server(target_port, timeout=10.0):
        fatal_msg = f"Backend server failed to respond on port {target_port} within 10 seconds."
        logger.critical(fatal_msg)
        show_native_error_dialog("Antigravity DataFlow Communication Error", fatal_msg, log_file)
        return 1

    app_url = f"http://127.0.0.1:{target_port}"
    logger.info(f"Backend server is healthy and responsive at {app_url}")

    # 8. Headless mode
    if args.headless:
        logger.info("Running in headless mode. Process active until interrupted.")
        print(f"[INFO] DataFlow server running at {app_url}. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            logger.info("Shutting down headless server.")
            if server:
                server.close()
            return 0

    # 9. Browser mode requested directly
    if args.browser:
        logger.info("User requested browser mode. Launching default browser...")
        import webbrowser
        webbrowser.open(app_url)
        try:
            while True:
                time.sleep(1.0)
        except KeyboardInterrupt:
            logger.info("Shutting down browser-mode server.")
            if server:
                server.close()
            return 0

    # 10. Multi-Tier Visual Launch Hierarchy
    # Tier 1: Native PyWebView with WebView2
    logger.info("Attempting Tier 1 launch: PyWebView Native Desktop Window...")
    icon_path = get_icon_path()
    try:
        import webview
        window = webview.create_window(
            title="Antigravity DataFlow",
            url=app_url,
            width=1440,
            height=900,
            min_size=(1024, 600),
            confirm_close=False,
            zoomable=True
        )
        logger.info("PyWebView window created. Starting GUI loop (gui=edgechromium)...")
        # Blocks until window is closed by user
        webview.start(gui="edgechromium", debug=False)
        logger.info("PyWebView window closed by user.")
    except Exception as webview_err:
        logger.warning(f"Tier 1 (PyWebView) failed: {webview_err}")

        # Tier 2: Microsoft Edge App Mode
        logger.info("Attempting Tier 2 fallback: Microsoft Edge App Mode...")
        proc = launch_edge_app_mode(app_url)
        if proc:
            logger.info(f"Tier 2 (Edge App Mode) started successfully (PID {proc.pid}).")
            proc.wait()
            logger.info("Edge App Mode window closed by user.")
        else:
            # Tier 3: Default Web Browser
            logger.warning("Tier 2 (Edge App Mode) unavailable. Attempting Tier 3 fallback: Default Browser...")
            try:
                import webbrowser
                webbrowser.open(app_url)
                logger.info(f"Tier 3 (Default Browser) opened {app_url}. Keeping background server alive.")
                print(f"[INFO] Antigravity DataFlow opened in your browser at {app_url}.")
                print("[INFO] Close this window or press Ctrl+C to terminate the application.")
                while True:
                    time.sleep(1.0)
            except KeyboardInterrupt:
                logger.info("Terminated by user keyboard interrupt.")
            except Exception as browser_err:
                fatal_msg = (
                    f"Unable to launch any visual user interface.\n\n"
                    f"Tier 1 (PyWebView): {webview_err}\n"
                    f"Tier 2 (Edge App Mode): msedge.exe not found\n"
                    f"Tier 3 (Default Browser): {browser_err}"
                )
                logger.critical(fatal_msg)
                show_native_error_dialog("Antigravity DataFlow Launch Error", fatal_msg, log_file)
                return 1

    # 11. Clean shutdown
    if server:
        try:
            logger.info("Closing Waitress WSGI server.")
            server.close()
        except Exception:
            pass

    logger.info("Antigravity DataFlow Desktop Shell terminated cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""
Local Application Launcher for Antigravity DataFlow.
Starts the production WSGI server (Waitress) or Flask dev server and opens the app in your default web browser.
"""
import sys
import os
import argparse

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from backend.app import start_server

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Antigravity DataFlow Server Launcher")
    parser.add_argument("pos_port", nargs="?", type=int, default=None, help="Optional positional port (e.g. 8080)")
    parser.add_argument("--port", "-p", type=int, default=5000, help="Port to run server on (default: 5000)")
    parser.add_argument("--server", "-s", choices=["waitress", "flask"], default="waitress", help="WSGI server to use (default: waitress)")
    parser.add_argument("--threads", "-t", type=int, default=8, help="Worker threads for Waitress (default: 8)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open web browser")

    args = parser.parse_args()
    port = args.pos_port if args.pos_port is not None else args.port
    open_browser = not args.no_browser

    start_server(port=port, open_browser=open_browser, server=args.server, threads=args.threads)


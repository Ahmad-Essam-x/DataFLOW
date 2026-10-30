"""
Local-API guard for the desktop app.

The server only listens on 127.0.0.1, but any web page open in the user's browser can still try to reach it
(drive-by requests, DNS rebinding). Three checks, applied to every request when enforcement is on:
  1. Host header must be the loopback address (and the real port)     -> blocks DNS rebinding
  2. Origin / Sec-Fetch-Site must be same-origin when the browser sends them -> blocks cross-site requests
  3. /api/* and /data/outputs/* need a per-launch random token (HttpOnly, SameSite=Strict cookie issued when
     the app page is served)                                          -> a page of another origin never has it
"""
import hmac
import secrets
from urllib.parse import urlparse

from flask import Flask, Response, jsonify, request

COOKIE_NAME = "dataflow_session"
PROTECTED_PREFIXES = ("/api/", "/data/outputs/")


def _deny(reason: str, status: int = 403):
    return jsonify({"success": False, "available": False, "error": "Forbidden", "message": reason}), status


def _host_ok(host_header: str, port: int | None) -> bool:
    parsed = urlparse("//" + (host_header or "").strip().lower())
    try:
        host_port = parsed.port
    except ValueError:
        return False
    host = parsed.hostname or ""
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return False
    return port is None or host_port is None or host_port == port


def _origin_ok(origin: str, port: int | None) -> bool:
    parsed = urlparse(origin)
    if parsed.scheme != "http" or (parsed.hostname or "").lower() not in {"127.0.0.1", "localhost", "::1"}:
        return False
    return port is None or parsed.port is None or parsed.port == port


def install_local_guard(app: Flask) -> None:
    """Registers the guard. It is inert unless app.config['ENFORCE_LOCAL_GUARD'] is truthy at request time."""
    app.config.setdefault("ENFORCE_LOCAL_GUARD", False)
    app.config.setdefault("LOCAL_GUARD_PORT", None)
    app.config["LOCAL_GUARD_TOKEN"] = secrets.token_urlsafe(32)

    @app.before_request
    def _guard():
        if not app.config.get("ENFORCE_LOCAL_GUARD"):
            return None
        port = app.config.get("LOCAL_GUARD_PORT")

        if not _host_ok(request.headers.get("Host", ""), port):
            return _deny("Unexpected Host header.")

        origin = request.headers.get("Origin")
        if origin and origin != "null" and not _origin_ok(origin, port):
            return _deny("Cross-origin requests are not allowed.")
        if origin == "null":
            return _deny("Cross-origin requests are not allowed.")
        if request.headers.get("Sec-Fetch-Site", "same-origin") not in ("same-origin", "none"):
            return _deny("Cross-site requests are not allowed.")

        if request.path.startswith(PROTECTED_PREFIXES):
            supplied = request.cookies.get(COOKIE_NAME, "")
            if not hmac.compare_digest(supplied, app.config["LOCAL_GUARD_TOKEN"]):
                return _deny("Missing or invalid session token. Reload the application window.")
        return None

    @app.after_request
    def _issue_token(response: Response):
        if app.config.get("ENFORCE_LOCAL_GUARD") and request.method == "GET" and request.path == "/":
            response.set_cookie(
                COOKIE_NAME, app.config["LOCAL_GUARD_TOKEN"],
                httponly=True, samesite="Strict", path="/",
            )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

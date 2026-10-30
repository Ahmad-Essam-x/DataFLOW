"""
Support bundle: a zip the user can send to whoever supports the tool.

Contains logs, version/environment info and a redacted copy of user settings. It never contains workflows,
datasets, outputs, API keys or connection details.
"""
import io
import json
import os
import platform
import re
import sys
import zipfile
from datetime import datetime
from typing import Any, Dict

from backend._version import APP_NAME, __version__

# Settings keys that are never copied into a bundle (matched anywhere in the key name, case-insensitive).
_SENSITIVE_HINTS = ("key", "token", "secret", "password", "passwd", "pwd", "auth", "credential", "bearer", "cookie",
                    "session", "dsn", "connection", "recent_workflows", "path", "approved_hosts")
_URL_CREDENTIALS = re.compile(r"(?i)([a-z][a-z0-9+.\-]*://)[^\s@]+@")  # user:pw@ or token@ (password may contain "/")
_QUERY_SECRET = re.compile(r"(?i)([?&](?:[a-z0-9_.\-]*(?:key|token|secret|password|passwd|pwd|sig|signature|auth)[a-z0-9_.\-]*)=)[^&\s\"']+")
_HEADER_SECRET = re.compile(r"(?im)(^|[\s\"'{,])((?:proxy-)?authorization|[a-z0-9\-]*api[-_]?key|x-[a-z0-9\-]*(?:key|token|secret)|cookie|set-cookie)(\s*:\s*)[^\r\n\"'}]+")
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]+")


def scrub_text(text: str) -> str:
    """Removes credentials embedded in free text: URL userinfo, secret query parameters, credential header lines, Bearer/Basic tokens."""
    text = _URL_CREDENTIALS.sub(lambda m: m.group(1) + "<redacted>@", text)
    text = _QUERY_SECRET.sub(lambda m: m.group(1) + "<redacted>", text)
    text = _HEADER_SECRET.sub(lambda m: m.group(1) + m.group(2) + m.group(3) + "<redacted>", text)
    return _BEARER.sub(lambda m: m.group(1) + " <redacted>", text)


def _redact(value: Any, key: str = "") -> Any:
    if any(h in key.lower() for h in _SENSITIVE_HINTS):
        return "<redacted>"
    if isinstance(value, dict):
        return {k: _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, key) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


def _log_files() -> Dict[str, str]:
    from backend.logging_setup import default_log_dir
    folder = default_log_dir()
    found = {}
    if os.path.isdir(folder):
        for name in sorted(os.listdir(folder)):
            if name.lower().endswith((".log", ".log.1", ".log.2", ".log.3", ".log.4", ".log.5")):
                found[name] = os.path.join(folder, name)
    return found


def build_bundle(settings_file: str = None, data_root: str = None) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        info = {
            "app": APP_NAME,
            "version": __version__,
            "created": datetime.now().isoformat(timespec="seconds"),
            "frozen": bool(getattr(sys, "frozen", False)),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "data_root_in_use": bool(data_root),
        }
        try:
            from desktop.diagnostics import run_system_diagnostics
            info["system_diagnostics"] = run_system_diagnostics()
        except Exception as exc:  # diagnostics are best effort
            info["system_diagnostics_error"] = type(exc).__name__
        zf.writestr("info.json", json.dumps(info, indent=2, default=str))

        for name, path in _log_files().items():
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    zf.writestr(f"logs/{name}", scrub_text(fh.read()))
            except OSError:
                pass

        if settings_file and os.path.exists(settings_file):
            try:
                with open(settings_file, "r", encoding="utf-8") as fh:
                    zf.writestr("settings_redacted.json", json.dumps(_redact(json.load(fh)), indent=2))
            except Exception:
                pass

        zf.writestr("README.txt",
                    "Antigravity DataFlow support bundle.\n"
                    "Contains logs, version/environment info and redacted settings.\n"
                    "It does NOT contain workflows, datasets, outputs, API keys or connection details.\n"
                    "Logs can mention file names and folder paths; review the bundle before sharing it outside your organization.\n")
    buf.seek(0)
    return buf

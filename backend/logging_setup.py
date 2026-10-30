"""Rotating application log with full stack traces. Call setup_logging() once at startup."""
import logging
import os
import uuid
from logging.handlers import RotatingFileHandler

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_configured = False


def default_log_dir() -> str:
    home = os.environ.get("DATAFLOW_HOME")  # development/tests: keep logs with the redirected data, not the real profile
    if home:
        return os.path.join(home, "logs")
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "AntigravityDataFlow", "logs")


def setup_logging(log_dir: str = None, level: int = logging.INFO) -> str:
    """Attach a rotating file handler (5 x 2 MB) to the 'dataflow' logger. Returns the log file path."""
    global _configured
    log_dir = log_dir or default_log_dir()
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "app.log")
    if _configured:
        return log_path
    logger = logging.getLogger("dataflow")
    logger.setLevel(level)
    handler = RotatingFileHandler(log_path, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logger.addHandler(handler)
    _configured = True
    return log_path


def new_error_id() -> str:
    return uuid.uuid4().hex[:8]

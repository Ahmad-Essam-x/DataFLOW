"""Crash-safe file writes: write to a temp file in the same folder, then atomically replace the target."""
import json
import os
import tempfile
from typing import Any


def atomic_write_text(path: str, text: str, encoding: str = "utf-8") -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp_", suffix=".part")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_json(path: str, data: Any, indent: int = 2, ensure_ascii: bool = True) -> None:
    atomic_write_text(path, json.dumps(data, indent=indent, ensure_ascii=ensure_ascii))

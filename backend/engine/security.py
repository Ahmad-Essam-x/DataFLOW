"""
Security and Path Sandboxing Utilities.
Enforces workspace directory containment, sanitizes file names,
and validates file uploads to prevent path traversal and arbitrary file execution.
"""
import os
import re
from typing import List, Tuple, Optional, Set

# Allowed file extensions for data ingestion and uploads
ALLOWED_DATA_EXTENSIONS: Set[str] = {
    ".csv", ".tsv", ".txt", ".xlsx", ".xls", ".xlsm", ".xlsb", ".parquet", ".json"
}

# Maximum allowed upload file size: 100 MB
MAX_UPLOAD_SIZE_BYTES: int = 100 * 1024 * 1024


class SecurityError(Exception):
    """Raised when an operation violates security or path containment constraints."""
    pass


def sanitize_file_basename(filename: str, fallback: str = "output") -> str:
    """
    Strips directory separators, relative navigation (..), null bytes,
    and unsafe characters, returning a clean single-level file name.
    """
    if not filename or not isinstance(filename, str):
        return fallback

    # Strip directory components first
    clean = os.path.basename(filename.replace("\\", "/"))
    clean = clean.replace("\x00", "")

    # Split name and extension
    name_part, ext_part = os.path.splitext(clean)
    name_part = re.sub(r'[^a-zA-Z0-9_\- ]', '', name_part)
    name_part = re.sub(r'\s+', ' ', name_part).strip("_- ")
    ext_part = re.sub(r'[^a-zA-Z0-9]', '', ext_part)

    if not name_part and not ext_part:
        return fallback

    if ext_part:
        return f"{name_part if name_part else 'file'}.{ext_part}"
    return name_part if name_part else fallback


def is_safe_path(target_path: str, allowed_dirs: List[str]) -> bool:
    """
    Returns True if target_path canonical real path is contained strictly
    within at least one of the allowed_dirs.
    """
    if not target_path or not allowed_dirs:
        return False

    try:
        real_target = os.path.realpath(os.path.abspath(target_path))
        for allowed in allowed_dirs:
            if not allowed:
                continue
            real_allowed = os.path.realpath(os.path.abspath(allowed))
            # Must either equal the allowed directory or be a child of it
            if real_target == real_allowed or real_target.startswith(real_allowed + os.sep):
                return True
        return False
    except Exception:
        return False


def validate_safe_path(target_path: str, allowed_dirs: List[str], label: str = "Path") -> str:
    """
    Validates that target_path is strictly contained within allowed_dirs.
    Returns the canonical real path if valid, or raises SecurityError if traversal is detected.
    """
    if not is_safe_path(target_path, allowed_dirs):
        raise SecurityError(
            f"{label} security violation: Access outside allowed workspace directories is forbidden: '{target_path}'"
        )
    return os.path.realpath(os.path.abspath(target_path))


def validate_upload_file(filename: str, content_length: Optional[int] = None) -> Tuple[bool, Optional[str]]:
    """
    Validates an uploaded file's extension and declared size.
    Returns (is_valid, error_message).
    """
    if not filename:
        return False, "Filename cannot be empty."

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_DATA_EXTENSIONS:
        allowed_str = ", ".join(sorted(ALLOWED_DATA_EXTENSIONS))
        return False, f"Unsupported file extension '{ext}' is not permitted. Allowed types: {allowed_str}"

    if content_length is not None and content_length > MAX_UPLOAD_SIZE_BYTES:
        mb_limit = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
        return False, f"File size exceeds the maximum limit of {mb_limit} MB."

    return True, None

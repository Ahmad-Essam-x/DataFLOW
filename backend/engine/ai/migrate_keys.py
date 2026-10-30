"""One-time cleanup: move LLM API keys already saved in plaintext workflow files into the credential store."""
import json
import os
from typing import List

from backend.engine.ai.secrets import scrub_workflow
from backend.fileio import atomic_write_json


def scrub_saved_workflows(workflows_dir: str) -> List[str]:
    """Rewrites any workflow/template/backup/autosave JSON under workflows_dir that contains an inline API key.

    Returns the list of files that were changed. Unreadable or non-workflow files are left alone.
    """
    changed = []
    # os.walk (not glob) so hidden folders such as .backups and .autosave are included.
    paths = [
        os.path.join(root, name)
        for root, _dirs, files in os.walk(workflows_dir)
        for name in files if name.lower().endswith(".json")
    ]
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        if isinstance(data, dict) and scrub_workflow(data):
            try:
                atomic_write_json(path, data, ensure_ascii=False)
                changed.append(path)
            except Exception:
                pass
    return changed

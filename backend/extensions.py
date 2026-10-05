"""
Shared application singletons and paths for Antigravity DataFlow.
Populated during app initialization to prevent circular dependencies across blueprints.

Usage:
    import backend.extensions as ext
    ext.executor.run(workflow)

All attributes start as None and are assigned in backend/app.py at startup.
Do not access them before the app factory runs.
"""
import os
import sys
from typing import TYPE_CHECKING, Optional, Dict, Any

if TYPE_CHECKING:
    from backend.engine.executor import WorkflowExecutor
    from backend.engine.workflow_manager import WorkflowManager
    from backend.engine.cache_manager import SessionRunCacheManager

# Shared singletons — assigned in app.py before first request
executor: Optional["WorkflowExecutor"] = None
workflow_manager: Optional["WorkflowManager"] = None
cache_manager: Optional["SessionRunCacheManager"] = None

# Paths — assigned in app.py based on frozen/source detection
BASE_DIR: Optional[str] = None
DATA_DIR: Optional[str] = None
OUTPUT_DIR: Optional[str] = None
WORKFLOWS_DIR: Optional[str] = None
WORKFLOW_TEMPLATES_DIR: Optional[str] = None
WORKFLOW_TEMPLATES_USER_DIR: Optional[str] = None
USER_SETTINGS_FILE: Optional[str] = None

# Global state
INITIAL_WORKFLOW_FILE: Optional[str] = None
_app_dirty_state: Dict[str, Any] = {"is_dirty": False, "dirty_tabs_count": 0}

"""
Shared application singletons and paths for Antigravity DataFlow.
Populated during app initialization to prevent circular dependencies across blueprints.
"""
import os
import sys

# Shared singletons
executor = None
workflow_manager = None
cache_manager = None

# Paths
BASE_DIR = None
DATA_DIR = None
OUTPUT_DIR = None
WORKFLOWS_DIR = None
WORKFLOW_TEMPLATES_DIR = None
WORKFLOW_TEMPLATES_USER_DIR = None
USER_SETTINGS_FILE = None

# Global state
INITIAL_WORKFLOW_FILE = None
_app_dirty_state = {"is_dirty": False, "dirty_tabs_count": 0}

"""Run the whole suite against a throwaway data home so tests never rewrite tracked files in the repo.

DATAFLOW_HOME must be set before `backend.app` is first imported (it reads the variable at import time).
The repo's sample data/workflows are copied in so tests that open them keep working.
"""
import os
import shutil
import tempfile

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HOME = tempfile.mkdtemp(prefix="dataflow_test_home_")
os.environ["DATAFLOW_HOME"] = _HOME

for _name in ("data", "workflows"):
    _src = os.path.join(_REPO, _name)
    if os.path.isdir(_src):
        shutil.copytree(_src, os.path.join(_HOME, _name), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".cache", ".autosave", ".backups", "outputs"))


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_HOME, ignore_errors=True)

"""The shipped payload must contain only curated content: no customer cases, scratch files, or personal paths."""
import json
import os
import re
import subprocess

import pytest

import build_desktop as bd

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PERSONAL_PATH = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\"]+|OneDrive|Siemens AG", re.IGNORECASE)


def _tracked():
    out = subprocess.run(["git", "ls-files", "-z", "--", *bd.PAYLOAD_DIRS], cwd=REPO, capture_output=True)
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    return [f for f in out.stdout.decode("utf-8").split("\0") if f]


def test_only_curated_workflows_ship():
    shipped = [f for f in _tracked() if bd._ships(f) and f.startswith("workflows/")]
    top_level = {f for f in shipped if f.count("/") == 1}
    assert top_level <= bd.RELEASE_WORKFLOWS
    assert not any(f.startswith("workflows/templates/user/") for f in shipped)


@pytest.mark.parametrize("rel", ["workflows/some_customer_case.json", "workflows/scratch_test.json",
                                 "workflows/my_private_flow.json", "workflows/.autosave/x.json", "workflows/.backups/x.json",
                                 "workflows/templates/user/mine.json", "data/.cache/n1_O.feather"])
def test_known_unwanted_files_are_excluded(rel):
    if rel.startswith("data/"):
        # runtime caches are never tracked; if one were, it must still not be staged
        assert rel not in _tracked()
    else:
        assert not bd._ships(rel)


def test_shipped_files_contain_no_personal_paths():
    offenders = []
    for rel in _tracked():
        if not bd._ships(rel) or not rel.endswith(".json"):
            continue
        text = open(os.path.join(REPO, rel), encoding="utf-8", errors="ignore").read()
        if PERSONAL_PATH.search(text):
            offenders.append(rel)
    assert offenders == [], f"personal/customer paths in shipped files: {offenders}"


def test_shipped_workflows_contain_no_api_keys():
    for rel in _tracked():
        if bd._ships(rel) and rel.endswith(".json"):
            try:
                data = json.load(open(os.path.join(REPO, rel), encoding="utf-8"))
            except Exception:
                continue
            for node in (data.get("nodes", []) if isinstance(data, dict) else []):
                conn = (node.get("config") or {}).get("connection") or {}
                assert not conn.get("api_key"), f"API key in {rel}"


def test_stage_payload_copies_only_shipping_files(tmp_path):
    n = bd.stage_payload(str(tmp_path / "payload"))
    assert n > 0
    staged = [os.path.relpath(os.path.join(r, f), tmp_path / "payload").replace("\\", "/")
              for r, _d, files in os.walk(tmp_path / "payload") for f in files]
    assert all(bd._ships(f) for f in staged)
    assert "workflows/sales_customer_enrichment.json" in staged
    assert "static/js/app.js" in staged and "templates/index.html" in staged


def test_build_script_does_not_regenerate_tracked_assets():
    """Builds must not modify the repository: the icon is only generated when missing."""
    src = open(os.path.join(REPO, "build_desktop.py"), encoding="utf-8").read()
    assert "if not os.path.exists(ico_path)" in src
    assert "icon.ico" in subprocess.run(["git", "ls-files", "assets"], cwd=REPO, capture_output=True, text=True).stdout

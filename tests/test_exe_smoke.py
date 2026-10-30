"""Smoke test for the built Windows EXE (skipped unless a build exists).

Runs the real AntigravityDataFlow.exe headless against a throwaway LOCALAPPDATA, with Python removed from PATH,
and checks: boot time, frozen flag + version, the local-API guard, a full workflow run, file export, the support
bundle, migration of legacy data, and that nothing is written next to the EXE.
Set DATAFLOW_EXE to test a specific build (CI does).
"""
import http.client
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import zipfile

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.environ.get("DATAFLOW_EXE") or os.path.join(REPO, "dist", "AntigravityDataFlow", "AntigravityDataFlow.exe")

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or not os.path.exists(EXE),
    reason="needs a Windows build: run build_desktop.py (or set DATAFLOW_EXE)",
)


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Client:
    def __init__(self, port):
        self.port = port
        self.cookie = None

    def request(self, method, path, body=None, headers=None, auth=True):
        h = dict(headers or {})
        if auth and self.cookie:
            h["Cookie"] = self.cookie
        if body is not None:
            h.setdefault("Content-Type", "application/json")
            h.setdefault("Origin", f"http://127.0.0.1:{self.port}")
            body = json.dumps(body)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        conn.request(method, path, body=body, headers=h)
        r = conn.getresponse()
        return r.status, r.getheader("Set-Cookie"), r.read()

    def login(self):
        status, cookie, _ = self.request("GET", "/", auth=False)
        assert status == 200
        self.cookie = "dataflow_session=" + re.match(r"dataflow_session=([^;]+)", cookie).group(1)


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    profile = tmp_path_factory.mktemp("exe_profile")
    local = profile / "Local"
    roaming = profile / "Roaming"
    (local / "AntigravityDataFlow" / "workflows").mkdir(parents=True)
    roaming.mkdir()
    # legacy data from an older build, to exercise the one-time migration
    legacy_wf = local / "AntigravityDataFlow" / "workflows" / "legacy_flow.json"
    legacy_wf.write_text(json.dumps({"name": "legacy", "nodes": [], "connections": []}), encoding="utf-8")

    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(p for p in env.get("PATH", "").split(os.pathsep)
                                  if "python" not in p.lower() and "anaconda" not in p.lower())
    for k in ("PYTHONHOME", "PYTHONPATH", "DATAFLOW_HOME"):
        env.pop(k, None)
    env.update(LOCALAPPDATA=str(local), APPDATA=str(roaming), USERPROFILE=str(profile), HOME=str(profile))

    exe_dir = os.path.dirname(EXE)
    before = set(os.listdir(exe_dir))
    port = _free_port()
    start = time.time()
    proc = subprocess.Popen([EXE, "--headless", "--port", str(port), "--log-file", str(profile / "launch.log")],
                            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    client = Client(port)
    boot = None
    try:
        while time.time() - start < 40:
            try:
                if client.request("GET", "/healthz", auth=False)[0] == 200:
                    boot = time.time() - start
                    break
            except OSError:
                time.sleep(0.2)
        assert boot is not None, "EXE did not become healthy within 40s"
        client.login()
        yield {"client": client, "local": local, "boot": boot, "exe_dir": exe_dir, "before": before}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_boots_quickly(app):
    assert app["boot"] < 30


def test_is_frozen_and_reports_version(app):
    from backend._version import __version__
    status, _, body = app["client"].request("GET", "/api/app-info")
    info = json.loads(body)
    assert status == 200 and info["frozen"] is True
    assert info["version"] == __version__ and info["app_name"] == "Antigravity DataFlow"


def test_local_api_guard_is_active(app):
    c = app["client"]
    assert c.request("GET", "/api/app-info", auth=False)[0] == 403
    assert c.request("GET", "/api/app-info", headers={"Host": "evil.example.com"})[0] == 403
    assert c.request("POST", "/api/user-settings", {}, headers={"Origin": "https://evil.example.com"})[0] == 403


def test_tools_discovered(app):
    status, _, body = app["client"].request("GET", "/api/tools")
    assert status == 200 and len(json.loads(body)["tools"]) >= 17


def test_runs_a_sample_workflow_and_exports(app):
    c = app["client"]
    status, _, body = c.request("GET", "/api/sample-workflow/sales_customer_enrichment.json")
    assert status == 200
    wf = json.loads(body)
    wf = wf.get("workflow", wf)
    status, _, body = c.request("POST", "/api/run", wf)
    res = json.loads(body)
    assert status == 200 and res["success"] is True, res.get("error")


def test_filter_and_csv_export_download(app):
    c = app["client"]
    wf = {"name": "smoke", "nodes": [
        {"id": "in_1", "type": "input_data", "name": "in", "config": {"file_path": "customers.csv", "has_header": True}},
        {"id": "f_1", "type": "filter", "name": "f", "config": {"mode": "basic", "conditions": [
            {"column": "Segment", "operator": "==", "value": "Corporate"}]}},
        {"id": "o_1", "type": "output_data", "name": "o", "config": {"filename": "smoke_export.csv", "format": "csv"}}],
        "connections": [
            {"source": "in_1", "sourceHandle": "O", "target": "f_1", "targetHandle": "I"},
            {"source": "f_1", "sourceHandle": "T", "target": "o_1", "targetHandle": "I"}]}
    status, _, body = c.request("POST", "/api/run", wf)
    assert status == 200 and json.loads(body)["success"] is True
    status, _, body = c.request("GET", "/data/outputs/smoke_export.csv")
    lines = body.decode().strip().splitlines()
    assert status == 200 and len(lines) > 2 and "Corporate" in lines[1]


def test_schema_fit_sandbox_works_in_the_frozen_app(app):
    """Exercises multiprocessing 'spawn' inside the PyInstaller bundle."""
    c = app["client"]
    wf = {"name": "sf", "nodes": [
        {"id": "t", "type": "text_input", "name": "t", "config": {"columns": ["CustomerID", "Name"], "data": [[1, "A"]]}},
        {"id": "s", "type": "text_input", "name": "s", "config": {"columns": ["cust_id", "cust_name"], "data": [[7, "x"]]}},
        {"id": "sf", "type": "schema_fit", "name": "sf", "config": {
            "custom_code": "df = df.rename(columns={'cust_id': 'CustomerID', 'cust_name': 'Name'})"}}],
        "connections": [
            {"source": "t", "sourceHandle": "O", "target": "sf", "targetHandle": "T"},
            {"source": "s", "sourceHandle": "O", "target": "sf", "targetHandle": "S"}]}
    status, _, body = c.request("POST", "/api/run", wf)
    res = json.loads(body)
    assert status == 200 and res["success"] is True, res.get("error")


def test_support_bundle_downloads(app):
    status, _, body = app["client"].request("GET", "/api/diagnostics/export")
    assert status == 200
    import io
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        assert "info.json" in zf.namelist()


def test_legacy_data_was_migrated(app):
    status, _, body = app["client"].request("GET", "/api/workflow/open?filename=legacy_flow.json")
    assert (app["local"] / "AntigravityDataFlow" / "workflows" / "legacy_flow.json").exists()


def test_nothing_written_next_to_the_exe(app):
    after = set(os.listdir(app["exe_dir"]))
    assert after - app["before"] == set(), f"new files next to the EXE: {after - app['before']}"

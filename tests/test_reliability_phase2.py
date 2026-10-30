"""Phase 2 reliability: atomic writes, error ids without leaked paths, version source, single-instance guard."""
import json
import os
import sys

import pytest

from backend.fileio import atomic_write_json, atomic_write_text


def test_atomic_write_json_roundtrip_and_no_temp_left(tmp_path):
    target = tmp_path / "settings.json"
    atomic_write_json(str(target), {"a": 1, "b": [1, 2]})
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1, "b": [1, 2]}
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


def test_atomic_write_keeps_old_file_when_serialization_fails(tmp_path):
    target = tmp_path / "settings.json"
    atomic_write_json(str(target), {"ok": True})
    with pytest.raises(TypeError):
        atomic_write_json(str(target), {"bad": object()})
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


def test_atomic_write_text_creates_missing_folder(tmp_path):
    target = tmp_path / "nested" / "dir" / "f.txt"
    atomic_write_text(str(target), "hello")
    assert target.read_text(encoding="utf-8") == "hello"


def test_app_info_reports_single_version_source():
    from backend._version import APP_NAME, __version__
    from backend.app import app
    data = app.test_client().get("/api/app-info").get_json()
    assert data["version"] == __version__
    assert data["app_name"] == APP_NAME


def test_unhandled_api_error_returns_ref_id_and_hides_detail():
    from backend.app import create_app
    app = create_app()  # fresh instance: Flask refuses new routes once an app has served a request
    secret = r"C:\Users\someone\private\secret_path.csv"

    @app.route("/api/_test_boom")
    def _boom():
        raise RuntimeError(f"failed reading {secret}")

    app.config["TESTING"] = False
    app.config["PROPAGATE_EXCEPTIONS"] = False
    resp = app.test_client().get("/api/_test_boom")
    body = resp.get_json()
    assert resp.status_code == 500
    assert body["error_id"] and body["error_id"] in body["message"]
    assert secret not in json.dumps(body)


def test_http_errors_keep_their_status_code():
    from backend.app import app
    resp = app.test_client().post("/api/app-info")  # GET-only route
    assert resp.status_code == 405


@pytest.mark.skipif(sys.platform != "win32", reason="named mutex is Windows-only")
def test_single_instance_mutex_blocks_second_holder():
    import ctypes
    import uuid
    import desktop_app
    # Unique name: must not collide with a real DataFlow window the developer has open.
    name = f"Local\\DataFlowTest.{uuid.uuid4().hex}"
    kernel32 = ctypes.windll.kernel32
    desktop_app._instance_mutex = None
    assert desktop_app.acquire_single_instance(name) is True
    first = desktop_app._instance_mutex
    assert desktop_app.acquire_single_instance(name) is False  # second holder of the same name is refused
    kernel32.CloseHandle(desktop_app._instance_mutex)
    kernel32.CloseHandle(first)
    desktop_app._instance_mutex = None


def test_default_mutex_name_is_the_per_user_app_name():
    import desktop_app
    assert desktop_app.SINGLE_INSTANCE_MUTEX == "Local\\AntigravityDataFlow.SingleInstance"

"""Support bundle: useful for troubleshooting, but must never carry workflows, data, keys or file paths."""
import json
import zipfile

from backend._version import __version__
from backend.app import app
from backend.diagnostics_bundle import _redact, build_bundle


def test_endpoint_returns_zip_with_info_and_readme():
    r = app.test_client().get("/api/diagnostics/export")
    assert r.status_code == 200
    assert r.mimetype == "application/zip"
    assert "dataflow_support_" in r.headers["Content-Disposition"]
    import io
    with zipfile.ZipFile(io.BytesIO(r.data)) as zf:
        names = zf.namelist()
        assert "info.json" in names and "README.txt" in names
        info = json.loads(zf.read("info.json"))
    assert info["version"] == __version__
    assert info["python"] and info["platform"]


def test_settings_are_redacted_and_workflows_excluded(tmp_path):
    settings = tmp_path / "user_settings.json"
    settings.write_text(json.dumps({
        "theme": "dark",
        "llm_api_key": "sk-secret",
        "recent_workflows": [{"name": "Client Payroll", "path": r"C:\Users\me\OneDrive\Cases\payroll.json"}],
        "llm_approved_hosts": ["api.openai.com"],
        "nested": {"db_password": "hunter2", "zoom": 1.1},
    }), encoding="utf-8")
    import io
    with zipfile.ZipFile(build_bundle(settings_file=str(settings))) as zf:
        blob = "\n".join(zf.read(n).decode("utf-8", "ignore") for n in zf.namelist())
        names = zf.namelist()
    for leaked in ("sk-secret", "hunter2", "Client Payroll", "OneDrive", "payroll.json"):
        assert leaked not in blob
    assert "dark" in blob and "1.1" in blob  # harmless settings stay useful
    assert not any(n.endswith((".csv", ".xlsx", ".feather", "workflow.json")) for n in names)


def test_redact_handles_nested_and_lists():
    out = _redact({"a": [{"token": "t", "ok": 1}], "path_hint": "x", "fine": "y"})
    assert out == {"a": [{"token": "<redacted>", "ok": 1}], "path_hint": "<redacted>", "fine": "y"}


def test_bundle_needs_session_token_when_guard_is_on():
    from backend.app import create_app
    guarded = create_app()
    guarded.config["ENFORCE_LOCAL_GUARD"] = True
    guarded.config["LOCAL_GUARD_PORT"] = 5999
    r = guarded.test_client().get("/api/diagnostics/export", headers={"Host": "127.0.0.1:5999"})
    assert r.status_code == 403


def test_about_dialog_has_no_hardcoded_version():
    import os
    html = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "index.html"), encoding="utf-8").read()
    assert "Version 2.0.0" not in html
    assert 'id="about-version-number"' in html
    assert 'data-action="help:export-diagnostics"' in html


def test_redaction_covers_more_key_names_and_embedded_credentials():
    from backend.diagnostics_bundle import scrub_text
    out = _redact({
        "bearer": "a", "cookie": "b", "session": "c", "passwd": "d", "dsn": "postgres://u:pw@h/db",
        "connection": {"base_url": "https://u:pw@host"}, "approved_hosts": ["intranet.example"],
        "url": "https://user:pass@example.com/path", "note": "see https://example.com/ok", "theme": "dark",
        "list": [{"token": "t"}, "http://a:b@c/d"],
    })
    flat = json.dumps(out)
    for leaked in ("pw", "user:pass", "a:b@", "intranet.example"):
        assert leaked not in flat
    assert out["theme"] == "dark" and out["note"] == "see https://example.com/ok"
    scrubbed = scrub_text("GET https://u:pw@host/v1 Authorization: Bearer sk-abcdefgh12345 Basic dXNlcjpwYXNz1234")
    assert "pw@" not in scrubbed and "sk-abcdefgh12345" not in scrubbed and "dXNlcjpwYXNz1234" not in scrubbed
    assert scrubbed.startswith("GET https://<redacted>@host/v1")


def test_log_files_in_the_bundle_are_scrubbed(tmp_path, monkeypatch):
    import io
    from backend import diagnostics_bundle as db
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "app.log").write_text("ERROR request to https://u:secretpw@api.example.com failed; Bearer sk-live-1234567890", encoding="utf-8")
    monkeypatch.setattr("backend.logging_setup.default_log_dir", lambda: str(logs))
    with zipfile.ZipFile(db.build_bundle()) as zf:
        text = zf.read("logs/app.log").decode()
    assert "secretpw" not in text and "sk-live-1234567890" not in text and "api.example.com" in text

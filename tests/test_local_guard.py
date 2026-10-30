"""Local API guard: Host / Origin / session-token enforcement for the desktop server."""
import pytest

from backend.app import create_app
from backend.security_guard import COOKIE_NAME

PORT = 5123


@pytest.fixture
def guarded():
    app = create_app()
    app.config["ENFORCE_LOCAL_GUARD"] = True
    app.config["LOCAL_GUARD_PORT"] = PORT
    return app


def _client_with_cookie(app):
    c = app.test_client()
    r = c.get("/", headers={"Host": f"127.0.0.1:{PORT}"})
    assert r.status_code == 200
    set_cookie = r.headers.get("Set-Cookie", "")
    assert COOKIE_NAME in set_cookie and "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie
    return c


def test_guard_inert_by_default():
    app = create_app()
    assert app.test_client().get("/api/app-info", headers={"Host": "evil.example.com"}).status_code == 200


def test_valid_session_gets_through(guarded):
    c = _client_with_cookie(guarded)
    r = c.get("/api/app-info", headers={"Host": f"127.0.0.1:{PORT}"})
    assert r.status_code == 200


@pytest.mark.parametrize("host", ["evil.example.com", f"evil.example.com:{PORT}", "127.0.0.1.evil.com", "10.0.0.5:5123", "127.0.0.1:9999"])
def test_wrong_host_rejected_even_with_cookie(guarded, host):
    c = _client_with_cookie(guarded)
    assert c.get("/api/app-info", headers={"Host": host}).status_code == 403


@pytest.mark.parametrize("origin", ["https://evil.example.com", "http://evil.example.com", f"http://127.0.0.1:{PORT + 1}", "null", "http://localhost.evil.com"])
def test_foreign_origin_rejected_even_with_cookie(guarded, origin):
    c = _client_with_cookie(guarded)
    r = c.post("/api/user-settings", json={"x": 1}, headers={"Host": f"127.0.0.1:{PORT}", "Origin": origin})
    assert r.status_code == 403


def test_same_origin_post_allowed(guarded):
    c = _client_with_cookie(guarded)
    r = c.post("/api/user-settings", json={"x": 1},
               headers={"Host": f"127.0.0.1:{PORT}", "Origin": f"http://127.0.0.1:{PORT}", "Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200


def test_cross_site_fetch_metadata_rejected(guarded):
    c = _client_with_cookie(guarded)
    r = c.get("/api/app-info", headers={"Host": f"127.0.0.1:{PORT}", "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_missing_or_wrong_token_rejected(guarded):
    r = guarded.test_client().get("/api/app-info", headers={"Host": f"127.0.0.1:{PORT}"})
    assert r.status_code == 403
    c = guarded.test_client()
    c.set_cookie(COOKIE_NAME, "not-the-token", domain="127.0.0.1")
    assert c.get("/api/app-info", headers={"Host": f"127.0.0.1:{PORT}"}).status_code == 403


def test_outputs_downloads_need_token_too(guarded):
    r = guarded.test_client().get("/data/outputs/anything.csv", headers={"Host": f"127.0.0.1:{PORT}"})
    assert r.status_code == 403


def test_healthz_is_open_but_still_host_checked(guarded):
    assert guarded.test_client().get("/healthz", headers={"Host": f"127.0.0.1:{PORT}"}).status_code == 200
    assert guarded.test_client().get("/healthz", headers={"Host": "evil.example.com"}).status_code == 403


def test_token_differs_per_app_instance():
    assert create_app().config["LOCAL_GUARD_TOKEN"] != create_app().config["LOCAL_GUARD_TOKEN"]


def test_security_headers_present(guarded):
    r = guarded.test_client().get("/healthz", headers={"Host": f"127.0.0.1:{PORT}"})
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "no-referrer"

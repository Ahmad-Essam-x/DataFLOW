"""Round-2 review follow-ups: proxy bypass for local endpoints, exact-localhost, Azure host match, wider credential scrubbing."""
from unittest import mock

import pytest

from backend.diagnostics_bundle import scrub_text
from backend.engine.ai import egress
from backend.engine.ai import http as llm_http
from backend.engine.ai.provider_openai_compat import _is_azure_host


def test_local_endpoints_bypass_environment_proxies():
    with mock.patch("backend.engine.ai.http.requests.post") as post:
        llm_http.post("http://127.0.0.1:11434/api/generate", json={})
    assert post.call_args.kwargs["proxies"] == {"http": None, "https": None}


def test_remote_endpoints_keep_normal_proxy_behaviour():
    with mock.patch("backend.engine.ai.http.requests.get") as get:
        llm_http.get("https://api.openai.com/v1/models")
    assert "proxies" not in get.call_args.kwargs
    assert get.call_args.kwargs["allow_redirects"] is False


def test_proxy_not_used_for_loopback_in_a_real_request(monkeypatch):
    import requests
    monkeypatch.setenv("HTTP_PROXY", "http://10.9.9.9:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://10.9.9.9:3128")
    seen = {}

    class Probe(requests.adapters.HTTPAdapter):
        def send(self, request, **kw):
            seen["proxies"] = dict(kw.get("proxies") or {})
            raise requests.ConnectionError("probe")

    real_get = requests.get

    def patched_get(url, **kw):
        with requests.Session() as s:
            s.mount("http://", Probe())
            return s.get(url, **kw)

    monkeypatch.setattr("backend.engine.ai.http.requests.get", patched_get)
    with pytest.raises(requests.ConnectionError):
        llm_http.get("http://localhost:11434/api/tags")
    assert seen["proxies"] == {}
    assert real_get  # silence unused warning


@pytest.mark.parametrize("host", ["a.localhost", "evil.localhost", "x.y.localhost"])
def test_only_the_exact_name_localhost_is_local(host):
    assert egress.is_local_host(host) is False


def test_localhost_and_loopback_addresses_are_local():
    for host in ("localhost", "127.0.0.1", "::1", "127.0.0.2"):
        assert egress.is_local_host(host) is True


@pytest.mark.parametrize("url,expected", [
    ("https://myres.openai.azure.com/openai/v1", True),
    ("https://openai.azure.com", True),
    ("https://evil.example/x?openai.azure.com", False),
    ("https://openai.azure.com.evil.example/v1", False),
    ("https://notopenai.azure.com.evil.io", False),
    ("http://localhost:1234/v1", False),
    ("not a url", False),
])
def test_azure_is_detected_from_the_host_only(url, expected):
    assert _is_azure_host(url) is expected


@pytest.mark.parametrize("text,gone", [
    ("GET https://h/v1/models?key=AIzaSyABC123&alt=json", "AIzaSyABC123"),
    ("https://h/?api_key=sk-abc123&x=1", "sk-abc123"),
    ("Authorization: sk-proj-abcdef", "sk-proj-abcdef"),
    ("api-key: abcdef123456", "abcdef123456"),
    ("x-goog-api-key: AIzaXYZ", "AIzaXYZ"),
    ("https://TOKEN123@host/path", "TOKEN123"),
    ("https://u:p/ss@h/", "p/ss"),
    ("Bearer abc", "abc"),
    ("Cookie: dataflow_session=abcDEF", "abcDEF"),
    ('{"Authorization": "Bearer sk-live-123456"}', "sk-live-123456"),
])
def test_credential_shapes_are_scrubbed(text, gone):
    assert gone not in scrub_text(text)


@pytest.mark.parametrize("text", [
    "normal log line: loaded 100 rows in 14.2ms",
    r"see https://example.com/docs?page=2 and folder C:\Users\me\x.csv",
    "email me@example.com about https://example.com",
    "url https://h/?api_key=sk-abc123&x=1",
])
def test_ordinary_text_keeps_its_meaning(text):
    out = scrub_text(text)
    for keep in ("loaded 100 rows", "page=2", "me@example.com", "&x=1"):
        if keep in text:
            assert keep in out

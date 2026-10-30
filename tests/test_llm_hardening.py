"""Hardening from the independent security review: endpoint parsing, LAN/metadata consent, redirects, key scoping,
and keeping API keys out of DataFrame attrs / cache files."""
import glob
import json
import os
from unittest import mock

import pandas as pd
import pytest

from backend.engine.ai import egress as egress_mod
from backend.engine.ai import secrets as llm_secrets
from backend.engine.nodes.llm_override import LLMOverrideNode

KEY = "sk-super-secret-1234567890"


@pytest.fixture(autouse=True)
def memory_store(monkeypatch):
    monkeypatch.setattr(llm_secrets, "HAS_KEYRING", False)
    monkeypatch.setattr(llm_secrets, "_MEMORY", {})


@pytest.fixture
def egress_on(monkeypatch, tmp_path):
    import backend.extensions as ext
    monkeypatch.setattr(egress_mod, "ENFORCE", True)
    monkeypatch.setattr(egress_mod, "_session_approved", set())
    monkeypatch.setattr(ext, "USER_SETTINGS_FILE", str(tmp_path / "user_settings.json"))
    return egress_mod


UNSAFE_URLS = [
    "http://evil.com\\@localhost:11434",         # backslash: urllib and requests disagree on the host
    "http://evil.com\\.localhost",
    "http://localhost@evil.com/v1",              # userinfo
    "http://user:pw@localhost:11434",
    "ftp://localhost/x",
    "file:///etc/passwd",
    "http://local host:11434",                   # whitespace
    "http://localhost:11434/\r\nHost: evil",     # control characters
    "//evil.com",
]


@pytest.mark.parametrize("url", UNSAFE_URLS)
def test_ambiguous_or_unsafe_endpoints_are_rejected(url):
    from backend.engine.ai.provider_registry import get_provider
    with pytest.raises(egress_mod.InvalidEndpoint):
        get_provider("ollama", {"base_url": url})


@pytest.mark.parametrize("url", UNSAFE_URLS)
def test_unsafe_endpoints_are_rejected_even_when_enforcement_is_on(egress_on, url):
    from backend.engine.ai.provider_registry import get_provider
    with pytest.raises(egress_mod.InvalidEndpoint):
        get_provider("ollama", {"base_url": url})


@pytest.mark.parametrize("url", ["", "http://localhost:11434", "http://127.0.0.1:1234/v1", "http://[::1]:11434", "http://localhost.:11434"])
def test_only_this_machine_is_local(egress_on, url):
    from backend.engine.ai.provider_registry import get_provider
    get_provider("ollama", {"base_url": url})


@pytest.mark.parametrize("url", ["http://192.168.1.20:8000", "http://10.0.0.5/v1", "http://169.254.169.254/latest", "http://172.16.0.9"])
def test_lan_and_metadata_addresses_need_approval(egress_on, url):
    from backend.engine.ai.provider_registry import get_provider
    with pytest.raises(egress_on.EgressNotApproved):
        get_provider("ollama", {"base_url": url})


def test_checked_host_is_the_host_requests_contacts():
    import requests
    from urllib3.util import parse_url
    for url in ["http://api.example.com:8080/v1", "https://API.Example.com/v1", "http://[2001:db8::1]:11434"]:
        prepared = requests.Request("GET", url).prepare()
        assert egress_mod.host_of(url) == (parse_url(prepared.url).host or "").lower().strip("[]")


def test_approve_host_rejects_non_host_input(egress_on):
    for bad in ("", "http://x", "a/b", "a@b", "a b"):
        with pytest.raises(ValueError):
            egress_on.approve_host(bad)


def test_redirects_are_never_followed():
    from backend.engine.ai import http as llm_http
    with mock.patch("backend.engine.ai.http.requests.post") as post, mock.patch("backend.engine.ai.http.requests.get") as get:
        llm_http.post("http://x", json={})
        llm_http.get("http://x")
    assert post.call_args.kwargs["allow_redirects"] is False
    assert get.call_args.kwargs["allow_redirects"] is False


def test_all_providers_use_the_no_redirect_client():
    import re
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "backend", "engine", "ai")
    for name in ("provider_gemini.py", "provider_ollama.py", "provider_openai_compat.py"):
        src = open(os.path.join(base, name), encoding="utf-8").read()
        assert not re.search(r"\brequests\.(post|get)\(", src), name


def test_stored_key_is_not_shared_between_http_and_https():
    llm_secrets.store_api_key("openai", "https://api.openai.com/v1", KEY)
    assert llm_secrets.resolve_api_key("openai", "https://api.openai.com/v1") == KEY
    assert llm_secrets.resolve_api_key("openai", "https://api.openai.com:443/v1") == KEY
    assert llm_secrets.resolve_api_key("openai", "http://api.openai.com/v1") == ""
    assert llm_secrets.resolve_api_key("openai", "https://api.openai.com:8443/v1") == ""


def test_stored_key_never_attached_to_cleartext_remote_endpoint():
    from backend.engine.ai.provider_registry import get_provider
    llm_secrets.store_api_key("openai_compat", "http://api.example.com/v1", KEY)
    assert get_provider("openai_compat", {"base_url": "http://api.example.com/v1"}).api_key == ""
    llm_secrets.store_api_key("openai_compat", "http://localhost:1234/v1", KEY)
    assert get_provider("openai_compat", {"base_url": "http://localhost:1234/v1"}).api_key == KEY


def test_llm_override_key_is_not_in_dataframe_attrs_or_cache_files(tmp_path):
    from backend.engine.cache_manager import SpillableRunDataCache
    node = LLMOverrideNode("o1", {"provider_type": "openai", "model": "m", "connection": {"api_key": KEY}})
    df = node.execute({})["M"]
    assert KEY not in json.dumps(df.attrs, default=str)
    assert llm_secrets.resolve_api_key("openai", "") == KEY  # still usable downstream through the store

    cache = SpillableRunDataCache("run_attrs", cache_root_dir=str(tmp_path), max_in_memory_nodes=1)
    cache["override"] = {"M": df}
    cache["other"] = {"O": pd.DataFrame({"a": [1]})}  # evicts the override frame to disk
    spilled = glob.glob(os.path.join(cache.cache_dir, "*"))
    assert spilled, "expected the override frame to be spilled for this check to mean anything"
    assert KEY.encode() not in b"".join(open(p, "rb").read() for p in spilled)


def test_schema_fit_still_resolves_the_key_for_an_override_connection():
    from backend.engine.nodes.schema_fit import SchemaFitNode
    m_frame = LLMOverrideNode("o1", {"provider_type": "openai", "model": "m", "connection": {"api_key": KEY}}).execute({})["M"]
    seen = {}

    def fake_get_provider(ptype, conn):
        from backend.engine.ai.provider_registry import get_provider as real
        seen["key"] = real(ptype, conn).api_key
        raise RuntimeError("stop here")

    with mock.patch("backend.engine.nodes.schema_fit.get_provider", fake_get_provider):
        SchemaFitNode("sf", {}).execute({"T": pd.DataFrame({"A": [1]}), "S": pd.DataFrame({"a": [1]}), "M": m_frame})
    assert seen["key"] == KEY

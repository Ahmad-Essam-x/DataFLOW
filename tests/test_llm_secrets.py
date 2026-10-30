"""LLM API keys must never reach workflow JSON, autosaves, backups, templates, or node output; they resolve from the store."""
import glob
import json
import os
from unittest import mock

import pandas as pd
import pytest

from backend.engine.ai import secrets as llm_secrets
from backend.engine.ai.provider_gemini import GeminiProvider
from backend.engine.ai.provider_base import LLMConfig
from backend.engine.nodes.llm_override import LLMOverrideNode
from backend.engine.workflow_manager import WorkflowManager

KEY = "sk-super-secret-1234567890"


@pytest.fixture(autouse=True)
def memory_store(monkeypatch):
    """Use only the in-memory store: tests must never touch the real Windows Credential Manager."""
    monkeypatch.setattr(llm_secrets, "HAS_KEYRING", False)
    monkeypatch.setattr(llm_secrets, "_MEMORY", {})


def _wf(provider="openai", base_url="", key=KEY, node_type="llm_process"):
    return {
        "name": "wf",
        "nodes": [{
            "id": "n1", "type": node_type, "name": "LLM", "x": 0, "y": 0,
            "config": {"provider_type": provider, "model": "gpt-4o-mini",
                       "connection": {"base_url": base_url, "api_key": key}},
        }],
        "connections": [],
    }


def _all_text(root):
    out = []
    for path in glob.glob(os.path.join(root, "**", "*"), recursive=True):
        if os.path.isfile(path):
            out.append(open(path, encoding="utf-8", errors="ignore").read())
    return "\n".join(out)


@pytest.fixture
def manager(tmp_path):
    (tmp_path / "workflows").mkdir()
    (tmp_path / "data").mkdir()
    return WorkflowManager(str(tmp_path / "workflows"), str(tmp_path / "data"), str(tmp_path))


def test_secret_name_normalizes_endpoint():
    assert llm_secrets.secret_name("OpenAI", "") == llm_secrets.secret_name("openai", "https://api.openai.com/v1/")
    assert llm_secrets.secret_name("openai", "https://a.example/v1") != llm_secrets.secret_name("openai", "https://b.example/v1")


def test_save_workflow_strips_key_and_remembers_it(manager, tmp_path):
    result = manager.save_workflow(_wf())
    assert result["success"]
    on_disk = _all_text(str(tmp_path))
    assert KEY not in on_disk
    saved = json.loads(open(os.path.join(tmp_path, "workflows", result["file"]), encoding="utf-8").read())
    conn = saved["nodes"][0]["config"]["connection"]
    assert conn["api_key"] == "" and conn["key_stored"] is True
    assert llm_secrets.resolve_api_key("openai", "") == KEY


def test_overwrite_creates_backup_without_key(manager, tmp_path):
    manager.save_workflow(_wf())
    manager.save_workflow(_wf())  # second save backs up the first
    assert glob.glob(os.path.join(tmp_path, "workflows", ".backups", "*.json"))
    assert KEY not in _all_text(str(tmp_path))


def test_autosave_has_no_key(manager, tmp_path):
    manager.save_autosave("sess1", _wf())
    assert glob.glob(os.path.join(tmp_path, "workflows", ".autosave", "*.json"))
    assert KEY not in _all_text(str(tmp_path))


def test_commit_checkpoint_has_no_key(manager, tmp_path):
    saved = manager.save_workflow(_wf())
    manager.commit_checkpoint(saved["file"], _wf(), message="m")
    assert KEY not in _all_text(str(tmp_path))


def test_exported_package_has_no_key(manager):
    import zipfile
    buf = manager.export_package(_wf())
    with zipfile.ZipFile(buf) as zf:
        assert all(KEY not in zf.read(n).decode("utf-8", "ignore") for n in zf.namelist())


def test_saving_does_not_mutate_callers_workflow(manager):
    wf = _wf()
    manager.save_workflow(wf)
    assert wf["nodes"][0]["config"]["connection"]["api_key"] == KEY


@pytest.mark.parametrize("node_type", ["llm_process", "llm_override", "schema_fit"])
def test_all_llm_node_types_are_scrubbed(manager, tmp_path, node_type):
    manager.save_workflow(_wf(node_type=node_type))
    assert KEY not in _all_text(str(tmp_path))


def test_template_save_has_no_key(tmp_path):
    from backend.app import app
    import backend.extensions as ext
    user_dir = tmp_path / "tpl"
    user_dir.mkdir()
    with mock.patch.object(ext, "WORKFLOW_TEMPLATES_USER_DIR", str(user_dir)):
        r = app.test_client().post("/api/templates/save", json={"name": "t", "workflow": _wf()})
    assert r.status_code == 200
    assert KEY not in _all_text(str(user_dir))


def test_provider_uses_stored_key_when_node_has_none():
    from backend.engine.ai.provider_registry import get_provider
    llm_secrets.store_api_key("openai", "", KEY)
    provider = get_provider("openai", {"base_url": "", "api_key": ""})
    assert provider.api_key == KEY


def test_provider_remembers_key_when_supplied():
    from backend.engine.ai.provider_registry import get_provider
    get_provider("openai", {"api_key": KEY})
    assert get_provider("openai", {}).api_key == KEY


def test_keys_are_per_endpoint():
    from backend.engine.ai.provider_registry import get_provider
    llm_secrets.store_api_key("openai", "https://a.example/v1", "key-a")
    assert get_provider("openai", {"base_url": "https://b.example/v1"}).api_key == ""


def test_llm_override_never_exposes_key_in_output_table():
    node = LLMOverrideNode("o1", {"provider_type": "openai", "model": "m", "connection": {"api_key": KEY}})
    df = node.execute({})["M"]
    assert KEY not in df.to_csv() and KEY[:4] not in df.to_csv() and KEY[-4:] not in df.to_csv()
    assert dict(zip(df["Setting"], df["Value"]))["API Key"] == "stored"


def test_gemini_key_is_sent_in_header_not_url():
    provider = GeminiProvider(api_key=KEY)
    resp = mock.Mock(status_code=200)
    resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "hi"}]}}], "usageMetadata": {}}
    with mock.patch("backend.engine.ai.provider_gemini.requests.post", return_value=resp) as post, \
         mock.patch("backend.engine.ai.provider_gemini.requests.get", return_value=mock.Mock(status_code=200, json=lambda: {"models": []})) as get:
        provider.generate("sys", "user", LLMConfig(model="gemini-2.0-flash"))
        provider.test_connection()
        provider.list_models()
    for call in (post.call_args, *get.call_args_list):
        assert KEY not in call.args[0]
        assert call.kwargs["headers"]["x-goog-api-key"] == KEY


def test_models_get_endpoint_ignores_api_key_query_param():
    from backend.app import app
    with mock.patch("backend.engine.ai.provider_registry.get_provider") as gp:
        gp.return_value.list_models.return_value = []
        app.test_client().get("/api/ai/models?provider=openai&api_key=leak&base_url=http://x")
    connection = gp.call_args.args[1]
    assert "api_key" not in connection


def test_startup_migration_scrubs_existing_plaintext_files(tmp_path):
    from backend.engine.ai.migrate_keys import scrub_saved_workflows
    for sub in ("", ".backups", ".autosave", "templates/user"):
        folder = tmp_path / sub
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "old.json").write_text(json.dumps(_wf()), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "clean.json").write_text(json.dumps({"name": "x", "nodes": []}), encoding="utf-8")

    changed = scrub_saved_workflows(str(tmp_path))

    assert len(changed) == 4
    assert KEY not in _all_text(str(tmp_path))
    assert llm_secrets.resolve_api_key("openai", "") == KEY
    assert (tmp_path / "broken.json").read_text(encoding="utf-8") == "{not json"
    assert scrub_saved_workflows(str(tmp_path)) == []  # idempotent


# ---------------------------------------------------------------- egress consent
@pytest.fixture
def egress_on(monkeypatch, tmp_path):
    from backend.engine.ai import egress
    import backend.extensions as ext
    monkeypatch.setattr(egress, "ENFORCE", True)
    monkeypatch.setattr(egress, "_session_approved", set())
    monkeypatch.setattr(ext, "USER_SETTINGS_FILE", str(tmp_path / "user_settings.json"))
    return egress


@pytest.mark.parametrize("url", ["", "http://localhost:11434", "http://127.0.0.1:1234/v1", "http://[::1]:11434", "http://localhost.:11434"])
def test_local_endpoints_need_no_approval(egress_on, url):
    from backend.engine.ai.provider_registry import get_provider
    get_provider("ollama", {"base_url": url})


def test_remote_host_blocked_until_approved(egress_on):
    from backend.engine.ai.provider_registry import get_provider
    with pytest.raises(egress_on.EgressNotApproved) as exc:
        get_provider("openai", {"base_url": "", "api_key": "k"})
    assert "api.openai.com" in str(exc.value) and "[egress:api.openai.com]" in str(exc.value)
    egress_on.approve_host("api.openai.com")
    get_provider("openai", {"base_url": "", "api_key": "k"})


def test_approval_persists_and_can_be_revoked(egress_on):
    egress_on.approve_host("API.Example.com")
    assert egress_on.approved_hosts() == ["api.example.com"]
    egress_on._session_approved.clear()
    assert egress_on.approved_hosts() == ["api.example.com"]  # read back from user_settings.json
    egress_on.revoke_host("api.example.com")
    assert egress_on.approved_hosts() == []


def test_approving_one_host_does_not_approve_lookalikes(egress_on):
    from backend.engine.ai.provider_registry import get_provider
    egress_on.approve_host("api.openai.com")
    with pytest.raises(egress_on.EgressNotApproved):
        get_provider("openai", {"base_url": "https://api.openai.com.evil.example/v1", "api_key": "k"})


def test_approval_api_roundtrip(egress_on):
    from backend.app import app
    c = app.test_client()
    assert c.post("/api/ai/approve-host", json={}).status_code == 400
    r = c.post("/api/ai/approve-host", json={"base_url": "https://api.example.com/v1"})
    assert r.get_json()["hosts"] == ["api.example.com"]
    assert c.get("/api/ai/approved-hosts").get_json()["hosts"] == ["api.example.com"]
    assert c.delete("/api/ai/approve-host", json={"host": "api.example.com"}).get_json()["hosts"] == []


def test_llm_process_node_surfaces_consent_error(egress_on):
    from backend.engine.nodes.ai import LLMProcessNode
    from backend.engine.nodes.base import NodeExecutionError
    node = LLMProcessNode("n", {"provider_type": "openai", "model": "m", "user_prompt_template": "{{a}}",
                                "connection": {"api_key": "k"}})
    with pytest.raises(NodeExecutionError) as exc:
        node.execute({"I": pd.DataFrame({"a": ["x"]})})
    assert "[egress:api.openai.com]" in str(exc.value)


def test_schema_fit_does_not_silently_fall_back_on_consent(egress_on):
    from backend.engine.nodes.schema_fit import SchemaFitNode
    node = SchemaFitNode("n", {"provider_type": "openai", "model": "m", "connection": {"api_key": "k"}})
    with pytest.raises(egress_on.EgressNotApproved):
        node.execute({"T": pd.DataFrame({"A": [1]}), "S": pd.DataFrame({"a": [1]})})

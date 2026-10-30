"""
LLM API key storage. Keys never live in workflow JSON, autosaves, backups or templates.

They are kept in the OS credential store (Windows Credential Manager via `keyring`), addressed by
provider + endpoint. If no credential store is available they are held in memory for the session only
(never written to disk).

Flow:
  * On the way to disk, scrub_workflow() moves every node's connection.api_key into the store and blanks it.
  * On the way to a provider, get_provider() calls resolve_api_key() when the node has no key of its own.
"""
import re
import threading
from typing import Any, Dict, Optional

try:
    import keyring
    HAS_KEYRING = True
except ImportError:  # pragma: no cover
    keyring = None
    HAS_KEYRING = False

SERVICE = "antigravity_dataflow_llm"
LLM_NODE_TYPES = frozenset({"llm_process", "llm_override", "schema_fit"})
_MEMORY: Dict[str, str] = {}
_LOCK = threading.Lock()

_DEFAULT_ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com",
}


def secret_name(provider_type: str, base_url: str = "") -> str:
    """Stable credential name: provider + scheme://host:port (default endpoint when none given).

    The scheme is part of the name, so a key stored for https://host is never found for http://host.
    """
    provider = (provider_type or "").strip().lower()
    url = (base_url or "").strip() or _DEFAULT_ENDPOINTS.get(provider, "")
    m = re.match(r"^(https?)://([^/?#]+)", url.lower())
    if m:
        scheme, authority = m.groups()
        default_port = {"http": ":80", "https": ":443"}[scheme]
        if authority.endswith(default_port):
            authority = authority[: -len(default_port)]
        return f"{provider}@{scheme}://{authority}"
    return f"{provider}@{url.lower().rstrip('/')}"


def store_api_key(provider_type: str, base_url: str, api_key: str) -> None:
    name = secret_name(provider_type, base_url)
    with _LOCK:
        _MEMORY[name] = api_key
        if HAS_KEYRING:
            try:
                keyring.set_password(SERVICE, name, api_key)
            except Exception:  # no usable backend: session-only
                pass


def resolve_api_key(provider_type: str, base_url: str = "") -> str:
    name = secret_name(provider_type, base_url)
    with _LOCK:
        if name in _MEMORY:
            return _MEMORY[name]
    if HAS_KEYRING:
        try:
            value = keyring.get_password(SERVICE, name)
            if value:
                with _LOCK:
                    _MEMORY[name] = value
                return value
        except Exception:
            pass
    return ""


def has_api_key(provider_type: str, base_url: str = "") -> bool:
    return bool(resolve_api_key(provider_type, base_url))


def _scrub_node(node: Dict[str, Any]) -> bool:
    """Moves a node's inline API key to the credential store. Returns True if a key was removed."""
    if not isinstance(node, dict) or node.get("type") not in LLM_NODE_TYPES:
        return False
    cfg = node.get("config")
    if not isinstance(cfg, dict):
        return False
    conn = cfg.get("connection")
    if not isinstance(conn, dict):
        return False
    key = conn.get("api_key")
    if not key or not isinstance(key, str):
        return False
    store_api_key(cfg.get("provider_type", "ollama"), conn.get("base_url", ""), key.strip())
    conn["api_key"] = ""
    conn["key_stored"] = True
    return True


def scrub_workflow(workflow: Dict[str, Any]) -> int:
    """Removes inline LLM API keys from a workflow dict in place. Returns how many were moved."""
    if not isinstance(workflow, dict):
        return 0
    return sum(1 for n in workflow.get("nodes", []) if _scrub_node(n))


def mask(key: Optional[str]) -> str:
    return "stored" if key else "None"

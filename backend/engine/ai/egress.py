"""
Data-egress consent for LLM tools.

LLM Process and Schema Fit send cell values (and sample values) to the configured endpoint. Only endpoints on
this machine (loopback) need no consent. Any other host, including LAN addresses, must be approved once; the
approval is stored per host in user_settings.json and the run is blocked until then.

The URL is parsed with urllib3 - the same parser `requests` uses to open the connection - so the host that is
checked is the host that is contacted. Ambiguous URLs (backslashes, control characters, userinfo, odd schemes)
are rejected outright rather than interpreted.
"""
import ipaddress
import json
import os
from typing import List, Optional

from urllib3.exceptions import LocationParseError
from urllib3.util import parse_url

SETTINGS_KEY = "llm_approved_hosts"
ENFORCE = False  # turned on by backend.app at startup; unit tests with mocked providers leave it off

_session_approved: set = set()  # fallback when settings cannot be read/written


class EgressNotApproved(Exception):
    """Raised when an LLM node targets a remote host the user has not approved."""

    def __init__(self, host: str):
        self.host = host
        super().__init__(
            f"Data from this workflow would be sent to '{host}', which has not been approved yet. "
            f"Approve it once to continue. [egress:{host}]"
        )


class InvalidEndpoint(ValueError):
    """The configured endpoint URL is ambiguous or unsafe."""


def parse_endpoint(url: str):
    """Returns urllib3's parsed URL for a base_url, or raises InvalidEndpoint. Empty string -> None."""
    raw = (url or "").strip()
    if not raw:
        return None
    if any(ord(c) < 33 or ord(c) == 127 for c in raw) or "\\" in raw:
        raise InvalidEndpoint("Endpoint URL contains whitespace, control characters or backslashes.")
    try:
        parsed = parse_url(raw)
    except LocationParseError as exc:
        raise InvalidEndpoint(f"Endpoint URL is not valid: {exc}") from exc
    if parsed.scheme not in ("http", "https"):
        raise InvalidEndpoint("Endpoint URL must start with http:// or https://")
    if parsed.auth:
        raise InvalidEndpoint("Endpoint URL must not contain credentials (user:password@).")
    if not parsed.host:
        raise InvalidEndpoint("Endpoint URL has no host.")
    return parsed


def host_of(url: str) -> str:
    parsed = parse_endpoint(url)
    return (parsed.host or "").lower().strip("[]").rstrip(".") if parsed else ""


def is_local_host(host: str) -> bool:
    """True only for this machine: 'localhost' or a loopback address. LAN/private/link-local are remote."""
    if not host:
        return True  # no endpoint configured -> provider default decides; defaults are checked by name
    if host == "localhost":  # not *.localhost: only the resolver decides where those go
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_cleartext_remote(url: str) -> bool:
    parsed = parse_endpoint(url)
    return bool(parsed and parsed.scheme == "http" and not is_local_host(host_of(url)))


def _settings_path() -> Optional[str]:
    import backend.extensions as ext
    return getattr(ext, "USER_SETTINGS_FILE", None)


def approved_hosts() -> List[str]:
    hosts = set(_session_approved)
    path = _settings_path()
    if path and os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                hosts.update(h.lower() for h in json.load(fh).get(SETTINGS_KEY, []))
        except Exception:
            pass
    return sorted(hosts)


def approve_host(host: str) -> List[str]:
    host = (host or "").strip().lower().rstrip(".")
    if not host or any(c in host for c in "/\\@ \t\r\n"):
        raise ValueError("A bare host name is required (for example api.openai.com).")
    _session_approved.add(host)
    path = _settings_path()
    if path:
        from backend.fileio import atomic_write_json
        data = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                data = {}
        data[SETTINGS_KEY] = sorted(set(h.lower() for h in data.get(SETTINGS_KEY, [])) | {host})
        try:
            atomic_write_json(path, data)
        except Exception:
            pass
    return approved_hosts()


def revoke_host(host: str) -> List[str]:
    host = (host or "").strip().lower().rstrip(".")
    _session_approved.discard(host)
    path = _settings_path()
    if path and os.path.exists(path):
        try:
            from backend.fileio import atomic_write_json
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            data[SETTINGS_KEY] = [h for h in data.get(SETTINGS_KEY, []) if h.lower() != host]
            atomic_write_json(path, data)
        except Exception:
            pass
    return approved_hosts()


def require_approval(base_url: str) -> None:
    """Raises InvalidEndpoint for ambiguous URLs, EgressNotApproved for unapproved remote hosts."""
    host = host_of(base_url)
    if is_local_host(host) or host in approved_hosts():
        return
    raise EgressNotApproved(host)

"""HTTP calls made by LLM providers.

* Redirects are never followed: a redirect would re-send the request body (row data and credentials) to a host the
  user never approved.
* Environment proxies are ignored for local endpoints, so "local" data cannot be routed to a proxy host. Remote
  endpoints still honor the usual proxy settings (corporate networks need them).
"""
import requests

from backend.engine.ai import egress

# Re-exported so providers keep their existing exception handling (requests.ConnectionError / Timeout).
ConnectionError = requests.ConnectionError
Timeout = requests.Timeout

_NO_PROXY = {"http": None, "https": None}


def _is_local(url) -> bool:
    try:
        return egress.is_local_host(egress.host_of(url))
    except egress.InvalidEndpoint:
        return False


def _prepare(url, kwargs):
    kwargs["allow_redirects"] = False
    if _is_local(url):
        kwargs.setdefault("proxies", dict(_NO_PROXY))
    return kwargs


def post(url, **kwargs):
    return requests.post(url, **_prepare(url, kwargs))


def get(url, **kwargs):
    return requests.get(url, **_prepare(url, kwargs))

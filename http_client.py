"""Small shared HTTP helpers with retries and a browser-like profile."""

import os
import random
import time

import requests
import urllib3

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

TIMEOUT = 30
RETRIES = 3
RETRY_STATUSES = {429, 500, 502, 503, 504}


def _tls_verify():
    """Return requests `verify` value from GSTIN_TLS_VERIFY (default False for NIC chains)."""
    val = os.getenv("GSTIN_TLS_VERIFY", "").strip()
    if not val or val.lower() in ("0", "false", "no"):
        return False
    if val.lower() in ("1", "true", "yes"):
        return True
    return val  # custom CA bundle path


if _tls_verify() is False:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class SourceError(Exception):
    """Raised when a source cannot answer (captcha, network, site error)."""

    def __init__(self, kind, detail=""):
        super().__init__("%s: %s" % (kind, detail) if detail else kind)
        self.kind = kind
        self.detail = detail


def new_session(referer: str | None = None) -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                      "image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }
    )
    if referer:
        s.headers["Referer"] = referer
    return s


def request(session: requests.Session, method: str, url: str, **kwargs):
    """Perform an HTTP request, retrying transient network and 5xx/429 errors."""
    kwargs.setdefault("timeout", TIMEOUT)
    kwargs.setdefault("verify", _tls_verify())
    last_exc = None
    last_resp = None
    for attempt in range(RETRIES):
        try:
            resp = session.request(method, url, **kwargs)
            if resp.status_code not in RETRY_STATUSES or attempt == RETRIES - 1:
                return resp
            last_resp = resp
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
        time.sleep(0.8 * (attempt + 1))

    if last_resp is not None:
        return last_resp
    raise SourceError("network", str(last_exc))


def require_image(resp, label: str = "captcha") -> str:
    """Validate an image HTTP response and return its media type."""
    ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
    if resp.status_code != 200 or not ctype.lower().startswith("image/"):
        raise SourceError(
            "site",
            "%s endpoint returned HTTP %s (%s, %d bytes)"
            % (label, resp.status_code, ctype or "unknown", len(resp.content)),
        )
    if not resp.content:
        raise SourceError("site", "%s endpoint returned empty body" % label)
    return ctype

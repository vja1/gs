"""Retry orchestration, TTL caching, and source failover."""

import logging
import os
import threading
import time

from http_client import SourceError

log = logging.getLogger("gstin")

SOURCES = {"ewaybill": "ewaybill_source", "gst": "gst_source"}
DEFAULT_CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))
MAX_CACHE_ENTRIES = 512

_cache_lock = threading.Lock()
_cache: dict[tuple[str, str], tuple[float, dict]] = {}


def _module(name):
    return __import__(SOURCES[name])


def clear_cache() -> None:
    """Clear the in-memory lookup cache."""
    with _cache_lock:
        _cache.clear()


def _get_cached(gstin: str, source: str, ttl: int) -> dict | None:
    if ttl <= 0:
        return None
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get((gstin, source))
        if not entry:
            return None
        expires_at, payload = entry
        if now >= expires_at:
            _cache.pop((gstin, source), None)
            return None
        return dict(payload)


def _set_cached(gstin: str, source: str, payload: dict, ttl: int) -> None:
    if ttl <= 0:
        return
    now = time.monotonic()
    with _cache_lock:
        if len(_cache) >= MAX_CACHE_ENTRIES:
            expired = [k for k, (exp, _) in _cache.items() if now >= exp]
            for k in expired:
                _cache.pop(k, None)
            if len(_cache) >= MAX_CACHE_ENTRIES:
                oldest = next(iter(_cache))
                _cache.pop(oldest, None)
        _cache[(gstin, source)] = (now + ttl, dict(payload))


def lookup(
    gstin: str,
    source: str = "auto",
    attempts: int = 8,
    backoff: float = 0.3,
    use_cache: bool = False,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    refresh: bool = False,
) -> dict:
    """Look a GSTIN up, retrying on captcha failures.

    `source` may be "auto" (e-waybill first, then GST portal), or a specific
    source name. Returns the detail dict with `source`, `attempts`, and
    `cached` added.
    """
    if source not in ("auto",) and source not in SOURCES:
        raise ValueError("unknown source %r" % source)

    if use_cache and not refresh:
        cached = _get_cached(gstin, source, cache_ttl)
        if cached is not None:
            cached["cached"] = True
            cached["attempts"] = 0
            return cached

    order = list(SOURCES) if source == "auto" else [source]
    tried = 0
    errors = []
    for name in order:
        module = _module(name)
        for attempt in range(attempts):
            tried += 1
            try:
                data = module.lookup(gstin)
                data["source"] = name
                data["attempts"] = tried
                data["cached"] = False
                if use_cache:
                    _set_cached(gstin, source, data, cache_ttl)
                return data
            except SourceError as exc:
                if exc.kind == "unknown-gstin":
                    raise
                errors.append({"source": name, "kind": exc.kind, "detail": exc.detail})
                log.info("%s attempt %s failed: %s", name, attempt + 1, exc)
                if exc.kind in ("site", "network", "parse"):
                    break  # this source is unusable right now, move on
                time.sleep(backoff)
            except Exception as exc:  # noqa: BLE001 - keep the API alive
                errors.append({"source": name, "kind": "unexpected", "detail": str(exc)})
                log.warning("%s attempt %s crashed: %s", name, attempt + 1, exc)
                time.sleep(backoff)

    raise SourceError("failed", "; ".join(
        "%s/%s: %s" % (e["source"], e["kind"], e["detail"]) for e in errors[-6:]
    ))

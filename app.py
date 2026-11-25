"""Flask HTTP wrapper around the GSTIN lookup service.

    GET /lookup/<gstin>?source=auto&attempts=8

Responses are JSON with optional in-memory TTL caching, per-IP rate limiting,
and optional API key protection (set `API_KEY` in the environment).
"""

from collections import deque
import hmac
import logging
import os
import threading
import time

from flask import Flask, jsonify, request

import gstin_utils
import lookup_service
from http_client import SourceError

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = Flask(__name__)

_rate_lock = threading.Lock()
_rate_buckets: dict[str, deque[float]] = {}
_META_KEYS = {"source", "attempts", "cached"}


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes")


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _check_api_key() -> bool:
    expected = os.getenv("API_KEY", "").strip()
    if not expected:
        return True
    provided = request.headers.get("X-API-Key", "").strip()
    if not provided:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            provided = auth[7:].strip()
    if not provided:
        provided = request.args.get("api_key", "").strip()
    return bool(provided) and hmac.compare_digest(provided, expected)


def _check_rate_limit() -> bool:
    try:
        limit = int(os.getenv("RATE_LIMIT_PER_MIN", "30"))
    except ValueError:
        limit = 30
    if limit <= 0:
        return True
    now = time.monotonic()
    cutoff = now - 60.0
    ip = _client_ip()
    with _rate_lock:
        bucket = _rate_buckets.setdefault(ip, deque())
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True


@app.after_request
def _add_cors_headers(response):
    if os.getenv("ENABLE_CORS", "true").strip().lower() not in ("0", "false", "no"):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    return response


@app.get("/")
def index():
    return jsonify(
        service="gstin-lookup",
        endpoints={
            "lookup": "/lookup/<GSTIN>?source=auto|ewaybill|gst&attempts=8",
            "health": "/health",
        },
        example="/lookup/27AAACT2727Q1ZW",
    )


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.get("/lookup/<gstin>")
def lookup(gstin: str):
    if not _check_api_key():
        return jsonify(success=False, error="unauthorized", reason="missing or invalid API key"), 401
    if not _check_rate_limit():
        return jsonify(success=False, error="rate_limited", reason="too many requests, try again shortly"), 429

    valid, reason = gstin_utils.validate(gstin)
    if not valid:
        return jsonify(success=False, error="invalid_gstin", reason=reason), 400

    source = request.args.get("source", "auto").lower()
    try:
        attempts = max(1, min(int(request.args.get("attempts", 8)), 25))
    except ValueError:
        return jsonify(success=False, error="bad_request", reason="attempts must be a number"), 400

    include_raw = _truthy(request.args.get("raw"))
    refresh = _truthy(request.args.get("refresh"))

    gstin = gstin_utils.normalise(gstin)
    try:
        data = lookup_service.lookup(
            gstin,
            source=source,
            attempts=attempts,
            use_cache=True,
            refresh=refresh,
        )
    except ValueError as exc:
        return jsonify(success=False, error="bad_request", reason=str(exc)), 400
    except SourceError as exc:
        status = 404 if exc.kind == "unknown-gstin" else 503
        return jsonify(success=False, error=exc.kind, reason=exc.detail), status

    body = {
        k: v for k, v in data.items()
        if not k.startswith("_") and k not in _META_KEYS and (include_raw or k != "raw")
    }
    return jsonify(
        success=True,
        gstin=gstin,
        state=gstin_utils.state_of(gstin),
        source=data.get("source"),
        attempts=data.get("attempts"),
        cached=bool(data.get("cached", False)),
        data=body,
    )


if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", "8000")),
            debug=_truthy(os.getenv("DEBUG")))

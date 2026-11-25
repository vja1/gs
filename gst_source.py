"""Taxpayer lookup against the GST portal public "Search Taxpayer" service.

The portal renders a 6-digit captcha and validates it against a `CaptchaCookie`
plus the JSON body `{"gstin": ..., "captcha": ...}` posted to
`/services/api/search/taxpayerDetails`.
"""

import json
import time

import captcha_solver
from http_client import SourceError, new_session, request

BASE = "https://services.gst.gov.in"
PAGE = BASE + "/services/searchtp"
CAPTCHA = BASE + "/services/captcha?rnd=%s"
API = BASE + "/services/api/search/taxpayerDetails"


def _to_dict(payload: dict) -> dict:
    pradr = payload.get("pradr") or {}
    addr = pradr.get("addr") or {}
    address = (pradr.get("adr") or "").strip() or " ".join(
        str(addr.get(part) or "").strip()
        for part in ("flno", "bno", "st", "loc", "landmark", "city", "dst", "stcd", "pncd")
        if str(addr.get(part) or "").strip()
    )
    nba = payload.get("nba") or []
    if isinstance(nba, str):
        nba = [nba]

    return {
        "gstin": payload.get("gstin"),
        "legal_name": payload.get("lgnm"),
        "trade_name": payload.get("tradeNam"),
        "status": payload.get("sts"),
        "registration_date": payload.get("rgdt"),
        "constitution": payload.get("ctb"),
        "dealer_type": payload.get("dty"),
        "taxpayer_type": payload.get("taxp"),
        "nature_of_business": [n for n in nba if n],
        "principal_place": {
            "address": address or None,
            "lat": addr.get("lt"),
            "lng": addr.get("lg"),
        },
        "centre_jurisdiction": payload.get("ctj"),
        "state_jurisdiction": payload.get("stj"),
        "einvoice_status": payload.get("einvoiceStatus"),
        "raw": payload,
    }


def lookup(gstin: str) -> dict:
    """One full attempt. Raises SourceError('captcha') when the code is wrong."""
    session = new_session(PAGE)
    session.headers["Accept"] = "application/json, text/plain, */*"
    request(session, "GET", PAGE)
    captcha = request(session, "GET", CAPTCHA % ("%d" % int(time.time() * 1000)))
    readings = captcha_solver.solve(captcha.content, captcha_solver.DIGITS)
    if not readings:
        raise SourceError("captcha", "could not read the captcha")
    code = readings[0][0]

    response = request(
        session,
        "POST",
        API,
        data=json.dumps({"gstin": gstin, "captcha": code}),
        headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
        },
    )
    try:
        payload = response.json()
    except ValueError:
        raise SourceError("site", "non-JSON response (HTTP %s)" % response.status_code)

    if payload.get("errorCode") == "SWEB_9000":
        raise SourceError("captcha", "captcha rejected")
    if payload.get("errorCode"):
        message = payload.get("message") or payload.get("errorCode")
        raise SourceError("unknown-gstin", message)

    error = payload.get("error") or {}
    if error.get("message"):
        raise SourceError("unknown-gstin", error.get("message"))

    data = _to_dict(payload)
    data["_captcha"] = code
    return data

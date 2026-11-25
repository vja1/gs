"""Taxpayer lookup against the e-Waybill public "Taxpayer Search" page.

The page is an ASP.NET WebForms postback guarded by a 6-character CAPTCHA, so a
lookup is: load the form, fetch + solve the captcha, post the form back and read
the result table. Every call uses a fresh session because the server raises
(custom error page) on stale view state.
"""

import re

from bs4 import BeautifulSoup

import captcha_solver
from http_client import SourceError, new_session, request, require_image

BASE = "https://ewaybillgst.gov.in"
PAGE = BASE + "/Others/TaxPayerSearch.aspx"
CAPTCHA = BASE + "/Captcha.aspx"

RESULT_LABELS = {
    "gstin": ("gstin", "gstin/uin", "gstin / uin"),
    "legal_name": ("legal name", "legal name of business"),
    "trade_name": ("trade name", "trade nam"),
    "registration_date": ("registration date", "date of registration"),
    "constitution": ("constitution of business", "constitution"),
    "principal_place": ("principal place of business", "address of principal place of business"),
    "nature_of_business": ("nature of business", "nature of business activity"),
    "status": ("gstin status", "status"),
    "dealer_type": ("dealer type", "taxpayer type"),
    "centre_jurisdiction": ("centre jurisdiction",),
    "state_jurisdiction": ("state jurisdiction",),
}

NOT_FOUND_MARKERS = (
    "no record found",
    "invalid gstin",
    "gstin does not exist",
    "not found",
)


def _hidden(form_html: str) -> dict:
    soup = BeautifulSoup(form_html, "lxml")
    fields = {}
    for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        tag = soup.find("input", {"name": name})
        if tag is None or not tag.has_attr("value"):
            raise SourceError("parse", "missing %s" % name)
        fields[name] = tag["value"]
    return fields


def _label_key(label: str):
    text = re.sub(r"\s+", " ", label.strip().lower()).rstrip(":").strip()
    for key, needles in RESULT_LABELS.items():
        if text in needles:
            return key
    for key, needles in RESULT_LABELS.items():
        if any(n in text for n in needles):
            return key
    return None


def parse_result(html: str) -> dict:
    """Extract the detail table into a normalised dict; empty dict when absent."""
    soup = BeautifulSoup(html, "lxml")
    raw_fields = {}

    for table in soup.find_all("table"):
        header = {}
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            if all(c.name == "th" for c in cells) and not header:
                for index, cell in enumerate(cells):
                    key = _label_key(cell.get_text())
                    if key and key not in header.values():
                        header[index] = key
                continue
            if cells[0].name == "th":
                # one or more "label | value" pairs inside a single row
                for index in range(0, len(cells) - 1, 2):
                    key = _label_key(cells[index].get_text())
                    value = cells[index + 1].get_text(" ", strip=True)
                    if key and key not in raw_fields and value:
                        raw_fields[key] = value
                continue
            if header:  # value row under a heading row
                for index, cell in enumerate(cells):
                    key = header.get(index)
                    value = cell.get_text(" ", strip=True)
                    if key and key not in raw_fields and value:
                        raw_fields[key] = value
                continue
            key = _label_key(cells[0].get_text())
            if not key or key in raw_fields:
                continue
            value = cells[1].get_text(" ", strip=True)
            if value:
                raw_fields[key] = value

    # single-cell "label : value" blocks
    if not raw_fields:
        for cell in soup.find_all(["td", "div"]):
            text = cell.get_text(" ", strip=True)
            if ":" not in text or len(text) > 220:
                continue
            label, _, value = text.partition(":")
            key = _label_key(label)
            if key and key not in raw_fields and value.strip():
                raw_fields[key] = value.strip()

    if not raw_fields:
        return {}

    nba = raw_fields.get("nature_of_business")
    if isinstance(nba, str):
        nba_list = [part.strip() for part in re.split(r"[,;]", nba) if part.strip()]
    else:
        nba_list = nba or []

    address = raw_fields.get("principal_place")
    return {
        "gstin": raw_fields.get("gstin"),
        "legal_name": raw_fields.get("legal_name"),
        "trade_name": raw_fields.get("trade_name"),
        "status": raw_fields.get("status"),
        "registration_date": raw_fields.get("registration_date"),
        "constitution": raw_fields.get("constitution"),
        "dealer_type": raw_fields.get("dealer_type"),
        "taxpayer_type": None,
        "nature_of_business": nba_list,
        "principal_place": {
            "address": address or None,
            "lat": None,
            "lng": None,
        },
        "centre_jurisdiction": raw_fields.get("centre_jurisdiction"),
        "state_jurisdiction": raw_fields.get("state_jurisdiction"),
        "einvoice_status": None,
    }


def lookup(gstin: str) -> dict:
    """One full attempt. Raises SourceError('captcha') when the code is wrong."""
    session = new_session()
    page = request(session, "GET", PAGE)
    if page.status_code != 200 or "txtSearchGSTIN" not in page.text:
        raise SourceError("site", "search form did not load (HTTP %s)" % page.status_code)

    fields = _hidden(page.text)
    captcha = request(session, "GET", CAPTCHA)
    ctype = require_image(captcha)

    readings = captcha_solver.solve(captcha.content)
    if not readings:
        raise SourceError(
            "captcha",
            "could not read the captcha (%s, %d bytes)"
            % (ctype, len(captcha.content)),
        )
    code = readings[0][0]

    payload = {
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        "__LASTFOCUS": "",
        "__VIEWSTATE": fields["__VIEWSTATE"],
        "__VIEWSTATEGENERATOR": fields["__VIEWSTATEGENERATOR"],
        "__VIEWSTATEENCRYPTED": "",
        "__EVENTVALIDATION": fields["__EVENTVALIDATION"],
        "__SCROLLPOSITIONX": "0",
        "__SCROLLPOSITIONY": "0",
        "ctl00$ContentPlaceHolder1$txtSearchGSTIN": gstin,
        "ctl00$ContentPlaceHolder1$txtCaptcha": code,
        "ctl00$ContentPlaceHolder1$btnGo": "Go",
    }
    session.headers["Referer"] = PAGE
    session.headers["Origin"] = BASE
    post = request(session, "POST", PAGE, data=payload, allow_redirects=False)

    if post.status_code in (301, 302):
        location = post.headers.get("Location", "")
        if "CustomError" in location:
            raise SourceError("site", "server error page (%s)" % location)
        post = request(session, "GET",
                       BASE + location if location.startswith("/") else location)

    body = post.text
    lowered = body.lower()
    if "captcha" in lowered and ("invalid" in lowered or "incorrect" in lowered):
        raise SourceError("captcha", "captcha rejected")

    detail = parse_result(body)
    if not detail:
        if any(marker in lowered for marker in NOT_FOUND_MARKERS):
            raise SourceError("unknown-gstin", "GSTIN not found on e-Waybill portal")
        raise SourceError("captcha" if "txtSearchGSTIN" in body else "empty",
                          "no result rows in response")
    detail["_captcha"] = code
    return detail

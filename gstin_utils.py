"""GSTIN helpers: validation, checksum and state lookup."""

import re

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z][Z][0-9A-Z]$")
UIN_RE = re.compile(r"^[0-9]{4}[A-Z]{3}[0-9]{5}[UO][N][0-9A-Z]$")

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana", "07": "Delhi",
    "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur",
    "15": "Mizoram", "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
    "97": "Other Territory", "99": "Centre Jurisdiction",
}


def normalise(gstin: str) -> str:
    return (gstin or "").strip().upper().replace(" ", "")


def checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        value = ALPHABET.index(ch)
        factor = 2 if i % 2 else 1
        total += value * factor
        total += value * factor // len(ALPHABET)
    return ALPHABET[(len(ALPHABET) - total % len(ALPHABET)) % len(ALPHABET)]


def validate(gstin: str) -> tuple[bool, str]:
    """Return (is_valid, reason)."""
    gstin = normalise(gstin)
    if not gstin:
        return False, "GSTIN is empty"
    if len(gstin) != 15:
        return False, "GSTIN must be 15 characters"
    if GSTIN_RE.match(gstin):
        if gstin[:2] not in STATE_CODES:
            return False, "Unknown state code %s" % gstin[:2]
        if checksum_char(gstin[:14]) != gstin[14]:
            return False, "Checksum digit does not match"
        return True, ""
    if UIN_RE.match(gstin):
        return True, ""
    return False, "Does not match the GSTIN/UIN format"


def state_of(gstin: str) -> str | None:
    return STATE_CODES.get(normalise(gstin)[:2])

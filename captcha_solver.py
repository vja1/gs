"""CAPTCHA solver for the NIC / GST family of 6-character CAPTCHAs.

Two visual styles are supported with one pipeline:

* e-Waybill (broker): blue text on a white dotted background with a long
  horizontal strike-through line and a second, vertically offset copy.
* GST portal: black text on a grey grid with red strike-through lines.

The pipeline segments on darkness/saturation, erases the strike lines, and runs
a PP-OCR recognition model over the cleaned line plus a per-character fallback.
"""

import cv2
import numpy as np
from rapidocr_onnxruntime import RapidOCR

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"
ALLOWED = LETTERS + DIGITS

_engine = RapidOCR()
TARGET_H = 64


def _decode(raw: bytes):
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    if img.shape[0] < 110:
        f = 140.0 / img.shape[0]
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_CUBIC)
    return img


def _drop_red(img):
    """Blank out red strike-through pixels so they stop gluing glyphs together."""
    b, g, r = cv2.split(img.astype(np.int16))
    red = (((r - g) > 35) & ((r - b) > 35)).astype(np.uint8) * 255
    red = cv2.dilate(red, np.ones((3, 3), np.uint8))
    out = img.copy()
    out[red > 0] = (255, 255, 255)
    return out


def _sat_mask(img):
    """Blue-style captchas: saturated glyphs on a light background."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1]
    m = ((s > 110) * 255).astype(np.uint8)
    m = cv2.medianBlur(m, 3)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    out = np.zeros_like(m)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= 40:
            out[lab == i] = 255
    return out


def _text_mask(img):
    """Local adaptive threshold: glyphs are darker than their own neighbourhood."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    m = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                              cv2.THRESH_BINARY_INV, 31, 12)
    m = cv2.medianBlur(m, 3)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    out = np.zeros_like(m)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= 40:
            out[lab == i] = 255
    return out


def _strip_lines(mask):
    """Erase long horizontal strike-throughs, then reconnect the cut strokes."""
    h, w = mask.shape
    out = mask
    for frac in (0.30, 0.55):
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(11, int(w * frac)), 1))
        line = cv2.morphologyEx(out, cv2.MORPH_OPEN, kernel)
        if line.any():
            line = cv2.dilate(line, np.ones((2, 1), np.uint8))
            out = cv2.subtract(out, line)
    return cv2.morphologyEx(out, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))


def _norm(m, pad=8):
    if m is None or m.size == 0:
        return None
    scale = TARGET_H / m.shape[0]
    m = cv2.resize(m, (max(1, int(m.shape[1] * scale)), TARGET_H), interpolation=cv2.INTER_CUBIC)
    m = cv2.copyMakeBorder(m, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    return cv2.cvtColor(m, cv2.COLOR_GRAY2BGR)


def _crop(mask, pad=4):
    pts = cv2.findNonZero(mask)
    if pts is None:
        return None
    x, y, w, h = cv2.boundingRect(pts)
    return _norm(mask[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad])


def _rec(imgs):
    out = []
    try:
        res = _engine.text_recognizer(imgs)
    except Exception:
        return out
    if isinstance(res, tuple):
        res = res[0]
    for r in res or []:
        try:
            txt, score = str(r[0]), float(r[1])
        except Exception:
            continue
        out.append((txt, score))
    return out


def _split_chars(mask):
    cols = (mask > 0).sum(axis=0)
    boxes, start, gap = [], None, 0
    for i, c in enumerate(cols):
        if c > 0:
            if start is None:
                start = i
            gap = 0
        elif start is not None:
            gap += 1
            if gap >= 3:
                boxes.append((start, i - gap))
                start = None
    if start is not None:
        boxes.append((start, len(cols) - 1))
    if not 5 <= len(boxes) <= 7:
        return []
    return [x for x in (_norm(mask[:, max(0, a - 2):b + 3]) for a, b in boxes) if x is not None]


def clean(text, charset):
    return "".join(c for c in text.upper().replace(" ", "") if c in charset)


CONFUSION = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2", "S": "5",
             "B": "8", "G": "6", "T": "7", "A": "4", "J": "1", "U": "0"}


def to_digits(text):
    return "".join(CONFUSION.get(c, c) for c in text.upper().replace(" ", "") if c.isalnum())


def normalise(text, charset):
    """Map letter look-alikes to digits when only digits are allowed."""
    if charset is DIGITS and any(c in LETTERS for c in text.upper()):
        return "".join(c for c in to_digits(text) if c in charset)
    return clean(text, charset)



def solve(raw: bytes, charset: str = ALLOWED) -> list:
    """Return candidate 6-character readings, most confident first."""
    img = _decode(raw)
    if img is None:
        return []
    img = _drop_red(img)
    masks = [_text_mask(img), _sat_mask(img)]

    cands = []
    for mask in masks:
        stripped = _strip_lines(mask)
        for m in (stripped, mask):
            line = _crop(m)
            if line is not None:
                cands.extend(_rec([line]))
        chars = _split_chars(stripped)
        if chars:
            reads = _rec(chars)
            if len(reads) == len(chars):
                cands.append(("".join(t for t, _ in reads), min(s for _, s in reads)))

    # colour original, cropped to the ink bbox
    pts = cv2.findNonZero(masks[0])
    if pts is not None:
        x, y, w, h = cv2.boundingRect(pts)
        crop = img[max(0, y - 6):y + h + 6, max(0, x - 6):x + w + 6]
        scale = TARGET_H / crop.shape[0]
        crop = cv2.resize(crop, (max(1, int(crop.shape[1] * scale)), TARGET_H))
        cands.extend(_rec([cv2.copyMakeBorder(crop, 8, 8, 8, 8, cv2.BORDER_CONSTANT,
                                              value=(255, 255, 255))]))

    seen, uniq = set(), []
    for text, score in sorted(cands, key=lambda c: -c[1]):
        text = normalise(text, charset)
        variants = [text]
        if len(text) == 7:  # PP-OCR often bolts a spurious edge character on
            variants = [text[1:], text[:6], text]
        for v in variants:
            if len(v) == 6 and v not in seen:
                seen.add(v)
                uniq.append((v, score))
    return uniq

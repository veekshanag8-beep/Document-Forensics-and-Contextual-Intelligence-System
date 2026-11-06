"""Deterministic validators and normalisers for common identifiers and values."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

# --- Verhoeff checksum (used by 12-digit national ID numbers) -----------------
_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]
_INV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_valid(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_check_digit(num: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


PAN_RE = re.compile(r"^[A-Z]{3}[PCHFATBLJG][A-Z][0-9]{4}[A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def norm_id(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


# --- Amounts -------------------------------------------------------------------
_AMT_RE = re.compile(r"-?\d[\d,]*(?:\.\d{1,2})?")


def parse_amount(s: str) -> Optional[float]:
    if s is None:
        return None
    t = str(s).replace("O", "0").replace("o", "0") if re.search(r"\d", str(s)) else str(s)
    m = _AMT_RE.search(t.replace(" ", ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def fmt_amount(v: Optional[float]) -> str:
    if v is None:
        return "-"
    neg = v < 0
    v = abs(v)
    whole, frac = f"{v:.2f}".split(".")
    # Indian digit grouping: last 3, then groups of 2
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return ("-" if neg else "") + whole + "." + frac


# --- Dates ---------------------------------------------------------------------
_DATE_FORMATS = ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%d/%m/%y"]


def parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    t = re.sub(r"\s+", " ", str(s).strip())
    m = re.search(r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2} [A-Za-z]{3,9} \d{4}", t)
    if m:
        t = m.group(0)
    for f in _DATE_FORMATS:
        try:
            return datetime.strptime(t, f).date()
        except ValueError:
            continue
    return None


def age_on(dob: date, on: date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


# --- Text normalisation -------------------------------------------------------
_HONORIFICS = {"mr", "mrs", "ms", "miss", "dr", "shri", "smt"}


def norm_name(s: str) -> str:
    t = re.sub(r"[^a-z ]", " ", (s or "").lower())
    toks = [w for w in t.split() if w not in _HONORIFICS]
    return " ".join(toks)


def norm_company(s: str) -> str:
    t = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    stop = {"pvt", "private", "ltd", "limited", "llp", "inc", "co", "company", "the"}
    return " ".join(w for w in t.split() if w not in stop)


def norm_address(s: str) -> str:
    t = re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())
    return " ".join(t.split())


def pincode(s: str) -> Optional[str]:
    m = re.search(r"\b(\d{6})\b", s or "")
    return m.group(1) if m else None

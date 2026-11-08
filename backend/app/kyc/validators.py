"""
Deterministic validators used by the KYC checks: GSTIN format and checksum, OCR-confusion repair,
state codes, Udyam format, fuzzy name/address comparison, dates and masking.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime

from rapidfuzz import fuzz

GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
UDYAM_RE = re.compile(r"^UDYAM-([A-Z]{2})-(\d{2})-(\d{7})$")

# GST state codes (first two digits of a GSTIN)
GST_STATE_CODES = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh", "05": "Uttarakhand",
    "06": "Haryana", "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim",
    "12": "Arunachal Pradesh", "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura", "17": "Meghalaya",
    "18": "Assam", "19": "West Bengal", "20": "Jharkhand", "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh",
    "24": "Gujarat", "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "29": "Karnataka",
    "30": "Goa", "31": "Lakshadweep", "32": "Kerala", "33": "Tamil Nadu", "34": "Puducherry",
    "35": "Andaman and Nicobar Islands", "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}
# Udyam state abbreviations used in the synthetic pack (and the common ones)
UDYAM_STATE_ABBR = {
    "AP": "Andhra Pradesh", "AR": "Arunachal Pradesh", "AS": "Assam", "BR": "Bihar", "CG": "Chhattisgarh", "DL": "Delhi",
    "GA": "Goa", "GJ": "Gujarat", "HR": "Haryana", "HP": "Himachal Pradesh", "JK": "Jammu and Kashmir", "JH": "Jharkhand",
    "KA": "Karnataka", "KR": "Karnataka", "KL": "Kerala", "MP": "Madhya Pradesh", "MH": "Maharashtra", "MN": "Manipur",
    "ML": "Meghalaya", "MZ": "Mizoram", "NL": "Nagaland", "OD": "Odisha", "PB": "Punjab", "RJ": "Rajasthan", "SK": "Sikkim",
    "TN": "Tamil Nadu", "TS": "Telangana", "TG": "Telangana", "TR": "Tripura", "UP": "Uttar Pradesh", "UK": "Uttarakhand",
    "WB": "West Bengal",
}

# Characters that OCR (and humans) confuse. Letter slots in a GSTIN cannot hold digits and vice versa.
CONFUSIONS: dict[str, list[str]] = {
    "0": ["O", "D", "Q"], "O": ["0", "D", "Q"], "D": ["0", "O"], "Q": ["O", "0"],
    "1": ["I", "L"], "I": ["1", "L"], "L": ["1", "I"],
    "5": ["S"], "S": ["5"], "8": ["B"], "B": ["8"], "2": ["Z"], "Z": ["2"], "6": ["G"], "G": ["6"],
}


def today() -> date:
    """The README fixes 'today' for date checks at 2026-07-15. Overridable for tests."""
    return date.fromisoformat(os.environ.get("KYC_TODAY", "2026-07-15"))


# ---------------------------------------------------------------------------
# GSTIN
# ---------------------------------------------------------------------------
def gstin_checksum_ok(gstin: str) -> bool:
    if not GSTIN_RE.match(gstin or ""):
        return False
    total = 0
    for i, ch in enumerate(gstin[:14]):
        v = GSTIN_CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return GSTIN_CHARS[(36 - total % 36) % 36] == gstin[14]


def repair_gstin(raw: str) -> tuple[str | None, list[str]]:
    """
    Try to fix a GSTIN that fails format/checksum by swapping visually similar characters in slots
    whose type is known (digits at 0-1 and 7-10, letters at 2-6 and 11, 'Z' at 13).
    Returns (repaired or None, list of substitutions made). Only single-slot repairs are attempted
    per slot, and the result must pass the checksum.
    """
    g = (raw or "").strip().upper().replace(" ", "")
    if len(g) != 15:
        return None, []
    slot_type = ["d", "d", "a", "a", "a", "a", "a", "d", "d", "d", "d", "a", "x", "Z", "x"]
    fixed = list(g)
    subs: list[str] = []
    # 1. slot-type repairs: a digit in a letter slot (or vice versa) can only be a look-alike
    for i, t in enumerate(slot_type):
        ch = fixed[i]
        if t == "d" and not ch.isdigit():
            alt = next((a for a in CONFUSIONS.get(ch, []) if a.isdigit()), None)
        elif t == "a" and not ch.isalpha():
            alt = next((a for a in CONFUSIONS.get(ch, []) if a.isalpha()), None)
        elif t == "Z" and ch != "Z":
            alt = "Z" if "Z" in CONFUSIONS.get(ch, []) else None
        else:
            alt = None
        if alt:
            subs.append(f"position {i + 1}: {ch} -> {alt}")
            fixed[i] = alt
    candidate = "".join(fixed)
    if gstin_checksum_ok(candidate):
        return candidate, subs
    # 2. last resort: one look-alike swap anywhere that makes the checksum pass
    for i, ch in enumerate(candidate):
        for alt in CONFUSIONS.get(ch, []):
            trial = candidate[:i] + alt + candidate[i + 1:]
            if gstin_checksum_ok(trial):
                return trial, subs + [f"position {i + 1}: {ch} -> {alt}"]
    return None, subs


def gstin_state(gstin: str) -> str | None:
    return GST_STATE_CODES.get((gstin or "")[:2])


def pan_from_gstin(gstin: str) -> str:
    return (gstin or "")[2:12]


# ---------------------------------------------------------------------------
# Udyam
# ---------------------------------------------------------------------------
def udyam_parts(udyam: str) -> dict | None:
    m = UDYAM_RE.match((udyam or "").strip().upper())
    if not m:
        return None
    return {"state_abbr": m.group(1), "district": m.group(2), "serial": m.group(3), "state": UDYAM_STATE_ABBR.get(m.group(1))}


# ---------------------------------------------------------------------------
# text comparison
# ---------------------------------------------------------------------------
LEGAL_SUFFIXES = re.compile(r"\b(llp|pvt\.?|private|ltd\.?|limited|co\.?|company|and|&)\b", re.I)


def norm_text(s: str | None) -> str:
    s = (s or "").lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def name_similarity(a: str | None, b: str | None, ignore_suffixes: bool = False) -> int:
    """0-100 similarity between two business names."""
    na, nb = norm_text(a), norm_text(b)
    if ignore_suffixes:
        na, nb = LEGAL_SUFFIXES.sub(" ", na), LEGAL_SUFFIXES.sub(" ", nb)
        na, nb = re.sub(r"\s+", " ", na).strip(), re.sub(r"\s+", " ", nb).strip()
    if not na or not nb:
        return 0
    return int(fuzz.token_set_ratio(na, nb))


def address_similarity(a: str | None, b: str | None) -> int:
    """Addresses on the specimens are broken across lines; compare with spaces removed too."""
    na, nb = norm_text(a), norm_text(b)
    if not na or not nb:
        return 0
    joined = fuzz.ratio(na.replace(" ", ""), nb.replace(" ", ""))
    tokens = fuzz.token_set_ratio(na, nb)
    return int(max(joined, tokens))


def pincode(address: str | None) -> str | None:
    m = re.search(r"(\d{6})\s*$", (address or "").replace(" ", "")[-12:])
    return m.group(1) if m else None


def proprietor_from_legal_name(legal_name: str | None) -> tuple[str | None, str | None]:
    """'Neha Kaur (Prop. Vindhya Tours & Travels)' -> ('Neha Kaur', 'Vindhya Tours & Travels')."""
    m = re.match(r"^\s*(.+?)\s*\(\s*Prop\.?\s*(.+?)\s*\)\s*$", legal_name or "", re.I)
    if not m:
        return None, None
    return m.group(1).strip(), m.group(2).strip()


def person_similarity(a: str | None, b: str | None) -> int:
    na, nb = norm_text(a), norm_text(b)
    return int(fuzz.token_sort_ratio(na, nb)) if na and nb else 0


# ---------------------------------------------------------------------------
# dates
# ---------------------------------------------------------------------------
def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def days_old(value: str | None) -> int | None:
    d = parse_date(value)
    return (today() - d).days if d else None


# ---------------------------------------------------------------------------
# masking (UI and logs never see full identifiers)
# ---------------------------------------------------------------------------
def mask(value: str | None, keep_start: int = 2, keep_end: int = 3) -> str | None:
    if not value:
        return value
    v = str(value)
    if len(v) <= keep_start + keep_end:
        return "*" * len(v)
    return v[:keep_start] + "*" * (len(v) - keep_start - keep_end) + v[-keep_end:]


def mask_udyam(value: str | None) -> str | None:
    if not value:
        return value
    parts = udyam_parts(value)
    if not parts:
        return mask(value, 6, 2)
    return f"UDYAM-{parts['state_abbr']}-{parts['district']}-*****{parts['serial'][-2:]}"

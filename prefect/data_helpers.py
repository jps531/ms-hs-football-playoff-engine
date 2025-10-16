from __future__ import annotations

import re, unicodedata
from typing import Any, Dict, Mapping, Optional, Union
from bs4 import BeautifulSoup

from data_classes import School


# -------------------------
# Constants
# -------------------------

SPACE_RE = re.compile(r"\s+")


# One source of truth: "official" -> "AHSFHS canonical"
OFFICIAL_TO_AHSFHS: Dict[str, str] = {
    "D'Iberville": "DIberville",
    "St. Andrew's": "Saint Andrews Episcopal",
    "St. Stanislaus": "Saint Stanislaus",
    "St. Patrick": "Saint Patrick",
    "St. Martin": "Saint Martin",
    "Thomas E. Edwards": "Edwards",
    "M. S. Palmer": "Palmer",
    "J Z George": "George",
    "H. W. Byers": "Byers",
    "Itawamba Agricultural": "Itawamba AHS",
    "Forrest County Agricultural": "Forrest County AHS",
    "Amanda Elzy": "Elzy",
}
    
_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}


# --- REGIONS CLEANING CONFIG ---
CLEAN_PHRASES = [
    r"\bHigh School\b",
    r"\bHigh\b",
    r"\bSchool\b",
    r"\bPublic\b",
    r"\bMemorial\b",
    r"\bSecondary\b",
    r"\bHi Sch\b",
    r"\bSch\b",
    r"\bDist\b",
    r"\bMiddle\b",
    r"\bSenior\b",
    r"\bJr Sr\b",
    r"\bJr\s*[/\\-]?\s*Sr\b",
    r"\(5-12\)",
    r"\(9-12\)",
    r"\bAttendance Center\b",
    r"\bName\b",
    r"\bClass\b",
    r"\bRegion\b",
]

CLEAN_RE = re.compile("|".join(CLEAN_PHRASES), flags=re.IGNORECASE)


# -------------------------
# Helpers
# -------------------------


def to_normal_case(s: str) -> str:
    """
    Convert a string to normal case (title case with special handling for "Mc" and possessives like "'s").
    """
    if not s:
        return s
    t = s.title()
    t = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), t)
    t = re.sub(r"(['’])S\b", r"\1s", t)
    t = re.sub(r"\bDiber", "D'Iber", t)
    t = re.sub(r"\bSt\b(?!\.)", "St.", t)
    return t


def _norm(s: str) -> str:
    s = s.strip()
    s = s.replace("’", "'")
    s = SPACE_RE.sub(" ", s).strip()
    return s.lower()


def update_school_name_for_maxpreps_search(s: str) -> str:
    s = s.replace("Pearl River Central", "PRC")
    s = s.replace("Cleveland Central", "Cleveland")
    s = s.replace("Leake Central", "Carthage")
    s = s.replace("Thomas E. Edwards", "Ruleville")
    s = s.replace("Jefferson Co", "Jefferson County")
    s = s.replace("J Z George", "J.Z. George")
    s = s.replace("M. S. Palmer", "Palmer")
    s = s.replace("H. W. Byers", "Byers")
    s = s.replace("Leake County", "Leake")
    s = s.replace("Enterprise Clarke", "Enterprise Bulldogs")
    s = s.replace("Enterprise Lincoln", "Enterprise Yellowjackets")
    return s.lower()


def update_school_name_for_ahsfhs_search(s: str) -> str:
    """
    Convert an "official" school name to the AHSFHS search name if known.
    """
    s = s.strip()

    if s in OFFICIAL_TO_AHSFHS:
        return OFFICIAL_TO_AHSFHS[s]

    return s.replace(" ", "%20")


def get_school_name_from_ahsfhs(s: str) -> str:
    """
    Convert an AHSFHS canonical name to the "official" school name if known.
    """
    s = s.strip()

    for official_name, ahsfhs_name in OFFICIAL_TO_AHSFHS.items():
        if s == ahsfhs_name:
            return official_name

    return s


def as_float_or_none(x):
    """
    Convert x to float, or return None if x is None, empty, or invalid.
    """
    if x is None:
        return None
    if isinstance(x, str) and x.strip() == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _pad(n: int) -> str:
    return f"{n:02d}"


def _month_to_num(m: str) -> Optional[int]:
    m = m.lower().rstrip(".")
    return _MONTHS.get(m)


def _normalize_ws(t: str) -> str:
    # Unicode normalize and tame whitespace weirdness
    t = unicodedata.normalize("NFKC", t)
    t = t.replace("\r\n", "\n").replace("\r", "\n").replace("\u00A0", " ")
    # collapse 3+ newlines to 2 to avoid giant gaps
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t

def to_plain_text(html: str) -> str:
    # 1) parse HTML → text (inserts spaces between nodes)
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ")

    # 2) normalize unicode, convert NBSP to space, collapse whitespace
    text = unicodedata.normalize("NFKC", text).replace("\u00A0", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parseTextSection(text: str, start_phrase: str, end_phrase: str) -> str:
    """
    Extracts the section of text between start_phrase and end_phrase.
    Handles arbitrary whitespace and newlines gracefully.
    """

    # Convert phrases into regex patterns that allow flexible whitespace
    pattern = rf"{start_phrase}(.*?){end_phrase}"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    
    if not match:
        return ""
    
    return match.group(1).strip()


def _get_field(r: Union["School", Mapping[str, Any]], attr: str, alt_key: str | None = None):
    """Fetch attr from dataclass or mapping; falls back to alt_key for 'class' vs 'class_'."""
    if hasattr(r, attr):
        return getattr(r, attr)
    if isinstance(r, Mapping):
        if attr in r:
            return r[attr]
        if alt_key and alt_key in r:
            return r[alt_key]
    return None


def clean_school_name(raw: str) -> str:
    """
    Clean the given raw school name by removing unwanted phrases and normalizing case.
    """

    # Special cases: Differentiate Enterprises
    if raw == "ENTERPRISE SCHOOL":
        return "Enterprise Lincoln"
    elif raw == "ENTERPRISE HIGH SCHOOL":
        return "Enterprise Clarke"
    else:
        tmp = CLEAN_RE.sub("", raw)
        tmp = SPACE_RE.sub(" ", tmp).strip(" ,.-\u2013\u2014\t\r\n")
        return to_normal_case(tmp)
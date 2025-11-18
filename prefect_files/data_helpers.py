from __future__ import annotations

import re, unicodedata
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union
from bs4 import BeautifulSoup

from prefect_files.data_classes import RawCompletedGame, CompletedGame, School


# -------------------------
# Constants
# -------------------------

SPACE_RE = re.compile(r"\s+")


# One source of truth: "official" -> "AHSFHS canonical"
OFFICIAL_TO_AHSFHS: Dict[str, str] = {
    "D'Iberville": "DIberville",
    "St. Andrew’s": "Saint Andrews Episcopal",
    "O’Bannon": "OBannon",
    "St. Stanislaus": "Saint Stanislaus",
    "St. Patrick": "Saint Patrick",
    "St. Martin": "Saint Martin",
    "Thomas E. Edwards": "Thomas Edwards",
    "M. S. Palmer": "Palmer",
    "J Z George": "George",
    "H. W. Byers": "Byers",
    "Itawamba Agricultural": "Itawamba AHS",
    "Forrest County Agricultural": "Forrest County AHS",
    "Amanda Elzy": "Elzy",
    "Tupelo Christian": "Tupelo Christian Prep",
    "Jim Hill": "Hill",
    "French Camp": "French Camp Academy",
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
    if raw.lower() == "enterprise school":
        return "Enterprise Lincoln"
    elif raw.lower() == "enterprise high school":
        return "Enterprise Clarke"
    elif raw.lower() == "jefferson co high":
        return "Jefferson County"
    elif raw.lower() == "franklin high school":
        return "Franklin County"
    else:
        tmp = CLEAN_RE.sub("", raw)
        tmp = SPACE_RE.sub(" ", tmp).strip(" ,.-\u2013\u2014\t\r\n")
        return to_normal_case(tmp)
    

def normalize_pair(x: str, y: str) -> Tuple[str, str, int]:
    """
    Given two team names x and y, return a tuple (a, b, sign) where a <= b (lexicographically) and sign is +1 if x==a else -1.
    """
    return (x, y, +1) if x <= y else (y, x, -1)
    

def get_completed_games(raw_results: List[RawCompletedGame]) -> List[CompletedGame]:
    """
    Convert raw results dicts into CompletedGame dataclass instances.
    """

    # Deduplicate by *game* key (a,b,date) where a<b (lexicographic).
    # Prefer the row where school==a (lex-first) if it exists; otherwise use the b-row inverted.
    by_game: Dict[Tuple[str, str, str], Dict[str, int] | Tuple[str, ...]] = {}

    for result in raw_results:
        a, b, _sign = normalize_pair(result["school"], result["opponent"])  # a<b
        gkey = (a, b, result["date"])

        # Compute contributions from the perspective of team 'a' (lex-first)
        if result["school"] == a:
            # from a's row directly
            res_a = 1 if result["result"] == 'W' else (-1 if result["result"] == 'L' else 0)
            pd_a  = (result["points_for"] - result["points_against"]) if (result["points_for"] is not None and result["points_against"] is not None) else 0
            pa_a  = (result["points_against"] or 0)
            pa_b  = (result["points_for"] or 0)

            # Always prefer the a-row: overwrite any prior b-row for this (a,b,date)
            by_game[gkey] = {"res_a": res_a, "pd_a": pd_a, "pa_a": pa_a, "pa_b": pa_b, "has_a": 1}

        else:
            # row is from b's perspective; invert to 'a'
            res_a = -1 if result == 'W' else (1 if result == 'L' else 0)
            pd_a  = (-(result["points_for"] - result["points_against"])) if (result["points_for"] is not None and result["points_against"] is not None) else 0
            pa_a  = (result["points_for"] or 0)  # a allowed b's points_for
            pa_b  = (result["points_against"] or 0)  # b allowed a's points_for

            prev = by_game.get(gkey)
            # Only store if we don't already have an a-row for this game
            if not prev or (isinstance(prev, dict) and not prev.get("has_a")):
                by_game[gkey] = {"res_a": res_a, "pd_a": pd_a, "pa_a": pa_a, "pa_b": pa_b, "has_a": 0}

    # Now aggregate per pair (a,b) across dates (in case there were multiple meetings)
    pair_totals: Dict[Tuple[str, str], Dict[str, int]] = {}
    for (a, b, _date), vals in by_game.items():
        d = pair_totals.setdefault((a, b), {"res_a": 0, "pd_a": 0, "pa_a": 0, "pa_b": 0})
        d["res_a"] += vals["res_a"] # type: ignore
        d["pd_a"]  += vals["pd_a"] # type: ignore
        d["pa_a"]  += vals["pa_a"] # type: ignore
        d["pa_b"]  += vals["pa_b"] # type: ignore

    out: List[CompletedGame] = []
    for (a, b), v in pair_totals.items():
        # Collapse res_a to {-1, 0, +1} for the season series (win/loss/split from 'a' pov)
        res_a_sign = 1 if v["res_a"] > 0 else (-1 if v["res_a"] < 0 else 0)
        out.append(CompletedGame(a, b, res_a_sign, v["pd_a"], v["pa_a"], v["pa_b"]))

    return out
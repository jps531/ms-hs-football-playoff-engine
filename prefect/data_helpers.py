from __future__ import annotations
import re

# -------------------------
# Constants
# -------------------------

SPACE_RE = re.compile(r"\s+")

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